from src.kora.clock import Clock
from src.kora import tech
from src.kora.sim import GameState, collect_food, forage_hexes, update_exhaustion

TROUPEAU_STEPPE_WEEKS = tech.TROUPEAU_STEPPE_WEEKS


def troupeau_ready(st, tid):
    return tech.status(st, tid, "troupeau") in ("disponible", "en_cours")


def _learn(st):
    for week in range(120):
        st.tick_count = week
        tech.update_learning(st)
from src.kora.types import Band, Season, Terrain, Tribe
from src.kora.world import food_production, make_filled_world, offset_to_axial


def _steppe_world():
    return make_filled_world(12, 10, Terrain.STEPPE)


def _tribe_on_steppe(pop=10, prestige=0, is_player=True, troupeau=False):
    world = _steppe_world()
    pos = offset_to_axial(3, 4)
    band = Band(id=1, tribe_id=1, position=pos, population=pop, stock=float(pop * 4))
    tribe = Tribe(
        1,
        "t",
        prestige,
        is_player,
        troupeau=troupeau,
        steppe_seen=True,
        steppe_weeks=TROUPEAU_STEPPE_WEEKS,
        knowledge={"feu", "outils", "epieu"},
        practice={"steppe": TROUPEAU_STEPPE_WEEKS},
    )
    st = GameState(
        world=world,
        clock=Clock(),
        tribes={1: tribe},
        bands={1: band},
    )
    return st, band, tribe


def test_not_ready_if_missing_pop():
    st, _band, _tribe = _tribe_on_steppe(pop=9)
    assert troupeau_ready(st, 1) is False


def test_needs_the_spear_hunt_first():
    st, _band, tribe = _tribe_on_steppe()
    tribe.knowledge = {"feu", "outils"}
    assert tech.status(st, 1, "troupeau") == "verrouille"


def test_ready_with_ten_pop_and_no_prestige():
    st, _band, tribe = _tribe_on_steppe(pop=10, prestige=0, is_player=True)
    assert troupeau_ready(st, 1) is True
    _learn(st)
    assert tribe.troupeau is False
    assert tech.choose(st, 1, "troupeau")
    _learn(st)
    assert tribe.troupeau is True
    assert troupeau_ready(st, 1) is False


def test_ai_adopts_when_ready():
    st, _band, tribe = _tribe_on_steppe(is_player=False)
    assert troupeau_ready(st, 1) is True
    _learn(st)
    assert tribe.troupeau is True


def test_steppe_weeks_accumulate():
    world = _steppe_world()
    pos = offset_to_axial(3, 4)
    band = Band(id=1, tribe_id=1, position=pos, population=40, stock=160)
    tribe = Tribe(1, "t", 0, True)
    st = GameState(world=world, clock=Clock(), tribes={1: tribe}, bands={1: band})
    tech.update_practice(st)
    tech.update_practice(st)
    assert tribe.steppe_weeks == 2
    assert tribe.practice["steppe"] == 2
    assert tribe.steppe_seen is True


def test_inland_forest_does_not_count_steppe_weeks():
    world = make_filled_world(8, 8, Terrain.FORET)
    pos = offset_to_axial(3, 3)
    band = Band(id=1, tribe_id=1, position=pos, population=40, stock=160)
    tribe = Tribe(1, "t", 0, True)
    st = GameState(world=world, clock=Clock(), tribes={1: tribe}, bands={1: band})
    tech.update_practice(st)
    tech.update_practice(st)
    assert tribe.steppe_weeks == 0
    assert tribe.steppe_seen is False


def test_herd_lets_steppe_hold_fifty():
    world = make_filled_world(8, 8, Terrain.STEPPE)
    h = offset_to_axial(3, 3)
    plain = make_filled_world(8, 8, Terrain.PLAINE)
    ph = offset_to_axial(3, 3)
    winter_herd = food_production(world, h, Season.HIVER, herd=True)
    winter_plain = food_production(plain, ph, Season.HIVER, herd=False)
    assert winter_herd > food_production(world, h, Season.HIVER, herd=False)
    assert winter_herd > winter_plain
    assert winter_herd * 19 + 4 * 50 / 13 >= 50
    assert food_production(plain, ph, Season.PRINTEMPS, herd=False) > food_production(
        world, h, Season.PRINTEMPS, herd=True
    )
    assert food_production(plain, ph, Season.ETE, herd=False) > food_production(
        world, h, Season.ETE, herd=True
    )
    assert food_production(world, h, Season.AUTOMNE, herd=True) > food_production(
        plain, ph, Season.AUTOMNE, herd=False
    )
    for season in (Season.PRINTEMPS, Season.ETE, Season.AUTOMNE, Season.HIVER):
        assert food_production(world, h, season, herd=True) > food_production(
            world, h, season, herd=False
        )
        assert food_production(plain, ph, season, herd=True) == food_production(
            plain, ph, season, herd=False
        )


def _winter_steppe_camp(pop=20, troupeau=False):
    world = make_filled_world(15, 15, Terrain.STEPPE)
    clock = Clock()
    clock.week = 45
    pos = offset_to_axial(7, 7)
    band = Band(id=1, tribe_id=1, position=pos, population=pop, stock=float(pop * 4))
    tribe = Tribe(
        1,
        "t",
        0,
        True,
        troupeau=troupeau,
        steppe_seen=True,
        steppe_weeks=TROUPEAU_STEPPE_WEEKS,
    )
    st = GameState(world=world, clock=clock, tribes={1: tribe}, bands={1: band})
    world.fill_season(Season.HIVER)
    return st, pos


def test_winter_steppe_without_herd_exhausts_under_a_band():
    st, pos = _winter_steppe_camp(troupeau=False)
    collect_food(st)
    update_exhaustion(st)
    assert st.world.exhaustion(pos) == 0.5


def test_winter_steppe_with_herd_stays_better_than_plain():
    st, pos = _winter_steppe_camp(troupeau=True)
    collect_food(st)
    update_exhaustion(st)
    assert st.world.exhaustion(pos) == 1.0
    food = food_production(st.world, pos, Season.HIVER, herd=True)
    plain = make_filled_world(8, 8, Terrain.PLAINE)
    ph = offset_to_axial(3, 3)
    assert food > food_production(plain, ph, Season.HIVER, herd=False)


def test_winter_steppe_with_herd_recovers_exhausted_land():
    st, pos = _winter_steppe_camp(troupeau=True)
    for h in forage_hexes(st, st.bands[1]):
        st.world.set_exhaustion(h, 0.5)
    collect_food(st)
    update_exhaustion(st)
    assert st.world.exhaustion(pos) == 0.6


def test_player_learning_logs_ai_does_not():
    st, _band, _tribe = _tribe_on_steppe(is_player=True)
    tech.choose(st, 1, "troupeau")
    _learn(st)
    assert any("Troupeau" in e.text and "Nouveau savoir" in e.text for e in st.log.entries)
    st2, _b, _t = _tribe_on_steppe(is_player=False)
    _learn(st2)
    assert st2.log.entries == []
