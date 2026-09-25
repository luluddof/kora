from src.kora.ai import decide_ai
from src.kora.clock import Clock
from src.kora.persist import load_game, save_game
from src.kora.sim import (
    GameState,
    apply_movement,
    band_lines,
    band_summary,
    can_split,
    is_shielded,
    new_game,
    resolve_raids,
    set_goto,
    set_march_to_band,
    tick,
)
from src.kora.types import Band, Order, OrderKind, Terrain, Tribe
from src.kora.world import make_filled_world, offset_to_axial


def _fight(player_loses=True, ally=False, world=None):
    world = world or make_filled_world(40, 24, Terrain.PLAINE)
    pos = offset_to_axial(20, 12)
    me = Band(id=1, tribe_id=1, position=pos, population=12, stock=100)
    foe = Band(id=2, tribe_id=2, position=pos, population=40, stock=50)
    foe.order = Order(kind=OrderKind.MARCH_TO_BAND, target_band_id=1)
    bands = {1: me, 2: foe}
    if ally:
        bands[3] = Band(id=3, tribe_id=1, position=offset_to_axial(30, 12), population=20, stock=0)
    st = GameState(
        world=world,
        clock=Clock(),
        tribes={1: Tribe(1, "Joueur", 20, True), 2: Tribe(2, "Steppe", 20, False)},
        bands=bands,
    )
    from src.kora.vision import recompute_vision

    recompute_vision(st)
    return st, me, foe


def test_beaten_band_loses_stock_and_retreats_toward_its_group():
    st, me, _foe = _fight(ally=True)
    resolve_raids(st)
    assert me.stock == 50
    assert me.retreating
    assert me.path[-1] == st.bands[3].position


def test_without_a_group_it_retreats_on_explored_land_far_from_foes():
    st, me, foe = _fight()
    resolve_raids(st)
    goal = me.path[-1]
    assert goal in st.vision.explored
    assert st.world.distance(goal, foe.position) >= 4


def test_retreat_walks_instead_of_teleporting():
    st, me, _foe = _fight(ally=True)
    start = me.position
    resolve_raids(st)
    assert me.position == start
    apply_movement(st)
    moved = st.world.distance(start, me.position)
    assert 1 <= moved <= 9


def test_orders_are_locked_until_the_retreat_is_over():
    st, me, foe = _fight(ally=True)
    resolve_raids(st)
    path = list(me.path)
    set_goto(st, me.id, offset_to_axial(2, 2))
    set_march_to_band(st, me.id, foe.id)
    assert me.path == path
    assert not can_split(st, me.id)
    assert "En repli" in band_lines(band_summary(st, me.id))[-1]
    for _ in range(4):
        apply_movement(st)
    assert not me.retreating
    set_goto(st, me.id, offset_to_axial(2, 2))
    assert me.order.kind is OrderKind.GOTO
    assert me.path[-1] == offset_to_axial(2, 2)


def test_a_retreating_band_cannot_be_attacked_again():
    st, me, foe = _fight()
    resolve_raids(st)
    assert is_shielded(st, me)
    before = me.population
    other = Band(id=4, tribe_id=2, position=me.position, population=40, stock=0)
    other.order = Order(kind=OrderKind.MARCH_TO_BAND, target_band_id=me.id)
    st.bands[4] = other
    resolve_raids(st)
    assert me.population == before


def test_ai_does_not_pick_a_shielded_band_as_prey():
    st, me, foe = _fight()
    resolve_raids(st)
    hunter = Band(id=8, tribe_id=2, position=offset_to_axial(24, 12), population=40, stock=100)
    st.bands[8] = hunter
    st.clock.week = 35
    decide_ai(st)
    assert not (
        hunter.order.kind is OrderKind.MARCH_TO_BAND and hunter.order.target_band_id == me.id
    )


def test_a_whole_game_week_does_not_pause_and_the_retreat_saves(tmp_path):
    st = new_game(make_filled_world(40, 24, Terrain.PLAINE, wrap_x=True))
    band = st.bands[1]
    band.retreating = True
    band.shield_until = 9
    band.path = [offset_to_axial(3, 3)]
    path = tmp_path / "kora.json"
    save_game(st, path, {})
    loaded, _view = load_game(path, st.world)
    assert loaded.bands[1].retreating
    assert loaded.bands[1].shield_until == 9
    st.clock.paused = False
    tick(st)
    assert st.clock.paused is False
