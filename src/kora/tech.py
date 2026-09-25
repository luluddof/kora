"""Savoirs : l'arbre, les conditions, l'apprentissage, les effets.

Un savoir ne s'achete pas avec des points de recherche : il devient
DISPONIBLE quand la tribu connait ses prerequis et a vecu ce qu'il faut
(semaines passees en foret, hivers traverses, taille du peuple...). Il
faut ensuite l'APPRENDRE : un savoir a la fois, pendant des semaines, et
plus le peuple est nombreux, plus ca va vite. L'IA suit les memes regles.
Un savoir connu d'un voisin s'apprend plus vite (diffusion, diplo.py).

Les effets sont des donnees (Tech.effects) ; le texte affiche au joueur
en est tire (effect_lines) : ce qui est ecrit est ce qui est simule.
Au depart, tout le monde connait le feu et les outils de pierre.
Un seul arbre : l'age tribal (paliers 0 a 3) puis le neolithique (4 et 5).
"""

from __future__ import annotations

from dataclasses import dataclass, field

from src.kora.log import LogKind
from src.kora.peoples import culture_of
from src.kora.types import Season, Terrain
from src.kora.world import MOVE_COST

BASE_STOCK_WEEKS = 10
BASE_MAX_BANDS = 8
# Le monde est grand et l'on y voit peu : 8 cases autour de ses bandes.
BASE_VISION = 8
BASE_REINFORCE = 2
BASE_WINTER_PRESTIGE = 4
BASE_FAMINE_PRESTIGE = -6
BASE_MOVE_COST = MOVE_COST
# Emprise du chef : distance (cases) jusqu'a laquelle ses clans restent
# attaches sans effort (voir chiefs.py).
BASE_CHIEF_REACH = 12
# Rayon de la zone d'influence autour d'une bande (voir influence.py).
BASE_INFLUENCE_RADIUS = 2
# Apprentissage : points par semaine = 1 + peuple / LEARN_POP.
LEARN_POP = 120
# Une partie longue : chaque palier demande deux fois plus qu'au debut du proto.
TIER_COST = {0: 0, 1: 40, 2: 90, 3: 160, 4: 240, 5: 360}
TIER_NAMES = {
    0: "Connu",
    1: "Premiers savoirs",
    2: "Savoirs du clan",
    3: "Aube du neolithique",
    4: "Premiers villages",
    5: "Villages prosperes",
}
BRANCHES = (
    "Chasse et guerre",
    "Terre et cueillette",
    "Reserves",
    "Eau",
    "Froid et voyage",
    "Pays et campements",
    "Foyer et societe",
    "Voisins",
)
# Un seul arbre, vertical : une colonne par branche. Au neolithique, chaque
# colonne prend un nouveau nom, dans le prolongement de la branche tribale
# (Reserves -> Greniers, Pays et campements -> Villages...).
NEO_BRANCHES = (
    "Guerre et defense",
    "Champs",
    "Greniers et artisans",
    "",
    "Troupeaux",
    "Villages",
    "Esprits et pouvoir",
    "Echanges",
)
# (nom de l'age, paliers, noms des colonnes)
ERAS = (
    ("Age tribal", (0, 1, 2, 3), BRANCHES),
    ("Neolithique", (4, 5), NEO_BRANCHES),
)
START_KNOWLEDGE = ("feu", "outils")
# Conditions de la pirogue et du troupeau (reprises des anciennes decisions).
PIROGUE_POP = 50
PIROGUE_COAST_WEEKS = 4
TROUPEAU_POP = 10
TROUPEAU_STEPPE_WEEKS = 4
SEE_RADIUS = 16

_T = Terrain
_TERRAIN_FR = {
    _T.PLAINE: "plaine",
    _T.VALLEE: "vallee",
    _T.STEPPE: "steppe",
    _T.FORET: "foret",
    _T.COLLINE: "colline",
    _T.MONTAGNE: "montagne",
    _T.COTE: "cote",
    _T.DESERT: "desert",
}


@dataclass(frozen=True)
class Cond:
    """Une condition pour rendre un savoir disponible.

    kind : "pop", "weeks" (terrains), "res" (ressources, dans terrains),
    "winters", "prestige", "bands", "seen", "flag" (label = drapeau d'un
    evenement), "camp_years", "contacts", "friends", "allies",
    "villages", "village_years"."""

    kind: str
    need: int = 0
    terrains: tuple = ()
    label: str = ""


@dataclass(frozen=True)
class Tech:
    id: str
    name: str
    tier: int
    branch: int
    about: str
    prereqs: tuple = ()
    conds: tuple = ()
    effects: dict = field(default_factory=dict)

    @property
    def cost(self) -> int:
        return TIER_COST[self.tier]


def _weeks(need: int, *terrains, label: str) -> Cond:
    return Cond("weeks", need, tuple(terrains), label)


def era_of(tech: Tech) -> int:
    return 0 if tech.tier <= 3 else 1


def branches_of(tech: Tech) -> tuple:
    return ERAS[era_of(tech)][2]


