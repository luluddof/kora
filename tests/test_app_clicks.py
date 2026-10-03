"""Le jeu lui-meme, sans fenetre : un scenario de touches et de clics joue
dans app.play (la vraie boucle), image par image. Chaque etape lit ce que
l'image precedente a dessine (renderer.*_hits) pour viser ses boutons, et
peut verifier l'etat. La sauvegarde de fin va dans un dossier temporaire."""

import os

os.environ.setdefault("SDL_VIDEODRIVER", "dummy")

import pygame

from src.kora import app, money, tech
from src.kora.render import Renderer
from test_goods import _village

W, H = 1280, 720


class _Clock:
    def tick(self, fps=0) -> int:
        return 16


def _center(rect):
    x, y, w, h = rect
    return (int(x + w / 2), int(y + h / 2))


def _key(k):
    return [pygame.event.Event(pygame.KEYDOWN, key=k, mod=0, unicode="", scancode=0)]


def _click(at, button=1):
    return [
        pygame.event.Event(pygame.MOUSEBUTTONDOWN, pos=at, button=button),
        pygame.event.Event(pygame.MOUSEBUTTONUP, pos=at, button=button),
    ]


def _play(monkeypatch, tmp_path, st, steps):
    """Joue `steps` (une fonction par image : renderer -> evenements) puis
    quitte. Rend le renderer."""
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
    monkeypatch.setattr(app, "default_save_path", lambda: tmp_path / "kora.json")
    st.clock.paused = True
    boot = app._start_view(st, app._first_player_band(st), W, H)
    out = app.play(renderer, _Clock(), boot)
    assert out[0] == "quit"
    return renderer


def _money_state():
    st, site, band = _village(("comptage", "nombres", "valeurs", "argent_pese"))
    tech.invalidate()
    return st


def test_the_big_screens_open_close_and_answer_clicks(monkeypatch, tmp_path):
    st = _money_state()
    seen = {}

    def need(cond, what):
        assert cond, what

    steps = [
        lambda r: [],
        # G ouvre le tresor.
        lambda r: _key(pygame.K_g),
        lambda r: need(r.treasury_hits, "le tresor s'ouvre avec G") or _click(_center(r.treasury_hits["taxes"][2])),
        lambda r: need(money.budget(st.tribes[1])["tax"] == 2, "impot moyen") or _click(_center(r.treasury_hits["toggles"]["dons"]["btn"])),
        lambda r: need(money.budget(st.tribes[1])["dons"] is True, "presents") or _key(pygame.K_m),
        # M ouvre le commerce et ferme le tresor.
        lambda r: need(r.trade_hits and not r.treasury_hits, "M : commerce seul") or _key(pygame.K_ESCAPE),
        lambda r: need(not r.trade_hits and not r.treasury_hits, "Échap ferme") or _click(_center(r.side_hits["tabs"]["tresor"])),
        # L'onglet ouvre le tresor ; un clic hors de l'ecran le ferme.
        lambda r: need(r.treasury_hits, "l'onglet ouvre le tresor") or _click((W // 2, H - 4)),
        lambda r: seen.update(closed=not r.treasury_hits) or _click(_center(r.side_hits["tabs"]["tresor"])),
        lambda r: need(r.treasury_hits, "rouvert") or _click(_center(r.treasury_hits["close"])),
        lambda r: need(not r.treasury_hits, "Fermer") or _key(pygame.K_t),
        # Les savoirs : l'onglet des nombres, une base en deux clics.
        lambda r: _click(_center(r.side_hits["items"]["ttab:nombres"])),
        lambda r: _click(_center(r.side_hits["items"]["nbase:60"])),
        lambda r: need(st.tribes[1].base == 0, "un clic ne suffit pas") or _click(_center(r.side_hits["items"]["nbase:60"])),
        lambda r: need(st.tribes[1].base == 60, "deux clics : base soixante") or [],
    ]
    _play(monkeypatch, tmp_path, st, steps)
    assert seen["closed"], "un clic hors du tresor le ferme"
    assert (tmp_path / "kora.json").exists()


def test_one_big_screen_at_a_time(monkeypatch, tmp_path):
    """Ouvrir un grand ecran ferme les autres ; une touche de panneau (B,
    T...) les ferme tous."""
    st = _money_state()
    site = next(s for s in st.sites.values() if s.kind == "village")

    def need(cond, what):
        assert cond, what

    def opened(r):
        return [n for n, h in (("village", r.village_hits), ("commerce", r.trade_hits), ("tresor", r.treasury_hits)) if h]

    steps = [
        lambda r: [],
        lambda r: _key(pygame.K_m),
        lambda r: need(opened(r) == ["commerce"], opened(r)) or _key(pygame.K_b),
        lambda r: need(opened(r) == [], ("B ferme le commerce", opened(r))) or _click(_center(r.side_hits["items"][f"vil_open:{site.id}"])),
        lambda r: need(opened(r) == ["village"], opened(r)) or _key(pygame.K_g),
        lambda r: need(opened(r) == ["tresor"], ("G ferme le village", opened(r))) or _key(pygame.K_m),
        lambda r: need(opened(r) == ["commerce"], opened(r)) or _key(pygame.K_t),
        lambda r: need(opened(r) == [], ("T ferme le commerce", opened(r))) or [],
    ]
    _play(monkeypatch, tmp_path, st, steps)


def test_keys_and_clicks_of_the_whole_game(monkeypatch, tmp_path):
    """Les touches et clics de tous les jours, dans la vraie boucle : le
    temps (espace, 1 a 5), les modes de carte (Z, R, X), les panneaux (T, B,
    P, J), la molette, le menu (Echap, Reprendre), la sauvegarde (F5)."""
    st = _money_state()
    clock_speed = {}

    def need(cond, what):
        assert cond, what

    wheel = [pygame.event.Event(pygame.MOUSEWHEEL, x=0, y=1, flipped=False, precise_x=0.0, precise_y=1.0)]
    steps = [
        lambda r: [],
        lambda r: _key(pygame.K_SPACE),
        lambda r: need(not st.clock.paused, "espace : le temps repart") or _key(pygame.K_3),
        lambda r: clock_speed.update(v=st.clock.speed) or _key(pygame.K_SPACE),
        lambda r: need(st.clock.paused, "espace : pause") or _key(pygame.K_r),
        lambda r: need(r.map_mode == "ressources", r.map_mode) or _key(pygame.K_x),
        lambda r: need(r.map_mode == "commerce", r.map_mode) or _key(pygame.K_z),
        lambda r: _key(pygame.K_p),
        lambda r: need(r.side_hits.get("panel") == "peuples", r.side_hits.get("panel")) or _key(pygame.K_j),
        lambda r: need(r.side_hits.get("panel") == "journal", r.side_hits.get("panel")) or _key(pygame.K_ESCAPE),
        lambda r: need(r.side_hits.get("panel") is None, "Échap ferme le panneau") or wheel,
        # Echap : le menu ; ses touches n'agissent plus sur la carte.
        lambda r: need(r.map_mode == "zones", r.map_mode) or _key(pygame.K_ESCAPE),
        lambda r: _key(pygame.K_r),
        lambda r: need(r.map_mode == "zones", "menu ouvert : R ne fait rien") or _click(_center(r.menu_hits["items"]["reprendre"])),
        lambda r: _key(pygame.K_r),
        lambda r: need(r.map_mode == "ressources", "Reprendre ferme le menu") or _key(pygame.K_F5),
        lambda r: [],
    ]
    _play(monkeypatch, tmp_path, st, steps)
    assert clock_speed["v"] == 3
    assert (tmp_path / "kora.json").exists()
