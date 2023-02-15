""" DataBase Interface Class provides methods to write/read formated data to sqlite3

   The SQLite3 API uses strings to define each table structure and to rd/wr rows to a table.
   Two strings are req'd for each tbl 'type': A Definition (DEF) and Command (CMD).

   Example DEF: '(rowid     INTEGER PRIMARY KEY,
                  conceptID INTEGER NOT NULL,
                  treedepth INTEGER NOT NULL,
                  weight    REAL,
                  balance   TEXT,
                  factIDs   BLOB); '

   Example CMD: '(rowid, conceptID, treedepth, weight, balance, factIDs) VALUES(?,?,?,?,?,?)'
"""
import os
import array
import sqlite3
import numpy as np

from datetime import date
from typing import List
from collections import namedtuple

# Climate Data Observation
DBDEF_FIP = [('code',        'INTEGER' 'PRIMARY KEY'),
             ('state',       'TEXT'),
             ('region',      'TEXT'),
             ('qualifier',   'TEXT')]

DBDEF_CDO = [('date',        'TEXT'    'PRIMARY KEY'),
             ('tmax',        'REAL'),
             ('tmin',        'REAL'),
             ('tavg',        'REAL'),
             ('prcp',        'REAL'),
             ('snow',        'REAL'),
             ('snwd',        'REAL')]

DBTYPE_FIP = namedtuple('DBTYPE_FIP',[x[0] for x in DBDEF_FIP], defaults=(-1, '', ''))
DBTYPE_CDO = namedtuple('DBTYPE_CDO', [x[0] for x in DBDEF_CDO],  defaults=('',) +  (float('nan'),)*6)

CDFLDS_NODATE = [x for x in DBTYPE_CDO._fields if x != 'date']   # field names of Climate Data Only, No Date
CD_NODATE_NPDT = np.dtype([(_key, np.float32) for _key in CDFLDS_NODATE])
DB_DEFINES = {'DBDEF_CDO': DBDEF_CDO, 'DBDEF_FIP': DBDEF_FIP}                 # dbCoupler.__init__() uses to set cmd/def strings


