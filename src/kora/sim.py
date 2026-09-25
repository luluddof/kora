from __future__ import annotations

import copy
import functools
import json
import math
import random
import sys
from dataclasses import dataclass, field
from pathlib import Path

from src.kora import chiefs, diplo, events, goods, influence, sites, tech
from src.kora.clock import Clock
from src.kora.diplo import Diplomacy
from src.kora.log import GameLog, LogKind, season_fr, terrain_fr
from src.kora.path import MOVE_POINTS_PER_WEEK, astar, travel_weeks
from src.kora.types import (
    Band,
    FightMark,
    Hex,
    Order,
    OrderKind,
    Season,
    Terrain,
    Tribe,
    stay_order,
)
from src.kora.world import World, enter_cost_for, food_production, offset_to_axial

PLAYER_TRIBE_ID = 1
AI_STEPPE_ID = 2
AI_FOREST_ID = 3
AI_COAST_ID = 4
FORAGE_RADIUS = 2
STOCK_MAX_FACTOR = 10
COMBAT_MARK_WEEKS = 26
COMBAT_MARK_MAX = 8
# Famine progressive : part de la bande qui meurt par semaine
# = part de nourriture manquante x FAMINE_RATE (minimum 1 mort).
FAMINE_RATE = 0.15
# Le prestige d'hiver ne regarde que les 4 dernieres semaines de l'hiver.
WINTER_TAIL_WEEK = 49
# Par mois ; une partie longue : les peuples grandissent lentement.
GROWTH_RATE = 0.018
SPLIT_MIN_POP = 20
MAX_BANDS_PER_TRIBE = 8
REINFORCE_RADIUS = 2
# Repli apres une defaite : la bande marche (pas de teleportation) vers
# une bande amie, sinon vers une case sure et nourriciere. Pendant le
# repli elle n'obeit plus et ne peut pas etre attaquee.
RETREAT_ALLY_RANGE = 30
RETREAT_SEARCH_RADIUS = 12
RETREAT_SAFE_DIST = 16
RETREAT_MIN_SHIELD = 4


@dataclass
class GameState:
    world: World
    clock: Clock
    tribes: dict[int, Tribe]
    bands: dict[int, Band]
    tick_count: int = 0
    rng: random.Random = field(default_factory=lambda: random.Random(1))
    last_error: str | None = None
    player_dead: bool = False
    last_pressure: dict[Hex, float] = field(default_factory=dict)
    vision: object | None = None
    log: GameLog = field(default_factory=GameLog)
    seen_enemy_tribes: set[int] = field(default_factory=set)
    fights: list = field(default_factory=list)
    next_band_id: int = 0
    # Positions deja examinees pour "rivage / steppe en vue" (la carte ne
    # change pas) : cache, pas sauvegarde.
    scan_memo: set = field(default_factory=set)
    # Hasard du recit (noms, evenements, chefs), separe de celui de l'IA :
    # ajouter une histoire ne change pas les choix de marche des bandes.
    story_rng: random.Random = field(default_factory=lambda: random.Random(7))
    next_tribe_id: int = 0
    # Zone d'influence : presences de la semaine (influence.py), cases
    # partagees entre deux peuples (recalcule chaque mois).
    presence: dict = field(default_factory=dict)
    overlap: dict = field(default_factory=dict)
    # Caches, campements, villages (sites.py).
    sites: dict = field(default_factory=dict)
    next_site_id: int = 1
    # Relations et pactes entre peuples (diplo.py).
    diplo: Diplomacy = field(default_factory=Diplomacy)
    next_person_id: int = 1
    # Evenements en attente du joueur, suites prevues (events.py). story :
    # les evenements tournent (vraie partie) ; les etats montes a la main
    # par les tests n'en ont pas.
    events: object | None = None
    story: bool = False
    # Caches de l'IA, le temps de decide_ai (ni sauvegardes ni copies) :
    # bandes rangees par carreaux de la carte, forces deja calculees.
    band_grid: object | None = None
    force_memo: object | None = None
    # Relations deja calculees, le temps d'une phase ou elles ne changent pas
    # (diplo.frozen_relations) : ni sauvegardees ni copiees.
    rel_memo: object | None = None


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


def note(state: GameState, kind: LogKind, text: str, where: Hex | None = None) -> None:
    state.log.add(kind, text, state.clock.year, state.clock.week, where=where)


def is_shielded(state: GameState, band: Band) -> bool:
    return band.retreating or state.tick_count < band.shield_until


def hex_inspect(state: GameState, h: Hex) -> dict | None:
    from src.kora.vision import enemy_band_visible, is_explored, is_visible

    placed = state.world.canonicalize(h)
    if placed is None or not is_explored(state, placed):
        return None
    terrain = state.world.terrain(placed)
    season = state.world.hex_season(placed)
    visible = is_visible(state, placed)
    band_info = None
    food = None
    if visible:
        food = food_production(
            state.world,
            placed,
            season,
            herd=_herd_ok(state, PLAYER_TRIBE_ID),
            bonus=bonus_of(state, PLAYER_TRIBE_ID),
        )
        for band in state.bands.values():
            if band.population <= 0:
                continue
            if band.position != placed:
                continue
            if band.tribe_id != PLAYER_TRIBE_ID and not enemy_band_visible(
                state, band
            ):
                continue
            tribe = state.tribes.get(band.tribe_id)
            band_info = {
                "id": band.id,
                "tribe_id": band.tribe_id,
                "name": tribe.name if tribe else "?",
                "population": band.population,
                "stock": band.stock,
                "ally": band.tribe_id == PLAYER_TRIBE_ID,
            }
            break
    site = sites.site_on_hex(state, placed)
    site_info = None
    if site is not None and (visible or site.tribe_id == PLAYER_TRIBE_ID):
        site_info = sites.site_lines(state, site)
    elif site is None:
        from src.kora import villages

        owner = villages.field_site(state, placed)
        if owner is not None and (visible or owner.tribe_id == PLAYER_TRIBE_ID):
            site_info = [f"Champ de {villages.name(owner)}"]
    return {
        "hex": placed,
        "terrain": terrain,
        "terrain_fr": terrain_fr(terrain),
        "season": season,
        "season_fr": season_fr(season),
        "visible": visible,
        "food": food,
        "band": band_info,
        "winter_weeks": local_winter_weeks(state.world, placed),
        "zone": influence.zone_lines(state, placed),
        "site": site_info,
        "resources": state.world.resource_lines(placed) if getattr(state.world, "resources", None) else [],
    }


