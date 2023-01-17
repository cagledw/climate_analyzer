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

from glob import glob
from datetime import date, datetime, timedelta
from collections import namedtuple
from noaa import noaa_aliases, get_stations
from guiMain import guiMain

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
        gui = guiMain(dbFiles, (800, 100))  # Gui Setup
        gui.mainloop()

