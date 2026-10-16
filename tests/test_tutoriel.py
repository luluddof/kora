"""Le tutoriel (tutoriel.py, render_tutoriel.py) : des etapes bien formees ;
la fiche avance d'elle-meme quand le geste demande est fait ; une etape a
lire attend Suivant ; dans la vraie boucle (sans fenetre) : la partie guidee
ouvre la fiche, ses boutons repondent, le bouton Tuto et F1 la ferment et la
rouvrent ou on l'avait laissee. Le tutoriel ne change pas la partie."""

import os
from types import SimpleNamespace

os.environ.setdefault("SDL_VIDEODRIVER", "dummy")

import pygame

from src.kora import app, partie, partie_carte, render_tutoriel, tutoriel
from src.kora.render import Renderer
from src.kora.sim import new_game, tick
from src.kora.types import Terrain
from src.kora.world import make_filled_world

TARGETS = {"", "hud:pause", "carte", "tuto", "tab:savoirs", "tab:peuples", "tab:journal", "tab:tribu"}


def test_every_step_is_well_formed():
    keys = [s.key for s in tutoriel.STEPS]
    assert len(keys) == len(set(keys))
    for s in tutoriel.STEPS:
        assert s.title and s.text.endswith((".", "!")), s.key
        assert bool(s.todo) == (s.done is not None), f"{s.key} : un geste demande se verifie, et l'inverse"
        assert s.target in TARGETS, s.key
        assert len(s.text) <= 330, f"{s.key} : la fiche doit rester courte"
    assert tutoriel.STEPS[-1].key == "fin"


def _fake_play():
    st = new_game(make_filled_world(40, 24, Terrain.VALLEE, wrap_x=True))
    return SimpleNamespace(
        state=st, ui={}, renderer=SimpleNamespace(map_mode="zones"),
        globe_yaw=0.0, globe_pitch=0.0, zoom=3.0, selected=None, side_panel=None,
    )


def _settle(play):
    for _ in range(3):
        tutoriel.guide_update(play, tutoriel.DONE_PAUSE)


def test_the_card_follows_the_gestures():
    play = _fake_play()
    me = play.state.viewer
    band = next(b for b in play.state.bands.values() if b.tribe_id == me)
    tutoriel.guide_open(play, 0)
    assert tutoriel.current(play.ui).key == "bienvenue"
    tutoriel.guide_update(play, 0.1)
    assert tutoriel.current(play.ui).key == "bienvenue", "rien n'est fait : on attend"
    play.globe_yaw += 0.4
    tutoriel.guide_update(play, 0.1)
    assert tutoriel.doing(play.ui) == "fait"
    _settle(play)
    assert tutoriel.current(play.ui).key == "bande"
    assert play.selected is None, "on choisit soi-même sa bande"
    play.selected = band.id
    _settle(play)
    assert tutoriel.current(play.ui).key == "marcher"
    band.path = [band.position]
    _settle(play)
    assert tutoriel.current(play.ui).key == "temps"
    tick(play.state)
    tick(play.state)
    _settle(play)
    assert tutoriel.current(play.ui).key == "manger"


def test_a_reading_step_waits_for_next_and_the_end_closes():
    play = _fake_play()
    tutoriel.guide_open(play, [s.key for s in tutoriel.STEPS].index("manger"))
    for _ in range(5):
        tutoriel.guide_update(play, 1.0)
    assert tutoriel.current(play.ui).key == "manger"
    assert tutoriel.doing(play.ui) == "lire"
    tutoriel.go(play, 1)
    assert tutoriel.current(play.ui).key == "hiver"
    tutoriel.guide_open(play, len(tutoriel.STEPS) - 1)
    tutoriel.go(play, 1)
    assert not tutoriel.is_open(play.ui)
    tutoriel.guide_open(play)
    assert tutoriel.current(play.ui).key == "bienvenue", "fini : il repart du début"


def test_the_guide_never_changes_the_game():
    play = _fake_play()
    from src.kora import persist
    import json

    before = json.dumps(persist.game_to_json(play.state, None), sort_keys=True, default=str)
    tutoriel.guide_open(play, 0)
    for i in range(len(tutoriel.STEPS)):
        tutoriel.guide_update(play, 0.5)
        tutoriel.go(play, 1)
    after = json.dumps(persist.game_to_json(play.state, None), sort_keys=True, default=str)
    assert before == after


# --- dans la vraie boucle, sans fenetre ---------------------------------------------

W, H = 1280, 720


class _Clock:
    def tick(self, fps=0) -> int:
        return 16


def _key(k):
    return [pygame.event.Event(pygame.KEYDOWN, key=k, mod=0, unicode="", scancode=0)]


def _click(at):
    return [pygame.event.Event(pygame.MOUSEBUTTONDOWN, pos=at, button=1), pygame.event.Event(pygame.MOUSEBUTTONUP, pos=at, button=1)]


def _center(rect):
    x, y, w, h = rect
    return (int(x + w / 2), int(y + h / 2))


def test_the_guided_game_opens_the_card_and_its_buttons_answer(monkeypatch, tmp_path):
    st = new_game(make_filled_world(40, 24, Terrain.VALLEE, wrap_x=True))
    st.clock.paused = True
    seen = {}

    def need(cond, what):
        assert cond, what

    steps = [
        lambda r: [],
        lambda r: need(r.tuto_hits.get("box"), "la partie guidee ouvre la fiche") or _click(_center(r.tuto_hits["next"])),
        # "Passer" : l'etape suivante (Vos gens).
        lambda r: seen.update(card=r.tuto_hits["box"]) or [],
        lambda r: _click(_center(r.tuto_button)),
        lambda r: need(not r.tuto_hits, "le bouton Tuto ferme la fiche") or _key(pygame.K_F1),
        lambda r: need(r.tuto_hits.get("box"), "F1 la rouvre") or _click(_center(r.tuto_hits["close"])),
        lambda r: need(not r.tuto_hits, "Fermer") or [],
    ]
    pygame.init()
    renderer = Renderer(pygame.display.set_mode((W, H)))
    pos = {"xy": (W // 2, H // 2)}
    script = iter(steps)

    def get(*_a, **_k):
        try:
            step = next(script)
        except StopIteration:
            return [pygame.event.Event(pygame.QUIT)]
        events = step(renderer) or []
        for e in events:
            if hasattr(e, "pos"):
                pos["xy"] = e.pos
        return events

    monkeypatch.setattr(pygame.event, "get", get)
    monkeypatch.setattr(pygame.mouse, "get_pos", lambda: pos["xy"])
    monkeypatch.setattr(partie, "default_save_path", lambda: tmp_path / "kora.json")
    boot = app._start_view(st, partie_carte.first_player_band(st), W, H)
    out = app.play(renderer, _Clock(), boot, tuto=True)
    assert out[0] == "quit"
    assert seen["card"]


def test_the_card_layout_is_pure():
    lay = render_tutoriel.tuto_layout(1280, 720, 120, first=True)
    assert lay["prev"] is None
    assert render_tutoriel.tuto_hit(lay, *_center(lay["next"])) == "next"
    assert render_tutoriel.tuto_hit(lay, *_center(lay["close"])) == "close"
    assert render_tutoriel.tuto_hit(lay, lay["box"][0] + 5, lay["box"][1] + 60) == "card"
    assert render_tutoriel.tuto_hit(lay, 900, 600) is None
    b = render_tutoriel.button_rect(1280, 720)
    assert b[0] > 270 and b[1] + b[3] <= 720
