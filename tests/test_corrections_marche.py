"""Les corrections de la marche et du monde (revue du 2026-11-27) : l'ordre
lointain qui se perdait sans un mot, la duree d'un trajet en montagne,
l'unite qui finissait sa semaine dans l'eau, le chemin valide annule, la
recherche des bandes proches tronquee, la poursuite figee, la memoire des
terres de l'IA, l'estimation d'A* des cavaliers, les memoires de cercles."""

from src.kora import ai, commands, points, tech
from src.kora import path as PA
from src.kora import world as W
from src.kora.bands import bands_near, build_band_grid, set_goto, set_march_to_band
from src.kora.clock import Clock
from src.kora.gamestate import GameState
from src.kora.sim import apply_movement, new_game
from src.kora.types import Band, OrderKind, Terrain, Tribe
from src.kora.world import enter_cost_for, make_filled_world, offset_to_axial


def _state(world, *bands, tribes=None):
    return GameState(
        world=world,
        clock=Clock(),
        tribes=tribes or {1: Tribe(1, "Joueur", 20, True), 2: Tribe(2, "Autres", 20, False)},
        bands={b.id: b for b in bands},
    )


def _mountain_wall():
    """Une plaine coupee du nord au sud par dix lieux de montagne."""
    world = make_filled_world(70, 50, Terrain.PLAINE)
    for row in range(50):
        for col in range(30, 40):
            world._terrains[row][col] = Terrain.MONTAGNE
    return world


# --- 1. l'ordre lointain ---------------------------------------------------------


def test_a_far_order_across_the_mountains_finds_its_path():
    world = _mountain_wall()
    start, goal = offset_to_axial(22, 25), offset_to_axial(48, 25)
    d = world.distance(start, goal)
    # L'ancien plafond (18 d + 60 lieux explores, 1 200 au plus) s'arretait
    # avant : l'ordre etait ignore sans un mot.
    assert PA.astar(world, start, goal, max_cost=d * 30 + 120, max_nodes=min(1200, 18 * d + 60)) is None
    band = Band(id=1, tribe_id=1, position=start, population=10, stock=40)
    st = _state(world, band)
    assert set_goto(st, 1, goal) is True
    assert band.order.kind is OrderKind.GOTO and band.path and band.path[-1] == goal


def test_search_limits_follow_the_area_of_the_disc():
    for d in (5, 10, 20, 25):
        cost, nodes = PA.search_limits(d)
        assert nodes >= min(PA.SEARCH_NODES_MAX, 8 * d * d)
        wide_cost, wide_nodes = PA.search_limits(d, wide=True)
        assert wide_nodes >= nodes and wide_cost >= cost


def test_the_player_is_told_when_there_is_no_path():
    world = make_filled_world(60, 30, Terrain.VALLEE, wrap_x=True)
    st = new_game(world, setup={"name": "Aroha"})
    band = next(b for b in st.bands.values() if b.tribe_id == 1 and not b.village)
    # Une ile : un lieu de plaine entoure d'eau, loin de la bande.
    island = offset_to_axial(40, 20)
    for h in world.hexes_in_radius(island, 2):
        if h != island:
            col, row = W.axial_to_offset(world.canonicalize(h))
            world._terrains[row][col] = Terrain.EAU
    before = band.order.kind
    res = commands.apply(st, commands.make(1, "goto", band.id, island.q, island.r))
    assert res["msg"] == "Pas de chemin jusque-là."
    assert band.order.kind is before
    # L'eau elle-meme : pas de chemin non plus.
    water = offset_to_axial(41, 20)
    assert commands.apply(st, commands.make(1, "goto", band.id, water.q, water.r))["msg"] == "Pas de chemin jusque-là."
    # Un ordre possible : rien a dire.
    land = offset_to_axial(20, 10)
    assert commands.apply(st, commands.make(1, "goto", band.id, land.q, land.r))["msg"] == ""
    assert band.order.kind is OrderKind.GOTO


# --- 2. la duree d'un trajet -----------------------------------------------------


def _walk(world, start, path, point=None):
    band = Band(id=1, tribe_id=1, position=start, population=10, stock=40)
    if point is not None:
        band.fu, band.fv = point
    band.path = list(path)
    weeks = 0
    while band.path and weeks < 200:
        points.march(world, band, PA.MOVE_POINTS_PER_WEEK, False, None)
        weeks += 1
    return weeks


def test_travel_weeks_in_the_mountains_is_the_real_march():
    world = make_filled_world(30, 10, Terrain.MONTAGNE)
    start, goal = offset_to_axial(2, 5), offset_to_axial(10, 5)
    path = PA.astar(world, start, goal)
    real = _walk(world, start, path)
    # Huit lieux de montagne (60 chacun, 40 par semaine) : une douzaine de
    # semaines, pas "1 semaine" (l'ancien compte s'arretait au premier pas
    # plus cher qu'une semaine).
    assert real >= 10
    assert PA.travel_weeks(world, start, path) == real


