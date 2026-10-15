"""LES BATIMENTS D'UN VILLAGE : ce qu'on y bati, les chantiers, le grand
monument, la palissade.

Les batiments (BUILDINGS, dans l'ordre de l'IA : BUILD_ORDER) appartiennent
au VILLAGE, pas a une case. Un chantier a la fois (VillageData.build), paye
en vivres du grenier (build_cost ; la paie des batisseurs en sicles l'accelere :
systems.BUILD_SPEED), sur des places qui viennent avec les habitants
(slots : BASE_SLOTS, puis une par SLOT_POP habitants ; une place prise ne se
rend pas). Chacun demande un savoir (Building.needs) et dit ce qu'il fait
(Building.lines) ; leurs effets se lisent la ou ils agissent (villages.py :
reserves, recoltes, defense ; chiefs.py : attachement ; vision.py : la tour).

Le GRAND MONUMENT se bati en etapes (MONUMENT_STAGES), pendant les grands
travaux (situations.GrandsTravaux) : le perdant le voit abattu
(pull_down_monument). La palissade est le batiment "palissade"
(palisade_state ; PALISADE_DEFENSE). Les chantiers avancent chaque semaine
(advance_works, appele par villages.update). N'importe pas pygame.
"""

from __future__ import annotations

import math
from dataclasses import dataclass

from src.kora import chiefdom, goods, situations, systems, tech, villages
from src.kora.log import LogKind
from src.kora.places import band_of, built, has, monument_stages, name, NEAR, oath_of, site_of, works


PALISADE_WEEKS = 12
PALISADE_COST_WEEKS = 4
PALISADE_DEFENSE = 1.6
TOWER_DEFENSE = 1.15


# Places a batir : 2, plus une par 40 habitants.
BASE_SLOTS = 2
SLOT_POP = 40


@dataclass(frozen=True)
class Building:
    id: str
    name: str
    text: str
    needs: str
    cost_weeks: float
    weeks: int
    lines: tuple
    icon: int


BUILDINGS = {
    b.id: b
    for b in (
        Building(
            "palissade", "Palissade", "Des pieux plantes en cercle autour des maisons.",
            "palissade", PALISADE_COST_WEEKS, PALISADE_WEEKS,
            (f"Défense du village x{PALISADE_DEFENSE:.1f}".replace(".", ","),), 0,
        ),
        Building(
            "grenier", "Grenier surélevé", "Sur pilotis, à l'abri des rats et de l'eau.",
            "", 3, 8, ("+8 semaines de réserve au grenier", "Le grain se gâte x0,6"), 1,
        ),
        Building(
            "puits", "Puits", "Une eau propre au milieu des maisons.",
            "", 2, 6, ("Fièvres du village x0,6",), 2,
        ),
        Building(
            "maison_longue", "Maison longue", "Une grande maison de bois pour plusieurs familles.",
            "maisons", 4, 10, ("Croissance du village x1,2",), 3,
        ),
        Building(
            "enclos", "Enclos", "Des haies d'épineux où l'on garde les bêtes.",
            "chevres", 3, 6, ("Vivres du village x1,1",), 4,
        ),
        Building(
            "guerriers", "Maison des guerriers", "Là où les jeunes gens apprennent la guerre.",
            "palissade", 3, 8, ("Troupes : force x1,25, moral +10", "Une compagnie de plus sous les armes"), 5,
        ),
        Building(
            "tour", "Tour de guet", "Une tour de rondins d'où l'on voit venir.",
            "guetteurs", 2, 6, ("Vue +3 autour du village", "Défense du village x1,15", "Alerte quand un ennemi approche"), 6,
        ),
        Building(
            "autel", "Autel des ancêtres", "La pierre où l'on parle aux morts du clan.",
            "rites", 2, 6, (f"Attachement +6 des clans à {NEAR} cases ou moins", "+1 prestige à chaque fin d'hiver"), 7,
        ),
        Building(
            "pierre", "Pierre levée", "Une pierre dressée que l'on voit de loin.",
            "megalithes", 6, 16, ("+2 prestige à chaque fin d'hiver", "Zone d'influence du village +1"), 8,
        ),
        Building(
            "atelier", "Ateliers", "Des abris où potiers, tisserands et tailleurs travaillent côte à côte.",
            "poterie", 3, 8, ("Métiers du village : production x1,25",), 9,
        ),
        Building(
            "place", "Place d'échange", "Une place où les porteurs des voisins étalent leurs biens.",
            "echanges", 3, 8, ("+2 convois de porteurs (routes commerciales)", "Vos ventes : prix +10 %"), 10,
        ),
        Building(
            "monument", "Grand monument", "Un tertre de pierres dressées, que l'on élève étape après étape pendant les grands travaux.",
            "", 2, 8, ("Une étape de plus au monument", "Le plus d'étapes gagne les grands travaux", "Gagné : il reste (+2 prestige par hiver) ; perdu : abattu"), 8,
        ),
    )
}
BUILD_ORDER = ("palissade", "grenier", "puits", "maison_longue", "enclos", "guerriers", "tour", "autel", "pierre", "atelier", "place", "monument")
# Le grand monument (situations.GrandsTravaux) : ses etapes, chacune plus
# longue et plus chere que la precedente.
MONUMENT_STAGES = 6


