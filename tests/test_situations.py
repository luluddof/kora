"""Les situations (situations.py) : crises et conjonctures. Chacune nait de
son contexte ; une crise resolue remet tout comme avant ; une conjoncture a
plusieurs peuples donne un prix au premier ; tout se sauvegarde ; en
multijoueur, une action est un ordre (commands)."""

from src.kora import commands, diplo, situations, tech, villages
from src.kora.persist import dumps_game, loads_game
from src.kora.sim import new_game, tick
from src.kora.gamestate import PLAYER_TRIBE_ID
from src.kora.situations import SPECS
from src.kora.types import Terrain
from src.kora.world import make_filled_world, offset_to_axial


def _world(terrain=Terrain.PLAINE):
    return make_filled_world(60, 30, terrain, wrap_x=True)


def _state(terrain=Terrain.PLAINE):
    st = new_game(_world(terrain))
    st.story = True
    return st


def _start(st, sid, center=None, radius=0, tids=(PLAYER_TRIBE_ID,), data=None):
    return situations._start(st, SPECS[sid], center, radius, list(tids or ()), data or {})


def _month(st):
    for _ in range(4):
        tick(st)
        st.clock.paused = False


def test_every_situation_with_its_effects_known_to_the_tech_tree():
    assert len(SPECS) == 16
    assert {s.kind for s in SPECS.values()} == {"crise", "conjoncture"}
    for sid, (name, effects) in situations.effect_specs().items():
        assert tech.situation_effect(sid) is not None, sid
        assert name
    for spec in SPECS.values():
        assert spec.name and spec.about and spec.actions, spec.id


def test_a_crisis_applies_its_stage_and_a_resolved_crisis_restores_everything():
    st = _state()
    me = st.tribes[PLAYER_TRIBE_ID]
    before = tech.bonuses(me)
    inst = _start(st, "disette")
    situations._sync_effects(st)
    hit = tech.bonuses(me)
    assert hit.growth < before.growth and hit.loyalty < before.loyalty
    inst.progress = 99.0
    for b in st.bands.values():
        if b.tribe_id == PLAYER_TRIBE_ID:
            b.stock = b.population * 10
    situations.monthly(st)
    assert inst.outcome == "resolue"
    after = tech.bonuses(me)
    assert after.growth == before.growth and after.loyalty == before.loyalty
    assert not me.situation_effects
    assert any("surmontée" in e.text for e in st.log.entries)


def test_a_failed_crisis_leaves_scars():
    st = _state()
    me = st.tribes[PLAYER_TRIBE_ID]
    me.prestige = 30
    inst = _start(st, "disette")
    inst.until = st.tick_count
    inst.progress = 10.0
    for b in st.bands.values():
        if b.tribe_id == PLAYER_TRIBE_ID:
            b.stock = 0.0
    situations.monthly(st)
    assert inst.outcome == "ratee"
    assert me.prestige < 30


def test_the_famine_is_born_from_a_real_famine():
    st = _state()
    band = next(b for b in st.bands.values() if b.tribe_id == PLAYER_TRIBE_ID)
    band.stock = 0.0
    st.tick_count = 300
    band.famine_tick = 296
    st.clock.week = 45
    assert any(PLAYER_TRIBE_ID in tids for _c, _r, tids, _d in SPECS["disette"].candidates(st))
    band.famine_tick = 200  # la faim est ancienne
    assert not any(PLAYER_TRIBE_ID in tids for _c, _r, tids, _d in SPECS["disette"].candidates(st))
    band.famine_tick = 296
    band.stock = band.population * 6
    assert not any(PLAYER_TRIBE_ID in tids for _c, _r, tids, _d in SPECS["disette"].candidates(st))


