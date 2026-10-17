"""Se liberer d'un suzerain n'est plus un simple clic (2026-10-17) : un
tributaire ne rompt pas son serment comme un accord ; il doit se REVOLTER,
pas avant la fin du serment (deux ans, quatre avec Otages et serments) ; le
parjure coute du prestige ; et le pays du suzerain lui fait aussitot la
guerre pour le soumettre a nouveau (un but, un motif). L'IA suit la meme
regle (la crise des tributaires ratee : la guerre, plus la liberte d'office).
Le suzerain, lui, peut toujours affranchir son tributaire."""

from src.kora import chiefdom, diplo, guerre, situations, tech
from test_war_goals import _three


def _vassal_state():
    """1 suzerain de 2 ; 3 est un autre tributaire de 1 ; tous ont la
    diplomatie et des villages."""
    st = _three()
    chiefdom.make_vassal(st, 1, 2, "force")
    chiefdom.make_vassal(st, 1, 3, "force")
    return st


def _age(st, weeks):
    st.tick_count += weeks


def test_a_tributary_cannot_just_break_its_oath():
    st = _vassal_state()
    _age(st, 400)
    v = diplo.evaluate(st, 2, 1, "rompre")
    assert v.blocked and "révolte" in v.blocked
    assert "Rompre" not in diplo.perform(st, 2, 1, "rompre")
    assert chiefdom.overlord_of(st, 2) == 1
    # Avec un autre pacte (des echanges), on rompt l'accord, pas le serment.
    diplo.add_pact(st, 1, 2, "commerce")
    diplo.perform(st, 2, 1, "rompre")
    assert chiefdom.overlord_of(st, 2) == 1 and not diplo.has_pact(st, 1, 2, "commerce")


def test_the_oath_holds_two_years_four_with_hostages():
    st = _vassal_state()
    assert diplo.evaluate(st, 2, 1, "revolte").blocked
    assert guerre.oath_left(st, 2, 1) == tech.VASSAL_OATH_WEEKS
    _age(st, tech.VASSAL_OATH_WEEKS)
    assert not diplo.evaluate(st, 2, 1, "revolte").blocked
    st.tribes[1].knowledge.add("otages")
    tech.invalidate()
    assert guerre.oath_weeks(st, 1) == 2 * tech.VASSAL_OATH_WEEKS
    assert "otages" in diplo.evaluate(st, 2, 1, "revolte").blocked


def test_a_revolt_is_a_war_against_the_whole_country():
    st = _vassal_state()
    _age(st, tech.VASSAL_OATH_WEEKS + 1)
    prestige = st.tribes[2].prestige = 40
    out = diplo.perform(st, 2, 1, "revolte")
    assert "révoltez" in out
    assert chiefdom.overlord_of(st, 2) == 0, "le pacte tombe"
    assert st.tribes[2].prestige == prestige - guerre.PERJURY_PRESTIGE
    assert guerre.declared_war(st, 1, 2), "le suzerain lui fait la guerre"
    assert guerre.declared_war(st, 3, 2), "son autre tributaire aussi"
    assert guerre.goal_of(st, 1, 2), "pour le soumettre à nouveau"
    assert guerre.casus_of(st, 1, 2), "avec un motif : pas de honte"
    assert chiefdom.overlord_of(st, 3) == 1


def test_beaten_the_rebel_serves_again():
    st = _vassal_state()
    _age(st, tech.VASSAL_OATH_WEEKS + 1)
    diplo.perform(st, 2, 1, "revolte")
    guerre.submit(st, 1, 2)
    assert chiefdom.overlord_of(st, 2) == 1
    assert not guerre.declared_war(st, 1, 2)


def test_the_lord_can_still_free_a_tributary():
    st = _vassal_state()
    assert not diplo.evaluate(st, 1, 2, "rompre").blocked
    diplo.perform(st, 1, 2, "rompre")
    assert chiefdom.overlord_of(st, 2) == 0


def test_a_failed_ai_crisis_brings_a_war_not_a_free_pass():
    st = _vassal_state()
    _age(st, tech.VASSAL_OATH_WEEKS + 1)
    spec = situations.SPECS["tributaires"]
    inst = situations._start(st, spec, None, 6, [1], {"vassal": 2})
    inst.outcome = "ratee"
    spec.end(st, inst)
    assert chiefdom.overlord_of(st, 2) == 0
    assert guerre.declared_war(st, 1, 2) and guerre.goal_of(st, 1, 2)


def test_no_tributary_crisis_while_the_oath_is_fresh(monkeypatch):
    st = _vassal_state()
    monkeypatch.setattr(chiefdom, "unrest", lambda state, v, lord: 100.0)
    spec = situations.SPECS["tributaires"]
    assert spec.candidates(st) == []
    _age(st, tech.VASSAL_OATH_WEEKS)
    assert {c[3]["vassal"] for c in spec.candidates(st)} == {2, 3}


def test_the_hostages_say_what_they_do():
    lines = tech.effect_lines(tech.TECHS["otages"])
    assert any("révolter avant 4 ans" in line for line in lines)
