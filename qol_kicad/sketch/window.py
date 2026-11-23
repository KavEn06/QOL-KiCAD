"""The sketch window: a canvas, a tool column and a value box around a Controller."""

from __future__ import annotations

import math
from typing import Callable, List, Optional, Sequence, Tuple

import wx

from .. import generators
from ..geom import Line, Point, Shape, bbox, dist, sample
from .model import TOL, Sketch
from .tools import MM, TOOLS, Controller

GRIDS = ["Off", "0.1", "0.25", "0.5", "1", "2.54", "5", "10"]
PICK_PX = 8

BACKGROUND = wx.Colour(24, 26, 32)
GRID = wx.Colour(60, 64, 76)
REFERENCE = wx.Colour(120, 124, 136)
EDGE = wx.Colour(232, 200, 72)
SELECTED = wx.Colour(80, 200, 255)
PREVIEW = wx.Colour(255, 255, 255)
SNAP = wx.Colour(120, 255, 140)
TEXT = wx.Colour(210, 214, 224)

# name -> (value, label, default) rows for "Add shape"
SHAPE_FIELDS = [
    ("shape", "Shape", ["Rounded rectangle", "Slot", "Polygon"]),
    ("width", "Width / slot width / polygon diameter (mm)", 50.0),
    ("height", "Height / slot length (mm)", 30.0),
    ("radius", "Corner radius (mm)", 2.0),
    ("sides", "Polygon sides", 6.0),
    ("vertical", "Slot: vertical", False),
]


