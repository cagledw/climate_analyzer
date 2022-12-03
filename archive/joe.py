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

            if sdiff < dist2home:
                results.append(STATION_T(id = _station['id'],
                                         name = _station['name'],
                                         lat_long = lat_long,
                                         elev = _station['elevation'],
                                         mindate = mindate,
                                         maxdate = maxdate,
                                         dist2home = sdiff))
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
