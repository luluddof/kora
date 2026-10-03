"""La population (enfants, hommes, femmes, anciens, blesses), les batailles
qui durent des jours, la conquete d'un village et ses tributaires, la
chefferie (grenier du chef, familles, revoltes)."""

import copy

from src.kora import battle, chiefdom, chiefs, diplo, events, persist, population, sites, situations, tech, villages
from src.kora.clock import Clock
from src.kora.sim import fight_out, tick, update_population
from src.kora.battle import helpers_of, resolve_raids
from src.kora.gamestate import PLAYER_TRIBE_ID, GameState
from src.kora.types import Band, Order, OrderKind, Terrain, Tribe
from src.kora.world import make_filled_world, offset_to_axial


def _state(terrain=Terrain.PLAINE, player=True):
    world = make_filled_world(40, 24, terrain, wrap_x=True)
    st = GameState(
        world=world,
        clock=Clock(),
        tribes={
            1: Tribe(1, "Kora", 30, player, knowledge=set(tech.START_KNOWLEDGE) | {"huttes", "semis", "palissade"}, culture="joueur"),
            2: Tribe(2, "Steppe", 30, False, knowledge=set(tech.START_KNOWLEDGE) | {"huttes", "semis"}),
        },
        bands={},
        next_band_id=50,
    )
    st.clock.week = 20
    world.fill_season(st.clock.season())
    st.story = True
    return st


def _band(st, bid, tid, pop, col=20, row=12, kind="", stock=600.0):
    b = Band(bid, tid, offset_to_axial(col, row), pop, stock, kind=kind)
    st.bands[bid] = b
    return b


def _attack(att, prey):
    att.order = Order(OrderKind.MARCH_TO_BAND, target_band_id=prey.id)


def _village(st, tid, bid, pop=120, col=20, row=12):
    b = _band(st, bid, tid, pop, col, row, stock=4000.0)
    chiefs.ensure(st)
    sites.make_camp(st, bid)
    return b, villages.found(st, bid)


# --- la population ------------------------------------------------------------------


def test_a_band_has_children_men_women_elders_and_only_men_go_to_war():
    st = _state()
    b = _band(st, 1, 1, 100)
    c = population.counts(b)
    assert sum(c[k] for k in population.CLASSES) == 100
    assert c["enfants"] > c["anciens"] > 0 and c["hommes"] > 0 and c["femmes"] > 0
    assert population.levable(b) < population.fit_men(b) < 30
    population.wound(b, 5)
    assert population.fit_men(b) == c["hommes"] - 5
    assert abs(population.men_force(b) - (100 * population.STRUCTURE["hommes"] - 5)) < 1e-9


def test_births_are_children_and_famine_takes_the_weak_first():
    st = _state()
    b = _band(st, 1, 1, 100)
    population.grow(b, 20, "enfants")
    assert population.counts(b)["enfants"] == 32 + 20
    before = population.counts(b)
    population.kill(b, 20, population.FAMINE_WEIGHTS)
    after = population.counts(b)
    lost = {k: before[k] - after[k] for k in population.CLASSES}
    assert lost["anciens"] / before["anciens"] > lost["hommes"] / before["hommes"]
    # Le temps refait la structure ordinaire.
    for _ in range(200):
        population.monthly(st)
    assert not b.demo or abs(b.demo["enfants"] - population.STRUCTURE["enfants"]) < 0.01


def test_a_levy_takes_men_only_and_they_come_back_as_men():
    st = _state()
    vb, site = _village(st, 1, 1, pop=120)
    kids = population.counts(vb)["enfants"]
    army = villages.raise_army(st, 1, villages.LEVY_SHARE["masse"])
    assert army is not None and army.population == int(population.fit_men(Band(9, 1, vb.position, 120, 0.0)) * population.LEVY_MAX)
    assert population.counts(vb)["enfants"] == kids
    assert population.counts(vb)["hommes"] < population.counts(Band(9, 1, vb.position, 120, 0.0))["hommes"]
    army.position = site.hex
    villages.disband(st, army.id)
    assert vb.population == 120 and population.counts(vb)["hommes"] == population.counts(Band(9, 1, vb.position, 120, 0.0))["hommes"]


