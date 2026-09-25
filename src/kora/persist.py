from __future__ import annotations

import json
import os
import random
import sys
import time
from pathlib import Path

from src.kora import chiefs, diplo, events, sites
from src.kora.clock import Clock
from src.kora.log import LOG_CAP, GameLog, LogEntry, LogKind
from src.kora.sim import GameState
from src.kora.types import Band, FightMark, Hex, Order, OrderKind, Season, Tribe
from src.kora.vision import PlayerVision, recompute_vision
from src.kora.world import World, offset_to_axial

SAVE_VERSION = 1


def default_save_path() -> Path:
    if getattr(sys, "frozen", False):
        root = Path(os.environ.get("APPDATA") or Path.home()) / "Kora"
    else:
        root = Path(__file__).resolve().parents[2]
    return root / "saves" / "kora.json"


def set_aside_save(path: Path) -> Path | None:
    """Sauvegarde illisible (autre carte, autre version) : on la renomme au
    lieu de l'ecraser avec la nouvelle partie."""
    path = Path(path)
    if not path.exists():
        return None
    stamp = time.strftime("%Y%m%d-%H%M%S")
    target = path.with_name(f"{path.stem}-ancienne-{stamp}{path.suffix}")
    try:
        path.replace(target)
    except OSError:
        return None
    return target


def _hex_to_list(h: Hex) -> list[int]:
    return [h.q, h.r]


def _hex_from_list(data) -> Hex:
    return Hex(int(data[0]), int(data[1]))


def _rng_to_json(rng: random.Random) -> dict:
    ver, mt, gauss = rng.getstate()
    return {"ver": ver, "mt": list(mt), "gauss": gauss}


def _rng_from_json(data: dict) -> random.Random:
    rng = random.Random()
    gauss = data.get("gauss")
    rng.setstate((data["ver"], tuple(data["mt"]), gauss))
    return rng


def _order_to_json(order: Order) -> dict:
    payload = {
        "kind": order.kind.value,
        "target_hex": None if order.target_hex is None else _hex_to_list(order.target_hex),
        "target_band_id": order.target_band_id,
    }
    return payload


def _order_from_json(data: dict) -> Order:
    kind = OrderKind(data["kind"])
    target = data.get("target_hex")
    return Order(
        kind=kind,
        target_hex=None if target is None else _hex_from_list(target),
        target_band_id=data.get("target_band_id"),
    )


def _band_to_json(band: Band) -> dict:
    return {
        "id": band.id,
        "tribe_id": band.tribe_id,
        "position": _hex_to_list(band.position),
        "population": band.population,
        "stock": band.stock,
        "order": _order_to_json(band.order),
        "path": [_hex_to_list(h) for h in band.path],
        "famine_in_period": band.famine_in_period,
        "recent_goals": [_hex_to_list(h) for h in band.recent_goals],
        "growth_acc": band.growth_acc,
        "last_raid_tick": band.last_raid_tick,
        "retreating": band.retreating,
        "shield_until": band.shield_until,
        "intent_prey": band.intent_prey,
        "intent_until": band.intent_until,
        "leader": chiefs.person_to_json(band.leader),
        "loyalty": band.loyalty,
        "honored": band.honored,
        "famine_tick": band.famine_tick,
        "village": band.village,
        "kind": band.kind,
        "home": band.home,
        "raised": band.raised,
        "units": [list(u) for u in band.units],
        "homebound": band.homebound,
        "notables": [chiefs.person_to_json(p) for p in band.notables],
        "welded_until": band.welded_until,
        "autonomy": band.autonomy,
    }


def _band_from_json(data: dict) -> Band:
    return Band(
        id=int(data["id"]),
        tribe_id=int(data["tribe_id"]),
        position=_hex_from_list(data["position"]),
        population=int(data["population"]),
        stock=float(data["stock"]),
        order=_order_from_json(data["order"]),
        path=[_hex_from_list(h) for h in data.get("path", [])],
        famine_in_period=bool(data.get("famine_in_period", False)),
        recent_goals=[_hex_from_list(h) for h in data.get("recent_goals", [])],
        growth_acc=float(data.get("growth_acc", 0.0)),
        last_raid_tick=int(data.get("last_raid_tick", -1000)),
        retreating=bool(data.get("retreating", False)),
        shield_until=int(data.get("shield_until", 0)),
        intent_prey=int(data.get("intent_prey", 0)),
        intent_until=int(data.get("intent_until", 0)),
        leader=chiefs.person_from_json(data.get("leader")),
        loyalty=float(data.get("loyalty", chiefs.START_LOYALTY)),
        honored=int(data.get("honored", -1000)),
        famine_tick=int(data.get("famine_tick", -1000)),
        village=int(data.get("village", 0)),
        kind=str(data.get("kind", "")),
        home=int(data.get("home", 0)),
        raised=int(data.get("raised", 0)),
        units=[[str(u[0]), int(u[1]), int(u[2])] for u in data.get("units", [])],
        homebound=bool(data.get("homebound", False)),
        notables=[p for p in (chiefs.person_from_json(x) for x in data.get("notables", [])) if p is not None],
        welded_until=int(data.get("welded_until", 0)),
        autonomy=float(data.get("autonomy", 0.0)),
    )


