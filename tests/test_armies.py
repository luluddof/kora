"""Troupes : levees au village, elles se battent, rentrent, desertent."""

from src.kora import chiefs, orders, sites, tech, villages
from src.kora.ai import decide_ai
from src.kora.clock import Clock
from src.kora.persist import load_game, save_game
from src.kora.sim import (
    GameState,
    can_split,
    merge_bands,
    new_game,
    resolve_joins,
    set_march_to_band,
    tribe_band_count,
    update_population,
)
from src.kora.types import Band, Terrain, Tribe
from src.kora.world import make_filled_world, offset_to_axial


def _village(pop=90, stock=3000.0, known=("huttes", "semis")):
    world = make_filled_world(60, 30, Terrain.VALLEE, wrap_x=True)
    tribe = Tribe(1, "Kora", 30, True, knowledge=set(tech.START_KNOWLEDGE) | set(known), culture="joueur")
    st = GameState(world=world, clock=Clock(), tribes={1: tribe}, bands={1: Band(1, 1, offset_to_axial(30, 15), pop, stock)}, next_band_id=2)
    world.fill_season(st.clock.season())
    chiefs.ensure(st)
    sites.make_camp(st, 1)
    site = villages.found(st, 1)
    return st, st.bands[1], site


def test_a_village_raises_a_troop_from_its_people():
    st, village, site = _village(pop=90)
    before = tribe_band_count(st, 1)
    from src.kora import population

    # Seule une part des hommes valides part : ni enfants, ni femmes, ni anciens.
    n = villages.levy_size(village, villages.LEVY_SHARE["troupe"])
    assert 0 < n < population.fit_men(village) < 30
    army = villages.raise_army(st, 1, villages.LEVY_SHARE["troupe"])
    assert army is not None and army.kind == "armee" and army.home == site.id
    assert army.population == n and village.population == 90 - n
    assert population.counts(village)["enfants"] == population.counts(Band(9, 1, site.hex, 90, 0.0))["enfants"]
    assert army.stock == villages.ARMY_SUPPLY_WEEKS * n
    assert army.leader is not None and army.loyalty == 100.0
    # Une troupe n'est pas un clan : elle ne compte pas dans la limite.
    assert tribe_band_count(st, 1) == before
    assert not can_split(st, army.id)
    assert "guerriers" in " ".join(villages.army_lines(st, army))


def test_raising_needs_people_and_one_troop_at_a_time():
    st, village, site = _village(pop=30)
    assert "habitants" in villages.army_block(st, 1)
    st2, v2, s2 = _village(pop=150)
    assert villages.raise_army(st2, 1, villages.LEVY_SHARE["poignee"]) is not None
    assert villages.raise_army(st2, 1, villages.LEVY_SHARE["poignee"]) is not None
    assert "compagnies" in villages.army_block(st2, 1, villages.LEVY_SHARE["poignee"])
    s2.data["buildings"].append("guerriers")
    assert villages.army_block(st2, 1, villages.LEVY_SHARE["poignee"]) == ""


def test_a_nomad_band_cannot_raise_a_troop():
    st = new_game(make_filled_world(40, 24, Terrain.PLAINE, wrap_x=True))
    assert "village" in orders.band_actions(st, 1)["army"]


def test_the_troop_comes_home_and_its_warriors_return():
    st, village, site = _village(pop=90)
    village.loyalty = 77.0
    army = villages.raise_army(st, 1)
    assert orders.band_actions(st, army.id)["merge"] == ""
    assert orders.labels(st, army.id)["merge"] == "Rentrer [F]"
    sel, msg = orders.perform(st, army.id, "merge")
    assert msg == "" and sel == 1
    assert army.id not in st.bands and village.population == 90


