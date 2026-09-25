import heapq

from src.kora.types import Hex
from src.kora.world import (
    INSHORE_MOVE_COST,
    MOVE_COST,
    NEIGHBOR_DELTAS,
    World,
    enter_cost_for,
)

# Le monde est grand : 4 cases de plaine par semaine (cout 10).
MOVE_POINTS_PER_WEEK = 40


def astar(
    world: World,
    start: Hex,
    goal: Hex,
    max_cost: int | None = None,
    max_nodes: int | None = None,
    water_ok: bool = False,
    costs: dict | None = None,
) -> list[Hex] | None:
    # A* sur des cases entieres (col, row) : memes voisins dans le meme ordre
    # que World.neighbors, meme cout, meme heuristique, meme departage
    # (compteur seq), donc exactement les memes chemins, sans objets Hex
    # pendant la recherche.
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
    # Heuristique 10 x distance : valable tant qu'aucun cout n'est sous 10.
    move_cost = costs or MOVE_COST
    goal_c, goal_r = goal_i
    goal_q = goal_c - (goal_r - (goal_r & 1)) // 2
    goal_s = -goal_q - goal_r
    goal_shift = (goal_c - width - (goal_r - (goal_r & 1)) // 2, goal_c + width - (goal_r - (goal_r & 1)) // 2)

    def heuristic(c: int, r: int) -> int:
        q = c - (r - (r & 1)) // 2
        s = -q - r
        dr = abs(r - goal_r)
        best = (abs(q - goal_q) + abs(s - goal_s) + dr) // 2
        if wrap:
            for gq in goal_shift:
                d = (abs(q - gq) + abs(s + gq + goal_r) + dr) // 2
                if d < best:
                    best = d
        return best * 10

    start_key = start_i[1] * width + start_i[0]
    goal_key = goal_r * width + goal_c
    open_heap: list[tuple[int, int, int]] = [(0, 0, start_key)]
    seq = 0
    came: dict[int, int] = {}
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
        for dq, dr in NEIGHBOR_DELTAS:
            nr = cr + dr
            if nr < 0 or nr >= height:
                continue
            nc = cq + dq + (nr - (nr & 1)) // 2
            if wrap:
                nc %= width
            elif nc < 0 or nc >= width:
                continue
            cost = move_cost.get(terrains[nr][nc])
            if cost is None:
                if not water_ok or not inshore(nc, nr):
                    continue
                cost = INSHORE_MOVE_COST
            tentative = g_cur + cost
            if max_cost is not None and tentative > max_cost:
                continue
            key = nr * width + nc
            if tentative < g.get(key, 10**9):
                came[key] = current
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
    for nxt in path:
        cost = enter_cost_for(world, nxt, water_ok, costs)
        if cost is None:
            return weeks
        if points < cost:
            weeks += 1
            points += MOVE_POINTS_PER_WEEK
            if points < cost:
                return weeks
        points -= cost
    return weeks