def test_population_and_wounded_are_saved():
    st = _state()
    b = _band(st, 1, 1, 100)
    population.grow(b, 10, "enfants")
    b.wounded = 4
    loaded, _v = persist.loads_game(persist.dumps_game(st), st.world)
    lb = loaded.bands[1]
    assert lb.demo == b.demo and lb.wounded == 4


# --- les batailles qui durent -------------------------------------------------------


def test_a_battle_lasts_days_killing_wounding_and_breaking_morale():
    st = _state(player=False)
    a = _band(st, 1, 1, 120)
    d = _band(st, 2, 2, 110)
    _attack(a, d)
    resolve_raids(st)
    bt = st.battles[0]
    assert bt.day == 0 and battle.in_battle(st, a) and battle.in_battle(st, d)
    first = bt.morale_d
    while not battle.day(st, bt):
        pass
    assert bt.day >= 2, "une bataille de forces proches dure des jours"
    assert sum(bt.killed.values()) > 0 and sum(bt.hurt.values()) > 0
    assert min(bt.morale_a, bt.morale_d) < first
    for d_ in bt.days:
        assert 0.8 <= d_["fa"] <= 1.2 and 0.8 <= d_["fd"] <= 1.2
    rep = bt.result.report
    assert rep["days"] == bt.day and len(rep["attacker"]["morale"]) == bt.day + 1


def test_bad_luck_never_turns_a_won_battle_it_only_costs_more():
    class Luck:
        def __init__(self, *_a):
            self.n = 0

        def random(self):
            # Le fort tire 0 (fortune 0,8), le faible 1 (fortune 1,2).
            self.n += 1
            return 0.0 if self.n % 2 == 1 else 1.0

    def run(unlucky):
        st = _state(player=False)
        a = _band(st, 1, 1, 160)
        d = _band(st, 2, 2, 90)
        _attack(a, d)
        real = battle.random.Random
        if unlucky:
            battle.random.Random = Luck
        try:
            fight_out(st)
        finally:
            battle.random.Random = real
        rep = st.fights[0].report if st.fights else st.battles
        return rep

    lucky, unlucky = run(False), run(True)
    assert lucky["winner"] == unlucky["winner"] == "attacker"
    assert unlucky["attacker"]["killed"] + unlucky["attacker"]["wounded"] >= lucky["attacker"]["killed"] + lucky["attacker"]["wounded"]


def test_a_skilled_general_and_the_hill_weigh_in():
    st = _state(player=False)
    a = _band(st, 1, 1, 100)
    chiefs.ensure(st)
    a.leader.traits = ("guerrier",)
    a.leader.renown = 80
    name, skill = battle.general(st, [a])
    assert name == a.leader.name and skill == 1 + 2 + 2
    plain = battle.cover_parts(st, a, a.position)
    hills = _state(Terrain.COLLINE, player=False)
    h = _band(hills, 1, 1, 100)
    assert battle.cover_parts(hills, h, h.position) and not plain


def test_a_battle_of_a_player_slows_time_to_days():
    st = _state(player=True)
    a = _band(st, 1, 1, 120)
    d = _band(st, 2, 2, 110)
    _attack(d, a)
    tick(st)
    assert st.battles and battle.slow(st)
    week = st.tick_count
    step = st.step
    tick(st)
    assert st.tick_count == week and st.day == 1 and st.step == step + 1, "le temps passe en jours"
    for _ in range(12):
        if not st.battles:
            break
        tick(st)
    assert not st.battles and st.fights
    assert any("le temps passe en jours" in e.text for e in st.log.entries)


