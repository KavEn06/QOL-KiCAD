import math

import pytest

from qol_kicad.generators import rounded_rect, slot
from qol_kicad.geom import Arc, Line, intersections, param_of
from qol_kicad.outline import add_tab, build_graph, clean, fillet_all, refit_arcs, trim

MM = 1e6


def rect(w=40 * MM, h=20 * MM):
    return rounded_rect((0, 0), w, h, 0)


def is_closed_loop(shapes, tol=1000):
    _, incident, _ = build_graph(shapes, tol)
    return all(len(v) == 2 for v in incident.values())


def test_arc_from_3pt_roundtrip():
    a = Arc.from_3pt((10, 0), (0, 10), (-10, 0))
    assert a.c == pytest.approx((0, 0), abs=1e-6)
    assert a.r == pytest.approx(10)
    assert a.sweep == pytest.approx(math.pi)
    b = Arc.from_3pt((10, 0), (0, -10), (-10, 0))
    assert b.sweep == pytest.approx(-math.pi)
    assert b.mid == pytest.approx((0, -10), abs=1e-6)


def test_param_of_arc_both_directions():
    for sweep in (math.pi / 2, -math.pi / 2):
        a = Arc((0, 0), 10 * MM, 0.3, sweep)
        for t in (0.0, 0.25, 0.5, 1.0):
            assert param_of(a, a.point_at(t), 1000) == pytest.approx(t, abs=1e-6)
        assert param_of(a, a.point_at(1.2), 1000) is None
        assert param_of(a, a.point_at(-0.2), 1000) is None


def test_intersections():
    l1 = Line((0, 0), (10 * MM, 0))
    l2 = Line((5 * MM, -5 * MM), (5 * MM, 5 * MM))
    assert intersections(l1, l2) == [pytest.approx((5 * MM, 0))]
    assert intersections(l1, Line((20 * MM, -1), (20 * MM, 1))) == []
    # T junction counts
    assert len(intersections(l1, Line((5 * MM, 0), (5 * MM, 5 * MM)))) == 1
    circle = Arc.circle((5 * MM, 0), 2 * MM)
    xs = sorted(p[0] for p in intersections(l1, circle))
    assert xs == pytest.approx([3 * MM, 7 * MM])
    half = Arc((5 * MM, 0), 2 * MM, 0, math.pi / 2)
    assert len(intersections(l1, half)) == 1
    c2 = Arc.circle((8 * MM, 0), 2 * MM)
    assert len(intersections(circle, c2)) == 2


def test_trim_removes_overhangs_only():
    # two lines crossing with overhangs past the corner
    h = Line((0, 0), (12 * MM, 0), ref="h")
    v = Line((10 * MM, -2 * MM), (10 * MM, 10 * MM), ref="v")
    out, removed, split = trim([h, v], [])
    assert removed == 2 and split == 0
    assert len(out) == 2
    assert out[0].b == pytest.approx((10 * MM, 0)) and out[0].a == (0, 0)
    assert out[1].a == pytest.approx((10 * MM, 0))
    # only the selected one is trimmed
    out, removed, _ = trim([h], [v])
    assert removed == 1 and len(out) == 1
    # attached at the start: the far overhang goes even though it is the longer piece
    anchor = Line((0, 0), (0, 5 * MM))
    out, removed, _ = trim([Line((0, 0), (12 * MM, 0))], [anchor, Line((3 * MM, -MM), (3 * MM, MM))])
    assert removed == 1 and out[0].b == pytest.approx((3 * MM, 0))


def test_trim_splits_when_both_ends_attached():
    top = Line((0, 0), (10 * MM, 0))
    left = Line((0, 0), (0, 5 * MM))
    right = Line((10 * MM, 0), (10 * MM, 5 * MM))
    cutter = Line((5 * MM, -1 * MM), (5 * MM, 1 * MM))
    out, removed, split = trim([top], [left, right, cutter])
    assert removed == 0 and split == 1 and len(out) == 2


def test_trim_arc():
    arc = Arc((0, 0), 10 * MM, 0, math.pi)  # from (10,0) over (0,10) to (-10,0)
    cutter = Line((0, 0), (0, 20 * MM))
    anchor = Line((10 * MM, 0), (20 * MM, 0))
    out, removed, _ = trim([arc], [cutter, anchor])
    assert removed == 1 and len(out) == 1
    assert out[0].end == pytest.approx((0, 10 * MM), abs=1)
    assert out[0].start == pytest.approx((10 * MM, 0), abs=1)


