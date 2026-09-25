import functools
import math

import numpy as np

from src.kora.mapgen import Noise3, continent_sizes, fbm, sphere_points
from src.kora.types import Terrain
from src.kora.world import generate_world as _generate_world
from src.kora.world import offset_to_axial


@functools.lru_cache(maxsize=None)
def generate_world(seed=42, width=None, height=None):
    # Une planete pleine taille prend ~15 s : chaque graine n'est generee
    # qu'une fois pour tout le fichier (les tests ne la modifient pas).
    return _generate_world(seed=seed, width=width, height=height)


def test_two_seeds_produce_different_land():
    a = generate_world(seed=11, width=96, height=48)
    b = generate_world(seed=23, width=96, height=48)
    mask_a = tuple(
        a.terrain(offset_to_axial(c, r)) is Terrain.EAU
        for r in range(a.height)
        for c in range(a.width)
    )
    mask_b = tuple(
        b.terrain(offset_to_axial(c, r)) is Terrain.EAU
        for r in range(b.height)
        for c in range(b.width)
    )
    assert mask_a != mask_b


def test_generated_planet_is_large_and_varied():
    world = generate_world(seed=42)
    assert world.width >= 300
    assert world.height >= 150
    assert world.wrap_x is True
    terrains = set()
    for row in range(world.height):
        for col in range(world.width):
            terrains.add(world.terrain(offset_to_axial(col, row)))
    for needed in (
        Terrain.EAU,
        Terrain.COTE,
        Terrain.PLAINE,
        Terrain.FORET,
        Terrain.DESERT,
        Terrain.MONTAGNE,
        Terrain.VALLEE,
        Terrain.STEPPE,
    ):
        assert needed in terrains, f"manque {needed}"
    land = sum(
        1
        for row in range(world.height)
        for col in range(world.width)
        if world.passable(offset_to_axial(col, row))
    )
    ratio = land / (world.width * world.height)
    assert 0.16 <= ratio <= 0.58


