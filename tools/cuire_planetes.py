"""Cuire les planetes du jeu (0.20) : data/planetes/<id>.json, <id>.png et
index.json.

    python tools/cuire_planetes.py            # toutes (PLANETS)
    python tools/cuire_planetes.py aurane     # une seule
    python tools/cuire_planetes.py --index    # le catalogue seul

Chaque planete : mapgen.generate_world (1536 x 768, numpy, ~3 min), puis un
CONTROLE (check) ; une graine qui ne passe pas est remplacee par la suivante
(graine + 1000) et on le dit. Les noms de l'atlas sont melanges par planete.
La vignette (300 x 150) : les sols, les rivieres, la glace. Le catalogue
garde : id, nom, graine, continents, traits (ce qui la distingue).
Outil de developpement (numpy) : le jeu, lui, ne fait que lire.
"""

from __future__ import annotations

import json
import os
import random
import sys
import time
from collections import Counter
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
os.environ.setdefault("SDL_VIDEODRIVER", "dummy")

from src.kora import mapgen  # noqa: E402
from src.kora.atlas import build_atlas_labels  # noqa: E402
from src.kora.resources import NAMES, PRESENT_BYTE  # noqa: E402
from src.kora.types import Terrain  # noqa: E402
from src.kora.world import landmass_grid, save_world  # noqa: E402

OUT = ROOT / "data" / "planetes"
# id, nom, graine de depart.
# Les graines sont reperees d'abord en petit (scout : 3 s) : la forme des
# continents ne depend pas de la resolution ; le CONTROLE juge en grand.
PLANETS = (
    ("aurane", "Aurane", 42),
    ("velmire", "Velmire", 1207),
    ("ondesie", "Ondésie", 909),
    ("caldere", "Caldère", 404),
    ("sylvene", "Sylvène", 808),
)
HABITABLE_MIN = 20000
TRAITS = {
    Terrain.SAVANE: "de grandes savanes",
    Terrain.JUNGLE: "des jungles",
    Terrain.TOUNDRA: "un grand nord",
    Terrain.DESERT: "des déserts",
    Terrain.FORET: "des forêts",
    Terrain.STEPPE: "des steppes",
    Terrain.MARAIS: "des marais",
    Terrain.MONTAGNE: "des montagnes",
}
# La part "normale" de chaque sol (les terres) : un trait, c'est 1,3 fois plus.
NORMAL = {
    Terrain.SAVANE: 0.15, Terrain.JUNGLE: 0.08, Terrain.TOUNDRA: 0.12, Terrain.DESERT: 0.06,
    Terrain.FORET: 0.17, Terrain.STEPPE: 0.05, Terrain.MARAIS: 0.012, Terrain.MONTAGNE: 0.05,
}


def check(world) -> tuple[list[str], dict]:
    """Ce qui ne va pas (liste vide : la planete est bonne) et ses mesures."""
    problems = []
    terr = Counter(t for row in world._terrains for t in row)
    land = sum(v for t, v in terr.items() if t not in (Terrain.EAU, Terrain.GLACE))
    grid = landmass_grid(world)
    habitable = Counter()
    for r in range(world.height):
        for c in range(world.width):
            mid = grid[r][c]
            if mid and world._terrains[r][c] not in (Terrain.MONTAGNE, Terrain.SOMMET, Terrain.GLACE):
                habitable[mid] += 1
    big = sorted((v for v in habitable.values() if v >= HABITABLE_MIN), reverse=True)
    if not 5 <= len(big) <= 8:
        problems.append(f"{len(big)} continents habitables (il en faut 5 a 8)")
    if big and not 70_000 <= big[0] <= 260_000:
        problems.append(f"le plus grand continent a {big[0]} cases habitables")
    rivers = sum(1 for v in world.rivers if v)
    if rivers / max(1, land) < 0.015:
        problems.append(f"trop peu de rivieres ({rivers / land:.1%})")
    for t in (Terrain.TOUNDRA, Terrain.MARAIS, Terrain.JUNGLE, Terrain.SAVANE, Terrain.DESERT, Terrain.VALLEE, Terrain.STEPPE):
        if terr[t] / max(1, land) < 0.004:
            problems.append(f"presque pas de {t.value}")
    # Chaque ressource sur plusieurs continents.
    for name in NAMES:
        layer = world.resources.get(name)
        if not layer:
            problems.append(f"pas de couche {name}")
            continue
        where = set()
        for i in range(0, len(layer), 7):
            if layer[i] >= PRESENT_BYTE:
                r, c = divmod(i, world.width)
                if grid[r][c] and habitable[grid[r][c]] >= HABITABLE_MIN:
                    where.add(grid[r][c])
        if name not in ("poisson",) and len(where) < 2:
            problems.append(f"{name} sur {len(where)} continent(s)")
    shares = {t: terr[t] / max(1, land) for t in TRAITS}
    traits = [TRAITS[t] for t, v in sorted(shares.items(), key=lambda it: -it[1] / NORMAL[it[0]]) if v >= 1.3 * NORMAL[t]][:2]
    return problems, {
        "continents": len(big),
        "biggest": big[0] if big else 0,
        "rivers": round(rivers / max(1, land), 4),
        "traits": " et ".join(traits) if traits else "des terres variées",
        "soils": {t.value: round(v / max(1, land), 3) for t, v in terr.items() if t is not Terrain.EAU},
    }


