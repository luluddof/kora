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
Ses batiments, ses chantiers, le grand monument : batiments.py ; ses
troupes (levee, milice, retour) : troupes.py. Un village ne fuit pas : pille, il perd son grain,
ses champs brulent, parfois un batiment. Les fievres de la promiscuite et
les crues des vallees le menacent (evenements).
N'importe ni pygame ni render.
"""

from __future__ import annotations

import math
import random
from dataclasses import dataclass

from src.kora import chiefdom, chiefs, events, goods, population, production, sites, systems, tech
from src.kora.log import LogKind
from src.kora.types import Band, Season, Terrain, stay_order
from src.kora.resources import LABELS, NAMES, PRESENT
from src.kora.world import offset_to_axial
from src.kora.places import VillageData
from src.kora.gamestate import PLAYER_TRIBE_ID, note
from src.kora.peoples import CULTURES, civ_of, culture_of, make_name
from src.kora.bands import (
    _ai_caches_changed,
    civ_band_cap,
    civ_band_count,
    gain_prestige,
    new_band_id,
    stock_max,
)
from src.kora.places import (  # noqa: F401
    RANKS,
    band_of,
    built,
    has,
    monument_stages,
    name,
    oath_of,
    rank_name,
    site_of,
    watch_spots,
    works,
)

from src.kora.population import ACTIVE_NORM, CRAFT_SEX, CRAFT_WORKERS, _craft_take, fit_men, fit_women
from src.kora.places import (  # noqa: F401
    NEAR,
    influence_radius,
)
from src.kora import troupes
from src.kora import batiments
from src.kora import guerre

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
BURNED = 0.6
DISEASE_POP = 80
FLOOD_CHANCE = 0.06
MIN_FOUND_POP = 20
# Bras pour la recolte : habitants par champ (sinon une part est perdue).
FIELD_HANDS = 0.6 * FIELD_WORKERS
HISTORY = 8
FIRST_VILLAGE_PRESTIGE = 10
LOSE_BUILDING = 0.35
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
    # 0.20 : la savane se cultive, la jungle seulement defrichee (comme la
    # foret), le marais pas (il faudrait l'assecher), la toundra a peine.
    _T.SAVANE: 0.55,
    _T.JUNGLE: 0.45,
    _T.TOUNDRA: 0.1,
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
            "Avant les maisons, on élève le grenier : ici, on ne manquera jamais.",
            ("Grenier du village +25 %", "Le grain se gâte x0,7"),
        ),
        Oath(
            "champs",
            "Les champs d'abord",
            "Chaque bras va à la terre : les champs seront les plus beaux de la vallée.",
            ("Récolte +10 %", "Croissance du village x1,1"),
        ),
        Oath(
            "pieux",
            "Les pieux d'abord",
            "On plante les pieux avant de semer : nul ne prendra ce village.",
            ("Palissade 2x plus vite, moitié prix", "Défense du village x1,15"),
        ),
        Oath(
            "feu",
            "Le feu des anciens",
            "Le feu du clan brûle au centre du village : tous les clans y reviennent.",
            (f"Attachement +8 des clans à {NEAR} cases ou moins", "+1 prestige à chaque fin d'hiver"),
        ),
    )
}
OATH_ORDER = ("grenier", "champs", "pieux", "feu")
# Serment de l'IA selon sa culture.
AI_OATH = {"steppe": "pieux", "collines": "pieux", "nord": "pieux", "vallee": "champs", "cote": "champs", "foret": "feu", "desert": "grenier"}


def _bonus(state, tribe_id: int):
    tribe = state.tribes.get(tribe_id)
    return tech.bonuses(tribe) if tribe is not None else tech.NO_BONUS


def _key(col: int, row: int) -> str:
    return f"{col},{row}"


# --- batiments ---------------------------------------------------------------------


# --- effets des batiments et du serment ------------------------------------------------


def stock_weeks(state, band) -> int:
    """Le grenier compte dans la reserve d'une bande installee
    (systems.STOCK_WEEKS)."""
    return store_weeks(state, band) if band.village else 0


def store_weeks(state, band) -> float:
    """Semaines de reserve propres au village (stock_max) : grenier de base,
    savoirs, Grenier sureleve, serment."""
    site = site_of(state, band)
    weeks = STORE_WEEKS + _bonus(state, band.tribe_id).granary + goods.store_weeks(state, band.tribe_id)
    if site is not None:
        if has(site, "grenier"):
            weeks += 8
        if oath_of(site) == "grenier":
            weeks *= 1.25
    return weeks


def rot_mult(state, site) -> float:
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
    since = site.data.season_at
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
    memo = site.data.forage
    if not isinstance(memo, dict):
        memo = site.data.forage = {}
    old = memo.get(key)
    memo[key] = round(take if old is None else old + FORAGE_MEMORY * (take - old), 2)


def food_outlook(state, site, band) -> tuple[int, float]:
    """(semaines avant la recolte, semaines de vivres qui resteront alors)."""
    pop = max(1, band.population)
    memo = site.data.forage
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


# Les troupeaux pres de leurs betes sauvages (0.20, C6) : chevres et
# moutons pres des chevres sauvages, boeufs pres des aurochs : on y renouvelle
# les betes, on y trouve leurs paturages.
WILD_HERD = (("chevres", "chevres", 1.05), ("bovins", "aurochs", 1.05))
# Les champs au bord d'une riviere (0.20, C3) : l'eau et le limon.
RIVER_FIELDS = 1.25
RIVER_IRRIGATION = 1.1


def herd_mult(state, site) -> float:
    if site is None:
        return 1.0
    knows = state.tribes[site.tribe_id].knowledge
    found = goods.riches(state.world, site.hex)
    mult = 1.0
    for tid, res, m in WILD_HERD:
        if tid in knows and found.get(res):
            mult *= m
    return mult


def food_mult(state, band) -> float:
    site = site_of(state, band)
    mult = _bonus(state, band.tribe_id).village_food
    if has(site, "enclos"):
        mult *= 1.1
    if site is not None:
        mult *= herd_mult(state, site)
        mult *= goods.forage_mult(site, band)
        mult *= production.of(state, band.tribe_id, "collecte")
        # Un village assiege ne sort plus de ses murs (siege.py).
        mult = systems.apply_mult(mult, systems.VILLAGE_FOOD, state, site)
    return mult


def winter_famine_mult(state, band) -> float:
    """Sel et etoffes : l'hiver tue moins au village."""
    return goods.winter_famine(state, band.tribe_id) if band.village else 1.0


