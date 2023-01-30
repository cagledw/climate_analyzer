""" A matplotlib derived class that 'acts' like a tkinter canvas Widget.
    The guiPlot constructor requires a tkinter 'parent' Widget and numpy 2D Structured Array.

    The guiPlot object generates an 3 Different Plots depending on its PLOT_TYPE: ALL_DOY, SNGL_DOY, HISTO
    Calls to the plot(type, arg1, ..) method will cause 1 of 3 plots to be generated.
    The guiPlot object maintains a lists of matplotlib graphics objects that are 'removed' prior
    to generating a new plot.
"""
from __future__ import annotations   # Fix Type Hint Problem

from enum        import IntEnum
from typing      import Dict, List, Tuple
from calendar    import month_abbr
from collections import namedtuple
from datetime    import date, timedelta

import re
import numpy as np
import tkinter as tk
import tkinter.ttk as ttk
import matplotlib as mpl
import matplotlib.transforms as mpl_xforms
import _mpl_tk

from matplotlib.figure import Figure
from matplotlib.collections import LineCollection
from matplotlib.backends.backend_pdf import PdfPages
from _mpl_tk import FigureCanvasTk

pltcolor1 = 'dimgray'
pltcolor2 = 'skyblue'
pltcolor3 = 'blue'
gridcolor = 'whitesmoke'

mm2days = [31, 29, 31, 30, 31, 30, 31, 31, 30, 31, 30, 31]
mmlabels = [month_abbr[x] for x in range(1,13)]
PLOT_TYPE = IntEnum('PLOT_TYPE', ['ALLDOY', 'SNGLDOY', 'HISTO'])
PLOT_DATA = IntEnum('PLOT_DATA', ['RAIN', 'TEMP'])
DATE_ENUM = namedtuple('DATE_ENUM',  ['yrenum', 'dayenum'])

def dayInt2Label(day):
    month_int = 0
    while day > mm2days[month_int]-1:
        day -= mm2days[month_int]
        month_int += 1
    return f'{mmlabels[month_int]}-{day+1:02d}'

def dayInt2MMDD(day):
    month_int = 0
    while day > mm2days[month_int]-1:
        day -= mm2days[month_int]
        month_int += 1
    return (month_int+1, day+1)

