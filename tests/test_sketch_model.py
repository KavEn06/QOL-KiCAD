import math

import pytest

from qol_kicad.geom import Arc, Line, dist
from qol_kicad.sketch.model import Sketch, tangent_arc

MM = 1e6


def rect(w=40.0, h=30.0):
    pts = [(0, 0), (w * MM, 0), (w * MM, h * MM), (0, h * MM)]
    return [Line(a, b) for a, b in zip(pts, pts[1:] + pts[:1])]


def near(p, q, tol=10.0):
    return dist(p, q) <= tol


def test_undo_and_redo():
    sk = Sketch()
    sk.checkpoint()
    sk.add([Line((0, 0), (MM, 0))])
    assert len(sk.shapes) == 1
    assert sk.undo() and sk.shapes == []
    assert sk.redo() and len(sk.shapes) == 1
    assert not sk.redo()


def test_dragging_a_corner_moves_both_edges():
    sk = Sketch(rect())
    sk.shapes = Sketch.dragged_from(sk.shapes, (40 * MM, 0), (50 * MM, -5 * MM))
    assert sk.shapes[0].b == (50 * MM, -5 * MM)
    assert sk.shapes[1].a == (50 * MM, -5 * MM)
    assert sk.shapes[2] == rect()[2]


def test_moving_an_edge_stretches_its_neighbours():
    sk = Sketch(rect())
    out = Sketch.moved_from(sk.shapes, [1], 10 * MM, 0)
    assert out[1] == Line((50 * MM, 0), (50 * MM, 30 * MM))
    assert out[0].b == (50 * MM, 0) and out[2].a == (50 * MM, 30 * MM)
    assert out[3] == sk.shapes[3]


def test_trim_removes_the_piece_between_crossings():
    sk = Sketch([Line((0, 0), (30 * MM, 0)), Line((10 * MM, -5 * MM), (10 * MM, 5 * MM)),
                 Line((20 * MM, -5 * MM), (20 * MM, 5 * MM))])
    assert sk.trim_at((15 * MM, 0), 0.5 * MM)
    lines = [s for s in sk.shapes if s.a[1] == 0 and s.b[1] == 0]
    assert sorted((s.a[0] / MM, s.b[0] / MM) for s in lines) == [(0, 10), (20, 30)]


def test_trim_removes_an_overhang_and_a_lone_shape():
    sk = Sketch([Line((0, 0), (30 * MM, 0)), Line((10 * MM, -5 * MM), (10 * MM, 5 * MM))])
    assert sk.trim_at((20 * MM, 0), 0.5 * MM)
    assert sk.shapes[0] == Line((0, 0), (10 * MM, 0))
    lone = Sketch([Line((0, 0), (MM, 0))])
    assert lone.trim_at((0.5 * MM, 0), 0.1 * MM) and lone.shapes == []


def test_trim_a_circle_leaves_an_arc():
    sk = Sketch([Arc.circle((0, 0), 10 * MM), Line((-20 * MM, 0), (20 * MM, 0))])
    assert sk.trim_at((0, 10 * MM), 0.5 * MM)
    arc = sk.shapes[0]
    assert not arc.closed and abs(abs(arc.sweep) - math.pi) < 1e-6
    assert near(arc.mid, (0, -10 * MM))


def test_extend_a_line_to_the_next_edge():
    sk = Sketch([Line((0, 0), (10 * MM, 0)), Line((25 * MM, -5 * MM), (25 * MM, 5 * MM))])
    assert sk.extend_at((9 * MM, 0), 0.5 * MM)
    assert near(sk.shapes[0].b, (25 * MM, 0))
    assert not sk.extend_at((1 * MM, 0), 0.5 * MM)  # nothing on that side


def test_extend_an_arc_along_its_circle():
    arc = Arc((0, 0), 10 * MM, 0.0, math.pi / 2)
    sk = Sketch([arc, Line((-20 * MM, 0), (-5 * MM, 0))])
    assert sk.extend_at(arc.end, 0.5 * MM)
    assert near(sk.shapes[0].end, (-10 * MM, 0)) and near(sk.shapes[0].start, arc.start)


def test_fillet_one_corner_only():
    sk = Sketch(rect())
    assert sk.fillet_at((40 * MM, 0), 5 * MM, MM)
    arcs = [s for s in sk.shapes if isinstance(s, Arc)]
    assert len(arcs) == 1 and abs(arcs[0].r - 5 * MM) < 1 and len(sk.shapes) == 5
    assert not sk.fillet_at((20 * MM, 0), 5 * MM, MM)  # not a corner