def _tribe_to_json(tribe: Tribe) -> dict:
    return {
        "id": tribe.id,
        "name": tribe.name,
        "prestige": tribe.prestige,
        "is_player": tribe.is_player,
        "famine_during_winter": tribe.famine_during_winter,
        "cabotage": tribe.cabotage,
        "shore_seen": tribe.shore_seen,
        "coast_weeks": tribe.coast_weeks,
        "troupeau": tribe.troupeau,
        "steppe_seen": tribe.steppe_seen,
        "steppe_weeks": tribe.steppe_weeks,
        "knowledge": sorted(tribe.knowledge),
        "learning": tribe.learning,
        "progress": dict(tribe.progress),
        "practice": dict(tribe.practice),
        "culture": tribe.culture,
        "color": list(tribe.color),
        "minor": tribe.minor,
        "origin": tribe.origin,
        "founded": tribe.founded,
        "flags": dict(tribe.flags),
        "chief_band": tribe.chief_band,
        "heir": tribe.heir,
        "settled_at": tribe.settled_at,
        "civ": tribe.civ,
        "goods": {k: round(v, 3) for k, v in tribe.goods.items()},
        "trade": tribe.trade,
    }


def _tribe_from_json(data: dict) -> Tribe:
    return Tribe(
        id=int(data["id"]),
        name=str(data["name"]),
        prestige=int(data["prestige"]),
        is_player=bool(data["is_player"]),
        famine_during_winter=bool(data.get("famine_during_winter", False)),
        cabotage=bool(data.get("cabotage", False)),
        shore_seen=bool(data.get("shore_seen", False)),
        coast_weeks=int(data.get("coast_weeks", 0)),
        troupeau=bool(data.get("troupeau", False)),
        steppe_seen=bool(data.get("steppe_seen", False)),
        steppe_weeks=int(data.get("steppe_weeks", 0)),
        knowledge=set(data.get("knowledge", [])),
        learning=data.get("learning"),
        progress={str(k): float(v) for k, v in data.get("progress", {}).items()},
        practice={str(k): int(v) for k, v in data.get("practice", {}).items()},
        culture=str(data.get("culture", "")),
        color=tuple(int(c) for c in data.get("color", ())),
        minor=bool(data.get("minor", False)),
        origin=int(data.get("origin", 0)),
        founded=int(data.get("founded", 1)),
        flags={str(k): int(v) for k, v in data.get("flags", {}).items()},
        chief_band=int(data.get("chief_band", 0)),
        heir=int(data.get("heir", 0)),
        settled_at=int(data.get("settled_at", -1)),
        civ=int(data.get("civ", 0)),
        goods={str(k): float(v) for k, v in data.get("goods", {}).items()},
        trade=data.get("trade", {}) if isinstance(data.get("trade", {}), dict) else {},
    )


def _log_to_json(log: GameLog) -> dict:
    return {
        "seq": log.seq,
        "entries": [
            {
                "year": e.year,
                "week": e.week,
                "kind": e.kind.value,
                "text": e.text,
                "seq": e.seq,
                "hex": None if e.hex is None else _hex_to_list(e.hex),
            }
            for e in log.entries
        ],
    }


def _log_from_json(data) -> GameLog:
    log = GameLog()
    if not isinstance(data, dict):
        return log
    rows = []
    for raw in data.get("entries", []):
        try:
            rows.append(
                LogEntry(
                    year=int(raw["year"]),
                    week=int(raw["week"]),
                    kind=LogKind(raw["kind"]),
                    text=str(raw["text"]),
                    seq=int(raw.get("seq", 0)),
                    hex=None if raw.get("hex") is None else _hex_from_list(raw["hex"]),
                )
            )
        except (KeyError, TypeError, ValueError):
            continue
    log.entries = rows[-LOG_CAP:]
    seq = data.get("seq")
    log.seq = int(seq) if seq is not None else (rows[-1].seq if rows else 0)
    return log


def _view_to_json(view: dict | None) -> dict:
    view = view or {}
    return {
        "camera_x": float(view.get("camera_x", 0.0)),
        "camera_y": float(view.get("camera_y", 0.0)),
        "zoom": float(view.get("zoom", 1.0)),
        "selected": view.get("selected"),
        "globe_yaw": float(view.get("globe_yaw", 0.0)),
        "globe_pitch": float(view.get("globe_pitch", 0.0)),
    }


