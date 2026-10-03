"""Un village par peuple (les autres lui sont tributaires, ou freres), les
villages freres, les chaines de tributaires, qui fait quoi dans un village,
la fuite des demoralises, le repli de l'IA, les loups des troupes en marche."""

from src.kora import battle, chiefdom, chiefs, diplo, events, goods, population, sites, tech, villages
from src.kora.sim import fight_out
from src.kora.battle import helpers_of, resolve_raids
from src.kora.types import Band, Order, OrderKind, Terrain
from test_war_chiefdom import _attack, _band, _state, _village


def _all_knowledge(st, tid):
    for t in tech.TECHS:
        tech.grant(st.tribes[tid], t)
    tech.invalidate()


# --- les loups des troupes en marche ------------------------------------------------


def test_a_marching_troop_can_bring_back_wolf_cubs_for_hunting_dogs():
    st = _state(Terrain.FORET)
    _village(st, 1, 1, pop=120)
    army = _band(st, 5, 1, 20, col=30, kind="armee")
    army.units = [["guerriers", 20, 0]]
    army.path = [army.position]
    st.clock.week = 40
    from src.kora.types import Season

    st.world.fill_season(Season.HIVER)
    chiefs.ensure(st)
    inst = events._new_instance(st, events.EVENTS["loups_troupe"], 1, army.id, {})
    assert events._eligible(st, events.EVENTS["loups_troupe"], inst)
    assert "la troupe de" in events.text_for(st, inst)
    st.tribes[1].knowledge |= {"epieu"}
    assert tech.status(st, 1, "chiens") != "disponible"
    cubs = events._new_instance(st, events.EVENTS["louveteaux_troupe"], 1, army.id, {})
    events.apply(st, cubs, ("flag", "louveteaux"))
    assert tech.status(st, 1, "chiens") == "disponible", "un peuple fixé peut avoir ses chiens"


# --- un village par peuple ------------------------------------------------------------


def test_an_old_game_with_two_villages_splits_into_a_lord_and_a_tributary():
    st = _state(Terrain.VALLEE)
    _all_knowledge(st, 1)
    first, s1 = _village(st, 1, 1, pop=120, col=10)
    # Une vieille partie : un second village du meme peuple (avant la regle).
    second = _band(st, 3, 1, 100, col=30, stock=3000.0)
    chiefs.ensure(st)
    sites.make_camp(st, 3)
    real = villages.found_block
    villages.found_block = lambda *a, **k: ""
    try:
        s2 = villages.found(st, 3)
    finally:
        villages.found_block = real
    assert s2 is not None and len(sites.of_tribe(st, 1, "village")) == 2
    chiefdom.split_extra_villages(st)
    assert len(sites.of_tribe(st, 1, "village")) == 1 and s2.tribe_id != 1
    assert chiefdom.overlord_of(st, s2.tribe_id) == 1, "le village frere devient tributaire"
    assert diplo.relation(st, 1, s2.tribe_id) > 0


def test_brother_villages_count_the_civilisation_and_tributaries():
    st = _state(Terrain.VALLEE)
    _all_knowledge(st, 1)
    _village(st, 1, 1, pop=120, col=5)
    st.tribes[1].knowledge.discard("freres")
    tech.invalidate()
    assert tech.status(st, 1, "freres") == "attente"
    for k, col in enumerate((18, 31)):
        b = _band(st, 10 + k, 1, 60, col=col)
        new = chiefs.secede(st, b.id, independence=True)
        st.tribes[new].knowledge |= set(st.tribes[1].knowledge)
        sites.make_camp(st, b.id)
        assert villages.found(st, b.id) is not None
    assert chiefdom.kin_villages(st, 1) == 2
    assert tech.status(st, 1, "freres") == "disponible"
    tech.grant(st.tribes[1], "freres")
    tech.invalidate()
    kin = chiefdom.kin_of(st, 1)
    assert len(kin) == 2
    other = sorted(kin)[0]
    reasons = dict(diplo.reasons(st, 1, other))
    assert reasons.get("Villages frères") == 15.0
    # Ils viennent en renfort.
    helper = next(b for b in st.bands.values() if b.tribe_id == other)
    me = next(b for b in st.bands.values() if b.tribe_id == 1)
    helper.position = me.position
    assert any(h.id == helper.id for h in helpers_of(st, me))


# --- les chaines de tributaires -------------------------------------------------------