@functools.lru_cache(maxsize=4)
def _winter_weeks_by_row(height: int) -> tuple[int, ...]:
    # Rejoue une annee de propagation (memes regles que apply_season_spread)
    # sur une carte d'une colonne : hiver court a l'equateur, long aux poles.
    from src.kora.world import make_filled_world

    world = make_filled_world(1, height, Terrain.PLAINE)
    clock = Clock()
    world.fill_season(clock.season())
    counts = [0] * height
    for week in range(104):
        clock.advance_week()
        target = clock.season()
        if world._aimed_season is not target:
            world.seed_season(target)
        world.spread_season(target)
        if week >= 52:
            for row in range(height):
                if world.hex_season(offset_to_axial(0, row)) is Season.HIVER:
                    counts[row] += 1
    return tuple(counts)


def local_winter_weeks(world: World, h: Hex) -> int:
    placed = world.canonicalize(h)
    if placed is None:
        return 0
    return _winter_weeks_by_row(world.height)[placed.r]


def band_summary(state: GameState, band_id: int) -> dict | None:
    band = state.bands.get(band_id)
    if band is None:
        return None
    herd = _herd_ok(state, band.tribe_id)
    bonus = bonus_of(state, band.tribe_id)
    forage = sum(
        food_production(state.world, h, state.world.hex_season(h), herd=herd, bonus=bonus)
        for h in forage_hexes(state, band)
    )
    mates = sum(
        1
        for b in state.bands.values()
        if b.id != band.id and b.tribe_id == band.tribe_id and b.position == band.position
    )
    return {
        "id": band.id,
        "population": band.population,
        "stock_weeks": band.stock / max(1, band.population),
        "forage": forage,
        "need": band.population,
        "terrain_fr": terrain_fr(state.world.terrain(band.position)),
        "season_fr": season_fr(state.world.hex_season(band.position)),
        "winter_weeks": local_winter_weeks(state.world, band.position),
        "bands": tribe_band_count(state, band.tribe_id),
        "max_bands": max_bands_of(state, band.tribe_id),
        "can_split": can_split(state, band.id),
        "split_min": SPLIT_MIN_POP,
        "mates_here": mates,
        "retreating": band.retreating,
        "retreat_weeks": travel_weeks(
            state.world,
            band.position,
            band.path,
            water_ok=_water_ok(state, band.tribe_id),
            costs=costs_of(state, band.tribe_id),
        )
        if band.retreating
        else 0,
        "extra": chiefs.band_lines_extra(state, band) + _village_lines(state, band) + _army_lines(state, band) + _raid_lines(state, band),
        "army": band.kind == "armee",
        "force": band_force(state, band),
        "obeys": chiefs.obeys(state, band),
        "site": sites.site_lines(state, sites.own_site_at(state, band))
        if sites.own_site_at(state, band) and not band.village
        else [],
    }


def _village_lines(state: GameState, band: Band) -> list[str]:
    if not band.village:
        return []
    from src.kora import villages

    return villages.lines(state, band)


def _army_lines(state: GameState, band: Band) -> list[str]:
    if band.kind != "armee":
        return []
    from src.kora import villages

    return villages.army_lines(state, band)


def _raid_lines(state: GameState, band: Band) -> list[str]:
    """Raid en cours : le rapport de force estime (battle.odds)."""
    if band.order.kind is not OrderKind.MARCH_TO_BAND:
        return []
    prey = state.bands.get(band.order.target_band_id)
    if prey is None or prey.tribe_id == band.tribe_id:
        return []
    from src.kora import battle

    ratio, word = battle.odds(state, band, prey)
    tribe = state.tribes.get(prey.tribe_id)
    who = tribe.name if tribe else "?"
    return [f"Raid sur les {who} : rapport de force {ratio:.1f} contre 1 ({word})".replace(".", ",", 1)]


def band_lines(info: dict) -> list[str]:
    stock = info["stock_weeks"]
    if info.get("army"):
        head = f"Troupe  ·  {info['population']} guerriers  ·  force {info.get('force', 0):.0f}"
    else:
        head = f"Bande  ·  {info['population']} personnes  ({info['bands']}/{info['max_bands']} bandes)"
    lines = [
        head,
        f"Stock : {stock:.0f} sem.   Collecte : {info['forage']:.0f} / besoin {info['need']}",
        f"{info['terrain_fr']}  ·  {info['season_fr']}  ·  hiver ici : {info['winter_weeks']} sem./an",
    ]
    lines.extend(info.get("extra") or [])
    if info.get("site"):
        lines.append("Ici : " + "  ·  ".join(info["site"]))
    if info.get("retreating"):
        lines.append(
            f"En repli : pas d'ordre avant l'arrivee (~{info['retreat_weeks']} sem.)."
        )
    elif not info.get("obeys", True):
        lines.append("Indocile : ce clan n'obeit plus. Rapprochez le chef ou honorez-le.")
    elif info["forage"] < info["need"] and stock < 4:
        lines.append("La collecte ne suffit pas : bougez ou scindez.")
    return lines


def band_warn_from(info: dict) -> int:
    """Indice de la premiere ligne d'alerte dans band_lines."""
    return 3 + len(info.get("extra") or []) + (1 if info.get("site") else 0)


def inspect_lines(info: dict) -> list[str]:
    lines = [info["terrain_fr"], f"Saison : {info['season_fr']}"]
    if info.get("winter_weeks") is not None:
        lines.append(f"Duree de l'hiver : {info['winter_weeks']} sem./an")
    if info.get("visible"):
        food = info.get("food")
        if food is not None:
            lines.append(f"Nourriture : {food:.1f}")
        band = info.get("band")
        if band:
            who = "Vous" if band.get("ally") else band.get("name", "?")
            lines.append(f"{who}  ·  {band['population']}")
    lines.extend(info.get("resources") or [])
    lines.extend(info.get("zone") or [])
    lines.extend(info.get("site") or [])
    return lines


def _note_spotted_enemies(state: GameState) -> None:
    from src.kora.vision import is_visible

    for band in state.bands.values():
        if band.population <= 0 or band.tribe_id == PLAYER_TRIBE_ID:
            continue
        if band.tribe_id in state.seen_enemy_tribes:
            continue
        if not is_visible(state, band.position):
            continue
        state.seen_enemy_tribes.add(band.tribe_id)
        tribe = state.tribes.get(band.tribe_id)
        name = tribe.name if tribe else "ennemie"
        note(state, LogKind.DECOUVERTE, f"Des {name} ont ete apercus.")


def _water_ok(state: GameState, tribe_id: int) -> bool:
    tribe = state.tribes.get(tribe_id)
    return bool(tribe and tribe.cabotage)


