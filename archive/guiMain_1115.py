"""
  A tkinter GUI Class tailored for displaying Investment Data.  It has 3 main Widgets:
    * SelectFrame  - events from this frame routed to on_selection()
    * AccountFrame - Display Accounts
    * AnalysisFrame - Display Analsysis of Financial Data

  The Select Frame is always displayed.  Only 1 of the other two (Acct or Analysis) may
  optionally be displayed.  Once displayed, the Account or Analysis Widget may then be
  hidden.  Because of the 'hide' feature, and because of matplotlib peculiarities, the
  position and width of guiMain must be managed manually by tracking the state of the
  widgets embedded in it.  Widgets that must be tracked are identified as 'fix_widgets'.

  Which widgets are displayed is controlled by two properties from the SelectFrame:
  - mode    : SELECT_MODE_T
  - submode : ALYZ_TYPE_T

"""

# from enum import IntEnum
# PLOT_MODE = IntEnum('PLOT_MODE', ['Data', 'Alyz'])

from os   import path
from collections import namedtuple

import tkinter as tk
import tkinter.ttk as ttk

from guiPlot   import guiPlot, dayInt2Label, PLOT_TYPE
from dbCoupler import dbCoupler


def guiStyle(parent):
    bg = "gray90"
    fg = "black"
    hi = "green2"

    f1 = ("Comic Sans MS", 10)
    f2 = ('Calibri', 9,'bold')
    f3 = ('Calibri', 10)

    topWidget = parent.winfo_toplevel()
    topWidget.configure(bg=bg)

    _s = ttk.Style()
    _s.theme_use("alt")  # available names: clam, alt, default, classic, vista, xpnative

    # --- Button ---
    # Programmatic States are: [selected, disabled, readonly]
    # Automatic States Changes are:
    _s.configure("TButton",
                 padding=(0,0),
                 background=bg,
                 focuscolor=bg,
                 borderwidth=0,
                 # bordercolor='green2',
                 # highlightcolor='green2',
                 font=f3,
                 relief='raised')

    # _s.map('TButton',
    #        foreground=[('selected', 'black'),
    #                    ('active',  'blue'),
    #                    ('disabled',  'red'),
    #                    ('readonly',  'black')],
    #        background=[('selected', 'IndianRed1'),
    #                    ('alternate',  'DarkSeaGreen1'),
    #                    ('active',  bg),
    #                    ('disabled', bg),
    #                    ('readonly', bg)],
    #        relief=[('selected', 'raised'),
    #                ('alternate', 'raised')])

    _s.map('TButton',
           foreground=[('selected', 'blue'),
                       ('readonly',  'blue')],
           background=[('selected', bg),
                       ('readonly', bg)],
           relief=[('selected', 'raised'),
                   ('alternate', 'raised')])
    return _s

