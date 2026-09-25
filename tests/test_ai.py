from src.kora.ai import decide_ai
from src.kora.clock import Clock
from src.kora.sim import AI_STEPPE_ID, GameState
from src.kora.types import Band, Order, OrderKind, Terrain, Tribe, stay_order
from src.kora.world import axial_to_offset, make_filled_world, offset_to_axial


def _steppe_state(world, start, stock=200):
    b = Band(
        id=12,
        tribe_id=AI_STEPPE_ID,
        position=start,
        population=36,
        stock=stock,
    )
    st = GameState(
        world=world,
        clock=Clock(),
        tribes={
            1: Tribe(1, "p", 20, True),
            AI_STEPPE_ID: Tribe(AI_STEPPE_ID, "s", 20, False),
        },
        bands={12: b},
    )
    return st, b


def test_hungry_ai_moves_toward_better_tile():
    world = make_filled_world(30, 30, Terrain.STEPPE)
    valley = offset_to_axial(20, 10)
    col, row = axial_to_offset(valley)
    world._terrains[row][col] = Terrain.VALLEE
    start = offset_to_axial(8, 10)
    st, b = _steppe_state(world, start, stock=0)
    decide_ai(st)
    assert b.order.kind is OrderKind.GOTO
    assert b.path


def test_ai_keeps_current_path_instead_of_restarting():
    world = make_filled_world(30, 12, Terrain.PLAINE)
    start = offset_to_axial(2, 6)
    st, b = _steppe_state(world, start, stock=400)
    goal = offset_to_axial(20, 6)
    b.order = Order(kind=OrderKind.GOTO, target_hex=goal)
    b.path = [offset_to_axial(c, 6) for c in range(3, 21)]
    kept = list(b.path)
    st.tick_count = 4
    decide_ai(st)
    assert b.path == kept


def test_roaming_ai_does_not_always_pick_the_same_hex():
    world = make_filled_world(24, 16, Terrain.PLAINE)
    start = offset_to_axial(12, 8)
    st, b = _steppe_state(world, start, stock=400)
    st.clock.week = 35  # trop pres de l'hiver pour se scinder
    goals = set()
    for _ in range(24):
        b.path = []
        b.order = stay_order()
        b.position = start
        st.tick_count = 0
        decide_ai(st)
        if b.order.target_hex is not None:
            goals.add(b.order.target_hex)
    assert len(goals) >= 3


def test_well_fed_ai_camps_instead_of_roaming():
    world = make_filled_world(24, 16, Terrain.VALLEE)
    start = offset_to_axial(12, 8)
    st, b = _steppe_state(world, start, stock=400)
    st.clock.week = 35
    b.population = 20
    b.stock = 200
    decide_ai(st)
    assert b.order.kind is OrderKind.STAY
    assert b.position == start


def test_big_fed_ai_band_splits_and_sends_the_half_away():
    world = make_filled_world(40, 24, Terrain.PLAINE)
    start = offset_to_axial(20, 12)
    st, b = _steppe_state(world, start, stock=400)
    b.population = 40
    decide_ai(st)
    mine = [x for x in st.bands.values() if x.tribe_id == AI_STEPPE_ID]
    assert len(mine) == 2
    assert sum(x.population for x in mine) == 40
    child = next(x for x in mine if x.id != b.id)
    assert child.path


def test_ai_does_not_raid_without_a_clear_edge():
    world = make_filled_world(30, 12, Terrain.PLAINE)
    st, b = _steppe_state(world, offset_to_axial(5, 6), stock=108)  # 3 semaines
    st.clock.week = 35
    prey = Band(id=20, tribe_id=1, position=offset_to_axial(9, 6), population=33, stock=0)
    st.bands[20] = prey
    b.population = 36
    decide_ai(st)
    assert b.order.kind is not OrderKind.MARCH_TO_BAND
    prey.population = 20
    b.path = []
    b.order = stay_order()
    decide_ai(st)
    assert b.order.kind is OrderKind.MARCH_TO_BAND
    assert b.order.target_band_id == 20
