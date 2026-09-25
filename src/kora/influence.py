"""Zone d'influence : la ou chaque peuple vit, chasse et se souvient.

Ce n'est pas un territoire : aucune case n'appartient a personne et rien
ne bloque le passage. Chaque semaine on note ou se tiennent les bandes ;
chaque mois l'influence s'use (x0,94 : demi-vie d'environ un an), puis
chaque lieu note l'etend sur un disque dont le rayon vient des savoirs.
Campements et villages l'ancrent, meme vides.

Une case est dans la zone d'un peuple si son influence y depasse
ZONE_MIN ; dans son coeur au-dela de CORE_MIN. Ses effets (nourriture,
defense) passent par les savoirs (tech.Bonuses.home_food, home_defense).
Pur Python : la simulation n'utilise pas numpy.
"""

from __future__ import annotations

import math

from src.kora import tech

ZONE_MIN = 0.12
CORE_MIN = 0.40
MONTH_DECAY = 0.94
# Influence ajoutee au centre par semaine de presence d'une bande de 40 :
# environ 6 semaines au meme endroit font entrer la case dans la zone.
GAIN = 0.02
MAX_WEIGHT = 3.0
# Ancrage mensuel d'un campement / d'un village (au centre).
CAMP_GAIN = 0.05
VILLAGE_GAIN = 0.10
VILLAGE_RADIUS = 5


def note_presence(state) -> None:
    """Chaque semaine : ou se tient chaque bande (et combien de monde)."""
    pres = state.presence
    for band in state.bands.values():
        if band.population <= 0:
            continue
        weight = min(MAX_WEIGHT, math.sqrt(band.population / 40.0))
        spots = pres.setdefault(band.tribe_id, {})
        spots[band.position] = spots.get(band.position, 0.0) + weight


def _spread(cells, world, center, tribe_id: int, radius: int, amount: float) -> None:
    around, dists = world.hexes_and_distances(center, radius)
    span = max(1, radius)
    for h, d in zip(around, dists):
        row = h.r
        col = h.q + (row - (row & 1)) // 2
        key = (col, row)
        cell = cells.get(key)
        if cell is None:
            cell = cells[key] = {}
        value = cell.get(tribe_id, 0.0) + amount * (1.0 - 0.5 * d / span)
        cell[tribe_id] = value if value < 1.0 else 1.0


def radius_of(state, tribe_id: int) -> int:
    tribe = state.tribes.get(tribe_id)
    return tech.bonuses(tribe).influence_radius if tribe is not None else tech.BASE_INFLUENCE_RADIUS


# Sous ce seuil, une trace est oubliee (bien en dessous de ZONE_MIN) : la
# carte d'influence reste petite.
FORGET = 0.02


def update(state) -> None:
    """Chaque mois : usure, puis presence du mois et ancrages.

    La carte est reconstruite (nouveaux dictionnaires) au lieu d'etre
    modifiee sur place : la copie de secours du tick (sim.snapshot) peut
    garder l'ancienne sans la recopier."""
    world = state.world
    cells: dict = {}
    for key, old in world._influence.items():
        cell = {t: v * MONTH_DECAY for t, v in old.items() if v * MONTH_DECAY >= FORGET}
        if cell:
            cells[key] = cell
    for tid in sorted(state.presence):
        radius = radius_of(state, tid)
        for h, weight in state.presence[tid].items():
            _spread(cells, world, h, tid, radius, GAIN * weight)
    state.presence = {}
    for site in sorted(getattr(state, "sites", {}).values(), key=lambda s: s.id):
        if site.tribe_id not in state.tribes:
            continue
        if site.kind == "camp":
            _spread(cells, world, site.hex, site.tribe_id, radius_of(state, site.tribe_id) + 1, CAMP_GAIN)
        elif site.kind == "village":
            from src.kora.villages import influence_radius

            _spread(cells, world, site.hex, site.tribe_id, influence_radius(site, VILLAGE_RADIUS), VILLAGE_GAIN)
    world._influence = cells
    world._influence_cells = set(cells)
    state.overlap = overlaps(world)
    world._influence_gen = getattr(world, "_influence_gen", 0) + 1


def overlaps(world) -> dict[tuple[int, int], int]:
    """Cases ou deux peuples sont chacun dans leur zone : (a, b) -> nombre."""
    out: dict[tuple[int, int], int] = {}
    for cell in world._influence.values():
        if len(cell) < 2:
            continue
        here = sorted(t for t, v in cell.items() if v >= ZONE_MIN)
        for i, a in enumerate(here):
            for b in here[i + 1 :]:
                out[(a, b)] = out.get((a, b), 0) + 1
    return out


# --- lecture ----------------------------------------------------------------


def dominant(world, h) -> tuple[int, float]:
    """(peuple, influence) le plus present sur la case, (0, 0.0) sinon."""
    idx = world._index(h)
    if idx is None:
        return 0, 0.0
    cell = world._influence.get(idx)
    if not cell:
        return 0, 0.0
    tid = max(cell, key=lambda t: (cell[t], -t))
    return tid, cell[tid]


def in_zone(world, h, tribe_id: int) -> bool:
    return world.influence(h, tribe_id) >= ZONE_MIN


def in_core(world, h, tribe_id: int) -> bool:
    return world.influence(h, tribe_id) >= CORE_MIN


def is_home(world, h, tribe_id: int) -> bool:
    """Dans sa zone ET le peuple le plus present : "chez soi"."""
    tid, value = dominant(world, h)
    return tid == tribe_id and value >= ZONE_MIN


def foreign_zone(world, h, tribe_id: int) -> int:
    """Peuple dominant sur la case si ce n'est pas le sien (0 sinon)."""
    tid, value = dominant(world, h)
    if tid and tid != tribe_id and value >= ZONE_MIN and world.influence(h, tribe_id) < value:
        return tid
    return 0


def zone_size(world, tribe_id: int) -> int:
    return sum(1 for cell in world._influence.values() if cell.get(tribe_id, 0.0) >= ZONE_MIN)


def zone_lines(state, h) -> list[str]:
    """Texte de la fiche de case : a qui est la zone ici."""
    world = state.world
    idx = world._index(h)
    if idx is None:
        return []
    cell = world._influence.get(idx) or {}
    here = sorted(
        ((v, t) for t, v in cell.items() if v >= ZONE_MIN and t in state.tribes),
        reverse=True,
    )
    if not here:
        return []

    def name(tid: int) -> str:
        return "Vous" if state.tribes[tid].is_player else state.tribes[tid].name

    if len(here) == 1:
        v, t = here[0]
        strength = "coeur" if v >= CORE_MIN else "zone"
        return [f"Influence : {name(t)} ({strength})"]
    return ["Influence partagee : " + ", ".join(name(t) for _v, t in here[:3])]
