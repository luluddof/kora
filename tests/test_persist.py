from src.kora.persist import load_game, save_game
from src.kora.sim import GameState, new_game
from src.kora.types import Order, OrderKind, Terrain
from src.kora.vision import recompute_vision
from src.kora.world import make_filled_world, offset_to_axial


def test_save_roundtrip_restores_clock_band_and_fog(tmp_path):
    world = make_filled_world(24, 12, Terrain.PLAINE, wrap_x=True)
    st = new_game(world)
    band = next(iter(st.bands.values()))
    goal = offset_to_axial(10, 6)
    band.order = Order(kind=OrderKind.GOTO, target_hex=goal)
    band.path = [offset_to_axial(8, 6), goal]
    st.clock.week = 41
    st.clock.year = 3
    st.clock.paused = False
    st.clock.speed = 4
    band.population = 33
    band.stock = 90.5
    st.tribes[1].prestige = 44
    st.tick_count = 17
    st.world.set_exhaustion(band.position, 0.5)
    recompute_vision(st)
    extra = offset_to_axial(2, 2)
    st.vision.explored.add(extra)
    path = tmp_path / "kora.json"
    view = {"camera_x": 12.5, "camera_y": 8.0, "zoom": 0.4, "selected": band.id}
    save_game(st, path, view)
    loaded, loaded_view = load_game(path, world)
    lb = loaded.bands[band.id]
    assert loaded.clock.week == 41
    assert loaded.clock.year == 3
    assert loaded.clock.speed == 4
    assert loaded.clock.paused is False
    assert lb.population == 33
    assert lb.stock == 90.5
    assert lb.order.kind is OrderKind.GOTO
    assert lb.order.target_hex == goal
    assert lb.path == [offset_to_axial(8, 6), goal]
    assert loaded.tribes[1].prestige == 44
    assert loaded.tick_count == 17
    assert loaded.world.exhaustion(band.position) == 0.5
    assert extra in loaded.vision.explored
    assert loaded_view["camera_x"] == 12.5
    assert loaded_view["selected"] == band.id
    assert loaded.log.seq == st.log.seq
    assert [e.text for e in loaded.log.entries] == [e.text for e in st.log.entries]
    assert loaded.seen_enemy_tribes == set(st.seen_enemy_tribes)


def test_save_roundtrip_restores_fight_marks(tmp_path):
    from src.kora.sim import resolve_raids
    from src.kora.types import Band, Tribe
    from src.kora.clock import Clock

    world = make_filled_world(12, 12, Terrain.PLAINE)
    pos = offset_to_axial(5, 5)
    st = GameState(
        world=world,
        clock=Clock(),
        tribes={1: Tribe(1, "a", 20, True), 2: Tribe(2, "b", 20, False)},
        bands={
            1: Band(1, 1, pos, 40, 80),
            2: Band(2, 2, pos, 20, 80),
        },
    )
    recompute_vision(st)
    resolve_raids(st)
    assert st.fights
    path = tmp_path / "kora.json"
    save_game(st, path, {"camera_x": 0, "camera_y": 0, "zoom": 1, "selected": 1})
    loaded, _view = load_game(path, world)
    assert len(loaded.fights) == 1
    assert loaded.fights[0].winner_tribe == st.fights[0].winner_tribe
    assert loaded.fights[0].loser_loss == st.fights[0].loser_loss
    assert loaded.fights[0].hex == st.fights[0].hex


def test_load_rejects_map_size_mismatch(tmp_path):
    world = make_filled_world(24, 12, Terrain.PLAINE, wrap_x=True)
    st = new_game(world)
    path = tmp_path / "kora.json"
    save_game(st, path, {"camera_x": 0, "camera_y": 0, "zoom": 1, "selected": 1})
    other = make_filled_world(10, 8, Terrain.PLAINE, wrap_x=True)
    assert load_game(path, other) is None


def test_missing_save_returns_none(tmp_path):
    world = make_filled_world(8, 8, Terrain.PLAINE)
    assert load_game(tmp_path / "nope.json", world) is None


def test_unreadable_save_is_set_aside_not_overwritten(tmp_path):
    from src.kora.persist import set_aside_save

    path = tmp_path / "kora.json"
    assert set_aside_save(path) is None
    path.write_text('{"version": 1, "map": {"width": 1}}', encoding="utf-8")
    moved = set_aside_save(path)
    assert moved is not None and moved.exists()
    assert not path.exists()
    assert "ancienne" in moved.name