def yield_mult(state, site) -> float:
    mult = _bonus(state, site.tribe_id).field_yield * goods.yield_mult(state, site.tribe_id)
    mult *= production.of(state, site.tribe_id, "agriculture")
    if oath_of(site) == "champs":
        mult *= 1.1
    return systems.apply_mult(mult, systems.VILLAGE_FOOD, state, site)


def wall_parts(state, band) -> list[tuple[str, float]]:
    """Les murs du village : palissade, tour, pieux du serment, enceintes."""
    site = site_of(state, band)
    if site is None:
        return []
    out = []
    if has(site, "palissade"):
        out.append(("Palissade", batiments.PALISADE_DEFENSE))
    if has(site, "tour"):
        out.append(("Tour de guet", batiments.TOWER_DEFENSE))
    if oath_of(site) == "pieux":
        out.append(("Serment des pieux", 1.15))
    wall = _bonus(state, band.tribe_id).village_defense
    if wall != 1.0:
        out.append(("Enceintes et fossés", wall))
    return out


def defense_parts(state, band, by: int = 0) -> list[tuple[str, float]]:
    """Les murs, et ce que les systemes y changent (le siege : siege.py,
    systems.VILLAGE_DEFENSE) ; by : le peuple qui attaque, s'il est connu."""
    if site_of(state, band) is None:
        return []
    return wall_parts(state, band) + systems.parts(systems.VILLAGE_DEFENSE, state, band, by)


def defense_mult(state, band) -> float:
    mult = 1.0
    for _label, m in defense_parts(state, band):
        mult *= m
    return mult


