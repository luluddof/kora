"""LES POINTS ET LA MARCHE (le monde sans grille, 0.28.0 ; sa demande du
2026-11-13 : "supprimer la grille dans le code, en gardant le fait que selon
le terrain, et meme sur un meme terrain, la proximite et donc l'influence
peuvent varier").

Une unite est a un POINT, n'importe ou : (fu, fv) en entiers FINS (FINE par
largeur de case ; le meme calcul sur chaque machine : le multijoueur,
l'empreinte). Le plan : u = 2 x colonne (+1 sur les rangees impaires), v =
rangee ; la vraie longueur entre deux points est racine((du^2 + 3 dv^2) / 4).
La case n'est plus qu'un RELEVE du monde sous le point (le sol, son cout de
marche et sa variation locale world.cost_pct, la nourriture) : cell_of.

LA MARCHE (march) : chaque semaine, l'unite avance le long de son chemin
(les centres des lieux du chemin, puis le point vise) d'autant que le sol
le permet : chaque bout de chemin coute le sol ou il passe (et le courant
d'une riviere a la traversee), a proportion de sa longueur. Elle s'arrete
ou son elan s'arrete, entre deux lieux ; plus d'elan perdu.
Band.position reste la case sous le point (les systemes qui lisent le monde
par releves la lisent). point_of : le point d'une unite (le centre de sa
case si rien d'autre ne le dit : une partie d'avant, une unite posee par le
code).
N'importe pas pygame.
"""

from __future__ import annotations

import math

from src.kora.types import Hex
from src.kora.world import axial_to_offset, enter_cost_for, offset_to_axial, step_cost

FINE = 64
# La marche avance par petits pas (un quart de case) : le sol est lu a
# chaque pas.
STEP = FINE // 4


def center(h: Hex) -> tuple[int, int]:
    """Le point au centre d'une case."""
    col, row = axial_to_offset(h)
    return (2 * col + (row & 1)) * FINE, row * FINE


def cell_of(world, u: int, v: int) -> Hex:
    """La case sous un point (le centre le plus proche)."""
    span = 2 * world.width * FINE
    if world.wrap_x:
        u %= span
    r0 = v // FINE
    best = None
    for r in (r0, r0 + 1):
        if r < 0 or r >= world.height:
            continue
        odd = (r & 1) * FINE
        c = (u - odd + FINE) // (2 * FINE)
        du = u - (2 * c * FINE + odd)
        dv = v - r * FINE
        d = du * du + 3 * dv * dv
        if best is None or d < best[0]:
            best = (d, c, r)
    if best is None:
        r = min(max(r0, 0), world.height - 1)
        best = (0, (u + FINE) // (2 * FINE), r)
    _d, c, r = best
    if world.wrap_x:
        c %= world.width
    else:
        c = min(max(c, 0), world.width - 1)
    return offset_to_axial(c, r)


def delta(world, a: tuple[int, int], b: tuple[int, int]) -> tuple[int, int]:
    """b - a, le plus court autour du monde."""
    du = b[0] - a[0]
    if world.wrap_x:
        span = 2 * world.width * FINE
        du = (du + span // 2) % span - span // 2
    return du, b[1] - a[1]


def length(world, a: tuple[int, int], b: tuple[int, int]) -> int:
    """La vraie longueur de a a b, en FINE par largeur de case."""
    du, dv = delta(world, a, b)
    return math.isqrt(du * du + 3 * dv * dv) // 2


def point_of(world, band) -> tuple[int, int]:
    """Le point d'une unite : le sien s'il est sur sa case, sinon le centre
    de sa case (un village est au centre de son lieu)."""
    if not band.village and band.fu >= 0 and band.fv >= 0 and cell_of(world, band.fu, band.fv) == band.position:
        return band.fu, band.fv
    return center(band.position)


def to_colrow(u: float, v: float) -> tuple[float, float]:
    """Le point en colonne et rangee a virgule (le dessin du globe)."""
    return u / (2.0 * FINE) - 0.25, v / FINE


def from_colrow(col: float, row: float) -> tuple[int, int]:
    """Un point du globe (colonne, rangee a virgule) en point fin."""
    return int(round((col + 0.25) * 2 * FINE)), int(round(row * FINE))


def aim_of(world, band):
    """Le point vise au bout du chemin (s'il est dans la derniere case du
    chemin), sinon None (le centre de la derniere case)."""
    if band.aim_u < 0 or band.aim_v < 0 or not band.path:
        return None
    if cell_of(world, band.aim_u, band.aim_v) != world.canonicalize(band.path[-1]):
        return None
    return band.aim_u, band.aim_v


def march(world, band, budget: int, water_ok: bool, costs) -> bool:
    """Une semaine de marche avec `budget` points (MOVE_POINTS_PER_WEEK).
    Rend True si le chemin est coupe (un lieu infranchissable)."""
    if not band.path:
        return False
    cur = point_of(world, band)
    cell = world.canonicalize(band.position) or band.position
    stay = enter_cost_for(world, cell, water_ok, costs) or 10
    corners = [center(h) for h in band.path]
    aim = aim_of(world, band)
    if aim is not None:
        corners[-1] = aim
    left = budget * FINE
    reached = 0
    cut = False
    for target in corners:
        du, dv = delta(world, cur, target)
        total = math.isqrt(du * du + 3 * dv * dv) // 2
        n = max(1, -(-total // STEP))
        done = 0
        start = cur
        stopped = False
        for k in range(1, n + 1):
            nu, nv = start[0] + du * k // n, start[1] + dv * k // n
            nxt = cell_of(world, nu, nv)
            if nxt != cell:
                c = step_cost(world, cell, nxt, water_ok, costs)
                if c is None:
                    cut = True
                    stopped = True
                    break
            else:
                c = stay
            seg = total * k // n - done
            need = c * seg
            if need > left:
                # Le reste de l'elan : un bout du pas.
                if need > 0 and left > 0:
                    pu = cur[0] + (nu - cur[0]) * left // need
                    pv = cur[1] + (nv - cur[1]) * left // need
                    cur = (pu, pv)
                    landed = cell_of(world, pu, pv)
                    if landed != cell:
                        cell = landed
                left = 0
                stopped = True
                break
            left -= need
            done += seg
            cur = (nu, nv)
            if nxt != cell:
                cell, stay = nxt, c
        if stopped:
            break
        cur = target
        reached += 1
    if world.wrap_x:
        cur = (cur[0] % (2 * world.width * FINE), cur[1])
    band.fu, band.fv = cur
    band.position = cell
    if cut:
        band.path = []
    else:
        band.path = band.path[reached:]
    if not band.path:
        band.aim_u = band.aim_v = -1
    return cut
