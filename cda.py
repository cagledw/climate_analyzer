"""
Climate Data Analysis, Download Data from NOAA Climate Data WebSite OR Launch tkinter GUI
Two options for Climate Data Download:
    -stations : write list of nearby stations to stdout
    -getcd    : download Historical Climate Data for specific Station to sqlite DB

Otherwise, launches GUI for analysis of data previously stored in sqlite DB.


"""

import re
import os
import copy
import numpy as np
from configparser import RawConfigParser

from glob import glob
from collections import namedtuple
from datetime import date, datetime, timedelta
from itertools import groupby, accumulate

from noaa import NOAA
# from noaa import noaa_aliases, get_noaa_id, get_stations, get_dataset_v1
from guiMain import guiMain
from guiPlot import dayInt2MMDD, dayInt2Label
from dbCoupler import dbCoupler, DBTYPE_CDO

user_dbPath = 'AppData\\ClimateData'


def print_stations(station_list):
    """ print station_list to std_out
    """
    for _s in station_list:
        sid = _s.id.split(':')
        if sid[0].upper() != 'GHCND':
            continue

        elev = f'{_s.elev * 3.28084:>4.0f}'
        print(f'{_s.id:17} {_s.dist2home:>4.1f}mi {elev} {_s.mindate.date()} {_s.maxdate.date()} {_s.name[:40]}')


def store_to_db(noaaObj: NOAA, dbPath: str, noaa_id, station_name):
    """ Download NOAA Climate Data from Web Portal & Store in SQLite DB
    """
    dbfName = os.path.join(dbPath, station_name + '.db')
    if os.path.isfile(dbfName):
        print('File Exists {}'.format(dbname))
        return

    noaa_info = noaaObj.get_station(noaa_id)

    dbMgr = dbCoupler()
    dbMgr.open(dbfName)
    for _yr in range(noaa_info.mindate.year, date.today().year + 1):
        start_date = date(_yr, 1, 1)
        cdList = noaaObj.get_dataset_v1(noaa_id, start_date)
        print(_yr, len(cdList))
        dbMgr.wr_cdtable(str(_yr), cdList)

    dbMgr.close()
    return None

def update_db(alias2id, updateDir, webAccessObj):
    """
     Scan for Climate DataBase Files in updateDir, and then check each for missing data.
     If missing data is found, attempt Download from NOAA & Update DB.
       Each sub-array of climate data has exactly 366 elements
       non-leap-year sub-array's are expected to be void for Feb-29 and are ignored.
       Only the two most recent years are checked.

    First, create 'void' list of isnan flags for each day.
    Then identify days that are all nan (void)
    """
    dbMgr = dbCoupler()

    dbMatch = os.path.join(dbDir, '*.db')
    updateFiles = [os.path.abspath(_f) for _f in glob(dbMatch)]

    for dbfName in updateFiles:
        s_alias = os.path.splitext(os.path.basename(dbfName))[0]
        s_id = alias2id[s_alias]
        print(s_alias, s_id, dbfName)

        dbMgr.open(dbfName)
        yrList, np_climate_data, missing_data = dbMgr.rd_climate_data()

        # Loop Over All Years, climate data is 2D array of records [yrs, days]
        for _yrenum in range(np_climate_data.shape[0]):
            chkyear = yrList[_yrenum]

            void = [np.all([np.isnan(x) for x in y]) for y in np_climate_data[_yrenum, :]]
            isnan_grpsize = [(_k, sum(1 for _ in _v)) for _k, _v in groupby(void)]
            isnan_dayenum = [0] + list(accumulate([x[1] for x in isnan_grpsize]))
            assert isnan_dayenum[-1] == np_climate_data.shape[1]   # the sum of all grp elements should == 366

            # isnan_grpsize is list of tuples: [(bool, int), ...], those with bool == True are all nan values
            for _grpidx, _isnan_grp in enumerate(isnan_grpsize):
                dayenum = isnan_dayenum[_grpidx]
                dayMMDD = dayInt2MMDD(dayenum)

                ismissing = _isnan_grp[0]
                nummissing = _isnan_grp[1]
                if ismissing:
                    if dayMMDD == (2,29) and nummissing == 1 and not dbMgr.is_leap_year(chkyear):
                        continue

                    update_day = date(chkyear, *dayMMDD)
                    print(f'    Missing {nummissing} days, starting @ {update_day}')

                    update_vals = webAccessObj.get_dataset_v1(s_id, update_day)

                    if not update_vals:
                        print('    No Updates for {}'.format(update_day))
                    else:
                        for _val in update_vals:
                            info = ', '.join([f'{_k}:{_v}' for _k, _v in _val._asdict().items() if _k != 'date'])
                            print('    Add {}: '.format(_val.date) + info)

                        dbMgr.wr_cdtable(str(chkyear), update_vals)

        chkyear = date.today().year
        if chkyear not in yrList:
            print(chkyear)

            update_day = date(chkyear, *dayInt2MMDD(0))     # Jan 1
            update_vals = get_dataset_v1(station_id, update_day)
            print(station_id, update_day)

            if not update_vals:
                print('  No Updates for {}'.format(update_day))

            else:
                for _val in update_vals:
                    print(_val._asdict())

                dbMgr.wr_cdtable(str(chkyear), update_vals)
        dbMgr.close()
    return updateFiles

    # for dbfName in dbList:
    #     station_name = os.path.splitext(os.path.basename(dbfName))[0]
    #     station_id = get_noaa_id(station_name)
    #     print(f'    Checking {station_name}, {station_id}')
    #
    #     dbMgr.open(dbfName)
    #     yrList, np_climate_data, missing_data = dbMgr.rd_climate_data()


