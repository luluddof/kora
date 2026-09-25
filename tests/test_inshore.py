from src.kora.path import astar, travel_weeks
from src.kora.types import Terrain
from src.kora.world import (
    INSHORE_MOVE_COST,
    enter_cost_for,
    is_inshore,
    make_filled_world,
    offset_to_axial,
)


def _coast_world():
    world = make_filled_world(10, 8, Terrain.PLAINE)
    for col in range(10):
        world._terrains[3][col] = Terrain.COTE
    for row in range(4, 8):
        for col in range(10):
            world._terrains[row][col] = Terrain.EAU
    return world


def test_water_touching_land_is_inshore():
    world = _coast_world()
    shore = offset_to_axial(2, 4)
    assert world.terrain(shore) is Terrain.EAU
    assert is_inshore(world, shore)
    assert not world.passable(shore)
    assert enter_cost_for(world, shore, False) is None
    assert enter_cost_for(world, shore, True) == INSHORE_MOVE_COST


def test_open_ocean_is_not_inshore():
    world = _coast_world()
    deep = offset_to_axial(2, 6)
    assert world.terrain(deep) is Terrain.EAU
    assert not is_inshore(world, deep)
    assert enter_cost_for(world, deep, True) is None


def test_land_is_not_inshore():
    world = _coast_world()
    land = offset_to_axial(2, 2)
    assert not is_inshore(world, land)
    assert enter_cost_for(world, land, False) == 10


def test_astar_blocks_inshore_without_flag():
    world = _coast_world()
    start = offset_to_axial(2, 3)
    goal = offset_to_axial(2, 4)
    assert astar(world, start, goal) is None
    assert astar(world, start, goal, water_ok=False) is None


def test_astar_allows_inshore_with_flag_not_ocean():
    world = _coast_world()
    start = offset_to_axial(2, 3)
    shore = offset_to_axial(2, 4)
    deep = offset_to_axial(2, 6)
    path = astar(world, start, shore, water_ok=True)
    assert path is not None
    assert path[-1] == shore
    assert astar(world, start, deep, water_ok=True) is None


def test_travel_weeks_counts_inshore_like_plain():
    world = _coast_world()
    start = offset_to_axial(1, 3)
    path = [offset_to_axial(1, 4)]
    assert travel_weeks(world, start, path, water_ok=True) == 1
    assert travel_weeks(world, start, path, water_ok=False) == 0
