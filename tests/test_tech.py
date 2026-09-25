"""Savoirs : l'arbre tient debout, chaque effet affiche agit vraiment."""

from src.kora import tech
from src.kora.clock import Clock
from src.kora.path import astar
from src.kora.persist import load_game, save_game
from src.kora.sim import (
    GameState,
    _restore,
    band_force,
    can_split,
    collect_food,
    new_game,
    side_force,
    snapshot,
    split_band,
    stock_max,
    update_exhaustion,
    update_population,
    update_prestige,
)
from src.kora.types import Band, Season, Terrain, Tribe
from src.kora.vision import recompute_vision
from src.kora.world import food_production, make_filled_world, offset_to_axial


def _tribe(known=(), is_player=True, tid=1):
    return Tribe(tid, "t", 20, is_player, knowledge=set(tech.START_KNOWLEDGE) | set(known))


def _state(terrain=Terrain.PLAINE, known=(), pop=40, stock=100.0, week=1, size=(20, 14)):
    world = make_filled_world(size[0], size[1], terrain)
    clock = Clock()
    clock.week = week
    world.fill_season(clock.season())
    band = Band(1, 1, offset_to_axial(size[0] // 2, size[1] // 2), pop, stock)
    st = GameState(world=world, clock=clock, tribes={1: _tribe(known)}, bands={1: band})
    return st, band


# --- l'arbre ---------------------------------------------------------------


def test_the_tree_is_sound():
    names = set()
    for t in tech.TECHS.values():
        assert t.name not in names
        names.add(t.name)
        assert t.about
        assert tech.effect_lines(t), f"{t.id} ne dit pas ce qu'il fait"
        assert 0 <= t.branch < len(tech.branches_of(t))
        for pid in t.prereqs:
            assert pid in tech.TECHS
            assert tech.TECHS[pid].tier < t.tier
        if t.tier == 0:
            assert not t.prereqs and t.id in tech.START_KNOWLEDGE
        else:
            assert t.prereqs and t.conds
    for tier in range(1, 4):
        assert sum(1 for t in tech.TECHS.values() if t.tier == tier) >= 4
    places = [(t.tier, t.branch) for t in tech.TECHS.values()]
    assert len(places) == len(set(places))


def test_everyone_starts_with_fire_and_tools_ai_with_its_speciality():
    st = new_game(make_filled_world(40, 24, Terrain.VALLEE, wrap_x=True))
    assert st.tribes[1].knowledge == {"feu", "outils"}
    assert {"epieu", "troupeau"} <= st.tribes[2].knowledge and st.tribes[2].troupeau
    assert "cueillette" in st.tribes[3].knowledge
    assert {"peche", "pirogue"} <= st.tribes[4].knowledge and st.tribes[4].cabotage
    for tribe in st.tribes.values():
        assert tribe.learning is None


def test_effect_text_is_drawn_from_the_numbers():
    lines = tech.effect_lines(tech.TECHS["epieu"])
    assert any("Force au combat : +10 %" in line for line in lines)
    assert any("Plaine et steppe : +10 % de nourriture" in line for line in lines)
    portage = " ".join(tech.effect_lines(tech.TECHS["portage"]))
    assert "foret : 4 cases/semaine (au lieu de 3)" in portage
    assert "Deja pris en compte" in tech.effect_lines(tech.TECHS["feu"])[0]


# --- disponible, apprentissage -------------------------------------------------


def test_status_goes_locked_waiting_available_learning_known():
    st, band = _state()
    tribe = st.tribes[1]
    assert tech.status(st, 1, "arc") == "verrouille"
    assert tech.status(st, 1, "epieu") == "attente"  # jamais vecu la plaine
    tribe.practice["plaine"] = 6
    assert tech.status(st, 1, "epieu") == "disponible"
    assert tech.choose(st, 1, "epieu")
    assert tech.status(st, 1, "epieu") == "en_cours"
    for _ in range(40):
        tech.update_learning(st)
    assert tech.status(st, 1, "epieu") == "connu"
    assert tech.status(st, 1, "arc") == "attente"


def test_cannot_choose_what_is_not_available():
    st, _band = _state()
    assert not tech.choose(st, 1, "arc")
    assert not tech.choose(st, 1, "inconnu")
    assert st.tribes[1].learning is None


def test_more_people_learn_faster_and_progress_is_kept_when_switching():
    small, _ = _state(pop=20)
    big, _ = _state(pop=200)
    assert tech.learn_rate(big, 1) > tech.learn_rate(small, 1)
    st, _band = _state(pop=40)
    tribe = st.tribes[1]
    tribe.practice.update({"plaine": 6, "foret": 8, "hivers": 1})
    tech.choose(st, 1, "epieu")
    tech.update_learning(st)
    tech.update_learning(st)
    kept = tribe.progress["epieu"]
    tech.choose(st, 1, "fumage")
    tech.update_learning(st)
    assert tribe.progress["epieu"] == kept
    assert tribe.progress["fumage"] > 0


def test_practice_counts_terrains_and_winters():
    st, band = _state(terrain=Terrain.FORET, week=45)
    st.world.fill_season(Season.HIVER)
    tech.update_practice(st)
    tech.update_practice(st)
    assert st.tribes[1].practice["foret"] == 2
    assert st.tribes[1].practice["hiver"] == 2
    st.clock.week = 52
    st.clock.advance_week()
    update_prestige(st)
    assert st.tribes[1].practice["hivers"] == 1


# --- chaque effet --------------------------------------------------------------


def test_food_knowledge_raises_what_the_band_gathers():
    for known, terrain in ((("cueillette",), Terrain.FORET), (("semis",), Terrain.VALLEE), (("epieu",), Terrain.PLAINE)):
        plain, band = _state(terrain=terrain, pop=20, stock=0)
        wise, wise_band = _state(terrain=terrain, known=known, pop=20, stock=0)
        collect_food(plain)
        collect_food(wise)
        assert wise_band.stock > band.stock, known


def test_fishing_makes_shore_water_feed():
    world = make_filled_world(12, 12, Terrain.EAU)
    for col in range(12):
        world._terrains[6][col] = Terrain.COTE
    water = offset_to_axial(5, 5)
    base = food_production(world, water, Season.ETE, bonus=tech.bonuses_of(("feu", "outils")))
    fished = food_production(world, water, Season.ETE, bonus=tech.bonuses_of(("peche",)))
    assert base == 0.0
    assert fished > 0.0
    deep = offset_to_axial(5, 1)
    assert food_production(world, deep, Season.ETE, bonus=tech.bonuses_of(("peche",))) == 0.0


def test_smoking_and_pottery_raise_the_stock_limit():
    st, band = _state()
    base = stock_max(band, st)
    st.tribes[1].knowledge.add("fumage")
    assert stock_max(band, st) == base + 4 * band.population
    st.tribes[1].knowledge.add("poterie")
    assert stock_max(band, st) == base + 10 * band.population


def test_hides_cut_winter_famine_and_help_on_hills():
    bare, bare_band = _state(terrain=Terrain.COLLINE, pop=40, stock=0, week=45)
    warm, warm_band = _state(terrain=Terrain.COLLINE, known=("peaux",), pop=40, stock=0, week=45)
    for st in (bare, warm):
        st.world.fill_season(Season.HIVER)
    collect_food(bare)
    collect_food(warm)
    assert warm_band.population > bare_band.population
    h = bare_band.position
    assert food_production(warm.world, h, Season.HIVER, bonus=tech.bonuses_of(("peaux",))) > food_production(
        bare.world, h, Season.HIVER
    )


def test_bows_and_spears_make_bands_stronger():
    st, band = _state()
    weak = band_force(st, band)
    st.tribes[1].knowledge.update(("epieu", "arc"))
    assert band_force(st, band) > weak * 1.25


def test_snowshoes_make_forest_walks_shorter():
    world = make_filled_world(30, 8, Terrain.FORET)
    start, goal = offset_to_axial(2, 4), offset_to_axial(20, 4)
    base = tech.move_costs(_tribe())
    quick = tech.move_costs(_tribe(("portage",)))
    assert quick[Terrain.FORET] < base[Terrain.FORET]
    from src.kora.path import travel_weeks

    slow_path = astar(world, start, goal, costs=base)
    fast_path = astar(world, start, goal, costs=quick)
    assert travel_weeks(world, start, fast_path, costs=quick) < travel_weeks(world, start, slow_path, costs=base)


def test_lookouts_see_farther_and_help_from_farther():
    st, band = _state(size=(60, 40))
    recompute_vision(st)
    seen = len(st.vision.visible)
    st.tribes[1].knowledge.update(("guetteurs",))
    recompute_vision(st)
    assert len(st.vision.visible) > seen
    ally = Band(2, 1, offset_to_axial(30 + 3, 20), 30, 0)
    st.bands[2] = ally
    band.position = offset_to_axial(30, 20)
    with_help = side_force(st, band)
    st.tribes[1].knowledge.discard("guetteurs")
    assert side_force(st, band) < with_help


def test_sowing_lets_camp_land_recover_faster():
    st, band = _state(terrain=Terrain.VALLEE)
    far = offset_to_axial(2, 2)
    near = band.position
    for h in (far, near):
        st.world.set_exhaustion(h, 0.5)
    st.last_pressure = {}
    st.tribes[1].knowledge.add("semis")
    update_exhaustion(st)
    assert st.world.exhaustion(near) > st.world.exhaustion(far)


def test_tales_raise_births_and_winter_prestige():
    st, band = _state(known=("conte",), pop=100, stock=1000)
    base, base_band = _state(pop=100, stock=1000)
    for _ in range(12):
        update_population(st)
        update_population(base)
    assert band.population > base_band.population
    st.clock.week = 52
    st.clock.advance_week()
    update_prestige(st)
    assert st.tribes[1].prestige == 26


def test_chiefdom_allows_more_bands():
    st, band = _state(pop=2000)
    while can_split(st, max(st.bands.values(), key=lambda b: b.population).id):
        split_band(st, max(st.bands.values(), key=lambda b: b.population).id)
    assert len(st.bands) == 8
    st.tribes[1].knowledge.add("chefferie")
    assert can_split(st, max(st.bands.values(), key=lambda b: b.population).id)


# --- sauvegarde, repli d'un tick rate ------------------------------------------


def test_knowledge_is_saved_and_old_saves_get_fire_and_tools(tmp_path):
    world = make_filled_world(30, 16, Terrain.PLAINE, wrap_x=True)
    st = new_game(world)
    tribe = st.tribes[1]
    tribe.knowledge.add("epieu")
    tribe.learning = "fumage"
    tribe.progress["fumage"] = 7.5
    tribe.practice["plaine"] = 12
    path = tmp_path / "kora.json"
    save_game(st, path, {})
    loaded, _ = load_game(path, world)
    lt = loaded.tribes[1]
    assert lt.knowledge == {"feu", "outils", "epieu"}
    assert lt.learning == "fumage" and lt.progress["fumage"] == 7.5 and lt.practice["plaine"] == 12
    import json

    data = json.loads(path.read_text(encoding="utf-8"))
    for raw in data["tribes"]:
        for key in ("knowledge", "learning", "progress", "practice"):
            raw.pop(key)
    path.write_text(json.dumps(data), encoding="utf-8")
    old, _ = load_game(path, world)
    assert old.tribes[1].knowledge == {"feu", "outils"}
    assert {"peche", "pirogue"} <= old.tribes[4].knowledge


def test_a_failed_tick_rolls_knowledge_back():
    st, _band = _state()
    saved = snapshot(st)
    st.tribes[1].knowledge.add("arc")
    st.tribes[1].progress["arc"] = 3.0
    st.tribes[1].practice["foret"] = 9
    _restore(st, saved)
    assert "arc" not in st.tribes[1].knowledge
    assert "arc" not in st.tribes[1].progress
    assert "foret" not in st.tribes[1].practice
