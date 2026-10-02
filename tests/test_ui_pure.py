"""Dessiner ne change pas la partie. En multijoueur, chaque joueur ouvre ses
fenetres a lui : si un dessin touchait a la partie (au hasard du recit, a un
stock...), les machines s'ecarteraient. On dessine tout, sur une partie
avancee (villages, troupes, commerce), et l'empreinte doit rester la meme."""

import os
import random

os.environ.setdefault("SDL_VIDEODRIVER", "dummy")

import pygame

from src.kora import events, session
from src.kora.app import _fresh_ui, _start_view, _first_player_band
from src.kora.render import Renderer
from src.kora.sim import PLAYER_TRIBE_ID, _default_world, hex_inspect, new_game, tick
from test_balance import _robot


def _advanced():
    """Six ans de jeu, puis tout savoir, deux villages, une troupe, un
    voisin a village et une route commerciale : de quoi remplir chaque ecran."""
    from src.kora import diplo, goods, sites, tech, units, villages

    st = new_game(_default_world())
    st.rng = random.Random(1)
    for _ in range(52 * 6):
        _robot(st)
        tick(st)
        st.clock.paused = False
    for tid in (PLAYER_TRIBE_ID, 2):
        for tech_id in tech.TECHS:
            tech.grant(st.tribes[tid], tech_id)
    tech.invalidate()
    for tid, count in ((PLAYER_TRIBE_ID, 2), (2, 1)):
        bands = sorted((b for b in st.bands.values() if b.tribe_id == tid and not b.village and b.kind != "armee"), key=lambda b: -b.population)
        for band in bands[:count]:
            band.population = max(band.population, 90)
            band.stock = max(band.stock, 2000.0)
            sites.make_camp(st, band.id)
            villages.found(st, band.id)
    home = next(b for b in st.bands.values() if b.tribe_id == PLAYER_TRIBE_ID and b.village)
    unit = units.best(st.tribes[PLAYER_TRIBE_ID], "melee")
    villages.raise_army(st, home.id, villages.LEVY_SHARE["troupe"], unit.id if unit else None)
    diplo.make_contact(st, PLAYER_TRIBE_ID, 2)
    diplo.add_pact(st, PLAYER_TRIBE_ID, 2, "commerce")
    goods.open_route(st, PLAYER_TRIBE_ID, 2, goods.GOODS[0], True, 1)
    for _ in range(8):
        tick(st)
        st.clock.paused = False
    return st


def test_drawing_every_screen_leaves_the_game_untouched():
    st = _advanced()
    villages = [s for s in st.sites.values() if s.kind == "village" and s.tribe_id == PLAYER_TRIBE_ID]
    assert villages, "la partie de test a des villages"
    before = session.sync_digest(st)
    rng, story = st.rng.getstate(), st.story_rng.getstate()
    pygame.init()
    r = Renderer(pygame.display.set_mode((1600, 900)))
    _s, sel, cx, cy, zoom, yaw, pitch = _start_view(st, _first_player_band(st), 1600, 900)
    ui = _fresh_ui()
    for mode in ("zones", "relief", "ressources", "commerce"):
        r.map_mode = mode
        r.draw(st, cx, cy, zoom, sel, False, yaw, pitch, None, ui=ui)
    for panel in ("savoirs", "tribu", "peuples", "journal", "armee"):
        for pick in (None, 2, 3):
            ui["people_pick"] = pick
            r.draw(st, cx, cy, zoom, sel, False, yaw, pitch, panel, ui=ui)
    for site in villages:
        for page in ("village", "metiers"):
            ui.update(village_open=site.id, village_page=page)
            r.draw(st, cx, cy, zoom, sel, False, yaw, pitch, None, ui=ui)
    ui["village_open"] = None
    ui["trade_open"] = True
    for partner in [None] + sorted(st.tribes)[:6]:
        ui["trade_partner"] = partner
        r.draw(st, cx, cy, zoom, sel, False, yaw, pitch, None, ui=ui)
    ui["trade_open"] = False
    for band in [b for b in st.bands.values() if b.tribe_id == PLAYER_TRIBE_ID][:4]:
        ui["found"] = band.id
        r.draw(st, cx, cy, zoom, band.id, False, yaw, pitch, None, ui=ui)
    ui["found"] = None
    for inst in events.pending(st, PLAYER_TRIBE_ID)[:3]:
        ui["event_open"] = inst.uid
        r.draw(st, cx, cy, zoom, sel, False, yaw, pitch, None, ui=ui)
    ui["event_open"] = None
    from src.kora import situations

    home = next(b for b in st.bands.values() if b.tribe_id == PLAYER_TRIBE_ID)
    for sid, tids in (("mal", [PLAYER_TRIBE_ID, 2]), ("passage", [PLAYER_TRIBE_ID, 2, 3]), ("rouille", [PLAYER_TRIBE_ID])):
        situations._start(st, situations.SPECS[sid], home.position, 8, tids, {"dq": 1, "dr": 0})
    before = session.sync_digest(st)
    rng, story = st.rng.getstate(), st.story_rng.getstate()
    for inst in list(st.situations):
        ui["situation_open"] = inst.uid
        r.draw(st, cx, cy, zoom, sel, False, yaw, pitch, None, ui=ui)
    ui["situation_open"] = None
    for mark in st.fights[:3]:
        r.draw(st, cx, cy, zoom, sel, False, yaw, pitch, None, open_fight=mark, ui=ui)
    r.draw(st, cx, cy, zoom, sel, True, yaw, pitch, None, ui=ui)
    for band in list(st.bands.values())[:60]:
        hex_inspect(st, band.position)
    for site in list(st.sites.values())[:60]:
        hex_inspect(st, site.hex)
    assert st.rng.getstate() == rng and st.story_rng.getstate() == story
    assert session.sync_digest(st) == before
