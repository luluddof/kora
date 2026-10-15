"""LES PLANETES (0.20) : celles qui sont livrees avec le jeu.

Chaque planete est cuite a l'avance (tools/cuire_planetes.py : numpy, des
minutes) dans data/planetes/<id>.json, avec sa vignette <id>.png ; le
catalogue est data/planetes/index.json (id, nom, graine, continents, sols).
L'ancienne carte (768 x 384, data/kora_map.json) garde l'id LEGACY : les
parties d'avant 0.20 la retrouvent (persist.game_from_json).
Une partie note sa planete (world.planet ; la sauvegarde : "map" -> "id") ;
en multijoueur, l'hote la choisit et les amis chargent la meme.
Pas de pygame ; le jeu n'y genere rien (deterministe : le meme fichier pour
tous).
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

from src.kora.world import World, cost_pct, load_world

LEGACY = "kora"
LEGACY_NAME = "L'ancienne Kora"
# Le choix du menu "au hasard" (une des planetes livrees, pas l'ancienne).
RANDOM = "hasard"


def _roots() -> list[Path]:
    """Ou chercher data/ : a cote du code, ou dans l'exe (PyInstaller)."""
    out: list[Path] = []
    if getattr(sys, "frozen", False):
        meipass = getattr(sys, "_MEIPASS", None)
        if meipass:
            out.append(Path(meipass) / "data")
        exe_dir = Path(sys.executable).resolve().parent
        out += [exe_dir / "data", exe_dir / "_internal" / "data"]
    else:
        out.append(Path(__file__).resolve().parents[2] / "data")
    return out


_CATALOG: list | None = None


def catalog() -> list[dict]:
    """Les planetes livrees (index.json), dans l'ordre ; vide sans elles."""
    global _CATALOG
    if _CATALOG is not None:
        return _CATALOG
    found: list = []
    for root in _roots():
        index = root / "planetes" / "index.json"
        if not index.exists():
            continue
        try:
            rows = json.loads(index.read_text(encoding="utf-8"))
        except (OSError, ValueError):
            continue
        for row in rows:
            if isinstance(row, dict) and (root / "planetes" / f"{row.get('id')}.json").exists():
                found.append(dict(row) | {"dir": str(root / "planetes")})
        if found:
            break
    _CATALOG = found
    return found


def ids() -> list[str]:
    return [row["id"] for row in catalog()]


def info(pid: str) -> dict | None:
    if pid == LEGACY:
        return {"id": LEGACY, "name": LEGACY_NAME}
    return next((row for row in catalog() if row["id"] == pid), None)


def name_of(pid: str) -> str:
    row = info(pid)
    return str(row.get("name", pid)) if row else pid


def thumbnail_path(pid: str) -> Path | None:
    row = info(pid)
    if not row or "dir" not in row:
        return None
    path = Path(row["dir"]) / f"{pid}.png"
    return path if path.exists() else None


def default_id() -> str:
    """La planete d'une partie neuve sans choix (et des tests) : la premiere
    livree, sinon l'ancienne."""
    planets = ids()
    return planets[0] if planets else LEGACY


def choose(choice: str | None, rng) -> str:
    """L'id d'une partie neuve : celui choisi, ou une planete au hasard."""
    planets = ids()
    if choice and choice != RANDOM and (choice in planets or choice == LEGACY):
        return choice
    return rng.choice(planets) if planets else LEGACY


def _legacy_path() -> Path | None:
    for root in _roots():
        path = root / "kora_map.json"
        if path.exists():
            return path
    return None


def load(pid: str) -> World | None:
    """Une planete fraiche (une partie la modifie : epuisement, influence) ;
    None si elle n'est pas la (une autre version du jeu)."""
    if pid == LEGACY:
        path = _legacy_path()
    else:
        row = info(pid)
        path = Path(row["dir"]) / f"{pid}.json" if row else None
    if path is None or not path.exists():
        return None
    try:
        world = load_world(path)
    except (KeyError, ValueError, OSError):
        return None
    world.planet = pid
    if pid == LEGACY:
        # L'ancienne carte n'a pas sa variation du cout de marche cuite : on la
        # calcule ici, au chargement (1 a 2 s, une fois par session), plutot qu'a
        # la premiere marche de la partie (l'ecran se figeait).
        cost_pct(world)
    return world