class guiPlot(FigureCanvasTk):
    """ NOT a tk Widget, instead a matplotlib derived object that embeds a tk.canvas.
        The tk.canvas is instantiated in a parent tk_Widet by calling this objects ctor.

        Constructor requires climate_data in form of a numpy 2D array:
          [yrs, 366][record]

    """
    canvas_dpi = 100

    # @staticmethod
    # def _calc_mean(npdict):
    #     result_mean = {}
    #     for _key, _npa in npdict.items():
    #         result_mean[_key] = np.nanmean(_npa, axis = 0)
    #     return result_mean

    @staticmethod
    def nice_scale(value):
        """ Return scale factor such that: 1.0 <= value * scale < 10.0
        """
        scale = 1.0
        for loop_count in range(6):
            factor = scale * value
            if factor < 10.0 and factor >= 1.0:
                break

            elif factor < 1.0:
                scale *= 10.0

            else:
                scale *= 0.1

        if loop_count > 5:
            raise ValueError

        return scale

    @staticmethod
    def nice_grid(mintick: int, maxtick):
        """ Calculate a nice grid spacing for the interval [mintick .. maxtick]
            Returns a list of equally spaced ints in the specified range.
            List always begins @ mintick but last value depends on grid spacing.

            Use the eqn: num_grid * grid_space = range
              grid_space = range / num_grid  : for min(num_grid) to max(num_grid)

            VERY UGLY - THERE MUST BE A BETTER ALGORITHM!
        """
        min_grid = 8.0
        max_grid = 25.0
        rng = maxtick - mintick

        scale = 1.0
        grid_range = range(int(min_grid), int(max_grid+1))
        rng = (maxtick - mintick)
        # print('nice_grid {} {} {} {}'.format(mintick, maxtick, rng, scale))

        good_mod = [5, 2, 1]
        for loop_count in range(6):
            pts_list = [rng * scale/x for x in grid_range]
            # print(','.join('{:.2f}'.format(x) for x in pts_list))

            if min(pts_list) > max(good_mod):    # too many grid lines, need bigger spacing
                scale *= 0.5
                # print('smaller', scale)
                continue

            elif max(pts_list) < min(good_mod):  # not enough grid lines, need smaller spacing
                scale *= 2.0
                # print('bigger',scale)
                continue

            grid_spacing = [int(round(x)) for x in pts_list]
            for _mod in good_mod:
                # print(_mod, good_mod)

                if _mod in grid_spacing:
                    grid_space = _mod / scale
                    break
                else:
                    grid_space = None

            # print('Loop End {} {} {}'.format(grid_space, mintick, maxtick))

            if grid_space:
                ticks_found = np.arange(mintick, maxtick, grid_space)
                # print('nice_grid {}'.format(ticks_found))

                return list(ticks_found), grid_space

        raise RuntimeError('guiPlot.nice_grid {}'.format(scale))

    def __init__(self, parent, station, years, np_climate_data, figsize):
        self._daysum = [sum(mm2days[:x]) for x in range(len(mm2days)+1)]  # Can't be Class Variable!

        self._parent = parent
        self._station = station
        self._yrList = years
        self._np_climate_data = np_climate_data
        self._np_alldoy_mean = {}
        self.xticks_xformed = False

        for _key in ['tmin', 'tmax', 'prcp']:
            self._np_alldoy_mean[_key] = np.nanmean(np_climate_data[:,:][_key], axis = 0)

        self._mean_byday = None
        self._stdev_byday = None
        self._ma_byday = None

        self._obs = None             # Observation, np_climate_data field name
        self._type = None             # Type of Plot of PLOT_TYPE
        self._obs_max = None
        self._ma_numdays = 15         # Moving Avg Window Size

        self._dayenum = 0             # Valid if type == SNGL_DOY
        self._yrenum = np_climate_data.shape[0] - 1
        self._doy_xorigin = DATE_ENUM(self._yrenum, 0)
        self._plty = {}

        # A Dict to match plot function to plot type
        self.plot_funcs = {PLOT_TYPE[_type] : getattr(self, 'plot_' + _type.lower()) \
                           for _type in PLOT_TYPE.__members__}

        self._figure = Figure(figsize = [x/guiPlot.canvas_dpi for x in figsize], dpi=guiPlot.canvas_dpi)
        self._figure.subplots_adjust(left = 0.04, right = .95, top = .95, bottom = .10)
        super().__init__(self._figure, master = parent)

        self._tk_canvas = self.get_tk_widget()
        self._tk_canvas.rowconfigure(0, weight=1)
        self._tk_canvas.columnconfigure(0, weight=1)
        self._tk_canvas.bind("<Configure>", self.on_configure)

        self._ax0 = self._figure.add_subplot(111)    # Matplotlib Axis, twin is initially off!
        self._ax0twin = self._ax0.twinx()
        self._ax0twin.set_axis_off()
        # self._ax0.set_axisbelow(True)

        self._alldoy_pts = []
        self._alldoy_mean = []
        self._sngldoy_mean = None
        self._alldoy_artlist = []                    # Matplotlib Artists (i.e. graphic objects)
        self._sngldoy_artlist = []
        self._histo_artlist = []

        self._vertLine = None
        # self._horzLine = None

        # self._tk_canvas.bind("<Button-3>", self.on_button3)

        mpl.rc('lines',  markersize = 2)
        mpl.rc('ytick',  labelsize  = 8)
        mpl.rc('xtick',  labelsize  = 10)
        mpl.rc('lines',  linewidth  = 0.7)
        mpl.rc('legend', fontsize   = 8)
        mpl.rc('axes',   titlesize  = 9)

        # cstep = 1.0/len(self._yrList)
        # self._colors = [mpl.colormaps['brg'](x) for x in np.arange(0, 1.0, cstep)]

        self.set_cursor(0)
        # Special Variables to Manage Position XTick Labels
        self._tick_offset = mpl_xforms.ScaledTranslation(-25/72, 0, self._figure.dpi_scale_trans)
        self._xtick_xform_list = []
        self._xtick_xform_dict = {}
        print(_mpl_tk.__file__)

    def grid(self, row, column, rowspan, columnspan):
        self._tk_canvas.grid(row = row, column = 0,
                             columnspan = columnspan, rowspan = rowspan,
                             sticky = 'nsew')

        # print(f'guiPlot {row}, {column}, {rowspan}, {columnspan}')

    def grid_remove(self):
        self._tk_canvas.grid_remove()

    def on_configure(self, event):
        """ Called anytime the canvas width, height changes
        """
        self.resize(event)

    @property
    def istemp(self):
        """ Enumerated_Day (0..365) of current plot, includes Feb 29
        """
        return self._obs in ['tmax', 'tmin']

    def sngldoy_data(self, dtype: PLOT_DATA, day: int) -> Dict[str, np.ndarray]:
        """ Return data for Single Day Of Year Plot, (i.e. data focused on MM/DD across all years)
            what data is returned depends on input (dtype, day) params.

            Along with the 'raw' climate data, the avg value is also calculated and returned.
            For each day [YR, MM, DD] the average is calculated from [YR, MM, [DD - winsz : DD + winsz + 1]]
        """
        if dtype == PLOT_DATA.TEMP:
            dnames = ['tmin', 'tmax']
        elif dtype == PLOT_DATA.RAIN:
            dnames = ['prcp']
        else:
            raise ValueError

        max_indx = self._np_climate_data.shape[1]
        avg_indicies = [x if x < max_indx else x - max_idx for x in range(day - int(self._ma_numdays/2), day + int(self._ma_numdays/2) + 1)]

        avg_indicies = np.asarray(avg_indicies, dtype=np.int32)
        roll_indicies = np.asarray(np.where(avg_indicies < 0)).flatten()

        obsList = []
        avgList = []
        for name in dnames:
            obsList.append(self._np_climate_data[:, day][name])

            sub_array = self._np_climate_data[:, avg_indicies][name]
            roll_array = np.roll(sub_array[:, roll_indicies], shift=1, axis=0)

            sub_array[:, roll_indicies] = roll_array
            avgList.append(np.nanmean(sub_array, axis=1))

        obs = obsList[0] if len(dnames) < 2 else np.stack(obsList, axis=1)
        avg = avgList[0] if len(dnames) < 2 else np.stack(avgList, axis=1)

        rtnDict = {dtype.name.lower():obs, 'avg': avg}
        return rtnDict

    def alldoy_data(self, dtype, xorigin) -> dict:
        """ Return Climate Temperature for 12 Months, starting @ month mstart
            X-Axis is always enumerated 0-365, but corresponding dates may be offset by _doy_xorigin
        """
        ma_winsize = self._ma_numdays
        ma_winsize_2 = int(ma_winsize/2.)

        if dtype == PLOT_DATA.TEMP:
            dnames = ['tmin', 'tmax']
        elif dtype == PLOT_DATA.RAIN:
            dnames = ['prcp']
        else:
            raise ValueError

        ddict = {}
        dshape = self._np_climate_data.shape
        for name in dnames:
            if xorigin.dayenum == 0:
                datayr2 = None
                prefix_yr = xorigin.yrenum-1
                prefix_slice = np.arange(dshape[1]-ma_winsize_2, dshape[1])

                postfix_yr = xorigin.yrenum+1
                postfix_slice = np.arange(ma_winsize_2)
            else:
                datayr2 = xorigin.yrenum+1
                prefix_yr = xorigin.yrenum
                prefix_slice = np.arange(xorigin.dayenum - ma_winsize_2, xorigin.dayenum)

                postfix_yr = xorigin.yrenum+1
                postfix_slice = np.arange(xorigin.dayenum, xorigin.dayenum + xorigin.dayenum)

            d1 = self._np_climate_data[xorigin.yrenum][name][xorigin.dayenum:]
            d2 = np.empty(0) if datayr2 is None else self._np_climate_data[datayr2][name][:xorigin.dayenum]
            ddict[name] = np.concatenate((d1, d2))

            try:
                prefix_data = self._np_climate_data[prefix_yr][name][prefix_slice]
            except IndexError:
                prefix_data = np.zeros(ma_winsize_2, dtype=d1.dtype)

            try:
                postfix_data = self._np_climate_data[postfix_yr][name][-ma_winsize_2:]
            except IndexError:
                postfix_data = np.zeros(ma_winsize_2, dtype=d1.dtype)

            ddict[name + '_ltmean'] = np.concatenate((self._np_alldoy_mean[name][xorigin.dayenum:],
                                                       self._np_alldoy_mean[name][:xorigin.dayenum]))

            # Moving Average, Average, & Standard Deviation
            extended_data = np.concatenate((prefix_data, ddict[name], postfix_data))
            np.nan_to_num(extended_data, copy = False)

            ma_vals = np.convolve(extended_data, np.ones(ma_winsize, dtype=ddict[name].dtype))/ma_winsize
            ddict[name+'_ma'] = ma_vals[ma_winsize-1:-ma_winsize+1]

            # ddict[name+'_avg'] = np.nanmean(np_data)
            # ddict[name+'_stdev'] = np.nanstd(np_data)
        return ddict

    # def temp_byday(self, day) -> Tuple[list, Tuple[np.ndarray, np.ndarray]]:
    #     """ Return Climate Temperature Data for Single Day
    #     """
    #
    #     tmin_data = self._np_climate_data[:, day]['tmin']
    #     tmin_indicies = np.argwhere(~np.isnan(tmin_data))
    #
    #     tmax_data = self._np_climate_data[:, day]['tmax']
    #     tmax_indicies = np.argwhere(~np.isnan(tmax_data))
    #
    #     if not np.array_equal(tmin_indicies, tmax_indicies):
    #         raise ValueError
    #
    #     x = tmin_indicies.flatten()
    #     ymin = tmin_data[x].flatten()
    #     ymax = tmax_data[x].flatten()
    #
    #     return x, (ymin, ymax)

    @property
    def dayenum(self):
        """ Enumerated_Day (0..365) of current plot, includes Feb 29
        """
        return self._dayenum

    @property
    def yearenum(self):
        """ Enumerated_Year (0..N = np_climate_data.shape[0] - 1) of current plot
        """
        return self._yrenum

    @yearenum.setter
    def yearenum(self,val):
        self._yrenum = val

    @property
    def year(self):
        """ Calendar_Year of Cursor Location
        """
        return self._yrList[self._yrenum]

    @property
    def plottype(self):
        return self._type

    @property
    def obs_max(self):
        """ Returns a tuple ((yr, m, d), yval)
        """
        return self._obs_max

    @property
    def tkwidget(self):
        return self._tk_canvas

    @property
    def canvas_sz(self):
        """ The figure pixel size
        """
        return [int(x) for x in self.figure.bbox.max]

    @property
    def figsize_inches(self):
        """ The figure size in inches
        """
        return self._figure.get_figwidth(), self._figure.get_figheight()

    @property
    def cursorx(self):
        if self._vertLine is None:
            return None

        return self._vertLine.get_xdata()

    @property
    def cursor(self):
        """ Returns a current cursor position as a dict {'date' : x, + mode specific keys,val pairs}
            The matplotlib object _verLine is queried to get the x-value of the current cursor
        """
        rtnDict = {}
        makey = f'{self._ma_numdays}pt_ma'
        tkeys = ['tmin', 'tmax']

        dayenum = self._dayenum
        yrenum = self._yrenum

        data_x = self.cursorx
        if self._type == PLOT_TYPE.SNGLDOY:  # data_x enumerated year
            yrenum = 0 if data_x < 0 else data_x
            yrenum = len(self._yrList) - 1 if yrenum >= len(self._yrList) else yrenum
            mdy = (self._yrList[yrenum], *dayInt2MMDD(self._dayenum))

        elif self._type == PLOT_TYPE.ALLDOY:  # data_x enumerated day
            yrenum = self._doy_xorigin.yrenum
            dayenum = self._doy_xorigin.dayenum + data_x
            if dayenum > 365:
                dayenum -= 366
                yrenum += 1
            mdy = (self._yrList[yrenum], *dayInt2MMDD(dayenum))

        elif self._type == PLOT_TYPE.HISTO:  # data_x enumerated day
            mdy = (self._yrList[self._yrenum], *dayInt2MMDD(data_x))
            # yVal = 2.0
            # zVal = 0.0

        for _key, np_vals in self._plty.items():
            if type(np_vals) is np.ndarray:
                yval = np_vals[data_x]
                if yval.ndim == 0:
                    rtnDict[_key] = 'nan' if yval is np.nan else f'{yval:.2f}'
                elif yval.ndim == 1:
                    rtnDict[_key] = ','.join(['{}'.format(int(x)) for x in yval])


        rtnDict['date'] = '-'.join([str(x) for x in mdy])
        return rtnDict

    @property
    def pltcolor(self) -> object:
        return self._colors[self._yrenum]

    def on_button3(self, event):
        """ Right Button within OHLC Plot Area
        """
        print('guiPlot.on_button3')

    def xform_tk_coords(self, tk_x, tk_y):
        """ Transform x,y coordinates in 'Display Space' to plot 'Data Space'
            Display Space 0,0 is top-left corner of frame, measured in pixels
            Data Space 0,0 is btm-left corner of plot BUT IS CLIPPED to plot limits
        """

        inv = self._ax0.transData.inverted()
        canvas_y = self._figure.bbox.height - tk_y
        canvas_x = tk_x
        xform_coords = inv.transform((canvas_x, canvas_y))

        xlimits = self._ax0.get_xlim()
        data_x = int(xlimits[0]) if xform_coords[0] < xlimits[0] \
          else int(xlimits[1]) if xform_coords[0] > xlimits[1] \
          else round(xform_coords[0])

        ylimits = self._ax0.get_ylim()
        data_y = ylimits[0] if xform_coords[1] < ylimits[0] \
          else ylimits[1] if xform_coords[1] > ylimits[1] \
          else xform_coords[1]

        return (data_x, data_y)

    def set_marker(self, data_x, data_y = None):
        """ data_x = yrenum
        """
        print('guiPlot.set_marker {} {}'.format(data_x, self._yrList[data_x]))
        # print(len(self._np_climate_data[data_x, :][self._obs]))
        print(len(self._np_climate_data[:, data_x][self._obs]))

        for _yr in range(self._np_climate_data.shape[0]):
            daymin = self._dayenum - 2
            daymax = self._dayenum + 3

            if daymin < 0: daymin = 0
            if daymax > 365: xmax = 365
            ma_vals = self._np_climate_data[_yr, daymin : daymax][self._obs]
            pts = ', '.join([f'{x:.2f}' for x in ma_vals])

            print(self._yrList[_yr], ',', pts, ',{:.3f}'.format(np.mean(ma_vals)))

    def set_cursor(self, data_x, data_y = None):
        if self._vertLine is None:
            self._vertLine = self._ax0.axvline(color='k', linewidth = 1, alpha=0.2)  # the vert line

        self._vertLine.set_xdata(data_x)
        self._ax0.figure.canvas.draw_idle()

    def plot(self, plotType, arg1=None, arg2=None, arg3=None):
        """ Perform requested plot operation depending on plotType.
            There are 3 types of plot: [SNGL_DOY, ALL_DOY, HISTO]
        """
        assert type(plotType) == PLOT_TYPE
        self._obs = arg1.lower()

        # Remove existing Plot graphics (i.e. MPL Artists) & Plot Data
        self._plty.clear()
        for _list in [self._sngldoy_artlist, self._alldoy_artlist, self._histo_artlist]:
            while _list:
                _art = _list.pop()
                _art.remove()

        # if self.xticks_xformed:
        #     self._ax0.set_xticks(ticks=[], labels=[])
        #     self.draw()
        #     print('Removed!')
        #
        # xticks = self._ax0.get_xticklabels()
        # print('Number of xticks = {}'.format(len(xticks)))

        # for _label in xticks:
        #     xform = _label.get_transform()
        #     print(f'{_label._x:3}, {_label._text}, {xform.depth}')

        # Perform the requested Plot
        if self._obs in ['tmin', 'tmax']:
            plt_data = PLOT_DATA.TEMP
        elif self._obs == 'prcp':
            plt_data = PLOT_DATA.RAIN
        else:
            raise ValueError
        self.plot_funcs[plotType](plt_data, arg2)

        ####################################
        # Apply MPL 'ScaledTranslation' to X-Axis Labels for ALLDOY Plots
        # and remove them for all other Plots.  To remove an XFORM, apply
        # an inverse.
        xlabels = self._ax0.xaxis.get_majorticklabels()

        xticks = self._ax0.get_xticklabels()
        for _label in xticks:
            xform = _label.get_transform()
            print(f'{_label._x:3}, {_label._text}, {xform.depth}')

        labels = self._ax0.get_xticklabels()
        xformlbls = self._xtick_xform_dict.keys()
        if plotType == PLOT_TYPE.ALLDOY:
            for _lblid, _lbl in enumerate(labels):
                if _lblid not in xformlbls:
                    self._xtick_xform_dict[_lblid] = _lbl.get_transform().depth
                    _lbl.set_transform(_lbl.get_transform() + self._tick_offset)
                    if _lblid > 5:
                        break
        else:
            for _lblid, _lbl in enumerate(labels):
                if _lblid in xformlbls:
                    _lbl.set_transform(_lbl.get_transform() - self._tick_offset)
                    del self._xtick_xform_dict[_lblid]
            print('remove!')
        #     for idx, label in enumerate(xlabels):
        #         try:
        #             inv_xform = self._xtick_xform_list[idx]
        #         except:
        #             print(type(label))
        #             label.set_transform(label.get_transform() + self._tick_offset)
        #             self._xtick_xform_list.append(self._tick_offset)
        # else:
        #     for idx, xform in enumerate(self._xtick_xform_list):
        #         label = xlabels[idx]
        #         label.set_transform(label.get_transform() - xform)
        #     self._xtick_xform_list.clear()
        ####################################

        self._type = plotType
        self._ax0.tick_params(axis='both', labelsize = 7)  # can't find rcParams for this
        self.draw()

    def plot_sngldoy(self, plt_dtype, day):
        """ Single Day of Year Plot Generation - X-Axis is enumerated years: 0..num_years - 1

            Special (i.e. UGLY) Processing for xtick Labels to REMOVE any offset transform.
            A matplotlib INVERSE 'ScaledTranslation' (i.e. subtraction) transform is applied to
            each label IF IT ALREADY APPLIED.  Applied transforms are maintained in _xtick_xform_list.
            ALL transforms ARE REMOVED from _xtick_xform_list to signal offset NO LONGER APPLIED.
        """

        self._dayenum = day
        self._ax0.grid(which = 'major', axis = 'both', color = gridcolor)
        self._ax0.xaxis.grid(True)

        # if self._type is None:  # Reconfigure Axes, Remove Twin
        self._ax0twin.set_axis_off()

        # Configure X-Axis
        xtendby = 4
        xlabels = list(range(self._yrList[0] + -xtendby, self._yrList[0])) \
                  + self._yrList \
                  + list(range(self._yrList[-1] + 1, self._yrList[-1] + xtendby))

        xlocs = list(range(-xtendby, len(xlabels) -xtendby))

        assert len(xlabels) == len(xlocs)

        xtickLocs, xDelta = guiPlot.nice_grid(xlocs[0], xlocs[-1])
        xtickLabels = [xlabels[xlocs.index(i)] for i in xtickLocs]

        self._ax0.set_xticks(xtickLocs)
        self._ax0.set_xticklabels(xtickLabels)
        self._ax0.set_xlim(xlocs[0], xlocs[-1])

        # Get the requested data and its average for the requested day
        obs_name = plt_dtype.name.lower()
        self._plty = self.sngldoy_data(plt_dtype, day)

        # Generated Plot depends on whether it is 1D or 2D (2D implies min/max temp)
        ymin = ymax = []
        x = np.arange(self._plty[obs_name].shape[0])
        if self._plty[obs_name].ndim == 1:
            spec = {obs_name: {'color': pltcolor1, 'label': 'SnglDay', 'width': 0.3, 'zorder': 10},
                    'avg':    {'color': pltcolor2, 'label': f'{self._ma_numdays}-ptma','width':  0.8, 'zorder': 5}}

            for _name, _opt in spec.items():
                y = self._plty[_name]
                prcp_bar = self._ax0.bar(x, y, **_opt)
                self._alldoy_artlist.append(prcp_bar)
                ymin.append(0.0)
                ymax.append(np.nanmax(y))

            prcp_legend = self._ax0.legend(bbox_to_anchor=(0.9, 1.0), loc='upper left')
            self._alldoy_artlist.append(prcp_legend)

            xlim = self._ax0.get_xlim()
            xscale = 1.0 / (xlim[1] - xlim[0])
            xend = (x[-1] - xlim[0])
            xstart = (x[0] - xlim[0])

            ma_mean = np.mean(self._plty['avg'])
            ma_stdev = np.std(self._plty['avg'])
            mean_line = self._ax0.axhline(ma_mean, xmin=xstart * xscale, \
                                          xmax=xend * xscale, color='blue', linestyle='--')

            self._sngldoy_artlist.append(mean_line)

            prcp_info = r'$\mu$' + '\n = {:.2f}'.format(ma_mean)
            prcp_text = self._ax0.text(xlim[0], ma_mean, prcp_info, fontsize = 7, color = 'blue')
            self._sngldoy_artlist.append(prcp_text)

        elif self._plty[obs_name].ndim == 2:
            figsize_points = self.figsize_inches[0] * 72
            xaxis_limits = self._ax0.get_xlim()
            xaxis_range = xaxis_limits[1] - xaxis_limits[0]
            lw = figsize_points / xaxis_range * 0.4

            spec = {plt_dtype.name.lower(): {'color': pltcolor1, 'linewidths': 0.4 * lw, 'zorder': 10},
                    'avg':                {'color': pltcolor2, 'linewidths': 1.0 * lw, 'zorder': 5}}

            for _name, _opt in spec.items():
                y = self._plty[_name]
                p1 = np.stack((x, y[:, 0]), axis=1)             # M x 2  (x,y1)
                p2 = np.stack((x, y[:, 1]), axis=1)             # M x 2  (x,y2)
                segs = np.swapaxes(np.stack((p1, p2)), 0, 1)    # 2 x M x 2 -> M x 2 x 2
                lineSegs = LineCollection(segs, **_opt)

                self._ax0.add_collection(lineSegs)
                self._sngldoy_artlist.append(lineSegs)
                ymin.append(np.nanmin(p1))
                ymax.append(np.nanmax(p2))

            ymin_avg = np.mean(self._plty['avg'][:, 0])
            ymax_avg = np.mean(self._plty['avg'][:, 1])
            ymin_std = np.std(self._plty['avg'][:, 0])
            ymax_std = np.std(self._plty['avg'][:, 1])

            val_list = [ymin_avg - ymin_std, ymax_avg + ymax_std]
            print(val_list)
            color_list = ['blue', 'firebrick']
            text_list = ['ymin\n' + r'$\mu - \sigma$', 'ymax\n' + r'$\mu + \sigma$']
            for _avg, _color, _text in zip(val_list, color_list, text_list):
                ymean_hline = self._ax0.axhline(_avg, xmin = x[0], xmax = x[-1],
                                                color = _color, linestyle = '--')
                self._sngldoy_artlist.append(ymean_hline)

                info_text = self._ax0.text(xaxis_limits[0], _avg, _text, color = _color, fontsize = 8, va = 'top')
                self._sngldoy_artlist.append(info_text)

        ymin = np.min(ymin)
        ymax = np.max(ymax)
        yticks, ydelta = guiPlot.nice_grid(ymin, ymax)
        self._ax0.set_ylim((0, yticks[-1]))
        self._ax0.set_yticks(yticks)

        if plt_dtype == PLOT_DATA.TEMP:
            ttl = 'Temperature'
        elif plt_dtype == PLOT_DATA.RAIN:
            ttl = 'Rain Precipitation'
        else:
            raise ValueError
        self._ax0.set_title(f'{self._station} {dayInt2Label(day)}  -' + ttl)
        # self.do_sngldoy(plt_dtype, day)

    def plot_alldoy(self, plt_dtype, yrenum):
        """ All Days of Year Plot Generation - X-Axis is enumerated days 0..365
            BUT DATA[0] DOES NOT NECESSARILY CORRESPOND WITH JAN-1 IF yrenum == current_yr !
            Instead, data is shifted so that DATA[0] corresponds with 1st day of next month.

            Special (i.e. UGLY) Processing for xtick Labels to center the MonthLabels between
            tick marks.  A matplotlib 'ScaledTranslation' transform is applied to each label
            IF IT ISN'T ALREADY APPLIED.  Applied transforms are maintained in _xtick_xform_list.
        """
        self._yrenum = yrenum

        # Determine Origin for X-Axis, Depends on Current Data
        today = date.today()
        plotYear = self._yrList[self._yrenum]
        if plotYear == today.year:
            xorigin_yr = self._yrenum -1
            xorigin_mm = today.month
        else:
            xorigin_yr = self._yrenum
            xorigin_mm = 0

        xorigin_dd = self._daysum[xorigin_mm]
        self._doy_xorigin = DATE_ENUM(xorigin_yr, xorigin_dd)
        self._ax0.yaxis.grid(visible=True, color=gridcolor)
        self._ax0.xaxis.grid(visible=True, color=gridcolor)

        ### Remove any xlabel transforms ###
        # xlabels = self._ax0.xaxis.get_majorticklabels()
        # for idx, xform in enumerate(self._xtick_xform_list):
        #     label = xlabels[idx]
        #     label.set_transform(label.get_transform() - xform)
        # self._xtick_xform_list.clear()
        ####################################

        if plt_dtype == PLOT_DATA.TEMP:
            self._ax0twin.set_axis_off()
            self.do_alldoy_temp(yrenum, self._doy_xorigin)
        elif plt_dtype == PLOT_DATA.RAIN:
            self._ax0twin.set_axis_on()
            self.do_alldoy_prcp(yrenum, self._doy_xorigin)
        else:
            raise ValueError

        tics = []
        xorigin = self._doy_xorigin.dayenum

        month_1 = self._daysum.index(xorigin)
        xorder = list(range(month_1, 12)) + list(range(0, month_1))
        for x in range(1, 13):
            items = [xorder[y] for y in range(x)]
            tics.append(sum([mm2days[y] for y in items]))

        xlabels = [mmlabels[x] for x in xorder]
        self._ax0.set_xticks(tics)
        self._ax0.set_xticklabels(xlabels)
        # print(tics)
        # print(xlabels)

        self._ax0.set_xlim(0,366)

        # if xtick[0] == 366:
        #     xtick = []
        #     xlabels = []
        # self._ax0.set_xticks(xtick)
        # self._ax0.set_xticklabels(xlabels)


    def plot_histo(self, plt_dtype: PLOT_DATA, dayenum: int):
        """ X-Axis =
        """
        obs_name = plt_dtype.name.lower()
        histData = self.sngldoy_data(plt_dtype, dayenum)

        # self._dayenum = dayenum
        # self._ax0.set_title(f'{self._station} {dayint2label(dayenum)} histograph   -  {self._obs}')
        x = histData[obs_name]
        # x = self._np_ma_byday[:, dayenum]

        bin_low = np.around(np.min(x), -1)
        bin_high = np.max(x)

        values, bins, container = self._ax0.hist(x, range = (bin_low, bin_high), bins = 25, color = 'blue')
        self._histo_artlist.append(container)

        # Y-Axis Grid & Ticks
        ymax = np.round_(np.max(values), 1)
        yticks, ydelta = guiPlot.nice_grid(0, ymax)
        yticks += [yticks[-1] + ydelta]

        self._ax0.set_ylim((yticks[0], yticks[-1]))
        self._ax0.set_yticks(yticks)

        print(f'Plot Histograph {bins} {bin_low}, {bin_high}, {self._ax0.get_xlim()}')
        self._ax0.set_xticks(bins)
        xtickLabels = ['{:.3f}'.format(x) for x in bins]
        self._ax0.set_xticklabels(xtickLabels)

        self._ax0.set_xlim((bins[0],bins[-1]))

    def do_sngldoy(self, pltData: PLOT_DATA, day: int):
        """ Create Plot with x-Axis representing the same day across multiple years
            The plot is either 2X MPL 'bar artists' OR 2X MPL 'line collections'.
            Which depends on whether the specified data is 1D or 2D.
              1D Plot Data -> 2X Bar Plots
              2D Plot Data -> 2X LineCollection Plots

        """
        # Get the requested data and its average for the requested day
        obs_name = pltData.name.lower()
        self._plty = self.sngldoy_data(pltData, day)

        # Generated Plot depends on whether it is 1D or 2D (2D implies min/max temp)
        ymin = ymax = []
        x = np.arange(self._plty[obs_name].shape[0])
        if self._plty[obs_name].ndim == 1:
            spec = {obs_name: {'color': pltcolor1, 'label': 'SnglDay', 'width': 0.3, 'zorder': 10},
                    'avg':    {'color': pltcolor2, 'label': f'{self._ma_numdays}-ptma','width':  0.8, 'zorder': 5}}

            for _name, _opt in spec.items():
                y = self._plty[_name]
                prcp_bar = self._ax0.bar(x, y, **_opt)
                self._alldoy_artlist.append(prcp_bar)
                ymin.append(0.0)
                ymax.append(np.nanmax(y))

            prcp_legend = self._ax0.legend(bbox_to_anchor=(0.9, 1.0), loc='upper left')
            self._alldoy_artlist.append(prcp_legend)

            xlim = self._ax0.get_xlim()
            xscale = 1.0 / (xlim[1] - xlim[0])
            xend = (x[-1] - xlim[0])
            xstart = (x[0] - xlim[0])

            ma_mean = np.mean(self._plty['avg'])
            ma_stdev = np.std(self._plty['avg'])
            mean_line = self._ax0.axhline(ma_mean, xmin=xstart * xscale, \
                                          xmax=xend * xscale, color='blue', linestyle='--')

            self._sngldoy_artlist.append(mean_line)

            prcp_info = r'$\mu$' + '\n = {:.2f}'.format(ma_mean)
            prcp_text = self._ax0.text(xlim[0], ma_mean, prcp_info, fontsize = 7, color = 'blue')
            self._sngldoy_artlist.append(prcp_text)

        elif self._plty[obs_name].ndim == 2:
            figsize_points = self.figsize_inches[0] * 72
            xaxis_limits = self._ax0.get_xlim()
            xaxis_range = xaxis_limits[1] - xaxis_limits[0]
            lw = figsize_points / xaxis_range * 0.4

            spec = {pltData.name.lower(): {'color': pltcolor1, 'linewidths': 0.4 * lw, 'zorder': 10},
                    'avg':                {'color': pltcolor2, 'linewidths': 1.0 * lw, 'zorder': 5}}

            for _name, _opt in spec.items():
                y = self._plty[_name]
                p1 = np.stack((x, y[:, 0]), axis=1)             # M x 2  (x,y1)
                p2 = np.stack((x, y[:, 1]), axis=1)             # M x 2  (x,y2)
                segs = np.swapaxes(np.stack((p1, p2)), 0, 1)    # 2 x M x 2 -> M x 2 x 2
                lineSegs = LineCollection(segs, **_opt)

                self._ax0.add_collection(lineSegs)
                self._sngldoy_artlist.append(lineSegs)
                ymin.append(np.nanmin(p1))
                ymax.append(np.nanmax(p2))

            ymin_avg = np.mean(self._plty['avg'][:, 0])
            ymax_avg = np.mean(self._plty['avg'][:, 1])
            ymin_std = np.std(self._plty['avg'][:, 0])
            ymax_std = np.std(self._plty['avg'][:, 1])

            val_list = [ymin_avg - ymin_std, ymax_avg + ymax_std]
            print(val_list)
            color_list = ['blue', 'firebrick']
            text_list = ['ymin\n' + r'$\mu - \sigma$', 'ymax\n' + r'$\mu + \sigma$']
            for _avg, _color, _text in zip(val_list, color_list, text_list):
                ymean_hline = self._ax0.axhline(_avg, xmin = x[0], xmax = x[-1],
                                                color = _color, linestyle = '--')
                self._sngldoy_artlist.append(ymean_hline)

                info_text = self._ax0.text(xaxis_limits[0], _avg, _text, color = _color, fontsize = 8, va = 'top')
                self._sngldoy_artlist.append(info_text)

        ymin = np.min(ymin)
        ymax = np.max(ymax)
        yticks, ydelta = guiPlot.nice_grid(ymin, ymax)
        self._ax0.set_ylim((0, yticks[-1]))
        self._ax0.set_yticks(yticks)

        if pltData == PLOT_DATA.TEMP:
            ttl = 'Temperature'
        elif pltData == PLOT_DATA.RAIN:
            ttl = 'Rain Precipitation'
        else:
            raise ValueError
        self._ax0.set_title(f'{self._station} {dayInt2Label(day)}  -' + ttl)

    def do_alldoy_temp(self, yrenum, xorigin):
        """ Add a LineCollection (min to max for each day) to ax0
            Add 2X lines to ax0 (temperature mean(min) & mean(max))

            yrenum : 0..n, index to self.yrList
        """
        assert type(xorigin) == DATE_ENUM
        self._plty = self.alldoy_data(PLOT_DATA.TEMP, xorigin)

        ptList = []
        for _key in ['tmin', 'tmax']:
            x = np.argwhere(~np.isnan(self._plty[_key]))
            y = self._plty[_key][x].flatten()
            pt = np.stack((x.flatten(), y), axis=1)                 # M x 2  (x,y)
            ptList.append(pt)
            if _key == 'tmin':
                ylim_min = np.min(y)
            else:
                ylim_max = np.max(y)
        ptStack = np.stack((ptList[0], ptList[1]))        # 2 x M x 2 -> M x 2 x 2
        segs = np.swapaxes(ptStack, 0, 1)

        lineSegs = LineCollection(segs, colors=[pltcolor1] * len(x))
        self._ax0.add_collection(lineSegs)
        self._alldoy_artlist.append(lineSegs)

        x = np.arange(366, dtype = int)
        colors = {'tmin' : 'navy', 'tmax' : 'firebrick'}
        for _k in colors.keys():
            y = self._np_alldoy_mean[_k]
            lc_mean = self._ax0.plot(x, y, color=colors[_k], linewidth = 0.5)[0]
            self._alldoy_artlist.append(lc_mean)
        # for _k, _npa in self._np_temperature_means.items():
        #     lc_mean = self._ax0.plot(x, _npa, color = colors[_k], linewidth = 0.5)[0]
        #     self._alldoy_artlist.append(lc_mean)

        # all_min = self._plty['tmin']
        # all_max = self._plty['tmax']
        # all_min = np.concatenate((self._plty['tmin'], self._alldoy_mean['tmin']))
        # all_max = np.concatenate((self._plty['tmax'], self._alldoy_mean['tmax']))

        # ylim_min = np.min(all_min)
        yscale = guiPlot.nice_scale(ylim_min)
        yrange_min = int(np.floor(yscale * ylim_min) / yscale)

        # ylim_max = int(np.max(all_max))
        yticks, ydelta = guiPlot.nice_grid(yrange_min, ylim_max)
        yticks += [yticks[-1] + ydelta]

        self._ax0.set_ylim((yrange_min, yticks[-1]))
        self._ax0.set_yticks(yticks)
        self._ax0.set_title(f'{self._station} {self._yrList[xorigin.yrenum]}  -  Tmin - Tmax')

    def do_alldoy_prcp(self, yrenum, xorigin: DATE_ENUM):
        """ Create Plot with X-Axis of 366 days, The starting position is xorigin
            Adds [prcp] as bar to ax0,  Adds [prcp_ma] AND [prcp_ltmean] as lines to ax0twin
        """
        assert type(xorigin) == DATE_ENUM
        self._plty = self.alldoy_data(PLOT_DATA.RAIN, xorigin)

        goodIndx = np.argwhere(~np.isnan(self._plty['prcp']))
        y = self._plty['prcp'][goodIndx].flatten()
        x = goodIndx.flatten()

        self._alldoy_artlist.append(self._ax0.bar(x, y, color = pltcolor1, label = 'SnglDay', zorder = 10))

        ymax = np.round_(np.max(y), 1)
        yticks, ydelta = guiPlot.nice_grid(0, ymax)
        yticks += [yticks[-1] + ydelta]

        self._ax0.set_ylim((0, yticks[-1]))
        self._ax0.set_yticks(yticks)

        # Twin Axis
        y = self._plty['prcp_ma']
        maxy1 = np.max(y)
        x = np.arange(len(y))
        self._alldoy_artlist.append(self._ax0twin.plot(x, y, color = pltcolor2,
                                                       label = f'{self._ma_numdays}day_ma')[0])
        #
        y = self._plty['prcp_ltmean']
        maxy2 = np.max(y)
        self._alldoy_artlist.append(self._ax0twin.plot(x, y, color = pltcolor3, linewidth = 0.5, linestyle = '-',
                                                       label = f'{self._np_climate_data.shape[0]}-yr avg')[0])
        maxy = np.max([maxy1, maxy2])
        yscale = guiPlot.nice_scale(maxy)
        ylim = np.ceil(10. * yscale * maxy) / (10. * yscale)
        self._ax0twin.set_ylim([0, ylim])

        self._ax0twin.set_axis_on()
        self._ax0twin.tick_params(axis='both', labelsize = 7)  # can't find rcParams for this

        self._alldoy_artlist.append(self._ax0.legend(bbox_to_anchor = (0.0, 1.07), loc = 'upper left'))
        self._alldoy_artlist.append(self._ax0twin.legend(bbox_to_anchor = (0.9, 1.07), loc = 'upper left'))

        self._ax0.set_title(f'{self._station} {self._yrList[yrenum]}  -  Rain Precipitation')

    def write_pdf(self, fname):
        pdfObj = PdfPages(fname)
        pdfObj.savefig(self._figure)
        pdfObj.close()
        print('write pdf')