def _herd_ok(state: GameState, tribe_id: int) -> bool:
    tribe = state.tribes.get(tribe_id)
    return bool(tribe and tribe.troupeau)


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
    if band.village:
        from src.kora.villages import store_weeks

        weeks += store_weeks(state, band)
    return weeks * band.population


def forage_hexes(state: GameState, band: Band) -> list[Hex]:
    return state.world.hexes_in_radius(band.position, FORAGE_RADIUS)


def famine_loss(population: int, missing_share: float) -> int:
    if population <= 0 or missing_share <= 0:
        return 0
    return min(population, max(1, round(population * missing_share * FAMINE_RATE)))


def collect_food(state: GameState) -> None:
    claimants: dict[Hex, list[Band]] = {}
    for band in state.bands.values():
        if band.population <= 0:
            continue
        for h in forage_hexes(state, band):
            claimants.setdefault(h, []).append(band)
    gained: dict[int, float] = {bid: 0.0 for bid in state.bands}
    pressure: dict[Hex, float] = {}
    world = state.world
    for h, bands in claimants.items():
        season = world.hex_season(h)
        total_pop = sum(b.population for b in bands)
        pressure[h] = sum(b.population / 19.0 for b in bands)
        if total_pop <= 0:
            continue
        for b in bands:
            know = bonus_of(state, b.tribe_id)
            prod = food_production(
                world,
                h,
                season,
                herd=_herd_ok(state, b.tribe_id),
                bonus=know,
            )
            if prod <= 0:
                continue
            if know.home_food != 1.0 and influence.is_home(world, h, b.tribe_id):
                # Pistes et reperes : on connait les bons coins de son pays.
                prod *= know.home_food
            gained[b.id] += prod * (b.population / total_pop)
    for band in state.bands.values():
        if band.leader is not None and band.id in gained:
            gained[band.id] *= chiefs.band_food(band)
        if band.village and band.id in gained:
            # Chevres, boeufs, enclos : les troupeaux du village nourrissent aussi.
            from src.kora.villages import food_mult, note_forage, site_of

            gained[band.id] *= food_mult(state, band)
            site = site_of(state, band)
            if site is not None:
                note_forage(state, site, gained[band.id])
    player_loss = 0
    for band in state.bands.values():
        take = gained.get(band.id, 0.0)
        need = band.population * 1.0
        available = band.stock + take
        if available >= need:
            band.stock = min(stock_max(band, state), available - need)
        else:
            deficit = need - available
            band.stock = 0.0
            loss = famine_loss(band.population, deficit / need)
            know = bonus_of(state, band.tribe_id)
            cut = know.winter_famine
            if state.world.hex_season(band.position) is Season.HIVER:
                if know.camp_shelter != 1.0 and sites.sheltered(state, band):
                    cut *= know.camp_shelter
                if band.village:
                    from src.kora.villages import winter_famine_mult

                    cut *= winter_famine_mult(state, band)
            else:
                cut = 1.0
            cut *= chiefs.band_famine(band)
            if cut != 1.0:
                loss = max(1, round(loss * cut))
            band.population = max(0, band.population - loss)
            band.famine_in_period = True
            band.famine_tick = state.tick_count
            tribe = state.tribes.get(band.tribe_id)
            if tribe is not None and state.clock.week >= WINTER_TAIL_WEEK:
                tribe.famine_during_winter = True
            if band.tribe_id == PLAYER_TRIBE_ID:
                player_loss += loss
    if player_loss > 0:
        note(state, LogKind.SURVIE, f"Famine : {player_loss} morts.")
    state.last_pressure = pressure


def update_exhaustion(state: GameState) -> None:
    cells: set[Hex] = set(state.last_pressure.keys())
    for col, row in list(state.world._recovering):
        cells.add(offset_to_axial(col, row))
    # Tribus qui collectent chaque case : l'epuisement compare la pression a
    # la meilleure production pleine (troupeau, savoirs) ; semis = les terres
    # se refont plus vite autour des camps.
    foragers: dict[Hex, set[int]] = {}
    for band in state.bands.values():
        if band.population <= 0:
            continue
        for h in forage_hexes(state, band):
            foragers.setdefault(h, set()).add(band.tribe_id)
    world = state.world
    info = {tid: (bonus_of(state, tid), _herd_ok(state, tid)) for tid in state.tribes}
    pressure = state.last_pressure
    for h in cells:
        tribes_here = foragers.get(h, ())
        p = pressure.get(h, 0.0)
        if not tribes_here and p <= 0.0:
            # Personne ne collecte ici : la terre se refait, sans calcul.
            world.set_exhaustion(h, min(1.0, world.exhaustion(h) + 0.1))
            continue
        recovery = 0.1
        for tid in tribes_here:
            recovery = max(recovery, 0.1 + info[tid][0].recovery)
        season = world.hex_season(h)
        prod = food_production(world, h, season, exhaustion=1.0)
        # Les savoirs ne font que monter la production : si la pression reste
        # sous deux fois la production de base, inutile de les calculer.
        if not (prod > 0 and p <= 2.0 * prod):
            for tid in tribes_here:
                b, herd = info[tid]
                prod = max(prod, food_production(world, h, season, herd=herd, exhaustion=1.0, bonus=b))
        if p > 2.0 * prod and prod > 0:
            world.set_exhaustion(h, 0.5)
        else:
            world.set_exhaustion(h, min(1.0, world.exhaustion(h) + recovery))


def remove_dead_bands(state: GameState) -> None:
    from src.kora.vision import is_visible

    dead = [bid for bid, b in state.bands.items() if b.population <= 0]
    for bid in dead:
        band = state.bands[bid]
        what = "troupe" if band.kind == "armee" else "bande"
        if band.tribe_id == PLAYER_TRIBE_ID:
            note(state, LogKind.COMBAT, f"Votre {what} a ete detruite.", where=band.position)
        elif is_visible(state, band.position):
            tribe = state.tribes.get(band.tribe_id)
            name = tribe.name if tribe else "ennemie"
            note(state, LogKind.COMBAT, f"Une {what} {name} a ete detruite.", where=band.position)
        del state.bands[bid]
        if band.village:
            from src.kora import villages

            villages.lost(state, band)
        chiefs.on_band_lost(state, band)
    if not any(b.tribe_id == PLAYER_TRIBE_ID for b in state.bands.values()):
        state.player_dead = True


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
    from src.kora.peoples import MINOR_BAND_CUT, civ_of

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
    from src.kora.peoples import civ_of

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
    from src.kora.peoples import civ_of

    civ = civ_of(state, tribe)
    free = civ_band_cap(state, civ) - civ_band_count(state, civ)
    return max(1, own + max(0, free))


