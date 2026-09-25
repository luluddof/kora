from src.kora.clock import Clock
from src.kora.sim import (
    COMBAT_MARK_MAX,
    COMBAT_MARK_WEEKS,
    GameState,
    band_force,
    apply_movement,
    consume_ticks,
    fight_at,
    fight_lines,
    prune_fight_marks,
    resolve_raids,
)
from src.kora.types import Band, FightMark, Terrain, Tribe
from src.kora.world import hex_distance, make_filled_world, offset_to_axial


def _raid_state(player=True, visible=True):
    world = make_filled_world(12, 12, Terrain.PLAINE)
    pos = offset_to_axial(5, 5)
    att = Band(id=1, tribe_id=1, position=pos, population=40, stock=80)
    deff = Band(id=2, tribe_id=2, position=pos, population=20, stock=80)
    st = GameState(
        world=world,
        clock=Clock(),
        tribes={
            1: Tribe(1, "a", 20, player),
            2: Tribe(2, "b", 20, False),
        },
        bands={1: att, 2: deff},
    )
    if visible:
        from src.kora.vision import recompute_vision

        recompute_vision(st)
    return st, att, deff, pos


def test_stronger_attacker_reduces_defender_and_forces_flee():
    st, att, deff, pos = _raid_state()
    assert band_force(st, att) > band_force(st, deff)
    resolve_raids(st)
    assert deff.population < 20
    # Pas de teleportation : le perdant part a pied la semaine suivante.
    assert deff.position == pos
    assert deff.retreating and deff.path
    apply_movement(st)
    assert hex_distance(deff.position, att.position) >= 1
    assert att.stock == 120
    assert st.tribes[1].prestige == 25
    assert st.tribes[2].prestige == 16


def test_visible_raid_leaves_a_fight_mark():
    st, att, deff, pos = _raid_state()
    resolve_raids(st)
    assert len(st.fights) == 1
    mark = st.fights[0]
    assert mark.hex == pos
    assert mark.winner_tribe == 1
    assert mark.loser_tribe == 2
    assert mark.winner_before == 40
    assert mark.loser_before == 20
    # Le vainqueur perd peu, le vaincu surtout dans la fuite (battle.py).
    assert 0 <= mark.winner_loss < mark.loser_loss
    assert 3 <= mark.loser_loss <= 10
    assert mark.report["outcome"] in ("deroute", "retraite")
    lines = fight_lines(mark)
    assert lines[0] == "Combat"
    assert any("Gagnant" in line for line in lines)
    after = 40 - mark.winner_loss
    assert any("40" in line and str(after) in line for line in lines)


def test_fog_ai_raid_leaves_no_mark():
    world = make_filled_world(12, 12, Terrain.PLAINE)
    pos = offset_to_axial(5, 5)
    st = GameState(
        world=world,
        clock=Clock(),
        tribes={
            2: Tribe(2, "b", 20, False),
            3: Tribe(3, "c", 20, False),
        },
        bands={
            2: Band(2, 2, pos, 40, 80),
            3: Band(3, 3, pos, 20, 80),
        },
    )
    resolve_raids(st)
    assert st.fights == []


def test_visible_raid_does_not_pause_the_clock():
    st, _att, _deff, _pos = _raid_state()
    st.clock.paused = False
    resolve_raids(st)
    assert st.clock.paused is False


def test_fog_ai_raid_does_not_pause_the_clock():
    world = make_filled_world(12, 12, Terrain.PLAINE)
    pos = offset_to_axial(5, 5)
    st = GameState(
        world=world,
        clock=Clock(),
        tribes={
            2: Tribe(2, "b", 20, False),
            3: Tribe(3, "c", 20, False),
        },
        bands={
            2: Band(2, 2, pos, 40, 80),
            3: Band(3, 3, pos, 20, 80),
        },
    )
    st.clock.paused = False
    resolve_raids(st)
    assert st.clock.paused is False
    assert st.fights == []


def test_visible_raid_lets_the_weeks_flow_and_logs_the_place():
    st, _att, _deff, pos = _raid_state()
    st.clock.paused = False
    st.clock.speed = 5
    consume_ticks(st, 0.0, dt=2.0, max_per_frame=8)
    assert st.clock.paused is False
    assert st.tick_count > 1
    mark = fight_at(st, pos)
    assert mark is not None
    assert any(e.hex == pos for e in st.log.entries)


def test_fight_marks_expire_and_cap():
    st, _att, _deff, pos = _raid_state()
    resolve_raids(st)
    assert st.fights
    st.tick_count = COMBAT_MARK_WEEKS
    prune_fight_marks(st)
    assert st.fights == []
    for i in range(COMBAT_MARK_MAX + 3):
        st.tick_count = i
        other = offset_to_axial(5, 5 + (i % 5))
        st.fights.append(
            FightMark(
                hex=other,
                tick=i,
                year=1,
                week=1,
                winner_tribe=1,
                loser_tribe=2,
                winner_name="a",
                loser_name="b",
                winner_before=40,
                loser_before=20,
                winner_loss=4,
                loser_loss=5,
                loot=10.0,
            )
        )
        prune_fight_marks(st)
    assert len(st.fights) <= COMBAT_MARK_MAX
