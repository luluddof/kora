"""Batailles : un combat simule en passes d'armes.

Deux camps : la bande engagee (et, a portee de renfort, ses clans soeurs
obeissants et les bandes de ses allies) contre l'autre. Chaque camp a :
  - des combattants : une troupe (villages.py) se bat tout entiere, un clan
    seulement a 40 % (le reste, ce sont les familles, sim.CLAN_SHARE) ;
  - une valeur par combattant : prestige, savoirs, chef, troupe aguerrie
    (sim.band_quality) ;
  - un abri, pour le defenseur : terrain, palissade, pays connu ;
  - un moral de depart : troupe, familles a defendre, village, faim...
A chaque passe (ROUNDS au plus), chacun tue selon sa puissance ; le moral
baisse avec les pertes et le rapport de force. Sous ROUT : deroute. Apres
la derniere passe sans deroute, le moins solide se retire en ordre.
Une deroute se paie a la poursuite : terrain ouvert, poursuivant aguerri,
et sans chemin de repli c'est l'encerclement. Il reste moins de WIPE_MIN
personnes (ou une troupe brisee) : ANEANTIE. Un village ne fuit pas : il
est pille (champs brules, grain pris, un batiment peut-etre perdu), ou
rase si ses defenseurs tombent.
Chaque combat a son propre hasard (tour, bandes) : rejouable, et il n'use
pas celui du reste du jeu. N'importe ni pygame ni render.
"""

from __future__ import annotations

import math
import random
from dataclasses import dataclass, field

from src.kora import chiefs, influence, sim
from src.kora.log import terrain_fr
from src.kora.types import Band, Terrain

ROUNDS = 6
KILL = 0.12
ROUT = 25.0
SHOCK = 150.0
PRESSURE = 5.0
MAX_RATIO = 8.0
MORALE_BASE = 60.0
ARMY_MORALE = 20.0
KIN_MORALE = 15.0
VILLAGE_MORALE = 25.0
HOME_MORALE = 5.0
HUNGER_MORALE = -20.0
GUARD_MORALE = 10.0
MARCH_MORALE = -10.0
LEADER_MORALE = 5.0
WELD_MORALE = -8.0
_T = Terrain
COVER = {_T.COLLINE: 1.2, _T.FORET: 1.15, _T.MONTAGNE: 1.35, _T.SOMMET: 1.35}
# Facilite de la poursuite : terrain ouvert, on rattrape ; bois et collines,
# on s'echappe.
ESCAPE = {
    _T.PLAINE: 1.2,
    _T.STEPPE: 1.25,
    _T.DESERT: 1.2,
    _T.FORET: 0.6,
    _T.COLLINE: 0.7,
    _T.MONTAGNE: 0.5,
    _T.SOMMET: 0.5,
}
PURSUIT = 0.15
ARMY_PURSUIT = 1.5
CLAN_PURSUIT = 0.6
ORDERLY = 0.3
ENCIRCLED = 0.35
# Un clan aneanti : ses derniers survivants rejoignent la bande de leur
# peuple la plus proche, a cette distance au plus (une troupe, non).
SCATTER_RANGE = 16
WIPE_MIN = 6
ARMY_BROKEN = 0.3
LOOT = 0.5
VILLAGE_SHIELD = 6
PLACE = {
    _T.PLAINE: "dans la plaine",
    _T.VALLEE: "dans la vallée",
    _T.STEPPE: "dans la steppe",
    _T.FORET: "en forêt",
    _T.COLLINE: "sur les collines",
    _T.MONTAGNE: "dans la montagne",
    _T.SOMMET: "sur les hauteurs",
    _T.COTE: "sur la côte",
    _T.DESERT: "dans le désert",
    _T.EAU: "sur l'eau",
}


@dataclass
class Side:
    main: Band
    bands: list
    start: dict
    now: dict
    quality: dict
    cover: float
    morale: float
    mods: list
    attacker: bool
    # Par bande (units.py) : attaque, tenue, tir ; un clan : 1, 1, 0.
    attack: dict = field(default_factory=dict)
    guard: dict = field(default_factory=dict)
    ranged: dict = field(default_factory=dict)

    def total(self) -> float:
        return sum(self.now.values())

    def total_start(self) -> float:
        return sum(self.start.values())

    def power(self, volley: float = 0.0) -> float:
        raw = sum(
            self.now[b.id] * self.quality[b.id] * (self.attack.get(b.id, 1.0) + volley * self.ranged.get(b.id, 0.0))
            for b in self.bands
        )
        return raw * math.sqrt(self.cover)

    def toughness(self) -> float:
        """Tenue moyenne : les pertes subies en sont divisees."""
        total = self.total()
        if total <= 0:
            return 1.0
        return sum(self.now[b.id] * self.guard.get(b.id, 1.0) for b in self.bands) / total


@dataclass
class Result:
    winner: Band
    loser: Band
    winner_before: int
    loser_before: int
    winner_loss: int
    loser_loss: int
    loot: float
    wiped: bool
    outcome: str
    report: dict
    building: str = ""
    engaged: set = field(default_factory=set)


def _fmt(x: float) -> str:
    return f"{x:.2f}".rstrip("0").rstrip(".").replace(".", ",")


# --- ce que chaque camp apporte ------------------------------------------------------


