import json
from pathlib import Path

from src.kora import resources as _res
from src.kora.types import Hex, Season, Terrain

INSHORE_MOVE_COST = 10

MOVE_COST = {
    Terrain.PLAINE: 10,
    Terrain.VALLEE: 10,
    Terrain.STEPPE: 10,
    Terrain.FORET: 20,
    Terrain.COLLINE: 15,
    Terrain.MONTAGNE: 60,
    Terrain.COTE: 12,
    Terrain.DESERT: 11,
}

BIOME_INDEX = {
    Terrain.PLAINE: 1.0,
    Terrain.VALLEE: 1.4,
    Terrain.STEPPE: 0.7,
    Terrain.FORET: 0.9,
    Terrain.COLLINE: 0.6,
    Terrain.MONTAGNE: 0.2,
    Terrain.COTE: 0.8,
    Terrain.DESERT: 0.35,
    Terrain.SOMMET: 0.0,
    Terrain.EAU: 0.0,
}

NEIGHBOR_DELTAS = (
    (1, 0),
    (1, -1),
    (0, -1),
    (-1, 0),
    (-1, 1),
    (0, 1),
)

WIDTH = 384
HEIGHT = 192
CHAR_TO_TERRAIN = {
    "P": Terrain.PLAINE,
    "V": Terrain.VALLEE,
    "S": Terrain.STEPPE,
    "F": Terrain.FORET,
    "C": Terrain.COLLINE,
    "M": Terrain.MONTAGNE,
    "X": Terrain.SOMMET,
    "E": Terrain.EAU,
    "O": Terrain.COTE,
    "D": Terrain.DESERT,
}
TERRAIN_TO_CHAR = {v: k for k, v in CHAR_TO_TERRAIN.items()}


# Deux caches de disques : petits rayons (collecte, rayon 2) et grands
# rayons (vision 16, recherches de l'IA), chacun borne en nombre d'entrees.
RADIUS_CACHE_MAX = 4
RADIUS_CACHE_SIZE = 40000
BIG_RADIUS_CACHE_SIZE = 3000
_RADIUS_DELTAS: dict[int, list[tuple[int, int]]] = {}


def _radius_deltas(radius: int) -> list[tuple[int, int]]:
    deltas = _RADIUS_DELTAS.get(radius)
    if deltas is None:
        deltas = [
            (dq, dr)
            for dq in range(-radius, radius + 1)
            for dr in range(-radius, radius + 1)
            if (abs(dq) + abs(dq + dr) + abs(dr)) // 2 <= radius
        ]
        _RADIUS_DELTAS[radius] = deltas
    return deltas


def offset_to_axial(col: int, row: int) -> Hex:
    q = col - (row - (row & 1)) // 2
    r = row
    return Hex(q, r)


def axial_to_offset(h: Hex) -> tuple[int, int]:
    col = h.q + (h.r - (h.r & 1)) // 2
    row = h.r
    return col, row


def hex_distance(a: Hex, b: Hex) -> int:
    return (abs(a.q - b.q) + abs(a.q + a.r - b.q - b.r) + abs(a.r - b.r)) // 2


def hex_neighbors(h: Hex) -> list[Hex]:
    return [Hex(h.q + dq, h.r + dr) for dq, dr in NEIGHBOR_DELTAS]


def is_passable(terrain: Terrain) -> bool:
    return terrain in MOVE_COST


def enter_cost(terrain: Terrain) -> int | None:
    return MOVE_COST.get(terrain)


def hex_distance_wrapped(a: Hex, b: Hex, width: int, wrap_x: bool) -> int:
    best = hex_distance(a, b)
    if not wrap_x:
        return best
    _bc, br = axial_to_offset(b)
    for dc in (-width, width):
        shifted = offset_to_axial(_bc + dc, br)
        best = min(best, hex_distance(a, shifted))
    return best


