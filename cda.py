"""
Climate Data Analysis.
  Download Data from NOAA Climate Data WebSite and/or Launch tkinter GUI
  Only Data for locations defined in this Apps's Config (*.ini) File can be downloaded

  Three options for Climate Data Download:
    -find : Display Stations and their ID within certain distance of 'Home'
    -station  : Display Stations whose ID is known
    -getcd    : download Historical Climate Data for specific Station to sqlite DB

  Otherwise, launches GUI for analysis of daa previously stored in sqlite DB.

"""

import re
import os
import sys
import copy
import logging
import numpy as np
from configparser import RawConfigParser

from glob import glob
# from collections import namedtuple
from datetime import date, datetime, timedelta
from itertools import groupby, accumulate

from noaa import NOAA
from guiMain import guiMain
from guiPlot import dayInt2MMDD, dayInt2Label, date2enum
from dbCoupler import dbCoupler, DBTYPE_CDO

dbName = 'fips_codes.db'
user_dbPath = 'AppData\\ClimateData'

def QueryStdIO(prompt):
    inp = None
    while inp is None:
        inp = input(prompt + "->")
        if not inp:
            return None

        try:
            choiceInt = int(inp)
            return choiceInt
        except:
            pass

def print_stations(station_list):
    """ print station_list to std_out
    """
    print(f'{"stations_id":^15} {"dist2home":^10} {"elev":^6} {"1st Date":^10} {"last Date"}')
    for _s in station_list:
        sid = _s.id.split(':')
        if sid[0].upper() != 'GHCND':
            continue

        elev = f'{_s.elev:>4.0f}'
        print(f'{_s.id:17} {_s.dist2home:>4.1f}mi {elev:>6}ft {_s.mindate.date()} {_s.maxdate.date()} {_s.name[:40]}')

def find_fipcode(state, locale=None):
    dbfName = os.path.join(os.path.dirname(__file__), dbName)

    dbMgr = dbCoupler()
    dbMgr.open(dbfName)
    fipList = dbMgr.find_rgn_by_state_and_locale(state, locale)
    dbMgr.close()

    return fipList

def find_region_bycode(code):
    dbfName = os.path.join(os.path.dirname(__file__), dbName)

    dbMgr = dbCoupler()
    dbMgr.open(dbfName)
    fipList = dbMgr.find_rgn_by_code(code)
    dbMgr.close()

    region = fipList.pop()
    if fipList:
        raise ValueError   # Only 1 Expected
    return region

def store_to_db(noaaObj: NOAA, dbPath: str, noaa_id, station_name):
    """ Download NOAA Climate Data from Web Portal & Store in SQLite DB
    """
    dbfName = os.path.join(dbPath, station_name + '.db')
    if os.path.isfile(dbfName):
        print('File Exists {}'.format(dbfName))
        return

    error, noaa_info = noaaObj.station_info(noaa_id)
    if error:
        print(str(err))
        return

    dbMgr = dbCoupler()
    dbMgr.open(dbfName)
    for _yr in range(noaa_info.mindate.year, date.today().year + 1):
        start_date = date(_yr, 1, 1)
        cdList = noaaObj.get_dataset_v1(noaa_id, start_date)
        print(_yr, len(cdList))
        dbMgr.wr_cdtable(str(_yr), cdList)

    dbMgr.close()