def cover_parts(state, band: Band, h) -> list[tuple[str, float]]:
    """Abri du defenseur : terrain, pays connu (Guetteurs), palissade..."""
    out = []
    terrain = state.world.terrain(h)
    c = COVER.get(terrain)
    if c:
        out.append((terrain_fr(terrain), c))
    know = sim.bonus_of(state, band.tribe_id)
    if know.home_defense != 1.0 and influence.is_home(state.world, h, band.tribe_id):
        out.append(("Pays connu (guetteurs)", know.home_defense))
    if band.village:
        from src.kora import villages

        out.extend(villages.defense_parts(state, band))
    return out


def start_morale(state, band: Band, attacker: bool, h) -> tuple[float, list[tuple[str, float]]]:
    parts: list[tuple[str, float]] = []
    tribe = state.tribes[band.tribe_id]
    if band.kind == "armee":
        from src.kora import villages

        parts.append(("Troupe aguerrie", ARMY_MORALE + villages.army_morale(state, band)))
    elif not attacker:
        parts.append(("Défend les siens", KIN_MORALE))
    if band.village and not attacker:
        parts.append(("Défend son village", VILLAGE_MORALE))
        from src.kora import villages

        site = villages.site_of(state, band)
        if site is not None:
            s = round((villages.stability(state, site, band) - villages.STABILITY_BASE) / 5.0)
            if s:
                parts.append(("Village stable" if s > 0 else "Village agité", s))
    if influence.is_home(state.world, h, band.tribe_id):
        parts.append(("Sur ses terres", HOME_MORALE))
    # Le prestige compte deja dans la valeur des combattants : ici, un peu.
    p = max(-5.0, min(8.0, (tribe.prestige - 40) / 6.0))
    if abs(p) >= 1:
        parts.append(("Prestige", round(p)))
    if band.famine_in_period:
        parts.append(("Affamés", HUNGER_MORALE))
    if not attacker and "sur_gardes" in tribe.flags:
        # Evenement "Ils n'ont pas oublie" : la tribu veille.
        parts.append(("Sur ses gardes", GUARD_MORALE))
    if not attacker and band.path and not band.village and not band.retreating:
        parts.append(("Surpris en marche", MARCH_MORALE))
    if band.leader is not None and "guerrier" in band.leader.traits:
        parts.append(("Chef guerrier", LEADER_MORALE))
    if band.kind == "armee":
        from src.kora import units

        m = units.profile(band)["morale"]
        if m >= 1:
            parts.append(("Boucliers", round(m)))
    if state.tick_count < band.welded_until:
        parts.append(("Pas encore soudes", WELD_MORALE))
    return MORALE_BASE + sum(v for _l, v in parts), parts


def fighters_in(band: Band, attacker: bool) -> float:
    """Combattants d'une bande dans cette bataille (fighters_now)."""
    return fighters_now(band, attacker)


def _side(state, main: Band, attacker: bool, h) -> Side:
    bands = [main] + sim.helpers_of(state, main)
    start = {b.id: fighters_in(b, attacker) for b in bands}
    quality = {b.id: sim.band_quality(state, b) for b in bands}
    mods: list[tuple[str, str]] = []
    cover = 1.0
    if not attacker:
        for label, mult in cover_parts(state, main, h):
            cover *= mult
            mods.append((f"{label} x{_fmt(mult)}", "+"))
    morale, parts = start_morale(state, main, attacker, h)
    for label, v in parts:
        mods.append((f"{label} {'+' if v >= 0 else ''}{v:.0f} moral", "+" if v >= 0 else "-"))
    helpers = len(bands) - 1
    if helpers:
        mods.append((f"Renforts : {helpers} bande{'s' if helpers > 1 else ''}", "+"))
    from src.kora import units

    terrain = state.world.terrain(h)
    attack, guard, ranged = {}, {}, {}
    for b in bands:
        prof = units.profile(b)
        attack[b.id] = units.attack_mult(b, terrain)
        guard[b.id] = prof["defense"]
        ranged[b.id] = prof["ranged"]
    if main.kind == "armee":
        prof = units.profile(main)
        if prof["ranged"] > 0:
            mods.append(("Tireurs : volee d'ouverture", "+"))
        if prof["defense"] > 1.05:
            mods.append((f"Tenue x{_fmt(prof['defense'])}", "+"))
    return Side(main, bands, start, dict(start), quality, cover, morale, mods, attacker, attack, guard, ranged)


def _seed(state, a: Band, b: Band) -> int:
    return (state.tick_count * 1_000_003 + a.id * 7919 + b.id * 104_729) & 0x7FFFFFFF


def _spread(side: Side, hit: float, lost: dict) -> None:
    """Pertes d'une passe, reparties selon la part de chaque bande."""
    weights = {b.id: side.now[b.id] * side.quality[b.id] for b in side.bands}
    total = sum(weights.values())
    if total <= 0:
        return
    for bid, w in weights.items():
        take = min(side.now[bid], hit * w / total)
        side.now[bid] -= take
        lost[bid] = lost.get(bid, 0.0) + take


# --- la bataille ----------------------------------------------------------------------


def pursuit_rate(state, winner: Side, loser: Side, h, outcome: str, encircled: bool) -> float:
    from src.kora import units

    esc = ESCAPE.get(state.world.terrain(h), 1.0)
    chase = ARMY_PURSUIT * units.profile(winner.main)["pursuit"] if winner.main.kind == "armee" else CLAN_PURSUIT
    ratio = max(0.5, min(9.0, winner.power() / max(0.1, loser.power())))
    rate = PURSUIT * chase * esc * math.sqrt(ratio)
    if outcome == "retraite":
        rate *= ORDERLY
    if encircled:
        rate += ENCIRCLED
    return min(0.9, rate)


