"""
A tkinter GUI Class
"""
from os import path
from datetime import date
from itertools import groupby, accumulate
from collections import defaultdict

import numpy as np
import tkinter as tk
import tkinter.ttk as ttk

from .db_coupler import dbCoupler
from .gui_plot import guiPlot, dayInt2MMDD, dayInt2Label, PLOT_TYPE
from .gui_style import guiStyle
from .climate_dataobj import ClimateDataObj

class guiMain(tk.Tk):
    """A tk Application (i.e. Main/Root Window)

    """
    def __init__(self, cdObj: ClimateDataObj, pos_tuple):
        """ A tk Application (i.e. Main/Root Window) to display Climate Data and its Analysis.
            Weather data is read from a sqlite DB.  A list of DB File Paths is passed to __init__.

            The data retrieved from sqlite DB is:
              - yrList[]           : years (e.g. [2000, 20001, ...], matches yr_enum in 2D Array
              - 2D Structured Array: [yr_enum, day_enum][obs] : year x day x observation

            Gui is structured as 2 Rows or tkinter Widgets:
              - row-0 : imported guiPlot Widget, colspan must be set to match # of col in row-1
              - row-1 : c0: info, c1: ArgSelFrame, c5: ObserMenu, c6: TypeButton

        """
        super().__init__()
        print('tkinter Version: {}'.format(self.tk.call('info', 'patchlevel')))

        # self.dbList = dbList
        self._posXY = pos_tuple
        self._ClimateDataObj = cdObj
        self._stations = cdObj.stationList
        self.np_climate_data = cdObj.np_data
        self.yrList = cdObj.yrList

        self._station_index = self._stations.index(self._ClimateDataObj.station)

        # Initial Gui Setup
        self.title("Climate Data Analyzer")
        self.geometry('+{}+{}'.format(*self._posXY))
        self._style = guiStyle(self)                  # Style for all Widgets!

        # self.bind("<Map>", self.on_map)
        self.bind("<Configure>", self.on_configure)
        # self.bind("<KeyPress>", self.on_key)
        self.bind("<Motion>", self.on_motion)
        self.bind("<Button-1>", self.on_button1_press)

        self.rowconfigure(0, weight=1)               # Expand Widgets in Height
        self.columnconfigure(0, weight=1)            # Expand Widgets in Width

        # Row-0, Column-0 : Plot Widget
        self._plot_widget = guiPlot(self, self._ClimateDataObj, figsize=(1000, 400))
        self._plot_widget.grid(row=0, column=0, rowspan=1, columnspan=8)

        # Column-0, Information Widget
        self._info_text = tk.StringVar()                                          # Col-0, Information Widget
        self._tk_info = ttk.Label(self, textvariable=self._info_text, width=40)
        self._tk_info.grid(row=1, column=0, sticky='nsw')

        # Column-1, PDF Button
        self._pdfButton = ttk.Button(self, text='PDF', style='red.TButton', width=5, command=self.on_pdfButton)
        self._pdfButton.grid(row=1, column=1, sticky='nse')

        # Column-6, TypeButton (cycles between 3 PLOT_TYPE modes)
        self._ArgSelFrame = None                               # circular reference issue, from tkBoggleButton
        self._TypeButton = tkToggleButton(self, PLOT_TYPE, self.on_TypeButton)
        self._TypeButton.grid(row=1, column=6, sticky='nse')
        self._TypeButton.enum = PLOT_TYPE.ALLDOY

        # Column-2 - Column-4,  ArgSelFrame - REFERENCES TypeButton!
        self._ArgSelFrame = tkArgSelFrame(self, self._TypeButton.enum, self.on_ArgSel, self.on_ArgLimits)
        self._ArgSelFrame.grid(row=1, column=2)
        self._ArgSelFrame.argtype = PLOT_TYPE.ALLDOY

        init_yrenum = len(self.yrList) - 1
        self._ArgSelFrame.argvalue = self.yrList[init_yrenum]

        # Column-5, OptionMenu (Climate Data Fields)
        self.cd_names = [x.upper() for x in self.np_climate_data.dtype.names]  # Numpy Structured Array Field Names
        self._ObserMenu = tkOptionMenu(self, self.cd_names, self.cd_names.index('PRCP'), self.on_ObserMenu)
        self._ObserMenu.grid(row=1, column=5, sticky='e')

        # Column-7, StationMenu
        # select_index = self._stations.index(self._ClimateDataObj.station)
        self._StationMenu = tkOptionMenu(self, self._stations, self._station_index, self.on_StationMenu)
        self._StationMenu.grid(row=1, column=7, sticky='e')

        self._plot_widget.plot(self._TypeButton.enum, self._ObserMenu.selectedItem, init_yrenum)
        self._update_info_text()

    @property
    def selected_station(self):
        return self._stations[self._station_index]

    def _update_info_text(self):
        cursor_info = self._plot_widget.cursor
        cursor_date = cursor_info.pop('date')
        cursor_extra = '  |  '.join([f'{x}: {y}' for x, y in cursor_info.items()])
        self._info_text.set('{}  |  '.format(cursor_date) + cursor_extra)

    def on_button1_press(self, event):
        if event.widget == self._plot_widget.tkwidget:
            cursor_xy = self._plot_widget.xform_tk_coords(event.x, event.y)
            self._plot_widget.set_marker(cursor_xy[0])
            # test = self._plot_widget.get_marker(cursor_xy[0])
            # print('{} {}'.format(self._ArgSelFrame.argtype.name, cursor_xy))

            if self._TypeButton.enum == PLOT_TYPE.SNGL_DOY:
                self._plot_widget.yearenum = cursor_xy[0]

            elif self._TypeButton.enum == PLOT_TYPE.ALL_DOY:
                pass

            elif self._TypeButton.enum == PLOT_TYPE.HISTO:
                print('TREND press cursor_xy = {}'.format(cursor_xy))
            else:
                raise ValueError('on_button1_press Bad TypeButton')

    def on_pdfButton(self):
        print('pdf', self._pdfButton.state())
        self._plot_widget.write_pdf(f'{self.selected_station}.pdf')

    def on_motion(self, event):
        """ Motion Events for ALL Widgets, 'event' provides cursor position in 'Display' Space
            and is converted to 'Data' Space to update the cursor position.
        """
        if event.widget == self._plot_widget.tkwidget:
            cursor_xy = self._plot_widget.xform_tk_coords(event.x, event.y)

            if self._ArgSelFrame.argtype == PLOT_TYPE.SNGLDOY:
                size_x = self.np_climate_data.shape[0]
            else:
                size_x = self.np_climate_data.shape[1]

            cursor_x = size_x - 1 if cursor_xy[0] >= size_x else cursor_xy[0]
            cursor_x = 0 if cursor_x < 0 else cursor_x

            # print('motion {} {} {} {:.3f}'.format(self._ArgSelFrame.argtype.name, max_x, *cursor_xy))
            self._plot_widget.set_cursor(cursor_x)
            self._update_info_text()

    def on_TypeButton(self, new_type):
        if self._ArgSelFrame is None:
            return

        argType = self._ArgSelFrame.argtype # This May Not Exist

        if argType != new_type:
            if new_type == PLOT_TYPE.ALLDOY:
                self._ArgSelFrame.argvalue = self._plot_widget.year
                plot_arg = self._plot_widget.yearenum

            elif new_type == PLOT_TYPE.SNGLDOY:
                self._ArgSelFrame.argvalue = self._plot_widget.dayenum
                plot_arg = self._plot_widget.dayenum

            elif new_type == PLOT_TYPE.HISTO:
                plot_arg = self._plot_widget.dayenum

            else:
                raise ValueError

            self._ArgSelFrame.argtype = new_type

        else:
            raise ValueError('on_TypeButton argType Error')

        # print('  on_TypeButton {} -> {}'.format(argType.name, new_type.name))

        argVal = self._ArgSelFrame.argvalue # This May Not Exist
        self._plot_widget.plot(self._TypeButton.enum, self._ObserMenu.selectedItem, plot_arg)
        self._update_info_text()

        # except AttributeError:
        #     print('AttributeError {}'.format(new_type.name))
        #
        # except Exception as e:
        #     print(f'  on_TypeButton Exception {e}')

    def on_ArgSel(self, argType, argVal):
        """ Performs validation of new argVal
        """
        if argType == PLOT_TYPE.SNGLDOY or argType == PLOT_TYPE.HISTO:
            plot_arg = argVal
            if plot_arg < 0 or plot_arg >= self.np_climate_data.shape[1]:
                return False

        elif argType == PLOT_TYPE.ALLDOY:
            try:
                plot_arg = self.yrList.index(argVal)
                if plot_arg < 0 or plot_arg >= self.np_climate_data.shape[0]:
                    return False
            except ValueError:
                return False

        self._plot_widget.plot(self._TypeButton.enum, self._ObserMenu.selectedItem, plot_arg)
        self._update_info_text()
        return True

    def on_ArgLimits(self, argType):
        if argType == PLOT_TYPE.SNGLDOY:
            return 0, self.np_climate_data.shape[1] - 1

        elif argType == PLOT_TYPE.ALLDOY:
            return self.yrList[0], self.yrList[self.np_climate_data.shape[0] - 1]

        elif argType == PLOT_TYPE.HISTO:
            return 0, self.np_climate_data.shape[1] - 1

    def on_ObserMenu(self, xItem):
        """ Activated on changes to Observation Menu.
            Calls guiPlot Widget to delete existing plot and generate a new plot.
        """
        if self._TypeButton.enum == PLOT_TYPE.SNGLDOY:
            plotarg = self._plot_widget.dayenum

        elif self._TypeButton.enum == PLOT_TYPE.ALLDOY:
            plotarg = self._plot_widget.yearenum

        elif self._TypeButton.enum == PLOT_TYPE.HISTO:
            plotarg = 0

        # print('guiMain.on_xItem {} {}'.format(xItem, self._ObserMenu.selectedItem))
        self._plot_widget.plot(self._TypeButton.enum, self._ObserMenu.selectedItem, plotarg)

    def on_StationMenu(self, xItem):
        """ Activated on changes to Station Menu.
            Calls guiPlot Widget to generate a new plot.
        """
        print('guiMain.on_StationMenu {} {}'.format(xItem, self._ObserMenu.selectedItem))
        self._ClimateDataObj.station = xItem
        self._plot_widget.plot(self._TypeButton.enum, self._ObserMenu.selectedItem, self._ArgSelFrame.argtype)

    def on_configure(self, event):
        """ Track Position of guiMain AND fix incorrect guiMain width changes made by MPL.
            Changes to ActiveFrame Widget configure may incorrectly change guiMain width.
            Fixed Here.
        """
        # print(event)
        if event.widget == self:
            self._posXY = (event.x, event.y)

    def mainloop(self, n: int = 0):
        tk.mainloop(n)

