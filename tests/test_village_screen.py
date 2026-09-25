"""Le village : serment de fondation, batiments, ecrans (sans fenetre)."""

import os

from src.kora import chiefs, influence, orders, sites, tech, villages
from src.kora.clock import Clock
from src.kora.sim import GameState, stock_max, update_prestige
from src.kora.types import Band, Terrain, Tribe
from src.kora.world import make_filled_world, offset_to_axial


def _state(known=("huttes", "semis"), pop=90, stock=3000.0):
    world = make_filled_world(60, 30, Terrain.VALLEE, wrap_x=True)
    tribe = Tribe(1, "Kora", 30, True, knowledge=set(tech.START_KNOWLEDGE) | set(known), culture="joueur")
    st = GameState(world=world, clock=Clock(), tribes={1: tribe}, bands={1: Band(1, 1, offset_to_axial(30, 15), pop, stock)}, next_band_id=2)
    world.fill_season(st.clock.season())
    chiefs.ensure(st)
    sites.make_camp(st, 1)
    return st, st.bands[1]


def test_the_first_village_opens_an_age():
    st, band = _state()
    prestige = st.tribes[1].prestige
    info = villages.found_preview(st, 1)
    assert info["first"] and info["name"] and info["fields"] > 0
    site = villages.found(st, 1, oath="grenier", name_=info["name"])
    assert site.name == info["name"] and villages.oath_of(site) == "grenier"
    assert st.tribes[1].prestige == prestige + villages.FIRST_VILLAGE_PRESTIGE
    assert "age_villages" in st.tribes[1].flags
    assert any("age des villages" in e.text for e in st.log.entries)


def test_the_proposed_name_does_not_move_while_the_window_is_open():
    st, band = _state()
    seq = st.story_rng.getstate()
    assert villages.propose_name(st, 1) == villages.propose_name(st, 1)
    assert st.story_rng.getstate() == seq


def test_the_oath_changes_the_village_for_good():
    st, band = _state()
    plain = villages.found(st, 1)
    cap = stock_max(band, st)
    st2, band2 = _state()
    villages.found(st2, 1, oath="grenier")
    assert stock_max(band2, st2) > cap * 1.1
    st3, band3 = _state(known=("huttes", "semis", "palissade"))
    site3 = villages.found(st3, 1, oath="pieux")
    assert villages.build_weeks(site3, "palissade") == villages.PALISADE_WEEKS // 2
    assert villages.build_cost(st3, site3, "palissade") < villages.build_cost(st, plain, "palissade")
    assert villages.defense_mult(st3, band3) > 1.0


def test_a_building_costs_food_takes_weeks_then_works():
    st, band = _state()
    site = villages.found(st, 1)
    assert villages.build_block(st, 1, "grenier") == ""
    before = band.stock
    cap = stock_max(band, st)
    assert villages.build(st, 1, "grenier")
    assert band.stock == before - villages.build_cost(st, site, "grenier")
    assert villages.building_status(st, site, "grenier") == "chantier"
    assert "a la fois" in villages.build_block(st, 1, "puits")
    for _ in range(villages.BUILDINGS["grenier"].weeks):
        villages.update(st)
    assert villages.has(site, "grenier")
    assert stock_max(band, st) > cap


def test_buildings_need_knowledge_and_room():
    st, band = _state(pop=40, known=("huttes", "semis", "rites"))
    site = villages.found(st, 1)
    assert villages.building_status(st, site, "palissade") == "verrouille"
    assert "Palissades" in villages.build_block(st, 1, "palissade")
    assert villages.slots(st, site) == villages.BASE_SLOTS + 1
    site.data["buildings"] = ["grenier", "puits", "enclos"]
    assert "place" in villages.build_block(st, 1, "autel")


def test_old_palisades_are_read_as_buildings():
    st, band = _state()
    site = villages.found(st, 1)
    site.data["palisade"] = -1
    site.data["buildings"] = []
    assert villages.palisade_state(site) == "built"
    site.data = {"band": 1, "palisade": 5, "fields": []}
    assert villages.palisade_state(site) == "building"
    assert villages.works(site) == ("palissade", 5)