def monument_open(state, site) -> bool:
    """Le peuple de ce village vit les grands travaux, et le village est
    dans leur lieu : il peut elever son monument."""
    return any(
        inst.sid == "travaux" and situations.in_zone(state, inst, site.hex)
        for inst in situations.of_tribe(state, site.tribe_id)
    )


def building_name(site, bid: str, short: bool = False) -> str:
    """Le nom d'un batiment ; le monument dit ou il en est (short : pour
    les petites cartes)."""
    if bid == "monument":
        n = monument_stages(site)
        if not n:
            return "Grand monument"
        return f"Monument {n}/{MONUMENT_STAGES}" if short else f"Grand monument · {n}/{MONUMENT_STAGES}"
    return BUILDINGS[bid].name


def pull_down_monument(state, site) -> bool:
    """Le monument d'un vaincu est abattu (situations.GrandsTravaux)."""
    if site is None:
        return False
    had = monument_stages(site) > 0 or has(site, "monument")
    site.data.monument = 0
    if "monument" in site.data.buildings:
        site.data.buildings.remove("monument")
    job = works(site)
    if job and job[0] == "monument":
        site.data.build = None
        had = True
    return had


def slots(state, site) -> int:
    band = band_of(state, site)
    pop = band.population if band is not None else 0
    # Un batiment garde sa place : la capacite ne descend jamais sous ce qui
    # est bati (un village qui perd du monde n'affiche pas 10/5).
    return max(min(len(BUILDINGS), BASE_SLOTS + pop // SLOT_POP), used_slots(site))


def used_slots(site) -> int:
    return len(built(site)) + (1 if works(site) else 0)


def build_weeks(site, bid: str) -> int:
    weeks = BUILDINGS[bid].weeks
    if bid == "monument":
        weeks += 2 * monument_stages(site)
    if bid == "palissade" and oath_of(site) == "pieux":
        weeks = max(1, weeks // 2)
    return weeks


def build_cost(state, site, bid: str) -> float:
    band = band_of(state, site)
    pop = band.population if band is not None else 0
    cost_weeks = BUILDINGS[bid].cost_weeks
    if bid == "monument":
        cost_weeks += 0.5 * monument_stages(site)
    cost = cost_weeks * pop * goods.build_mult(state, site.tribe_id)
    if bid == "palissade" and oath_of(site) == "pieux":
        cost *= 0.5
    return float(math.floor(cost))


def building_status(state, site, bid: str) -> str:
    """"bati", "chantier", "possible", "attente" (manque vivres ou place) ou
    "verrouille" (savoir)."""
    if bid == "monument":
        job = works(site)
        if job and job[0] == bid:
            return "chantier"
        n = monument_stages(site)
        if n >= MONUMENT_STAGES or (n and not monument_open(state, site)):
            return "bati"
        if not monument_open(state, site):
            return "verrouille"
        return "possible" if not build_block_site(state, site, bid) else "attente"
    if has(site, bid):
        return "bati"
    job = works(site)
    if job and job[0] == bid:
        return "chantier"
    b = BUILDINGS[bid]
    if b.needs and b.needs not in state.tribes[site.tribe_id].knowledge:
        return "verrouille"
    return "possible" if not build_block_site(state, site, bid) else "attente"


def build_block_site(state, site, bid: str) -> str:
    if bid not in BUILDINGS:
        return "?"
    b = BUILDINGS[bid]
    band = band_of(state, site)
    if band is None:
        return "Le village est vide"
    monument = bid == "monument"
    if monument:
        if monument_stages(site) >= MONUMENT_STAGES:
            return "Le grand monument est achevé"
        if not monument_open(state, site):
            return "Seulement pendant les grands travaux (une conjoncture)"
    elif has(site, bid):
        return f"{b.name} : déjà bâti"
    job = works(site)
    if job:
        if job[0] == bid:
            return f"En construction (encore {job[1]} sem.)"
        return f"Un chantier à la fois ({BUILDINGS[job[0]].name})"
    if b.needs and b.needs not in state.tribes[site.tribe_id].knowledge:
        return f"Il faut connaître {tech.TECHS[b.needs].name}"
    if used_slots(site) >= slots(state, site) and not (monument and has(site, "monument")):
        return f"Plus de place (il faut {SLOT_POP} habitants de plus)"
    cost = build_cost(state, site, bid)
    if monument:
        cost -= min(cost, getattr(state.tribes[site.tribe_id], "granary", 0.0))
    if band.stock < cost:
        return f"Il faut {cost:.0f} vivres au grenier"
    return ""


def build_block(state, band_id: int, bid: str) -> str:
    band = state.bands.get(band_id)
    site = site_of(state, band)
    if site is None:
        return "Seul un village peut bâtir"
    return build_block_site(state, site, bid)


def build(state, band_id: int, bid: str) -> bool:
    if build_block(state, band_id, bid):
        return False
    band = state.bands[band_id]
    site = site_of(state, band)
    cost = build_cost(state, site, bid)
    if bid == "monument":
        # Le grand monument : le grenier du chef paie d'abord.
        cost -= chiefdom.granary_pay(state, band.tribe_id, cost)
    band.stock -= cost
    site.data.build = [bid, build_weeks(site, bid)]
    if state.tribes[band.tribe_id].is_player:
        villages._note(state, LogKind.SURVIE, f"{name(site)} : chantier de {BUILDINGS[bid].name.lower()} ({build_weeks(site, bid)} sem.).", site.hex, to=band.tribe_id)
    return True


def advance_works(state, site, band) -> None:
    job = works(site)
    if not job:
        return
    bid, left = job
    left -= 1
    # Des batisseurs payes (money.py) : du travail en plus, semaine apres semaine.
    extra = site.data.build_extra + systems.total(systems.BUILD_SPEED, state, site)
    if extra >= 1.0 and left > 0:
        left -= 1
        extra -= 1.0
    site.data.build_extra = round(extra, 4) if left > 0 else 0.0
    if left > 0:
        site.data.build = [bid, left]
        return
    site.data.build = None
    if bid == "monument":
        n = monument_stages(site) + 1
        site.data.monument = n
        if "monument" not in site.data.buildings:
            site.data.buildings.append("monument")
        if state.tribes[band.tribe_id].is_player:
            villages._note(state, LogKind.SURVIE, f"{name(site)} : le grand monument s'élève (étape {n} sur {MONUMENT_STAGES}).", site.hex, to=band.tribe_id)
        return
    site.data.buildings.append(bid)
    if state.tribes[band.tribe_id].is_player:
        text = f"{name(site)} : la palissade est debout." if bid == "palissade" else f"{name(site)} : {BUILDINGS[bid].name.lower()} achevée."
        villages._note(state, LogKind.SURVIE, text, site.hex, to=band.tribe_id)


def palisade_state(site) -> str:
    if has(site, "palissade"):
        return "built"
    job = works(site)
    if job and job[0] == "palissade":
        return "building"
    return "none"


def palisade_block(state, band_id: int) -> str:
    band = state.bands.get(band_id)
    site = site_of(state, band)
    if site is None:
        return "Seul un village peut se fortifier"
    if not villages._bonus(state, band.tribe_id).palisade:
        return "Il faut connaître Palissades"
    if palisade_state(site) == "built":
        return "La palissade est debout"
    return build_block_site(state, site, "palissade")


def build_palisade(state, band_id: int) -> bool:
    if palisade_block(state, band_id):
        return False
    return build(state, band_id, "palissade")
