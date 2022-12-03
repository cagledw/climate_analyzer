"""
  A tkinter GUI Class tailored for displaying Climate Data and its Analysis.


"""

from os   import path
from datetime import date
from itertools import groupby, accumulate
from collections import defaultdict

import numpy as np
import tkinter as tk
import tkinter.ttk as ttk

from noaa        import get_noaa_id, get_dataset_v1

from guiStyle    import guiStyle
from guiPlot     import guiPlot, dayInt2MMDD, dayInt2Label, PLOT_TYPE
from dbCoupler   import dbCoupler

class guiMain(tk.Tk):
    """ A tk Application (i.e. Main/Root Window) to display Climate Data and its Analysis
        Weather data is read from a sqlite DB.  A list of DB File Paths is passed to __init__.

        The data retrieved from sqlite DB is:
          - yrList[]           : years (e.g. [2000, 20001, ...], matches yr_enum in 2D Array
          - 2D Structured Array: [yr_enum, day_enum][obs] : year x day x observation

    """
    def __init__(self, dbList, pos_tuple):

        self.dbList = dbList
        self._posXY = pos_tuple
        self._stations = [path.splitext(path.basename(x))[0] for x in self.dbList]
        self._selected_station = self._stations[0]
        station_id = get_noaa_id(self._selected_station)

        self.db = dbCoupler()
        print(self.dbList[0])
        self.db.open(self.dbList[0])

        self.years, self.np_climate_data, missing_data = self.db.rd_climate_data()

        # Examine climate_data for void (i.e. missing, all fields == nan) data
        # Create a list of tuples: [(all_nan : bool, num_consecutive : int)]
        # Attempt Download of Missing Data from NOAA & Update DB if available
        for _yrenum in range(self.np_climate_data.shape[0]):
            chkyear = self.years[_yrenum]

            void = [np.all([np.isnan(x) for x in y]) for y in self.np_climate_data[_yrenum, :]]
            isnan_grpsize = [(_k, sum(1 for _ in _v)) for _k, _v in groupby(void)]
            isnan_dayenum = [0] + list(accumulate([x[1] for x in isnan_grpsize]))
            assert isnan_dayenum[-1] == self.np_climate_data.shape[1]   # the sum of all grp elements should == 366

            for _grpidx, _isnan_grp in enumerate(isnan_grpsize):
                dayenum = isnan_dayenum[_grpidx]
                dayMMDD = dayInt2MMDD(dayenum)

                if _isnan_grp[0]:
                    if dayMMDD == (2,29) and isnan_grpsize[_grpidx][1] == 1 and not self.db.is_leap_year(chkyear):
                        continue

                    grp_size = isnan_grpsize[_grpidx]
                    grp_dayenum = isnan_dayenum[_grpidx]
                    print('  Missing Data: {} {} + {} days'.format(chkyear,
                                                                   dayInt2Label(grp_dayenum),
                                                                   grp_size[1] - 1))

                    if chkyear == date.today().year and _grpidx == len(isnan_grpsize) - 1:
                        update_day = date(chkyear, *dayInt2MMDD(grp_dayenum))
                        update_vals = get_dataset_v1(station_id, update_day)
                        if not update_vals:
                            print('  No Updates for {}'.format(update_day))

                        else:
                            for _val in update_vals:
                                info = ', '.join([f'{_k}:{_v}' for _k, _v in _val._asdict().items() if _k != 'date'])
                                print('    Add {}: '.format(_val.date) + info)
                            self.db.add_climate_data(str(chkyear), update_vals)

        # Initial Gui Setup
        super().__init__()
        self.geometry('+{}+{}'.format(*self._posXY))
        self.title("Climate Data Analyzer")
        self._style = guiStyle(self)  #Style for all Widgets!

        # --- Plot Widget ---
        self._plot_widget = guiPlot(self, self._selected_station, self.years, self.np_climate_data, figsize = (1000, 400))
        self._plot_widget.grid(row = 0, column = 0, rowspan = 1, columnspan = 7)

        self.bind("<Map>", self.on_map)
        self.bind("<Configure>", self.on_configure)
        # self.bind("<KeyPress>", self.on_key)
        self.bind("<Motion>", self.on_motion)
        self.bind("<Button-1>", self.on_button1_press)

        self.rowconfigure(0, weight=1)      # Expand Widgets in Height
        self.columnconfigure(0, weight=1)   # Expand Widgets in Width
        print('tkinter Version: {}'.format(self.tk.call('info', 'patchlevel')))

        # --- Buttons & Selection Menus ---
        self._info_text = tk.StringVar()                # Information Widget
        self._tk_info = ttk.Label(self, textvariable = self._info_text, width = 32)
        self._tk_info.grid(row = 1, column = 0, sticky='nsw')

        self._YearMenu = None
        self._DayEntry = None

        self.cd_names = [x.upper() for x in self.np_climate_data.dtype.names]  # Numpy Structured Array Field Names
        self._ObserMenu = tkOptionMenu(self, self.cd_names, self.cd_names.index('PRCP'), self.on_ObserMenu)
        self._ObserMenu.grid(row = 1, column = 5, sticky='e')

        self._TypeButton = tkToggleButton(self, PLOT_TYPE, self.on_TypeButton)
        self._TypeButton.grid(row = 1, column = 6, sticky='nse')
        self._TypeButton.enum = PLOT_TYPE.ALL_DOY

        self._ArgSelFrame = tkArgSelFrame(self, self._TypeButton.enum, self.on_ArgSel, self.on_ArgLimits)
        self._ArgSelFrame.grid(row = 1, column = 1)
        self._ArgSelFrame.argtype = PLOT_TYPE.ALL_DOY

        init_yrenum = len(self.years) - 1
        self._ArgSelFrame.argvalue = self.years[init_yrenum]
        # print(self._ArgSelFrame.argvalue)

        self._plot_widget.plot(self._TypeButton.enum, self._ObserMenu.selectedItem, init_yrenum)
        self._update_info_text()

    def _update_info_text(self):
        cursor_xyz = self._plot_widget.cursor
        # print('here {}'.format(cursor_xyz))
        # return

        datestr = '{}-{}-{}'.format(*cursor_xyz[0])
        self._info_text.set('{} :   dayVal: {:.2f}   maVal: {:.2f}'.format(datestr, *cursor_xyz[1:]))

    def on_cfgOption(self, value):
        if value >= 0 and value <= 365:
            self._info_text.set(dayInt2Label(value))
            self._plot_widget.plot(self._TypeButton.enum, self._ObserMenu.selectedItem, self._DayEntry.value)
        else:
            print('Bad')

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


    def on_motion(self, event):
        """ Motion Events for ALL Widgets, 'event' provides cursor position in 'Display' Space
            and is converted to 'Data' Space to update the cursor position.
        """
        if event.widget == self._plot_widget.tkwidget:
            cursor_xy = self._plot_widget.xform_tk_coords(event.x, event.y)

            if self._ArgSelFrame.argtype == PLOT_TYPE.SNGL_DOY:
                size_x = self.np_climate_data.shape[0]
            else:
                size_x = self.np_climate_data.shape[1]

            cursor_x = size_x - 1 if cursor_xy[0] >= size_x else cursor_xy[0]
            cursor_x = 0 if cursor_x < 0 else cursor_x

            # print('motion {} {} {} {:.3f}'.format(self._ArgSelFrame.argtype.name, max_x, *cursor_xy))
            self._plot_widget.set_cursor(cursor_x)
            self._update_info_text()

    def on_TypeButton(self, new_type):
        try:
            argType = self._ArgSelFrame.argtype # This May Not Exist

            if argType != new_type:

                if new_type == PLOT_TYPE.ALL_DOY:
                    self._ArgSelFrame.argvalue = self._plot_widget.year
                    plot_arg = self._plot_widget.yearenum

                elif new_type == PLOT_TYPE.SNGL_DOY:
                    self._ArgSelFrame.argvalue = self._plot_widget.dayenum
                    plot_arg = self._plot_widget.dayenum

                elif new_type == PLOT_TYPE.HISTO:
                    plot_arg = self._plot_widget.dayenum

                # self._ArgSelFrame.argvalue = self._plot_widget.year
                self._ArgSelFrame.argtype = new_type

            else:
                raise ValueError('on_TypeButton argType Error')

            print('  on_TypeButton {} -> {}'.format(argType.name, new_type.name))

            argVal = self._ArgSelFrame.argvalue # This May Not Exist
            self._plot_widget.plot(self._TypeButton.enum, self._ObserMenu.selectedItem, plot_arg)
            self._update_info_text()

        except AttributeError:
            print('AttributeError {}'.format(new_type.name))

        except Exception as e:
            print(f'  on_TypeButton Exception {e}')


    def on_ArgSel(self, argType, argVal):
        """ Performs validation of new argVal
        """
        if argType == PLOT_TYPE.SNGL_DOY or argType == PLOT_TYPE.HISTO:
            plot_arg = argVal
            if plot_arg < 0 or plot_arg >= self.np_climate_data.shape[1]:
                return False

        elif argType == PLOT_TYPE.ALL_DOY:
            try:
                plot_arg = self.years.index(argVal)
                if plot_arg < 0 or plot_arg >= self.np_climate_data.shape[0]:
                    return False
            except:
                return False

        self._plot_widget.plot(self._TypeButton.enum, self._ObserMenu.selectedItem, plot_arg)
        self._update_info_text()
        return True

    def on_ArgLimits(self, argType):
        if argType == PLOT_TYPE.SNGL_DOY:
            return (0, self.np_climate_data.shape[1] - 1)

        elif argType == PLOT_TYPE.ALL_DOY:
            return (self.years[0], self.years[self.np_climate_data.shape[0] - 1])

        elif argType == PLOT_TYPE.HISTO:
            return (0, self.np_climate_data.shape[1] - 1)

    def on_ObserMenu(self, xItem):
        """ Activated on changes to SelectionFrame and displays the appropriate Frame.
            If the current mode doesn't match the ActiveFrame it is hidden via grid_remove()
            and the appropriate frame is created (if necessary) and then displayed.
        """
        if self._TypeButton.enum == PLOT_TYPE.SNGL_DOY:
            plotarg = self._plot_widget.dayenum

        elif self._TypeButton.enum == PLOT_TYPE.ALL_DOY:
            plotarg = self._plot_widget.yearenum

        elif self._TypeButton.enum == PLOT_TYPE.HISTO:
            plotarg = 0

        print('guiMain.on_xItem {} {}'.format(xItem, self._ObserMenu.selectedItem))
        self._plot_widget.plot(self._TypeButton.enum, self._ObserMenu.selectedItem, plotarg)

    # def on_YearMenu(self, xItem):
    #     """ Activated on changes to SelectionFrame and displays the appropriate Frame.
    #         If the current mode doesn't match the ActiveFrame it is hidden via grid_remove()
    #         and the appropriate frame is created (if necessary) and then displayed.
    #     """

    #     print('guiMain.on_YearMenu {} {}'.format(self._ModeMenu.selectedItem, xItem))
    #     self._plot_widget.update(self._ModeMenu.selectedItem, xItem)

    def on_map(self, event):
        """ Initialize the _width attribute and maintain dict of mappedWidgets.
        """
        # if event.widget == self._plot_widget.tk_canvas:
        #     print('guiMain Map       {:16} [{}]'.format(event.widget.winfo_name(), event.widget.winfo_id()))
        pass


    def on_configure(self, event):
        """ Track Position of guiMain AND fix incorrect guiMain width changes made by MPL.
            Changes to ActiveFrame Widget configure may incorrectly change guiMain width.
            Fixed Here.
        """
        # print(event)
        if event.widget == self:
            self._posXY = (event.x, event.y)
            # print('guiMain Configure {:16} [{}] {}'.format(event.widget.winfo_name(), event.widget.winfo_id(), self._posXY))

            # config_widget_list = list(self._configuredWidgets.keys())
            # for _id, _widget in self.fix_widgets.items():
            #     if _id not in config_widget_list:
            #         _widget.bind("<Map>", self.on_map)
            #         _widget.bind("<Unmap>", self.on_unmap)
            #         self._configuredWidgets[_id] = _widget
            # #         print('*Configure [{:8}] {}'.format(_id, str(_widget)))
            # self.fix_geo()



    def mainloop(self):
        tk.mainloop()


