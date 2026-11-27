"""Les corrections de l'interface (revue du 2026-11-27) : un clic sur ce qui
est dessine par-dessus la carte (la barre, une fiche, la colonne de gauche)
ne donne plus d'ordre sur la carte ; deux alertes au meme geste se cliquent
toutes deux ; la coupe d'un texte trop long (theme.fit) rend la meme chose
que lettre a lettre."""

import os

os.environ.setdefault("SDL_VIDEODRIVER", "dummy")

import random

import pygame

from src.kora import partie, partie_carte, theme
from src.kora.sim import new_game
from src.kora.types import OrderKind, Terrain
from src.kora.world import make_filled_world
from test_app_clicks import H, W, _click, _play


def _game():
    return new_game(make_filled_world(40, 24, Terrain.VALLEE, wrap_x=True))


def _record(monkeypatch):
    """Les ordres donnes par l'ecran (Play.issue -> commands.apply)."""
    sent = []
    real = partie.commands.apply

    def apply(state, cmd):
        sent.append(list(cmd))
        return real(state, cmd)

    monkeypatch.setattr(partie.commands, "apply", apply)
    return sent


def test_a_click_on_the_body_of_the_first_village_path_gives_no_order(monkeypatch, tmp_path):
    st = _game()
    sent = _record(monkeypatch)
    seen = {}

    def body(r):
        box = r.goal_box
        assert box, "le chemin du premier village est dessine"
        seen["box"] = box
        return _click((box[0] + 60, box[1] + box[3] - 12))

    steps = [lambda r: [], body, lambda r: []]
    _play(monkeypatch, tmp_path, st, steps)
    assert not [c for c in sent if c[1] == "goto"], sent
    assert st.bands[1].order.kind is not OrderKind.GOTO


def test_a_right_click_on_the_interface_never_attacks(monkeypatch, tmp_path):
    st = _game()
    sent = _record(monkeypatch)
    # Un etranger "sous la souris" ou que l'on clique : le test ne depend
    # pas de la place des jetons a l'ecran.
    monkeypatch.setattr(partie_carte.MapInput, "_foe_under", lambda self, mx, my: 1 if (mx, my) != (W // 2, H // 2 + 40) else 1)

    def right(at):
        return [
            pygame.event.Event(pygame.MOUSEBUTTONDOWN, pos=at, button=3),
            pygame.event.Event(pygame.MOUSEBUTTONUP, pos=at, button=3),
        ]

    seen = {}

    def on_card(r):
        box = r.band_hits.get("box")
        assert box, "la fiche de la bande choisie"
        seen["card"] = len(sent)
        return right((box[0] + 20, box[1] + 8))

    steps = [
        lambda r: [],
        lambda r: right((30, 20)),  # la barre du haut
        on_card,
        lambda r: seen.update(after=len(sent)) or right((W // 2, H // 2 + 40)),  # la carte
        lambda r: [],
    ]
    _play(monkeypatch, tmp_path, st, steps)
    assert seen["card"] == 0 and seen["after"] == 0, f"un clic droit sur l'interface a donne un ordre : {sent}"
    assert any(c[1] == "march" for c in sent), "sur la carte, le clic droit vise toujours"


def test_two_alerts_to_the_same_place_are_both_clickable():
    from src.kora import render_objectifs

    class R:
        pass

    r = R()
    r.alert_hits = [((10, 60, 286, 30), "tab_tribu"), ((10, 94, 286, 30), "tab_tribu")]
    assert render_objectifs.alert_hit(r, 50, 70) == "tab_tribu"
    assert render_objectifs.alert_hit(r, 50, 104) == "tab_tribu"
    assert render_objectifs.alert_hit(r, 50, 200) is None


def test_fit_is_the_longest_head_that_fits():
    pygame.init()
    f = theme.font("mini")
    rng = random.Random(3)
    words = ["la", "fièvre", "au", "village", "Ouvre", ":", "chefferie", "grandes", "chasses", "l'arc", "composite"]

    def slow(text, width):
        if f.size(text)[0] <= width:
            return text
        while text and f.size(text + "…")[0] > width:
            text = text[:-1]
        return text.rstrip() + "…"

    for _ in range(200):
        text = " ".join(rng.choice(words) for _ in range(rng.randint(1, 30)))
        width = rng.randint(10, 400)
        assert theme.fit(f, text, width) == slow(text, width)
