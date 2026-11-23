"""The sketch itself: a list of shapes plus the editing operations. No GUI code.

Coordinates are floats in nanometres, y down, the same as the board.
"""

from __future__ import annotations

import math
from typing import Iterable, List, Optional, Sequence, Tuple

from ..geom import TAU, Arc, Line, Point, Shape, dist, intersections, param_of, sample
from ..outline import fillet_all

TOL = 1000.0  # 1 um: ends closer than this are joined
FAR = 1e12  # 1 km: long enough to stand in for an infinite line


def reverse(s: Shape) -> Shape:
    if isinstance(s, Line):
        return Line(s.b, s.a, s.ref)
    return Arc(s.c, s.r, s.a0 + s.sweep, -s.sweep, s.ref)


def end_of(s: Shape, end: int) -> Point:
    return s.end if end else s.start


def with_end(s: Shape, end: int, p: Point) -> Shape:
    """Stretch ``s`` so one end sits at ``p`` (arcs keep their sweep angle)."""
    return s.with_ends(s.start, p) if end else s.with_ends(p, s.end)


def carrier(s: Shape) -> Shape:
    """The infinite line or full circle a shape lies on."""
    if isinstance(s, Line):
        length = s.length or 1.0
        ux, uy = (s.b[0] - s.a[0]) / length, (s.b[1] - s.a[1]) / length
        return Line((s.a[0] - ux * FAR, s.a[1] - uy * FAR), (s.b[0] + ux * FAR, s.b[1] + uy * FAR))
    return Arc.circle(s.c, s.r)


def on_carrier(s: Shape, end: int, p: Point) -> Shape:
    """Move one end to ``p`` along the shape's own line or circle."""
    if isinstance(s, Line):
        return with_end(s, end, p)
    ang = math.atan2(p[1] - s.c[1], p[0] - s.c[0])
    if end:
        sweep = (ang - s.a0) % TAU if s.sweep > 0 else -((s.a0 - ang) % TAU)
        return Arc(s.c, s.r, s.a0, sweep or s.sweep, s.ref)
    a1 = s.a0 + s.sweep
    sweep = (a1 - ang) % TAU if s.sweep > 0 else -((ang - a1) % TAU)
    return Arc(s.c, s.r, ang, sweep or s.sweep, s.ref)


def nearest_on(s: Shape, p: Point) -> Point:
    if isinstance(s, Line):
        dx, dy = s.b[0] - s.a[0], s.b[1] - s.a[1]
        l2 = dx * dx + dy * dy
        t = 0.0 if l2 == 0 else max(0.0, min(1.0, ((p[0] - s.a[0]) * dx + (p[1] - s.a[1]) * dy) / l2))
        return s.point_at(t)
    d = dist(s.c, p)
    if d == 0:
        return s.start
    q = (s.c[0] + (p[0] - s.c[0]) * s.r / d, s.c[1] + (p[1] - s.c[1]) * s.r / d)
    if s.closed or param_of(s, q, TOL) is not None:
        return q
    return min((s.start, s.end), key=lambda e: dist(e, p))


def mirror_shape(s: Shape, a: Point, b: Point) -> Shape:
    dx, dy = b[0] - a[0], b[1] - a[1]
    l2 = dx * dx + dy * dy

    def m(p: Point) -> Point:
        t = ((p[0] - a[0]) * dx + (p[1] - a[1]) * dy) / l2
        fx, fy = a[0] + dx * t, a[1] + dy * t
        return (2 * fx - p[0], 2 * fy - p[1])

    if isinstance(s, Line):
        return Line(m(s.a), m(s.b))
    if s.closed:
        return Arc.circle(m(s.c), s.r)
    return Arc.from_3pt(m(s.start), m(s.mid), m(s.end))


