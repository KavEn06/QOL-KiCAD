"""Bridge between KiCad board items (via the IPC API) and the pure geometry."""

from __future__ import annotations

from collections import defaultdict
from typing import Dict, List, Optional, Sequence, Tuple

from kipy import KiCad
from kipy.board import Board
from kipy.board_types import BoardArc, BoardCircle, BoardLayer, BoardRectangle, BoardSegment, BoardShape
from kipy.geometry import Vector2

from .geom import Arc, Line, Point, Shape, dist

EDGE_WIDTH_NM = 50_000


def connect() -> Tuple[KiCad, Board]:
    kicad = KiCad()
    return kicad, kicad.get_board()


def _p(v: Vector2) -> Point:
    return (float(v.x), float(v.y))


def _v(p: Point) -> Vector2:
    return Vector2.from_xy(int(round(p[0])), int(round(p[1])))


def to_shapes(item: BoardShape) -> Optional[List[Shape]]:
    ref = item.id.value
    if isinstance(item, BoardSegment):
        return [Line(_p(item.start), _p(item.end), ref)]
    if isinstance(item, BoardArc):
        return [Arc.from_3pt(_p(item.start), _p(item.mid), _p(item.end), ref)]
    if isinstance(item, BoardCircle):
        c = _p(item.center)
        return [Arc.circle(c, dist(c, _p(item.radius_point)), ref)]
    if isinstance(item, BoardRectangle):
        (x0, y0), (x1, y1) = _p(item.top_left), _p(item.bottom_right)
        pts = [(x0, y0), (x1, y0), (x1, y1), (x0, y1)]
        return [Line(a, b, ref) for a, b in zip(pts, pts[1:] + pts[:1])]
    return None


def _set_geometry(item: BoardShape, s: Shape) -> None:
    if isinstance(s, Line):
        item.start, item.end = _v(s.a), _v(s.b)
    elif s.closed:
        item.center, item.radius_point = _v(s.c), _v((s.c[0] + s.r, s.c[1]))
    else:
        item.start, item.mid, item.end = _v(s.start), _v(s.mid), _v(s.end)


def _matches(item: BoardShape, s: Shape) -> bool:
    if isinstance(s, Line):
        return isinstance(item, BoardSegment)
    return isinstance(item, BoardCircle if s.closed else BoardArc)


def _new_item(s: Shape, width: int) -> BoardShape:
    item = BoardSegment() if isinstance(s, Line) else BoardCircle() if s.closed else BoardArc()
    item.layer = BoardLayer.BL_Edge_Cuts
    item.attributes.stroke.width = width
    _set_geometry(item, s)
    return item


class EdgeSet:
    """Edge.Cuts shapes read from the board, plus what is needed to write changes back."""

    def __init__(self, board: Board, items: Sequence[BoardShape]):
        self.board = board
        self.items: Dict[str, BoardShape] = {}
        self.shapes: List[Shape] = []
        self.unsupported = 0
        for item in items:
            if item.layer != BoardLayer.BL_Edge_Cuts:
                continue
            shapes = to_shapes(item)
            if shapes is None:
                self.unsupported += 1
                continue
            self.items[item.id.value] = item
            self.shapes.extend(shapes)

    @classmethod
    def all(cls, board: Board) -> "EdgeSet":
        return cls(board, board.get_shapes())

    @classmethod
    def selected(cls, board: Board) -> "EdgeSet":
        return cls(board, [i for i in board.get_selection() if isinstance(i, BoardShape)])

    @classmethod
    def selected_or_all(cls, board: Board) -> "EdgeSet":
        sel = cls.selected(board)
        return sel if sel.shapes else cls.all(board)

    def width(self) -> int:
        for item in self.items.values():
            return item.attributes.stroke.width or EDGE_WIDTH_NM
        for item in self.board.get_shapes():
            if item.layer == BoardLayer.BL_Edge_Cuts:
                return item.attributes.stroke.width or EDGE_WIDTH_NM
        return EDGE_WIDTH_NM

    def apply(self, after: Sequence[Shape], message: str) -> List[BoardShape]:
        """Write ``after`` back as one undo step. Returns the items that were created.

        Shapes keep their board item (and its ID) when they still carry its
        ``ref``; shapes without a ref are created; items whose ref vanished
        are removed.
        """
        before: Dict[str, List[Shape]] = defaultdict(list)
        for s in self.shapes:
            before[s.ref].append(s)
        wanted: Dict[Optional[str], List[Shape]] = defaultdict(list)
        for s in after:
            wanted[s.ref if s.ref in self.items else None].append(s)

        width = self.width()
        updates: List[BoardShape] = []
        removes: List[BoardShape] = []
        creates: List[BoardShape] = [_new_item(s, width) for s in wanted.pop(None, [])]
        for ref, item in self.items.items():
            outs = wanted.get(ref, [])
            if outs == before[ref]:
                continue
            if outs and _matches(item, outs[0]):
                _set_geometry(item, outs[0])
                updates.append(item)
                outs = outs[1:]
            else:
                removes.append(item)
            creates.extend(_new_item(s, width) for s in outs)

        if not (updates or removes or creates):
            return []
        commit = self.board.begin_commit()
        try:
            if removes:
                self.board.remove_items(removes)
            if updates:
                self.board.update_items(updates)
            created = list(self.board.create_items(creates)) if creates else []
        except Exception:
            self.board.drop_commit(commit)
            raise
        self.board.push_commit(commit, message)
        return created