def thumbnail(world, path: Path) -> None:
    import pygame

    from src.kora.look import BIOME_COLORS

    w, h = 300, 150
    surf = pygame.Surface((w, h))
    for y in range(h):
        row = int((y + 0.5) * world.height / h)
        for x in range(w):
            col = int((x + 0.5) * world.width / w)
            color = BIOME_COLORS[world._terrains[row][col]]
            # Les rivieres d'une certaine taille dans le carre de la vignette.
            step = world.width // w
            if any(world.river_at((col + k) % world.width, row) >> 3 >= 2 for k in range(step)):
                color = (70, 130, 220)
            surf.set_at((x, y), color)
    pygame.image.save(surf, str(path))


def scout(seed: int) -> int:
    """Les continents habitables d'une graine, en 768 x 384 (25 s, sans
    ressources) : la forme des terres ne depend pas de la resolution."""
    from src.kora.world import CHAR_TO_TERRAIN, World

    w, h = mapgen.PLANET_WIDTH // 2, mapgen.PLANET_HEIGHT // 2
    grid, _climate = mapgen._generate(seed, w, h)
    world = World([[CHAR_TO_TERRAIN[c] for c in row] for row in grid.tolist()], wrap_x=True)
    ids = landmass_grid(world)
    hab = Counter(ids[r][c] for r in range(h) for c in range(w) if ids[r][c] and grid[r, c] not in ("M", "X", "G"))
    return sum(1 for v in hab.values() if v >= HABITABLE_MIN // 4)


def bake(pid: str, name: str, seed: int) -> dict | None:
    for _try in range(14):
        t0 = time.time()
        n = scout(seed)
        if not 5 <= n <= 8:
            print(f"{pid} graine {seed} : {n} continents en repérage ({time.time() - t0:.0f} s), suivante", flush=True)
            seed += 101
            continue
        world = mapgen.generate_world(seed=seed, width=mapgen.PLANET_WIDTH, height=mapgen.PLANET_HEIGHT, resources=True)
        problems, stats = check(world)
        print(f"{pid} graine {seed} : {time.time() - t0:.0f} s, {stats['continents']} continents, {stats['traits']}", flush=True)
        if not problems:
            break
        print("   refusee :", " ; ".join(problems), flush=True)
        seed += 101
    else:
        print(f"{pid} : aucune graine ne passe", flush=True)
        return None
    world.planet = pid
    labels = build_atlas_labels(world, random.Random(seed))
    meta = {"id": pid, "name": name, "seed": seed}
    OUT.mkdir(parents=True, exist_ok=True)
    save_world(world, OUT / f"{pid}.json", labels, meta)
    thumbnail(world, OUT / f"{pid}.png")
    return meta | {k: stats[k] for k in ("continents", "traits", "rivers")}


def row_from_file(pid: str) -> dict:
    from src.kora.world import load_world

    world = load_world(OUT / f"{pid}.json")
    _problems, stats = check(world)
    meta = getattr(world, "planet_meta", {"id": pid})
    return {"id": pid, "name": meta.get("name", pid), "seed": meta.get("seed", 0)} | {k: stats[k] for k in ("continents", "traits", "rivers")}


def main(argv) -> None:
    if "--index" in argv:
        # Le catalogue seul, relu des fichiers deja cuits.
        rows = [row_from_file(p) for p, _n, _s in PLANETS if (OUT / f"{p}.json").exists()]
        (OUT / "index.json").write_text(json.dumps(rows, ensure_ascii=False, indent=1), encoding="utf-8")
        print("index :", ", ".join(f"{r['name']} ({r['continents']} continents, {r['traits']})" for r in rows))
        return
    wanted = [p for p in PLANETS if not argv or p[0] in argv]
    index_path = OUT / "index.json"
    index = json.loads(index_path.read_text(encoding="utf-8")) if index_path.exists() else []
    by_id = {row["id"]: row for row in index}
    # Une planete deja cuite sans sa ligne (un arret) : on la relit.
    for pid, _name, _seed in PLANETS:
        if pid not in by_id and (OUT / f"{pid}.json").exists() and not (argv and pid in argv):
            by_id[pid] = row_from_file(pid)
    order = [p[0] for p in PLANETS]
    for pid, name, seed in wanted:
        row = bake(pid, name, seed)
        if row is not None:
            by_id[pid] = row
        # Le catalogue a chaque planete reussie (un echec n'efface rien).
        rows = [by_id[p] for p in order if p in by_id and (OUT / f"{p}.json").exists()]
        index_path.write_text(json.dumps(rows, ensure_ascii=False, indent=1), encoding="utf-8")
    print("index :", ", ".join(f"{r['name']} ({r['continents']} continents, {r['traits']})" for r in rows))


if __name__ == "__main__":
    main(sys.argv[1:])
