"""Batailles simulees : passes d'armes, moral, poursuite, aneantissement."""

import copy

from src.kora import battle, chiefs, sites, tech, villages
from src.kora.clock import Clock
from src.kora.persist import load_game, save_game
from src.kora.sim import GameState, band_force, new_game, resolve_raids
from src.kora.types import Band, Order, OrderKind, Terrain, Tribe
from src.kora.world import make_filled_world, offset_to_axial


def _state(terrain=Terrain.PLAINE, prestige=20):
    world = make_filled_world(40, 24, terrain)
    st = GameState(
        world=world,
        clock=Clock(),
        tribes={
            1: Tribe(1, "Kora", prestige, True, knowledge=set(tech.START_KNOWLEDGE)),
            2: Tribe(2, "Steppe", prestige, False, knowledge=set(tech.START_KNOWLEDGE)),
        },
        bands={},
        next_band_id=50,
    )
    st.clock.week = 30
    return st


def _band(st, bid, tribe, pop, col=20, row=12, kind="", stock=200.0):
    b = Band(bid, tribe, offset_to_axial(col, row), pop, stock, kind=kind)
    st.bands[bid] = b
    return b


def _attack(att, prey):
    att.order = Order(OrderKind.MARCH_TO_BAND, target_band_id=prey.id)


def test_a_troop_fights_whole_a_clan_with_its_adults_only():
    st = _state()
    troop = _band(st, 1, 1, 30, kind="armee")
    clan = _band(st, 2, 2, 30)
    assert band_force(st, troop) > 2 * band_force(st, clan)


def test_the_same_battle_gives_the_same_result():
    st = _state()
    a = _band(st, 1, 1, 40)
    d = _band(st, 2, 2, 34)
    _attack(a, d)
    h = a.position
    one = battle.simulate(copy.deepcopy(st), a, d, h)[2]
    two = battle.simulate(copy.deepcopy(st), a, d, h)[2]
    assert one == two


def test_morale_falls_round_after_round_until_a_side_routs():
    st = _state()
    a = _band(st, 1, 1, 60)
    d = _band(st, 2, 2, 40)
    _attack(a, d)
    resolve_raids(st)
    rep = st.fights[0].report
    md = rep["defender"]["morale"]
    assert md[0] > md[-1]
    assert rep["winner"] == "attacker"
    assert rep["outcome"] in ("deroute", "retraite", "aneanti")
    assert len(md) == rep["rounds"] + 1
    assert rep["headline"]


def test_a_crushed_troop_in_the_open_is_annihilated():
    st = _state()
    big = _band(st, 1, 1, 60, kind="armee")
    small = _band(st, 2, 2, 12, kind="armee")
    chiefs.ensure(st)
    _attack(big, small)
    before = st.tribes[1].prestige
    resolve_raids(st)
    assert 2 not in st.bands
    rep = st.fights[0].report
    assert rep["wiped"] and rep["outcome"] == "aneanti"
    assert st.tribes[1].prestige == before + 10
    assert "aneanti" in rep["headline"]
    assert any("aneantis" in e.text for e in st.log.entries)


def test_woods_and_hills_help_the_beaten_to_escape():
    st = _state()
    a = _band(st, 1, 1, 60, kind="armee")
    d = _band(st, 2, 2, 20)
    sa = battle._side(st, a, True, a.position)
    sd = battle._side(st, d, False, d.position)
    plain = battle.pursuit_rate(st, sa, sd, a.position, "deroute", False)
    trapped = battle.pursuit_rate(st, sa, sd, a.position, "deroute", True)
    st.world = make_filled_world(40, 24, Terrain.FORET)
    wood = battle.pursuit_rate(st, sa, sd, a.position, "deroute", False)
    assert wood < plain < trapped
    assert battle.pursuit_rate(st, sa, sd, a.position, "retraite", False) < wood


def test_the_defender_holds_the_hill():
    st = _state()
    a = _band(st, 1, 1, 30)
    d = _band(st, 2, 2, 30)
    assert battle._side(st, d, False, d.position).cover == 1.0
    st.world = make_filled_world(40, 24, Terrain.COLLINE)
    assert battle._side(st, d, False, d.position).cover == battle.COVER[Terrain.COLLINE]
    assert battle._side(st, a, True, a.position).cover == 1.0


