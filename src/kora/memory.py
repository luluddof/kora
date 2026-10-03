"""LA MEMOIRE DU BROUILLARD : ce qu'un joueur a vu la derniere fois.

Dans le brouillard (une case exploree que ses bandes ne voient plus), la
carte montre le monde tel qu'il l'a laisse :
  - les lieux (villages, campements, caches) qu'il sait exister, a la
    couleur du peuple qui les tenait (et de son suzerain d'alors) ; un village pris, brule ou abandonne
    depuis reste tel qu'il l'a vu jusqu'a ce qu'il revienne ;
  - les zones d'influence, telles qu'il les a vues.
La memoire ne change que sous ses yeux (update, chaque semaine, apres la
vue : sim._week). Elle vit dans sa vue (vision.PlayerVision : sites, zones,
mem_gen) et se sauve avec elle (persist). Elle ne change rien a la partie.
N'importe pas pygame.
"""

from __future__ import annotations

from src.kora import chiefdom, influence
from src.kora.gamestate import humans
from src.kora.types import Hex
from src.kora.vision import vision_of

KINDS = ("village", "camp", "cache")


def _entry(state, site) -> list:
    walled = site.kind == "village" and "palissade" in site.data.buildings
    lord = chiefdom.top_lord(state, site.tribe_id) if site.tribe_id in state.tribes else 0
    return [site.hex.q, site.hex.r, site.kind, site.tribe_id, walled, lord if lord != site.tribe_id else 0]


def update(state, cells=None) -> None:
    """Chaque joueur retient ce qu'il voit (cells : les cases a relire, sa
    vue par defaut)."""
    world = state.world
    for tid in humans(state):
        vis = vision_of(state, tid)
        if vis is None:
            continue
        seen = vis.visible if cells is None else cells
        changed = False
        live = set()
        for site in state.sites.values():
            if site.kind not in KINDS or site.hex not in seen:
                continue
            live.add(site.id)
            entry = _entry(state, site)
            if vis.sites.get(site.id) != entry:
                vis.sites[site.id] = entry
                changed = True
        # Ce qui a disparu sous ses yeux s'efface de sa memoire.
        for sid, entry in list(vis.sites.items()):
            if sid not in live and Hex(entry[0], entry[1]) in seen:
                del vis.sites[sid]
                changed = True
        for h in seen:
            idx = world._index(h)
            if idx is None:
                continue
            tid_, value = influence.dominant(world, h)
            if tid_ and value >= influence.ZONE_MIN:
                entry = [tid_, round(value, 2)]
                if vis.zones.get(idx) != entry:
                    vis.zones[idx] = entry
                    changed = True
            elif idx in vis.zones:
                del vis.zones[idx]
                changed = True
        if changed:
            vis.mem_gen += 1


def seed(state) -> None:
    """Une vieille partie (sans memoire) : ce qu'il a explore, tel qu'il est."""
    for tid in humans(state):
        vis = vision_of(state, tid)
        if vis is not None and vis.explored and not vis.sites and not vis.zones:
            update(state, vis.explored)


def site_at(state, h, tid: int):
    """Le lieu dont le joueur se souvient sur la case : (site id, entree) ou None."""
    vis = vision_of(state, tid)
    if vis is None:
        return None
    for sid, entry in vis.sites.items():
        if entry[0] == h.q and entry[1] == h.r:
            return sid, entry
    return None
