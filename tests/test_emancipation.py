"""Apres le premier village, les clans errants s'eloignent et partent fonder
des villages de votre souche."""

from src.kora import chiefs, sites, tech, villages
from src.kora.ai import decide_ai
from src.kora.clock import Clock
from src.kora.peoples import culture_of
from src.kora.sim import GameState
from src.kora.types import Band, Terrain, Tribe
from src.kora.world import make_filled_world, offset_to_axial


def _tribe(settled=True):
    world = make_filled_world(80, 30, Terrain.VALLEE, wrap_x=True)
    tribe = Tribe(1, "Kora", 40, True, knowledge=set(tech.START_KNOWLEDGE) | {"huttes", "semis"}, culture="joueur")
    st = GameState(
        world=world,
        clock=Clock(),
        tribes={1: tribe},
        bands={
            1: Band(1, 1, offset_to_axial(20, 15), 90, 3000.0),
            2: Band(2, 1, offset_to_axial(24, 15), 30, 300.0),
            3: Band(3, 1, offset_to_axial(60, 15), 30, 300.0),
        },
        next_band_id=10,
    )
    world.fill_season(st.clock.season())
    chiefs.ensure(st)
    if settled:
        sites.make_camp(st, 1)
        villages.found(st, 1)
    return st


def _part(st, band_id, label):
    return next((v for lab, v in chiefs.loyalty_parts(st, st.bands[band_id]) if label in lab), None)


def test_after_the_first_village_nomad_clans_grow_independent():
    nomads = _tribe(settled=False)
    assert chiefs.autonomy_rate(nomads, nomads.bands[3]) == 0.0
    st = _tribe()
    assert st.tribes[1].settled_at == 0
    far, near, village = st.bands[3], st.bands[2], st.bands[1]
    # Loin des villages et du chef : plus vite ; pres du village : lentement ;
    # le village lui-meme ne s'emancipe pas.
    assert chiefs.autonomy_rate(st, far) > chiefs.autonomy_rate(st, near) > 0
    assert chiefs.autonomy_rate(st, village) == 0.0
    st.tick_count = 4
    chiefs.monthly(st)
    assert far.autonomy > near.autonomy > 0 and village.autonomy == 0.0
    assert "independance" in chiefs.band_lines_extra(st, far)[1]


def test_a_clan_leaves_when_its_independence_is_full_and_honor_slows_it():
    st = _tribe()
    far = st.bands[3]
    far.autonomy = 60.0
    st.tribes[1].prestige = 60
    assert chiefs.honor(st, 3)
    assert far.autonomy == 60.0 - chiefs.HONOR_AUTONOMY
    far.autonomy = 99.5
    st.tick_count = 4
    chiefs.monthly(st)
    assert far.tribe_id != 1
    kin = st.tribes[far.tribe_id]
    assert culture_of(kin).id == "souche"
    from src.kora.peoples import civ_of

    assert civ_of(st, kin) == civ_of(st, st.tribes[1]) == 1


def test_the_chief_goes_to_govern_the_first_village():
    st = _tribe(settled=False)
    heart = chiefs.chief_band(st, 1)
    chief = heart.leader
    founder = st.bands[2]
    assert heart is not founder
    sites.make_camp(st, 2)
    assert villages.found(st, 2) is not None
    assert chiefs.chief_band(st, 1) is founder and founder.leader is chief