TECHS: dict[str, Tech] = {
    t.id: t
    for t in (
        # --- palier 0 : connu ---------------------------------------------
        Tech(
            "feu", "Feu", 0, 6,
            "Chaleur, cuisson, lumiere. Sans lui, aucun hiver n'est possible.",
            effects={"base": True},
        ),
        Tech(
            "outils", "Outils de pierre", 0, 1,
            "Bifaces, racloirs, pieux : la cueillette et la chasse de base.",
            effects={"base": True},
        ),
        # --- palier 1 : premiers savoirs -----------------------------------
        Tech(
            "epieu", "Chasse a l'epieu", 1, 0,
            "Des pieux durcis au feu et des chasseurs qui rabattent ensemble le gros gibier.",
            prereqs=("outils",),
            conds=(Cond("pop", 30), _weeks(6, _T.PLAINE, _T.STEPPE, label="plaine ou steppe")),
            effects={"combat": 1.10, "food": {_T.PLAINE: 1.10, _T.STEPPE: 1.10}},
        ),
        Tech(
            "cueillette", "Cueillette savante", 1, 1,
            "Savoir quelles baies, racines et noix se mangent, et ou les trouver selon la saison.",
            prereqs=("outils",),
            conds=(_weeks(8, _T.FORET, _T.VALLEE, label="foret ou vallee"),),
            effects={"food": {_T.FORET: 1.12, _T.VALLEE: 1.06}},
        ),
        Tech(
            "fumage", "Fumage et sechage", 1, 2,
            "La viande et le poisson fumes se gardent des mois : on prepare l'hiver, on cache des vivres.",
            prereqs=("feu",),
            conds=(Cond("winters", 1),),
            effects={"stock_weeks": 4, "caches": 3, "cache_cap": 300},
        ),
        Tech(
            "peche", "Peche au harpon", 1, 3,
            "Harpons d'os et pieges a poissons au bord de l'eau.",
            prereqs=("outils",),
            conds=(Cond("seen", label="rivage"), _weeks(4, _T.COTE, _T.VALLEE, label="cote ou vallee")),
            effects={"water_food": 0.25, "food": {_T.COTE: 1.08}},
        ),
        Tech(
            "peaux", "Vetements de peau", 1, 4,
            "Aiguilles d'os et peaux cousues : on survit au froid.",
            prereqs=("feu", "outils"),
            conds=(Cond("weeks", 10, ("hiver",), "hiver local"),),
            effects={"winter_famine": 0.7, "winter_hills": 1.5},
        ),
        Tech(
            "huttes", "Huttes et campements", 1, 5,
            "Des huttes de branches et de peaux qu'on retrouve chaque saison : un lieu a soi.",
            prereqs=("feu",),
            conds=(Cond("winters", 1), Cond("pop", 30)),
            effects={"camps": 2, "camp_shelter": 0.6},
        ),
        Tech(
            "rites", "Rites et sepultures", 1, 6,
            "Ocre, parures, morts enterres avec leurs outils : les clans partagent les memes ancetres.",
            prereqs=("feu",),
            conds=(Cond("winters", 2), Cond("pop", 40)),
            effects={"loyalty": 6, "chief_reach": 3},
        ),
        Tech(
            "palabres", "Dons et palabres", 1, 7,
            "Echanger des presents, s'asseoir autour du meme feu : on parle avant de se battre.",
            prereqs=("feu",),
            conds=(Cond("contacts", 1),),
            effects={"gifts": 1.5, "diplo": 10},
        ),
        # --- palier 2 : savoirs du clan ------------------------------------
        Tech(
            "arc", "Arc et fleches", 2, 0,
            "Tuer de loin : le petit gibier des forets, et l'ennemi avant qu'il n'approche.",
            prereqs=("epieu",),
            conds=(Cond("pop", 80), _weeks(12, _T.FORET, label="foret")),
            effects={"combat": 1.15, "food": {_T.FORET: 1.06}},
        ),
        Tech(
            "troupeau", "Troupeau", 2, 1,
            "Suivre et garder un troupeau plutot que le chasser : la steppe devient un garde-manger.",
            prereqs=("epieu",),
            conds=(
                Cond("seen", label="steppe"),
                _weeks(TROUPEAU_STEPPE_WEEKS, _T.STEPPE, label="steppe"),
                Cond("pop", TROUPEAU_POP),
            ),
            effects={"herd": True},
        ),
        Tech(
            "salaison", "Salaison", 2, 2,
            "Le sel garde la viande et le poisson : des reserves plus grandes, des caches qui durent.",
            prereqs=("fumage",),
            conds=(Cond("res", 10, ("sel",), "pres du sel"), Cond("winters", 2)),
            effects={"stock_weeks": 3, "cache_cap": 200, "cache_decay": 0.5},
        ),
        Tech(
            "pirogue", "Pirogue", 2, 3,
            "Un tronc creuse au feu : on longe les rives, on traverse les lacs et les detroits.",
            prereqs=("peche",),
            conds=(
                Cond("seen", label="rivage"),
                _weeks(PIROGUE_COAST_WEEKS, _T.COTE, label="cote"),
                Cond("pop", PIROGUE_POP),
            ),
            effects={"cabotage": True},
        ),
        Tech(
            "portage", "Raquettes et portage", 2, 4,
            "Raquettes, traineaux, sentiers battus : la foret et les collines ralentissent moins.",
            prereqs=("peaux",),
            conds=(_weeks(14, _T.FORET, _T.COLLINE, label="foret ou collines"),),
            effects={"move": {_T.FORET: 15, _T.COLLINE: 12, _T.MONTAGNE: 45}},
        ),
        Tech(
            "reperes", "Pistes et reperes", 2, 5,
            "Chaque source, chaque gue, chaque passage des betes a un nom : on connait son pays.",
            prereqs=("huttes",),
            conds=(Cond("bands", 2), Cond("winters", 3)),
            effects={"influence_radius": 1, "home_food": 1.08, "chief_reach": 4},
        ),
        Tech(
            "conte", "Recits autour du feu", 2, 6,
            "Les anciens racontent les hivers passes : la tribu se souvient et se tient.",
            prereqs=("feu",),
            conds=(Cond("winters", 3), Cond("pop", 70)),
            effects={"winter_prestige": 2, "famine_prestige": 2, "growth": 1.05, "chief_reach": 3},
        ),
        Tech(
            "mariages", "Mariages entre clans", 2, 7,
            "On donne ses filles et ses fils aux voisins : les alliances se scellent par le sang.",
            prereqs=("palabres",),
            conds=(Cond("pop", 80), Cond("friends", 1)),
            effects={"alliance": True, "loyalty": 4},
        ),
        # --- palier 3 : aube du neolithique --------------------------------
        Tech(
            "guetteurs", "Guetteurs et signaux", 3, 0,
            "Des veilleurs sur les hauteurs et des signaux de fumee : on voit venir, on s'entraide.",
            prereqs=("arc", "conte"),
            conds=(Cond("bands", 4), Cond("pop", 160)),
            effects={"vision": 4, "reinforce": 1, "home_defense": 1.15},
        ),
        Tech(
            "semis", "Premieres semailles", 3, 1,
            "Replanter les graines des meilleures plantes pres du camp : le debut des champs.",
            prereqs=("cueillette", "fumage"),
            conds=(
                Cond("pop", 160),
                Cond("winters", 5),
                Cond("res", 20, ("cereales", "racines"), "pres de cereales ou de racines sauvages"),
            ),
            effects={"food": {_T.VALLEE: 1.2, _T.PLAINE: 1.1}, "recovery": 0.1, "villages": 1},
        ),
        Tech(
            "poterie", "Poterie", 3, 2,
            "Des pots d'argile cuite : grain et graisse a l'abri de l'humidite et des rongeurs.",
            prereqs=("fumage",),
            conds=(Cond("pop", 180), Cond("winters", 6), Cond("res", 8, ("argile",), "pres de l'argile")),
            effects={
                "stock_weeks": 6,
                "winter_famine": 0.85,
                "caches": 2,
                "cache_cap": 300,
                "cache_decay": 0.5,
            },
        ),
        Tech(
            "filets", "Filets et nasses", 3, 3,
            "Filets tresses et nasses en osier : la mer et les lacs nourrissent vraiment.",
            prereqs=("pirogue",),
            conds=(Cond("pop", 140), _weeks(30, _T.COTE, label="cote")),
            effects={"water_food": 0.15, "food": {_T.COTE: 1.08}},
        ),
        Tech(
            "chiens", "Chiens de chasse", 3, 4,
            "Les louveteaux d'autrefois sont devenus des chiens : ils rabattent le gibier et veillent la nuit.",
            prereqs=("epieu",),
            conds=(Cond("flag", 1, label="louveteaux"),),
            effects={"food": {_T.FORET: 1.06, _T.PLAINE: 1.06, _T.STEPPE: 1.06}, "vision": 2},
        ),
        Tech(
            "campement", "Grand campement", 3, 5,
            "Un camp tenu d'annee en annee, avec ses reserves et ses tombes : le coeur du pays.",
            prereqs=("reperes",),
            conds=(Cond("camp_years", 3), Cond("pop", 150)),
            effects={"camps": 1, "influence_radius": 1, "camp_growth": 1.10},
        ),
        Tech(
            "chefferie", "Chefferie", 3, 6,
            "Un chef reconnu par plusieurs clans : la tribu peut s'etendre sans se defaire.",
            prereqs=("conte",),
            conds=(Cond("pop", 250), Cond("prestige", 50), Cond("winters", 8)),
            effects={"max_bands": 4, "growth": 1.05, "loyalty": 8, "chief_reach": 8, "camps": 1},
        ),
        Tech(
            "confederation", "Confederation", 3, 7,
            "Plusieurs peuples sous les memes serments : les petits se joignent aux grands.",
            prereqs=("mariages",),
            conds=(Cond("allies", 1), Cond("prestige", 40)),
            effects={"union": True, "diffusion": 0.15},
        ),
        # --- neolithique, palier 4 : premiers villages ---------------------
        Tech(
            "palissade", "Palissades", 4, 0,
            "Des pieux plantes en cercle autour des maisons : le village ne fuit pas, il se defend.",
            prereqs=("semis",),
            conds=(Cond("villages", 1),),
            effects={"palisade": True},
        ),
        Tech(
            "champs", "Champs cultives", 4, 1,
            "On choisit les meilleures graines, on desherbe, on garde les oiseaux : les champs rendent enfin.",
            prereqs=("semis",),
            conds=(Cond("village_years", 2), Cond("res", 20, ("cereales", "racines"), "pres de cereales ou de racines")),
            effects={"field_yield": 1.4},
        ),
        Tech(
            "chevres", "Chevres et moutons", 4, 4,
            "Des betes qui suivent le berger : du lait, de la laine, de la viande sur pied.",
            prereqs=("epieu",),
            conds=(Cond("res", 20, ("chevres",), "pres des chevres sauvages"), Cond("pop", 120)),
            effects={
                "food": {_T.COLLINE: 1.2, _T.MONTAGNE: 1.2, _T.PLAINE: 1.05},
                "village_food": 1.1,
                "winter_famine": 0.9,
            },
        ),
        Tech(
            "greniers", "Greniers", 4, 2,
            "Des greniers sureleves, a l'abri des rats et de l'eau : le grain dure.",
            prereqs=("poterie",),
            conds=(Cond("villages", 1), Cond("winters", 8)),
            effects={"granary": 8, "grain_rot": 0.5},
        ),
        Tech(
            "maisons", "Maisons de terre", 4, 5,
            "Des murs de terre et de bois, des toits de chaume : on vit mieux, on tombe moins malade.",
            prereqs=("campement",),
            conds=(Cond("village_years", 3),),
            effects={"villages": 1, "disease": 0.6, "village_growth": 1.1},
        ),
        Tech(
            "ancetres", "Culte des ancetres", 4, 6,
            "Les morts reposent sous les maisons : le village appartient a ceux qui y sont nes.",
            prereqs=("rites",),
            conds=(Cond("villages", 1), Cond("winters", 10)),
            effects={"stability": 10, "winter_prestige": 2},
        ),
        Tech(
            "echanges", "Echanges lointains", 4, 7,
            "Du silex contre du sel, des perles contre des peaux : les biens voyagent de main en main.",
            prereqs=("palabres",),
            conds=(Cond("contacts", 3), Cond("pop", 150)),
            effects={"diffusion": 0.1, "gifts": 1.25, "diplo": 5, "commerce": True},
        ),
        # --- neolithique, palier 5 : villages prosperes -----------------------
        Tech(
            "haches", "Haches polies", 5, 0,
            "La pierre polie abat les arbres et les ennemis : la foret recule devant les champs.",
            prereqs=("palissade",),
            conds=(Cond("res", 20, ("silex",), "pres du silex"), Cond("pop", 200)),
            effects={"combat": 1.1, "clearing": True},
        ),
        Tech(
            "jachere", "Jachere", 5, 1,
            "Laisser reposer la terre une annee sur trois : le sol ne s'epuise plus.",
            prereqs=("champs",),
            conds=(Cond("village_years", 5),),
            effects={"soil_loss": 0.5, "field_yield": 1.2},
        ),
        Tech(
            "bovins", "Boeufs et vaches", 5, 4,
            "L'aurochs dompte : de la viande, du lait, et le fumier qui engraisse les champs.",
            prereqs=("chevres",),
            conds=(Cond("res", 30, ("aurochs",), "pres des aurochs"), Cond("pop", 200)),
            effects={
                "food": {_T.PLAINE: 1.12, _T.VALLEE: 1.08},
                "village_food": 1.15,
                "winter_famine": 0.9,
                "field_yield": 1.15,
            },
        ),
        Tech(
            "tissage", "Tissage", 5, 2,
            "Le lin et la laine tisses : des vetements chauds, et des etoffes qu'on echange.",
            prereqs=("poterie",),
            conds=(Cond("villages", 1), Cond("pop", 200)),
            effects={"winter_famine": 0.8, "winter_prestige": 1},
        ),
        Tech(
            "freres", "Villages freres", 5, 5,
            "Des villages nes du meme village : un meme sang, un meme chef.",
            prereqs=("maisons",),
            conds=(Cond("villages", 2),),
            effects={"villages": 2, "stability": 10},
        ),
        Tech(
            "megalithes", "Pierres levees", 5, 6,
            "Des pierres dressees que tous les clans ont tirees ensemble : on les voit de loin.",
            prereqs=("ancetres",),
            conds=(Cond("prestige", 60), Cond("pop", 300)),
            effects={"winter_prestige": 3, "stability": 15, "influence_radius": 1},
        ),
        Tech(
            "routes", "Routes du sel et du silex", 5, 7,
            "Des sentiers de peuple en peuple, jalonnes de haltes : on se connait, on commerce.",
            prereqs=("echanges",),
            conds=(Cond("allies", 1), Cond("contacts", 4)),
            effects={"diffusion": 0.15, "trade": True},
        ),
    )
}

