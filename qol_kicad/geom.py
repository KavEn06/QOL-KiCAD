"""Pure 2D geometry for outline editing. Coordinates are floats in nanometres."""

from __future__ import annotations

import math
from dataclasses import dataclass, field, replace
from typing import List, Optional, Sequence, Tuple, Union

Point = Tuple[float, float]
TAU = 2 * math.pi


def dist(a: Point, b: Point) -> float:
    return math.hypot(a[0] - b[0], a[1] - b[1])


def lerp(a: Point, b: Point, t: float) -> Point:
    return (a[0] + (b[0] - a[0]) * t, a[1] + (b[1] - a[1]) * t)


def circle_from_3pt(a: Point, b: Point, c: Point) -> Optional[Tuple[Point, float]]:
    """Centre and radius of the circle through three points, or None if collinear."""
    ax, ay = a
    bx, by = b[0] - ax, b[1] - ay
    cx, cy = c[0] - ax, c[1] - ay
    d = 2 * (bx * cy - by * cx)
    scale = max(math.hypot(bx, by), math.hypot(cx, cy))
    if scale == 0 or abs(d) < 1e-12 * scale * scale:
        return None
    b2, c2 = bx * bx + by * by, cx * cx + cy * cy
    ux, uy = (cy * b2 - by * c2) / d, (bx * c2 - cx * b2) / d
    return (ax + ux, ay + uy), math.hypot(ux, uy)


def fit_circle(pts: Sequence[Point]) -> Optional[Tuple[Point, float]]:
    """Least-squares circle through points (Kasa fit), or None if they are collinear."""
    n = len(pts)
    mx, my = sum(p[0] for p in pts) / n, sum(p[1] for p in pts) / n
    sxx = sxy = syy = sxz = syz = sz = 0.0
    for px, py in pts:
        x, y = px - mx, py - my
        z = x * x + y * y
        sxx += x * x
        sxy += x * y
        syy += y * y
        sxz += x * z
        syz += y * z
        sz += z
    det = sxx * syy - sxy * sxy
    if det <= 1e-12 * (sxx + syy) ** 2:
        return None
    cx = (sxz * syy - syz * sxy) / (2 * det)
    cy = (syz * sxx - sxz * sxy) / (2 * det)
    return (mx + cx, my + cy), math.sqrt(cx * cx + cy * cy + sz / n)


@dataclass(frozen=True)
class Line:
    a: Point
    b: Point
    ref: Optional[str] = field(default=None, compare=False)

    @property
    def start(self) -> Point:
        return self.a

    @property
    def end(self) -> Point:
        return self.b

    @property
    def mid(self) -> Point:
        return lerp(self.a, self.b, 0.5)

    @property
    def length(self) -> float:
        return dist(self.a, self.b)

    @property
    def closed(self) -> bool:
        return False

    def point_at(self, t: float) -> Point:
        return lerp(self.a, self.b, t)

    def sub(self, t0: float, t1: float) -> "Line":
        return replace(self, a=self.point_at(t0), b=self.point_at(t1))

    def with_ends(self, start: Point, end: Point) -> "Line":
        return replace(self, a=start, b=end)

    def moved(self, dx: float, dy: float) -> "Line":
        return replace(self, a=(self.a[0] + dx, self.a[1] + dy), b=(self.b[0] + dx, self.b[1] + dy))


