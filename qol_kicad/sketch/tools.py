"""What mouse clicks and typed values do in each tool. No GUI code, so it can be tested."""

from __future__ import annotations

import math
from typing import Callable, List, Optional, Sequence, Set, Tuple

from ..geom import Arc, Line, Point, Shape, dist
from .model import TOL, Sketch, end_of, tangent_arc

MM = 1e6

# name, label, hint shown in the status bar
TOOLS: Sequence[Tuple[str, str, str]] = (
    ("select", "Select", "Click or drag a box to select. Drag an edge or a corner to move it; joined edges follow."),
    ("line", "Line", "Click points. Type a length, length<angle or dx,dy and press Enter. Esc ends the chain."),
    ("arc", "Arc", "Click the start, the end, then a point on the arc."),
    ("tangent", "Tangent arc", "Click the end of an edge, then where the arc should end."),
    ("circle", "Circle", "Click the centre, then a point on the circle, or type the radius."),
    ("rect", "Rectangle", "Click two opposite corners, or type width,height after the first."),
    ("trim", "Trim", "Click the piece of an edge to remove."),
    ("extend", "Extend", "Click near the end of an edge to lengthen it to the next edge."),
    ("fillet", "Fillet", "Type a radius, then click corners to round them."),
    ("chamfer", "Chamfer", "Type a size, then click corners to cut them."),
    ("offset", "Offset", "Select edges first. Type a distance, then click on the side to copy to."),
    ("mirror", "Mirror", "Select edges first, then click two points of the mirror line."),
    ("dimension", "Dimension", "Click a line to set its length, or an arc or circle to set its radius."),
)
VALUE_TOOLS = {"fillet": 1.0, "chamfer": 1.0, "offset": 1.0}  # default value in mm


def parse_numbers(text: str) -> Optional[Tuple[str, List[float]]]:
    """'30' -> ('', [30]); '30<45' -> ('<', [30, 45]); '10,5' -> (',', [10, 5])."""
    text = text.strip().replace(" ", "")
    for sep in ("<", ",", "x"):
        if sep in text:
            parts = text.split(sep)
            break
    else:
        sep, parts = "", [text]
    try:
        values = [float(p) for p in parts]
    except ValueError:
        return None
    return (sep, values) if len(values) <= 2 else None


