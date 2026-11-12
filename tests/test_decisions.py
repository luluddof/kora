"""Les decisions (decisions.py, l'onglet Decisions) : la soudure (rationner,
acheter du grain, une razzia, piller une route), les effets et le repos,
le mariage, l'IA qui decide aussi, les evenements devenus des decisions,
la sauvegarde ; l'ecran au clavier et a la souris."""

import os

os.environ.setdefault("SDL_VIDEODRIVER", "dummy")

import pygame

from src.kora import commands, decisions, diplo, events_data, goods, persist, sim, tech, villages
from src.kora.types import OrderKind, TradeRoute
from src.kora.world import offset_to_axial
from test_grain import _two
from test_ost_siege import _state, _village


def test_rationing_in_the_lean_weeks(monkeypatch):
    st, buyer, bsite, seller, ssite = _two(stock=100.0)
    tribe = st.tribes[1]
    # 100 vivres pour 200 personnes, 13 semaines avant la recolte : la soudure.
    assert decisions.status(st, 1, "rationner")[0] == "possible"
    before = villages.food_outlook(st, bsite, buyer)[1]
    out = commands.apply(st, commands.make(1, "decide", "rationner", None))
    assert out["msg"] == "Le rationnement commence."
    assert decisions.rationing(st, 1)
    assert decisions.status(st, 1, "rationner")[0] == "manque", "pas deux fois"
    # La prevision compte le rationnement ; les naissances et la stabilite aussi.
    weeks = tribe.ration_until - st.tick_count
    gain = villages.food_outlook(st, bsite, buyer)[1] - before
    assert abs(gain - weeks * (1 - decisions.RATION)) < 1e-6
    b = tech.bonuses(tribe)
    assert b.growth == decisions.RATION_GROWTH and b.stability == decisions.RATION_STABILITY
    # Chacun mange les trois quarts de sa part.
    buyer.stock = 1000.0
    pop = buyer.population
    # Rien n'est cueilli : seul le repas compte.
    monkeypatch.setattr(sim, "food_production", lambda *a, **k: 0.0)
    sim.collect_food(st)
    assert abs((1000.0 - buyer.stock) - pop * decisions.RATION) < 1e-6
    # La recolte venue, le rationnement s'en va.
    st.tick_count = tribe.ration_until
    decisions.monthly(st)
    assert not decisions.rationing(st, 1) and "ration" not in tribe.decision_effects
    assert tech.bonuses(tribe).growth == 1.0


def test_buying_grain_in_the_lean_weeks():
    st, buyer, bsite, seller, ssite = _two(stock=100.0)
    assert decisions.block(st, 1, "acheter_grain") == ""
    before = buyer.stock
    commands.apply(st, commands.make(1, "decide", "acheter_grain", None))
    assert buyer.stock > before
    # Sans partenaire : la condition dit pourquoi.
    st, buyer, bsite, seller, ssite = _two(stock=100.0)
    diplo.break_pact(st, 1, 3, "commerce")
    assert "Un peuple qui vend" in decisions.block(st, 1, "acheter_grain")


def test_a_raid_sends_a_troop_against_a_village():
    st, buyer, bsite, seller, ssite = _two(stock=100.0)
    targets = decisions.targets_of(st, 1, "razzia")
    assert ssite.id in targets
    assert "il faut choisir" in decisions.block(st, 1, "razzia").lower()
    out = commands.apply(st, commands.make(1, "decide", "razzia", ssite.id))
    assert out["msg"] == "La troupe part.", out
    army = next(b for b in st.bands.values() if b.tribe_id == 1 and b.kind == "armee")
    assert army.order.kind is OrderKind.MARCH_TO_BAND and army.order.target_band_id == seller.id


def _route_world():
    """Deux peuples qui commercent (2 vend du sel a 3), et le joueur pres de
    leur route."""
    st = _state()
    me, msite = _village(st, 1, 1, col=20, row=10)
    a, asite = _village(st, 2, 2, col=14, row=15)
    b, bsite = _village(st, 3, 3, col=26, row=15)
    route = TradeRoute(2, 3, "sel", by=2, units=10.0)
    goods.all_routes(st).append(route)
    st.tribes[3].goods["sel"] = 10.0
    return st, me, route


def test_a_troop_posted_on_a_trade_route_takes_its_share():
    st, me, route = _route_world()
    key = decisions._route_key(route)
    assert decisions.targets_of(st, 1, "piller_routes") == [key]
    out = commands.apply(st, commands.make(1, "decide", "piller_routes", key))
    assert out["msg"] == "La troupe part.", out
    army = next(b for b in st.bands.values() if b.tribe_id == 1 and b.kind == "armee")
    assert army.raid_route == key
    # Arrivee sur la route : chaque mois, la moitie de ce qui passe.
    army.position = offset_to_axial(20, 15)
    army.path = []
    taken = decisions.seize(st, route)
    assert taken == 5.0
    assert st.tribes[1].goods["sel"] == 5.0 and st.tribes[3].goods["sel"] == 5.0
    assert route.status == "pillée"
    for victim in (2, 3):
        assert any(m.key == "routes_pillees" for m in diplo.of(st).mods.get(diplo.pair(1, victim), []))
        assert diplo.of(st).casus.get((victim, 1), -1) > st.tick_count
    # Loin de la route : rien.
    army.position = offset_to_axial(20, 2)
    assert decisions.seize(st, route) == 0.0