class World:
    def __init__(self, terrains: list[list[Terrain]], wrap_x: bool = False):
        self._terrains = terrains
        self.height = len(terrains)
        self.width = len(terrains[0]) if terrains else 0
        self.wrap_x = wrap_x
        self._exhaustion = [
            [1.0 for _ in range(self.width)] for _ in range(self.height)
        ]
        self._influence: dict[tuple[int, int], dict[int, float]] = {}
        self._influence_cells: set[tuple[int, int]] = set()
        # Compteur de mises a jour de la zone d'influence (cache du rendu).
        self._influence_gen = 0
        # Ressources du pays : nom -> octets 0..255 (voir resources.py) ;
        # _rich : bonus de collecte de chaque case (vide sans ressources).
        self.resources: dict = {}
        self._rich = b""
        self._res_near: dict = {}
        self._lands: dict = {}
        self._recovering: set[tuple[int, int]] = set()
        self._hex_season = [[0 for _ in range(self.width)] for _ in range(self.height)]
        self._aimed_season = Season.PRINTEMPS
        self._season_frontier: list[int] = []
        self._season_gen = 0
        self._radius_cache: dict = {}
        self._big_radius_cache: dict = {}
        self._inshore_memo: dict[tuple[int, int], bool] = {}

    def canonicalize(self, h: Hex) -> Hex | None:
        col, row = axial_to_offset(h)
        if row < 0 or row >= self.height:
            return None
        if self.wrap_x:
            col %= self.width
        elif col < 0 or col >= self.width:
            return None
        return offset_to_axial(col, row)

    def _index(self, h: Hex) -> tuple[int, int] | None:
        # Meme resultat que axial_to_offset(canonicalize(h)), sans creer
        # de Hex intermediaire (c'est l'appel le plus frequent du jeu).
        row = h.r
        if row < 0 or row >= self.height:
            return None
        col = h.q + (row - (row & 1)) // 2
        if self.wrap_x:
            col %= self.width
        elif col < 0 or col >= self.width:
            return None
        return col, row

    def in_bounds(self, h: Hex) -> bool:
        return self._index(h) is not None

    def neighbors(self, h: Hex) -> list[Hex]:
        found: list[Hex] = []
        for nb in hex_neighbors(h):
            wrapped = self.canonicalize(nb)
            if wrapped is not None:
                found.append(wrapped)
        return found

    def distance(self, a: Hex, b: Hex) -> int:
        # Meme calcul que hex_distance_wrapped(canonicalize(a), canonicalize(b)),
        # en entiers, sans Hex intermediaires.
        ia = self._index(a)
        ib = self._index(b)
        if ia is None or ib is None:
            return 10**9
        ca, ra = ia
        cb, rb = ib
        qa = ca - (ra - (ra & 1)) // 2
        sa = -qa - ra
        half_b = (rb - (rb & 1)) // 2
        qb = cb - half_b
        dr = abs(ra - rb)
        best = (abs(qa - qb) + abs(sa + qb + rb) + dr) // 2
        if self.wrap_x:
            for shift in (-self.width, self.width):
                qs = cb + shift - half_b
                d = (abs(qa - qs) + abs(sa + qs + rb) + dr) // 2
                if d < best:
                    best = d
        return best

    def terrain(self, h: Hex) -> Terrain:
        idx = self._index(h)
        if idx is None:
            return Terrain.EAU
        col, row = idx
        return self._terrains[row][col]

    def passable(self, h: Hex) -> bool:
        return self.in_bounds(h) and is_passable(self.terrain(h))

    def enter_cost_hex(self, h: Hex) -> int | None:
        # Hors carte, terrain() rend EAU : pas de cout, comme avant.
        return MOVE_COST.get(self.terrain(h))

    def biome_index(self, h: Hex) -> float:
        if not self.in_bounds(h):
            return 0.0
        return BIOME_INDEX[self.terrain(h)]

    def hexes_in_radius(self, center: Hex, radius: int) -> list[Hex]:
        """Liste partagee (cache) : ne pas la modifier."""
        return self.hexes_and_distances(center, radius)[0]

    def hexes_and_distances(
        self, center: Hex, radius: int
    ) -> tuple[list[Hex], list[int]]:
        """Disque autour de center + distance de chaque case au centre,
        dans le meme ordre. Listes partagees (cache) : ne pas les modifier."""
        origin = self.canonicalize(center)
        if origin is None:
            return [], []
        key = (origin, radius)
        small = radius <= RADIUS_CACHE_MAX
        cache = self._radius_cache if small else self._big_radius_cache
        cached = cache.get(key)
        if cached is not None:
            return cached
        found: list[Hex] = []
        dists: list[int] = []
        width, height, wrap = self.width, self.height, self.wrap_x
        # Sans wrap, ou si la carte est plus large que le disque, deux
        # decalages differents ne tombent jamais sur la meme case, et la
        # distance du decalage est la vraie distance.
        narrow = wrap and width <= 2 * radius
        seen: set[Hex] = set()
        q0, r0 = origin.q, origin.r
        for dq, dr in _radius_deltas(radius):
            row = r0 + dr
            if row < 0 or row >= height:
                continue
            half = (row - (row & 1)) // 2
            col = q0 + dq + half
            if wrap:
                col %= width
            elif col < 0 or col >= width:
                continue
            h = Hex(col - half, row)
            if narrow:
                if h in seen:
                    continue
                seen.add(h)
                dists.append(self.distance(origin, h))
            else:
                dists.append((abs(dq) + abs(dq + dr) + abs(dr)) // 2)
            found.append(h)
        limit = RADIUS_CACHE_SIZE if small else BIG_RADIUS_CACHE_SIZE
        if len(cache) >= limit:
            # On oublie le quart le plus ancien (vider tout d'un coup faisait
            # tout recalculer au tick suivant).
            for old in list(cache)[: limit // 4]:
                del cache[old]
        cache[key] = (found, dists)
        return found, dists

    def inshore_at(self, col: int, row: int) -> bool:
        # Eau touchee par de la terre (memo : la carte ne change pas en jeu).
        key = (col, row)
        hit = self._inshore_memo.get(key)
        if hit is None:
            hit = False
            if self._terrains[row][col] is Terrain.EAU:
                for nb in self.neighbors(offset_to_axial(col, row)):
                    nc, nr = axial_to_offset(nb)
                    if self._terrains[nr][nc] is not Terrain.EAU:
                        hit = True
                        break
            self._inshore_memo[key] = hit
        return hit

    # --- ressources du pays (voir resources.py) ------------------------------

    def set_resources(self, layers: dict, rich: bytes | None = None) -> None:
        """layers : nom -> octets 0..255 (rangee par rangee)."""
        from src.kora.resources import NAMES, richness

        n = self.width * self.height
        self.resources = {k: bytes(v) for k, v in layers.items() if k in NAMES and len(v) == n}
        if rich is None or len(rich) != n:
            rich = richness(self.resources, self.width, self.height)
        self._rich = bytes(rich)
        self._res_near = {}
        self._lands = {}

    def resource(self, h: Hex, name: str) -> float:
        layer = self.resources.get(name)
        idx = self._index(h)
        if layer is None or idx is None:
            return 0.0
        col, row = idx
        return layer[row * self.width + col] / 255.0

    def resources_near(self, h: Hex) -> frozenset:
        """Ressources presentes (0,4 et plus) sur la case ou juste a cote."""
        idx = self._index(h)
        if idx is None or not self.resources:
            return frozenset()
        memo = self._res_near
        hit = memo.get(idx)
        if hit is not None:
            return hit
        from src.kora.resources import PRESENT_BYTE

        found = set()
        width = self.width
        for x in self.hexes_in_radius(h, 1):
            col, row = self._index(x)
            i = row * width + col
            for name, layer in self.resources.items():
                if layer[i] >= PRESENT_BYTE:
                    found.add(name)
        out = frozenset(found)
        if len(memo) > 200_000:
            memo.clear()
        memo[idx] = out
        return out

    def resource_lines(self, h: Hex) -> list[str]:
        from src.kora.resources import LABELS, NAMES, level_word

        parts = []
        for name in NAMES:
            v = self.resource(h, name)
            word = level_word(v)
            if word:
                parts.append((v, f"{LABELS[name]} ({word})"))
        if not parts:
            return []
        parts.sort(key=lambda it: -it[0])
        return ["Ressources : " + ", ".join(p for _v, p in parts[:4])]

    def exhaustion_snapshot(self) -> dict[tuple[int, int], float]:
        # Hors de _recovering, l'epuisement vaut 1.0 (set_exhaustion le garantit).
        grid = self._exhaustion
        return {(c, r): grid[r][c] for c, r in self._recovering}

    def exhaustion_restore(self, saved: dict[tuple[int, int], float]) -> None:
        grid = self._exhaustion
        for c, r in self._recovering:
            grid[r][c] = 1.0
        for (c, r), value in saved.items():
            grid[r][c] = value
        self._recovering = set(saved)

    def exhaustion(self, h: Hex) -> float:
        idx = self._index(h)
        if idx is None:
            return 1.0
        col, row = idx
        return self._exhaustion[row][col]

    def set_exhaustion(self, h: Hex, value: float) -> None:
        idx = self._index(h)
        if idx is None:
            return
        col, row = idx
        self._exhaustion[row][col] = min(1.0, max(0.5, value))
        if self._exhaustion[row][col] < 1.0:
            self._recovering.add((col, row))
        else:
            self._recovering.discard((col, row))

    def influence(self, h: Hex, tribe_id: int) -> float:
        idx = self._index(h)
        if idx is None:
            return 0.0
        cell = self._influence.get(idx)
        if not cell:
            return 0.0
        return cell.get(tribe_id, 0.0)

    def add_influence(self, h: Hex, tribe_id: int, delta: float) -> None:
        idx = self._index(h)
        if idx is None:
            return
        cell = self._influence.setdefault(idx, {})
        cell[tribe_id] = min(1.0, cell.get(tribe_id, 0.0) + delta)
        self._influence_cells.add(idx)

    def scale_all_influence(self, factor: float) -> None:
        empty: list[tuple[int, int]] = []
        for key in list(self._influence_cells):
            cell = self._influence.get(key)
            if not cell:
                empty.append(key)
                continue
            for tid in list(cell):
                cell[tid] *= factor
                if cell[tid] < 0.0001:
                    del cell[tid]
            if not cell:
                empty.append(key)
        for key in empty:
            self._influence.pop(key, None)
            self._influence_cells.discard(key)

    def hex_season(self, h: Hex) -> Season:
        idx = self._index(h)
        if idx is None:
            return Season.PRINTEMPS
        col, row = idx
        return _INDEX_SEASON[self._hex_season[row][col]]

    def fill_season(self, season: Season) -> None:
        code = _SEASON_INDEX[season]
        self._hex_season = [[code for _ in range(self.width)] for _ in range(self.height)]
        self._aimed_season = season
        self._season_frontier = []
        self._season_gen += 1

    # La saison part toujours de rangees entieres (poles ou equateur) et
    # chaque hex touche les rangees voisines : le front avance donc par
    # rangees entieres. On le stocke comme une liste de rangees.
    def _row_is(self, row: int, code: int) -> bool:
        return self._hex_season[row].count(code) == self.width

    def seed_season(self, season: Season) -> None:
        code = _SEASON_INDEX[season]
        if season in (Season.HIVER, Season.AUTOMNE):
            rows = {0, max(0, self.height - 1)}
        else:
            mid = self.height // 2
            rows = {mid}
            if mid > 0:
                rows.add(mid - 1)
            if mid + 1 < self.height:
                rows.add(mid + 1)
        for row in rows:
            self._hex_season[row] = [code] * self.width
        self._aimed_season = season
        self._season_frontier = sorted(rows)
        self._season_gen += 1

    def rebuild_season_frontier(self) -> None:
        code = _SEASON_INDEX[self._aimed_season]
        frontier: list[int] = []
        for row in range(self.height):
            if not self._row_is(row, code):
                continue
            for nr in (row - 1, row + 1):
                if 0 <= nr < self.height and not self._row_is(nr, code):
                    frontier.append(row)
                    break
        self._season_frontier = frontier

    def spread_season(self, target: Season, steps: int | None = None) -> int:
        code = _SEASON_INDEX[target]
        if steps is None:
            steps = max(8, self.height // 16)
        frontier = list(self._season_frontier)
        changed = 0
        for _ in range(steps):
            nxt: list[int] = []
            for row in frontier:
                for nr in (row - 1, row + 1):
                    if nr < 0 or nr >= self.height or nr in nxt:
                        continue
                    line = self._hex_season[nr]
                    left = self.width - line.count(code)
                    if left == 0:
                        continue
                    self._hex_season[nr] = [code] * self.width
                    nxt.append(nr)
                    changed += left
            frontier = nxt
            if not frontier:
                break
        self._season_frontier = frontier
        if changed:
            self._season_gen += 1
        return changed


def is_inshore(world: World, h: Hex) -> bool:
    idx = world._index(h)
    if idx is None:
        return False
    return world.inshore_at(*idx)


def enter_cost_for(world: World, h: Hex, water_ok: bool, costs: dict | None = None) -> int | None:
    # costs : couts de marche de la tribu (savoirs) ; par defaut MOVE_COST.
    idx = world._index(h)
    if idx is None:
        return None
    col, row = idx
    cost = (costs or MOVE_COST).get(world._terrains[row][col])
    if cost is not None or not water_ok:
        return cost
    return INSHORE_MOVE_COST if world.inshore_at(col, row) else None


_SEASON_INDEX = {
    Season.PRINTEMPS: 0,
    Season.ETE: 1,
    Season.AUTOMNE: 2,
    Season.HIVER: 3,
}
_INDEX_SEASON = (
    Season.PRINTEMPS,
    Season.ETE,
    Season.AUTOMNE,
    Season.HIVER,
)
SEASONS_BY_CODE = _INDEX_SEASON


def make_filled_world(
    width: int, height: int, terrain: Terrain, wrap_x: bool = False
) -> World:
    grid = [[terrain for _ in range(width)] for _ in range(height)]
    return World(grid, wrap_x=wrap_x)


def generate_world(seed: int = 42, width: int | None = None, height: int | None = None) -> World:
    from src.kora.mapgen import PLANET_HEIGHT, PLANET_WIDTH
    from src.kora.mapgen import generate_world as _gen

    return _gen(
        seed,
        PLANET_WIDTH if width is None else width,
        PLANET_HEIGHT if height is None else height,
    )


def paint_kora() -> World:
    return generate_world(seed=42)


def _polar_ice(world: World, col: int, row: int) -> bool:
    if world.height <= 1:
        return False
    lat = abs((row / (world.height - 1)) * 2.0 - 1.0)
    return lat > 0.80 and world._terrains[row][col] is Terrain.SOMMET


def landmass_grid(world: World) -> list[list[int]]:
    ids = [[0] * world.width for _ in range(world.height)]
    next_id = 1
    for row in range(world.height):
        for col in range(world.width):
            if ids[row][col] or world._terrains[row][col] is Terrain.EAU:
                continue
            if _polar_ice(world, col, row):
                continue
            stack = [(col, row)]
            ids[row][col] = next_id
            while stack:
                c, r = stack.pop()
                for nb in world.neighbors(offset_to_axial(c, r)):
                    nc, nr = axial_to_offset(nb)
                    if ids[nr][nc] or world._terrains[nr][nc] is Terrain.EAU:
                        continue
                    if _polar_ice(world, nc, nr):
                        continue
                    ids[nr][nc] = next_id
                    stack.append((nc, nr))
            next_id += 1
    return ids


def same_landmass(world: World, a: Hex, b: Hex) -> bool:
    ga = world.canonicalize(a)
    gb = world.canonicalize(b)
    if ga is None or gb is None:
        return False
    grid = landmass_grid(world)
    ca, ra = axial_to_offset(ga)
    cb, rb = axial_to_offset(gb)
    ia, ib = grid[ra][ca], grid[rb][cb]
    return ia > 0 and ia == ib


def spawn_forage(world: World, h: Hex) -> float:
    # Nourriture de printemps dans le rayon de collecte (2), sans epuisement.
    return sum(2.0 * BIOME_INDEX[world.terrain(x)] for x in world.hexes_in_radius(h, 2))


def pick_spawn_hexes(
    world: World,
    count: int,
    prefs: list | None = None,
    min_forage: float | list = 0.0,
) -> list[Hex]:
    """Un depart par tribu. prefs[i] : terrains voulus pour le depart i.
    min_forage : nourriture de printemps minimale autour du depart
    (un nombre, ou un nombre par depart).
    Chaque exigence est relachee si la carte ne permet pas mieux."""
    preferred = (
        Terrain.VALLEE,
        Terrain.PLAINE,
        Terrain.COTE,
        Terrain.STEPPE,
        Terrain.FORET,
    )
    lo = int(world.height * 0.32)
    hi = int(world.height * 0.68)
    candidates: list[Hex] = []
    for row in range(lo, hi):
        for col in range(world.width):
            h = offset_to_axial(col, row)
            if world.terrain(h) in preferred and world.passable(h):
                candidates.append(h)
    if not candidates:
        for row in range(world.height):
            for col in range(world.width):
                h = offset_to_axial(col, row)
                if world.passable(h):
                    candidates.append(h)
    if not candidates:
        return [offset_to_axial(world.width // 2, world.height // 2)] * count
    grid = landmass_grid(world)

    def mass_id(h: Hex) -> int:
        col, row = axial_to_offset(h)
        if row < 0 or row >= world.height or col < 0 or col >= world.width:
            return 0
        return grid[row][col]

    by_mass: dict[int, list[Hex]] = {}
    for h in candidates:
        mid = mass_id(h)
        if mid <= 0:
            continue
        by_mass.setdefault(mid, []).append(h)
    pools = by_mass if by_mass else {1: candidates}
    home = max(pools, key=lambda k: (len(pools[k]) >= 2, len(pools[k])))
    min_sep = max(12, world.width // (count * 2))
    # Le voisin du meme continent part hors de vue (rayon 16) si la carte
    # est assez grande : on le decouvre en explorant.
    mate_sep = max(6, min(min_sep, 24))
    chosen: list[Hex] = []
    forage_cache: dict[Hex, float] = {}

    def fed(h: Hex, need: float) -> bool:
        if need <= 0:
            return True
        if h not in forage_cache:
            forage_cache[h] = spawn_forage(world, h)
        return forage_cache[h] >= need

    def pick(pool: list[Hex], sep: int, want, need: float, spread=True) -> Hex | None:
        step = max(1, len(pool) // 64) if spread else 1
        for scan in (pool[::step], pool):
            for h in scan:
                if h in chosen:
                    continue
                if want and world.terrain(h) not in want:
                    continue
                if not fed(h, need):
                    continue
                if all(world.distance(h, o) >= sep for o in chosen):
                    return h
        return None

    home_pool = pools[home]
    others = [h for h in candidates if mass_id(h) != home] or candidates
    for slot in range(count):
        pool = home_pool if slot < 2 else others
        sep = mate_sep if slot == 1 else min_sep
        want = prefs[slot] if prefs and slot < len(prefs) else None
        need = (
            min_forage[slot] if isinstance(min_forage, list) else min_forage
        )
        found = None
        spread = True
        if slot == 1 and chosen:
            # Le voisin : la case convenable la plus proche au-dela de
            # mate_sep (hors de vue, mais a quelques semaines de marche).
            pool = sorted(pool, key=lambda h: world.distance(h, chosen[0]))
            spread = False
        # Le continent compte plus que la nourriture, la nourriture plus
        # que le biome.
        for p in (pool, candidates):
            for w, food in ((want, need), (None, need), (want, 0.0), (None, 0.0)):
                found = pick(p, sep, w, food, spread if p is pool else True)
                if found is not None:
                    break
            if found is not None:
                break
        if found is None:
            found = pick(candidates, 2, None, 0.0)
        if found is None:
            break
        chosen.append(found)
    guard = 0
    while len(chosen) < count and candidates:
        h = candidates[guard % len(candidates)]
        if h not in chosen:
            chosen.append(h)
        guard += 1
        if guard > len(candidates) * 2:
            chosen.append(candidates[0])
            break
    return chosen[:count]


def save_world(world: World, path: Path, labels: list | None = None) -> None:
    rows = []
    for row in range(world.height):
        chars = []
        for col in range(world.width):
            t = world._terrains[row][col]
            chars.append(TERRAIN_TO_CHAR[t])
        rows.append("".join(chars))
    path.parent.mkdir(parents=True, exist_ok=True)
    payload = {
        "width": world.width,
        "height": world.height,
        "wrap_x": world.wrap_x,
        "rows": rows,
        # Noms de l'atlas precalcules (donnee de carte, comme les biomes).
        "labels": [[lab.name, lab.col, lab.row, lab.kind] for lab in labels or []],
    }
    if world.resources:
        # Ressources du pays : octets compresses (zlib + base64).
        payload["resources"] = {k: _res.encode(v) for k, v in world.resources.items()}
        payload["richness"] = _res.encode(world._rich)
    path.write_text(json.dumps(payload), encoding="utf-8")


def load_world(path: Path) -> World:
    data = json.loads(Path(path).read_text(encoding="utf-8"))
    grid = []
    for line in data["rows"]:
        grid.append([CHAR_TO_TERRAIN[ch] for ch in line])
    world = World(grid, wrap_x=bool(data.get("wrap_x", False)))
    if isinstance(data.get("resources"), dict):
        layers = {k: _res.decode(v) for k, v in data["resources"].items()}
        rich = _res.decode(data["richness"]) if data.get("richness") else None
        world.set_resources(layers, rich)
    if data.get("labels"):
        from src.kora.atlas import AtlasLabel

        world.atlas = [
            AtlasLabel(str(n), float(c), float(r), str(k)) for n, c, r, k in data["labels"]
        ]
    return world


def season_multiplier(terrain: Terrain, season: Season, herd: bool = False) -> float:
    if season is Season.PRINTEMPS:
        base = 1.0
    elif season is Season.ETE:
        base = 1.2
    elif season is Season.AUTOMNE:
        base = 0.9
    else:
        base = 0.35
    if season is Season.HIVER and terrain in (Terrain.COLLINE, Terrain.MONTAGNE):
        return 0.20
    if herd and terrain is Terrain.STEPPE:
        if season is Season.PRINTEMPS:
            return 1.35
        if season is Season.ETE:
            return 1.65
        if season is Season.AUTOMNE:
            return 1.50
        if season is Season.HIVER:
            return 1.50
    return base


_FOOD_BASE: dict[tuple[Terrain, Season, bool], tuple[float, float]] = {}
# Un cran de _rich (0..255) en part de nourriture en plus.
_RICH_STEP = (_res.RICH_GAME + _res.RICH_PLANT + _res.RICH_FISH) / 255.0


def food_production(
    world: World,
    h: Hex,
    season: Season,
    herd: bool = False,
    exhaustion: float | None = None,
    bonus=None,
) -> float:
    """Nourriture d'une case par semaine. bonus : tech.Bonuses de la tribu
    qui collecte (savoirs) ; None = jeu de base."""
    idx = world._index(h)
    if idx is None:
        return 0.0
    col, row = idx
    t = world._terrains[row][col]
    exh = world._exhaustion[row][col] if exhaustion is None else exhaustion
    key = (t, season, herd)
    base = _FOOD_BASE.get(key)
    if base is None:
        # Meme ordre d'operations que la formule d'origine : memes flottants.
        base = _FOOD_BASE[key] = (2.0 * BIOME_INDEX[t], season_multiplier(t, season, herd))
    value = base[0] * base[1] * exh
    rich = world._rich
    if rich:
        # Gibier, plantes et poisson du pays (resources.py).
        value *= 1.0 + rich[row * world.width + col] * _RICH_STEP
    if bonus is None:
        return value
    if t is Terrain.EAU:
        # Peche : l'eau pres des rives nourrit un peu (plus la ou il y a du poisson).
        if bonus.water_food and world.inshore_at(col, row):
            fish = 1.0
            layer = world.resources.get("poisson")
            if layer:
                fish = 0.7 + 0.6 * layer[row * world.width + col] / 255.0
            return 2.0 * bonus.water_food * season_multiplier(Terrain.PLAINE, season) * exh * fish
        return value
    mult = bonus.food.get(t)
    if mult is not None:
        value *= mult
    if season is Season.HIVER and t in (Terrain.COLLINE, Terrain.MONTAGNE):
        value *= bonus.winter_hills
    return value
