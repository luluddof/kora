from __future__ import annotations

import json
import os
import random
import sys
import time
from pathlib import Path

from src.kora import __version__
from src.kora import battle, chiefs, diplo, draws, events, memory, records, sites, situations, tech, turning, villages
from src.kora.clock import Clock
from src.kora.log import GameLog, LOG_CAP, LogEntry, LogKind
from src.kora.gamestate import GameState, Pov
from src.kora.types import Band, FightMark, Hex, Season, Tribe
from src.kora.vision import PlayerVision, recompute_vision
from src.kora.world import World, offset_to_axial
from src.kora.francais import convert
from src.kora.peoples import LEGACY_COLOR, LEGACY_CULTURE, MINOR_START, free_color
from src.kora.sim import add_minor_peoples

SAVE_VERSION = 1


def default_save_path() -> Path:
    if getattr(sys, "frozen", False):
        root = Path(os.environ.get("APPDATA") or Path.home()) / "Kora"
    else:
        root = Path(__file__).resolve().parents[2]
    return root / "saves" / "kora.json"


def multi_save_path() -> Path:
    """La partie multijoueur de l'hote (a cote de la partie solo)."""
    return default_save_path().with_name("kora-multi.json")


def prefs_path() -> Path:
    """Les reglages du joueur (nom, couleur, bonus, derniere adresse)."""
    return default_save_path().with_name("reglages.json")


def load_prefs() -> dict:
    try:
        data = json.loads(prefs_path().read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return {}
    return data if isinstance(data, dict) else {}


def save_prefs(prefs: dict) -> None:
    path = prefs_path()
    try:
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(json.dumps(prefs), encoding="utf-8")
    except OSError:
        pass


KEEP_ASIDE = 5

# --- les sauvegardes : une par partie ------------------------------------------------
# Chaque partie solo a SA sauvegarde dans le dossier des sauvegardes (la
# premiere, d'avant : kora.json ; les suivantes : partie-<date>.json). Le
# menu "Continuer" reprend la plus recente qui se lit ; "Charger une
# partie" les montre toutes. Supprimer met le fichier a la corbeille (un
# dossier a cote : on peut le recuperer a la main ; CORBEILLE_KEEP au plus).
# La partie a plusieurs (kora-multi.json) et les reglages n'en sont pas.
NOT_SAVES = ("kora-multi.json", "reglages.json")
CORBEILLE = "corbeille"
CORBEILLE_KEEP = 20


def saves_dir() -> Path:
    return default_save_path().parent


def new_save_path() -> Path:
    """Le fichier d'une partie neuve (ou d'une copie) : jamais un existant."""
    root = saves_dir()
    stamp = time.strftime("%Y%m%d-%H%M%S")
    path = root / f"partie-{stamp}.json"
    n = 2
    while path.exists():
        path = root / f"partie-{stamp}-{n}.json"
        n += 1
    return path


def list_saves() -> list[dict]:
    """Les sauvegardes solo, la plus recente d'abord : {"path", "time" (date
    du fichier), "info" (peek_save ; None : elle ne se lit pas)}."""
    root = saves_dir()
    out = []
    try:
        files = [p for p in root.glob("*.json") if p.name not in NOT_SAVES]
    except OSError:
        return []
    for path in files:
        try:
            when = path.stat().st_mtime
        except OSError:
            continue
        out.append({"path": path, "time": when, "info": peek_save(path)})
    out.sort(key=lambda s: (-s["time"], s["path"].name))
    return out


def latest_save() -> Path | None:
    """La sauvegarde la plus recente qui se lit (Continuer)."""
    return next((s["path"] for s in list_saves() if s["info"] is not None), None)


def trash_save(path: Path) -> bool:
    """Supprimer une sauvegarde : elle va a la corbeille (recuperable)."""
    path = Path(path)
    bin_ = path.parent / CORBEILLE
    try:
        bin_.mkdir(parents=True, exist_ok=True)
        target = bin_ / path.name
        if target.exists():
            target = bin_ / f"{path.stem}-{time.strftime('%Y%m%d-%H%M%S')}{path.suffix}"
        path.replace(target)
    except OSError:
        return False
    old = sorted(bin_.glob("*.json"), key=lambda p: p.stat().st_mtime)
    for extra in old[:-CORBEILLE_KEEP]:
        try:
            extra.unlink()
        except OSError:
            pass
    return True


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
    # Chaque nouvelle partie met l'ancienne de cote : on en garde les
    # KEEP_ASIDE dernieres (pas un dossier qui grossit sans fin).
    old = sorted(path.parent.glob(f"{path.stem}-ancienne-*{path.suffix}"), key=lambda p: p.name)
    for extra in old[:-KEEP_ASIDE]:
        try:
            extra.unlink()
        except OSError:
            pass
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


def _accents(text: str) -> str:
    """Les journaux d'avant les accents (version 0.2) : on les leur rend."""
    if text.isascii():
        return convert(text)
    return text


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
                    text=_accents(str(raw["text"])),
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
    payload = game_to_json(state, view)
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload), encoding="utf-8")


