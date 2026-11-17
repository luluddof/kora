"""LES CHEMINS : A* sur le sol releve par lieux (astar) et la duree d'un
trajet en semaines (travel_weeks).

Le monde sans grille (0.31.0) : la recherche va aussi EN BIAIS, en ligne
droite (deux lieux en escalier pour racine de 3 au lieu de 2, au cout du
moins cher des deux escaliers), avec la vraie distance pour heuristique :
le trajet choisi n'a plus le biais des cases (contourner un lac par ou c'est
vraiment plus court). Le chemin rendu reste une suite de lieux voisins (le
pas en biais rend sa case du milieu) ; la marche le redresse (points.march).

Une bande a MOVE_POINTS_PER_WEEK points de marche par semaine (40 : 4 cases
de plaine, le monde doit paraitre grand). Chaque pas coute
world.step_cost : le sol (world.MOVE_COST), sa variation douce
(world.cost_pct) et le courant des rivieres (x0,7 dans le sens, x1,3 a
contre-courant, gue x1,25). L'heuristique reste admissible (le courant le
plus favorable). astar a un plafond de noeuds : un ordre vers l'autre bout
du monde peut echouer (None), c'est voulu. Les memes voisins dans le meme
ordre que World.neighbors : les memes chemins sur chaque machine.
N'importe pas pygame.
"""

import heapq
import math

from src.kora.types import Hex
from src.kora.world import (
    COST_VAR_MIN,
    INSHORE_MOVE_COST,
    MOVE_COST,
    NEIGHBOR_DELTAS,
    RIVER_PCT,
    cost_pct,
    World,
    enter_cost_for,
    river_pct,
    step_cost,
)

# Le monde est grand : 4 cases de plaine par semaine (cout 10).
MOVE_POINTS_PER_WEEK = 40
# Un pas en biais (deux lieux en escalier, en ligne droite) : racine de 3 sur
# 2 du cout des deux pas, en millièmes (des entiers : le multijoueur).
DIAGONAL_PER_MILLE = 866


