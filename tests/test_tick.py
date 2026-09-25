import time

from src.kora.globe import FOCUS_ZOOM, hex_to_globe_screen, look_at_hex, view_params
from src.kora.path import astar, travel_weeks
from src.kora.sim import PLAYER_TRIBE_ID, _restore, new_game, player_home_hex, snapshot, tick
from src.kora.types import Terrain
from src.kora.world import make_filled_world, offset_to_axial


def _valley():
    return make_filled_world(40, 24, Terrain.VALLEE, wrap_x=True)


def test_new_game_kora_has_player_bands():
    st = new_game(_valley())
    assert st.clock.week == 1
    assert st.clock.paused is True
    player_bands = [b for b in st.bands.values() if b.tribe_id == 1]
    assert len(player_bands) == 1
    assert sum(b.population for b in player_bands) == 40
    assert len(st.tribes) == 4
    assert sum(1 for t in st.tribes.values() if t.is_player) == 1
    ai_bands = [b for b in st.bands.values() if b.tribe_id != 1]
    assert len(ai_bands) == 3
    assert all(b.population > 0 for b in ai_bands)
    assert all(not st.tribes[b.tribe_id].is_player for b in ai_bands)
    assert len({b.position for b in st.bands.values()}) == 4


def test_new_game_player_tribe_is_centered_on_screen():
    st = new_game(_valley())
    home = player_home_hex(st)
    assert home is not None
    yaw, pitch = look_at_hex(home, st.world.width, st.world.height)
    cx, cy, focal, dist = view_params(FOCUS_ZOOM, 1280, 720, 48)
    pos = hex_to_globe_screen(home, st.world, yaw, pitch, cx, cy, focal, dist)
    assert pos is not None
    assert abs(pos[0] - cx) < 80
    assert abs(pos[1] - cy) < 80
    band = next(b for b in st.bands.values() if b.tribe_id == PLAYER_TRIBE_ID)
    assert band.position == home


def test_path_twelve_plains_three_weeks():
    w = make_filled_world(20, 8, Terrain.PLAINE)
    start = offset_to_axial(1, 3)
    goal = offset_to_axial(13, 3)
    path = astar(w, start, goal)
    assert path is not None
    assert len(path) == 12
    assert travel_weeks(w, start, path) == 3


def test_four_ticks_on_kora_do_not_crash():
    st = new_game(_valley())
    st.clock.paused = False
    for _ in range(4):
        tick(st)
    assert st.last_error is None
    assert st.clock.week == 5


def test_snapshot_on_large_world_is_fast_and_restores():
    world = make_filled_world(384, 192, Terrain.PLAINE, wrap_x=True)
    st = new_game(world)
    t0 = time.perf_counter()
    saved = snapshot(st)
    assert time.perf_counter() - t0 < 0.04
    before = st.bands[1].population
    st.bands[1].population = 0
    _restore(st, saved)
    assert st.bands[1].population == before
    assert st.world is world


def test_speed_five_does_not_burst_missed_ticks():
    from src.kora.sim import consume_ticks

    st = new_game(_valley())
    st.clock.paused = False
    st.clock.set_speed(5)
    week0 = st.clock.week
    acc = consume_ticks(st, 0.0, dt=4.0)
    assert st.clock.week - week0 <= 2
    assert acc <= 2.0
    assert st.last_error is None