# --- la bataille : jour apres jour ------------------------------------------------------
#
# Une bataille DURE : chaque jour (day), chaque camp frappe l'autre selon sa
# puissance - ses combattants (les hommes valides, population.py), leur
# valeur (prestige, savoirs, chef, troupe), leurs armes sur ce terrain
# (units.attack_mult), son general (general) et, pour le defenseur, l'abri
# du terrain ou des murs - multipliee par la FORTUNE du jour (0,8 a 1,2) :
# le hasard pese sur les pertes, il ne decide jamais seul. Les coups
# tuent (KILLED_SHARE) ou blessent ; pertes et rapport de force usent le
# moral. Sous ROUT : deroute. Un camp qui demande le repli se retire en
# ordre ; au bout de MAX_DAYS, le moins solide se retire.
# Quand une bataille touche un joueur, le temps passe en jours (sim.tick) ;
# sinon, une semaine fait jusqu'a sept jours de bataille.

DAY_KILL = 0.07
KILLED_SHARE = 0.35
MAX_DAYS = 8
FORTUNE = 0.4
# Les familles d'un clan battu : quelques-unes sont prises dans la fuite.
FAMILIES_CAUGHT = 0.15
# Les blesses d'un camp battu restent sur le terrain : une part est perdue
# (deroute / retraite en ordre).
WOUNDED_LOST = {"deroute": 0.5, "retraite": 0.15}
# Au mur d'un village attaque : les hommes valides, et une part des femmes.
WALL_WOMEN = 0.3
GENERAL_STEP = 0.06
# Sous ce moral, des combattants fuient (une part, jamais tous, pas chaque
# jour pareil) : une troupe perd ses deserteurs (ils rentrent au village),
# un clan ses hommes qui ne se battent plus.
FLEE_MORALE = 50.0
FLEE_RATE = 0.08
# L'IA se replie quand elle perd et n'a rien a perdre : loin de chez elle,
# interceptee, ou une troupe qui se brise.
AI_LOSING = 0.8
AI_FAR = 12


@dataclass
class Battle:
    uid: int
    hex: object
    attackers: list
    defenders: list
    started: int
    hunted: bool = False
    village: bool = False
    day: int = 0
    morale_a: float = 0.0
    morale_d: float = 0.0
    start_a: float = 0.0
    start_d: float = 0.0
    pop0: dict = field(default_factory=dict)
    killed: dict = field(default_factory=dict)
    hurt: dict = field(default_factory=dict)
    days: list = field(default_factory=list)
    mods_a: list = field(default_factory=list)
    mods_d: list = field(default_factory=list)
    general_a: list = field(default_factory=list)
    general_d: list = field(default_factory=list)
    retreat: str = ""
    outcome: str = ""
    morale0_a: float = 0.0
    morale0_d: float = 0.0
    units0: dict = field(default_factory=dict)
    fled: dict = field(default_factory=dict)
    intercepted: str = ""


def battles(state) -> list:
    return getattr(state, "battles", [])


def battle_of(state, band_id: int):
    for bt in battles(state):
        if not bt.outcome and (band_id in bt.attackers or band_id in bt.defenders):
            return bt
    return None


def in_battle(state, band) -> bool:
    return band is not None and battle_of(state, band.id) is not None


def involves_human(state, bt) -> bool:
    tids = {state.bands[b].tribe_id for b in bt.attackers + bt.defenders if b in state.bands}
    return any(sim.is_human(state, t) for t in tids)


def slow(state) -> bool:
    """Une bataille en cours touche un joueur : le temps passe en jours."""
    return any(not bt.outcome and involves_human(state, bt) for bt in battles(state))