def test_travel_weeks_counts_the_straightened_route_from_the_point():
    world = _mountain_wall()
    start, goal = offset_to_axial(5, 10), offset_to_axial(25, 30)
    path = PA.astar(world, start, goal)
    cu, cv = points.center(start)
    point = (cu + 20, cv - 10)
    assert points.cell_of(world, *point) == start
    assert PA.travel_weeks(world, start, path, point=point) == _walk(world, start, path, point)
    assert PA.travel_weeks(world, start, path) == _walk(world, start, path)


# --- 3. l'eau et les sommets -----------------------------------------------------


def _lakes():
    world = make_filled_world(16, 12, Terrain.PLAINE)
    for col, row in ((5, 4), (8, 6), (10, 3), (4, 8), (11, 8), (7, 9)):
        world._terrains[row][col] = Terrain.EAU
    return world


def test_a_stop_between_two_samples_never_lands_in_the_water():
    world = _lakes()
    here = offset_to_axial(10, 10)
    # Cas trouve avec l'ancien code : l'elan s'arretait dans le coin du lac
    # (8, 6), entre deux echantillons de la ligne droite.
    out = points._leg(world, (1296, 618), here, enter_cost_for(world, here, False), (896, 128), False, None, 2432)
    assert out[4] == "arret"
    assert enter_cost_for(world, out[2], False) is not None
    assert points.cell_of(world, *out[1]) == out[2]


def test_a_valid_path_is_not_cut_by_the_samples_of_another_week():
    world = _lakes()
    start = offset_to_axial(12, 6)
    band = Band(id=1, tribe_id=1, position=start, population=10, stock=40)
    band.fu, band.fv = 1563, 377
    band.path = [offset_to_axial(c, r) for c, r in ((11, 5), (11, 4), (10, 4), (9, 3), (9, 2), (8, 1))]
    # Cas trouve avec l'ancien code : la troisieme semaine, la ligne droite
    # tombait sur un coin de lac et l'ordre etait annule.
    for budget in (17, 9, 40):
        assert points.march(world, band, budget, False, None) is False
        assert enter_cost_for(world, band.position, False) is not None
    assert band.path == [] and band.position == offset_to_axial(8, 1)


def test_a_band_left_in_the_water_can_walk_out():
    world = _lakes()
    wet = offset_to_axial(8, 6)
    band = Band(id=1, tribe_id=1, position=wet, population=10, stock=40)
    st = _state(world, band)
    goal = offset_to_axial(12, 6)
    assert set_goto(st, 1, goal) is True and band.path
    for _ in range(5):
        apply_movement(st)
    assert band.position == goal


# --- 4. les bandes proches ---------------------------------------------------------


def test_the_band_grid_sees_the_whole_circle():
    world = make_filled_world(60, 60, Terrain.PLAINE)
    here = offset_to_axial(30, 30)
    bands = []
    bid = 1
    # Des bandes en haut et en bas (les rangees sont plus serrees que les
    # colonnes), a toutes les distances autour du rayon.
    for row in range(14, 47):
        for col in (28, 30, 31):
            h = offset_to_axial(col, row)
            b = Band(id=bid, tribe_id=2, position=h, population=10, stock=40)
            cu, cv = points.center(h)
            b.fu, b.fv = cu, cv + (bid % 3 - 1) * 20
            if points.cell_of(world, b.fu, b.fv) != h:
                b.fu = b.fv = -1
            bands.append(b)
            bid += 1
    st = _state(world, *bands)
    for radius in (4, 10, 14):
        st.band_grid = None
        full = [b.id for b in bands_near(st, here, radius)]
        st.band_grid = build_band_grid(st)
        assert [b.id for b in bands_near(st, here, radius)] == full
    st.band_grid = None


# --- 5. la poursuite -----------------------------------------------------------------


def test_a_pursuit_in_the_same_lieu_closes_in():
    world = make_filled_world(20, 12, Terrain.PLAINE)
    h = offset_to_axial(8, 6)
    cu, cv = points.center(h)
    hunter = Band(id=1, tribe_id=1, position=h, population=10, stock=40)
    prey = Band(id=2, tribe_id=1, position=h, population=10, stock=40)
    hunter.fu, hunter.fv = cu + 58, cv
    prey.fu, prey.fv = cu - 58, cv
    st = _state(world, hunter, prey)
    assert points.apart(world, hunter, prey) > points.MEET
    assert set_march_to_band(st, 1, 2) is True
    # Dans le meme lieu : le chemin est ce lieu (un chemin vide figeait la
    # poursuite a plus de MEET, pour toujours).
    assert hunter.path == [h]
    apply_movement(st)
    assert points.apart(world, hunter, prey) <= points.MEET
    # Et si le chemin s'est vide (une vieille partie), la poursuite repart.
    hunter.fu, hunter.fv = cu + 58, cv
    hunter.path = []
    apply_movement(st)
    assert points.apart(world, hunter, prey) <= points.MEET


