"""LES BATIMENTS D'UN VILLAGE, A PLUSIEURS NIVEAUX (refonte du 2026-10-18,
la demande du joueur : "on peut batir plusieurs fois un meme batiment ; des
batiments peu couteux comme les logements rudimentaires, et des plus
couteux, les plus gros").

Chaque batiment (BUILDINGS) a un NIVEAU (VillageData.buildings : id ->
niveau ; un vieux village a tout au niveau 1, ou ses effets sont ceux
d'avant) et un niveau le plus haut (Building.top). Trois genres de prix
(Building.tier) : peu couteux (des huttes, des fosses), moyens, couteux (la
maison longue, la palissade doublee, la maison du conseil). Un niveau de
plus coute plus cher (LEVEL_COST, LEVEL_WEEKS ; les logements et les fosses
presque pas : CHEAP_LEVEL_COST) ; certains niveaux demandent un savoir de
plus (Building.level_needs : la palissade et son fosse, Enceintes et
fosses).

LE TERRAIN du village (space : BASE_SPACE, puis un de plus par SPACE_POP
habitants ; il ne descend jamais sous ce qui est bati) : chaque niveau en
prend Building.size (la palissade, autour, rien). LES LOGEMENTS
(housing : BASE_HOUSING, plus les huttes, les maisons, la maison longue) :
au-dela, le village s'entasse (villages.py : la croissance ralentit, la
stabilite baisse, les fievres montent) ; une hutte loge 20 personnes et
prend la place que ces 20 personnes donnent : batir des logements, c'est
grandir.

LES CHANTIERS : un a la fois (VillageData.build), paye en vivres du grenier
au moment ou il commence (build_cost ; la paie des batisseurs en sicles
l'accelere : systems.BUILD_SPEED) ; les suivants attendent dans la FILE
(VillageData.queue, QUEUE_MAX), payes quand vient leur tour (start_next,
chaque semaine). On retire un chantier de la file (unqueue), on demolit un
niveau (demolish : la place revient, rien n'est rendu).

Les effets se lisent la ou ils agissent, par level / value (villages.py :
reserves, recoltes, croissance, defense, stabilite ; chiefs.py :
attachement ; vision.py : la tour ; goods.py : ateliers, place d'echange ;
troupes.py : la maison des guerriers). Le GRAND MONUMENT garde ses etapes
(MONUMENT_STAGES, VillageData.monument), pendant les grands travaux
(situations.GrandsTravaux) ; le perdant le voit abattu (pull_down_monument).
Les chantiers avancent chaque semaine (advance_works, appele par
villages.update). L'IA : ai_choice. N'importe pas pygame.
"""

from __future__ import annotations

import math
from dataclasses import dataclass

from src.kora import chiefdom, goods, situations, systems, tech, villages, vision
from src.kora.log import LogKind
from src.kora.places import band_of, has, level, monument_stages, name, NEAR, oath_of, site_of, works


PALISADE_WEEKS = 12
PALISADE_COST_WEEKS = 4

# Le terrain : BASE_SPACE, puis un de plus par SPACE_POP habitants.
BASE_SPACE = 6
SPACE_POP = 15
# Les logements : BASE_HOUSING (les huttes des familles fondatrices).
BASE_HOUSING = 100
# Un niveau de plus : le prix x(1 + LEVEL_COST x niveau), le temps
# x(1 + LEVEL_WEEKS x niveau) ; les batiments peu couteux a la chaine
# (huttes, maisons, fosses) presque pas (CHEAP_LEVEL_COST, et le meme temps).
LEVEL_COST = 0.5
LEVEL_WEEKS = 0.25
CHEAP_LEVEL_COST = 0.05
QUEUE_MAX = 4