def test_a_far_troop_deserts_after_a_while():
    st, village, site = _village(pop=90)
    army = villages.raise_army(st, 1)
    army.position = offset_to_axial(45, 15)
    assert orders.band_actions(st, army.id)["army"] == ""
    assert "Rentrez" in villages.disband_block(st, army.id)
    # Les desertions se comptent toutes les 4 semaines.
    st.tick_count = (villages.ARMY_TERM // 4 + 2) * 4
    before = army.population
    villages.update(st)
    assert army.population < before and village.population > 60


def test_a_troop_does_not_grow_and_has_no_families():
    st, village, site = _village(pop=90)
    army = villages.raise_army(st, 1)
    n = army.population
    army.growth_acc = 0.99
    update_population(st)
    assert army.population == n


def test_clans_and_troops_do_not_mix_by_accident():
    st, village, site = _village(pop=90)
    army = villages.raise_army(st, 1)
    n = army.population
    army.position = offset_to_axial(40, 15)
    clan = Band(40, 1, army.position, 20, 0.0)
    st.bands[40] = clan
    merge_bands(st, 40)
    assert army.id in st.bands and army.population == n and 40 in st.bands
    set_march_to_band(st, 40, army.id)
    clan.position = army.position
    resolve_joins(st)
    assert army.population == n and 40 in st.bands
    # Une troupe qui rejoint son village y redevient villageoise.
    army.position = site.hex
    set_march_to_band(st, army.id, 1)
    resolve_joins(st)
    assert army.id not in st.bands and village.population == 90


def test_a_troop_without_village_becomes_a_clan():
    st, village, site = _village(pop=90)
    army = villages.raise_army(st, 1)
    villages.leave(st, 1)
    villages.update(st)
    assert army.kind == "" and army.home == 0
    from src.kora import population

    assert population.counts(army)["enfants"] == 0, "un clan d'hommes"


def test_a_troop_away_leaves_the_harvest_short_of_hands():
    st, village, site = _village(pop=100)
    # Beaucoup de champs : il faut tous les bras.
    site.data["fields"] = [[c, 0] for c in range(6)]
    full = villages.field_hands_mult(site, village)
    villages.raise_army(st, 1, villages.LEVY_SHARE["masse"])
    assert villages.field_hands_mult(site, village) < full


def test_troops_are_saved(tmp_path):
    world = make_filled_world(40, 20, Terrain.VALLEE, wrap_x=True)
    st = new_game(world)
    st.tribes[1].knowledge.update(("huttes", "semis"))
    st.bands[1].population = 90
    st.bands[1].stock = 2000.0
    sites.make_camp(st, 1)
    site = villages.found(st, 1)
    army = villages.raise_army(st, 1)
    path = tmp_path / "kora.json"
    save_game(st, path, {})
    loaded, _ = load_game(path, world)
    back = loaded.bands[army.id]
    assert back.kind == "armee" and back.home == site.id and back.raised == army.raised


def test_an_ai_village_raises_a_troop_when_threatened():
    world = make_filled_world(60, 30, Terrain.VALLEE, wrap_x=True)
    st = GameState(
        world=world,
        clock=Clock(),
        tribes={
            1: Tribe(1, "Kora", 30, True, knowledge=set(tech.START_KNOWLEDGE)),
            2: Tribe(2, "Vallée", 30, False, knowledge=set(tech.START_KNOWLEDGE) | {"huttes", "semis"}, culture="vallee"),
            3: Tribe(3, "Steppe", 30, False, knowledge=set(tech.START_KNOWLEDGE), culture="steppe"),
        },
        bands={
            1: Band(1, 1, offset_to_axial(2, 2), 20, 100.0),
            2: Band(2, 2, offset_to_axial(30, 15), 100, 3000.0),
        },
        next_band_id=10,
    )
    world.fill_season(st.clock.season())
    chiefs.ensure(st)
    sites.make_camp(st, 2)
    site = villages.found(st, 2, oath=villages.ai_oath(st, 2))
    assert villages.oath_of(site) == "champs"
    st.bands[3] = Band(3, 3, offset_to_axial(34, 15), 120, 500.0)
    chiefs.ensure(st)
    for week in range(8):
        st.tick_count = week
        decide_ai(st)
    assert villages.armies_of(st, site)


def test_a_dissolved_troop_never_becomes_a_nomad_clan_of_a_settled_people():
    """Un peuple sedentaire ne refait pas de tribu : une troupe dissoute loin,
    sans chemin praticable, rentre quand meme au village (par d'autres voies)."""
    from src.kora import population, sim

    st, village, site = _village(pop=120)
    army = villages.raise_army(st, 1)
    n = army.population
    army.position = offset_to_axial(55, 15)
    real = sim.set_goto
    sim.set_goto = lambda state, bid, goal, **kw: setattr(state.bands[bid], "path", [])
    try:
        assert villages.dissolve(st, army.id)
    finally:
        sim.set_goto = real
    assert army.id not in st.bands, "la troupe a rejoint son village"
    assert village.population == 120 and not any(b.kind == "" and not b.village and b.tribe_id == 1 for b in st.bands.values())
    assert population.counts(village)["hommes"] >= n


def test_a_settled_people_holds_a_single_village():
    """En cet age, un chef ne tient qu'un village : un second ne se fonde pas."""
    st, village, site = _village(pop=120)
    for t in tech.TECHS:
        tech.grant(st.tribes[1], t)
    tech.invalidate()
    st.bands[7] = Band(7, 1, offset_to_axial(45, 15), 100, 3000.0)
    sites.make_camp(st, 7)
    assert "un chef n'en tient qu'un" in villages.found_block(st, 7)
    assert villages.found(st, 7) is None