def _fight_to_json(mark: FightMark) -> dict:
    return {
        "hex": _hex_to_list(mark.hex),
        "tick": mark.tick,
        "year": mark.year,
        "week": mark.week,
        "winner_tribe": mark.winner_tribe,
        "loser_tribe": mark.loser_tribe,
        "winner_name": mark.winner_name,
        "loser_name": mark.loser_name,
        "winner_before": mark.winner_before,
        "loser_before": mark.loser_before,
        "winner_loss": mark.winner_loss,
        "loser_loss": mark.loser_loss,
        "loot": mark.loot,
        "report": mark.report,
    }


def _fight_from_json(data: dict) -> FightMark:
    return FightMark(
        hex=_hex_from_list(data["hex"]),
        tick=int(data["tick"]),
        year=int(data["year"]),
        week=int(data["week"]),
        winner_tribe=int(data["winner_tribe"]),
        loser_tribe=int(data["loser_tribe"]),
        winner_name=str(data["winner_name"]),
        loser_name=str(data["loser_name"]),
        winner_before=int(data["winner_before"]),
        loser_before=int(data["loser_before"]),
        winner_loss=int(data["winner_loss"]),
        loser_loss=int(data["loser_loss"]),
        loot=float(data["loot"]),
        report=data.get("report") if isinstance(data.get("report"), dict) else None,
    )


def save_game(state: GameState, path: Path, view: dict | None = None) -> None:
    vis = state.vision if isinstance(state.vision, PlayerVision) else None
    explored = []
    if vis is not None:
        explored = [_hex_to_list(h) for h in vis.explored]
    exhaustion = []
    for col, row in state.world._recovering:
        exhaustion.append([col, row, state.world._exhaustion[row][col]])
    influence = []
    for (col, row), cell in state.world._influence.items():
        influence.append([col, row, {str(tid): val for tid, val in cell.items()}])
    payload = {
        "version": SAVE_VERSION,
        "map": {
            "width": state.world.width,
            "height": state.world.height,
            "wrap_x": state.world.wrap_x,
        },
        "clock": {
            "year": state.clock.year,
            "week": state.clock.week,
            "paused": state.clock.paused,
            "speed": state.clock.speed,
            "finished_winter": state.clock._finished_winter,
        },
        "tick_count": state.tick_count,
        "next_band_id": state.next_band_id,
        "player_dead": state.player_dead,
        "rng": _rng_to_json(state.rng),
        "story_rng": _rng_to_json(state.story_rng),
        "chief_seats": True,
        "next_tribe_id": state.next_tribe_id,
        "next_person_id": state.next_person_id,
        "next_site_id": state.next_site_id,
        "sites": [sites.to_json(s) for s in state.sites.values()],
        "diplo": diplo.to_json(state.diplo),
        "presence": [
            [tid, [[h.q, h.r, w] for h, w in spots.items()]] for tid, spots in state.presence.items()
        ],
        "overlap": [[a, b, n] for (a, b), n in state.overlap.items()],
        "events": events.to_json(state.events),
        "tribes": [_tribe_to_json(t) for t in state.tribes.values()],
        "bands": [_band_to_json(b) for b in state.bands.values()],
        "explored": explored,
        "exhaustion": exhaustion,
        "influence": influence,
        "hex_season": ["".join(str(v) for v in row) for row in state.world._hex_season],
        "aimed_season": state.world._aimed_season.value,
        "log": _log_to_json(state.log),
        "seen_enemy_tribes": sorted(state.seen_enemy_tribes),
        "fights": [_fight_to_json(m) for m in state.fights],
        "view": _view_to_json(view),
    }
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload), encoding="utf-8")