@dataclass(frozen=True)
class Building:
    id: str
    name: str
    text: str
    needs: str
    cost_weeks: float
    weeks: int
    icon: str
    size: int
    top: int
    family: str
    # Les savoirs de plus pour les niveaux 2, 3... ("" : rien de plus).
    level_needs: tuple = ()
    # Le nom de chaque niveau, s'il change (la palissade doublee...).
    titles: tuple = ()
    # Un batiment qu'on enchaine (logements, fosses) : presque le meme prix
    # a chaque niveau.
    chain: bool = False

    @property
    def tier(self) -> str:
        """peu couteux, moyen, couteux (l'ecran les distingue)."""
        if self.cost_weeks < 1.5:
            return "peu"
        return "moyen" if self.cost_weeks < 4 else "cher"


BUILDINGS = {
    b.id: b
    for b in (
        # Les logements.
        Building("huttes", "Huttes de branchages", "Des perches, des branches et des peaux : un abri vite monté pour une famille.",
                 "", 0.5, 3, "camp", 1, 30, "logements", chain=True),
        Building("maisons", "Maisons de terre", "Des murs de terre et de clayonnage, un toit de chaume : on y passe l'hiver au chaud.",
                 "maisons", 1.2, 5, "hutte", 1, 20, "logements", chain=True),
        Building("maison_longue", "Maison longue", "Une grande maison de bois pour plusieurs familles.",
                 "maisons", 4, 10, "village", 2, 4, "logements"),
        # Les vivres et les reserves.
        Building("fosses", "Fosses à grain", "Des fosses tapissées d'argile, scellées : le grain s'y garde.",
                 "", 0.8, 3, "cache", 1, 6, "vivres", chain=True),
        Building("sechoir", "Claies de séchage", "Des claies au vent et à la fumée : viande et poisson ne pourrissent plus.",
                 "", 0.6, 3, "herbes", 1, 3, "vivres"),
        Building("grenier", "Grenier surélevé", "Sur pilotis, à l'abri des rats et de l'eau.",
                 "", 3, 8, "grenier", 2, 3, "vivres", level_needs=("greniers", "greniers")),
        Building("enclos", "Enclos", "Des haies d'épineux où l'on garde les bêtes.",
                 "chevres", 3, 6, "troupeau", 1, 3, "vivres"),
        Building("puits", "Puits", "Une eau propre au milieu des maisons.",
                 "", 2, 6, "eau", 1, 2, "vivres"),
        # La defense.
        Building("palissade", "Palissade", "Des pieux plantés en cercle autour des maisons.",
                 "palissade", PALISADE_COST_WEEKS, PALISADE_WEEKS, "palissade", 0, 3, "defense",
                 level_needs=("", "enceintes"), titles=("Palissade", "Double palissade", "Palissade et fossé")),
        Building("tour", "Tour de guet", "Une tour de rondins d'où l'on voit venir.",
                 "guetteurs", 2, 6, "tour", 1, 2, "defense"),
        Building("guerriers", "Maison des guerriers", "Là où les jeunes gens apprennent la guerre.",
                 "palissade", 3, 8, "armee", 2, 2, "defense"),
        # Le peuple et ses morts.
        Building("foyer", "Foyer commun", "Un grand feu au milieu du village, où l'on se retrouve le soir.",
                 "", 0.8, 4, "feu", 1, 2, "peuple"),
        Building("autel", "Autel des ancêtres", "La pierre où l'on parle aux morts du clan.",
                 "rites", 2, 6, "totem", 1, 2, "peuple", level_needs=("ancetres",)),
        Building("pierre", "Pierre levée", "Une pierre dressée que l'on voit de loin.",
                 "megalithes", 6, 16, "menhir", 2, 3, "peuple", titles=("Pierre levée", "Deux pierres levées", "Alignement")),
        Building("conseil", "Maison du conseil", "La grande maison où le chef et les anciens tiennent conseil.",
                 "chefferie", 7, 18, "chef", 3, 1, "peuple"),
        Building("monument", "Grand monument", "Un tertre de pierres dressées, que l'on élève étape après étape pendant les grands travaux.",
                 "", 2, 8, "dolmen", 0, 6, "peuple"),
        # Les metiers et les echanges.
        Building("atelier", "Ateliers", "Des abris où potiers, tisserands et tailleurs travaillent côte à côte.",
                 "poterie", 3, 8, "poterie", 1, 3, "metiers"),
        Building("place", "Place d'échange", "Une place où les porteurs des voisins étalent leurs biens.",
                 "echanges", 3, 8, "balance", 2, 2, "metiers"),
    )
}
BUILD_ORDER = tuple(BUILDINGS)
# Les familles de l'ecran (render_village : la page Les batiments).
FAMILIES = (
    ("logements", "Logements", "hutte"),
    ("vivres", "Vivres et réserves", "grenier"),
    ("defense", "Défense", "palissade"),
    ("peuple", "Le peuple et ses morts", "totem"),
    ("metiers", "Métiers et échanges", "poterie"),
)
TIER_NAMES = {"peu": "Peu coûteux", "moyen": "Moyen", "cher": "Coûteux"}

