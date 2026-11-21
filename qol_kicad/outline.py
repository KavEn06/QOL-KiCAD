"""Outline operations on lists of shapes: clean, trim, fillet, arc refit, tab."""

from __future__ import annotations

import math
from collections import defaultdict
from dataclasses import dataclass, field
from typing import Dict, List, Optional, Sequence, Tuple

from .geom import TAU, Arc, Line, Point, Shape, dist, fit_circle, intersections, param_of, point_in_polygon, sample


class Nodes:
    """Clusters points that lie within ``tol`` of each other into numbered nodes."""

    def __init__(self, tol: float):
        self.tol = max(tol, 1e-6)
        self.points: List[Point] = []
        self._parent: List[int] = []
        self._grid: Dict[Tuple[int, int], List[int]] = defaultdict(list)

    def _find(self, i: int) -> int:
        while self._parent[i] != i:
            self._parent[i] = self._parent[self._parent[i]]
            i = self._parent[i]
        return i

    def add(self, p: Point) -> int:
        idx = len(self.points)
        self.points.append(p)
        self._parent.append(idx)
        cx, cy = int(math.floor(p[0] / self.tol)), int(math.floor(p[1] / self.tol))
        for gx in (cx - 1, cx, cx + 1):
            for gy in (cy - 1, cy, cy + 1):
                for j in self._grid.get((gx, gy), ()):
                    if dist(self.points[j], p) <= self.tol:
                        self._parent[self._find(j)] = self._find(idx)
        self._grid[(cx, cy)].append(idx)
        return idx

    def node(self, idx: int) -> int:
        return self._find(idx)

    def centroids(self) -> Dict[int, Point]:
        groups: Dict[int, List[Point]] = defaultdict(list)
        for i, p in enumerate(self.points):
            groups[self._find(i)].append(p)
        return {k: (sum(p[0] for p in v) / len(v), sum(p[1] for p in v) / len(v)) for k, v in groups.items()}


def build_graph(shapes: Sequence[Shape], tol: float):
    """Returns (ends, incident, positions).

    ``ends[i]`` is the (start node, end node) of open shape i, or None for circles.
    ``incident[node]`` lists (shape index, 0 for start / 1 for end).
    """
    nodes = Nodes(tol)
    raw: List[Optional[Tuple[int, int]]] = []
    for s in shapes:
        raw.append(None if s.closed else (nodes.add(s.start), nodes.add(s.end)))
    ends = [None if r is None else (nodes.node(r[0]), nodes.node(r[1])) for r in raw]
    incident: Dict[int, List[Tuple[int, int]]] = defaultdict(list)
    for i, e in enumerate(ends):
        if e is not None:
            incident[e[0]].append((i, 0))
            incident[e[1]].append((i, 1))
    return ends, incident, nodes.centroids()


@dataclass
class CleanReport:
    joined: int = 0
    removed: int = 0
    merged: int = 0
    open_ends: List[Point] = field(default_factory=list)
    branches: List[Point] = field(default_factory=list)

    @property
    def is_closed(self) -> bool:
        return not self.open_ends and not self.branches


def _try_merge(s1: Shape, end1: int, s2: Shape, end2: int, tol: float) -> Optional[Shape]:
    """Merge two shapes meeting at s1's ``end1`` and s2's ``end2`` if they continue each other."""
    p_far1 = s1.start if end1 == 1 else s1.end
    p_far2 = s2.start if end2 == 1 else s2.end
    p_join = s1.end if end1 == 1 else s1.start
    if isinstance(s1, Line) and isinstance(s2, Line):
        span = Line(p_far1, p_far2)
        if span.length < max(s1.length, s2.length):
            return None  # folds back on itself
        t = param_of(span, p_join, tol)
        if t is None:
            return None
        return Line(p_far1, p_far2, s1.ref) if end1 == 1 else Line(p_far2, p_far1, s1.ref)
    if isinstance(s1, Arc) and isinstance(s2, Arc):
        if dist(s1.c, s2.c) > tol or abs(s1.r - s2.r) > tol:
            return None
        # orient both so the result runs far1 -> join -> far2
        sw1 = s1.sweep if end1 == 1 else -s1.sweep
        sw2 = s2.sweep if end2 == 0 else -s2.sweep
        if (sw1 > 0) != (sw2 > 0):
            return None
        total = sw1 + sw2
        a0 = math.atan2(p_far1[1] - s1.c[1], p_far1[0] - s1.c[0])
        if abs(total) >= TAU - tol / s1.r:
            return Arc.circle(s1.c, s1.r, s1.ref)
        return Arc(s1.c, s1.r, a0, total, s1.ref)
    return None