def tangent_arc(prev: Shape, end: int, to: Point) -> Optional[Shape]:
    """Arc leaving ``prev`` at one of its ends, tangent to it, and ending at ``to``."""
    start = end_of(prev, end)
    if isinstance(prev, Line):
        other = end_of(prev, 1 - end)
        tx, ty = start[0] - other[0], start[1] - other[1]
    else:
        ang = prev.a0 + prev.sweep * end
        sign = (1 if prev.sweep > 0 else -1) * (1 if end else -1)
        tx, ty = -math.sin(ang) * sign, math.cos(ang) * sign
    tl = math.hypot(tx, ty)
    ex, ey = to[0] - start[0], to[1] - start[1]
    if tl == 0 or (ex == 0 and ey == 0):
        return None
    tx, ty = tx / tl, ty / tl
    nx, ny = -ty, tx
    den = 2 * (nx * ex + ny * ey)
    if abs(den) < 1e-9 * math.hypot(ex, ey):
        return Line(start, to)
    k = (ex * ex + ey * ey) / den
    c = (start[0] + nx * k, start[1] + ny * k)
    a0 = math.atan2(start[1] - c[1], start[0] - c[0])
    a1 = math.atan2(to[1] - c[1], to[0] - c[0])
    # travelling along the tangent turns towards the centre
    sweep = (a1 - a0) % TAU if k > 0 else -((a0 - a1) % TAU)
    return Arc(c, abs(k), a0, sweep)