# Specialites de depart et gout de l'IA : voir peoples.CULTURES.


# --- effets ----------------------------------------------------------------


@dataclass(frozen=True)
class Bonuses:
    """Somme des effets des savoirs connus d'une tribu."""

    food: dict
    water_food: float = 0.0
    winter_hills: float = 1.0
    combat: float = 1.0
    winter_famine: float = 1.0
    stock_weeks: int = BASE_STOCK_WEEKS
    move: dict = field(default_factory=dict)
    vision: int = BASE_VISION
    reinforce: int = BASE_REINFORCE
    recovery: float = 0.0
    growth: float = 1.0
    max_bands: int = BASE_MAX_BANDS
    winter_prestige: int = BASE_WINTER_PRESTIGE
    famine_prestige: int = BASE_FAMINE_PRESTIGE
    # Campements et caches (sites.py).
    camps: int = 0
    camp_shelter: float = 1.0
    camp_growth: float = 1.0
    caches: int = 0
    cache_cap: int = 0
    cache_decay: float = 1.0
    # Zone d'influence (influence.py) et chefs (chiefs.py).
    influence_radius: int = BASE_INFLUENCE_RADIUS
    home_food: float = 1.0
    home_defense: float = 1.0
    loyalty: int = 0
    chief_reach: int = BASE_CHIEF_REACH
    # Neolithique : la stabilite des villages (villages.stability), pas
    # l'attachement des clans nomades.
    stability: int = 0
    # Diplomatie (diplo.py).
    gifts: float = 1.0
    diplo: int = 0
    alliance: bool = False
    union: bool = False
    diffusion: float = 0.0
    # Villages (villages.py).
    villages: int = 0
    field_yield: float = 1.0
    soil_loss: float = 1.0
    granary: int = 0
    grain_rot: float = 1.0
    disease: float = 1.0
    village_growth: float = 1.0
    village_food: float = 1.0
    palisade: bool = False
    clearing: bool = False
    trade: bool = False
    # Accords commerciaux (diplo, goods.py).
    commerce: bool = False