def update_db(alias2id, updateDir, webAccessObj, upd_yrs, verbose=False):
    """
     Scan for Climate DataBase Files in updateDir, and then check each for missing data.
     If missing data is found, attempt Download from NOAA & Update DB.
       Each sub-array of climate data has exactly 366 elements
       non-leap-year sub-array's are expected to be void for Feb-29 and are ignored.
       Only the years now - upd_yrs are checked.

     Returns: list of dbFiles discovered
    """
    dayenumLim, yrLim = date2enum(date.today())     # Update Scan Limit

    upd_fldNames = [_name for _name in DBTYPE_CDO._fields if _name != 'date']
    dbMgr = dbCoupler()

    dbMatch = os.path.join(dbDir, '*.db')
    updateFiles = [os.path.abspath(_f) for _f in glob(dbMatch)]
    for dbfName in updateFiles:
        s_alias = os.path.splitext(os.path.basename(dbfName))[0]
        s_id = alias2id[s_alias]

        dbMgr.open(dbfName)
        yrList, np_climate_data, missing_data = dbMgr.rd_climate_data()
        print(f'  {s_alias:10} Years: {yrList[0]} - {yrList[-1]}')

        if yrList[-1] != date.today().year:
            yrList.append(date.today().year)

        # Loop Over All Years, climate data is 2D array of records [yrs, days]
        stationStatusDict = {}
        for _yrenum in range(np_climate_data.shape[0] - upd_yrs, np_climate_data.shape[0]):
            chkyear = yrList[_yrenum]
            yrstatus = {'Valid': 0, 'Partial': 0, 'Missing': 0}

            new_indx = 0
            new_vals = None

            # Find db rows with ANY missing data
            void = [np.any([np.isnan(x) for x in y]) for y in np_climate_data[_yrenum, :]]
            isnan_grpsize = [(_k, sum(1 for _ in _v)) for _k, _v in groupby(void)]
            isnan_dayenum = [0] + list(accumulate([x[1] for x in isnan_grpsize]))
            assert isnan_dayenum[-1] == np_climate_data.shape[1]   # the sum of all grp elements should == 366

            for _grpidx, _isnan_grp in enumerate(isnan_grpsize):
                ismissing = _isnan_grp[0]
                nummissing = _isnan_grp[1]

                dayenum = isnan_dayenum[_grpidx]
                if _yrenum == len(yrList) - 1 and dayenum == dayenumLim:      # yrenum, dayenum past today?
                    break

                if not ismissing:
                    yrstatus['Valid'] += nummissing
                    continue

                while nummissing:
                    if dayenum == 59 and not dbMgr.is_leap_year(chkyear):     # Skip Feb29 if not LeapYear
                        dayenum += 1
                        nummissing -= 1
                        continue

                    current_vals = [np_climate_data[_yrenum, dayenum][_fld]   # This day's current Climate Data
                                    for _fld in upd_fldNames]
                    current_isnan = [np.isnan(x) for x in current_vals]

                    if new_vals is None:
                        new_vals = webAccessObj.get_dataset_v1(s_id, date(chkyear, 1, 1))

                    missingDate = date(chkyear, *dayInt2MMDD(dayenum))
                    while True:
                        newCDO_date = date.fromisoformat(new_vals[new_indx].date)
                        if newCDO_date >= missingDate or new_indx + 1 >= len(new_vals):
                            break
                        else:
                            new_indx += 1

                    if newCDO_date == missingDate:                           # New Download Date Matches Missing
                        newcd_vals = [getattr(new_vals[new_indx], _fld)
                                      for _fld in upd_fldNames]

                        new_isvalid = [bool(_value) for _value in newcd_vals]
                        isnan_and_isvalid = [all(test_tuple) for test_tuple in zip(new_isvalid, current_isnan)]

                        if all(new_isvalid):
                            yrstatus['Valid'] += 1
                        else:
                            yrstatus['Partial'] += 1

                        info = ', '.join([f'{_fld}:{_val}' for _change, _fld, _val
                                          in zip(isnan_and_isvalid, upd_fldNames, newcd_vals) if _change])

                        if all(current_isnan):
                            loginfo = 'AddNew'
                            dbMgr.add_climate_data(str(missingDate.year), [new_vals[new_indx]])

                        elif any(isnan_and_isvalid):
                            loginfo = 'Revise'
                            upd_dict = dict([(_k, _v) for _k, _v in zip(upd_fldNames, newcd_vals) if _v])
                            # upd_dict = dict(zip(upd_fldNames, newcd_vals))
                            dbMgr.upd_climate_data(str(missingDate.year),
                                                   {'date': missingDate.isoformat()},
                                                   upd_dict)
                        else:
                            loginfo = None

                        if loginfo:
                            ClimateData_log.info(f'{loginfo} {s_alias:10} {missingDate} {info}')
                    else:
                        if all(current_isnan):
                            yrstatus['Missing'] += 1
                        else:
                            yrstatus['Partial'] += 1

                    dayenum += 1
                    nummissing -= 1

                    if _yrenum == np_climate_data.shape[0] - 1 and dayenum > dayenumLim:
                        break
            stationStatusDict[chkyear] = yrstatus

        for _yr, _stat in stationStatusDict.items():
            print(f'{_yr:>19}: ' + ','.join(f'{_k}:{_v:>3}' for _k, _v in _stat.items()))

        dbMgr.close()
    return updateFiles

