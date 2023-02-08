"""
A tkinter GUI Class
"""
from enum import IntEnum
from typing import Dict, List, Tuple, TypedDict

import warnings
import numpy as np

PLOT_DATA = IntEnum('PLOT_DATA', ['RAIN', 'TEMP'])
HIST_DATA = TypedDict('HIST_DATA',
                      {'dtype': PLOT_DATA, 'dnames': List[str], 'obs': np.ndarray})

class ClimateDataObj():
    """A tk Application (i.e. Main/Root Window)

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
            src_array[R-Rows x C-Columns] of a dtype = float, where each year represents 366 days

            N-Pt Centered Moving Average is calculated along a row centered @ dayenum.

        """
        max_indx = src_array.shape[1]
        avg_indicies = [x if x < max_indx else x - max_indx
                        for x in range(dayenum - int(numPts/2), dayenum + int(numPts/2) + 1)]
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

    def __init__(self, np_climate_data, years, station):
        """

        """
        self._np_climate_data = np_climate_data
        self._station = station
        self._yrList = years
        self._ma_numdays = 15         # Moving Avg Window Size

        self._np_alldoy_mean = {}          # Mean Across all Years for each Day, shape = (366,)
        for _key in ['tmin', 'tmax', 'prcp']:
            self._np_alldoy_mean[_key] = np.nanmean(np_climate_data[:, :][_key], axis=0)

    @property
    def num_years(self):
        """
        """
        return self._np_climate_data.shape[0]

    def hist_data(self, dtype: PLOT_DATA, day: int) -> HIST_DATA:
        """ Construct a dict of data required for HIST Plot with the following keys:
              'dtype'    = PLOT_DATA
              'dnames'   = List[str]
        """

        dnames = ClimateDataObj.get_dnames(dtype)
        title = f'{self._station} Histogram'
        rtnDict = {'dtype': dtype, 'dnames': dnames, 'obs': [], 'station': self._station, 'title': title}

        # Construct ndarray's with nan pts removed and x, y combined into single array
        obsList = []
        for _name in dnames:
            obs = self._np_climate_data[:, day][_name]
            goodIndx = np.argwhere(~np.isnan(obs))

            y = obs[goodIndx].flatten()
            x = goodIndx.flatten()
            obsList.append(np.stack((x, y), axis=1).astype(np.float32))    # (M x 1, M x 1) -> M x 2

            obsMovAvg = ClimateDataObj.moving_average(self._np_climate_data[_name], day, self._ma_numdays)

        if len(obsList) == 1:
            rtnDict['obs'] = obsList[0]
        elif len(obsList) == 2:
            rtnDict['obs'] = np.stack(obsList)                                    # (M x 2, M x 2) -> 2 x M x 2
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
                        for x in range(day - int(self._ma_numdays/2), day + int(self._ma_numdays/2) + 1)]
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
                goodList.append(np.stack((x, y), axis=1).astype(np.float32))    # (M x 1, M x 1) -> M x 2

            if len(goodList) == 1:
                rtnDict[_name] = goodList[0]
            elif len(goodList) == 2:
                ptStack = np.stack(goodList)                                    # (M x 2, M x 2) -> 2 x M x 2
                rtnDict[_name] = np.swapaxes(ptStack, 0, 1)                     # 2 x M x 2      -> M x 2 x 2

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
        ma_winsize_2 = int(ma_winsize/2.)

        if dtype == PLOT_DATA.TEMP:
            dnames = ['tmin', 'tmax']
            title = f'{self._station} {self._yrList[xorigin.yrenum]}  -  Tmin - Tmax'

        elif dtype == PLOT_DATA.RAIN:
            dnames = ['prcp']
            title = f'{self._station} {self._yrList[xorigin.yrenum]}  -  Rain Precipitation'
        else:
            raise ValueError

        obs = []
        ddict = {'dtype': dtype, 'dnames': dnames, 'ltmean': [], 'ma': [], 'station': self._station, 'title': title}
        dshape = self._np_climate_data.shape
        for name in dnames:
            if xorigin.dayenum == 0:
                datayr2 = None
                prefix_yr = xorigin.yrenum-1
                prefix_slice = np.arange(dshape[1]-ma_winsize_2, dshape[1])

                postfix_yr = xorigin.yrenum+1
                # postfix_slice = np.arange(ma_winsize_2)
            else:
                datayr2 = xorigin.yrenum+1
                prefix_yr = xorigin.yrenum
                prefix_slice = np.arange(xorigin.dayenum - ma_winsize_2, xorigin.dayenum)

                postfix_yr = xorigin.yrenum+1
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

            ma_vals = np.convolve(extended_data, np.ones(ma_winsize, dtype=ddict[name].dtype))/ma_winsize
            ddict['ma'].append(ma_vals[ma_winsize-1:-ma_winsize+1])

            # ddict[name+'_avg'] = np.nanmean(np_data)
            # ddict[name+'_stdev'] = np.nanstd(np_data)
        obsList = []
        for _nparray in obs:
            goodIndx = np.argwhere(~np.isnan(_nparray))
            y = _nparray[goodIndx].flatten()
            x = goodIndx.flatten()
            obsList.append(np.stack((x, y), axis=1).astype(np.float32))    # (M x 1, M x 1) -> M x 2
        if len(obsList) == 1:
            ddict['obs'] = obsList[0]
        elif len(obsList) == 2:
            ptStack = np.stack(obsList)                                    # (M x 2, M x 2) -> 2 x M x 2
            ddict['obs'] = np.swapaxes(ptStack, 0, 1)                      # 2 x M x 2      -> M x 2 x 2
        return ddict