"""Caches et campements : debloques par les savoirs."""

from src.kora import orders, sites, tech
from src.kora.clock import Clock
from src.kora.persist import load_game, save_game
from src.kora.sim import GameState, collect_food, new_game, stock_max
from src.kora.types import Band, Season, Terrain, Tribe
from src.kora.world import make_filled_world, offset_to_axial


def _state(known=(), stock=400.0, pop=40):
    world = make_filled_world(40, 20, Terrain.PLAINE)
    pos = offset_to_axial(20, 10)
    band = Band(1, 1, pos, pop, stock)
    tribe = Tribe(1, "t", 20, True, knowledge=set(tech.START_KNOWLEDGE) | set(known))
    st = GameState(world=world, clock=Clock(), tribes={1: tribe}, bands={1: band})
    world.fill_season(st.clock.season())
    return st, band


def test_no_camp_nor_cache_without_the_knowledge():
    st, band = _state()
    assert "Huttes" in sites.camp_block(st, 1)
    assert "Fumage" in sites.deposit_block(st, 1)
    assert orders.band_actions(st, 1)["camp"]


def test_a_camp_is_made_counted_and_spaced():
    st, band = _state(known=("huttes",))
    assert sites.make_camp(st, 1) is not None
    assert "tout pres" in sites.camp_block(st, 1)
    band.position = offset_to_axial(30, 10)
    assert sites.make_camp(st, 1) is not None
    band.position = offset_to_axial(5, 10)
    assert "2/2" in sites.camp_block(st, 1)


def test_deposit_keeps_four_weeks_and_withdraw_takes_back():
    st, band = _state(known=("fumage",), stock=400.0)
    put = sites.deposit(st, 1)
    assert put > 0 and abs(band.stock - 4 * band.population) < 1e-6
    cache = sites.own_site_at(st, band)
    assert cache.kind == "cache" and cache.store == put
    got = sites.withdraw(st, 1)
    assert got > 0 and band.stock > 4 * band.population
    assert band.stock <= stock_max(band, st)


def test_food_rots_slower_with_salt_and_pots():
    plain, pb = _state(known=("fumage",))
    salted, sb = _state(known=("fumage", "salaison"))
    for st in (plain, salted):
        sites.deposit(st, 1)
        st.bands[1].position = offset_to_axial(2, 2)
    for _ in range(20):
        sites.update(plain)
        sites.update(salted)
    left_plain = sum(s.store for s in plain.sites.values())
    left_salted = sum(s.store for s in salted.sites.values())
    assert left_salted > left_plain


def test_a_foreign_band_can_loot_an_unguarded_cache():
    st, band = _state(known=("fumage",))
    sites.deposit(st, 1)
    band.position = offset_to_axial(2, 2)
    st.tribes[2] = Tribe(2, "raider", 20, False)
    cache = next(iter(st.sites.values()))
    st.bands[2] = Band(2, 2, cache.hex, 30, 0.0)
    for _ in range(30):
        sites.update(st)
    assert st.bands[2].stock > 0
    assert any("pillee" in e.text for e in st.log.entries)


def test_huts_cut_winter_famine_at_camp():
    bare, bb = _state(known=("huttes",), stock=0.0)
    camped, cb = _state(known=("huttes",), stock=0.0)
    sites.make_camp(camped, 1)
    for st in (bare, camped):
        st.clock.week = 45
        st.world.fill_season(Season.HIVER)
        for h in st.world.hexes_in_radius(st.bands[1].position, 2):
            st.world.set_exhaustion(h, 0.5)
    collect_food(bare)
    collect_food(camped)
    assert cb.population > bb.population


def test_forgotten_camps_fall_to_ruin():
    st, band = _state(known=("huttes",))
    sites.make_camp(st, 1)
    band.position = offset_to_axial(2, 2)
    st.tick_count = sites.CAMP_FORGOTTEN + 5
    sites.update(st)
    assert not st.sites


def test_sites_are_saved(tmp_path):
    world = make_filled_world(30, 16, Terrain.PLAINE, wrap_x=True)
    st = new_game(world)
    st.tribes[1].knowledge.update(("huttes", "fumage"))
    sites.make_camp(st, 1)
    st.bands[1].stock = 400.0
    sites.deposit(st, 1)
    path = tmp_path / "kora.json"
    save_game(st, path, {})
    loaded, _ = load_game(path, world)
    camp = next(iter(loaded.sites.values()))
    assert camp.kind == "camp" and camp.store > 0
    assert loaded.next_site_id == st.next_site_id