def get_appCfg(iniFilePath: str) -> RawConfigParser:
    """ Attempt to Open a Configuration iniFile and create one if Non-Existent
    """
    config = RawConfigParser(allow_no_value=True)
    try:
        with open(iniFilePath) as rfp:
            config.read(iniFilePath)
    except IOError:
        config['Paths'] = {}
        config['Paths']['dbDir'] = os.path.join("%USERPROFILE%", user_dbPath)

        config['NOAA'] = {}
        config['NOAA']['cdo_token'] = ''
        config['NOAA']['findrgn'] = '53033'
        config['NOAA']['home'] = str((47.60923, -122.16787))
        config['NOAA']['date_1st'] = '2000-01-01'
        config['NOAA']['date_last'] = 'now'
        config['NOAA']['upd_yrs'] = '2'

        config['Stations'] = {}
        with open(iniFilePath, 'w') as fp:
            fp.write(';  Climate Data Analysis Configuration\n')
            fp.write(';  Obtain cdo_token from https://www.ncdc.noaa.gov/cdo-web/token\n')
            fp.write(';  [Stations] Must Be Populated In Order to Download their Climate Data\n')
            fp.write(';     <alias> = <id>            # <alias> may be any convenient string\n')
            fp.write(';\n')
            fp.write(';  -find uses <code>, <home>, <date_1st>, <date_last>\n')

            config.write(fp)
        fp.close()
    return config

def save_appCfg(cfgParser: RawConfigParser, iniFilePath: str):
    try:
        with open(iniFilePath, 'w') as wfp:
            cfgParser.write(wfp)

    except IOError:
        print('Error')

class cdaLogFilter(logging.Filter):
    def filter(self, record):
        test = record.module == __file__
        return test 


