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
from ClimateDataObj import ClimateDataObj, PLOT_DATA

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


if __name__ == '__main__':

    # INI File Specifies critical parameters - cdo_token MUST BE SUPPLIED!
    iniPath = os.path.splitext(__file__)[0] + '.ini'
    appCfg = get_appCfg(os.path.join(iniPath))
    dbDir = os.path.expandvars(appCfg['Paths']['dbDir'])
    cdo_token = appCfg['NOAA']['cdo_token']

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
            upd_yrs = range(date.today().year - int(appCfg['NOAA']['upd_yrs']), date.today().year)
            upd_yrList = [_yr + 1 for _yr in upd_yrs]
            cdObj = ClimateDataObj(dbDir, upd_yrList, station_dict, noaaObj)

            gui = guiMain(cdObj, (800, 100))  # Gui Setup
            gui.mainloop()
