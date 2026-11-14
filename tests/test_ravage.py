"""Le ravage (ravage.py) : une troupe dans les champs d'un village ennemi
detruit sa recolte, vit sur le pays, fait monter l'avantage de guerre ; le
village peut sortir ; assiege et affame, il se rend."""

import random

import pytest

from src.kora import chiefdom, chiefs, commands, diplo, events, guerre, orders, places, ravage, siege, sites, tech, troupes, villages
from src.kora.clock import Clock
from src.kora.gamestate import GameState
from src.kora.types import Band, Terrain, Tribe
from src.kora.world import make_filled_world, offset_to_axial

NEO = {"huttes", "semis", "sedentarite", "palissade", "arc", "palabres", "messagers"}


def _state():
    world = make_filled_world(60, 30, Terrain.PLAINE, wrap_x=True)
    st = GameState(
        world=world,
        clock=Clock(),
        tribes={
            1: Tribe(1, "Kora", 30, True, knowledge=set(tech.START_KNOWLEDGE) | NEO, culture="joueur"),
            2: Tribe(2, "Ennemis", 30, False, knowledge=set(tech.START_KNOWLEDGE) | NEO),
        },
        bands={},
        next_band_id=50,
    )
    st.rng = random.Random(3)
    st.clock.week = 20
    world.fill_season(st.clock.season())
    return st


def _village(st, tid, bid, pop=220, col=20, row=15):
    b = Band(bid, tid, offset_to_axial(col, row), pop, 4000.0)
    st.bands[bid] = b
    chiefs.ensure(st)
    sites.make_camp(st, bid)
    return villages.found(st, bid), b


def _post(army, col, row):
    army.position = offset_to_axial(col, row)
    army.fu = army.fv = -1
    army.path = []


@pytest.fixture()
def war():
    """Deux villages a douze cases, en guerre declaree ; une troupe du
    premier est postee dans les champs du second."""
    st = _state()
    home, village_a = _village(st, 1, 1, col=10)
    target, village_b = _village(st, 2, 2, col=22)
    assert home is not None and target is not None
    diplo.make_contact(st, 1, 2, quiet=True)
    assert guerre.needs_declaration(st, 1, 2)
    guerre.declare_war(st, 1, 2, 2)
    army = troupes.raise_army(st, village_a.id, troupes.LEVY_SHARE["masse"])
    assert army is not None
    _post(army, 21, 15)
    # Des champs semes.
    villages.sow(st, target, village_b)
    assert target.data.sown_ratio > 0 and target.data.fields
    return st, army, target, village_b, home, village_a


def test_block_says_why_and_target_is_the_enemy_village(war):
    st, army, target, village_b, home, _va = war
    assert ravage.target_of(st, army) is target
    assert ravage.block(st, army) == ""
    _post(army, 40, 3)
    assert "Aucun village ennemi" in ravage.block(st, army)
    _post(army, 21, 15)
    guerre.end_war(st, army.tribe_id, target.tribe_id)
    assert "en paix" in ravage.block(st, army)


def test_ravage_destroys_the_crop_feeds_the_troop_and_gives_the_lead(war):
    st, army, target, village_b, _home, _va = war
    before = villages.expected_harvest(st, target, village_b)
    assert before > 0
    assert ravage.start(st, army) == places.name(target)
    food = army.stock
    for _ in range(4):
        st.tick_count += 1
        ravage.weekly(st)
    assert target.data.ravage == 4 and target.data.ravager == army.tribe_id
    assert 0 < target.data.ravaged <= ravage.MAX
    assert villages.expected_harvest(st, target, village_b) == pytest.approx(before * (1 - target.data.ravaged))
    assert army.stock > food
    assert army.population >= ravage.MEN
    assert guerre.score(st, army.tribe_id, target.tribe_id) == pytest.approx(4 * ravage.SCORE)
    assert ravage.food_mult(st, target) == pytest.approx(ravage.FOOD)
    assert ("Champs ravagés", ravage.STABILITY) in ravage.stability_parts(st, target.tribe_id)
    assert ravage.lines(st, target)
    # Jamais tout : il reste toujours une part de la recolte.
    for _ in range(40):
        st.tick_count += 1
        ravage.weekly(st)
    assert target.data.ravaged == pytest.approx(ravage.MAX)


def test_ravage_stops_when_the_troop_leaves_and_at_peace(war):
    st, army, target, _vb, _home, _va = war
    ravage.start(st, army)
    ravage.weekly(st)
    assert target.data.ravage == 1
    out = commands.apply(st, commands.make(army.tribe_id, "goto", army.id, *offset_to_axial(40, 3)))
    assert out["msg"] == "" and army.ravage == 0
    ravage.weekly(st)
    assert target.data.ravage == 0 and target.data.ravager == 0
    _post(army, 21, 15)
    ravage.start(st, army)
    ravage.weekly(st)
    assert target.data.ravage == 1
    guerre.end_war(st, army.tribe_id, target.tribe_id)
    diplo.add_pact(st, army.tribe_id, target.tribe_id, "treve", 104)
    ravage.weekly(st)
    assert army.ravage == 0 and target.data.ravage == 0


