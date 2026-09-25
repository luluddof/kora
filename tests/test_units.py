"""Unites : types par role et par age, piles, detacher, dissoudre, reequiper."""

from src.kora import battle, chiefs, orders, sites, tech, units, villages
from src.kora.clock import Clock
from src.kora.persist import load_game, save_game
from src.kora.sim import GameState, apply_movement, band_force, merge_bands, new_game, resolve_raids
from src.kora.types import Band, Order, OrderKind, Terrain, Tribe
from src.kora.world import make_filled_world, offset_to_axial


def _village(pop=150, stock=5000.0, known=("huttes", "semis")):
    world = make_filled_world(60, 30, Terrain.VALLEE, wrap_x=True)
    tribe = Tribe(1, "Kora", 30, True, knowledge=set(tech.START_KNOWLEDGE) | set(known), culture="joueur")
    st = GameState(world=world, clock=Clock(), tribes={1: tribe}, bands={1: Band(1, 1, offset_to_axial(30, 15), pop, stock)}, next_band_id=2)
    world.fill_season(st.clock.season())
    chiefs.ensure(st)
    sites.make_camp(st, 1)
    site = villages.found(st, 1)
    return st, st.bands[1], site


def test_each_role_has_its_best_type_by_age():
    tribe = Tribe(1, "Kora", 30, True, knowledge=set())
    assert units.best(tribe, "melee").id == "guerriers"
    assert units.best(tribe, "garde") is None
    tribe.knowledge.update(("epieu", "arc"))
    assert units.best(tribe, "melee").id == "epieux"
    assert units.best(tribe, "tir").id == "archers"
    tribe.knowledge.update(("haches", "palissade"))
    assert units.best(tribe, "melee").id == "haches"
    assert units.best(tribe, "garde").id == "boucliers"
    assert units.outdated(tribe, "epieux") and not units.outdated(tribe, "haches")
    for u in units.UNITS.values():
        assert u.role in units.ROLES and (not u.needs or u.needs in tech.TECHS)


def test_a_second_company_joins_the_troop_at_the_village():
    st, village, site = _village(known=("huttes", "semis", "arc"))
    first = villages.raise_army(st, 1, villages.LEVY_SHARE["poignee"], "guerriers")
    second = villages.raise_army(st, 1, villages.LEVY_SHARE["poignee"], "archers")
    assert second is first
    assert [u[0] for u in first.units] == ["guerriers", "archers"]
    assert first.population == sum(u[1] for u in first.units)
    assert "archers" in " ".join(units.lines(st, first))


def test_troops_merge_into_one_stack_and_detach_again():
    st, village, site = _village(known=("huttes", "semis", "arc"))
    a = villages.raise_army(st, 1, villages.LEVY_SHARE["poignee"], "guerriers")
    a.position = offset_to_axial(36, 15)
    b = villages.raise_army(st, 1, villages.LEVY_SHARE["poignee"], "archers")
    b.position = a.position
    assert b is not a
    total = a.population + b.population
    merge_bands(st, a.id)
    assert b.id not in st.bands and a.population == total and len(a.units) == 2
    assert orders.labels(st, a.id)["split"] == "Detacher [S]"
    sel, msg = orders.perform(st, a.id, "split")
    part = st.bands[sel]
    assert msg == "" and part is not a and part.units[0][0] == "archers"
    assert a.population + part.population == total


def test_a_dissolved_troop_walks_home_and_rejoins_the_village():
    st, village, site = _village()
    army = villages.raise_army(st, 1)
    army.position = offset_to_axial(40, 15)
    left = village.population
    assert orders.labels(st, army.id)["army"] == "Dissoudre [L]"
    orders.perform(st, army.id, "army")
    assert army.homebound and army.path
    assert orders.band_actions(st, army.id)["merge"] == orders.HOMEBOUND
    for _ in range(6):
        apply_movement(st)
        villages.update(st)
        if army.id not in st.bands:
            break
    assert army.id not in st.bands
    assert village.population == left + 50


