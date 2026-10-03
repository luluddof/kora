"""Le pays (chiefdom.country) : les tributaires suivent leur suzerain a la
guerre sans en declarer ; la vue partagee ; le clic sur une ville connue du
brouillard."""

import os

os.environ.setdefault("SDL_VIDEODRIVER", "dummy")

import pygame

from src.kora import app, battle, chiefdom, commands, confed, diplo, influence, memory
from src.kora.globe import hex_to_globe_screen, view_params
from src.kora.layout import HUD_HEIGHT
from src.kora.render import Renderer
from src.kora.types import Band
from src.kora.vision import is_visible, recompute_vision, vision_of
from src.kora.world import offset_to_axial
from test_approach import _state


def _realm():
    """3 tributaire de 2 ; le joueur (1) en contact avec les deux, en treve
    avec 3."""
    st = _state(strong=100, weak=90)
    st.bands[1].position = offset_to_axial(40, 20)
    diplo.make_contact(st, 1, 2, quiet=True)
    diplo.make_contact(st, 1, 3, quiet=True)
    chiefdom.make_vassal(st, 2, 3, "force")
    return st


def test_a_tributary_does_not_start_a_war_but_joins_its_overlords():
    st = _realm()
    assert chiefdom.country(st, 3) == {2, 3} and chiefdom.lords_of(st, 3) == [2]
    assert "tributaire" in diplo.may_start(st, 3, 1)
    assert not diplo.hostile_intent(st, 3, 1)
    # Un suzerain peut, lui ; et son tributaire le suit.
    assert diplo.may_start(st, 2, 1) == ""
    diplo.add_pact(st, 1, 3, "treve", diplo.TRUCE_WEEKS)
    diplo.on_fight(st, 2, 1, True, True)
    assert not diplo.has_pact(st, 1, 3), "la guerre du suzerain est celle du tributaire"
    assert diplo.may_start(st, 3, 1) == "" and diplo.hostile_intent(st, 3, 1)
    # Se revolter contre son suzerain reste possible.
    assert diplo.may_start(st, 3, 2) == ""


def test_an_attack_on_a_tributary_is_an_attack_on_the_country():
    st = _realm()
    diplo.add_pact(st, 1, 2, "treve", diplo.TRUCE_WEEKS)
    diplo.on_fight(st, 1, 3, True, True)
    assert not diplo.has_pact(st, 1, 2)
    assert any(m.key == "raid_pays" for m in st.diplo.mods.get(diplo.pair(1, 2), []))


def test_the_whole_country_comes_to_help():
    st = _realm()
    st.bands[3].position = offset_to_axial(22, 20)
    assert st.bands[3] in battle.helpers_of(st, st.bands[2])
    assert st.bands[2] in battle.helpers_of(st, st.bands[3])


def test_a_tributary_player_cannot_send_a_raid_on_its_own():
    st = _state(strong=100, weak=90)
    st.bands[1].position = offset_to_axial(26, 20)
    diplo.make_contact(st, 1, 2, quiet=True)
    diplo.make_contact(st, 1, 3, quiet=True)
    chiefdom.make_vassal(st, 2, 1, "force")
    st.bands[5] = Band(5, 1, offset_to_axial(27, 20), 30, 100.0)
    st.next_band_id = 6
    out = commands.apply(st, commands.make(1, "march", 5, 3))
    assert "tributaire" in out["msg"]
    # Son suzerain se bat contre eux : il peut le suivre.
    diplo.on_fight(st, 2, 3, True, True)
    out = commands.apply(st, commands.make(1, "march", 5, 3))
    assert "tributaire" not in out["msg"]


def test_tributaries_and_confederates_share_their_sight():
    st = _state(strong=100, weak=90)
    far = offset_to_axial(20, 20)  # le village de 2, loin du joueur (70, 20)
    recompute_vision(st)
    assert not is_visible(st, far, 1)
    chiefdom.make_vassal(st, 1, 2, "force")
    recompute_vision(st)
    assert is_visible(st, far, 1), "le suzerain voit ce que voit son tributaire"
    st.diplo.pacts.clear()
    recompute_vision(st)
    assert not is_visible(st, far, 1)
    chiefdom.make_vassal(st, 2, 1, "force")
    recompute_vision(st)
    assert is_visible(st, far, 1), "le tributaire voit ce que voit son suzerain"
    st.diplo.pacts.clear()
    diplo.add_pact(st, 1, 2, confed.KIND, payer=1)
    recompute_vision(st)
    assert is_visible(st, far, 1), "les confederes partagent leur vue"


def test_a_known_town_in_the_fog_opens_its_diplomacy_even_with_a_clan_chosen():
    st = _state()
    st.bands[1].position = offset_to_axial(26, 20)
    diplo.make_contact(st, 1, 3, quiet=True)
    for _ in range(4):
        influence.update(st)
    recompute_vision(st)
    memory.update(st)
    st.bands[1].position = offset_to_axial(60, 20)
    recompute_vision(st)
    village = next(s for s in st.sites.values() if s.tribe_id == 3 and s.kind == "village")
    assert village.hex not in vision_of(st, 1).visible and village.id in vision_of(st, 1).sites
    pygame.init()
    renderer = Renderer(pygame.display.set_mode((1280, 720)))
    boot = app._start_view(st, 1, 1280, 720)
    play = app.Play(renderer, None, boot)
    play.selected = 1  # un clan, pas une troupe
    play.sw, play.sh = 1280, 720
    play.globe_yaw, play.globe_pitch = app.look_at_hex(village.hex, st.world.width, st.world.height)
    gcx, gcy, focal, dist = view_params(play.zoom, play.sw, play.sh, HUD_HEIGHT)
    x, y = hex_to_globe_screen(village.hex, st.world, play.globe_yaw, play.globe_pitch, gcx, gcy, focal, dist)
    assert app._seen_village_at_pixel(st, x + 3, y, play.zoom, play.globe_yaw, play.globe_pitch, play.sw, play.sh) == 3
    play._on_click(pygame.event.Event(pygame.MOUSEBUTTONDOWN, pos=(int(x), int(y)), button=1))
    assert play.side_panel == "peuples" and play.ui["people_pick"] == 3
    assert st.bands[1].order.kind.name == "STAY", "le clan ne part pas vers la ville"
