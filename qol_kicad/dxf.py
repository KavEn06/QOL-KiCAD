"""Read a DXF file into outline shapes (nanometres, KiCad's Y-down axis)."""

from __future__ import annotations

from typing import List, Tuple

from .geom import Arc, Line, Shape

NM_PER_MM = 1e6
_FLATTEN_MM = 0.001


def read_dxf(path: str, default_unit_mm: float = 1.0) -> Tuple[List[Shape], int]:
    """Returns (shapes, number of entities skipped as unsupported)."""
    import ezdxf
    from ezdxf import units

    doc = ezdxf.readfile(path)
    mm = units.conversion_factor(doc.units, units.MM) if doc.units else default_unit_mm
    k = mm * NM_PER_MM

    def pt(v) -> Tuple[float, float]:
        return (v[0] * k, -v[1] * k)

    shapes: List[Shape] = []
    skipped = 0

    def polyline(points) -> None:
        pts = [pt(p) for p in points]
        shapes.extend(Line(a, b) for a, b in zip(pts, pts[1:]) if a != b)

    def add(e) -> None:
        nonlocal skipped
        kind = e.dxftype()
        if kind == "LINE":
            shapes.append(Line(pt(e.dxf.start), pt(e.dxf.end)))
        elif kind == "CIRCLE":
            shapes.append(Arc.circle(pt(e.ocs().to_wcs(e.dxf.center)), e.dxf.radius * k))
        elif kind == "ARC":
            a0 = e.dxf.start_angle
            span = (e.dxf.end_angle - a0) % 360 or 360
            start, mid, end = e.vertices([a0, a0 + span / 2, a0 + span])
            shapes.append(Arc.from_3pt(pt(start), pt(mid), pt(end)))
        elif kind in ("LWPOLYLINE", "POLYLINE", "INSERT"):
            for sub in e.virtual_entities():
                add(sub)
        elif kind == "SPLINE":
            polyline(e.flattening(_FLATTEN_MM / mm))
        elif kind == "ELLIPSE":
            polyline(e.flattening(_FLATTEN_MM / mm))
        else:
            skipped += 1

    for entity in doc.modelspace():
        add(entity)
    return shapes, skipped
