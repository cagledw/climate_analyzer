import os
import re
import copy
import requests
import numpy as np

from glob import glob
from datetime import date, datetime, timedelta
from collections import namedtuple
from haversine import haversine, Unit

from dbCoupler   import dbCoupler, DBTYPE_CDO

CDO_TOKEN = 'vOQSRjlXjSwPyEbbAOFCOphAoAaYQgcM'
# CFE_HEADER = {
#     'User-Agent': 'cfebot/1.0',
#     'From': 'davidc@clearfocusengineering.com'  # This is another valid field
# }
noaa_ids = {'KENT'         : 'GHCND:USC00454169',
            'SEATAC'       : 'GHCND:USW00024233',
            'BOEING_FIELD' : 'GHCND:USW00024234',
            'MAPLE_VALLEY' : 'GHCND:USC00454486'}

HomeLoc = [47.60923, -122.16787]   # Lat & Long of HomeLoc
STATION_T = namedtuple('STATION_T',  ['id', 'name', 'lat_long', 'elev', 'mindate', 'maxdate', 'dist2home'])

CDFLDS_NODATE = [x for x in DBTYPE_CDO._fields if x != 'date']   # field names of Climate Data Only, No Date
CD_NODATE_NPDT = np.dtype([(_key, np.float32) for _key in CDFLDS_NODATE])
DEFAULT_END_POINT = 'www.ncei.noaa.gov'


def get_noaa_id(alias):
    try:
        id = noaa_ids[alias]
    except:
        print('fail', alias)
        id = None
    return id

def noaa_aliases():
    return station_ids.keys()

def get_station(station_id):
    header = {'token': CDO_TOKEN}
    uri='cdo-web/api/v2/{}/{}'.format('stations', station_id)

    res = requests.get('https://{}/{}'.format(DEFAULT_END_POINT, uri), headers=header)
    if res.status_code == 200:
        data = res.json()

        mindate = datetime.strptime(data['mindate'], "%Y-%m-%d")
        maxdate = datetime.strptime(data['maxdate'], "%Y-%m-%d")
        lat_long = (data['latitude'], data['longitude'])
        miles2home = haversine(lat_long, HomeLoc, unit=Unit.MILES)

        # sdiff = sum([(x - y)**2 for x,y in zip(HomeLoc, lat_long)])

        station = (STATION_T(id = station_id,
                             name = data['name'],
                             lat_long = lat_long,
                             elev = data['elevation'],
                             mindate = mindate,
                             maxdate = maxdate,
                             dist2home = miles2home))
    else:
        print('bad')
        station = None
    return station


def get_stations(dist2home):
    """

    """
    fipwa = 'FIPS:53033'  #Location Identifier
    results = []

    header = {'token': CDO_TOKEN}
    uri='cdo-web/api/v2/{}?locationid={}&limit=1000'.format('stations', fipwa)
    # print(uri)

    res = requests.get(
        'https://{}/{}'.format(DEFAULT_END_POINT, uri), headers=header)

    if res.status_code == 200:
        meta = res.json()['metadata']
        data = res.json()['results']

        for _station in data:
            mindate = datetime.strptime(_station['mindate'], "%Y-%m-%d")
            maxdate = datetime.strptime(_station['maxdate'], "%Y-%m-%d")
            if maxdate.year < 2022 or mindate.year > 2000:
                continue

            lat_long = (_station['latitude'], _station['longitude'])
            sdiff = sum([(x - y)**2 for x,y in zip(HomeLoc, lat_long)])
            miles2home = haversine(lat_long, HomeLoc, unit=Unit.MILES)

            if miles2home < dist2home:
                results.append(STATION_T(id = _station['id'],
                                         name = _station['name'],
                                         lat_long = lat_long,
                                         elev = _station['elevation'],
                                         mindate = mindate,
                                         maxdate = maxdate,
                                         dist2home = miles2home))
    return sorted(results, key = lambda x: x.dist2home)


def get_dataset_v1(station_id, start):
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
        payload = {'dataset' : 'daily-summaries',
                   'dataTypes' : ','.join(hcdd_flds),
                   'stations' : station,
                   'startDate' : start.isoformat(),
                   'endDate'   : date(start.year, 12, 31).isoformat(),
                   'units' : 'standard'}

        res = requests.get(noaa_url, params = payload, headers = {"Token": CDO_TOKEN})
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
                station_index = no_quotes.index('STATION')

                first_line = False
            else:
                if (_l):
                    cd_dict = {'date' : no_quotes[date_index]}
                    for _idx, _fld in enumerate(hcdd_flds):
                        try: cd_dict[_fld.lower()] = no_quotes[data_indexes[_idx]]
                        except: cd_dict[_fld.lower()] = float('nan')
                    hcdd_list.append(DBTYPE_CDO(**cd_dict))
        done = True
    return copy.copy(hcdd_list)


def get_dataset_v2(id):
    """ Retrieve Historical Climate Data - Daily (HCDD) from NOAA USING V1 API.
        The station_id is used to query NOAA's Climate Data Online Web-Site for
        its Daily-Summary Values for all years and days that it is available.
        Returns a dict by year, each dict value is a list of namedtuple DBTYPE_CDO.
    """
    noaa_url = 'https://www.ncei.noaa.gov/cdo-web/api/v2/data'

    limit_count = 1000
    header = {'token': CDO_TOKEN}
    hcdd_flds = ['TMAX', 'TMIN', 'TAVG', 'PRCP', 'SNOW', 'SNWD']
    data_by_year = {}

    info = get_station(id)
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


if __name__ == '__main__':
    import argparse

    parser = argparse.ArgumentParser(description='Download NOAA Climate Data')
    group = parser.add_mutually_exclusive_group()
    group.add_argument('-stations', action='store_true', default = False,
                       help='[arg1] - Display Stations within [arg1] distance')
    group.add_argument('-getcd', action='store_true', default = False,
                       help='[arg1] - Get Climate Data for station [arg1]')
    group.add_argument('-dsets', action='store_true', default = False)
    parser.add_argument('arg1', action='store', nargs='?', default=None)

    args = parser.parse_args()

    if args.stations:
        dist2home = float(args.arg1) if args.arg1 is not None else 30
        for _s in get_stations(dist2home):
            id = _s.id.split(':')
            if id[0].upper() != 'GHCND':
                continue

            elev = f'{_s.elev * 3.28084:4.0f}\''
            print(f'{_s.id:17} {_s.dist2home:.2f} {_s.mindate.date()} {_s.maxdate.date()} {elev} {_s.name[:40]}')

    elif args.getcd:
        if args.arg1 is None:
            station_info = '\n'.join(['    ' + x for x in stations.keys()])
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
