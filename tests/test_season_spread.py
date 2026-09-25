from src.kora.sim import new_game, tick
from src.kora.types import Season, Terrain
from src.kora.world import make_filled_world, offset_to_axial


def test_winter_does_not_cover_the_map_on_the_first_step():
    world = make_filled_world(20, 16, Terrain.PLAINE)
    world.fill_season(Season.PRINTEMPS)
    world.seed_season(Season.HIVER)
    assert world.hex_season(offset_to_axial(10, 0)) is Season.HIVER
    mid = offset_to_axial(10, 8)
    assert world.hex_season(mid) is Season.PRINTEMPS
    world.spread_season(Season.HIVER, steps=1)
    assert world.hex_season(mid) is Season.PRINTEMPS
    assert world.hex_season(offset_to_axial(10, 1)) is Season.HIVER


def test_season_reaches_every_hex_after_enough_steps():
    world = make_filled_world(12, 10, Terrain.PLAINE)
    world.fill_season(Season.PRINTEMPS)
    world.seed_season(Season.HIVER)
    world.spread_season(Season.HIVER, steps=20)
    for row in range(world.height):
        for col in range(world.width):
            assert world.hex_season(offset_to_axial(col, row)) is Season.HIVER


def test_tick_spreads_summer_from_the_middle_not_the_poles():
    world = make_filled_world(24, 40, Terrain.PLAINE)
    st = new_game(world)
    st.clock.week = 13
    tick(st)
    assert st.clock.season() is Season.ETE
    assert st.world.hex_season(offset_to_axial(10, 20)) is Season.ETE
    assert st.world.hex_season(offset_to_axial(10, 0)) is Season.PRINTEMPS