def merge_continuations(shapes: Sequence[Shape], tol: float) -> Tuple[List[Shape], int]:
    """Merge collinear lines and co-circular arcs that meet at a 2-way joint."""
    shapes = list(shapes)
    merged = 0
    changed = True
    while changed:
        changed = False
        ends, incident, _ = build_graph(shapes, tol)
        dead = set()
        for node, inc in incident.items():
            if len(inc) != 2:
                continue
            (i, ei), (j, ej) = inc
            if i == j or i in dead or j in dead:
                continue
            m = _try_merge(shapes[i], ei, shapes[j], ej, tol)
            if m is None:
                continue
            shapes[i] = m
            dead.add(j)
            dead.add(i)  # its ends changed; revisit next pass
            shapes[j] = None  # type: ignore[call-overload]
            merged += 1
            changed = True
        shapes = [s for s in shapes if s is not None]
    return shapes, merged


def clean(shapes: Sequence[Shape], tol: float) -> Tuple[List[Shape], CleanReport]:
    """Join nearly-touching ends, drop duplicates and zero-length shapes, merge continuations."""
    rep = CleanReport()
    live = [s for s in shapes if s.closed or s.length > tol]
    rep.removed += len(shapes) - len(live)

    ends, _, pos = build_graph(live, tol)
    snapped: List[Shape] = []
    for s, e in zip(live, ends):
        if e is None:
            snapped.append(s)
            continue
        if e[0] == e[1]:
            if isinstance(s, Arc) and s.length > 4 * tol:
                snapped.append(Arc.circle(s.c, s.r, s.ref))  # arc whose ends meet: a circle
            else:
                rep.removed += 1
            continue
        a, b = pos[e[0]], pos[e[1]]
        if dist(a, s.start) > 0.5 or dist(b, s.end) > 0.5:
            rep.joined += 1
            s = s.with_ends(a, b)
        snapped.append(s)

    seen = set()
    unique: List[Shape] = []
    q = max(tol, 1.0)
    for s in snapped:
        if s.closed:
            key = ("c", round(s.c[0] / q), round(s.c[1] / q), round(s.r / q))
        else:
            ends_key = tuple(sorted((round(p[0] / q), round(p[1] / q)) for p in (s.start, s.end)))
            key = (ends_key, round(s.mid[0] / q), round(s.mid[1] / q))
        if key in seen:
            rep.removed += 1
            continue
        seen.add(key)
        unique.append(s)

    out, rep.merged = merge_continuations(unique, tol)

    _, incident, pos = build_graph(out, tol)
    for node, inc in incident.items():
        if len(inc) == 1:
            rep.open_ends.append(pos[node])
        elif len(inc) > 2:
            rep.branches.append(pos[node])
    return out, rep