def test_companies_from_two_villages_go_back_each_to_its_own():
    st, village, site = _village()
    other = Band(9, 1, offset_to_axial(40, 15), 150, 5000.0)
    st.bands[9] = other
    chiefs.ensure(st)
    st.tribes[1].knowledge.add("maisons")
    sites.make_camp(st, 9)
    site2 = villages.found(st, 9)
    a = villages.raise_army(st, 1, villages.LEVY_SHARE["poignee"])
    b = villages.raise_army(st, 9, villages.LEVY_SHARE["poignee"])
    b.position = a.position = offset_to_axial(35, 15)
    merge_bands(st, a.id)
    assert {u[2] for u in a.units} == {site.id, site2.id}
    villages.dissolve(st, a.id)
    walkers = [x for x in st.bands.values() if x.kind == "armee" and x.homebound]
    assert {x.home for x in walkers} == {site.id, site2.id}


def test_archers_shoot_first_and_shields_hold():
    st, village, site = _village(known=("huttes", "semis", "arc", "palissade"))
    # Loin les unes des autres : pas de renforts entre elles.
    archers = Band(20, 1, offset_to_axial(5, 5), 30, 100.0, kind="armee", units=[["archers", 30, site.id]])
    shields = Band(21, 1, offset_to_axial(15, 25), 30, 100.0, kind="armee", units=[["boucliers", 30, site.id]])
    plain = Band(22, 1, offset_to_axial(50, 5), 30, 100.0, kind="armee", units=[["guerriers", 30, site.id]])
    for b in (archers, shields, plain):
        st.bands[b.id] = b
    sa = battle._side(st, archers, True, archers.position)
    assert sa.power(units.VOLLEY) > sa.power(0.0)
    ss = battle._side(st, shields, False, shields.position)
    sp = battle._side(st, plain, False, plain.position)
    assert ss.toughness() > sp.toughness()
    assert band_force(st, shields) != band_force(st, plain)


def test_losses_fall_first_on_the_exposed():
    band = Band(1, 1, offset_to_axial(1, 1), 60, 0.0, kind="armee", units=[["guerriers", 30, 1], ["archers", 30, 1]])
    units.remove(band, 20)
    men = {u[0]: u[1] for u in band.units}
    assert band.population == 40 and men["guerriers"] < men["archers"]


def test_reequip_at_the_village_for_the_new_age():
    st, village, site = _village(known=("huttes", "semis", "epieu"))
    army = villages.raise_army(st, 1)
    assert army.units[0][0] == "epieux"
    assert "Rien" in villages.reequip_block(st, army.id)
    st.tribes[1].knowledge.add("haches")
    stock = village.stock
    assert villages.reequip(st, army.id)
    assert army.units[0][0] == "haches" and village.stock < stock


def test_the_battle_report_lists_companies():
    st, village, site = _village(known=("huttes", "semis", "arc"))
    army = villages.raise_army(st, 1, villages.LEVY_SHARE["poignee"], "guerriers")
    villages.raise_army(st, 1, villages.LEVY_SHARE["poignee"], "archers")
    army.position = offset_to_axial(45, 15)
    st.tribes[2] = Tribe(2, "Steppe", 20, False, knowledge=set(tech.START_KNOWLEDGE))
    st.bands[50] = Band(50, 2, army.position, 12, 50.0)
    chiefs.ensure(st)
    army.order = Order(OrderKind.MARCH_TO_BAND, target_band_id=50)
    resolve_raids(st)
    rep = st.fights[0].report
    assert [u[0] for u in rep["attacker"]["units"]] == ["Guerriers", "Archers"]


def test_companies_are_saved(tmp_path):
    world = make_filled_world(40, 20, Terrain.VALLEE, wrap_x=True)
    st = new_game(world)
    st.tribes[1].knowledge.update(("huttes", "semis", "arc"))
    st.bands[1].population = 150
    st.bands[1].stock = 5000.0
    sites.make_camp(st, 1)
    villages.found(st, 1)
    army = villages.raise_army(st, 1, villages.LEVY_SHARE["poignee"], "archers")
    army.homebound = True
    path = tmp_path / "kora.json"
    save_game(st, path, {})
    loaded, _ = load_game(path, world)
    back = loaded.bands[army.id]
    assert back.units == army.units and back.homebound
