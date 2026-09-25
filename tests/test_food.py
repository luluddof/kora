from src.kora.clock import Clock
from src.kora.sim import GameState, collect_food, forage_hexes
from src.kora.types import Band, Terrain, Tribe, stay_order
from src.kora.world import make_filled_world, offset_to_axial


def _state(terrain: Terrain, pop: int, stock: float, season_week: int = 1) -> GameState:
    world = make_filled_world(15, 15, terrain)
    clock = Clock()
    clock.week = season_week
    pos = offset_to_axial(7, 7)
    band = Band(
        id=1,
        tribe_id=1,
        position=pos,
        population=pop,
        stock=stock,
        order=stay_order(),
    )
    tribe = Tribe(id=1, name="t", prestige=20, is_player=True)
    st = GameState(
        world=world,
        clock=clock,
        tribes={1: tribe},
        bands={1: band},
    )
    world.fill_season(clock.season())
    return st


def test_forage_radius_nineteen_on_plains():
    st = _state(Terrain.PLAINE, 10, 0)
    hexes = forage_hexes(st, st.bands[1])
    assert len(hexes) == 19


def test_spring_valley_small_band_does_not_starve_one_week():
    st = _state(Terrain.VALLEE, 18, 0, season_week=1)
    collect_food(st)
    assert st.bands[1].population == 18
    assert st.bands[1].stock >= 0


def test_winter_hill_no_stock_loses_people_in_four_weeks():
    st = _state(Terrain.COLLINE, 40, 0, season_week=40)
    start = st.bands[1].population
    for _ in range(4):
        collect_food(st)
        st.clock.advance_week()
    assert st.bands[1].population < start
