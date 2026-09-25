"""Zone d'influence : ou l'on vit, pas ce que l'on possede."""

from src.kora import influence, tech
from src.kora.clock import Clock
from src.kora.sim import GameState, collect_food, defense_force, update_influence
from src.kora.types import Band, Terrain, Tribe
from src.kora.world import make_filled_world, offset_to_axial


def _state(known=(), size=(24, 16)):
    world = make_filled_world(size[0], size[1], Terrain.PLAINE)
    pos = offset_to_axial(size[0] // 2, size[1] // 2)
    band = Band(id=1, tribe_id=1, position=pos, population=40, stock=200)
    tribe = Tribe(1, "t", 20, True, knowledge=set(tech.START_KNOWLEDGE) | set(known))
    st = GameState(world=world, clock=Clock(), tribes={1: tribe}, bands={1: band})
    world.fill_season(st.clock.season())
    return st, band


def _live(st, weeks):
    for _ in range(weeks):
        st.tick_count += 1
        update_influence(st)


def test_influence_rises_then_falls():
    world = make_filled_world(12, 12, Terrain.PLAINE)
    pos = offset_to_axial(6, 6)
    b = Band(id=1, tribe_id=1, position=pos, population=50, stock=200)
    st = GameState(
        world=world,
        clock=Clock(),
        tribes={1: Tribe(1, "t", 20, True)},
        bands={1: b},
    )
    update_influence(st)
    up = world.influence(pos, 1)
    assert up > 0
    b.position = offset_to_axial(1, 1)
    for _ in range(30):
        update_influence(st)
    assert world.influence(pos, 1) < up


def test_influence_index_forgets_empty_cells():
    world = make_filled_world(8, 8, Terrain.PLAINE)
    h = offset_to_axial(2, 2)
    world.add_influence(h, 1, 0.0002)
    world.scale_all_influence(0.1)
    assert world.influence(h, 1) == 0.0
    assert len(world._influence_cells) == 0


def test_a_few_weeks_in_one_place_make_it_home_and_it_fades_in_about_a_year():
    st, band = _state()
    _live(st, 8)
    assert influence.in_zone(st.world, band.position, 1)
    assert influence.is_home(st.world, band.position, 1)
    here = band.position
    band.position = offset_to_axial(1, 1)
    peak = st.world.influence(here, 1)
    _live(st, 52)
    assert st.world.influence(here, 1) < peak * 0.6


def test_zone_radius_grows_with_landmarks_knowledge():
    base, b1 = _state()
    wise, b2 = _state(known=("huttes", "reperes"))
    _live(base, 12)
    _live(wise, 12)
    edge = offset_to_axial(12 + 3, 8)
    assert base.world.influence(edge, 1) == 0.0
    assert wise.world.influence(edge, 1) > 0.0


def test_two_peoples_in_the_same_place_share_it():
    st, band = _state()
    st.tribes[2] = Tribe(2, "u", 20, False)
    st.bands[2] = Band(id=2, tribe_id=2, position=band.position, population=40, stock=200)
    _live(st, 12)
    assert st.overlap.get((1, 2), 0) > 0
    assert "partagee" in " ".join(influence.zone_lines(st, band.position))


def test_landmarks_feed_more_at_home_only():
    plain, pb = _state(known=("huttes",))
    wise, wb = _state(known=("huttes", "reperes"))
    for st in (plain, wise):
        _live(st, 12)
        st.bands[1].stock = 0.0
    plain_gain = wise_gain = 0.0
    collect_food(plain)
    collect_food(wise)
    plain_gain, wise_gain = pb.stock, wb.stock
    assert wise_gain > plain_gain
    # Hors de la zone : pas de bonus.
    for st, b in ((plain, pb), (wise, wb)):
        b.position = offset_to_axial(2, 2)
        b.stock = 0.0
        collect_food(st)
    assert abs(wb.stock - pb.stock) < 1e-6


def test_lookouts_defend_better_at_home():
    st, band = _state(known=("guetteurs",))
    away = defense_force(st, band)
    _live(st, 12)
    assert defense_force(st, band) > away * 1.1
