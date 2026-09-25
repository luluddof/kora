"""Unites : une troupe est une pile de compagnies.

Une compagnie : [type, hommes, village d'origine]. Chaque type a un role
(melee, tir, garde, eclaireurs) et un age ; a chaque age, un role a son
meilleur type, debloque par un savoir. Les types d'un age suivant
remplacent ceux d'avant : une compagnie peut etre reequipee a son village.

Au combat (battle.py), une troupe vaut la moyenne de ses compagnies :
attaque, tenue (pertes subies), tir (volee d'ouverture), poursuite, moral,
bonus en foret ; ses pertes tombent d'abord sur les compagnies exposees.
Band.population reste le total : si elle change ailleurs (famine,
evenement), les compagnies suivent au prorata (normalize).
N'importe ni pygame ni render.
"""

from __future__ import annotations

from dataclasses import dataclass

from src.kora.types import Terrain


@dataclass(frozen=True)
class UnitType:
    id: str
    name: str
    role: str
    era: int
    needs: str
    attack: float = 1.0
    defense: float = 1.0
    ranged: float = 0.0
    pursuit: float = 1.0
    morale: float = 0.0
    forest: float = 1.0
    exposure: float = 1.0
    text: str = ""
    short: str = ""


ROLES = ("melee", "tir", "garde", "eclaireurs")
ROLE_LABEL = {"melee": "Melee", "tir": "Tir", "garde": "Garde", "eclaireurs": "Eclaireurs"}
UNITS: dict[str, UnitType] = {
    u.id: u
    for u in (
        UnitType("guerriers", "Guerriers", "melee", 0, "", short="Guerriers", text="Massues et epieux de chasse : le gros de la troupe."),
        UnitType(
            "epieux", "Guerriers a l'epieu", "melee", 0, "epieu", attack=1.15, defense=1.05, short="Epieux",
            text="Des pieux durcis au feu, et l'habitude de chasser ensemble.",
        ),
        UnitType(
            "haches", "Guerriers a la hache polie", "melee", 1, "haches", attack=1.4, defense=1.1, short="Haches",
            text="La pierre polie fend les boucliers d'osier.",
        ),
        UnitType(
            "frondeurs", "Frondeurs", "tir", 0, "", attack=0.6, defense=0.8, ranged=0.8, exposure=0.6, short="Frondeurs",
            text="Des pierres lancees de loin, avant le choc.",
        ),
        UnitType(
            "archers", "Archers", "tir", 0, "arc", attack=0.7, defense=0.8, ranged=1.3, forest=1.2, exposure=0.6, short="Archers",
            text="Une volee de fleches brise l'elan de l'ennemi.",
        ),
        UnitType(
            "boucliers", "Porteurs de boucliers", "garde", 1, "palissade", attack=0.8, defense=1.6, pursuit=0.5, morale=10.0, short="Boucliers",
            text="Un mur de boucliers d'osier et de cuir : on tient, on ne court pas.",
        ),
        UnitType(
            "pisteurs", "Pisteurs", "eclaireurs", 0, "reperes", attack=0.8, defense=0.8, pursuit=2.2, forest=1.3, exposure=0.8, short="Pisteurs",
            text="Ils connaissent chaque piste : personne ne leur echappe.",
        ),
    )
}
# Volee d'ouverture : part de la puissance de tir ajoutee a la premiere passe.
VOLLEY = 0.8
# Ensuite, les tireurs tirent encore, moins bien.
VOLLEY_LATER = 0.25
REEQUIP_COST = 3.0


def known(tribe, u: UnitType) -> bool:
    return not u.needs or u.needs in tribe.knowledge


def best(tribe, role: str):
    """Le meilleur type connu d'un role (le plus recent), ou None."""
    found = [u for u in UNITS.values() if u.role == role and known(tribe, u)]
    if not found:
        return None
    return max(found, key=lambda u: (u.era, u.attack + u.defense + u.ranged + u.pursuit, u.id))


def available(tribe) -> list[UnitType]:
    """Un type par role : ce que le village peut lever."""
    out = []
    for role in ROLES:
        u = best(tribe, role)
        if u is not None:
            out.append(u)
    return out


