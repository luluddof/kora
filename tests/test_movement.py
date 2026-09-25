from src.kora.clock import Clock
from src.kora.sim import GameState, apply_movement, set_goto, set_march_to_band
from src.kora.types import Band, OrderKind, Terrain, Tribe
from src.kora.world import hex_distance, make_filled_world, offset_to_axial


def test_goto_moves_four_plains_in_one_week():
    world = make_filled_world(20, 8, Terrain.PLAINE)
    start = offset_to_axial(1, 3)
    goal = offset_to_axial(9, 3)
    band = Band(id=1, tribe_id=1, position=start, population=10, stock=40)
    st = GameState(
        world=world,
        clock=Clock(),
        tribes={1: Tribe(1, "t", 20, True)},
        bands={1: band},
    )
    set_goto(st, 1, goal)
    apply_movement(st)
    assert hex_distance(start, band.position) == 4
    apply_movement(st)
    assert band.position == goal


def test_invalid_goto_ignored():
    world = make_filled_world(6, 6, Terrain.PLAINE)
    start = offset_to_axial(1, 1)
    band = Band(id=1, tribe_id=1, position=start, population=10, stock=40)
    st = GameState(
        world=world,
        clock=Clock(),
        tribes={1: Tribe(1, "t", 20, True)},
        bands={1: band},
    )
    set_goto(st, 1, offset_to_axial(99, 99))
    assert band.order.kind is OrderKind.STAY or band.path == []
    assert band.position == start


def test_goto_missing_band_does_not_crash():
    world = make_filled_world(6, 6, Terrain.PLAINE)
    st = GameState(
        world=world,
        clock=Clock(),
        tribes={1: Tribe(1, "t", 20, True)},
        bands={},
    )
    set_goto(st, 2, offset_to_axial(2, 2))
    assert st.bands == {}


def test_set_goto_same_goal_keeps_existing_path():
    world = make_filled_world(20, 8, Terrain.PLAINE)
    start = offset_to_axial(1, 3)
    goal = offset_to_axial(13, 3)
    band = Band(id=1, tribe_id=1, position=start, population=10, stock=40)
    st = GameState(
        world=world,
        clock=Clock(),
        tribes={1: Tribe(1, "t", 20, True)},
        bands={1: band},
    )
    set_goto(st, 1, goal)
    first = band.path
    assert first
    set_goto(st, 1, goal)
    assert band.path is first


def test_march_missing_actor_does_not_crash():
    world = make_filled_world(6, 6, Terrain.PLAINE)
    target = Band(id=3, tribe_id=2, position=offset_to_axial(2, 2), population=10, stock=40)
    st = GameState(
        world=world,
        clock=Clock(),
        tribes={1: Tribe(1, "t", 20, True), 2: Tribe(2, "e", 20, False)},
        bands={3: target},
    )
    set_march_to_band(st, 2, 3)
    assert 3 in st.bands

