"""L'ost (les troupes des tributaires rejoignent celle du suzerain) et le
siege (torches, investissement d'un village : siege.py)."""

from src.kora import ai_war, chiefdom, chiefs, commands, diplo, orders, ost, siege, sites, tech, villages
from src.kora.clock import Clock
from src.kora.gamestate import GameState
from src.kora.persist import load_game, save_game
from src.kora.sim import apply_movement, resolve_joins, tick
from src.kora.types import Band, Terrain, Tribe
from src.kora.world import make_filled_world, offset_to_axial

NEO = {"huttes", "semis", "sedentarite", "palissade", "arc", "palabres"}


def _state():
    world = make_filled_world(60, 30, Terrain.PLAINE, wrap_x=True)
    st = GameState(
        world=world,
        clock=Clock(),
        tribes={
            1: Tribe(1, "Kora", 30, True, knowledge=set(tech.START_KNOWLEDGE) | NEO, culture="joueur"),
            2: Tribe(2, "Vassaux", 30, False, knowledge=set(tech.START_KNOWLEDGE) | NEO),
            3: Tribe(3, "Ennemis", 30, False, knowledge=set(tech.START_KNOWLEDGE) | NEO),
        },
        bands={},
        next_band_id=50,
    )
    st.clock.week = 20
    world.fill_season(st.clock.season())
    return st


def _village(st, tid, bid, pop=200, col=20, row=15):
    b = Band(bid, tid, offset_to_axial(col, row), pop, 4000.0)
    st.bands[bid] = b
    chiefs.ensure(st)
    sites.make_camp(st, bid)
    return b, villages.found(st, bid)


def _realm():
    st = _state()
    lord, lsite = _village(st, 1, 1, col=10)
    vas, vsite = _village(st, 2, 2, col=22)
    for a, b in ((1, 2), (1, 3), (2, 3)):
        diplo.make_contact(st, a, b, quiet=True)
    chiefdom.make_vassal(st, 1, 2, "force")
    a1 = villages.raise_army(st, 1)
    a2 = villages.raise_army(st, 2)
    a1.position = offset_to_axial(14, 15)
    a2.position = offset_to_axial(26, 15)
    return st, a1, a2, lsite, vsite


def test_the_overlord_calls_the_ost_and_the_vassal_troop_joins_his_own():
    st, a1, a2, lsite, vsite = _realm()
    assert orders.labels(st, a1.id)["honor"] == "Ost [H]"
    assert orders.band_actions(st, a1.id)["honor"] == ""
    # Sans tributaire, pas d'ost.
    assert "tributaires" in ost.call_block(st, a2.id)
    total = a1.population + a2.population
    sel, msg = orders.perform(st, a1.id, "honor")
    assert msg == "" and a2.ost == a1.id and a2.path
    for _ in range(12):
        apply_movement(st)
        resolve_joins(st)
        ost.weekly(st)
        if a2.id not in st.bands:
            break
    assert a2.id not in st.bands, "la troupe du tributaire s'est fondue dans l'ost"
    assert a1.population == total and a1.tribe_id == 1
    homes = {u[2] for u in a1.units}
    assert homes == {lsite.id, vsite.id}, "chaque compagnie garde son village"
    assert any("L'ost" in line for line in ost.lines(st, a1))


def test_a_dissolved_ost_sends_each_company_home_to_its_own_people():
    st, a1, a2, lsite, vsite = _realm()
    a2.position = a1.position
    ost.join(st, a1, a2)
    vmen = sum(u[1] for u in a1.units if u[2] == vsite.id)
    before = st.bands[2].population
    villages.dissolve(st, a1.id)
    back = [b for b in st.bands.values() if b.kind == "armee" and b.tribe_id == 2]
    assert len(back) == 1 and back[0].population == vmen and back[0].homebound
    for _ in range(12):
        apply_movement(st)
        villages.update(st)
    assert st.bands[2].population == before + vmen


def test_a_freed_vassal_takes_its_companies_back():
    st, a1, a2, lsite, vsite = _realm()
    a2.position = a1.position
    ost.join(st, a1, a2)
    chiefdom._revolt(st, 2, 1)
    ost.weekly(st)
    assert all(u[2] == lsite.id for u in a1.units)
    assert any(b.kind == "armee" and b.tribe_id == 2 for b in st.bands.values())


def test_a_player_vassal_keeps_his_troop_with_a_march_order():
    st, a1, a2, lsite, vsite = _realm()
    st.tribes[2].is_player, st.tribes[1].is_player = True, False
    ost.call(st, a1.id)
    assert a2.ost == a1.id
    commands.apply(st, commands.make(2, "goto", a2.id, a2.position.q + 1, a2.position.r))
    assert a2.ost == 0