def get_appCfg(iniFilePath):
    config = RawConfigParser(allow_no_value=True)
    try:
        with open(iniFilePath) as rfp:
            config.read(iniFilePath)
    except IOError:
        config['Paths'] = {}
        config['Paths']['dbDir'] = os.path.join("%USERPROFILE%", user_dbPath)

        config['NOAA'] = {}
        config['NOAA']['cdo_token'] = ''
        config['NOAA']['fips_loc'] = 'FIPS:53033'
        config['NOAA']['lat_long'] = str((47.60923, -122.16787))

        config['Stations'] = {}
        with open(iniFilePath, 'w') as fp:
            config.write(fp)
        fp.close()

    return config


if __name__ == '__main__':

    # INI File Specifies critical parameters - cdo_token MUST BE SUPPLIED!
    iniPath = os.path.splitext(__file__)[0] + '.ini'
    appCfg = get_appCfg(os.path.join(iniPath))
    dbDir = os.path.expandvars(appCfg['Paths']['dbDir'])
    cdo_token = appCfg['NOAA']['cdo_token']

    if not cdo_token:
        print(f'Error: {iniPath} must supply a cdo_token')
        print('See: https://www.ncdc.noaa.gov/cdo-web/token')

    else:
        import argparse
        parser = argparse.ArgumentParser(description='  \033[32mDownload and Analyze NOAA Climate Data\n'
                                                     '  Station Alias and ID must configured in cda.ini\n'
                                                     '  Use -show_ids to display configured stations\n'
                                                     '  Use -find_ids to display local stations\033[37m',
                                         formatter_class=argparse.RawTextHelpFormatter)

        group = parser.add_mutually_exclusive_group()

        group.add_argument('-find_ids', action='store_true', default=False,
                           help='[arg1] - Display Stations within [arg1] distance')
        group.add_argument('-show_ids', action='store_true', default=False,
                           help='[arg1] - Display Stations within [arg1] distance')
        group.add_argument('-getcd', action='store_true', default = False,
                           help='[arg1] - Get Climate Data for station [arg1]')
        parser.add_argument('arg1', action='store', nargs='?', default=None)
        args = parser.parse_args()

        noaaObj = NOAA(dict(appCfg['NOAA']))     # NOAA Obj provided with dict from ini file
        station_dict = dict(appCfg['Stations'])  # ini file provides dict of alias:station_id
        if args.find_ids:
            dist2home = float(args.arg1) if args.arg1 is not None else 30.0
            print_stations(noaaObj.get_stations(dist2home))

        elif args.show_ids:
            print('{:^20}{:^16}'.format('alias', 'station_id'))
            for _k, _v in appCfg['Stations'].items():
                print(f'{_k:20}: {_v}')

        elif args.getcd:

            if args.arg1 is None:
                station_info = '\n'.join(['    ' + x for x in noaa_aliases()])
            else:
                try:
                    station_id = appCfg['Stations'][args.arg1]

                except KeyError:
                    parser.error('[arg1] must supply station alias:\n' + station_info)
                    station_id = None

                if station_id:
                    store_to_db(noaaObj, dbDir, station_id, args.arg1)
                else:
                    raise ValueError
        else:
            dbFiles = update_db(station_dict, dbDir, noaaObj)

            gui = guiMain(dbFiles, (800, 100))  # Gui Setup
            gui.mainloop()