def winter_prestige(state, tribe_id: int) -> int:
    gain = goods.winter_prestige(state, tribe_id) if goods.has_village(state, tribe_id) else 0
    for site in state.sites.values():
        if site.kind != "village" or site.tribe_id != tribe_id or band_of(state, site) is None:
            continue
        if has(site, "autel"):
            gain += 1
        if has(site, "pierre"):
            gain += 2
        if has(site, "monument"):
            # Seul le monument du vainqueur reste debout.
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
            out.append((f"Près de {name(site)} (autel, feu)", v))
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
# Civilisation au complet : les familles d'un village agite rejoignent un
# village de leur civilisation a UNREST_JOIN_RANGE cases au plus.
UNREST_JOIN_RANGE = 40


def stability_parts(state, site, band=None) -> list[tuple[str, float]]:
    band = band or band_of(state, site)
    if band is None:
        return []
    tribe = state.tribes[band.tribe_id]
    parts: list[tuple[str, float]] = [("Base", STABILITY_BASE)]
    know = _bonus(state, band.tribe_id).stability
    if know:
        parts.append(("Savoirs du néolithique", float(know)))
    for bid, v, label in (
        ("autel", 8.0, "Autel des ancêtres"),
        ("pierre", 10.0, "Pierre levée"),
        ("puits", 4.0, "Puits"),
        ("grenier", 4.0, "Grenier"),
        ("maison_longue", 4.0, "Maison longue"),
    ):
        if has(site, bid):
            parts.append((label, v))
    if oath_of(site) == "feu":
        parts.append(("Serment du feu", 10.0))
    # Ce que chaque systeme fait a la stabilite (systems.STABILITY).
    parts.extend(systems.parts(systems.STABILITY, state, band.tribe_id))
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
        parts.append(("Famine récente", -20.0))
    if site.data.burned:
        parts.append(("Champs brûlés", -10.0))
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
    return "agité"


def stability_growth(state, band) -> float:
    site = site_of(state, band)
    if site is None:
        return 1.0
    return 0.85 + 0.3 * stability(state, site, band) / 100.0


def _unrest(state, site, band) -> None:
    """Village agite : des familles s'en vont former un clan nomade."""
    if band.population < UNREST_MIN_POP:
        return
    value = stability(state, site, band)
    if value >= UNREST or state.story_rng.random() >= (UNREST - value) / 100.0:
        return
    moved = max(10, int(band.population * UNREST_SHARE))
    stock = band.stock * moved / band.population
    civ = civ_of(state, state.tribes[band.tribe_id])
    if civ_band_count(state, civ) >= civ_band_cap(state, civ):
        # La civilisation est au complet : pas de nouvelle tribu. Les familles
        # rejoignent un autre village de leur civilisation, sinon se dispersent.
        homes = [
            other
            for s2 in sorted(state.sites.values(), key=lambda s2: s2.id)
            if s2.kind == "village" and s2.id != site.id
            for other in [band_of(state, s2)]
            if other is not None and civ_of(state, state.tribes[other.tribe_id]) == civ
        ]
        band.population -= moved
        band.stock -= stock
        target = min(homes, key=lambda o: (state.world.distance(o.position, band.position), o.id)) if homes else None
        if target is not None and state.world.distance(target.position, band.position) <= UNREST_JOIN_RANGE:
            target.population += moved
            target.stock = min(stock_max(target, state), target.stock + stock)
            where = name(site_of(state, target))
            for me in sorted({band.tribe_id, target.tribe_id}):
                if state.tribes[me].is_player:
                    _note(state, LogKind.POLITIQUE, f"{name(site)} est agité : {moved} personnes partent vivre à {where}.", site.hex, to=me)
        elif state.tribes[band.tribe_id].is_player:
            _note(state, LogKind.POLITIQUE, f"{name(site)} est agité : {moved} personnes s'en vont et se dispersent.", site.hex, to=band.tribe_id)
        return
    band.population -= moved
    band.stock -= stock
    nid = new_band_id(state)
    clan = Band(nid, band.tribe_id, band.position, moved, stock, famine_in_period=band.famine_in_period)
    state.bands[nid] = clan
    chiefs.on_split(state, band, clan)
    clan.loyalty = min(clan.loyalty, 50.0)
    _ai_caches_changed(state)
    if state.tribes[band.tribe_id].is_player:
        _note(state, LogKind.POLITIQUE, f"{name(site)} est agité : {moved} personnes s'en vont, lasses du désordre.", site.hex, to=band.tribe_id)
    # Elles ne deviennent pas une tribu errante : elles partent fonder leur
    # propre village, sous leur propre chef (un proto-pays de la meme
    # civilisation).
    chiefs.emancipate(state, nid)


