"""La confederation (confed.py) : deux peuples, un seul pays au dehors."""

from src.kora import battle, chiefdom, confed, diplo, events, tech
from src.kora.world import offset_to_axial
from test_approach import _state


def _pair():
    """2 et 3 voisins, de force comparable, amis, qui connaissent
    Confederation ; le joueur (1) en contact avec les deux."""
    st = _state(strong=100, weak=90, known=("mariages", "confederation"))
    st.tribes[3].knowledge |= {"mariages", "confederation"}
    st.bands[1].position = offset_to_axial(40, 20)
    diplo.make_contact(st, 1, 2, quiet=True)
    diplo.make_contact(st, 1, 3, quiet=True)
    diplo.add_mod(st, 2, 3, "cadeau", 60, actor=2)
    tech.invalidate()
    return st


def test_two_peoples_confederate_and_share_their_peace():
    st = _pair()
    diplo.add_pact(st, 2, 1, "treve", diplo.TRUCE_WEEKS)
    assert not diplo.evaluate(st, 2, 3, "confederer").blocked
    confed.form(st, 2, 3)
    assert confed.members(st, 2) == (2, 3) and confed.same(st, 3, 2)
    assert confed.leader(st, 3) == 2 and "Akor" in confed.name(st, 3)
    # La treve de l'un engage l'autre ; l'alliance conclue ensuite aussi.
    assert diplo.has_pact(st, 3, 1, "treve")
    diplo.add_pact(st, 3, 1, "alliance")
    assert diplo.allied(st, 2, 1)
    assert ("Même confédération", 20.0) in diplo.reasons(st, 2, 3)
    assert "Confédérés" in diplo.status_line(st, 2, 3)
    # Ils ne se raident pas.
    assert diplo.at_peace(st, 2, 3)


def test_a_raid_against_one_is_a_raid_against_all():
    st = _pair()
    confed.form(st, 2, 3)
    diplo.add_pact(st, 2, 1, "treve", diplo.TRUCE_WEEKS)
    assert diplo.has_pact(st, 1, 3)
    diplo.on_fight(st, 1, 3, True, True)
    assert not diplo.has_pact(st, 1, 2) and not diplo.has_pact(st, 1, 3)
    assert any(m.key == "raid_pays" for m in st.diplo.mods.get(diplo.pair(1, 2), []))


def test_confederates_come_to_help_in_war():
    st = _pair()
    st.bands[3].position = offset_to_axial(22, 20)
    assert st.bands[2] not in battle.helpers_of(st, st.bands[3])
    confed.form(st, 2, 3)
    assert st.bands[2] in battle.helpers_of(st, st.bands[3])


def test_vassalage_breaks_the_confederation():
    st = _pair()
    confed.form(st, 2, 3)
    chiefdom.make_vassal(st, 1, 3, "force")
    assert confed.members(st, 3) == (3,)
    assert "tributaire" in confed.block(st, 2, 3)


def test_the_proposal_needs_the_knowledge_and_friendship():
    st = _pair()
    st.tribes[2].knowledge.discard("confederation")
    tech.invalidate()
    assert "Confédération" in diplo.evaluate(st, 2, 3, "confederer").blocked
    st.tribes[2].knowledge.add("confederation")
    tech.invalidate()
    st.diplo.mods.clear()
    assert "Relation" in diplo.evaluate(st, 2, 3, "confederer").blocked


def test_a_player_receives_a_card_and_accepting_confederates():
    st = _pair()
    diplo.add_mod(st, 1, 2, "cadeau", 60, actor=2)
    st.tribes[1].knowledge |= {"mariages", "confederation"}
    tech.invalidate()
    st.story = True
    out = diplo.perform(st, 2, 1, "confederer")
    assert "à eux de décider" in out
    inst = next(p for p in events.pending(st, 1) if p.event_id == "offre_confederation")
    events.choose(st, inst.uid, 0)
    assert confed.same(st, 1, 2)


def test_an_ai_chief_leaves_when_friendship_is_gone():
    st = _pair()
    confed.form(st, 2, 3)
    st.diplo.mods.clear()
    diplo.add_mod(st, 2, 3, "raid", -80, actor=2)
    confed.monthly(st)
    assert confed.members(st, 2) == (2,)


def test_a_tributary_takes_a_light_shade_of_its_overlord_and_gets_its_own_back():
    from src.kora import look
    from src.kora.peoples import color_of

    st = _pair()
    own3, own2, own1 = color_of(st.tribes[3]), color_of(st.tribes[2]), color_of(st.tribes[1])
    assert look.country_color(st, 3) == own3
    chiefdom.make_vassal(st, 2, 3, "force")
    shade = look.country_color(st, 3)
    dist = lambda a, b: sum(abs(x - y) for x, y in zip(a, b))
    assert dist(shade, own2) < dist(shade, own3) and shade != own2
    assert look.realm_of(st, 3) == 2 and look.great_realms(st) == [(2, [2, 3])]
    # Un autre suzerain : la nuance du nouveau.
    chiefdom.make_vassal(st, 1, 3, "force")
    assert dist(look.country_color(st, 3), own1) < dist(look.country_color(st, 3), own2)
    # Libre : sa couleur a lui.
    st.diplo.pacts.pop(diplo.pair(1, 3), None)
    assert look.country_color(st, 3) == own3


def test_confederates_read_as_one_country():
    from src.kora import look
    from src.kora.peoples import color_of

    st = _pair()
    confed.form(st, 2, 3)
    assert look.realm_of(st, 3) == 2 and look.country_color(st, 2) == color_of(st.tribes[2])
    assert look.country_color(st, 3) != color_of(st.tribes[3])
