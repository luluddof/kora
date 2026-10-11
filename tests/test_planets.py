"""0.20 : les nouvelles planetes (planets.py) : registre, sauvegarde, departs
au hasard sur les continents, courant des rivieres, sols, ressources
cachees, champs au bord de l'eau, nouveaux metiers."""

import functools
import random

from src.kora import goods, planets, villages
from src.kora.path import astar
from src.kora.persist import game_from_json, map_id
from src.kora.resources import hidden_for
from src.kora.types import Hex, Terrain, Tribe
from src.kora.world import (
    FORD_PCT,
    MOVE_COST,
    NEIGHBOR_DELTAS,
    RIVER_PCT,
    World,
    axial_to_offset,
    landmass_grid,
    offset_to_axial,
    pick_spawn_continents,
    step_cost,
)


@functools.lru_cache(maxsize=None)
def _planet(pid: str):
    return planets.load(pid)


def test_the_game_ships_several_planets_and_the_old_map():
    ids = planets.ids()
    assert len(ids) >= 3 and planets.default_id() == ids[0]
    world = _planet(ids[0])
    assert (world.width, world.height) == (1536, 768) and world.planet == ids[0]
    assert world.rivers and world.resources.get("cuivre")
    legacy = planets.load(planets.LEGACY)
    assert (legacy.width, legacy.height) == (768, 384) and not legacy.rivers
    assert planets.choose("hasard", random.Random(3)) in ids
    assert planets.choose(ids[1], random.Random(3)) == ids[1]


def test_a_save_finds_its_own_planet():
    """Une partie notee sur sa planete se recharge dessus, meme si on propose
    une autre carte ; une sauvegarde d'avant 0.20 (sans id) est sur l'ancienne."""
    data = {"version": 0, "map": {"width": 1536, "height": 768}}
    assert map_id(data) == planets.LEGACY
    data["map"]["id"] = planets.ids()[1]
    assert map_id(data) == planets.ids()[1]
    from src.kora import persist
    from src.kora.sim import new_game

    st = new_game(_fresh(planets.ids()[1]), minor_peoples=0, setup={"seed": 5})
    text = persist.dumps_game(st)
    loaded, _view = persist.loads_game(text, planets.load(planets.LEGACY))
    assert loaded.world.planet == planets.ids()[1] and loaded.world.width == 1536
    assert game_from_json({"version": -1}, None) is None


def _fresh(pid):
    return planets.load(pid)


def test_every_people_starts_at_random_on_a_continent():
    """Le joueur aussi : d'une graine a l'autre, son continent change ; la
    meme graine donne les memes departs (le multijoueur)."""
    world = _planet(planets.ids()[0])
    grid = landmass_grid(world)

    def mass(h):
        c, r = axial_to_offset(h)
        return grid[r][c]

    seen = set()
    for seed in range(8):
        spots = pick_spawn_continents(world, 4, random.Random(seed))
        assert spots == pick_spawn_continents(world, 4, random.Random(seed))
        assert all(world.passable(h) for h in spots)
        assert all(world.distance(a, b) >= 40 for i, a in enumerate(spots) for b in spots[i + 1:])
        seen.add(mass(spots[0]))
    assert len(seen) >= 2, "le joueur part toujours sur le même continent"


def _river_world():
    """Une plaine traversee par une riviere qui coule vers l'est (rangee 5)."""
    w, h = 20, 11
    grid = [[Terrain.PLAINE for _ in range(w)] for _ in range(h)]
    world = World(grid)
    layer = bytearray(w * h)
    for col in range(2, 18):
        layer[5 * w + col] = (0 + 1) | (2 << 3)  # vers l'est, une riviere
    world.set_rivers(bytes(layer))
    return world


def test_the_current_helps_downstream_and_slows_upstream():
    world = _river_world()
    a, b = offset_to_axial(5, 5), offset_to_axial(6, 5)
    plain = MOVE_COST[Terrain.PLAINE]
    down = step_cost(world, a, b, False)
    up = step_cost(world, b, a, False)
    assert down < up
    assert down == world_cost(world, b) * RIVER_PCT[0] // 100
    assert up == world_cost(world, a) * RIVER_PCT[3] // 100
    # Hors du cours : rien ; entrer dans la riviere de loin : un gue.
    far1, far2 = offset_to_axial(5, 1), offset_to_axial(6, 1)
    assert step_cost(world, far1, far2, False) == world_cost(world, far2)
    north = offset_to_axial(5, 3)
    bank = offset_to_axial(5, 4)
    assert step_cost(world, north, bank, False) == world_cost(world, bank)
    assert plain > 0 and FORD_PCT > 100
    # A* prend la riviere dans le sens du courant.
    path = astar(world, offset_to_axial(3, 5), offset_to_axial(16, 5))
    assert path and all(axial_to_offset(h)[1] in (4, 5, 6) for h in path)


def world_cost(world, h):
    from src.kora.world import enter_cost_for

    return enter_cost_for(world, h, False)


def test_copper_and_tin_hide_until_known():
    tribe = Tribe(1, "Kora", 20, True)
    assert {"cuivre", "etain"} <= hidden_for(tribe)
    tribe.knowledge.add("cuivre")
    assert "cuivre" not in hidden_for(tribe) and "etain" in hidden_for(tribe)
    assert hidden_for(None) == frozenset()


def test_new_soils_have_every_rule():
    from src.kora import battle, influence, look
    from src.kora.world import BIOME_INDEX

    for soil in (Terrain.TOUNDRA, Terrain.MARAIS, Terrain.JUNGLE, Terrain.SAVANE):
        assert soil in MOVE_COST and soil in BIOME_INDEX and soil in look.BIOME_COLORS
        assert soil in influence.PROJECTION and soil in battle.PLACE
    assert Terrain.GLACE not in MOVE_COST, "la glace ne se traverse pas"


def test_rivers_feed_the_fields_and_new_crafts_have_effects():
    from test_approach import _state

    st = _state()
    site = next(s for s in st.sites.values() if s.kind == "village")
    h = site.hex
    dry = villages.fertility(st, site.tribe_id, h)
    w, hh = st.world.width, st.world.height
    layer = bytearray(w * hh)
    col, row = axial_to_offset(h)
    layer[row * w + col] = 1 | (2 << 3)
    st.world.set_rivers(bytes(layer))
    wet = villages.fertility(st, site.tribe_id, h)
    if dry > 0:
        assert abs(wet / dry - villages.RIVER_FIELDS) < 1e-6
    tid = site.tribe_id
    base = goods.army_mult(st, tid)
    st.tribes[tid].goods["lames"] = 5.0
    assert abs(goods.army_mult(st, tid) / base - 1.08) < 1e-6
    st.tribes[tid].goods["teintures"] = 5.0
    assert ("Teintures", 3.0) in goods.stability_parts(st, tid)
    assert goods.winter_prestige(st, tid) >= 1
    assert NEIGHBOR_DELTAS and Hex(0, 0)
