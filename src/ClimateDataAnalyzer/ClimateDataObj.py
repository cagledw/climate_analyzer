"""
Climate Data Abstraction and Formating Class
"""
from datetime import date
from glob import glob
from enum import IntEnum
from typing import Dict, List, Tuple, TypedDict
from collections import namedtuple
from calendar import month_abbr
from dbCoupler import dbCoupler, DBTYPE_CDO
from itertools import groupby, accumulate
from noaa import NOAA

import logging
import os
import warnings
import numpy as np

STATION_T = namedtuple('STATION_T', ['alias', 'id'])
PLOT_DATA = IntEnum('PLOT_DATA', ['RAIN', 'TEMP'])
HIST_DATA = TypedDict('HIST_DATA',
                      {'dtype': PLOT_DATA,
                       'station': str,
                       'dnames': List[str],
                       'obs': np.ndarray,
                       'ma': np.ndarray,
                       'ma_winsz': int},
                      total=False)

mm2days = [31, 29, 31, 30, 31, 30, 31, 31, 30, 31, 30, 31]
mmlabels = [month_abbr[x] for x in range(1, 13)]
PLOT_TYPE = IntEnum('PLOT_TYPE', ['ALLDOY', 'SNGLDOY', 'HISTO'])
DATE_ENUM = namedtuple('DATE_ENUM', ['yrenum', 'dayenum'])


def dayInt2Label(day):
    month_int = 0
    while day > mm2days[month_int] - 1:
        day -= mm2days[month_int]
        month_int += 1
    return f'{mmlabels[month_int]}-{day + 1:02d}'


def dayInt2MMDD(day):
    if day > 365:
        raise ValueError

    month_int = 0
    while day > mm2days[month_int] - 1:
        day -= mm2days[month_int]
        month_int += 1
    return month_int + 1, day + 1


def date2enum(dayDate: date | str):
    dayenum = 0
    if type(dayDate) == date:
        yr, mm, dd = dayDate.year, dayDate.month, dayDate.day
    elif type(dayDate) == str:
        yr, mm, dd = dayDate.split('-')
    else:
        raise ValueError

    for indx in range(12):
        if mm == 1:
            break
        else:
            mm -= 1
            dayenum += mm2days[indx]
    dayenum += dd - 1
    return dayenum, int(yr)