# CE QUE FAIT CHAQUE NIVEAU : la valeur au niveau 1, 2, 3... (au-dela du
# dernier : la derniere). Le niveau 1 fait ce que faisait le batiment avant
# la refonte (les vieilles parties ne changent pas).
VALUES = {
    "huttes": {"logement": (20,)},
    "maisons": {"logement": (35,)},
    "maison_longue": {"logement": (40,), "croissance": (1.2, 1.25, 1.3, 1.35), "stabilite": (4, 4, 5, 5)},
    "fosses": {"reserve": (3,)},
    "sechoir": {"gate": (0.9, 0.81, 0.73)},
    "grenier": {"reserve": (8, 14, 18), "gate": (0.6, 0.51, 0.43), "stabilite": (4, 5, 6)},
    "enclos": {"vivres": (1.1, 1.15, 1.2)},
    "puits": {"fievres": (0.6, 0.48), "stabilite": (4, 6)},
    "palissade": {"defense": (1.6, 1.9, 2.2)},
    "tour": {"defense": (1.15, 1.25), "vue": vision.TOWER_SIGHTS},
    "guerriers": {"qualite": (1.25, 1.35), "compagnies": (1, 2)},
    "foyer": {"stabilite": (3, 5)},
    "autel": {"attachement": (6, 9), "prestige": (1, 2), "stabilite": (8, 12)},
    "pierre": {"prestige": (2, 4, 6), "influence": (1,), "stabilite": (10, 15, 20)},
    "conseil": {"stabilite": (8,), "attachement": (4,), "prestige": (1,)},
    "atelier": {"metiers": (1.25, 1.35, 1.45)},
    "place": {"convois": (2, 4), "prix": (1.1,)},
}
# Ces valeurs-la s'ajoutent a chaque niveau (une hutte de plus loge 20 de
# plus) ; les autres sont le total du niveau atteint.
PER_LEVEL = {("huttes", "logement"), ("maisons", "logement"), ("maison_longue", "logement"), ("fosses", "reserve")}
# Le grand monument (situations.GrandsTravaux) : ses etapes, chacune plus
# longue et plus chere que la precedente.
MONUMENT_STAGES = 6
# Compatibilite (les effets de la palissade et de la tour au niveau 1).
PALISADE_DEFENSE = VALUES["palissade"]["defense"][0]
TOWER_DEFENSE = VALUES["tour"]["defense"][0]


def value(site, bid: str, key: str, default=0):
    """Ce que fait le batiment `bid` du village pour `key`, a son niveau
    (default s'il n'est pas bati)."""
    n = level(site, bid)
    if n <= 0:
        return default
    row = VALUES.get(bid, {}).get(key)
    if not row:
        return default
    if (bid, key) in PER_LEVEL:
        return row[0] * n
    return row[min(n, len(row)) - 1]


def value_at(bid: str, key: str, n: int, default=0):
    """La meme chose a un niveau donne (l'ecran : ce que fera le suivant)."""
    if n <= 0:
        return default
    row = VALUES.get(bid, {}).get(key)
    if not row:
        return default
    if (bid, key) in PER_LEVEL:
        return row[0] * n
    return row[min(n, len(row)) - 1]


def _num(v) -> str:
    if isinstance(v, float) and v != int(v):
        return f"{v:.2f}".rstrip("0").replace(".", ",")
    return f"{int(v)}"