def test_the_player_can_order_a_retreat_in_good_order():
    st = _state(player=True)
    a = _band(st, 1, 1, 100)
    d = _band(st, 2, 2, 100)
    _attack(d, a)
    from src.kora.vision import recompute_vision

    recompute_vision(st)
    resolve_raids(st)
    bt = st.battles[0]
    from src.kora import commands

    res = commands.apply(st, commands.make(1, "battle_retreat", 1))
    assert "Repli" in res["msg"]
    battle.day(st, bt)
    assert bt.outcome == "retraite" and bt.result.loser.tribe_id == 1
    assert a.retreating


def test_a_band_in_battle_cannot_walk_away():
    st = _state(player=True)
    a = _band(st, 1, 1, 100)
    d = _band(st, 2, 2, 100)
    _attack(d, a)
    resolve_raids(st)
    from src.kora import commands, orders

    assert "bataille" in commands.apply(st, commands.make(1, "goto", 1, a.position.q + 3, a.position.r))["msg"]
    assert "bataille" in orders.band_actions(st, 1)["split"]


def test_a_battle_in_progress_is_saved_and_goes_on_the_same():
    st = _state(player=True)
    a = _band(st, 1, 1, 120)
    d = _band(st, 2, 2, 150)
    chiefs.ensure(st)
    from src.kora.vision import recompute_vision

    recompute_vision(st)
    _attack(d, a)
    resolve_raids(st)
    battle.day(st, st.battles[0])
    assert st.battles, "la bataille dure"
    loaded, _v = persist.loads_game(persist.dumps_game(st), st.world)
    assert len(loaded.battles) == 1 and loaded.battles[0].day == 1
    one, two = copy.deepcopy(st), loaded
    for s in (one, two):
        battle.advance(s, 9, humans=True)
    assert one.fights[0].report == two.fights[0].report


# --- la conquete --------------------------------------------------------------------


def _siege(player_attacks=True):
    st = _state(Terrain.VALLEE, player=True)
    if player_attacks:
        vb, site = _village(st, 2, 2, pop=90, col=24)
        army = _band(st, 1, 1, 60, col=24, kind="armee")
        army.units = [["guerriers", 60, 0]]
        _attack(army, vb)
    else:
        vb, site = _village(st, 1, 1, pop=90, col=24)
        army = _band(st, 5, 2, 60, col=24, kind="armee")
        _attack(army, vb)
    chiefs.ensure(st)
    return st, vb, site, army


def test_a_taken_village_keeps_its_families_and_the_player_chooses():
    st, vb, site, army = _siege(player_attacks=True)
    kids = population.counts(vb)["enfants"]
    fight_out(st)
    rep = st.fights[0].report
    assert rep["outcome"] == "pris"
    assert population.counts(vb)["enfants"] == kids, "on ne tue pas les familles"
    card = next(p for p in events.pending(st, 1) if p.event_id == "conquete")
    assert card.other == 2 and card.site_id == site.id
    events.choose(st, card.uid, 0)
    assert chiefdom.overlord_of(st, 2) == 1 and chiefdom.vassals_of(st, 1) == [2]
    assert diplo.at_peace(st, 1, 2)


def test_a_tributary_pays_each_month_and_follows_to_war():
    st, vb, site, army = _siege(player_attacks=True)
    chiefdom.make_vassal(st, 1, 2)
    vb.stock = 4000.0
    paid = chiefdom._pay_vassal(st, 2, 1)
    assert paid > 0 and vb.stock < 4000.0
    # Le tributaire est un renfort de son suzerain.
    vb.position = army.position
    assert vb in helpers_of(st, army) or any(h.id == vb.id for h in helpers_of(st, army))


def test_the_ai_conquers_or_pillages_without_killing_everyone():
    st, vb, site, army = _siege(player_attacks=False)
    pop = vb.population
    fight_out(st)
    rep = st.fights[0].report
    assert rep["outcome"] == "pris" and vb.population > pop * 0.6