class guiMain(tk.Tk):
    """ A tk Application (i.e. Main/Root Window) to display Weather Data
        Weather data is expected to be a dict of numpy structed arrays, keyed by int(year)
    """
    def __init__(self, dbList, pos_tuple):

        self.dbList = dbList
        self._posXY = pos_tuple
        self._stations = [path.splitext(path.basename(x))[0] for x in self.dbList]
        self._selected_station = self._stations[0]

        self.db = dbCoupler()
        print(self.dbList[0])
        self.db.open(self.dbList[0])

        self.years, self.np_climate_data = self.db.rd_climate_data()
        self.cd_names = [x.upper() for x in self.np_climate_data.dtype.names]
        # print(self.np_climate_data.shape)
        # print(self.np_climate_data.dtype.names)

        # Initial Gui Setup
        super().__init__()
        self.geometry('+{}+{}'.format(*self._posXY))
        self.title("Climate Data Analyzer")
        self._style = guiStyle(self)  #Style for all Widgets!


        # --- Plot Widget ---
        self._plot_widget = guiPlot(self, self._selected_station, self.years, self.np_climate_data, figsize = (800, 400))
        self._plot_widget.grid(row = 0, column = 0, rowspan = 1, columnspan = 5)

        self.bind("<Map>", self.on_map)
        self.bind("<Configure>", self.on_configure)
        # self.bind("<KeyPress>", self.on_key)
        self.bind("<Motion>", self.on_motion)

        self.rowconfigure(0, weight=1)      # Expand Widgets in Height
        self.columnconfigure(0, weight=1)   # Expand Widgets in Width
        print('tkinter Version: {}'.format(self.tk.call('info', 'patchlevel')))

        # --- Buttons & Selection Menus ---
        self._info_text = tk.StringVar()                # Information Widget
        self._tk_info = ttk.Label(self, textvariable = self._info_text)
        self._tk_info.grid(row = 1, column = 0, sticky='nsw')
        # self._info_text.set('Testing123')

        self._YearMenu = None
        self._DayEntry = None

        self._ObserMenu = tkOptionMenu(self, self.cd_names, self.cd_names.index('PRCP'), self.on_ObserMenu)
        self._ObserMenu.grid(row = 1, column = 3, sticky='e')

        self._TypeButton = tkToggleButton(self, PLOT_TYPE, self.on_TypeButton)
        self._TypeButton.grid(row = 1, column = 4, sticky='nse')
        self._TypeButton.enum = PLOT_TYPE(1)

        # self.configOptions()
        # self._plot_widget.plot(self._TypeButton.enum, self._ObserMenu.selectedItem)

        # print(self._YearMenu.selectedItem, self._ModeMenu.selectedItem)
        # self._plot_widget.plot_series(self._ModeMenu.selectedItem, self._YearMenu.selectedItem)


    # def configOptions(self):
    #     if self._TypeButton.enum == PLOT_TYPE.SNGL_DOY:
    #         self._DayEntry = tkIntEntry(self, 'Day', self.on_cfgOption)
    #         self._DayEntry.grid(row = 1, column = 1, sticky='e')
    #         info_text = dayInt2Label(self._DayEntry.value)
    #         self._info_text.set(info_text)

    #         # print(info_text)

    #         # print('Config Analysis')
    #     else:
    #         print('Config Observation')

        # self._YearMenu = tkOptionMenu(self, self.years, -1, self.on_YearMenu)     # Range Selection Widget
        # self._YearMenu.grid(row = 1, column = 2, sticky='e')

    def on_cfgOption(self, value):
        if value >= 0 and value <= 365:
            self._info_text.set(dayInt2Label(value))
            self._plot_widget.plot(self._TypeButton.enum, self._ObserMenu.selectedItem, self._DayEntry.value)
        else:
            print('Bad')

    def on_motion(self, event):
        cursor_xy = self._plot_widget.xform_tk_coords(event.x, event.y)
        self._plot_widget.set_cursor(cursor_xy[0])
        cursor_date = self._plot_widget.days2date(cursor_xy[0])

        # self._info_text.set(str(cursor_date))


    # def on_key(self, event):
    #     """ Debug Support
    #     """
    #     print('    self.mapped_widgets geo: {}:'.format(self.geometry()))
    #     for _id, _widget in self._mappedWidgets.items():
    #         print('     [{:8}] {} reqw: {:3}, w: {:3} {:30}'.format(_id, _widget.winfo_ismapped(),
    #                                                            _widget.winfo_reqwidth(),
    #                                                            _widget.winfo_width(),
    #                                                            str(_widget)))

    #     print('    self.configured_widgets, posXY {}:'.format(self._posXY))
    #     for _id, _widget in self._configuredWidgets.items():
    #         print('     [{:8}] {} reqw: {:3}, w: {:3} {:30}'.format(_id, _widget.winfo_ismapped(),
    #                                                            _widget.winfo_reqwidth(),
    #                                                            _widget.winfo_width(),
    #                                                            str(_widget)))

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


    def on_selection(self, mode):
        """ Activated on changes to SelectionFrame and displays the appropriate Frame.
            If the current mode doesn't match the ActiveFrame it is hidden via grid_remove()
            and the appropriate frame is created (if necessary) and then displayed.
        """

        # if len(self.selected_items) == 0:
        #     return

        # if guiMain._dbugMe:
        print('guiMain.on_selection')
            # submode = f'-{self.submode.name}' if self.mode == SELECT_MODE_T.Analysis else ''
            # print('--- guiMain.on_selection {}{}, ActiveFrame: {}'.format(mode.name,
                                                                          # submode,
                                                                          # self._ActiveFrame))
    def on_TypeButton(self, new_type):
        if new_type == PLOT_TYPE.SNGL_DOY:
            self._DayEntry = tkIntEntry(self, 'Day', self.on_cfgOption)
            self._DayEntry.grid(row = 1, column = 1, sticky='e')
            info_text = dayInt2Label(self._DayEntry.value)
            self._info_text.set(info_text)

            self._plot_widget.plot(new_type, self._ObserMenu.selectedItem, self._DayEntry.value)
        else:
            print('Config Observation')


    def on_ObserMenu(self, xItem):
        """ Activated on changes to SelectionFrame and displays the appropriate Frame.
            If the current mode doesn't match the ActiveFrame it is hidden via grid_remove()
            and the appropriate frame is created (if necessary) and then displayed.
        """

        print('guiMain.on_xItem {}'.format(xItem))
        self._plot_widget.update(self._selected_station, xItem)

    def on_YearMenu(self, xItem):
        """ Activated on changes to SelectionFrame and displays the appropriate Frame.
            If the current mode doesn't match the ActiveFrame it is hidden via grid_remove()
            and the appropriate frame is created (if necessary) and then displayed.
        """

        print('guiMain.on_YearMenu {} {}'.format(self._ModeMenu.selectedItem, xItem))
        self._plot_widget.update(self._ModeMenu.selectedItem, xItem)

    def mainloop(self):
        tk.mainloop()


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
        self._label = ttk.Label(parent, text = 'Day:')

        self._reg = parent.register(self.isOkay)
        self.config(validate = 'key', validatecommand = (self._reg, '%d', '%P'))

    @property
    def value(self):
        return self._value

    def grid(self, row, column, sticky):
        self._label.grid(row = 1, column = 1, sticky='e')
        super().grid(row = 1, column = 2, sticky='e')

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
        self.state(['selected'])

        if self._event_callback:
            self._event_callback(self._CurrentEnum)

    def on_change(self):
        print('tkToggleButton.enum.on_change')

        try:    self._CurrentEnum = self._type(self._CurrentEnum.value + 1)
        except: self._CurrentEnum = self._type(1)
        self._tkVar.set(self._CurrentEnum.name)

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

