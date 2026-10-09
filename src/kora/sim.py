from __future__ import annotations

import copy
import functools
import json
import math
import random
import sys
from dataclasses import dataclass, field
from pathlib import Path

from src.kora import (
    battle,
    chiefdom,
    chiefs,
    diplo,
    draws,
    events,
    influence,
    learning,
    memory,
    ost,
    places,
    population,
    records,
    siege,
    sites,
    situations,
    systems,
    tech,
    turning,
    units,
    villages,
)
from src.kora.clock import Clock
from src.kora.log import GameLog, LogKind, season_fr, terrain_fr
from src.kora.path import MOVE_POINTS_PER_WEEK, astar, travel_weeks
from src.kora.types import Band, FightMark, Hex, Order, OrderKind, Season, Terrain, Tribe, stay_order
from src.kora.world import (
    World,
    enter_cost_for,
    food_production,
    load_world,
    make_filled_world,
    offset_to_axial,
    pick_spawn_hexes,
    save_world,
)

# L'etat de la partie et ses joueurs vivent dans gamestate.py ; note_seen
# dans vision.py. sim les rend aussi (anciens appels, tests).
from src.kora.gamestate import (  # noqa: F401
    AI_COAST_ID,
    AI_FOREST_ID,
    AI_STEPPE_ID,
    PLAYER_TRIBE_ID,
    GameState,
    Pov,
    human_dead,
    humans,
    is_human,
    log_of,
    note,
    note_all,
    pov_of,
    seen_of,
)
from src.kora.vision import enemy_band_visible, is_explored, is_visible, recompute_vision, vision_of
from src.kora.peoples import (
    CULTURES,
    LEGACY_COLOR,
    MINOR_BAND_CUT,
    MINOR_POP,
    MINOR_START,
    civ_of,
    civ_villages,
    culture_for_place,
    free_color,
    make_name,
    pick_minor_spots,
)
from src.kora.mapgen import generate_world
from src.kora.villages import food_mult, growth_mult, note_forage, store_weeks, winter_famine_mult
from src.kora.places import site_of
from src.kora.bands import (  # noqa: F401
    SPLIT_MIN_POP,
    _absorb,
    _herd_ok,
    _water_ok,
    bands_near,
    bonus_of,
    can_split,
    costs_of,
    fighters,
    forage_hexes,
    gain_prestige,
    is_shielded,
    max_bands_of,
    merge_text,
    new_band_id,
    set_goto,
    stock_max,
    tribe_band_count,
)
from src.kora.battle import (  # noqa: F401
    band_force,
    prune_fight_marks,
    resolve_raids,
)
from src.kora.world import (  # noqa: F401
    local_winter_weeks,
)
from src.kora.ai import decide_ai

# Famine progressive : part de la bande qui meurt par semaine
# = part de nourriture manquante x FAMINE_RATE (minimum 1 mort).
FAMINE_RATE = 0.15
# Le prestige d'hiver ne regarde que les 4 dernieres semaines de l'hiver.
WINTER_TAIL_WEEK = 49
# Par mois ; une partie longue : les peuples grandissent lentement.
GROWTH_RATE = 0.018


