"""Chefs, clans, emprise : un clan loin du chef se detache, puis part."""

from src.kora import chiefs, diplo, influence, orders, tech
from src.kora.clock import Clock
from src.kora.persist import load_game, save_game
from src.kora.sim import GameState, merge_bands, new_game, split_band
from src.kora.types import Band, Terrain, Tribe
from src.kora.world import make_filled_world, offset_to_axial


def _state(prestige=30, known=()):
    world = make_filled_world(120, 40, Terrain.PLAINE, wrap_x=True)
    tribe = Tribe(1, "Kora", prestige, True, knowledge=set(tech.START_KNOWLEDGE) | set(known), culture="joueur")
    heart = Band(1, 1, offset_to_axial(10, 20), 40, 200.0)
    far = Band(2, 1, offset_to_axial(70, 20), 40, 200.0)
    st = GameState(world=world, clock=Clock(), tribes={1: tribe}, bands={1: heart, 2: far}, next_band_id=3)
    world.fill_season(st.clock.season())
    chiefs.ensure(st)
    return st, heart, far


def test_every_band_gets_a_leader_and_the_tribe_a_chief():
    st, heart, far = _state()
    assert heart.leader is not None and far.leader is not None
    assert chiefs.chief_band(st, 1) is heart
    assert chiefs.is_chief_band(st, heart) and not chiefs.is_chief_band(st, far)


def test_a_far_clan_drifts_away_and_a_near_one_stays():
    st, heart, far = _state()
    near = Band(3, 1, offset_to_axial(12, 20), 30, 100.0)
    st.bands[3] = near
    chiefs.ensure(st)
    for _ in range(12):
        st.tick_count += 4
        chiefs.monthly(st)
    assert far.loyalty < near.loyalty
    labels = " ".join(label for label, _v in chiefs.loyalty_parts(st, far))
    assert "Loin du chef" in labels


def test_rites_and_chiefdom_widen_the_chief_reach():
    st, heart, far = _state()
    plain = chiefs.loyalty_target(st, far)
    st.tribes[1].knowledge.update(("rites", "conte", "chefferie"))
    assert chiefs.loyalty_target(st, far) > plain


def test_an_indocile_clan_no_longer_obeys_but_can_be_honored():
    st, heart, far = _state(prestige=30)
    far.loyalty = 30.0
    acts = orders.band_actions(st, far.id)
    assert acts["split"] == orders.INDOCILE and acts["camp"] == orders.INDOCILE
    assert acts["honor"] == ""
    assert chiefs.honor(st, far.id)
    assert far.loyalty == 50.0 and st.tribes[1].prestige == 25
    assert "Deja honore" in chiefs.can_honor(st, far.id)


def test_a_clan_that_leaves_founds_a_people_of_the_same_stock():
    st, heart, far = _state()
    new_tid = chiefs.secede(st, far.id)
    assert new_tid and new_tid != 1
    assert far.tribe_id == new_tid
    child = st.tribes[new_tid]
    assert child.origin == 1 and child.knowledge == st.tribes[1].knowledge
    assert chiefs.chief_band(st, new_tid) is far
    assert diplo.in_contact(st, 1, new_tid)
    assert any("Meme souche" in label for label, _v in diplo.reasons(st, 1, new_tid))


def test_a_clan_living_among_a_prestigious_people_may_join_them():
    st, heart, far = _state(prestige=20)
    st.tribes[2] = Tribe(2, "Hotes", 60, False, culture="vallee")
    host = Band(9, 2, far.position, 60, 200.0)
    st.bands[9] = host
    chiefs.ensure(st)
    for _ in range(8):
        st.tick_count += 1
        influence.note_presence(st)
    st.bands.pop(2)
    influence.update(st)
    st.bands[2] = far
    assert chiefs.secede(st, far.id) == 2
    assert far.tribe_id == 2


def test_when_the_chief_dies_the_heir_succeeds():
    st, heart, far = _state()
    chiefs.set_heir(st, far.id)
    heir_name = far.leader.name
    chiefs.leader_dies(st, heart, "de vieillesse")
    assert chiefs.chief_band(st, 1) is far
    assert chiefs.chief_of(st, 1).name == heir_name
    assert heart.leader is not None and heart.leader.name != heir_name


def test_split_gives_a_new_leader_and_merge_keeps_the_chief():
    st, heart, far = _state()
    chief_name = heart.leader.name
    nid = split_band(st, heart.id)
    assert st.bands[nid].leader is not None and st.bands[nid].leader.name != chief_name
    st.bands[nid].position = heart.position
    merge_bands(st, nid)
    keep = next(b for b in st.bands.values() if b.tribe_id == 1 and chiefs.is_chief_band(st, b))
    assert keep.leader.name == chief_name


def test_the_chief_can_move_to_another_band_on_the_same_hex():
    st, heart, far = _state()
    far.position = heart.position
    assert chiefs.can_move_chief(st, far.id) == ""
    name = heart.leader.name
    assert chiefs.move_chief(st, far.id)
    assert chiefs.chief_band(st, 1) is far and far.leader.name == name


def test_leaders_and_loyalty_are_saved(tmp_path):
    world = make_filled_world(30, 16, Terrain.PLAINE, wrap_x=True)
    st = new_game(world)
    band = st.bands[1]
    band.leader.traits = ("sage",)
    path = tmp_path / "kora.json"
    save_game(st, path, {})
    loaded, _ = load_game(path, world)
    lb = loaded.bands[1]
    assert lb.leader.name == band.leader.name and lb.leader.traits == ("sage",)
    assert loaded.tribes[1].chief_band == 1


def test_trait_text_is_drawn_from_the_numbers():
    lines = chiefs.trait_lines(chiefs.TRAITS["chasseur"])
    assert lines == ["Sa bande : +8 % de nourriture"]
    assert any("apprentissage" in line for line in chiefs.trait_lines(chiefs.TRAITS["sage"]))