def trim(targets: Sequence[Shape], others: Sequence[Shape], tol: float = 1000.0) -> Tuple[List[Shape], int, int]:
    """Cut each target where other shapes cross it and drop the overhanging end pieces.

    An end piece overhangs when its outer end touches nothing. Returns
    (new target shapes, pieces removed, targets split without removal).
    """
    everything = list(targets) + list(others)
    out: List[Shape] = []
    removed = split = 0
    for t in targets:
        if t.closed:
            out.append(t)
            continue
        ts: List[float] = []
        for s in everything:
            if s is t:
                continue
            for p in intersections(t, s, tol):
                u = param_of(t, p, tol)
                if u is not None:
                    ts.append(u)
        eps = tol / t.length
        interior = sorted(u for u in ts if eps < u < 1 - eps)
        cuts = [0.0]
        for u in interior:
            if u - cuts[-1] > eps:
                cuts.append(u)
        cuts.append(1.0)
        if len(cuts) == 2:
            out.append(t)
            continue
        pieces = [t.sub(a, b) for a, b in zip(cuts, cuts[1:])]
        before = len(pieces)
        start_free = not any(u <= eps for u in ts)
        end_free = not any(u >= 1 - eps for u in ts)
        if start_free and end_free and before == 2:
            # one crossing, nothing attached: the shorter side is the overhang
            pieces = [max(pieces, key=lambda s: s.length)]
        else:
            if start_free:
                pieces = pieces[1:]
            if end_free:
                pieces = pieces[:-1]
        if len(pieces) == before:
            split += 1
        removed += before - len(pieces)
        out.extend(pieces)
    return out, removed, split


def fillet_all(shapes: Sequence[Shape], radius: float, tol: float = 1000.0) -> Tuple[List[Shape], int, int]:
    """Round every corner where exactly two straight lines meet.

    Returns (shapes, corners filleted, corners skipped). Corners are skipped
    when an arc is involved or the lines are too short for the radius.
    """
    shapes = list(shapes)
    ends, incident, pos = build_graph(shapes, tol)
    plans = []
    used: Dict[Tuple[int, int], float] = {}
    skipped = 0
    for node, inc in incident.items():
        if len(inc) != 2:
            continue
        (i, ei), (j, ej) = inc
        s1, s2 = shapes[i], shapes[j]
        if i == j:
            continue
        if not (isinstance(s1, Line) and isinstance(s2, Line)):
            skipped += 1
            continue
        p = pos[node]
        f1 = s1.a if ei == 1 else s1.b
        f2 = s2.a if ej == 1 else s2.b
        l1, l2 = dist(p, f1), dist(p, f2)
        u1 = ((f1[0] - p[0]) / l1, (f1[1] - p[1]) / l1)
        u2 = ((f2[0] - p[0]) / l2, (f2[1] - p[1]) / l2)
        cos_t = max(-1.0, min(1.0, u1[0] * u2[0] + u1[1] * u2[1]))
        theta = math.acos(cos_t)
        if theta < 1e-6 or math.pi - theta < 1e-6:
            continue  # straight through or doubled back: not a corner
        setback = radius / math.tan(theta / 2)
        plans.append((i, ei, j, ej, p, u1, u2, setback, theta))
        used[(i, ei)] = setback
        used[(j, ej)] = setback

    new_arcs: List[Shape] = []
    trims: Dict[int, Dict[int, Point]] = defaultdict(dict)
    done = 0
    for i, ei, j, ej, p, u1, u2, setback, theta in plans:
        fits = all(
            used.get((k, 0), 0.0) + used.get((k, 1), 0.0) <= shapes[k].length + tol for k in (i, j)
        )
        if not fits:
            skipped += 1
            continue
        t1 = (p[0] + u1[0] * setback, p[1] + u1[1] * setback)
        t2 = (p[0] + u2[0] * setback, p[1] + u2[1] * setback)
        bis = (u1[0] + u2[0], u1[1] + u2[1])
        bl = math.hypot(*bis)
        h = radius / math.sin(theta / 2)
        c = (p[0] + bis[0] / bl * h, p[1] + bis[1] / bl * h)
        new_arcs.append(Arc.from_center(c, t1, t2))
        trims[i][ei] = t1
        trims[j][ej] = t2
        done += 1

    out: List[Shape] = []
    for k, s in enumerate(shapes):
        if k in trims:
            a = trims[k].get(0, s.start)
            b = trims[k].get(1, s.end)
            if dist(a, b) <= tol:
                continue  # consumed entirely by its two fillets
            s = s.with_ends(a, b)
        out.append(s)
    return out + new_arcs, done, skipped