@dataclass(frozen=True)
class Arc:
    """Circular arc: centre, radius, start angle and signed sweep (radians).

    A sweep of +/- 2*pi is a full circle.
    """

    c: Point
    r: float
    a0: float
    sweep: float
    ref: Optional[str] = field(default=None, compare=False)

    @classmethod
    def from_3pt(cls, start: Point, mid: Point, end: Point, ref: Optional[str] = None) -> Union["Arc", Line]:
        circ = circle_from_3pt(start, mid, end)
        if circ is None:
            return Line(start, end, ref)
        c, r = circ
        a0 = math.atan2(start[1] - c[1], start[0] - c[0])
        am = (math.atan2(mid[1] - c[1], mid[0] - c[0]) - a0) % TAU
        ae = (math.atan2(end[1] - c[1], end[0] - c[0]) - a0) % TAU
        sweep = ae if am < ae else ae - TAU
        return cls(c, r, a0, sweep, ref)

    @classmethod
    def from_center(cls, c: Point, start: Point, end: Point, ref: Optional[str] = None) -> "Arc":
        """Shorter arc around ``c`` from ``start`` to ``end``."""
        a0 = math.atan2(start[1] - c[1], start[0] - c[0])
        sweep = (math.atan2(end[1] - c[1], end[0] - c[0]) - a0 + math.pi) % TAU - math.pi
        return cls(c, dist(c, start), a0, sweep, ref)

    @classmethod
    def circle(cls, c: Point, r: float, ref: Optional[str] = None) -> "Arc":
        return cls(c, r, 0.0, TAU, ref)

    @property
    def closed(self) -> bool:
        return abs(self.sweep) >= TAU - 1e-9

    @property
    def start(self) -> Point:
        return self.point_at(0.0)

    @property
    def end(self) -> Point:
        return self.point_at(1.0)

    @property
    def mid(self) -> Point:
        return self.point_at(0.5)

    @property
    def length(self) -> float:
        return abs(self.sweep) * self.r

    def point_at(self, t: float) -> Point:
        a = self.a0 + self.sweep * t
        return (self.c[0] + self.r * math.cos(a), self.c[1] + self.r * math.sin(a))

    def sub(self, t0: float, t1: float) -> "Arc":
        return replace(self, a0=self.a0 + self.sweep * t0, sweep=self.sweep * (t1 - t0))

    def with_ends(self, start: Point, end: Point) -> Union["Arc", Line]:
        """Same arc stretched between new ends: the sweep angle (its bulge) is kept."""
        chord = dist(start, end)
        if self.closed or chord == 0:
            return self
        half = self.sweep / 2
        r = chord / (2 * abs(math.sin(half)))
        # centre sits left of the chord for a positive sweep under pi, at distance r*cos(half)
        h = r * math.cos(half) * (1 if self.sweep > 0 else -1)
        ux, uy = (end[0] - start[0]) / chord, (end[1] - start[1]) / chord
        c = ((start[0] + end[0]) / 2 - uy * h, (start[1] + end[1]) / 2 + ux * h)
        return replace(self, c=c, r=r, a0=math.atan2(start[1] - c[1], start[0] - c[0]))

    def moved(self, dx: float, dy: float) -> "Arc":
        return replace(self, c=(self.c[0] + dx, self.c[1] + dy))


Shape = Union[Line, Arc]


def param_of(shape: Shape, p: Point, tol: float) -> Optional[float]:
    """Parameter (0..1) of ``p`` on ``shape`` if it lies on it within ``tol``."""
    if isinstance(shape, Line):
        dx, dy = shape.b[0] - shape.a[0], shape.b[1] - shape.a[1]
        l2 = dx * dx + dy * dy
        if l2 == 0:
            return None
        t = ((p[0] - shape.a[0]) * dx + (p[1] - shape.a[1]) * dy) / l2
        tt = tol / math.sqrt(l2)
        if t < -tt or t > 1 + tt or dist(shape.point_at(t), p) > tol:
            return None
        return min(1.0, max(0.0, t))
    d = dist(shape.c, p)
    if abs(d - shape.r) > tol or shape.r == 0:
        return None
    ang = math.atan2(p[1] - shape.c[1], p[0] - shape.c[0])
    delta = (ang - shape.a0) % TAU if shape.sweep > 0 else -((shape.a0 - ang) % TAU)
    t = delta / shape.sweep
    tt = tol / shape.length
    if t > 1 + tt:
        # just before the start, seen the long way round
        if (TAU / abs(shape.sweep)) - t <= tt:
            return 0.0
        return None
    return min(1.0, t)


