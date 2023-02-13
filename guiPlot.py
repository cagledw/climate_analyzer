""" A matplotlib derived class that 'acts' like a tkinter canvas Widget.
    The guiPlot constructor requires a tkinter 'parent' Widget and numpy 2D Structured Array.

    The guiPlot object generates an 3 Different Plots depending on its PLOT_TYPE: ALL_DOY, SNGL_DOY, HISTO
    Calls to the plot(type, arg1, ..) method will cause 1 of 3 plots to be generated.
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
from ClimateDataObj import ClimateDataObj, PLOT_DATA

pltcolor1 = 'dimgray'
pltcolor2 = 'skyblue'
pltcolor3 = 'blue'
pltcolor4 = 'navy'
pltcolor5 = 'firebrick'
gridcolor = 'whitesmoke'

mm2days = [31, 29, 31, 30, 31, 30, 31, 31, 30, 31, 30, 31]
mmlabels = [month_abbr[x] for x in range(1, 13)]
PLOT_TYPE = IntEnum('PLOT_TYPE', ['ALLDOY', 'SNGLDOY', 'HISTO'])
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
    return month_int+1, day+1

class guiPlot(FigureCanvasTk):
    """ NOT a tk Widget, instead a matplotlib derived object that embeds a tk.canvas.
        The tk.canvas is instantiated in a parent tk_Widet by calling this objects ctor.

        Constructor requires climate_data in form of a numpy 2D array:
          [yrs, 366][record]

    """
    canvas_dpi = 100

    def __init__(self, parent, station, years, np_climate_data, figsize):
        self._daysum = [sum(mm2days[:x]) for x in range(len(mm2days)+1)]  # Can't be Class Variable!

        self._parent = parent
        self._station = station
        self._yrList = years
        self._np_climate_data = np_climate_data
        self._ClimateDataObj = ClimateDataObj(np_climate_data, years, station)

        self._np_alldoy_mean = {}          # Mean Across all Years for each Day, shape = (366,)
        for _key in ['tmin', 'tmax', 'prcp']:
            self._np_alldoy_mean[_key] = np.nanmean(np_climate_data[:, :][_key], axis=0)

        self._obs = None             # Observation, np_climate_data field name
        self._type = None             # Type of Plot of PLOT_TYPE
        self._ma_numdays = 15         # Moving Avg Window Size

        self._dayenum = 0             # Valid if type == SNGL_DOY
        self._yrenum = self._ClimateDataObj.num_years - 1
        self._doy_xorigin = DATE_ENUM(self._yrenum, 0)
        self._plty = {}

        # A Dict to match plot function to plot type, matches PLOT_TYPE to fcn name
        self.plot_funcs = {PLOT_TYPE[_type] : getattr(self, 'plot_' + _type.lower()) \
                           for _type in PLOT_TYPE.__members__}

        self._figure = Figure(figsize = [x/guiPlot.canvas_dpi for x in figsize], dpi=guiPlot.canvas_dpi)
        self._figure.subplots_adjust(left=0.04, right=.95, top=.90, bottom=.10)
        super().__init__(self._figure, master = parent)

        self._tk_canvas = self.get_tk_widget()
        self._tk_canvas.rowconfigure(0, weight=1)
        self._tk_canvas.columnconfigure(0, weight=1)
        self._tk_canvas.bind("<Configure>", self.on_configure)

        self._ax0 = None
        self._ax0twin = None
        self._vertLine = None

        mpl.rc('lines',  markersize = 2)
        mpl.rc('ytick',  labelsize  = 8)
        mpl.rc('xtick',  labelsize  = 10)
        mpl.rc('lines',  linewidth  = 0.7)
        mpl.rc('legend', fontsize   = 8)
        mpl.rc('axes',   titlesize  = 9)

        # cstep = 1.0/len(self._yrList)
        # self._colors = [mpl.colormaps['brg'](x) for x in np.arange(0, 1.0, cstep)]

        # Special Variables to Manage Position XTick Labels
        self._tick_offset = mpl_xforms.ScaledTranslation(-25/72, 0, self._figure.dpi_scale_trans)
        print(_mpl_tk.__file__)

    # @property
    # def istemp(self):
    #     """ Enumerated_Day (0..365) of current plot, includes Feb 29
    #     """
    #     return self._obs in ['tmax', 'tmin']

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
    def yearenum(self, val):
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
    def cursor(self):
        """ Returns a current cursor position as a dict {'date' : x, + mode specific keys,val pairs}
            The matplotlib object _verLine is queried to get the x-value of the current cursor
        """
        data_x = 0 if self._vertLine is None else self._vertLine.get_xdata()

        # Determine Date @ Cursor
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
            mdy = dayInt2MMDD(self._dayenum)

        rtnDict = {'date':  '-'.join([str(x) for x in mdy])}

        obs = self._plty['obs']
        obs_x = obs[:,0].astype(np.int32)
        try:
            if self._type == PLOT_TYPE.HISTO:
                bins = self._plty['bins']
                x_bin = np.searchsorted(bins, data_x)
                bIndex = x_bin - 1 if x_bin > 0 else 0

                for _lbl in ['obs', 'ma']:
                    binVals = self._plty['binVals'][_lbl]
                    rtnDict[_lbl] = f'{int(binVals[bIndex])}'
            else:
                x_index = np.nonzero(obs_x == data_x)[0][0]     # nonzero returns a tuple of ndarray
                if obs.ndim == 2:
                    y_value = obs[x_index][1]
                    y_text = f'{y_value:.2f}'

                elif obs.ndim == 3:
                    y_value = obs[x_index][:, 1]
                    y_text = ','.join([f'{int(y)}' for y in y_value])
                else:
                    print('bad2', data_x)
                rtnDict[','.join(self._plty['dnames'])] = y_text
        except IndexError:
            y_text = ','.join(['nan' for x in self._plty['dnames']])

        return rtnDict

    def grid(self, row, column, rowspan, columnspan):
        self._tk_canvas.grid(row=row, column=0, columnspan=columnspan, rowspan=rowspan, sticky='nsew')

    def grid_remove(self):
        self._tk_canvas.grid_remove()

    def on_configure(self, event):
        """ Called anytime the canvas width, height changes
        """
        self.resize(event)

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
        data_x = int(
            xlimits[0]) if xform_coords[0] < xlimits[0] \
            else int(xlimits[1]) if xform_coords[0] > xlimits[1] \
            else xform_coords[0] if self._type == PLOT_TYPE.HISTO \
            else round(xform_coords[0])

        ylimits = self._ax0.get_ylim()
        data_y = \
            ylimits[0] if xform_coords[1] < ylimits[0] \
            else ylimits[1] if xform_coords[1] > ylimits[1] \
            else xform_coords[1]

        # if self._type == PLOT_TYPE.HISTO:
        #     print(tk_x, xform_coords[0], data_x, xlimits)

        return data_x, data_y

    def set_marker(self, data_x, data_y=None):
        """ data_x = yrenum
        """
        print('guiPlot.set_marker {} {}'.format(data_x, self._yrList[data_x]))
        # print(len(self._np_climate_data[data_x, :][self._obs]))
        # print(len(self._np_climate_data[:, data_x][self._obs]))

        for _yr in range(self._ClimateDataObj.num_years):
            daymin = self._dayenum - 2
            daymax = self._dayenum + 3

            if daymin < 0: daymin = 0
            if daymax > 365: xmax = 365
            # ma_vals = self._np_climate_data[_yr, daymin : daymax][self._obs]
            # pts = ', '.join([f'{x:.2f}' for x in ma_vals])

            # print(self._yrList[_yr], ',', pts, ',{:.3f}'.format(np.mean(ma_vals)))

    def set_cursor(self, data_x, data_y=None):
        if self._vertLine is None:
            self._vertLine = self._ax0.axvline(color='k', linewidth=1, alpha=0.2)  # the vert line

        self._vertLine.set_xdata(data_x)
        self._ax0.figure.canvas.draw_idle()

    def plot(self, plotType, arg1=None, arg2=None, arg3=None):
        """ Perform requested plot operation depending on plotType.
            There are 3 types of plot: [SNGL_DOY, ALL_DOY, HISTO]
        """
        assert type(plotType) == PLOT_TYPE
        self._obs = arg1.lower()

        # Clear Existing graphic objects from plot, start with new MPL axis
        self._plty.clear()
        self._figure.clear()
        self._vertLine = None
        # for _child in self._figure.get_children():
        #     self.showArtists(_child, 1)

        self._ax0 = self._figure.add_subplot(111)    # Matplotlib Axis, twin is initially off!
        self._ax0.tick_params(axis='both', labelsize = 7)  # can't find rcParams for this
        self._ax0twin = None

        self._ax0.yaxis.grid(visible=True, color=gridcolor, zorder=0)
        self._ax0.xaxis.grid(visible=True, color=gridcolor)

        # Perform the requested Plot
        avg_label = f'{self._ma_numdays}-ptma'
        if self._obs in ['tmin', 'tmax']:
            plt_data = PLOT_DATA.TEMP

            if plotType == PLOT_TYPE.ALLDOY:
                popt = {'tmin': {'color': pltcolor4, 'label': 'tmin', 'linewidth': 0.5},
                        'tmax': {'color': pltcolor5, 'label': 'tmax', 'linewidth': 0.5}}
            elif plotType == PLOT_TYPE.SNGLDOY:
                popt = {'obs': {'color': pltcolor1, 'label': 'SnglDay', 'linewidths': 0.2, 'zorder': 10},
                        'avg': {'color': pltcolor2, 'label': avg_label, 'linewidths': 0.5, 'zorder': 5}}
            elif plotType == PLOT_TYPE.HISTO:
                popt = {'obs': {'color': pltcolor1, 'bins': 25, 'rwidth': 0.3, 'zorder': 20},
                         'ma': {'color': pltcolor2, 'bins': 25, 'rwidth': 0.6, 'zorder': 10}}

            else:
                raise ValueError

        elif self._obs == 'prcp':
            plt_data = PLOT_DATA.RAIN
            if plotType == PLOT_TYPE.ALLDOY:
                popt = {'obs': {'color': pltcolor1, 'label': 'SnglDay', 'zorder': 10},
                        'avg': {'color': pltcolor2, 'label': avg_label, 'width': 0.8, 'zorder': 5}}
            elif plotType == PLOT_TYPE.SNGLDOY:
                popt = {'obs': {'color': pltcolor1, 'label': 'SnglDay', 'width': 0.3, 'zorder': 10},
                        'avg': {'color': pltcolor2, 'label': avg_label, 'width': 0.8, 'zorder': 5}}
            elif plotType == PLOT_TYPE.HISTO:
                popt = {'obs': {'color': pltcolor1, 'bins': 25, 'rwidth': 0.3, 'zorder': 20},
                         'ma': {'color': pltcolor2, 'bins': 25, 'rwidth': 0.6, 'zorder': 10}}
            else:
                raise ValueError
        else:
            raise ValueError

        self.plot_funcs[plotType](plt_data, arg2, popt)

        # Adjust X-Axis Tick Labels for ALLDOY Plots
        if plotType == PLOT_TYPE.ALLDOY:
            self.set_cursor(self._yrenum)
            labels = self._ax0.get_xticklabels()
            for _lblid, _lbl in enumerate(labels):
                _lbl.set_transform(_lbl.get_transform() + self._tick_offset)

        self._type = plotType
        self.draw()

    def plot_sngldoy(self, plt_dtype, day, plt_opt):
        """ Single Day of Year Plot Generation - X-Axis is enumerated years: 0..num_years - 1

        """
        self._dayenum = day

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

        # Get the requested data and its average for the specified day
        obs_name = plt_dtype.name.lower()
        self._plty = self._ClimateDataObj.sngldoy_data(plt_dtype, day)

        # Generated Plot depends on whether it is 1D or 2D (2D implies min/max temp)
        ymin = []
        ymax = []
        avg_label = f'{self._ma_numdays}-ptma'

        if self._plty['dtype'] == PLOT_DATA.RAIN:
            # for _name, _popt in self._plty['popt'].items():
            for _name, _popt in plt_opt.items():
                x = self._plty[_name][:, 0]
                y = self._plty[_name][:, 1]
                # popt = plt_opt[_name]
                sngldoy_bar = self._ax0.bar(x, y, **_popt)
                ymin.append(0.0)
                ymax.append(np.nanmax(y))

            xlim = self._ax0.get_xlim()
            xrange = xlim[1] - xlim[0]
            xscale = 1.0/xrange

            xend = x[-1] - xlim[0]
            xstart = x[0] - xlim[0]

            ma_mean = np.nanmean(self._plty['avg'][:, 1])
            ma_stdev = np.nanstd(self._plty['avg'][:, 1])
            mean_line = self._ax0.axhline(ma_mean, xmin=xstart * xscale,
                                          xmax=xend * xscale, color='blue', linestyle='--')
            sngldoy_info = avg_label + '\n' + r'$\mu$: {:.2f}'.format(ma_mean)
            sngldoy_text = self._ax0.text(xlim[0], ma_mean, sngldoy_info, fontsize = 7, color = 'blue')

        elif self._plty['dtype'] == PLOT_DATA.TEMP:
            for _name, _popt in plt_opt.items():
                segs = self._plty[_name]
                _popt['linewidths'] *= self.xunits2pts(self._ax0)

                lineSegs = LineCollection(segs, **_popt)
                self._ax0.add_collection(lineSegs)

                ymin.append(np.nanmin(segs[:, 0, 1]))
                ymax.append(np.nanmax(segs[:, 1, 1]))

            ymin_avg = np.nanmean(self._plty['avg'][:, 0, 1])
            ymin_std = np.nanstd(self._plty['avg'][:, 0, 1])

            ymax_avg = np.nanmean(self._plty['avg'][:, 1, 1])
            ymax_std = np.nanstd(self._plty['avg'][:, 1, 1])

            x = self._plty['avg'][:, 0, 0]
            val_list = [ymin_avg - ymin_std, ymax_avg + ymax_std]
            color_list = ['blue', 'firebrick']
            text_list = ['ymin\n' + r'$\mu - \sigma$', 'ymax\n' + r'$\mu + \sigma$']
            xaxis_limits = self._ax0.get_xlim()
            for _avg, _color, _text in zip(val_list, color_list, text_list):
                ymean_hline = self._ax0.axhline(_avg, xmin = x[0], xmax = x[-1],
                                                color = _color, linestyle = '--')

                info_text = self._ax0.text(xaxis_limits[0], _avg, _text, color=_color, fontsize=8, va='top')

        sngldoy_legend = self._ax0.legend(loc = (0.0, 1.0))

        ymin = np.min(ymin)
        ymax = np.max(ymax)
        yticks, ydelta = guiPlot.nice_grid(ymin, ymax)
        yticks += [yticks[-1] + ydelta]
        self._ax0.set_ylim((yticks[0], yticks[-1]))
        self._ax0.set_yticks(yticks)

        if plt_dtype == PLOT_DATA.TEMP:
            ttl = 'Temperature'
        elif plt_dtype == PLOT_DATA.RAIN:
            ttl = 'Rain Precipitation'
        else:
            raise ValueError
        self._ax0.set_title(f'{self._station} {dayInt2Label(day)}  -' + ttl)

    def plot_alldoy(self, plt_dtype, yrenum, plt_opt):
        """ Plot Generation for All Days of Year, X-Axis is enumerated days 0..365
            BUT DATA[0] DOES NOT NECESSARILY CORRESPOND WITH JAN-1 IF yrenum == current_yr !
            Instead, data is shifted so that DATA[0] corresponds with 1st day of next month.
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
        self._doy_xorigin = DATE_ENUM(xorigin_yr, self._daysum[xorigin_mm])

        # Configure X-Axis Ticks & Labels Based on xorigin
        #  xorder = a list of enumerated months, starting from doy_xorigin
        month_1 = self._daysum.index(self._doy_xorigin.dayenum)
        xorder = list(range(month_1, 12)) + list(range(0, month_1))

        tics = []
        for x in range(1, 13):
            items = [xorder[y] for y in range(x)]
            tics.append(sum([mm2days[y] for y in items]))

        xlabels = [mmlabels[x] for x in xorder]
        self._ax0.set_xticks(tics)
        self._ax0.set_xticklabels(xlabels)

        # Add Y-Axis Values depending on plt_dtype
        self._plty = self._ClimateDataObj.alldoy_data(plt_dtype, self._doy_xorigin)

        if self._plty['dtype'] == PLOT_DATA.RAIN:
            test = plt_opt['obs']
            bar = self._ax0.bar(self._plty['obs'][:, 0], self._plty['obs'][:, 1],
                                color=pltcolor1, label = 'SnglDay', zorder=10)

            ymax = np.round_(np.max(self._plty['obs'][:, 1]), 1)
            yticks, ydelta = guiPlot.nice_grid(0, ymax)
            yticks += [yticks[-1] + ydelta]

            self._ax0.set_ylim((0, yticks[-1]))
            self._ax0.set_yticks(yticks)

            # Twin Axis
            self._ax0twin = self._ax0.twinx()
            maxy = []

            y = self._plty['ma'][0]
            x = np.arange(len(y))
            line = self._ax0twin.plot(x, y, color = pltcolor2, label = f'{self._ma_numdays}day_ma')[0]
            maxy.append(np.max(y))

            y = self._plty['ltmean'][0]
            x = np.arange(len(y))
            line = self._ax0twin.plot(x, y, color = pltcolor3, linewidth = 0.5, linestyle = '-',
                                      label=f'{self._np_climate_data.shape[0]}-yr avg')[0]
            maxy.append(np.max(y))

            maxy = np.max(maxy)
            yscale = guiPlot.nice_scale(maxy)
            ylim = np.ceil(10. * yscale * maxy) / (10. * yscale)
            self._ax0twin.set_ylim([0, ylim])

            self._ax0twin.tick_params(axis='both', labelsize=7)        # can't find rcParams for this
            self._ax0twin.legend(loc = (0.88, 1.0))

        elif self._plty['dtype'] == PLOT_DATA.TEMP:
            Mpts = self._plty['obs'].shape[0]
            lineSegs = LineCollection(self._plty['obs'], colors=[pltcolor1] * Mpts)
            self._ax0.add_collection(lineSegs)

            spec = {'tmin': {'color': pltcolor4, 'label': 'tmin', 'linewidth': 0.5},
                    'tmax': {'color': pltcolor5, 'label': 'tmax', 'linewidth': 0.5}}

            for _name, _y in zip(self._plty['dnames'], self._plty['ltmean']):
                x = np.arange(len(_y))
                self._ax0.plot(x, _y, **spec[_name])
        else:
            raise ValueError

        self._ax0.set_xlim(0, 366)
        self._ax0.legend(loc=(0.0, 1.0))
        self._ax0.set_title(self._plty['title'])

    def plot_histo(self, plt_dtype: PLOT_DATA, dayenum: int, plt_opt):
        """ Plot Generation for Histogram of Single Day of Year
        """
        self._dayenum = dayenum
        dayLabel = dayInt2Label(dayenum)

        self._plty = self._ClimateDataObj.hist_data(plt_dtype, dayenum)
        if len(self._plty['dnames']) == 1:
            ma_data = self._plty['ma'][:, 1]
            obs_data = self._plty['obs'][:, 1]
        elif len(self._plty['dnames']) == 2:
            data_index = self._plty['dnames'].index(self._obs)
            ma_data = self._plty['ma'][data_index, :, 1]
            obs_data = self._plty['obs'][data_index, :, 1]
        else:
            raise ValueError

        plt_opt['ma']['label'] = f'{self._plty["ma_winsz"]}day-ma'
        plt_opt['obs']['label'] = f'{dayLabel} {self._obs}'

        obsHisto, bins, container = self._ax0.hist(obs_data, **plt_opt['obs'])
        plt_opt['ma']['bins'] = list(bins)

        maHisto, bins, container = self._ax0.hist(ma_data, **plt_opt['ma'])
        self._plty['bins'] = bins
        self._plty['binVals'] = {'obs': obsHisto, 'ma': maHisto}

        fmtstr = '{:.3f}' if plt_dtype == PLOT_DATA.RAIN \
            else '{:.1f}' if plt_dtype == PLOT_DATA.TEMP \
            else ''

        self._ax0.set_xticks(bins)
        xtickLabels = [fmtstr.format(x) for x in bins]
        self._ax0.set_xticklabels(xtickLabels)

        self._ax0.set_xlim((bins[0], bins[-1]))
        ttl = f'{self._plty["station"]} {dayInt2Label(dayenum)} {self._obs} Histogram'
        self._ax0.set_title(ttl)
        self._ax0.legend(loc=(0.0, 1.0))

    def write_pdf(self, fname):
        pdfObj = PdfPages(fname)
        pdfObj.savefig(self._figure)
        pdfObj.close()
        print('write pdf')

    @staticmethod
    def nice_scale(value):
        """ Return scale factor such that: 1.0 <= value * scale < 10.0
        """
        scale = 1.0
        for loop_count in range(6):
            factor = scale * value
            if factor >= 1.0 and factor < 10.0:
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

