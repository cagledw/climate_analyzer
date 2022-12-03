import tkinter.ttk as ttk

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