# --- fertilite et champs -----------------------------------------------------------


def fertility(state, tribe_id: int, h) -> float:
    world = state.world
    terrain = world.terrain(h)
    base = FERTILITY.get(terrain, 0.0)
    if terrain in (_T.FORET, _T.JUNGLE) and not _bonus(state, tribe_id).clearing:
        return 0.0
    if base <= 0:
        return 0.0
    wild = max(world.resource(h, "cereales"), world.resource(h, "racines")) if world.resources else 0.3
    fert = base * (0.6 + 0.8 * wild)
    idx = world._index(h)
    if idx is not None and world.flow_at(*idx):
        # Au bord de l'eau : le limon et l'eau des crues.
        fert *= RIVER_FIELDS
        if "irrigation" in state.tribes[tribe_id].knowledge:
            fert *= RIVER_IRRIGATION
    return fert


def land_profile(world, h) -> tuple:
    """Terrains et ressources presentes (0,4) des terres d'un village : les
    cases a FIELD_RADIUS ou moins. La carte ne change pas : memorise."""
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
            taken.update(tuple(f) for f in other.data.fields)
    return taken


def choose_fields(state, site, band) -> list:
    """Les meilleures cases autour du village, sol compris."""
    world = state.world
    want = min(MAX_FIELDS, max(1, math.ceil(band.population / FIELD_WORKERS)))
    soil = site.data.soil
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
    hands = population.labor_pop(band) - busy
    if need <= 0 or hands >= need:
        return 1.0
    return max(0.3, hands / need)


def field_hands_mult(site, band, state=None) -> float:
    """Assez de bras aux champs ? Les adultes valides qui ne sont pas aux
    metiers (occupations) ; les hommes partis a la guerre manquent."""
    fields = len(site.data.fields)
    need = fields * FIELD_HANDS * population.ACTIVE_NORM
    if need <= 0:
        return 1.0
    men, women = population.fit_men(band), population.fit_women(band)
    for cid, n in sorted(goods.teams(site).items()):
        if n > 0 and cid in goods.CRAFTS:
            m, w = population._craft_take(cid, goods.TEAM * n, men, women)
            men -= m
            women -= w
    hands = men + women
    return 1.0 if hands >= need else max(0.3, hands / need)


def expected_harvest(state, site, band=None) -> float:
    band = band or band_of(state, site)
    if band is None:
        return 0.0
    soil = site.data.soil
    total = 0.0
    fields = site.data.fields
    for col, row in fields:
        h = offset_to_axial(col, row)
        total += fertility(state, site.tribe_id, h) * soil.get(_key(col, row), 1.0)
    ratio = site.data.sown_ratio
    burned = BURNED if site.data.burned else 1.0
    return total * FIELD_FOOD * ratio * yield_mult(state, site) * burned * field_hands_mult(site, band)


# Semailles : faute de semences gardees, on seme le grain du grenier (en
# gardant SOW_KEEP_WEEKS semaines de vivres) ; sans rien, les graines
# sauvages des terres (cereales, racines) donnent de quoi semer un champ :
# un village qui a mange ses semences n'est pas condamne a la cueillette.
SOW_KEEP_WEEKS = 4


def _wild_seed(state, site) -> float:
    found = goods.riches(state.world, site.hex)
    return SEED if found.get("cereales") or found.get("racines") else 0.0


