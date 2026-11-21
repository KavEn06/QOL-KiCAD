"""Live follow: keep ends that were joined together joined after one of them moves."""

from __future__ import annotations

from typing import Dict, List, Tuple

from .geom import Point, dist
from .outline import Nodes

Ends = Dict[str, Tuple[Point, Point]]


def follow(old: Ends, new: Ends, tol: float) -> Ends:
    """Given shape ends before and after a user edit, return the ends to rewrite.

    For every joint in ``old`` (ends within ``tol``), if some of its ends moved
    to one common place and the rest stayed put, the rest are moved there too.
    """
    nodes = Nodes(tol)
    members: Dict[int, List[Tuple[str, int]]] = {}
    handles = []
    for ref, ends in old.items():
        if ref not in new:
            continue
        for k in (0, 1):
            handles.append((nodes.add(ends[k]), ref, k))
    for h, ref, k in handles:
        members.setdefault(nodes.node(h), []).append((ref, k))

    out: Dict[str, List[Point]] = {}
    for joint in members.values():
        if len(joint) < 2:
            continue
        moved = [(r, k) for r, k in joint if dist(old[r][k], new[r][k]) > tol]
        stayed = [(r, k) for r, k in joint if (r, k) not in moved]
        if not moved or not stayed:
            continue
        target = new[moved[0][0]][moved[0][1]]
        if any(dist(new[r][k], target) > tol for r, k in moved):
            continue  # the joint was pulled apart on purpose
        for r, k in stayed:
            out.setdefault(r, list(new[r]))[k] = target
    return {r: (e[0], e[1]) for r, e in out.items() if dist(e[0], e[1]) > tol}