def test_a_conquered_lord_keeps_its_tributaries_and_changes_master():
    st = _state(Terrain.VALLEE)
    st.tribes[3] = type(st.tribes[2])(3, "Akor", 30, False, knowledge=set(st.tribes[2].knowledge))
    _village(st, 2, 2, pop=90, col=5)
    _village(st, 3, 3, pop=60, col=20)
    chiefdom.make_vassal(st, 2, 3)
    chiefdom.conquer(st, 1, 2, 0, "soumettre")
    assert chiefdom.overlord_of(st, 2) == 1 and chiefdom.overlord_of(st, 3) == 2
    # Le tributaire de 2 conquiert son suzerain... qui etait au-dessus de lui.
    chiefdom.make_vassal(st, 3, 1)
    assert chiefdom.overlord_of(st, 1) == 3
    assert chiefdom.overlord_of(st, 3) == 0, "pas de cercle : il s'est libéré"


def test_the_ai_subjugates_a_village_that_has_tributaries():
    st = _state(Terrain.VALLEE)
    _village(st, 2, 2, pop=90, col=5)
    st.tribes[3] = type(st.tribes[2])(3, "Akor", 30, False, knowledge=set(st.tribes[2].knowledge))
    _village(st, 3, 3, pop=60, col=18)
    chiefdom.make_vassal(st, 2, 3)
    st.tribes[4] = type(st.tribes[2])(4, "Ral", 30, False, knowledge=set(st.tribes[2].knowledge))
    _village(st, 4, 4, pop=200, col=31)
    assert chiefdom.ai_choice(st, 4, 2) == "soumettre"


# --- qui fait quoi --------------------------------------------------------------------


def test_village_people_work_by_trade_and_sex_and_soldiers_return_to_work():
    st = _state(Terrain.VALLEE)
    _all_knowledge(st, 1)
    vb, site = _village(st, 1, 1, pop=120)
    site.data.teams = {"potiers": 1, "tailleurs": 1}
    o = population.occupations(st, vb)
    assert o["metiers"]["potiers"] == goods.TEAM and o["metiers"]["tailleurs"] == goods.TEAM
    assert o["chasse"] == population.fit_men(vb) - goods.TEAM - (o["champs"] - (population.fit_women(vb) - goods.TEAM - o["cueillette"]))
    # Plus de femmes libres : pas de potieres de plus.
    vb.demo = {"hommes": 0.6, "enfants": 0.4}
    assert "femmes" in goods.add_block(st, site, "potiers") or goods.max_teams(st, site, "potiers") <= 1
    vb.demo = {}
    army = villages.raise_army(st, 1, villages.LEVY_SHARE["troupe"])
    assert population.occupations(st, vb)["soldats"] == army.population
    army.position = site.hex
    villages.disband(st, army.id)
    assert population.occupations(st, vb)["soldats"] == 0


# --- la fuite et le repli -------------------------------------------------------------


def test_demoralised_warriors_desert_home_and_clans_lose_heart():
    import random

    st = _state(player=False)
    vb, site = _village(st, 2, 2, pop=200, col=10)
    army = villages.raise_army(st, 2, villages.LEVY_SHARE["masse"])
    foe = _band(st, 9, 1, 400, col=30)
    army.position = foe.position
    _attack(foe, army)
    resolve_raids(st)
    bt = st.battles[0]
    side = battle._now(st, bt, False)
    home_pop = vb.population
    gone = battle._flee(st, bt, side, 10.0, random.Random(1))
    assert gone > 0 and vb.population == home_pop + gone, "les deserteurs rentrent au village"
    clan = battle._now(st, bt, True)
    fled = battle._flee(st, bt, clan, 10.0, random.Random(2))
    assert fled > 0 and bt.fled[foe.id] == fled
    assert battle._now(st, bt, True).now[foe.id] < clan.now[foe.id]


def test_a_losing_ai_raider_falls_back_but_a_clan_covering_its_families_holds():
    # Deux peuples de l'IA (le peuple 1 est toujours le joueur).
    st = _state(player=False)
    st.tribes[3] = type(st.tribes[2])(3, "Akor", 30, False, knowledge=set(st.tribes[2].knowledge))
    raider = _band(st, 1, 3, 100)
    prey = _band(st, 2, 2, 130)
    _attack(raider, prey)
    resolve_raids(st)
    bt = st.battles[0]
    while not battle.day(st, bt):
        pass
    assert bt.outcome == "retraite" and bt.result.loser is raider, "un pillard qui perd renonce"
    st2 = _state(player=False)
    st2.tribes[3] = type(st2.tribes[2])(3, "Akor", 30, False, knowledge=set(st2.tribes[2].knowledge))
    big = _band(st2, 1, 3, 240)
    clan = _band(st2, 2, 2, 120)
    _attack(big, clan)
    resolve_raids(st2)
    bt2 = st2.battles[0]
    battle.day(st2, bt2)
    assert bt2.day == 1 and (not bt2.outcome or bt2.morale_d < battle.ROUT + 7), "le clan tient tant qu'il peut"
