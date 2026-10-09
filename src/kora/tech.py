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
Un seul arbre : l'age tribal (paliers 0 a 3) puis le neolithique (4 a 6).

Deux sortes de savoirs :
  - les GRANDS TOURNANTS (kind="tournant", turning.py) : de grosses
    recherches qui ouvrent tout un pan de l'arbre (ceux qui les ont en
    prerequis, et leurs suites). Ils NAISSENT chez un peuple qui remplit
    leurs conditions, puis se REPANDENT chez ses voisins ; on ne peut les
    adopter que quand ils sont arrives chez soi (comme les institutions
    d'Europa Universalis V). Ils ont leur rangee dans l'arbre (1,5 et 3,5).
  - les savoirs, dont certains sont TIRES (draws.py, comme Terra Invicta) :
    chance : chaque peuple a cette chance de le voir venir ;
    world : le monde a cette chance de le voir naitre (une fois par partie) ;
    group : un groupe EXCLUSIF : un seul de ses savoirs nait dans le monde.
    Un savoir tire n'est le prerequis d'aucun savoir sur (pas d'impasse).
"""

from __future__ import annotations

from dataclasses import dataclass, field

from src.kora.log import LogKind
from src.kora.peoples import children_alive, culture_of
from src.kora.types import Season, Terrain
from src.kora.world import MOVE_COST, is_inshore
from src.kora.gamestate import note
from src.kora import systems

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
# Combien de fois plus fort il faut etre pour prendre un peuple sous sa
# protection (chiefdom.protect_ratio).
BASE_PROTECT_RATIO = 2.5
# Apprentissage : points par semaine = 1 + peuple / LEARN_POP.
LEARN_POP = 120
# Une partie longue : chaque palier demande deux fois plus qu'au debut du proto.
TIER_COST = {0: 0, 1: 40, 2: 90, 3: 160, 4: 240, 5: 360, 6: 500}
TIER_NAMES = {
    0: "Connu",
    1: "Premiers savoirs",
    1.5: "Grand tournant",
    2: "Savoirs du clan",
    3: "Aube du néolithique",
    4: "Premiers villages",
    3.5: "Grands tournants",
    5: "Villages prospères",
    6: "Grandes chefferies",
}
# Les rangees des grands tournants (turning.py) dans l'arbre.
TURNING_TIERS = (1.5, 3.5)
BRANCHES = (
    "Chasse et guerre",
    "Terre et cueillette",
    "Réserves",
    "Eau",
    "Froid et voyage",
    "Pays et campements",
    "Foyer et société",
    "Voisins",
    "Nombres",
)
# Un seul arbre, vertical : une colonne par branche. Au neolithique, chaque
# colonne prend un nouveau nom, dans le prolongement de la branche tribale
# (Reserves -> Greniers, Pays et campements -> Villages...).
NEO_BRANCHES = (
    "Guerre et défense",
    "Champs",
    "Greniers et artisans",
    "Valeurs et passages",
    "Troupeaux",
    "Villages",
    "Esprits et pouvoir",
    "Échanges",
    "Nombres et métal",
)
# (nom de l'age, paliers, noms des colonnes)
ERAS = (
    ("Âge tribal", (0, 1, 1.5, 2, 3), BRANCHES),
    ("Néolithique", (3.5, 4, 5, 6), NEO_BRANCHES),
)
# Les groupes EXCLUSIFS (draws.py) : un seul de leurs savoirs nait dans le
# monde ; (nom, chance qu'aucun ne naisse).
GROUPS = {
    "croyances": ("Les croyances", 0.0),
    "morts": ("Les tombes des morts", 0.0),
    "calendriers": ("Le calendrier", 0.25),
}
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
    _T.VALLEE: "vallée",
    _T.STEPPE: "steppe",
    _T.FORET: "forêt",
    _T.COLLINE: "colline",
    _T.MONTAGNE: "montagne",
    _T.COTE: "côte",
    _T.DESERT: "désert",
}


@dataclass(frozen=True)
class Cond:
    """Une condition pour rendre un savoir disponible.

    kind : "pop", "weeks" (terrains), "res" (ressources, dans terrains),
    "winters", "prestige", "bands", "seen", "flag" (label = drapeau d'un
    evenement), "camp_years", "contacts", "friends", "allies",
    "villages", "village_years", "kin_villages", "vassals" (tributaires)."""

    kind: str
    need: int = 0
    terrains: tuple = ()
    label: str = ""


@dataclass(frozen=True)
class Tech:
    id: str
    name: str
    tier: float
    branch: int
    about: str
    prereqs: tuple = ()
    conds: tuple = ()
    effects: dict = field(default_factory=dict)
    # "tournant" : un grand tournant (turning.py) ; ses conds sont celles de
    # sa NAISSANCE chez un peuple, ses prereqs ce qu'il faut pour l'adopter.
    kind: str = "savoir"
    # Dans l'arbre : colonnes occupees (un tournant), sous-rangee de sa case.
    span: int = 1
    slot: int = 0
    # Un cout a lui (les tournants) ; 0 : celui de son palier.
    price: int = 0
    # Les tirages (draws.py) : chance par peuple, chance du monde, groupe
    # exclusif (GROUPS).
    chance: float = 1.0
    world: float = 1.0
    group: str = ""

    @property
    def cost(self) -> int:
        return self.price or TIER_COST[self.tier]

    @property
    def turning(self) -> bool:
        return self.kind == "tournant"

    @property
    def drawn(self) -> bool:
        """Un savoir tire : il peut ne pas venir (draws.py)."""
        return self.chance < 1.0 or self.world < 1.0 or bool(self.group)


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
            "Chaleur, cuisson, lumière. Sans lui, aucun hiver n'est possible.",
            effects={"base": True},
        ),
        Tech(
            "outils", "Outils de pierre", 0, 1,
            "Bifaces, racloirs, pieux : la cueillette et la chasse de base.",
            effects={"base": True},
        ),
        # --- palier 1 : premiers savoirs -----------------------------------
        Tech(
            "epieu", "Chasse à l'épieu", 1, 0,
            "Des pieux durcis au feu et des chasseurs qui rabattent ensemble le gros gibier.",
            prereqs=("outils",),
            conds=(Cond("pop", 30), _weeks(6, _T.PLAINE, _T.STEPPE, label="plaine ou steppe")),
            effects={"combat": 1.10, "food": {_T.PLAINE: 1.10, _T.STEPPE: 1.10}},
        ),
        Tech(
            "cueillette", "Cueillette", 1, 1,
            "Savoir quelles baies, racines et noix se mangent, et où les trouver selon la saison.",
            prereqs=("outils",),
            conds=(_weeks(8, _T.FORET, _T.VALLEE, label="forêt ou vallée"),),
            effects={"food": {_T.FORET: 1.12, _T.VALLEE: 1.06}},
        ),
        Tech(
            "fumage", "Fumage et séchage", 1, 2,
            "La viande et le poisson fumés se gardent des mois : on prépare l'hiver, on cache des vivres.",
            prereqs=("feu",),
            conds=(Cond("winters", 1),),
            effects={"stock_weeks": 4, "caches": 3, "cache_cap": 300},
        ),
        Tech(
            "peche", "Pêche au harpon", 1, 3,
            "Harpons d'os et pièges à poissons au bord de l'eau.",
            prereqs=("outils",),
            conds=(Cond("seen", label="rivage"), _weeks(4, _T.COTE, _T.VALLEE, label="côte ou vallée")),
            effects={"water_food": 0.25, "food": {_T.COTE: 1.08}},
        ),
        Tech(
            "peaux", "Vêtements de peau", 1, 4,
            "Aiguilles d'os et peaux cousues : on survit au froid.",
            prereqs=("feu", "outils"),
            conds=(Cond("weeks", 10, ("hiver",), "hiver local"),),
            effects={"winter_famine": 0.7, "winter_hills": 1.5},
        ),
        Tech(
            "huttes", "Huttes et campements", 1, 5,
            "Des huttes de branches et de peaux qu'on retrouve chaque saison : un lieu à soi.",
            prereqs=("feu",),
            conds=(Cond("winters", 1), Cond("pop", 30)),
            effects={"camps": 2, "camp_shelter": 0.6},
        ),
        Tech(
            "rites", "Rites et sépultures", 1, 6,
            "Ocre, parures, morts enterrés avec leurs outils : les clans partagent les mêmes ancêtres.",
            prereqs=("feu",),
            conds=(Cond("winters", 2), Cond("pop", 40)),
            effects={"loyalty": 6, "chief_reach": 3},
        ),
        Tech(
            "palabres", "Dons et palabres", 1, 7,
            "Échanger des présents, s'asseoir autour du même feu : on parle avant de se battre.",
            prereqs=("feu",),
            conds=(Cond("contacts", 1),),
            effects={"gifts": 1.5, "diplo": 10, "diplomacy": True},
        ),
        # --- palier 2 : savoirs du clan ------------------------------------
        Tech(
            "arc", "Arc et flèches", 2, 0,
            "Tuer de loin : le petit gibier des forêts, et l'ennemi avant qu'il n'approche.",
            prereqs=("epieu",),
            conds=(Cond("pop", 80), _weeks(12, _T.FORET, label="forêt")),
            effects={"combat": 1.15, "food": {_T.FORET: 1.06}},
        ),
        Tech(
            "troupeau", "Garde des troupeaux", 2, 1,
            "Suivre et garder un troupeau plutôt que le chasser : la steppe devient un garde-manger.",
            prereqs=("domestication",),
            conds=(
                Cond("seen", label="steppe"),
                _weeks(TROUPEAU_STEPPE_WEEKS, _T.STEPPE, label="steppe"),
                Cond("pop", TROUPEAU_POP),
            ),
            effects={"herd": True},
        ),
        Tech(
            "salaison", "Salaison", 2, 2,
            "Le sel garde la viande et le poisson : des réserves plus grandes, des caches qui durent.",
            prereqs=("fumage",),
            conds=(Cond("res", 10, ("sel",), "près du sel"), Cond("winters", 2)),
            effects={"stock_weeks": 3, "cache_cap": 200, "cache_decay": 0.5},
        ),
        Tech(
            "pirogue", "Pirogue", 2, 3,
            "Un tronc creusé au feu : on longe les rives, on traverse les lacs et les détroits.",
            prereqs=("peche",),
            conds=(
                Cond("seen", label="rivage"),
                _weeks(PIROGUE_COAST_WEEKS, _T.COTE, label="côte"),
                Cond("pop", PIROGUE_POP),
            ),
            effects={"cabotage": True},
        ),
        Tech(
            "portage", "Raquettes et portage", 2, 4,
            "Raquettes, traîneaux, sentiers battus : la forêt et les collines ralentissent moins.",
            prereqs=("peaux",),
            conds=(_weeks(14, _T.FORET, _T.COLLINE, label="forêt ou collines"),),
            effects={"move": {_T.FORET: 15, _T.COLLINE: 12, _T.MONTAGNE: 45}},
        ),
        Tech(
            "reperes", "Pistes et repères", 2, 5,
            "Chaque source, chaque gué, chaque passage des bêtes a un nom : on connaît son pays.",
            prereqs=("huttes", "clan"),
            conds=(Cond("bands", 2), Cond("winters", 3)),
            effects={"influence_radius": 1, "home_food": 1.08, "chief_reach": 4},
        ),
        Tech(
            "conte", "Récits autour du feu", 2, 6,
            "Les anciens racontent les hivers passés : la tribu se souvient et se tient.",
            prereqs=("clan",),
            conds=(Cond("winters", 3), Cond("pop", 70)),
            effects={"winter_prestige": 2, "famine_prestige": 2, "growth": 1.05, "chief_reach": 3},
        ),
        Tech(
            "mariages", "Mariages entre clans", 2, 7,
            "On donne ses filles et ses fils aux voisins : les alliances se scellent par le sang.",
            prereqs=("palabres", "clan"),
            conds=(Cond("pop", 80), Cond("friends", 1)),
            effects={"alliance": True, "loyalty": 4},
        ),
        # --- palier 3 : aube du neolithique --------------------------------
        Tech(
            "guetteurs", "Guetteurs et signaux", 3, 0,
            "Des veilleurs sur les hauteurs et des signaux de fumée : on voit venir, on s'entraide.",
            prereqs=("arc", "conte"),
            conds=(Cond("bands", 4), Cond("pop", 160)),
            effects={"vision": 4, "reinforce": 1, "home_defense": 1.15},
        ),
        Tech(
            "semis", "Premières semailles", 3, 1,
            "Replanter les graines des meilleures plantes près du camp : le début des champs.",
            prereqs=("cueillette", "fumage"),
            conds=(
                Cond("pop", 120),
                Cond("winters", 4),
                Cond("res", 20, ("cereales", "racines"), "près de céréales ou de racines sauvages"),
            ),
            effects={"food": {_T.VALLEE: 1.2, _T.PLAINE: 1.1}, "recovery": 0.1},
        ),
        Tech(
            "poterie", "Poterie", 3, 2,
            "Des pots d'argile cuite : grain et graisse à l'abri de l'humidité et des rongeurs.",
            prereqs=("fumage",),
            conds=(Cond("pop", 180), Cond("winters", 6), Cond("res", 8, ("argile",), "près de l'argile")),
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
            "Filets tressés et nasses en osier : la mer et les lacs nourrissent vraiment.",
            prereqs=("pirogue",),
            conds=(Cond("pop", 140), _weeks(30, _T.COTE, label="côte")),
            effects={"water_food": 0.15, "food": {_T.COTE: 1.08}},
        ),
        Tech(
            "chiens", "Chiens de chasse", 3, 4,
            "Les louveteaux d'autrefois sont devenus des chiens : ils rabattent le gibier et veillent la nuit.",
            prereqs=("domestication",),
            conds=(Cond("flag", 1, label="louveteaux"),),
            effects={"food": {_T.FORET: 1.06, _T.PLAINE: 1.06, _T.STEPPE: 1.06}, "vision": 2},
        ),
        Tech(
            "campement", "Camp permanent", 3, 5,
            "Un camp tenu d'année en année, avec ses réserves et ses tombes : le cœur du pays.",
            prereqs=("reperes",),
            conds=(Cond("camp_years", 3), Cond("pop", 150)),
            effects={"camps": 1, "influence_radius": 1, "camp_growth": 1.10},
        ),
        Tech(
            "chefferie", "Chefferie", 3, 6,
            "Un chef reconnu par plusieurs clans : la tribu peut s'étendre sans se défaire.",
            prereqs=("conte",),
            conds=(Cond("pop", 250), Cond("prestige", 50), Cond("winters", 8)),
            effects={"max_bands": 4, "growth": 1.05, "loyalty": 8, "chief_reach": 8, "camps": 1},
        ),
        Tech(
            "confederation", "Confédération", 3, 7,
            "Plusieurs peuples sous les mêmes serments : les petits se joignent aux grands.",
            prereqs=("mariages",),
            conds=(Cond("allies", 1), Cond("prestige", 40)),
            effects={"union": True, "diffusion": 0.15},
        ),
        # --- neolithique, palier 4 : premiers villages ---------------------
        Tech(
            "palissade", "Palissades", 4, 0,
            "Des pieux plantés en cercle autour des maisons : le village ne fuit pas, il se défend.",
            prereqs=("sedentarite",),
            conds=(Cond("villages", 1),),
            effects={"palisade": True},
        ),
        Tech(
            "champs", "Champs cultivés", 4, 1,
            "On choisit les meilleures graines, on désherbe, on garde les oiseaux : les champs rendent enfin.",
            prereqs=("sedentarite",),
            conds=(Cond("village_years", 2), Cond("res", 20, ("cereales", "racines"), "près de céréales ou de racines")),
            effects={"field_yield": 1.4},
        ),
        Tech(
            "chevres", "Chèvres et moutons", 4, 4,
            "Des bêtes qui suivent le berger : du lait, de la laine, de la viande sur pied.",
            prereqs=("domestication", "sedentarite"),
            conds=(Cond("res", 20, ("chevres",), "près des chèvres sauvages"), Cond("pop", 120)),
            effects={
                "food": {_T.COLLINE: 1.2, _T.MONTAGNE: 1.2, _T.PLAINE: 1.05},
                "village_food": 1.1,
                "winter_famine": 0.9,
            },
        ),
        Tech(
            "greniers", "Greniers", 4, 2,
            "Des greniers surélevés, à l'abri des rats et de l'eau : le grain dure.",
            prereqs=("poterie", "sedentarite"),
            conds=(Cond("villages", 1), Cond("winters", 8)),
            effects={"granary": 8, "grain_rot": 0.5},
        ),
        Tech(
            "maisons", "Maisons de terre", 4, 5,
            "Des murs de terre et de bois, des toits de chaume : on vit mieux, on tombe moins malade.",
            prereqs=("campement", "sedentarite"),
            conds=(Cond("village_years", 3),),
            effects={"disease": 0.6, "village_growth": 1.1},
        ),
        Tech(
            "ancetres", "Culte des ancêtres", 4, 6,
            "Les morts reposent sous les maisons : le village appartient à ceux qui y sont nés.",
            prereqs=("terre_ancetres",),
            conds=(Cond("villages", 1), Cond("winters", 10)),
            effects={"stability": 10, "winter_prestige": 2},
        ),
        Tech(
            "echanges", "Échanges lointains", 4, 7,
            "Du silex contre du sel, des perles contre des peaux : les biens voyagent de main en main.",
            prereqs=("don",),
            conds=(Cond("contacts", 3), Cond("pop", 150)),
            effects={"diffusion": 0.1, "gifts": 1.25, "diplo": 5, "commerce": True},
        ),
        # --- neolithique, palier 5 : villages prosperes -----------------------
        Tech(
            "haches", "Haches polies", 5, 0,
            "La pierre polie abat les arbres et les ennemis : la forêt recule devant les champs.",
            prereqs=("champs",),
            conds=(Cond("res", 20, ("silex",), "près du silex"), Cond("pop", 200)),
            effects={"combat": 1.1, "clearing": True},
        ),
        Tech(
            "jachere", "Jachère", 5, 1,
            "Laisser reposer la terre une année sur trois : le sol ne s'épuise plus.",
            prereqs=("champs",),
            conds=(Cond("village_years", 5),),
            effects={"soil_loss": 0.5, "field_yield": 1.2},
        ),
        Tech(
            "bovins", "Bœufs et vaches", 5, 4,
            "L'aurochs dompté : de la viande, du lait, et le fumier qui engraisse les champs.",
            prereqs=("chevres",),
            conds=(Cond("res", 30, ("aurochs",), "près des aurochs"), Cond("pop", 200)),
            effects={
                "food": {_T.PLAINE: 1.12, _T.VALLEE: 1.08},
                "village_food": 1.15,
                "winter_famine": 0.9,
                "field_yield": 1.15,
            },
        ),
        Tech(
            "tissage", "Tissage", 5, 2,
            "Le lin et la laine tissés : des vêtements chauds, et des étoffes qu'on échange.",
            prereqs=("champs",),
            conds=(Cond("villages", 1), Cond("pop", 200)),
            effects={"winter_famine": 0.8, "winter_prestige": 1},
        ),
        Tech(
            "freres", "Villages frères", 5, 5,
            "Des villages nés du même village : un même sang, chacun son chef. On s'entraide.",
            prereqs=("maisons",),
            conds=(Cond("kin_villages", 2),),
            effects={"kin": True, "stability": 10},
        ),
        Tech(
            "megalithes", "Pierres levées", 5, 6,
            "Des pierres dressées que tous les clans ont tirées ensemble : on les voit de loin.",
            prereqs=("ancetres",),
            conds=(Cond("prestige", 60), Cond("pop", 300)),
            effects={"winter_prestige": 3, "stability": 15, "influence_radius": 1},
        ),
        Tech(
            "routes", "Routes du sel et du silex", 5, 7,
            "Des sentiers de peuple en peuple, jalonnés de haltes : on se connaît, on commerce.",
            prereqs=("echanges",),
            conds=(Cond("allies", 1), Cond("contacts", 4)),
            effects={"diffusion": 0.15, "trade": True},
        ),
        # --- les nombres et l'argent (numbers.py, money.py) --------------------
        Tech(
            "comptage", "Comptage par bâtons", 2, 8,
            "Des encoches sur un bâton, une par lune, une par bête : on compte ce qu'on ne voit plus.",
            prereqs=("clan",),
            conds=(Cond("winters", 3),),
            effects={"math": True},
        ),
        Tech(
            "nombres", "Nombres additifs", 4, 8,
            "Un signe pour un, un autre pour dix, et on les aligne : les nombres s'écrivent. Il faut choisir sa base.",
            prereqs=("comptage", "sedentarite"),
            conds=(Cond("villages", 1),),
            effects={"numbers": True},
        ),
        Tech(
            "valeurs", "Valeurs d'échange", 4, 3,
            "Les perles, les coquillages, les haches polies valent tant : on paie, on doit, on garde un trésor.",
            prereqs=("comptage", "don"),
            conds=(Cond("contacts", 2), Cond("village_years", 2)),
            effects={"money": True},
        ),
        Tech(
            "argent_pese", "Argent pesé", 5, 8,
            "Le métal blanc des collines, pesé à la balance : un sicle vaut partout un sicle.",
            prereqs=("valeurs", "nombres"),
            conds=(Cond("village_years", 4),),
            effects={"silver": True},
        ),
        Tech(
            "peages", "Droits de passage", 5, 3,
            "Les porteurs qui traversent votre pays paient leur passage : un gué, un col, une halte gardée.",
            prereqs=("valeurs", "reperes"),
            conds=(Cond("contacts", 4),),
            effects={"tolls": True},
        ),
        # --- les grandes chefferies (fin du neolithique) : des chefs qui
        # gagnent leurs voisins par les fetes, les dons, les serments ou la
        # force ; et ceux qui preferent leurs champs et leurs betes.
        Tech(
            "enceintes", "Enceintes et fossés", 6, 0,
            "Un fossé, un talus, une palissade double : le village devient un refuge où l'on tient un siège.",
            prereqs=("palissade", "haches"),
            conds=(Cond("village_years", 6),),
            effects={"village_defense": 1.3},
        ),
        Tech(
            "araire", "Araire", 6, 1,
            "Un soc de bois tiré par des bœufs : on ouvre plus de terre, plus vite, sans rien prendre à personne.",
            prereqs=("jachere", "bovins"),
            conds=(Cond("village_years", 6),),
            effects={"field_yield": 1.15},
        ),
        Tech(
            "festins", "Festins de prestige", 6, 2,
            "Le chef nourrit tout le pays et ses voisins : qui a mangé à sa table lui doit quelque chose.",
            prereqs=("greniers", "ancetres"),
            conds=(Cond("prestige", 40), Cond("village_years", 5)),
            effects={"feasts": True, "feast_cost": 0.75},
        ),
        Tech(
            "lait", "Lait et laine", 5, 4,
            "On trait les vaches et les chèvres, on tond les moutons : les bêtes vivantes nourrissent et habillent.",
            prereqs=("chevres",),
            conds=(Cond("village_years", 5),),
            effects={"village_food": 1.08, "stability": 3},
            slot=1,
        ),
        Tech(
            "grand_chef", "Chef des chefs", 6, 5,
            "D'autres chefs viennent s'asseoir à vos pieds : un chef au-dessus des chefs de village.",
            prereqs=("maisons", "ancetres"),
            conds=(Cond("vassals", 1), Cond("prestige", 50)),
            effects={"vassal_cap": 2, "vassal_tribute": 1.5, "protect_ratio": 0.8},
        ),
        Tech(
            "otages", "Otages et serments", 6, 6,
            "Les fils des chefs soumis grandissent chez vous, et chacun a juré devant les ancêtres.",
            prereqs=("ancetres",),
            conds=(Cond("vassals", 1),),
            effects={"vassal_unrest": 0.6},
        ),
        Tech(
            "biens_prestige", "Biens de prestige", 6, 7,
            "Haches de jade, parures de coquillages venues de loin : le chef les donne, et ceux qui les portent lui sont liés.",
            prereqs=("echanges",),
            conds=(Cond("contacts", 4),),
            effects={"gifts": 1.5, "obligations": True},
        ),
        # --- les GRANDS TOURNANTS (turning.py) --------------------------------
        # Leurs conds : leur NAISSANCE chez un peuple ; ensuite ils se
        # repandent chez les voisins. Leurs prereqs : ce qu'il faut savoir
        # pour les adopter.
        Tech(
            "clan", "Le clan", 1.5, 5,
            "Au-delà du foyer, une grande famille : des ancêtres communs, des mariages, une parole transmise. Tout ce qui fait un peuple vient de là.",
            prereqs=("rites", "palabres"),
            conds=(Cond("pop", 50), Cond("winters", 2), Cond("bands", 2)),
            effects={"loyalty": 5},
            kind="tournant", span=2, price=90,
        ),
        Tech(
            "sedentarite", "La sédentarité", 3.5, 1,
            "On ne suit plus le gibier : on reste, on sème, on bâtit. La révolution qui change tout : les villages, les champs, les greniers.",
            prereqs=("semis", "huttes"),
            conds=(Cond("pop", 140), Cond("winters", 4)),
            effects={"villages": 1},
            kind="tournant", span=2, price=140,
        ),
        Tech(
            "domestication", "La domestication", 1.5, 1,
            "Le loup qui rôde autour du feu devient chien ; la bête qu'on chassait, on la garde et on la fait naître. Les bêtes deviennent des compagnes, puis une richesse.",
            prereqs=("epieu",),
            conds=(
                Cond("res", 10, ("chevres", "aurochs", "chevaux", "rennes"), "près de bêtes sauvages à apprivoiser"),
                Cond("pop", 40),
                Cond("winters", 2),
            ),
            effects={"winter_famine": 0.95},
            kind="tournant", span=2, price=90,
        ),
        Tech(
            "terre_ancetres", "La terre des ancêtres", 3.5, 5,
            "Les morts gardent la terre où ils reposent : les lignées s'y enracinent, les chefs parlent en leur nom.",
            prereqs=("rites", "chefferie"),
            conds=(Cond("villages", 1), Cond("winters", 10)),
            effects={"stability": 2},
            kind="tournant", span=2, price=240,
        ),
        Tech(
            "don", "Le don et l'échange", 3.5, 7,
            "Ce qu'on donne oblige, ce qu'on reçoit se rend : entre les peuples, les biens circulent et lient.",
            prereqs=("palabres", "mariages"),
            conds=(Cond("contacts", 3), Cond("pop", 120)),
            effects={"diplo": 5},
            kind="tournant", span=2, price=200,
        ),
        # --- des savoirs TIRES (draws.py) ------------------------------------
        # Age tribal.
        Tech(
            "propulseur", "Propulseur", 2, 0,
            "Un bois à crochet qui prolonge le bras : la sagaie part plus loin et plus fort.",
            prereqs=("epieu",),
            conds=(Cond("pop", 40), _weeks(10, _T.PLAINE, _T.STEPPE, label="plaine ou steppe")),
            effects={"combat": 1.08, "food": {_T.PLAINE: 1.06, _T.STEPPE: 1.06}},
            slot=1, world=0.7, chance=0.6,
        ),
        Tech(
            "brulis", "Brûlis du sous-bois", 2, 1,
            "On met le feu aux broussailles : l'herbe tendre repousse et le gibier revient.",
            prereqs=("cueillette",),
            conds=(_weeks(20, _T.FORET, label="forêt"),),
            effects={"home_food": 1.05, "food": {_T.FORET: 1.05}},
            slot=1, world=0.6,
        ),
        Tech(
            "peintures", "Peintures des cavernes", 2, 6,
            "Des bêtes peintes à la lueur des torches, au fond des grottes : on y apprend, on s'y souvient.",
            prereqs=("rites", "clan"),
            conds=(Cond("winters", 3),),
            effects={"winter_prestige": 2, "learn": 1.05},
            slot=1, chance=0.5,
        ),
        Tech(
            "rabattages", "Grandes chasses collectives", 3, 0,
            "Tous les clans ensemble rabattent les troupeaux vers un ravin ou un enclos : la viande de toute une saison.",
            prereqs=("arc", "clan"),
            conds=(Cond("pop", 120), Cond("bands", 3)),
            effects={"food": {_T.PLAINE: 1.08, _T.STEPPE: 1.08, _T.VALLEE: 1.05}},
            slot=1, chance=0.5,
        ),
        Tech(
            "chamanes", "Chamanes et esprits animaux", 3, 5,
            "Le chamane voyage chez les esprits des bêtes : la chasse est permise, le clan protégé.",
            prereqs=("rites", "clan"),
            conds=(Cond("winters", 4),),
            effects={"food": {_T.FORET: 1.05, _T.STEPPE: 1.05}, "loyalty": 3},
            slot=1, group="croyances",
        ),
        Tech(
            "deesse", "La Grande Mère", 3, 6,
            "Une mère de toutes choses, aux formes généreuses, qu'on sculpte dans l'ivoire et la pierre : la vie revient.",
            prereqs=("rites", "clan"),
            conds=(Cond("winters", 4),),
            effects={"growth": 1.06, "winter_famine": 0.95},
            slot=1, group="croyances",
        ),
        # Neolithique.
        Tech(
            "irrigation", "Rigoles d'irrigation", 5, 1,
            "On détourne un peu de la rivière vers les champs : la sécheresse fait moins peur.",
            prereqs=("champs",),
            conds=(Cond("village_years", 4), _weeks(20, _T.VALLEE, label="vallée")),
            effects={"field_yield": 1.1},
            slot=1, chance=0.4,
        ),
        Tech(
            "jetons", "Jetons d'argile", 5, 8,
            "Un petit cône d'argile pour une mesure de grain, une bille pour une bête : on garde les comptes dans une bourse.",
            prereqs=("nombres", "don"),
            conds=(Cond("village_years", 3),),
            effects={"tax": 1.1, "trade_price": 1.03},
            slot=1, world=0.6, chance=0.5,
        ),
        Tech(
            "cheval", "Le cheval monté", 6, 3,
            "On ne mange plus le cheval : on le monte. La steppe rétrécit, et les cavaliers frappent loin.",
            prereqs=("troupeau", "chevres"),
            conds=(Cond("res", 20, ("chevaux",), "près des chevaux sauvages"), Cond("pop", 150)),
            effects={"move": {_T.PLAINE: 8, _T.STEPPE: 7}, "combat": 1.1, "vision": 1},
            world=0.4, chance=0.35,
        ),
        Tech(
            "cuivre", "Le cuivre martelé", 6, 8,
            "Une pierre verte qu'on chauffe et qu'on bat : des perles, des poinçons, des haches qui brillent.",
            prereqs=("haches", "valeurs"),
            conds=(Cond("village_years", 5), Cond("pop", 200)),
            effects={"combat": 1.06, "prestige_gain": 1.1, "trade_price": 1.04},
            world=0.5, chance=0.5,
        ),
        Tech(
            "fromage", "Fromages et laitages", 6, 4,
            "Le lait caillé se garde des mois : l'hiver devient moins maigre.",
            prereqs=("lait",),
            conds=(Cond("village_years", 4),),
            effects={"village_food": 1.04, "winter_famine": 0.93},
            slot=1, chance=0.5,
        ),
        Tech(
            "kourganes", "Tumulus des chefs", 6, 5,
            "Le chef repose seul sous une colline de terre, avec ses armes et ses chevaux : son nom ne meurt pas.",
            prereqs=("ancetres",),
            conds=(Cond("village_years", 5),),
            effects={"prestige_gain": 1.12, "vassal_unrest": 0.9},
            slot=1, group="morts", chance=0.6,
        ),
        Tech(
            "dolmens", "Tombes collectives", 6, 6,
            "Une grande chambre de pierre où dorment tous les morts du village : on est d'ici, ensemble.",
            prereqs=("ancetres",),
            conds=(Cond("village_years", 5),),
            effects={"stability": 3, "loyalty": 3},
            slot=1, group="morts",
        ),
        Tech(
            "calendrier_soleil", "Calendrier des pierres levées", 6, 7,
            "Le soleil se lève dans l'axe des pierres au plus long jour : on sait quand semer.",
            prereqs=("megalithes",),
            conds=(Cond("village_years", 6),),
            effects={"field_yield": 1.05, "winter_prestige": 1},
            slot=1, group="calendriers",
        ),
        Tech(
            "calendrier_lune", "Calendrier des lunes", 6, 8,
            "Une encoche par lune sur l'os gravé : on compte les mois, on prévoit les greniers.",
            prereqs=("nombres",),
            conds=(Cond("village_years", 6),),
            effects={"learn": 1.05, "grain_rot": 0.93},
            slot=1, group="calendriers",
        ),
    )
}


def pan_of(tid: str) -> list[Tech]:
    """Le PAN d'un tournant : les savoirs qui l'ont en prerequis (il les
    ouvre), dans l'ordre de l'arbre."""
    return sorted((t for t in TECHS.values() if tid in t.prereqs), key=lambda t: (t.tier, t.branch, t.slot))


def descendants(tid: str) -> set:
    """Tout ce qui vient apres un savoir (ses suites, et leurs suites)."""
    out: set = set()
    todo = [tid]
    while todo:
        cur = todo.pop()
        for t in TECHS.values():
            if cur in t.prereqs and t.id not in out:
                out.add(t.id)
                todo.append(t.id)
    return out


def turnings() -> list[Tech]:
    return sorted((t for t in TECHS.values() if t.turning), key=lambda t: (t.tier, t.branch))

# Specialites de depart et gout de l'IA : voir peoples.CULTURES.


# --- bonus de depart ---------------------------------------------------------------
# A la creation de sa tribu, le joueur en choisit START_BONUS_PICKS dans ce pool ;
# ils durent START_BONUS_YEARS ans (Tribe.start_bonuses, start_bonus_until), puis
# s'eteignent. Leurs effets sont ceux des savoirs (memes noms, meme calcul).
START_BONUS_YEARS = 5
START_BONUS_WEEKS = 52 * START_BONUS_YEARS
START_BONUS_PICKS = 2


@dataclass(frozen=True)
class StartBonus:
    id: str
    name: str
    about: str
    effects: dict
    icon: int = 0


START_BONUSES: dict[str, StartBonus] = {
    b.id: b
    for b in (
        StartBonus(
            "bonus:aurochs", "Chasseurs d'aurochs",
            "On sait rabattre les grands troupeaux des plaines.",
            {"food": {_T.PLAINE: 1.15, _T.STEPPE: 1.15}}, 0,
        ),
        StartBonus(
            "bonus:bois", "Cueilleurs des bois",
            "Baies, noix, champignons : les bois nourrissent.",
            {"food": {_T.FORET: 1.15, _T.VALLEE: 1.12}}, 1,
        ),
        StartBonus(
            "bonus:rivages", "Gens des rivages",
            "Coquillages, poissons des lagunes : on vit du rivage.",
            {"food": {_T.COTE: 1.15}, "water_food": 0.2}, 3,
        ),
        StartBonus(
            "bonus:froid", "Enfants du froid",
            "Nés dans la neige, ils savent passer l'hiver.",
            {"winter_famine": 0.6, "winter_hills": 1.3}, 4,
        ),
        StartBonus(
            "bonus:prevoyants", "Prévoyants",
            "On sèche, on fume, on cache : il y a toujours une réserve.",
            {"stock_weeks": 4, "caches": 1, "cache_cap": 200}, 2,
        ),
        StartBonus(
            "bonus:fertiles", "Peuple fécond",
            "Beaucoup d'enfants, et qui survivent.",
            {"growth": 1.3}, 5,
        ),
        StartBonus(
            "bonus:guerriers", "Guerriers redoutés",
            "Vos chasseurs sont aussi des combattants.",
            {"combat": 1.2, "home_defense": 1.1}, 0,
        ),
        StartBonus(
            "bonus:eclaireurs", "Éclaireurs",
            "Des yeux perçants sur chaque colline.",
            {"vision": 3}, 5,
        ),
        StartBonus(
            "bonus:conteurs", "Conteurs",
            "Les anciens transmettent tout : on apprend vite.",
            {"learn": 1.3, "winter_prestige": 1}, 6,
        ),
        StartBonus(
            "bonus:rassembleur", "Chef rassembleur",
            "Les clans suivent le chef, même loin de lui.",
            {"loyalty": 10, "chief_reach": 4}, 6,
        ),
        StartBonus(
            "bonus:diplomates", "Diplomates",
            "On parle avant de se battre, et on sait offrir.",
            {"diplo": 15, "gifts": 1.5}, 7,
        ),
        StartBonus(
            "bonus:campeurs", "Bâtisseurs de camps",
            "Des huttes solides, des camps qu'on retrouve chaque saison.",
            {"camps": 1, "camp_shelter": 0.7, "camp_growth": 1.1}, 5,
        ),
    )
}


_SPECS: dict = {}


def spec_effect(eid: str):
    """L'effet d'une situation, d'une base, d'une operation... comme un
    savoir : decrit par le systeme qui porte son prefixe
    (systems.EFFECT_SPECS). None : ce n'en est pas un."""
    if eid in _SPECS:
        return _SPECS[eid]
    prefix = next((p for p in systems.EFFECT_SPECS if eid.startswith(p)), None)
    if prefix is not None:
        for k, (name, effects) in systems.fn(systems.EFFECT_SPECS[prefix])().items():
            if k.startswith(prefix) and k not in _SPECS:
                _SPECS[k] = StartBonus(k, name, "", effects)
    return _SPECS.setdefault(eid, None)


# Les anciens noms (ecrans, tests).
situation_effect = spec_effect
math_effect = spec_effect


def start_bonus_ids(tribe) -> list:
    """Les bonus de depart comptent comme des savoirs tant qu'ils durent."""
    return getattr(tribe, "start_bonuses", None) or []


def start_bonus_lines(bonus: StartBonus) -> list[str]:
    """Ce que fait un bonus de depart (les memes phrases que les savoirs)."""

    class _Shim:
        id = bonus.id
        effects = bonus.effects

    lines = effect_lines(_Shim)
    return lines


def start_bonus_lines_for(tribe, bonus: StartBonus) -> list[str]:
    """Pareil, avec les vrais chiffres du peuple (None : ceux du depart)."""
    return lines_for(tribe, bonus) if tribe is not None else start_bonus_lines(bonus)


def set_start_bonuses(tribe, picks, tick: int) -> None:
    tribe.start_bonuses = [b for b in picks if b in START_BONUSES][:START_BONUS_PICKS]
    tribe.start_bonus_until = tick + START_BONUS_WEEKS if tribe.start_bonuses else -1


def update_start_bonuses(state) -> None:
    """Fin des bonus de depart, START_BONUS_YEARS ans apres le debut."""
    for tribe in state.tribes.values():
        if tribe.start_bonuses and state.tick_count >= tribe.start_bonus_until:
            names = ", ".join(START_BONUSES[b].name for b in tribe.start_bonuses if b in START_BONUSES)
            tribe.start_bonuses = []
            tribe.start_bonus_until = -1
            invalidate()
            if tribe.is_player:
                note(state, LogKind.DECOUVERTE, f"Les bonus de départ s'éteignent ({names}) : votre peuple vole de ses propres ailes.", to=tribe.id)


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
    # Vitesse d'apprentissage (bonus de depart des Conteurs).
    learn: float = 1.0
    # Prestige gagne (le grand monument, situations.py) et prix de vos
    # ventes sur les routes (le marche refuge).
    prestige_gain: float = 1.0
    trade_price: float = 1.0
    # Villages freres : les villages de sa civilisation et ses tributaires
    # sont des freres (diplo, battle.helpers_of).
    kin: bool = False
    # Les nombres et l'argent (numbers.py, money.py).
    math: bool = False
    numbers: bool = False
    money: bool = False
    silver: bool = False
    tolls: bool = False
    tax: float = 1.0
    # Les grandes chefferies (chiefdom.py, diplo.py, villages.py).
    village_defense: float = 1.0
    vassal_cap: int = 0
    vassal_tribute: float = 1.0
    vassal_unrest: float = 1.0
    protect_ratio: float = 1.0
    feasts: bool = False
    feast_cost: float = 1.0
    obligations: bool = False
    # La diplomatie (diplo.py) : on ne s'attaque plus sans declarer la guerre.
    diplomacy: bool = False


_MULT = {
    "learn",
    "village_defense",
    "vassal_tribute",
    "vassal_unrest",
    "protect_ratio",
    "feast_cost",
    "tax",
    "prestige_gain",
    "trade_price",
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
_FLAGS = {"alliance", "union", "palisade", "clearing", "trade", "commerce", "kin", "math", "numbers", "money", "silver", "tolls", "feasts", "obligations", "diplomacy"}
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
        tech = TECHS.get(tid) or START_BONUSES.get(tid) or spec_effect(tid)
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
    for path in systems.EFFECT_FIELDS:
        # Ce qui compte comme des savoirs : bonus de depart, situations,
        # nombres... (systems.EFFECT_FIELDS).
        extra = systems.fn(path)(tribe)
        if extra:
            known = set(known or ()) | set(extra)
    bonus = bonuses_of(known) if known else NO_BONUS
    if memo is not None:
        memo[id(tribe)] = (tribe, bonus)
    return bonus


def bonuses_without(tribe, tid: str) -> Bonuses:
    """Les bonus du peuple sans ce savoir (ou cet effet) : la base des
    chiffres de effect_lines."""
    known = set(getattr(tribe, "knowledge", None) or ())
    for path in systems.EFFECT_FIELDS:
        known |= set(systems.fn(path)(tribe) or ())
    known.discard(tid)
    return bonuses_of(known) if known else NO_BONUS


def has_effect(tribe, tid: str) -> bool:
    if tid in (getattr(tribe, "knowledge", None) or ()):
        return True
    return any(tid in (systems.fn(path)(tribe) or ()) for path in systems.EFFECT_FIELDS)


def lines_for(tribe, tech) -> list[str]:
    """effect_lines avec les vrais chiffres de ce peuple (None : ceux du depart)."""
    if tribe is None:
        return effect_lines(tech)
    return effect_lines(tech, bonuses_without(tribe, tech.id), has_effect(tribe, tech.id))


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
        return "ne se gâtent plus"
    times = 1.0 / mult
    return f"se gâtent {_num(times)} fois moins vite"


def effect_lines(tech: Tech, base: "Bonuses | None" = None, known: bool = False) -> list[str]:
    """Ce que fait un savoir (ou un effet du meme genre), en phrases tirees
    des donnees. base : les bonus du peuple SANS ce savoir (bonuses_without) ;
    les totaux sont alors ses vrais chiffres ("jusqu'a 14, aujourd'hui 10") ;
    known : il le sait deja ("sans lui 10"). Sans base : les chiffres du
    depart."""
    e = tech.effects
    out: list[str] = []
    b = base if base is not None else NO_BONUS
    word = "sans lui" if known else ("aujourd'hui" if base is not None else "au départ")

    def was(value) -> str:
        return f" ({word} {value})"
    if e.get("base"):
        out.append("Déjà pris en compte dans le jeu de base.")
    groups: dict[float, list] = {}
    for terrain, mult in e.get("food", {}).items():
        groups.setdefault(mult, []).append(terrain)
    for mult, terrains in groups.items():
        out.append(f"{_terrain_list(terrains)} : {_pct(mult)} de nourriture")
    if e.get("water_food"):
        per = 2.0 * e["water_food"]
        out.append(f"Eau près des rives (mer, lacs) : +{_num(per)} nourriture par case (printemps)")
    if e.get("winter_hills"):
        out.append(f"Collines et montagnes en hiver : nourriture x{_num(e['winter_hills'])}")
    if e.get("combat"):
        out.append(f"Force au combat : {_pct(e['combat'])}")
    if e.get("home_defense"):
        out.append(f"Défense dans votre zone d'influence : {_pct(e['home_defense'])}")
    if e.get("winter_famine"):
        out.append(f"Famine pendant l'hiver local : {_pct(e['winter_famine'])} de morts")
    if e.get("stock_weeks"):
        out.append(f"Réserves : {b.stock_weeks + e['stock_weeks']} semaines de stock par personne" + was(b.stock_weeks))
    if e.get("caches"):
        out.append(f"Caches de vivres : jusqu'à {b.caches + e['caches']} (bouton Déposer de la bande)" + was(b.caches))
    if e.get("cache_cap"):
        out.append(f"Chaque cache garde {b.cache_cap + e['cache_cap']} vivres de plus" + was(b.cache_cap))
    if e.get("cache_decay"):
        out.append(f"Les caches {_slower(e['cache_decay'])}")
    if e.get("camps"):
        out.append(f"Campements : jusqu'à {b.camps + e['camps']} (bouton Camper ici)" + was(b.camps))
    if e.get("camp_shelter"):
        out.append(f"En hiver au campement : {_pct(e['camp_shelter'])} de morts de faim")
    if e.get("camp_growth"):
        out.append(f"Naissances des bandes au campement : {_pct(e['camp_growth'])}")
    for terrain, cost in e.get("move", {}).items():
        now_cost = (b.move or BASE_MOVE_COST).get(terrain, BASE_MOVE_COST[terrain])
        before = 60 / now_cost
        after = 60 / min(cost, now_cost)
        out.append(f"Marche en {_TERRAIN_FR[terrain]} : {_num(after)} cases/semaine" + was(_num(before)))
    if e.get("vision"):
        out.append(f"Vue : {b.vision + e['vision']} cases autour de vos bandes" + was(b.vision))
    if e.get("reinforce"):
        out.append(f"Renforts : vos bandes s'entraident jusqu'à {b.reinforce + e['reinforce']} cases" + was(b.reinforce))
    if e.get("influence_radius"):
        out.append(f"Zone d'influence : {b.influence_radius + e['influence_radius']} cases autour de vos bandes et camps" + was(b.influence_radius))
    if e.get("home_food"):
        out.append(f"Dans votre zone d'influence : {_pct(e['home_food'])} de nourriture")
    if e.get("recovery"):
        out.append("Terres épuisées autour de vos camps : se refont 2 fois plus vite")
    if e.get("growth"):
        out.append(f"Naissances : {_pct(e['growth'])}")
    if e.get("max_bands"):
        out.append(f"Bandes : jusqu'à {b.max_bands + e['max_bands']}" + was(b.max_bands))
    if e.get("loyalty"):
        out.append(f"Attachement des clans à la tribu : {b.loyalty + e['loyalty']:+d}" + was(f"{b.loyalty:+d}"))
    if e.get("stability"):
        out.append(f"Stabilité de vos villages : {b.stability + e['stability']:+d}" + was(f"{b.stability:+d}"))
    if e.get("chief_reach"):
        out.append(f"Emprise du chef : {b.chief_reach + e['chief_reach']} cases" + was(b.chief_reach))
    if e.get("winter_prestige") or e.get("famine_prestige"):
        good = b.winter_prestige + e.get("winter_prestige", 0)
        bad = b.famine_prestige + e.get("famine_prestige", 0)
        out.append(f"Prestige à la fin de l'hiver : {good:+d} sans famine, {bad:+d} avec" + was(f"{b.winter_prestige:+d} / {b.famine_prestige:+d}"))
    if e.get("herd"):
        out.append("Steppe : nourriture x1,35 au printemps, x1,65 en été, x1,5 en automne et en hiver")
    if e.get("cabotage"):
        out.append("Vos bandes peuvent longer l'eau près des rives (mer et lacs)")
    if e.get("gifts"):
        out.append(f"Cadeaux aux autres peuples : {_pct(e['gifts'])} d'effet")
    if e.get("diplo"):
        out.append(f"Vos propositions aux autres peuples : {b.diplo + e['diplo']:+d} d'acceptation" + was(f"{b.diplo:+d}"))
    if e.get("diplomacy"):
        out.append("La diplomatie : entre peuples qui la connaissent, on ne s'attaque plus sans déclarer la guerre (écran Peuples)")
    if e.get("alliance"):
        out.append("Vous pouvez proposer une alliance (mariages entre les chefs)")
    if e.get("union"):
        out.append("Vous pouvez proposer l'union à un petit peuple ami")
    if e.get("diffusion"):
        out.append(f"Savoirs connus des voisins : +{round(100 * e['diffusion'])} % d'apprentissage en plus")
    if e.get("villages"):
        if tech.id == "sedentarite":
            out.append("Vous pouvez fonder un village sur un de vos campements (bouton Village)")
        else:
            out.append(f"Villages : {b.villages + e['villages']}" + was(b.villages))
    if e.get("palisade"):
        out.append("Vos villages peuvent bâtir une palissade (défense x1,6) et une maison des guerriers")
    if e.get("field_yield"):
        out.append(f"Récolte des champs : {_pct(e['field_yield'])}")
    if e.get("soil_loss"):
        out.append(f"Épuisement des champs : {_pct(e['soil_loss'])}")
    if e.get("granary"):
        out.append(f"Greniers des villages : {b.granary + e['granary']} semaines de réserve en plus" + was(b.granary))
    if e.get("grain_rot"):
        out.append(f"Grain perdu au grenier (rats, humidité) : {_pct(e['grain_rot'])}")
    if e.get("disease"):
        out.append(f"Fièvres dans les villages : {_pct(e['disease'])}")
    if e.get("village_growth"):
        out.append(f"Naissances dans les villages : {_pct(e['village_growth'])}")
    if e.get("village_food"):
        out.append(f"Collecte autour des villages (troupeaux) : {_pct(e['village_food'])}")
    if e.get("clearing"):
        out.append("Les villages peuvent défricher la forêt pour y faire des champs")
    if e.get("trade"):
        out.append("Relations avec vos voisins : +1 par mois (échanges), jusqu'à +10")
        out.append("Échanges des accords commerciaux : charges x2, portée x2")
    if e.get("commerce"):
        out.append("Accords commerciaux : vos villages échangent leurs biens")
    if e.get("learn"):
        out.append(f"Apprentissage des savoirs : {_pct(e['learn'])}")
    if e.get("prestige_gain"):
        out.append(f"Prestige gagné : {_pct(e['prestige_gain'])}")
    if e.get("trade_price"):
        out.append(f"Prix de vos ventes sur les routes : {_pct(e['trade_price'])}")
    if e.get("kin"):
        out.append("Les villages de votre civilisation et vos tributaires : relation +15, ils viennent en renfort")
    if e.get("math"):
        out.append("On compte : l'addition (+), et l'onglet des nombres dans les savoirs")
    if e.get("numbers"):
        out.append("Choisir la base de vos nombres (10, 12, 20 ou 60), chacune son avantage")
        out.append("Un métier : les calculateurs, qui trouvent de nouvelles opérations")
    if e.get("money"):
        out.append("L'argent : un trésor, un budget (impôt, solde, gages), le commerce en argent")
    if e.get("silver"):
        out.append("Un métier : les mineurs d'argent (filons des collines) ; l'impôt rentre mieux (+25 %)")
    if e.get("tolls"):
        out.append("Les convois étrangers qui traversent votre pays paient leur passage")
    if e.get("tax"):
        out.append(f"Rendement de l'impôt : {_pct(e['tax'])}")
    if e.get("village_defense"):
        out.append(f"Défense de votre village : {_pct(e['village_defense'])}")
    if e.get("vassal_cap"):
        out.append(f"Tributaires que vous pouvez tenir : {b.vassal_cap + e['vassal_cap']:+d} en plus" + was(f"{b.vassal_cap:+d}"))
    if e.get("vassal_tribute"):
        out.append(f"Tribut de vos tributaires : {_pct(e['vassal_tribute'])}")
    if e.get("protect_ratio"):
        now_ratio = BASE_PROTECT_RATIO * b.protect_ratio
        out.append(f"Prendre un peuple sous sa protection : il suffit d'être {_num(now_ratio * e['protect_ratio'])} fois plus fort" + was(_num(now_ratio)))
    if e.get("vassal_unrest"):
        out.append(f"Agitation de vos tributaires : {_pct(e['vassal_unrest'])}")
    if e.get("feasts"):
        out.append("Vos voisins sont invités à la grande fête : relation +8 ; pendant un an, ils se mettent plus volontiers sous votre protection (+10)")
    if e.get("feast_cost"):
        out.append(f"Coût d'une grande fête : {_pct(e['feast_cost'])}")
    if e.get("obligations"):
        out.append("Un peuple qui reçoit vos dons vous est obligé : il se met plus volontiers sous votre protection (+12) et paie plus volontiers un tribut (+8)")

    for path in systems.TECH_LINES:
        # Ce que d'autres systemes disent de ce savoir (un metier qu'il ouvre...).
        out.extend(systems.fn(path)(tech))
    return out


# --- etat d'une tribu -----------------------------------------------------------


def _plural(n: int, word: str) -> str:
    # Chaque mot s'accorde : "2 autres peuples", "2 villages frères".
    if n <= 1:
        return f"{n} {word}"
    return f"{n} " + " ".join(w + "s" for w in word.split(" "))


def missing_prereqs(tribe, tech: Tech) -> list[Tech]:
    return [TECHS[p] for p in tech.prereqs if p not in tribe.knowledge]


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


def summary(tech: Tech, tribe=None) -> str:
    lines = lines_for(tribe, tech)
    return lines[0] if lines else ""


# --- chaque semaine ---------------------------------------------------------------

