"""Les guerres qui bougent : les buts de guerre (soumettre un peuple, ou
tout son pays), l'usure des alliances (P1), les conquerants qui trahissent
(P2), les causes de guerre (P3), l'accord commercial qui n'empeche plus la
guerre (P4)."""

import random

from src.kora import ai_war, casus, chiefdom, chiefs, diplo, events, tech
from src.kora.persist import load_game, save_game
from src.kora.types import Band
from test_ost_siege import _state, _village


def _three():
    """Trois peuples a villages, qui se connaissent (diplomatie : palabres)."""
    st = _state()
    a, _sa = _village(st, 1, 1, pop=300, col=10)
    b, _sb = _village(st, 2, 2, pop=120, col=22)
    c, _sc = _village(st, 3, 3, pop=150, col=34)
    for x, y in ((1, 2), (1, 3), (2, 3)):
        diplo.make_contact(st, x, y, quiet=True)
    return st


# --- P4 -------------------------------------------------------------------------------


def test_a_trade_accord_no_longer_prevents_war():
    st = _three()
    diplo.add_pact(st, 1, 2, "commerce")
    assert not diplo.peace_pact(st, 1, 2)
    assert not diplo.evaluate(st, 1, 2, "guerre").blocked
    # Sans la diplomatie : un partenaire commercial peut etre raide, et ce
    # n'est pas une trahison.
    st.tribes[1].knowledge.discard("palabres")
    tech.invalidate()
    assert not diplo.at_peace(st, 1, 2)
    assert ai_war.fair_game(st, st.bands[1], st.bands[2], hungry=True)
    prestige = st.tribes[1].prestige
    diplo.on_fight(st, 1, 2, True, True)
    assert st.tribes[1].prestige == prestige and not diplo.has_pact(st, 1, 2, "commerce")
    # Une alliance, elle, l'empeche toujours.
    diplo.add_pact(st, 1, 3, "alliance")
    assert diplo.at_peace(st, 1, 3)


# --- P1 -------------------------------------------------------------------------------


def test_an_alliance_without_a_common_enemy_wears_out():
    st = _three()
    diplo.add_pact(st, 1, 2, "alliance")
    st.tick_count += diplo.ALLIANCE_WEAR - diplo.ALLIANCE_WARN
    assert "se dénoue" in diplo.status_line(st, 1, 2)
    st.tick_count += diplo.ALLIANCE_WARN
    diplo._wear_alliances(st)
    assert not diplo.allied(st, 1, 2)
    assert diplo.on_cooldown(st, 1, 2, "alliance")


def test_a_shared_war_keeps_the_alliance_alive():
    st = _three()
    diplo.add_pact(st, 1, 2, "alliance")
    diplo.declare_war(st, 3, 1)
    assert diplo.declared_war(st, 2, 3), "l'allié de l'attaque entre en guerre"
    st.tick_count += diplo.ALLIANCE_WEAR + 4
    diplo._wear_alliances(st)
    assert diplo.allied(st, 1, 2)


# --- P3 -------------------------------------------------------------------------------


def test_disputed_land_gives_the_crowded_people_a_motive():
    st = _three()
    st.overlap = {(1, 2): casus.LAND_CELLS + 3}
    casus._land_claims(st)
    assert diplo.casus_of(st, 1, 2) == "Terres disputées" and not diplo.casus_of(st, 2, 1)
    v = diplo.evaluate(st, 1, 2, "guerre")
    assert any("motif" in label for label, _v in v.reasons)
    prestige = st.tribes[1].prestige
    diplo.declare_war(st, 1, 2, 2)
    assert st.tribes[1].prestige == prestige, "un motif : pas de honte"


def test_a_flint_deposit_in_their_lands_is_a_motive(monkeypatch):
    st = _three()
    st.tribes[1].knowledge.add("haches")
    site_b = next(s for s in st.sites.values() if s.tribe_id == 2)
    monkeypatch.setattr(casus.goods, "riches", lambda world, h: {})
    monkeypatch.setattr(casus, "_deposits_near", lambda world, h, res: [site_b.hex] if res == "silex" else [])
    monkeypatch.setattr(casus.influence, "dominant", lambda world, h: (2, 1.0))
    casus._resource_claims(st)
    assert diplo.casus_of(st, 1, 2) == "Le silex de leurs terres"


def test_a_dead_chief_opens_a_disputed_succession(monkeypatch):
    st = _three()
    diplo.add_pact(st, 1, 2, "alliance")
    casus._successions(st)
    st.tribes[2].flags["chef_pid"] = -5
    monkeypatch.setattr(casus, "SUCCESSION_CLAIM", 1.1)
    casus._successions(st)
    assert diplo.casus_of(st, 1, 2).startswith("Succession disputée")


# --- les buts de guerre -------------------------------------------------------------------


