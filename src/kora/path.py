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
contre-courant, gue x1,25). L'heuristique reste admissible (heuristic_rate :
le sol le moins cher du peuple, le courant le plus favorable, le pas en
biais). astar a un plafond de noeuds : un ordre vers l'autre bout du monde
peut echouer (None), c'est voulu ; search_limits donne des plafonds qui
suivent l'aire du disque explore (un ordre lointain ne se perd plus sans
raison ; revue du 2026-11-27). travel_weeks rejoue la vraie marche
(points.weeks_along). Les memes voisins dans le meme ordre que
World.neighbors : les memes chemins sur chaque machine.
N'importe pas pygame.
"""

import heapq
import math

# path et points s'appellent l'un l'autre (la duree d'un trajet rejoue la
# marche ; la marche coupee cherche un detour) : modules entiers.
from src.kora import points
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
# LE PLAFOND D'UNE RECHERCHE (search_limits ; revue du 2026-11-27) : A*
# explore un DISQUE autour du depart (son estimation compte 6 par lieu avec
# les rivieres, un lieu coute 10 a 60) : le plafond de lieux explores suit
# l'AIRE du disque. Mesure sur sa planete (900 buts atteignables a 3-25
# lieues, ceux de la revue) : 1 x d^2 lieux explores en mediane, 2,5 x d^2 a
# 90 %, 10 a 40 x d^2 en montagne ou pour contourner un lac. L'ancien
# plafond (18 d + 60, 1 200 au plus) perdait l'ordre 7 % des fois a 3-9
# lieues, 26 % a 10-17, 55 % a 18-25. Le plafond courant (8 d^2 + 400,
# 80 par lieu) en perd 1 / 2 / 1 % (les grands detours, la montagne) ;
# l'ordre du JOUEUR (wide : 30 d^2 + 2 000, 150 par lieu) 0 / 0 / 0,2 %. Une
# recherche qui echoue (une ile) coute ~30 microsecondes par lieu explore :
# 6 000 au plus pour l'IA (0,2 s), 12 000 pour le joueur (0,4 s, un clic).
SEARCH_NODES_PER_D2 = 8
SEARCH_NODES_BASE = 400
SEARCH_NODES_MAX = 6000
SEARCH_COST_PER_LIEU = 80
SEARCH_COST_BASE = 240
WIDE_NODES_PER_D2 = 30
WIDE_NODES_BASE = 2000
WIDE_NODES_MAX = 12000
WIDE_COST_PER_LIEU = 150
WIDE_COST_BASE = 600


def search_limits(dist: int, wide: bool = False) -> tuple[int, int]:
    """Les plafonds d'une recherche de chemin vers un but a `dist` lieux :
    (max_cost, max_nodes). Un ordre lointain ne se perd plus parce que la
    recherche s'arrete trop tot (set_goto, set_march_to_band, la poursuite) ;
    wide : l'ordre du joueur (un clic, rare : il peut chercher plus)."""
    dist = max(0, dist)
    if wide:
        return (
            dist * WIDE_COST_PER_LIEU + WIDE_COST_BASE,
            min(WIDE_NODES_MAX, WIDE_NODES_PER_D2 * dist * dist + WIDE_NODES_BASE),
        )
    return (
        dist * SEARCH_COST_PER_LIEU + SEARCH_COST_BASE,
        min(SEARCH_NODES_MAX, SEARCH_NODES_PER_D2 * dist * dist + SEARCH_NODES_BASE),
    )


