

def test_polygon_is_closed_with_corners_on_the_circle():
    import math

    import pytest

    from qol_kicad.generators import polygon

    shapes = polygon((0.0, 0.0), 6, 20.0)
    assert len(shapes) == 6
    for a, b in zip(shapes, shapes[1:] + shapes[:1]):
        assert math.dist(a.b, b.a) < 1e-6
        assert math.hypot(*a.a) == pytest.approx(10.0)
    with pytest.raises(ValueError):
        polygon((0.0, 0.0), 2, 20.0)