def test_exhausted_land_brings_the_game_crisis_and_leaving_cures_it():
    st = _state()
    band = next(b for b in st.bands.values() if b.tribe_id == PLAYER_TRIBE_ID)
    for h in st.world.hexes_in_radius(band.position, 6):
        st.world.set_exhaustion(h, 0.2)
    cands = SPECS["gibier"].candidates(st)
    assert any(PLAYER_TRIBE_ID in tids for _c, _r, tids, _d in cands)
    center, radius, tids, data = next(c for c in cands if PLAYER_TRIBE_ID in c[2])
    inst = situations._start(st, SPECS["gibier"], center, radius, tids, data)
    situations._sync_effects(st)
    assert tech.bonuses(st.tribes[PLAYER_TRIBE_ID]).food[Terrain.PLAINE] < 1.0
    band.position = offset_to_axial(40, 15)  # loin du pays epuise
    p0 = inst.progress
    SPECS["gibier"].month(st, inst)
    assert inst.progress > p0 + 20


def test_the_sickness_spreads_to_neighbours_of_any_people():
    st = _state()
    me = next(b for b in st.bands.values() if b.tribe_id == PLAYER_TRIBE_ID)
    other = next(b for b in st.bands.values() if b.tribe_id == 3)
    other.position = me.position
    inst = _start(st, "mal", me.position, 8, [PLAYER_TRIBE_ID])
    for _ in range(6):
        SPECS["mal"].month(st, inst)
        st.tick_count += 4
    assert 3 in inst.participants
    pop = me.population
    inst.stage = 1
    SPECS["mal"].month(st, inst)
    assert me.population < pop


def test_isolating_the_sick_blocks_merging_for_a_while():
    from src.kora import orders

    st = _state()
    band = next(b for b in st.bands.values() if b.tribe_id == PLAYER_TRIBE_ID)
    band.population = 80
    from src.kora.sim import split_band

    split_band(st, band.id)
    inst = _start(st, "mal", band.position, 8)
    assert situations.act(st, inst.uid, PLAYER_TRIBE_ID, "isoler") == "Isoler les malades : fait."
    assert "isolés" in orders.band_actions(st, band.id)["merge"]
    assert "semaines" in situations.action_block(st, inst, PLAYER_TRIBE_ID, "isoler")


def test_actions_cost_and_are_orders_of_their_own_player():
    st = new_game(_world(), others={2: {"name": "Tahu"}})
    st.story = True
    me = st.tribes[PLAYER_TRIBE_ID]
    me.prestige = 5
    inst = _start(st, "mal", next(b.position for b in st.bands.values() if b.tribe_id == 1), 8)
    assert "prestige" in situations.action_block(st, inst, PLAYER_TRIBE_ID, "rites")
    me.prestige = 20
    res = commands.apply(st, commands.make(1, "situation", inst.uid, "rites"))
    assert res["msg"].endswith("fait.") and me.prestige == 12
    assert "pas" in commands.apply(st, commands.make(2, "situation", inst.uid, "rites"))["msg"]
    assert commands.apply(st, commands.make(1, "situation", 999, "rites"))["msg"] == "Cette situation est finie"


def test_a_contest_crowns_its_winner_only_when_several_peoples_are_in():
    st = _state()
    before = tech.bonuses(st.tribes[1]).food.get(Terrain.PLAINE, 1.0)
    inst = _start(st, "passage", next(b.position for b in st.bands.values() if b.tribe_id == 1), 6, [1, 2], {"dq": 1, "dr": 0})
    inst.participants[1]["score"] = 300.0
    inst.participants[2]["score"] = 100.0
    inst.until = st.tick_count
    situations.monthly(st)
    assert inst.outcome == "gagnee" and inst.winner == 1
    assert any(e[0] == "sit:passage:prix" and e[1] > st.tick_count for e in st.tribes[1].situation_effects)
    assert tech.bonuses(st.tribes[1]).food[Terrain.PLAINE] > before
    assert not st.tribes[2].situation_effects, "le second n'a rien"
    alone = _start(st, "rassemblement", None, 0, [3])
    alone.participants[3]["score"] = 50.0
    alone.until = st.tick_count
    situations.monthly(st)
    assert alone.outcome == "finie" and alone.winner == 0


def test_the_hunting_passage_moves_and_shares_a_fixed_meat():
    st = _state()
    me = next(b for b in st.bands.values() if b.tribe_id == 1)
    other = next(b for b in st.bands.values() if b.tribe_id == 2)
    other.position = me.position
    inst = _start(st, "passage", me.position, 6, [1, 2], {"dq": 1, "dr": 0})
    s1, s2 = me.stock, other.stock
    c0 = inst.center
    SPECS["passage"].month(st, inst)
    gained = (me.stock - s1) + (other.stock - s2)
    assert abs(gained - situations.PASSAGE_MEAT) < 1e-6
    assert inst.center != c0
    assert inst.participants[1]["score"] > 0 and inst.participants[2]["score"] > 0
    assert diplo.relation(st, 1, 2) < diplo.relation(new_game(_world()), 1, 2) + 1e-9