def test_clean_joins_gaps_and_merges():
    g = 0.004 * MM
    shapes = [
        Line((0, 0), (10 * MM, 0)),
        Line((10 * MM + g, g), (20 * MM, 0)),  # collinear continuation with a gap
        Line((20 * MM, -g), (20 * MM, 10 * MM)),
        Line((20 * MM, 10 * MM), (0, 10 * MM)),
        Line((0, 10 * MM), (0, 0)),
        Line((0, 10 * MM), (0, 0)),  # duplicate
        Line((5, 5), (6, 6)),  # zero length
    ]
    out, rep = clean(shapes, 0.01 * MM)
    assert rep.is_closed
    assert len(out) == 4
    assert rep.merged == 1 and rep.removed == 2 and rep.joined >= 2
    assert is_closed_loop(out, 1)


def test_clean_reports_open_ends():
    out, rep = clean([Line((0, 0), (10 * MM, 0)), Line((10 * MM, 0), (10 * MM, 10 * MM))], 0.01 * MM)
    assert len(rep.open_ends) == 2 and not rep.is_closed and len(out) == 2


def test_clean_merges_arcs_into_circle():
    a = Arc((0, 0), 5 * MM, 0, math.pi)
    b = Arc((0, 0), 5 * MM, math.pi, math.pi)
    out, rep = clean([a, b], 0.01 * MM)
    assert len(out) == 1 and out[0].closed


def test_fillet_all_rectangle():
    out, done, skipped = fillet_all(rect(), 2 * MM)
    assert done == 4 and skipped == 0
    arcs = [s for s in out if isinstance(s, Arc)]
    assert len(arcs) == 4 and len(out) == 8
    assert all(a.r == pytest.approx(2 * MM) and abs(a.sweep) == pytest.approx(math.pi / 2) for a in arcs)
    assert is_closed_loop(out)
    # same result as the generator
    want = {(round(a.c[0]), round(a.c[1])) for a in rounded_rect((0, 0), 40 * MM, 20 * MM, 2 * MM) if isinstance(a, Arc)}
    assert {(round(a.c[0]), round(a.c[1])) for a in arcs} == want


def test_fillet_concave_corner_and_too_big_radius():
    # L shape: one concave corner
    pts = [(0, 0), (20, 0), (20, 10), (10, 10), (10, 20), (0, 20)]
    shapes = [Line((a[0] * MM, a[1] * MM), (b[0] * MM, b[1] * MM)) for a, b in zip(pts, pts[1:] + pts[:1])]
    out, done, skipped = fillet_all(shapes, 1 * MM)
    assert done == 6 and is_closed_loop(out)
    out, done, skipped = fillet_all(shapes, 6 * MM)
    assert skipped > 0 and is_closed_loop(out)


def test_fillet_exact_fit_consumes_line():
    out, done, _ = fillet_all(rect(20 * MM, 10 * MM), 5 * MM)
    assert done == 4 and is_closed_loop(out)
    assert sum(isinstance(s, Line) for s in out) == 2


def test_generators():
    rr = rounded_rect((5 * MM, 5 * MM), 30 * MM, 20 * MM, 3 * MM)
    assert len(rr) == 8 and is_closed_loop(rr)
    s = slot((0, 0), 10 * MM, 4 * MM)
    assert len(s) == 4 and is_closed_loop(s)
    assert sum(isinstance(x, Arc) for x in s) == 2
    v = slot((0, 0), 10 * MM, 4 * MM, vertical=True)
    assert is_closed_loop(v) and max(abs(p[1]) for x in v for p in (x.start, x.mid, x.end)) == pytest.approx(5 * MM)
    assert slot((0, 0), 4 * MM, 4 * MM)[0].closed
    with pytest.raises(ValueError):
        slot((0, 0), 2 * MM, 4 * MM)
    with pytest.raises(ValueError):
        rounded_rect((0, 0), 10, 10, 6)


