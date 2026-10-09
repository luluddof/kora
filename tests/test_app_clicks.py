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


def _track_at(r, key, frac):
    tx, ty, tw, th = r.treasury_hits["sliders"][key]["track"]
    return (int(tx + tw * frac), ty + th // 2)


def _press_at(r, key, frac):
    return [pygame.event.Event(pygame.MOUSEBUTTONDOWN, pos=_track_at(r, key, 0.1), button=1)]


def _drag_to(r, key, frac):
    return [pygame.event.Event(pygame.MOUSEMOTION, pos=_track_at(r, key, frac), rel=(0, 0), buttons=(1, 0, 0))]


def _release(r, key, frac):
    return [pygame.event.Event(pygame.MOUSEBUTTONUP, pos=_track_at(r, key, frac), button=1)]


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
        lambda r: need(r.treasury_hits, "le tresor s'ouvre avec G") or _click(_center(r.treasury_hits["sliders"]["impot"]["plus"])),
        lambda r: need(money.budget(st.tribes[1])["impot"] == 1, "+ : un point d'impot") or _press_at(r, "dons", 0.5),
        # Glisser le curseur des presents jusqu'a la moitie de la piste : 100 %.
        lambda r: _drag_to(r, "dons", 0.5),
        lambda r: _release(r, "dons", 0.5),
        lambda r: need(money.budget(st.tribes[1])["dons"] == 1.0, money.budget(st.tribes[1])["dons"]) or _key(pygame.K_m),
        # M ouvre le commerce et ferme le tresor.
        lambda r: need(r.trade_hits and not r.treasury_hits, "M : commerce seul") or _key(pygame.K_ESCAPE),
        lambda r: need(not r.trade_hits and not r.treasury_hits, "Échap ferme") or _click(_center(r.side_hits["tabs"]["tresor"])),
        # L'onglet ouvre le tresor ; un clic hors de l'ecran le ferme.
        lambda r: need(r.treasury_hits, "l'onglet ouvre le tresor") or _click((W // 2, H - 4)),
        lambda r: seen.update(closed=not r.treasury_hits) or _click(_center(r.side_hits["tabs"]["tresor"])),
        lambda r: need(r.treasury_hits, "rouvert") or _click(_center(r.treasury_hits["close"])),
        lambda r: need(not r.treasury_hits, "Fermer") or _key(pygame.K_t),
        # Les savoirs, l'onglet des nombres : la base est une loi (Pays).
        lambda r: _click(_center(r.side_hits["items"]["ttab:nombres"])),
        lambda r: _click(_center(r.side_hits["items"]["nlaws"])),
        lambda r: need(r.country_hits, "le bouton ouvre le pays") or _click(_center(r.country_hits["rows"]["base"]["cards"]["60"]["btn"])),
        lambda r: need(st.tribes[1].base == 0, "un clic ne suffit pas") or _click(_center(r.country_hits["rows"]["base"]["cards"]["60"]["btn"])),
        lambda r: need(st.tribes[1].base == 60, "deux clics : base soixante") or _click(_center(r.country_hits["rows"]["paiement"]["cards"]["argent"]["btn"])),
        lambda r: need(st.tribes[1].laws.get("paiement") == "argent", "la loi du paiement") or _key(pygame.K_n),
        lambda r: need(not r.country_hits, "N ferme le pays") or _key(pygame.K_n),
        lambda r: need(r.country_hits, "N ouvre le pays") or [],
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


def test_the_turning_map_and_the_tree_answer_clicks(monkeypatch, tmp_path):
    """I : la carte des grands tournants ; un clic sur une ligne de sa legende
    choisit le tournant montre ; dans l'arbre, un clic sur un tournant le
    montre dans la fiche, « Adopter » l'apprend quand il est arrive."""
    from src.kora import render_tech
    from src.kora.layout import cam_on, tech_panel_layout

    st = _money_state()
    st.tribes[1].knowledge |= {"palabres", "mariages"}
    st.tribes[1].tournants["don"] = 100.0
    seen = {}
    # L'arbre s'ouvre sur le tournant (la vue suit d'habitude la recherche en cours).
    monkeypatch.setattr(render_tech, "focus_cam", lambda state, w, h: cam_on(tech_panel_layout(w, h)["view"], tech_panel_layout(w, h)["world"], "don", 1.0))

    def need(cond, what):
        assert cond, what

    steps = [
        lambda r: [],
        lambda r: _key(pygame.K_i),
        lambda r: need(r.map_mode == "tournants", r.map_mode) or _click(_center(r.turning_hits["terre_ancetres"])),
        lambda r: need(r.turning_pick == "terre_ancetres", r.turning_pick) or _key(pygame.K_t),
        lambda r: seen.update(cam=r.side_hits["tech"]["cam"]) or [],
        lambda r: _click(_center(r.side_hits["items"]["tech:don"])),
        lambda r: [],
        lambda r: _click(_center(r.side_hits["items"]["learn"])),
        lambda r: need(st.tribes[1].learning == "don", st.tribes[1].learning) or [],
    ]
    _play(monkeypatch, tmp_path, st, steps)


def test_the_map_mode_button_and_its_list(monkeypatch, tmp_path):
    """Le bouton « Carte » en bas a gauche : il ouvre la liste des modes ; un
    mode choisi la referme ; un clic ailleurs aussi."""
    st = _money_state()

    def need(cond, what):
        assert cond, what

    steps = [
        lambda r: [],
        lambda r: _click(_center(r.mode_hits["button"])),
        lambda r: need(r.mode_menu_open and r.mode_hits["items"], "la liste s'ouvre") or _click(_center(r.mode_hits["items"]["suzerains"])),
        lambda r: need(r.map_mode == "suzerains" and not r.mode_menu_open, r.map_mode) or _click(_center(r.mode_hits["button"])),
        lambda r: need(r.mode_menu_open, "rouverte") or _click((W // 2, H // 2)),
        lambda r: need(not r.mode_menu_open and r.map_mode == "suzerains", "un clic ailleurs la ferme") or [],
    ]
    _play(monkeypatch, tmp_path, st, steps)


def test_the_village_levies_its_militia_and_buys_grain_in_dearth(monkeypatch, tmp_path):
    """L'ecran du village : la milice (on ne choisit pas le genre des
    guerriers), la levee, puis le grenier presque vide : un clic achete du
    grain a un partenaire."""
    from src.kora import diplo
    from test_grain import _two

    st, buyer, bsite, seller, ssite = _two()
    buyer.stock = 4000.0
    seen = {}

    def need(cond, what):
        assert cond, what

    def starve(r):
        buyer.stock = 50.0
        return []

    steps = [
        lambda r: [],
        lambda r: _key(pygame.K_v),
        lambda r: need(r.village_hits, "V ouvre le village") or need("types" in r.village_hits, "la milice") or [],
        lambda r: _click(_center(r.village_hits["raise"])),
        lambda r: seen.update(army=[b for b in st.bands.values() if b.kind == "armee"]) or starve(r),
        lambda r: [],
        lambda r: need(r.village_hits.get("grain"), "disette : la tuile du grenier acheté") or _click(_center(r.village_hits["tiles"][1])),
        lambda r: seen.update(stock=buyer.stock) or [],
    ]
    _play(monkeypatch, tmp_path, st, steps)
    army = seen["army"]
    assert len(army) == 1 and len(army[0].units) >= 2, "chacun dans sa categorie : plusieurs compagnies"
    assert seen["stock"] > 50.0, "le grain acheté arrive au grenier"
    assert diplo.relation(st, 1, 3) is not None