def _line_circle(a: Point, b: Point, c: Point, r: float, tol: float) -> List[Point]:
    dx, dy = b[0] - a[0], b[1] - a[1]
    length = math.hypot(dx, dy)
    if length == 0:
        return []
    ux, uy = dx / length, dy / length
    s = (c[0] - a[0]) * ux + (c[1] - a[1]) * uy
    foot = (a[0] + ux * s, a[1] + uy * s)
    h = dist(foot, c)
    if h > r + tol:
        return []
    k = math.sqrt(max(0.0, r * r - h * h))
    if k <= math.sqrt(2 * r * tol) and h >= r - tol:
        return [foot]
    return [(foot[0] - ux * k, foot[1] - uy * k), (foot[0] + ux * k, foot[1] + uy * k)]


def _circle_circle(c1: Point, r1: float, c2: Point, r2: float, tol: float) -> List[Point]:
    d = dist(c1, c2)
    if d < tol or d > r1 + r2 + tol or d < abs(r1 - r2) - tol:
        return []
    x = (d * d + r1 * r1 - r2 * r2) / (2 * d)
    h2 = r1 * r1 - x * x
    ux, uy = (c2[0] - c1[0]) / d, (c2[1] - c1[1]) / d
    base = (c1[0] + ux * x, c1[1] + uy * x)
    if h2 <= 2 * r1 * tol:
        return [base]
    h = math.sqrt(h2)
    return [(base[0] - uy * h, base[1] + ux * h), (base[0] + uy * h, base[1] - ux * h)]


def intersections(s1: Shape, s2: Shape, tol: float = 1000.0) -> List[Point]:
    """Points where two shapes cross or touch. Overlapping collinear parts are ignored."""
    if isinstance(s1, Line) and isinstance(s2, Line):
        d1 = (s1.b[0] - s1.a[0], s1.b[1] - s1.a[1])
        d2 = (s2.b[0] - s2.a[0], s2.b[1] - s2.a[1])
        den = d1[0] * d2[1] - d1[1] * d2[0]
        if abs(den) <= 1e-9 * s1.length * s2.length:
            # parallel: only end-to-end touches count
            cands = [p for p in (s2.a, s2.b) if dist(p, s1.a) <= tol or dist(p, s1.b) <= tol]
        else:
            w = (s2.a[0] - s1.a[0], s2.a[1] - s1.a[1])
            t = (w[0] * d2[1] - w[1] * d2[0]) / den
            cands = [s1.point_at(t)]
    elif isinstance(s1, Line):
        cands = _line_circle(s1.a, s1.b, s2.c, s2.r, tol)
    elif isinstance(s2, Line):
        cands = _line_circle(s2.a, s2.b, s1.c, s1.r, tol)
    else:
        cands = _circle_circle(s1.c, s1.r, s2.c, s2.r, tol)
    out: List[Point] = []
    for p in cands:
        if param_of(s1, p, tol) is None or param_of(s2, p, tol) is None:
            continue
        if all(dist(p, q) > tol for q in out):
            out.append(p)
    return out


def sample(shape: Shape, max_step: float = math.radians(5)) -> List[Point]:
    """Polyline approximation including both ends."""
    if isinstance(shape, Line):
        return [shape.a, shape.b]
    n = max(2, int(math.ceil(abs(shape.sweep) / max_step)))
    return [shape.point_at(i / n) for i in range(n + 1)]


def point_in_polygon(p: Point, poly: List[Point]) -> bool:
    inside = False
    x, y = p
    for (x1, y1), (x2, y2) in zip(poly, poly[1:] + poly[:1]):
        if (y1 > y) != (y2 > y) and x < x1 + (y - y1) * (x2 - x1) / (y2 - y1):
            inside = not inside
    return inside


def bbox(shapes: List[Shape]) -> Tuple[float, float, float, float]:
    pts = [p for s in shapes for p in sample(s)]
    xs, ys = [p[0] for p in pts], [p[1] for p in pts]
    return min(xs), min(ys), max(xs), max(ys)
