"""LES BANDES ET LEURS PEUPLES : les outils que tous les systemes partagent.

Les bandes proches (grille de l'IA), un nouvel id, les reserves (stock_max),
le prestige gagne (gain_prestige), les savoirs d'un peuple (bonus_of), les
chemins (set_goto, set_march_to_band), combien de bandes un peuple peut
avoir (max_bands_of), se scinder (split_band), se reunir (merge_bands), les
combattants d'une bande (fighters).
Etage 5 (tools/dependances.py) : il n'importe que plus bas ; ce que les
systemes y ajoutent passe par systems.py (systems.STOCK_WEEKS).
N'importe pas pygame.
"""

from __future__ import annotations

from src.kora import population, systems, tech, units
from src.kora.gamestate import GameState, is_human, note
from src.kora.log import LogKind
from src.kora.path import astar
from src.kora.peoples import MINOR_BAND_CUT, civ_of, civ_villages
from src.kora.types import Band, Hex, Order, OrderKind, stay_order
from src.kora.world import enter_cost_for


FORAGE_RADIUS = 2
STOCK_MAX_FACTOR = 10
SPLIT_MIN_POP = 20
MAX_BANDS_PER_TRIBE = 8
GRID = 8


def build_band_grid(state: GameState) -> dict:
    grid: dict = {}
    world = state.world
    for b in state.bands.values():
        if b.population <= 0:
            continue
        idx = world._index(b.position)
        if idx is None:
            continue
        grid.setdefault((idx[0] // GRID, idx[1] // GRID), []).append(b)
    return grid


def bands_near(state: GameState, h: Hex, radius: int) -> list[Band]:
    """Bandes vivantes a `radius` cases ou moins de h (grille pendant l'IA,
    sinon parcours complet). Ordre : par id."""
    world = state.world
    grid = state.band_grid
    if grid is None:
        found = [b for b in state.bands.values() if b.population > 0 and world.distance(b.position, h) <= radius]
        found.sort(key=lambda b: b.id)
        return found
    idx = world._index(h)
    if idx is None:
        return []
    col, row = idx
    nbx = -(-world.width // GRID)
    found = []
    for by in range((row - radius) // GRID, (row + radius) // GRID + 1):
        if by < 0 or by * GRID >= world.height:
            continue
        seen_x = set()
        for bx in range((col - radius - 1) // GRID, (col + radius + 1) // GRID + 1):
            key_x = bx % nbx if world.wrap_x else bx
            if key_x in seen_x:
                continue
            seen_x.add(key_x)
            for b in grid.get((key_x, by), ()):
                if world.distance(b.position, h) <= radius:
                    found.append(b)
    found.sort(key=lambda b: b.id)
    return found


def new_band_id(state: GameState) -> int:
    # Jamais reutiliser l'id d'une bande morte : un ordre "marcher vers"
    # ou un marqueur de combat pourrait viser la mauvaise bande.
    nid = max(state.next_band_id, max(state.bands, default=0) + 1)
    state.next_band_id = nid + 1
    return nid


def is_shielded(state: GameState, band: Band) -> bool:
    return band.retreating or state.tick_count < band.shield_until


def _water_ok(state: GameState, tribe_id: int) -> bool:
    tribe = state.tribes.get(tribe_id)
    return bool(tribe and tribe.cabotage)


def _herd_ok(state: GameState, tribe_id: int) -> bool:
    tribe = state.tribes.get(tribe_id)
    return bool(tribe and tribe.troupeau)


def gain_prestige(state, tribe, amount: int) -> int:
    """Un peuple gagne du prestige (plafond 100) ; le bonus prestige_gain
    (le grand monument) le multiplie. Rend ce qui a ete gagne."""
    if tribe is None or amount <= 0:
        return 0
    mult = tech.bonuses(tribe).prestige_gain
    if mult != 1.0:
        amount = max(1, round(amount * mult))
    before = tribe.prestige
    tribe.prestige = min(100, tribe.prestige + amount)
    return tribe.prestige - before


def bonus_of(state: GameState, tribe_id: int) -> tech.Bonuses:
    tribe = state.tribes.get(tribe_id)
    return tech.bonuses(tribe) if tribe is not None else tech.NO_BONUS


def costs_of(state: GameState, tribe_id: int) -> dict:
    tribe = state.tribes.get(tribe_id)
    return tech.move_costs(tribe) if tribe is not None else tech.BASE_MOVE_COST


def _tribe_pop(state: GameState, tribe_id: int) -> int:
    return sum(
        b.population
        for b in state.bands.values()
        if b.tribe_id == tribe_id and b.population > 0
    )


def stock_max(band: Band, state: GameState | None = None) -> float:
    # Semaines de reserve : 10 de base, plus les savoirs (fumage, poterie) ;
    # un village a son grenier (villages.STORE_WEEKS, Greniers).
    if state is None:
        return STOCK_MAX_FACTOR * band.population
    know = bonus_of(state, band.tribe_id)
    weeks = know.stock_weeks
    # Le grenier d'un village, et ce que d'autres systemes y ajoutent
    # (systems.STOCK_WEEKS).
    weeks += systems.total(systems.STOCK_WEEKS, state, band)
    return weeks * band.population


def forage_hexes(state: GameState, band: Band) -> list[Hex]:
    return state.world.hexes_in_radius(band.position, FORAGE_RADIUS)


def set_goto(
    state: GameState,
    band_id: int,
    goal: Hex,
    max_nodes: int | None = None,
    max_cost: int | None = None,
) -> None:
    band = state.bands.get(band_id)
    if band is None or band.retreating or band.village or band.homebound:
        return
    goal_c = state.world.canonicalize(goal)
    water_ok = _water_ok(state, band.tribe_id)
    costs = costs_of(state, band.tribe_id)
    if goal_c is None or enter_cost_for(state.world, goal_c, water_ok, costs) is None:
        return
    if (
        band.order.kind is OrderKind.GOTO
        and band.order.target_hex == goal_c
        and band.path
    ):
        return
    dist = state.world.distance(band.position, goal_c)
    if max_nodes is None:
        max_nodes = min(1200, max(180, dist * 18 + 60))
    if max_cost is None:
        max_cost = dist * 30 + 120
    path = astar(
        state.world,
        band.position,
        goal_c,
        max_cost=max_cost,
        max_nodes=max_nodes,
        water_ok=water_ok,
        costs=costs,
    )
    if path is None:
        return
    band.order = Order(kind=OrderKind.GOTO, target_hex=goal_c)
    band.path = path


def set_march_to_band(state: GameState, band_id: int, target_band_id: int) -> None:
    if (
        band_id not in state.bands
        or target_band_id not in state.bands
        or band_id == target_band_id
    ):
        return
    band = state.bands[band_id]
    if band.retreating or band.village or band.homebound:
        return
    target = state.bands[target_band_id]
    dist = state.world.distance(band.position, target.position)
    water_ok = _water_ok(state, band.tribe_id)
    path = astar(
        state.world,
        band.position,
        target.position,
        max_cost=dist * 30 + 120,
        max_nodes=min(800, max(180, dist * 18 + 60)),
        water_ok=water_ok,
        costs=costs_of(state, band.tribe_id),
    )
    if path is None:
        return
    band.order = Order(kind=OrderKind.MARCH_TO_BAND, target_band_id=target_band_id)
    band.path = path
    if target.tribe_id != band.tribe_id:
        # Choisir d'attaquer met fin au repit d'apres-combat.
        band.shield_until = 0


def tribe_band_count(state: GameState, tribe_id: int) -> int:
    # Les troupes ne comptent pas : ce sont des guerriers, pas des clans.
    return sum(
        1
        for b in state.bands.values()
        if b.tribe_id == tribe_id and b.population > 0 and b.kind != "armee"
    )


def can_split(state: GameState, band_id: int) -> bool:
    band = state.bands.get(band_id)
    if band is None or band.population < SPLIT_MIN_POP or band.retreating or band.kind == "armee":
        return False
    if welded_left(state, band):
        return False
    return tribe_band_count(state, band.tribe_id) < max_bands_of(state, band.tribe_id)


def civ_band_cap(state: GameState, civ: int) -> int:
    """Le plafond COMMUN d'une civilisation (bandes et villages de tous ses
    peuples, le joueur compris) : celui de son peuple d'origine, selon ses
    savoirs (8, 12 avec la Chefferie ; un petit peuple 4 de moins). Le
    peuple d'origine disparu : le mieux loti de ses peuples."""
    def cap_of(t) -> int:
        cut = MINOR_BAND_CUT if t.minor and not t.origin else 0
        return bonus_of(state, t.id).max_bands - cut

    alive = {b.tribe_id for b in state.bands.values() if b.population > 0}
    root = state.tribes.get(civ)
    if root is not None and root.id in alive:
        return max(1, cap_of(root))
    members = [t for t in state.tribes.values() if t.id in alive and civ_of(state, t) == civ]
    return max(1, max((cap_of(t) for t in members), default=1))


def civ_band_count(state: GameState, civ: int) -> int:
    """Bandes (clans et villages, pas les troupes) de tous les peuples d'une
    civilisation."""
    civs: dict = {}
    n = 0
    for b in state.bands.values():
        if b.population <= 0 or b.kind == "armee":
            continue
        c = civs.get(b.tribe_id)
        if c is None:
            tribe = state.tribes.get(b.tribe_id)
            c = civs[b.tribe_id] = civ_of(state, tribe) if tribe is not None else 0
        if c == civ:
            n += 1
    return n


def max_bands_of(state: GameState, tribe_id: int) -> int:
    """Bandes que ce peuple peut avoir : les siennes, plus les places libres
    de sa civilisation (plafond commun : les peuples independants d'une
    culture le partagent avec le peuple d'origine, joueur compris)."""
    tribe = state.tribes.get(tribe_id)
    own = tribe_band_count(state, tribe_id)
    if tribe is None:
        return max(1, own)
    if settler_people(state, tribe):
        # Ne d'une civilisation qui a des villages, sans village a lui : il
        # n'a qu'a fonder le sien, il ne se divise plus en tribus.
        return max(1, own)
    civ = civ_of(state, tribe)
    free = civ_band_cap(state, civ) - civ_band_count(state, civ)
    return max(1, own + max(0, free))


def settler_people(state: GameState, tribe) -> bool:
    """Un peuple ne d'un autre (clan emancipe, secession), dont la
    civilisation a des villages, et qui n'a pas encore le sien."""
    if not tribe.origin or tribe.is_player:
        return False
    if civ_villages(state, civ_of(state, tribe)) <= 0:
        return False
    return not any(s.kind == "village" and s.tribe_id == tribe.id for s in state.sites.values())


def split_band(state: GameState, band_id: int) -> int | None:
    if not can_split(state, band_id):
        return None
    band = state.bands[band_id]
    moved = band.population // 2
    stock = band.stock * moved / band.population
    nid = new_band_id(state)
    state.bands[nid] = Band(
        nid,
        band.tribe_id,
        band.position,
        moved,
        stock,
        famine_in_period=band.famine_in_period,
    )
    population.split_wounded(band, state.bands[nid], moved, band.population)
    band.population -= moved
    band.stock -= stock
    # Ce que les systemes en font (les chefs du clan : systems.BAND_SPLIT).
    for path in systems.BAND_SPLIT:
        systems.fn(path)(state, band, state.bands[nid])
    _ai_caches_changed(state)
    if is_human(state, band.tribe_id):
        note(
            state,
            LogKind.SURVIE,
            f"La bande se scinde : {band.population} et {moved}.",
            to=band.tribe_id,
        )
    return nid


def _ai_caches_changed(state: GameState) -> None:
    if state.force_memo is not None:
        state.force_memo.clear()
    if state.band_grid is not None:
        state.band_grid = build_band_grid(state)


# Un groupe reuni n'est pas soude tout de suite (moral, pas de scission).
WELD_WEEKS = 4
WELD_MIN = 10


def welded_left(state: GameState, band: Band) -> int:
    return max(0, band.welded_until - state.tick_count)


def _absorb(state: GameState, keep: Band, gone: Band) -> None:
    if keep.kind == "armee" and gone.kind == "armee":
        # Deux troupes : une seule pile de compagnies (units.py).
        units.normalize(keep)
        for type_id, men, home in units.normalize(gone):
            units.add(keep, type_id, men, home)
        keep.population -= gone.population
        keep.raised = min(keep.raised, gone.raised)
    elif keep.kind != "armee" and gone.kind != "armee" and gone.population >= WELD_MIN:
        # Reunies pour un meme raid : elles savent pourquoi, pas de temps mort.
        if not (keep.intent_prey and keep.intent_prey == gone.intent_prey):
            keep.welded_until = max(keep.welded_until, state.tick_count + WELD_WEEKS)
    population.mix(keep, gone)
    keep.population += gone.population
    keep.stock = min(stock_max(keep, state), keep.stock + gone.stock)
    keep.famine_in_period = keep.famine_in_period or gone.famine_in_period
    keep.growth_acc += gone.growth_acc
    keep.famine_tick = max(keep.famine_tick, gone.famine_tick)
    # Ce que les systemes en font (les anciens : systems.BAND_MERGE).
    for path in systems.BAND_MERGE:
        systems.fn(path)(state, keep, gone)
    del state.bands[gone.id]
    _ai_caches_changed(state)
    for b in state.bands.values():
        if b.order.kind is OrderKind.MARCH_TO_BAND and b.order.target_band_id == gone.id:
            if b.id == keep.id:
                b.order = stay_order()
                b.path = []
            else:
                b.order = Order(kind=OrderKind.MARCH_TO_BAND, target_band_id=keep.id)


# Regrouper sans compter les cases : les bandes proches se reunissent tout de
# suite, celles un peu plus loin viennent a pied (resolve_joins).
MERGE_NEAR = 2
MERGE_CALL = 5


def merge_mates(state: GameState, band: Band, radius: int = MERGE_CALL) -> list:
    """Bandes de son peuple, du meme genre (clan / troupe), qui obeissent et
    sont a `radius` cases ou moins."""
    world = state.world
    return sorted(
        (
            b
            for b in state.bands.values()
            if b.id != band.id
            and b.tribe_id == band.tribe_id
            and b.population > 0
            and not b.retreating
            and not b.homebound
            and (b.kind == "armee") == (band.kind == "armee")
            and all(systems.fn(path)(state, b) for path in systems.MERGE_ALLOWED)
            and world.distance(b.position, band.position) <= radius
        ),
        key=lambda b: (world.distance(b.position, band.position), b.id),
    )


def merge_bands(state: GameState, band_id: int) -> int:
    """Reunir [F] : les bandes proches rejoignent celle-ci (son chef mene) ;
    un village accueille les bandes de sa case ou d'a cote. Rend le nombre
    de bandes reunies ou en route."""
    band = state.bands.get(band_id)
    if band is None or band.retreating or band.homebound:
        return 0
    mates = merge_mates(state, band)
    keep = band
    # Sur son village (ou juste a cote), c'est le village qui accueille.
    home = next((b for b in mates if b.village and state.world.distance(b.position, band.position) <= 1), None)
    if home is not None and not band.village:
        keep = home
        mates = [b for b in mates if b is not home] + [band]
    elif not band.village:
        # Loin de la case, un village ne vient pas : on ne le compte pas.
        mates = [b for b in mates if not b.village]
    near = [m for m in mates if m.village == 0 and state.world.distance(m.position, keep.position) <= MERGE_NEAR]
    if keep is not band and band not in near:
        near.append(band)
    far = [m for m in mates if m not in near and not m.village]
    names = [m.leader.name for m in near if m.leader is not None]
    for mate in near:
        _absorb(state, keep, mate)
    for mate in far:
        set_march_to_band(state, mate.id, keep.id)
    walking = [m for m in far if m.order.kind is OrderKind.MARCH_TO_BAND]
    if is_human(state, keep.tribe_id):
        if near:
            note(state, LogKind.SURVIE, merge_text(keep, names), to=keep.tribe_id)
        if walking:
            n = len(walking)
            note(state, LogKind.SURVIE, f"{n} bande{'s' if n > 1 else ''} proche{'s' if n > 1 else ''} vien{'nent' if n > 1 else 't'} vous rejoindre.", keep.position, to=keep.tribe_id)
    return len(near) + len(walking)


def merge_text(band: Band, names: list) -> str:
    lead = band.leader.name if band.leader is not None else "la bande"
    if band.kind == "armee":
        return f"Troupes réunies sous {lead} : {band.population} guerriers."
    if not names:
        return f"Bandes réunies : {band.population} personnes."
    who = ", ".join(names)
    return f"Bandes réunies sous {lead} : {band.population} personnes ; {who} rejoint les anciens du clan."


# Un clan se bat avec ses adultes valides, pas avec ses familles ; une
# troupe (villages.py) se bat tout entiere.
CLAN_SHARE = 0.4


def is_army(band: Band) -> bool:
    return band.kind == "armee"


def fighters(band: Band) -> float:
    """Ceux qui se battent : les hommes valides d'un clan (population.py),
    toute une troupe sauf ses blesses."""
    return population.men_force(band)