class Sketch:
    def __init__(self, shapes: Iterable[Shape] = (), reference: Iterable[Shape] = ()):
        self.shapes: List[Shape] = list(shapes)
        self.reference: List[Shape] = list(reference)  # shown and snapped to, never edited
        self._undo: List[List[Shape]] = []
        self._redo: List[List[Shape]] = []

    # -- undo ---------------------------------------------------------------
    def checkpoint(self) -> None:
        """Call before a change; the state at this moment becomes one undo step."""
        self._undo.append(list(self.shapes))
        self._redo.clear()

    def discard_checkpoint(self) -> None:
        if self._undo:
            self.shapes = self._undo.pop()

    def undo(self) -> bool:
        if not self._undo:
            return False
        self._redo.append(self.shapes)
        self.shapes = self._undo.pop()
        return True

    def redo(self) -> bool:
        if not self._redo:
            return False
        self._undo.append(self.shapes)
        self.shapes = self._redo.pop()
        return True

    # -- queries ------------------------------------------------------------
    def pick(self, p: Point, tol: float) -> Optional[int]:
        best, best_d = None, tol
        for i, s in enumerate(self.shapes):
            d = dist(nearest_on(s, p), p)
            if d <= best_d:
                best, best_d = i, d
        return best

    def pick_end(self, p: Point, tol: float) -> Optional[Tuple[int, int]]:
        best, best_d = None, tol
        for i, s in enumerate(self.shapes):
            if s.closed:
                continue
            for end in (0, 1):
                d = dist(end_of(s, end), p)
                if d <= best_d:
                    best, best_d = (i, end), d
        return best

    def joined(self, p: Point, tol: float = TOL) -> List[Tuple[int, int]]:
        return [
            (i, end)
            for i, s in enumerate(self.shapes)
            if not s.closed
            for end in (0, 1)
            if dist(end_of(s, end), p) <= tol
        ]

    def in_box(self, a: Point, b: Point) -> List[int]:
        x0, x1 = sorted((a[0], b[0]))
        y0, y1 = sorted((a[1], b[1]))
        return [
            i
            for i, s in enumerate(self.shapes)
            if all(x0 <= x <= x1 and y0 <= y <= y1 for x, y in sample(s))
        ]

    def snap(self, p: Point, tol: float, grid: float = 0.0, skip: Sequence[int] = ()) -> Tuple[Point, str]:
        """Best point near ``p``: end, centre, middle, crossing, on a shape, then grid."""
        skipped = set(skip)
        mine = [s for i, s in enumerate(self.shapes) if i not in skipped]
        everything = mine + self.reference
        near = [
            s
            for s in everything
            if dist(nearest_on(s, p), p) <= tol or (isinstance(s, Arc) and dist(s.c, p) <= tol)
        ]
        cands: List[Tuple[int, float, Point, str]] = []

        def add(rank: int, q: Point, kind: str) -> None:
            d = dist(p, q)
            if d <= tol:
                cands.append((rank, d, q, kind))

        for s in near:
            if not s.closed:
                add(0, s.start, "end")
                add(0, s.end, "end")
                add(2, s.mid, "middle")
            if isinstance(s, Arc):
                add(1, s.c, "centre")
        for i, s1 in enumerate(near):
            for s2 in near[i + 1 :]:
                for q in intersections(s1, s2, TOL):
                    add(1, q, "crossing")
        if cands:
            _, _, q, kind = min(cands, key=lambda c: (c[0], c[1]))
            return q, kind
        on = [q for q in (nearest_on(s, p) for s in near) if dist(p, q) <= tol]
        if on:
            return min(on, key=lambda q: dist(p, q)), "on edge"
        if grid > 0:
            return (round(p[0] / grid) * grid, round(p[1] / grid) * grid), "grid"
        return p, ""

    # -- basic edits (callers take the checkpoint) ----------------------------
    def add(self, shapes: Iterable[Shape]) -> List[int]:
        start = len(self.shapes)
        self.shapes.extend(s for s in shapes if s.closed or s.length > TOL)
        return list(range(start, len(self.shapes)))

    def delete(self, indices: Iterable[int]) -> None:
        drop = set(indices)
        self.shapes = [s for i, s in enumerate(self.shapes) if i not in drop]

    @staticmethod
    def moved_from(base: Sequence[Shape], indices: Iterable[int], dx: float, dy: float) -> List[Shape]:
        """``base`` with some shapes moved; ends of other shapes joined to them follow."""
        sel = set(indices)
        out = list(base)
        moved_ends = [end_of(base[i], e) for i in sel if not base[i].closed for e in (0, 1)]
        for i in sel:
            out[i] = base[i].moved(dx, dy)
        for i, s in enumerate(base):
            if i in sel or s.closed:
                continue
            for end in (0, 1):
                p = end_of(out[i], end)
                if any(dist(p, q) <= TOL for q in moved_ends):
                    out[i] = with_end(out[i], end, (p[0] + dx, p[1] + dy))
        return out

    @staticmethod
    def dragged_from(base: Sequence[Shape], at: Point, to: Point) -> List[Shape]:
        """``base`` with every shape end at ``at`` moved to ``to``."""
        out = list(base)
        for i, s in enumerate(base):
            if s.closed:
                continue
            for end in (0, 1):
                if dist(end_of(s, end), at) <= TOL:
                    out[i] = with_end(out[i], end, to)
        return out

    # -- tools ----------------------------------------------------------------
    def _cut_params(self, i: int) -> List[float]:
        s = self.shapes[i]
        ts: List[float] = []
        for j, o in enumerate(self.shapes):
            if j == i:
                continue
            for q in intersections(s, o, TOL):
                u = param_of(s, q, TOL)
                if u is not None:
                    ts.append(u)
        return sorted(ts)

    def trim_at(self, p: Point, tol: float) -> bool:
        """Remove the piece under ``p``, up to the nearest crossings on each side."""
        i = self.pick(p, tol)
        if i is None:
            return False
        s = self.shapes[i]
        u = param_of(s, nearest_on(s, p), TOL)
        if u is None:
            return False
        eps = TOL / max(s.length, 1.0)
        cuts = [t for t in self._cut_params(i)]
        if s.closed:
            cuts = sorted({round(t % 1.0, 12) for t in cuts})
            if len(cuts) < 2:
                self.delete([i])
                return True
            after = next((t for t in cuts if t > u), cuts[0] + 1.0)
            before = max((t for t in cuts if t <= u), default=cuts[-1] - 1.0)
            keep = Arc(s.c, s.r, s.a0 + s.sweep * after, s.sweep * (1.0 - (after - before)))
            self.shapes[i] = keep
            return True
        before = max((t for t in cuts if t < u - eps), default=None)
        after = min((t for t in cuts if t > u + eps), default=None)
        pieces: List[Shape] = []
        if before is not None and before > eps:
            pieces.append(s.sub(0.0, before))
        if after is not None and after < 1 - eps:
            pieces.append(s.sub(after, 1.0))
        self.shapes[i : i + 1] = pieces
        return True

    def extend_at(self, p: Point, tol: float) -> bool:
        """Lengthen the end nearest ``p`` to the next shape it would hit."""
        i = self.pick(p, tol)
        if i is None or self.shapes[i].closed:
            return False
        s = self.shapes[i]
        end = 1 if dist(p, s.end) <= dist(p, s.start) else 0
        tip = end_of(s, end)
        full = carrier(s)
        best, best_d = None, None
        for j, o in enumerate(self.shapes):
            if j == i:
                continue
            for q in intersections(full, o, TOL):
                if param_of(s, q, TOL) is not None:
                    continue  # already on the shape
                if isinstance(s, Line):
                    other = end_of(s, 1 - end)
                    if (q[0] - tip[0]) * (tip[0] - other[0]) + (q[1] - tip[1]) * (tip[1] - other[1]) <= 0:
                        continue  # behind this end
                    d = dist(q, tip)
                else:
                    d = abs(on_carrier(s, end, q).sweep)
                if best_d is None or d < best_d:
                    best, best_d = q, d
        if best is None:
            return False
        self.shapes[i] = on_carrier(s, end, best)
        return True

    def _corner(self, p: Point, tol: float) -> Optional[Tuple[int, int]]:
        hit = self.pick_end(p, tol)
        if hit is None:
            return None
        at = end_of(self.shapes[hit[0]], hit[1])
        idx = sorted({i for i, _ in self.joined(at)})
        if len(idx) != 2 or not all(isinstance(self.shapes[i], Line) for i in idx):
            return None
        return idx[0], idx[1]

    def fillet_at(self, p: Point, radius: float, tol: float) -> bool:
        """Round the corner nearest ``p`` where two straight lines meet."""
        pair = self._corner(p, tol)
        if pair is None or radius <= 0:
            return False
        out, done, _ = fillet_all([self.shapes[pair[0]], self.shapes[pair[1]]], radius, TOL)
        if not done:
            return False
        self.delete(pair)
        self.shapes.extend(out)
        return True

    def chamfer_at(self, p: Point, size: float, tol: float) -> bool:
        """Cut the corner nearest ``p`` with a straight line ``size`` back from it."""
        pair = self._corner(p, tol)
        if pair is None or size <= 0:
            return False
        hit = self.pick_end(p, tol)
        at = end_of(self.shapes[hit[0]], hit[1])
        new, tips = [], []
        for i in pair:
            s = self.shapes[i]
            if s.length <= size + TOL:
                return False
            end = 0 if dist(s.start, at) <= TOL else 1
            far = end_of(s, 1 - end)
            t = size / s.length
            tip = (at[0] + (far[0] - at[0]) * t, at[1] + (far[1] - at[1]) * t)
            new.append(with_end(s, end, tip))
            tips.append(tip)
        self.delete(pair)
        self.shapes.extend(new + [Line(tips[0], tips[1])])
        return True

    def _chain(self, indices: Sequence[int]) -> List[Shape]:
        """Selected open shapes ordered and turned so each one starts where the last ended."""
        left = [self.shapes[i] for i in indices if not self.shapes[i].closed]
        if not left:
            return []
        chain = [left.pop(0)]
        grew = True
        while left and grew:
            grew = False
            for k, s in enumerate(left):
                for cand in (s, reverse(s)):
                    if dist(cand.start, chain[-1].end) <= TOL:
                        chain.append(cand)
                    elif dist(cand.end, chain[0].start) <= TOL:
                        chain.insert(0, cand)
                    else:
                        continue
                    left.pop(k)
                    grew = True
                    break
                if grew:
                    break
        return chain

    def offset(self, indices: Sequence[int], distance: float, side: Point) -> List[int]:
        """Copy the selected shapes ``distance`` away, on the side where ``side`` is."""
        if distance <= 0:
            return []
        created: List[Shape] = []
        for i in indices:
            s = self.shapes[i]
            if s.closed:
                r = s.r + distance if dist(side, s.c) > s.r else s.r - distance
                if r > TOL:
                    created.append(Arc.circle(s.c, r))
        chain = self._chain(indices)
        if chain:
            near = min(chain, key=lambda s: dist(nearest_on(s, side), side))
            q = nearest_on(near, side)
            sign = 1.0 if _left_of(near, q, side) else -1.0
            moved: List[Shape] = []
            for s in chain:
                o = _offset_left(s, distance * sign)
                if o is not None:
                    moved.append(o)
            closed = len(chain) > 1 and dist(chain[0].start, chain[-1].end) <= TOL
            pairs = list(zip(range(len(moved) - 1), range(1, len(moved))))
            if closed and len(moved) == len(chain):
                pairs.append((len(moved) - 1, 0))
            for a, b in pairs:
                target = moved[a].end
                hits = intersections(carrier(moved[a]), carrier(moved[b]), TOL)
                if hits:
                    q = min(hits, key=lambda h: dist(h, target))
                    moved[a] = on_carrier(moved[a], 1, q)
                    moved[b] = on_carrier(moved[b], 0, q)
            created.extend(moved)
        return self.add(created)

    def mirror(self, indices: Sequence[int], a: Point, b: Point, copy: bool = True) -> List[int]:
        if dist(a, b) <= TOL:
            return []
        new = [mirror_shape(self.shapes[i], a, b) for i in indices]
        if not copy:
            self.delete(indices)
        return self.add(new)

    def set_length(self, i: int, length: float) -> bool:
        """Set a line's length keeping its start and direction; joined ends follow."""
        s = self.shapes[i]
        if not isinstance(s, Line) or length <= TOL or s.length == 0:
            return False
        k = length / s.length
        to = (s.a[0] + (s.b[0] - s.a[0]) * k, s.a[1] + (s.b[1] - s.a[1]) * k)
        self.shapes = self.dragged_from(self.shapes, s.b, to)
        return True

    def set_radius(self, i: int, radius: float) -> bool:
        """Set a circle's or arc's radius. An arc keeps its ends and changes its bulge."""
        s = self.shapes[i]
        if not isinstance(s, Arc) or radius <= TOL:
            return False
        if s.closed:
            self.shapes[i] = Arc.circle(s.c, radius)
            return True
        chord = dist(s.start, s.end)
        if radius < chord / 2:
            return False
        half = math.asin(min(1.0, chord / (2 * radius)))
        sweep = 2 * half if abs(s.sweep) <= math.pi else TAU - 2 * half
        bent = Arc(s.c, s.r, s.a0, math.copysign(sweep, s.sweep)).with_ends(s.start, s.end)
        self.shapes[i] = bent
        return True


def _left_of(s: Shape, q: Point, p: Point) -> bool:
    """Is ``p`` on the left of ``s`` (looking from start to end) near its point ``q``?"""
    if isinstance(s, Line):
        return (s.b[0] - s.a[0]) * (p[1] - s.a[1]) - (s.b[1] - s.a[1]) * (p[0] - s.a[0]) > 0
    inside = dist(p, s.c) < s.r
    return inside if s.sweep > 0 else not inside


def _offset_left(s: Shape, d: float) -> Optional[Shape]:
    if isinstance(s, Line):
        length = s.length
        if length == 0:
            return None
        nx, ny = -(s.b[1] - s.a[1]) / length, (s.b[0] - s.a[0]) / length
        return Line((s.a[0] + nx * d, s.a[1] + ny * d), (s.b[0] + nx * d, s.b[1] + ny * d))
    r = s.r - d if s.sweep > 0 else s.r + d
    return Arc(s.c, r, s.a0, s.sweep) if r > TOL else None