def test_village_crises_hit_the_harvest_and_travel_by_trade_routes():
    st = _state(Terrain.VALLEE)
    from src.kora import sites

    for tid in (1, 2):
        for t in tech.TECHS:
            tech.grant(st.tribes[tid], t)
        band = next(b for b in st.bands.values() if b.tribe_id == tid)
        band.population, band.stock = 130, 3000.0
        sites.make_camp(st, band.id)
        villages.found(st, band.id)
    tech.invalidate()
    inst = _start(st, "rouille", next(s.hex for s in st.sites.values() if s.kind == "village" and s.tribe_id == 1), 10)
    situations._sync_effects(st)
    assert tech.bonuses(st.tribes[1]).field_yield < tech.bonuses(st.tribes[2]).field_yield
    diplo.make_contact(st, 1, 2)
    diplo.add_pact(st, 1, 2, "commerce")
    from src.kora import goods

    route = diplo.TradeRoute(1, 2, goods.GOODS[0], 1, 1, 0)
    route.units = 3.0
    st.diplo.routes.append(route)
    beasts = _start(st, "mal_betes", next(s.hex for s in st.sites.values() if s.kind == "village" and s.tribe_id == 1), 6)
    for k in range(40):
        st.tick_count += 4
        SPECS["mal_betes"].month(st, beasts)
        if 2 in beasts.participants:
            break
    assert 2 in beasts.participants, "le mal voyage avec les porteurs"
    situations.act(st, beasts.uid, 1, "routes")
    assert not goods.routes_of(st, 1)


def test_the_great_winter_takes_half_the_world():
    st = _state()
    inst = _start(st, "grand_hiver", None, -1, None, {"moitie": "nord"})
    rows = {}
    from src.kora.world import axial_to_offset

    for tid in st.tribes:
        bands = [b for b in st.bands.values() if b.tribe_id == tid]
        rows[tid] = [axial_to_offset(b.position)[1] for b in bands]
    for tid in inst.participants:
        assert any(r < st.world.height // 2 for r in rows[tid])
    for tid in st.tribes:
        if tid not in inst.participants and rows[tid]:
            assert all(r >= st.world.height // 2 for r in rows[tid])


def test_situations_survive_save_and_load_and_the_tick_rollback():
    st = _state()
    inst = _start(st, "passage", next(b.position for b in st.bands.values() if b.tribe_id == 1), 6, [1, 2], {"dq": 1, "dr": 0})
    inst.participants[1]["score"] = 42.0
    situations.grant_effect(st.tribes[1], "sit:passage:prix", st.tick_count + 100)
    loaded, _view = loads_game(dumps_game(st), _world())
    got = situations.find(loaded, inst.uid)
    assert got is not None and got.participants[1]["score"] == 42.0 and got.data["dq"] == 1
    assert loaded.tribes[1].situation_effects == st.tribes[1].situation_effects
    assert loaded.next_situation_uid == st.next_situation_uid
    from src.kora.sim import _restore, snapshot

    snap = snapshot(st)
    inst.participants[1]["score"] = 0.0
    _restore(st, snap)
    assert situations.find(st, inst.uid).participants[1]["score"] == 42.0


def test_situation_randomness_does_not_touch_the_story():
    st = _state()
    state = st.story_rng.getstate()
    for _ in range(12):
        situations.monthly(st)
        st.tick_count += 4
    assert st.story_rng.getstate() == state


def test_the_ai_takes_its_actions():
    st = _state()
    st.tribes[3].prestige = 50
    inst = _start(st, "mal", next(b.position for b in st.bands.values() if b.tribe_id == 3), 8, [3])
    for _ in range(12):
        situations._ai(st, inst)
        st.tick_count += 4
    assert inst.participants[3]["acted"], "l'IA a agi"
