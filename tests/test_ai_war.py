from src.kora.ai import decide_ai
from src.kora.ai_war import advance_plans, plan_raid, recheck_hunts, start_plan
from src.kora.clock import Clock
from src.kora.persist import load_game, save_game
from src.kora.sim import GameState, new_game, set_march_to_band, tick
from src.kora.types import Band, OrderKind, Terrain, Tribe
from src.kora.world import make_filled_world, offset_to_axial

AI = 2
PREY = 1


def _state():
    world = make_filled_world(50, 24, Terrain.PLAINE)
    st = GameState(
        world=world,
        clock=Clock(),
        tribes={
            PREY: Tribe(PREY, "Joueur", 20, True),
            AI: Tribe(AI, "Steppe", 20, False),
        },
        bands={},
        next_band_id=100,
    )
    st.clock.week = 35  # pas de scission, pas d'hiver proche
    return st


def _band(st, bid, tribe, col, row, pop, stock=0.0):
    b = Band(id=bid, tribe_id=tribe, position=offset_to_axial(col, row), population=pop, stock=stock)
    st.bands[bid] = b
    return b


def test_no_raid_when_the_target_has_help_nearby():
    st = _state()
    ai = _band(st, 12, AI, 10, 12, 36)
    _band(st, 1, PREY, 14, 12, 20)
    _band(st, 2, PREY, 15, 12, 15)  # renfort a 1 case de la cible
    assert plan_raid(st, ai, 4) is None
    st.bands[2].position = offset_to_axial(49, 23)  # le renfort s'en va (hors de portee)
    assert plan_raid(st, ai, 4) == ("attack", st.bands[1])


def test_too_weak_alone_it_merges_with_a_sister_band_close_by():
    st = _state()
    # Des vivres : des affames se battraient mal (moral, battle.py).
    ai = _band(st, 12, AI, 10, 12, 20, stock=200.0)
    sister = _band(st, 13, AI, 12, 12, 20, stock=200.0)
    prey = _band(st, 1, PREY, 16, 12, 28, stock=200.0)
    plan = plan_raid(st, ai, 4)
    assert plan == ("merge", sister, prey)
    start_plan(st, ai, plan)
    assert ai.order.kind is OrderKind.MARCH_TO_BAND and ai.order.target_band_id == sister.id
    for _ in range(4):
        tick(st)
    assert 12 not in st.bands  # fusionnee dans la soeur...
    assert st.bands[13].last_raid_tick >= 0  # ...qui a attaque ensuite
    assert prey.population < 28 and prey.shield_until > 0  # et gagne (proie en repli)
    assert st.tribes[AI].prestige > 20


def test_a_far_sister_is_called_and_they_leave_together():
    st = _state()
    ai = _band(st, 12, AI, 10, 12, 20)
    sister = _band(st, 13, AI, 17, 12, 20)
    prey = _band(st, 1, PREY, 10, 18, 28)
    plan = plan_raid(st, ai, 4)
    assert plan[0] == "call" and plan[1] is sister
    start_plan(st, ai, plan)
    assert ai.order.kind is OrderKind.STAY
    assert sister.path and sister.path[-1] == ai.position
    for _ in range(3):
        from src.kora.sim import apply_movement

        apply_movement(st)
        advance_plans(st)
    assert sister.position == ai.position
    assert ai.order.target_band_id == prey.id
    assert sister.order.target_band_id == prey.id
    assert ai.path == sister.path


def test_a_raid_is_called_off_when_the_target_gets_reinforced():
    st = _state()
    ai = _band(st, 12, AI, 10, 12, 36)
    prey = _band(st, 1, PREY, 20, 12, 20)
    set_march_to_band(st, ai.id, prey.id)
    recheck_hunts(st)
    assert ai.order.kind is OrderKind.MARCH_TO_BAND
    _band(st, 2, PREY, 21, 12, 25)
    recheck_hunts(st)
    assert ai.order.kind is OrderKind.STAY


def test_roaming_ai_does_not_settle_next_to_a_stronger_band():
    st = _state()
    ai = _band(st, 12, AI, 25, 12, 20, stock=400)
    foe = _band(st, 1, PREY, 29, 12, 60)
    for _ in range(12):
        ai.path = []
        ai.order.kind = OrderKind.STAY
        st.tick_count = 0
        decide_ai(st)
        if ai.path:
            assert st.world.distance(ai.path[-1], foe.position) > 2


def test_plans_are_saved(tmp_path):
    world = make_filled_world(30, 16, Terrain.PLAINE, wrap_x=True)
    st = new_game(world)
    st.bands[2].intent_prey = 1
    st.bands[2].intent_until = 30
    path = tmp_path / "kora.json"
    save_game(st, path, {})
    loaded, _view = load_game(path, world)
    assert loaded.bands[2].intent_prey == 1
    assert loaded.bands[2].intent_until == 30
