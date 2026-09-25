"""Lieux fixes d'un peuple : caches de vivres, campements (puis villages).

Cache (savoir Fumage et sechage) : des vivres laisses sur une case ; ils
se gatent lentement, et une bande etrangere qui passe a cote peut les
trouver.
Campement (savoir Huttes et campements) : la ou la bande se tient.
Abri l'hiver, reserve plus grande, ancre de la zone d'influence, lieu de
repli. Des que plus aucune bande du peuple n'y est, il est leve : ce qui
reste de sa reserve devient une cache (qu'un ennemi peut trouver). C'est
la graine du village.
N'importe ni pygame ni render.
"""

from __future__ import annotations

import copy
from dataclasses import dataclass, field

from src.kora import tech
from src.kora.log import LogKind
from src.kora.types import Hex, Terrain

CAMP_STORE = 600
CACHE_ROT = 0.015
CAMP_ROT = 0.005
KEEP_WEEKS = 4
CAMP_FORGOTTEN = 156
CAMP_SPACING = 4
FOREIGN_SPACING = 3
FIND_CHANCE = 0.25
# Voisinage d'un lieu : a cette distance, une bande "y est".
AT = 1


@dataclass
class Site:
    id: int
    kind: str  # "camp", "cache", "village"
    tribe_id: int
    hex: Hex
    store: float = 0.0
    founded: int = 0
    visited: int = 0
    name: str = ""
    # population : inutilise (les villageois sont une bande installee).
    population: int = 0
    # Village (villages.py) : bande, champs, sol, semences, palissade...
    data: dict = field(default_factory=dict)


def _copy_data(value):
    """Copie d'une donnee de lieu (dicts, listes, nombres, textes) : meme
    resultat que deepcopy, bien plus vite (la sauvegarde du tick en fait
    une par lieu, chaque semaine)."""
    if isinstance(value, dict):
        return {k: _copy_data(v) for k, v in value.items()}
    if isinstance(value, list):
        return [_copy_data(v) for v in value]
    if isinstance(value, (int, float, str, bool, type(None))):
        return value
    return copy.deepcopy(value)


def copy_site(site: Site) -> Site:
    out = copy.copy(site)
    out.data = _copy_data(site.data)
    return out


def _bonus(state, tribe_id: int):
    tribe = state.tribes.get(tribe_id)
    return tech.bonuses(tribe) if tribe is not None else tech.NO_BONUS


def of_tribe(state, tribe_id: int, kind: str | None = None) -> list[Site]:
    return [
        s
        for s in sorted(state.sites.values(), key=lambda s: s.id)
        if s.tribe_id == tribe_id and (kind is None or s.kind == kind)
    ]


def capacity(state, site: Site) -> float:
    if site.kind == "cache":
        return float(_bonus(state, site.tribe_id).cache_cap)
    if site.kind == "camp":
        return float(CAMP_STORE + _bonus(state, site.tribe_id).cache_cap)
    return float(site.data.get("granary", 0.0))


def own_site_at(state, band) -> Site | None:
    """Lieu de son peuple sur la case de la bande (ou juste a cote)."""
    best = None
    for s in of_tribe(state, band.tribe_id):
        d = state.world.distance(s.hex, band.position)
        if d <= AT and (best is None or d < state.world.distance(best.hex, band.position)):
            best = s
    return best


def camp_at(state, band) -> Site | None:
    s = own_site_at(state, band)
    return s if s is not None and s.kind in ("camp", "village") else None


def site_on_hex(state, h) -> Site | None:
    placed = state.world.canonicalize(h)
    for s in sorted(state.sites.values(), key=lambda s: s.id):
        if s.hex == placed:
            return s
    return None


def _new_id(state) -> int:
    sid = max(state.next_site_id, max(state.sites, default=0) + 1)
    state.next_site_id = sid + 1
    return sid


def _land(state, h) -> bool:
    return state.world.terrain(h) not in (Terrain.EAU, Terrain.SOMMET)