def dumps_game(state: GameState, view: dict | None = None) -> str:
    """La partie en texte (multijoueur : ce que l'hote envoie aux autres)."""
    return json.dumps(game_to_json(state, view))


def loads_game(text: str, world: World) -> tuple[GameState, dict] | None:
    try:
        data = json.loads(text)
    except (ValueError, TypeError):
        return None
    return game_from_json(data, world)


def _memory_to_json(vis) -> dict:
    """La memoire du brouillard (memory.py) : les lieux, les zones."""
    if vis is None:
        return {}
    return {
        "sites": [[sid, *e] for sid, e in sorted(vis.sites.items())],
        "zones": [[c, r, t, v] for (c, r), (t, v) in sorted(vis.zones.items())],
    }


def _memory_from_json(vis, data) -> None:
    if not isinstance(vis, PlayerVision) or not isinstance(data, dict):
        return
    vis.sites = {int(r[0]): [int(r[1]), int(r[2]), str(r[3]), int(r[4]), bool(r[5]), int(r[6]) if len(r) > 6 else 0] for r in data.get("sites", [])}
    vis.zones = {(int(r[0]), int(r[1])): [int(r[2]), float(r[3])] for r in data.get("zones", [])}
    vis.mem_gen += 1


def _pov_to_json(pov) -> dict:
    vis = pov.vision if isinstance(pov.vision, PlayerVision) else None
    return {
        "log": _log_to_json(pov.log),
        "explored": [_hex_to_list(h) for h in vis.explored] if vis is not None else [],
        "memory": _memory_to_json(vis),
        "seen": sorted(pov.seen),
    }


def game_to_json(state: GameState, view: dict | None = None) -> dict:
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
        "game_version": __version__,
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
        # Pression de cueillette de la derniere semaine : l'epuisement des
        # terres de la semaine suivante en depend (sans elle, recharger
        # changeait la suite de la partie).
        "pressure": [[h.q, h.r, p] for h, p in state.last_pressure.items()],
        "events": events.to_json(state.events),
        # Tribus et bandes : d'apres leurs champs (records.py, types.py).
        "tribes": [records.to_json(t) for t in state.tribes.values()],
        "bands": [records.to_json(b) for b in state.bands.values()],
        "explored": explored,
        "memory": _memory_to_json(vis),
        "exhaustion": exhaustion,
        "influence": influence,
        "hex_season": ["".join(str(v) for v in row) for row in state.world._hex_season],
        "aimed_season": state.world._aimed_season.value,
        "log": _log_to_json(state.log),
        "seen_enemy_tribes": sorted(state.seen_enemy_tribes),
        "fights": [_fight_to_json(m) for m in state.fights],
        "view": _view_to_json(view),
        # Multijoueur : journal, carte exploree, peuples apercus des autres
        # joueurs (le joueur solo : log, explored, seen_enemy_tribes).
        "povs": [[tid, _pov_to_json(pov)] for tid, pov in sorted(state.povs.items()) if tid in state.tribes],
        "situations": [situations.to_json(s) for s in state.situations],
        "battles": [battle.to_json(b) for b in state.battles if not b.outcome],
        "next_battle_uid": state.next_battle_uid,
        "research": records.json_copy(state.research),
        "day": state.day,
        "step": state.step,
        "next_situation_uid": state.next_situation_uid,
        "situation_last": dict(state.situation_last),
    }
    return payload


def load_game(path: Path, world: World) -> tuple[GameState, dict] | None:
    path = Path(path)
    if not path.exists():
        return None
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError, UnicodeDecodeError):
        return None
    return game_from_json(data, world)


