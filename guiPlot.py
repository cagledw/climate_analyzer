""" A matplotlib derived class that 'acts' like a tkinter canvas Widget.
    The guiPlot constructor requires a tkinter 'parent' Widget and numpy 2D Structured Array.


    The guiPlot object generates an 3 Different Plots depending on its PLOT_TYPE: ALL_DOY, SNGL_DOY, HISTO
    Calls to the plot(type, arg1, ..) method will cause 1 of 3 plots to be generated.
    The guiPlot object maintains a lists of matplotlib graphics objects that are 'removed' prior
    to generating a new plot.
"""
from __future__ import annotations   # Fix Type Hint Problem

from enum        import IntEnum
from datetime    import date
from calendar    import month_abbr
from collections import namedtuple

import re
import numpy as np
import tkinter as tk
import tkinter.ttk as ttk
import matplotlib as mpl
import matplotlib.transforms as mpl_xforms

from matplotlib.figure import Figure
from matplotlib.axes._axes import Axes
from matplotlib.collections import LineCollection
from _mpl_tk import FigureCanvasTk
from mpl_toolkits.axes_grid.inset_locator import (inset_axes, InsetPosition, mark_inset)
# from colorspacious import cspace_convert

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
    def nice_grid(mintick, maxtick):
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
        # print('nice_grid {} {}'.format(rng, scale))

        good_mod = [5, 2, 1]
        for loop_count in range(6):
            pts_list = [rng * scale/x for x in grid_range]
            # print(','.join('{:.1f}'.format(x) for x in pts_list))

            if min(pts_list) > max(good_mod):    # too many grid lines, need bigger spacing
                scale *= 0.5
                # print('smaller', scale)
                continue

            elif max(pts_list) < min(good_mod):  # not enough grid lines, need smaller spacing
                scale *= 2.0
                # print('bigger',scale)
                continue

            grid_spacing = [int(round(x)) for x in pts_list]
            # print(grid_spacing)
            for _mod in good_mod:
                if _mod in grid_spacing:
                    grid_space = int(_mod / scale)
                    break
                else:
                    grid_space = None

            if grid_space:
                return list(range(mintick, maxtick, grid_space))

        raise RuntimeError('guiPlot.nice_grid {}'.format(scale))

    def __init__(self, parent, station, years, np_climate_data, figsize):
        self._daysum = [sum(mm2days[:x]) for x in range(len(mm2days)+1)]  # Can't be Class Variable!

        self._parent = parent
        self._station = station
        self._yrList = years
        self._np_climate_data = np_climate_data

        self._mean_byday = None
        self._stdev_byday = None
        self._ma_byday = None

        self._obs  = None     # Observation, np_climate_data field name
        self._year = None     # Valid if type == ALL_DOY or TREND
        self._type = None
        self._obs_max = None
        self._ma_numdays = 9  # Moving Avg Window Size

        self._dayenum  = 0     # Valid if type == SNGL_DOY
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
    def cursorx(self):
        if self._vertLine is None:
            return None

        return self._vertLine.get_xdata()

    @property
    def cursor(self):
        """ Returns a tuple ((yr, m, d), yval, zval)
        """
        data_x = self.cursorx

        if self._type == PLOT_TYPE.SNGL_DOY:  # data_x enumerated year
            data_x = 0 if data_x < 0 else data_x
            data_x = len(self._yrList) - 1 if data_x >= len(self._yrList) else data_x

            xVal = (self._yrList[data_x], *dayInt2MMDD(self._dayenum))
            yVal = self._np_climate_data[data_x, self._dayenum][self._obs]
            zVal = self._np_ma_byday[data_x, self._dayenum]

        elif self._type == PLOT_TYPE.ALL_DOY:  # data_x enumerated day
            xVal = (self._yrList[self._yrenum], *dayInt2MMDD(data_x))
            yVal = self._np_climate_data[self._yrenum, data_x][self._obs]
            zVal = self._np_ma_byday[self._yrenum, data_x]

        elif self._type == PLOT_TYPE.HISTO:  # data_x enumerated day
            xVal = (self._yrList[self._yrenum], *dayInt2MMDD(data_x))
            yVal = 2.0
            zVal = 0.0

        return (xVal, yVal, zVal)

    @property
    def pltcolor(self):
        return self._colors[self._yrenum]


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
        self._ax0.set_title(f'{self._obs} - {dayInt2Label(day)}')

        num_pts = self._np_climate_data.shape[0]
        x = np.arange(num_pts)
        y = self._np_climate_data[:, day][self._obs]
        self._sngldoy_artlist.append(self._ax0.scatter(x,y,c = 'lightsteelblue',
                                                       marker = 's',
                                                       label = 'not averaged'))

        y2 = self._np_ma_byday[:, day]
        self._sngldoy_artlist.append(self._ax0.scatter(x, y2, c = 'blue',
                                                       marker = 'o',
                                                       label = f'{self._ma_numdays}-pt mov_avg'))

        self._sngldoy_artlist.append(self._ax0.legend(bbox_to_anchor = (0.9, 1.0),
                                                      loc = 'upper left'))

        maxy = np.max(self._np_ma_byday)
        yscale = guiPlot.nice_scale(maxy)
        ylim = round(10.0 * yscale * maxy) / (10.0 * yscale)
        self._ax0.set_ylim([0, ylim])

        if self._type == None:  # Reconfigure Axes, Remove Twin
            self._ax0twin.set_axis_off()
            self._ax0.grid(visible = True, which = 'major', axis = 'y')

            xtendby = 4
            xlabels = list(range(self._yrList[0] + -xtendby, self._yrList[0])) \
                      + self._yrList \
                      + list(range(self._yrList[-1] + 1, self._yrList[-1] + xtendby))

            xlocs = list(range(-xtendby, len(xlabels) -xtendby))

            assert len(xlabels) == len(xlocs)

            xtickLocs = guiPlot.nice_grid(xlocs[0], xlocs[-1])
            xtickLabels = [xlabels[xlocs.index(i)] for i in xtickLocs]

            self._ax0.set_xticks(xtickLocs)
            self._ax0.set_xticklabels(xtickLabels)

            self._ax0.set_xlim(xlocs[0], xlocs[-1])
            self._ax0.xaxis.grid(True)


        xlim = self._ax0.get_xlim()
        xscale = 1.0 / (xlim[1] - xlim[0])
        xend = (x[-1] - xlim[0])
        xstart = (x[0] - xlim[0])

        ma_mean = np.mean(y2)
        ma_stdev = np.std(y2)

        self._sngldoy_artlist.append(self._ax0.axhline(ma_mean, xmin = xstart * xscale,
                                                       xmax = xend * xscale,
                                                       color = 'blue', linestyle = '--'))

        self._sngldoy_artlist.append(self._ax0.text(xlim[0], ma_mean,
                                                    r'$\mu = {:.2f}$'.format(ma_mean), fontsize = 7, color = 'blue'))

        if self._vertLine: self._vertLine.set_xdata(self._yrenum)


    def plot_all_doy(self, yrenum, reserved):
        """ All Days of Year Plot Generation - X-Axis is enumerated days 0..365

            Special (i.e. UGLY) Processing for xtick Labels to center the MonthLabels between
            tick marks.  A matplotlib 'ScaledTranslation' transform is applied to each label
            IF IT ISN'T ALREADY APPLIED.  Applied transforms are maintained in _xtick_xform_list.
        """
        self._yrenum = yrenum
        self._ax0.set_title(f'{self._obs} - {self._yrList[self._yrenum]}')

        focus_data = self._np_climate_data[self._yrenum][self._obs]
        valid_indicies = np.argwhere(~np.isnan(focus_data))
        valid_data = focus_data[valid_indicies]

        x = valid_indicies.flatten()
        y = valid_data.flatten()
        self._alldoy_artlist.append(self._ax0.bar(x, y, color = 'blue'))
        # self._alldoy_artlist.append(self._ax0.bar(x, y, color = self.pltcolor))

        y = self._np_ma_byday[self._yrenum]
        x = np.arange(len(y))
        pcolor = [x * 0.5 for x in self.pltcolor]
        self._alldoy_artlist.append(self._ax0twin.plot(x, y, color = 'dodgerblue')[0])
        # self._alldoy_artlist.append(self._ax0twin.plot(x, y, color = pcolor)[0])

        maxy = np.max(y)
        yscale = guiPlot.nice_scale(maxy)
        ylim = round(yscale * maxy) / yscale
        self._ax0twin.set_ylim([0, ylim])


        y = self._np_mean_byday
        self._alldoy_artlist.append(self._ax0twin.plot(x, y, color = 'k', linewidth = 0.5)[0])

        if self._type == None:  # Reconfigure Axes, Enable Twin Axis
            self._ax0twin.set_axis_on()
            self._ax0twin.yaxis.grid(True)
            self._ax0twin.tick_params(axis='both', labelsize = 7)  # can't find rcParams for this

            self._ax0.set_xlim(0,365)
            self._ax0.xaxis.grid(True)

            grid = [sum(mm2days[:x]) for x in range(1,len(mm2days)+1)]
            self._ax0.set_xticks(grid)
            self._ax0.set_xticklabels(mmlabels[:12])

            for idx, label in enumerate(self._ax0.xaxis.get_majorticklabels()):
                try:
                    inv_xform = self._xtick_xform_list[idx]
                except:
                    label.set_transform(label.get_transform() + self._tick_offset)
                    self._xtick_xform_list.append(self._tick_offset)

            self._ax0.grid(visible = False, which = 'major', axis = 'y')

            # lim_scale = guiPlot.nice_scale(self._ax0twin.get_ylim()[1])
            # ylim = round(lim_scale * self._ax0twin.get_ylim()[1]) / lim_scale
            # self._ax0twin.set_ylim([0, ylim])

            # scale = self._ax0twin.get_ylim()[1] / self._ax0.get_ylim()[1]
            # print(self._ax0.get_ylim(), self._ax0twin.get_ylim(), ylim)
            # print(guiPlot.nice_scale(self._ax0twin.get_ylim()[1]))


    def plot_histo(self, dayenum, reserved2):

        self._dayenum = dayenum
        self._ax0.set_title(f'{self._obs} - {dayInt2Label(dayenum)}')

        # self._ax0.autoscale(enable = True, axis = 'y')
        x = self._np_ma_byday[:, dayenum]

        bin_low = np.min(x)
        bin_high = np.max(x)

        values, bins, container = self._ax0.hist(x, range = (bin_low, bin_high), bins = 25, color = 'blue')
        self._histo_artlist.append(container)
        self._ax0.set_ylim([0, max(values) + 1])

        # print(f'Plot Histograph {dayenum} {bin_low}, {bin_high}, {self._ax0.get_xlim()}')
        self._ax0.set_xticks(bins)
        xtickLabels = ['{:.3f}'.format(x) for x in bins]
        self._ax0.set_xticklabels(xtickLabels)

        self._ax0.set_xlim((0,bins[-1]))




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

    # @property
    # def cntl_options(self) -> List[_PlotDefObj]:
    #     """ Expose the available plot type options for the parent along with
    #         which ones are 'enabled' (ie 'normal')
    #     """
    #     return self._plot_options


    def on_button3(self, event):
        """ Right Button within OHLC Plot Area
        """
        if self._plot_def is None:
            return

        self._popup = Popup_Table(self._tk_canvas.winfo_toplevel(),
                                  self._ticker,
                                  np.flip(self._plot_def.plotData.as_nparray),
                                  ['{}', '{}', '{:0.4f}', '{:0.4f}', '{:0.04f}'])