class tkArgSelFrame(ttk.Frame):
    """ A Container (i.e. Frame) Class that changes gui widgets depending on its argType.

    """

    def __init__(self, parent, argType, callback, callback_lim):
        self._parent = parent
        self._argType = argType
        self._callback = callback
        self._callback_lim = callback_lim
        self._label_text = tk.StringVar()                # Information Widget
        super().__init__(parent, width=100)

        iconDir = path.join(path.dirname(__file__), 'extra')
        iconPaths = {_name: _path for _name, _path in
                     zip(['arrow-lf', 'arrow-rt'], [path.join(iconDir, _icon)
                                                    for _icon in ['arrow-lf16x16.gif', 'arrow-rt16x16.gif']])}

        self._tkImages = {_name: tk.PhotoImage(master=self, file=_file, name=_name)
                          for _name, _file in iconPaths.items()}

        self._tkPrevBtn = ttk.Button(self, image=self._tkImages['arrow-lf'], width=1, command=self.on_PrevBtn)
        self._tkPrevBtn.grid(row=0, column=2, sticky='nse')

        self._tkNextBtn = ttk.Button(self, image=self._tkImages['arrow-rt'], width=1, command=self.on_NextBtn)
        self._tkNextBtn.grid(row=0, column=3, sticky='nse')

        self._ArgEntry = tkIntEntry(self, 'Day', self.on_ArgEntry)
        self._ArgEntry.grid(row = 0, column=1, sticky='e')
        self._ArgEntry.bind("<Return>", self.on_return)

        self._ArgLabel = ttk.Label(self, textvariable = self._label_text)
        self._ArgLabel.grid(row = 0, column = 0, sticky='nwe')

        self.update_label()

    @property
    def argvalue(self):
        return self._ArgEntry._value

    @argvalue.setter
    def argvalue(self, newval):
        # print('tkArgSelFrame.value = {}'.format(newval))
        self._ArgEntry.value = newval

    @property
    def argtype(self):
        # print(f'tkArgSelFrame.argtype', {self._argType})
        return self._argType

    @argtype.setter
    def argtype(self, newval):
        self._argType = newval
        self.update_label()

    def update_label(self):
        if self._argType == PLOT_TYPE.SNGLDOY or self._argType == PLOT_TYPE.HISTO:
            self._label_text.set('Day: ')
        else:
            self._label_text.set('Year: ')

    def grid(self, row, column, rowspan = 1, colspan = 1, sticky = 'nse'):
        super().grid(row = row, column = column, sticky = sticky)

    def on_PrevBtn(self):
        limits = self._callback_lim(self._argType)
        newval = self._ArgEntry.value - 1
        if newval < limits[0]:
            newval = limits[1]
        self._ArgEntry.value = newval
        self._callback(self._argType, newval)

    def on_NextBtn(self):
        limits = self._callback_lim(self._argType)
        newval = self._ArgEntry.value + 1
        if newval > limits[1]:
            newval = limits[0]
        self._ArgEntry.value = newval
        self._callback(self._argType, newval)

    def on_ArgEntry(self, value):
        """ Currently Do Nothing - Use <Return>
        """
        pass
        # print('tkArgSelFrame.on_ArgEntry {}'.format(value))

    def on_return(self, event):
        newval = self._ArgEntry.value
        self._callback(self._argType, newval)

        # print('Return {}'.format(event))


