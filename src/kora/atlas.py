from __future__ import annotations

import math
from dataclasses import dataclass

from src.kora.types import Terrain
from src.kora.world import World, axial_to_offset, offset_to_axial

LAND_NAMES = (
    "Kora",
    "Aran",
    "Selim",
    "Nara",
    "Veld",
    "Orun",
    "Tassa",
    "Mekar",
    "Lir",
    "Sora",
    "Yuna",
    "Belak",
)
SEA_NAMES = (
    "Grand Ocean",
    "Ocean du Couchant",
    "Ocean du Levant",
    "Mer du Sel",
    "Mer Pale",
    "Mer Verte",
    "Golfe Brumeux",
    "Mer Froide",
    "Bassin d'Ivoire",
    "Mer Interieure",
)
ICE_NAMES = ("Banquise du Nord", "Banquise du Sud")
INLAND_NAMES = (
    "Mer Interieure",
    "Lac Profond",
    "Mer Close",
    "Lac des Brumes",
    "Mer Douce",
    "Grand Lac",
)


@dataclass(frozen=True)
class AtlasLabel:
    name: str
    col: float
    row: float
    kind: str


def _is_water(terrain: Terrain) -> bool:
    return terrain is Terrain.EAU


def _polar_ice(world: World, col: int, row: int) -> bool:
    if world.height <= 1:
        return False
    lat = abs((row / (world.height - 1)) * 2.0 - 1.0)
    return lat > 0.8 and world._terrains[row][col] is Terrain.SOMMET


def _components(world: World, kind: str) -> list[list[tuple[int, int]]]:
    """kind : "land" (sans les calottes), "ice" (calottes), "water"."""

    def member(col: int, row: int) -> bool:
        terrain = world._terrains[row][col]
        if kind == "water":
            return _is_water(terrain)
        if _is_water(terrain):
            return False
        return _polar_ice(world, col, row) == (kind == "ice")

    visited = [[False] * world.width for _ in range(world.height)]
    out: list[list[tuple[int, int]]] = []
    for row in range(world.height):
        for col in range(world.width):
            if visited[row][col] or not member(col, row):
                continue
            cells: list[tuple[int, int]] = []
            stack = [(col, row)]
            visited[row][col] = True
            while stack:
                c, r = stack.pop()
                cells.append((c, r))
                for nb in world.neighbors(offset_to_axial(c, r)):
                    nc, nr = axial_to_offset(nb)
                    if visited[nr][nc] or not member(nc, nr):
                        continue
                    visited[nr][nc] = True
                    stack.append((nc, nr))
            out.append(cells)
    return out


def _circular_mean_col(cols: list[int], width: int) -> float:
    if not cols:
        return 0.0
    s = 0.0
    c = 0.0
    for col in cols:
        ang = 2.0 * math.pi * (col / width)
        s += math.sin(ang)
        c += math.cos(ang)
    ang = math.atan2(s, c)
    val = (ang / (2.0 * math.pi)) * width
    if val < 0:
        val += width
    return val


def _anchor(cells: list[tuple[int, int]], world: World) -> tuple[float, float]:
    """Point d'ancrage du nom : la case de la composante la plus proche de
    son barycentre (un croissant garde son nom sur lui, pas dans le vide)."""
    cols = [c for c, _ in cells]
    rows = [r for _, r in cells]
    row = sum(rows) / len(rows)
    col = _circular_mean_col(cols, world.width) if world.wrap_x else sum(cols) / len(cols)
    target = offset_to_axial(int(col) % world.width, max(0, min(world.height - 1, int(row))))
    best = min(cells, key=lambda cr: world.distance(offset_to_axial(*cr), target))
    return float(best[0]), float(best[1])


def _pick_name(names: tuple[str, ...], index: int, used: set[str]) -> str:
    for i in range(len(names)):
        name = names[(index + i) % len(names)]
        if name not in used:
            used.add(name)
            return name
    name = f"{names[index % len(names)]} {index + 1}"
    used.add(name)
    return name


def _ocean_basins(world: World, cells: list[tuple[int, int]], count: int) -> list[tuple[int, int]]:
    """Points du grand large, loin des terres et loin les uns des autres."""
    water = set(cells)
    far: dict[tuple[int, int], int] = {}
    frontier = []
    for col, row in cells:
        for nb in world.neighbors(offset_to_axial(col, row)):
            if axial_to_offset(nb) not in water:
                far[(col, row)] = 0
                frontier.append((col, row))
                break
    while frontier:
        nxt = []
        for col, row in frontier:
            d = far[(col, row)] + 1
            for nb in world.neighbors(offset_to_axial(col, row)):
                key = axial_to_offset(nb)
                if key in water and key not in far:
                    far[key] = d
                    nxt.append(key)
        frontier = nxt
    open_sea = [cr for cr in cells if far.get(cr, 0) >= 6 and 0.12 < cr[1] / world.height < 0.88]
    if not open_sea:
        return []
    anchors = [max(open_sea, key=lambda cr: far[cr])]
    while len(anchors) < count:
        def spread(cr):
            h = offset_to_axial(*cr)
            return min(world.distance(h, offset_to_axial(*a)) for a in anchors) + far[cr]

        best = max(open_sea, key=spread)
        if spread(best) < world.width // 6:
            break
        anchors.append(best)
    return anchors


def build_atlas_labels(world: World) -> list[AtlasLabel]:
    baked = getattr(world, "atlas", None)
    if baked is not None:
        return list(baked)
    area = max(1, world.width * world.height)
    min_land = max(20, area // 600)
    min_ice = max(16, area // 900)
    min_inland = max(40, area // 1000)
    labels: list[AtlasLabel] = []
    used: set[str] = set()

    for i, cells in enumerate(
        c for c in sorted(_components(world, "land"), key=len, reverse=True) if len(c) >= min_land
    ):
        col, row = _anchor(cells, world)
        labels.append(AtlasLabel(_pick_name(LAND_NAMES, i, used), col, row, "land"))
    for cells in _components(world, "ice"):
        if len(cells) < min_ice:
            continue
        north = sum(r for _c, r in cells) / len(cells) < world.height / 2
        name = ICE_NAMES[0] if north else ICE_NAMES[1]
        if name in used:
            continue
        used.add(name)
        col, row = _anchor(cells, world)
        labels.append(AtlasLabel(name, col, row, "ice"))

    seas = sorted(_components(world, "water"), key=len, reverse=True)
    sea_i = 0
    if seas:
        # Le grand ocean mondial : un nom par bassin.
        for col, row in _ocean_basins(world, seas[0], 6):
            labels.append(AtlasLabel(_pick_name(SEA_NAMES, sea_i, used), float(col), float(row), "sea"))
            sea_i += 1
    for cells in seas[1:]:
        if len(cells) < min_inland:
            continue
        col, row = _anchor(cells, world)
        labels.append(AtlasLabel(_pick_name(INLAND_NAMES, sea_i, used), col, row, "sea"))
        sea_i += 1
    return labels