_MULT = {
    "field_yield",
    "soil_loss",
    "grain_rot",
    "disease",
    "village_growth",
    "village_food",
    "combat",
    "winter_famine",
    "growth",
    "winter_hills",
    "camp_shelter",
    "camp_growth",
    "cache_decay",
    "home_food",
    "home_defense",
    "gifts",
}
_FLAGS = {"alliance", "union", "palisade", "clearing", "trade", "commerce"}
_CACHE: dict[frozenset, Bonuses] = {}
NO_BONUS = Bonuses(food={})


def bonuses_of(known) -> Bonuses:
    key = frozenset(known)
    hit = _CACHE.get(key)
    if hit is not None:
        return hit
    food: dict = {}
    move = dict(BASE_MOVE_COST)
    acc = {
        name: getattr(NO_BONUS, name)
        for name in Bonuses.__dataclass_fields__
        if name not in ("food", "move")
    }
    for tid in sorted(key):
        tech = TECHS.get(tid)
        if tech is None:
            continue
        for name, value in tech.effects.items():
            if name == "food":
                for terrain, mult in value.items():
                    food[terrain] = food.get(terrain, 1.0) * mult
            elif name == "move":
                for terrain, cost in value.items():
                    move[terrain] = min(move[terrain], cost)
            elif name in _MULT:
                acc[name] *= value
            elif name in _FLAGS:
                acc[name] = acc[name] or bool(value)
            elif name in acc:
                acc[name] += value
    bonus = Bonuses(food=food, move=move, **acc)
    _CACHE[key] = bonus
    return bonus


# Pendant un tick, les savoirs ne changent qu'a des moments connus : on
# garde les bonus de chaque tribu au lieu de refaire le calcul a chaque
# appel (c'etait l'un des postes les plus chers du tick).
_TICK_MEMO: dict | None = None


def begin_tick() -> None:
    global _TICK_MEMO
    _TICK_MEMO = {}


def invalidate() -> None:
    if _TICK_MEMO is not None:
        _TICK_MEMO.clear()


def end_tick() -> None:
    global _TICK_MEMO
    _TICK_MEMO = None


