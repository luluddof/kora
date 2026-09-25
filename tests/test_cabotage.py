from src.kora.clock import Clock
from src.kora.persist import load_game, save_game
from src.kora import tech
from src.kora.sim import GameState, apply_movement, set_goto, tick
from src.kora.types import Band, OrderKind, Terrain, Tribe
from src.kora.world import make_filled_world, offset_to_axial


def _coast_world():
    world = make_filled_world(12, 10, Terrain.PLAINE)
    for col in range(12):
        world._terrains[4][col] = Terrain.COTE
    for row in range(5, 10):
        for col in range(12):
            world._terrains[row][col] = Terrain.EAU
    return world


def _tribe_on_coast(pop=tech.PIROGUE_POP, prestige=30, is_player=True, cabotage=False):
    world = _coast_world()
    pos = offset_to_axial(3, 4)
    band = Band(id=1, tribe_id=1, position=pos, population=pop, stock=float(pop * 4))
    tribe = Tribe(
        1,
        "t",
        prestige,
        is_player,
        cabotage=cabotage,
        shore_seen=True,
        coast_weeks=tech.PIROGUE_COAST_WEEKS,
        knowledge={"feu", "outils", "peche"},
        practice={"cote": tech.PIROGUE_COAST_WEEKS},
    )
    st = GameState(
        world=world,
        clock=Clock(),
        tribes={1: tribe},
        bands={1: band},
    )
    return st, band, tribe


def _ready(st, tid=1):
    return tech.status(st, tid, "pirogue") in ("disponible", "en_cours")


def test_pirogue_needs_fishing_first():
    st, _band, tribe = _tribe_on_coast()
    tribe.knowledge = {"feu", "outils"}
    assert tech.status(st, 1, "pirogue") == "verrouille"
    tribe.knowledge.add("peche")
    assert _ready(st)


def test_ready_without_prestige():
    st, _band, tribe = _tribe_on_coast(prestige=0)
    assert tribe.prestige == 0
    assert _ready(st)


def test_not_ready_if_missing_pop():
    st, _band, _tribe = _tribe_on_coast(pop=tech.PIROGUE_POP - 1)
    assert not _ready(st)


def test_not_ready_if_coast_weeks_short():
    st, _band, tribe = _tribe_on_coast()
    tribe.coast_weeks = 3
    tribe.practice["cote"] = 3
    assert not _ready(st)


def test_not_ready_if_shore_unseen():
    st, _band, tribe = _tribe_on_coast()
    tribe.shore_seen = False
    assert not _ready(st)


def test_player_must_choose_then_learns_it():
    st, _band, tribe = _tribe_on_coast(is_player=True)
    for _ in range(80):
        tech.update_learning(st)
    assert tribe.cabotage is False  # le joueur n'apprend rien tout seul
    assert tech.choose(st, 1, "pirogue")
    for _ in range(80):
        tech.update_learning(st)
    assert tribe.cabotage is True
    assert "pirogue" in tribe.knowledge
    assert tech.status(st, 1, "pirogue") == "connu"


def test_ai_learns_it_on_its_own():
    st, _band, tribe = _tribe_on_coast(is_player=False)
    for week in range(80):
        st.tick_count = week
        tech.update_learning(st)
    assert tribe.cabotage is True


def test_goto_water_ignored_until_cabotage():
    st, band, tribe = _tribe_on_coast(cabotage=False)
    shore = offset_to_axial(3, 5)
    set_goto(st, 1, shore)
    assert band.order.kind is OrderKind.STAY or not band.path
    tribe.cabotage = True
    set_goto(st, 1, shore)
    assert band.order.kind is OrderKind.GOTO
    assert band.path
    apply_movement(st)
    assert band.position == shore


def test_goto_ocean_ignored_even_with_cabotage():
    st, band, tribe = _tribe_on_coast(cabotage=True)
    deep = offset_to_axial(3, 8)
    set_goto(st, 1, deep)
    assert not band.path
    assert band.position == offset_to_axial(3, 4)


def test_coast_weeks_accumulate_on_tick():
    world = _coast_world()
    pos = offset_to_axial(3, 4)
    band = Band(id=1, tribe_id=1, position=pos, population=40, stock=160)
    tribe = Tribe(1, "t", 20, True)
    st = GameState(world=world, clock=Clock(), tribes={1: tribe}, bands={1: band})
    assert tribe.coast_weeks == 0
    tech.update_practice(st)
    tech.update_practice(st)
    assert tribe.coast_weeks == 2
    assert tribe.practice["cote"] == 2
    assert tribe.shore_seen is True


def test_inland_does_not_count_coast_weeks():
    world = make_filled_world(8, 8, Terrain.PLAINE)
    pos = offset_to_axial(3, 3)
    band = Band(id=1, tribe_id=1, position=pos, population=40, stock=160)
    tribe = Tribe(1, "t", 20, True)
    st = GameState(world=world, clock=Clock(), tribes={1: tribe}, bands={1: band})
    tech.update_practice(st)
    assert tribe.coast_weeks == 0


def test_detail_lists_the_three_conditions_with_progress():
    st, _band, _tribe = _tribe_on_coast()
    lines = [text for text, _style in tech.detail_lines(st, 1, "pirogue")]
    assert any("Rivage en vue" in line for line in lines)
    assert any(f"Peuple {tech.PIROGUE_POP}" in line for line in lines)
    assert any("sem. en cote" in line for line in lines)
    assert any("longer l'eau" in line for line in lines)


def test_ticks_give_ai_cabotage_not_player():
    # La pirogue presque apprise : l'IA la choisit et l'acheve seule, le
    # joueur doit la choisir lui-meme (la cote du test nourrit mal : un long
    # apprentissage y ferait fondre la bande sous le seuil).
    almost = tech.TECHS["pirogue"].cost - 3
    st, band, tribe = _tribe_on_coast(is_player=False)
    tribe.progress["pirogue"] = almost
    st.clock.paused = False
    for _ in range(20):
        tick(st)
        if tribe.cabotage:
            break
    assert tribe.cabotage is True
    st2, _band2, player = _tribe_on_coast(is_player=True)
    player.progress["pirogue"] = almost
    st2.clock.paused = False
    for _ in range(20):
        tick(st2)
    assert player.cabotage is False


def test_persist_roundtrip_cabotage_flags(tmp_path):
    st, _band, tribe = _tribe_on_coast(cabotage=True)
    tribe.shore_seen = True
    tribe.coast_weeks = 4
    path = tmp_path / "kora.json"
    save_game(st, path, {"camera_x": 0, "camera_y": 0, "zoom": 1, "selected": 1})
    loaded, _view = load_game(path, st.world)
    lt = loaded.tribes[1]
    assert lt.cabotage is True
    assert lt.shore_seen is True
    assert lt.coast_weeks == 4
