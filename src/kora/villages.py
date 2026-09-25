"""Villages : une bande qui s'installe.

Un village n'est pas une case. C'est une bande "installee" (Band.village)
qui ne marche plus, et un lieu (Site "village") qui porte ce qui ne bouge
pas : ses champs, repartis sur les meilleures cases autour du centre
(fertilite du terrain, cereales et racines sauvages, eau), le sol de
chaque champ, les semences mises de cote, ses batiments, son serment.

Fonder est un tournant (fenetre "Fonder un village", render_village.py) :
on choisit le serment du village (OATHS), un trait definitif. Le premier
village d'un peuple ouvre l'age des villages : les villages levent des
troupes, les premieres armees (Band.kind == "armee").

Le rythme est celui des saisons LOCALES :
  - au printemps, on seme : un champ par 25 habitants (12 au plus), sur
    les cases ou le sol est le meilleur. Sans semences, pas de champs ;
  - a l'automne, on recolte dans le grenier (le stock de la bande, plus
    grand dans un village), et l'on garde les semences de l'an prochain.
    Il faut des bras : un village vide par ses troupes perd une part de sa
    recolte ;
  - chaque recolte epuise le sol ; un champ laisse en repos se refait :
    le village deplace ses champs de lui-meme.
Batiments (BUILDINGS) : un chantier a la fois, paye en vivres du grenier,
sur des places qui viennent avec les habitants. Ils appartiennent au
village, pas a une case. Un village ne fuit pas : pille, il perd son grain,
ses champs brulent, parfois un batiment. Les fievres de la promiscuite et
les crues des vallees le menacent (evenements).
N'importe ni pygame ni render.
"""

from __future__ import annotations

import math
import random
from dataclasses import dataclass

from src.kora import tech
from src.kora.log import LogKind
from src.kora.types import Season, Terrain

FIELD_WORKERS = 25
MAX_FIELDS = 12
FIELD_RADIUS = 3
# Recolte d'un champ seme en entier, fertilite 1, sol neuf (vivres) : un
# peu plus de la moitie de ce que mangent ses 25 travailleurs. Le reste
# vient encore de la chasse et de la cueillette (transition difficile).
FIELD_FOOD = 700.0
SEED = 120.0
LATE_SOW = 0.5
STORE_WEEKS = 20
GROWTH = 1.4
SOIL_LOSS = 0.08
SOIL_REST = 0.12
GRAIN_ROT = 0.003
PALISADE_WEEKS = 12
PALISADE_COST_WEEKS = 4
PALISADE_DEFENSE = 1.6
BURNED = 0.6
DISEASE_POP = 80
FLOOD_CHANCE = 0.06
MIN_FOUND_POP = 20
# Bras pour la recolte : habitants par champ (sinon une part est perdue).
FIELD_HANDS = 0.6 * FIELD_WORKERS
HISTORY = 8
FIRST_VILLAGE_PRESTIGE = 10
# Places a batir : 2, plus une par 40 habitants.
BASE_SLOTS = 2
SLOT_POP = 40
LOSE_BUILDING = 0.35
# Rayons des effets d'un village sur les clans alentour (autel, serment).
NEAR = 8
ALERT_RANGE = 5
ALERT_EVERY = 8

_T = Terrain
FERTILITY = {
    _T.VALLEE: 1.0,
    _T.PLAINE: 0.85,
    _T.COTE: 0.6,
    _T.STEPPE: 0.5,
    _T.FORET: 0.5,
    _T.COLLINE: 0.4,
    _T.DESERT: 0.15,
}


@dataclass(frozen=True)
class Oath:
    id: str
    name: str
    text: str
    lines: tuple


OATHS = {
    o.id: o
    for o in (
        Oath(
            "grenier",
            "Le grenier d'abord",
            "Avant les maisons, on eleve le grenier : ici, on ne manquera jamais.",
            ("Grenier du village +25 %", "Le grain se gate x0,7"),
        ),
        Oath(
            "champs",
            "Les champs d'abord",
            "Chaque bras va a la terre : les champs seront les plus beaux de la vallee.",
            ("Recolte +10 %", "Croissance du village x1,1"),
        ),
        Oath(
            "pieux",
            "Les pieux d'abord",
            "On plante les pieux avant de semer : nul ne prendra ce village.",
            ("Palissade 2x plus vite, moitie prix", "Defense du village x1,15"),
        ),
        Oath(
            "feu",
            "Le feu des anciens",
            "Le feu du clan brule au centre du village : tous les clans y reviennent.",
            (f"Attachement +8 des clans a {NEAR} cases ou moins", "+1 prestige a chaque fin d'hiver"),
        ),
    )
}
OATH_ORDER = ("grenier", "champs", "pieux", "feu")
# Serment de l'IA selon sa culture.
AI_OATH = {"steppe": "pieux", "collines": "pieux", "nord": "pieux", "vallee": "champs", "cote": "champs", "foret": "feu", "desert": "grenier"}


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
            (f"Defense du village x{PALISADE_DEFENSE:.1f}".replace(".", ","),), 0,
        ),
        Building(
            "grenier", "Grenier sureleve", "Sur pilotis, a l'abri des rats et de l'eau.",
            "", 3, 8, ("+8 semaines de reserve au grenier", "Le grain se gate x0,6"), 1,
        ),
        Building(
            "puits", "Puits", "Une eau propre au milieu des maisons.",
            "", 2, 6, ("Fievres du village x0,6",), 2,
        ),
        Building(
            "maison_longue", "Maison longue", "Une grande maison de bois pour plusieurs familles.",
            "maisons", 4, 10, ("Croissance du village x1,2",), 3,
        ),
        Building(
            "enclos", "Enclos", "Des haies d'epineux ou l'on garde les betes.",
            "chevres", 3, 6, ("Vivres du village x1,1",), 4,
        ),
        Building(
            "guerriers", "Maison des guerriers", "La ou les jeunes gens apprennent la guerre.",
            "palissade", 3, 8, ("Troupes : force x1,25, moral +10", "Une compagnie de plus sous les armes"), 5,
        ),
        Building(
            "tour", "Tour de guet", "Une tour de rondins d'ou l'on voit venir.",
            "guetteurs", 2, 6, ("Vue +3 autour du village", "Defense du village x1,15", "Alerte quand un ennemi approche"), 6,
        ),
        Building(
            "autel", "Autel des ancetres", "La pierre ou l'on parle aux morts du clan.",
            "rites", 2, 6, (f"Attachement +6 des clans a {NEAR} cases ou moins", "+1 prestige a chaque fin d'hiver"), 7,
        ),
        Building(
            "pierre", "Pierre levee", "Une pierre dressee que l'on voit de loin.",
            "megalithes", 6, 16, ("+2 prestige a chaque fin d'hiver", "Zone d'influence du village +1"), 8,
        ),
        Building(
            "atelier", "Ateliers", "Des abris ou potiers, tisserands et tailleurs travaillent cote a cote.",
            "poterie", 3, 8, ("Metiers du village : production x1,25",), 9,
        ),
        Building(
            "place", "Place d'echange", "Une place ou les porteurs des voisins etalent leurs biens.",
            "echanges", 3, 8, ("+2 convois de porteurs (routes commerciales)", "Vos ventes : prix +10 %"), 10,
        ),
    )
}
BUILD_ORDER = ("palissade", "grenier", "puits", "maison_longue", "enclos", "guerriers", "tour", "autel", "pierre", "atelier", "place")

# Troupes : part des habitants levee, vivres emportes, duree avant les
# desertions.
LEVIES = (("poignee", 0.2, "Une poignee"), ("troupe", 1 / 3, "Une troupe"), ("masse", 0.5, "Levee en masse"))
LEVY_SHARE = {k: v for k, v, _l in LEVIES}
ARMY_MIN_VILLAGE = 40
ARMY_MIN = 8
VILLAGE_KEEP = 20
ARMY_SUPPLY_WEEKS = 8
ARMY_TERM = 26
DESERTION = 0.05
ARMY_HOME = 1
WARRIORS_QUALITY = 1.25
WARRIORS_MORALE = 10.0


