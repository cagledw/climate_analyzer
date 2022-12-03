"""
  Climate Data Analysis, Download Data from NOAA Climate Data WebSite OR Launch tkinter GUI
  Two options for Climate Data Download:
     -stations : write list of nearby stations to stdout
     -getcd    : download Historical Climate Data for specific Station to sqlite DB

  Otherwise, launches GUI for analysis of data previously stored in sqlite DB.


"""

import os
import re
import copy
import numpy as np

from glob import glob
from datetime import date, datetime, timedelta
from collections import namedtuple
from haversine import haversine, Unit

from noaa        import noaa_aliases, get_station, get_stations, get_dataset_v1
from guiMain     import guiMain
from dbCoupler   import dbCoupler, DBTYPE_CDO

# CDO_TOKEN = 'vOQSRjlXjSwPyEbbAOFCOphAoAaYQgcM'
# CFE_HEADER = {
#     'User-Agent': 'cfebot/1.0',
#     'From': 'davidc@clearfocusengineering.com'  # This is another valid field
# }

# HomeLoc = [47.61103, -122.16105]   # Lat & Long of HomeLoc
# STATION_T = namedtuple('STATION_T',  ['id', 'name', 'lat_long', 'elev', 'mindate', 'maxdate', 'dist2home'])

CDFLDS_NODATE = [x for x in DBTYPE_CDO._fields if x != 'date']   # field names of Climate Data Only, No Date
CD_NODATE_NPDT = np.dtype([(_key, np.float32) for _key in CDFLDS_NODATE])
DEFAULT_END_POINT = 'www.ncei.noaa.gov'

# def is_leap_year(year):
#     return year % 4 == 0 and (year % 100 != 0 or year % 400 == 0)

# def mmdd2enum(month, day):
#     mm2days = [31, 29, 31, 30, 31, 30, 31, 31, 30, 31, 30, 31]
#     return sum(mm2days[:month-1]) + day-1


def print_stations(station_list):
    """ print station_list to std_out
    """
    HomeLoc = [47.60923, -122.16787]   # Lat & Long of HomeLoc

    for _s in station_list:
        id = _s.id.split(':')
        if id[0].upper() != 'GHCND':
            continue

        elev = f'{_s.elev * 3.28084:>4.0f}\''
        print(f'{_s.id:17} {_s.dist2home:>4.1f}mi {elev} {_s.mindate.date()} {_s.maxdate.date()} {_s.name[:40]}')


def store_to_db(station_id, station_name):
    """ Download NOAA Climate Data from Web Portal & Store in SQLite DB
    """

    dbname = os.path.join(".", station_name + '.db')
    if os.path.isfile(dbname):
        print('File Exists {}'.format(dbname))
        return

    info = get_station(station_id)
    yr_start = info.mindate.year
    yr_end = info.maxdate.year

    db = dbCoupler()
    db.open(os.path.join(".", station_name + '.db'))

    # print(info)
    for _yr in range(info.mindate.date().year, info.maxdate.date().year + 1):

    # # for _yr in range(2000, 2023):
        climate_data = get_dataset_v1(station_id, date(_yr, 1, 1))
        print(_yr, climate_data[0].date, climate_data[-1].date, len(climate_data))
        db.wr_cdtable(str(_yr), climate_data)

    db.close()


if __name__ == '__main__':
    import argparse

    parser = argparse.ArgumentParser(description='Download NOAA Climate Data')
    group = parser.add_mutually_exclusive_group()
    group.add_argument('-stations', action='store_true', default = False,
                       help='[arg1] - Display Stations within [arg1] distance')
    group.add_argument('-getcd', action='store_true', default = False,
                       help='[arg1] - Get Climate Data for station [arg1]')
    parser.add_argument('arg1', action='store', nargs='?', default=None)

    args = parser.parse_args()

    if args.stations:
        dist2home = float(args.arg1) if args.arg1 is not None else 30
        print_stations(get_stations(dist2home))

    elif args.getcd:
        if args.arg1 is None:
            station_info = '\n'.join(['    ' + x for x in noaa_aliases()])
            parser.error('[arg1] must supply station name:\n' + station_info)
        else:
            try:
                station_id = stations[args.arg1]
            except:
                parser.error('[arg1] must supply station name:\n' + station_info)
                station_id = None

            if station_id:
                store_to_db(station_id, args.arg1)
    else:
        dbFiles = [os.path.abspath(_f) for _f in glob('./*.db')]
        gui = guiMain(dbFiles, (800, 100))  # Gui Setup
        gui.mainloop()