LINES = {
    "logement": lambda v: f"Loge {_num(v)} personnes",
    "croissance": lambda v: f"Croissance du village x{_num(v)}",
    "stabilite": lambda v: f"Stabilité +{_num(v)}",
    "reserve": lambda v: f"+{_num(v)} semaines de réserve au grenier",
    "gate": lambda v: f"Le grain se gâte x{_num(v)}",
    "vivres": lambda v: f"Vivres du village x{_num(v)}",
    "fievres": lambda v: f"Fièvres du village x{_num(v)}",
    "defense": lambda v: f"Défense du village x{_num(v)}",
    "vue": lambda v: f"Vue +{_num(v)} autour du village, alerte quand un ennemi approche",
    "qualite": lambda v: f"Troupes : force x{_num(v)}, moral +10",
    "compagnies": lambda v: f"{_num(v)} compagnie{'s' if v > 1 else ''} de plus sous les armes",
    "attachement": lambda v: f"Attachement +{_num(v)} des clans à {NEAR} cases ou moins",
    "prestige": lambda v: f"+{_num(v)} prestige à chaque fin d'hiver",
    "influence": lambda v: f"Zone d'influence du village +{_num(v)}",
    "metiers": lambda v: f"Métiers du village : production x{_num(v)}",
    "convois": lambda v: f"+{_num(v)} convois de porteurs (routes commerciales)",
    "prix": lambda v: f"Vos ventes : prix +{round((v - 1) * 100)} %",
}


def effect_lines(bid: str, n: int) -> list[str]:
    """Ce que fait le batiment au niveau n, en mots."""
    if bid == "monument":
        return ["Une étape de plus au monument", "Le plus d'étapes gagne les grands travaux", "Gagné : il reste (+2 prestige par hiver) ; perdu : abattu"]
    return [LINES[key](value_at(bid, key, n)) for key in VALUES.get(bid, {}) if value_at(bid, key, n)]


def title_of(bid: str, n: int) -> str:
    """Le nom du niveau n (la palissade doublee...) ; sinon le nom."""
    b = BUILDINGS[bid]
    if b.titles and n >= 1:
        return b.titles[min(n, len(b.titles)) - 1]
    return b.name


def monument_open(state, site) -> bool:
    """Le peuple de ce village vit les grands travaux, et le village est
    dans leur lieu : il peut elever son monument."""
    return any(
        inst.sid == "travaux" and situations.in_zone(state, inst, site.hex)
        for inst in situations.of_tribe(state, site.tribe_id)
    )


def building_name(site, bid: str, short: bool = False) -> str:
    """Le nom d'un batiment a son niveau ; le monument dit ou il en est
    (short : pour les petites cartes)."""
    if bid == "monument":
        n = monument_stages(site)
        if not n:
            return "Grand monument"
        return f"Monument {n}/{MONUMENT_STAGES}" if short else f"Grand monument · {n}/{MONUMENT_STAGES}"
    return title_of(bid, level(site, bid))


def pull_down_monument(state, site) -> bool:
    """Le monument d'un vaincu est abattu (situations.GrandsTravaux)."""
    if site is None:
        return False
    had = monument_stages(site) > 0
    site.data.monument = 0
    site.data.buildings.pop("monument", None)
    if "monument" in site.data.queue:
        site.data.queue = [b for b in site.data.queue if b != "monument"]
    job = works(site)
    if job and job[0] == "monument":
        site.data.build = None
        had = True
    return had


# --- le terrain, les logements ---------------------------------------------------------


def used_space(site, queued: bool = False) -> int:
    """Le terrain pris : chaque niveau bati, le chantier (et la file, si
    queued : ce qui le prendra)."""
    used = sum(BUILDINGS[b].size * n for b, n in site.data.buildings.items() if b in BUILDINGS and b != "monument")
    job = works(site)
    if job:
        used += BUILDINGS[job[0]].size if job[0] in BUILDINGS else 0
    if queued:
        used += sum(BUILDINGS[b].size for b in site.data.queue if b in BUILDINGS)
    return used