def test_sowing_and_harvest_reset_the_ravaged_share(war):
    st, army, target, village_b, _home, _va = war
    ravage.start(st, army)
    for _ in range(3):
        ravage.weekly(st)
    assert target.data.ravaged > 0
    villages.harvest(st, target, village_b)
    assert target.data.ravaged == 0
    target.data.ravaged = 0.3
    villages.sow(st, target, village_b)
    assert target.data.ravaged == 0


def test_the_herd_can_be_driven_off_and_the_pen_stays_empty(war):
    st, army, target, village_b, _home, _va = war
    target.data.buildings["enclos"] = 1
    ravage.start(st, army)
    for _ in range(60):
        st.tick_count += 1
        ravage.weekly(st)
        if target.data.herd_lost > st.tick_count:
            break
    assert target.data.herd_lost > st.tick_count
    assert ravage.food_mult(st, target) < ravage.FOOD + 1e-9
    assert any("Troupeau volé" in line for line in ravage.lines(st, target))
    assert ("Troupeau volé", ravage.HERD_STABILITY) in ravage.stability_parts(st, target.tribe_id)


def test_the_player_orders_it_from_the_troop_card(war):
    st, army, target, _vb, _home, _va = war
    assert orders.band_actions(st, army.id)["camp"] == ""
    assert orders.labels(st, army.id)["camp"] == "Ravager [C]"
    out = commands.apply(st, commands.make(army.tribe_id, "band", army.id, "camp"))
    assert army.ravage == target.id and "ravage" in out["msg"]
    assert orders.labels(st, army.id)["camp"] == "Cesser [C]"
    commands.apply(st, commands.make(army.tribe_id, "band", army.id, "camp"))
    assert army.ravage == 0


def test_the_village_sorties_with_all_its_men(war):
    st, army, target, village_b, _home, _va = war
    ravage.start(st, army)
    ravage.weekly(st)
    out = ravage.sortie(st, village_b)
    assert out is not None and out.kind == "armee" and out.tribe_id == village_b.tribe_id
    assert out.order.target_band_id == army.id


def test_a_starving_besieged_village_opens_its_gates(war):
    st, army, target, village_b, _home, _va = war
    tech.grant(st.tribes[army.tribe_id], "siege")
    tech.invalidate()
    if not tech.bonuses(st.tribes[army.tribe_id]).siege:
        pytest.skip("le savoir du siege a change de nom")
    _post(army, 22, 14)
    village_b.stock = 0.0
    for _ in range(ravage.SURRENDER_WEEKS + 1):
        st.tick_count += 1
        siege.weekly(st)
        ravage.weekly(st)
    assert target.data.siege == 0
    assert chiefdom.overlord_of(st, village_b.tribe_id) == army.tribe_id or target.data.burned


def test_war_tribute_ends_the_war(war):
    st, army, target, _vb, _home, _va = war
    a, b = army.tribe_id, target.tribe_id
    guerre.add_score(st, a, b, 60)
    assert guerre.tribute_peace(st, a, b)
    assert not guerre.declared_war(st, a, b)
    assert guerre.score(st, a, b) == 0
    assert not guerre.tribute_peace(st, a, b)


def test_the_event_card_exists_and_its_words_are_known():
    ev = events.EVENTS["ravage_subi"]
    assert ev.trigger == "ravage_subi" and len(ev.options) == 3
    conds, effects, texts = events.vocabulary()
    assert "can_sortie" in conds and {"sortie", "war_tribute"} <= set(effects)
    assert texts["sortie"](()) and texts["war_tribute"](())


def test_the_ravage_is_saved_and_reloaded(war, tmp_path):
    from src.kora.persist import load_game, save_game

    st, army, target, _vb, _home, _va = war
    ravage.start(st, army)
    for _ in range(3):
        st.tick_count += 1
        ravage.weekly(st)
    target.data.herd_lost = st.tick_count + 30
    target.data.starved = 2
    path = tmp_path / "kora.json"
    save_game(st, path, {})
    loaded, _ = load_game(path, st.world)
    data = loaded.sites[target.id].data
    assert loaded.bands[army.id].ravage == target.id
    assert (data.ravage, data.ravager, data.herd_lost, data.starved) == (3, army.tribe_id, st.tick_count + 30, 2)
    assert data.ravaged == pytest.approx(target.data.ravaged)


def test_an_old_save_has_no_ravage():
    from src.kora.places import VillageData
    from src.kora.types import Band

    data = VillageData()
    assert (data.ravage, data.ravager, data.ravaged, data.herd_lost, data.starved) == (0, 0, 0.0, 0, 0)
    assert Band(1, 1, offset_to_axial(1, 1), 10, 0.0).ravage == 0


def test_the_ai_world_at_war_keeps_running(war):
    """Un village IA dont on ravage les champs, une troupe IA qui ravage :
    la semaine du monde tourne sans erreur."""
    from src.kora.sim import tick

    st, army, target, _vb, _home, _va = war
    st.tribes[1].is_player = False
    ravage.start(st, army)
    for _ in range(12):
        tick(st)
        assert st.last_error is None, st.last_trace


def test_a_handful_of_men_gives_little_lead(war):
    st, army, target, _vb, _home, _va = war
    army.units = [[army.units[0][0], 5, army.units[0][2]]]
    army.population = 5
    ravage.start(st, army)
    st.tick_count += 1
    ravage.weekly(st)
    assert guerre.score(st, army.tribe_id, target.tribe_id) == pytest.approx(ravage.SCORE * 5 / ravage.MEN)
