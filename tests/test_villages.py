"""Villages : une bande qui s'installe, des champs sur plusieurs cases."""

from src.kora import chiefs, orders, sites, tech, villages
from src.kora.clock import Clock
from src.kora.persist import load_game, save_game
from src.kora.sim import GameState, merge_bands, new_game, resolve_raids, set_goto, set_march_to_band, split_band, stock_max
from src.kora.types import Band, Season, Terrain, Tribe
from src.kora.world import make_filled_world, offset_to_axial


def _state(known=("huttes", "semis"), pop=60, stock=600.0, week=1):
    world = make_filled_world(60, 30, Terrain.VALLEE, wrap_x=True)
    tribe = Tribe(1, "Kora", 30, True, knowledge=set(tech.START_KNOWLEDGE) | set(known), culture="joueur")
    band = Band(1, 1, offset_to_axial(30, 15), pop, stock)
    st = GameState(world=world, clock=Clock(), tribes={1: tribe}, bands={1: band}, next_band_id=2)
    st.clock.week = week
    world.fill_season(st.clock.season())
    chiefs.ensure(st)
    return st, band


def _village(**kw):
    st, band = _state(**kw)
    assert sites.make_camp(st, 1) is not None
    site = villages.found(st, 1)
    assert site is not None
    return st, band, site


def _to_season(st, season):
    st.world.fill_season(season)
    villages.update(st)


def test_a_village_needs_sowing_knowledge_and_a_camp():
    st, band = _state(known=("huttes",))
    assert "Premieres semailles" in villages.found_block(st, 1)
    st.tribes[1].knowledge.add("semis")
    assert "campements" in villages.found_block(st, 1)
    sites.make_camp(st, 1)
    assert villages.found_block(st, 1) == ""


def test_founding_settles_the_band_on_its_camp():
    st, band, site = _village()
    assert band.village == site.id and site.kind == "village" and site.name
    assert site.data["fields"], "au printemps on seme tout de suite"
    before = band.position
    set_goto(st, 1, offset_to_axial(40, 15))
    assert not band.path and band.position == before
    assert orders.band_actions(st, 1)["deposit"] == orders.GRANARY
    assert stock_max(band, st) > stock_max(Band(9, 1, before, band.population, 0.0), st)


def test_fields_spread_over_several_hexes_and_follow_the_best_soil():
    st, band, site = _village(pop=110)
    fields = site.data["fields"]
    assert len(fields) == 5
    assert len({tuple(f) for f in fields}) == 5
    centre = st.world._index(site.hex)
    assert all(st.world.distance(site.hex, offset_to_axial(c, r)) <= villages.FIELD_RADIUS for c, r in fields)
    assert centre is not None
    # Un champ au sol epuise cede la place.
    worn = tuple(fields[0])
    site.data["soil"][f"{worn[0]},{worn[1]}"] = 0.2
    again = villages.choose_fields(st, site, band)
    assert list(worn) not in again


def test_harvest_in_autumn_keeps_seed_and_wears_the_soil():
    st, band, site = _village(pop=60)
    band.stock = 0.0
    fields = [tuple(f) for f in site.data["fields"]]
    _to_season(st, Season.ETE)
    _to_season(st, Season.AUTOMNE)
    assert site.data["last_harvest"] > 0
    assert band.stock > 0 and site.data["seed"] > 0
    assert all(site.data["soil"][f"{c},{r}"] < 1.0 for c, r in fields)


def test_no_seed_the_granary_sows_and_without_grain_no_fields():
    # Semences mangees : on seme le grain du grenier (4 semaines gardees).
    st, band, site = _village(pop=60)
    _to_season(st, Season.ETE)
    _to_season(st, Season.AUTOMNE)
    villages.eat_seed(st, band)
    band.stock = 30.0 * band.population
    _to_season(st, Season.HIVER)
    _to_season(st, Season.PRINTEMPS)
    assert site.data["fields"] and band.stock < 30.0 * band.population
    # Ni semences, ni grain, ni graines sauvages (carte sans ressources) :
    # les champs restent vides.
    st, band, site = _village(pop=60)
    _to_season(st, Season.ETE)
    _to_season(st, Season.AUTOMNE)
    villages.eat_seed(st, band)
    band.stock = 0.0
    site.data["seed"] = 0.0
    villages.sow(st, site, band)
    assert site.data["fields"] == []
    assert "Semailles" in " ".join(villages.lines(st, band)) or "semences 0" in " ".join(villages.lines(st, band))


def test_better_fields_with_neolithic_knowledge():
    plain, pb, ps = _village(pop=60)
    wise, wb, ws = _village(pop=60, known=("huttes", "semis", "champs"))
    assert villages.expected_harvest(wise, ws) > villages.expected_harvest(plain, ps) * 1.2


def test_a_village_does_not_flee_it_is_pillaged():
    st, band, site = _village(pop=40, stock=400.0)
    st.tribes[2] = Tribe(2, "Pillards", 60, False, knowledge=set(tech.START_KNOWLEDGE))
    st.bands[2] = Band(2, 2, band.position, 200, 0.0)
    chiefs.ensure(st)
    set_march_to_band(st, 2, 1)
    resolve_raids(st)
    assert band.position == site.hex and band.village == site.id
    assert site.data["burned"] and not band.retreating
    assert st.bands[2].stock > 0


def test_a_palisade_takes_time_and_food_then_defends():
    st, band, site = _village(known=("huttes", "semis", "palissade"), stock=900.0)
    assert villages.palisade_block(st, 1) == ""
    assert villages.build_palisade(st, 1)
    assert villages.palisade_state(site) == "building"
    for _ in range(villages.PALISADE_WEEKS):
        villages.update(st)
    assert villages.palisade_state(site) == "built"
    assert villages.defense_mult(st, band) == villages.PALISADE_DEFENSE


def test_a_band_leaves_the_village_and_can_come_back_to_settle():
    st, band, site = _village(pop=80)
    nid = split_band(st, 1)
    child = st.bands[nid]
    assert not child.village
    merge_bands(st, nid)
    assert nid not in st.bands and band.population == 80


def test_leaving_turns_the_village_back_into_a_camp():
    st, band, site = _village()
    assert villages.leave(st, 1)
    assert band.village == 0 and site.kind == "camp"


def test_villages_are_saved(tmp_path):
    world = make_filled_world(40, 20, Terrain.VALLEE, wrap_x=True)
    st = new_game(world)
    st.tribes[1].knowledge.update(("huttes", "semis"))
    st.bands[1].stock = 400.0
    sites.make_camp(st, 1)
    site = villages.found(st, 1)
    path = tmp_path / "kora.json"
    save_game(st, path, {})
    loaded, _ = load_game(path, world)
    band = loaded.bands[1]
    assert band.village == site.id
    assert loaded.sites[site.id].data["fields"] == site.data["fields"]
