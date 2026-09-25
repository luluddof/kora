from src.kora.log import FILTER_ALL, GameLog, LogKind
from src.kora.globe import land_draw_stride
from src.kora.clock import Clock
from src.kora import tech
from src.kora.sim import GameState, collect_food, tick
from src.kora.types import Band, Terrain, Tribe
from src.kora.world import make_filled_world, offset_to_axial
from src.kora.persist import load_game, save_game


def test_log_keeps_the_last_entries_and_filters():
    from src.kora.log import LOG_CAP

    log = GameLog()
    total = LOG_CAP + 10
    for i in range(total):
        kind = LogKind.SAISON if i % 2 == 0 else LogKind.COMBAT
        log.add(kind, f"n{i}", 1, i)
    assert len(log.entries) == LOG_CAP
    combats = log.filtered(LogKind.COMBAT.value)
    assert all(e.kind is LogKind.COMBAT for e in combats)
    assert log.filtered(FILTER_ALL, newest_first=True)[0].text == f"n{total - 1}"
    assert log.filtered(FILTER_ALL, newest_first=False)[0].text == "n10"


def test_far_camera_skips_more_land_dots():
    assert land_draw_stride(1.20) == 1
    assert land_draw_stride(1.40) >= 2
    assert land_draw_stride(1.90) >= 2
    assert land_draw_stride(2.80) >= 3
    assert land_draw_stride(3.20) >= land_draw_stride(1.90)


def test_player_famine_logs_ai_does_not():
    world = make_filled_world(15, 15, Terrain.COLLINE)
    clock = Clock()
    clock.week = 40
    pos = offset_to_axial(7, 7)
    player = Band(id=1, tribe_id=1, position=pos, population=40, stock=0)
    st = GameState(
        world=world,
        clock=clock,
        tribes={1: Tribe(1, "t", 20, True)},
        bands={1: player},
    )
    world.fill_season(clock.season())
    collect_food(st)
    assert any(e.kind is LogKind.SURVIE and "Famine" in e.text for e in st.log.entries)
    world2 = make_filled_world(15, 15, Terrain.COLLINE)
    clock2 = Clock()
    clock2.week = 40
    ai = Band(id=1, tribe_id=2, position=pos, population=40, stock=0)
    st2 = GameState(
        world=world2,
        clock=clock2,
        tribes={2: Tribe(2, "ia", 20, False)},
        bands={1: ai},
    )
    world2.fill_season(clock2.season())
    collect_food(st2)
    assert st2.log.entries == []


def test_season_change_logs_once():
    world = make_filled_world(16, 12, Terrain.PLAINE, wrap_x=True)
    pos = offset_to_axial(4, 6)
    st = GameState(
        world=world,
        clock=Clock(),
        tribes={1: Tribe(1, "t", 20, True)},
        bands={1: Band(1, 1, pos, 40, 160)},
    )
    world.fill_season(st.clock.season())
    st.clock.week = 13
    st.clock.paused = False
    tick(st)
    seasons = [e for e in st.log.entries if e.kind is LogKind.SAISON]
    assert len(seasons) == 1
    assert "Ete" in seasons[0].text


def test_player_new_knowledge_logs_ai_does_not():
    world = make_filled_world(12, 10, Terrain.PLAINE)
    pos = offset_to_axial(3, 4)
    for is_player, tid in ((True, 1), (False, 2)):
        tribe = Tribe(tid, "t", 20, is_player, knowledge={"feu", "outils"})
        tribe.practice["hivers"] = 1
        st = GameState(
            world=world, clock=Clock(), tribes={tid: tribe}, bands={tid: Band(tid, tid, pos, 40, 200)}
        )
        if is_player:
            assert tech.choose(st, tid, "fumage")
        for week in range(40):
            st.tick_count = week
            tech.update_learning(st)
        assert "fumage" in tribe.knowledge
        logged = [e for e in st.log.entries if e.kind is LogKind.DECOUVERTE]
        assert bool(logged) is is_player
        if is_player:
            assert "Fumage" in logged[0].text and "+4 semaines" in logged[0].text


def test_log_survives_save(tmp_path):
    world = make_filled_world(24, 12, Terrain.PLAINE, wrap_x=True)
    from src.kora.sim import new_game

    st = new_game(world)
    st.log.add(LogKind.COMBAT, "Raid contre Steppe.", 1, 3)
    path = tmp_path / "kora.json"
    save_game(st, path, {"camera_x": 0, "camera_y": 0, "zoom": 1, "selected": 1})
    loaded, _view = load_game(path, world)
    texts = [e.text for e in loaded.log.entries]
    assert "Raid contre Steppe." in texts
    assert loaded.log.seq >= st.log.seq
    assert loaded.seen_enemy_tribes == st.seen_enemy_tribes
