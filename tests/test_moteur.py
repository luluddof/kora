"""Le moteur du temps (sim.tick_steps, sim.TickRunner) : la semaine calculee
en morceaux, l'ecran dessinant entre deux, donne EXACTEMENT la meme partie que
la semaine d'une traite ; un ordre attend la fin de la semaine ; la pause
termine la semaine en cours sans en commencer d'autre ; une erreur ramene la
partie a la semaine d'avant."""

import json

import pytest

from src.kora import diplo, persist, sim, tech
from src.kora.sim import TickRunner, hex_inspect, new_game, tick, tick_steps
from src.kora.types import Terrain
from src.kora.world import make_filled_world


def _game(seed: int = 3):
    st = new_game(make_filled_world(60, 36, Terrain.VALLEE, wrap_x=True), setup={"seed": seed})
    st.story = True
    for t in st.tribes.values():
        t.is_player = False
    return st


def _fingerprint(st) -> str:
    out = persist.game_to_json(st, None)
    out.pop("game_version", None)
    return json.dumps(out, sort_keys=True, default=str)


def _read_like_the_screen(st) -> None:
    """Ce que l'ecran lit entre deux morceaux : une case, des relations, des
    savoirs. Lire ne doit rien changer."""
    for b in list(st.bands.values())[:3]:
        hex_inspect(st, b.position)
    ids = sorted(st.tribes)
    for a in ids[:3]:
        tech.bonuses(st.tribes[a])
        for b in ids[:3]:
            if a != b:
                diplo.relation(st, a, b)


def test_a_week_in_pieces_is_the_same_week(monkeypatch):
    # Le budget a zero : chaque image ne fait qu'un morceau de la semaine.
    monkeypatch.setattr(sim, "RUNNER_BUDGET", 0.0)
    monkeypatch.setattr(sim, "RUNNER_BUDGET_LATE", 0.0)
    whole, pieces = _game(), _game()
    for _ in range(40):
        tick(whole)
    runner = TickRunner(pieces)
    pieces.clock.paused = False
    pieces.clock.speed = 5
    frames = 0
    while pieces.tick_count < 40 or runner.busy:
        runner.frame(1.0)
        _read_like_the_screen(pieces)
        frames += 1
        assert frames < 10_000
    pieces.clock.paused = whole.clock.paused
    pieces.clock.speed = whole.clock.speed
    assert frames > 40 * 8, "la semaine se fait bien en plusieurs morceaux"
    assert _fingerprint(pieces) == _fingerprint(whole)


def test_a_month_is_cut_in_many_pieces():
    st = _game()
    while (st.tick_count + 1) % 4:
        tick(st)
    pieces = sum(1 for _ in tick_steps(st))
    assert st.tick_count % 4 == 0
    assert pieces >= 20, f"une semaine de mois en {pieces} morceaux seulement"


def test_an_order_waits_for_the_end_of_the_week(monkeypatch):
    monkeypatch.setattr(sim, "RUNNER_BUDGET", 0.0)
    st = _game()
    st.clock.paused = False
    runner = TickRunner(st)
    runner.frame(1.0)
    assert runner.busy and st.tick_count == 0
    runner.finish()
    assert not runner.busy and st.tick_count == 1


def test_the_pause_ends_the_week_in_progress_and_starts_no_other(monkeypatch):
    monkeypatch.setattr(sim, "RUNNER_BUDGET", 0.0)
    st = _game()
    st.clock.paused = False
    runner = TickRunner(st)
    runner.frame(1.0)
    assert runner.busy
    st.clock.paused = True
    for _ in range(200):
        runner.frame(1.0)
    assert not runner.busy and st.tick_count == 1, "la semaine commencee s'acheve, aucune autre"
    runner.frame(1.0, hold=True)
    assert st.tick_count == 1


def test_an_error_mid_week_brings_back_the_week_before(monkeypatch):
    monkeypatch.setattr(sim, "RUNNER_BUDGET", 0.0)
    st = _game()
    tick(st)
    before = _fingerprint(st)

    def boom(state):
        raise RuntimeError("panne")

    monkeypatch.setattr(sim, "collect_food", boom)
    st.clock.paused = False
    runner = TickRunner(st)
    for _ in range(200):
        runner.frame(1.0)
        if not runner.busy and st.clock.paused:
            break
    assert st.last_error and "panne" in st.last_error
    assert st.clock.paused
    st.last_error = None
    assert _fingerprint(st) == before


@pytest.mark.parametrize("speed", [1, 5])
def test_the_runner_keeps_the_speed_when_weeks_are_cheap(speed):
    st = _game()
    st.clock.paused = False
    st.clock.speed = speed
    runner = TickRunner(st)
    for _ in range(60):          # une seconde a 60 images par seconde
        runner.frame(1 / 60)
    runner.finish()
    want = {1: 2, 5: 10}[speed]
    assert want - 1 <= st.tick_count <= want + 1