class dbCoupler:

    @staticmethod
    def newTableCmd(tblName, tblDef):
        return 'CREATE TABLE IF NOT EXISTS \"{}\" {}'.format(tblName, tblDef)

    @staticmethod
    def wrRowCmd(tblName, tblRow):
        return 'INSERT INTO \"{}\" {}'.format(tblName, tblRow)

    @staticmethod
    def addRowCmd(tblName, tblRow):
        return 'INSERT OR FAIL INTO \"{}\" {}'.format(tblName, tblRow)

    @staticmethod
    def updRowCmd(tblName, whereDict, setDict):
        whereText = ','.join('{} = {}'.format(_k, _v) for _k, _v in whereDict.items())
        return 'UPDATE {} SET '.format(tblName, whereText)

    @staticmethod
    def repRowCmd(tblName, tblRow):
        return 'INSERT OR REPLACE INTO {}{}'.format(tblName, tblRow)

    @staticmethod
    def findCmd(tblName, key_val1, key_val2):
        # cmd = 'SELECT * FROM FIP_CODES WHERE state = "WA"'
        cmd = 'SELECT * FROM {} WHERE {} = "{}"'.format(tblName, key_val1[0], key_val1[1])
        # if key_val2:
        #     cmd += 'AND {} = {}'.format(*key_val2)
        return cmd

    @staticmethod
    def is_leap_year(year):
        return year % 4 == 0 and (year % 100 != 0 or year % 400 == 0)

    @staticmethod
    def mmdd2enum(month, day):
        mm2days = [31, 29, 31, 30, 31, 30, 31, 31, 30, 31, 30, 31]
        return sum(mm2days[:month-1]) + day-1

    @property
    def table_names(self):
        self.cursor.execute("SELECT name FROM sqlite_master WHERE type='table';")
        return [x[0] for x in self.cursor.fetchall()]

    def __init__(self):
        """ Create strings for sqlite3 DB Operations.
            Each Table needs 2 strings:
              DEF = (<field1> <type1> <option1>, <field2> <type2> <option2>, ...)
              CMD = (<field1>, <field2> ...) VALUES(?, ?, ..)
        """

        self.dbFileName = None
        self.conn = None
        self.cursor = None

        for _key, _pydef in DB_DEFINES.items():
            _dbdef = '(' + ','.join([' '.join(x) for x in _pydef]) + ');'
            setattr(self, _key, _dbdef)

            _dbcmd = '(' + ','.join([x[0] for x in _pydef]) + ')'
            _dbcmd += ' VALUES(' + ','.join('?' for _ in range(len(_pydef))) + ')'
            _cmdattr = _key.replace('DEF', 'CMD')
            setattr(self, _cmdattr, _dbcmd)

    def open(self, dbFileName):
        """ sqlite3 will always create a database file if it doesn't exist
            filemode = rwc.  There is no way to force it NOT to create!
        """
        if self.dbFileName is not None and self.dbFileName != dbFileName:
            raise Exception('dbCoupler Multiple Open Files')

        dbDirectory = os.path.dirname(dbFileName)
        if not os.path.exists(dbDirectory):
            os.mkdir(dbDirectory)

        self.dbFileName = dbFileName
        self.conn = sqlite3.connect(dbFileName)

        self.conn.execute('PRAGMA foreign_keys = 1')
        self.cursor = self.conn.cursor()

    def close(self):
        self.conn.close()
        self.cursor = None
        self.dbFileName  = None

    def rd_climate_data(self):
        """ Read Climate Data from SQLite DB & return as (LIST_OF_YRS,NUMPY_2D_Array)
            NUMPY_2D is structured as [yr, day_of_yr] of dtype CD_NODATE_NPDT
        """

        # A list of years and 2D Array initialized to nan
        tbl_years = [int(x) for x in self.table_names]
        cd_by_year = np.full((len(tbl_years), 366), np.nan, dtype = CD_NODATE_NPDT)
        missing_data = {}

        for tblnum, _yr in enumerate(tbl_years):
            cdtbl = self.rd_cdtable(_yr)   # _yr is int here, latter converted to str

            for _count, _cdrec in enumerate(cdtbl):
                mmdd = getattr(_cdrec, 'date').split('-')
                recnum = dbCoupler.mmdd2enum(*[int(x) for x in mmdd[1:]])
                cdvals = [getattr(_cdrec, x) for x in CDFLDS_NODATE]

                cd_by_year[tblnum, recnum] = tuple([np.nan if type(x) is str else np.float32(x) for x in cdvals])

            # Data Sanity Check
            if (_count == 365 and dbCoupler.is_leap_year(_yr)) or \
              (_count == 364 and not dbCoupler.is_leap_year(_yr)):
                continue
            missing_data[_yr] = (_count, _cdrec.date)
            # print(f'  !{_yr} Missing Data! Records Read = {_count}, Last Data = {_cdrec.date}')

        return tbl_years, cd_by_year, missing_data

    #-----   FIP TABLE   -------
    def find_fip_by_state_and_region(self, val1, val2=None):
        """
        """
        key_val1 = ('state', val1.upper())
        key_val2 = ('region', val2) if val2 else None
        tblName = 'FIP_CODES'
        cmd = dbCoupler.findCmd(tblName, key_val1, key_val2)

        self.cursor.execute(cmd)
        # return self.cursor.fetchall()
        return list(map(DBTYPE_FIP._make, self.cursor.fetchall()))

    def wr_fiptable(self, tblName, key, value):
        """ tblItemList = listOf(CONCEPTDETAILS)
        """
        cmd = dbCoupler.newTableCmd(tblName, self.DBDEF_FIP)
        self.cursor.execute(cmd)

        cmd = dbCoupler.wrRowCmd(tblName, self.DBCMD_FIP)

        for _rowid, row in enumerate(tblItemList):
            row_data = [getattr(row, _f) for _f in DBTYPE_FIP._fields]
            self.cursor.execute(cmd, row_data)
        self.conn.commit()

    # -----CLIMATE DATA TABLE -------
    def wr_cdtable(self, tblName, tblItemList):
        """ tblItemList = listOf(CONCEPTDETAILS)
        """
        cmd = dbCoupler.newTableCmd(tblName, self.DBDEF_CDO)
        self.cursor.execute(cmd)

        cmd = dbCoupler.wrRowCmd(tblName, self.DBCMD_CDO)

        for _rowid, row in enumerate(tblItemList):
            row_data  = [getattr(row, _f) for _f in DBTYPE_CDO._fields]
            self.cursor.execute(cmd, row_data)
        self.conn.commit()

    def rd_cdtable(self, tblName):
        self.cursor.execute('SELECT ' + ','.join(DBTYPE_CDO._fields) +
                            ' FROM "{}"'.format(tblName))
        return map(DBTYPE_CDO._make, self.cursor.fetchall())

    def add_climate_data(self, tblName, tblItemList):
        """ Add rows to an existing table, fail on overwrite of existing key
        """
        cmd = dbCoupler.addRowCmd(tblName, self.DBCMD_CDO)

        for _rowid, row in enumerate(tblItemList):
            row_data  = [getattr(row, _f) for _f in DBTYPE_CDO._fields]
            self.cursor.execute(cmd, row_data)
        self.conn.commit()