def _realm():
    """3 a pour tributaire 2 ; 1 veut soumettre 2."""
    st = _three()
    chiefdom.make_vassal(st, 3, 2, "force")
    return st


def test_a_war_to_subdue_a_tributary_is_a_war_on_its_whole_country():
    st = _realm()
    v = diplo.evaluate(st, 1, 2, "guerre")
    assert any("tout leur pays" in label for label, _v in v.reasons)
    diplo.perform(st, 1, 2, "guerre")
    assert diplo.declared_war(st, 1, 2) and diplo.declared_war(st, 1, 3), "le suzerain et ses tributaires"
    assert diplo.goal_of(st, 1, 2) and "pour les soumettre" in diplo.status_line(st, 1, 2)


def test_a_war_on_the_whole_country_aims_at_its_overlord():
    st = _realm()
    assert diplo.evaluate(st, 1, 3, "guerre_pays").blocked, "un peuple libre : la guerre simple suffit"
    assert not diplo.evaluate(st, 1, 2, "guerre_pays").blocked
    diplo.perform(st, 1, 2, "guerre_pays")
    assert diplo.goal_of(st, 1, 3) and diplo.declared_war(st, 1, 2)


def test_the_loser_submits_and_leaves_its_old_overlord():
    st = _realm()
    diplo.perform(st, 1, 2, "guerre")
    assert diplo.evaluate(st, 1, 2, "soumission").score <= 0
    for _ in range(6):
        diplo.on_fight(st, 1, 2, True, True)
    assert diplo.score(st, 1, 2) == 6 * diplo.WIN_SCORE
    v = diplo.evaluate(st, 1, 2, "soumission")
    assert v.accepted, v.reasons
    diplo.perform(st, 1, 2, "soumission")
    assert chiefdom.overlord_of(st, 2) == 1, "on ne sert qu'un suzerain"
    assert 2 not in chiefdom.vassals_of(st, 3)
    assert not diplo.declared_war(st, 1, 3) and diplo.has_pact(st, 1, 3, "treve"), "l'ancien suzerain fait la trêve"
    assert not diplo.goal_of(st, 1, 2)


def test_a_taken_village_counts_and_the_ai_subdues_it():
    st = _three()
    st.tribes[3].approach = "affame"
    diplo.declare_war(st, 3, 2, 2)
    winner, loser = st.bands[3], st.bands[2]
    site = next(s for s in st.sites.values() if s.tribe_id == 2)
    assert chiefdom.ai_choice(st, 3, 2) == "soumettre", "le but de guerre passe avant la faim"
    chiefdom.village_taken(st, winner, loser, site.id)
    assert chiefdom.overlord_of(st, 2) == 3 and not diplo.goal_of(st, 3, 2)


def test_the_ai_demands_the_submission_of_a_player_it_beats():
    st = _three()
    st.story = True
    diplo.declare_war(st, 3, 1, 1)
    diplo.add_score(st, 3, 1, 50)
    st.tick_count = 4  # son tour (un mois sur deux)
    casus._ai_submissions(st)
    assert any(p.event_id == "exige_soumission" for p in events.pending(st, 1))


# --- P2 -------------------------------------------------------------------------------


def test_a_conqueror_betrays_his_weak_ally_to_subdue_him(monkeypatch):
    st = _three()
    st.tribes[3].approach = "conquerant"
    diplo.add_pact(st, 3, 2, "alliance")
    st.bands[3].population = 900
    st.bands[1].population = 800  # le joueur, trop fort pour lui
    monkeypatch.setattr(casus, "CONQUER_CHANCE", 1.1)
    st.tick_count = 4  # son tour du mois (un peuple sur quatre)
    casus._ai_wars(st)
    assert not diplo.allied(st, 3, 2) and diplo.declared_war(st, 3, 2)
    assert diplo.goal_of(st, 3, 2) and diplo._betrayer(st, 3)


def test_goals_scores_and_motives_are_saved(tmp_path):
    st = _realm()
    diplo.set_casus(st, 1, 2, 50, "Terres disputées")
    diplo.declare_war(st, 1, 2, 2)
    diplo.add_score(st, 1, 2, 20)
    path = tmp_path / "kora.json"
    save_game(st, path, {})
    back, _ = load_game(path, st.world)
    assert diplo.goal_of(back, 1, 2) and diplo.score(back, 1, 2) == 20
    assert diplo.casus_of(back, 1, 2) == "Terres disputées"


def test_a_battle_does_not_end_the_war_with_the_rest_of_their_country():
    """Avant 0.14, le premier combat effacait la guerre avec le reste du pays."""
    st = _realm()
    diplo.declare_war(st, 1, 2, 2)
    diplo.on_fight(st, 1, 2, True, True)
    assert diplo.declared_war(st, 1, 3) and diplo.declared_war(st, 1, 2)
