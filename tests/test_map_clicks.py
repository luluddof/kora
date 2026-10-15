"""Les clics sur la carte : un pays clique sans armee choisie ouvre sa
diplomatie (celle de son grand suzerain s'il est tributaire)."""

import os

os.environ.setdefault("SDL_VIDEODRIVER", "dummy")

import pygame

from src.kora import app, chiefdom, diplo
from src.kora.render import Renderer
from src.kora.vision import recompute_vision
from src.kora.world import offset_to_axial
from test_approach import _state
from src.kora import guerre
from src.kora import partie_carte
from src.kora import partie


def _play(st):
    pygame.init()
    renderer = Renderer(pygame.display.set_mode((1280, 720)))
    boot = app._start_view(st, partie_carte.first_player_band(st), 1280, 720)
    return partie.Play(renderer, None, boot)


def test_a_click_on_a_country_opens_its_diplomacy_or_its_overlords():
    st = _state()
    st.bands[1].position = offset_to_axial(26, 20)
    diplo.make_contact(st, 1, 2, quiet=True)
    diplo.make_contact(st, 1, 3, quiet=True)
    recompute_vision(st)
    play = _play(st)
    play.selected = None
    village_of_3 = next(s for s in st.sites.values() if s.tribe_id == 3 and s.kind == "village")
    assert play._country_at(village_of_3.hex) == 3
    play.open_diplomacy(3)
    assert play.side_panel == "peuples" and play.ui["people_pick"] == 3
    # Tributaire : c'est son suzerain qui parle pour lui.
    chiefdom.make_vassal(st, 2, 3, "force")
    play.open_diplomacy(3)
    assert play.ui["people_pick"] == 2
    assert chiefdom.top_lord(st, 3) == 2 and chiefdom.top_lord(st, 2) == 2


def test_an_unknown_people_opens_nothing():
    st = _state()
    play = _play(st)
    play.open_diplomacy(3)
    assert play.side_panel is None


def test_a_right_click_attacks_a_left_click_talks():
    """Une de vos bandes choisie : clic droit sur un etranger = l'attaquer ;
    clic gauche = sa diplomatie ; un clic droit glisse fait tourner la
    planete sans attaquer."""
    from src.kora.globe import hex_to_globe_screen, look_at_hex, view_params
    from src.kora.layout import HUD_HEIGHT

    st = _state()
    st.bands[1].position = offset_to_axial(28, 20)
    diplo.make_contact(st, 1, 3, quiet=True)
    recompute_vision(st)
    play = _play(st)
    play.sw, play.sh = 1280, 720
    play.selected = 1
    foe = st.bands[3]
    play.globe_yaw, play.globe_pitch = look_at_hex(foe.position, st.world.width, st.world.height)
    gcx, gcy, focal, dist = view_params(play.zoom, play.sw, play.sh, HUD_HEIGHT)
    x, y = (int(v) for v in hex_to_globe_screen(foe.position, st.world, play.globe_yaw, play.globe_pitch, gcx, gcy, focal, dist))
    hit = partie_carte.band_at_pixel(st, x, y, play.zoom, play.globe_yaw, play.globe_pitch, play.sw, play.sh)
    assert hit is not None and hit.tribe_id == 3
    # Clic droit glisse : rien.
    play._on_event(pygame.event.Event(pygame.MOUSEBUTTONDOWN, pos=(x, y), button=3))
    play._on_event(pygame.event.Event(pygame.MOUSEBUTTONUP, pos=(x + 40, y), button=3))
    assert st.bands[1].order.kind.name == "STAY"
    # Clic gauche : la diplomatie, et la bande ne bouge pas.
    play._on_click(pygame.event.Event(pygame.MOUSEBUTTONDOWN, pos=(x, y), button=1))
    assert play.side_panel == "peuples" and play.ui["people_pick"] == 3
    assert st.bands[1].order.kind.name == "STAY"
    # En paix (tous deux ont la diplomatie) : le clic droit ne lance rien.
    assert guerre.needs_declaration(st, 1, 3)
    play._on_event(pygame.event.Event(pygame.MOUSEBUTTONDOWN, pos=(x, y), button=3))
    play._on_event(pygame.event.Event(pygame.MOUSEBUTTONUP, pos=(x, y), button=3))
    assert st.bands[1].order.kind.name == "STAY"
    # La guerre declaree : le clic droit attaque.
    guerre.declare_war(st, 1, 3)
    play._on_event(pygame.event.Event(pygame.MOUSEBUTTONDOWN, pos=(x, y), button=3))
    play._on_event(pygame.event.Event(pygame.MOUSEBUTTONUP, pos=(x, y), button=3))
    assert st.bands[1].order.kind.name == "MARCH_TO_BAND" and st.bands[1].order.target_band_id == hit.id


def test_army_and_wars_share_one_screen():
    """A : l'armee, W : les guerres, dans le meme grand ecran ; la meme
    touche le ferme ; "Lever des troupes" d'une guerre mene a l'armee."""
    from src.kora import render_wars, screens

    st = _state()
    diplo.make_contact(st, 1, 2, quiet=True)
    play = _play(st)
    play.open_war_room(render_wars.ARMY)
    assert play.ui.get("wars_open") and play.ui["war_pick"] == render_wars.ARMY
    play.open_war_room(render_wars.ARMY)
    assert not play.ui.get("wars_open"), "la touche A ferme l'écran ouvert sur l'armée"
    play.open_war_room(None)
    assert play.ui.get("wars_open") and play.ui["war_pick"] == render_wars.ARMY, "sans guerre, W montre l'armée"
    screens.close_all(play.ui)
    guerre.declare_war(st, 1, 2)
    play.open_war_room(None)
    assert play.ui["war_pick"] == 2
    play.open_war_room(render_wars.ARMY)
    assert play.ui.get("wars_open") and play.ui["war_pick"] == render_wars.ARMY, "la touche A passe des guerres à l'armée"
    play.wars_click("wpick:2")
    play.wars_click("wlevy")
    assert play.ui["war_pick"] == render_wars.ARMY
    play.open_war_room(None)
    assert play.ui["war_pick"] == 2, "W revient à la guerre"
