"""
NOAA Object for Download of NOAA Climate Data via Internet.
Two data types are central to accessing Climate Data:
  DBTYPE_CDO : represents 1 day of Climate Data for 1 location (i.e. station)
  STATION_T  : represents a location, includes noaa recognized id + other meta deta
"""
import os
import re
import copy
import requests
import numpy as np

from glob import glob
from datetime import date, datetime
from collections import namedtuple
from haversine import haversine, Unit
from .db_coupler import DBTYPE_CDO
from typing import Dict, List, Tuple

STATION_T = namedtuple('STATION_T',  ['id', 'name', 'lat_long', 'elev', 'mindate', 'maxdate', 'dist2home'])

CDFLDS_NODATE = [x for x in DBTYPE_CDO._fields if x != 'date']   # field names of Climate Data Only, No Date
CD_NODATE_NPDT = np.dtype([(_key, np.float32) for _key in CDFLDS_NODATE])
DEFAULT_END_POINT = 'www.ncei.noaa.gov'

class NOAA():
    """ NOAA Daily Summary Climate Data Access
        Methods provide access to station (ie location) identification
        and Daily Climate Summary Data for a particular station.

        NOAA's Web-Site requires a 'cdo_token' to access its data.
        The ctor for this class must be supplied with the cdo_token.
    """
    def __init__(self, cfgDict: Dict[str, str]):
        self._cdo_token = cfgDict['cdo_token']
        self._findrgn = cfgDict['findrgn']
        self._date_1st = date.fromisoformat(cfgDict['date_1st'])
        self._date_last = date.today() if cfgDict['date_last'] == 'now' \
            else date.fromisoformat(cfgDict['date_last'])

        homeCoords = cfgDict['home'].strip('()').split(',')
        self.home_coords = [float(x) for x in homeCoords]

    @property
    def home(self):
        return '(' + ','.join(['{}'.format(x) for x in self.home_coords]) + ')'

    @property
    def findrgn(self):
        return self._findrgn

    def station_info(self, station_id):
        header = {'token': self._cdo_token}
        uri = 'cdo-web/api/v2/{}/{}'.format('stations', station_id)
        station = None
        errStatus = None

        try:
            res = requests.get('https://{}/{}'.format(DEFAULT_END_POINT, uri), headers=header)
        except requests.exceptions.ReadTimeout as err:
            errStatus = err.args[0]
            res = None

        if errStatus is None and res is not None and res.status_code != 200:
            errStatus = requests.exceptions.ConnectionError(f'status:{res.status_code}')

        if errStatus is None:
            data = res.json()
            mindate = datetime.strptime(data['mindate'], "%Y-%m-%d")
            maxdate = datetime.strptime(data['maxdate'], "%Y-%m-%d")
            lat_long = (data['latitude'], data['longitude'])
            miles2home = haversine(lat_long, self.home_coords, unit=Unit.MILES)
            sta_elevation = data['elevation']
            if data['elevationUnit'] == 'METERS':
                sta_elevation *= 3.28084

            station = (STATION_T(id=station_id,
                                 name=data['name'],
                                 lat_long=lat_long,
                                 elev=sta_elevation,
                                 mindate=mindate,
                                 maxdate=maxdate,
                                 dist2home=miles2home))
        return errStatus, station

    def get_stations(self, dist2home: float):
        """  Returns list of STATION_T within dist2home miles of home_lat_long.
             Only stations within the geographic area defined by findrgn are returned.
        """
        home_coords = self.home.strip('()')
        home_lat_long = [float(x) for x in home_coords.split(',')]

        results = []
        header = {'token': self._cdo_token}
        uri = 'cdo-web/api/v2/{}?locationid={}&limit=1000'.format('stations',
                                                                  f'FIPS:{self.findrgn}')
        offset = 0
        done = False
        errStatus = None
        date_filter_max = date.today().year
        while not done:
            try:
                res = requests.get('https://{}/{}'.format(DEFAULT_END_POINT, uri),
                                   headers=header, timeout=(2.0, 2.0))
            except requests.exceptions.ReadTimeout as err:
                errStatus = err.args[0]
                break

            if res.status_code != 200:
                errStatus = requests.exceptions.ConnectionError(f'status:{res.status_code}')
                break

            data_count = int(res.json()['metadata']['resultset']['count'])
            offset += len(res.json()['results'])
            if offset >= data_count:
                done = True

            if res.status_code == 200:
                # meta = res.json()['metadata']
                data = res.json()['results']

                for _station in data:
                    mindate = datetime.strptime(_station['mindate'], "%Y-%m-%d")
                    maxdate = datetime.strptime(_station['maxdate'], "%Y-%m-%d")
                    if maxdate.year < self._date_last.year or mindate.year > self._date_1st.year:
                        continue

                    sta_lat_long = (_station['latitude'], _station['longitude'])
                    try:
                        sta_elevation = _station['elevation']
                        if _station['elevationUnit'] == 'METERS':
                            sta_elevation *= 3.28084
                    except KeyError:
                        sta_elevation = float('nan')

                    miles2home = haversine(sta_lat_long, home_lat_long, unit=Unit.MILES)

                    if miles2home < dist2home:
                        results.append(STATION_T(id=_station['id'],
                                                 name=_station['name'],
                                                 lat_long=sta_lat_long,
                                                 elev=sta_elevation,
                                                 mindate=mindate,
                                                 maxdate=maxdate,
                                                 dist2home=miles2home))

        return errStatus, sorted(results, key=lambda x: x.dist2home)

    def get_dataset_v1(self, station_id, start):
        """ NOAA has TWO API's to Retrieve Historical Climate Data - Daily (HCDD):
            V1 - non-jason capatible, returns values as line delimited text
            V2 - jason capatible but fails to return values for Jan & Feb

            The station_id is used to query NOAA's Climate Data Online Web-Site for
            its Daily-Summary Values for all years and days that it is available.
            Returns a dict by year, each dict value is a list of namedtuple DBTYPE_CDO.
        """
        station = station_id.split(':')[-1]

        noaa_url = 'https://www.ncei.noaa.gov/access/services/data/v1'
        hcdd_flds = ['TMAX', 'TMIN', 'TAVG', 'PRCP', 'SNOW', 'SNWD']

        hcdd_list = []

        done = False
        while not done:
            payload = {'dataset'  : 'daily-summaries',
                       'dataTypes': ','.join(hcdd_flds),
                       'stations' : station,
                       'startDate': start.isoformat(),
                       'endDate'  : date(start.year, 12, 31).isoformat(),
                       'units' : 'standard'}
            try:
                res = requests.get(noaa_url, params=payload, timeout=(5.0, 5.0),
                                   headers={"Token": self._cdo_token})
            except Exception as err:
                print('Err {}'.format(err))
                break

            if res.status_code != 200:
                print('fail', res.status_code)
                break

            first_line = True
            for _l in res.text.split('\n'):
                fields = _l.split(',')
                no_quotes = [item.strip('\"') for item in fields]

                if first_line:
                    data_indexes = [no_quotes.index(item) for item in hcdd_flds]

                    date_index = no_quotes.index('DATE')
                    # station_index = no_quotes.index('STATION')

                    first_line = False
                else:
                    if _l:
                        cd_dict = {'date': no_quotes[date_index]}
                        for _idx, _fld in enumerate(hcdd_flds):
                            try: cd_dict[_fld.lower()] = no_quotes[data_indexes[_idx]]
                            except: cd_dict[_fld.lower()] = float('nan')
                        hcdd_list.append(DBTYPE_CDO(**cd_dict))
            done = True
        return copy.copy(hcdd_list)

    def get_dataset_v2(self, id):
        """ Retrieve Historical Climate Data - Daily (HCDD) from NOAA USING V2 API.
            The station_id is used to query NOAA's Climate Data Online Web-Site for
            its Daily-Summary Values for all years and days that it is available.
            Returns a dict by year, each dict value is a list of namedtuple DBTYPE_CDO.
        """
        noaa_url = 'https://www.ncei.noaa.gov/cdo-web/api/v2/data'

        # limit_count = 1000
        header = {'token': CDO_TOKEN}
        hcdd_flds = ['TMAX', 'TMIN', 'TAVG', 'PRCP', 'SNOW', 'SNWD']
        data_by_year = {}

        info = station_info(id)
        for _yr in range(info.mindate.date().year, info.maxdate.date().year + 1):
        # for _yr in range(2021, 2022):
            hcdd_list = []
            startdate = date(_yr, 1, 1)
            enddate = date(_yr, 12, 31)

            offset = 0
            done = False
            daily_dict = {}
            while not done:
                payload = {'dataset' : 'daily-summaries',
                           'dataTypes' : ','.join(hcdd_flds),
                           'stations' : 'USW00003893',
                           'startDate' : startdate.isoformat(),
                           'endDate'   : enddate.isoformat(),
                           'units' : 'standard'}

                # payload = {'offset' : offset,
                #            'datasetid' : 'GHCND',
                #            'stationid' : id,
                #            'startdate' : startdate.isoformat(),
                #            'enddate'   : enddate.isoformat(),
                #            'datatypeid' : ['TMAX', 'TMIN', 'TAVG', 'PRCP', 'SNOW', 'SNWD'],
                #            'units' : 'standard',
                #            'limit' : limit_count}


                res = requests.get(noaa_url, params = payload, headers = {"Token": CDO_TOKEN})





                if res.status_code != 200:
                    print('fail', res.status_code)
                    break

                first_line = True
                for _l in res.text.split('\n'):
                    fields = _l.split(',')

                    if first_line:
                        print(_l, len(fields))
                        first_line = False
                    else:
                        print(_l)

                break
                data_count = int(res.json()['metadata']['resultset']['count'])
                data_list = res.json()['results']
                rx_count = len(data_list) + offset

                for _itemnum, _hcdd in enumerate(data_list):
                    item_date = _hcdd['date'].split('T')[0]

                    if not daily_dict:
                        daily_dict['date'] = item_date

                    if daily_dict['date'] != item_date:
                        check_it = [x for x in hcdd_flds if x not in daily_dict.keys()]
                        if check_it:
                            print(f"{daily_dict['date']}, Missing {','.join(check_it)}")

                        hcdd_list.append(DBTYPE_CDO(**{_k.lower() : _v for _k, _v in daily_dict.items()}))
                        daily_dict = {'date' : item_date}
                        # print(item_date)

                    daily_dict[_hcdd['datatype']] = _hcdd['value']

                offset += rx_count
                if rx_count >= data_count:
                    done = True

            data_by_year[_yr] = copy.copy(hcdd_list)
        return data_by_year

