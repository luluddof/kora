"""Ressources du pays : plusieurs par case, cuites avec la carte."""

import functools

from src.kora import resources, tech
from src.kora.clock import Clock
from src.kora.mapgen import generate_world
from src.kora.sim import GameState, _default_world
from src.kora.types import Band, Season, Terrain, Tribe
from src.kora.world import food_production, make_filled_world, offset_to_axial


@functools.lru_cache(maxsize=1)
def _map():
    return _default_world()


def test_the_baked_map_carries_every_resource_in_sensible_amounts():
    world = _map()
    assert set(world.resources) == set(resources.NAMES)
    n = world.width * world.height
    land = [
        i
        for i in range(0, n, 7)
        if world._terrains[i // world.width][i % world.width] not in (Terrain.EAU, Terrain.SOMMET)
    ]
    for name in resources.NAMES:
        layer = world.resources[name]
        share = sum(1 for i in land if layer[i] >= resources.PRESENT_BYTE) / len(land)
        target = resources.COVER[name]
        assert target * 0.6 < share < target * 1.6, (name, share)


def test_one_hex_can_hold_several_resources():
    world = _map()
    rich = 0
    for row in range(0, world.height, 3):
        for col in range(0, world.width, 3):
            h = offset_to_axial(col, row)
            here = [n for n in resources.NAMES if world.resource(h, n) >= resources.PRESENT]
            if len(here) >= 2:
                rich += 1
                assert world.resource_lines(h)[0].startswith("Ressources : ")
    assert rich > 50


def test_resources_do_not_change_the_relief():
    plain = generate_world(5, 96, 48)
    rich = generate_world(5, 96, 48, resources=True)
    assert plain._terrains == rich._terrains
    assert rich.resources and not plain.resources


def test_game_and_plants_make_the_land_richer():
    world = _map()
    best = None
    for row in range(0, world.height, 2):
        for col in range(0, world.width, 2):
            if world._rich[row * world.width + col] > 130 and world._terrains[row][col] is Terrain.PLAINE:
                best = offset_to_axial(col, row)
                break
        if best:
            break
    assert best is not None
    bare = make_filled_world(4, 4, Terrain.PLAINE)
    assert food_production(world, best, Season.ETE, exhaustion=1.0) > food_production(
        bare, offset_to_axial(1, 1), Season.ETE, exhaustion=1.0
    ) * 1.12


def test_living_near_a_resource_counts_for_knowledge():
    world = _map()
    spot = None
    for row in range(world.height // 4, 3 * world.height // 4):
        for col in range(0, world.width, 2):
            h = offset_to_axial(col, row)
            if world.resource(h, "cereales") >= 0.6 and world.terrain(h) not in (Terrain.EAU, Terrain.SOMMET):
                spot = h
                break
        if spot:
            break
    tribe = Tribe(1, "t", 20, True, knowledge=set(tech.START_KNOWLEDGE))
    band = Band(1, 1, spot, 40, 100.0)
    st = GameState(world=world, clock=Clock(), tribes={1: tribe}, bands={1: band})
    st.world.fill_season(st.clock.season())
    for _ in range(3):
        tech.update_practice(st)
    assert tribe.practice["res:cereales"] == 3
    label = tech.cond_progress(st, tribe, tech.TECHS["semis"].conds[2])[2]
    assert "cereales" in label