def bonuses(tribe) -> Bonuses:
    memo = _TICK_MEMO
    if memo is not None:
        hit = memo.get(id(tribe))
        if hit is not None and hit[0] is tribe:
            return hit[1]
    known = getattr(tribe, "knowledge", None)
    bonus = bonuses_of(known) if known else NO_BONUS
    if memo is not None:
        memo[id(tribe)] = (tribe, bonus)
    return bonus


def move_costs(tribe) -> dict:
    b = bonuses(tribe)
    return b.move if b.move else BASE_MOVE_COST


# --- texte des effets (tire des donnees) --------------------------------------


def _num(x: float) -> str:
    text = f"{x:.1f}".rstrip("0").rstrip(".")
    return text.replace(".", ",")


def _pct(mult: float) -> str:
    delta = round((mult - 1.0) * 100)
    return f"+{delta} %" if delta >= 0 else f"{delta} %"


def _terrain_list(terrains) -> str:
    names = [_TERRAIN_FR.get(t, t.value) for t in terrains]
    if len(names) == 1:
        return names[0].capitalize()
    return (", ".join(names[:-1]) + " et " + names[-1]).capitalize()


def _slower(mult: float) -> str:
    if mult <= 0:
        return "ne se gatent plus"
    times = 1.0 / mult
    return f"se gatent {_num(times)} fois moins vite"


def effect_lines(tech: Tech) -> list[str]:
    e = tech.effects
    out: list[str] = []
    if e.get("base"):
        out.append("Deja pris en compte dans le jeu de base.")
    groups: dict[float, list] = {}
    for terrain, mult in e.get("food", {}).items():
        groups.setdefault(mult, []).append(terrain)
    for mult, terrains in groups.items():
        out.append(f"{_terrain_list(terrains)} : {_pct(mult)} de nourriture")
    if e.get("water_food"):
        per = 2.0 * e["water_food"]
        out.append(f"Eau pres des rives (mer, lacs) : +{_num(per)} nourriture par case (printemps)")
    if e.get("winter_hills"):
        out.append(f"Collines et montagnes en hiver : nourriture x{_num(e['winter_hills'])}")
    if e.get("combat"):
        out.append(f"Force au combat : {_pct(e['combat'])}")
    if e.get("home_defense"):
        out.append(f"Defense dans votre zone d'influence : {_pct(e['home_defense'])}")
    if e.get("winter_famine"):
        out.append(f"Famine pendant l'hiver local : {_pct(e['winter_famine'])} de morts")
    if e.get("stock_weeks"):
        out.append(f"Reserves : +{e['stock_weeks']} semaines de stock par personne")
    if e.get("caches"):
        if e["caches"] >= 3:
            out.append(f"Caches de vivres : jusqu'a {e['caches']} (bouton Deposer de la bande)")
        else:
            out.append(f"Caches de vivres : +{e['caches']}")
    if e.get("cache_cap"):
        out.append(f"Chaque cache garde +{e['cache_cap']} de vivres")
    if e.get("cache_decay"):
        out.append(f"Les caches {_slower(e['cache_decay'])}")
    if e.get("camps"):
        if e["camps"] >= 2:
            out.append(f"Campements : jusqu'a {e['camps']} (bouton Camper ici)")
        else:
            out.append(f"Campements : +{e['camps']}")
    if e.get("camp_shelter"):
        out.append(f"En hiver au campement : {_pct(e['camp_shelter'])} de morts de faim")
    if e.get("camp_growth"):
        out.append(f"Naissances des bandes au campement : {_pct(e['camp_growth'])}")
    for terrain, cost in e.get("move", {}).items():
        before = 60 / BASE_MOVE_COST[terrain]
        after = 60 / cost
        out.append(
            f"Marche en {_TERRAIN_FR[terrain]} : {_num(after)} cases/semaine (au lieu de {_num(before)})"
        )
    if e.get("vision"):
        out.append(f"Vue : +{e['vision']} cases autour de vos bandes")
    if e.get("reinforce"):
        out.append(f"Renforts : vos bandes s'entraident jusqu'a {BASE_REINFORCE + e['reinforce']} cases (au lieu de {BASE_REINFORCE})")
    if e.get("influence_radius"):
        out.append(f"Zone d'influence : +{e['influence_radius']} case autour de vos bandes et camps")
    if e.get("home_food"):
        out.append(f"Dans votre zone d'influence : {_pct(e['home_food'])} de nourriture")
    if e.get("recovery"):
        out.append("Terres epuisees autour de vos camps : se refont 2 fois plus vite")
    if e.get("growth"):
        out.append(f"Naissances : {_pct(e['growth'])}")
    if e.get("max_bands"):
        out.append(f"Bandes : jusqu'a {BASE_MAX_BANDS + e['max_bands']} (au lieu de {BASE_MAX_BANDS})")
    if e.get("loyalty"):
        out.append(f"Attachement des clans a la tribu : +{e['loyalty']}")
    if e.get("stability"):
        out.append(f"Stabilite de vos villages : +{e['stability']}")
    if e.get("chief_reach"):
        out.append(f"Emprise du chef : +{e['chief_reach']} cases")
    if e.get("winter_prestige") or e.get("famine_prestige"):
        good = BASE_WINTER_PRESTIGE + e.get("winter_prestige", 0)
        bad = BASE_FAMINE_PRESTIGE + e.get("famine_prestige", 0)
        out.append(f"Prestige a la fin de l'hiver : +{good} sans famine, {bad} avec (au lieu de +4 / -6)")
    if e.get("herd"):
        out.append("Steppe : nourriture x1,35 au printemps, x1,65 en ete, x1,5 en automne et en hiver")
    if e.get("cabotage"):
        out.append("Vos bandes peuvent longer l'eau pres des rives (mer et lacs)")
    if e.get("gifts"):
        out.append(f"Cadeaux aux autres peuples : {_pct(e['gifts'])} d'effet")
    if e.get("diplo"):
        out.append(f"Vos propositions aux autres peuples : +{e['diplo']} d'acceptation")
    if e.get("alliance"):
        out.append("Vous pouvez proposer une alliance (mariages entre les chefs)")
    if e.get("union"):
        out.append("Vous pouvez proposer l'union a un petit peuple ami")
    if e.get("diffusion"):
        out.append(f"Savoirs connus des voisins : +{round(100 * e['diffusion'])} % d'apprentissage en plus")
    if e.get("villages"):
        if tech.id == "semis":
            out.append("Vous pouvez fonder un village sur un de vos campements (bouton Village)")
        else:
            out.append(f"Villages : +{e['villages']}")
    if e.get("palisade"):
        out.append("Vos villages peuvent batir une palissade (defense x1,6) et une maison des guerriers")
    if e.get("field_yield"):
        out.append(f"Recolte des champs : {_pct(e['field_yield'])}")
    if e.get("soil_loss"):
        out.append(f"Epuisement des champs : {_pct(e['soil_loss'])}")
    if e.get("granary"):
        out.append(f"Greniers des villages : +{e['granary']} semaines de reserve")
    if e.get("grain_rot"):
        out.append(f"Grain perdu au grenier (rats, humidite) : {_pct(e['grain_rot'])}")
    if e.get("disease"):
        out.append(f"Fievres dans les villages : {_pct(e['disease'])}")
    if e.get("village_growth"):
        out.append(f"Naissances dans les villages : {_pct(e['village_growth'])}")
    if e.get("village_food"):
        out.append(f"Collecte autour des villages (troupeaux) : {_pct(e['village_food'])}")
    if e.get("clearing"):
        out.append("Les villages peuvent defricher la foret pour y faire des champs")
    if e.get("trade"):
        out.append("Relations avec vos voisins : +1 par mois (echanges), jusqu'a +10")
        out.append("Echanges des accords commerciaux : charges x2, portee x2")
    if e.get("commerce"):
        out.append("Accords commerciaux : vos villages echangent leurs biens")
    from src.kora.goods import CRAFTS, res_label

    for craft in CRAFTS.values():
        if craft.needs == tech.id:
            out.append(f"Metier du village : {craft.name.lower()} ({res_label(craft.id)} des terres)")
    return out