# if __name__ == '__main__':
#     import argparse
#
#     parser = argparse.ArgumentParser(description='Download NOAA Climate Data')
#     group = parser.add_mutually_exclusive_group()
#     group.add_argument('-stations', action='store_true', default = False,
#                        help='[arg1] - Display Stations within [arg1] distance')
#     group.add_argument('-getcd', action='store_true', default = False,
#                        help='[arg1] - Get Climate Data for station [arg1]')
#     group.add_argument('-dsets', action='store_true', default = False)
#     parser.add_argument('arg1', action='store', nargs='?', default=None)
#
#     args = parser.parse_args()
#
#     if args.stations:
#         dist2home = float(args.arg1) if args.arg1 is not None else 30
#         for _s in get_stations(dist2home):
#             sid = _s.id.split(':')
#             if sid[0].upper() != 'GHCND':
#                 continue
#
#             elev = f'{_s.elev * 3.28084:4.0f}\''
#             print(f'{_s.id:17} {_s.dist2home:.2f} {_s.mindate.date()} {_s.maxdate.date()} {elev} {_s.name[:40]}')
#
#     elif args.getcd:
#         if args.arg1 is None:
#             station_info = '\n'.join(['    ' + x for x in stations.keys()])
#             parser.error('[arg1] must supply station name:\n' + station_info)
#         else:
#             try:
#                 station_id = stations[args.arg1]
#             except Exception as ex:
#                 print(ex)
#                 parser.error('[arg1] must supply station name:\n' + station_info)
#                 station_id = None
#
#             if station_id:
#                 store_to_db(station_id, args.arg1)
#     else:
#         dbFiles = [os.path.abspath(_f) for _f in glob('./*.db')]
#         gui = guiMain(dbFiles, (800, 100))  # Gui Setup
#         gui.mainloop()