def sow(state, site, band, late: bool = False) -> None:
    fields = choose_fields(state, site, band)
    need = SEED * len(fields)
    seed = site.data.seed
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
    site.data.seed = seed - sown
    # Ce qui reste des semences retourne au grenier.
    if site.data.seed > 0:
        band.stock = min(stock_max(band, state), band.stock + site.data.seed)
        site.data.seed = 0.0
    site.data.fields = fields if sown > 0 else []
    ratio = (sown / need) if need > 0 else 0.0
    site.data.sown_ratio = ratio * (LATE_SOW if late else 1.0)
    site.data.burned = False
    if state.tribes[band.tribe_id].is_player:
        if sown <= 0:
            _note(state, LogKind.SURVIE, f"{name(site)} : pas de semences, les champs restent vides cette année.", site.hex, to=band.tribe_id)
        else:
            extra = ""
            if from_granary >= 1:
                extra += f" ({from_granary:.0f} vivres du grenier semes"
                extra += ", et des graines sauvages)" if wild else ")"
            elif wild:
                extra = " (des graines sauvages, faute de semences)"
            _note(state, LogKind.SURVIE, f"{name(site)} : semailles sur {len(fields)} champs{extra}.", site.hex, to=band.tribe_id)


def harvest(state, site, band) -> float:
    bonus = _bonus(state, site.tribe_id)
    luck = state.story_rng.uniform(0.8, 1.2)
    crop = expected_harvest(state, site, band) * luck
    short = field_hands_mult(site, band)
    # Le sol des champs s'epuise ; celui des cases au repos se refait.
    soil = site.data.soil
    fields = {tuple(f) for f in site.data.fields}
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
    site.data.seed = site.data.seed + keep
    # La part du chef part au grenier commun (chiefdom.py).
    left = chiefdom.take_from_harvest(state, band, crop - keep)
    band.stock = min(stock_max(band, state), band.stock + left)
    site.data.fields = []
    site.data.sown_ratio = 0.0
    site.data.last_harvest = round(crop)
    history = site.data.history
    history.append([state.clock.year, round(crop)])
    del history[:-HISTORY]
    if state.tribes[band.tribe_id].is_player and crop > 0:
        text = f"{name(site)} : récolte de {crop:.0f} vivres."
        if short < 1.0:
            text += " Il manquait des bras : une part est restee aux champs."
        _note(state, LogKind.SURVIE, text, site.hex, to=band.tribe_id)
    if crop > 0 and luck >= 1.15:
        events.hook(state, "bonne_recolte", tribe_id=band.tribe_id, band_id=band.id)
    return crop


# --- fonder, quitter ----------------------------------------------------------------


def found_block(state, band_id: int) -> str:
    band = state.bands.get(band_id)
    if band is None:
        return "Pas de bande"
    if band.village:
        return ""
    if band.kind == "armee":
        return "Une troupe ne fonde pas de village"
    know = _bonus(state, band.tribe_id)
    if know.villages <= 0:
        return "Il faut connaître Premières semailles"
    if not chiefs.obeys(state, band):
        return "Ce clan n'obéit plus"
    if band.retreating:
        return "La bande est en repli"
    camp = sites.own_site_at(state, band)
    if camp is None or camp.kind != "camp":
        return "Il faut être sur un de vos campements"
    if sites.of_tribe(state, band.tribe_id, "village"):
        # En cet age, un chef ne tient qu'un village : les autres sont ses
        # tributaires, ou des villages freres independants.
        return "Votre peuple a son village : un chef n'en tient qu'un (les autres lui sont tributaires, ou frères)"
    if band.population < MIN_FOUND_POP:
        return f"Il faut {MIN_FOUND_POP} personnes"
    if not any(fertility(state, band.tribe_id, h) > 0.35 for h in state.world.hexes_in_radius(camp.hex, FIELD_RADIUS)):
        return "Aucune terre à cultiver autour"
    return ""


def propose_name(state, band_id: int) -> str:
    """Nom propose dans la fenetre de fondation : stable tant qu'elle est
    ouverte, sans toucher au hasard du recit."""
    band = state.bands[band_id]
    camp = sites.own_site_at(state, band)
    tribe = state.tribes[band.tribe_id]
    rng = random.Random((camp.id if camp else 0) * 7919 + band.tribe_id * 131 + 17)
    taken = [s.name for s in state.sites.values() if s.name]
    culture = culture_of(tribe) if culture_of(tribe).syllables else CULTURES["vallee"]
    return make_name(rng, culture, taken)


