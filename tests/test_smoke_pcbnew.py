"""Headless check that generated outlines are valid KiCad board edges."""

import pytest

pcbnew = pytest.importorskip("pcbnew")

from qol_kicad.generators import rounded_rect, slot  # noqa: E402
from qol_kicad.geom import Line  # noqa: E402
from qol_kicad.outline import fillet_all  # noqa: E402

MM = 1e6


def _add(board, s):
    item = pcbnew.PCB_SHAPE(board)
    item.SetLayer(pcbnew.Edge_Cuts)

    def v(p):
        return pcbnew.VECTOR2I(int(round(p[0])), int(round(p[1])))

    if isinstance(s, Line):
        item.SetShape(pcbnew.SHAPE_T_SEGMENT)
        item.SetStart(v(s.a))
        item.SetEnd(v(s.b))
    else:
        item.SetShape(pcbnew.SHAPE_T_ARC)
        item.SetArcGeometry(v(s.start), v(s.mid), v(s.end))
    board.Add(item)


def test_outline_is_a_closed_board_edge(tmp_path):
    shapes, done, _ = fillet_all(rounded_rect((100 * MM, 100 * MM), 50 * MM, 30 * MM), 3 * MM)
    assert done == 4
    shapes += slot((100 * MM, 100 * MM), 12 * MM, 3 * MM)
    board = pcbnew.BOARD()
    for s in shapes:
        _add(board, s)
    path = str(tmp_path / "b.kicad_pcb")
    pcbnew.SaveBoard(path, board)
    board = pcbnew.LoadBoard(path)
    outlines = pcbnew.SHAPE_POLY_SET()
    assert board.GetBoardPolygonOutlines(outlines, False)
    assert outlines.OutlineCount() == 1 and outlines.HoleCount(0) == 1
    box = board.GetBoardEdgesBoundingBox()
    assert box.GetWidth() == pytest.approx(50.1 * MM, abs=0.01 * MM)
    assert box.GetHeight() == pytest.approx(30.1 * MM, abs=0.01 * MM)
