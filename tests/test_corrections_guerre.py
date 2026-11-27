"""Les corrections de la guerre et de la diplomatie (revue du 2026-11-27) :
une bande n'est jamais dans les deux camps ; un village pris et soumis le
reste ; pas de guerre a l'interieur d'un pays ; une seule paix (celle des
deux pays) ; un tribut, une alliance ou une treve avec le pays vise
empechent la guerre ; un ordre d'attaque accepte est une bataille qui aura
lieu ; une partie rechargee fait la meme suite ; le tribut ne se perd pas."""

import copy
import json
import types

from src.kora import battle, casus, chiefdom, commands, confed, diplo, events, guerre, orders, persist, sim, tech, troupes
from src.kora.bands import stock_max
from src.kora.types import Band, Order, OrderKind
from test_war_goals import _three


def _camps_ok(st) -> None:
    """L'invariant : aucune bande dans les deux camps d'une bataille."""
    for bt in battle.battles(st):
        assert not set(bt.attackers) & set(bt.defenders), (bt.attackers, bt.defenders)


def _no_inner_war(st) -> None:
    """L'invariant : pas de guerre declaree entre deux peuples d'un meme pays."""
    for (a, b), pacts in st.diplo.pacts.items():
        if any(p.kind == guerre.WAR for p in pacts):
            assert b not in chiefdom.country(st, a), (a, b)


def _kin(st, *tids) -> None:
    """Villages freres, une meme civilisation."""
    for t in tids:
        st.tribes[t].civ = 7
        tech.grant(st.tribes[t], "freres")
    tech.invalidate()


def _clan(st, bid, tid, where, pop=60):
    band = Band(bid, tid, where, pop, 400.0)
    st.bands[bid] = band
    return band


# --- 1. les deux camps -----------------------------------------------------------------


def test_a_kin_village_at_war_is_never_on_both_sides():
    """Avant : un "village frere" (meme civilisation) venait en renfort de
    celui qui l'attaquait (14 batailles sur 63 en dix ans de sa partie)."""
    st = _three()
    _kin(st, 1, 2, 3)
    assert 2 in chiefdom.kin_of(st, 1)
    guerre.declare_war(st, 1, 2, 2)
    assert 2 not in chiefdom.kin_of(st, 1) and not chiefdom.is_kin(st, 1, 2)
    village = st.bands[2]
    army = troupes.raise_army(st, 1)
    army.position = village.position
    # Un frere en paix avec les deux (la diplomatie, pas de guerre) : il ne
    # vient d'aucun cote.
    cousin = _clan(st, 60, 3, village.position)
    bt = battle.start(st, army, village, village.position, hunted=True)
    _camps_ok(st)
    assert village.id not in bt.attackers and cousin.id not in bt.attackers + bt.defenders
    while not battle.day(st, bt):
        _camps_ok(st)


def test_reinforcements_follow_the_same_rule_as_the_start():
    """Les renforts qui arrivent : la meme regle qu'au depart (le pays, les
    allies, les freres en guerre), plus seulement les allies d'un pacte."""
    st = _three()
    chiefdom.make_vassal(st, 1, 3, "force")
    guerre.declare_war(st, 1, 2, 2)
    village = st.bands[2]
    army = troupes.raise_army(st, 1)
    army.position = village.position
    bt = battle.start(st, army, village, village.position, hunted=True)
    # Le tributaire du suzerain arrive sur le champ de bataille : il est de
    # son pays, en guerre avec les memes ; il rejoint l'attaque.
    vassal_band = _clan(st, 61, 3, bt.hex)
    battle.resolve_raids(st)
    assert vassal_band.id in bt.attackers and vassal_band.id not in bt.defenders
    _camps_ok(st)
    assert battle.may_help(st, 3, 1, 2) and not battle.may_help(st, 3, 2, 1)


# --- 2. le village pris et soumis ----------------------------------------------------------


