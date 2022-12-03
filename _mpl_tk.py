"""  Support for Matplotlib Integration with tkinter
"""
import math
import uuid
import numpy as np
import tkinter as tk

from matplotlib.backends import _tkagg
from matplotlib.backend_bases import FigureCanvasBase
from matplotlib.backends.backend_agg import FigureCanvasAgg

_blit_args = {}
# Initialize to a non-empty string that is not a Tcl command
_blit_tcl_name = "mpl_blit_" + uuid.uuid4().hex

TK_PHOTO_COMPOSITE_OVERLAY = 0  # apply transparency rules pixel-wise
TK_PHOTO_COMPOSITE_SET = 1  # set image buffer directly

def _blit(argsid):
    """
    Thin wrapper to blit called via tkapp.call.

    *argsid* is a unique string identifier to fetch the correct arguments from
    the ``_blit_args`` dict, since arguments cannot be passed directly.
    """
    photoimage, dataptr, offsets, bboxptr, comp_rule = _blit_args.pop(argsid)
    _tkagg.blit(photoimage.tk.interpaddr(), str(photoimage), dataptr,
                comp_rule, offsets, bboxptr)

def blit(photoimage, aggimage, offsets, bbox=None):
    """
    Blit *aggimage* to *photoimage*.

    *offsets* is a tuple describing how to fill the ``offset`` field of the
    ``Tk_PhotoImageBlock`` struct: it should be (0, 1, 2, 3) for RGBA8888 data,
    (2, 1, 0, 3) for little-endian ARBG32 (i.e. GBRA8888) data and (1, 2, 3, 0)
    for big-endian ARGB32 (i.e. ARGB8888) data.

    If *bbox* is passed, it defines the region that gets blitted. That region
    will be composed with the previous data according to the alpha channel.

    Tcl events must be dispatched to trigger a blit from a non-Tcl thread.
    """
    data = np.asarray(aggimage)
    height, width = data.shape[:2]
    dataptr = (height, width, data.ctypes.data)
    if bbox is not None:
        (x1, y1), (x2, y2) = bbox.__array__()
        x1 = max(math.floor(x1), 0)
        x2 = min(math.ceil(x2), width)
        y1 = max(math.floor(y1), 0)
        y2 = min(math.ceil(y2), height)
        bboxptr = (x1, x2, y1, y2)
        comp_rule = TK_PHOTO_COMPOSITE_OVERLAY
    else:
        bboxptr = (0, width, 0, height)
        comp_rule = TK_PHOTO_COMPOSITE_SET

    # NOTE: _tkagg.blit is thread unsafe and will crash the process if called
    # from a thread (GH#13293). Instead of blanking and blitting here,
    # use tkapp.call to post a cross-thread event if this function is called
    # from a non-Tcl thread.

    # tkapp.call coerces all arguments to strings, so to avoid string parsing
    # within _blit, pack up the arguments into a global data structure.
    args = photoimage, dataptr, offsets, bboxptr, comp_rule
    # Need a unique key to avoid thread races.
    # Again, make the key a string to avoid string parsing in _blit.
    argsid = str(id(args))
    _blit_args[argsid] = args

    try:
        photoimage.tk.call(_blit_tcl_name, argsid)
    except tk.TclError as e:
        if "invalid command name" not in str(e):
            raise
        photoimage.tk.createcommand(_blit_tcl_name, _blit)
        photoimage.tk.call(_blit_tcl_name, argsid)

class FigureCanvasTk(FigureCanvasAgg, FigureCanvasBase):
    def __init__(self, figure=None, master=None, resize_callback=None):
        super().__init__(figure)

        # SOMEWHERE in matplotlib, it uses geometry to scale the drawing and must be set
        w, h = self.get_width_height(physical=True)
        # print('*Creating Canvas with {}x{}'.format(w,h))

        self._tkcanvas = tk.Canvas(
            master=master, background="white",
            width=w, height=h, borderwidth=0, highlightthickness=0)
        self._tkphoto = tk.PhotoImage(
            master=self._tkcanvas, width=w, height=h)
        self._tkcanvas.create_image(w//2, h//2, image=self._tkphoto)
        self._tkcanvas.focus_set()
        self._first_resize = True   #This is a very ugly fix but works!

    def blit(self, bbox=None):
        blit(self._tkphoto, self.renderer.buffer_rgba(),
                         (0, 1, 2, 3), bbox=bbox)

    def draw(self):
        super().draw()
        self.blit()

    def resize(self, event):
        """ tk Callback Function for <Configure> Event, bound by FigureCanvasBase ??
            The event.width, event.height doesn't have the correct values on 1st pass!
        """
        width = event.width
        height = event.height

        # compute desired figure size in inches
        dpival = self.figure.dpi
        winch = width / dpival
        hinch = height / dpival
        self.figure.set_size_inches(winch, hinch, forward=True)

        self._tkcanvas.delete(self._tkphoto)
        self._tkphoto = tk.PhotoImage(
            master=self._tkcanvas, width=int(width), height=int(height))
        self._tkcanvas.create_image(
            int(width / 2), int(height / 2), image=self._tkphoto)
        self.resize_event()


    def get_tk_widget(self):
        """
        Return the Tk widget used to implement FigureCanvasTkAgg.

        Although the initial implementation uses a Tk canvas,  this routine
        is intended to hide that fact.
        """
        return self._tkcanvas