# class tkMetricMenu(ttk.OptionMenu):
#     """ A tk Widget that presents a Menu of Options. To populate the menu options,
#         use the update() method.  Any previous options are deleted on each update().
#     """
#     def __init__(self, parent, event_callback = None):

#         self._event_callback = event_callback
#         self._opt_list = []
#         self._selected_opt = None

#         self._tkVar = tk.StringVar(parent)
#         # self._tkVar.set(None)

#         super().__init__(parent,
#                          self._tkVar,
#                          # self._tkVar.get(),
#                          None,
#                          None,
#                          command = self.on_change)
#         self.configure(width = 12)

#     @property
#     def selected_item(self):
#         # if not self._tkVar.get():
#         #     sel = None
#         # else:
#         #     sel = next(filter(lambda x: x.name == self._tkVar.get(), self._opt_list)).name

#         # print('tkMetricMenu selected_item = {}, {}'.format(sel, self._selected_opt))

#         # return sel
#         return self._selected_opt

#     def update(self, opt_list):
#         """ Can be called directly from tkinter
#         """
#         self._opt_list = opt_list

#         for _opt in opt_list:
#             if _opt.state == 'normal':
#                 self._selected_opt = _opt.name
#                 break
#         else:
#             self._selected_opt = None

#         self.set_menu(self._selected_opt, *[x.name for x in opt_list])
#         for _opt in opt_list:
#             self['menu'].entryconfig(_opt.name, state = _opt.state)

#         # print('tkMetricMenu.update {} {}'.format(self._selected_opt, self._tkVar.get()))
#         # for _item in self._opt_list:
#         #     print('  {:20} {}'.format(_item.name, _item.state))

#     def on_change(self, val):
#         print('tkMetricMenu.on_change')
#         self._selected_opt = val
#         self._event_callback(val)


if __name__ == '__main__':
    gui = guiMain();
    gui.mainloop()
