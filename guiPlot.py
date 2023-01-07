""" A matplotlib derived class that 'acts' like a tkinter canvas Widget.
    The guiPlot constructor requires a tkinter 'parent' Widget and numpy 2D Structured Array.

    The guiPlot object generates an 3 Different Plots depending on its PLOT_TYPE: ALL_DOY, SNGL_DOY, HISTO
    Calls to the plot(type, arg1, ..) method will cause 1 of 3 plots to be generated.
    The guiPlot object maintains a lists of matplotlib graphics objects that are 'removed' prior
    to generating a new plot.
"""
from __future__ import annotations   # Fix Type Hint Problem

from enum        import IntEnum
from calendar    import month_abbr
from collections import namedtuple

import re
import numpy as np
import tkinter as tk
import tkinter.ttk as ttk
import matplotlib as mpl
import matplotlib.transforms as mpl_xforms

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
PLOT_TYPE = IntEnum('PLOT_TYPE', ['ALL_DOY', 'SNGL_DOY', 'HISTO'])
DATE_N_VAL = namedtuple('DATE_N_VAL',  ['datetup', 'val'])

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

    @staticmethod
    def _calc_mean(npdict):
        result_mean = {}
        for _key, _npa in npdict.items():
            result_mean[_key] = np.nanmean(_npa, axis = 0)
        return result_mean


    @staticmethod
    def _calc_ma(np_srcdata, obs, ma_window_sz):
        """ Calculate Centered Moving Average for each 'obs' value of the src_data.
            src_data must to be numpy 2D structured array with named fields for each element.
            'obs' is the field name of the value whose moving average is calculated.
        """
        w_2 = int(ma_window_sz/2)

        result_shape = np_srcdata.shape           # Result Numpy Array
        result_dtype = np_srcdata[:,:][obs].dtype
        result_ma = np.empty(result_shape, dtype = result_dtype)

        for _dim0 in range(result_shape[0]):
            # Extend Data with previous/next data if available
            extra_before = np.zeros(w_2, dtype = result_dtype)
            extra_after = np.zeros(w_2, dtype = result_dtype)

            if _dim0 != 0:
                extra_before = np_srcdata[_dim0 - 1][obs][-w_2:]

            if _dim0 != result_shape[0] - 1:
                extra_after = np_srcdata[_dim0 + 1][obs][:w_2]

            extended_data = np.concatenate((extra_before, np_srcdata[_dim0,:][obs], extra_after))
            np.nan_to_num(extended_data, copy = False)

            ma_vals = np.convolve(extended_data, np.ones(ma_window_sz, dtype = result_dtype))/ma_window_sz
            result_ma[_dim0] = ma_vals[ma_window_sz-1:-ma_window_sz+1]

        result_mean = np.nanmean(np_srcdata[obs], axis = 0)
        result_stdev = np.nanstd(np_srcdata[obs], axis = 0)

        # x = np_srcdata[:,0][obs]
        # y = np.mean(x)
        # print(mean_dim1[0], y)

        # x = np_srcdata[:,22][obs]
        # y = np.mean(x)

        return result_mean, result_stdev, result_ma

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

        # Calculate mean temperatures for each day of year
        self._np_temperature_means = {}
        for _key in np_climate_data.dtype.names:
            if _key in ['tmin', 'tmax']:
                self._np_temperature_means[_key] = np.nanmean(np_climate_data[:,:][_key], axis = 0)

        self._mean_byday = None
        self._stdev_byday = None
        self._ma_byday = None

        self._obs  = None          # Observation, np_climate_data field name
        self._type = None          # Type of Plot of PLOT_TYPE
        self._obs_max = None
        self._ma_numdays = 15       # Moving Avg Window Size

        self._dayenum  = 0         # Valid if type == SNGL_DOY
        self._yrenum = np_climate_data.shape[0] - 1

        # A Dict to match plot function to plot type
        self.plot_funcs = {PLOT_TYPE[_type] : getattr(self, 'plot_' + _type.lower()) \
                           for _type in PLOT_TYPE.__members__}

        self._figure = Figure(figsize = [x/guiPlot.canvas_dpi for x in figsize], dpi=guiPlot.canvas_dpi)
        self._figure.subplots_adjust(left = 0.04, right = .95, top = .95, bottom = .07)
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
        self._horzLine = None

        # self._tk_canvas.bind("<Button-3>", self.on_button3)

        mpl.rc('lines',  markersize = 2)
        mpl.rc('ytick',  labelsize  = 8)
        mpl.rc('xtick',  labelsize  = 10)
        mpl.rc('lines',  linewidth  = 0.7)
        mpl.rc('legend', fontsize   = 8)
        mpl.rc('axes',   titlesize  = 9)

        cstep = 1.0/len(self._yrList)
        self._colors = [mpl.colormaps['brg'](x) for x in np.arange(0, 1.0, cstep)]

        self.set_cursor(0)
        # Special Variables to Manage Position XTick Labels
        self._tick_offset = mpl_xforms.ScaledTranslation(-20/72, 0, self._figure.dpi_scale_trans)
        self._xtick_xform_list = []

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

    def temp_byyr(self, year):
        tmin_data = self._np_climate_data[year]['tmin']
        tmin_indicies = np.argwhere(~np.isnan(tmin_data))

        tmax_data = self._np_climate_data[year]['tmax']
        tmax_indicies = np.argwhere(~np.isnan(tmax_data))

        if not np.array_equal(tmin_indicies, tmax_indicies):
            raise ValueError

        x = tmin_indicies.flatten()
        ymin = tmin_data[x].flatten()
        ymax = tmax_data[x].flatten()

        return x, (ymin, ymax)

    def temp_byday(self, day):
        tmin_data = self._np_climate_data[:, day]['tmin']
        tmin_indicies = np.argwhere(~np.isnan(tmin_data))

        tmax_data = self._np_climate_data[:, day]['tmax']
        tmax_indicies = np.argwhere(~np.isnan(tmax_data))

        if not np.array_equal(tmin_indicies, tmax_indicies):
            raise ValueError

        x = tmin_indicies.flatten()
        ymin = tmin_data[x].flatten()
        ymax = tmax_data[x].flatten()

        return x, (ymin, ymax)

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
        if self._type == PLOT_TYPE.SNGL_DOY:  # data_x enumerated year
            yrenum = 0 if data_x < 0 else data_x
            yrenum = len(self._yrList) - 1 if yrenum >= len(self._yrList) else yrenum
            mdy = (self._yrList[yrenum], *dayInt2MMDD(self._dayenum))

        elif self._type == PLOT_TYPE.ALL_DOY:  # data_x enumerated day
            dayenum = data_x
            mdy = (self._yrList[self._yrenum], *dayInt2MMDD(data_x))

        elif self._type == PLOT_TYPE.HISTO:  # data_x enumerated day
            mdy = (self._yrList[self._yrenum], *dayInt2MMDD(data_x))
            # yVal = 2.0
            # zVal = 0.0

        if self._obs == 'prcp':
            rtnDict[self._obs] = f'{self._np_climate_data[yrenum, dayenum][self._obs]:.2f}'
            rtnDict[makey] = f'{self._np_ma_byday[yrenum, dayenum]:.2f}'

        elif self._obs in tkeys:
            for _key in tkeys:
                rtnDict[_key] = f'{self._np_climate_data[yrenum, dayenum][_key]:.0f}'

        rtnDict['date'] = '-'.join([str(x) for x in mdy])
        return rtnDict

    @property
    def pltcolor(self):
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
        # for _ in self._np_climate_data[:, data_x][self._obs]:
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


    def plot(self, plotType, arg1 = None, arg2 = None, arg3 = None):
        """ Perform requested plot operation depending on plotType.
            There are 3 types of plot: [SNGL_DOY, ALL_DOY, HISTO]
        """
        # print('plot {} {} {}'.format(plotType.name, arg1, arg2))
        # mpl.rcParams.update({"grid.color": gridcolor})

        assert type(plotType) == PLOT_TYPE
        new_obs = arg1.lower()

        if plotType != self._type:   # Signal Axes Need Reconfigured
            self._type = None

        # Remove existing Plot graphics (i.e. MPL Artists)
        for _list in [self._sngldoy_artlist, self._alldoy_artlist, self._histo_artlist]:
            while _list:
                _art = _list.pop()
                _art.remove()

        # Processing if the Observation Type changes: calc moving avg & max values
        if new_obs != self._obs:
            self._obs = new_obs
            self._np_mean_byday, self._np_stdev_byday, self._np_ma_byday \
              = guiPlot._calc_ma(self._np_climate_data, self._obs, self._ma_numdays)

            obs_data = self._np_climate_data[:, :][self._obs]
            index_flat = np.nanargmax(obs_data)
            index_2d = np.divmod(index_flat, obs_data.shape[1])

            obs_value = self._np_climate_data[index_2d][self._obs]
            obs_datetup = (self._yrList[index_2d[0]], *dayInt2MMDD(index_2d[1]))
            self._obs_max = DATE_N_VAL(obs_datetup, obs_value)

            if self._horzLine:
                self._horzLine.remove()

            # self._horzLine = self._ax0.axhline(obs_value)

        self.plot_funcs[plotType](arg2, None)
        self._type = plotType

        self._ax0.tick_params(axis='both', labelsize = 7)  # can't find rcParams for this
        self.draw()

    def plot_sngl_doy(self, day, reserved):
        """ Single Day of Year Plot Generation - X-Axis is enumerated years: 0..num_years - 1

            Special (i.e. UGLY) Processing for xtick Labels to REMOVE any offset transform.
            A matplotlib INVERSE 'ScaledTranslation' (i.e. subtraction) transform is applied to
            each label IF IT ALREADY APPLIED.  Applied transforms are maintained in _xtick_xform_list.
            ALL transforms ARE REMOVED from _xtick_xform_list to signal offset NO LONGER APPLIED.
        """
        ### Remove any xlabel transforms ###
        xlabels = self._ax0.xaxis.get_majorticklabels()
        for idx, xform in enumerate(self._xtick_xform_list):
            label = xlabels[idx]
            label.set_transform(label.get_transform() - xform)
        self._xtick_xform_list.clear()
        ####################################

        self._dayenum = day
        self._ax0.grid(which = 'major', axis = 'both', color = gridcolor)
        self._ax0.xaxis.grid(True)

        if self._type == None:  # Reconfigure Axes, Remove Twin
            self._ax0twin.set_axis_off()

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

        if self.istemp:
            self.do_sngldoy_temp(day)
            self._ax0.set_title(f'{self._station} {dayInt2Label(day)}  -  Temperature min:max')
        else:
            self.do_sngldoy_prcp(day)
            self._ax0.set_title(f'{self._station} {dayInt2Label(day)}  -  Rain Precipitation')


    def plot_all_doy(self, yrenum, reserved):
        """ All Days of Year Plot Generation - X-Axis is enumerated days 0..365

            Special (i.e. UGLY) Processing for xtick Labels to center the MonthLabels between
            tick marks.  A matplotlib 'ScaledTranslation' transform is applied to each label
            IF IT ISN'T ALREADY APPLIED.  Applied transforms are maintained in _xtick_xform_list.
        """
        self._yrenum = yrenum
        self._ax0.yaxis.grid(visible = True, color = gridcolor)
        self._ax0.xaxis.grid(visible = True, color = gridcolor)

        if self.istemp:
            self._ax0twin.set_axis_off()
            self.do_alldoy_temp(yrenum)
        else:
            self._ax0twin.set_axis_on()
            self.do_alldoy_prcp(yrenum)

        if self._type == None:  # Reconfigure Axes, Remove Twin
            self._ax0.set_xlim(0,365)

            grid = [sum(mm2days[:x]) for x in range(1,len(mm2days)+1)]
            self._ax0.set_xticks(grid)
            self._ax0.set_xticklabels(mmlabels[:12])

            for idx, label in enumerate(self._ax0.xaxis.get_majorticklabels()):
                try:
                    inv_xform = self._xtick_xform_list[idx]
                except:
                    label.set_transform(label.get_transform() + self._tick_offset)
                    self._xtick_xform_list.append(self._tick_offset)


    def plot_histo(self, dayenum, reserved2):
        """ X-Axis =
        """

        self._dayenum = dayenum
        self._ax0.set_title(f'{self._station} {dayInt2Label(dayenum)} Histograph   -  {self._obs}')

        x = self._np_ma_byday[:, dayenum]

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


    def do_sngldoy_temp(self, day):
        """ Generate a Series of Lines for [tmin:tmax] for single Month/Day.
            X-Axis is the Year of each [tmin:tmax] Line.
        """
        # tmin:tmax Line Width Calculation
        figsize_points = self.figsize_inches[0] * 72
        xaxis_limits = self._ax0.get_xlim()
        xaxis_range = xaxis_limits[1] - xaxis_limits[0]
        lw = figsize_points / xaxis_range * 0.4

        lcList = []
        x, (ymin, ymax) = self.temp_byday(day)
        ymin_avg = np.mean(ymin)
        ymin_std = np.std(ymin)

        ymax_avg = np.mean(ymax)
        ymax_std = np.std(ymax)

        p1 = np.stack((x, ymin), axis = 1)   # M x 2  (x,y1)
        p2 = np.stack((x, ymax), axis = 1)   # M x 2  (x,y2)
        segs = np.swapaxes(np.stack((p1,p2)), 0, 1)        # 2 x M x 2 -> M x 2 x 2
        lineSegs = LineCollection(segs, colors = [pltcolor1] * len(x), linewidths = [lw] * len(x))

        self._ax0.add_collection(lineSegs)
        self._sngldoy_artlist.append(lineSegs)

        val_list = [ymin_avg - ymin_std, ymax_avg + ymax_std]
        color_list = ['blue', 'firebrick']
        text_list = ['ymin\n' + r'$\mu - \sigma$', 'ymax\n' + r'$\mu + \sigma$']
        # val_list = [ymin_avg, ymin_avg - ymin_std, ymax_avg, ymax_avg - ymax_std]
        # color_list = ['blue', 'blue', 'firebrick', 'firebrick']
        for _avg, _color, _text in zip(val_list, color_list, text_list):
            ymean_hline = self._ax0.axhline(_avg, xmin = x[0], xmax = x[-1],
                                            color = _color, linestyle = '--')
            self._sngldoy_artlist.append(ymean_hline)

            info_text = self._ax0.text(xaxis_limits[0], _avg, _text, color = _color, fontsize = 8, va = 'top')
            self._sngldoy_artlist.append(info_text)

        ylim_min = np.min(ymin)
        yscale = guiPlot.nice_scale(ylim_min)
        yrange_min = int(np.floor(yscale * ylim_min) / yscale)

        ylim_max = int(np.max(ymax))
        yticks, ydelta = guiPlot.nice_grid(yrange_min, ylim_max)
        yticks += [yticks[-1] + ydelta]

        self._ax0.set_ylim((yrange_min, yticks[-1]))
        self._ax0.set_yticks(yticks)
        self._ax0.yaxis.grid(True)


    def do_sngldoy_prcp(self, day):
        """ Add matplotlib 'Artists' to Primary Axis to display 2X bar plots with legend
            All 3 'Artist' objects are added to alldoy_artlist so they can be removed latter.
        """

        # Primary Axis
        num_pts = self._np_climate_data.shape[0]
        x = np.arange(num_pts)
        y = self._np_climate_data[:, day][self._obs]
        y2 = self._np_ma_byday[:, day]

        prcp_bar = self._ax0.bar(x, y2, color = pltcolor2, label = f'{self._ma_numdays}-pt mov_avg', width = 0.8, zorder = 5)
        self._alldoy_artlist.append(prcp_bar)

        prcp_bar = self._ax0.bar(x, y, color = pltcolor1, label = 'SnglDay', width = .3, zorder = 10)
        self._alldoy_artlist.append(prcp_bar)

        prcp_legend = self._ax0.legend(bbox_to_anchor = (0.9, 1.0), loc = 'upper left')
        self._alldoy_artlist.append(prcp_legend)

        ymax = np.round_(np.nanmax(y), 1)

        # yticks, ydelta = guiPlot.nice_grid(0, ymax)
        # yticks += [yticks[-1] + ydelta]

        # self._ax0.set_ylim((0, yticks[-1]))
        # self._ax0.set_yticks(yticks)

        maxy = np.max(self._np_ma_byday)
        yscale = guiPlot.nice_scale(maxy)
        ylim = round(10.0 * yscale * maxy) / (10.0 * yscale)

        yticks, ydelta = guiPlot.nice_grid(0, ylim)
        yticks += [yticks[-1] + ydelta]

        self._ax0.set_ylim((0, yticks[-1]))
        self._ax0.set_yticks(yticks)

        # self._ax0.set_ylim([0, ylim])
        print('do_sngldoy_prcp {:.2f} {:.2f}'.format(ymax, yticks[-1]))

        xlim = self._ax0.get_xlim()
        xscale = 1.0 / (xlim[1] - xlim[0])
        xend = (x[-1] - xlim[0])
        xstart = (x[0] - xlim[0])

        ma_mean = np.mean(y2)
        ma_stdev = np.std(y2)

        prcp_line = self._ax0.axhline(ma_mean, xmin = xstart * xscale, \
                                      xmax = xend * xscale, color = 'blue', linestyle = '--')
        self._sngldoy_artlist.append(prcp_line)

        prcp_info = r'$\mu$' + '\n = {:.2f}'.format(ma_mean)
        prcp_text = self._ax0.text(xlim[0], ma_mean, prcp_info, fontsize = 7, color = 'blue')
        self._sngldoy_artlist.append(prcp_text)

        if self._vertLine: self._vertLine.set_xdata(self._yrenum)


    def do_alldoy_temp(self, year):
        """ Add a LineCollection to ax0
        """
        self._ax0.set_title(f'{self._station} {self._yrList[year]}  -  Tmin - Tmax')
        x, (ymin, ymax) = self.temp_byyr(year)

        lcList = []
        p1 = np.stack((x, ymin), axis = 1)   # M x 2  (x,y1)
        p2 = np.stack((x, ymax), axis = 1)   # M x 2  (x,y2)
        segs = np.swapaxes(np.stack((p1,p2)), 0, 1)        # 2 x M x 2 -> M x 2 x 2

        lineSegs = LineCollection(segs, colors = [pltcolor1] * len(x))

        self._ax0.add_collection(lineSegs)
        self._alldoy_artlist.append(lineSegs)

        ylim_min = np.min(ymin)
        yscale = guiPlot.nice_scale(ylim_min)
        yrange_min = int(np.floor(yscale * ylim_min) / yscale)

        ylim_max = int(np.max(ymax))
        yticks, ydelta = guiPlot.nice_grid(yrange_min, ylim_max)
        yticks += [yticks[-1] + ydelta]

        self._ax0.set_ylim((yrange_min, yticks[-1]))
        self._ax0.set_yticks(yticks)


        x = np.arange(366, dtype = int)
        colors = {'tmin' : 'navy', 'tmax' : 'firebrick'}
        for _k, _npa in self._np_temperature_means.items():
            lc_mean = self._ax0.plot(x, _npa, color = colors[_k], linewidth = 0.5)[0]
            self._alldoy_artlist.append(lc_mean)

    def do_alldoy_prcp(self, year):
        self._ax0.set_title(f'{self._station} {self._yrList[year]}  -  Rain Precipitation')
        # self._ax0twin.yaxis.grid(visible = True, color = gridcolor)

        focus_data = self._np_climate_data[year][self._obs]
        valid_indicies = np.argwhere(~np.isnan(focus_data))
        valid_data = focus_data[valid_indicies]

        # Primary Axis
        x = valid_indicies.flatten()
        y = valid_data.flatten()
        self._alldoy_artlist.append(self._ax0.bar(x, y, color = pltcolor1, label = 'SnglDay', zorder = 10))

        ymax = np.round_(np.max(y), 1)
        yticks, ydelta = guiPlot.nice_grid(0, ymax)
        yticks += [yticks[-1] + ydelta]

        self._ax0.set_ylim((0, yticks[-1]))
        self._ax0.set_yticks(yticks)

        # Twin Axis
        y = self._np_ma_byday[self._yrenum]
        x = np.arange(len(y))
        self._alldoy_artlist.append(self._ax0twin.plot(x, y, color = pltcolor2,
                                                       label = f'{self._ma_numdays}day_ma')[0])

        maxy = np.max(y)
        yscale = guiPlot.nice_scale(maxy)
        ylim = round(yscale * maxy) / yscale
        self._ax0twin.set_ylim([0, ylim])

        y = self._np_mean_byday
        self._alldoy_artlist.append(self._ax0twin.plot(x, y, color = pltcolor3, linewidth = 0.5, linestyle = '-',
                                                       label = f'{self._np_climate_data.shape[0]}-yr avg')[0])

        if self._type == None:  # Reconfigure Axes, Enable Twin Axis
            self._ax0twin.set_axis_on()
            self._ax0twin.tick_params(axis='both', labelsize = 7)  # can't find rcParams for this

        self._alldoy_artlist.append(self._ax0.legend(bbox_to_anchor = (0.0, 1.07), loc = 'upper left'))
        self._alldoy_artlist.append(self._ax0twin.legend(bbox_to_anchor = (0.9, 1.07), loc = 'upper left'))

    def write_pdf(self, fname):
        pdfObj = PdfPages(fname)
        pdfObj.savefig(self._figure)
        pdfObj.close()
        print('write pdf')