def found(state, band_id: int, oath: str = "", name_: str | None = None):
    """La bande s'installe : son campement devient un village."""
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
    band.order = stay_order()
    band.village = camp.id
    band.autonomy = 0.0
    camp.founded = state.clock.year
    # L'etat du village (places.VillageData) : sa bande, son serment ; ce que
    # le campement savait (sa saison) est garde.
    data = camp.data
    data.band = band.id
    data.fields, data.soil, data.seed, data.sown_ratio = [], {}, 0.0, 0.0
    data.buildings, data.build, data.history = [], None, []
    data.oath = oath if oath in OATHS else ""
    # Les reserves du campement et une part du stock deviennent semences.
    band.stock = min(stock_max(band, state), band.stock + camp.store)
    camp.store = 0.0
    need = SEED * min(MAX_FIELDS, max(1, math.ceil(band.population / FIELD_WORKERS)))
    seed = min(need, band.stock * 0.5)
    band.stock -= seed
    camp.data.seed = seed
    season = state.world.hex_season(camp.hex)
    camp.data.season = season.value
    if season in (Season.PRINTEMPS, Season.ETE):
        sow(state, camp, band, late=season is Season.ETE)
    if first:
        # L'age des villages : prestige, les premieres troupes, et les clans
        # restes nomades qui s'eloignent (chiefs.loyalty_parts).
        tribe.flags["age_villages"] = -1
        gain_prestige(state, tribe, FIRST_VILLAGE_PRESTIGE)
    if tribe.settled_at < 0:
        tribe.settled_at = state.tick_count
    if first:
        _chief_takes_the_village(state, tribe, band)
    if tribe.is_player:
        _note(state, LogKind.SURVIE, f"Le village de {camp.name} est fonde.", camp.hex, to=tribe.id)
        if first:
            _note(
                state,
                LogKind.POLITIQUE,
                f"L'âge des villages commence (+{FIRST_VILLAGE_PRESTIGE} prestige) : vos villages levent des troupes, vos clans nomades s'émanciperont.",
                camp.hex,
                to=tribe.id,
            )
    return camp


def seat_chiefs(state) -> None:
    """Chaque peuple qui a un village : son chef gouverne le plus grand."""
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
    heart = chiefs.chief_band(state, tribe.id)
    if heart is None or heart.id == band.id:
        return
    chief, local = heart.leader, band.leader
    band.leader, heart.leader = chief, local
    tribe.chief_band = band.id
    band.loyalty = 100.0
    heart.loyalty = min(heart.loyalty, 70.0)
    if tribe.is_player and chief is not None and not quiet:
        _note(state, LogKind.POLITIQUE, f"{chief.name} s'installe au village et y gouverne ; ses anciens clans ne lui obéiront plus longtemps.", band.position, to=tribe.id)


def ai_oath(state, tribe_id: int) -> str:
    return AI_OATH.get(culture_of(state.tribes[tribe_id]).id, "grenier")


def found_preview(state, band_id: int) -> dict:
    """Ce que la fenetre de fondation montre : le lieu, ses terres, ses
    dangers, le nom propose, et si c'est le premier village du peuple."""
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
        risks.append("Vallée : les crues du printemps peuvent noyer les champs")
    if forest and not _bonus(state, band.tribe_id).clearing:
        risks.append(f"{forest} cases de forêt à défricher (il faut Haches polies)")
    foes = {
        b.tribe_id
        for b in state.bands.values()
        if b.tribe_id != band.tribe_id
        and b.population > 0
        and not guerre.at_peace(state, b.tribe_id, band.tribe_id)
        and world.distance(b.position, center) <= 12
    }
    if foes:
        names = ", ".join(sorted(state.tribes[t].name for t in foes if t in state.tribes))
        risks.append(f"Voisins sans pacte à moins de 12 cases : {names}")
    if band.population >= DISEASE_POP:
        risks.append("Beaucoup de monde : les fièvres guettent les gros villages")
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
    band = state.bands.get(band_id)
    site = site_of(state, band)
    if site is None:
        return False
    band.village = 0
    cap = stock_max(band, state)
    extra = max(0.0, band.stock - cap) + site.data.seed
    band.stock = min(band.stock, cap)
    site.kind = "camp"
    site.store = extra
    site.data = VillageData()
    if state.tribes[band.tribe_id].is_player:
        _note(state, LogKind.SURVIE, f"{name(site)} est abandonné.", site.hex, to=band.tribe_id)
    return True