def test_a_civilisation_shares_one_band_cap_between_all_its_peoples():
    from src.kora.sim import civ_band_cap, civ_band_count, max_bands_of

    st = _tribe(settled=False)
    cap = civ_band_cap(st, 1)
    assert cap == tech.bonuses(st.tribes[1]).max_bands
    # Chefferie : 12 pour toute la culture.
    st.tribes[1].knowledge.add("chefferie")
    assert civ_band_cap(st, 1) == 12
    assert civ_band_count(st, 1) == 3 and max_bands_of(st, 1) == 12
    # Un clan qui prend son independance reste dans la reserve commune :
    # ses bandes comptent pour le peuple d'origine, joueur compris.
    sites.make_camp(st, 1)
    villages.found(st, 1)
    kin = chiefs.emancipate(st, 3)
    assert civ_band_count(st, 1) == 3
    st.bands[40] = Band(40, kin, offset_to_axial(70, 20), 30, 100.0)
    st.bands[41] = Band(41, kin, offset_to_axial(72, 20), 30, 100.0)
    assert civ_band_count(st, 1) == 5
    assert max_bands_of(st, 1) == 2 + (12 - 5)
    # La civilisation au complet : personne ne se divise plus.
    for k in range(7):
        st.bands[50 + k] = Band(50 + k, kin, offset_to_axial(10 + 2 * k, 5), 30, 100.0)
    assert civ_band_count(st, 1) == 12
    st.bands[1].population = 120
    from src.kora.sim import can_split

    assert not can_split(st, 1) and max_bands_of(st, 1) == 2


def test_a_clan_that_leaves_founds_a_people_of_your_stock():
    st = _tribe()
    new = chiefs.secede(st, 3)
    kin = st.tribes[new]
    assert culture_of(kin).id == "souche"
    assert "semis" in kin.knowledge and kin.origin == 1
    assert any("independance" in e.text for e in st.log.entries)


def test_the_kin_people_camps_on_good_land_then_founds_its_village():
    st = _tribe()
    new = chiefs.secede(st, 3)
    band = st.bands[3]
    assert band.tribe_id == new
    founded = None
    for week in range(1, 40):
        st.tick_count = week
        decide_ai(st)
        founded = next((s for s in sites.of_tribe(st, new, "village")), None)
        if founded:
            break
    assert founded is not None and founded.tribe_id == new


def test_the_tribe_tab_becomes_the_villages_when_no_nomad_is_left():
    import os

    os.environ.setdefault("SDL_VIDEODRIVER", "dummy")
    import pygame

    from src.kora.render import Renderer

    st = _tribe()
    for bid in (2, 3):
        chiefs.secede(st, bid)
    assert [b.id for b in st.bands.values() if b.tribe_id == 1] == [1]
    pygame.init()
    from src.kora import render_panels
    from src.kora.render import side_hit

    assert render_panels.tribe_tab_label(st) == "Village"
    try:
        r = Renderer(pygame.display.set_mode((1280, 720)))
        r.draw_side(st, "tribu", ui={})
        items = r.side_hits["items"]
        assert r.side_hits["box"][2] > 0 and any(k.startswith("vil_row:") for k in items)
        # Le bouton dans la rangee gagne sur la rangee.
        opn = next(rect for k, rect in items.items() if k.startswith("vil_open:"))
        assert side_hit(r.side_hits, opn[0] + 3, opn[1] + 3).startswith("vil_open:")
    finally:
        pygame.quit()


def test_ai_peoples_emancipate_too_even_when_they_honor():
    st = _tribe()
    ai = Tribe(5, "Steppe", 90, False, knowledge=set(tech.START_KNOWLEDGE) | {"huttes", "semis"}, culture="steppe", settled_at=0)
    st.tribes[5] = ai
    st.bands[20] = Band(20, 5, offset_to_axial(70, 5), 60, 400.0)
    st.bands[21] = Band(21, 5, offset_to_axial(70, 25), 30, 300.0)
    chiefs.ensure(st)
    for month in range(1, 60):
        st.tick_count = 4 * month
        chiefs.monthly(st)
        if st.bands[21].tribe_id != 5:
            break
    assert st.bands[21].tribe_id != 5
    from src.kora.peoples import civ_of

    assert civ_of(st, st.tribes[st.bands[21].tribe_id]) == 5


def test_civilisation_and_independence_are_saved(tmp_path):
    from src.kora.persist import load_game, save_game
    from src.kora.sim import new_game

    world = make_filled_world(40, 20, Terrain.VALLEE, wrap_x=True)
    st = new_game(world)
    st.bands[1].autonomy = 42.0
    st.tribes[2].civ = 1
    path = tmp_path / "kora.json"
    save_game(st, path, {})
    loaded, _ = load_game(path, world)
    assert loaded.bands[1].autonomy == 42.0 and loaded.tribes[2].civ == 1


