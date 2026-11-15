"""Le monde sans grille, la suite (0.30.0) : le chemin redresse (droit quand
ca ne coute pas plus), les rencontres a la vraie distance et les unites qui
se croisent, les lieux poses a un point (village, camp, cache)."""

import math
import random

from src.kora import battle, chiefs, glisse, memory, points, sites, tech, villages
from src.kora.bands import costs_of, set_goto, set_march_to_band
from src.kora.clock import Clock
from src.kora.gamestate import GameState
from src.kora.path import MOVE_POINTS_PER_WEEK
from src.kora.persist import load_game, save_game
from src.kora.sim import apply_movement, resolve_joins
from src.kora.types import Band, Terrain, Tribe
from src.kora.world import make_filled_world, offset_to_axial

FINE = points.FINE


def _state(terrain=Terrain.PLAINE, known=()):
    world = make_filled_world(60, 40, terrain, wrap_x=True)
    st = GameState(
        world=world,
        clock=Clock(),
        tribes={
            1: Tribe(1, "Kora", 30, True, knowledge=set(tech.START_KNOWLEDGE) | set(known), culture="joueur"),
            2: Tribe(2, "Autres", 30, False, knowledge=set(tech.START_KNOWLEDGE) | set(known)),
        },
        bands={},
        next_band_id=50,
    )
    st.rng = random.Random(3)
    st.clock.week = 20
    world.fill_season(st.clock.season())
    return st


def _band(st, bid, tid, col, row, pop=30, kind="", du=0, dv=0):
    h = offset_to_axial(col, row)
    b = Band(bid, tid, h, pop, 600.0, kind=kind)
    if kind == "armee":
        b.units = [["guerriers", pop, 0]]
    if du or dv:
        u, v = points.center(h)
        b.fu, b.fv = u + du, v + dv
    st.bands[bid] = b
    chiefs.ensure(st)
    return b


def _off_line(a, b, p) -> float:
    """La distance du point p a la droite (a, b), en largeurs de lieu."""
    ax, ay = a[0] / 2.0, a[1] * math.sqrt(3) / 2.0
    bx, by = b[0] / 2.0, b[1] * math.sqrt(3) / 2.0
    px, py = p[0] / 2.0, p[1] * math.sqrt(3) / 2.0
    return abs((bx - ax) * (py - ay) - (by - ay) * (px - ax)) / math.hypot(bx - ax, by - ay) / FINE


# --- le chemin redresse -------------------------------------------------------------


