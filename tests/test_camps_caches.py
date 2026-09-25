"""Campements leves au depart, caches prises par l'IA, onglet Armee, monde
plus grand (vue, marche, taille des bandes)."""

import os

from src.kora import chiefs, sites, tech, villages
from src.kora.ai import decide_ai
from src.kora.clock import Clock
from src.kora.sim import GameState, apply_movement, set_goto
from src.kora.types import Band, Terrain, Tribe
from src.kora.world import make_filled_world, offset_to_axial


def _state():
    world = make_filled_world(60, 30, Terrain.PLAINE, wrap_x=True)
    st = GameState(
        world=world,
        clock=Clock(),
        tribes={
            1: Tribe(1, "Kora", 30, True, knowledge=set(tech.START_KNOWLEDGE) | {"huttes", "fumage"}),
            2: Tribe(2, "Steppe", 30, False, knowledge=set(tech.START_KNOWLEDGE), culture="steppe"),
        },
        bands={1: Band(1, 1, offset_to_axial(20, 15), 40, 800.0)},
        next_band_id=10,
    )
    world.fill_season(st.clock.season())
    chiefs.ensure(st)
    return st


def test_a_camp_is_struck_when_the_band_leaves_and_its_store_stays_hidden():
    st = _state()
    camp = sites.make_camp(st, 1)
    sites.deposit(st, 1)
    stored = camp.store
    assert stored > 0
    sites.update(st)
    assert st.sites[camp.id].kind == "camp"
    set_goto(st, 1, offset_to_axial(40, 15))
    apply_movement(st)
    sites.update(st)
    site = st.sites[camp.id]
    assert site.kind == "cache" and site.store > 0
    assert any("Campement leve" in e.text for e in st.log.entries)


def test_an_empty_camp_simply_disappears():
    st = _state()
    camp = sites.make_camp(st, 1)
    st.bands[1].position = offset_to_axial(40, 15)
    sites.update(st)
    assert camp.id not in st.sites


def test_an_enemy_band_goes_for_a_cache_it_finds_and_takes_it():
    st = _state()
    sites.deposit(st, 1)
    cache = next(s for s in st.sites.values() if s.kind == "cache")
    st.bands[1].position = offset_to_axial(50, 15)
    thief = Band(2, 2, offset_to_axial(24, 15), 30, 10.0)
    st.bands[2] = thief
    chiefs.ensure(st)
    st.tick_count = 2  # (2 + 2) % 4 == 0 : la bande decide cette semaine
    decide_ai(st)
    assert thief.path and thief.path[-1] == cache.hex
    for _ in range(3):
        apply_movement(st)
    before = thief.stock
    held = cache.store
    sites.update(st)
    # Elle emporte ce qu'elle peut porter.
    assert thief.stock > before
    assert cache.id not in st.sites or st.sites[cache.id].store < held * 0.1
    assert any("pillee" in e.text for e in st.log.entries)


def test_the_world_is_big_little_seen_slowly_crossed():
    from src.kora.path import MOVE_POINTS_PER_WEEK

    assert tech.BASE_VISION == 8 and MOVE_POINTS_PER_WEEK == 40


def test_bands_do_not_grow_on_screen_with_their_people():
    from src.kora.render import band_radius

    assert band_radius(10, 1.4) == band_radius(400, 1.4)
    assert band_radius(10, 1.2) <= 9


def test_the_army_tab_comes_with_the_first_village():
    from src.kora.render import side_layout
    from src.kora.render_panels import army_ready

    st = _state()
    st.tribes[1].knowledge.update(("semis",))
    st.world = make_filled_world(60, 30, Terrain.VALLEE, wrap_x=True)
    st.world.fill_season(st.clock.season())
    assert not army_ready(st)
    assert "armee" not in side_layout(1280, 720)["tabs"]
    sites.make_camp(st, 1)
    assert villages.found(st, 1) is not None
    assert army_ready(st)
    tabs = side_layout(1280, 720, army=True)["tabs"]
    assert list(tabs)[-1] == "armee"
    x, y, w, h = tabs["armee"]
    assert y + h <= 720


def test_the_army_panel_and_square_villages_draw():
    os.environ.setdefault("SDL_VIDEODRIVER", "dummy")
    import pygame

    from src.kora import render_panels
    from src.kora.render import Renderer, side_layout

    pygame.init()
    try:
        screen = pygame.display.set_mode((1280, 720))
        r = Renderer(screen)
        st = _state()
        st.tribes[1].knowledge.update(("semis",))
        st.world = make_filled_world(60, 30, Terrain.VALLEE, wrap_x=True)
        st.world.fill_season(st.clock.season())
        st.bands[1].population = 120
        sites.make_camp(st, 1)
        site = villages.found(st, 1)
        army = villages.raise_army(st, 1)
        lay = side_layout(1280, 720, panel="armee", army=True)
        ui = {}
        render_panels.draw_army(r, st, lay, ui)
        assert f"araise:{site.id}" in lay["items"] and f"asee:{army.id}" in lay["items"]
        r.draw_village_icon(site, 300, 300, (200, 60, 60), 7)
        assert screen.get_at((300, 300))[:3] == (200, 60, 60)
    finally:
        pygame.quit()
