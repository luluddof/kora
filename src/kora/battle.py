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
# Un village attaque : 60 % des habitants tiennent les murs (un clan en
# marche : sim.CLAN_SHARE).
VILLAGE_SHARE = 0.6
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
FAMILIES_CAUGHT = 0.3
# Un clan aneanti : ses derniers survivants rejoignent la bande de leur
# peuple la plus proche, a cette distance au plus (une troupe, non).
SCATTER_RANGE = 16
WIPE_MIN = 6
ARMY_BROKEN = 0.3
LOOT = 0.5
VILLAGE_SHIELD = 6
PLACE = {
    _T.PLAINE: "dans la plaine",
    _T.VALLEE: "dans la vallee",
    _T.STEPPE: "dans la steppe",
    _T.FORET: "en foret",
    _T.COLLINE: "sur les collines",
    _T.MONTAGNE: "dans la montagne",
    _T.SOMMET: "sur les hauteurs",
    _T.COTE: "sur la cote",
    _T.DESERT: "dans le desert",
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
        parts.append(("Defend les siens", KIN_MORALE))
    if band.village and not attacker:
        parts.append(("Defend son village", VILLAGE_MORALE))
        from src.kora import villages

        site = villages.site_of(state, band)
        if site is not None:
            s = round((villages.stability(state, site, band) - villages.STABILITY_BASE) / 5.0)
            if s:
                parts.append(("Village stable" if s > 0 else "Village agite", s))
    if influence.is_home(state.world, h, band.tribe_id):
        parts.append(("Sur ses terres", HOME_MORALE))
    # Le prestige compte deja dans la valeur des combattants : ici, un peu.
    p = max(-5.0, min(8.0, (tribe.prestige - 40) / 6.0))
    if abs(p) >= 1:
        parts.append(("Prestige", round(p)))
    if band.famine_in_period:
        parts.append(("Affames", HUNGER_MORALE))
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
    """Combattants d'une bande dans cette bataille : un village attaque
    defend ses murs avec presque tout le monde."""
    if band.village and not attacker and band.kind != "armee":
        return band.population * VILLAGE_SHARE
    return sim.fighters(band)


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


def simulate(state, attacker: Band, defender: Band, h):
    """Les passes d'armes, sans rien changer au monde : (camp attaquant,
    camp defenseur, passes, pertes par bande, vaincu, issue)."""
    rng = random.Random(_seed(state, attacker, defender))
    a = _side(state, attacker, True, h)
    d = _side(state, defender, False, h)
    lost: dict[int, float] = {}
    rounds = [{"a": 0.0, "d": 0.0, "ma": round(a.morale, 1), "md": round(d.morale, 1)}]
    a_start, d_start = max(1e-6, a.total_start()), max(1e-6, d.total_start())
    from src.kora import units

    for rnd in range(ROUNDS):
        # Premiere passe : la volee des tireurs, avant le choc.
        volley = units.VOLLEY if rnd == 0 else units.VOLLEY_LATER
        pa, pd = a.power(volley), d.power(volley)
        if pa <= 0 or pd <= 0:
            break
        hit_d = min(d.total(), pa * KILL * rng.uniform(0.85, 1.15) / (math.sqrt(d.cover) * d.toughness()))
        hit_a = min(a.total(), pd * KILL * rng.uniform(0.85, 1.15) / (math.sqrt(a.cover) * a.toughness()))
        _spread(d, hit_d, lost)
        _spread(a, hit_a, lost)
        d.morale = max(0.0, d.morale - SHOCK * hit_d / d_start - PRESSURE * max(0.0, min(MAX_RATIO, pa / pd) - 1.0))
        a.morale = max(0.0, a.morale - SHOCK * hit_a / a_start - PRESSURE * max(0.0, min(MAX_RATIO, pd / pa) - 1.0))
        rounds.append({"a": round(hit_a, 1), "d": round(hit_d, 1), "ma": round(a.morale, 1), "md": round(d.morale, 1)})
        if a.morale < ROUT or d.morale < ROUT or a.total() <= 0 or d.total() <= 0:
            break
    if a.morale < ROUT or d.morale < ROUT or a.total() <= 0 or d.total() <= 0:
        # Deroute : le plus ebranle cede (a egalite, l'attaquant).
        broken = a if (a.total() <= 0 or (d.total() > 0 and a.morale <= d.morale)) else d
        outcome = "deroute"
    else:
        # Personne ne cede : le moins solide se retire (a egalite, le
        # defenseur tient).
        broken = a if a.power() * max(1.0, a.morale) <= d.power() * max(1.0, d.morale) else d
        outcome = "retraite"
    return a, d, rounds, lost, broken, outcome, rng


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


def fight(state, attacker: Band, defender: Band, h) -> Result:
    """Livre la bataille et en applique l'issue : pertes, poursuite, repli
    ou pillage, butin. Le prestige, le journal et la diplomatie restent a
    sim.resolve_raids."""
    a, d, rounds, lost, broken, outcome, rng = simulate(state, attacker, defender, h)
    lose, win = (a, d) if broken is a else (d, a)
    loser, winner = lose.main, win.main
    before = {b.id: b.population for b in a.bands + d.bands}
    from src.kora import units

    units_before = {b.id: [list(u) for u in units.normalize(b)] for b in a.bands + d.bands if b.kind == "armee"}
    # Morts des passes d'armes (dans une troupe : d'abord les exposes).
    for b in a.bands + d.bands:
        dead = int(math.floor(lost.get(b.id, 0.0) + 0.5))
        _kill(b, dead)
    if loser.population >= 1 and before[loser.id] - loser.population < 1:
        _kill(loser, 1)
    # Les vaincus sur la case partent avec leur bande ; les renforts venus
    # d'a cote rentrent chez eux.
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
    if not village:
        rate = pursuit_rate(state, win, lose, h, outcome, encircled)
        still = lose.now.get(loser.id, 0.0)
        families = 0.0 if loser.kind == "armee" else max(0.0, loser.population - still)
        pursuit = int(math.floor(rate * still + rate * FAMILIES_CAUGHT * families + 0.5))
        pursuit = min(loser.population, pursuit)
        _kill(loser, pursuit)
    wiped = loser.population < WIPE_MIN
    if loser.kind == "armee" and outcome == "deroute" and loser.population < ARMY_BROKEN * before[loser.id]:
        wiped = True
    # Butin : la moitie des vivres, tout si le vaincu est aneanti.
    loot = loser.stock if wiped else float(math.floor(loser.stock * LOOT))
    loser.stock -= loot
    winner.stock = min(sim.stock_max(winner, state), winner.stock + loot)
    building = ""
    scattered = 0
    if wiped:
        if loser.kind != "armee" and not village and loser.population > 0:
            kin = _nearest_kin(state, loser)
            if kin is not None:
                scattered = loser.population
                kin.population += scattered
        loser.population = 0
        loser.retreating = False
        loser.path = []
    elif village:
        from src.kora import villages

        building = villages.pillaged(state, loser, rng)
        loser.shield_until = state.tick_count + VILLAGE_SHIELD
        chiefs.battle_death(state, loser)
    else:
        chiefs.battle_death(state, loser)
    if loser.population <= 0:
        loser.shield_until = state.tick_count + sim.RETREAT_MIN_SHIELD
    engaged = {b.id for b in a.bands + d.bands if b.position == h}
    if wiped:
        final = "rase" if village else "aneanti"
    else:
        final = "pille" if village else outcome
    report = _report(state, a, d, rounds, before, winner is attacker, final, wiped, encircled, pursuit, loot, building, h)
    for key, side in (("attacker", a), ("defender", d)):
        old = units_before.get(side.main.id)
        if old:
            now = {(u[0], u[2]): u[1] for u in side.main.units} if side.main.population > 0 else {}
            report[key]["units"] = [
                [units.UNITS[t].name if t in units.UNITS else t, men, now.get((t, home), 0)] for t, men, home in old
            ]
    w_loss = sum(before[b.id] - b.population for b in win.bands)
    l_loss = sum(before[b.id] - b.population for b in lose.bands) - scattered
    if scattered:
        # Les survivants ne sont pas morts : ils ont rejoint les leurs.
        side = report["attacker" if lose is a else "defender"]
        side["lost"] -= scattered
        report["scattered"] = scattered
        report["headline"] = f"La bande des {side['name']} est dispersee"
    return Result(
        winner=winner,
        loser=loser,
        winner_before=sum(before[b.id] for b in win.bands),
        loser_before=sum(before[b.id] for b in lose.bands),
        winner_loss=w_loss,
        loser_loss=l_loss,
        loot=loot,
        wiped=wiped,
        outcome=final,
        report=report,
        building=building,
        engaged=engaged,
    )


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
        return f"pres de {best[1]}" if best[0] else f"a {best[1]}"
    return PLACE.get(state.world.terrain(h), "")


def _side_report(state, side: Side, before: dict, pursuit: int, rounds: list, key: str) -> dict:
    tribe = state.tribes.get(side.main.tribe_id)
    lead = side.main.leader.name if side.main.leader is not None else ""
    return {
        "tribe": side.main.tribe_id,
        "name": tribe.name if tribe else "?",
        "kind": _kind(side.main),
        "leader": lead,
        "bands": len(side.bands),
        "fighters": round(side.total_start()),
        "fighters_left": round(side.total()),
        "pop": before[side.main.id],
        "left": side.main.population,
        "lost": sum(before[b.id] - b.population for b in side.bands),
        "pursuit": pursuit,
        "power": round(sum(side.start[b.id] * side.quality[b.id] for b in side.bands) * math.sqrt(side.cover), 1),
        "morale": [r["m" + key] for r in rounds],
        "hits": [r[key] for r in rounds[1:]],
        "mods": [list(m) for m in side.mods],
    }


def _report(state, a, d, rounds, before, attacker_won, outcome, wiped, encircled, pursuit, loot, building, h) -> dict:
    loser = d if attacker_won else a
    rep = {
        "place": place_of(state, h),
        "attacker": _side_report(state, a, before, 0 if attacker_won else pursuit, rounds, "a"),
        "defender": _side_report(state, d, before, pursuit if attacker_won else 0, rounds, "d"),
        "rounds": len(rounds) - 1,
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
        return f"{what} des {name} est aneantie"
    if out == "rase":
        return f"Le village des {name} est rase"
    if out == "pille":
        return f"Le village des {name} est pille"
    if out == "retraite":
        return f"Les {name} se retirent en bon ordre"
    return f"Deroute des {name}"


def log_suffix(state, res: Result) -> str:
    """Ce que le journal ajoute au texte du raid."""
    if res.outcome == "aneanti":
        mine = res.loser.tribe_id == sim.PLAYER_TRIBE_ID
        left = res.report.get("scattered", 0)
        if left:
            return f" La bande est dispersee ; {left} survivants rejoignent les leurs."
        what = "troupe" if res.loser.kind == "armee" else "bande"
        return f" Votre {what} est aneantie." if mine else " Ils sont aneantis !"
    if res.outcome == "rase":
        return " Le village est rase."
    if res.report.get("encircled"):
        return " Encercles, ils ont ete massacres dans la fuite."
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