def settler_people(state: GameState, tribe) -> bool:
    """Un peuple ne d'un autre (clan emancipe, secession), dont la
    civilisation a des villages, et qui n'a pas encore le sien."""
    if not tribe.origin or tribe.is_player:
        return False
    from src.kora.peoples import civ_of, civ_villages

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
    band.population -= moved
    band.stock -= stock
    chiefs.on_split(state, band, state.bands[nid])
    _ai_caches_changed(state)
    if band.tribe_id == PLAYER_TRIBE_ID:
        note(
            state,
            LogKind.SURVIE,
            f"La bande se scinde : {band.population} et {moved}.",
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
        from src.kora import units

        units.normalize(keep)
        for type_id, men, home in units.normalize(gone):
            units.add(keep, type_id, men, home)
        keep.population -= gone.population
        keep.raised = min(keep.raised, gone.raised)
    elif keep.kind != "armee" and gone.kind != "armee" and gone.population >= WELD_MIN:
        # Reunies pour un meme raid : elles savent pourquoi, pas de temps mort.
        if not (keep.intent_prey and keep.intent_prey == gone.intent_prey):
            keep.welded_until = max(keep.welded_until, state.tick_count + WELD_WEEKS)
    keep.population += gone.population
    keep.stock = min(stock_max(keep, state), keep.stock + gone.stock)
    keep.famine_in_period = keep.famine_in_period or gone.famine_in_period
    keep.growth_acc += gone.growth_acc
    keep.famine_tick = max(keep.famine_tick, gone.famine_tick)
    chiefs.on_merge(state, keep, gone)
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
            and chiefs.obeys(state, b)
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
    if keep.tribe_id == PLAYER_TRIBE_ID:
        if near:
            note(state, LogKind.SURVIE, merge_text(keep, names))
        if walking:
            n = len(walking)
            note(state, LogKind.SURVIE, f"{n} bande{'s' if n > 1 else ''} proche{'s' if n > 1 else ''} vien{'nent' if n > 1 else 't'} vous rejoindre.", keep.position)
    return len(near) + len(walking)


def merge_text(band: Band, names: list) -> str:
    lead = band.leader.name if band.leader is not None else "la bande"
    if band.kind == "armee":
        return f"Troupes reunies sous {lead} : {band.population} guerriers."
    if not names:
        return f"Bandes reunies : {band.population} personnes."
    who = ", ".join(names)
    return f"Bandes reunies sous {lead} : {band.population} personnes ; {who} rejoint les anciens du clan."


def resolve_joins(state: GameState) -> None:
    # "Marcher vers" une bande amie = la rejoindre a l'arrivee.
    for band in list(state.bands.values()):
        if band.id not in state.bands or band.order.kind is not OrderKind.MARCH_TO_BAND:
            continue
        target = state.bands.get(band.order.target_band_id)
        if target is None or target.tribe_id != band.tribe_id:
            continue
        # Rejoindre : il suffit d'etre tout pres (on ne compte pas les cases).
        if state.world.distance(target.position, band.position) > 1:
            continue
        if target.kind == "armee" and band.kind != "armee":
            # Des familles ne s'engagent pas dans une troupe : on s'arrete.
            band.order = stay_order()
            band.path = []
            continue
        if band.kind == "armee" and target.village:
            from src.kora import villages

            if villages.disband(state, band.id):
                continue
        names = [band.leader.name] if band.leader is not None and band.kind == target.kind else []
        _absorb(state, target, band)
        if target.tribe_id == PLAYER_TRIBE_ID:
            note(state, LogKind.SURVIE, merge_text(target, names))


def apply_movement(state: GameState) -> None:
    for band in state.bands.values():
        if band.population <= 0:
            continue
        water_ok = _water_ok(state, band.tribe_id)
        costs = costs_of(state, band.tribe_id)
        if band.order.kind is OrderKind.MARCH_TO_BAND:
            tid = band.order.target_band_id
            if tid not in state.bands:
                band.order = stay_order()
                band.path = []
                continue
            target = state.bands[tid]
            need = (not band.path) or (
                state.world.canonicalize(band.path[-1]) != target.position
            )
            if need:
                dist = state.world.distance(band.position, target.position)
                path = astar(
                    state.world,
                    band.position,
                    target.position,
                    max_cost=dist * 30 + 120,
                    max_nodes=min(1200, max(150, dist * 20 + 80)),
                    water_ok=water_ok,
                    costs=costs,
                )
                band.path = [] if path is None else path
        points = MOVE_POINTS_PER_WEEK
        while band.path and points > 0:
            nxt = band.path[0]
            cost = enter_cost_for(state.world, nxt, water_ok, costs)
            if cost is None:
                # Chemin coupe : ordre annule, la bande reste (spec du 14).
                band.path = []
                break
            if cost > points:
                break
            points -= cost
            placed = state.world.canonicalize(nxt)
            band.position = nxt if placed is None else placed
            band.path.pop(0)
        if not band.path and band.order.kind is OrderKind.GOTO:
            band.order = stay_order()
        if band.retreating and not band.path:
            band.retreating = False
            if band.tribe_id == PLAYER_TRIBE_ID:
                note(
                    state,
                    LogKind.COMBAT,
                    f"Repli termine : {band.population} personnes a l'abri.",
                    where=band.position,
                )


def update_population(state: GameState) -> None:
    # Croissance proportionnelle, avec report des fractions : scinder une
    # bande ne multiplie pas les naissances.
    for band in list(state.bands.values()):
        if band.famine_in_period:
            band.famine_in_period = False
            continue
        if band.kind == "armee":
            # Une troupe ne fait pas d'enfants.
            continue
        know = bonus_of(state, band.tribe_id)
        rate = GROWTH_RATE * know.growth
        if band.village:
            from src.kora.villages import growth_mult

            rate *= growth_mult(state, band)
        elif know.camp_growth != 1.0 and sites.sheltered(state, band):
            rate *= know.camp_growth
        band.growth_acc += band.population * rate
        gain = math.floor(band.growth_acc)
        band.growth_acc -= gain
        band.population += gain
        if band.stock > stock_max(band, state):
            band.stock = stock_max(band, state)
    remove_dead_bands(state)


def update_influence(state: GameState) -> None:
    """Presence de la semaine ; toutes les 4 semaines, la zone d'influence
    s'use puis s'etend (influence.py)."""
    influence.note_presence(state)
    if state.tick_count % 4 == 0:
        influence.update(state)


# Un clan se bat avec ses adultes valides, pas avec ses familles ; une
# troupe (villages.py) se bat tout entiere.
CLAN_SHARE = 0.4


def is_army(band: Band) -> bool:
    return band.kind == "armee"


def fighters(band: Band) -> float:
    return band.population * (1.0 if band.kind == "armee" else CLAN_SHARE)


def band_quality(state: GameState, band: Band) -> float:
    """Valeur d'un combattant : prestige, savoirs, chef, troupe aguerrie."""
    tribe = state.tribes[band.tribe_id]
    q = (1.0 + tribe.prestige / 200.0) * tech.bonuses(tribe).combat
    if band.leader is not None:
        q *= chiefs.band_combat(band)
    if band.kind == "armee":
        from src.kora import villages

        q *= villages.army_quality(state, band)
    return q


def band_force(state: GameState, band: Band) -> float:
    force = fighters(band) * band_quality(state, band)
    if band.kind == "armee":
        # Estimation d'une pile (units.py) : attaque, tenue, volee.
        from src.kora import units

        p = units.profile(band)
        force *= p["attack"] * math.sqrt(p["defense"]) + 0.3 * p["ranged"]
    return force


def helpers_of(state: GameState, band: Band) -> list[Band]:
    """Bandes qui viendraient en renfort : les clans soeurs obeissants et les
    bandes des peuples allies, a portee de renfort."""
    out = []
    tid = band.tribe_id
    reach = bonus_of(state, tid).reinforce
    friends = {tid}
    for a, b in state.diplo.pacts:
        if tid in (a, b) and diplo.allied(state, a, b):
            friends.add(b if a == tid else a)
    world = state.world
    pool = bands_near(state, band.position, reach) if state.band_grid is not None else state.bands.values()
    for ally in pool:
        if ally.tribe_id not in friends or ally.id == band.id or ally.population <= 0:
            continue
        if world.distance(ally.position, band.position) > reach:
            continue
        if ally.tribe_id == tid and not chiefs.helps(state, ally):
            continue
        out.append(ally)
    return out


def side_force(state: GameState, band: Band) -> float:
    # La bande + les bandes amies (rayon de renfort). Seule la bande
    # engagee subit les pertes.
    memo = state.force_memo
    if memo is not None:
        hit = memo.get(band.id)
        if hit is not None:
            return hit
    force = band_force(state, band)
    for ally in helpers_of(state, band):
        force += band_force(state, ally)
    if memo is not None:
        memo[band.id] = force
    return force


def defense_force(state: GameState, band: Band) -> float:
    """Force estimee d'une bande attaquee chez elle (pour l'IA) : renforts,
    abri (terrain, palissade, pays connu) et moral (battle.py)."""
    from src.kora import battle

    force = side_force(state, band)
    if band.village and band.kind != "armee":
        # Tout le village tient les murs (battle.VILLAGE_SHARE).
        force += band_force(state, band) * (battle.VILLAGE_SHARE / CLAN_SHARE - 1.0)
    cover = 1.0
    for _label, mult in battle.cover_parts(state, band, band.position):
        cover *= mult
    morale, _parts = battle.start_morale(state, band, attacker=False, h=band.position)
    return force * cover * morale / (battle.MORALE_BASE + battle.KIN_MORALE)


def _retreat_sites(state: GameState, band: Band, winner: Band) -> list[Hex]:
    # Cases candidates, meilleures d'abord : loin des autres tribus ET
    # nourricieres. Le joueur ne se replie que sur des cases explorees.
    from src.kora.vision import is_explored

    world = state.world
    herd = _herd_ok(state, band.tribe_id)
    bonus = bonus_of(state, band.tribe_id)
    water_ok = _water_ok(state, band.tribe_id)
    player = band.tribe_id == PLAYER_TRIBE_ID
    # Seuls les etrangers assez proches peuvent changer le score d'une case.
    span = RETREAT_SEARCH_RADIUS + RETREAT_SAFE_DIST
    foes = [
        b.position
        for b in state.bands.values()
        if b.tribe_id != band.tribe_id
        and b.population > 0
        and not diplo.at_peace(state, b.tribe_id, band.tribe_id)
        and world.distance(b.position, band.position) <= span
    ]
    scored: list[tuple[float, Hex]] = []
    for h in world.hexes_in_radius(band.position, RETREAT_SEARCH_RADIUS)[::2]:
        if h == band.position or enter_cost_for(world, h, water_ok) is None:
            continue
        if player and not is_explored(state, h):
            continue
        near = min((world.distance(h, f) for f in foes), default=RETREAT_SAFE_DIST)
        if near < 3 or world.distance(h, winner.position) < 4:
            continue
        safety = min(near, RETREAT_SAFE_DIST) / RETREAT_SAFE_DIST
        food = sum(
            food_production(world, x, world.hex_season(x), herd=herd, bonus=bonus)
            for x in world.hexes_in_radius(h, 2)
        )
        scored.append((food * safety - 0.5 * world.distance(band.position, h), h))
    scored.sort(key=lambda it: it[0], reverse=True)
    return [h for _score, h in scored[:6]]


def _retreat(state: GameState, loser: Band, winner: Band) -> bool:
    """Le vaincu part a pied vers ses soeurs, un de ses lieux, sinon une case
    sure. Rend False s'il n'a nulle part ou aller (encercle, battle.py)."""
    loser.order = stay_order()
    loser.path = []
    loser.shield_until = state.tick_count + RETREAT_MIN_SHIELD
    allies = sorted(
        (
            b
            for b in state.bands.values()
            if b.id != loser.id
            and b.tribe_id == loser.tribe_id
            and b.population > 0
            and not b.retreating
            and state.world.distance(b.position, winner.position) >= 2
            and state.world.distance(b.position, loser.position) <= RETREAT_ALLY_RANGE
        ),
        key=lambda b: state.world.distance(b.position, loser.position),
    )
    camps = sorted(
        (
            s.hex
            for s in sites.of_tribe(state, loser.tribe_id)
            if s.kind in ("camp", "village")
            and state.world.distance(s.hex, winner.position) >= 4
            and state.world.distance(s.hex, loser.position) <= RETREAT_ALLY_RANGE
        ),
        key=lambda h: state.world.distance(h, loser.position),
    )
    for goal in [a.position for a in allies] + camps + _retreat_sites(state, loser, winner):
        set_goto(state, loser.id, goal)
        if loser.path:
            loser.retreating = True
            return True
    return False


def prune_fight_marks(state: GameState) -> None:
    keep = [
        m
        for m in state.fights
        if state.tick_count - m.tick < COMBAT_MARK_WEEKS
    ]
    if len(keep) > COMBAT_MARK_MAX:
        keep = keep[-COMBAT_MARK_MAX:]
    state.fights = keep


def add_fight_mark(state: GameState, mark: FightMark) -> None:
    state.fights = [m for m in state.fights if m.hex != mark.hex]
    state.fights.append(mark)
    prune_fight_marks(state)


def player_home_hex(state: GameState) -> Hex | None:
    for band in state.bands.values():
        if band.tribe_id == PLAYER_TRIBE_ID and band.population > 0:
            return band.position
    return None


def fight_at(state: GameState, h: Hex | None) -> FightMark | None:
    if h is None:
        return None
    return next((m for m in reversed(state.fights) if m.hex == h), None)


def fight_lines(mark: FightMark) -> list[str]:
    def label(tribe_id: int, name: str) -> str:
        return "Vous" if tribe_id == PLAYER_TRIBE_ID else name

    w = label(mark.winner_tribe, mark.winner_name)
    l = label(mark.loser_tribe, mark.loser_name)
    w_after = max(0, mark.winner_before - mark.winner_loss)
    l_after = max(0, mark.loser_before - mark.loser_loss)
    return [
        "Combat",
        f"An {mark.year}  ·  semaine {mark.week}",
        f"{w}  vs  {l}",
        f"Gagnant : {w}",
        f"{w} : {mark.winner_before} -> {w_after}  (-{mark.winner_loss})",
        f"{l} : {mark.loser_before} -> {l_after}  (-{mark.loser_loss})",
        f"Butin : {mark.loot:.0f}",
    ]


def _raid_sides(a: Band, b: Band) -> tuple[Band, Band]:
    # L'attaquant est celui qui marchait vers l'autre. A defaut
    # (rencontre fortuite) : jamais un village, plutot une troupe, sinon la
    # bande d'id le plus bas.
    a_hunts = a.order.kind is OrderKind.MARCH_TO_BAND and a.order.target_band_id == b.id
    b_hunts = b.order.kind is OrderKind.MARCH_TO_BAND and b.order.target_band_id == a.id
    if b_hunts and not a_hunts:
        return b, a
    if a_hunts:
        return a, b
    if a.village and not b.village:
        return b, a
    if b.kind == "armee" and a.kind != "armee" and not b.village:
        return b, a
    return a, b


def _raid_text(state: GameState, attacker: Band, defender: Band, winner: Band) -> str:
    def name(band: Band) -> str:
        tribe = state.tribes.get(band.tribe_id)
        return tribe.name if tribe else "ennemi"

    hunted = attacker.order.kind is OrderKind.MARCH_TO_BAND
    player_won = winner.tribe_id == PLAYER_TRIBE_ID
    if PLAYER_TRIBE_ID not in (attacker.tribe_id, defender.tribe_id):
        return f"Un raid a ete apercu : {name(attacker)} contre {name(defender)}."
    if not hunted:
        other = defender if attacker.tribe_id == PLAYER_TRIBE_ID else attacker
        result = "vous l'emportez" if player_won else "vous perdez"
        return f"Accrochage avec {name(other)} : {result}."
    if attacker.tribe_id == PLAYER_TRIBE_ID:
        result = "victoire" if player_won else "echec"
        return f"Raid contre {name(defender)} : {result}."
    result = "repousse" if player_won else "vous perdez"
    return f"Raid de {name(attacker)} contre vous : {result}."


def resolve_raids(state: GameState) -> None:
    """Combats de la semaine : deux bandes ennemies sur la meme case se
    battent (battle.py). Une bande ne livre qu'une bataille par semaine."""
    from collections import defaultdict

    from src.kora import battle
    from src.kora.vision import is_visible

    by_hex: dict[Hex, list[Band]] = defaultdict(list)
    for band in state.bands.values():
        if band.population <= 0:
            continue
        by_hex[band.position].append(band)
    fought: set[int] = set()
    for h, group in by_hex.items():
        while True:
            # Une bande en repli (ou dans son repit) ne se bat pas : c'est ce
            # qui empeche d'attaquer plusieurs fois la meme bande.
            present = sorted(
                (
                    b
                    for b in group
                    if b.position == h and b.population > 0 and not is_shielded(state, b) and b.id not in fought
                ),
                key=lambda b: b.id,
            )
            # Celle qui est venue attaquer livre sa bataille d'abord (sinon
            # une bande soeur sur la meme case la livrerait a sa place).
            pairs = [
                (a, foe)
                for i, a in enumerate(present)
                for foe in present[i + 1 :]
                if foe.tribe_id != a.tribe_id and _will_fight(state, a, foe)
            ]
            pair = next((p for p in pairs if _hunts(*p) or _hunts(p[1], p[0])), pairs[0] if pairs else None)
            if pair is None:
                break
            a, foe = pair
            attacker, defender = _raid_sides(a, foe)
            hunted = _hunts(attacker, defender)
            seen = is_visible(state, h)
            player_in = PLAYER_TRIBE_ID in (a.tribe_id, foe.tribe_id)
            res = battle.fight(state, attacker, defender, h)
            fought.update(res.engaged)
            winner, loser = res.winner, res.loser
            if player_in or seen:
                note(state, LogKind.COMBAT, _raid_text(state, attacker, defender, winner) + battle.log_suffix(state, res), where=h)
            wt = state.tribes[winner.tribe_id]
            lt = state.tribes[loser.tribe_id]
            wt.prestige = min(100, wt.prestige + (10 if res.wiped else 5))
            lt.prestige = max(0, lt.prestige - (8 if res.wiped else 4))
            winner.last_raid_tick = state.tick_count
            loser.last_raid_tick = state.tick_count
            diplo.on_fight(state, attacker.tribe_id, defender.tribe_id, winner is attacker, hunted)
            if winner.leader is not None:
                winner.leader.renown += 10 if res.wiped else 5
            if winner.order.kind is OrderKind.MARCH_TO_BAND:
                winner.order = stay_order()
                winner.path = []
            if player_in or seen:
                add_fight_mark(
                    state,
                    FightMark(
                        hex=h,
                        tick=state.tick_count,
                        year=state.clock.year,
                        week=state.clock.week,
                        winner_tribe=winner.tribe_id,
                        loser_tribe=loser.tribe_id,
                        winner_name=wt.name,
                        loser_name=lt.name,
                        winner_before=res.winner_before,
                        loser_before=res.loser_before,
                        winner_loss=res.winner_loss,
                        loser_loss=res.loser_loss,
                        loot=res.loot,
                        report=res.report,
                    ),
                )
            if res.building and loser.tribe_id == PLAYER_TRIBE_ID:
                note(state, LogKind.COMBAT, f"Le village a perdu : {res.building}.", where=h)
    remove_dead_bands(state)


def _hunts(a: Band, b: Band) -> bool:
    return a.order.kind is OrderKind.MARCH_TO_BAND and a.order.target_band_id == b.id


def _will_fight(state: GameState, a: Band, b: Band) -> bool:
    """Deux bandes etrangeres sur la meme case se battent, sauf pacte
    (treve, alliance, tribut) - a moins que l'une ne soit venue attaquer."""
    if diplo.hostile_intent(state, a.tribe_id, b.tribe_id):
        return True
    return _hunts(a, b) or _hunts(b, a)


def update_prestige(state: GameState) -> None:
    if state.clock.just_finished_winter():
        living = {b.tribe_id for b in state.bands.values()}
        tech.count_winter(state)
        for tid, tribe in state.tribes.items():
            if tid not in living:
                continue
            b = tech.bonuses(tribe)
            if tribe.famine_during_winter:
                tribe.prestige = max(0, tribe.prestige + b.famine_prestige)
            else:
                from src.kora import villages

                gain = b.winter_prestige + chiefs.winter_prestige(state, tid) + villages.winter_prestige(state, tid)
                tribe.prestige = min(100, tribe.prestige + gain)
            tribe.famine_during_winter = False
    if state.tick_count > 0 and state.tick_count % 4 == 0:
        for tid, tribe in state.tribes.items():
            pop = sum(b.population for b in state.bands.values() if b.tribe_id == tid)
            if pop <= 0:
                continue
            # Un grand peuple gagne du prestige, jusqu'a un plafond qui suit sa
            # taille (sinon toutes les IA finissaient a 100).
            if pop >= 80 and tribe.prestige < 40 + pop // 10:
                tribe.prestige = min(100, tribe.prestige + 1)
            elif pop < 20:
                tribe.prestige = max(0, tribe.prestige - 1)


@dataclass
class _Snap:
    clock: object
    tribes: dict
    bands: dict
    tick_count: int
    rng: random.Random
    player_dead: bool
    last_pressure: dict
    vision: object
    exhaustion: dict
    influence: dict
    influence_cells: set
    hex_season: list
    aimed_season: object
    season_frontier: list
    season_gen: int
    log: GameLog
    seen_enemy_tribes: set
    fights: list
    next_band_id: int
    story_rng: random.Random
    next_tribe_id: int
    presence: dict
    overlap: dict
    sites: dict
    next_site_id: int
    diplo: object
    next_person_id: int
    events: object


def _copy_tribe(tribe: Tribe) -> Tribe:
    out = copy.copy(tribe)
    out.knowledge = set(tribe.knowledge)
    out.progress = dict(tribe.progress)
    out.practice = dict(tribe.practice)
    out.flags = dict(tribe.flags)
    out.goods = dict(tribe.goods)
    out.trade = copy.deepcopy(tribe.trade)
    return out


def _copy_band(band: Band) -> Band:
    # Hex et Order sont remplaces, jamais modifies sur place : une copie
    # des listes suffit (deepcopy etait le poste le plus lent du tick).
    out = copy.copy(band)
    out.order = copy.copy(band.order)
    out.path = list(band.path)
    out.recent_goals = list(band.recent_goals)
    out.leader = chiefs.copy_person(band.leader)
    out.units = [list(u) for u in band.units]
    out.notables = [chiefs.copy_person(p) for p in band.notables]
    return out


def snapshot(state: GameState) -> _Snap:
    return _Snap(
        clock=copy.copy(state.clock),
        tribes={tid: _copy_tribe(t) for tid, t in state.tribes.items()},
        bands={bid: _copy_band(b) for bid, b in state.bands.items()},
        tick_count=state.tick_count,
        rng=copy.deepcopy(state.rng),
        player_dead=state.player_dead,
        last_pressure=dict(state.last_pressure),
        vision=None,
        exhaustion=state.world.exhaustion_snapshot(),
        # influence.update reconstruit la carte : garder la reference suffit.
        influence=state.world._influence,
        influence_cells=state.world._influence_cells,
        # Les rangees de saison sont remplacees, jamais modifiees sur place.
        hex_season=list(state.world._hex_season),
        aimed_season=state.world._aimed_season,
        season_frontier=list(state.world._season_frontier),
        season_gen=state.world._season_gen,
        log=GameLog(entries=list(state.log.entries), seq=state.log.seq),
        seen_enemy_tribes=set(state.seen_enemy_tribes),
        fights=list(state.fights),
        next_band_id=state.next_band_id,
        story_rng=copy.deepcopy(state.story_rng),
        next_tribe_id=state.next_tribe_id,
        presence={k: dict(v) for k, v in state.presence.items()},
        overlap=dict(state.overlap),
        sites={k: sites.copy_site(s) for k, s in state.sites.items()},
        next_site_id=state.next_site_id,
        diplo=diplo.copy_diplo(state.diplo),
        next_person_id=state.next_person_id,
        events=copy.deepcopy(state.events),
    )


def _restore(state: GameState, saved: _Snap) -> None:
    state.clock = saved.clock
    state.tribes = saved.tribes
    state.bands = saved.bands
    state.tick_count = saved.tick_count
    state.rng = saved.rng
    state.player_dead = saved.player_dead
    state.last_pressure = saved.last_pressure
    state.world.exhaustion_restore(saved.exhaustion)
    state.world._influence = saved.influence
    state.world._influence_cells = saved.influence_cells
    state.world._hex_season = saved.hex_season
    state.world._aimed_season = saved.aimed_season
    state.world._season_frontier = saved.season_frontier
    state.world._season_gen = saved.season_gen
    state.log = saved.log
    state.seen_enemy_tribes = saved.seen_enemy_tribes
    state.fights = saved.fights
    state.next_band_id = saved.next_band_id
    state.story_rng = saved.story_rng
    state.next_tribe_id = saved.next_tribe_id
    state.presence = saved.presence
    state.overlap = saved.overlap
    state.sites = saved.sites
    state.next_site_id = saved.next_site_id
    state.diplo = saved.diplo
    state.next_person_id = saved.next_person_id
    state.events = saved.events
    from src.kora.vision import recompute_vision

    recompute_vision(state)


def _default_world() -> World:
    from src.kora.world import generate_world, load_world, save_world

    candidates: list[Path] = []
    if getattr(sys, "frozen", False):
        meipass = getattr(sys, "_MEIPASS", None)
        if meipass:
            candidates.append(Path(meipass) / "data" / "kora_map.json")
        exe_dir = Path(sys.executable).resolve().parent
        candidates.append(exe_dir / "data" / "kora_map.json")
        candidates.append(exe_dir / "_internal" / "data" / "kora_map.json")
    else:
        candidates.append(
            Path(__file__).resolve().parents[2] / "data" / "kora_map.json"
        )
    for map_path in candidates:
        if not map_path.exists():
            continue
        try:
            loaded = load_world(map_path)
        except (KeyError, ValueError, json.JSONDecodeError):
            continue
        if loaded.wrap_x and loaded.width >= 300:
            return loaded
    world = generate_world(seed=42)
    if not getattr(sys, "frozen", False):
        try:
            save_world(world, candidates[0])
        except OSError:
            pass
    return world


def new_game(world: World | None = None, minor_peoples: int | None = None) -> GameState:
    from src.kora.clock import Clock
    from src.kora.types import Band, Tribe
    from src.kora.vision import recompute_vision
    from src.kora.world import pick_spawn_hexes

    from src.kora.peoples import CULTURES, LEGACY_COLOR, make_name

    if world is None:
        world = _default_world()
    clock = Clock()
    story = random.Random(20260924)
    tribes = {PLAYER_TRIBE_ID: Tribe(PLAYER_TRIBE_ID, "Kora", 20, True, culture="joueur")}
    for tid, culture in ((AI_STEPPE_ID, "steppe"), (AI_FOREST_ID, "foret"), (AI_COAST_ID, "cote")):
        name = make_name(story, CULTURES[culture], [t.name for t in tribes.values()])
        tribes[tid] = Tribe(tid, name, 20, False, culture=culture)
    for tribe in tribes.values():
        tribe.color = LEGACY_COLOR[tribe.id]
    # Chaque tribu part sur le biome de son nom, avec de quoi nourrir
    # sa bande au printemps. La Steppe connait deja le troupeau, la Cote
    # le cabotage : c'est leur savoir de depart.
    spots = pick_spawn_hexes(
        world,
        4,
        prefs=[
            {Terrain.VALLEE, Terrain.PLAINE},
            {Terrain.STEPPE},
            {Terrain.FORET},
            {Terrain.COTE},
        ],
        min_forage=[40.0, 30.0, 32.0, 24.0],
    )
    for tribe in tribes.values():
        tech.start_knowledge(tribe)
    bands = {
        1: Band(1, PLAYER_TRIBE_ID, spots[0], 40, 160.0),
        2: Band(2, AI_STEPPE_ID, spots[1], 36, 144.0),
        3: Band(3, AI_FOREST_ID, spots[2], 32, 128.0),
        4: Band(4, AI_COAST_ID, spots[3], 32, 128.0),
    }
    world.fill_season(clock.season())
    st = GameState(
        world=world,
        clock=clock,
        tribes=tribes,
        bands=bands,
        next_band_id=5,
        story_rng=story,
        next_tribe_id=5,
        story=True,
    )
    chiefs.ensure(st)
    if minor_peoples is None:
        from src.kora.peoples import MINOR_START

        # Les petites cartes des tests restent a 4 peuples.
        minor_peoples = MINOR_START if world.width >= 300 else 0
    if minor_peoples:
        add_minor_peoples(st, minor_peoples)
    recompute_vision(st)
    _note_spotted_enemies(st)
    tech.update_practice(st, count=False)
    return st


def add_minor_peoples(state: GameState, count: int, avoid=None) -> list[int]:
    """Petits peuples : une bande chacun, loin de tous les autres."""
    from src.kora.peoples import (
        CULTURES,
        MINOR_POP,
        culture_for_place,
        free_color,
        make_name,
        pick_minor_spots,
    )

    taken = [b.position for b in state.bands.values() if b.population > 0]
    spots = pick_minor_spots(state.world, taken, count, state.story_rng, avoid=avoid)
    made = []
    for h in spots:
        culture = culture_for_place(state.world, h)
        tid = max(state.next_tribe_id, max(state.tribes) + 1)
        state.next_tribe_id = tid + 1
        name = make_name(state.story_rng, CULTURES[culture], [t.name for t in state.tribes.values()])
        tribe = Tribe(
            tid,
            name,
            10,
            False,
            culture=culture,
            color=free_color(state.tribes.values()),
            minor=True,
            founded=state.clock.year,
        )
        tech.start_knowledge(tribe)
        state.tribes[tid] = tribe
        pop = state.story_rng.randint(*MINOR_POP)
        bid = new_band_id(state)
        state.bands[bid] = Band(bid, tid, h, pop, 4.0 * pop)
        made.append(tid)
    chiefs.ensure(state)
    return made


def apply_season_spread(state: GameState) -> None:
    target = state.clock.season()
    if state.world._aimed_season is not target:
        state.world.seed_season(target)
    state.world.spread_season(target)


def tick(state: GameState) -> None:
    from src.kora.ai import decide_ai
    from src.kora.vision import recompute_vision

    saved = snapshot(state)
    tech.begin_tick()
    try:
        prev_season = state.clock.season()
        state.clock.advance_week()
        if state.clock.season() is not prev_season:
            note(
                state,
                LogKind.SAISON,
                f"{season_fr(state.clock.season())} commence.",
            )
        apply_season_spread(state)
        apply_movement(state)
        resolve_joins(state)
        tech.update_practice(state)
        prune_fight_marks(state)
        resolve_raids(state)
        update_exhaustion(state)
        collect_food(state)
        remove_dead_bands(state)
        sites.update(state)
        state.tick_count += 1
        monthly = state.tick_count % 4 == 0
        if monthly:
            update_population(state)
        update_influence(state)
        if monthly:
            diplo.monthly(state)
            goods.monthly(state)
            chiefs.monthly(state)
            diplo.ai_monthly(state)
            events.monthly(state)
        events.weekly(state)
        tech.invalidate()
        update_prestige(state)
        tech.update_learning(state)
        tech.invalidate()
        recompute_vision(state)
        _note_spotted_enemies(state)
        decide_ai(state)
        state.last_error = None
    except Exception as exc:
        _restore(state, saved)
        state.clock.paused = True
        state.last_error = str(exc)
    finally:
        tech.end_tick()


def consume_ticks(
    state: GameState,
    acc: float,
    dt: float,
    max_per_frame: int = 1,
    max_acc: float = 2.0,
) -> float:
    if state.clock.paused or state.player_dead:
        return 0.0
    acc += dt * state.clock.ticks_per_second()
    if acc > max_acc:
        acc = max_acc
    ran = 0
    while acc >= 1.0 and ran < max_per_frame:
        tick(state)
        acc -= 1.0
        ran += 1
        if state.clock.paused or state.player_dead:
            break
    return acc