# --- etat d'une tribu -----------------------------------------------------------


def _pop(state, tribe_id: int) -> int:
    return sum(b.population for b in state.bands.values() if b.tribe_id == tribe_id and b.population > 0)


def _lineage_all(state) -> dict:
    """Gens de chaque peuple et de tous les peuples nes de lui."""
    pop: dict = {}
    for b in state.bands.values():
        if b.population > 0:
            pop[b.tribe_id] = pop.get(b.tribe_id, 0) + b.population
    children: dict = {}
    for t in state.tribes.values():
        if t.origin and t.origin != t.id:
            children.setdefault(t.origin, []).append(t.id)
    out = {}
    for tid in state.tribes:
        total, seen, todo = 0, {tid}, [tid]
        while todo:
            cur = todo.pop()
            total += pop.get(cur, 0)
            for kid in children.get(cur, ()):
                if kid not in seen:
                    seen.add(kid)
                    todo.append(kid)
        out[tid] = total
    return out


def _lineage_pop(state, tribe_id: int) -> int:
    memo = _TICK_MEMO
    if memo is None:
        return _lineage_all(state).get(tribe_id, 0)
    pops = memo.get("lineage")
    if pops is None:
        pops = memo["lineage"] = _lineage_all(state)
    return pops.get(tribe_id, 0)


def _bands(state, tribe_id: int) -> int:
    return sum(1 for b in state.bands.values() if b.tribe_id == tribe_id and b.population > 0)


def _plural(n: int, word: str) -> str:
    return f"{n} {word}{'s' if n > 1 else ''}"


