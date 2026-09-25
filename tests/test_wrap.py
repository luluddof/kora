from src.kora.path import astar
from src.kora.types import Terrain
from src.kora.world import (
    axial_to_offset,
    make_filled_world,
    offset_to_axial,
)


def test_east_edge_wraps_to_west():
    w = make_filled_world(10, 8, Terrain.PLAINE, wrap_x=True)
    edge = offset_to_axial(9, 4)
    cols = {axial_to_offset(n)[0] for n in w.neighbors(edge)}
    assert 0 in cols
    wrapped = w.canonicalize(offset_to_axial(10, 4))
    assert wrapped is not None
    assert axial_to_offset(wrapped)[0] == 0


def test_north_pole_does_not_wrap():
    w = make_filled_world(10, 8, Terrain.PLAINE, wrap_x=True)
    north = offset_to_axial(4, 0)
    rows = {axial_to_offset(n)[1] for n in w.neighbors(north)}
    assert min(rows) >= 0
    assert w.canonicalize(offset_to_axial(4, -1)) is None


def test_astar_wraps_east_west():
    w = make_filled_world(10, 8, Terrain.PLAINE, wrap_x=True)
    a = offset_to_axial(9, 4)
    b = offset_to_axial(0, 4)
    path = astar(w, a, b)
    assert path is not None
    assert len(path) == 1
    assert path[-1] == b


def test_radius_wraps_across_date_line():
    w = make_filled_world(20, 12, Terrain.PLAINE, wrap_x=True)
    edge = offset_to_axial(0, 6)
    found = {axial_to_offset(h)[0] for h in w.hexes_in_radius(edge, 2)}
    assert 19 in found
    assert 1 in found
