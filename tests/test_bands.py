from src.kora.clock import Clock
from src.kora.persist import load_game, save_game
from src.kora.sim import (
    MAX_BANDS_PER_TRIBE,
    SPLIT_MIN_POP,
    GameState,
    can_split,
    merge_bands,
    new_game,
    resolve_joins,
    set_march_to_band,
    split_band,
    tick,
)
from src.kora.types import Band, OrderKind, Terrain, Tribe
from src.kora.world import make_filled_world, offset_to_axial


def _state(pop=40, stock=200.0):
    world = make_filled_world(20, 12, Terrain.PLAINE)
    pos = offset_to_axial(8, 6)
    band = Band(id=1, tribe_id=1, position=pos, population=pop, stock=stock)
    st = GameState(
        world=world,
        clock=Clock(),
        tribes={1: Tribe(1, "Joueur", 20, True), 2: Tribe(2, "Steppe", 20, False)},
        bands={1: band},
    )
    return st, band


def test_split_halves_people_and_stock_on_the_same_hex():
    st, band = _state(pop=41, stock=164.0)
    nid = split_band(st, band.id)
    assert nid is not None
    child = st.bands[nid]
    assert band.population + child.population == 41
    assert child.population == 20
    assert band.stock + child.stock == 164.0
    assert child.position == band.position
    assert child.tribe_id == band.tribe_id


def test_split_needs_enough_people_and_a_free_band_slot():
    st, band = _state(pop=SPLIT_MIN_POP - 1)
    assert not can_split(st, band.id)
    assert split_band(st, band.id) is None
    band.population = 400
    while len(st.bands) < MAX_BANDS_PER_TRIBE:
        biggest = max(st.bands.values(), key=lambda b: b.population)
        assert split_band(st, biggest.id) is not None
    biggest = max(st.bands.values(), key=lambda b: b.population)
    assert biggest.population >= SPLIT_MIN_POP
    assert not can_split(st, biggest.id)


def test_new_band_ids_are_never_reused():
    st, band = _state(pop=80)
    first = split_band(st, band.id)
    del st.bands[first]
    second = split_band(st, band.id)
    assert second != first


def test_merge_joins_every_ally_on_the_hex():
    st, band = _state(pop=40, stock=100.0)
    nid = split_band(st, band.id)
    assert merge_bands(st, band.id) == 1
    assert nid not in st.bands
    assert band.population == 40
    assert band.stock == 100.0


def test_marching_to_an_ally_merges_on_arrival():
    st, band = _state(pop=40)
    nid = split_band(st, band.id)
    child = st.bands[nid]
    child.position = offset_to_axial(12, 6)
    set_march_to_band(st, band.id, nid)
    assert band.order.kind is OrderKind.MARCH_TO_BAND
    st.clock.paused = False
    tick(st)
    assert band.id not in st.bands
    assert st.bands[nid].population >= 40


def test_join_retargets_enemies_that_hunted_the_absorbed_band():
    st, band = _state(pop=40)
    nid = split_band(st, band.id)
    hunter = Band(id=9, tribe_id=2, position=offset_to_axial(2, 2), population=10, stock=0)
    st.bands[9] = hunter
    set_march_to_band(st, 9, band.id)
    set_march_to_band(st, band.id, nid)
    resolve_joins(st)
    assert band.id not in st.bands
    assert hunter.order.target_band_id == nid


def test_save_keeps_split_bands_and_the_id_counter(tmp_path):
    world = make_filled_world(24, 12, Terrain.PLAINE, wrap_x=True)
    st = new_game(world)
    band = st.bands[1]
    nid = split_band(st, band.id)
    st.bands[nid].growth_acc = 0.6
    st.bands[nid].last_raid_tick = 12
    path = tmp_path / "kora.json"
    save_game(st, path, {})
    loaded, _view = load_game(path, world)
    assert nid in loaded.bands
    assert loaded.bands[nid].growth_acc == 0.6
    assert loaded.bands[nid].last_raid_tick == 12
    assert loaded.next_band_id == st.next_band_id
