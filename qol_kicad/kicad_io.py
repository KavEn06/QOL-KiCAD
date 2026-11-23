"""Bridge between KiCad board items (via the IPC API) and the pure geometry."""

from __future__ import annotations

from collections import defaultdict
from typing import Dict, List, Optional, Sequence, Tuple

from kipy import KiCad
from kipy.board import Board
from kipy.board_types import BoardArc, BoardCircle, BoardLayer, BoardRectangle, BoardSegment, BoardShape, Group
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


def _new_item(s: Shape, width: int, layer: int = BoardLayer.BL_Edge_Cuts) -> BoardShape:
    item = BoardSegment() if isinstance(s, Line) else BoardCircle() if s.closed else BoardArc()
    item.layer = layer
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



SKETCH_PREFIX = "QOL sketch: "


def layer_name(layer: int) -> str:
    return BoardLayer.Name(layer)[3:].replace("_", ".")


def drawing_layers(board: Board) -> List[int]:
    """Enabled layers, Edge.Cuts first."""
    layers = [int(v) for v in board.get_enabled_layers()]
    edge = int(BoardLayer.BL_Edge_Cuts)
    return [edge] + [v for v in layers if v != edge]


class SketchTarget:
    """Where a sketch goes on the board: a new group, or an existing group being edited."""

    def __init__(self, board: Board, group: Optional[Group] = None):
        self.board = board
        self.group = group
        self.items: Dict[str, BoardShape] = {}
        self.kept: list = []  # group members the sketch cannot edit (text, footprints, ...)
        self.shapes: List[Shape] = []
        self.layer = int(BoardLayer.BL_Edge_Cuts)
        self.width = 0
        for member in board.get_items_by_id(list(group.proto.items)) if group is not None else []:
            shapes = to_shapes(member) if isinstance(member, BoardShape) else None
            if shapes is None:
                self.kept.append(member)
                continue
            if not self.items:
                self.layer = int(member.layer)
                self.width = member.attributes.stroke.width
            self.items[member.id.value] = member
            self.shapes.extend(shapes)
        if not self.width:
            self.width = EdgeSet(board, []).width()

    @classmethod
    def from_selection(cls, board: Board) -> "SketchTarget":
        """The selected group, if exactly one is selected; otherwise a new sketch."""
        groups = [i for i in board.get_selection() if isinstance(i, Group)]
        return cls(board, groups[0] if len(groups) == 1 else None)

    @property
    def name(self) -> str:
        name = self.group.name if self.group is not None else ""
        return name[len(SKETCH_PREFIX):] if name.startswith(SKETCH_PREFIX) else name

    def reference(self) -> List[Shape]:
        """Board outline shapes outside this sketch, shown greyed out and snapped to."""
        return [s for s in EdgeSet.all(self.board).shapes if s.ref not in self.items]

    def write(self, after: Sequence[Shape], layer: int, name: str) -> int:
        """Put ``after`` on the board as the group's shapes. Returns the number of undo steps.

        Board items are reused where possible, so editing a group that does
        not gain shapes is one undo step. KiCad only accepts group members
        that are already on the board (also within one commit), so new shapes
        are one step and adding them to the group is a second one.
        """
        by_ref: Dict[str, List[Shape]] = defaultdict(list)
        loose: List[Shape] = []
        for s in after:
            (by_ref[s.ref] if s.ref in self.items else loose).append(s)
        before: Dict[str, List[Shape]] = defaultdict(list)
        for s in self.shapes:
            before[s.ref].append(s)
        members: List[BoardShape] = []
        updates: List[BoardShape] = []
        spare: List[BoardShape] = []
        for ref, item in self.items.items():
            outs = by_ref.get(ref, [])
            if outs and _matches(item, outs[0]):
                members.append(item)
                if outs != before[ref] or int(item.layer) != layer:
                    _set_geometry(item, outs[0])
                    item.layer = layer
                    updates.append(item)
                outs = outs[1:]
            else:
                spare.append(item)
            loose.extend(outs)
        creates: List[Shape] = []
        for s in loose:  # reuse items of deleted shapes before creating new ones
            item = next((i for i in spare if _matches(i, s)), None)
            if item is None:
                creates.append(s)
                continue
            spare.remove(item)
            _set_geometry(item, s)
            item.layer = layer
            updates.append(item)
            members.append(item)

        full_name = SKETCH_PREFIX + (name.strip() or "outline")
        rename = self.group is not None and self.group.name != full_name
        if not (updates or spare or creates or rename):
            return 0
        board = self.board
        message = "QOL: Edit sketch" if self.group is not None else "QOL: Insert sketch"
        commit = board.begin_commit()
        try:
            if spare:
                board.remove_items(spare)
            if updates:
                board.update_items(updates)
            created = list(board.create_items([_new_item(s, self.width, layer) for s in creates])) if creates else []
        except Exception:
            board.drop_commit(commit)
            raise
        board.push_commit(commit, message)
        steps = 1
        result = self.group
        if created or rename or self.group is None:
            group = self.group if self.group is not None else Group()
            group.proto.name = full_name
            group.items = list(self.kept) + members + created
            commit = board.begin_commit()
            try:
                if self.group is None:
                    result = board.create_items([group])[0]
                else:
                    # Every member goes in the step with the group: KiCad's undo
                    # drops members from the group that the step did not record.
                    board.update_items(list(group.items) + [group])
            except Exception:
                board.drop_commit(commit)
                raise
            board.push_commit(commit, message + " (group)")
            steps = 2
        try:
            board.clear_selection()
            board.add_to_selection([g for g in board.get_groups() if g.id.value == result.id.value])
        except Exception:
            pass  # selecting the result is a convenience only
        return steps