def test_refit_polyline_arc():
    # rounded rect whose corners are 16-segment polylines
    src = rounded_rect((0, 0), 30 * MM, 20 * MM, 4 * MM)
    shapes = []
    for s in src:
        if isinstance(s, Arc):
            pts = [s.point_at(i / 16) for i in range(17)]
            shapes += [Line(a, b) for a, b in zip(pts, pts[1:])]
        else:
            shapes.append(s)
    out, n = refit_arcs(shapes, 0.005 * MM, 0.01 * MM)
    out, rep = clean(out, 0.01 * MM)
    assert n >= 4
    arcs = [s for s in out if isinstance(s, Arc)]
    assert len(arcs) == 4 and len(out) == 8 and rep.is_closed
    assert all(a.r == pytest.approx(4 * MM, rel=1e-6) for a in arcs)


def test_refit_polygon_circle_and_leaves_square_alone():
    c = Arc.circle((0, 0), 5 * MM)
    pts = [c.point_at(i / 48) for i in range(49)]
    out, n = refit_arcs([Line(a, b) for a, b in zip(pts, pts[1:])], 0.005 * MM, 0.01 * MM)
    out, _ = clean(out, 0.01 * MM)
    assert len(out) == 1 and out[0].closed and out[0].r == pytest.approx(5 * MM)
    sq, n = refit_arcs(rect(10 * MM, 10 * MM), 0.005 * MM, 0.01 * MM)
    assert n == 0 and len(sq) == 4


def test_tab_points_outward_and_notch_inward():
    shapes = rect()  # top edge first, at y = -10mm
    top = 0
    out = add_tab(shapes, top, 6 * MM, 3 * MM)
    assert len(out) == 5
    tip = out[2]
    assert tip.a[1] == pytest.approx(-13 * MM) and tip.length == pytest.approx(6 * MM)
    assert is_closed_loop(out + shapes[1:])
    notch = add_tab(shapes, top, 6 * MM, -3 * MM)
    assert notch[2].a[1] == pytest.approx(-7 * MM)
    # bottom edge: outward is +y
    out = add_tab(shapes, 2, 6 * MM, 3 * MM)
    assert out[2].a[1] == pytest.approx(13 * MM)
    with pytest.raises(ValueError):
        add_tab(shapes, top, 50 * MM, 3 * MM)


def test_arc_with_ends_keeps_sweep():
    for sweep in (math.pi / 2, -math.pi / 2, 1.5 * math.pi, -1.5 * math.pi):
        a = Arc((3 * MM, -2 * MM), 5 * MM, 0.7, sweep)
        same = a.with_ends(a.start, a.end)
        assert same.c == pytest.approx(a.c, abs=1e-3) and same.r == pytest.approx(a.r)
        moved = a.with_ends((0, 0), (10 * MM, 4 * MM))
        assert moved.sweep == sweep
        assert moved.start == pytest.approx((0, 0), abs=1e-3)
        assert moved.end == pytest.approx((10 * MM, 4 * MM), abs=1e-3)


def test_follow():
    from qol_kicad.follow import follow

    old = {"a": ((0, 0), (10, 0)), "b": ((10, 0), (10, 10)), "c": ((10, 10), (0, 10)), "d": ((0, 10), (0, 0))}
    scaled = {k: tuple((x * MM, y * MM) for x, y in v) for k, v in old.items()}
    # corner of a dragged to a new place: b follows
    new = dict(scaled, a=((0, 0), (12 * MM, -1 * MM)))
    assert follow(scaled, new, 1000) == {"b": ((12 * MM, -1 * MM), (10 * MM, 10 * MM))}
    # whole line a moved up: both neighbours follow
    new = dict(scaled, a=((0, -3 * MM), (10 * MM, -3 * MM)))
    fixes = follow(scaled, new, 1000)
    assert fixes == {"b": ((10 * MM, -3 * MM), (10 * MM, 10 * MM)), "d": ((0, 10 * MM), (0, -3 * MM))}
    # everything moved together, or nothing moved: no fixes
    shifted = {k: tuple((x + MM, y) for x, y in v) for k, v in scaled.items()}
    assert follow(scaled, shifted, 1000) == {} and follow(scaled, scaled, 1000) == {}
    # deleted shapes are ignored
    assert follow(scaled, {k: v for k, v in scaled.items() if k != "a"}, 1000) == {}