def test_when_the_world_is_full_the_clan_waits_instead_of_bouncing(monkeypatch):
    from src.kora import peoples

    st = _tribe()
    monkeypatch.setattr(peoples, "MAX_LIVING_TRIBES", 1)
    far = st.bands[3]
    far.autonomy = 99.5
    st.tick_count = 4
    chiefs.monthly(st)
    assert far.tribe_id == 1 and far.autonomy == 100.0 and far.loyalty <= 30.0
    assert len(st.tribes) == 1


def test_an_old_save_seats_the_chief_in_its_village(tmp_path):
    import json

    from src.kora.persist import load_game, save_game

    st = _tribe(settled=False)
    sites.make_camp(st, 2)
    villages.found(st, 2)
    # Comme avant la scission : le chef menait un clan nomade.
    st.tribes[1].chief_band = 1
    path = tmp_path / "kora.json"
    save_game(st, path, {})
    data = json.loads(path.read_text(encoding="utf-8"))
    data.pop("chief_seats", None)
    path.write_text(json.dumps(data), encoding="utf-8")
    loaded, _ = load_game(path, st.world)
    heart = chiefs.chief_band(loaded, 1)
    assert heart is not None and heart.village


def test_a_people_born_from_us_frees_its_places_when_it_dies():
    from src.kora.sim import civ_band_count, max_bands_of

    st = _tribe()
    before = max_bands_of(st, 1)
    kin = chiefs.secede(st, 3)
    # Le clan parti garde sa place dans la reserve commune.
    assert max_bands_of(st, 1) == before - 1
    st.bands[3].population = 0
    del st.bands[3]
    assert max_bands_of(st, 1) == before
    assert civ_band_count(st, 1) == 2
    assert kin in st.tribes


def test_a_full_civilisation_sends_its_restless_families_to_a_kin_village():
    from src.kora import villages as v
    from src.kora.sim import civ_band_cap, civ_band_count

    st = _tribe()
    village = st.bands[1]
    site = v.site_of(st, village)
    kin = chiefs.emancipate(st, 3)
    st.bands[3].position = offset_to_axial(40, 15)
    sites.make_camp(st, 3)
    v.found(st, 3)
    for k in range(civ_band_cap(st, 1) - civ_band_count(st, 1)):
        st.bands[60 + k] = Band(60 + k, kin, offset_to_axial(10 + 2 * k, 5), 20, 50.0)
    assert civ_band_count(st, 1) == civ_band_cap(st, 1)
    other = st.bands[3]
    before = other.population
    st.tribes[1].prestige = 0
    site.data["burned"] = True
    for month in range(1, 40):
        st.tick_count = 4 * month
        village.famine_tick = st.tick_count
        v._unrest(st, site, village)
        if other.population > before:
            break
    assert other.population > before
    assert civ_band_count(st, 1) == civ_band_cap(st, 1)


def test_an_emancipated_clan_leaves_to_find_land_away_from_villages():
    st = _tribe()
    far = st.bands[3]
    far.position = offset_to_axial(26, 15)
    far.autonomy = 99.5
    st.tick_count = 4
    chiefs.monthly(st)
    assert far.tribe_id != 1
    assert far.path, "il part chercher sa terre"
    village = next(s for s in st.sites.values() if s.kind == "village")
    from src.kora import ai

    assert st.world.distance(far.path[-1], village.hex) >= ai.VILLAGE_SPACING


def test_ai_does_not_settle_at_the_foot_of_another_village():
    from src.kora import ai

    st = _tribe()
    new = chiefs.secede(st, 2)
    band = st.bands[2]
    band.path = []
    band.position = offset_to_axial(22, 15)
    assert not ai._settle_ai(st, band)


