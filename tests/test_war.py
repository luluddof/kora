"""La guerre declaree (diplo.py) : entre peuples qui ont la diplomatie, on
ne s'attaque plus sans declarer la guerre."""

from src.kora import ai_war, battle, chiefdom, commands, diplo, tech
from src.kora.world import offset_to_axial
from test_approach import _state


def _two():
    st = _state()
    # NEO (test_approach) : Messagers et serments, la diplomatie.
    assert diplo.diplomatic(st, 2) and diplo.diplomatic(st, 3)
    return st


def test_two_diplomatic_peoples_are_at_peace_until_war_is_declared():
    st = _two()
    assert diplo.at_peace(st, 2, 3) and not diplo.hostile_intent(st, 2, 3)
    # Sans la diplomatie chez l'un : les raids restent libres.
    st.tribes[3].knowledge.discard("messagers")
    tech.invalidate()
    assert not diplo.needs_declaration(st, 2, 3) and not diplo.at_peace(st, 2, 3)
    st.tribes[3].knowledge.add("messagers")
    tech.invalidate()
    v = diplo.evaluate(st, 2, 3, "guerre")
    assert not v.blocked and any("prestige" in label for label, _v in v.reasons)
    prestige = st.tribes[2].prestige
    diplo.perform(st, 2, 3, "guerre")
    assert diplo.declared_war(st, 2, 3) and not diplo.at_peace(st, 2, 3) and diplo.hostile_intent(st, 2, 3)
    assert st.tribes[2].prestige <= prestige
    assert "En guerre" in diplo.status_line(st, 2, 3)
    assert diplo.evaluate(st, 2, 3, "guerre").blocked == "Vous êtes déjà en guerre"
    # Une treve y met fin.
    diplo.perform(st, 2, 3, "treve") if diplo.evaluate(st, 2, 3, "treve").accepted else diplo.end_war(st, 2, 3)
    diplo.end_war(st, 2, 3)
    assert not diplo.declared_war(st, 2, 3)


def test_allies_join_the_defender_and_the_country_follows():
    st = _two()
    diplo.make_contact(st, 1, 3, quiet=True)
    diplo.add_pact(st, 1, 3, "alliance")
    assert 1 in diplo.war_allies(st, 3, 2)
    diplo.declare_war(st, 2, 3)
    assert diplo.declared_war(st, 2, 1), "l'allié de 3 entre en guerre"
    assert any("déclarent la guerre" in e.text for e in st.log.entries)


def test_a_war_needs_no_alliance_or_truce_first():
    st = _two()
    diplo.add_pact(st, 2, 3, "alliance")
    assert "alliés" in diplo.evaluate(st, 2, 3, "guerre").blocked
    st = _two()
    diplo.add_pact(st, 2, 3, "treve", diplo.TRUCE_WEEKS)
    assert "trêve" in diplo.evaluate(st, 2, 3, "guerre").blocked
    st = _two()
    chiefdom.make_vassal(st, 2, 3, "force")
    assert diplo.evaluate(st, 3, 1, "guerre").blocked


def test_bands_at_peace_do_not_fight_even_when_one_marches_on_the_other():
    st = _two()
    a, b = st.bands[2], st.bands[3]
    b.position = a.position
    from src.kora.types import Order, OrderKind

    a.order = Order(OrderKind.MARCH_TO_BAND, target_band_id=b.id)
    assert not battle._will_fight(st, a, b)
    diplo.declare_war(st, 2, 3)
    assert battle._will_fight(st, a, b)


def test_the_player_must_declare_war_before_attacking():
    st = _two()
    st.bands[1].position = offset_to_axial(28, 20)
    diplo.make_contact(st, 1, 3, quiet=True)
    out = commands.apply(st, commands.make(1, "march", 1, 3))
    assert "déclarez-leur d'abord la guerre" in out["msg"]
    commands.apply(st, commands.make(1, "diplo", 3, "guerre"))
    assert diplo.declared_war(st, 1, 3)
    out = commands.apply(st, commands.make(1, "march", 1, 3))
    assert st.bands[1].order.target_band_id == 3


def test_the_ai_declares_war_when_its_raid_starts():
    st = _two()
    band, prey = st.bands[2], st.bands[3]
    assert ai_war.fair_game(st, band, prey, hungry=True)
    ai_war.start_plan(st, band, ("attack", prey))
    assert diplo.declared_war(st, 2, 3)


def test_a_war_without_fights_fades():
    st = _two()
    diplo.declare_war(st, 2, 3)
    st.tick_count += diplo.WAR_FADE_WEEKS + 1
    diplo._fade_wars(st)
    assert not diplo.declared_war(st, 2, 3)
