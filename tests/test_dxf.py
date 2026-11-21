import math

import pytest

ezdxf = pytest.importorskip("ezdxf")

from qol_kicad.dxf import read_dxf  # noqa: E402
from qol_kicad.geom import Arc, Line  # noqa: E402
from qol_kicad.outline import clean, refit_arcs  # noqa: E402

MM = 1e6


def _import(path, tol=0.01 * MM, fit=0.005 * MM):
    raw, skipped = read_dxf(str(path))
    shapes, _ = clean(raw, tol)
    shapes, _ = refit_arcs(shapes, fit, tol)
    shapes, rep = clean(shapes, tol)
    return raw, shapes, rep, skipped


def test_polyline_with_bulges_circle_and_text(tmp_path):
    doc = ezdxf.new("R2010")
    doc.units = ezdxf.units.MM
    msp = doc.modelspace()
    b = math.tan(math.pi / 8)
    pts = [(5, 0, b * 0), (55, 0, b), (60, 5, 0), (60, 35, b), (55, 40, 0), (5, 40, b), (0, 35, 0), (0, 5, b)]
    msp.add_lwpolyline(pts, format="xyb", close=True)
    msp.add_circle((30, 20), 4)
    msp.add_text("ignored")
    path = tmp_path / "a.dxf"
    doc.saveas(path)

    raw, shapes, rep, skipped = _import(path)
    assert skipped == 1
    assert rep.is_closed
    arcs = [s for s in shapes if isinstance(s, Arc) and not s.closed]
    circles = [s for s in shapes if s.closed]
    lines = [s for s in shapes if isinstance(s, Line)]
    assert (len(lines), len(arcs), len(circles)) == (4, 4, 1)
    assert all(a.r == pytest.approx(5 * MM, rel=1e-6) for a in arcs)
    # Y is flipped: DXF y=40 becomes -40 mm
    assert min(p[1] for s in lines for p in (s.a, s.b)) == pytest.approx(-40 * MM)


def test_messy_segmented_slot_in_inches(tmp_path):
    doc = ezdxf.new("R2010")
    doc.units = ezdxf.units.IN
    msp = doc.modelspace()

    def arc_pts(cx, a0, n=24):
        return [(cx + 0.1 * math.cos(a0 + math.pi * i / n), 0.1 * math.sin(a0 + math.pi * i / n)) for i in range(n + 1)]

    for cx, a0 in ((1.0, -math.pi / 2), (0.0, math.pi / 2)):
        p = arc_pts(cx, a0)
        for a, c in zip(p, p[1:]):
            msp.add_line(a, c)
    msp.add_line((1.0001, 0.1), (0, 0.1))  # 2.5 um gap
    msp.add_line((0, -0.1), (1.0, -0.1001))
    path = tmp_path / "slot.dxf"
    doc.saveas(path)

    raw, shapes, rep, _ = _import(path)
    assert len(raw) == 50 and len(shapes) == 4 and rep.is_closed
    arcs = [s for s in shapes if isinstance(s, Arc)]
    assert len(arcs) == 2
    assert all(a.r == pytest.approx(2.54 * MM, rel=1e-3) for a in arcs)


def test_spline_and_ellipse_are_flattened(tmp_path):
    doc = ezdxf.new("R2010")
    doc.units = ezdxf.units.MM
    msp = doc.modelspace()
    msp.add_ellipse((0, 0), major_axis=(6, 0), ratio=0.5)
    msp.add_spline([(10, 0), (12, 3), (15, -3), (18, 0)])
    path = tmp_path / "curves.dxf"
    doc.saveas(path)
    raw, shapes, rep, skipped = _import(path)
    assert skipped == 0 and len(raw) > 20
    assert len(rep.open_ends) == 2  # the ellipse closes; the spline has two free ends