def test_a_weak_neighbour_can_be_taken_under_protection():
    st = _state(Terrain.VALLEE, player=True)
    _village(st, 1, 1, pop=300, col=10)
    _village(st, 2, 2, pop=40, col=16)
    diplo.make_contact(st, 1, 2)
    diplo.add_mod(st, 1, 2, "cadeau", 40, actor=1)
    st.tribes[1].prestige = 70
    v = diplo.evaluate(st, 1, 2, "proteger")
    assert not v.blocked and v.accepted, v.reasons
    diplo.perform(st, 1, 2, "proteger")
    assert chiefdom.overlord_of(st, 2) == 1


# --- la chefferie -------------------------------------------------------------------


def test_the_chief_takes_his_share_of_the_harvest():
    st = _state(Terrain.VALLEE)
    vb, site = _village(st, 1, 1, pop=120)
    st.tribes[1].levy_rate = 20
    left = chiefdom.take_from_harvest(st, vb, 1000.0)
    assert left == 800.0 and st.tribes[1].granary == 200.0
    parts = dict(chiefdom.stability_parts(st, 1))
    assert parts["Le prélèvement du chef"] < 0
    assert chiefdom.army_morale(st, 1) > 0


def test_families_appear_take_charges_and_a_war_chief_helps_the_general():
    st = _state(Terrain.VALLEE)
    vb, site = _village(st, 1, 1, pop=120)
    st.tick_count = 4
    chiefdom.monthly(st)
    fams = st.tribes[1].families
    assert len(fams) == 2 and all(f["trait"] in chiefdom.TRAITS for f in fams)
    before = battle.general(st, [vb])[1]
    msg = chiefdom.set_charge(st, 1, fams[0]["id"], "guerre")
    assert "chef de guerre" in msg
    assert battle.general(st, [vb])[1] > before
    # Une famille sans charge et un prelevement lourd : elle gronde.
    st.tribes[1].levy_rate = 30
    f1 = fams[1]["favour"]
    chiefdom.monthly(st)
    assert st.tribes[1].families[1]["favour"] < f1


def test_a_feast_costs_the_granary_and_calms_the_villages():
    st = _state(Terrain.VALLEE)
    vb, site = _village(st, 1, 1, pop=120)
    st.tribes[1].granary = 5000.0
    st.tick_count = 60
    assert chiefdom.feast(st, 1) == "La fête est donnée."
    assert dict(chiefdom.stability_parts(st, 1)).get("La grande fête") == chiefdom.FEAST_STABILITY
    assert "il y a peu" in chiefdom.feast_block(st, 1)


def test_too_heavy_a_levy_warns_then_revolts_and_a_failed_revolt_overthrows_the_chief():
    st = _state(Terrain.VALLEE)
    chief_v, s1 = _village(st, 1, 1, pop=120, col=10)
    tribe = st.tribes[1]
    tribe.levy_rate = 30
    tribe.granary = 400.0
    tribe.families = [{"id": 1, "name": "Arvo", "trait": "rites", "charge": "", "favour": 10.0, "village": s1.id}]
    old_chief = chief_v.leader.name
    assert SPECS_REVOLT().risk(st, 1)
    cands = SPECS_REVOLT().candidates(st)
    assert any(1 in c[2] for c in cands)
    inst = situations._start(st, situations.SPECS["revolte"], None, 0, [1], {})
    situations.act(st, inst.uid, 1, "baisser")
    assert tribe.levy_rate == 10
    tribe.levy_rate = 30
    inst.until = st.tick_count
    inst.progress = 0.0
    situations.SPECS["revolte"].month = lambda *_a: None
    try:
        situations.monthly(st)
    finally:
        del situations.SPECS["revolte"].month
    assert inst.outcome == "ratee"
    assert chief_v.leader.name != old_chief, "le chef est renverse"
    assert tribe.levy_rate == 0 and tribe.granary < 400.0
    assert s1.tribe_id == 1, "le village reste au peuple"


def SPECS_REVOLT():
    return situations.SPECS["revolte"]
