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


def _play(st):
    pygame.init()
    renderer = Renderer(pygame.display.set_mode((1280, 720)))
    boot = app._start_view(st, app._first_player_band(st), 1280, 720)
    return app.Play(renderer, None, boot)


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