class Controller:
    def __init__(self, sketch: Sketch, ask_value: Optional[Callable[[str, float], Optional[float]]] = None):
        self.sketch = sketch
        self.ask_value = ask_value
        self.tool = "select"
        self.selection: Set[int] = set()
        self.points: List[Point] = []
        self.cursor: Point = (0.0, 0.0)
        self.snap_kind = ""
        self.preview: List[Shape] = []
        self.box: Optional[Tuple[Point, Point]] = None
        self.message = ""
        self.values = dict(VALUE_TOOLS)
        self.tol = 0.5 * MM  # pick distance; the window sets it from the zoom level
        self.grid = 1.0 * MM
        self.placing: List[Shape] = []  # shapes being placed with the mouse, centred on (0, 0)
        self._drag = None  # (kind, base shapes, start point, payload)
        self._chain_from: Optional[Tuple[int, int]] = None

    # -- helpers --------------------------------------------------------------
    def hint(self) -> str:
        if self.placing:
            return "Click where the shape should go."
        return next(h for n, _, h in TOOLS if n == self.tool)

    def set_tool(self, name: str) -> None:
        self.cancel()
        self.tool = name
        self.message = ""

    def cancel(self) -> None:
        if self._drag and self._drag[0] != "box":  # a box drag takes no checkpoint
            self.sketch.discard_checkpoint()
        self._drag = None
        self.points, self.preview, self.box, self.placing = [], [], None, []
        self._chain_from = None

    def escape(self) -> None:
        if self.points or self.placing or self._drag:
            self.cancel()
        elif self.tool != "select":
            self.set_tool("select")
        else:
            self.selection.clear()

    def _snap(self, p: Point, shift: bool = False, skip: Sequence[int] = ()) -> Point:
        q, self.snap_kind = self.sketch.snap(p, self.tol, self.grid, skip)
        if shift and self.points:
            a = self.points[-1]
            q = (q[0], a[1]) if abs(q[0] - a[0]) >= abs(q[1] - a[1]) else (a[0], q[1])
            self.snap_kind = "horizontal" if q[1] == a[1] else "vertical"
        return q

    def _commit(self, shapes: Sequence[Shape]) -> List[int]:
        self.sketch.checkpoint()
        new = self.sketch.add(shapes)
        if not new:
            self.sketch.discard_checkpoint()
        return new

    def place(self, shapes: Sequence[Shape]) -> None:
        """Start placing ready-made shapes (given centred on the origin) with the mouse."""
        self.cancel()
        self.tool = "select"
        self.placing = list(shapes)
        self.preview = [s.moved(*self.cursor) for s in self.placing]

    def select_all(self) -> None:
        self.selection = set(range(len(self.sketch.shapes)))

    def delete_selection(self) -> None:
        if self.selection:
            self.sketch.checkpoint()
            self.sketch.delete(self.selection)
            self.selection.clear()

    def undo(self) -> None:
        self.cancel()
        self.selection.clear()
        self.sketch.undo()

    def redo(self) -> None:
        self.cancel()
        self.selection.clear()
        self.sketch.redo()

    # -- shapes being drawn ---------------------------------------------------
    def _draft(self, p: Point) -> List[Shape]:
        pts = self.points
        if not pts:
            return []
        if self.tool == "line":
            return [Line(pts[0], p)]
        if self.tool == "circle":
            return [Arc.circle(pts[0], dist(pts[0], p))] if dist(pts[0], p) > TOL else []
        if self.tool == "rect":
            (x0, y0), (x1, y1) = pts[0], p
            if abs(x1 - x0) <= TOL or abs(y1 - y0) <= TOL:
                return []
            c = [(x0, y0), (x1, y0), (x1, y1), (x0, y1)]
            return [Line(a, b) for a, b in zip(c, c[1:] + c[:1])]
        if self.tool == "arc":
            if len(pts) == 1:
                return [Line(pts[0], p)]
            return [Arc.from_3pt(pts[0], p, pts[1])]
        if self.tool == "tangent" and self._chain_from is not None:
            i, end = self._chain_from
            arc = tangent_arc(self.sketch.shapes[i], end, p)
            return [arc] if arc is not None else []
        if self.tool == "mirror":
            return [Line(pts[0], p)]
        return []

    def _finish_draft(self, p: Point) -> None:
        """A click (or typed value) at ``p`` that completes the current shape."""
        new = self._commit(self._draft(p))
        if self.tool == "line" and new:
            closes = len(self.sketch.joined(p)) > 1
            self.points = [] if closes else [p]
        elif self.tool == "tangent" and new:
            self._chain_from = (new[-1], 1)
            self.points = [p]
        else:
            self.points = []
            self._chain_from = None
        self.preview = []

    # -- mouse ----------------------------------------------------------------
    def move(self, raw: Point, shift: bool = False) -> None:
        if self._drag:
            kind, base, start, payload = self._drag
            if kind == "end":
                to = self._snap(raw, skip=[i for i, _ in payload])
                self.sketch.shapes = Sketch.dragged_from(base, start, to)
            elif kind == "move":
                to = self._snap(raw, skip=sorted(payload))
                anchor = start[1]
                self.sketch.shapes = Sketch.moved_from(base, payload, to[0] - anchor[0], to[1] - anchor[1])
            else:
                self.box = (start, raw)
            self.cursor = raw
            return
        self.cursor = self._snap(raw, shift)
        if self.placing:
            self.preview = [s.moved(*self.cursor) for s in self.placing]
        else:
            self.preview = self._draft(self.cursor)

    def press(self, raw: Point, shift: bool = False) -> None:
        """Mouse button down."""
        self.message = ""
        if self.placing:
            p = self._snap(raw)
            new = self._commit([s.moved(*p) for s in self.placing])
            self.placing, self.preview = [], []
            self.selection = set(new)
            return
        handler = getattr(self, "_press_" + self.tool)
        handler(raw, shift)

    def release(self, raw: Point, shift: bool = False) -> None:
        if not self._drag:
            return
        kind, base, start, payload = self._drag
        self._drag = None
        if kind == "box":
            hit = self.sketch.in_box(start, raw) if dist(start, raw) > self.tol else []
            self.selection = (self.selection | set(hit)) if shift else set(hit)
            self.box = None
        elif self.sketch.shapes == list(base):
            self.sketch.discard_checkpoint()  # a click without movement is not an undo step

    def _press_select(self, raw: Point, shift: bool) -> None:
        sk = self.sketch
        hit_end = sk.pick_end(raw, self.tol)
        hit = sk.pick(raw, self.tol)
        if hit_end is not None and not shift:
            at = end_of(sk.shapes[hit_end[0]], hit_end[1])
            self.selection = {i for i, _ in sk.joined(at)}
            sk.checkpoint()
            self._drag = ("end", list(sk.shapes), at, sk.joined(at))
        elif hit is not None:
            if shift:
                self.selection ^= {hit}
                return
            if hit not in self.selection:
                self.selection = {hit}
            sk.checkpoint()
            anchor = self._snap(raw)
            self._drag = ("move", list(sk.shapes), (raw, anchor), set(self.selection))
        else:
            if not shift:
                self.selection.clear()
            self._drag = ("box", sk.shapes, raw, None)

    def _click_points(self, raw: Point, shift: bool, needed: int) -> Optional[Point]:
        p = self._snap(raw, shift)
        if len(self.points) + 1 < needed:
            self.points.append(p)
            return None
        return p

    def _press_line(self, raw: Point, shift: bool) -> None:
        p = self._click_points(raw, shift, 2)
        if p is not None:
            self._finish_draft(p)

    _press_circle = _press_line
    _press_rect = _press_line

    def _press_arc(self, raw: Point, shift: bool) -> None:
        p = self._click_points(raw, shift, 3)
        if p is not None:
            self._finish_draft(p)

    def _press_tangent(self, raw: Point, shift: bool) -> None:
        if self._chain_from is None:
            hit = self.sketch.pick_end(raw, self.tol)
            if hit is None:
                self.message = "Click the end of an existing edge first."
                return
            self._chain_from = hit
            self.points = [end_of(self.sketch.shapes[hit[0]], hit[1])]
            return
        self._finish_draft(self._snap(raw))

    def _edit(self, done: bool, failed: str) -> None:
        if done:
            self.selection.clear()
        else:
            self.sketch.discard_checkpoint()
            self.message = failed

    def _press_trim(self, raw: Point, shift: bool) -> None:
        self.sketch.checkpoint()
        self._edit(self.sketch.trim_at(raw, self.tol), "Click on an edge to trim it.")

    def _press_extend(self, raw: Point, shift: bool) -> None:
        self.sketch.checkpoint()
        self._edit(self.sketch.extend_at(raw, self.tol), "There is no edge to extend to in that direction.")

    def _press_fillet(self, raw: Point, shift: bool) -> None:
        self.sketch.checkpoint()
        done = self.sketch.fillet_at(raw, self.values["fillet"] * MM, self.tol)
        self._edit(done, "Click a corner where two straight lines meet, long enough for the radius.")

    def _press_chamfer(self, raw: Point, shift: bool) -> None:
        self.sketch.checkpoint()
        done = self.sketch.chamfer_at(raw, self.values["chamfer"] * MM, self.tol)
        self._edit(done, "Click a corner where two straight lines meet, long enough for the size.")

    def _press_offset(self, raw: Point, shift: bool) -> None:
        if not self.selection:
            hit = self.sketch.pick(raw, self.tol)
            if hit is None:
                self.message = "Select the edges to offset first."
            else:
                self.selection = {hit}
                self.message = "Now click on the side to copy to."
            return
        self.sketch.checkpoint()
        new = self.sketch.offset(sorted(self.selection), self.values["offset"] * MM, raw)
        if new:
            self.selection = set(new)
        else:
            self.sketch.discard_checkpoint()
            self.message = "Nothing could be offset by that distance."

    def _press_mirror(self, raw: Point, shift: bool) -> None:
        if not self.selection:
            self.message = "Select the edges to mirror first (Select tool)."
            return
        p = self._click_points(raw, shift, 2)
        if p is None:
            return
        self.sketch.checkpoint()
        new = self.sketch.mirror(sorted(self.selection), self.points[0], p)
        self.points, self.preview = [], []
        if new:
            self.selection = set(new)
        else:
            self.sketch.discard_checkpoint()

    def _press_dimension(self, raw: Point, shift: bool) -> None:
        i = self.sketch.pick(raw, self.tol)
        if i is None or self.ask_value is None:
            return
        s = self.sketch.shapes[i]
        is_line = isinstance(s, Line)
        value = self.ask_value("Length (mm)" if is_line else "Radius (mm)", (s.length if is_line else s.r) / MM)
        if value is None:
            return
        self.sketch.checkpoint()
        done = self.sketch.set_length(i, value * MM) if is_line else self.sketch.set_radius(i, value * MM)
        if not done:
            self.sketch.discard_checkpoint()
            self.message = "That value does not fit this edge."
        self.selection = {i} if done else set()

    # -- typed values -----------------------------------------------------------
    def enter(self, text: str) -> bool:
        """A value typed in the box. Returns False if it made no sense here."""
        parsed = parse_numbers(text)
        if parsed is None:
            self.message = "Type a number, length<angle, or two numbers separated by a comma."
            return False
        sep, v = parsed
        if self.tool in self.values and sep == "" and v[0] > 0:
            self.values[self.tool] = v[0]
            self.message = f"{self.tool.capitalize()} value: {v[0]:g} mm."
            return True
        if not self.points:
            self.message = "Click a first point, then type the size."
            return False
        a = self.points[-1] if self.tool == "line" else self.points[0]
        if self.tool == "line":
            if sep == ",":
                p = (a[0] + v[0] * MM, a[1] + v[1] * MM)
            else:
                if sep == "<":
                    ang = -math.radians(v[1])  # y points down on the board
                else:
                    ang = math.atan2(self.cursor[1] - a[1], self.cursor[0] - a[0])
                p = (a[0] + v[0] * MM * math.cos(ang), a[1] + v[0] * MM * math.sin(ang))
        elif self.tool == "circle" and sep == "":
            p = (a[0] + v[0] * MM, a[1])
        elif self.tool == "rect" and len(v) == 2:
            sx = -1 if self.cursor[0] < a[0] else 1
            sy = -1 if self.cursor[1] < a[1] else 1
            p = (a[0] + sx * v[0] * MM, a[1] + sy * v[1] * MM)
        else:
            self.message = "That value does not fit this tool."
            return False
        self._finish_draft(p)
        return True