def hex_inspect(state: GameState, h: Hex) -> dict | None:
    """Ce que le joueur de cet ecran (state.viewer) sait d'une case."""
    me = state.viewer
    placed = state.world.canonicalize(h)
    if placed is None or not is_explored(state, placed, me):
        return None
    terrain = state.world.terrain(placed)
    season = state.world.hex_season(placed)
    visible = is_visible(state, placed, me)
    band_info = None
    food = None
    if visible:
        food = food_production(
            state.world,
            placed,
            season,
            herd=_herd_ok(state, me),
            bonus=bonus_of(state, me),
        )
        for band in state.bands.values():
            if band.population <= 0:
                continue
            if band.position != placed:
                continue
            if band.tribe_id != me and not enemy_band_visible(state, band, me):
                continue
            tribe = state.tribes.get(band.tribe_id)
            band_info = {
                "id": band.id,
                "tribe_id": band.tribe_id,
                "name": tribe.name if tribe else "?",
                "population": band.population,
                "stock": band.stock,
                "ally": band.tribe_id == me,
            }
            break
    site = sites.site_on_hex(state, placed)
    site_info = None
    if site is not None and (visible or site.tribe_id == me):
        site_info = sites.site_lines(state, site)
    elif site is None:
        owner = villages.field_site(state, placed)
        if owner is not None and (visible or owner.tribe_id == me):
            site_info = [f"Champ de {places.name(owner)}"]
    zone = influence.zone_lines(state, placed)
    if not visible:
        # Le brouillard : ce qu'on en a vu la derniere fois (memory.py).
        seen = memory.site_at(state, placed, me)
        if site_info is None and seen is not None:
            _sid, (_q, _r, kind, tid, _w, _lord) = seen
            word = {"village": "Village", "camp": "Campement", "cache": "Cache"}.get(kind, "Lieu")
            who = state.tribes[tid].name if tid in state.tribes else "?"
            site_info = [f"{word} des {who}", "Vu la dernière fois : il a pu changer depuis."]
        vis = vision_of(state, me)
        mem = vis.zones.get(state.world._index(placed)) if vis is not None else None
        zone = [f"Zone des {state.tribes[mem[0]].name} (votre dernière visite)"] if mem and mem[0] in state.tribes else []
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
        "zone": zone,
        "site": site_info,
        "resources": state.world.resource_lines(placed) if getattr(state.world, "resources", None) else [],
    }


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
        "extra": _people_lines(band) + _work_lines(state, band) + chiefs.band_lines_extra(state, band) + _village_lines(state, band) + _army_lines(state, band) + _raid_lines(state, band),
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
    site = places.site_of(state, band)
    return villages.lines(state, band) + (siege.lines(state, site) if site is not None else [])


def _army_lines(state: GameState, band: Band) -> list[str]:
    if band.kind != "armee":
        return []
    return villages.army_lines(state, band) + ost.lines(state, band)


def _raid_lines(state: GameState, band: Band) -> list[str]:
    """Raid en cours : le rapport de force estime (battle.odds)."""
    if band.order.kind is not OrderKind.MARCH_TO_BAND:
        return []
    prey = state.bands.get(band.order.target_band_id)
    if prey is None or prey.tribe_id == band.tribe_id:
        return []
    ratio, word = battle.odds(state, band, prey)
    tribe = state.tribes.get(prey.tribe_id)
    who = tribe.name if tribe else "?"
    return [f"Raid sur les {who} : rapport de force {ratio:.1f} contre 1 ({word})".replace(".", ",", 1)]


def _people_lines(band: Band) -> list[str]:
    """Qui sont les gens de la bande (population.py)."""
    c = population.counts(band)
    if band.kind == "armee":
        return [f"{c['blesses']} blessés parmi les guerriers"] if c["blesses"] else []
    line = f"{c['enfants']} enfants · {c['hommes']} hommes · {c['femmes']} femmes · {c['anciens']} anciens"
    if c["blesses"]:
        line += f" · {c['blesses']} blessés"
    return [line]


def _work_lines(state: GameState, band: Band) -> list[str]:
    """Qui fait quoi (villages.occupations) : pour un clan, la chasse et la
    cueillette."""
    if band.kind == "armee" or band.village:
        return []
    return villages.occupation_lines(state, band)


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
            f"En repli : pas d'ordre avant l'arrivée (~{info['retreat_weeks']} sem.)."
        )
    elif not info.get("obeys", True):
        lines.append("Indocile : ce clan n'obéit plus. Rapprochez le chef ou honorez-le.")
    elif info["forage"] < info["need"] and stock < 4:
        lines.append("La collecte ne suffit pas : bougez ou scindez.")
    return lines


def band_warn_from(info: dict) -> int:
    """Indice de la premiere ligne d'alerte dans band_lines."""
    return 3 + len(info.get("extra") or []) + (1 if info.get("site") else 0)


