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

from glob import glob
from collections import namedtuple
from datetime import date, datetime, timedelta
from itertools import groupby, accumulate

from noaa import noaa_aliases, get_noaa_id, get_stations, get_dataset_v1
from guiMain import guiMain
from guiPlot import dayInt2MMDD, dayInt2Label
from dbCoupler import dbCoupler, DBTYPE_CDO

user_dbPath = 'AppData\\ClimateData'


def print_stations(station_list):
    """ print station_list to std_out
    """
    HomeLoc = [47.60923, -122.16787]   # Lat & Long of HomeLoc

    for _s in station_list:
        id = _s.id.split(':')
        if id[0].upper() != 'GHCND':
            continue

        elev = f'{_s.elev * 3.28084:>4.0f}'
        print(f'{_s.id:17} {_s.dist2home:>4.1f}mi {elev} {_s.mindate.date()} {_s.maxdate.date()} {_s.name[:40]}')


def store_to_db(station_id, station_name):
    """ Download NOAA Climate Data from Web Portal & Store in SQLite DB
    """

    dbname = os.path.join(".", station_name + '.db')
    if os.path.isfile(dbname):
        print('File Exists {}'.format(dbname))
        return

def update_db(dbList):
    """
     Check each db in dbList for missing data.
     If missing data is found, attempt Download from NOAA & Update DB.
       Each sub-array of climate data has exactly 366 elements
       non-leap-year sub-array's are expected to be void for Feb-29 and are ignored.
       Only the two most recent years are checked.

    First, create 'void' list of isnan flags for each day.
    Then identify days that are all nan (void)
    """
    dbMgr = dbCoupler()
    for dbfName in dbList:
        station_name = os.path.splitext(os.path.basename(dbfName))[0]
        station_id = get_noaa_id(station_name)
        print(f'    Checking {station_name}, {station_id}')

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

                    update_vals = get_dataset_v1(station_id, update_day)

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


if __name__ == '__main__':

    import argparse
    homedir = os.getenv('USERPROFILE')
    dbPath = os.path.join(homedir, user_dbPath, '*.db')
    print(dbPath)

    parser = argparse.ArgumentParser(description='Download NOAA Climate Data')
    group = parser.add_mutually_exclusive_group()

    group.add_argument('-stations', action='store_true', default = False, help='[arg1] - Display Stations within [arg1] distance')
    group.add_argument('-getcd', action='store_true', default = False,
                       help='[arg1] - Get Climate Data for station [arg1]')
    parser.add_argument('arg1', action='store', nargs='?', default=None)

    args = parser.parse_args()
    if args.stations:
        dist2home = float(args.arg1) if args.arg1 is not None else 30.0
        print_stations(get_stations(dist2home))
    elif args.getcd:
        if args.arg1 is None:
            station_info = '\n'.join(['    ' + x for x in noaa_aliases()])
        else:
            raise ValueError
    else:
        dbFiles = [os.path.abspath(_f) for _f in glob(dbPath)]
        update_db(dbFiles)

        gui = guiMain(dbFiles, (800, 100))  # Gui Setup
        gui.mainloop()

