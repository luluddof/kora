"""LES LIEUX et ce qu'on y lit.

Un lieu (Site) : une cache, un campement ou un village ; l'etat d'un village
(VillageData : sa bande, ses champs, ses semences, ses batiments...). Et les
lectures simples que tout le jeu partage : le village d'une bande, la bande
d'un village, son nom, ses batiments, son chantier.
La mecanique des campements est dans sites.py, celle des villages dans
villages.py. Etage 3 (tools/dependances.py) : n'importe que plus bas.
N'importe pas pygame.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Optional

from src.kora import records
from src.kora.types import Hex


@dataclass
class VillageData:
    """L'etat d'un VILLAGE (villages.py) ; un campement ou une cache garde
    ces valeurs par defaut. Sauve en ne gardant que ce qui differe du defaut
    (records.py : COMPACT)."""

    COMPACT = True

    # La bande installee, le serment de la fondation.
    band: int = 0
    oath: str = ""
    # Les champs ([col, row]) et le sol de chaque case ("col,row" -> 0..1).
    fields: list[list] = field(default_factory=list)
    soil: dict[str, float] = field(default_factory=dict)
    # Semences au grenier, part semee de la derniere saison, champs brules.
    seed: float = 0.0
    sown_ratio: float = 0.0
    burned: bool = False
    # Les batiments, le chantier en cours [batiment, semaines restantes],
    # les etapes du grand monument.
    buildings: list[str] = field(default_factory=list)
    build: Optional[list] = None
    # Le travail en plus des batisseurs payes (money.build_speed), en semaines.
    build_extra: float = 0.0
    monument: int = 0
    # Les recoltes : [annee, vivres] et la derniere.
    history: list[list] = field(default_factory=list)
    last_harvest: Optional[int] = None
    # La saison locale et la semaine ou elle a commence.
    season: Optional[str] = None
    season_at: Optional[int] = None
    # Collecte moyenne par saison (prevoir l'hiver en ete).
    forage: dict[str, float] = field(default_factory=dict)
    # Equipes de metier (goods.py) : metier -> equipes.
    teams: dict[str, int] = field(default_factory=dict)
    # Derniere alerte au joueur, derniere annee ou il a ete sollicite.
    alert: int = -1000
    asked: Optional[int] = None


def _village_data(raw) -> VillageData:
    """Relire les donnees d'un lieu (vieilles parties : la palissade etait
    un compteur a part, "palisade" : -1 batie, n en cours)."""
    raw = dict(raw or {})
    p = raw.pop("palisade", None)
    data = records.from_json(VillageData, {k: v for k, v in raw.items() if k in VillageData.__dataclass_fields__})
    if p is not None:
        if p < 0 and "palissade" not in data.buildings:
            data.buildings.append("palissade")
        elif p > 0 and not data.build:
            data.build = ["palissade", int(p)]
    return data


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
    # L'etat du village (VillageData ; par defaut pour un campement).
    data: VillageData = field(default_factory=VillageData, metadata={"decode": _village_data})


def site_of(state, band):
    if band is None or not band.village:
        return None
    site = state.sites.get(band.village)
    if site is None or site.kind != "village":
        return None
    return site


def band_of(state, site):
    bid = site.data.band
    band = state.bands.get(bid)
    if band is None or band.village != site.id or band.population <= 0:
        return None
    return band


def name(site) -> str:
    return site.name or "Le village"


# Rang d'un village selon ses habitants (titre de son ecran, panneau).
RANKS = ((150, "Gros village"), (50, "Village"), (0, "Hameau"))


def rank_name(population: int) -> str:
    return next(label for floor, label in RANKS if population >= floor)


def oath_of(site) -> str:
    return site.data.oath if site is not None else ""


def built(site) -> list:
    # (Les vieilles palissades sont relues a la relecture : places._village_data.)
    if site is None:
        return []
    return site.data.buildings


def has(site, bid: str) -> bool:
    return site is not None and bid in built(site)


def monument_stages(site) -> int:
    return int(site.data.monument) if site is not None else 0


def works(site):
    """Chantier en cours : (id, semaines restantes) ou None."""
    if site is None:
        return None
    job = site.data.build
    return (job[0], int(job[1])) if job else None


def watch_spots(state, tribe_id: int) -> list:
    """Villages a tour de guet (vision.py : +3 de vue autour)."""
    return [
        s.hex
        for s in sorted(state.sites.values(), key=lambda s: s.id)
        if s.kind == "village" and s.tribe_id == tribe_id and has(s, "tour")
    ]


def influence_radius(site, base: int) -> int:
    return base + (1 if has(site, "pierre") else 0)