def test_hunger_and_a_troop_change_morale():
    st = _state()
    clan = _band(st, 1, 1, 30)
    troop = _band(st, 3, 1, 30, kind="armee", col=5)
    base, _ = battle.start_morale(st, clan, True, clan.position)
    clan.famine_in_period = True
    hungry, parts = battle.start_morale(st, clan, True, clan.position)
    assert hungry == base + battle.HUNGER_MORALE
    assert any(label == "Affames" for label, _v in parts)
    fierce, _ = battle.start_morale(st, troop, True, troop.position)
    assert fierce == base + battle.ARMY_MORALE


def test_a_band_fights_only_one_battle_a_week():
    st = _state()
    st.tribes[3] = Tribe(3, "Foret", 20, False, knowledge=set(tech.START_KNOWLEDGE))
    strong = _band(st, 1, 1, 80)
    _band(st, 2, 2, 20)
    _band(st, 3, 3, 20)
    resolve_raids(st)
    assert len(st.fights) == 1
    assert strong.last_raid_tick == 0


def test_a_palisade_makes_the_village_hold():
    def siege(with_palisade):
        world = make_filled_world(40, 24, Terrain.VALLEE, wrap_x=True)
        st = GameState(
            world=world,
            clock=Clock(),
            tribes={
                1: Tribe(1, "Kora", 20, True, knowledge=set(tech.START_KNOWLEDGE) | {"huttes", "semis", "palissade"}),
                2: Tribe(2, "Pillards", 20, False, knowledge=set(tech.START_KNOWLEDGE)),
            },
            bands={1: Band(1, 1, offset_to_axial(20, 12), 60, 900.0)},
            next_band_id=10,
        )
        world.fill_season(st.clock.season())
        chiefs.ensure(st)
        sites.make_camp(st, 1)
        site = villages.found(st, 1)
        if with_palisade:
            site.data["buildings"].append("palissade")
        raider = Band(2, 2, site.hex, 44, 0.0, kind="armee")
        st.bands[2] = raider
        chiefs.ensure(st)
        _attack(raider, st.bands[1])
        resolve_raids(st)
        return st.fights[0].report if st.fights else None, st, site

    open_rep, _st, _site = siege(False)
    walled_rep, st, site = siege(True)
    assert open_rep["winner"] == "attacker"
    assert walled_rep["winner"] == "defender"
    assert any("Palissade" in text for text, _sign in walled_rep["defender"]["mods"])


def test_a_beaten_village_is_pillaged_and_stays():
    world = make_filled_world(40, 24, Terrain.VALLEE, wrap_x=True)
    st = GameState(
        world=world,
        clock=Clock(),
        tribes={
            1: Tribe(1, "Kora", 20, True, knowledge=set(tech.START_KNOWLEDGE) | {"huttes", "semis"}),
            2: Tribe(2, "Pillards", 20, False, knowledge=set(tech.START_KNOWLEDGE)),
        },
        bands={1: Band(1, 1, offset_to_axial(20, 12), 60, 900.0)},
        next_band_id=10,
    )
    world.fill_season(st.clock.season())
    chiefs.ensure(st)
    sites.make_camp(st, 1)
    site = villages.found(st, 1)
    st.bands[2] = Band(2, 2, site.hex, 200, 0.0, kind="armee")
    chiefs.ensure(st)
    _attack(st.bands[2], st.bands[1])
    resolve_raids(st)
    rep = st.fights[0].report
    assert rep["outcome"] in ("pille", "rase")
    if rep["outcome"] == "pille":
        village = st.bands[1]
        assert village.position == site.hex and not village.retreating
        assert site.data["burned"]


def test_odds_read_the_balance_of_forces():
    st = _state()
    a = _band(st, 1, 1, 60, kind="armee")
    weak = _band(st, 2, 2, 20, col=24)
    strong = _band(st, 3, 2, 200, col=30)
    assert battle.odds(st, a, weak)[1] in ("ecrasant", "favorable")
    assert battle.odds(st, a, strong)[1] == "defavorable"


def test_the_battle_report_is_saved(tmp_path):
    st = new_game(make_filled_world(40, 24, Terrain.PLAINE, wrap_x=True))
    me = st.bands[1]
    foe = Band(90, 2, me.position, 10, 50.0)
    st.bands[90] = foe
    chiefs.ensure(st)
    _attack(me, foe)
    resolve_raids(st)
    assert st.fights and st.fights[0].report
    path = tmp_path / "kora.json"
    save_game(st, path, {})
    loaded, _ = load_game(path, st.world)
    assert loaded.fights[0].report == st.fights[0].report