def load_game(path: Path, world: World) -> tuple[GameState, dict] | None:
    path = Path(path)
    if not path.exists():
        return None
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError, UnicodeDecodeError):
        return None
    if not isinstance(data, dict) or data.get("version") != SAVE_VERSION:
        return None
    info = data.get("map") or {}
    if (
        int(info.get("width", -1)) != world.width
        or int(info.get("height", -1)) != world.height
        or bool(info.get("wrap_x", False)) != world.wrap_x
    ):
        return None
    try:
        clock = Clock()
        ck = data["clock"]
        clock.year = int(ck["year"])
        clock.week = int(ck["week"])
        clock.paused = bool(ck["paused"])
        clock.speed = int(ck["speed"])
        clock._finished_winter = bool(ck.get("finished_winter", False))
        tribes = {}
        for raw in data["tribes"]:
            tribe = _tribe_from_json(raw)
            if "knowledge" not in raw:
                # Sauvegarde d'avant les savoirs : feu, outils, et ce que les
                # anciens drapeaux disaient.
                from src.kora import tech

                tech.start_knowledge(tribe)
                if tribe.cabotage:
                    tribe.knowledge.update(("peche", "pirogue"))
                if tribe.troupeau:
                    tribe.knowledge.update(("epieu", "troupeau"))
            tribes[tribe.id] = tribe
        bands = {}
        for raw in data["bands"]:
            band = _band_from_json(raw)
            bands[band.id] = band
        state = GameState(
            world=world,
            clock=clock,
            tribes=tribes,
            bands=bands,
            tick_count=int(data.get("tick_count", 0)),
            rng=_rng_from_json(data["rng"]),
            player_dead=bool(data.get("player_dead", False)),
            log=_log_from_json(data.get("log")),
            seen_enemy_tribes={
                int(tid) for tid in data.get("seen_enemy_tribes", [])
            },
            fights=[
                _fight_from_json(raw)
                for raw in data.get("fights", [])
                if isinstance(raw, dict)
            ],
            next_band_id=int(data.get("next_band_id", 0)),
            next_tribe_id=int(data.get("next_tribe_id", max(tribes, default=0) + 1)),
        )
        if isinstance(data.get("story_rng"), dict):
            state.story_rng = _rng_from_json(data["story_rng"])
        from src.kora.peoples import LEGACY_COLOR, LEGACY_CULTURE, free_color

        for tribe in tribes.values():
            # Sauvegarde d'avant les peuples en donnees.
            if not tribe.culture:
                tribe.culture = LEGACY_CULTURE.get(tribe.id, "vallee")
            if not tribe.color:
                tribe.color = LEGACY_COLOR.get(tribe.id) or free_color(tribes.values())
        state.next_person_id = int(data.get("next_person_id", 1))
        state.next_site_id = int(data.get("next_site_id", 1))
        state.sites = {}
        for raw in data.get("sites", []):
            site = sites.from_json(raw)
            state.sites[site.id] = site
        state.diplo = diplo.from_json(data.get("diplo"))
        if "diplo" not in data:
            # Avant la diplomatie : on connait les peuples deja apercus.
            for tid in state.seen_enemy_tribes:
                if tid in tribes:
                    state.diplo.contacts.add(diplo.pair(1, tid))
        state.presence = {}
        for tid, spots in data.get("presence", []):
            state.presence[int(tid)] = {Hex(int(q), int(r)): float(w) for q, r, w in spots}
        state.overlap = {(int(a), int(b)): int(n) for a, b, n in data.get("overlap", [])}
        state.events = events.from_json(data.get("events"))
        state.story = True
        # Avant les chefs : chaque bande recoit le sien.
        chiefs.ensure(state)
        if not data.get("chief_seats"):
            # Sauvegarde d'avant la scission du village (2026-09-25) : le chef
            # d'un peuple qui a deja un village vient y gouverner.
            from src.kora import villages

            villages.seat_chiefs(state)
        world._exhaustion = [[1.0 for _ in range(world.width)] for _ in range(world.height)]
        world._recovering = set()
        world._influence = {}
        world._influence_cells = set()
        for col, row, value in data.get("exhaustion", []):
            if 0 <= row < world.height and 0 <= col < world.width:
                hx = offset_to_axial(int(col), int(row))
                world.set_exhaustion(hx, float(value))
        for col, row, cell in data.get("influence", []):
            key = (int(col), int(row))
            parsed = {int(tid): float(val) for tid, val in cell.items()}
            if parsed:
                world._influence[key] = parsed
                world._influence_cells.add(key)
        raw_seasons = data.get("hex_season")
        if isinstance(raw_seasons, list) and len(raw_seasons) == world.height:
            grid = []
            for line in raw_seasons:
                row = [int(ch) for ch in line]
                if len(row) != world.width:
                    raise ValueError("hex_season width")
                grid.append(row)
            world._hex_season = grid
            aimed = data.get("aimed_season")
            world._aimed_season = Season(aimed) if aimed else clock.season()
            world.rebuild_season_frontier()
            world._season_gen += 1
        else:
            world.fill_season(clock.season())
        recompute_vision(state)
        vis = state.vision
        if isinstance(vis, PlayerVision):
            vis.explored |= {_hex_from_list(h) for h in data.get("explored", [])}
        if "diplo" not in data and world.width >= 300 and len(tribes) <= 4:
            # Partie d'avant les petits peuples : ils naissent hors de ce que
            # le joueur a deja explore (ils etaient la, on ne les voyait pas).
            from src.kora.peoples import MINOR_START
            from src.kora.sim import add_minor_peoples

            add_minor_peoples(state, MINOR_START, avoid=vis.explored if isinstance(vis, PlayerVision) else None)
        view = _view_to_json(data.get("view"))
        return state, view
    except (KeyError, TypeError, ValueError, AttributeError):
        return None