def test_chamfer_a_corner():
    sk = Sketch(rect())
    assert sk.chamfer_at((0, 0), 4 * MM, MM)
    assert len(sk.shapes) == 5
    cut = sk.shapes[-1]
    assert sorted([cut.a, cut.b]) == [(0, 4 * MM), (4 * MM, 0)]


@pytest.mark.parametrize("side,size", [((20 * MM, 15 * MM), (36, 26)), ((-10 * MM, 15 * MM), (44, 34))])
def test_offset_a_closed_outline(side, size):
    sk = Sketch(rect())
    new = sk.offset([0, 1, 2, 3], 2 * MM, side)
    assert len(new) == 4
    xs = [p[0] for i in new for p in (sk.shapes[i].a, sk.shapes[i].b)]
    ys = [p[1] for i in new for p in (sk.shapes[i].a, sk.shapes[i].b)]
    assert round((max(xs) - min(xs)) / MM, 6) == size[0]
    assert round((max(ys) - min(ys)) / MM, 6) == size[1]


def test_offset_a_circle_and_an_arc_chain():
    sk = Sketch([Arc.circle((0, 0), 10 * MM)])
    (i,) = sk.offset([0], 2 * MM, (0, 0))
    assert sk.shapes[i].r == 8 * MM
    sk = Sketch([Line((0, 0), (10 * MM, 0)), Arc((10 * MM, 5 * MM), 5 * MM, -math.pi / 2, math.pi)])
    new = sk.offset([0, 1], 1 * MM, (5 * MM, 3 * MM))
    line, arc = (sk.shapes[i] for i in new)
    assert near(line.b, arc.start) and abs(arc.r - 4 * MM) < 1 and line.a[1] == 1 * MM


def test_mirror_copies_across_a_line():
    sk = Sketch([Line((MM, 0), (2 * MM, MM)), Arc((3 * MM, 0), MM, 0.0, math.pi / 2)])
    new = sk.mirror([0, 1], (0, 0), (0, MM))
    assert len(sk.shapes) == 4
    assert sk.shapes[new[0]] == Line((-MM, 0), (-2 * MM, MM))
    assert near(sk.shapes[new[1]].c, (-3 * MM, 0))


def test_set_length_and_radius():
    sk = Sketch(rect())
    assert sk.set_length(0, 50 * MM)
    assert sk.shapes[0].b == (50 * MM, 0) and sk.shapes[1].a == (50 * MM, 0)
    sk = Sketch([Arc.circle((0, 0), MM), Arc((0, 0), MM, 0.0, math.pi / 2)])
    assert sk.set_radius(0, 3 * MM) and sk.shapes[0].r == 3 * MM
    start, end = sk.shapes[1].start, sk.shapes[1].end
    assert sk.set_radius(1, 2 * MM)
    assert abs(sk.shapes[1].r - 2 * MM) < 1 and near(sk.shapes[1].start, start) and near(sk.shapes[1].end, end)


def test_snap_prefers_ends_then_crossings_then_grid():
    sk = Sketch([Line((0, 0), (10 * MM, 0)), Line((5 * MM, -5 * MM), (5 * MM, 5 * MM))])
    assert sk.snap((0.2 * MM, 0.1 * MM), 0.5 * MM) == ((0, 0), "end")
    assert sk.snap((5.1 * MM, 0.1 * MM), 0.5 * MM)[1] in ("crossing", "middle")
    p, kind = sk.snap((2 * MM, 0.2 * MM), 0.5 * MM)
    assert kind == "on edge" and near(p, (2 * MM, 0))
    assert sk.snap((20.2 * MM, 20.4 * MM), 0.5 * MM, grid=MM) == ((20 * MM, 20 * MM), "grid")


def test_snap_uses_the_reference_outline():
    sk = Sketch([], reference=[Line((0, 0), (10 * MM, 0))])
    assert sk.snap((10.1 * MM, 0.1 * MM), 0.5 * MM) == ((10 * MM, 0), "end")


def test_tangent_arc_leaves_a_line_smoothly():
    arc = tangent_arc(Line((0, 0), (10 * MM, 0)), 1, (15 * MM, 5 * MM))
    assert isinstance(arc, Arc) and near(arc.c, (10 * MM, 5 * MM))
    assert near(arc.start, (10 * MM, 0)) and near(arc.end, (15 * MM, 5 * MM))
    assert abs(abs(arc.sweep) - math.pi / 2) < 1e-6