def astar(
    world: World,
    start: Hex,
    goal: Hex,
    max_cost: int | None = None,
    max_nodes: int | None = None,
    water_ok: bool = False,
    costs: dict | None = None,
) -> list[Hex] | None:
    # A* sur des cases entieres (col, row), sans objets Hex pendant la
    # recherche ; les memes voisins dans le meme ordre et le meme departage
    # (compteur seq) : les memes chemins sur chaque machine.
    start_i = world._index(start)
    goal_i = world._index(goal)
    if start_i is None or goal_i is None:
        return None
    if start_i == goal_i:
        return []
    if enter_cost_for(world, start, water_ok, costs) is None:
        return None
    if enter_cost_for(world, goal, water_ok, costs) is None:
        return None
    width, height, wrap = world.width, world.height, world.wrap_x
    terrains = world._terrains
    inshore = world.inshore_at
    # Heuristique : le plus petit cout d'une case (plaine 10 a COST_VAR_MIN %,
    # soit 9) par case de distance ; valable tant qu'aucun cout n'est dessous.
    move_cost = costs or MOVE_COST
    pct = cost_pct(world)
    # Le pas le moins cher : la plaine au plus bas de sa variation, et, avec
    # des rivieres, dans le sens du courant (river_pct).
    step = min(10 * COST_VAR_MIN // 100, INSHORE_MOVE_COST)
    rivers = bool(world._flow)
    if rivers:
        step = step * min(RIVER_PCT) // 100
    goal_c, goal_r = goal_i
    goal_q = goal_c - (goal_r - (goal_r & 1)) // 2

    def heuristic(c: int, r: int) -> int:
        # La vraie distance (a vol d'oiseau, arrondie en dessous) : le chemin
        # n'est jamais plus court (le monde sans grille, 0.31.0).
        q = c - (r - (r & 1)) // 2
        dr = goal_r - r
        x = 2 * (goal_q - q) + dr
        if wrap:
            w2 = 2 * width
            x = (x + width) % w2 - width
        return (math.isqrt(x * x + 3 * dr * dr) // 2) * step

    paid: dict = {}

    def enter(cc: int, cr: int, nc: int, nr: int, k: int):
        """Le cout du pas de (cc, cr) a sa voisine (nc, nr), direction k ;
        None : infranchissable (garde pendant la recherche : les pas en biais
        repassent par les memes pas)."""
        mk = (cr * width + cc) * 6 + k
        if mk in paid:
            return paid[mk]
        paid[mk] = out = _enter(cc, cr, nc, nr, k)
        return out

    def _enter(cc: int, cr: int, nc: int, nr: int, k: int):
        cost = move_cost.get(terrains[nr][nc])
        if cost is None:
            if not water_ok or not inshore(nc, nr):
                return None
            return INSHORE_MOVE_COST
        cost = cost * pct[nr][nc] // 100
        if rivers:
            cost = cost * river_pct(world, cc, cr, nc, nr, k) // 100
        return cost

    def neighbour(cq: int, cr: int, k: int):
        dq, dr = NEIGHBOR_DELTAS[k]
        nr = cr + dr
        if nr < 0 or nr >= height:
            return None
        nc = cq + dq + (nr - (nr & 1)) // 2
        if wrap:
            nc %= width
        elif nc < 0 or nc >= width:
            return None
        return nc, nr

    start_key = start_i[1] * width + start_i[0]
    goal_key = goal_r * width + goal_c
    open_heap: list[tuple[int, int, int]] = [(0, 0, start_key)]
    seq = 0
    came: dict[int, int] = {}
    # EN BIAIS : la case par ou passe le pas en biais (pour rendre un chemin
    # de lieux voisins : la marche le redresse ensuite).
    via: dict[int, int] = {}
    g: dict[int, int] = {start_key: 0}
    closed: set[int] = set()
    expanded = 0
    while open_heap:
        _f, _, current = heapq.heappop(open_heap)
        if current in closed:
            continue
        if current == goal_key:
            path: list[Hex] = []
            node = current
            while node != start_key:
                r, c = divmod(node, width)
                path.append(Hex(c - (r - (r & 1)) // 2, r))
                mid = via.get(node, -1)
                if mid >= 0:
                    r, c = divmod(mid, width)
                    path.append(Hex(c - (r - (r & 1)) // 2, r))
                node = came[node]
            path.reverse()
            return path
        closed.add(current)
        expanded += 1
        if max_nodes is not None and expanded > max_nodes:
            return None
        cr, cc = divmod(current, width)
        cq = cc - (cr - (cr & 1)) // 2
        g_cur = g[current]
        # Les six voisins, puis les six pas en biais (deux lieux en escalier,
        # en ligne droite : racine de 3 au lieu de 2, au cout du moins cher
        # des deux escaliers) : le chemin cherche n'a plus le biais des
        # cases (le monde sans grille, 0.31.0).
        moves = []
        near = []
        for k in range(6):
            nb = neighbour(cq, cr, k)
            if nb is None:
                near.append(None)
                continue
            c1 = enter(cc, cr, nb[0], nb[1], k)
            near.append(None if c1 is None else (nb, c1))
            if c1 is not None:
                moves.append((nb[0], nb[1], c1, -1))
        for k in range(6):
            best = None
            for first, turn in ((k, (k + 1) % 6), ((k + 1) % 6, k)):
                one = near[first]
                if one is None:
                    continue
                (mc, mr), c1 = one
                mq = mc - (mr - (mr & 1)) // 2
                far = neighbour(mq, mr, turn)
                if far is None:
                    continue
                c2 = enter(mc, mr, far[0], far[1], turn)
                if c2 is not None and (best is None or c1 + c2 < best[0]):
                    best = (c1 + c2, far, mr * width + mc)
            if best is not None:
                moves.append((best[1][0], best[1][1], best[0] * DIAGONAL_PER_MILLE // 1000, best[2]))
        for nc, nr, cost, mid in moves:
            tentative = g_cur + cost
            if max_cost is not None and tentative > max_cost:
                continue
            key = nr * width + nc
            if tentative < g.get(key, 10**9):
                came[key] = current
                if mid >= 0:
                    via[key] = mid
                else:
                    via.pop(key, None)
                g[key] = tentative
                seq += 1
                heapq.heappush(open_heap, (tentative + heuristic(nc, nr), seq, key))
    return None


def travel_weeks(
    world: World, start: Hex, path: list[Hex], water_ok: bool = False, costs: dict | None = None
) -> int:
    if not path:
        return 0
    weeks = 0
    points = 0
    here = start
    for nxt in path:
        cost = step_cost(world, here, nxt, water_ok, costs)
        here = nxt
        if cost is None:
            return weeks
        if points < cost:
            weeks += 1
            points += MOVE_POINTS_PER_WEEK
            if points < cost:
                return weeks
        points -= cost
    return weeks