def _chains(shapes: Sequence[Shape], tol: float) -> List[List[Tuple[int, bool]]]:
    """Runs of lines connected through 2-way joints. Items are (index, reversed)."""
    ends, incident, _ = build_graph(shapes, tol)
    is_line = [isinstance(s, Line) for s in shapes]

    def nxt(i: int, node: int) -> Optional[Tuple[int, int]]:
        inc = incident[node]
        if len(inc) != 2:
            return None
        other = inc[0] if inc[1][0] == i else inc[1]
        if other[0] == i or not is_line[other[0]]:
            return None
        return other

    visited = set()
    chains = []
    for i0 in range(len(shapes)):
        if not is_line[i0] or i0 in visited:
            continue
        # walk backwards to the chain start (or all the way round a loop)
        i, rev = i0, False
        seen = {i0}
        while True:
            node = ends[i][1] if rev else ends[i][0]
            n = nxt(i, node)
            if n is None or n[0] in seen:
                break
            i, rev = n[0], n[1] == 0  # we arrive at its end unless we hit its start
            seen.add(i)
        chain = []
        while True:
            chain.append((i, rev))
            visited.add(i)
            node = ends[i][0] if rev else ends[i][1]
            n = nxt(i, node)
            if n is None or n[0] in visited:
                break
            i, rev = n[0], n[1] == 1
        chains.append(chain)
    return chains