def test_a_village_taken_and_subdued_by_the_ai_stays_subdued_without_treason():
    """Avant : diplo.on_fight effacait le serment ne de la prise, et le
    vainqueur passait pour traitre (prestige -10)."""
    st = _three()
    guerre.declare_war(st, 3, 2, 2)
    village = st.bands[2]
    host = _clan(st, 62, 3, village.position, pop=900)
    host.order = Order(OrderKind.MARCH_TO_BAND, target_band_id=village.id)
    st.tick_count = 30
    res = battle.fight(st, host, village, village.position)
    assert res.outcome == "pris"
    assert chiefdom.overlord_of(st, 2) == 3, "le serment né de la prise reste"
    assert not diplo._betrayer(st, 3)


def test_a_fight_between_lord_and_tributary_does_not_break_the_oath():
    st = _three()
    chiefdom.make_vassal(st, 1, 2, "force")
    st.tick_count = 20
    diplo.on_fight(st, 1, 2, True, True, since=20)
    assert chiefdom.overlord_of(st, 2) == 1, "le serment ne tombe que par la révolte ou l'affranchissement"
    assert diplo._betrayer(st, 1), "se battre malgré lui reste une trahison"


# --- 3. pas de guerre a l'interieur d'un pays ----------------------------------------------


def test_two_peoples_who_become_one_country_stop_their_war():
    st = _three()
    guerre.declare_war(st, 2, 3, 3)
    chiefdom.make_vassal(st, 1, 2, "force")
    chiefdom.make_vassal(st, 1, 3, "force")
    assert not guerre.declared_war(st, 2, 3) and (2, 3) not in st.diplo.goals
    _no_inner_war(st)
    # La soumission par la guerre (guerre.submit), et la confederation.
    st = _three()
    guerre.declare_war(st, 2, 3)
    guerre.declare_war(st, 1, 3, 3)
    guerre.submit(st, 1, 3)
    chiefdom.make_vassal(st, 1, 2, "protection")
    _no_inner_war(st)
    st = _three()
    guerre.declare_war(st, 2, 3)
    confed.form(st, 2, 3)
    assert not guerre.declared_war(st, 2, 3)
    _no_inner_war(st)


# --- 4. une seule paix -------------------------------------------------------------------


def _realm_at_war():
    """3 a pour tributaire 2 ; 1 (le joueur) leur fait la guerre."""
    st = _three()
    chiefdom.make_vassal(st, 3, 2, "force")
    guerre.declare_war(st, 1, 2, 2)
    assert guerre.declared_war(st, 1, 3)
    return st


def _country_peace(st) -> None:
    assert not guerre.declared_war(st, 1, 2) and not guerre.declared_war(st, 1, 3)
    assert diplo.has_pact(st, 1, 2, "treve") and diplo.has_pact(st, 1, 3, "treve")
    assert diplo.evaluate(st, 3, 1, "guerre").blocked, "le suzerain ne redéclare pas la semaine suivante"
    assert not st.diplo.goals


def test_the_peace_card_makes_peace_with_the_whole_country():
    """Avant : la carte posait une treve sans finir la guerre ; le joueur
    restait en guerre avec le suzerain."""
    st = _realm_at_war()
    events._eff_pact(st, types.SimpleNamespace(other=2), st.tribes[1], None, "treve")
    _country_peace(st)


def test_a_truce_with_a_tributary_is_treated_with_its_overlord(monkeypatch):
    """Avant : l'ecran Peuples finissait la guerre des deux pays mais ne
    posait la treve qu'avec le tributaire ; le suzerain redeclarait."""
    st = _realm_at_war()
    assert diplo.peace_partner(st, 1, 2) == 3
    v = diplo.evaluate(st, 1, 2, "treve")
    assert "suzerain" in v.reasons[0][0]
    monkeypatch.setattr(guerre, "truce_mood", lambda state, a, t: [("Lassitude", 200)])
    text = diplo.perform(st, 1, 2, "treve")
    assert st.tribes[3].name in text
    _country_peace(st)