# --- campements ----------------------------------------------------------------


def camp_block(state, band_id: int) -> str:
    """"" si la bande peut camper ici, sinon la raison (pour la fiche)."""
    band = state.bands.get(band_id)
    if band is None:
        return "Pas de bande"
    allowed = _bonus(state, band.tribe_id).camps
    if allowed <= 0:
        return "Il faut connaitre Huttes et campements"
    if band.retreating:
        return "La bande est en repli"
    if not _land(state, band.position):
        return "Pas de campement sur l'eau"
    mine = of_tribe(state, band.tribe_id, "camp")
    if len(mine) >= allowed:
        return f"Campements : {len(mine)}/{allowed} (abandonnez-en un)"
    for s in state.sites.values():
        d = state.world.distance(s.hex, band.position)
        if s.tribe_id == band.tribe_id and s.kind in ("camp", "village") and d < CAMP_SPACING:
            return "Un de vos campements est tout pres"
        if s.tribe_id != band.tribe_id and s.kind in ("camp", "village") and d < FOREIGN_SPACING:
            return "Le campement d'un autre peuple est tout pres"
    return ""


def make_camp(state, band_id: int) -> Site | None:
    if camp_block(state, band_id):
        return None
    band = state.bands[band_id]
    here = own_site_at(state, band)
    sid = _new_id(state)
    site = Site(sid, "camp", band.tribe_id, band.position, founded=state.tick_count, visited=state.tick_count)
    if here is not None and here.kind == "cache" and here.hex == band.position:
        # La cache devient la reserve du campement.
        site.store = here.store
        del state.sites[here.id]
    state.sites[sid] = site
    if state.tribes[band.tribe_id].is_player:
        _note(state, LogKind.SURVIE, "Campement etabli.", band.position)
    return site


def abandon(state, site_id: int) -> None:
    site = state.sites.pop(site_id, None)
    if site is not None and state.tribes.get(site.tribe_id) and state.tribes[site.tribe_id].is_player:
        what = "Campement abandonne." if site.kind == "camp" else "Cache abandonnee."
        _note(state, LogKind.SURVIE, what, site.hex)


# --- caches ------------------------------------------------------------------------


def deposit_block(state, band_id: int) -> str:
    band = state.bands.get(band_id)
    if band is None:
        return "Pas de bande"
    keep = KEEP_WEEKS * band.population
    if band.stock <= keep + 1:
        return f"Stock trop bas (on garde {KEEP_WEEKS} semaines)"
    here = own_site_at(state, band)
    if here is not None:
        if here.store >= capacity(state, here) - 1:
            return "La reserve est pleine"
        return ""
    b = _bonus(state, band.tribe_id)
    if b.caches <= 0:
        return "Il faut connaitre Fumage et sechage"
    if not _land(state, band.position):
        return "Pas de cache sur l'eau"
    if len(of_tribe(state, band.tribe_id, "cache")) >= b.caches:
        return f"Caches : {len(of_tribe(state, band.tribe_id, 'cache'))}/{b.caches}"
    return ""


def deposit(state, band_id: int) -> float:
    """Tout sauf KEEP_WEEKS semaines de vivres va dans le lieu de la case
    (campement ou cache) ; sans lieu, une cache est creusee."""
    if deposit_block(state, band_id):
        return 0.0
    band = state.bands[band_id]
    here = own_site_at(state, band)
    if here is None:
        sid = _new_id(state)
        here = Site(sid, "cache", band.tribe_id, band.position, founded=state.tick_count, visited=state.tick_count)
        state.sites[sid] = here
    room = capacity(state, here) - here.store
    amount = min(room, band.stock - KEEP_WEEKS * band.population)
    if amount <= 0:
        return 0.0
    band.stock -= amount
    here.store += amount
    if state.tribes[band.tribe_id].is_player:
        where = "au campement" if here.kind == "camp" else "dans une cache"
        _note(state, LogKind.SURVIE, f"{amount:.0f} de vivres mis {where}.", here.hex)
    return amount