def space(state, site) -> int:
    """Le terrain du village : BASE_SPACE, un de plus par SPACE_POP
    habitants ; jamais moins que ce qui est bati (un village qui perd du
    monde garde ses maisons)."""
    band = band_of(state, site)
    pop = band.population if band is not None else 0
    return max(BASE_SPACE + pop // SPACE_POP, used_space(site))


def housing(site) -> int:
    """Combien le village loge : les familles fondatrices, puis chaque
    hutte, maison, maison longue."""
    return BASE_HOUSING + sum(value(site, b, "logement") for b in ("huttes", "maisons", "maison_longue"))


def crowding(state, site, band=None) -> int:
    """Les gens de trop (0 : chacun a son toit)."""
    band = band or band_of(state, site)
    if band is None:
        return 0
    return max(0, band.population - housing(site))


def house_everyone(state, site, margin: float = 1.1) -> int:
    """Des huttes pour que tout le village ait un toit (avec une marge) :
    a la fondation (les familles montent leurs huttes), et pour les villages
    des parties d'avant la refonte. Rend les huttes ajoutees."""
    band = band_of(state, site)
    if band is None:
        return 0
    need = math.ceil(band.population * margin) - housing(site)
    if need <= 0:
        return 0
    per = VALUES["huttes"]["logement"][0]
    n = -(-need // per)
    site.data.buildings["huttes"] = level(site, "huttes") + n
    return n


def house_old_villages(state) -> int:
    """Une partie d'avant les logements (persist) : chaque village loge ses
    gens. Rend les huttes ajoutees."""
    return sum(house_everyone(state, s) for s in sorted(state.sites.values(), key=lambda s: s.id) if s.kind == "village")


# --- les prix, l'etat, les chantiers -----------------------------------------------------


def _next_level(site, bid: str) -> int:
    """Le niveau qu'aura le prochain chantier de ce batiment (ceux de la
    file comptent)."""
    n = level(site, bid) + sum(1 for b in site.data.queue if b == bid)
    job = works(site)
    if job and job[0] == bid:
        n += 1
    return n + 1


def build_weeks(site, bid: str, n: int | None = None) -> int:
    """Les semaines du chantier qui mene au niveau n (le prochain sinon)."""
    b = BUILDINGS[bid]
    n = n or _next_level(site, bid)
    if bid == "monument":
        return b.weeks + 2 * (n - 1)
    weeks = b.weeks if b.chain else int(round(b.weeks * (1 + LEVEL_WEEKS * (n - 1))))
    if bid == "palissade" and oath_of(site) == "pieux":
        weeks = max(1, weeks // 2)
    return weeks


def build_cost(state, site, bid: str, n: int | None = None) -> float:
    """Les vivres du chantier qui mene au niveau n (le prochain sinon)."""
    b = BUILDINGS[bid]
    n = n or _next_level(site, bid)
    band = band_of(state, site)
    pop = band.population if band is not None else 0
    if bid == "monument":
        cost_weeks = b.cost_weeks + 0.5 * (n - 1)
    else:
        cost_weeks = b.cost_weeks * (1 + (CHEAP_LEVEL_COST if b.chain else LEVEL_COST) * (n - 1))
    cost = cost_weeks * pop * goods.build_mult(state, site.tribe_id)
    if bid == "palissade" and oath_of(site) == "pieux":
        cost *= 0.5
    return float(math.floor(cost))


def needs_for(bid: str, n: int) -> str:
    """Le savoir qu'il faut pour le niveau n ("" : aucun)."""
    b = BUILDINGS[bid]
    if n <= 1 or not b.level_needs:
        return b.needs
    extra = b.level_needs[min(n - 1, len(b.level_needs)) - 1]
    return extra or b.needs


def building_status(state, site, bid: str) -> str:
    """"chantier" (en cours), "file" (en attente dans la file), "possible",
    "attente" (manque vivres, terrain, chantier), "haut" (au plus haut),
    "verrouille" (un savoir, ou le monument hors des grands travaux) ;
    l'ecran dit aussi le niveau (level)."""
    job = works(site)
    if job and job[0] == bid:
        return "chantier"
    if bid == "monument":
        n = monument_stages(site)
        if n >= MONUMENT_STAGES:
            return "haut"
        if not monument_open(state, site):
            return "verrouille"
        return "possible" if not build_block_site(state, site, bid) else "attente"
    b = BUILDINGS[bid]
    n = level(site, bid)
    if n >= b.top:
        return "haut"
    need = needs_for(bid, n + 1)
    if need and need not in state.tribes[site.tribe_id].knowledge:
        return "verrouille" if n == 0 else "attente"
    return "possible" if not build_block_site(state, site, bid) else "attente"


def build_block_site(state, site, bid: str) -> str:
    """Pourquoi on ne peut pas lancer (ou mettre en file) un niveau de plus
    ("" : on peut). Un chantier en cours n'empeche pas : le suivant attend
    dans la file."""
    if bid not in BUILDINGS:
        return "?"
    b = BUILDINGS[bid]
    band = band_of(state, site)
    if band is None:
        return "Le village est vide"
    n = _next_level(site, bid)
    if bid == "monument":
        if n > MONUMENT_STAGES:
            return "Le grand monument est achevé"
        if not monument_open(state, site):
            return "Seulement pendant les grands travaux (une conjoncture)"
    elif n > b.top:
        return f"{b.name} : au plus haut ({b.top} niveau{'x' if b.top > 1 else ''})"
    need = needs_for(bid, n)
    if need and need not in state.tribes[site.tribe_id].knowledge:
        return f"Il faut connaître {tech.TECHS[need].name}"
    if works(site) and len(site.data.queue) >= QUEUE_MAX:
        return f"La file est pleine ({QUEUE_MAX} chantiers attendent)"
    if b.size and used_space(site, queued=True) + b.size > space(state, site):
        more = (used_space(site, queued=True) + b.size - BASE_SPACE) * SPACE_POP - band.population
        return f"Plus de terrain (encore {max(1, more)} habitants)"
    if not works(site):
        cost = build_cost(state, site, bid, n)
        if bid == "monument":
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


def _start(state, site, band, bid: str) -> None:
    n = _next_level(site, bid)
    cost = build_cost(state, site, bid, n)
    if bid == "monument":
        # Le grand monument : le grenier du chef paie d'abord.
        cost -= chiefdom.granary_pay(state, band.tribe_id, cost)
    band.stock -= cost
    site.data.build = [bid, build_weeks(site, bid, n)]
    if state.tribes[band.tribe_id].is_player:
        what = title_of(bid, n) if bid != "monument" else "le grand monument"
        lvl = f", niveau {n}" if n > 1 and bid != "monument" else ""
        villages._note(state, LogKind.SURVIE, f"{name(site)} : chantier de {what.lower()}{lvl} ({build_weeks(site, bid, n)} sem.).", site.hex, to=band.tribe_id)


def build(state, band_id: int, bid: str) -> bool:
    """Un niveau de plus : le chantier commence (paye), ou attend dans la file."""
    if build_block(state, band_id, bid):
        return False
    band = state.bands[band_id]
    site = site_of(state, band)
    if works(site):
        site.data.queue.append(bid)
        return True
    _start(state, site, band, bid)
    return True


def unqueue(state, site, index: int) -> bool:
    """Retirer un chantier de la file (rien n'etait paye)."""
    if not 0 <= index < len(site.data.queue):
        return False
    site.data.queue.pop(index)
    return True


def demolish_block(state, site, bid: str) -> str:
    if bid not in BUILDINGS or bid == "monument":
        return "On n'abat pas le grand monument"
    if level(site, bid) <= 0:
        return "Rien à démolir"
    job = works(site)
    if job and job[0] == bid:
        return "Un chantier est en cours sur ce bâtiment"
    if bid in ("huttes", "maisons", "maison_longue"):
        band = band_of(state, site)
        if band is not None and band.population > housing(site) - value_at(bid, "logement", 1):
            return "Ses habitants n'auraient plus de toit"
    return ""


def demolish(state, site, bid: str) -> bool:
    """Abattre un niveau : le terrain revient, rien n'est rendu."""
    if demolish_block(state, site, bid):
        return False
    n = level(site, bid) - 1
    if n > 0:
        site.data.buildings[bid] = n
    else:
        site.data.buildings.pop(bid, None)
    return True


def lose_level(site, bid: str) -> None:
    """Un niveau perdu (un pillage : villages.pillaged)."""
    n = level(site, bid) - 1
    if n > 0:
        site.data.buildings[bid] = n
    else:
        site.data.buildings.pop(bid, None)


def start_next(state, site, band) -> None:
    """Pas de chantier : le premier de la file qui le peut commence (il
    paie maintenant) ; les autres attendent leur tour."""
    if works(site) or not site.data.queue:
        return
    for i, bid in enumerate(list(site.data.queue)):
        site.data.queue.pop(i)
        if not build_block_site(state, site, bid):
            _start(state, site, band, bid)
            return
        site.data.queue.insert(i, bid)


def queue_block(state, site, index: int) -> str:
    """Ce qu'attend le chantier n de la file (l'ecran le dit)."""
    if not 0 <= index < len(site.data.queue):
        return ""
    if works(site):
        return "Attend la fin du chantier en cours"
    bid = site.data.queue[index]
    site.data.queue.pop(index)
    why = build_block_site(state, site, bid)
    site.data.queue.insert(index, bid)
    return why


def advance_works(state, site, band) -> None:
    job = works(site)
    if not job:
        start_next(state, site, band)
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
        if state.tribes[band.tribe_id].is_player:
            villages._note(state, LogKind.SURVIE, f"{name(site)} : le grand monument s'élève (étape {n} sur {MONUMENT_STAGES}).", site.hex, to=band.tribe_id)
        start_next(state, site, band)
        return
    n = level(site, bid) + 1
    site.data.buildings[bid] = n
    if state.tribes[band.tribe_id].is_player:
        if bid == "palissade" and n == 1:
            text = f"{name(site)} : la palissade est debout."
        elif n == 1:
            text = f"{name(site)} : {BUILDINGS[bid].name.lower()} achevé{'es' if BUILDINGS[bid].name.endswith('s') else ''}."
        else:
            text = f"{name(site)} : {title_of(bid, n).lower()}, niveau {n}."
        villages._note(state, LogKind.SURVIE, text, site.hex, to=band.tribe_id)
    start_next(state, site, band)


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


# --- l'IA -----------------------------------------------------------------------------------
# Un village de l'IA batit d'abord ce qui le loge (entasse a AI_HOUSE_AT de
# ses logements), puis dans l'ordre d'AI_PLAN (le batiment, le niveau vise) :
# les premiers niveaux dans l'ordre d'avant la refonte, puis les suivants.
AI_HOUSE_AT = 0.9
AI_PLAN = (
    ("palissade", 1), ("grenier", 1), ("puits", 1), ("guerriers", 1), ("tour", 1), ("autel", 1),
    ("maison_longue", 1), ("enclos", 1), ("atelier", 1), ("place", 1), ("pierre", 1),
    ("fosses", 2), ("foyer", 1), ("sechoir", 1), ("conseil", 1), ("palissade", 2), ("grenier", 2),
    ("tour", 2), ("enclos", 2), ("atelier", 2), ("autel", 2), ("guerriers", 2), ("pierre", 2),
    ("puits", 2), ("fosses", 4), ("palissade", 3), ("grenier", 3), ("place", 2), ("foyer", 2),
)


def ai_choice(state, site, band) -> list[str]:
    """Ce que l'IA voudrait batir maintenant, dans l'ordre (le premier
    possible l'emporte)."""
    out = []
    if monument_open(state, site):
        out.append("monument")
    if band.population >= AI_HOUSE_AT * housing(site):
        known = state.tribes[band.tribe_id].knowledge
        out += ["maisons", "huttes"] if "maisons" in known else ["huttes"]
    for bid, target in AI_PLAN:
        if level(site, bid) < target:
            out.append(bid)
    return out