def inspect_lines(info: dict) -> list[str]:
    lines = [info["terrain_fr"], f"Saison : {info['season_fr']}"]
    if info.get("winter_weeks") is not None:
        lines.append(f"Durée de l'hiver : {info['winter_weeks']} sem./an")
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
    for me in humans(state):
        seen = seen_of(state, me)
        for band in state.bands.values():
            if band.population <= 0 or band.tribe_id == me:
                continue
            if band.tribe_id in seen:
                continue
            if not is_visible(state, band.position, me):
                continue
            seen.add(band.tribe_id)
            tribe = state.tribes.get(band.tribe_id)
            name = tribe.name if tribe else "ennemie"
            note(state, LogKind.DECOUVERTE, f"Des {name} ont été aperçus.", to=me)


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
            gained[band.id] *= food_mult(state, band)
            site = site_of(state, band)
            if site is not None:
                note_forage(state, site, gained[band.id])
    losses: dict[int, int] = {}
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
                    cut *= winter_famine_mult(state, band)
            else:
                cut = 1.0
            cut *= chiefs.band_famine(band)
            if cut != 1.0:
                loss = max(1, round(loss * cut))
            population.kill(band, loss, population.FAMINE_WEIGHTS)
            band.famine_in_period = True
            band.famine_tick = state.tick_count
            tribe = state.tribes.get(band.tribe_id)
            if tribe is not None and state.clock.week >= WINTER_TAIL_WEEK:
                tribe.famine_during_winter = True
            if tribe is not None and (tribe.is_player or band.tribe_id == PLAYER_TRIBE_ID):
                losses[band.tribe_id] = losses.get(band.tribe_id, 0) + loss
    for tid in sorted(losses):
        note(state, LogKind.SURVIE, f"Famine : {losses[tid]} morts.", to=tid)
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
    dead = [bid for bid, b in state.bands.items() if b.population <= 0]
    for bid in dead:
        band = state.bands[bid]
        what = "troupe" if band.kind == "armee" else "bande"
        if is_human(state, band.tribe_id):
            note(state, LogKind.COMBAT, f"Votre {what} a été détruite.", where=band.position, to=band.tribe_id)
        tribe = state.tribes.get(band.tribe_id)
        name = tribe.name if tribe else "ennemie"
        for me in humans(state):
            if me != band.tribe_id and is_visible(state, band.position, me):
                note(state, LogKind.COMBAT, f"Une {what} {name} a été détruite.", where=band.position, to=me)
        del state.bands[bid]
        if band.village:
            villages.lost(state, band)
        chiefs.on_band_lost(state, band)
    if not any(b.tribe_id == PLAYER_TRIBE_ID for b in state.bands.values()):
        state.player_dead = True


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
            if villages.disband(state, band.id):
                continue
        names = [band.leader.name] if band.leader is not None and band.kind == target.kind else []
        _absorb(state, target, band)
        if is_human(state, target.tribe_id):
            note(state, LogKind.SURVIE, merge_text(target, names), to=target.tribe_id)