if __name__ == '__main__':

    # INI File Specifies critical parameters - cdo_token MUST BE SUPPLIED!
    iniPath = os.path.splitext(__file__)[0] + '.ini'
    appCfg = get_appCfg(os.path.join(iniPath))
    dbDir = os.path.expandvars(appCfg['Paths']['dbDir'])
    cdo_token = appCfg['NOAA']['cdo_token']

    # Logging
    logPath = os.path.join(dbDir, 'DownLoads.log')
    ClimateData_log = logging.getLogger(__name__)
    ClimateData_log.setLevel(logging.INFO)
    ClimateData_fmtr = logging.Formatter('%(asctime)s %(message)s', "%Y-%m-%d %H:%M")

    fh = logging.FileHandler(logPath, mode='a')
    fh.setLevel(logging.INFO)
    fh.setFormatter(ClimateData_fmtr)
    ClimateData_log.addHandler(fh)

    # Command Line Processing
    if not cdo_token:
        print(f'Error: {iniPath} must supply a cdo_token')
        print('See: https://www.ncdc.noaa.gov/cdo-web/token')

    else:
        import argparse
        parser = argparse.ArgumentParser(description='  \033[32mDownload and Analyze NOAA Climate Data\n'
                                                     '  Station Alias and ID must configured in cda.ini\n'
                                                     '\n'
                                                     '  -find    download station info from NOAA in region <FIPSRGN>\n'
                                                     '  -home    set/show <LAT,LONG> used by find\n'
                                                     '  -findrgn set/show region <FIPSRGN> used by find\n'
                                                     '  -station show configured stations from ini-file\033[37m',
                                         formatter_class=argparse.RawTextHelpFormatter)
        group = parser.add_mutually_exclusive_group()

        group.add_argument('-find', action='store_true', default=False,
                           help='[radius]  - Download NOAA Weather Stations Info within [radius] of <HOME>')
        group.add_argument('-findrgn', action='store_true', default=False,
                           help='[state]   - Display or Set FIPS Region <FIPSRGN> used by find')
        group.add_argument('-home',  action='store_true', default=False,
                           help='[lat,long]- Display or Set <HOME> lat,long used by find')
        group.add_argument('-getcd', action='store_true', default=False,
                           help='[alias]   - Download all available Climate Data for station [alias]')
        parser.add_argument('arg1', action='store', nargs='?', default=None)
        group.add_argument('-station', action='store_true', default=False,
                           help='          - Display info on configured stations from ini-file')
        args = parser.parse_args()

        noaaObj = NOAA(dict(appCfg['NOAA']))     # NOAA Obj provided with dict from ini file
        station_dict = dict(appCfg['Stations'])  # ini file provides dict of alias:station_id

        if args.find:
            dist2home = float(args.arg1) if args.arg1 is not None else 30.0
            err, station_list = noaaObj.get_stations(dist2home)
            if err:
                print(err)
            else:
                print_stations(station_list)
                print(f'home @ {appCfg["NOAA"]["home"]}')

        elif args.findrgn:
            if not args.arg1:
                rgnInfo = find_region_bycode(noaaObj.findrgn)
                print(f'code {noaaObj.findrgn} = {rgnInfo.state}, {rgnInfo.region} {rgnInfo.qualifier}')
            else:
                item = None
                fipItems = find_fipcode(*args.arg1.split(','))
                while item is None:
                    for _cnt, _metaData in enumerate(fipItems):
                        print(f'  [{_cnt:>2d}]  {_metaData.region} {_metaData.qualifier}')
                    index = QueryStdIO('Select Region')
                    try:
                        item = fipItems[index]

                    except IndexError:
                        print('  Invalid, Requires Integer 0:{}'.format(len(fipItems)))
                        continue
                    appCfg['NOAA']['code'] = f'{item.code:05d}'
                    save_appCfg(appCfg, iniPath)
                    print(f'  {item.state}, {item.region} {item.qualifier} = {appCfg["NOAA"]["code"]}')

        elif args.home:
            if not args.arg1:
                print(f'home {noaaObj.home}')
            else:
                lat_long = args.arg1.strip('()').split(',')
                print(lat_long)
                try:
                    new_home = [float(x) for x in lat_long]
                    new_cfg = '(' + ','.join(['{:.5f}'.format(x) for x in new_home]) + ')'
                    appCfg['NOAA']['home'] = new_cfg
                    save_appCfg(appCfg, iniPath)

                except Exception as err:
                    print(err)

        elif args.station:
            print('{:^20}{:^20}{:^18}{:^14}{:^10}'.format(
                'alias', 'station_id', 'lat_long', 'dist2home', 'elev'))

            for _alias, _sid in appCfg['Stations'].items():
                cfgInfo = f'{_alias:20}: {_sid}'

                err, metaData = noaaObj.station_info(_sid)
                if err:
                    infoStr = str(err)
                else:
                    infoStr = (','.join([f'{x:3.3f}' for x in metaData.lat_long])
                               + f'  {metaData.dist2home:> 6.1f} mi'
                               + f'  {metaData.elev:> 7.1f} ft')
                print(cfgInfo, f'  {infoStr}')
            print(f'home @ {appCfg["NOAA"]["home"]}')

        elif args.getcd:
            if args.arg1 is None:
                station_info = '\n'.join(['    ' + x for x in noaa_aliases()])
            else:
                try:
                    station_id = appCfg['Stations'][args.arg1]

                except KeyError:
                    parser.error('[arg1] must supply station alias:\n'
                                 + '\n'.join(station_dict.keys()))
                    station_id = None

                if station_id:
                    store_to_db(noaaObj, dbDir, station_id, args.arg1)
                else:
                    raise ValueError
        else:
            upd_yrs = int(appCfg['NOAA']['upd_yrs'])
            dbFiles = update_db(station_dict, dbDir, noaaObj, upd_yrs)

            gui = guiMain(dbFiles, (800, 100))  # Gui Setup
            gui.mainloop()