def cond_progress(state, tribe, cond: Cond, eased: bool = False) -> tuple[int, int, str]:
    """(valeur, besoin, libelle) d'une condition pour cette tribu.
    eased : savoir vu chez un voisin, les semaines vecues comptent double."""
    kind = cond.kind
    if kind == "pop":
        # Les peuples nes du votre (clans partis fonder le leur) comptent :
        # un peuple fixe, reduit a ses villages, n'est pas sans savoirs.
        own = _pop(state, tribe.id)
        have = max(own, _lineage_pop(state, tribe.id))
        label = f"Peuple {cond.need}" + (" (avec les peuples nes du votre)" if have > own else "")
        return have, cond.need, label
    if kind in ("weeks", "res"):
        need = -(-cond.need // 2) if eased else cond.need
        prefix = "res:" if kind == "res" else ""
        have = sum(tribe.practice.get(prefix + _key(t), 0) for t in cond.terrains)
        if cond.label == "hiver local":
            return have, need, f"{need} sem. d'hiver local"
        if kind == "res":
            return have, need, f"{need} sem. {cond.label}"
        return have, need, f"{need} sem. en {cond.label}"
    if kind == "winters":
        return tribe.practice.get("hivers", 0), cond.need, f"{_plural(cond.need, 'hiver')} traverse{'s' if cond.need > 1 else ''}"
    if kind == "prestige":
        return tribe.prestige, cond.need, f"Prestige {cond.need}"
    if kind == "bands":
        # Les bandes qu'on a eues comptent : un peuple fixe n'en forme plus,
        # et ses clans partis etaient les siens.
        from src.kora.peoples import children_alive

        have = max(tribe.practice.get("bandes", 0), _bands(state, tribe.id) + children_alive(state, tribe.id))
        return have, cond.need, f"Avoir eu {_plural(cond.need, 'bande')}"
    if kind == "seen":
        seen = tribe.shore_seen if cond.label == "rivage" else tribe.steppe_seen
        return int(seen), 1, f"{cond.label.capitalize()} en vue"
    if kind == "flag":
        flags = getattr(tribe, "flags", {}) or {}
        have = 1 if cond.label in flags else 0
        return have, 1, _FLAG_LABELS.get(cond.label, cond.label)
    if kind == "camp_years":
        from src.kora import sites

        return sites.oldest_camp_years(state, tribe.id), cond.need, f"Un campement tenu {cond.need} ans"
    if kind in ("contacts", "friends", "allies"):
        from src.kora import diplo

        have = {
            "contacts": diplo.contact_count,
            "friends": diplo.friend_count,
            "allies": diplo.ally_count,
        }[kind](state, tribe.id)
        label = {
            "contacts": f"Connaitre {_plural(cond.need, 'autre peuple')}",
            "friends": f"{_plural(cond.need, 'peuple')} cordia{'ux' if cond.need > 1 else 'l'} (relation 20)",
            "allies": _plural(cond.need, "allie"),
        }[kind]
        return have, cond.need, label
    if kind in ("villages", "village_years"):
        from src.kora import sites

        if kind == "villages":
            return sites.village_count(state, tribe.id), cond.need, _plural(cond.need, "village")
        return sites.oldest_village_years(state, tribe.id), cond.need, f"Un village tenu {cond.need} ans"
    return 0, 1, "?"


# Drapeaux poses par les evenements, lus par les conditions de savoirs.
_FLAG_LABELS = {
    "louveteaux": "Avoir apprivoise des louveteaux (evenement)",
}


def _key(terrain) -> str:
    return terrain if isinstance(terrain, str) else terrain.value


def missing_prereqs(tribe, tech: Tech) -> list[Tech]:
    return [TECHS[p] for p in tech.prereqs if p not in tribe.knowledge]


def _neighbors_know(state, tribe_id: int, tech_id: str) -> list:
    from src.kora import diplo

    return diplo.teachers(state, tribe_id, tech_id)


def conditions_met(state, tribe, tech: Tech) -> bool:
    eased = bool(_neighbors_know(state, tribe.id, tech.id))
    for cond in tech.conds:
        have, need, _label = cond_progress(state, tribe, cond, eased)
        if have < need:
            return False
    return True


def status(state, tribe_id: int, tech_id: str) -> str:
    """"connu", "en_cours", "disponible", "attente" (prerequis OK, pas les
    conditions) ou "verrouille" (prerequis manquants)."""
    tribe = state.tribes[tribe_id]
    tech = TECHS[tech_id]
    if tech_id in tribe.knowledge:
        return "connu"
    # Un savoir commence se finit : les conditions (terrains, bandes...)
    # ne comptent que pour le commencer.
    if tribe.learning == tech_id:
        return "en_cours"
    if tribe.progress.get(tech_id, 0.0) > 0:
        return "disponible"
    if missing_prereqs(tribe, tech):
        return "verrouille"
    if not conditions_met(state, tribe, tech):
        return "attente"
    return "disponible"


def available(state, tribe_id: int) -> list[str]:
    return [tid for tid in TECHS if status(state, tribe_id, tid) in ("disponible", "en_cours")]


def _learning_pop(state, tribe_id: int) -> int:
    """Les clans indociles n'apportent plus rien a la tribu."""
    from src.kora import chiefs

    return sum(
        b.population
        for b in state.bands.values()
        if b.tribe_id == tribe_id and b.population > 0 and chiefs.obeys(state, b)
    )


def base_rate(state, tribe_id: int) -> float:
    from src.kora import chiefs

    return (1.0 + _learning_pop(state, tribe_id) / LEARN_POP) * chiefs.learn_mult(state, tribe_id)


def diffusion_bonus(state, tribe_id: int, tech_id: str | None) -> float:
    """Part d'apprentissage en plus quand des voisins connaissent le savoir."""
    if tech_id is None:
        return 0.0
    from src.kora import diplo

    return diplo.diffusion_bonus(state, tribe_id, tech_id)


def learn_rate(state, tribe_id: int, tech_id: str | None = None) -> float:
    rate = base_rate(state, tribe_id)
    if tech_id is not None:
        rate *= 1.0 + diffusion_bonus(state, tribe_id, tech_id)
    return rate


def weeks_left(state, tribe_id: int, tech_id: str) -> int:
    tribe = state.tribes[tribe_id]
    left = max(0.0, TECHS[tech_id].cost - tribe.progress.get(tech_id, 0.0))
    rate = learn_rate(state, tribe_id, tech_id)
    return int(-(-left // rate)) if rate > 0 else 999


def choose(state, tribe_id: int, tech_id: str) -> bool:
    """Commencer (ou reprendre) l'apprentissage d'un savoir disponible."""
    if tech_id not in TECHS or status(state, tribe_id, tech_id) != "disponible":
        return False
    state.tribes[tribe_id].learning = tech_id
    return True


def auto_choose(state, tribe_id: int) -> str | None:
    """Choix de l'IA (et du robot des tests) : son gout, sinon le moins cher."""
    tribe = state.tribes[tribe_id]
    if tribe.learning:
        return tribe.learning
    ready = [tid for tid in TECHS if status(state, tribe_id, tid) == "disponible"]
    if not ready:
        return None
    taste = culture_of(tribe).taste
    ready.sort(key=lambda tid: (taste.index(tid) if tid in taste else 99, TECHS[tid].cost, tid))
    choose(state, tribe_id, ready[0])
    return ready[0]


def grant(tribe, tech_id: str) -> None:
    """Savoir acquis : dans la liste, et les drapeaux historiques suivent."""
    tribe.knowledge.add(tech_id)
    if tech_id == "pirogue":
        tribe.cabotage = True
    if tech_id == "troupeau":
        tribe.troupeau = True
    tribe.progress.pop(tech_id, None)
    if tribe.learning == tech_id:
        tribe.learning = None


def start_knowledge(tribe) -> None:
    extra = () if tribe.is_player else culture_of(tribe).knowledge
    for tid in START_KNOWLEDGE + extra:
        grant(tribe, tid)


def summary(tech: Tech) -> str:
    lines = effect_lines(tech)
    return lines[0] if lines else ""


# --- chaque semaine ---------------------------------------------------------------


def update_practice(state, count: bool = True) -> None:
    """Ce que chaque tribu a vecu cette semaine : terrains sous ses bandes,
    hiver local, rivage et steppe en vue, ressources du pays."""
    world = state.world
    by_tribe: dict[int, list] = {}
    for b in state.bands.values():
        if b.population > 0:
            by_tribe.setdefault(b.tribe_id, []).append(b)
    has_res = bool(getattr(world, "resources", None))
    for tribe in state.tribes.values():
        bands = by_tribe.get(tribe.id, [])
        if not tribe.shore_seen or not tribe.steppe_seen:
            from src.kora.world import is_inshore

            for band in bands:
                # La carte ne change pas : une position deja examinee n'a
                # rien de neuf a montrer.
                memo = (tribe.id, band.position)
                if memo in state.scan_memo:
                    continue
                state.scan_memo.add(memo)
                for h in world.hexes_in_radius(band.position, SEE_RADIUS):
                    if not tribe.shore_seen and is_inshore(world, h):
                        tribe.shore_seen = True
                    if not tribe.steppe_seen and world.terrain(h) is Terrain.STEPPE:
                        tribe.steppe_seen = True
                    if tribe.shore_seen and tribe.steppe_seen:
                        break
        if not count:
            continue
        seen = set()
        winter = False
        near: set = set()
        for band in bands:
            if band.village:
                # Un village vit de ses terres : chasse, peche, cueillette et
                # glaise de tout son pays (villages.FIELD_RADIUS).
                from src.kora.villages import land_profile

                terrains, found = land_profile(world, band.position)
                seen |= terrains
                if has_res:
                    near |= found
            else:
                seen.add(world.terrain(band.position))
                if has_res:
                    near |= world.resources_near(band.position)
            if world.hex_season(band.position) is Season.HIVER:
                winter = True
        if len(bands) > tribe.practice.get("bandes", 0):
            tribe.practice["bandes"] = len(bands)
        goods = getattr(tribe, "goods", None)
        if goods and has_res:
            # Le sel, les pots, les haches qui arrivent par l'echange : on
            # apprend a connaitre ce qu'on n'a pas chez soi.
            for good, res in _GOOD_RESOURCE.items():
                if goods.get(good, 0.0) > 0:
                    near.add(res)
        for terrain in seen:
            tribe.practice[terrain.value] = min(999, tribe.practice.get(terrain.value, 0) + 1)
        for res in near:
            key = "res:" + res
            tribe.practice[key] = min(999, tribe.practice.get(key, 0) + 1)
        if winter:
            tribe.practice["hiver"] = min(999, tribe.practice.get("hiver", 0) + 1)
        # Compteurs historiques de la pirogue et du troupeau (bornes).
        if Terrain.COTE in seen and tribe.coast_weeks < PIROGUE_COAST_WEEKS:
            tribe.coast_weeks += 1
        if Terrain.STEPPE in seen and tribe.steppe_weeks < TROUPEAU_STEPPE_WEEKS:
            tribe.steppe_weeks += 1


_GOOD_RESOURCE = {"sel": "sel", "poteries": "argile", "haches": "silex", "etoffes": "chevres", "cuirs": "aurochs"}


def count_winter(state) -> None:
    """Fin de l'hiver : chaque tribu vivante a traverse un hiver de plus."""
    living = {b.tribe_id for b in state.bands.values() if b.population > 0}
    for tribe in state.tribes.values():
        if tribe.id in living:
            tribe.practice["hivers"] = tribe.practice.get("hivers", 0) + 1


def update_learning(state) -> None:
    """Chaque semaine : l'apprentissage avance ; l'IA choisit le suivant (une
    semaine sur quatre, decalee selon le peuple ; un peuple eteint ne
    cherche plus)."""
    from src.kora import diplo

    with diplo.frozen_relations(state):
        _update_learning(state)


def _update_learning(state) -> None:
    living = {b.tribe_id for b in state.bands.values() if b.population > 0}
    for tribe in state.tribes.values():
        if tribe.id not in living:
            continue
        if not tribe.is_player and not tribe.learning and (state.tick_count + tribe.id) % 4 == 0:
            auto_choose(state, tribe.id)
        tid = tribe.learning
        if not tid:
            continue
        if tid in tribe.knowledge or tid not in TECHS:
            tribe.learning = None
            continue
        tribe.progress[tid] = tribe.progress.get(tid, 0.0) + learn_rate(state, tribe.id, tid)
        if tribe.progress[tid] >= TECHS[tid].cost:
            grant(tribe, tid)
            if tribe.is_player:
                tech = TECHS[tid]
                state.log.add(
                    LogKind.DECOUVERTE,
                    f"Nouveau savoir : {tech.name}. {summary(tech)}",
                    state.clock.year,
                    state.clock.week,
                )


def detail_lines(state, tribe_id: int, tech_id: str) -> list[tuple[str, str]]:
    """Fiche d'un savoir pour le panneau : (texte, style) ; style parmi
    "titre", "texte", "effet", "ok", "manque", "note"."""
    tribe = state.tribes[tribe_id]
    tech = TECHS[tech_id]
    st = status(state, tribe_id, tech_id)
    out: list[tuple[str, str]] = [(tech.name, "titre"), (tech.about, "texte")]
    out.append(("Effets :", "note"))
    out.extend((f"  {line}", "effet") for line in effect_lines(tech))
    if st == "connu":
        out.append(("Savoir connu.", "ok"))
        return out
    if tech.prereqs:
        out.append(("Il faut connaitre :", "note"))
        for pid in tech.prereqs:
            out.append((f"  {TECHS[pid].name}", "ok" if pid in tribe.knowledge else "manque"))
    teachers = _neighbors_know(state, tribe_id, tech_id)
    if tech.conds:
        out.append(("Il faut avoir vecu :", "note"))
        for cond in tech.conds:
            have, need, label = cond_progress(state, tribe, cond, bool(teachers))
            shown = f"  {label}  ({min(have, need)}/{need})" if cond.kind not in ("seen", "flag") else f"  {label}"
            out.append((shown, "ok" if have >= need else "manque"))
    if teachers:
        names = ", ".join(state.tribes[t].name for t in teachers[:3])
        bonus = round(100 * diffusion_bonus(state, tribe_id, tech_id))
        out.append((f"Connu de : {names}  -  apprentissage +{bonus} %, semaines vecues divisees par 2", "ok"))
    if st in ("disponible", "en_cours"):
        done = tribe.progress.get(tech_id, 0.0)
        out.append(
            (
                f"Apprentissage : {int(100 * done / tech.cost)} %  -  encore ~{weeks_left(state, tribe_id, tech_id)} sem.",
                "note",
            )
        )
    return out