def heuristic_rate(move_cost: dict, rivers: bool) -> int:
    """Le moins qu'un lieu de distance puisse couter, en milliemes : le sol
    le moins cher DE CE PEUPLE (ses savoirs : steppe 6, plaine 7 pour un
    cavalier ; revue du 2026-11-27 : 9 suppose, des chemins trop chers) au
    plus bas de sa variation (COST_VAR_MIN), les eaux du rivage, le courant
    le plus favorable avec des rivieres, et le pas en biais (racine de 3 pour
    deux pas a DIAGONAL_PER_MILLE). L'estimation d'A* ne depasse jamais le
    vrai cout : le chemin trouve est le moins cher."""
    low = min((c for c in move_cost.values() if c is not None), default=10)
    step = min(low * COST_VAR_MIN // 100, INSHORE_MOVE_COST)
    if rivers:
        step = step * min(RIVER_PCT) // 100
    # En biais : (deux pas) * 866 // 1000 pour racine de 3 lieux (1,732051 :
    # un peu plus que racine de 3, l'estimation reste dessous), en milliemes.
    diagonal = (2 * step) * DIAGONAL_PER_MILLE // 1000
    return max(0, min(step * 1000, diagonal * 1000 * 1000000 // 1732051))


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
    # Le depart peut etre infranchissable (une unite d'une vieille partie
    # restee dans l'eau ou sur un sommet) : elle doit pouvoir en sortir ; seul
    # le but doit etre franchissable (revue du 2026-11-27).
    if enter_cost_for(world, goal, water_ok, costs) is None:
        return None
    width, height, wrap = world.width, world.height, world.wrap_x
    terrains = world._terrains
    inshore = world.inshore_at
    move_cost = costs or MOVE_COST
    pct = cost_pct(world)
    rivers = bool(world._flow)
    rate = heuristic_rate(move_cost, rivers)
    goal_c, goal_r = goal_i
    goal_q = goal_c - (goal_r - (goal_r & 1)) // 2

    def heuristic(c: int, r: int) -> int:
        # La vraie distance (a vol d'oiseau ; isqrt rend le double, arrondi
        # en dessous) fois le moins cher par lieu : le chemin n'est jamais
        # plus court (le monde sans grille, 0.31.0).
        q = c - (r - (r & 1)) // 2
        dr = goal_r - r
        x = 2 * (goal_q - q) + dr
        if wrap:
            w2 = 2 * width
            x = (x + width) % w2 - width
        return math.isqrt(x * x + 3 * dr * dr) * rate // 2000

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


# La duree des trajets deja comptes (travel_weeks), gardee sur le monde : le
# trace d'un trajet la redemande a chaque image.
WEEKS_MEMO = 512


def travel_weeks(
    world: World,
    start: Hex,
    path: list[Hex],
    water_ok: bool = False,
    costs: dict | None = None,
    point: tuple[int, int] | None = None,
    aim: tuple[int, int] | None = None,
) -> int:
    """LA DUREE D'UN TRAJET, en semaines : la VRAIE marche (points.march : le
    chemin redresse, l'elan garde d'une semaine a l'autre, un pas plus cher
    qu'une semaine fait en plusieurs) rejouee sur une unite fictive partie
    de `point` (le point de l'unite ; le centre de `start` sinon) et visant
    `aim` au bout. Revue du 2026-11-27 : l'ancien compte s'arretait au
    premier pas plus cher qu'une semaine ("1 semaine" pour 21 en montagne)
    et comptait l'escalier, pas le trajet redresse. Un lieu infranchissable
    sur le chemin : les semaines jusque-la."""
    if not path:
        return 0
    # Ce qui se marche : jusqu'au premier lieu infranchissable.
    here = start
    for m, nxt in enumerate(path):
        if step_cost(world, here, nxt, water_ok, costs) is None:
            path = path[:m]
            break
        here = nxt
    if not path:
        return 0
    memo = world.__dict__.get("_weeks_memo")
    if memo is None:
        memo = world.__dict__["_weeks_memo"] = {}
    key = (
        start,
        tuple(path),
        bool(water_ok),
        None if costs is None else tuple(costs.items()),
        point,
        aim,
    )
    hit = memo.get(key)
    if hit is not None:
        return hit
    weeks = points.weeks_along(world, start, path, MOVE_POINTS_PER_WEEK, water_ok, costs, point, aim)
    if len(memo) >= WEEKS_MEMO:
        memo.clear()
    memo[key] = weeks
    return weeks
