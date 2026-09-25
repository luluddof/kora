from src.kora.path import astar, travel_weeks
from src.kora.types import Terrain
from src.kora.world import hex_distance, make_filled_world, offset_to_axial


def test_astar_plain_line_length():
    w = make_filled_world(20, 8, Terrain.PLAINE)
    start = offset_to_axial(1, 3)
    goal = offset_to_axial(13, 3)
    path = astar(w, start, goal)
    assert path is not None
    assert path[-1] == goal
    assert start not in path
    assert len(path) == hex_distance(start, goal)


def test_twelve_plains_hexes_are_three_weeks():
    w = make_filled_world(20, 8, Terrain.PLAINE)
    start = offset_to_axial(1, 3)
    goal = offset_to_axial(13, 3)
    path = astar(w, start, goal)
    assert path is not None
    assert len(path) == 12
    assert travel_weeks(w, start, path) == 3


def test_water_blocks():
    w = make_filled_world(6, 6, Terrain.EAU)
    a = offset_to_axial(1, 1)
    b = offset_to_axial(4, 4)
    assert astar(w, a, b) is None


def test_same_hex_empty_path_zero_weeks():
    w = make_filled_world(4, 4, Terrain.PLAINE)
    h = offset_to_axial(1, 1)
    path = astar(w, h, h)
    assert path == []
    assert travel_weeks(w, h, path) == 0


def test_astar_respects_max_cost():
    w = make_filled_world(20, 8, Terrain.PLAINE)
    start = offset_to_axial(1, 3)
    goal = offset_to_axial(13, 3)
    assert astar(w, start, goal, max_cost=50) is None
    found = astar(w, start, goal, max_cost=200)
    assert found is not None
    assert found[-1] == goal


def test_astar_respects_max_nodes():
    w = make_filled_world(30, 10, Terrain.PLAINE)
    start = offset_to_axial(0, 5)
    goal = offset_to_axial(29, 5)
    assert astar(w, start, goal, max_nodes=4) is None
    found = astar(w, start, goal, max_nodes=400)
    assert found is not None
    assert found[-1] == goal