def _bonus(state, tribe_id: int):
    tribe = state.tribes.get(tribe_id)
    return tech.bonuses(tribe) if tribe is not None else tech.NO_BONUS


def site_of(state, band):
    if band is None or not band.village:
        return None
    site = state.sites.get(band.village)
    if site is None or site.kind != "village":
        return None
    return site


def band_of(state, site):
    bid = site.data.get("band", 0)
    band = state.bands.get(bid)
    if band is None or band.village != site.id or band.population <= 0:
        return None
    return band


def _key(col: int, row: int) -> str:
    return f"{col},{row}"


def name(site) -> str:
    return site.name or "Le village"


# Rang d'un village selon ses habitants (titre de son ecran, panneau).
RANKS = ((150, "Gros village"), (50, "Village"), (0, "Hameau"))


def rank_name(population: int) -> str:
    return next(label for floor, label in RANKS if population >= floor)


def oath_of(site) -> str:
    return site.data.get("oath", "") if site is not None else ""


# --- batiments ---------------------------------------------------------------------


def _migrate(site) -> None:
    """Anciennes sauvegardes : la palissade etait un compteur a part."""
    data = site.data
    if "palisade" in data:
        p = data.pop("palisade")
        built = data.setdefault("buildings", [])
        if p < 0 and "palissade" not in built:
            built.append("palissade")
        elif p > 0 and not data.get("build"):
            data["build"] = ["palissade", int(p)]


def built(site) -> list:
    if site is None:
        return []
    _migrate(site)
    return site.data.get("buildings", [])


def has(site, bid: str) -> bool:
    return site is not None and bid in built(site)


def works(site):
    """Chantier en cours : (id, semaines restantes) ou None."""
    if site is None:
        return None
    _migrate(site)
    job = site.data.get("build")
    return (job[0], int(job[1])) if job else None