def refit_arcs(
    shapes: Sequence[Shape], fit_tol: float, join_tol: float, max_step: float = math.radians(30)
) -> Tuple[List[Shape], int]:
    """Replace runs of short lines that follow a circle with real arcs.

    A run qualifies when it has at least 3 lines, every vertex is within
    ``fit_tol`` of one circle, it always turns the same way, and no single
    line spans more than ``max_step`` of that circle.
    """
    shapes = list(shapes)
    replaced: Dict[int, Optional[Shape]] = {}
    count = 0
    for chain in _chains(shapes, join_tol):
        pts = []
        for i, rev in chain:
            s = shapes[i]
            pts.append(s.b if rev else s.a)
        last_i, last_rev = chain[-1]
        pts.append(shapes[last_i].a if last_rev else shapes[last_i].b)
        if len(chain) > 3 and dist(pts[0], pts[-1]) <= join_tol:
            # closed loop: start at its longest line so no arc straddles the seam
            k0 = max(range(len(chain)), key=lambda k: dist(pts[k], pts[k + 1]))
            chain = chain[k0:] + chain[:k0]
            pts = pts[k0:-1] + pts[:k0] + [pts[k0]]

        def fits(lo: int, hi: int) -> Optional[Tuple[Point, float]]:
            circ = fit_circle(pts[lo : hi + 1])
            if circ is None:
                return None
            c, r = circ
            half_chord = max(dist(pts[lo], pts[k]) for k in range(lo + 1, hi + 1)) / 2
            if half_chord < r and r - math.sqrt(r * r - half_chord * half_chord) < 2 * fit_tol:
                return None  # so flat that it is a straight line
            sign = 0
            for k in range(lo, hi + 1):
                if abs(dist(pts[k], c) - r) > fit_tol:
                    return None
            for k in range(lo, hi):
                a, b = pts[k], pts[k + 1]
                cross = (a[0] - c[0]) * (b[1] - c[1]) - (a[1] - c[1]) * (b[0] - c[0])
                step = 2 * math.asin(min(1.0, dist(a, b) / (2 * r)))
                if step > max_step or cross == 0:
                    return None
                sg = 1 if cross > 0 else -1
                if sign and sg != sign:
                    return None
                sign = sg
            return c, r

        lo = 0
        n = len(pts) - 1
        while lo + 3 <= n:
            hi = lo + 3
            best = fits(lo, hi)
            if best is None:
                lo += 1
                continue
            while hi + 1 <= n:
                better = fits(lo, hi + 1)
                if better is None:
                    break
                best, hi = better, hi + 1
            c, r = best
            ref = shapes[chain[lo][0]].ref
            if hi - lo == n and dist(pts[lo], pts[hi]) <= join_tol:
                arc: Shape = Arc.circle(c, r, ref)
            else:
                mid = pts[(lo + hi) // 2]
                k = r / dist(c, mid)
                on_circle = (c[0] + (mid[0] - c[0]) * k, c[1] + (mid[1] - c[1]) * k)
                arc = Arc.from_3pt(pts[lo], on_circle, pts[hi], ref)
            for k in range(lo, hi):
                replaced[chain[k][0]] = None
            replaced[chain[lo][0]] = arc
            count += 1
            lo = hi
    out = [replaced.get(i, s) if i in replaced else s for i, s in enumerate(shapes)]
    return [s for s in out if s is not None], count


def find_loop(shapes: Sequence[Shape], index: int, tol: float) -> Optional[List[Point]]:
    """Polygon of the closed loop that contains shape ``index``, if there is one."""
    ends, incident, _ = build_graph(shapes, tol)
    if ends[index] is None:
        return None
    start_node, node = ends[index]
    poly = list(sample(shapes[index]))
    i = index
    for _ in range(len(shapes)):
        if node == start_node:
            return poly
        inc = incident[node]
        if len(inc) != 2:
            return None
        j, ej = inc[0] if inc[1][0] == i else inc[1]
        if j == i:
            return None
        pts = sample(shapes[j])
        poly.extend(pts[1:] if ej == 0 else pts[::-1][1:])
        node = ends[j][1] if ej == 0 else ends[j][0]
        i = j
    return None


def add_tab(
    shapes: Sequence[Shape], index: int, width: float, depth: float, offset: float = 0.0, tol: float = 1000.0
) -> List[Shape]:
    """Replace line ``index`` with the same line carrying a rectangular tab.

    Positive ``depth`` points away from the board when the line is part of a
    closed outline (a tab); negative cuts into it (a notch). ``offset`` shifts
    the tab along the line from its midpoint. Returns the replacement shapes.
    """
    line = shapes[index]
    if not isinstance(line, Line):
        raise ValueError("A tab can only be added to a straight line.")
    length = line.length
    if width <= 0 or width / 2 + abs(offset) > length / 2 + tol:
        raise ValueError("The tab does not fit on the selected line.")
    ux, uy = (line.b[0] - line.a[0]) / length, (line.b[1] - line.a[1]) / length
    nx, ny = uy, -ux
    loop = find_loop(shapes, index, tol)
    if loop is not None:
        probe = min(length, abs(depth) or length) * 1e-3
        m = line.mid
        if point_in_polygon((m[0] + nx * probe, m[1] + ny * probe), loop):
            nx, ny = -nx, -ny
    mid_t = length / 2 + offset
    p1 = (line.a[0] + ux * (mid_t - width / 2), line.a[1] + uy * (mid_t - width / 2))
    p2 = (line.a[0] + ux * (mid_t + width / 2), line.a[1] + uy * (mid_t + width / 2))
    q1 = (p1[0] + nx * depth, p1[1] + ny * depth)
    q2 = (p2[0] + nx * depth, p2[1] + ny * depth)
    out: List[Shape] = []
    if dist(line.a, p1) > tol:
        out.append(Line(line.a, p1, line.ref))
    out += [Line(p1, q1), Line(q1, q2), Line(q2, p2)]
    if dist(p2, line.b) > tol:
        out.append(Line(p2, line.b))
    return out
