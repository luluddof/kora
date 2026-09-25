from dataclasses import dataclass, field
from enum import Enum
from typing import NamedTuple, Optional


class Terrain(Enum):
    PLAINE = "plaine"
    VALLEE = "vallee"
    STEPPE = "steppe"
    FORET = "foret"
    COLLINE = "colline"
    MONTAGNE = "montagne"
    SOMMET = "sommet"
    EAU = "eau"
    COTE = "cote"
    DESERT = "desert"

    # Les membres sont uniques : le hachage par identite (en C) remplace
    # celui d'Enum (en Python), appele des millions de fois par partie.
    __hash__ = object.__hash__


class Season(Enum):
    PRINTEMPS = "printemps"
    ETE = "ete"
    AUTOMNE = "automne"
    HIVER = "hiver"

    __hash__ = object.__hash__


class OrderKind(Enum):
    STAY = "stay"
    GOTO = "goto"
    MARCH_TO_BAND = "march_to_band"


class Hex(NamedTuple):
    """Case en coordonnees axiales. Un tuple nomme : hachage et egalite en
    C (c'est la cle la plus utilisee du jeu)."""

    q: int
    r: int


@dataclass
class Order:
    kind: OrderKind
    target_hex: Optional[Hex] = None
    target_band_id: Optional[int] = None


def stay_order() -> Order:
    return Order(kind=OrderKind.STAY)


@dataclass
class Band:
    id: int
    tribe_id: int
    position: Hex
    population: int
    stock: float
    order: Order = field(default_factory=stay_order)
    path: list = field(default_factory=list)
    famine_in_period: bool = False
    recent_goals: list = field(default_factory=list)
    growth_acc: float = 0.0
    last_raid_tick: int = -1000
    retreating: bool = False
    shield_until: int = 0
    # IA : proie visee par un raid a plusieurs, et date limite du plan.
    intent_prey: int = 0
    intent_until: int = 0
    # Clan (chiefs.py) : son chef de bande, son attachement a la tribu,
    # la derniere fois qu'il a ete honore, la derniere famine.
    leader: Optional["Person"] = None
    loyalty: float = 80.0
    honored: int = -1000
    famine_tick: int = -1000
    # Bande installee dans un village (id du lieu, voir villages.py) : elle
    # ne marche plus.
    village: int = 0
    # Troupe de guerriers levee par un village ("armee", voir villages.py) :
    # son village, la semaine de sa levee.
    kind: str = ""
    home: int = 0
    raised: int = 0
    # Troupe : ses compagnies [type, hommes, village] (units.py) ; dissoute,
    # elle rentre a pied (homebound) et redevient villageoise a l'arrivee.
    units: list = field(default_factory=list)
    homebound: bool = False
    # Clan : les chefs des clans reunis (anciens) ; groupe pas encore soude.
    notables: list = field(default_factory=list)
    welded_until: int = 0
    # Clan nomade d'un peuple fixe : son independance (0 a 100, chiefs.py).
    autonomy: float = 0.0


@dataclass
class Person:
    """Un chef de bande (et peut-etre le chef de la tribu)."""

    pid: int
    name: str
    born: int
    traits: tuple = ()
    renown: int = 0


@dataclass
class Tribe:
    id: int
    name: str
    prestige: int
    is_player: bool
    famine_during_winter: bool = False
    cabotage: bool = False
    shore_seen: bool = False
    coast_weeks: int = 0
    troupeau: bool = False
    steppe_seen: bool = False
    steppe_weeks: int = 0
    # Savoirs (voir tech.py) : connus, en cours, avancement, vecu.
    knowledge: set = field(default_factory=set)
    learning: Optional[str] = None
    progress: dict = field(default_factory=dict)
    practice: dict = field(default_factory=dict)
    # Peuple (voir peoples.py) : culture, couleur, petit peuple, peuple
    # d'origine (secession), annee de naissance du peuple.
    culture: str = ""
    color: tuple = ()
    minor: bool = False
    origin: int = 0
    founded: int = 1
    # Memoire des evenements : drapeau -> semaine d'expiration (-1 = toujours).
    flags: dict = field(default_factory=dict)
    # Chef de la tribu : la bande qu'il mene ; heritier designe (pid).
    chief_band: int = 0
    heir: int = 0
    # Semaine du premier village (-1 : nomades) : l'age des villages.
    settled_at: int = -1
    # Civilisation (peuples.civ_of) : le peuple d'origine de la lignee ; 0 :
    # la sienne (ou celle du peuple dont il est ne).
    civ: int = 0
    # Biens du peuple (goods.py) : bien -> charges en reserve ; derniers
    # echanges : peuple (texte) -> {"in": {bien: n}, "out": {...}, "vivres": v}.
    goods: dict = field(default_factory=dict)
    trade: dict = field(default_factory=dict)


@dataclass
class FightMark:
    hex: Hex
    tick: int
    year: int
    week: int
    winner_tribe: int
    loser_tribe: int
    winner_name: str
    loser_name: str
    winner_before: int
    loser_before: int
    winner_loss: int
    loser_loss: int
    loot: float
    # Rapport de bataille (battle.py) : camps, passes d'armes, issue.
    report: Optional[dict] = None