def general(state, bands) -> tuple[str, int]:
    """Le general d'un camp : le chef de sa bande menee (ses traits, sa
    renommee), et le chef de guerre du peuple (chiefdom.py). Sa competence
    (0 a 6) fait GENERAL_STEP de puissance par point."""
    if not bands:
        return "", 0
    main = bands[0]
    lead = main.leader
    skill = 0
    name = ""
    if lead is not None:
        name = lead.name
        skill = 1 + (2 if "guerrier" in lead.traits else 0) + min(2, lead.renown // 40)
    from src.kora import chiefdom

    skill += chiefdom.war_chief_bonus(state, main.tribe_id)
    return name, min(6, skill)


def fighters_now(band: Band, attacker: bool) -> float:
    """Combattants d'une bande : ses hommes valides ; au mur de son village,
    une part des femmes aussi."""
    from src.kora import population

    men = population.men_force(band)
    if band.village and not attacker and band.kind != "armee":
        return men + WALL_WOMEN * population.women_force(band)
    return men


def _alive(state, ids) -> list:
    return [state.bands[b] for b in ids if b in state.bands and state.bands[b].population > 0]


def _now(state, bt, attacker: bool) -> Side:
    """Un camp tel qu'il est ce jour-la (ses bandes vivantes)."""
    from src.kora import units

    bands = _alive(state, bt.attackers if attacker else bt.defenders)
    h = bt.hex
    terrain = state.world.terrain(h)
    start = {b.id: max(0.0, fighters_now(b, attacker) - bt.fled.get(b.id, 0)) for b in bands}
    quality = {b.id: sim.band_quality(state, b) for b in bands}
    cover = 1.0
    if not attacker and bands:
        for _label, mult in cover_parts(state, bands[0], h):
            cover *= mult
    attack, guard, ranged = {}, {}, {}
    for b in bands:
        prof = units.profile(b)
        attack[b.id] = units.attack_mult(b, terrain)
        guard[b.id] = prof["defense"]
        ranged[b.id] = prof["ranged"]
    morale = bt.morale_a if attacker else bt.morale_d
    main = bands[0] if bands else None
    return Side(main, bands, start, dict(start), quality, cover, morale, [], attacker, attack, guard, ranged)


def start(state, attacker: Band, defender: Band, h, hunted: bool = False) -> Battle:
    """La bataille commence : deux camps (la bande et ses renforts), leur
    moral, leurs generaux. Les bandes sur la case ne marchent plus."""
    a = _side(state, attacker, True, h)
    d = _side(state, defender, False, h)
    for side in (a, d):
        for b in side.bands:
            side.start[b.id] = fighters_now(b, side.attacker)
            side.now[b.id] = side.start[b.id]
    uid = getattr(state, "next_battle_uid", 1)
    state.next_battle_uid = uid + 1
    ga, gd = general(state, a.bands), general(state, d.bands)
    mods_a, mods_d = list(a.mods), list(d.mods)
    if ga[1]:
        mods_a.append((f"Général {ga[0]} : {ga[1]} (puissance x{_fmt(1 + GENERAL_STEP * ga[1])})", "+"))
    if gd[1]:
        mods_d.append((f"Général {gd[0]} : {gd[1]} (puissance x{_fmt(1 + GENERAL_STEP * gd[1])})", "+"))
    bt = Battle(
        uid=uid, hex=h, attackers=[b.id for b in a.bands], defenders=[b.id for b in d.bands], started=state.tick_count,
        hunted=hunted, village=bool(defender.village), morale_a=a.morale, morale_d=d.morale,
        start_a=max(1e-6, a.total_start()), start_d=max(1e-6, d.total_start()),
        pop0={b.id: b.population for b in a.bands + d.bands},
        mods_a=[list(m) for m in mods_a], mods_d=[list(m) for m in mods_d],
        general_a=[ga[0], ga[1]], general_d=[gd[0], gd[1]],
        morale0_a=a.morale, morale0_d=d.morale,
        units0={b.id: [list(u) for u in b.units] for b in a.bands + d.bands if b.kind == "armee"},
    )
    from src.kora.types import OrderKind, stay_order

    # Intercepte : le defenseur marchait lui-meme a l'attaque (ou une troupe
    # loin de chez elle).
    if defender.order.kind is OrderKind.MARCH_TO_BAND or (defender.kind == "armee" and not defender.homebound):
        bt.intercepted = "d"
    for b in a.bands + d.bands:
        if b.position == h and not b.village:
            b.path = []
            b.order = stay_order()
    state.battles.append(bt)
    return bt


def join(state, bt, band: Band, attacker: bool) -> None:
    """Des renforts arrivent sur la case : ils entrent dans la bataille."""
    side = bt.attackers if attacker else bt.defenders
    if band.id in bt.attackers or band.id in bt.defenders:
        return
    side.append(band.id)
    bt.pop0[band.id] = band.population
    if attacker:
        bt.start_a += fighters_now(band, True)
    else:
        bt.start_d += fighters_now(band, False)
    from src.kora.types import stay_order

    band.path = []
    band.order = stay_order()


def _seed_day(state, bt) -> int:
    return (bt.started * 1_000_003 + bt.uid * 7919 + bt.day * 104_729 + 17) & 0x7FFFFFFF


def _hits(state, bt, side: Side, hit: float, prudent: bool) -> tuple[int, int]:
    """Les coups recus par un camp : morts et blesses, repartis entre ses
    bandes selon leur part du combat."""
    from src.kora import population

    if prudent:
        hit *= 0.9
    weights = {b.id: side.now[b.id] * side.quality[b.id] for b in side.bands}
    total = sum(weights.values())
    if total <= 0 or hit <= 0:
        return 0, 0
    dead_all = hurt_all = 0
    for b in side.bands:
        share = hit * weights[b.id] / total
        share = min(share, side.now[b.id])
        dead = int(math.floor(share * KILLED_SHARE + 0.5))
        hurt = int(math.floor(share - dead + 0.5))
        if b.kind == "armee":
            dead = min(dead, b.population - b.wounded)
            _kill(b, dead)
        else:
            dead = population.kill_fighters(b, dead)
        hurt = population.wound(b, hurt)
        bt.killed[b.id] = bt.killed.get(b.id, 0) + dead
        bt.hurt[b.id] = bt.hurt.get(b.id, 0) + hurt
        dead_all += dead
        hurt_all += hurt
    return dead_all, hurt_all


def day(state, bt) -> bool:
    """Un jour de bataille. Rend True si elle est finie."""
    from src.kora import units

    if bt.outcome:
        return True
    a, d = _now(state, bt, True), _now(state, bt, False)
    if not a.bands or not d.bands or a.total() <= 0 or d.total() <= 0:
        _end(state, bt, a, d, a if (not a.bands or a.total() <= 0) else d, "deroute")
        return True
    rng = random.Random(_seed_day(state, bt))
    volley = units.VOLLEY if bt.day == 0 else units.VOLLEY_LATER
    ga, gd = 1.0 + GENERAL_STEP * bt.general_a[1], 1.0 + GENERAL_STEP * bt.general_d[1]
    pa, pd = a.power(volley) * ga, d.power(volley) * gd
    fa = 1.0 - FORTUNE / 2 + FORTUNE * rng.random()
    fd = 1.0 - FORTUNE / 2 + FORTUNE * rng.random()
    hit_d = min(d.total(), pa * DAY_KILL * fa / (math.sqrt(d.cover) * d.toughness()))
    hit_a = min(a.total(), pd * DAY_KILL * fd / (math.sqrt(a.cover) * a.toughness()))
    prudent_a = a.main.leader is not None and "prudent" in a.main.leader.traits
    prudent_d = d.main.leader is not None and "prudent" in d.main.leader.traits
    kd, wd = _hits(state, bt, d, hit_d, prudent_d)
    ka, wa = _hits(state, bt, a, hit_a, prudent_a)
    bt.morale_d = max(0.0, bt.morale_d - SHOCK * (kd + wd) / bt.start_d - PRESSURE * max(0.0, min(MAX_RATIO, pa / max(0.1, pd)) - 1.0))
    bt.morale_a = max(0.0, bt.morale_a - SHOCK * (ka + wa) / bt.start_a - PRESSURE * max(0.0, min(MAX_RATIO, pd / max(0.1, pa)) - 1.0))
    # Les demoralises fuient.
    ra = _flee(state, bt, _now(state, bt, True), bt.morale_a, rng)
    rd = _flee(state, bt, _now(state, bt, False), bt.morale_d, rng)
    bt.day += 1
    bt.days.append({"ka": ka, "wa": wa, "kd": kd, "wd": wd, "ma": round(bt.morale_a, 1), "md": round(bt.morale_d, 1),
                    "fa": round(fa, 2), "fd": round(fd, 2), "ra": ra, "rd": rd})
    a, d = _now(state, bt, True), _now(state, bt, False)
    _ai_retreat(state, bt, a, d)
    if bt.morale_a < ROUT or bt.morale_d < ROUT or a.total() <= 0 or d.total() <= 0:
        broken = a if (a.total() <= 0 or (d.total() > 0 and bt.morale_a <= bt.morale_d)) else d
        _end(state, bt, a, d, broken, "deroute")
        return True
    if bt.retreat:
        _end(state, bt, a, d, a if bt.retreat == "a" else d, "retraite")
        return True
    if bt.day >= MAX_DAYS:
        broken = a if a.power() * max(1.0, bt.morale_a) <= d.power() * max(1.0, bt.morale_d) else d
        _end(state, bt, a, d, broken, "retraite")
        return True
    return False


def _flee(state, bt, side: Side, morale: float, rng) -> int:
    """Sous FLEE_MORALE, une part des combattants s'enfuit (plus le moral est
    bas, plus ils sont nombreux ; jamais tous, pas chaque jour pareil)."""
    from src.kora import population, villages

    if morale >= FLEE_MORALE or not side.bands:
        return 0
    share = FLEE_RATE * (FLEE_MORALE - morale) / FLEE_MORALE * (0.5 + rng.random())
    gone = 0
    for b in side.bands:
        n = int(math.floor(side.now[b.id] * share))
        if n <= 0:
            continue
        if b.kind == "armee":
            # Des deserteurs : ils rentrent chez eux.
            n = min(n, b.population - b.wounded - 1)
            if n <= 0:
                continue
            home = villages.home_of(state, b)
            _kill(b, n)
            band = villages.band_of(state, home) if home is not None else None
            if band is not None:
                population.add(band, n, "hommes")
        else:
            bt.fled[b.id] = bt.fled.get(b.id, 0) + n
        gone += n
    return gone


def _side_tribes(state, ids) -> set:
    return {state.bands[b].tribe_id for b in ids if b in state.bands}


def _ai_retreat(state, bt, a: Side, d: Side) -> None:
    """L'IA se replie quand elle perd et n'a rien a perdre : elle n'est pas
    au mur de son village, et elle est loin de chez elle, ou interceptee,
    ou c'est une troupe ; ou son moral s'effondre."""
    from src.kora import sites

    if bt.retreat or bt.outcome:
        return
    for side, key, ids in ((a, "a", bt.attackers), (d, "d", bt.defenders)):
        if not side.bands or any(sim.is_human(state, t) for t in _side_tribes(state, ids)):
            continue
        if any(b.village for b in side.bands):
            continue
        other = d if side is a else a
        mine_m = bt.morale_a if key == "a" else bt.morale_d
        their_m = bt.morale_d if key == "a" else bt.morale_a
        ratio = side.power() * max(1.0, mine_m) / max(0.1, other.power() * max(1.0, their_m))
        if ratio >= AI_LOSING:
            continue
        main = side.bands[0]
        homes = [s.hex for s in sites.of_tribe(state, main.tribe_id) if s.kind in ("village", "camp")]
        far = not homes or min(state.world.distance(h, main.position) for h in homes) > AI_FAR
        # Rien a perdre : l'attaquant (il peut renoncer), une troupe, une bande
        # interceptee en marche, ou loin de chez elle sans familles a couvrir.
        families = main.kind != "armee" and key == "d"
        nothing = key == "a" or main.kind == "armee" or bt.intercepted == key or (far and not families)
        # Un clan qui couvre ses familles ne cede qu'au bord de la deroute.
        if nothing or mine_m < ROUT + 7:
            bt.retreat = key
            return


def advance(state, days: int, humans: bool) -> None:
    """Faire avancer les batailles de `days` jours (humans : aussi celles
    d'un joueur)."""
    for bt in sorted(battles(state), key=lambda b: b.uid):
        if bt.outcome or (not humans and involves_human(state, bt)):
            continue
        for _ in range(days):
            if day(state, bt):
                break
    state.battles = [bt for bt in battles(state) if not bt.outcome]


def ask_retreat(state, tid: int, band_id: int) -> str:
    """Un joueur demande le repli de son camp (a la fin du jour)."""
    bt = battle_of(state, band_id)
    if bt is None:
        return "Pas de bataille ici"
    a_tribe = state.bands[bt.attackers[0]].tribe_id if bt.attackers and bt.attackers[0] in state.bands else 0
    side = "a" if any(state.bands[b].tribe_id == tid for b in bt.attackers if b in state.bands) else "d"
    if side == "d" and bt.village and any(state.bands[b].village for b in bt.defenders if b in state.bands):
        return "Un village ne se replie pas"
    bt.retreat = side
    del a_tribe
    return "Repli ordonné : les vôtres se retirent à la fin du jour."


def _end(state, bt, a: Side, d: Side, broken: Side, outcome: str) -> None:
    """La fin de la bataille : poursuite, repli, butin, village pris."""
    from src.kora import chiefdom, diplo, population

    h = bt.hex
    lose, win = (a, d) if broken is a else (d, a)
    winner = win.main or _alive(state, bt.defenders if broken is a else bt.attackers)[:1] or None
    if isinstance(winner, list):
        winner = winner[0] if winner else None
    loser = lose.main or next(iter(_alive(state, bt.attackers if broken is a else bt.defenders)), None)
    bt.outcome = outcome
    if winner is None or loser is None:
        return
    before = dict(bt.pop0)
    on_hex = [b for b in lose.bands if b.position == h and b.population > 0]
    encircled = False
    pursuit = 0
    village = bool(loser.village)
    for b in on_hex:
        if b.village:
            continue
        fled = sim._retreat(state, b, winner)
        if b is loser:
            encircled = not fled
    if not village and lose.bands:
        rate = pursuit_rate(state, win, lose, h, outcome, encircled)
        still = lose.now.get(loser.id, 0.0)
        caught = int(math.floor(rate * still + 0.5))
        if loser.kind == "armee":
            caught = min(caught, loser.population)
            _kill(loser, caught)
        else:
            caught = population.kill_fighters(loser, caught)
            civilians = max(0, loser.population - int(population.men_force(loser)))
            taken = int(math.floor(rate * FAMILIES_CAUGHT * civilians + 0.5))
            caught += population.kill(loser, taken)
        pursuit = caught
    # Les blesses laisses sur le terrain.
    for b in lose.bands:
        if b.position != h or b.wounded <= 0:
            continue
        gone = population.lose_wounded(b, int(math.floor(b.wounded * WOUNDED_LOST.get(outcome, 0.3) + 0.5)))
        if b is loser:
            pursuit += gone
    wiped = loser.population < WIPE_MIN
    fit = loser.population - loser.wounded
    if loser.kind == "armee" and outcome == "deroute" and fit < ARMY_BROKEN * before.get(loser.id, loser.population):
        wiped = True
    if loser.kind != "armee" and not village and population.men_force(loser) < 1 and loser.population < 3 * WIPE_MIN:
        wiped = True
    loot = loser.stock if (wiped and not village) else float(math.floor(loser.stock * LOOT))
    loser.stock -= loot
    winner.stock = min(sim.stock_max(winner, state), winner.stock + loot)
    building = ""
    scattered = 0
    final = outcome
    if wiped and not village:
        if loser.kind != "armee" and loser.population > 0:
            kin = _nearest_kin(state, loser)
            if kin is not None:
                scattered = loser.population
                population.mix(kin, loser)
                kin.population += scattered
        loser.population = 0
        loser.retreating = False
        loser.path = []
        final = "aneanti"
    elif village:
        # Le village est pris : on ne tue pas ses familles. Le vainqueur
        # choisit : le soumettre (tributaire) ou le piller (chiefdom.py).
        loser.shield_until = state.tick_count + VILLAGE_SHIELD
        chiefs.battle_death(state, loser)
        final = "pris"
        site_id = loser.village
        if winner.tribe_id in state.tribes and loser.tribe_id in state.tribes:
            building = chiefdom.village_taken(state, winner, loser, site_id)
    else:
        chiefs.battle_death(state, loser)
    if loser.population <= 0:
        loser.shield_until = state.tick_count + sim.RETREAT_MIN_SHIELD
    # Le journal, le prestige, les relations, la marque de bataille.
    attacker = state.bands.get(bt.attackers[0]) if bt.attackers else None
    defender = state.bands.get(bt.defenders[0]) if bt.defenders else None
    report = _battle_report(state, bt, a, d, before, win is a, final, wiped, encircled, pursuit, loot, building)
    if scattered:
        side = report["attacker" if lose is a else "defender"]
        side["lost"] -= scattered
        report["scattered"] = scattered
        report["headline"] = f"La bande des {side['name']} est dispersée"
    w_loss = sum(before.get(b, 0) - (state.bands[b].population if b in state.bands else 0) for b in (bt.attackers if win is a else bt.defenders))
    l_loss = sum(before.get(b, 0) - (state.bands[b].population if b in state.bands else 0) for b in (bt.defenders if win is a else bt.attackers)) - scattered
    res = Result(
        winner=winner, loser=loser,
        winner_before=sum(before.get(b, 0) for b in (bt.attackers if win is a else bt.defenders)),
        loser_before=sum(before.get(b, 0) for b in (bt.defenders if win is a else bt.attackers)),
        winner_loss=w_loss, loser_loss=l_loss, loot=loot, wiped=wiped, outcome=final, report=report, building=building,
        engaged={b for b in bt.attackers + bt.defenders},
    )
    bt.result = res
    if attacker is not None and defender is not None:
        sim.after_battle(state, attacker, defender, h, res, bt.hunted)
    del diplo


def fight(state, attacker: Band, defender: Band, h) -> Result:
    """Toute une bataille d'un coup, jour apres jour (essais, et ce que la
    semaine resout sans joueur)."""
    bt = start(state, attacker, defender, h, sim._hunts(attacker, defender))
    while not day(state, bt):
        pass
    state.battles = [b for b in battles(state) if not b.outcome]
    return bt.result


def _kill(band: Band, dead: int) -> None:
    if dead <= 0:
        return
    if band.kind == "armee":
        from src.kora import units

        units.remove(band, dead)
    else:
        band.population = max(0, band.population - dead)


def _nearest_kin(state, band: Band):
    best, best_d = None, SCATTER_RANGE + 1
    for other in state.bands.values():
        if other.id == band.id or other.tribe_id != band.tribe_id or other.population <= 0 or other.kind == "armee":
            continue
        d = state.world.distance(other.position, band.position)
        if d < best_d or (d == best_d and best is not None and other.id < best.id):
            best, best_d = other, d
    return best


# --- le rapport -------------------------------------------------------------------------


def _kind(band: Band) -> str:
    if band.kind == "armee":
        return "troupe"
    if band.village:
        return "village"
    return "clan"


def place_of(state, h) -> str:
    from src.kora import villages

    best = None
    for site in state.sites.values():
        if site.kind != "village":
            continue
        dist = state.world.distance(site.hex, h)
        if dist <= 3 and (best is None or dist < best[0]):
            best = (dist, villages.name(site))
    if best is not None:
        return f"près de {best[1]}" if best[0] else f"à {best[1]}"
    return PLACE.get(state.world.terrain(h), "")


def _side_report(state, bt, side: Side, ids: list, before: dict, pursuit: int, key: str) -> dict:
    from src.kora import units

    first = next((state.bands[b] for b in ids if b in state.bands), None)
    main = side.main or first
    tid = main.tribe_id if main is not None else 0
    tribe = state.tribes.get(tid)
    lead = main.leader.name if main is not None and main.leader is not None else ""
    now = {b: state.bands[b].population if b in state.bands else 0 for b in ids}
    general = bt.general_a if key == "a" else bt.general_d
    out = {
        "tribe": tid,
        "name": tribe.name if tribe else "?",
        "kind": _kind(main) if main is not None else "clan",
        "leader": lead,
        "general": list(general),
        "bands": len(ids),
        "fighters": round(bt.start_a if key == "a" else bt.start_d),
        "fighters_left": round(sum(fighters_now(state.bands[b], key == "a") for b in ids if b in state.bands and state.bands[b].population > 0)),
        "pop": before.get(ids[0], 0) if ids else 0,
        "left": now.get(ids[0], 0) if ids else 0,
        "lost": sum(before.get(b, 0) - now[b] for b in ids),
        "killed": sum(bt.killed.get(b, 0) for b in ids),
        "wounded": sum(bt.hurt.get(b, 0) for b in ids),
        "fled": sum(d.get("r" + key, 0) for d in bt.days),
        "pursuit": pursuit,
        "power": round(sum(side.start[b.id] * side.quality[b.id] for b in side.bands) * math.sqrt(side.cover), 1) if side.bands else 0.0,
        "hits": [d["k" + key] + d["w" + key] for d in bt.days],
        "dead": [d["k" + key] for d in bt.days],
        "fortune": [d["f" + key] for d in bt.days],
        "mods": [list(m) for m in (bt.mods_a if key == "a" else bt.mods_d)],
    }
    out["morale"] = [round(bt.morale0_a if key == "a" else bt.morale0_d, 1)] + [d["m" + key] for d in bt.days]
    old = bt.units0.get(main.id) if main is not None else None
    if old:
        live = {(u[0], u[2]): u[1] for u in main.units} if main.population > 0 else {}
        out["units"] = [[units.UNITS[t].name if t in units.UNITS else t, men, live.get((t, home), 0)] for t, men, home in old]
    return out


def _battle_report(state, bt, a, d, before, attacker_won, outcome, wiped, encircled, pursuit, loot, building) -> dict:
    loser = d if attacker_won else a
    rep = {
        "place": place_of(state, bt.hex),
        "attacker": _side_report(state, bt, a, bt.attackers, before, 0 if attacker_won else pursuit, "a"),
        "defender": _side_report(state, bt, d, bt.defenders, before, pursuit if attacker_won else 0, "d"),
        "rounds": bt.day,
        "days": bt.day,
        "winner": "attacker" if attacker_won else "defender",
        "outcome": outcome,
        "wiped": wiped,
        "encircled": encircled,
        "loot": round(loot),
        "building": building,
    }
    rep["headline"] = headline(rep, loser.main)
    return rep


def headline(rep: dict, loser: Band | None = None) -> str:
    side = rep["defender"] if rep["winner"] == "attacker" else rep["attacker"]
    name = side["name"]
    what = {"troupe": "La troupe", "village": "Le village", "clan": "La bande"}.get(side["kind"], "La bande")
    out = rep["outcome"]
    if out == "aneanti":
        return f"{what} des {name} est anéantie"
    if out == "rase":
        return f"Le village des {name} est rasé"
    if out == "pris":
        return f"Le village des {name} est pris"
    if out == "pille":
        return f"Le village des {name} est pillé"
    if out == "retraite":
        return f"Les {name} se retirent en bon ordre"
    return f"Déroute des {name}"


def log_suffix(state, res: Result, me: int | None = None) -> str:
    """Ce que le journal du joueur `me` ajoute au texte du raid."""
    if res.outcome == "aneanti":
        mine = res.loser.tribe_id == (sim.PLAYER_TRIBE_ID if me is None else me)
        left = res.report.get("scattered", 0)
        if left:
            return f" La bande est dispersée ; {left} survivants rejoignent les leurs."
        what = "troupe" if res.loser.kind == "armee" else "bande"
        return f" Votre {what} est anéantie." if mine else " Ils sont anéantis !"
    if res.outcome == "rase":
        return " Le village est rasé."
    if res.outcome == "pris":
        return " Le village est pris."
    if res.report.get("encircled"):
        return " Encerclés, ils ont été massacrés dans la fuite."
    return ""


def odds(state, band: Band, prey: Band) -> tuple[float, str]:
    """Rapport de force estime d'un raid de `band` sur `prey` (fiche de
    bande) : (rapport, mot)."""
    mine = sim.side_force(state, band)
    theirs = sim.defense_force(state, prey)
    ratio = mine / max(0.1, theirs)
    if ratio >= 2.0:
        word = "ecrasant"
    elif ratio >= 1.3:
        word = "favorable"
    elif ratio >= 0.85:
        word = "incertain"
    else:
        word = "defavorable"
    return ratio, word


# --- sauvegarde -----------------------------------------------------------------------------


def to_json(bt) -> dict:
    return {
        "uid": bt.uid, "hex": [bt.hex.q, bt.hex.r], "attackers": list(bt.attackers), "defenders": list(bt.defenders),
        "started": bt.started, "hunted": bt.hunted, "village": bt.village, "day": bt.day,
        "morale_a": bt.morale_a, "morale_d": bt.morale_d, "start_a": bt.start_a, "start_d": bt.start_d,
        "pop0": [[k, v] for k, v in sorted(bt.pop0.items())],
        "killed": [[k, v] for k, v in sorted(bt.killed.items())],
        "hurt": [[k, v] for k, v in sorted(bt.hurt.items())],
        "days": list(bt.days), "mods_a": list(bt.mods_a), "mods_d": list(bt.mods_d),
        "general_a": list(bt.general_a), "general_d": list(bt.general_d), "retreat": bt.retreat,
        "morale0_a": bt.morale0_a, "morale0_d": bt.morale0_d,
        "units0": [[k, v] for k, v in sorted(bt.units0.items())],
        "fled": [[k, v] for k, v in sorted(bt.fled.items())], "intercepted": bt.intercepted,
    }


def from_json(d: dict):
    from src.kora.types import Hex

    try:
        return Battle(
            uid=int(d["uid"]), hex=Hex(int(d["hex"][0]), int(d["hex"][1])),
            attackers=[int(x) for x in d.get("attackers", [])], defenders=[int(x) for x in d.get("defenders", [])],
            started=int(d.get("started", 0)), hunted=bool(d.get("hunted", False)), village=bool(d.get("village", False)),
            day=int(d.get("day", 0)), morale_a=float(d.get("morale_a", 0.0)), morale_d=float(d.get("morale_d", 0.0)),
            start_a=float(d.get("start_a", 1.0)), start_d=float(d.get("start_d", 1.0)),
            pop0={int(k): int(v) for k, v in d.get("pop0", [])},
            killed={int(k): int(v) for k, v in d.get("killed", [])},
            hurt={int(k): int(v) for k, v in d.get("hurt", [])},
            days=[dict(x) for x in d.get("days", [])],
            mods_a=[list(m) for m in d.get("mods_a", [])], mods_d=[list(m) for m in d.get("mods_d", [])],
            general_a=list(d.get("general_a", ["", 0])), general_d=list(d.get("general_d", ["", 0])),
            retreat=str(d.get("retreat", "")),
            morale0_a=float(d.get("morale0_a", 0.0)), morale0_d=float(d.get("morale0_d", 0.0)),
            units0={int(k): [list(u) for u in v] for k, v in d.get("units0", [])},
            fled={int(k): int(v) for k, v in d.get("fled", [])}, intercepted=str(d.get("intercepted", "")),
        )
    except (KeyError, ValueError, TypeError):
        return None

