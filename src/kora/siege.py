"""LE SIEGE : la guerre contre les villages, telle que le neolithique la
connait (des palissades brulees, des enceintes investies ; les beliers, les
echelles et les tours roulantes viendront avec le bronze et les villes).

  Torches et brandons (palier 5 ; Palissades et l'arc, un village tenu
    trois ans) : contre un village que ce peuple attaque, les palissades, la
    tour et les enceintes ne comptent plus qu'a moitie (tech.SIEGE_FIRE :
    une defense x1,6 devient x1,3).
  L'art du siege (palier 6 ; un village tenu six ans, un peuple de 300) : une troupe EN GUERRE qui se
    tient a cote d'un village ennemi (SIEGE_RANGE case, sans marcher)
    l'INVESTIT. Tant qu'elle reste :
      - le village ne cueille et ne recolte plus que tech.SIEGE_FOOD de ce
        qu'il trouve (on ne sort plus des murs) ;
      - sa defense s'use de tech.SIEGE_ERODE par semaine, jusqu'a
        tech.SIEGE_FLOOR (la faim, la fatigue, les pieux qu'on sape).
    Une troupe qui part, ou la paix : le siege est leve.
L'IA (ai.py) : un village qui sait assieger leve une troupe contre un
village qu'il prendrait une fois sa defense usee ; la troupe declare la
guerre, s'installe devant lui et attend que la defense tombe, puis donne
l'assaut. En guerre, les villages levent en masse. Un suzerain appelle aussi
l'ost (ost.py).

Le siege d'un village est dans ses donnees (VillageData.siege : semaines,
besieger : le peuple qui l'investit). N'importe pas pygame.
"""

from __future__ import annotations

from src.kora import diplo, places, tech, villages
from src.kora.gamestate import is_human, note
from src.kora.log import LogKind

SIEGE_RANGE = 1


def _walls(state, band) -> float:
    """Ce que valent les murs du village (palissade, tour, pieux, enceintes)."""
    walls = 1.0
    for _label, mult in villages.wall_parts(state, band):
        walls *= mult
    return walls


def at_war(state, a: int, b: int) -> bool:
    """a peut-il assieger b : la guerre declaree entre eux, ou (sans la
    diplomatie) une hostilite ouverte."""
    if a == b:
        return False
    if diplo.declared_war(state, a, b):
        return True
    return not diplo.needs_declaration(state, a, b) and diplo.hostile_intent(state, a, b)


def _foes_at(state, site) -> list[int]:
    """Les peuples en guerre avec ce village qui ont des bandes tout pres."""
    out = set()
    for b in state.bands.values():
        if b.population <= 0 or b.tribe_id == site.tribe_id or b.village:
            continue
        if state.world.distance(b.position, site.hex) <= SIEGE_RANGE and at_war(state, b.tribe_id, site.tribe_id):
            out.add(b.tribe_id)
    return sorted(out)


def defense_parts(state, band, by: int = 0) -> list[tuple[str, float]]:
    """Ce que le siege retire a la defense d'un village (villages.defense_parts,
    systems.VILLAGE_DEFENSE) ; by : le peuple qui attaque (sinon : ceux qui
    sont devant le village)."""
    site = places.site_of(state, band)
    if site is None:
        return []
    out = []
    foes = [by] if by else _foes_at(state, site)
    walls = _walls(state, band)
    if walls > 1.0 and any(tech.bonuses(state.tribes[t]).siege_fire for t in foes if t in state.tribes):
        kept = 1.0 + (walls - 1.0) * tech.SIEGE_FIRE
        out.append(("Torches contre les pieux", round(kept / walls, 3)))
    weeks = getattr(site.data, "siege", 0)
    if weeks > 0:
        out.append((f"Assiégés depuis {weeks} sem.", erosion(weeks)))
    return out


def erosion(weeks: int) -> float:
    return round(max(tech.SIEGE_FLOOR, 1.0 - tech.SIEGE_ERODE * weeks), 3)


def food_mult(state, site) -> float:
    """Un village investi ne sort plus de ses murs (systems.VILLAGE_FOOD)."""
    return tech.SIEGE_FOOD if getattr(site.data, "siege", 0) > 0 else 1.0


def besiegers(state, site) -> list:
    """Les troupes qui investissent ce village : en guerre avec lui, qui
    savent assieger, a cote de lui et qui ne marchent pas."""
    out = []
    for b in state.bands.values():
        if b.kind != "armee" or b.population <= 0 or b.homebound or b.retreating or b.path:
            continue
        if state.world.distance(b.position, site.hex) > SIEGE_RANGE:
            continue
        tribe = state.tribes.get(b.tribe_id)
        if tribe is None or not tech.bonuses(tribe).siege or not at_war(state, b.tribe_id, site.tribe_id):
            continue
        out.append(b)
    return sorted(out, key=lambda b: b.id)


def can_besiege(state, band) -> bool:
    tribe = state.tribes.get(band.tribe_id)
    return band.kind == "armee" and tribe is not None and tech.bonuses(tribe).siege


def weekly(state) -> None:
    """Chaque semaine : les sieges commencent, durent ou sont leves."""
    for site in sorted(state.sites.values(), key=lambda s: s.id):
        if site.kind != "village" or places.band_of(state, site) is None:
            continue
        here = besiegers(state, site)
        was = getattr(site.data, "siege", 0)
        if not here:
            if was:
                site.data.siege = 0
                _tell(state, site, site.data.besieger, f"Le siège de {places.name(site)} est levé.")
                site.data.besieger = 0
            continue
        site.data.siege = was + 1
        site.data.besieger = here[0].tribe_id
        # Chaque semaine de siege : un avantage dans la guerre (diplo).
        diplo.add_score(state, here[0].tribe_id, site.tribe_id, diplo.SIEGE_SCORE)
        if not was:
            who = state.tribes[here[0].tribe_id].name
            _tell(state, site, here[0].tribe_id, f"Les {who} assiègent {places.name(site)} : on ne sort plus des murs.")


def _tell(state, site, besieger: int, text: str) -> None:
    for tid in (site.tribe_id, besieger):
        if tid and is_human(state, tid):
            note(state, LogKind.COMBAT, text, site.hex, to=tid)


def lines(state, site) -> list[str]:
    """Pour la fiche du village."""
    weeks = getattr(site.data, "siege", 0)
    if not weeks:
        return []
    who = state.tribes.get(site.data.besieger)
    name = who.name if who is not None else "?"
    return [
        f"Assiégé par les {name} depuis {weeks} sem. : défense x{erosion(weeks):.2f}".replace(".", ",")
        + f", vivres trouvés x{tech.SIEGE_FOOD:.2f}".replace(".", ",")
    ]