def slots(state, site) -> int:
    band = band_of(state, site)
    pop = band.population if band is not None else 0
    return min(len(BUILDINGS), BASE_SLOTS + pop // SLOT_POP)


def used_slots(site) -> int:
    return len(built(site)) + (1 if works(site) else 0)


def build_weeks(site, bid: str) -> int:
    weeks = BUILDINGS[bid].weeks
    if bid == "palissade" and oath_of(site) == "pieux":
        weeks = max(1, weeks // 2)
    return weeks


def build_cost(state, site, bid: str) -> float:
    band = band_of(state, site)
    pop = band.population if band is not None else 0
    from src.kora import goods

    cost = BUILDINGS[bid].cost_weeks * pop * goods.build_mult(state, site.tribe_id)
    if bid == "palissade" and oath_of(site) == "pieux":
        cost *= 0.5
    return float(math.floor(cost))


def building_status(state, site, bid: str) -> str:
    """"bati", "chantier", "possible", "attente" (manque vivres ou place) ou
    "verrouille" (savoir)."""
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
    if has(site, bid):
        return f"{b.name} : deja bati"
    job = works(site)
    if job:
        if job[0] == bid:
            return f"En construction (encore {job[1]} sem.)"
        return f"Un chantier a la fois ({BUILDINGS[job[0]].name})"
    if b.needs and b.needs not in state.tribes[site.tribe_id].knowledge:
        return f"Il faut connaitre {tech.TECHS[b.needs].name}"
    if used_slots(site) >= slots(state, site):
        return f"Plus de place (il faut {SLOT_POP} habitants de plus)"
    cost = build_cost(state, site, bid)
    if band.stock < cost:
        return f"Il faut {cost:.0f} vivres au grenier"
    return ""


def build_block(state, band_id: int, bid: str) -> str:
    band = state.bands.get(band_id)
    site = site_of(state, band)
    if site is None:
        return "Seul un village peut batir"
    return build_block_site(state, site, bid)


def build(state, band_id: int, bid: str) -> bool:
    if build_block(state, band_id, bid):
        return False
    band = state.bands[band_id]
    site = site_of(state, band)
    band.stock -= build_cost(state, site, bid)
    site.data["build"] = [bid, build_weeks(site, bid)]
    if state.tribes[band.tribe_id].is_player:
        _note(state, LogKind.SURVIE, f"{name(site)} : chantier de {BUILDINGS[bid].name.lower()} ({build_weeks(site, bid)} sem.).", site.hex)
    return True


def _advance_works(state, site, band) -> None:
    job = works(site)
    if not job:
        return
    bid, left = job
    left -= 1
    if left > 0:
        site.data["build"] = [bid, left]
        return
    site.data["build"] = None
    site.data.setdefault("buildings", []).append(bid)
    if state.tribes[band.tribe_id].is_player:
        text = f"{name(site)} : la palissade est debout." if bid == "palissade" else f"{name(site)} : {BUILDINGS[bid].name.lower()} achevee."
        _note(state, LogKind.SURVIE, text, site.hex)


# --- effets des batiments et du serment ------------------------------------------------


def store_weeks(state, band) -> float:
    """Semaines de reserve propres au village (stock_max) : grenier de base,
    savoirs, Grenier sureleve, serment."""
    from src.kora import goods

    site = site_of(state, band)
    weeks = STORE_WEEKS + _bonus(state, band.tribe_id).granary + goods.store_weeks(state, band.tribe_id)
    if site is not None:
        if has(site, "grenier"):
            weeks += 8
        if oath_of(site) == "grenier":
            weeks *= 1.25
    return weeks


def rot_mult(state, site) -> float:
    from src.kora import goods

    mult = _bonus(state, site.tribe_id).grain_rot * goods.rot_mult(state, site.tribe_id)
    if has(site, "grenier"):
        mult *= 0.6
    if oath_of(site) == "grenier":
        mult *= 0.7
    return mult


# Les naissances suivent les vivres a venir (plus de boom suivi d'une
# famine) : pleine croissance si le grenier tiendra jusqu'a la prochaine
# recolte avec FOOD_SAFE_WEEKS semaines de marge ; aucune s'il sera vide.
FOOD_SAFE_WEEKS = 6.0
FOOD_LOW_GROWTH = 0.0
FORAGE_MEMORY = 0.1


_NEXT_SEASON = {Season.HIVER: Season.PRINTEMPS, Season.PRINTEMPS: Season.ETE, Season.ETE: Season.AUTOMNE, Season.AUTOMNE: Season.HIVER}


def _to_harvest(state, site) -> list:
    """[(saison, semaines)] jusqu'a la prochaine recolte (debut de l'automne
    local)."""
    season = state.world.hex_season(site.hex)
    since = site.data.get("season_at")
    if since is None:
        left = 13 - (state.clock.week - 1) % 13
    else:
        left = max(1, 13 - (state.tick_count - since))
    out = [(season, left)]
    nxt = _NEXT_SEASON[season]
    while nxt is not Season.AUTOMNE:
        out.append((nxt, 13))
        nxt = _NEXT_SEASON[nxt]
    return out


def weeks_to_harvest(state, site) -> int:
    return sum(w for _s, w in _to_harvest(state, site))


def note_forage(state, site, take: float) -> None:
    """Collecte de la semaine (sim.collect_food) : une moyenne par saison,
    pour prevoir l'hiver en ete."""
    key = state.world.hex_season(site.hex).value
    memo = site.data.setdefault("forage", {})
    if not isinstance(memo, dict):
        memo = site.data["forage"] = {}
    old = memo.get(key)
    memo[key] = round(take if old is None else old + FORAGE_MEMORY * (take - old), 2)


def food_outlook(state, site, band) -> tuple[int, float]:
    """(semaines avant la recolte, semaines de vivres qui resteront alors)."""
    from src.kora import goods

    pop = max(1, band.population)
    memo = site.data.get("forage")
    memo = memo if isinstance(memo, dict) else {}
    here = memo.get(state.world.hex_season(site.hex).value, float(pop))
    fish = goods.output(state, site, "pecheurs")
    food = band.stock
    total = 0
    for season, weeks in _to_harvest(state, site):
        food += weeks * (memo.get(season.value, here) + fish - pop)
        total += weeks
    return total, food / pop


def granary_growth(state, band) -> float:
    site = site_of(state, band)
    if site is None:
        return 1.0
    _left, margin = food_outlook(state, site, band)
    return max(FOOD_LOW_GROWTH, min(1.0, FOOD_LOW_GROWTH + (1.0 - FOOD_LOW_GROWTH) * margin / FOOD_SAFE_WEEKS))


def growth_mult(state, band) -> float:
    site = site_of(state, band)
    mult = GROWTH * _bonus(state, band.tribe_id).village_growth * stability_growth(state, band) * granary_growth(state, band)
    if site is not None:
        if has(site, "maison_longue"):
            mult *= 1.2
        if oath_of(site) == "champs":
            mult *= 1.1
    return mult


def food_mult(state, band) -> float:
    from src.kora import goods

    site = site_of(state, band)
    mult = _bonus(state, band.tribe_id).village_food
    if has(site, "enclos"):
        mult *= 1.1
    if site is not None:
        mult *= goods.forage_mult(site, band)
    return mult


def winter_famine_mult(state, band) -> float:
    """Sel et etoffes : l'hiver tue moins au village."""
    from src.kora import goods

    return goods.winter_famine(state, band.tribe_id) if band.village else 1.0


def yield_mult(state, site) -> float:
    from src.kora import goods

    mult = _bonus(state, site.tribe_id).field_yield * goods.yield_mult(state, site.tribe_id)
    if oath_of(site) == "champs":
        mult *= 1.1
    return mult


def defense_parts(state, band) -> list[tuple[str, float]]:
    site = site_of(state, band)
    if site is None:
        return []
    out = []
    if has(site, "palissade"):
        out.append(("Palissade", PALISADE_DEFENSE))
    if has(site, "tour"):
        out.append(("Tour de guet", 1.15))
    if oath_of(site) == "pieux":
        out.append(("Serment des pieux", 1.15))
    return out


def defense_mult(state, band) -> float:
    mult = 1.0
    for _label, m in defense_parts(state, band):
        mult *= m
    return mult


def influence_radius(site, base: int) -> int:
    return base + (1 if has(site, "pierre") else 0)


def winter_prestige(state, tribe_id: int) -> int:
    from src.kora import goods

    gain = goods.winter_prestige(state, tribe_id) if goods.has_village(state, tribe_id) else 0
    for site in state.sites.values():
        if site.kind != "village" or site.tribe_id != tribe_id or band_of(state, site) is None:
            continue
        if has(site, "autel"):
            gain += 1
        if has(site, "pierre"):
            gain += 2
        if oath_of(site) == "feu":
            gain += 1
    return gain


def loyalty_parts(state, band) -> list[tuple[str, float]]:
    """Autel des ancetres, feu des anciens : les clans proches y tiennent."""
    out = []
    for site in state.sites.values():
        if site.kind != "village" or site.tribe_id != band.tribe_id:
            continue
        v = (6.0 if has(site, "autel") else 0.0) + (8.0 if oath_of(site) == "feu" else 0.0)
        if v and state.world.distance(site.hex, band.position) <= NEAR:
            out.append((f"Pres de {name(site)} (autel, feu)", v))
    return out[:2]


def nearest_village(state, band, radius: int):
    """Village vivant du peuple de la bande a `radius` cases au plus."""
    best, best_d = None, radius + 1
    for site in state.sites.values():
        if site.kind != "village" or site.tribe_id != band.tribe_id:
            continue
        d = state.world.distance(site.hex, band.position)
        if d < best_d or (d == best_d and best is not None and site.id < best.id):
            best, best_d = site, d
    return best


# --- stabilite ----------------------------------------------------------------------
# Un village tient ensemble ou se defait : savoirs du neolithique, batiments,
# serment, chef present, prestige ; la faim, le pillage, la foule le minent.
# Stable, il grandit mieux et se bat mieux ; sous 30, des familles s'en vont
# (un clan nomade de plus, qui s'emancipera a son tour).
STABILITY_BASE = 50.0
UNREST = 30.0
UNREST_SHARE = 0.15
UNREST_MIN_POP = 40
CROWD_POP = 150


def stability_parts(state, site, band=None) -> list[tuple[str, float]]:
    from src.kora import chiefs

    band = band or band_of(state, site)
    if band is None:
        return []
    tribe = state.tribes[band.tribe_id]
    parts: list[tuple[str, float]] = [("Base", STABILITY_BASE)]
    know = _bonus(state, band.tribe_id).stability
    if know:
        parts.append(("Savoirs du neolithique", float(know)))
    for bid, v, label in (
        ("autel", 8.0, "Autel des ancetres"),
        ("pierre", 10.0, "Pierre levee"),
        ("puits", 4.0, "Puits"),
        ("grenier", 4.0, "Grenier"),
        ("maison_longue", 4.0, "Maison longue"),
    ):
        if has(site, bid):
            parts.append((label, v))
    if oath_of(site) == "feu":
        parts.append(("Serment du feu", 10.0))
    from src.kora import goods

    parts.extend(goods.stability_parts(state, band.tribe_id))
    if chiefs.is_chief_band(state, band):
        parts.append(("Le chef y gouverne", 10.0))
    else:
        heart = chiefs.chief_band(state, band.tribe_id)
        if heart is not None:
            d = state.world.distance(heart.position, band.position)
            if d > 8:
                parts.append(("Loin du chef", -min(20.0, 0.5 * d)))
    p = (tribe.prestige - 40) * 0.2
    if abs(p) >= 1:
        parts.append(("Prestige", round(p)))
    if state.tick_count - band.famine_tick <= 8:
        parts.append(("Famine recente", -20.0))
    if site.data.get("burned"):
        parts.append(("Champs brules", -10.0))
    crowd = band.population - CROWD_POP - (40 if has(site, "maison_longue") else 0)
    if crowd > 0:
        parts.append(("Trop de monde", -min(20.0, crowd / 10.0)))
    return [(label, round(v, 1)) for label, v in parts]


def stability(state, site, band=None) -> float:
    return max(0.0, min(100.0, sum(v for _l, v in stability_parts(state, site, band))))


def stability_word(value: float) -> str:
    if value >= 75:
        return "florissant"
    if value >= 50:
        return "stable"
    if value >= UNREST:
        return "fragile"
    return "agite"


def stability_growth(state, band) -> float:
    site = site_of(state, band)
    if site is None:
        return 1.0
    return 0.85 + 0.3 * stability(state, site, band) / 100.0


def _unrest(state, site, band) -> None:
    """Village agite : des familles s'en vont former un clan nomade."""
    from src.kora.sim import _ai_caches_changed, new_band_id
    from src.kora.types import Band
    from src.kora import chiefs

    if band.population < UNREST_MIN_POP:
        return
    value = stability(state, site, band)
    if value >= UNREST or state.story_rng.random() >= (UNREST - value) / 100.0:
        return
    moved = max(10, int(band.population * UNREST_SHARE))
    stock = band.stock * moved / band.population
    band.population -= moved
    band.stock -= stock
    nid = new_band_id(state)
    clan = Band(nid, band.tribe_id, band.position, moved, stock, famine_in_period=band.famine_in_period)
    state.bands[nid] = clan
    chiefs.on_split(state, band, clan)
    clan.loyalty = min(clan.loyalty, 50.0)
    _ai_caches_changed(state)
    if state.tribes[band.tribe_id].is_player:
        _note(state, LogKind.POLITIQUE, f"{name(site)} est agite : {moved} personnes s'en vont, lasses du desordre.", site.hex)
    # Elles ne deviennent pas une tribu errante : elles partent fonder leur
    # propre village, sous leur propre chef (un proto-pays de la meme
    # civilisation).
    chiefs.emancipate(state, nid)


def watch_spots(state, tribe_id: int) -> list:
    """Villages a tour de guet (vision.py : +3 de vue autour)."""
    return [
        s.hex
        for s in sorted(state.sites.values(), key=lambda s: s.id)
        if s.kind == "village" and s.tribe_id == tribe_id and has(s, "tour")
    ]


# --- fertilite et champs -----------------------------------------------------------


def fertility(state, tribe_id: int, h) -> float:
    world = state.world
    terrain = world.terrain(h)
    base = FERTILITY.get(terrain, 0.0)
    if terrain is _T.FORET and not _bonus(state, tribe_id).clearing:
        return 0.0
    if base <= 0:
        return 0.0
    wild = max(world.resource(h, "cereales"), world.resource(h, "racines")) if world.resources else 0.3
    return base * (0.6 + 0.8 * wild)


def land_profile(world, h) -> tuple:
    """Terrains et ressources presentes (0,4) des terres d'un village : les
    cases a FIELD_RADIUS ou moins. La carte ne change pas : memorise."""
    from src.kora.resources import NAMES, PRESENT

    memo = getattr(world, "_lands", None)
    if memo is None:
        memo = world._lands = {}
    key = world._index(h)
    hit = memo.get(key)
    if hit is not None:
        return hit
    terrains, found = set(), set()
    for x in world.hexes_in_radius(h, FIELD_RADIUS):
        terrains.add(world.terrain(x))
        if world.resources:
            found.update(n for n in NAMES if world.resource(x, n) >= PRESENT)
    hit = (frozenset(terrains), frozenset(found))
    memo[key] = hit
    return hit


def _taken_by_others(state, site) -> set:
    taken = set()
    for other in state.sites.values():
        if other.kind == "village" and other.id != site.id:
            taken.update(tuple(f) for f in other.data.get("fields", []))
    return taken


def choose_fields(state, site, band) -> list:
    """Les meilleures cases autour du village, sol compris."""
    world = state.world
    want = min(MAX_FIELDS, max(1, math.ceil(band.population / FIELD_WORKERS)))
    soil = site.data.setdefault("soil", {})
    taken = _taken_by_others(state, site)
    scored = []
    for h in world.hexes_in_radius(site.hex, FIELD_RADIUS):
        idx = world._index(h)
        if idx is None or idx in taken:
            continue
        fert = fertility(state, site.tribe_id, h)
        if fert <= 0.1:
            continue
        s = soil.get(_key(*idx), 1.0)
        scored.append((fert * s, idx))
    scored.sort(key=lambda it: (-it[0], it[1]))
    return [list(idx) for _v, idx in scored[:want]]


def hands_mult(band, fields: int, busy: int = 0) -> float:
    """Assez de bras pour rentrer la recolte ? (les troupes sont loin, les
    gens de metier a leur ouvrage)."""
    need = fields * FIELD_HANDS
    hands = band.population - busy
    if need <= 0 or hands >= need:
        return 1.0
    return max(0.3, hands / need)


def field_hands_mult(site, band) -> float:
    from src.kora import goods

    return hands_mult(band, len(site.data.get("fields", [])), goods.workers(site, band))


def expected_harvest(state, site, band=None) -> float:
    band = band or band_of(state, site)
    if band is None:
        return 0.0
    from src.kora.world import offset_to_axial

    soil = site.data.get("soil", {})
    total = 0.0
    fields = site.data.get("fields", [])
    for col, row in fields:
        h = offset_to_axial(col, row)
        total += fertility(state, site.tribe_id, h) * soil.get(_key(col, row), 1.0)
    ratio = site.data.get("sown_ratio", 0.0)
    burned = BURNED if site.data.get("burned") else 1.0
    return total * FIELD_FOOD * ratio * yield_mult(state, site) * burned * field_hands_mult(site, band)


# Semailles : faute de semences gardees, on seme le grain du grenier (en
# gardant SOW_KEEP_WEEKS semaines de vivres) ; sans rien, les graines
# sauvages des terres (cereales, racines) donnent de quoi semer un champ :
# un village qui a mange ses semences n'est pas condamne a la cueillette.
SOW_KEEP_WEEKS = 4


def _wild_seed(state, site) -> float:
    from src.kora import goods

    found = goods.riches(state.world, site.hex)
    return SEED if found.get("cereales") or found.get("racines") else 0.0


def sow(state, site, band, late: bool = False) -> None:
    fields = choose_fields(state, site, band)
    need = SEED * len(fields)
    seed = site.data.get("seed", 0.0)
    from_granary = 0.0
    wild = 0.0
    if seed < need:
        from_granary = min(need - seed, max(0.0, band.stock - SOW_KEEP_WEEKS * band.population))
        band.stock -= from_granary
        seed += from_granary
    if seed < SEED and fields:
        wild = min(_wild_seed(state, site), need - seed)
        seed += wild
    sown = min(seed, need)
    site.data["seed"] = seed - sown
    # Ce qui reste des semences retourne au grenier.
    if site.data["seed"] > 0:
        from src.kora.sim import stock_max

        band.stock = min(stock_max(band, state), band.stock + site.data["seed"])
        site.data["seed"] = 0.0
    site.data["fields"] = fields if sown > 0 else []
    ratio = (sown / need) if need > 0 else 0.0
    site.data["sown_ratio"] = ratio * (LATE_SOW if late else 1.0)
    site.data["burned"] = False
    if state.tribes[band.tribe_id].is_player:
        if sown <= 0:
            _note(state, LogKind.SURVIE, f"{name(site)} : pas de semences, les champs restent vides cette annee.", site.hex)
        else:
            extra = ""
            if from_granary >= 1:
                extra += f" ({from_granary:.0f} vivres du grenier semes"
                extra += ", et des graines sauvages)" if wild else ")"
            elif wild:
                extra = " (des graines sauvages, faute de semences)"
            _note(state, LogKind.SURVIE, f"{name(site)} : semailles sur {len(fields)} champs{extra}.", site.hex)


def harvest(state, site, band) -> float:
    from src.kora.sim import stock_max

    bonus = _bonus(state, site.tribe_id)
    luck = state.story_rng.uniform(0.8, 1.2)
    crop = expected_harvest(state, site, band) * luck
    short = field_hands_mult(site, band)
    # Le sol des champs s'epuise ; celui des cases au repos se refait.
    soil = site.data.setdefault("soil", {})
    fields = {tuple(f) for f in site.data.get("fields", [])}
    for key in list(soil):
        col, row = (int(x) for x in key.split(","))
        if (col, row) not in fields:
            soil[key] = min(1.0, soil[key] + SOIL_REST)
            if soil[key] >= 1.0:
                del soil[key]
    for col, row in fields:
        k = _key(col, row)
        soil[k] = max(0.2, soil.get(k, 1.0) - SOIL_LOSS * bonus.soil_loss)
    # Semences de l'an prochain d'abord, le reste au grenier.
    want = SEED * min(MAX_FIELDS, max(1, math.ceil(band.population / FIELD_WORKERS)))
    keep = min(crop, want)
    site.data["seed"] = site.data.get("seed", 0.0) + keep
    band.stock = min(stock_max(band, state), band.stock + crop - keep)
    site.data["fields"] = []
    site.data["sown_ratio"] = 0.0
    site.data["last_harvest"] = round(crop)
    history = site.data.setdefault("history", [])
    history.append([state.clock.year, round(crop)])
    del history[:-HISTORY]
    if state.tribes[band.tribe_id].is_player and crop > 0:
        text = f"{name(site)} : recolte de {crop:.0f} vivres."
        if short < 1.0:
            text += " Il manquait des bras : une part est restee aux champs."
        _note(state, LogKind.SURVIE, text, site.hex)
    if crop > 0 and luck >= 1.15:
        from src.kora import events

        events.hook(state, "bonne_recolte", tribe_id=band.tribe_id, band_id=band.id)
    return crop


# --- fonder, quitter ----------------------------------------------------------------


def found_block(state, band_id: int) -> str:
    from src.kora import chiefs, sites

    band = state.bands.get(band_id)
    if band is None:
        return "Pas de bande"
    if band.village:
        return ""
    if band.kind == "armee":
        return "Une troupe ne fonde pas de village"
    know = _bonus(state, band.tribe_id)
    if know.villages <= 0:
        return "Il faut connaitre Premieres semailles"
    if not chiefs.obeys(state, band):
        return "Ce clan n'obeit plus"
    if band.retreating:
        return "La bande est en repli"
    camp = sites.own_site_at(state, band)
    if camp is None or camp.kind != "camp":
        return "Il faut etre sur un de vos campements"
    if len(sites.of_tribe(state, band.tribe_id, "village")) >= know.villages:
        return f"Villages : {len(sites.of_tribe(state, band.tribe_id, 'village'))}/{know.villages}"
    if band.population < MIN_FOUND_POP:
        return f"Il faut {MIN_FOUND_POP} personnes"
    if not any(fertility(state, band.tribe_id, h) > 0.35 for h in state.world.hexes_in_radius(camp.hex, FIELD_RADIUS)):
        return "Aucune terre a cultiver autour"
    return ""


def propose_name(state, band_id: int) -> str:
    """Nom propose dans la fenetre de fondation : stable tant qu'elle est
    ouverte, sans toucher au hasard du recit."""
    from src.kora import sites
    from src.kora.peoples import CULTURES, culture_of, make_name

    band = state.bands[band_id]
    camp = sites.own_site_at(state, band)
    tribe = state.tribes[band.tribe_id]
    rng = random.Random((camp.id if camp else 0) * 7919 + band.tribe_id * 131 + 17)
    taken = [s.name for s in state.sites.values() if s.name]
    culture = culture_of(tribe) if culture_of(tribe).syllables else CULTURES["vallee"]
    return make_name(rng, culture, taken)


def found(state, band_id: int, oath: str = "", name_: str | None = None):
    """La bande s'installe : son campement devient un village."""
    from src.kora import sites
    from src.kora.peoples import CULTURES, culture_of, make_name

    if found_block(state, band_id) or state.bands[band_id].village:
        return None
    band = state.bands[band_id]
    camp = sites.own_site_at(state, band)
    tribe = state.tribes[band.tribe_id]
    first = not sites.of_tribe(state, band.tribe_id, "village") and "age_villages" not in tribe.flags
    camp.kind = "village"
    if name_:
        camp.name = name_
    else:
        taken = [s.name for s in state.sites.values() if s.name]
        camp.name = make_name(state.story_rng, culture_of(tribe) if culture_of(tribe).syllables else CULTURES["vallee"], taken)
    band.position = camp.hex
    band.path = []
    from src.kora.types import stay_order

    band.order = stay_order()
    band.village = camp.id
    band.autonomy = 0.0
    camp.founded = state.clock.year
    camp.data.update(
        {
            "band": band.id,
            "fields": [],
            "soil": {},
            "seed": 0.0,
            "sown_ratio": 0.0,
            "buildings": [],
            "build": None,
            "oath": oath if oath in OATHS else "",
            "history": [],
        }
    )
    # Les reserves du campement et une part du stock deviennent semences.
    from src.kora.sim import stock_max

    band.stock = min(stock_max(band, state), band.stock + camp.store)
    camp.store = 0.0
    need = SEED * min(MAX_FIELDS, max(1, math.ceil(band.population / FIELD_WORKERS)))
    seed = min(need, band.stock * 0.5)
    band.stock -= seed
    camp.data["seed"] = seed
    season = state.world.hex_season(camp.hex)
    camp.data["season"] = season.value
    if season in (Season.PRINTEMPS, Season.ETE):
        sow(state, camp, band, late=season is Season.ETE)
    if first:
        # L'age des villages : prestige, les premieres troupes, et les clans
        # restes nomades qui s'eloignent (chiefs.loyalty_parts).
        tribe.flags["age_villages"] = -1
        tribe.prestige = min(100, tribe.prestige + FIRST_VILLAGE_PRESTIGE)
    if tribe.settled_at < 0:
        tribe.settled_at = state.tick_count
    if first:
        _chief_takes_the_village(state, tribe, band)
    if tribe.is_player:
        _note(state, LogKind.SURVIE, f"Le village de {camp.name} est fonde.", camp.hex)
        if first:
            _note(
                state,
                LogKind.POLITIQUE,
                f"L'age des villages commence (+{FIRST_VILLAGE_PRESTIGE} prestige) : vos villages levent des troupes, vos clans nomades s'emanciperont.",
                camp.hex,
            )
    return camp


def seat_chiefs(state) -> None:
    """Chaque peuple qui a un village : son chef gouverne le plus grand."""
    from src.kora import chiefs

    for tribe in state.tribes.values():
        heart = chiefs.chief_band(state, tribe.id)
        if heart is None or heart.village:
            continue
        homes = [band_of(state, s) for s in state.sites.values() if s.kind == "village" and s.tribe_id == tribe.id]
        homes = [b for b in homes if b is not None]
        if homes:
            seat = max(homes, key=lambda b: (b.population, -b.id))
            _chief_takes_the_village(state, tribe, seat, quiet=True)


def _chief_takes_the_village(state, tribe, band, quiet: bool = False) -> None:
    """Le premier village devient le siege du chef : s'il menait une autre
    bande, il vient y gouverner (les deux chefs de bande echangent)."""
    from src.kora import chiefs

    heart = chiefs.chief_band(state, tribe.id)
    if heart is None or heart.id == band.id:
        return
    chief, local = heart.leader, band.leader
    band.leader, heart.leader = chief, local
    tribe.chief_band = band.id
    band.loyalty = 100.0
    heart.loyalty = min(heart.loyalty, 70.0)
    if tribe.is_player and chief is not None and not quiet:
        _note(state, LogKind.POLITIQUE, f"{chief.name} s'installe au village et y gouverne ; ses anciens clans ne lui obeiront plus longtemps.", band.position)


def ai_oath(state, tribe_id: int) -> str:
    from src.kora.peoples import culture_of

    return AI_OATH.get(culture_of(state.tribes[tribe_id]).id, "grenier")


def found_preview(state, band_id: int) -> dict:
    """Ce que la fenetre de fondation montre : le lieu, ses terres, ses
    dangers, le nom propose, et si c'est le premier village du peuple."""
    from src.kora import diplo, sites
    from src.kora.resources import LABELS, PRESENT

    band = state.bands[band_id]
    camp = sites.own_site_at(state, band)
    world = state.world
    center = camp.hex if camp is not None else band.position
    ferts = []
    forest = 0
    for h in world.hexes_in_radius(center, FIELD_RADIUS):
        f = fertility(state, band.tribe_id, h)
        if f > 0.1:
            ferts.append(f)
        elif world.terrain(h) is _T.FORET:
            forest += 1
    ferts.sort(reverse=True)
    want = min(MAX_FIELDS, max(1, math.ceil(band.population / FIELD_WORKERS)))
    best = ferts[:want]
    need = SEED * want
    seed = min(need, (band.stock + (camp.store if camp else 0.0)) * 0.5)
    sown = (seed / need) if need else 0.0
    harvest_guess = sum(best) * FIELD_FOOD * _bonus(state, band.tribe_id).field_yield * sown
    res = {}
    for h in world.hexes_in_radius(center, FIELD_RADIUS):
        for rname in ("cereales", "racines", "argile", "silex", "sel", "chevres", "aurochs", "poisson"):
            if world.resources and world.resource(h, rname) >= PRESENT:
                res[rname] = res.get(rname, 0) + 1
    risks = []
    if world.terrain(center) is _T.VALLEE:
        risks.append("Vallee : les crues du printemps peuvent noyer les champs")
    if forest and not _bonus(state, band.tribe_id).clearing:
        risks.append(f"{forest} cases de foret a defricher (il faut Haches polies)")
    foes = {
        b.tribe_id
        for b in state.bands.values()
        if b.tribe_id != band.tribe_id
        and b.population > 0
        and not diplo.at_peace(state, b.tribe_id, band.tribe_id)
        and world.distance(b.position, center) <= 12
    }
    if foes:
        names = ", ".join(sorted(state.tribes[t].name for t in foes if t in state.tribes))
        risks.append(f"Voisins sans pacte a moins de 12 cases : {names}")
    if band.population >= DISEASE_POP:
        risks.append("Beaucoup de monde : les fievres guettent les gros villages")
    tribe = state.tribes[band.tribe_id]
    return {
        "name": propose_name(state, band_id),
        "hex": center,
        "fields": len(best),
        "fields_max": want,
        "fertility": (sum(best) / len(best)) if best else 0.0,
        "harvest": harvest_guess,
        "seed_ratio": sown,
        "resources": [LABELS[k] for k, _n in sorted(res.items(), key=lambda it: -it[1])][:5],
        "risks": risks,
        "first": not sites.of_tribe(state, band.tribe_id, "village") and "age_villages" not in tribe.flags,
        "villages": len(sites.of_tribe(state, band.tribe_id, "village")),
        "villages_max": _bonus(state, band.tribe_id).villages,
        "population": band.population,
    }


def leave_block(state, band_id: int) -> str:
    band = state.bands.get(band_id)
    if band is None or not band.village:
        return "Pas un village"
    return ""


def leave(state, band_id: int) -> bool:
    """Le village est abandonne : la bande reprend la route, le lieu redevient
    un campement (avec ce qui ne tient pas dans le stock). Batiments perdus."""
    from src.kora.sim import stock_max

    band = state.bands.get(band_id)
    site = site_of(state, band)
    if site is None:
        return False
    band.village = 0
    cap = stock_max(band, state)
    extra = max(0.0, band.stock - cap) + site.data.get("seed", 0.0)
    band.stock = min(band.stock, cap)
    site.kind = "camp"
    site.store = extra
    site.data = {}
    if state.tribes[band.tribe_id].is_player:
        _note(state, LogKind.SURVIE, f"{name(site)} est abandonne.", site.hex)
    return True


# --- palissade (le batiment "palissade") ---------------------------------------------------


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
    if not _bonus(state, band.tribe_id).palisade:
        return "Il faut connaitre Palissades"
    if palisade_state(site) == "built":
        return "La palissade est debout"
    return build_block_site(state, site, "palissade")


def build_palisade(state, band_id: int) -> bool:
    if palisade_block(state, band_id):
        return False
    return build(state, band_id, "palissade")


# --- troupes -----------------------------------------------------------------------------
# Une troupe (Band.kind == "armee") est une pile de compagnies
# [type, hommes, village] (units.py). Band.home : le village de sa premiere
# compagnie (son chef de guerre y est ne).


def _companies(band) -> list:
    from src.kora import units

    return units.normalize(band)


def armies_of(state, site) -> list:
    """Troupes ou sert au moins une compagnie de ce village."""
    return sorted(
        (
            b
            for b in state.bands.values()
            if b.kind == "armee" and b.population > 0 and any(u[2] == site.id for u in _companies(b))
        ),
        key=lambda b: b.id,
    )


def companies_of(state, site) -> int:
    return sum(1 for b in armies_of(state, site) for u in _companies(b) if u[2] == site.id)


def army_cap(state, site) -> int:
    """Compagnies qu'un village peut avoir sous les armes en meme temps."""
    return 2 + (1 if has(site, "guerriers") else 0)


def _village_alive(state, site_id: int):
    site = state.sites.get(site_id)
    if site is None or site.kind != "village" or band_of(state, site) is None:
        return None
    return site


def home_of(state, band):
    if band is None or band.kind != "armee":
        return None
    return _village_alive(state, band.home)


def _warrior_share(state, band) -> float:
    comps = _companies(band)
    total = sum(u[1] for u in comps)
    if total <= 0:
        return 0.0
    trained = sum(u[1] for u in comps if has(_village_alive(state, u[2]), "guerriers"))
    return trained / total


def army_quality(state, band) -> float:
    from src.kora import goods

    return (1.0 + (WARRIORS_QUALITY - 1.0) * _warrior_share(state, band)) * goods.army_mult(state, band.tribe_id)


def army_morale(state, band) -> float:
    return WARRIORS_MORALE * _warrior_share(state, band)


def levy_size(band, share: float) -> int:
    return int(band.population * share)


def levy_type(state, tribe_id: int, type_id: str | None):
    from src.kora import units

    tribe = state.tribes[tribe_id]
    u = units.UNITS.get(type_id or "")
    if u is not None and units.known(tribe, u):
        return u
    return units.best(tribe, "melee")


def army_block(state, band_id: int, share: float = LEVY_SHARE["troupe"], type_id: str | None = None) -> str:
    from src.kora import tech, units

    band = state.bands.get(band_id)
    site = site_of(state, band)
    if site is None:
        return "Seul un village leve des guerriers"
    if type_id and type_id in units.UNITS and not units.known(state.tribes[band.tribe_id], units.UNITS[type_id]):
        return f"Il faut connaitre {tech.TECHS[units.UNITS[type_id].needs].name}"
    if band.population < ARMY_MIN_VILLAGE:
        return f"Il faut {ARMY_MIN_VILLAGE} habitants"
    n = levy_size(band, share)
    if n < ARMY_MIN:
        return f"Trop peu de guerriers ({n}, il en faut {ARMY_MIN})"
    if band.population - n < VILLAGE_KEEP:
        return "Le village se viderait"
    count, cap = companies_of(state, site), army_cap(state, site)
    if count >= cap:
        return f"Deja {count}/{cap} compagnies levees (Maison des guerriers : une de plus)"
    return ""


def raise_army(state, band_id: int, share: float = LEVY_SHARE["troupe"], type_id: str | None = None):
    """Le village leve une compagnie : ses hommes partent avec des vivres du
    grenier. Une troupe du village est au village : la compagnie la rejoint ;
    sinon, c'est une nouvelle troupe, menee par un chef de guerre."""
    from src.kora import chiefs, units
    from src.kora.sim import _ai_caches_changed, new_band_id, stock_max
    from src.kora.types import Band

    if army_block(state, band_id, share, type_id):
        return None
    band = state.bands[band_id]
    site = site_of(state, band)
    tribe = state.tribes[band.tribe_id]
    kind = levy_type(state, band.tribe_id, type_id)
    n = levy_size(band, share)
    supply = min(band.stock, float(ARMY_SUPPLY_WEEKS * n))
    band.stock -= supply
    band.population -= n
    here = next(
        (
            a
            for a in armies_of(state, site)
            if a.tribe_id == band.tribe_id
            and not a.homebound
            and not a.retreating
            and state.world.distance(a.position, site.hex) <= ARMY_HOME
        ),
        None,
    )
    if here is not None:
        units.add(here, kind.id, n, site.id)
        here.stock = min(stock_max(here, state), here.stock + supply)
        if tribe.is_player:
            _note(state, LogKind.COMBAT, f"{name(site)} leve {n} {kind.name.lower()} : ils rejoignent la troupe.", site.hex)
        return here
    nid = new_band_id(state)
    army = Band(nid, band.tribe_id, site.hex, n, supply, kind="armee", home=site.id, raised=state.tick_count, units=[[kind.id, n, site.id]])
    army.leader = chiefs.new_person(state, tribe)
    army.loyalty = 100.0
    state.bands[nid] = army
    _ai_caches_changed(state)
    if tribe.is_player:
        _note(state, LogKind.COMBAT, f"{name(site)} leve une troupe : {n} {kind.name.lower()}, menes par {army.leader.name}.", site.hex)
    return army


def detach_block(state, band_id: int) -> str:
    band = state.bands.get(band_id)
    if band is None or band.kind != "armee":
        return "Pas une troupe"
    if band.homebound:
        return "La troupe rentre au village"
    if band.retreating:
        return "La troupe est en repli"
    if len(_companies(band)) < 2:
        return "Une seule compagnie : rien a detacher"
    return ""


def _split_units(state, band, comps: list, leader=None, homebound: bool = False):
    """Une nouvelle troupe faite de ces compagnies (retirees de band)."""
    from src.kora import chiefs
    from src.kora.sim import _ai_caches_changed, new_band_id
    from src.kora.types import Band

    men = sum(u[1] for u in comps)
    share = men / max(1, band.population)
    stock = band.stock * share
    band.stock -= stock
    band.units = [u for u in band.units if not any(u is c for c in comps)]
    band.population -= men
    nid = new_band_id(state)
    out = Band(
        nid, band.tribe_id, band.position, men, stock, kind="armee", home=comps[0][2], raised=band.raised,
        units=[list(u) for u in comps], homebound=homebound,
    )
    out.leader = leader or chiefs.new_person(state, state.tribes[band.tribe_id])
    out.loyalty = 100.0
    state.bands[nid] = out
    _ai_caches_changed(state)
    return out


def detach(state, band_id: int):
    """La derniere compagnie forme une troupe a part."""
    if detach_block(state, band_id):
        return None
    band = state.bands[band_id]
    comp = _companies(band)[-1]
    return _split_units(state, band, [comp])


def disband_block(state, band_id: int) -> str:
    """Rentrer tout de suite : au village (sinon, dissoudre = rentrer a pied)."""
    band = state.bands.get(band_id)
    if band is None or band.kind != "armee":
        return "Pas une troupe"
    if band.retreating:
        return "La troupe est en repli"
    if _village_near(state, band) is None:
        return "Rentrez au village pour liberer les guerriers"
    return ""


def dissolve_block(state, band_id: int) -> str:
    band = state.bands.get(band_id)
    if band is None or band.kind != "armee":
        return "Pas une troupe"
    if band.retreating:
        return "La troupe est en repli"
    if band.homebound:
        return "La troupe rentre deja au village"
    return ""


def _village_near(state, band):
    """Village de son peuple sur la case (ou a cote) : le sien d'abord."""
    best = None
    for site in state.sites.values():
        if site.kind != "village" or site.tribe_id != band.tribe_id or band_of(state, site) is None:
            continue
        if state.world.distance(site.hex, band.position) <= ARMY_HOME:
            if site.id == band.home:
                return site
            best = best or site
    return best


def _join_village(state, army, site) -> None:
    """Les hommes de la troupe redeviennent villageois de ce village."""
    from src.kora import chiefs
    from src.kora.sim import _absorb

    home = band_of(state, site)
    keep = home.loyalty
    n = army.population
    army.units = []
    _absorb(state, home, army)
    if not chiefs.is_chief_band(state, home):
        home.loyalty = keep
    if state.tribes[home.tribe_id].is_player:
        _note(state, LogKind.COMBAT, f"La troupe rentre a {name(site)} : {n} guerriers retrouvent leurs champs.", site.hex)


def _to_clan(state, band) -> None:
    band.kind = ""
    band.home = 0
    band.units = []
    band.homebound = False
    if state.tribes[band.tribe_id].is_player:
        who = band.leader.name if band.leader else "?"
        _note(state, LogKind.COMBAT, f"La troupe de {who} n'a plus de village : elle devient un clan errant.", band.position)


def _send_home(state, band, site) -> None:
    from src.kora.sim import set_goto

    band.homebound = False
    set_goto(state, band.id, site.hex, max_nodes=1200, max_cost=4000)
    if band.path:
        band.homebound = True
    elif state.world.distance(site.hex, band.position) > ARMY_HOME:
        _to_clan(state, band)


def dissolve(state, band_id: int) -> bool:
    """Dissoudre la troupe : chaque compagnie rentre a son village (a pied)
    et y redevient villageoise a l'arrivee ; au village, tout de suite."""
    if dissolve_block(state, band_id):
        return False
    army = state.bands[band_id]
    comps = _companies(army)
    groups: dict[int, list] = {}
    for u in comps:
        groups.setdefault(u[2], []).append(u)
    here = _village_near(state, army)
    main = here.id if here is not None and here.id in groups else (army.home if army.home in groups else max(groups, key=lambda k: sum(u[1] for u in groups[k])))
    for home, us in sorted(groups.items()):
        if home == main:
            continue
        part = _split_units(state, army, us)
        site = _village_alive(state, home)
        if site is None:
            _to_clan(state, part)
        elif state.world.distance(site.hex, part.position) <= ARMY_HOME:
            _join_village(state, part, site)
        else:
            _send_home(state, part, site)
    site = _village_alive(state, main)
    if site is None and here is not None:
        site = here
    if site is None:
        _to_clan(state, army)
    elif state.world.distance(site.hex, army.position) <= ARMY_HOME:
        _join_village(state, army, site)
    else:
        army.home = site.id
        _send_home(state, army, site)
        if army.homebound and state.tribes[army.tribe_id].is_player:
            _note(state, LogKind.COMBAT, f"La troupe est dissoute : ses hommes rentrent a {name(site)}.", army.position)
    return True


def disband(state, band_id: int) -> bool:
    """La troupe est au village : ses guerriers redeviennent villageois (les
    compagnies d'autres villages rentrent chez elles)."""
    if disband_block(state, band_id):
        return False
    return dissolve(state, band_id) if not state.bands[band_id].homebound else _arrive(state, state.bands[band_id])


def _arrive(state, band) -> bool:
    site = _village_alive(state, band.home)
    if site is None:
        _to_clan(state, band)
        return False
    band.homebound = False
    _join_village(state, band, site)
    return True


def recall(state, band_id: int) -> bool:
    """Ancien ordre "Rappeler" : c'est desormais dissoudre (rentrer a pied)."""
    return dissolve(state, band_id)


def reequip_block(state, band_id: int) -> str:
    from src.kora import units

    band = state.bands.get(band_id)
    if band is None or band.kind != "armee":
        return "Pas une troupe"
    site = _village_near(state, band)
    if site is None:
        return "Au village seulement"
    tribe = state.tribes[band.tribe_id]
    old = [u for u in _companies(band) if u[2] == site.id and units.outdated(tribe, u[0])]
    if not old:
        return "Rien a reequiper"
    cost = units.REEQUIP_COST * sum(u[1] for u in old)
    if band_of(state, site).stock < cost:
        return f"Il faut {cost:.0f} vivres au grenier"
    return ""


def reequip(state, band_id: int) -> bool:
    """Un age nouveau : les compagnies de ce village prennent les armes de leur
    temps (meilleur type de leur role)."""
    from src.kora import units

    if reequip_block(state, band_id):
        return False
    band = state.bands[band_id]
    site = _village_near(state, band)
    tribe = state.tribes[band.tribe_id]
    village = band_of(state, site)
    for u in _companies(band):
        if u[2] == site.id and units.outdated(tribe, u[0]):
            new = units.best(tribe, units.UNITS[u[0]].role)
            village.stock -= units.REEQUIP_COST * u[1]
            u[0] = new.id
    if tribe.is_player:
        _note(state, LogKind.COMBAT, f"{name(site)} reequipe ses compagnies.", site.hex)
    return True


def _update_armies(state) -> None:
    """Troupes qui rentrent, troupes sans village, desertions."""
    for band in sorted(state.bands.values(), key=lambda b: b.id):
        if band.kind != "armee" or band.population <= 0 or band.id not in state.bands:
            continue
        comps = _companies(band)
        if band.homebound:
            site = _village_alive(state, band.home)
            if site is None:
                _to_clan(state, band)
            elif state.world.distance(site.hex, band.position) <= ARMY_HOME:
                _arrive(state, band)
            elif not band.path:
                _send_home(state, band, site)
            continue
        if not any(_village_alive(state, u[2]) is not None for u in comps):
            _to_clan(state, band)
            continue
        site = home_of(state, band) or next(_village_alive(state, u[2]) for u in comps if _village_alive(state, u[2]) is not None)
        away = state.world.distance(site.hex, band.position) > 2
        if not away or state.tick_count - band.raised <= ARMY_TERM or state.tick_count % 4:
            continue
        gone = max(1, round(band.population * DESERTION))
        band.population -= gone
        band_of(state, site).population += gone
        if state.tribes[band.tribe_id].is_player and state.tick_count % 12 == 0:
            _note(state, LogKind.COMBAT, f"Trop longtemps loin de {name(site)} : des guerriers desertent et rentrent chez eux.", band.position)


def _alert(state, site, band) -> None:
    """Tour de guet : on voit venir l'ennemi."""
    from src.kora import diplo

    if not state.tribes[band.tribe_id].is_player or not has(site, "tour"):
        return
    if state.tick_count - site.data.get("alert", -1000) < ALERT_EVERY:
        return
    for foe in state.bands.values():
        if foe.tribe_id == band.tribe_id or foe.population <= 0:
            continue
        if diplo.at_peace(state, foe.tribe_id, band.tribe_id):
            continue
        if state.world.distance(foe.position, site.hex) <= ALERT_RANGE:
            site.data["alert"] = state.tick_count
            who = state.tribes[foe.tribe_id].name if foe.tribe_id in state.tribes else "etrangers"
            what = "une troupe" if foe.kind == "armee" else f"{foe.population} personnes"
            _note(state, LogKind.COMBAT, f"Tour de guet de {name(site)} : des {who} approchent ({what}) !", foe.position)
            return


# --- chaque semaine --------------------------------------------------------------------


def update(state) -> None:
    """Saisons locales (semailles, recolte), grain qui se perd, chantiers,
    semences en temps de famine, fievres, crues, troupes, tours de guet."""
    from src.kora import events

    for site in sorted(state.sites.values(), key=lambda s: s.id):
        if site.kind != "village":
            continue
        band = band_of(state, site)
        if band is None:
            continue
        site.tribe_id = band.tribe_id
        tribe = state.tribes.get(band.tribe_id)
        if tribe is not None and tribe.settled_at < 0:
            # Ancienne sauvegarde, clan parti avec son village : l'age des
            # villages commence maintenant pour ce peuple.
            tribe.settled_at = state.tick_count
        bonus = _bonus(state, site.tribe_id)
        season = state.world.hex_season(site.hex)
        last = site.data.get("season")
        if last != season.value:
            site.data["season"] = season.value
            site.data["season_at"] = state.tick_count
            if season is Season.PRINTEMPS:
                sow(state, site, band)
                if state.world.terrain(site.hex) is _T.VALLEE and state.story_rng.random() < FLOOD_CHANCE:
                    events.hook(state, "crue", tribe_id=band.tribe_id, band_id=band.id)
            elif season is Season.AUTOMNE:
                harvest(state, site, band)
        if band.stock > 0:
            band.stock *= 1.0 - GRAIN_ROT * rot_mult(state, site)
        _advance_works(state, site, band)
        if band.famine_in_period and site.data.get("seed", 0.0) > 0 and site.data.get("asked") != state.clock.year:
            site.data["asked"] = state.clock.year
            if not events.hook(state, "semences", tribe_id=band.tribe_id, band_id=band.id):
                if not state.tribes[band.tribe_id].is_player and state.story_rng.random() < 0.5:
                    eat_seed(state, band)
        if state.tick_count % 4 == 0:
            _unrest(state, site, band)
        if state.tick_count % 4 == 0 and band.population >= DISEASE_POP:
            risk = 0.012 * band.population / 100.0 * bonus.disease * (0.6 if has(site, "puits") else 1.0)
            if state.story_rng.random() < risk:
                events.hook(state, "fievre_village", tribe_id=band.tribe_id, band_id=band.id)
        _alert(state, site, band)
    from src.kora import goods

    goods.update(state)
    _update_armies(state)


def eat_seed(state, band) -> float:
    from src.kora.sim import stock_max

    site = site_of(state, band)
    if site is None:
        return 0.0
    seed = site.data.get("seed", 0.0)
    band.stock = min(stock_max(band, state) + seed, band.stock + seed)
    site.data["seed"] = 0.0
    return seed


def pillaged(state, band, rng=None) -> str:
    """Village battu : les champs brulent (recolte x0,6), et parfois un
    batiment (jamais la palissade). Rend le nom du batiment perdu."""
    site = site_of(state, band)
    if site is None:
        return ""
    site.data["burned"] = True
    rng = rng or state.story_rng
    lost = [b for b in built(site) if b != "palissade"]
    if lost and rng.random() < LOSE_BUILDING:
        gone = lost[int(rng.random() * len(lost)) % len(lost)]
        site.data["buildings"].remove(gone)
        return BUILDINGS[gone].name
    return ""


def lost(state, band) -> None:
    """La bande du village a disparu : il n'en reste que des ruines."""
    site = site_of(state, band)
    if site is not None:
        state.sites.pop(site.id, None)
        tribe = state.tribes.get(band.tribe_id)
        if tribe is not None and tribe.is_player:
            _note(state, LogKind.COMBAT, f"{name(site)} n'est plus que ruines.", site.hex)


# --- lecture ----------------------------------------------------------------------------


def field_site(state, h):
    """Le village dont cette case est un champ (ou None)."""
    idx = state.world._index(h)
    if idx is None:
        return None
    for site in state.sites.values():
        if site.kind == "village" and list(idx) in site.data.get("fields", []):
            return site
    return None


def soil_avg(site) -> float:
    soil = site.data.get("soil", {})
    fields = site.data.get("fields", [])
    if not fields:
        return 1.0
    return sum(soil.get(_key(c, r), 1.0) for c, r in fields) / len(fields)


def next_step(state, site) -> tuple[str, int]:
    """Prochaine etape des champs (semailles ou recolte) et dans combien de
    semaines, a peu pres (saisons locales : 13 semaines chacune)."""
    season = state.world.hex_season(site.hex)
    week = (state.clock.week - 1) % 13
    left = 13 - week
    if season is Season.PRINTEMPS:
        return "Recolte a l'automne", left + 13
    if season is Season.ETE:
        return "Recolte a l'automne", left
    if season is Season.AUTOMNE:
        return "Semailles au printemps", left + 13
    return "Semailles au printemps", left


def lines(state, band) -> list[str]:
    """Lignes de la fiche d'une bande installee."""
    site = site_of(state, band)
    if site is None:
        return []
    fields = site.data.get("fields", [])
    seed = site.data.get("seed", 0.0)
    out = [f"Village de {name(site)}  ·  champs {len(fields)}  ·  semences {seed:.0f}  ·  batiments {len(built(site))}"]
    season = state.world.hex_season(site.hex)
    crop = expected_harvest(state, site, band)
    if fields:
        out.append(f"Recolte attendue a l'automne : ~{crop:.0f}  ·  sol {100 * soil_avg(site):.0f} %")
    elif season in (Season.ETE, Season.AUTOMNE, Season.HIVER):
        last = site.data.get("last_harvest")
        out.append(f"Derniere recolte : {last}  ·  semailles au printemps" if last is not None else "Semailles au printemps")
    job = works(site)
    if job:
        out.append(f"Chantier : {BUILDINGS[job[0]].name} (encore {job[1]} sem.)  ·  [V] pour gerer le village")
    elif palisade_state(site) == "built":
        out.append("Palissade : debout (defense x1,6)  ·  [V] pour gerer le village")
    else:
        out.append("[V] pour gerer le village : batiments, troupes")
    return out


def army_lines(state, band) -> list[str]:
    """Lignes de la fiche d'une troupe."""
    if band.kind != "armee":
        return []
    from src.kora import units

    site = home_of(state, band)
    home = name(site) if site is not None else "sans village"
    out = [f"Troupe de {home}  ·  {band.population} guerriers  ·  levee il y a {state.tick_count - band.raised} sem."]
    out += units.lines(state, band)
    if band.homebound:
        out.append(f"Dissoute : elle rentre a {home}, on ne la commande plus")
    elif site is not None:
        d = state.world.distance(site.hex, band.position)
        if d > 2 and state.tick_count - band.raised > ARMY_TERM:
            out.append("Trop longtemps loin du village : des guerriers desertent")
        elif d <= ARMY_HOME:
            out.append("Au village : [F] Rentrer libere les guerriers")
    return out


def _note(state, kind, text: str, where=None) -> None:
    state.log.add(kind, text, state.clock.year, state.clock.week, where=where)