def test_a_war_tribute_is_the_same_peace():
    st = _realm_at_war()
    assert guerre.tribute_peace(st, 1, 2)
    _country_peace(st)


# --- 5 et 6. ce qui lie au pays vise ---------------------------------------------------------


def test_a_war_tribute_still_paid_forbids_a_new_war(monkeypatch):
    """Avant : l'IA redeclarait la guerre a qui lui payait encore le tribut."""
    st = _three()
    diplo.add_pact(st, 3, 2, "tribut", diplo.TRIBUTE_WEEKS, payer=2)
    assert diplo.evaluate(st, 3, 2, "guerre").blocked == "Un tribut vous lie : rompez-le d'abord"
    st.tribes[3].approach = "conquerant"
    st.bands[3].population = 900
    st.bands[1].population = 800
    monkeypatch.setattr(casus, "CONQUER_CHANCE", 1.1)
    st.tick_count = 4
    casus._ai_wars(st)
    assert not guerre.declared_war(st, 3, 2) and diplo.has_pact(st, 3, 2, "tribut")


def test_an_alliance_or_truce_with_the_overlord_forbids_war_on_its_tributary():
    """Avant : declarer la guerre au tributaire d'un allie rompait
    l'alliance en silence."""
    for kind, word in (("alliance", "alliés des"), ("treve", "trêve vous lie aux")):
        st = _three()
        diplo.add_pact(st, 1, 3, kind)
        chiefdom.make_vassal(st, 3, 2, "force")
        v = diplo.evaluate(st, 1, 2, "guerre")
        assert word in v.blocked
        diplo.perform(st, 1, 2, "guerre")
        assert not guerre.declared_war(st, 1, 2) and diplo.has_pact(st, 1, 3, kind)
    # Un allie de la cible lie a l'attaquant reste hors de la guerre.
    st = _three()
    diplo.add_pact(st, 2, 3, "alliance")
    diplo.add_pact(st, 1, 3, "treve", diplo.TRUCE_WEEKS)
    assert guerre.war_allies(st, 2, 1) == []
    guerre.declare_war(st, 1, 2)
    assert not guerre.declared_war(st, 1, 3) and diplo.has_pact(st, 1, 3, "treve")


# --- 7. un ordre d'attaque est une bataille qui aura lieu -------------------------------------


def test_a_motive_is_not_a_war_and_the_attack_order_says_so():
    """Avant : un simple motif suffisait a l'ordre ; la bataille (qui exige
    une guerre declaree) n'avait jamais lieu, la troupe attendait."""
    st = _three()
    army = troupes.raise_army(st, 1)
    guerre.set_casus(st, 1, 2, 52, "Terres disputées")
    assert guerre.at_war(st, 1, 2) and not guerre.declared_war(st, 1, 2)
    out = commands.apply(st, commands.make(1, "march", army.id, 2))
    assert "motif" in out["msg"] and "déclarez-leur" in out["msg"]
    assert army.order.kind is not OrderKind.MARCH_TO_BAND
    assert "déclarez-leur" in orders.attack_preview(st, army.id, 2)["blocked"]
    guerre.declare_war(st, 1, 2, 2)
    assert commands.apply(st, commands.make(1, "march", army.id, 2))["msg"] == ""
    assert army.order.kind is OrderKind.MARCH_TO_BAND
    # La paix vient pendant la marche : la troupe s'arrete (et le dit).
    guerre.make_peace(st, 1, 2)
    sim.apply_movement(st)
    assert army.order.kind is OrderKind.STAY and not army.path
    assert any("Pas de guerre déclarée" in e.text for e in st.log.entries)


# --- 8. une partie rechargee fait la meme suite ----------------------------------------------

_SETS = ("explored", "exhaustion", "influence", "pressure", "overlap")