def test_effects_last_and_decisions_rest():
    st, buyer, bsite, seller, ssite = _two(stock=4000.0)
    tribe = st.tribes[1]
    tribe.knowledge.add("ancetres")
    tech.invalidate()
    base = tech.bonuses(tribe).stability
    assert decisions.block(st, 1, "fete_morts") == ""
    decisions.take(st, 1, "fete_morts")
    assert tech.bonuses(tribe).stability == base + 4
    assert decisions.status(st, 1, "fete_morts")[0] == "repos"
    assert "En repos" in decisions.block(st, 1, "fete_morts")
    st.tick_count += 2 * 52
    decisions.monthly(st)
    assert tech.bonuses(tribe).stability == base
    st.tick_count += 3 * 52
    assert decisions.status(st, 1, "fete_morts")[0] == "possible"


def test_a_marriage_binds_two_peoples():
    st, buyer, bsite, seller, ssite = _two(stock=4000.0)
    st.tribes[1].knowledge.add("mariages")
    diplo.add_mod(st, 1, 3, "cadeau", 30.0, actor=1)
    before = diplo.relation(st, 1, 3)
    assert decisions.targets_of(st, 1, "mariage") == [3]
    out = commands.apply(st, commands.make(1, "decide", "mariage", 3))
    assert out["msg"] == "Le mariage est fait."
    assert diplo.relation(st, 1, 3) > before


def test_the_ai_takes_its_decisions_too():
    st, buyer, bsite, seller, ssite = _two(stock=4000.0)
    ai = st.tribes[3]
    ai.knowledge.add("conte")
    ai.practice["hivers"] = 12
    tech.invalidate()
    decisions.ai_monthly(st)
    assert "recits" in ai.decided
    assert "dec:recits" in decisions.effect_ids(ai)
    assert tech.bonuses(ai).learn > 1.0
    # Le joueur, lui, decide seul.
    st.tribes[1].knowledge.add("conte")
    st.tribes[1].practice["hivers"] = 12
    decisions.ai_monthly(st)
    assert "recits" not in st.tribes[1].decided


def test_two_events_became_decisions():
    by_id = events_data.EVENTS
    assert by_id["rassemblement"].weight == 0 and by_id["ancien"].weight == 0
    assert {"rassemblement", "ancien"} <= decisions.REPLACED


def test_decisions_are_saved():
    st, buyer, bsite, seller, ssite = _two(stock=100.0)
    decisions.take(st, 1, "rationner")
    st.bands[1].raid_route = "2:3:sel"
    back, _view = persist.loads_game(persist.dumps_game(st), st.world)
    t = back.tribes[1]
    assert t.decided == st.tribes[1].decided and t.ration_until == st.tribes[1].ration_until
    assert t.decision_effects == st.tribes[1].decision_effects
    assert back.bands[1].raid_route == "2:3:sel"


def test_the_decisions_screen_with_keys_and_clicks(monkeypatch, tmp_path):
    from test_app_clicks import _center, _click, _key, _money_state, _play

    st = _money_state()
    band = next(b for b in st.bands.values() if b.village)
    band.stock = 60.0

    def need(cond, what):
        assert cond, what

    steps = [
        lambda r: [],
        lambda r: need("decisions" in r.side_hits["tabs"], "l'onglet Decisions avec le village") or _key(pygame.K_d),
        lambda r: need(r.decisions_hits, "D ouvre les decisions") or _click(_center(r.decisions_hits["buttons"]["dfilt:possible"])),
        lambda r: need("dpick:rationner" in r.decisions_hits["buttons"], "rationner est possible") or _click(_center(r.decisions_hits["buttons"]["dpick:rationner"])),
        lambda r: _click(_center(r.decisions_hits["buttons"]["ddecide:rationner"])),
        lambda r: need(decisions.rationing(st, 1), "Décider : le rationnement") or _key(pygame.K_d),
        lambda r: need(not r.decisions_hits, "D ferme") or _click(_center(r.side_hits["tabs"]["decisions"])),
        lambda r: need(r.decisions_hits, "l'onglet ouvre") or _click(_center(r.decisions_hits["close"])),
        lambda r: need(not r.decisions_hits, "Fermer") or [],
    ]
    _play(monkeypatch, tmp_path, st, steps)