def test_neolithic_knowledge_steadies_villages_not_nomad_clans():
    from src.kora.villages import stability, stability_parts

    st = _tribe()
    village = st.bands[1]
    site = villages.site_of(st, village)
    base = stability(st, site)
    nomad_before = chiefs.loyalty_target(st, st.bands[3])
    st.tribes[1].knowledge.update(("ancetres", "megalithes"))
    assert stability(st, site) == base + 25
    assert any(label == "Savoirs du neolithique" for label, _v in stability_parts(st, site))
    assert chiefs.loyalty_target(st, st.bands[3]) == nomad_before


def test_a_troubled_village_loses_families():
    from src.kora import villages as v

    st = _tribe()
    village = st.bands[1]
    site = v.site_of(st, village)
    st.tribes[1].prestige = 0
    village.famine_tick = 0
    site.data["burned"] = True
    assert v.stability(st, site) < v.UNREST
    before = village.population
    for month in range(1, 30):
        st.tick_count = 4 * month
        village.famine_tick = st.tick_count
        v._unrest(st, site, village)
        if village.population < before:
            break
    assert village.population < before
    # Elles ne restent pas une tribu errante du peuple : elles fondent le
    # leur, de la meme civilisation, et partent chercher leur terre.
    assert len([b for b in st.bands.values() if b.tribe_id == 1]) == 3
    kin = [t for t in st.tribes.values() if t.origin == 1]
    assert len(kin) == 1


def test_a_settled_civilisation_stops_making_tribes():
    from src.kora import ai
    from src.kora.sim import can_split, max_bands_of

    st = _tribe()
    # Un clan parti fonder son peuple : une seule bande tant qu'il n'a pas
    # son village.
    new = chiefs.emancipate(st, 3)
    st.bands[3].population = 120
    assert max_bands_of(st, new) == 1 and not can_split(st, 3)
    # Un clan nomade d'un peuple fixe (IA) ne se divise plus.
    st.tribes[1].is_player = False
    st.bands[2].population = 120
    assert not ai._should_split(st, st.bands[2], 10.0)


def test_clans_leave_one_by_one_not_all_the_same_month():
    st = _tribe()
    st.bands[2].autonomy = 100.0
    st.bands[3].autonomy = 100.0
    st.tick_count = 4
    chiefs.monthly(st)
    left = [b for b in (st.bands[2], st.bands[3]) if b.tribe_id != 1]
    assert len(left) == 1
    st.tick_count = 8
    chiefs.monthly(st)
    assert all(b.tribe_id != 1 for b in (st.bands[2], st.bands[3]))


def test_more_villages_and_disobedience_speed_the_split():
    st = _tribe()
    far = st.bands[3]
    base = chiefs.autonomy_rate(st, far)
    far.loyalty = 10.0
    indocile = chiefs.autonomy_rate(st, far)
    assert indocile > base
    # Trois villages de plus : le chef a d'autres soucis.
    st.tribes[1].knowledge |= {"maisons", "freres"}
    for k, col in enumerate((40, 50, 70)):
        bid = 20 + k
        st.bands[bid] = Band(bid, 1, offset_to_axial(col, 5), 40, 800.0)
        sites.make_camp(st, bid)
        villages.found(st, bid)
    assert chiefs.autonomy_rate(st, far) > indocile * 2
    labels = [lab for lab, _v in chiefs.autonomy_parts(st, far)]
    assert any("4 villages" in lab for lab in labels) and any("Indocile" in lab for lab in labels)


def test_a_settled_people_loses_clans_to_their_own_people_not_to_neighbours():
    st = _tribe()
    new = chiefs.secede(st, 3)
    assert new and st.tribes[new].origin == 1 and st.tribes[new].civ in (0, 1)


def test_an_emancipated_clan_does_not_crumble_and_goes_to_found_its_village():
    from src.kora import ai

    st = _tribe()
    st.bands[3].population = 90
    new = chiefs.emancipate(st, 3)
    band = st.bands[3]
    assert new and ai._settler(st, band)
    assert not ai._should_split(st, band, 10.0)
    spot = ai.find_new_land(st, band)
    assert spot is not None and ai.good_land(st, new, spot, ai.CROWDED_SPACING)


def test_nobody_waits_forever_when_many_peoples_live():
    from src.kora import peoples

    assert peoples.MAX_LIVING_TRIBES >= 100
