from dataclasses import dataclass, field
from enum import Enum
from typing import Any, NamedTuple, Optional


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


def _families(v) -> list:
    """Familles d'une vieille partie : les cles qui manquaient."""
    return [
        {"id": int(f["id"]), "name": str(f["name"]), "trait": str(f["trait"]), "charge": str(f.get("charge", "")),
         "favour": float(f.get("favour", 50.0)), "village": int(f.get("village", 0))}
        for f in v
    ]


def _people(v) -> list:
    from src.kora.chiefs import person_from_json

    return [p for p in (person_from_json(x) for x in v) if p is not None]


def _trade(v) -> dict:
    return v if isinstance(v, dict) else {}


# Les champs de Band et de Tribe se sauvent, se relisent et se copient
# d'apres leur TYPE (records.py) : un champ nouveau = une ligne ici, avec
# son type precis et sa valeur par defaut (celle des vieilles parties).


@dataclass
class Band:
    id: int
    tribe_id: int
    position: Hex
    population: int
    stock: float
    order: Order = field(default_factory=stay_order)
    path: list[Hex] = field(default_factory=list)
    famine_in_period: bool = False
    recent_goals: list[Hex] = field(default_factory=list)
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
    units: list[list] = field(default_factory=list)
    homebound: bool = False
    # Clan : les chefs des clans reunis (anciens) ; groupe pas encore soude.
    notables: list["Person"] = field(default_factory=list, metadata={"decode": _people})
    welded_until: int = 0
    # Clan nomade d'un peuple fixe : son independance (0 a 100, chiefs.py).
    autonomy: float = 0.0
    # Qui sont ses gens (population.py) : la part de chaque classe (vide :
    # la structure ordinaire), et ses blesses.
    demo: dict[str, float] = field(default_factory=dict)
    wounded: int = 0


@dataclass
class Person:
    """Un chef de bande (et peut-etre le chef de la tribu)."""

    pid: int
    name: str
    born: int
    traits: tuple[str, ...] = ()
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
    knowledge: set[str] = field(default_factory=set)
    learning: Optional[str] = None
    progress: dict[str, float] = field(default_factory=dict)
    practice: dict[str, int] = field(default_factory=dict)
    # Peuple (voir peoples.py) : culture, couleur, petit peuple, peuple
    # d'origine (secession), annee de naissance du peuple.
    culture: str = ""
    color: tuple[int, ...] = ()
    minor: bool = False
    origin: int = 0
    founded: int = 1
    # Memoire des evenements : drapeau -> semaine d'expiration (-1 = toujours).
    flags: dict[str, int] = field(default_factory=dict)
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
    goods: dict[str, float] = field(default_factory=dict, metadata={"round": 3})
    trade: dict = field(default_factory=dict, metadata={"decode": _trade})
    # Bonus de depart choisis a la creation (tech.START_BONUSES), jusqu'a la
    # semaine start_bonus_until (-1 : aucun).
    start_bonuses: list[str] = field(default_factory=list)
    start_bonus_until: int = -1
    # Effets des situations (situations.py) : [id, jusqu'a la semaine] ; -1 :
    # tant que la situation dure.
    situation_effects: list[list] = field(default_factory=list)
    # Savoir-faire des villages (production.py) : genre de production ->
    # efficacite (1,0 au depart) ; et mois de surproduction par bien.
    efficiency: dict[str, float] = field(default_factory=dict)
    glut: dict[str, int] = field(default_factory=dict)
    # La chefferie (chiefdom.py) : prelevement du chef sur les recoltes (%),
    # son grenier commun, les familles qui comptent, la derniere fete.
    levy_rate: int = 10
    granary: float = 0.0
    families: list[dict[str, Any]] = field(default_factory=list, metadata={"decode": _families})
    feast_until: int = -1
    # Les nombres (numbers.py) : la base, les operations, les points de
    # calcul, les effets en vigueur ; la derniere reforme.
    base: int = 0
    base_changed: int = -1000000
    base_reform_until: int = -1
    operations: list[str] = field(default_factory=list)
    math_progress: float = 0.0
    math_effects: list[str] = field(default_factory=list)
    # L'argent (money.py) : le tresor, le budget, le mois en cours, l'histoire.
    money: float = 0.0
    budget: dict[str, Any] = field(default_factory=dict)
    money_month: dict[str, float] = field(default_factory=dict)
    # [annee, semaine, rentrees, depenses, tresor, {poste: sicles}]
    money_hist: list = field(default_factory=list)


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