class Canvas(wx.Window):
    def __init__(self, parent, controller: Controller, on_change: Callable[[], None]):
        super().__init__(parent, style=wx.WANTS_CHARS | wx.FULL_REPAINT_ON_RESIZE)
        self.SetBackgroundStyle(wx.BG_STYLE_PAINT)
        self.c = controller
        self.on_change = on_change
        self.scale = 5e-6  # pixels per nanometre
        self.origin: Point = (0.0, 0.0)  # board point at the top-left pixel
        self._pan: Optional[Tuple[int, int]] = None
        self.Bind(wx.EVT_PAINT, self.on_paint)
        self.Bind(wx.EVT_LEFT_DOWN, self.on_down)
        self.Bind(wx.EVT_LEFT_UP, self.on_up)
        self.Bind(wx.EVT_MOTION, self.on_motion)
        self.Bind(wx.EVT_MOUSEWHEEL, self.on_wheel)
        for ev in (wx.EVT_MIDDLE_DOWN, wx.EVT_RIGHT_DOWN):
            self.Bind(ev, self.on_pan_start)
        for ev in (wx.EVT_MIDDLE_UP, wx.EVT_RIGHT_UP):
            self.Bind(ev, self.on_pan_end)

    # -- view -------------------------------------------------------------------
    def to_board(self, x: float, y: float) -> Point:
        return (self.origin[0] + x / self.scale, self.origin[1] + y / self.scale)

    def to_screen(self, p: Point) -> Tuple[float, float]:
        return ((p[0] - self.origin[0]) * self.scale, (p[1] - self.origin[1]) * self.scale)

    def fit(self, shapes: Sequence[Shape]) -> None:
        w, h = self.GetClientSize()
        if not shapes or w < 20 or h < 20:
            self.scale = 5e-6
            self.origin = (-w / 2 / self.scale, -h / 2 / self.scale)
        else:
            x0, y0, x1, y1 = bbox(list(shapes))
            self.scale = min(w / max(x1 - x0, MM), h / max(y1 - y0, MM)) * 0.8
            self.origin = ((x0 + x1) / 2 - w / 2 / self.scale, (y0 + y1) / 2 - h / 2 / self.scale)
        self._sync()

    def _sync(self) -> None:
        self.c.tol = PICK_PX / self.scale
        self.Refresh()

    def _event_point(self, event) -> Point:
        return self.to_board(event.GetX(), event.GetY())

    # -- mouse ------------------------------------------------------------------
    def on_down(self, event) -> None:
        self.SetFocus()
        if not self.HasCapture():
            self.CaptureMouse()
        self.c.press(self._event_point(event), event.ShiftDown())
        self.on_change()

    def on_up(self, event) -> None:
        if self.HasCapture():
            self.ReleaseMouse()
        self.c.release(self._event_point(event), event.ShiftDown())
        self.on_change()

    def on_motion(self, event) -> None:
        if self._pan is not None:
            dx, dy = event.GetX() - self._pan[0], event.GetY() - self._pan[1]
            self.origin = (self.origin[0] - dx / self.scale, self.origin[1] - dy / self.scale)
            self._pan = (event.GetX(), event.GetY())
            self.Refresh()
            return
        self.c.move(self._event_point(event), event.ShiftDown())
        self.on_change()

    def on_wheel(self, event) -> None:
        at = self._event_point(event)
        factor = 1.2 ** (event.GetWheelRotation() / max(event.GetWheelDelta(), 1))
        self.scale = min(max(self.scale * factor, 1e-8), 1e-2)
        self.origin = (at[0] - event.GetX() / self.scale, at[1] - event.GetY() / self.scale)
        self._sync()

    def on_pan_start(self, event) -> None:
        self._pan = (event.GetX(), event.GetY())

    def on_pan_end(self, event) -> None:
        self._pan = None

    # -- drawing ----------------------------------------------------------------
    def _stroke(self, gc, shapes: Sequence[Shape], colour, width: float = 1.5, style=wx.PENSTYLE_SOLID) -> None:
        if not shapes:
            return
        gc.SetPen(wx.Pen(colour, max(1, int(round(width))), style))
        gc.SetBrush(wx.TRANSPARENT_BRUSH)
        path = gc.CreatePath()
        for s in shapes:
            pts = [self.to_screen(p) for p in sample(s)]
            path.MoveToPoint(*pts[0])
            for p in pts[1:]:
                path.AddLineToPoint(*p)
        gc.StrokePath(path)

    def _label(self, gc, text: str, at: Point, colour=TEXT) -> None:
        gc.SetFont(self.GetFont(), colour)
        x, y = self.to_screen(at)
        gc.DrawText(text, x + 8, y - 18)

    def on_paint(self, event) -> None:
        dc = wx.AutoBufferedPaintDC(self)
        dc.SetBackground(wx.Brush(BACKGROUND))
        dc.Clear()
        gc = wx.GraphicsContext.Create(dc)
        c, sk = self.c, self.c.sketch
        w, h = self.GetClientSize()

        step = c.grid
        if step > 0:
            while step * self.scale < 12:
                step *= 5
            gc.SetPen(wx.Pen(GRID, 1))
            x0, y0 = self.to_board(0, 0)
            path = gc.CreatePath()
            gx = math.floor(x0 / step) * step
            while (gx - self.origin[0]) * self.scale < w:
                gy = math.floor(y0 / step) * step
                while (gy - self.origin[1]) * self.scale < h:
                    px, py = self.to_screen((gx, gy))
                    path.MoveToPoint(px - 1, py)
                    path.AddLineToPoint(px + 1, py)
                    gy += step
                gx += step
            gc.StrokePath(path)

        self._stroke(gc, sk.reference, REFERENCE, 1, wx.PENSTYLE_SHORT_DASH)
        plain = [s for i, s in enumerate(sk.shapes) if i not in c.selection]
        chosen = [s for i, s in enumerate(sk.shapes) if i in c.selection]
        self._stroke(gc, plain, EDGE, 2)
        self._stroke(gc, chosen, SELECTED, 3)

        gc.SetPen(wx.Pen(EDGE, 1))
        gc.SetBrush(wx.Brush(BACKGROUND))
        for i, s in enumerate(sk.shapes):
            if s.closed:
                continue
            gc.SetPen(wx.Pen(SELECTED if i in c.selection else EDGE, 1))
            for p in (s.start, s.end):
                x, y = self.to_screen(p)
                gc.DrawRectangle(x - 3, y - 3, 6, 6)

        for s in chosen[:12]:
            self._label(gc, describe(s), s.mid, SELECTED)

        self._stroke(gc, c.preview, PREVIEW, 1.5, wx.PENSTYLE_SHORT_DASH)
        if c.preview and not c.placing and len(c.preview) == 1:
            self._label(gc, describe(c.preview[0]), c.cursor, PREVIEW)
        if c.box:
            (ax, ay), (bx, by) = self.to_screen(c.box[0]), self.to_screen(c.box[1])
            gc.SetPen(wx.Pen(SELECTED, 1, wx.PENSTYLE_SHORT_DASH))
            gc.SetBrush(wx.Brush(wx.Colour(80, 200, 255, 30)))
            gc.DrawRectangle(min(ax, bx), min(ay, by), abs(bx - ax), abs(by - ay))
        if c.snap_kind and (c.tool != "select" or c.placing):
            x, y = self.to_screen(c.cursor)
            gc.SetPen(wx.Pen(SNAP, 2))
            gc.SetBrush(wx.TRANSPARENT_BRUSH)
            gc.DrawEllipse(x - 5, y - 5, 10, 10)
            if c.snap_kind != "grid":
                gc.SetFont(self.GetFont(), SNAP)
                gc.DrawText(c.snap_kind, x + 8, y + 6)