# --- palissade (le batiment "palissade") ---------------------------------------------------


# --- l'alerte : des etrangers pres du village ------------------------------------------


def _alert(state, site, band) -> None:
    """Tour de guet : on voit venir l'ennemi."""
    if not state.tribes[band.tribe_id].is_player or not has(site, "tour"):
        return
    if state.tick_count - site.data.alert < ALERT_EVERY:
        return
    for foe in state.bands.values():
        if foe.tribe_id == band.tribe_id or foe.population <= 0:
            continue
        if guerre.at_peace(state, foe.tribe_id, band.tribe_id):
            continue
        if state.world.distance(foe.position, site.hex) <= ALERT_RANGE:
            site.data.alert = state.tick_count
            who = state.tribes[foe.tribe_id].name if foe.tribe_id in state.tribes else "étrangers"
            what = "une troupe" if foe.kind == "armee" else f"{foe.population} personnes"
            _note(state, LogKind.COMBAT, f"Tour de guet de {name(site)} : des {who} approchent ({what}) !", foe.position, to=band.tribe_id)
            return


# --- chaque semaine --------------------------------------------------------------------


def update(state) -> None:
    """Saisons locales (semailles, recolte), grain qui se perd, chantiers,
    semences en temps de famine, fievres, crues, troupes, tours de guet."""
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
        last = site.data.season
        if last != season.value:
            site.data.season = season.value
            site.data.season_at = state.tick_count
            if season is Season.PRINTEMPS:
                sow(state, site, band)
                if state.world.terrain(site.hex) is _T.VALLEE and state.story_rng.random() < FLOOD_CHANCE:
                    events.hook(state, "crue", tribe_id=band.tribe_id, band_id=band.id)
            elif season is Season.AUTOMNE:
                harvest(state, site, band)
        if band.stock > 0:
            band.stock *= 1.0 - GRAIN_ROT * rot_mult(state, site)
        batiments.advance_works(state, site, band)
        if band.famine_in_period and site.data.seed > 0 and site.data.asked != state.clock.year:
            site.data.asked = state.clock.year
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
    goods.update(state)
    troupes.update_armies(state)


def eat_seed(state, band) -> float:
    site = site_of(state, band)
    if site is None:
        return 0.0
    seed = site.data.seed
    band.stock = min(stock_max(band, state) + seed, band.stock + seed)
    site.data.seed = 0.0
    return seed


def pillaged(state, band, rng=None) -> str:
    """Village battu : les champs brulent (recolte x0,6), et parfois un
    batiment (jamais la palissade). Rend le nom du batiment perdu."""
    site = site_of(state, band)
    if site is None:
        return ""
    site.data.burned = True
    rng = rng or state.story_rng
    lost = [b for b in built(site) if b != "palissade"]
    if lost and rng.random() < LOSE_BUILDING:
        gone = lost[int(rng.random() * len(lost)) % len(lost)]
        site.data.buildings.remove(gone)
        return batiments.BUILDINGS[gone].name
    return ""


def lost(state, band) -> None:
    """La bande du village a disparu : il n'en reste que des ruines."""
    site = site_of(state, band)
    if site is not None:
        state.sites.pop(site.id, None)
        tribe = state.tribes.get(band.tribe_id)
        if tribe is not None and tribe.is_player:
            _note(state, LogKind.COMBAT, f"{name(site)} n'est plus que ruines.", site.hex, to=tribe.id)


# --- lecture ----------------------------------------------------------------------------


def field_site(state, h):
    """Le village dont cette case est un champ (ou None)."""
    idx = state.world._index(h)
    if idx is None:
        return None
    for site in state.sites.values():
        if site.kind == "village" and list(idx) in site.data.fields:
            return site
    return None


