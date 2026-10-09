"""0.18 : la diplomatie vient avec les villages (Messagers et serments) ;
la lassitude de la guerre (plus elle dure, plus la paix blanche tente les
deux camps)."""

from src.kora import diplo, tech
from src.kora.tech import TECHS
from test_war_goals import _three


# --- La diplomatie avec les villages ---------------------------------------------------


def test_diplomacy_comes_with_villages_not_with_palabres():
    t = TECHS["messagers"]
    assert set(t.prereqs) == {"palabres", "sedentarite"}
    assert any(c.kind == "villages" for c in t.conds)
    assert t.effects.get("diplomacy") and not TECHS["palabres"].effects.get("diplomacy")
    st = _three()
    st.tribes[2].knowledge.discard("messagers")
    tech.invalidate()
    assert "palabres" in st.tribes[2].knowledge and not diplo.diplomatic(st, 2)
    # Avant la diplomatie (chez l'un des deux) : des bandes qui s'accrochent,
    # pas de guerre declaree.
    assert not diplo.needs_declaration(st, 1, 2)
    assert "Messagers et serments" in diplo.evaluate(st, 2, 1, "guerre").blocked
    assert "attaquez-les" in diplo.evaluate(st, 1, 2, "guerre").blocked


def test_an_old_game_keeps_its_diplomacy_where_there_is_a_village():
    st = _three()
    for t in st.tribes.values():
        t.knowledge.discard("messagers")
    # Le peuple 3 n'a plus de village (une bande nomade).
    for s in [s for s in st.sites.values() if s.tribe_id == 3 and s.kind == "village"]:
        s.kind = "camp"
    st.research.pop("messagers", None)
    tech.invalidate()
    diplo.migrate(st)
    assert diplo.diplomatic(st, 1) and diplo.diplomatic(st, 2)
    assert not diplo.diplomatic(st, 3), "sans village, pas de messagers"
    st.tribes[1].knowledge.discard("messagers")
    tech.invalidate()
    diplo.migrate(st)
    assert not diplo.diplomatic(st, 1), "une seule fois (une partie migree ne se re-migre pas)"


# --- La lassitude de la guerre ---------------------------------------------------------


def test_weariness_grows_with_each_season_of_war_up_to_a_cap():
    st = _three()
    assert diplo.weariness(st, 1, 2) == 0
    diplo.declare_war(st, 1, 2)
    assert diplo.weariness(st, 1, 2) == 0, "pas avant une saison"
    st.tick_count += diplo.WEARY_SEASON
    assert diplo.weariness(st, 1, 2) == diplo.WEARY_STEP == diplo.weariness(st, 2, 1)
    st.tick_count += 52
    assert diplo.weariness(st, 1, 2) == 5 * diplo.WEARY_STEP
    st.tick_count += 52 * 10
    assert diplo.weariness(st, 1, 2) == diplo.WEARY_CAP


def test_a_long_war_turns_a_refused_truce_into_a_white_peace():
    st = _three()
    diplo.declare_war(st, 1, 2)
    fresh = diplo.evaluate(st, 1, 2, "treve")
    assert not any("Lassitude" in label for label, _v in fresh.reasons)
    st.tick_count += 52 * 6
    worn = diplo.evaluate(st, 1, 2, "treve")
    tired = dict(worn.reasons)
    assert any(label.startswith("Lassitude de la guerre (72 mois)") for label in tired)
    assert worn.score == fresh.score + diplo.WEARY_CAP


def test_the_side_that_leads_wants_its_victory_the_losing_side_wants_out():
    st = _three()
    diplo.declare_war(st, 1, 2)
    base = diplo.evaluate(st, 1, 2, "treve").score
    diplo.add_score(st, 2, 1, 60)  # les 2 menent
    leading = diplo.evaluate(st, 1, 2, "treve")
    assert ("Ils mènent la guerre", -15) in leading.reasons and leading.score == base - 15
    losing = diplo.evaluate(st, 2, 1, "treve")
    assert ("Ils perdent la guerre", 15) in losing.reasons


def test_ai_peoples_at_the_lowest_relation_still_end_a_long_war():
    """Une longue guerre fait tomber la relation au plus bas : avant 0.18,
    l'IA ne proposait plus rien sous -60, et la guerre durait des annees.
    Apres un an, la lassitude passe outre ; la reponse decide."""
    st = _three()
    st.tribes[1].is_player = False
    diplo.make_contact(st, 2, 3, quiet=True)
    diplo.declare_war(st, 3, 2)
    diplo.add_mod(st, 2, 3, "raid", -200, actor=3)
    assert diplo.relation(st, 2, 3) <= -60

    def month():
        # Chaque peuple IA regarde ses voisins un mois sur quatre.
        for _ in range(4):
            st.tick_count += 4
            diplo.ai_monthly(st)

    st.diplo.raids[(3, 2)] = (st.tick_count, 1)
    month()
    assert diplo.declared_war(st, 2, 3), "au début, la guerre continue"
    st.tick_count += 52 * 6
    st.diplo.raids[(3, 2)] = (st.tick_count, 1)
    assert diplo.weariness(st, 2, 3) == diplo.WEARY_CAP
    month()
    assert not diplo.declared_war(st, 2, 3) and diplo.has_pact(st, 2, 3, "treve"), "six ans : la paix blanche"


def test_a_weary_ai_offers_the_player_a_white_peace():
    from src.kora import events

    st = _three()
    st.story = True
    diplo.declare_war(st, 2, 1)
    st.tick_count += 52 + 26
    st.diplo.raids[(2, 1)] = (st.tick_count - 30, 1)
    assert diplo.evaluate(st, 1, 2, "treve").accepted, "les 2, las, la veulent"
    diplo._propose_to_player(st, 2, 1)
    card = next(c for c in events.pending(st, 1) if c.event_id == "offre_paix_blanche")
    assert "18 mois" in events._fmt(st, card, events.EVENTS["offre_paix_blanche"].text)
    events.choose(st, card.uid, 0)
    assert not diplo.declared_war(st, 1, 2) and diplo.has_pact(st, 1, 2, "treve")