def withdraw_block(state, band_id: int) -> str:
    from src.kora.sim import stock_max

    band = state.bands.get(band_id)
    if band is None:
        return "Pas de bande"
    here = own_site_at(state, band)
    if here is None or here.store < 1:
        return "Pas de reserve ici"
    if band.stock >= stock_max(band, state) - 1:
        return "Le stock de la bande est plein"
    return ""


def withdraw(state, band_id: int) -> float:
    from src.kora.sim import stock_max

    if withdraw_block(state, band_id):
        return 0.0
    band = state.bands[band_id]
    here = own_site_at(state, band)
    amount = min(here.store, stock_max(band, state) - band.stock)
    band.stock += amount
    here.store -= amount
    if here.kind == "cache" and here.store < 1:
        del state.sites[here.id]
    return amount


# --- chaque semaine ----------------------------------------------------------------


def update(state) -> None:
    """Visites, vivres qui se gatent, caches trouvees, campements oublies ;
    puis la vie des villages (villages.update)."""
    if not state.sites:
        return
    from src.kora import villages

    villages.update(state)
    world = state.world
    here: dict = {}
    for b in state.bands.values():
        if b.population > 0:
            here.setdefault(b.position, []).append(b)
    for site in sorted(state.sites.values(), key=lambda s: s.id):
        if site.id not in state.sites:
            continue
        if site.tribe_id not in state.tribes:
            del state.sites[site.id]
            continue
        near = sorted(
            (b for h in world.hexes_in_radius(site.hex, AT) for b in here.get(h, ())),
            key=lambda b: b.id,
        )
        mine = [b for b in near if b.tribe_id == site.tribe_id]
        if mine:
            site.visited = state.tick_count
        if site.kind in ("camp", "cache") and site.store > 0:
            rot = CACHE_ROT if site.kind == "cache" else CAMP_ROT
            site.store *= 1.0 - rot * _bonus(state, site.tribe_id).cache_decay
        foes = [b for b in near if b.tribe_id != site.tribe_id]
        if site.kind == "camp" and not mine:
            # La bande est partie : le campement est leve, la reserve reste
            # sur place, cachee.
            _strike_camp(state, site)
        if foes and not mine and site.store >= 1 and site.kind in ("camp", "cache"):
            _maybe_found(state, site, foes)
        if site.id not in state.sites:
            continue
        if site.kind == "cache" and site.store < 1:
            del state.sites[site.id]
        elif site.kind == "camp" and state.tick_count - site.visited > CAMP_FORGOTTEN:
            del state.sites[site.id]
            if state.tribes[site.tribe_id].is_player:
                _note(state, LogKind.SURVIE, "Un campement oublie est tombe en ruine.", site.hex)


def _strike_camp(state, site: Site) -> None:
    player = state.tribes[site.tribe_id].is_player
    room = len(of_tribe(state, site.tribe_id, "cache")) < _bonus(state, site.tribe_id).caches
    if site.store >= 1 and room:
        site.kind = "cache"
        site.founded = state.tick_count
        if player:
            _note(state, LogKind.SURVIE, f"Campement leve : sa reserve reste en cache ({site.store:.0f} vivres).", site.hex)
    else:
        lost = site.store
        del state.sites[site.id]
        if player:
            text = "Campement leve." if lost < 1 else f"Campement leve : plus de place pour une cache, {lost:.0f} vivres perdus."
            _note(state, LogKind.SURVIE, text, site.hex)


