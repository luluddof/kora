"""Equilibrage sur la vraie carte (LENT, ~30 s).

Un joueur-robot "raisonnable" joue plusieurs annees : il cherche la
meilleure collecte, prepare l'hiver (vers l'equateur, ou l'hiver est
court), se scinde au printemps et evite les voisins plus forts.
Ces tests disent : bien jouer fait grandir la tribu, ne rien faire la
laisse petite, et les IA restent en vie.

Lancer sans eux : pytest tests/ -q -m "not slow"
"""

import random

import pytest

from src.kora.sim import (
    PLAYER_TRIBE_ID,
    _default_world,
    _herd_ok,
    new_game,
    set_goto,
    side_force,
    split_band,
    tick,
)
from src.kora import tech
from src.kora.types import Season
from src.kora.world import axial_to_offset, enter_cost_for, food_production

pytestmark = pytest.mark.slow


def _forage(st, h, season, herd):
    return sum(
        food_production(st.world, x, season, herd=herd)
        for x in st.world.hexes_in_radius(h, 2)
    )


def _robot(st):
    if st.tick_count % 4:
        return
    # Le robot apprend les savoirs disponibles, comme l'IA.
    tech.auto_choose(st, PLAYER_TRIBE_ID)
    herd = _herd_ok(st, PLAYER_TRIBE_ID)
    water = st.tribes[PLAYER_TRIBE_ID].cabotage
    wait = st.clock.weeks_until_winter()
    prep = wait <= 6 or st.clock.week >= 40
    mid = st.world.height / 2

    def score(h):
        if prep:
            _col, row = axial_to_offset(h)
            return _forage(st, h, Season.HIVER, herd) + 12 * (1 - abs(row - mid) / mid)
        return _forage(st, h, st.world.hex_season(h), herd)

    own = [b for b in st.bands.values() if b.tribe_id == PLAYER_TRIBE_ID]
    for band in own:
        if band.population >= 30 and band.stock / band.population >= 2 and wait >= 10:
            split_band(st, band.id)
    own = [b for b in st.bands.values() if b.tribe_id == PLAYER_TRIBE_ID]
    enemies = [b for b in st.bands.values() if b.tribe_id != PLAYER_TRIBE_ID]
    for band in own:
        if band.path:
            continue
        others = [o.position for o in own if o.id != band.id]
        others += [o.path[-1] for o in own if o.id != band.id and o.path]
        crowded = any(st.world.distance(band.position, p) < 5 for p in others)
        best, best_val = None, score(band.position) - (15 if crowded else 0)
        mine = side_force(st, band)
        for h in st.world.hexes_in_radius(band.position, 16)[::4]:
            if enter_cost_for(st.world, h, water) is None:
                continue
            if any(st.world.distance(h, p) < 5 for p in others):
                continue
            if any(
                st.world.distance(h, e.position) < 7 and side_force(st, e) > mine
                for e in enemies
            ):
                continue
            val = score(h)
            if val > best_val + 3:
                best, best_val = h, val
        if best is not None:
            set_goto(st, band.id, best)


def _play(years, robot, seed=1):
    st = new_game(_default_world())
    st.rng = random.Random(seed)
    yearly = []
    for _ in range(52 * years):
        if robot:
            _robot(st)
        tick(st)
        st.clock.paused = False
        assert st.last_error is None
        if st.clock.week == 1:
            yearly.append(
                {
                    tid: sum(b.population for b in st.bands.values() if b.tribe_id == tid)
                    for tid in st.tribes
                }
            )
    return st, yearly


@pytest.fixture(scope="module")
def robot_game():
    return _play(6, robot=True)


@pytest.fixture(scope="module")
def idle_game():
    return _play(3, robot=False)


@pytest.fixture(scope="module")
def robot_seeds(robot_game):
    # Une seule partie est une piece qu'on lance (raids, chefs, evenements) :
    # la croissance se juge sur la moyenne de quatre graines.
    return [robot_game] + [_play(6, robot=True, seed=seed) for seed in (2, 3, 4)]


def test_good_play_grows_the_tribe_well_past_one_band(robot_game, robot_seeds):
    st, yearly = robot_game
    assert not st.player_dead
    finals = [y[-1][PLAYER_TRIBE_ID] for _st, y in robot_seeds]
    assert sum(finals) / len(finals) >= 120, finals
    assert min(finals) >= 80, finals
    assert sum(1 for b in st.bands.values() if b.tribe_id == PLAYER_TRIBE_ID) >= 4


def test_the_first_winter_does_not_wipe_out_the_starting_band(robot_game, idle_game):
    for _st, yearly in (robot_game, idle_game):
        assert yearly[0][PLAYER_TRIBE_ID] >= 20


def test_doing_nothing_leaves_the_tribe_small(robot_game, idle_game):
    _st, robot_years = robot_game
    _st, idle_years = idle_game
    assert idle_years[2][PLAYER_TRIBE_ID] <= 60
    assert robot_years[2][PLAYER_TRIBE_ID] >= idle_years[2][PLAYER_TRIBE_ID] + 30


def test_ai_tribes_stay_alive_and_grow(robot_game):
    st, yearly = robot_game
    ai = [tid for tid, t in st.tribes.items() if not t.is_player]
    assert all(yearly[-1][tid] > 0 for tid in ai)
    assert sum(yearly[-1][tid] for tid in ai) >= 150


def test_the_tribe_progresses_through_the_era(robot_game):
    st, _yearly = robot_game
    known = st.tribes[PLAYER_TRIBE_ID].knowledge
    learned = known - set(tech.START_KNOWLEDGE)
    # Six ans de jeu raisonnable : tous les premiers savoirs ou presque,
    # et deja des savoirs du clan.
    assert len(learned) >= 6
    assert sum(1 for t in learned if tech.TECHS[t].tier >= 2) >= 2
