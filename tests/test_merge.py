"""Fusion des bandes : qui mene, les anciens, l'attachement, la soudure."""

from src.kora import battle, chiefs, orders, tech
from src.kora.clock import Clock
from src.kora.persist import load_game, save_game
from src.kora.sim import GameState, merge_bands, new_game, split_band
from src.kora.types import Band, Person, Terrain, Tribe
from src.kora.world import make_filled_world, offset_to_axial


def _state():
    world = make_filled_world(40, 24, Terrain.PLAINE, wrap_x=True)
    tribe = Tribe(1, "Kora", 40, True, knowledge=set(tech.START_KNOWLEDGE))
    pos = offset_to_axial(20, 12)
    st = GameState(
        world=world,
        clock=Clock(),
        tribes={1: tribe},
        bands={
            1: Band(1, 1, pos, 40, 100.0),
            2: Band(2, 1, pos, 30, 100.0, loyalty=50.0),
            3: Band(3, 1, pos, 10, 100.0, loyalty=90.0),
        },
        next_band_id=10,
    )
    chiefs.ensure(st)
    st.tribes[1].chief_band = 5  # personne n'est chef de ces trois clans
    return st


def test_the_chosen_band_leads_and_the_others_become_elders():
    st = _state()
    lead = st.bands[2].leader.name
    others = {st.bands[1].leader.pid, st.bands[3].leader.pid}
    merge_bands(st, 2)
    band = st.bands[2]
    assert band.leader.name == lead and band.population == 80
    assert {p.pid for p in band.notables} == others
    assert any("anciens" in e.text for e in st.log.entries)
    assert "anciens" in chiefs.band_lines_extra(st, band)[1]


def test_loyalty_is_weighted_by_people():
    st = _state()
    st.bands[1].loyalty = 40.0
    merge_bands(st, 1)
    # (40 x 40 + 50 x 30 + 90 x 10) / 80
    assert abs(st.bands[1].loyalty - 50.0) < 0.01


def test_a_merged_group_is_not_welded_at_once():
    st = _state()
    merge_bands(st, 1)
    band = st.bands[1]
    assert "reuni" in orders.band_actions(st, 1)["split"]
    morale, parts = battle.start_morale(st, band, True, band.position)
    assert any(label == "Pas encore soudes" for label, _v in parts)
    st.tick_count = band.welded_until
    assert orders.band_actions(st, 1)["split"] == ""


def test_an_elder_leads_the_next_split_and_succeeds_a_dead_chief():
    st = _state()
    merge_bands(st, 1)
    band = st.bands[1]
    elders = [p.pid for p in band.notables]
    st.tick_count = band.welded_until
    nid = split_band(st, 1)
    assert st.bands[nid].leader.pid == elders[0]
    old = band.leader
    chiefs.leader_dies(st, band, "de maladie")
    assert band.leader.pid == elders[1] and band.leader is not old


def test_the_clan_can_be_given_to_an_elder():
    st = _state()
    merge_bands(st, 1)
    band = st.bands[1]
    was = band.leader
    elder = band.notables[0]
    assert chiefs.can_promote(st, 1, elder.pid) == ""
    assert chiefs.promote(st, 1, elder.pid)
    assert band.leader is elder and was in band.notables


def test_an_ambitious_elder_troubles_the_clan():
    st = _state()
    band = st.bands[1]
    chiefs.add_notable(band, Person(99, "Orgo", 1, ("ambitieux",), 50))
    assert any("ambitieux" in label for label, _v in chiefs.loyalty_parts(st, band))


def test_elders_are_kept_to_the_most_renowned_three():
    band = Band(1, 1, offset_to_axial(1, 1), 10, 0.0)
    for i in range(5):
        chiefs.add_notable(band, Person(i, f"P{i}", 1, (), i * 10))
    assert [p.renown for p in band.notables] == [40, 30, 20]


def test_elders_are_saved(tmp_path):
    st = new_game(make_filled_world(40, 24, Terrain.PLAINE, wrap_x=True))
    band = st.bands[1]
    chiefs.add_notable(band, Person(77, "Ana", 1, ("sage",), 12))
    band.welded_until = 9
    path = tmp_path / "kora.json"
    save_game(st, path, {})
    loaded, _ = load_game(path, st.world)
    back = loaded.bands[1]
    assert back.notables[0].name == "Ana" and back.welded_until == 9


def _spread():
    world = make_filled_world(40, 24, Terrain.PLAINE, wrap_x=True)
    tribe = Tribe(1, "Kora", 40, True, knowledge=set(tech.START_KNOWLEDGE))
    st = GameState(
        world=world,
        clock=Clock(),
        tribes={1: tribe},
        bands={
            1: Band(1, 1, offset_to_axial(20, 12), 40, 100.0),
            2: Band(2, 1, offset_to_axial(22, 12), 20, 100.0),
            3: Band(3, 1, offset_to_axial(24, 12), 20, 100.0),
            4: Band(4, 1, offset_to_axial(35, 12), 20, 100.0),
        },
        next_band_id=10,
    )
    chiefs.ensure(st)
    return st


def test_close_bands_merge_without_sharing_a_hex_and_nearby_ones_walk_over():
    from src.kora.sim import apply_movement, resolve_joins

    st = _spread()
    assert orders.band_actions(st, 1)["merge"] == ""
    merge_bands(st, 1)
    band = st.bands[1]
    assert 2 not in st.bands and band.population == 60
    walker = st.bands[3]
    assert walker.order.target_band_id == 1
    assert 4 in st.bands and st.bands[4].order.target_band_id != 1
    for _ in range(3):
        apply_movement(st)
        resolve_joins(st)
        if 3 not in st.bands:
            break
    assert 3 not in st.bands and band.population == 80


def test_a_band_far_from_all_others_has_nothing_to_merge():
    st = _spread()
    assert "5 cases" in orders.band_actions(st, 4)["merge"]


def test_the_chief_does_not_leave_his_people():
    st = _state()
    heart = chiefs.chief_band(st, 1) or st.bands[1]
    st.tribes[1].chief_band = heart.id
    assert chiefs.secede(st, heart.id) == 0 and heart.tribe_id == 1