def _maybe_found(state, site: Site, foes: list) -> None:
    from src.kora.sim import stock_max

    for foe in sorted(foes, key=lambda b: b.id):
        foe_tribe = state.tribes.get(foe.tribe_id)
        if foe_tribe is None:
            continue
        if foe_tribe.is_player:
            # Le joueur decide (evenement "cache trouvee") : pas de pillage
            # automatique par ses bandes.
            _offer_player_find(state, site, foe)
            return
        # En passant a cote, on la trouve parfois ; sur la case, toujours (l'IA
        # vient la chercher : ai._seek_cache).
        if site.kind == "cache" and foe.position != site.hex and state.story_rng.random() >= FIND_CHANCE:
            continue
        from src.kora import diplo

        if diplo.at_peace(state, foe.tribe_id, site.tribe_id):
            continue
        take = min(site.store, max(0.0, stock_max(foe, state) - foe.stock))
        if take < 1:
            continue
        foe.stock += take
        site.store -= take
        diplo.add_mod(state, foe.tribe_id, site.tribe_id, "pillage", -10, actor=foe.tribe_id)
        owner = state.tribes[site.tribe_id]
        if owner.is_player:
            what = "Votre cache" if site.kind == "cache" else "La reserve de votre campement"
            _note(
                state,
                LogKind.COMBAT,
                f"{what} a ete pillee par les {foe_tribe.name} ({take:.0f} vivres).",
                site.hex,
            )
        return


def _offer_player_find(state, site: Site, band) -> None:
    from src.kora import events

    events.hook(state, "cache_trouvee", tribe_id=band.tribe_id, band_id=band.id, other=site.tribe_id, site_id=site.id)


def _note(state, kind, text: str, where=None) -> None:
    state.log.add(kind, text, state.clock.year, state.clock.week, where=where)


# --- effets sur les bandes ----------------------------------------------------------


def sheltered(state, band) -> bool:
    return camp_at(state, band) is not None


def oldest_camp_years(state, tribe_id: int) -> int:
    ages = [state.tick_count - s.founded for s in of_tribe(state, tribe_id) if s.kind in ("camp", "village")]
    return max(ages, default=0) // 52


def village_count(state, tribe_id: int) -> int:
    return len(of_tribe(state, tribe_id, "village"))


def oldest_village_years(state, tribe_id: int) -> int:
    ages = [state.tick_count - s.founded for s in of_tribe(state, tribe_id, "village")]
    return max(ages, default=0) // 52


def site_lines(state, site: Site) -> list[str]:
    tribe = state.tribes.get(site.tribe_id)
    who = "Vous" if tribe is not None and tribe.is_player else (tribe.name if tribe else "?")
    if site.kind == "cache":
        return [f"Cache de vivres ({who})", f"Vivres : {site.store:.0f} / {capacity(state, site):.0f}"]
    if site.kind == "camp":
        years = (state.tick_count - site.founded) // 52
        lines = [f"Campement ({who})", f"Reserve : {site.store:.0f} / {capacity(state, site):.0f}"]
        lines.append(f"Tenu depuis {years} an{'s' if years > 1 else ''}" if years else "Etabli cette annee")
        return lines
    from src.kora import villages

    band = villages.band_of(state, site)
    people = band.population if band is not None else 0
    return [f"Village de {villages.name(site)} ({who})", f"Habitants : {people}  ·  champs {len(site.data.get('fields', []))}"]


# --- sauvegarde ----------------------------------------------------------------------


def to_json(site: Site) -> dict:
    return {
        "id": site.id,
        "kind": site.kind,
        "tribe_id": site.tribe_id,
        "hex": [site.hex.q, site.hex.r],
        "store": site.store,
        "founded": site.founded,
        "visited": site.visited,
        "name": site.name,
        "population": site.population,
        "data": site.data,
    }


def from_json(data: dict) -> Site:
    return Site(
        id=int(data["id"]),
        kind=str(data["kind"]),
        tribe_id=int(data["tribe_id"]),
        hex=Hex(int(data["hex"][0]), int(data["hex"][1])),
        store=float(data.get("store", 0.0)),
        founded=int(data.get("founded", 0)),
        visited=int(data.get("visited", 0)),
        name=str(data.get("name", "")),
        population=int(data.get("population", 0)),
        data=dict(data.get("data", {})),
    )