def test_a_unit_walks_straight_where_it_costs_no_more():
    st = _state()
    band = _band(st, 1, 1, 10, 10)
    start = points.point_of(st.world, band)
    # En biais, hors des axes de l'ancienne grille : le chemin cherche de
    # lieu en lieu fait un escalier.
    goal = offset_to_axial(22, 17)
    set_goto(st, 1, goal)
    assert band.path
    end = points.center(goal)
    weeks = 0
    while band.path and weeks < 20:
        apply_movement(st)
        weeks += 1
        here = points.point_of(st.world, band)
        # Toujours sur la droite du depart a l'arrivee (a un dixieme de lieu).
        assert _off_line(start, end, here) < 0.1, (weeks, _off_line(start, end, here))
    assert points.point_of(st.world, band) == end
    # La vraie distance (14 lieux), a 4 lieux de plaine par semaine : 4
    # semaines ; l'escalier en faisait 5.
    assert weeks == -(-points.length(st.world, start, end) * 10 // (MOVE_POINTS_PER_WEEK * FINE))


def test_the_first_week_covers_the_true_distance():
    st = _state()
    band = _band(st, 1, 1, 10, 10)
    start = points.point_of(st.world, band)
    set_goto(st, 1, offset_to_axial(22, 17))
    apply_movement(st)
    walked = points.length(st.world, start, points.point_of(st.world, band))
    # 40 points de marche, 10 par lieu de plaine : 4 lieux, a un pas pres.
    assert abs(walked - 4 * FINE) <= points.STEP


def test_it_goes_round_what_costs_more():
    # Un lac entre le depart et l'arrivee : le chemin le contourne, l'unite
    # aussi (elle ne coupe pas a travers).
    world = make_filled_world(60, 40, Terrain.PLAINE, wrap_x=True)
    for col in range(14, 19):
        for row in range(6, 15):
            world._terrains[row][col] = Terrain.EAU
    st = _state()
    st.world = world
    world.fill_season(st.clock.season())
    band = _band(st, 1, 1, 10, 10)
    goal = offset_to_axial(22, 10)
    set_goto(st, 1, goal)
    assert band.path
    seen = set()
    weeks = 0
    while band.path and weeks < 30:
        apply_movement(st)
        weeks += 1
        seen.add(world.terrain(band.position))
        for p in getattr(band, "trail", []):
            assert world.terrain(points.cell_of(world, *p)) is not Terrain.EAU
    assert band.position == goal and Terrain.EAU not in seen


def test_the_route_drawn_is_the_one_walked():
    st = _state()
    band = _band(st, 1, 1, 10, 10)
    set_goto(st, 1, offset_to_axial(15, 13))
    route = points.route(st.world, band, False, costs_of(st, 1))
    # Sur un sol uni, dans la portee du regard : une seule ligne droite.
    assert route[0] == points.point_of(st.world, band) and route[-1] == points.center(offset_to_axial(15, 13))
    assert len(route) == 2
    apply_movement(st)
    assert band.trail[0] == route[0]
    assert _off_line(route[0], route[-1], band.trail[-1]) < 0.1


def test_the_glide_follows_the_walk():
    st = _state()
    band = _band(st, 1, 1, 10, 10)
    set_goto(st, 1, offset_to_axial(22, 17))
    glisse.observe(st, band, now=0.0)
    apply_movement(st)
    glisse.observe(st, band, now=0.0)
    mid = glisse.place(st, band, now=0.2)
    assert mid is not None
    start = points.center(offset_to_axial(10, 10))
    end = points.center(offset_to_axial(22, 17))
    u, v = points.from_colrow(*mid)
    assert _off_line(start, end, (u, v)) < 0.15


# --- les rencontres a la distance -----------------------------------------------------


def test_crossed_says_if_two_marches_came_close():
    world = make_filled_world(60, 40, Terrain.PLAINE, wrap_x=True)
    c = points.center
    a0, a1 = c(offset_to_axial(10, 10)), c(offset_to_axial(18, 10))
    # L'autre vient en face sur la meme ligne : ils se croisent.
    assert points.crossed(world, a0, a1, c(offset_to_axial(18, 10)), c(offset_to_axial(10, 10)), points.MEET)
    # Il coupe la route au milieu de la semaine.
    assert points.crossed(world, a0, a1, c(offset_to_axial(14, 6)), c(offset_to_axial(14, 14)), points.MEET)
    # Il passe au meme endroit, mais plus tot : pas de rencontre.
    assert not points.crossed(world, a0, a1, c(offset_to_axial(11, 6)), c(offset_to_axial(11, 14)), points.MEET)
    # Deux marches paralleles, a trois lieux.
    assert not points.crossed(world, a0, a1, c(offset_to_axial(10, 13)), c(offset_to_axial(18, 13)), points.MEET)
    # Immobiles et loin ; immobiles et tout pres.
    assert not points.crossed(world, a0, a0, a1, a1, points.MEET)
    assert points.crossed(world, a0, a0, (a0[0] + 20, a0[1]), (a0[0] + 20, a0[1]), points.MEET)


def test_two_bands_meet_at_a_distance_not_in_a_place():
    st = _state()
    # Dans deux lieux voisins, a un demi-lieu l'une de l'autre : elles se
    # rencontrent (u compte double : FINE // 2 = un quart de lieu).
    a = _band(st, 1, 1, 10, 10, du=FINE // 2)
    b = _band(st, 2, 2, 11, 10, du=-FINE // 2)
    assert a.position != b.position
    assert points.apart(st.world, a, b) <= points.MEET
    battle.resolve_raids(st)
    assert len(st.battles) == 1
    assert a.position == b.position and points.apart(st.world, a, b) == 0


def test_two_bands_in_neighbouring_places_but_apart_do_not_meet():
    st = _state()
    _band(st, 1, 1, 10, 10)
    _band(st, 2, 2, 11, 10)
    battle.resolve_raids(st)
    assert not st.battles
    # Dans le meme lieu mais a plus de trois quarts de lieu : non plus.
    st2 = _state()
    _band(st2, 1, 1, 10, 10, du=-FINE + 4, dv=0)
    _band(st2, 2, 2, 10, 10, du=FINE - 4, dv=0)
    assert st2.bands[1].position == st2.bands[2].position
    battle.resolve_raids(st2)
    assert not st2.battles


def test_a_hunter_catches_the_band_it_crossed():
    st = _state()
    hunter = _band(st, 1, 1, 18, 10)
    prey = _band(st, 2, 2, 10, 10)
    set_march_to_band(st, 1, 2)
    assert hunter.order.target_band_id == 2
    # Dans la semaine, chacune a traverse la route de l'autre ; a la fin,
    # elles sont a huit lieux.
    hunter.pu, hunter.pv = points.center(offset_to_axial(10, 10))
    prey.pu, prey.pv = points.center(offset_to_axial(18, 10))
    assert points.apart(st.world, hunter, prey) > 4 * FINE
    battle.resolve_raids(st)
    assert len(st.battles) == 1 and hunter.position == prey.position


def test_two_wandering_clans_that_crossed_do_not_fight():
    st = _state()
    a = _band(st, 1, 1, 18, 10)
    b = _band(st, 2, 2, 10, 10)
    a.pu, a.pv = points.center(offset_to_axial(10, 10))
    b.pu, b.pv = points.center(offset_to_axial(18, 10))
    battle.resolve_raids(st)
    assert not st.battles


def test_a_troop_fights_those_it_crossed():
    st = _state()
    troop = _band(st, 1, 1, 18, 10, kind="armee")
    clan = _band(st, 2, 2, 10, 10)
    troop.pu, troop.pv = points.center(offset_to_axial(10, 10))
    clan.pu, clan.pv = points.center(offset_to_axial(18, 10))
    battle.resolve_raids(st)
    assert len(st.battles) == 1 and troop.position == clan.position


def test_a_village_is_a_place_one_enters():
    st = _state(known=("huttes", "semis", "sedentarite"))
    home = _band(st, 2, 2, 20, 15, pop=120)
    home.stock = 3000.0
    sites.make_camp(st, 2)
    assert villages.found(st, 2) is not None
    # Une troupe a un demi-lieu du village, mais dans le lieu voisin : pas
    # de bataille (un assaut ne part pas par megarde).
    troop = _band(st, 1, 1, 21, 15, kind="armee", du=-FINE + 8)
    assert points.apart(st.world, troop, home) <= points.MEET and troop.position != home.position
    battle.resolve_raids(st)
    assert not st.battles
    # Elle entre dans le lieu du village : la bataille.
    troop.position = home.position
    troop.fu, troop.fv = points.center(home.position)[0] + 20, points.center(home.position)[1]
    battle.resolve_raids(st)
    assert len(st.battles) == 1 and st.battles[0].village


def test_joining_one_s_own_only_needs_to_be_near():
    st = _state()
    a = _band(st, 1, 1, 10, 10, du=FINE - 4)
    b = _band(st, 2, 1, 12, 10, du=-FINE + 4)
    assert st.world.distance(a.position, b.position) == 2
    assert points.apart(st.world, a, b) <= points.NEAR
    set_march_to_band(st, 1, 2)
    a.path = []
    resolve_joins(st)
    assert 1 not in st.bands and b.population == 60


# --- les lieux a un point --------------------------------------------------------------


def test_a_camp_and_a_village_stand_where_the_band_stood(tmp_path):
    st = _state(known=("huttes", "semis", "sedentarite"))
    band = _band(st, 1, 1, 20, 15, pop=120, du=20, dv=-14)
    band.stock = 3000.0
    spot = points.point_of(st.world, band)
    assert spot != points.center(band.position)
    camp = sites.make_camp(st, 1)
    assert (camp.u, camp.v) == spot and points.site_point(camp) == spot
    site = villages.found(st, 1)
    assert site is camp and band.village == site.id
    # Le village est au point de son campement, sa bande aussi.
    assert points.site_point(site) == spot and points.point_of(st.world, band) == spot
    # Sauve, relu : au meme point.
    path = tmp_path / "kora.json"
    save_game(st, path, {})
    back, _ = load_game(path, st.world)
    assert points.site_point(back.sites[site.id]) == spot
    assert points.point_of(back.world, back.bands[1]) == spot


def test_a_place_of_an_old_game_is_at_the_centre(tmp_path):
    st = _state(known=("huttes", "semis", "sedentarite"))
    band = _band(st, 1, 1, 20, 15, pop=120, du=20, dv=-14)
    band.stock = 3000.0
    sites.make_camp(st, 1)
    site = villages.found(st, 1)
    # Une partie d'avant : le lieu n'a pas de point, et la bande du village
    # gardait celui ou elle s'etait arretee.
    site.u = site.v = -1
    stale = (band.fu, band.fv)
    assert stale != (-1, -1)
    path = tmp_path / "kora.json"
    save_game(st, path, {})
    back, _ = load_game(path, st.world)
    centre = points.center(site.hex)
    assert points.site_point(back.sites[site.id]) == centre
    assert points.point_of(back.world, back.bands[1]) == centre


def test_the_fog_remembers_where_a_place_was():
    st = _state(known=("huttes",))
    band = _band(st, 2, 2, 20, 15, du=18, dv=10)
    camp = sites.make_camp(st, 2)
    entry = memory._entry(st, camp)
    assert memory.point(entry) == points.site_point(camp)
    # Un souvenir d'avant (six valeurs) : le centre du lieu.
    assert memory.point(entry[:6]) == points.center(camp.hex)
