import re
import copy
import requests
import json
# from noaa_sdk import NOAA
# from noaa_sdk.ncdc import NCDC
from datetime import date, datetime, timedelta
from collections import namedtuple

HomeLoc = [47.61103, -122.16105]
CFE_HEADER = {
    'User-Agent': 'cfebot/1.0',
    'From': 'davidc@clearfocusengineering.com'  # This is another valid field
}
CDO_TOKEN = 'vOQSRjlXjSwPyEbbAOFCOphAoAaYQgcM'
DEFAULT_END_POINT = 'www.ncei.noaa.gov'
BASE_URL = 'https://www.ncei.noaa.gov/cdo-web/api/v2/'
STATION_T = namedtuple('STATION_T',  ['id', 'name', 'lat_long', 'elev', 'mindate', 'maxdate', 'dist2home'])
fipwa = 'FIPS:53033'
SQL_DB_NAME = 'ClimateDB'

# Climate Data Observation
DBDEF_CDO   = [('date',        'TEXT',    'PRIMARY KEY'),
               ('tmax',        'REAL',    'NOT NULL'),
               ('tmin',        'REAL',    'NOT NULL'),
               ('tavg',        'REAL',    'NOT NULL'),
               ('prcp',        'REAL',    'NOT NULL'),
               ('snow',        'INTEGER', 'NOT NULL'),
               ('snwd',        'REAL',    'NOT NULL')]

DBTYPE_CDO  = namedtuple('DBTYPE_CDO',        [x[0] for x in DBDEF_CDO])

DB_DEFINES       = {'DBDEF_CDO'   : DBDEF_CDO}, # dbCoupler.__init__() uses to set cmd/def strings


def get_station(station_id):
    header = {'token': CDO_TOKEN}
    uri='cdo-web/api/v2/{}/{}'.format('stations', station_id)

    res = requests.get('https://{}/{}'.format(DEFAULT_END_POINT, uri), headers=header)
    if res.status_code == 200:
        data = res.json()
        mindate = datetime.strptime(data['mindate'], "%Y-%m-%d")
        maxdate = datetime.strptime(data['maxdate'], "%Y-%m-%d")
        lat_long = (data['latitude'], data['longitude'])
        sdiff = sum([(x - y)**2 for x,y in zip(HomeLoc, lat_long)])

        station = (STATION_T(id = station_id,
                             name = data['name'],
                             lat_long = lat_long,
                             elev = data['elevation'],
                             mindate = mindate,
                             maxdate = maxdate,
                             dist2home = sdiff))

    else:
        print('bad')
        station = None
    return station


def get_stations(dist2home):
    """

    """
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

            if sdiff < dist2home:
                results.append(STATION_T(id = _station['id'],
                                         name = _station['name'],
                                         lat_long = lat_long,
                                         elev = _station['elevation'],
                                         mindate = mindate,
                                         maxdate = maxdate,
                                         dist2home = sdiff))
    return sorted(results, key = lambda x: x.dist2home)


