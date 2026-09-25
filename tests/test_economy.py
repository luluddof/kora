from src.kora.clock import Clock
from src.kora.sim import (
    FAMINE_RATE,
    STOCK_MAX_FACTOR,
    GameState,
    apply_movement,
    collect_food,
    famine_loss,
    new_game,
    resolve_raids,
    update_population,
    update_prestige,
)
from src.kora.types import Band, Order, OrderKind, Terrain, Tribe
from src.kora.world import (
    make_filled_world,
    offset_to_axial,
    pick_spawn_hexes,
    spawn_forage,
)


def test_famine_kills_a_share_of_the_band_not_one_per_missing_unit():
    # Ancienne regle : 22 unites manquantes = 22 morts en une semaine.
    assert famine_loss(40, 22 / 40) == round(40 * 22 / 40 * FAMINE_RATE)
    assert famine_loss(40, 22 / 40) < 5
    assert famine_loss(40, 0.01) == 1
    assert famine_loss(3, 1.0) <= 3
    assert famine_loss(40, 0.0) == 0


def test_stock_can_cover_a_winter():
    assert STOCK_MAX_FACTOR >= 10


def _winter_state(pop, stock):
    world = make_filled_world(15, 15, Terrain.PLAINE)
    clock = Clock()
    clock.week = 41
    band = Band(id=1, tribe_id=1, position=offset_to_axial(7, 7), population=pop, stock=stock)
    st = GameState(world=world, clock=clock, tribes={1: Tribe(1, "t", 20, True)}, bands={1: band})
    world.fill_season(clock.season())
    return st, band


def test_a_stocked_band_crosses_winter_a_bare_one_suffers():
    fed, fed_band = _winter_state(30, 300.0)
    bare, bare_band = _winter_state(30, 0.0)
    for _ in range(10):
        collect_food(fed)
        collect_food(bare)
    assert fed_band.population == 30
    assert 10 < bare_band.population < 30


def test_growth_is_proportional_and_splitting_does_not_multiply_it():
    world = make_filled_world(8, 8, Terrain.VALLEE)
    one = Band(id=1, tribe_id=1, position=offset_to_axial(3, 3), population=40, stock=400)
    halves = [
        Band(id=2, tribe_id=1, position=offset_to_axial(3, 3), population=20, stock=200),
        Band(id=3, tribe_id=1, position=offset_to_axial(3, 3), population=20, stock=200),
    ]
    a = GameState(world=world, clock=Clock(), tribes={1: Tribe(1, "t", 20, True)}, bands={1: one})
    b = GameState(
        world=world,
        clock=Clock(),
        tribes={1: Tribe(1, "t", 20, True)},
        bands={h.id: h for h in halves},
    )
    for _ in range(12):
        update_population(a)
        update_population(b)
    # Ancienne regle (minimum 1 par bande) : +12 contre +24 en 12 periodes.
    grown_one = one.population - 40
    grown_halves = sum(h.population for h in halves) - 40
    assert grown_one > 0
    assert abs(grown_halves - grown_one) <= 1


def test_winter_prestige_only_looks_at_the_end_of_winter():
    st, band = _winter_state(30, 0.0)
    st.clock.week = 42
    collect_food(st)
    assert st.tribes[1].famine_during_winter is False
    st.clock.week = 50
    collect_food(st)
    assert st.tribes[1].famine_during_winter is True
    st.clock.week = 52
    st.clock.advance_week()
    update_prestige(st)
    assert st.tribes[1].prestige == 14


def _raid(att_pop, def_pop, ally_pop=0):
    world = make_filled_world(20, 20, Terrain.PLAINE)
    pos = offset_to_axial(10, 10)
    att = Band(id=1, tribe_id=1, position=pos, population=att_pop, stock=50)
    deff = Band(id=2, tribe_id=2, position=pos, population=def_pop, stock=50)
    att.order = Order(kind=OrderKind.MARCH_TO_BAND, target_band_id=2)
    bands = {1: att, 2: deff}
    if ally_pop:
        bands[3] = Band(id=3, tribe_id=2, position=offset_to_axial(11, 10), population=ally_pop, stock=0)
    st = GameState(
        world=world,
        clock=Clock(),
        tribes={1: Tribe(1, "a", 20, True), 2: Tribe(2, "b", 20, False)},
        bands=bands,
    )
    return st, att, deff


def test_tie_goes_to_the_defender_even_with_the_higher_band_id():
    st, att, deff = _raid(20, 20)
    resolve_raids(st)
    assert st.tribes[2].prestige > st.tribes[1].prestige
    assert deff.position == offset_to_axial(10, 10)


def test_nearby_allies_reinforce_the_defender():
    st, att, deff = _raid(30, 20, ally_pop=15)
    ally = st.bands[3]
    resolve_raids(st)
    assert st.tribes[2].prestige > st.tribes[1].prestige
    # Le renfort se bat (il prend sa part des coups) mais reste chez lui.
    assert 12 <= ally.population <= 15
    assert ally.position == offset_to_axial(11, 10) and not ally.retreating
    rep = st.fights[0].report if st.fights else None
    assert rep is None or rep["defender"]["bands"] == 2


def test_loser_walks_away_to_a_safe_fed_place_when_alone():
    st, att, deff = _raid(40, 10)
    resolve_raids(st)
    assert deff.retreating
    goal = deff.path[-1]
    assert st.world.distance(goal, att.position) >= 4
    for _ in range(6):
        apply_movement(st)
    assert not deff.retreating
    assert deff.position == goal


def test_player_log_says_who_attacked():
    st, att, deff = _raid(40, 10)
    resolve_raids(st)
    assert any(e.text == "Raid contre b : victoire." for e in st.log.entries)


def test_spawns_start_where_the_band_can_eat():
    world = make_filled_world(80, 40, Terrain.STEPPE, wrap_x=True)
    for row in range(10, 30):
        for col in range(50, 70):
            world._terrains[row][col] = Terrain.VALLEE
    spots = pick_spawn_hexes(world, 4, min_forage=[40.0, 0, 0, 0])
    assert spawn_forage(world, spots[0]) >= 40.0
    assert world.terrain(spots[0]) is Terrain.VALLEE


def test_ai_tribes_start_on_their_own_biome_with_their_know_how():
    st = new_game()
    assert st.world.terrain(st.bands[2].position) is Terrain.STEPPE
    assert st.world.terrain(st.bands[3].position) is Terrain.FORET
    assert st.world.terrain(st.bands[4].position) is Terrain.COTE
    assert st.tribes[2].troupeau
    assert st.tribes[4].cabotage
    assert spawn_forage(st.world, st.bands[1].position) >= 40.0
    player = st.bands[1].position
    assert all(st.world.distance(player, b.position) > 16 for b in st.bands.values() if b.id != 1)