def describe(s: Shape) -> str:
    if isinstance(s, Line):
        angle = math.degrees(math.atan2(-(s.b[1] - s.a[1]), s.b[0] - s.a[0])) % 360
        return f"{s.length / MM:.3f} mm  {angle:.1f}°"
    if s.closed:
        return f"R {s.r / MM:.3f} mm"
    return f"R {s.r / MM:.3f} mm  {abs(math.degrees(s.sweep)):.1f}°"


def open_ends(shapes: Sequence[Shape]) -> int:
    ends = [p for s in shapes if not s.closed for p in (s.start, s.end)]
    return sum(1 for p in ends if sum(1 for q in ends if dist(p, q) <= TOL) != 2)


class SketchFrame(wx.Frame):
    """``on_finish(shapes, layer_index, name)`` puts the sketch on the board and returns a message."""

    def __init__(
        self,
        shapes: Sequence[Shape],
        reference: Sequence[Shape],
        layers: Sequence[str],
        layer_index: int,
        name: str,
        editing: bool,
        on_finish: Callable[[List[Shape], int, str], str],
        ask: Callable[..., Optional[dict]],
        read_dxf: Callable[[], Optional[Tuple[List[Shape], str]]],
    ):
        title = "QOL-KiCAD: Sketch" + (f" (editing group '{name}')" if editing else "")
        super().__init__(None, title=title, size=(1180, 780))
        self.sketch = Sketch(shapes, reference)
        self.c = Controller(self.sketch, ask_value=self.ask_value)
        self.on_finish, self.ask, self.read_dxf = on_finish, ask, read_dxf
        self.editing = editing
        self._saved = list(self.sketch.shapes)

        root = wx.Panel(self)
        self.canvas = Canvas(root, self.c, self.refresh)

        top = wx.BoxSizer(wx.HORIZONTAL)

        def button(label: str, handler, tip: str = ""):
            b = wx.Button(root, label=label)
            b.Bind(wx.EVT_BUTTON, lambda e: (handler(), self.refresh()))
            if tip:
                b.SetToolTip(tip)
            top.Add(b, 0, wx.RIGHT, 4)
            return b

        button("Import DXF…", self.import_dxf, "Read a DXF file and place it in the sketch")
        button("Add shape…", self.add_shape, "Rounded rectangle, slot or polygon by size")
        button("Undo", self.c.undo, "Cmd/Ctrl+Z")
        button("Redo", self.c.redo, "Shift+Cmd/Ctrl+Z")
        button("Zoom to fit", self.zoom_fit)
        top.AddStretchSpacer()
        top.Add(wx.StaticText(root, label="Grid (mm)"), 0, wx.ALIGN_CENTER_VERTICAL | wx.RIGHT, 4)
        self.grid = wx.Choice(root, choices=GRIDS)
        self.grid.SetSelection(GRIDS.index("1"))
        self.grid.Bind(wx.EVT_CHOICE, self.on_grid)
        top.Add(self.grid, 0, wx.RIGHT, 10)
        top.Add(wx.StaticText(root, label="Layer"), 0, wx.ALIGN_CENTER_VERTICAL | wx.RIGHT, 4)
        self.layer = wx.Choice(root, choices=list(layers))
        self.layer.SetSelection(layer_index)
        top.Add(self.layer, 0, wx.RIGHT, 10)
        top.Add(wx.StaticText(root, label="Group name"), 0, wx.ALIGN_CENTER_VERTICAL | wx.RIGHT, 4)
        self.name = wx.TextCtrl(root, value=name or "outline", size=(130, -1))
        top.Add(self.name, 0)

        side = wx.BoxSizer(wx.VERTICAL)
        self.tool_buttons = {}
        for tool, label, hint in TOOLS:
            b = wx.ToggleButton(root, label=label, size=(110, -1))
            b.SetToolTip(hint)
            b.Bind(wx.EVT_TOGGLEBUTTON, lambda e, t=tool: (self.c.set_tool(t), self.refresh()))
            side.Add(b, 0, wx.BOTTOM, 2)
            self.tool_buttons[tool] = b

        bottom = wx.BoxSizer(wx.HORIZONTAL)
        self.value_label = wx.StaticText(root, label="Value")
        bottom.Add(self.value_label, 0, wx.ALIGN_CENTER_VERTICAL | wx.RIGHT, 4)
        self.value = wx.TextCtrl(root, size=(110, -1), style=wx.TE_PROCESS_ENTER)
        self.value.Bind(wx.EVT_TEXT_ENTER, self.on_value)
        bottom.Add(self.value, 0, wx.RIGHT, 10)
        self.status = wx.StaticText(root, label="", style=wx.ST_ELLIPSIZE_END)
        bottom.Add(self.status, 1, wx.ALIGN_CENTER_VERTICAL)
        cancel = wx.Button(root, label="Cancel")
        cancel.Bind(wx.EVT_BUTTON, lambda e: self.Close())
        bottom.Add(cancel, 0, wx.LEFT, 6)
        finish = wx.Button(root, label="Update group" if editing else "Insert as group")
        finish.Bind(wx.EVT_BUTTON, lambda e: self.finish())
        bottom.Add(finish, 0, wx.LEFT, 6)

        middle = wx.BoxSizer(wx.HORIZONTAL)
        middle.Add(side, 0, wx.RIGHT, 6)
        middle.Add(self.canvas, 1, wx.EXPAND)
        outer = wx.BoxSizer(wx.VERTICAL)
        outer.Add(top, 0, wx.EXPAND | wx.ALL, 6)
        outer.Add(middle, 1, wx.EXPAND | wx.LEFT | wx.RIGHT, 6)
        outer.Add(bottom, 0, wx.EXPAND | wx.ALL, 6)
        root.SetSizer(outer)

        self.Bind(wx.EVT_CHAR_HOOK, self.on_key)
        self.Bind(wx.EVT_CLOSE, self.on_close)
        self.on_grid(None)
        self.Layout()
        wx.CallAfter(self.zoom_fit)
        wx.CallAfter(self.refresh)

    # -- state ------------------------------------------------------------------
    def refresh(self) -> None:
        c = self.c
        for tool, b in self.tool_buttons.items():
            b.SetValue(tool == c.tool and not c.placing)
        if c.tool in c.values:
            label = f"{c.tool.capitalize()} (mm): {c.values[c.tool]:g}"
        else:
            label = "Value"
        if self.value_label.GetLabel() != label:
            self.value_label.SetLabel(label)
            self.value_label.GetContainingSizer().Layout()
        x, y = c.cursor
        text = f"X {x / MM:.3f}  Y {y / MM:.3f} mm    {c.message or c.hint()}"
        if self.status.GetLabel() != text:
            self.status.SetLabel(text)
        self.canvas.Refresh()

    def zoom_fit(self) -> None:
        self.canvas.fit(list(self.sketch.shapes) + list(self.sketch.reference))

    def on_grid(self, event) -> None:
        choice = GRIDS[self.grid.GetSelection()]
        self.c.grid = 0.0 if choice == "Off" else float(choice) * MM
        self.canvas.Refresh()

    def ask_value(self, label: str, current: float) -> Optional[float]:
        with wx.TextEntryDialog(self, label, "QOL-KiCAD: Dimension", f"{current:g}") as dlg:
            if dlg.ShowModal() != wx.ID_OK:
                return None
            try:
                value = float(dlg.GetValue())
            except ValueError:
                return None
        return value if value > 0 else None

    # -- keys -------------------------------------------------------------------
    def on_value(self, event) -> None:
        if self.c.enter(self.value.GetValue()):
            self.value.SetValue("")
        self.refresh()

    def on_key(self, event) -> None:
        key = event.GetKeyCode()
        typing = isinstance(self.FindFocus(), wx.TextCtrl)
        command = event.CmdDown() or event.ControlDown()
        if key == wx.WXK_ESCAPE:
            self.c.escape()
            self.value.SetValue("")
            self.canvas.SetFocus()
        elif command and key == ord("Z"):
            self.c.redo() if event.ShiftDown() else self.c.undo()
        elif command and key == ord("Y"):
            self.c.redo()
        elif command and key == ord("A") and not typing:
            self.c.select_all()
        elif key in (wx.WXK_DELETE, wx.WXK_BACK) and not typing:
            self.c.delete_selection()
        elif not typing and not command and (chr(key) if 32 < key < 127 else "") in "0123456789.-":
            # typing a number anywhere goes to the value box
            self.value.SetFocus()
            self.value.AppendText(chr(key))
        else:
            event.Skip()
            return
        self.refresh()

    # -- actions ----------------------------------------------------------------
    def _view_centre(self) -> Point:
        w, h = self.canvas.GetClientSize()
        return self.canvas.to_board(w / 2, h / 2)

    def _place(self, shapes: List[Shape]) -> None:
        x0, y0, x1, y1 = bbox(shapes)
        self.c.place([s.moved(-(x0 + x1) / 2, -(y0 + y1) / 2) for s in shapes])
        self.canvas.SetFocus()

    def add_shape(self) -> None:
        p = self.ask("sketch_shape", "Add shape", SHAPE_FIELDS)
        if p is None:
            return
        try:
            if p["shape"] == "Slot":
                shapes = generators.slot((0, 0), p["height"] * MM, p["width"] * MM, p["vertical"])
            elif p["shape"] == "Polygon":
                shapes = generators.polygon((0, 0), int(p["sides"]), p["width"] * MM)
            else:
                shapes = generators.rounded_rect((0, 0), p["width"] * MM, p["height"] * MM, p["radius"] * MM)
        except ValueError as e:
            wx.MessageBox(str(e), "QOL-KiCAD", wx.OK | wx.ICON_ERROR, self)
            return
        self._place(shapes)

    def import_dxf(self) -> None:
        result = self.read_dxf()
        if result is None:
            return
        shapes, message = result
        self._place(shapes)
        self.c.message = message

    def finish(self) -> None:
        shapes = list(self.sketch.shapes)
        if not shapes and not self.editing:
            wx.MessageBox("The sketch is empty.", "QOL-KiCAD", wx.OK | wx.ICON_INFORMATION, self)
            return
        loose = open_ends(shapes)
        if loose and self.layer.GetStringSelection() == "Edge.Cuts":
            text = f"The sketch has {loose} open end{'s' if loose != 1 else ''}, so it is not a closed outline.\nInsert it anyway?"
            if wx.MessageBox(text, "QOL-KiCAD", wx.YES_NO | wx.ICON_WARNING, self) != wx.YES:
                return
        try:
            message = self.on_finish(shapes, self.layer.GetSelection(), self.name.GetValue())
        except Exception as e:
            wx.MessageBox(f"Could not write to the board:\n{type(e).__name__}: {e}", "QOL-KiCAD", wx.OK | wx.ICON_ERROR, self)
            return
        self._saved = shapes
        if message:
            wx.MessageBox(message, "QOL-KiCAD", wx.OK | wx.ICON_INFORMATION, self)
        self.Destroy()

    def on_close(self, event) -> None:
        if event.CanVeto() and list(self.sketch.shapes) != self._saved:
            text = "Close the sketch without putting it on the board?"
            if wx.MessageBox(text, "QOL-KiCAD", wx.YES_NO | wx.ICON_QUESTION, self) != wx.YES:
                event.Veto()
                return
        self.Destroy()