def soil_avg(site) -> float:
    soil = site.data.soil
    fields = site.data.fields
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
        return "Récolte à l'automne", left + 13
    if season is Season.ETE:
        return "Récolte à l'automne", left
    if season is Season.AUTOMNE:
        return "Semailles au printemps", left + 13
    return "Semailles au printemps", left


def lines(state, band) -> list[str]:
    """Lignes de la fiche d'une bande installee."""
    site = site_of(state, band)
    if site is None:
        return []
    fields = site.data.fields
    seed = site.data.seed
    out = [f"Village de {name(site)}  ·  champs {len(fields)}  ·  semences {seed:.0f}  ·  bâtiments {len(built(site))}"]
    season = state.world.hex_season(site.hex)
    crop = expected_harvest(state, site, band)
    if fields:
        out.append(f"Récolte attendue à l'automne : ~{crop:.0f}  ·  sol {100 * soil_avg(site):.0f} %")
    elif season in (Season.ETE, Season.AUTOMNE, Season.HIVER):
        last = site.data.last_harvest
        out.append(f"Dernière récolte : {last}  ·  semailles au printemps" if last is not None else "Semailles au printemps")
    job = works(site)
    if job:
        out.append(f"Chantier : {batiments.BUILDINGS[job[0]].name} (encore {job[1]} sem.)  ·  [V] pour gérer le village")
    elif batiments.palisade_state(site) == "built":
        out.append("Palissade : debout (défense x1,6)  ·  [V] pour gérer le village")
    else:
        out.append("[V] pour gérer le village : bâtiments, troupes")
    return out


def _note(state, kind, text: str, where=None, to: int | None = None) -> None:
    """Au journal du joueur `to` (par defaut le joueur solo)."""
    note(state, kind, text, where, to=PLAYER_TRIBE_ID if to is None else to)


def occupations(state, band) -> dict:
    """Qui fait quoi dans une bande : {"chasse", "cueillette", "champs",
    "metiers" (metier -> gens), "soldats" (partis a la guerre), "valides"}."""
    men, women = fit_men(band), fit_women(band)
    out = {"chasse": 0, "cueillette": 0, "champs": 0, "metiers": {}, "soldats": 0, "valides": men + women}
    if band.kind == "armee":
        out["soldats"] = men
        return out
    if band.village:
        site = site_of(state, band)
        if site is not None:
            for cid, n in sorted(goods.teams(site).items()):
                if n <= 0 or cid not in goods.CRAFTS:
                    continue
                m, w = _craft_take(cid, goods.TEAM * n, men, women)
                men -= m
                women -= w
                out["metiers"][cid] = m + w
            fields = len(site.data.fields)
            need = int(round(fields * FIELD_HANDS * ACTIVE_NORM))
            free = men + women
            take = min(need, free)
            if take > 0 and free > 0:
                m = int(round(take * men / free))
                w = take - m
                men -= m
                women -= w
                out["champs"] = take
            out["soldats"] = sum(troupes.men_away(state, site).values())
    out["chasse"] = men
    out["cueillette"] = women
    return out


def free_for_craft(state, band, cid: str) -> int:
    """Combien de gens du bon sexe pourraient encore entrer a ce metier."""
    men, women = fit_men(band), fit_women(band)
    site = site_of(state, band)
    if site is not None:
        for other, n in sorted(goods.teams(site).items()):
            if n <= 0 or other not in goods.CRAFTS:
                continue
            m, w = _craft_take(other, goods.TEAM * n, men, women)
            men -= m
            women -= w
    sex = CRAFT_SEX.get(cid, "")
    return men if sex == "hommes" else women if sex == "femmes" else men + women


def occupation_lines(state, band) -> list[str]:
    o = occupations(state, band)
    parts = []
    if o["chasse"]:
        parts.append(f"{o['chasse']} à la chasse")
    if o["cueillette"]:
        parts.append(f"{o['cueillette']} à la cueillette")
    if o["champs"]:
        parts.append(f"{o['champs']} aux champs")
    for cid, n in o["metiers"].items():
        parts.append(f"{n} {CRAFT_WORKERS.get(cid, cid)}")
    if o["soldats"] and band.kind != "armee":
        parts.append(f"{o['soldats']} à la guerre")
    return [" · ".join(parts)] if parts else []