def get_dataset(id):
    """ Retrieve Historical Climate Data - Daily from NOAA
        PRCP, TAVG, TMIN, TMAX, SNOW,
    """
    hcdd_flds = ['TMAX', 'TMIN', 'TAVG', 'PRCP', 'SNOW', 'SNWD']
    header = {'token': CDO_TOKEN}
    url_endpt = 'data'
    dset = 'datasetid=GHCND'
    dtype = '&'.join([f'datatypeid={x}' for x in hcdd_flds])
    limit = 'limit=1000'
    units = 'units=standard'
    station = 'stationid={}'.format(id)
    # print(info.mindate.date().year, info.maxdate.date().year)

    offset = 0
    info = get_station(id)
    # for _yr in range(info.mindate.date().year, info.maxdate.date().year + 1):
    for _yr in range(2019, 2020):
        startdate = date(_yr, 2, 1)
        enddate = startdate + timedelta(days = 10)
        t1 = f'startdate={startdate.year}-' + str(startdate.month).zfill(2) + '-' + \
                                              str(startdate.day).zfill(2)
        t2 = f'enddate={enddate.year}-' + str(enddate.month).zfill(2) + '-' + \
                                          str(enddate.day).zfill(2)
        # t1 = f'startdate={startdate.year}-{startdate.month}-{startdate.day}'
        # t2 = f'enddate={enddate.year}-{enddate.month}-{enddate.day}'

        # start = f'startdate={_yr}-01-01'
        # end = f'enddate={_yr}-10-31'
        hcdd_list = []
        print(t1, t2)
        # print(start, end)

        uri = f'{BASE_URL}/{url_endpt}?{dset}&offset={offset}&' + '&'.join([station, dtype, t1, t2, units])
        res = requests.get(uri, headers=header)

        if res.status_code == 200:
            print(res.json().keys())
            break

            results = res.json()['results']
            if 'metadata' in res.json():
                # meta = res.json()['metadata']['resultset']
                print(res.json()['metadata'])

            daily_dict = {}
            for _itemnum, _hcdd in enumerate(results):
                if 'date' not in daily_dict.keys():
                    daily_dict['date'] = _hcdd['date'].split('T')[0]

                elif daily_dict['date'] != _hcdd['date'].split('T')[0]:
                    # print(daily_dict['date'], [x for x in daily_dict.keys() if x != 'date'])
                    hcdd_list.append(copy.copy(daily_dict))
                    daily_dict = {}

                    daily_dict['date'] = _hcdd['date'].split('T')[0]
                    daily_dict[_hcdd['datatype']] = _hcdd['value']
                    continue

                if _hcdd['datatype'] in hcdd_flds:
                    daily_dict[_hcdd['datatype']] = _hcdd['value']
                # else:

            print(hcdd_list[0]['date'], hcdd_list[-1]['date'])
            offset += 900
            # print(hcdd_list[-1]['date'])
                # test = [
                # hcd_date = _hcdd['date'].split('T')[0]
                # if _day < 2:
                #     print(hcd_date, _hcdd['datatype'], _hcdd['value'])


        else:
            print('bad {}'.format(res.status_code))


    # start = 'startdate=2000-01-01'
    # start = 'startdate=2021-01-01'
    # end = 'enddate=2021-12-31'

    # uri = f'{BASE_URL}/{url_endpt}?' + '&'.join([dset, station, dtype, start, end, units, limit])
    # # print(uri, '\n')

    # res = requests.get(uri, headers=header)


    # if res.status_code == 200:

    #     meta = res.json()['metadata']
    #     data = res.json()['results']
    #     print(meta)

    #     for _d in data:
    #         hcd_date = _d['date'].split('T')[0]
    #         # print(hcd_date, _d['datatype'], _d['value'])


    # else:
    #     print('bad {}'.format(res.status_code))


def load_db(station_id):

    get_dataset(station_id)
    # stations = get_stations(0.07)
    # for _s in stations:

    #     info = re.match('.*TACOMA.*', _s.name)
    #     # info = re.match('.*BOEING.*', _s.name)
    #     if info:
    #         print('{:18} {:.3f} {} {} {}'.format(_s.id, _s.dist2home, _s.mindate.date(), _s.maxdate.date(), _s.name[:45]))

    #         get_datasets(_s.id)
    #         break

    #         # print(_s.id)

    # return



if __name__ == '__main__':
    import argparse

    parser = argparse.ArgumentParser(description='Download NOAA Daily Climate Data')
    group = parser.add_mutually_exclusive_group()
    group.add_argument('-stations', action='store_true', default = False)
    group.add_argument('-load', action='store_true', default = False)
    parser.add_argument('arg1', action='store', nargs='?', default=None)

    args = parser.parse_args()

    if args.stations:
        dist2home = float(args.arg1) if args.arg1 is not None else .07
        for _s in get_stations(dist2home):
            print(f'{_s.id:17} {_s.dist2home:.2f} {_s.mindate.date()} {_s.maxdate.date()} {_s.name}')

    elif args.load:
        if args.arg1 is None:
            parser.error('-load requires a station_id')
        else:
            load_db('GHCND:USW00024233')