def apply_movement(state: GameState) -> None:
    # Une bande engagee dans une bataille ne marche pas (sauf le repli, a la fin).
    fighting = {b for bt in battle.battles(state) if not bt.outcome for b in bt.attackers + bt.defenders}
    for band in state.bands.values():
        if band.population <= 0 or band.id in fighting:
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
            if is_human(state, band.tribe_id):
                note(
                    state,
                    LogKind.COMBAT,
                    f"Repli terminé : {band.population} personnes à l'abri.",
                    where=band.position,
                    to=band.tribe_id,
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
            rate *= growth_mult(state, band)
        elif know.camp_growth != 1.0 and sites.sheltered(state, band):
            rate *= know.camp_growth
        band.growth_acc += band.population * rate
        gain = math.floor(band.growth_acc)
        band.growth_acc -= gain
        population.grow(band, gain, "enfants")
        if band.stock > stock_max(band, state):
            band.stock = stock_max(band, state)
    remove_dead_bands(state)


def update_influence(state: GameState) -> None:
    """Presence de la semaine ; toutes les 4 semaines, la zone d'influence
    s'use puis s'etend (influence.py)."""
    influence.note_presence(state)
    if state.tick_count % 4 == 0:
        influence.update(state)


def player_home_hex(state: GameState) -> Hex | None:
    for band in state.bands.values():
        if band.tribe_id == state.viewer and band.population > 0:
            return band.position
    return None


def fight_at(state: GameState, h: Hex | None) -> FightMark | None:
    if h is None:
        return None
    return next((m for m in reversed(state.fights) if m.hex == h), None)


def fight_lines(mark: FightMark, me: int = PLAYER_TRIBE_ID) -> list[str]:
    def label(tribe_id: int, name: str) -> str:
        return "Vous" if tribe_id == me else name

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


def fight_out(state: GameState) -> None:
    """Les rencontres de la semaine, et chaque bataille jusqu'a sa fin
    (essais ; une partie passe par tick)."""
    resolve_raids(state)
    battle.advance(state, battle.MAX_DAYS + 1, humans=True)
    remove_dead_bands(state)


def update_prestige(state: GameState) -> None:
    if state.clock.just_finished_winter():
        living = {b.tribe_id for b in state.bands.values()}
        learning.count_winter(state)
        for tid, tribe in state.tribes.items():
            if tid not in living:
                continue
            b = tech.bonuses(tribe)
            if tribe.famine_during_winter:
                tribe.prestige = max(0, tribe.prestige + b.famine_prestige)
            else:
                gain = b.winter_prestige + chiefs.winter_prestige(state, tid) + villages.winter_prestige(state, tid)
                gain_prestige(state, tribe, gain)
            tribe.famine_during_winter = False
    if state.tick_count > 0 and state.tick_count % 4 == 0:
        for tid, tribe in state.tribes.items():
            pop = sum(b.population for b in state.bands.values() if b.tribe_id == tid)
            if pop <= 0:
                continue
            # Un grand peuple gagne du prestige, jusqu'a un plafond qui suit sa
            # taille (sinon toutes les IA finissaient a 100).
            if pop >= 80 and tribe.prestige < 40 + pop // 10:
                gain_prestige(state, tribe, 1)
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
    povs: dict = field(default_factory=dict)
    situations: list = field(default_factory=list)
    next_situation_uid: int = 1
    situation_last: dict = field(default_factory=dict)
    battles: list = field(default_factory=list)
    next_battle_uid: int = 1
    day: int = 0
    step: int = 0
    research: dict = field(default_factory=dict)


def snapshot(state: GameState) -> _Snap:
    return _Snap(
        clock=copy.copy(state.clock),
        # Copies d'apres leurs champs (records.py) : rien de modifiable partage.
        tribes={tid: records.copy(t) for tid, t in state.tribes.items()},
        bands={bid: records.copy(b) for bid, b in state.bands.items()},
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
        povs={
            tid: Pov(GameLog(entries=list(p.log.entries), seq=p.log.seq), p.vision, set(p.seen))
            for tid, p in state.povs.items()
        },
        situations=_copy_situations(state.situations),
        next_situation_uid=state.next_situation_uid,
        situation_last=dict(state.situation_last),
        battles=copy.deepcopy(state.battles),
        next_battle_uid=state.next_battle_uid,
        day=state.day,
        step=state.step,
        research=records.json_copy(state.research),
    )


def _copy_situations(items) -> list:
    if not items:
        return []
    return situations.copy_all(items)


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
    state.povs = saved.povs
    state.situations = saved.situations
    state.next_situation_uid = saved.next_situation_uid
    state.situation_last = saved.situation_last
    state.battles = saved.battles
    state.next_battle_uid = saved.next_battle_uid
    state.day = saved.day
    state.step = saved.step
    state.research = saved.research
    recompute_vision(state)


def _default_world() -> World:
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
    # Pas de carte cuite : on la genere (numpy, lent ; seulement dans ce cas).
    world = generate_world(seed=42)
    if not getattr(sys, "frozen", False):
        try:
            save_world(world, candidates[0])
        except OSError:
            pass
    return world


def new_game(
    world: World | None = None,
    minor_peoples: int | None = None,
    setup: dict | None = None,
    others: dict | None = None,
) -> GameState:
    """Une partie neuve. setup (menu de demarrage) : "name", "color" et
    "bonuses" (tech.START_BONUSES) de la tribu du joueur. others
    (multijoueur) : {place: setup} des autres joueurs, places 2 a 4
    (steppe, foret, cote) ; les places libres restent a l'IA."""
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
    seats = {PLAYER_TRIBE_ID: setup} if setup else {}
    for tid, extra in sorted((others or {}).items()):
        if int(tid) in tribes and int(tid) != PLAYER_TRIBE_ID:
            seats[int(tid)] = extra or {}
    for tid, seat in seats.items():
        player = tribes[tid]
        if seat.get("name"):
            player.name = str(seat["name"])[:24]
        if seat.get("color"):
            player.color = tuple(int(c) for c in seat["color"])
        tech.set_start_bonuses(player, seat.get("bonuses", ()), 0)
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
    # Les autres joueurs gardent le savoir de leur pays (troupeau pour la
    # steppe, cabotage pour la cote) : start_knowledge est passe avant.
    for tid in seats:
        tribes[tid].is_player = True
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
    # Les tirages des savoirs : la graine de la partie (le menu en tire une ;
    # sans elle, la meme pour toutes : les tests, l'empreinte).
    draws.set_seed(st, int((setup or {}).get("seed", 1)))
    turning.migrate(st)
    if minor_peoples is None:
        # Les petites cartes des tests restent a 4 peuples.
        minor_peoples = MINOR_START if world.width >= 300 else 0
    if minor_peoples:
        add_minor_peoples(st, minor_peoples)
    recompute_vision(st)
    memory.update(st)
    _note_spotted_enemies(st)
    learning.update_practice(st, count=False)
    return st


def add_minor_peoples(state: GameState, count: int, avoid=None) -> list[int]:
    """Petits peuples : une bande chacun, loin de tous les autres."""
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
    """Un pas de la partie : une SEMAINE ; ou un JOUR quand une bataille touche
    un joueur (battle.slow : le temps ralentit en bataille). Sept jours font la
    semaine. state.step compte les pas (le multijoueur s'y cale)."""
    saved = snapshot(state)
    tech.begin_tick()
    try:
        if battle.slow(state):
            battle.advance(state, 1, humans=True)
            remove_dead_bands(state)
            state.day += 1
            if state.day >= 7:
                state.day = 0
                _week(state, 0)
        else:
            days = 7 - state.day
            state.day = 0
            _week(state, days)
        state.step += 1
        state.last_error = None
    except Exception as exc:
        _restore(state, saved)
        state.clock.paused = True
        state.last_error = str(exc)
    finally:
        tech.end_tick()


def _week(state: GameState, battle_days: int) -> None:
    """La semaine du monde. Les batailles sans joueur y font `battle_days`
    jours."""
    prev_season = state.clock.season()
    state.clock.advance_week()
    if state.clock.season() is not prev_season:
        note_all(
            state,
            LogKind.SAISON,
            f"{season_fr(state.clock.season())} commence.",
        )
    apply_season_spread(state)
    apply_movement(state)
    resolve_joins(state)
    systems.run(systems.WEEKLY, state)
    learning.update_practice(state)
    prune_fight_marks(state)
    resolve_raids(state)
    if battle_days:
        battle.advance(state, battle_days, humans=False)
    update_exhaustion(state)
    collect_food(state)
    remove_dead_bands(state)
    sites.update(state)
    state.tick_count += 1
    monthly = state.tick_count % 4 == 0
    if monthly:
        update_population(state)
        population.monthly(state)
    update_influence(state)
    if monthly:
        # Le mois de chaque systeme, dans l'ordre du tableau (systems.py).
        systems.run(systems.MONTHLY, state)
    events.weekly(state)
    tech.invalidate()
    update_prestige(state)
    learning.update_learning(state)
    tech.invalidate()
    recompute_vision(state)
    memory.update(state)
    _note_spotted_enemies(state)
    decide_ai(state)


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
