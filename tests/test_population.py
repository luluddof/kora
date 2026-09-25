from src.kora.clock import Clock
from src.kora.sim import GameState, update_population
from src.kora.types import Band, Terrain, Tribe
from src.kora.world import make_filled_world, offset_to_axial


def test_fed_band_grows():
    world = make_filled_world(8, 8, Terrain.VALLEE)
    b = Band(id=1, tribe_id=1, position=offset_to_axial(3, 3), population=40, stock=160)
    b.famine_in_period = False
    st = GameState(
        world=world,
        clock=Clock(),
        tribes={1: Tribe(1, "t", 20, True)},
        bands={1: b},
        tick_count=4,
    )
    # 1,8 % par mois : un de plus au bout de deux mois.
    update_population(st)
    st.tick_count = 8
    update_population(st)
    assert b.population == 41


def test_famine_band_does_not_grow():
    world = make_filled_world(8, 8, Terrain.VALLEE)
    b = Band(id=1, tribe_id=1, position=offset_to_axial(3, 3), population=40, stock=0)
    b.famine_in_period = True
    st = GameState(
        world=world,
        clock=Clock(),
        tribes={1: Tribe(1, "t", 20, True)},
        bands={1: b},
    )
    update_population(st)
    assert b.population == 40
    assert b.famine_in_period is False
