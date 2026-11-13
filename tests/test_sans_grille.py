"""Le monde sans grille, premiere version (0.27.0) : la vraie distance (des
cercles, plus des hexagones), l'influence qui rayonne en rond, la carte
dessinee en formes (plus de polygones de case), le glissement des unites et
le chemin en courbe."""

import math
import os

os.environ.setdefault("SDL_VIDEODRIVER", "dummy")

import numpy as np
import pygame

from src.kora import glisse, influence
from src.kora.globe_draw import Planet, TERRAINS
from src.kora.types import Hex, Terrain
from src.kora.world import make_filled_world, offset_to_axial, true_distance


def test_the_true_distance_is_a_circle():
    # Un pas vers un voisin : 1 ; deux pas en escalier en biais : 1,73 -> 2 ;
    # quatre pas en escalier en biais (3,46) : 3, plus 4.
    assert true_distance(1, 0) == true_distance(0, 1) == true_distance(1, -1) == 1
    assert true_distance(2, -1) == 2
    assert true_distance(4, -2) == 3
    world = make_filled_world(80, 60, Terrain.PLAINE, wrap_x=True)
    c = offset_to_axial(40, 30)
    disc = world.hexes_in_radius(c, 10)
    # Un cercle de rayon 10 (10,5 : la distance est arrondie) : pi x r x r
    # sur l'aire d'une case ; un hexagone en aurait 331.
    assert abs(len(disc) - math.pi * 10.5 * 10.5 / (math.sqrt(3) / 2)) < 20
    # Autour du monde : la distance la plus courte.
    a, b = offset_to_axial(1, 30), offset_to_axial(78, 30)
    assert world.distance(a, b) == 3


def test_influence_spreads_round_and_follows_the_ground():
    world = make_filled_world(60, 40, Terrain.PLAINE, wrap_x=True)
    c = offset_to_axial(30, 20)
    hexes, costs = influence.projection(world, c, 8)
    reach = {world.distance(h, c) for h in hexes}
    assert max(reach) == 8
    # Rond : dans toutes les directions la meme portee (a une case pres).
    far = [h for h, d in zip(hexes, costs) if d > 6.5]
    angles = sorted(math.atan2((h.r - c.r) * math.sqrt(3) / 2, (h.q - c.q) + (h.r - c.r) / 2) for h in far)
    gaps = [b - a for a, b in zip(angles, angles[1:])] + [angles[0] + 2 * math.pi - angles[-1]]
    assert max(gaps) < 0.6


def test_the_map_is_drawn_in_shapes():
    """Plus de polygones : chaque point vote avec les neuf centres voisins ;
    une case seule (un etang) garde son coeur ; la frontiere entre deux sols
    est une courbe (elle ne suit plus les bords des hexagones)."""
    world = make_filled_world(40, 30, Terrain.PLAINE, wrap_x=True)
    world._terrains[15][20] = Terrain.EAU
    for row in range(30):
        for col in range(25, 40):
            world._terrains[row][col] = Terrain.FORET
    pygame.init()
    planet = Planet(world)
    xf = np.array([20.0 - 1.0 / 6.0 * (1 if 15 % 2 == 0 else -1)], dtype=np.float32)
    code, _r, _c, _w = planet._bake_codes(xf, np.array([15.0], dtype=np.float32))
    assert TERRAINS[int(code[0])] is Terrain.EAU
    # La frontiere plaine / foret : la ou elle passe d'une rangee a l'autre,
    # elle ne saute pas d'un demi-hexagone (pas d'escalier).
    xs = np.linspace(22.0, 28.0, 241, dtype=np.float32)
    edges = []
    for row in (10.0, 10.5, 11.0):
        code, _r, _c, _w = planet._bake_codes(xs, np.full_like(xs, row))
        forest = np.array([TERRAINS[int(k)] is Terrain.FORET for k in code])
        edges.append(xs[np.argmax(forest)])
    assert max(edges) - min(edges) < 0.4
    assert not hasattr(planet, "draw_hexes")


def test_a_unit_glides_along_a_smooth_path(monkeypatch):
    world = make_filled_world(40, 30, Terrain.PLAINE, wrap_x=True)

    class Clock:
        paused = False

        def ticks_per_second(self):
            return 1.0

    class State:
        pass

    class Band:
        id = 7
        position = offset_to_axial(10, 10)
        path = [offset_to_axial(11, 10), offset_to_axial(12, 11), offset_to_axial(13, 11)]

    st = State()
    st.world, st.clock = world, Clock()
    band = Band()
    glisse.observe(st, band, now=0.0)
    band.position = band.path[2]
    band.path = []
    glisse.observe(st, band, now=10.0)
    start = glisse.place(st, band, now=10.0)
    mid = glisse.place(st, band, now=10.5)
    assert start is not None and abs(start[0] - 10.0) < 1e-6
    assert 10.5 < mid[0] < 12.5
    assert glisse.place(st, band, now=11.5) is None
    # Le chemin lisse passe par ses points, sans angle.
    curve = glisse.smooth([(0.0, 0.0), (1.0, 0.0), (2.0, 1.0), (3.0, 1.0)])
    assert curve[0] == (0.0, 0.0) and curve[-1] == (3.0, 1.0)
    assert any(abs(p[0] - 1.0) < 1e-9 and abs(p[1]) < 1e-9 for p in curve)
    assert len(curve) > 10