class ClimateDataObj:
    """ Manage Climate Data for N different locations (i.e. stations)
        The ctor receives the full path to a directory @ which sqlite DB's are to be found
        Data is obtained from DB's using dbCoupler Object.

        Data from dbCoupler is expected to be Numpy Structured Array: [yrs, dayofyr, rec_array]
          1st dim of Climate Data = yrs & must match the dim of the yrList
          2nd dim of Climate Data = dayofyr  and is ALWAYS 366
          3rd dim of Climate Date = numpy structured array, fld names match NOAA names
    """

    @staticmethod
    def get_dnames(dtype: PLOT_DATA) -> List[str]:
        """ Returns List of Observation Names matching the supplied dtype
        """
        if dtype == PLOT_DATA.TEMP:
            dnames = ['tmin', 'tmax']

        elif dtype == PLOT_DATA.RAIN:
            dnames = ['prcp']
        else:
            raise ValueError
        return dnames

    @staticmethod
    def moving_average(src_array, dayenum, numPts):
        """ Returns an 1D ndarray of N-Pt Moving Average Values calculated from src_array
            src_array[R-Rows x C-Columns] of a dtype = float, where each row represents 366 days

            N-Pt Centered Moving Average is calculated along a row centered @ dayenum.

        """
        max_indx = src_array.shape[1]
        avg_indicies = [x if x < max_indx else x - max_indx
                        for x in range(dayenum - int(numPts / 2), dayenum + int(numPts / 2) + 1)]
        avg_indicies = np.asarray(avg_indicies, dtype=np.int32)
        roll_indicies = np.asarray(np.where(avg_indicies < 0)).flatten()

        sub_array = src_array[:, avg_indicies]
        if np.any(roll_indicies):
            roll_array = np.roll(sub_array[:, roll_indicies], shift=1, axis=0)
            sub_array[:, roll_indicies] = roll_array

        with warnings.catch_warnings():
            warnings.simplefilter("ignore", category=RuntimeWarning)
            obsMean = np.nanmean(sub_array, axis=1)
        return obsMean

    def __init__(self, dbDir: str,             # Full Path to Directory Containing sqllite DBs.
                 updYrList: List[int],         # A list of years that should be checked for updates
                 stationDict: Dict[str, str],  # key = station_alias, must match sqlite DB name
                 noaaObj: NOAA):               # Object that provides Internet access to NOAA data
        """ Loads Climate Data for the first NOAA Station identified in stationDict.
            This requires stationDict to be ordered!  That in turn requires Python > 3.7!

        """
        self._dbDir = dbDir
        self._noaaObj = noaaObj
        self._stationDict = stationDict
        self._dbMgr = dbCoupler()
        self._ma_numdays = 15  # Moving Avg Window Size

        self._logger = logging.getLogger(__name__)  # Logger
        self._logger.setLevel(logging.INFO)
        fh = logging.FileHandler(os.path.join(dbDir, 'DownLoads.log'), mode='a')
        fh.setLevel(logging.INFO)
        fh.setFormatter(logging.Formatter('%(asctime)s %(message)s', "%Y-%m-%d %H:%M"))
        self._logger.addHandler(fh)

        dbMatch = os.path.join(dbDir, '*.db')
        dbFileList = [os.path.abspath(_f) for _f in glob(dbMatch)]

        self._stationList = []
        if updYrList:
            for _fpath in dbFileList:
                station_alias = os.path.splitext(os.path.basename(_fpath))[0]
                try:
                    station = STATION_T(alias=station_alias,
                                        id=self._stationDict[station_alias])

                    self.update_db(station, _fpath, noaaObj, updYrList)
                    self._stationList.append(station_alias)

                except KeyError:
                    pass

        for _s in stationDict.keys():
            selectDB = os.path.join(dbDir, _s + '.db')
            if selectDB in dbFileList:
                self._station = _s
                self._dbMgr.open(selectDB)
                self._yrList, self._np_climate_data, missing_data = self._dbMgr.rd_climate_data()
                self._dbMgr.close()
                break
            else:
                self._station = None

        self._np_alldoy_mean = {}  # Mean Across all Years for each Day, shape = (366,)
        for _key in ['tmin', 'tmax', 'prcp']:
            self._np_alldoy_mean[_key] = np.nanmean(self._np_climate_data[:, :][_key], axis=0)

    @property
    def yrList(self):
        return self._yrList

    @property
    def np_alldoy_mean(self):
        return self._np_alldoy_mean

    @property
    def np_data(self):
        return self._np_climate_data

    @property
    def num_years(self):
        return self._np_climate_data.shape[0]

    @property
    def num_days(self):
        return self._np_climate_data.shape[1]

    @property
    def station(self):
        return self._station

    @station.setter
    def station(self, newval):
        dbFilePath = os.path.join(self._dbDir, newval + '.db')

        self._dbMgr.open(dbFilePath)
        self._yrList, self._np_climate_data, missing_data = self._dbMgr.rd_climate_data()
        self._dbMgr.close()
        self._station = newval

        self._np_alldoy_mean = {}  # Mean Across all Years for each Day, shape = (366,)
        for _key in ['tmin', 'tmax', 'prcp']:
            self._np_alldoy_mean[_key] = np.nanmean(self._np_climate_data[:, :][_key], axis=0)

    @property
    def stationList(self):
        return self._stationList

    def hist_data(self, dtype: PLOT_DATA, day: int) -> HIST_DATA:
        """ Construct a dict of data required for HIST Plot.
        """
        dnames = ClimateDataObj.get_dnames(dtype)
        rtnDict: HIST_DATA = {'dtype': dtype,
                              'dnames': dnames,
                              'station': self._station,
                              'ma_winsz': self._ma_numdays}

        # Construct ndarray's with nan pts removed and x, y combined into single array
        maList = []
        obsList = []
        for _name in dnames:
            obs = self._np_climate_data[:, day][_name]
            goodIndx = np.argwhere(~np.isnan(obs))

            y = obs[goodIndx].flatten()
            x = goodIndx.flatten()
            obsList.append(np.stack((x, y), axis=1).astype(np.float32))  # (M x 1, M x 1) -> M x 2

            ma = ClimateDataObj.moving_average(self._np_climate_data[_name], day, self._ma_numdays)
            goodIndx = np.argwhere(~np.isnan(ma))

            y = ma[goodIndx].flatten()
            x = goodIndx.flatten()
            maList.append(np.stack((x, y), axis=1).astype(np.float32))

        if len(obsList) == 1:
            rtnDict['obs'] = obsList[0]
            rtnDict['ma'] = maList[0]
        elif len(obsList) == 2:
            rtnDict['obs'] = np.stack(obsList)  # (M x 2, M x 2) -> 2 x M x 2
            rtnDict['ma'] = np.stack(maList)
        else:
            raise ValueError
        return rtnDict

    def sngldoy_data(self, dtype: PLOT_DATA, day: int) -> Dict[str, np.ndarray]:
        """ Construct a dict of data required for ALLDOY Plot with the following keys:
              'dtype'    = PLOT_DATA
              'dnames'   = List[str]
              'obs'      = np.ndarray  (ndarray(Mx2) OR ndarray(M x 2 x 2)
              'avg'      = np.ndarray     same as obs

            'avg' for each day [YR, MM, DD] is calculated as N-Pt Centered Moving Average.
            For days early in the calendar year, the ma calculation requires 'rolling back' to the
            previous year.  Also, it is possible that the ma calculation requires future
            data that does not exist (i.e. ALL nan).  np.nanmean generates a RuntimeWarning for this.
        """
        if dtype == PLOT_DATA.TEMP:
            dnames = ['tmin', 'tmax']

        elif dtype == PLOT_DATA.RAIN:
            dnames = ['prcp']

        else:
            raise ValueError
        rtnDict = {'dtype': dtype, 'dnames': dnames}

        max_indx = self._np_climate_data.shape[1]
        avg_indicies = [x if x < max_indx else x - max_indx
                        for x in range(day - int(self._ma_numdays / 2), day + int(self._ma_numdays / 2) + 1)]
        avg_indicies = np.asarray(avg_indicies, dtype=np.int32)
        roll_indicies = np.asarray(np.where(avg_indicies < 0)).flatten()

        obs = []
        avg = []
        for name in dnames:
            obs.append(self._np_climate_data[:, day][name])

            sub_array = self._np_climate_data[:, avg_indicies][name]
            if np.any(roll_indicies):
                roll_array = np.roll(sub_array[:, roll_indicies], shift=1, axis=0)
                sub_array[:, roll_indicies] = roll_array

            with warnings.catch_warnings():
                warnings.simplefilter("ignore", category=RuntimeWarning)
                obsMean = np.nanmean(sub_array, axis=1)
            avg.append(obsMean)

        # Construct ndarray's with nan pts removed and x, y combined into single array
        for _name, _list in {'obs': obs, 'avg': avg}.items():
            goodList = []
            for _nparray in _list:
                goodIndx = np.argwhere(~np.isnan(_nparray))
                y = _nparray[goodIndx].flatten()
                x = goodIndx.flatten()
                goodList.append(np.stack((x, y), axis=1).astype(np.float32))  # (M x 1, M x 1) -> M x 2

            if len(goodList) == 1:
                rtnDict[_name] = goodList[0]
            elif len(goodList) == 2:
                ptStack = np.stack(goodList)  # (M x 2, M x 2) -> 2 x M x 2
                rtnDict[_name] = np.swapaxes(ptStack, 0, 1)  # 2 x M x 2      -> M x 2 x 2

        return rtnDict

    def alldoy_data(self, dtype, xorigin) -> Dict[str, np.ndarray]:
        """ Construct a dict of data required for ALLDOY Plot with the following keys:
              'dtype'    = PLOT_DATA
              'dnames'   = List[str]
              'obs'      = np.ndarray

            Return Climate Temperature for 12 Months, starting @ month mstart
            X-Axis is always enumerated 0-365, but corresponding dates may be offset by _doy_xorigin

        """
        ma_winsize = self._ma_numdays
        ma_winsize_2 = int(ma_winsize / 2.)

        if dtype == PLOT_DATA.TEMP:
            dnames = ['tmin', 'tmax']
            title = 'Tmin - Tmax'

        elif dtype == PLOT_DATA.RAIN:
            dnames = ['prcp']
            title = 'Rain Precipitation'
        else:
            raise ValueError

        obs = []
        ddict = {'dtype': dtype, 'dnames': dnames, 'ltmean': [], 'ma': [], 'station': self._station, 'title': title}
        dshape = self._np_climate_data.shape
        for name in dnames:
            if xorigin.dayenum == 0:
                datayr2 = None
                prefix_yr = xorigin.yrenum - 1
                prefix_slice = np.arange(dshape[1] - ma_winsize_2, dshape[1])

                postfix_yr = xorigin.yrenum + 1
                # postfix_slice = np.arange(ma_winsize_2)
            else:
                datayr2 = xorigin.yrenum + 1
                prefix_yr = xorigin.yrenum
                prefix_slice = np.arange(xorigin.dayenum - ma_winsize_2, xorigin.dayenum)

                postfix_yr = xorigin.yrenum + 1
                # postfix_slice = np.arange(xorigin.dayenum, xorigin.dayenum + xorigin.dayenum)

            # Climate Data for each dname, adjusted for xorigin
            d1 = self._np_climate_data[xorigin.yrenum][name][xorigin.dayenum:]
            d2 = np.empty(0) if datayr2 is None else self._np_climate_data[datayr2][name][:xorigin.dayenum]
            ddict[name] = np.concatenate((d1, d2))
            obs.append(ddict[name])

            # The mean value for each day across all years, adjusted for xorigin
            np_data = np.concatenate((self._np_alldoy_mean[name][xorigin.dayenum:],
                                      self._np_alldoy_mean[name][:xorigin.dayenum]))
            ddict['ltmean'].append(np_data)

            # The N-Pt Moving average for each day, across the N/2 prceeding, following days
            try:
                prefix_data = self._np_climate_data[prefix_yr][name][prefix_slice]
            except IndexError:
                prefix_data = np.zeros(ma_winsize_2, dtype=d1.dtype)

            try:
                postfix_data = self._np_climate_data[postfix_yr][name][-ma_winsize_2:]
            except IndexError:
                postfix_data = np.zeros(ma_winsize_2, dtype=d1.dtype)

            extended_data = np.concatenate((prefix_data, ddict[name], postfix_data))
            np.nan_to_num(extended_data, copy=False)

            ma_vals = np.convolve(extended_data, np.ones(ma_winsize, dtype=ddict[name].dtype)) / ma_winsize
            ddict['ma'].append(ma_vals[ma_winsize - 1:-ma_winsize + 1])

            # ddict[name+'_avg'] = np.nanmean(np_data)
            # ddict[name+'_stdev'] = np.nanstd(np_data)
        obsList = []
        for _nparray in obs:
            goodIndx = np.argwhere(~np.isnan(_nparray))
            y = _nparray[goodIndx].flatten()
            x = goodIndx.flatten()
            obsList.append(np.stack((x, y), axis=1).astype(np.float32))  # (M x 1, M x 1) -> M x 2
        if len(obsList) == 1:
            ddict['obs'] = obsList[0]
        elif len(obsList) == 2:
            ptStack = np.stack(obsList)  # (M x 2, M x 2) -> 2 x M x 2
            ddict['obs'] = np.swapaxes(ptStack, 0, 1)  # 2 x M x 2      -> M x 2 x 2
        return ddict

    def update_db(self, station, dbFilePath, webAccessObj, upd_yrs):
        """
         Scan for Climate DataBase Files in updateDir, and then check each for missing data.
         If missing data is found, attempt Download from NOAA & Update DB.
           Each sub-array of climate data has exactly 366 elements
           non-leap-year sub-array's are expected to be void for Feb-29 and are ignored.
           Only the years now - upd_yrs are checked.

         Returns: list of dbFiles discovered
        """
        dayenumLim, yrLim = date2enum(date.today())  # Update Scan Limit
        upd_fldNames = [_name for _name in DBTYPE_CDO._fields if _name != 'date']

        self._dbMgr.open(dbFilePath)

        yrList, np_climate_data, missing_data = self._dbMgr.rd_climate_data()
        print(f'  {station.alias:10} Years: {yrList[0]} - {yrList[-1]}')

        if yrList[-1] != date.today().year:
            yrList.append(date.today().year)

        # Loop Over All Years, climate data is 2D array of records [yrs, days]
        stationStatusDict = {}
        for _chkyear in upd_yrs:
            _yrenum = yrList.index(_chkyear)

            yrstatus = {'Valid': 0, 'Partial': 0, 'Missing': 0}

            new_indx = 0
            new_vals = None

            # Find db rows with ANY missing data
            void = [np.any([np.isnan(x) for x in y]) for y in np_climate_data[_yrenum, :]]
            isnan_grpsize = [(_k, sum(1 for _ in _v)) for _k, _v in groupby(void)]
            isnan_dayenum = [0] + list(accumulate([x[1] for x in isnan_grpsize]))
            assert isnan_dayenum[-1] == np_climate_data.shape[1]  # the sum of all grp elements should == 366

            for _grpidx, _isnan_grp in enumerate(isnan_grpsize):
                ismissing = _isnan_grp[0]
                nummissing = _isnan_grp[1]

                dayenum = isnan_dayenum[_grpidx]
                if _yrenum == len(yrList) - 1 and dayenum == dayenumLim:  # yrenum, dayenum past today?
                    break

                if not ismissing:
                    yrstatus['Valid'] += nummissing
                    continue

                while nummissing:
                    if dayenum == 59 and not self._dbMgr.is_leap_year(_chkyear):  # Skip Feb29 if not LeapYear
                        dayenum += 1
                        nummissing -= 1
                        continue

                    current_vals = [np_climate_data[_yrenum, dayenum][_fld]  # This day's current Climate Data
                                    for _fld in upd_fldNames]
                    current_isnan = [np.isnan(x) for x in current_vals]

                    if new_vals is None:
                        new_vals = webAccessObj.get_dataset_v1(station.id, date(_chkyear, 1, 1))

                    missingDate = date(_chkyear, *dayInt2MMDD(dayenum))
                    while True:
                        newCDO_date = date.fromisoformat(new_vals[new_indx].date)
                        if newCDO_date >= missingDate or new_indx + 1 >= len(new_vals):
                            break
                        else:
                            new_indx += 1

                    if newCDO_date == missingDate:  # New Download Date Matches Missing
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
                            self._dbMgr.add_climate_data(str(missingDate.year), [new_vals[new_indx]])

                        elif any(isnan_and_isvalid):
                            loginfo = 'Revise'
                            upd_dict = dict([(_k, _v) for _k, _v in zip(upd_fldNames, newcd_vals) if _v])
                            # upd_dict = dict(zip(upd_fldNames, newcd_vals))
                            self._dbMgr.upd_climate_data(str(missingDate.year),
                                                         {'date': missingDate.isoformat()},
                                                         upd_dict)
                        else:
                            loginfo = None

                        if loginfo:
                            self._logger.info(f'{loginfo} {station.alias:10} {missingDate} {info}')
                    else:
                        if all(current_isnan):
                            yrstatus['Missing'] += 1
                        else:
                            yrstatus['Partial'] += 1

                    dayenum += 1
                    nummissing -= 1

                    if _yrenum == np_climate_data.shape[0] - 1 and dayenum > dayenumLim:
                        break
            stationStatusDict[_chkyear] = yrstatus

        for _yr, _stat in stationStatusDict.items():
            print(f'{_yr:>19}: ' + ','.join(f'{_k}: {_v:>3}' for _k, _v in _stat.items()))

        self._dbMgr.close()