def test_planet_has_several_continents_not_one_equatorial_mass():
    world = generate_world(seed=31)
    sizes = continent_sizes(world)
    big = [s for s in sizes if s >= max(180, world.width * world.height // 500)]
    assert len(big) >= 3
    assert sizes[0] <= sum(sizes) * 0.55


def test_mountains_follow_ranges_not_continent_cores():
    world = generate_world(seed=31)
    land = 0
    mtn = 0
    for row in range(world.height):
        lat = abs((row / max(1, world.height - 1)) * 2.0 - 1.0)
        for col in range(world.width):
            t = world.terrain(offset_to_axial(col, row))
            if t is Terrain.EAU:
                continue
            if lat > 0.80 and t is Terrain.SOMMET:
                continue
            land += 1
            if t in (Terrain.MONTAGNE, Terrain.SOMMET):
                mtn += 1
    assert land > 0
    assert mtn / land < 0.34


def test_polar_ice_does_not_merge_continents():
    from src.kora.world import World

    w, h = 24, 16
    grid = [[Terrain.EAU for _ in range(w)] for _ in range(h)]
    for col in range(w):
        grid[0][col] = Terrain.SOMMET
        grid[1][col] = Terrain.SOMMET
        grid[h - 1][col] = Terrain.SOMMET
    for row in range(3, 7):
        grid[row][3] = Terrain.PLAINE
        grid[row][4] = Terrain.PLAINE
        grid[row][16] = Terrain.PLAINE
        grid[row][17] = Terrain.PLAINE
    grid[2][3] = Terrain.SOMMET
    grid[2][16] = Terrain.SOMMET
    world = World(grid, wrap_x=True)
    sizes = continent_sizes(world)
    assert len(sizes) >= 2
    assert sizes[0] <= 12


def test_noise_closes_east_west():
    # Le bruit est pris sur la sphere : longitude -pi et +pi sont le meme point.
    noise = Noise3(np.random.default_rng(5))
    lat = 0.4
    west = np.array([[math.cos(lat) * math.sin(-math.pi), math.sin(lat), math.cos(lat) * math.cos(-math.pi)]])
    east = np.array([[math.cos(lat) * math.sin(math.pi), math.sin(lat), math.cos(lat) * math.cos(math.pi)]])
    assert abs(fbm(noise, west, 2.0, 6)[0] - fbm(noise, east, 2.0, 6)[0]) < 1e-9
    p, _lat = sphere_points(96, 48)
    assert np.allclose(np.linalg.norm(p, axis=-1), 1.0)


def _water_match(world, col_a: int, col_b: int) -> float:
    same = 0
    for row in range(world.height):
        wa = world.terrain(offset_to_axial(col_a, row)) is Terrain.EAU
        wb = world.terrain(offset_to_axial(col_b, row)) is Terrain.EAU
        if wa == wb:
            same += 1
    return same / world.height


def test_date_line_is_as_continuous_as_the_interior():
    world = generate_world(seed=11, width=96, height=48)
    wrap = _water_match(world, 0, world.width - 1)
    mid = _water_match(world, world.width // 2, world.width // 2 + 1)
    assert wrap >= mid - 0.18


def test_biomes_mix_along_the_same_latitude():
    world = generate_world(seed=31)
    mixed = 0
    land_rows = 0
    for row in range(int(world.height * 0.28), int(world.height * 0.72)):
        kinds = set()
        for col in range(0, world.width, 2):
            t = world.terrain(offset_to_axial(col, row))
            if t in (Terrain.PLAINE, Terrain.FORET, Terrain.DESERT, Terrain.STEPPE):
                kinds.add(t)
        if kinds:
            land_rows += 1
        if len(kinds) >= 2:
            mixed += 1
    assert land_rows >= 8
    assert mixed >= max(6, land_rows // 3)


def test_continents_are_not_the_same_ellipse():
    world = generate_world(seed=31)
    aspects = _continent_aspects(world)
    big = [a for a in aspects if a[0] >= 400]
    assert len(big) >= 3
    ratios = [max(a[1], 0.15) for a in big]
    assert max(ratios) / min(ratios) >= 1.35


def _continent_aspects(world) -> list[tuple[int, float]]:
    from src.kora.mapgen import _is_polar_cap
    from src.kora.world import axial_to_offset

    visited = [[False] * world.width for _ in range(world.height)]
    out: list[tuple[int, float]] = []
    for row in range(world.height):
        for col in range(world.width):
            if visited[row][col] or world._terrains[row][col] is Terrain.EAU:
                continue
            if _is_polar_cap(world, col, row):
                visited[row][col] = True
                continue
            stack = [(col, row)]
            visited[row][col] = True
            cells = [(col, row)]
            while stack:
                c, r = stack.pop()
                for nb in world.neighbors(offset_to_axial(c, r)):
                    nc, nr = axial_to_offset(nb)
                    if visited[nr][nc] or world._terrains[nr][nc] is Terrain.EAU:
                        continue
                    if _is_polar_cap(world, nc, nr):
                        visited[nr][nc] = True
                        continue
                    visited[nr][nc] = True
                    stack.append((nc, nr))
                    cells.append((nc, nr))
            rows = [r for _c, r in cells]
            cols = sorted({c for c, _r in cells})
            hspan = max(rows) - min(rows) + 1
            if len(cols) <= 1:
                wspan = 1
            else:
                gaps = [cols[i + 1] - cols[i] for i in range(len(cols) - 1)]
                gaps.append(cols[0] + world.width - cols[-1])
                wspan = max(1, world.width - max(gaps))
            out.append((len(cells), wspan / max(1, hspan)))
    return out


def test_poles_are_ice_or_ocean():
    world = generate_world(seed=11, width=96, height=48)
    allowed = {Terrain.EAU, Terrain.SOMMET, Terrain.COTE}
    for col in range(world.width):
        for row in (0, 1, world.height - 2, world.height - 1):
            t = world.terrain(offset_to_axial(col, row))
            assert t in allowed, f"{t} au pole col={col} row={row}"


def _count(world, *kinds):
    return sum(1 for row in world._terrains for t in row if t in kinds)


def test_the_planet_has_rivers_lakes_ranges_and_archipelagos():
    world = generate_world(seed=42)
    land = _count(world, *(t for t in Terrain if t is not Terrain.EAU))
    assert _count(world, Terrain.VALLEE) / land > 0.015
    assert _count(world, Terrain.MONTAGNE) / land > 0.01
    assert _count(world, Terrain.COLLINE) / land > 0.02
    sizes = continent_sizes(world)
    assert sum(1 for s in sizes if s < 60) >= 20  # iles et archipels
    from src.kora.atlas import _components

    waters = sorted(_components(world, "water"), key=len, reverse=True)
    assert sum(1 for w in waters[1:] if len(w) >= 12) >= 5  # lacs, mers fermees


def test_atlas_names_several_oceans_and_the_continents():
    from src.kora.atlas import build_atlas_labels

    labels = build_atlas_labels(generate_world(seed=42))
    kinds = [lab.kind for lab in labels]
    assert kinds.count("land") >= 3
    assert kinds.count("sea") >= 4
    assert len({lab.name for lab in labels}) == len(labels)