def _norm(st) -> dict:
    """L'etat sauve, sans ce qui n'a pas d'ordre (des ensembles) ; 5 == 5.0."""
    d = json.loads(persist.dumps_game(st))
    d.pop("view", None)
    for key in _SETS:
        d[key] = sorted(d.get(key, []), key=json.dumps)
    d["presence"] = sorted([t, sorted(spots)] for t, spots in d.get("presence", []))
    for _t, pov in d.get("povs", []):
        pov["explored"] = sorted(pov.get("explored", []))
    return d


def _tributes():
    """Une partie deja relue une fois, puis deux tributs du meme payeur
    poses dans un ordre qui n'est pas le tri (2-3 avant 1-2)."""
    base = _three()
    st, _view = persist.loads_game(persist.dumps_game(base), base.world)
    sim.tick(st)
    diplo.add_pact(st, 2, 3, "tribut", 520, payer=2)
    diplo.add_pact(st, 1, 2, "tribut", 520, payer=2)
    for p in diplo.pacts_between(st, 2, 3) + diplo.pacts_between(st, 1, 2):
        p.paid = -20
    # Le payeur n'a pas de quoi payer les deux tributs en entier : l'ordre
    # des pactes decide qui recoit le plus (relu trie, la suite s'ecartait a
    # la 3e semaine).
    st.bands[2].stock = 3 * st.bands[2].population + 150.0
    for b in (1, 3):
        st.bands[b].stock = 4000.0
    return st


def test_the_diplomacy_keeps_its_order_through_a_save():
    """Avant : la sauvegarde triait les pactes ; la partie relue payait les
    tributs dans un autre ordre (diplo.monthly), et s'ecartait."""
    st = _tributes()
    back, _view = persist.loads_game(persist.dumps_game(st), copy.deepcopy(st.world))
    for name in ("mods", "pacts", "casus", "raids", "casus_why", "goals", "scores"):
        assert list(getattr(back.diplo, name)) == list(getattr(st.diplo, name)), name
    assert list(back.diplo.pacts)[-2:] == [(2, 3), (1, 2)]
    for s in (st, back):
        s.bands[2].stock = s.bands[2].population + 150.0
        s.bands[1].stock = s.bands[3].stock = 1000.0
        diplo.monthly(s)
    assert [round(b.stock, 3) for b in sorted(st.bands.values(), key=lambda b: b.id)] == [
        round(b.stock, 3) for b in sorted(back.bands.values(), key=lambda b: b.id)
    ]
    assert st.bands[3].stock > st.bands[1].stock, "le premier pacte arrivé est payé d'abord"


def test_a_reloaded_game_plays_the_same_weeks():
    """Sauver, relire, jouer N semaines : la meme suite que sans recharger."""
    a = _tributes()
    b, _view = persist.loads_game(persist.dumps_game(a), copy.deepcopy(a.world))
    for week in range(16):
        sim.tick(a)
        sim.tick(b)
        assert a.last_error is None and b.last_error is None
        assert _norm(a) == _norm(b), f"la partie relue s'écarte à la semaine {week + 1}"


# --- 9. le tribut ne se perd pas ------------------------------------------------------------


def test_a_tribute_pays_only_what_the_receiver_can_carry():
    st = _three()
    diplo.add_pact(st, 1, 2, "tribut", 520, payer=2)
    pact = diplo.pacts_between(st, 1, 2)[0]
    payer, receiver = st.bands[2], st.bands[1]
    payer.stock = 4000.0
    receiver.stock = stock_max(receiver, st) - 25.0
    before = payer.stock + receiver.stock
    diplo._pay_tribute(st, pact, 1, 2)
    assert receiver.stock <= stock_max(receiver, st) + 1e-6
    assert abs(payer.stock + receiver.stock - before) < 1e-6, "rien ne se perd"
    assert any("Tribut des" in e.text and "25 vivres" in e.text for e in st.log.entries)