class tkArgSelFrame(ttk.Frame):
    """ A Container (i.e. Frame) Class that changes gui widgets depending on its argType.

    """

    def __init__(self, parent, argType, callback, callback_lim):
        self._parent = parent
        self._argType = argType
        self._callback = callback
        self._callback_lim = callback_lim
        self._label_text = tk.StringVar()                # Information Widget
        super().__init__(parent, width = 100)

        self.iconLf = tk.PhotoImage(master=self, file = 'arrow-lf16x16.gif', name = 'arrow-lf')
        self._tkPrevBtn = ttk.Button(self, image = self.iconLf, width = 1, command=self.on_PrevBtn)
        self._tkPrevBtn.grid(row = 0, column = 2, sticky = 'nse')

        self.iconRt = tk.PhotoImage(master=self, file = 'arrow-rt16x16.gif', name = 'arrow-rt')
        self._tkNextBtn = ttk.Button(self, image = self.iconRt, width = 1, command=self.on_NextBtn)
        self._tkNextBtn.grid(row = 0, column = 3, sticky = 'nse')

        self._ArgEntry = tkIntEntry(self, 'Day', self.on_ArgEntry)
        self._ArgEntry.grid(row = 0, column = 1, sticky='e')
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
        if self._argType == PLOT_TYPE.SNGL_DOY or self._argType == PLOT_TYPE.HISTO:
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
        print('tkArgSelFrame.on_ArgEntry {}'.format(value))

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

        print('XItem Change {}'.format(val))

        if self.event_callback:
            self.event_callback(val)



if __name__ == '__main__':
    gui = guiMain();
    gui.mainloop()
