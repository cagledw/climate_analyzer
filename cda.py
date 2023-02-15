"""
Climate Data Analysis.
  Download Data from NOAA Climate Data WebSite and/or Launch tkinter GUI
  Only Climate Data for locations this Apps's Configuration (*.ini) File can be downloaded

  Three options for Climate Data Download:
    -find_ids : Display Stations and their ID within certain distance of 'Home'
    -show_ids : Display Stations whose ID is known
    -getcd    : download Historical Climate Data for specific Station to sqlite DB

  Otherwise, launches GUI for analysis of data previously stored in sqlite DB.


"""

import re
import os
import sys
import copy
import numpy as np
from configparser import RawConfigParser

from glob import glob
# from collections import namedtuple
from datetime import date, datetime, timedelta
from itertools import groupby, accumulate

from noaa import NOAA
from guiMain import guiMain
from guiPlot import dayInt2MMDD, dayInt2Label
from dbCoupler import dbCoupler, DBTYPE_CDO

fip_dbName = 'fip_codes.db'
user_dbPath = 'AppData\\ClimateData'

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
        config['NOAA']['fip_code'] = '53033'
        config['NOAA']['home_lat_long'] = str((47.60923, -122.16787))

        config['Stations'] = {}
        with open(iniFilePath, 'w') as fp:
            fp.write(';  Climate Data Analysis Configuration\n')
            fp.write(';  Obtain cdo_token from https://www.ncdc.noaa.gov/cdo-web/token\n')
            fp.write(';  Lookup FIPS State+County Codes @ \n')
            fp.write(';     https://en.wikipedia.org/wiki/List_of_United_States_FIPS_codes_by_county\n')
            config.write(fp)
        fp.close()
    return config

def save_appCfg(cfgParser, iniFilePath: str):
    try:
        with open(iniFilePath, 'w') as wfp:
            cfgParser.write(wfp)

    except IOError:
        print('Error')

def find_fipcode(state, region=None):
    dbfName = os.path.join(os.path.dirname(__file__), fip_dbName)

    dbMgr = dbCoupler()
    dbMgr.open(dbfName)
    fipList = dbMgr.find_fip_by_state_and_region(state, region)
    dbMgr.close()

    return fipList


def find_region(state, region=None):
    print(state, region)
    return None

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
                                                     '\n'
                                                     '  -find_ids to download station info from NOAA in region <FIPCODE>\n'
                                                     '  -fipcode  to show/set region used by find_ids\n'
                                                     '  -config   to display configured stations in ini-file\033[37m',
                                         formatter_class=argparse.RawTextHelpFormatter)
        group = parser.add_mutually_exclusive_group()

        group.add_argument('-find_ids', action='store_true', default=False,
                           help='[radius] - Download NOAA Weather Station IDs within [radius] distance')
        group.add_argument('-fipcode',  action='store_true', default=False,
                           help='[state]   - Display or Set <FIPCODE> used by find_ids')
        group.add_argument('-home',  action='store_true', default=False,
                           help='[state]   - Display or Set <HOME> lat,long used by find_ids')
        group.add_argument('-getcd', action='store_true', default=False,
                           help='[alias]   - Download all available Climate Data for station [alias]')
        parser.add_argument('arg1', action='store', nargs='?', default=None)
        group.add_argument('-config', action='store_true', default=False,
                           help='         - Display info on configured stations from ini-file')
        args = parser.parse_args()

        noaaObj = NOAA(dict(appCfg['NOAA']))     # NOAA Obj provided with dict from ini file
        station_dict = dict(appCfg['Stations'])  # ini file provides dict of alias:station_id

        if args.find_ids:
            dist2home = float(args.arg1) if args.arg1 is not None else 30.0
            err, station_list = noaaObj.get_stations(dist2home)
            if err:
                print(err)
            else:
                print_stations(station_list)
                print(f'home @ {appCfg["NOAA"]["home"]}')

        elif args.fipcode:
            if not args.arg1:
                print(f'fip_code {noaaObj.fip_code}')
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
                    appCfg['NOAA']['fip_code'] = f'{item.code:05d}'
                    save_appCfg(appCfg, iniPath)
                    print(f'  {item.state}, {item.region} {item.qualifier} = {appCfg["NOAA"]["fip_code"]}')

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
                    # try:
                    #     lat_long = [float(x)]

        elif args.config:
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
            dbFiles = update_db(station_dict, dbDir, noaaObj)

            gui = guiMain(dbFiles, (800, 100))  # Gui Setup
            gui.mainloop()