def test_altar_tower_and_stone_reach_beyond_the_village():
    st, band = _state(known=("huttes", "semis", "guetteurs", "rites", "megalithes"))
    site = villages.found(st, 1)
    site.data["buildings"] = ["autel", "tour", "pierre"]
    clan = Band(5, 1, offset_to_axial(33, 15), 20, 100.0)
    st.bands[5] = clan
    assert any("autel" in label for label, _v in chiefs.loyalty_parts(st, clan))
    assert villages.winter_prestige(st, 1) == 3
    assert villages.influence_radius(site, influence.VILLAGE_RADIUS) == influence.VILLAGE_RADIUS + 1
    from src.kora.vision import recompute_vision

    far = offset_to_axial(30, 15)
    vis = recompute_vision(st)
    assert far in vis.visible
    assert villages.watch_spots(st, 1) == [site.hex]
    st.clock.week = 12
    st.clock.advance_week()
    if st.clock.just_finished_winter():
        before = st.tribes[1].prestige
        update_prestige(st)
        assert st.tribes[1].prestige >= before + 3


def test_the_village_button_opens_the_village_and_leaving_is_apart():
    st, band = _state()
    site = villages.found(st, 1)
    assert orders.band_actions(st, 1)["village"] == ""
    assert orders.labels(st, 1)["village"] == "Gerer [V]"
    orders.perform(st, 1, "village")
    assert band.village == site.id
    _sel, msg = orders.perform(st, 1, "leave")
    assert msg == "" and band.village == 0


def test_windows_fit_on_small_and_large_screens():
    from src.kora.render_village import battle_layout, found_hit, found_layout, village_hit, village_layout

    for w, h in ((1024, 640), (1280, 720), (1920, 1080)):
        lay = found_layout(w, h)
        bx, by, bw, bh = lay["box"]
        assert bx >= 0 and by >= 0 and bx + bw <= w and by + bh <= h
        for oid, (x, y, cw, ch) in lay["oaths"].items():
            assert bx <= x and x + cw <= bx + bw and y + ch <= by + bh
            assert found_hit(lay, x + 3, y + 3) == f"oath:{oid}"
        assert found_hit(lay, lay["ok"][0] + 3, lay["ok"][1] + 3) == "found_ok"
        vl = village_layout(w, h, 2)
        bx, by, bw, bh = vl["box"]
        assert bx + bw <= w - 32 and by + bh <= h
        for bid, (x, y, cw, ch) in vl["cards"].items():
            assert y + ch <= vl["detail"][1]
            assert village_hit(vl, x + 3, y + 3) == f"vb:{bid}"
        assert village_hit(vl, vl["raise"][0] + 3, vl["raise"][1] + 3) == "vraise"
        see = vl["armies"][1]["see"]
        assert village_hit(vl, see[0] + 3, see[1] + 3, [7, 9]) == "vsee:9"
        bl = battle_layout(w, h)
        bx, by, bw, bh = bl["box"]
        assert bx >= 0 and bx + bw <= w and by + bh <= h


def test_the_windows_draw_without_error():
    os.environ.setdefault("SDL_VIDEODRIVER", "dummy")
    import pygame

    from src.kora import render_village
    from src.kora.render import Renderer
    from src.kora.sim import resolve_raids
    from src.kora.types import Order, OrderKind

    pygame.init()
    try:
        screen = pygame.display.set_mode((1280, 720))
        r = Renderer(screen)
        st, band = _state(known=("huttes", "semis", "palissade"))
        r.draw_village_icon  # noqa: B018 (methode utilisee par l'ecran)
        render_village.draw_found(r, st, {"found": 1, "found_oath": "feu"})
        assert r.found_hits["ok"]
        site = villages.found(st, 1, oath="feu")
        villages.build(st, 1, "palissade")
        army = villages.raise_army(st, 1)
        render_village.draw_village(r, st, {"village_open": site.id, "levy": "masse"})
        assert r.village_armies == [army.id]
        st.tribes[2] = Tribe(2, "Steppe", 20, False, knowledge=set(tech.START_KNOWLEDGE))
        st.bands[70] = Band(70, 2, army.position, 12, 30.0)
        chiefs.ensure(st)
        army.order = Order(OrderKind.MARCH_TO_BAND, target_band_id=70)
        resolve_raids(st)
        mark = st.fights[0]
        render_village.draw_battle(r, st, mark)
        assert r.fight_hits["close"]
    finally:
        pygame.quit()