def test_the_ai_overlord_too_weak_alone_calls_the_ost():
    st, a1, a2, lsite, vsite = _realm()
    st.tribes[1].is_player = False
    prey = Band(3, 3, offset_to_axial(14, 22), 100, 300.0)
    st.bands[3] = prey
    chiefs.ensure(st)
    diplo.declare_war(st, 1, 3)
    assert not ai_war.wins(st, [a1], prey) and ai_war.wins(st, [a1, a2], prey)
    plan = ai_war.plan_raid(st, a1, 12, hungry=True)
    assert plan[0] == "ost" and plan[1] is a2
    ai_war.start_plan(st, a1, plan)
    assert a2.ost == a1.id and a1.intent_prey == prey.id
    # Le suzerain attend l'ost (il ne renonce pas), puis part a l'attaque.
    for _ in range(14):
        apply_movement(st)
        resolve_joins(st)
        ost.weekly(st)
        ai_war.advance_plans(st)
        if a1.order.target_band_id == prey.id:
            break
    assert a2.id not in st.bands and a1.order.target_band_id == prey.id


def test_torches_halve_the_walls_of_a_village_you_attack():
    st = _state()
    vb, vsite = _village(st, 3, 3)
    vsite.data.buildings.append("palissade")
    walls = villages.defense_mult(st, vb)
    assert abs(walls - villages.PALISADE_DEFENSE) < 1e-6
    st.tribes[1].knowledge.add("torches")
    tech.invalidate()
    burnt = 1.0
    for _label, m in villages.defense_parts(st, vb, 1):
        burnt *= m
    assert abs(burnt - (1 + (villages.PALISADE_DEFENSE - 1) * tech.SIEGE_FIRE)) < 1e-3
    # Sans torches chez l'attaquant : les murs tiennent.
    assert abs(villages.defense_mult(st, vb) - walls) < 1e-6
    assert any("palissades" in line for line in tech.effect_lines(tech.TECHS["torches"]))


def test_a_siege_starves_a_village_and_wears_its_defense_down():
    st = _state()
    vb, vsite = _village(st, 3, 3)
    st.tribes[1].knowledge.update(("torches", "siege"))
    tech.invalidate()
    diplo.make_contact(st, 1, 3, quiet=True)
    army = Band(60, 1, st.world.neighbors(vsite.hex)[0], 60, 400.0, kind="armee", units=[["guerriers", 60, 0]])
    st.bands[60] = army
    siege.weekly(st)
    assert vsite.data.siege == 0, "en paix : pas de siege"
    diplo.declare_war(st, 1, 3)
    food = villages.food_mult(st, vb)
    before = villages.defense_mult(st, vb)
    for _ in range(5):
        siege.weekly(st)
    assert vsite.data.siege == 5 and vsite.data.besieger == 1
    assert villages.food_mult(st, vb) < food * 0.5
    assert villages.defense_mult(st, vb) < before
    assert any("Assiégé" in line for line in siege.lines(st, vsite))
    # La troupe s'en va : le siege est leve.
    army.position = offset_to_axial(50, 5)
    siege.weekly(st)
    assert vsite.data.siege == 0


def test_the_siege_techs_follow_the_village_and_its_palisade():
    t = tech.TECHS["torches"]
    assert t.tier == 5 and set(t.prereqs) == {"palissade", "arc"}
    assert tech.TECHS["siege"].prereqs == ("torches",) and tech.TECHS["siege"].tier == 6


def test_the_ai_raises_a_troop_to_besiege_a_village_it_could_not_storm():
    from src.kora import ai

    st = _state()
    me, msite = _village(st, 1, 1, pop=320, col=10)
    prey, psite = _village(st, 3, 3, pop=100, col=18)
    psite.data.buildings.append("palissade")
    st.tribes[1].is_player = False
    diplo.make_contact(st, 1, 3, quiet=True)
    diplo.declare_war(st, 1, 3)
    assert not ai._could_take(st, me, prey, "masse")
    st.tribes[1].knowledge.update(("torches", "siege"))
    tech.invalidate()
    assert ai._could_take(st, me, prey, "masse")
    army = villages.raise_army(st, 1, villages.LEVY_SHARE["masse"])
    assert ai._besiege(st, army, 10.0) and army.path
    army.position, army.path = army.path[-1], []
    siege.weekly(st)
    assert psite.data.siege == 1


def test_ost_and_siege_are_saved(tmp_path):
    st, a1, a2, lsite, vsite = _realm()
    ost.call(st, a1.id)
    vsite.data.siege, vsite.data.besieger = 3, 3
    path = tmp_path / "kora.json"
    save_game(st, path, {})
    loaded, _ = load_game(path, st.world)
    assert loaded.bands[a2.id].ost == a1.id
    assert loaded.sites[vsite.id].data.siege == 3 and loaded.sites[vsite.id].data.besieger == 3


def test_a_besieged_ai_world_keeps_running():
    st, a1, a2, lsite, vsite = _realm()
    for _ in range(8):
        tick(st)
    assert st.last_error is None
