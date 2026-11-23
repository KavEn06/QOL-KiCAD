from qol_kicad.geom import Arc, Line
from qol_kicad.sketch.model import Sketch
from qol_kicad.sketch.tools import Controller, parse_numbers

MM = 1e6


def make(shapes=()):
    c = Controller(Sketch(shapes))
    c.grid = 0.0
    return c


def click(c, x, y, shift=False):
    p = (x * MM, y * MM)
    c.move(p, shift)
    c.press(p, shift)
    c.release(p, shift)


def rect():
    pts = [(0, 0), (40 * MM, 0), (40 * MM, 30 * MM), (0, 30 * MM)]
    return [Line(a, b) for a, b in zip(pts, pts[1:] + pts[:1])]


def test_parse_numbers():
    assert parse_numbers("30") == ("", [30.0])
    assert parse_numbers("30<45") == ("<", [30.0, 45.0])
    assert parse_numbers(" 10, 5 ") == (",", [10.0, 5.0])
    assert parse_numbers("abc") is None


def test_line_chain_closes_and_stops():
    c = make()
    c.set_tool("line")
    for x, y in [(0, 0), (10, 0), (10, 10), (0, 0)]:
        click(c, x, y)
    assert len(c.sketch.shapes) == 3 and c.points == []
    c.undo()
    assert len(c.sketch.shapes) == 2


def test_line_by_typed_length_and_angle():
    c = make()
    c.set_tool("line")
    click(c, 0, 0)
    c.move((5 * MM, 0))
    assert c.enter("30")
    assert c.sketch.shapes[0] == Line((0, 0), (30 * MM, 0))
    assert c.enter("10<90")
    end = c.sketch.shapes[1].b
    assert abs(end[0] - 30 * MM) < 1 and abs(end[1] + 10 * MM) < 1  # 90 degrees is up
    assert c.enter("5,5")
    assert len(c.sketch.shapes) == 3


def test_shift_keeps_lines_horizontal_or_vertical():
    c = make()
    c.set_tool("line")
    click(c, 0, 0)
    click(c, 20, 1.5, shift=True)
    assert c.sketch.shapes[0] == Line((0, 0), (20 * MM, 0))


def test_circle_rect_and_arc():
    c = make()
    c.set_tool("circle")
    click(c, 0, 0)
    assert c.enter("5")
    assert c.sketch.shapes[0] == Arc.circle((0, 0), 5 * MM)
    c.set_tool("rect")
    click(c, 20, 20)
    c.move((30 * MM, 30 * MM))
    assert c.enter("10,4")
    assert len(c.sketch.shapes) == 5
    c.set_tool("arc")
    for x, y in [(50, 0), (60, 0), (55, 5)]:
        click(c, x, y)
    arc = c.sketch.shapes[-1]
    assert isinstance(arc, Arc) and abs(arc.r - 5 * MM) < 1


def test_tangent_arc_needs_an_edge_end():
    c = make([Line((0, 0), (10 * MM, 0))])
    c.set_tool("tangent")
    click(c, 50, 50)
    assert c.message and len(c.sketch.shapes) == 1
    click(c, 10, 0)
    click(c, 15, 5)
    assert isinstance(c.sketch.shapes[1], Arc)


def test_drag_a_corner_and_undo_in_one_step():
    c = make(rect())
    c.press((40 * MM, 0))
    c.move((45 * MM, -5 * MM))
    c.release((45 * MM, -5 * MM))
    assert c.sketch.shapes[0].b == (45 * MM, -5 * MM) and c.sketch.shapes[1].a == (45 * MM, -5 * MM)
    c.undo()
    assert c.sketch.shapes == rect()


def test_drag_an_edge_and_a_plain_click_is_not_an_undo_step():
    c = make(rect())
    click(c, 40, 15)
    assert c.selection == {1} and not c.sketch.undo()
    c.press((40 * MM, 15 * MM))
    c.move((50 * MM, 15 * MM))
    c.release((50 * MM, 15 * MM))
    assert c.sketch.shapes[1] == Line((50 * MM, 0), (50 * MM, 30 * MM))
    assert c.sketch.shapes[0].b == (50 * MM, 0)


def test_box_select_and_delete():
    c = make(rect() + [Line((100 * MM, 0), (110 * MM, 0))])
    c.press((-5 * MM, -5 * MM))
    c.move((45 * MM, 35 * MM))
    c.release((45 * MM, 35 * MM))
    assert c.selection == {0, 1, 2, 3}
    c.delete_selection()
    assert len(c.sketch.shapes) == 1


def test_fillet_uses_the_typed_radius():
    c = make(rect())
    c.set_tool("fillet")
    assert c.enter("5")
    click(c, 40, 0)
    arcs = [s for s in c.sketch.shapes if isinstance(s, Arc)]
    assert len(arcs) == 1 and abs(arcs[0].r - 5 * MM) < 1
    click(c, 20, 15)
    assert c.message  # no corner there, and no stray undo step
    c.undo()
    assert c.sketch.shapes == rect()


def test_offset_and_mirror_use_the_selection():
    c = make(rect())
    c.select_all()
    c.set_tool("offset")
    c.select_all()
    c.enter("2")
    click(c, 20, 15)
    assert len(c.sketch.shapes) == 8
    c = make([Line((10 * MM, 0), (20 * MM, 0))])
    c.select_all()
    c.tool = "mirror"
    click(c, 0, 50)
    click(c, 0, 60)
    assert c.sketch.shapes[1] == Line((-10 * MM, 0), (-20 * MM, 0))


def test_dimension_sets_a_length():
    c = Controller(Sketch(rect()), ask_value=lambda label, current: 50.0)
    c.grid = 0.0
    c.set_tool("dimension")
    click(c, 20, 0)
    assert c.sketch.shapes[0].b == (50 * MM, 0) and c.sketch.shapes[1].a == (50 * MM, 0)


def test_placing_ready_made_shapes():
    c = make()
    c.place([Arc.circle((0, 0), MM)])
    click(c, 7, 8)
    assert c.sketch.shapes == [Arc.circle((7 * MM, 8 * MM), MM)] and not c.placing


def test_escape_cancels_then_returns_to_select():
    c = make()
    c.set_tool("line")
    click(c, 0, 0)
    c.escape()
    assert c.points == [] and c.tool == "line"
    c.escape()
    assert c.tool == "select"
