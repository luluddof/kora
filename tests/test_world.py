from pathlib import Path

from src.kora.types import Hex, Terrain
from src.kora.world import (
    HEIGHT,
    WIDTH,
    hex_distance,
    load_world,
    make_filled_world,
    offset_to_axial,
    pick_spawn_hexes,
    same_landmass,
    save_world,
)


def test_tiny_world_bounds_and_passable():
    w = make_filled_world(5, 4, Terrain.PLAINE)
    h = offset_to_axial(2, 2)
    assert w.in_bounds(h)
    assert w.passable(h)
    assert w.terrain(h) is Terrain.PLAINE
    outside = Hex(999, 999)
    assert not w.in_bounds(outside)
    assert not w.passable(outside)


def test_water_impassable():
    w = make_filled_world(3, 3, Terrain.EAU)
    h = offset_to_axial(1, 1)
    assert not w.passable(h)
    assert w.enter_cost_hex(h) is None


def test_radius_two_has_nineteen_on_open_map():
    w = make_filled_world(20, 20, Terrain.PLAINE)
    center = offset_to_axial(10, 10)
    found = w.hexes_in_radius(center, 2)
    assert len(found) == 19
    assert all(hex_distance(center, h) <= 2 for h in found)


def test_planet_constants():
    assert WIDTH == 384
    assert HEIGHT == 192


def test_save_load_roundtrip_keeps_wrap_and_desert(tmp_path: Path):
    world = make_filled_world(8, 6, Terrain.DESERT, wrap_x=True)
    path = tmp_path / "kora_map.json"
    save_world(world, path)
    loaded = load_world(path)
    assert loaded.wrap_x is True
    assert loaded.width == 8
    assert loaded.terrain(offset_to_axial(3, 2)) is Terrain.DESERT


def test_pick_spawn_finds_passable_hexes():
    world = make_filled_world(40, 24, Terrain.VALLEE, wrap_x=True)
    spots = pick_spawn_hexes(world, 4)
    assert len(spots) == 4
    assert all(world.passable(h) for h in spots)


def _two_continents():
    world = make_filled_world(28, 16, Terrain.EAU, wrap_x=False)
    for row in range(16):
        for col in range(6):
            world._terrains[row][col] = Terrain.PLAINE
        for col in range(12, 28):
            world._terrains[row][col] = Terrain.PLAINE
    return world


def test_water_splits_landmasses():
    world = _two_continents()
    west = offset_to_axial(2, 8)
    east = offset_to_axial(20, 8)
    other_west = offset_to_axial(4, 10)
    assert same_landmass(world, west, other_west)
    assert not same_landmass(world, west, east)


def test_pick_spawn_keeps_one_ai_on_player_continent():
    world = _two_continents()
    spots = pick_spawn_hexes(world, 4)
    assert len(spots) == 4
    assert len(set(spots)) == 4
    player = spots[0]
    assert any(same_landmass(world, player, other) for other in spots[1:])