def game_from_json(data, world: World) -> tuple[GameState, dict] | None:
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
            tribe = records.from_json(Tribe, raw)
            if "knowledge" not in raw:
                # Sauvegarde d'avant les savoirs : feu, outils, et ce que les
                # anciens drapeaux disaient.
                tech.start_knowledge(tribe)
                if tribe.cabotage:
                    tribe.knowledge.update(("peche", "pirogue"))
                if tribe.troupeau:
                    tribe.knowledge.update(("epieu", "troupeau"))
            tribes[tribe.id] = tribe
        bands = {}
        for raw in data["bands"]:
            band = records.from_json(Band, raw)
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
        state.last_pressure = {Hex(int(q), int(r)): float(p) for q, r, p in data.get("pressure", [])}
        state.situations = [s for s in (situations.from_json(raw) for raw in data.get("situations", [])) if s is not None]
        state.next_situation_uid = int(data.get("next_situation_uid", 1))
        state.battles = [b for b in (battle.from_json(raw) for raw in data.get("battles", [])) if b is not None]
        state.next_battle_uid = int(data.get("next_battle_uid", 1))
        state.day = int(data.get("day", 0))
        state.step = int(data.get("step", data.get("tick_count", 0)))
        state.situation_last = {str(k): int(v) for k, v in data.get("situation_last", {}).items()}
        state.research = dict(data.get("research") or {})
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
        explored_of = {}
        memory_of = {}
        for tid, raw in data.get("povs", []):
            tid = int(tid)
            if tid in tribes and isinstance(raw, dict):
                state.povs[tid] = Pov(log=_log_from_json(raw.get("log")), seen={int(t) for t in raw.get("seen", [])})
                explored_of[tid] = raw.get("explored", [])
                memory_of[tid] = raw.get("memory")
        recompute_vision(state)
        vis = state.vision
        if isinstance(vis, PlayerVision):
            vis.explored |= {_hex_from_list(h) for h in data.get("explored", [])}
            _memory_from_json(vis, data.get("memory"))
        for tid, cells in explored_of.items():
            pov_vis = state.povs[tid].vision
            if isinstance(pov_vis, PlayerVision):
                pov_vis.explored |= {_hex_from_list(h) for h in cells}
                _memory_from_json(pov_vis, memory_of.get(tid))
        # Une vieille partie sans memoire du brouillard : ce qu'il a explore,
        # tel qu'il est aujourd'hui ; puis ce qu'il voit.
        memory.seed(state)
        memory.update(state)
        # Une partie d'avant les tirages et les grands tournants : sa graine
        # (tiree de ses peuples), et les tournants a qui sait deja leur pan.
        if "seed" not in state.research:
            draws.set_seed(state, draws.seed_from(state))
        turning.migrate(state)
        if "diplo" not in data and world.width >= 300 and len(tribes) <= 4:
            # Partie d'avant les petits peuples : ils naissent hors de ce que
            # le joueur a deja explore (ils etaient la, on ne les voyait pas).
            add_minor_peoples(state, MINOR_START, avoid=vis.explored if isinstance(vis, PlayerVision) else None)
        view = _view_to_json(data.get("view"))
        return state, view
    except (KeyError, TypeError, ValueError, AttributeError):
        return None


def peek_save(path: Path) -> dict | None:
    """Ce que le menu de demarrage montre d'une sauvegarde (bouton
    Continuer) : annee, semaine, nom du peuple, gens, villages. None si
    elle manque ou ne se lit pas."""
    try:
        data = json.loads(Path(path).read_text(encoding="utf-8"))
        if data.get("version") != SAVE_VERSION:
            return None
        player = next((t for t in data.get("tribes", []) if t.get("is_player")), None)
        pid = player["id"] if player else 1
        pop = sum(int(b.get("population", 0)) for b in data.get("bands", []) if b.get("tribe_id") == pid)
        villages = sum(1 for s in data.get("sites", []) if s.get("kind") == "village" and s.get("tribe_id") == pid)
        return {
            "year": int(data["clock"]["year"]),
            "week": int(data["clock"]["week"]),
            "name": player.get("name", "?") if player else "?",
            "color": tuple(player.get("color", ())) if player else (),
            "population": pop,
            "villages": villages,
            "dead": bool(data.get("player_dead", False)),
            "game_version": str(data.get("game_version", "")),
        }
    except (OSError, ValueError, KeyError, TypeError):
        return None
