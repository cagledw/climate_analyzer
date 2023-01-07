import tkinter.ttk as ttk

def guiStyle(parent):
    bg = "gray90"
    fg = "black"
    hi = "green2"

    f1 = ("Comic Sans MS", 10)
    f2 = ('Calibri', 9,'bold')
    f3 = ('Calibri', 10)
    f4 = ('Calibri', 11)

    topWidget = parent.winfo_toplevel()
    topWidget.configure(bg=bg)

    _s = ttk.Style()
    _s.theme_use("alt")  # available names: clam, alt, default, classic, vista, xpnative

    # --- Button ---
    # Programmatic States are: [selected, disabled, readonly]
    # Automatic States Changes are: [active, focus, hover, pressed}
    # Each State is a boolean!
    # Ensure focuscolor == background to active active dashed line
    _s.configure("TButton",
                 padding=(0,0),
                 background=bg,
                 focuscolor=bg,
                 borderwidth=0,
                 # bordercolor='green2',
                 # highlightcolor='green2',
                 font=f3,
                 relief='raised')


    _s.map('TButton',
           foreground=[('selected', 'blue'),
                       ('readonly',  'blue')],
           background=[('selected', bg),
                       ('readonly', bg)],
           relief=[('selected', 'groove'),
                   ('!selected', 'ridge')])

    _s.configure("red.TButton",
                 padding=(0,0),
                 background='red',
                 focuscolor='red',
                 borderwidth=0,
                 # bordercolor='green2',
                 # highlightcolor='green2',
                 font=f4)

    _s.map('red.TButton',
           foreground=[('selected', 'blue'),
                       ('readonly',  'blue')],
           background=[('selected', bg),
                       ('readonly', bg)],
           relief=[('pressed', 'groove'),
                   ('!pressed', 'ridge')])

    return _s