def outdated(tribe, type_id: str) -> bool:
    u = UNITS.get(type_id)
    b = best(tribe, u.role) if u is not None else None
    return b is not None and b.id != type_id


def ages_of(role: str) -> list[UnitType]:
    """Les types d'un role, age par age (fiche du village)."""
    return sorted((u for u in UNITS.values() if u.role == role), key=lambda u: (u.era, u.attack + u.defense + u.ranged))


# --- une troupe ------------------------------------------------------------------------


def normalize(band) -> list:
    """Les compagnies suivent Band.population (famine, evenement...)."""
    units = band.units
    if band.kind != "armee":
        return units
    if not units:
        band.units = units = [["guerriers", band.population, band.home]]
        return units
    total = sum(u[1] for u in units)
    if total == band.population:
        return units
    if total <= 0:
        units[0][1] = band.population
        for u in units[1:]:
            u[1] = 0
    else:
        shares = [u[1] * band.population / total for u in units]
        for u, s in zip(units, shares):
            u[1] = int(s)
        left = band.population - sum(u[1] for u in units)
        order = sorted(range(len(units)), key=lambda i: -(shares[i] - int(shares[i])))
        for i in order[:left]:
            units[i][1] += 1
    band.units = [u for u in units if u[1] > 0] or [[units[0][0], 0, units[0][2]]]
    return band.units


def remove(band, dead: int) -> None:
    """Pertes d'une troupe : d'abord les compagnies exposees."""
    units = normalize(band)
    dead = min(dead, sum(u[1] for u in units))
    if dead <= 0:
        return
    weights = [u[1] * UNITS.get(u[0], UNITS["guerriers"]).exposure for u in units]
    total = sum(weights) or 1.0
    takes = [min(u[1], dead * w / total) for u, w in zip(units, weights)]
    cut = [int(t) for t in takes]
    left = dead - sum(cut)
    order = sorted(range(len(units)), key=lambda i: -(takes[i] - cut[i]))
    for i in order:
        if left <= 0:
            break
        if cut[i] < units[i][1]:
            cut[i] += 1
            left -= 1
    for i in range(len(units)):
        if left <= 0:
            break
        room = units[i][1] - cut[i]
        take = min(room, left)
        cut[i] += take
        left -= take
    for u, c in zip(units, cut):
        u[1] -= c
    band.population = sum(u[1] for u in units)
    band.units = [u for u in units if u[1] > 0] or [[units[0][0], 0, units[0][2]]]


def add(band, type_id: str, men: int, home: int) -> None:
    """Une compagnie de plus dans la pile (chaque levee reste une compagnie :
    c'est ce que compte la limite du village)."""
    normalize(band)
    band.units.append([type_id, men, home])
    band.population = sum(u[1] for u in band.units)


def profile(band) -> dict:
    """Moyennes d'une troupe (ou d'un clan : 1, pas de tir)."""
    if band.kind != "armee":
        return {"attack": 1.0, "defense": 1.0, "ranged": 0.0, "pursuit": 1.0, "morale": 0.0, "forest": 1.0}
    units = normalize(band)
    total = sum(u[1] for u in units)
    if total <= 0:
        return {"attack": 1.0, "defense": 1.0, "ranged": 0.0, "pursuit": 1.0, "morale": 0.0, "forest": 1.0}
    out = {}
    for key in ("attack", "defense", "ranged", "pursuit", "morale", "forest"):
        out[key] = sum(u[1] * getattr(UNITS.get(u[0], UNITS["guerriers"]), key) for u in units) / total
    return out


def attack_mult(band, terrain) -> float:
    p = profile(band)
    mult = p["attack"]
    if terrain is Terrain.FORET:
        mult *= p["forest"]
    return mult


def lines(state, band) -> list[str]:
    from src.kora import villages

    if band.kind != "armee":
        return []
    parts = []
    for type_id, men, home in normalize(band):
        u = UNITS.get(type_id)
        site = state.sites.get(home)
        where = f" ({villages.name(site)})" if site is not None else ""
        parts.append(f"{men} {u.name.lower() if u else type_id}{where}")
    return ["Compagnies : " + " · ".join(parts)]