# --- 6. la memoire des terres de l'IA ----------------------------------------------


def _river_savanna():
    world = make_filled_world(30, 20, Terrain.SAVANE)
    layer = bytearray(30 * 20)
    for col in range(30):
        # Un ruisseau vers l'est (direction 0 + 1, taille 1).
        layer[10 * 30 + col] = 1 | (1 << 3)
    world.set_rivers(bytes(layer))
    return world


def test_good_land_memo_does_not_depend_on_who_asks_first():
    world = _river_savanna()
    st = _state(world)
    tech.grant(st.tribes[1], "irrigation")
    tech.invalidate()
    h = offset_to_axial(15, 10)

    def fresh(tid):
        world._lands = {}
        return ai._good_count(st, tid, h)

    wet, dry = fresh(1), fresh(2)
    # La savane au bord de l'eau n'est une bonne terre qu'irriguee.
    assert wet > dry
    world._lands = {}
    assert ai._good_count(st, 2, h) == dry
    assert ai._good_count(st, 1, h) == wet
    world._lands = {}
    assert ai._good_count(st, 1, h) == wet
    assert ai._good_count(st, 2, h) == dry


def test_new_land_memo_keeps_the_point_and_the_irrigation():
    world = _river_savanna()
    h = offset_to_axial(3, 10)
    cu, cv = points.center(h)
    a = Band(id=1, tribe_id=1, position=h, population=30, stock=40)
    b = Band(id=2, tribe_id=2, position=h, population=30, stock=40)
    a.fu, a.fv = cu - 20, cv
    b.fu, b.fv = cu + 20, cv
    st = _state(world, a, b)
    tech.grant(st.tribes[1], "irrigation")
    tech.invalidate()

    def fresh(band):
        world._lands = {}
        return ai.find_new_land(st, band)

    first_a, first_b = fresh(a), fresh(b)
    world._lands = {}
    assert ai.find_new_land(st, b) == first_b
    assert ai.find_new_land(st, a) == first_a


# --- 7. les memoires de cercles -------------------------------------------------------


def test_circle_memories_are_bounded_by_the_lieux_they_keep(monkeypatch):
    world = make_filled_world(80, 60, Terrain.PLAINE)
    monkeypatch.setattr(W, "BIG_RADIUS_CACHE_CELLS", 3000)
    monkeypatch.setattr(points, "NEAR_CACHE_CELLS", 3000)
    for col in range(5, 75, 3):
        h = offset_to_axial(col, 30)
        found, _d = world.hexes_and_distances(h, 9)
        assert found
        points.cells_near(world, points.center(h), 8)
        kept = sum(len(v[0]) for v in world._big_radius_cache.values())
        assert kept <= 3000 + len(found)
        near = sum(len(v[0]) for v in world.__dict__["_near"].values())
        assert near <= 3000 + 400
    # Ce qui est garde reste juste.
    h = offset_to_axial(40, 30)
    found, dists = world.hexes_and_distances(h, 9)
    assert len(found) == len(dists) and all(world.distance(h, x) == d for x, d in zip(found, dists))


# --- 8. l'estimation d'A* des cavaliers ------------------------------------------------


def test_the_heuristic_never_overestimates_for_horsemen():
    cavalry = dict(tech.BASE_MOVE_COST)
    cavalry.update({Terrain.STEPPE: 6, Terrain.PLAINE: 7})
    for costs, rivers in ((cavalry, True), (cavalry, False), (W.MOVE_COST, True), (W.MOVE_COST, False)):
        rate = PA.heuristic_rate(costs, rivers)
        low = min(costs.values()) * W.COST_VAR_MIN // 100
        if rivers:
            low = low * min(W.RIVER_PCT) // 100
        # Un pas droit (1 lieu) et un pas en biais (racine de 3 lieux).
        assert 900 * low <= rate <= 1000 * low
        assert rate * 17320508 <= (2 * low * PA.DIAGONAL_PER_MILLE // 1000) * 1000 * 10000000
    # Un cavalier n'est plus estime a 9 par lieu (des chemins trop chers).
    assert PA.heuristic_rate(cavalry, False) < PA.heuristic_rate(W.MOVE_COST, False)
