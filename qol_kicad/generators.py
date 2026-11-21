"""Outline generators. All sizes in nanometres, centred on ``center``."""

from __future__ import annotations

import math
from typing import List

from .geom import Arc, Line, Point, Shape


def rounded_rect(center: Point, width: float, height: float, radius: float = 0.0) -> List[Shape]:
    if width <= 0 or height <= 0:
        raise ValueError("Width and height must be positive.")
    if radius < 0 or radius > min(width, height) / 2:
        raise ValueError("Corner radius must be between 0 and half the shorter side.")
    cx, cy = center
    x0, x1, y0, y1 = cx - width / 2, cx + width / 2, cy - height / 2, cy + height / 2
    r = radius
    out: List[Shape] = []
    for a, b in (
        ((x0 + r, y0), (x1 - r, y0)),
        ((x1, y0 + r), (x1, y1 - r)),
        ((x1 - r, y1), (x0 + r, y1)),
        ((x0, y1 - r), (x0, y0 + r)),
    ):
        if a != b:
            out.append(Line(a, b))
    if r > 0:
        out += [
            Arc.from_center((x1 - r, y0 + r), (x1 - r, y0), (x1, y0 + r)),
            Arc.from_center((x1 - r, y1 - r), (x1, y1 - r), (x1 - r, y1)),
            Arc.from_center((x0 + r, y1 - r), (x0 + r, y1), (x0, y1 - r)),
            Arc.from_center((x0 + r, y0 + r), (x0, y0 + r), (x0 + r, y0)),
        ]
    return out


def slot(center: Point, length: float, width: float, vertical: bool = False) -> List[Shape]:
    """Stadium-shaped slot. ``length`` is the overall end-to-end size."""
    if width <= 0 or length < width:
        raise ValueError("Slot length must be at least its width, and both positive.")
    if length == width:
        return [Arc.circle(center, width / 2)]
    cx, cy = center
    r, half = width / 2, (length - width) / 2
    shapes: List[Shape] = [
        Line((cx - half, cy - r), (cx + half, cy - r)),
        Arc((cx + half, cy), r, -math.pi / 2, math.pi),
        Line((cx + half, cy + r), (cx - half, cy + r)),
        Arc((cx - half, cy), r, math.pi / 2, math.pi),
    ]
    if vertical:
        shapes = [_rot90(s, center) for s in shapes]
    return shapes


def _rot90(s: Shape, c: Point) -> Shape:
    def rot(p: Point) -> Point:
        return (c[0] - (p[1] - c[1]), c[1] + (p[0] - c[0]))

    if isinstance(s, Line):
        return Line(rot(s.a), rot(s.b))
    return Arc(rot(s.c), s.r, s.a0 + math.pi / 2, s.sweep)