class tkIntEntry(ttk.Entry):
    """ requires 2 columns
    """

    def __init__(self, parent, label, callback = None):
        self._value = 0
        self._callback = callback

        self._tkVar = tk.StringVar(parent)
        self._tkVar.set(str(self._value))

        super().__init__(parent,
                         textvariable = self._tkVar,
                         width = 5,
                         justify = tk.CENTER)

        self._reg = parent.register(self.isOkay)
        self.config(validate = 'key', validatecommand = (self._reg, '%d', '%P'))

    def on_return(self, event):
        print('Return {}'.format(event))

    @property
    def value(self):
        return self._value

    @value.setter
    def value(self, newval):
        self._value = newval
        self._tkVar.set(str(self._value))

    def grid(self, row, column, sticky):
        # self._label.grid(row = 1, column = 1, sticky='e')
        super().grid(row = row, column = column, sticky='e')

    def isOkay(self, why, text):
        try:
            self._value = int(text)

            if self._callback:
                self._callback(self._value)
        except:
            # print(f'validate fail {why} {text}')
            pass

        return True


class tkToggleButton(ttk.Button):
    """ Encapsulates a Button that represents an enum.  Selecting Button cycles enum.
        Each enum value as a text and numeric value.  Numeric value ranges 1..n (No Zero!)
    """

    def __init__(self, parent, enum_type, event_callback = None):

        self._type = enum_type
        self._event_callback = event_callback

        self._CurrentEnum = None
        self._tkVar = tk.StringVar(parent)

        super().__init__(parent,
                         textvariable = self._tkVar,
                         command = self.on_change,
                         takefocus=False)

    @property
    def enum(self):
        return self._CurrentEnum

    @enum.setter
    def enum(self, newval):
        self._CurrentEnum = newval
        self._tkVar.set(self._CurrentEnum.name)
        # self.state(['selected'])

        if self._event_callback:
            self._event_callback(self._CurrentEnum)

    def on_change(self):
        try:    self._CurrentEnum = self._type(self._CurrentEnum.value + 1)
        except: self._CurrentEnum = self._type(1)
        self._tkVar.set(self._CurrentEnum.name)
        # print('tkToggleButton {}'.format(self._CurrentEnum.name))

        if self._event_callback:
            self._event_callback(self._CurrentEnum)


class tkOptionMenu(ttk.OptionMenu):
    """ Encapsulates GUI Elements AND a timedelta (days) object and the callback
        method is actived on a change.
    """

    def __init__(self, parent, ItemList, SelIndex, event_callback = None):

        self._ItemList = ItemList
        self._selectedItem = ItemList[SelIndex]
        self.event_callback = event_callback

        self._tkVar = tk.StringVar(parent)
        self._tkVar.set(self._selectedItem)

        super().__init__(parent,
                         self._tkVar,
                         self._tkVar.get(),
                         *self._ItemList,
                         command = self.on_change)
        self.configure(width = 8)

    @property
    def selectedItem(self):
        return self._selectedItem

    def on_change(self, val):
        self._selectedItem = val

        # print('XItem Change {}'.format(val))

        if self.event_callback:
            self.event_callback(val)

