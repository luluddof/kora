"""Diplomatie : contacts, relations, pactes, propositions, diffusion.

Relation entre deux peuples en contact : de -100 a +100, somme de raisons
lisibles (Mod), chacune avec sa valeur et son usure mensuelle, plus des
raisons "du moment" recalculees (terres qui se chevauchent, pactes,
ennemi commun). La relation est la meme dans les deux sens ; le libelle
d'une raison depend de qui l'a causee (actor).

Pactes : treve (2 ans), alliance (sans fin), tribut (2 ans, le payeur
donne une semaine de vivres par saison). Raider un peuple avec qui l'on
a un pacte : trahison.

LA GUERRE DECLAREE : deux peuples qui connaissent tous deux la diplomatie
(Dons et palabres : le bonus "diplomacy") sont EN PAIX par defaut ; pour se
battre, l'un doit DECLARER LA GUERRE (action "guerre" : un pacte "guerre"
entre les deux pays - tributaires et confederes compris -, et les allies de
l'attaque entrent en guerre a ses cotes). Sans declaration, ni le joueur ni
l'IA ne peuvent les attaquer, et leurs bandes ne se battent pas en se
croisant. Une treve y met fin ; trois ans sans combat, elle s'eteint.
Avec un peuple qui n'a pas la diplomatie, rien ne change (raids libres).

Propositions : evaluate() rend le score de l'autre peuple et ses raisons
(le panneau les montre AVANT de cliquer), perform() l'execute.
Diffusion : un savoir connu d'un voisin en contact (pas ennemi) s'apprend
plus vite, ses semaines vecues comptent double (tech.py).
N'importe ni pygame ni render.
"""

from __future__ import annotations

from dataclasses import dataclass, field

from src.kora import approach, battle, chiefdom, chiefs, confed, events, goods, influence, money, tech
from src.kora.log import LogKind
# Les donnees (contacts, relations, pactes, routes) : types.py.
from src.kora.types import Diplomacy, Mod, Pact, TradeRoute  # noqa: F401
from src.kora.types import stay_order
from src.kora.gamestate import PLAYER_TRIBE_ID, note
from src.kora.peoples import culture_of, living_tribe_ids
from src.kora.vision import is_visible
from src.kora.bands import gain_prestige, stock_max

CONTACT_RANGE = 16
NEIGHBOR_RANGE = 40
TRUCE_WEEKS = 104
TRIBUTE_WEEKS = 104
TRIBUTE_EVERY = 13
GIFT_RANGE = 30
GIFT_SIZES = (50, 150, 400)
# Les presents en sicles (money.py) : pas besoin d'une bande a cote, des
# envoyes les portent ; un peuple sans argent n'y voit que des parures
# (moitie moins).
PRESENT_SIZES = (5, 15, 40)
PRESENT_NO_MONEY = 0.5
AI_PRESENT = 5
INVITE_COST = 10
BETRAYAL_PRESTIGE = 10
DIFFUSE_NEIGHBOR = 0.35
DIFFUSE_ALLY = 0.70
DIFFUSE_CAP = 1.0
OFFER_COOLDOWN = 26

# key -> (vu par celui qui a agi, vu par l'autre, usure par mois)
MOD_TEXT = {
    "raid": ("Vous les avez attaqués", "Ils vous ont attaqués", 1.0),
    "accrochage": ("Accrochage", "Accrochage", 1.0),
    "cadeau": ("Vos cadeaux", "Leurs cadeaux", 1.0),
    "meme_souche": ("Même souche", "Même souche", 0.2),
    "separation": ("Séparation", "Séparation", 0.5),
    "trahison": ("Vous les avez trahis", "Ils vous ont trahis", 0.4),
    "reputation": ("Votre réputation de traître", "Leur réputation de traîtres", 0.3),
    "mariage": ("Mariages entre vos chefs", "Mariages entre vos chefs", 0.3),
    "pillage": ("Vous avez pillé leurs vivres", "Ils ont pillé vos vivres", 1.0),
    "tribut_refuse": ("Ils ont refusé votre tribut", "Vous avez refusé leur tribut", 0.8),
    "debauchage": ("Vous avez pris leurs gens", "Ils ont pris vos gens", 0.6),
    "rupture": ("Vous avez rompu un pacte", "Ils ont rompu un pacte", 0.6),
    "accueil": ("Vous les avez bien accueillis", "Ils vous ont bien accueillis", 0.8),
    "chasses": ("Vous les avez chassés", "Ils vous ont chassés", 0.8),
    "entraide": ("Entraide", "Entraide", 0.6),
    "echanges": ("Échanges réguliers", "Échanges réguliers", 0.3),
    "route_fermee": ("Vous avez fermé une de leurs routes", "Ils ont fermé une de vos routes", 0.5),
    "union_refusee": ("Union refusée", "Union refusée", 0.8),
    # Les situations (situations.py).
    "passage": ("Rivaux au grand passage", "Rivaux au grand passage", 0.5),
    "chasse_partagee": ("Vous leur avez laissé la chasse", "Ils vous ont laissé la chasse", 0.5),
    "rassemblement": ("Le rassemblement des clans", "Le rassemblement des clans", 0.3),
    "carrefour": ("Ils passent par vous", "Vous passez par eux", 0.3),
    "intimidation": ("Vous les avez menacés", "Ils vous ont menacés", 0.6),
    "domination": ("Vous dominez la vallée", "Ils dominent la vallée", 0.2),
    "monument": ("Vous les avez reçus au pied du monument", "Ils vous ont reçus au pied de leur monument", 0.3),
    "brade": ("Vous leur avez cédé vos surplus", "Ils vous ont cédé leurs surplus", 0.5),
    "soutien": ("Vous les avez soutenus dans l'effondrement", "Ils vous ont soutenus dans l'effondrement", 0.3),
    "soumis": ("Vous les avez soumis", "Ils vous ont soumis", 0.2),
    "revolte": ("Ils se sont révoltés", "Vous vous êtes révoltés", 0.3),
    "protection": ("Ils sont sous votre protection", "Vous êtes sous leur protection", 0.2),
    # Les grandes chefferies.
    "festin": ("Ils ont mangé à votre table", "Vous avez mangé à leur table", 0.4),
    "oblige": ("Vos dons les obligent", "Leurs dons vous obligent", 0.5),
    "freres": ("Un village né du vôtre", "Votre village est né du leur", 0.1),
    # La confederation (confed.py).
    "raid_confedere": ("Vous avez attaqué leurs confédérés", "Ils ont attaqué vos confédérés", 1.0),
    "raid_pays": ("Vous avez attaqué leur pays", "Ils ont attaqué votre pays", 1.0),
    "confed_refusee": ("Confédération refusée", "Confédération refusée", 0.8),
    # La guerre declaree.
    "guerre_declaree": ("Vous leur avez déclaré la guerre", "Ils vous ont déclaré la guerre", 0.5),
    "agresseur": ("Vous avez déclaré une guerre sans motif", "Ils ont déclaré une guerre sans motif", 0.3),
}


def pair(a: int, b: int) -> tuple[int, int]:
    return (a, b) if a < b else (b, a)


def _d(state) -> Diplomacy:
    d = getattr(state, "diplo", None)
    if d is None:
        d = Diplomacy()
        state.diplo = d
    return d


def copy_diplo(d: Diplomacy) -> Diplomacy:
    return Diplomacy(
        contacts=set(d.contacts),
        mods={k: [Mod(m.key, m.value, m.actor, m.year) for m in v] for k, v in d.mods.items()},
        pacts={k: [Pact(p.kind, p.since, p.until, p.payer, p.paid) for p in v] for k, v in d.pacts.items()},
        cooldown=dict(d.cooldown),
        casus=dict(d.casus),
        betrayed=dict(d.betrayed),
        raids=dict(d.raids),
        neighbors={k: list(v) for k, v in d.neighbors.items()},
        routes=[TradeRoute(**vars(r)) for r in d.routes],
    )


# --- contacts -------------------------------------------------------------------


def in_contact(state, a: int, b: int) -> bool:
    return a != b and pair(a, b) in _d(state).contacts


def contacts_of(state, tid: int) -> list[int]:
    out = []
    for a, b in _d(state).contacts:
        if a == tid and b in state.tribes:
            out.append(b)
        elif b == tid and a in state.tribes:
            out.append(a)
    return sorted(out)


def contact_count(state, tid: int) -> int:
    alive = _living(state)
    return sum(1 for t in contacts_of(state, tid) if t in alive)


def friend_count(state, tid: int) -> int:
    return sum(1 for t in contacts_of(state, tid) if relation(state, tid, t) >= 20)


def ally_count(state, tid: int) -> int:
    return sum(1 for t in contacts_of(state, tid) if allied(state, tid, t))


def _living(state) -> set[int]:
    return living_tribe_ids(state)


def make_contact(state, a: int, b: int, quiet: bool = False) -> bool:
    if a == b or a not in state.tribes or b not in state.tribes:
        return False
    key = pair(a, b)
    d = _d(state)
    if key in d.contacts:
        return False
    d.contacts.add(key)
    # Chaque joueur de la paire (deux, si deux joueurs se rencontrent).
    for player in [t for t in (a, b) if state.tribes[t].is_player]:
        if quiet:
            break
        other = b if player == a else a
        _note(state, LogKind.POLITIQUE, f"Premier contact avec les {state.tribes[other].name}.", to=player)
        found = gift_carrier(state, player, other)
        band_id = found[0].id if found is not None else next(
            (x.id for x in sorted(state.bands.values(), key=lambda x: x.id) if x.tribe_id == player), 0
        )
        events.hook(state, "contact", tribe_id=player, band_id=band_id, other=other)
    return True


def update_contacts(state) -> None:
    """Deux peuples dont des bandes se sont approchees (16 cases), ou dont
    les zones se touchent, se connaissent desormais."""
    alive = _living(state)
    bands = [b for b in sorted(state.bands.values(), key=lambda b: b.id) if b.population > 0]
    by_tribe: dict[int, list] = {}
    for b in bands:
        by_tribe.setdefault(b.tribe_id, []).append(b)
    tids = sorted(t for t in by_tribe if t in alive)
    d = _d(state)
    world = state.world
    for i, a in enumerate(tids):
        for b in tids[i + 1 :]:
            if (a, b) in d.contacts:
                continue
            if getattr(state, "overlap", {}).get((a, b), 0) > 0 or any(
                world.distance(x.position, y.position) <= CONTACT_RANGE
                for x in by_tribe[a]
                for y in by_tribe[b]
            ):
                make_contact(state, a, b)


# --- relation ---------------------------------------------------------------------


def add_mod(state, a: int, b: int, key: str, value: float, actor: int = 0) -> None:
    if a == b or a not in state.tribes or b not in state.tribes:
        return
    d = _d(state)
    k = pair(a, b)
    mods = d.mods.setdefault(k, [])
    same = next((m for m in mods if m.key == key and m.actor == actor), None)
    if same is not None and key in ("cadeau", "pillage", "raid", "accrochage", "entraide", "echanges"):
        # Les raisons de meme nature s'additionnent, avec un plafond.
        same.value = max(-60.0, min(40.0, same.value + value))
        same.year = state.clock.year
    elif same is not None:
        same.value = value if abs(value) > abs(same.value) else same.value
        same.year = state.clock.year
    else:
        mods.append(Mod(key, float(value), actor, state.clock.year))


def _pacts(state, a: int, b: int) -> list[Pact]:
    return _d(state).pacts.get(pair(a, b), [])


def has_pact(state, a: int, b: int, kind: str | None = None) -> bool:
    """Un pacte (kind None : un pacte de paix, pas la guerre)."""
    if kind is None:
        return any(p.kind != WAR for p in _pacts(state, a, b))
    return any(p.kind == kind for p in _pacts(state, a, b))


def allied(state, a: int, b: int) -> bool:
    return has_pact(state, a, b, "alliance")


WAR = "guerre"
# Sans combat entre les deux pays depuis ce temps, la guerre s'eteint.
WAR_FADE_WEEKS = 156
DECLARE_RELATION = -30
DECLARE_PRESTIGE = 5


def diplomatic(state, tid: int) -> bool:
    """Le peuple connait la diplomatie (on lui declare la guerre)."""
    tribe = state.tribes.get(tid)
    return tribe is not None and tech.bonuses(tribe).diplomacy


def needs_declaration(state, a: int, b: int) -> bool:
    """Entre eux, il faut declarer la guerre pour se battre."""
    return diplomatic(state, a) and diplomatic(state, b)


def declared_war(state, a: int, b: int) -> bool:
    return has_pact(state, a, b, WAR)


def at_peace(state, a: int, b: int) -> bool:
    """Treve, alliance, tribut ou accord commercial : pas de raid entre eux ;
    deux peuples qui ont la diplomatie sont en paix tant que la guerre n'est
    pas declaree."""
    if a == b:
        return True
    if declared_war(state, a, b):
        return False
    if has_pact(state, a, b):
        return True
    return needs_declaration(state, a, b)


def _base(state, a: int, b: int) -> list[tuple[str, float]]:
    """Raisons sans l'ennemi commun (qui a besoin des autres relations)."""
    d = _d(state)
    out: list[tuple[str, float]] = []
    for m in d.mods.get(pair(a, b), []):
        text = MOD_TEXT.get(m.key, (m.key, m.key, 1.0))
        label = text[0] if m.actor == a else text[1] if m.actor == b else text[0]
        out.append((label, m.value))
    shared = getattr(state, "overlap", {}).get(pair(a, b), 0)
    if shared and not allied(state, a, b):
        out.append(("Terres qui se chevauchent", -min(25.0, shared / 6.0)))
    for p in _pacts(state, a, b):
        if p.kind == WAR:
            out.append(("En guerre", -20.0))
        elif p.kind == "treve":
            out.append(("Trêve", 10.0))
        elif p.kind == "alliance":
            out.append(("Alliance", 25.0))
        elif p.kind == "tribut":
            out.append(("Tribut", -5.0))
        elif p.kind == "vassal":
            out.append(("Suzerain et tributaire", -8.0))
        elif p.kind == "commerce":
            out.append(("Accord commercial", 8.0))
        elif p.kind == confed.KIND:
            out.append(("Même confédération", 20.0))
    # Villages freres : la meme civilisation, ou suzerain et tributaire.
    if b in chiefdom.kin_of(state, a) or a in chiefdom.kin_of(state, b):
        out.append(("Villages frères", 15.0))
    for t in (a, b):
        chief = _chief_traits(state, t)
        if "querelleur" in chief:
            out.append(("Chef querelleur", -5.0))
        if "genereux" in chief:
            out.append(("Chef généreux", 3.0))
        if approach.of(state, t) == "conquerant":
            out.append(("Chef conquérant", -4.0))
    return out


def _chief_traits(state, tid: int) -> tuple:
    person = chiefs.chief_of(state, tid)
    return person.traits if person is not None else ()


def _clamp(v: float) -> float:
    return max(-100.0, min(100.0, v))


def base_relation(state, a: int, b: int) -> float:
    memo = getattr(state, "rel_memo", None)
    if memo is not None:
        key = ("b", a, b)
        hit = memo.get(key)
        if hit is None:
            hit = memo[key] = _clamp(sum(v for _l, v in _base(state, a, b)))
        return hit
    return _clamp(sum(v for _l, v in _base(state, a, b)))


class frozen_relations:
    """Le temps d'une phase ou aucune relation ne change (decisions de l'IA,
    apprentissage, voisinages du mois), on garde les relations calculees.
    Meme resultat, beaucoup moins de calcul quand les peuples sont nombreux."""

    def __init__(self, state):
        self.state = state
        self.owner = False

    def __enter__(self):
        if getattr(self.state, "rel_memo", None) is None:
            self.state.rel_memo = {}
            self.owner = True
        return self

    def __exit__(self, *exc):
        if self.owner:
            self.state.rel_memo = None
        return False


def reasons(state, a: int, b: int) -> list[tuple[str, float]]:
    """Raisons de la relation, vues par a, de la plus forte a la plus faible."""
    out = _base(state, a, b)
    if _common_enemy(state, a, b):
        out.append(("Ennemi commun", 10.0))
    out = [(label, v) for label, v in out if abs(v) >= 0.5]
    out.sort(key=lambda it: -abs(it[1]))
    return out


def _common_enemy(state, a: int, b: int) -> bool:
    for t in contacts_of(state, a):
        if t == b or not in_contact(state, b, t):
            continue
        if base_relation(state, a, t) <= -30 and base_relation(state, b, t) <= -30:
            return True
    return False


def relation(state, a: int, b: int) -> float:
    if a == b:
        return 100.0
    if not in_contact(state, a, b):
        return 0.0
    memo = getattr(state, "rel_memo", None)
    if memo is not None:
        hit = memo.get((a, b))
        if hit is not None:
            return hit
    total = base_relation(state, a, b)
    if _common_enemy(state, a, b):
        total += 10.0
    total = _clamp(total)
    if memo is not None:
        memo[(a, b)] = total
    return total


def level_of(rel: float) -> str:
    if rel <= -50:
        return "Ennemis"
    if rel <= -15:
        return "Hostiles"
    if rel < 15:
        return "Méfiants"
    if rel < 50:
        return "Cordiaux"
    return "Amis"


def level(state, a: int, b: int) -> str:
    if allied(state, a, b):
        return "Alliés"
    return level_of(relation(state, a, b))


def status_line(state, a: int, b: int) -> str:
    parts = []
    for p in _pacts(state, a, b):
        left = max(0, p.until - state.tick_count) if p.until else 0
        if p.kind == WAR:
            weeks = state.tick_count - p.since
            parts.append(f"En guerre (depuis {weeks} sem.)")
        elif p.kind == "treve":
            parts.append(f"Trêve ({left} sem.)")
        elif p.kind == "alliance":
            parts.append("Alliance")
        elif p.kind == "tribut":
            who = "ils vous paient" if p.payer == b else "vous payez"
            parts.append(f"Tribut : {who} ({left} sem.)")
        elif p.kind == "vassal":
            parts.append("Vos tributaires" if p.payer == b else "Vous êtes leurs tributaires")
        elif p.kind == "commerce":
            parts.append("Accord commercial")
        elif p.kind == confed.KIND:
            parts.append("Confédérés")
    return " · ".join(parts)


# --- raids -----------------------------------------------------------------------


def on_fight(state, attacker: int, defender: int, attacker_won: bool, hunted: bool) -> None:
    """Appele apres chaque combat entre deux peuples."""
    if attacker == defender:
        return
    make_contact(state, attacker, defender)
    d = _d(state)
    d.raids[(attacker, defender)] = (state.tick_count, attacker_won)
    if not hunted:
        add_mod(state, attacker, defender, "accrochage", -8, actor=attacker)
        return
    add_mod(state, attacker, defender, "raid", -25, actor=attacker)
    # Un raid contre l'un est un raid contre tout son pays (ses confederes,
    # son suzerain, ses tributaires) : les deux pays sont en guerre, leurs
    # pactes tombent (sauf entre suzerain et tributaire).
    for m in sorted(chiefdom.country(state, defender)):
        if m != defender and m != attacker:
            add_mod(state, attacker, m, "raid_pays", -10, actor=attacker)
    for x, y in confed.war_pairs(state, attacker, defender):
        _drop_war(state, x, y)
    if has_pact(state, attacker, defender):
        excused = d.casus.get((attacker, defender), -1) >= state.tick_count
        d.pacts.pop(pair(attacker, defender), None)
        if not excused:
            betray(state, attacker, defender)


def betray(state, traitor: int, victim: int) -> None:
    d = _d(state)
    add_mod(state, traitor, victim, "trahison", -50, actor=traitor)
    d.betrayed[traitor] = state.tick_count
    tribe = state.tribes.get(traitor)
    if tribe is not None:
        tribe.prestige = max(0, tribe.prestige - BETRAYAL_PRESTIGE)
    for other in contacts_of(state, traitor):
        if other != victim:
            add_mod(state, traitor, other, "reputation", -10, actor=traitor)
    names = (state.tribes[traitor].name, state.tribes[victim].name)
    if state.tribes[traitor].is_player:
        _note(state, LogKind.POLITIQUE, f"Vous avez trahi les {names[1]} : prestige -{BETRAYAL_PRESTIGE}, tous s'en souviendront.", to=traitor)
    if state.tribes[victim].is_player:
        _note(state, LogKind.POLITIQUE, f"Les {names[0]} ont trahi leur parole.", to=victim)


def hostile_intent(state, a: int, b: int) -> bool:
    """Deux peuples qui se battraient en se croisant (un tributaire ne se bat
    pas de lui-meme contre qui son pays ne combat pas)."""
    if at_peace(state, a, b):
        return False
    return not may_start(state, a, b) and not may_start(state, b, a)


WAR_WEEKS = 52


def at_war(state, a: int, b: int) -> bool:
    """Les pays de a et de b sont en guerre declaree, ou se sont battus depuis
    un an (un raid, un accrochage), ou l'un a un pretexte contre l'autre."""
    d = _d(state)
    if declared_war(state, a, b):
        return True
    ga, gb = chiefdom.country(state, a), chiefdom.country(state, b)
    for x in ga:
        for y in gb:
            for key in ((x, y), (y, x)):
                hit = d.raids.get(key)
                if hit is not None and state.tick_count - hit[0] <= WAR_WEEKS:
                    return True
                if d.casus.get(key, -1) >= state.tick_count:
                    return True
    return False


def may_start(state, a: int, b: int) -> str:
    """Pourquoi a ne peut pas attaquer b de lui-meme ("" : il peut). Un
    TRIBUTAIRE suit son suzerain a la guerre mais n'en declare pas : il ne
    se bat que contre qui son pays combat deja (ou contre son suzerain : une
    revolte). Un confedere, lui, peut entrainer tout son pays."""
    if a == b or a not in state.tribes or b not in state.tribes:
        return ""
    lords = chiefdom.lords_of(state, a)
    if not lords or b in lords or b in chiefdom.country(state, a):
        return ""
    if at_war(state, a, b):
        return ""
    return f"Un tributaire ne déclare pas la guerre : les {state.tribes[lords[-1]].name} ne combattent pas les {state.tribes[b].name}"


# --- pactes et paiements -------------------------------------------------------------


def add_pact(state, a: int, b: int, kind: str, weeks: int = 0, payer: int = 0, shared: bool = True) -> None:
    """Le pacte ; une treve ou une alliance engage aussi les confederes des
    deux peuples (confed.py : une seule diplomatie exterieure)."""
    _set_pact(state, a, b, kind, weeks, payer)
    if shared and kind in confed.SHARED:
        pairs = confed.outside_pairs(state, a, b)
        for x, y in pairs:
            _set_pact(state, x, y, kind, weeks, payer)
        if pairs:
            confed.shared_note(state, a, b, kind, pairs)


def _drop_war(state, a: int, b: int) -> None:
    """La guerre entre deux pays : plus de treve, d'alliance, de commerce."""
    d = _d(state)
    k = pair(a, b)
    kept = [p for p in d.pacts.get(k, []) if p.kind == "vassal"]
    if kept:
        d.pacts[k] = kept
    else:
        d.pacts.pop(k, None)


def _drop_shared(state, a: int, b: int) -> None:
    d = _d(state)
    k = pair(a, b)
    kept = [p for p in d.pacts.get(k, []) if p.kind not in confed.SHARED]
    if kept:
        d.pacts[k] = kept
    else:
        d.pacts.pop(k, None)


def _set_pact(state, a: int, b: int, kind: str, weeks: int = 0, payer: int = 0) -> None:
    d = _d(state)
    k = pair(a, b)
    pacts = [p for p in d.pacts.get(k, []) if p.kind != kind]
    if kind != WAR:
        # Un pacte de paix (treve, tribut, tributaire...) met fin a la guerre.
        pacts = [p for p in pacts if p.kind != WAR]
    if kind == "alliance":
        pacts = [p for p in pacts if p.kind != "treve"]
    until = state.tick_count + weeks if weeks else 0
    pacts.append(Pact(kind, state.tick_count, until, payer, state.tick_count))
    d.pacts[k] = pacts
    make_contact(state, a, b)


def break_pact(state, actor: int, other: int, kind: str | None = None) -> bool:
    d = _d(state)
    k = pair(actor, other)
    pacts = d.pacts.get(k, [])
    kept = [p for p in pacts if kind is not None and p.kind != kind]
    if len(kept) == len(pacts):
        return False
    if kept:
        d.pacts[k] = kept
    else:
        d.pacts.pop(k, None)
    add_mod(state, actor, other, "rupture", -20, actor=actor)
    tribe = state.tribes.get(actor)
    if tribe is not None:
        tribe.prestige = max(0, tribe.prestige - 3)
    # Rompre la paix avec le dehors : tout le pays la rompt.
    if kind is None or kind in confed.SHARED:
        for x, y in confed.outside_pairs(state, actor, other):
            _drop_shared(state, x, y)
    return True


def _pay_tribute(state, pact: Pact, a: int, b: int) -> None:
    payer = pact.payer
    receiver = b if payer == a else a
    payer_bands = [x for x in state.bands.values() if x.tribe_id == payer and x.population > 0]
    recv_bands = [x for x in state.bands.values() if x.tribe_id == receiver and x.population > 0]
    if not payer_bands or not recv_bands:
        return
    due = float(sum(x.population for x in payer_bands))
    paid = 0.0
    for band in sorted(payer_bands, key=lambda x: -x.stock):
        take = min(due - paid, max(0.0, band.stock - band.population))
        band.stock -= take
        paid += take
        if paid >= due:
            break
    if paid <= 0:
        return
    target = max(recv_bands, key=lambda x: (stock_max(x, state) - x.stock, -x.id))
    target.stock = min(stock_max(target, state), target.stock + paid)
    if state.tribes[receiver].is_player:
        _note(state, LogKind.POLITIQUE, f"Tribut des {state.tribes[payer].name} : {paid:.0f} vivres.", to=receiver)
    if state.tribes[payer].is_player:
        _note(state, LogKind.POLITIQUE, f"Tribut verse aux {state.tribes[receiver].name} : {paid:.0f} vivres.", to=payer)


def monthly(state) -> None:
    """Usure des raisons, fin des pactes, tributs, voisins, contacts, IA."""
    d = _d(state)
    alive = _living(state)
    for k in list(d.mods):
        kept = []
        for m in d.mods[k]:
            decay = MOD_TEXT.get(m.key, ("", "", 1.0))[2]
            if m.value > 0:
                m.value = max(0.0, m.value - decay)
            else:
                m.value = min(0.0, m.value + decay)
            if abs(m.value) >= 0.5:
                kept.append(m)
        if kept and k[0] in state.tribes and k[1] in state.tribes:
            d.mods[k] = kept
        else:
            d.mods.pop(k, None)
    for k in list(d.pacts):
        a, b = k
        live = []
        for p in d.pacts[k]:
            if a not in alive or b not in alive:
                continue
            if p.until and state.tick_count >= p.until:
                what = {"treve": "La trêve", "tribut": "Le tribut", "alliance": "L'alliance", "commerce": "L'accord commercial"}.get(p.kind, "Le pacte")
                for me, other in ((a, b), (b, a)):
                    if state.tribes[me].is_player:
                        _note(state, LogKind.POLITIQUE, f"{what} avec les {state.tribes[other].name} prend fin.", to=me)
                continue
            if p.kind == "tribut" and state.tick_count - p.paid >= TRIBUTE_EVERY:
                _pay_tribute(state, p, a, b)
                p.paid = state.tick_count
            live.append(p)
        if live:
            d.pacts[k] = live
        else:
            d.pacts.pop(k, None)
    d.casus = {k: v for k, v in d.casus.items() if v >= state.tick_count}
    _fade_wars(state)
    update_contacts(state)
    _update_neighbors(state)
    # Routes du sel et du silex : on commerce avec ses voisins.
    for tid, near in d.neighbors.items():
        tribe = state.tribes.get(tid)
        if tribe is None or not tech.bonuses(tribe).trade:
            continue
        for other in near:
            mods = d.mods.get(pair(tid, other), [])
            now = next((m.value for m in mods if m.key == "echanges"), 0.0)
            if now < 10.0:
                add_mod(state, tid, other, "echanges", min(1.3, 10.0 - now))


def _fade_wars(state) -> None:
    """Une guerre sans combat depuis WAR_FADE_WEEKS s'eteint d'elle-meme."""
    d = _d(state)
    for (a, b), pacts in sorted(d.pacts.items()):
        war = next((p for p in pacts if p.kind == WAR), None)
        if war is None or state.tick_count - war.since < WAR_FADE_WEEKS:
            continue
        last = max(
            [h[0] for key in ((a, b), (b, a)) if (h := d.raids.get(key)) is not None] + [war.since]
        )
        if state.tick_count - last >= WAR_FADE_WEEKS:
            d.pacts[(a, b)] = [p for p in pacts if p.kind != WAR]
            if not d.pacts[(a, b)]:
                d.pacts.pop((a, b), None)
            for me, other in ((a, b), (b, a)):
                if state.tribes[me].is_player:
                    _note(state, LogKind.POLITIQUE, f"La guerre avec les {state.tribes[other].name} s'éteint : plus un combat depuis trois ans.", to=me)


def _update_neighbors(state) -> None:
    with frozen_relations(state):
        _update_neighbors_now(state)


def _update_neighbors_now(state) -> None:
    d = _d(state)
    alive = _living(state)
    bands: dict[int, list] = {}
    for b in state.bands.values():
        if b.population > 0:
            bands.setdefault(b.tribe_id, []).append(b.position)
    for site in getattr(state, "sites", {}).values():
        if site.kind == "village":
            bands.setdefault(site.tribe_id, []).append(site.hex)
    traders = set()
    for r in d.routes:
        if r.units > 0:
            traders.add((r.exporter, r.importer))
            traders.add((r.importer, r.exporter))
    out: dict[int, list] = {}
    for tid in sorted(alive):
        near = []
        for other in contacts_of(state, tid):
            if other not in alive:
                continue
            if relation(state, tid, other) <= -15 and not allied(state, tid, other):
                continue
            if (
                allied(state, tid, other)
                or getattr(state, "overlap", {}).get(pair(tid, other), 0)
                or (tid, other) in traders
                or _close(state, bands.get(tid, []), bands.get(other, []), NEIGHBOR_RANGE)
            ):
                # Les porteurs des routes commerciales apportent aussi les
                # savoirs, de loin.
                near.append(other)
        out[tid] = near
    d.neighbors = out


def _close(state, xs, ys, limit: int) -> bool:
    world = state.world
    return any(world.distance(x, y) <= limit for x in xs for y in ys)


# --- diffusion des savoirs ------------------------------------------------------------


def teachers(state, tid: int, tech_id: str) -> list[int]:
    d = getattr(state, "diplo", None)
    if d is None:
        return []
    return [t for t in d.neighbors.get(tid, []) if t in state.tribes and tech_id in state.tribes[t].knowledge]


def diffusion_bonus(state, tid: int, tech_id: str) -> float:
    found = teachers(state, tid, tech_id)
    if not found:
        return 0.0
    extra = tech.bonuses(state.tribes[tid]).diffusion
    total = 0.0
    for t in found:
        total += (DIFFUSE_ALLY if allied(state, tid, t) else DIFFUSE_NEIGHBOR) + extra
    return min(DIFFUSE_CAP, total)


# --- forces et distances ------------------------------------------------------------------


def power(state, tid: int) -> float:
    return sum(battle.band_force(state, b) for b in state.bands.values() if b.tribe_id == tid and b.population > 0)


def gap(state, a: int, b: int) -> int:
    """Distance entre les bandes les plus proches des deux peuples."""
    xs = [x.position for x in state.bands.values() if x.tribe_id == a and x.population > 0]
    ys = [y.position for y in state.bands.values() if y.tribe_id == b and y.population > 0]
    world = state.world
    return min((world.distance(x, y) for x in xs for y in ys), default=10**6)


def pop_of(state, tid: int) -> int:
    return sum(b.population for b in state.bands.values() if b.tribe_id == tid and b.population > 0)


# --- propositions -----------------------------------------------------------------------

ACTIONS = ("cadeau", "present", "guerre", "treve", "alliance", "commerce", "tribut", "proteger", "confederer", "union", "rompre")
ACTION_LABELS = {
    "proteger": "Prendre sous sa protection",
    "cadeau": "Offrir des vivres",
    "present": "Offrir des sicles",
    "guerre": "Déclarer la guerre",
    "treve": "Proposer une trêve",
    "alliance": "Proposer une alliance",
    "commerce": "Proposer des échanges",
    "tribut": "Exiger un tribut",
    "confederer": "Proposer la confédération",
    "union": "Proposer l'union",
    "rompre": "Rompre le pacte",
}


@dataclass
class Verdict:
    """Reponse probable d'un peuple : bloque (raison), ou score et raisons."""

    blocked: str = ""
    score: int = 0
    reasons: list = field(default_factory=list)

    @property
    def accepted(self) -> bool:
        return not self.blocked and self.score > 0


def _warlike(state, tid: int) -> bool:
    return culture_of(state.tribes[tid]).raid_prestige <= 30


def _recent_raid(state, attacker: int, defender: int, weeks: int = 26):
    hit = _d(state).raids.get((attacker, defender))
    if hit is None or state.tick_count - hit[0] > weeks:
        return None
    return hit[1]


def _other_enemy(state, tid: int, but: int) -> bool:
    return any(t != but and relation(state, tid, t) <= -40 for t in contacts_of(state, tid))


def _obliged(state, actor: int, target: int) -> bool:
    """`target` a recu des dons de `actor` (Biens de prestige) : il lui doit."""
    return any(m.key == "oblige" and m.actor == actor and m.value > 0 for m in _d(state).mods.get(pair(actor, target), []))


def _betrayer(state, tid: int, weeks: int = 156) -> bool:
    last = _d(state).betrayed.get(tid)
    return last is not None and state.tick_count - last <= weeks


def evaluate(state, actor: int, target: int, action: str) -> Verdict:
    """Ce que `target` repondrait a `actor` (score > 0 : oui)."""
    if actor not in state.tribes or target not in state.tribes or actor == target:
        return Verdict(blocked="Personne a qui parler")
    if target not in _living(state):
        return Verdict(blocked="Ce peuple a disparu")
    if not in_contact(state, actor, target):
        return Verdict(blocked="Vous ne les connaissez pas encore")
    bonus = tech.bonuses(state.tribes[actor])
    rel = relation(state, actor, target)
    p_actor = max(1.0, power(state, actor))
    p_target = max(1.0, power(state, target))
    ratio = p_actor / p_target
    out: list[tuple[str, int]] = []
    if action == "cadeau":
        carrier = gift_carrier(state, actor, target)
        if carrier is None:
            return Verdict(blocked=f"Aucune de vos bandes à moins de {GIFT_RANGE} cases d'eux")
        return Verdict(score=1, reasons=[("Un cadeau est toujours accepté", 1)])
    if action == "present":
        if not money.has_money(state, actor):
            return Verdict(blocked="Il faut connaître Valeurs d'échange")
        if state.tribes[actor].money < PRESENT_SIZES[0]:
            return Verdict(blocked=f"Il faut {PRESENT_SIZES[0]} sicles au trésor")
        out = [("Un présent est toujours accepté", 1)]
        if not money.has_money(state, target):
            out.append(("Ils ne connaissent pas l'argent : des parures, moitié moins", 0))
        return Verdict(score=1, reasons=out)
    if action == "guerre":
        return _war_verdict(state, actor, target)
    if action == "rompre":
        if not has_pact(state, actor, target):
            return Verdict(blocked="Aucun pacte avec eux")
        return Verdict(score=1, reasons=[("Rompre coûte du prestige (-3) et de la relation (-20)", 0)])
    if action == "treve":
        if at_peace(state, actor, target):
            return Verdict(blocked="Vous êtes déjà en paix")
        out.append(("Base", -10))
        out.append(("Relation", round(rel * 0.5)))
        if ratio > 1.3:
            out.append(("Vous êtes plus forts", 15))
        elif ratio < 0.6:
            out.append(("Vous êtes plus faibles", -10))
        if _recent_raid(state, target, actor):
            out.append(("Leurs raids réussissent", -15))
        if _recent_raid(state, actor, target):
            out.append(("Vos raids les épuisent", 15))
        if _other_enemy(state, target, actor):
            out.append(("Ils ont d'autres ennemis", 10))
        if _warlike(state, target):
            out.append(("Peuple guerrier", -5))
    elif action == "alliance":
        if not bonus.alliance:
            return Verdict(blocked="Il faut connaître Mariages entre clans")
        if allied(state, actor, target):
            return Verdict(blocked="Vous êtes déjà alliés")
        if rel < 20:
            return Verdict(blocked=f"Relation trop basse ({rel:.0f}, il faut 20)")
        out.append(("Base", -30))
        out.append(("Relation", round(rel * 0.8)))
        if _common_enemy(state, actor, target):
            out.append(("Ennemi commun", 20))
        if 0.5 <= ratio <= 2.0:
            out.append(("Forces comparables", 10))
        elif ratio < 0.5:
            out.append(("Vous êtes trop faibles", -10))
        if ally_count(state, target) >= 2:
            out.append(("Ils ont déjà deux alliés", -15))
    elif action == "commerce":
        if not bonus.commerce:
            return Verdict(blocked="Il faut connaître Échanges lointains")
        if has_pact(state, actor, target, "commerce"):
            return Verdict(blocked="Un accord commercial est déjà en place")
        if not goods.has_village(state, actor):
            return Verdict(blocked="Il vous faut un village")
        if not goods.has_village(state, target):
            return Verdict(blocked="Ils n'ont pas de village : rien a échanger")
        dist, reach = goods.trade_distance(state, actor, target), goods.trade_range(state, actor, target)
        if dist > reach:
            return Verdict(blocked=f"Trop loin : {dist} cases entre vos villages ({reach} au plus)")
        if rel < -15:
            return Verdict(blocked=f"Relation trop basse ({rel:.0f}, il faut -15)")
        out.append(("Base", -10))
        out.append(("Relation", round(rel * 0.6)))
        if goods.offers(state, actor, target):
            out.append(("Vous avez ce qui leur manque", 15))
        if goods.offers(state, target, actor):
            out.append(("Ils ont de quoi vendre", 5))
        if tech.bonuses(state.tribes[target]).commerce:
            out.append(("Ils connaissent les échanges", 10))
        if dist <= 20:
            out.append(("Voisins", 5))
        if _recent_raid(state, actor, target, 52):
            out.append(("Vos raids récents", -20))
    elif action == "tribut":
        if has_pact(state, actor, target, "tribut"):
            return Verdict(blocked="Un tribut est déjà en place")
        if allied(state, actor, target):
            return Verdict(blocked="On n'exige rien d'un allié")
        out.append(("Base", -40))
        out.append(("Rapport de forces", max(-30, min(50, round((ratio - 1.0) * 25)))))
        dist = gap(state, actor, target)
        if dist <= 20:
            out.append(("Vous êtes à leur porte", 10))
        elif dist > 40:
            out.append(("Vous êtes loin", -20))
        out.append(("Relation", round(rel * 0.2)))
        if state.tribes[target].prestige >= 50:
            out.append(("Trop fiers pour payer", -10))
        if _obliged(state, actor, target):
            out.append(("Vos dons les obligent", 8))
    elif action == "proteger":
        if not chiefdom.has_chiefdom(state, actor):
            return Verdict(blocked="Il vous faut un village")
        if not chiefdom.has_chiefdom(state, target):
            return Verdict(blocked="Ils n'ont pas de village")
        if chiefdom.overlord_of(state, target) == actor:
            return Verdict(blocked="Ils sont déjà vos tributaires")
        if chiefdom.overlord_of(state, target):
            return Verdict(blocked="Ils sont déjà tributaires d'un autre peuple")
        if chiefdom.overlord_of(state, actor) == target:
            return Verdict(blocked="Vous êtes leurs tributaires")
        need = chiefdom.protect_ratio(state, actor)
        if ratio < need:
            times = "deux fois et demie" if need >= 2.45 else "deux fois"
            return Verdict(blocked=f"Vous n'êtes pas assez puissants (il faut {times} leur force)")
        if len(chiefdom.vassals_of(state, actor)) >= chiefdom.vassal_cap(state, actor):
            return Verdict(blocked="Vous avez déjà autant de tributaires que vous pouvez en tenir")
        out.append(("Base", -60))
        out.append(("Rapport de forces", max(-20, min(30, round((ratio - need) * 10)))))
        if chiefdom.feasted(state, actor, target):
            out.append(("Ils ont mangé à votre table", 10))
        if _obliged(state, actor, target):
            out.append(("Vos dons les obligent", 12))
        out.append(("Relation", round(rel * 0.3)))
        gap_p = state.tribes[actor].prestige - state.tribes[target].prestige
        out.append(("Votre prestige", max(-15, min(20, round(gap_p * 0.3)))))
        if allied(state, actor, target):
            out.append(("Mariages entre vos familles", 15))
        if gap(state, actor, target) <= 20:
            out.append(("Vous êtes à leur porte", 10))
        if state.tribes[target].prestige >= 50:
            out.append(("Trop fiers pour plier", -10))
    elif action == "confederer":
        why = confed.block(state, actor, target)
        if why:
            return Verdict(blocked=why)
        out.extend(confed.reasons(state, actor, target))
    elif action == "union":
        if not bonus.union:
            return Verdict(blocked="Il faut connaître Confédération")
        if state.tribes[target].is_player:
            return Verdict(blocked="Un peuple mené par un joueur ne se fond pas dans un autre")
        if rel < 50:
            return Verdict(blocked=f"Relation trop basse ({rel:.0f}, il faut 50)")
        pa, pt = max(1, pop_of(state, actor)), pop_of(state, target)
        if pt > 0.4 * pa:
            return Verdict(blocked="Ils sont trop nombreux (40 % de votre peuple au plus)")
        out.append(("Base", -20))
        out.append(("Relation", round((rel - 50) * 0.8)))
        out.append(("Vous êtes bien plus nombreux", round((1.0 - pt / pa) * 30)))
        out.append(("Fiers de leur nom", -round(state.tribes[target].prestige * 0.3)))
        if state.tribes[target].minor:
            out.append(("Petit peuple", 10))
    else:
        return Verdict(blocked="?")
    seen = approach.accept(state, target, action)
    if seen is not None:
        out.append(seen)
    if bonus.diplo:
        out.append(("Dons et palabres", bonus.diplo))
    if _betrayer(state, actor):
        out.append(("Vous avez trahi une parole", -25))
    out = [(label, v) for label, v in out if v]
    return Verdict(score=sum(v for _l, v in out), reasons=out)


def war_allies(state, target: int, actor: int) -> list[int]:
    """Ceux qui entreraient en guerre aux cotes de target : ses allies (et
    leurs pays), qui ont la diplomatie, hors du pays de l'attaquant."""
    out: set = set()
    mine = chiefdom.country(state, actor)
    for t in sorted(chiefdom.country(state, target)):
        for other in contacts_of(state, t):
            if allied(state, t, other) and other not in mine and diplomatic(state, other):
                out |= chiefdom.country(state, other)
    return sorted(out - chiefdom.country(state, target) - mine)


def war_pairs(state, actor: int, target: int) -> list[tuple[int, int]]:
    """Les paires en guerre si actor la declare a target : son pays contre
    le pays de target et ses allies."""
    mine = chiefdom.country(state, actor)
    theirs = chiefdom.country(state, target) | set(war_allies(state, target, actor))
    return sorted((x, y) for x in mine for y in theirs if x != y)


def _war_verdict(state, actor: int, target: int) -> Verdict:
    if not diplomatic(state, actor):
        return Verdict(blocked="Il faut connaître Dons et palabres (la diplomatie)")
    if not diplomatic(state, target):
        return Verdict(blocked="Ils ne connaissent pas la diplomatie : attaquez-les au clic droit, sans déclaration")
    if declared_war(state, actor, target):
        return Verdict(blocked="Vous êtes déjà en guerre")
    if target in chiefdom.country(state, actor):
        return Verdict(blocked="Ils sont de votre pays")
    why = may_start(state, actor, target)
    if chiefdom.lords_of(state, actor):
        return Verdict(blocked=why or "Un tributaire ne déclare pas la guerre")
    if allied(state, actor, target):
        return Verdict(blocked="Vous êtes alliés : rompez d'abord l'alliance")
    if has_pact(state, actor, target, "treve"):
        return Verdict(blocked="Une trêve vous lie : rompez-la d'abord")
    out = [(f"Relation {DECLARE_RELATION}", 0)]
    if _d(state).casus.get((actor, target), -1) >= state.tick_count:
        out.append(("Vous avez un motif (ils ont refusé votre tribut) : pas de honte", 0))
    else:
        out.append((f"Sans motif : prestige -{DECLARE_PRESTIGE}, et les autres peuples s'en souviennent", 0))
    if has_pact(state, actor, target, "commerce"):
        out.append(("L'accord commercial tombe", 0))
    allies = war_allies(state, target, actor)
    if allies:
        out.append(("Leurs alliés entrent en guerre : " + ", ".join(state.tribes[t].name for t in allies[:5]), 0))
    mine = sorted(chiefdom.country(state, actor) - {actor})
    if mine:
        out.append(("Votre pays vous suit : " + ", ".join(state.tribes[t].name for t in mine[:5]), 0))
    return Verdict(score=1, reasons=out)


def declare_war(state, actor: int, target: int) -> str:
    """actor declare la guerre a target : les deux pays (et les allies de
    target) sont en guerre ; la paix et le commerce entre eux tombent."""
    d = _d(state)
    pairs = war_pairs(state, actor, target)
    motive = d.casus.get((actor, target), -1) >= state.tick_count
    for x, y in pairs:
        _drop_war(state, x, y)
        k = pair(x, y)
        d.pacts.setdefault(k, []).append(Pact(WAR, state.tick_count, 0, actor, state.tick_count))
        make_contact(state, x, y, quiet=True)
    add_mod(state, actor, target, "guerre_declaree", DECLARE_RELATION, actor=actor)
    tribe = state.tribes[actor]
    if not motive:
        tribe.prestige = max(0, tribe.prestige - DECLARE_PRESTIGE)
        for other in contacts_of(state, actor):
            if other != target:
                add_mod(state, actor, other, "agresseur", -5, actor=actor)
    names = (tribe.name, state.tribes[target].name)
    involved = sorted({x for p_ in pairs for x in p_})
    for t in involved:
        if not state.tribes[t].is_player or t == actor:
            continue
        side = "vous" if t == target else ("votre pays" if t in chiefdom.country(state, target) else "vos alliés")
        _note(state, LogKind.COMBAT, f"Les {names[0]} déclarent la guerre aux {names[1]} : {side} entrez en guerre contre eux.", to=t)
    if tribe.is_player:
        joined = sorted({y for _x, y in pairs} - {target})
        extra = f" Leurs alliés et leur pays les suivent : {', '.join(state.tribes[t].name for t in joined[:5])}." if joined else ""
        return f"Vous déclarez la guerre aux {names[1]}.{extra}"
    return ""


def end_war(state, a: int, b: int) -> None:
    """La paix (une treve) entre les deux pays : plus de guerre entre eux."""
    for x in chiefdom.country(state, a) | {a}:
        for y in chiefdom.country(state, b) | {b}:
            k = pair(x, y)
            kept = [p for p in _d(state).pacts.get(k, []) if p.kind != WAR]
            if kept:
                _d(state).pacts[k] = kept
            else:
                _d(state).pacts.pop(k, None)


def wars_of(state, tid: int) -> list[int]:
    """Les peuples en guerre declaree avec tid."""
    return sorted(o for o in contacts_of(state, tid) if declared_war(state, tid, o))


def gift_carrier(state, actor: int, target: int):
    """(bande qui porte, bande qui recoit) : les plus proches, a portee."""
    world = state.world
    best = None
    for x in state.bands.values():
        if x.tribe_id != actor or x.population <= 0 or x.retreating:
            continue
        for y in state.bands.values():
            if y.tribe_id != target or y.population <= 0:
                continue
            d = world.distance(x.position, y.position)
            if d <= GIFT_RANGE and (best is None or d < best[0]):
                best = (d, x, y)
    return None if best is None else (best[1], best[2])


def gift_sizes(state, actor: int, target: int) -> list[int]:
    found = gift_carrier(state, actor, target)
    if found is None:
        return []
    carrier = found[0]
    spare = carrier.stock - 2 * carrier.population
    return [s for s in GIFT_SIZES if s <= spare]


def present_sizes(state, actor: int) -> list[int]:
    have = state.tribes[actor].money if money.has_money(state, actor) else 0.0
    return [s for s in PRESENT_SIZES if s <= have]


def present_value(state, actor: int, target: int, sicles: float) -> float:
    """Ce qu'un present en sicles vaut en relation (comme des vivres)."""
    v = gift_value(state, actor, target, sicles * money.VPS)
    return v if money.has_money(state, target) else v * PRESENT_NO_MONEY


def gift_value(state, actor: int, target: int, amount: float) -> float:
    base = 40.0 * amount / (4.0 * max(1, pop_of(state, target)) + 40.0)
    return min(25.0, base) * tech.bonuses(state.tribes[actor]).gifts


# Proposer a un autre joueur : il recoit la carte que l'IA lui enverrait.
HUMAN_OFFERS = {"treve": "offre_treve", "alliance": "offre_alliance", "commerce": "offre_commerce", "tribut": "exige_tribut", "proteger": "offre_protection", "confederer": "offre_confederation"}


def perform(state, actor: int, target: int, action: str, amount: float = 0.0) -> str:
    """Executer une proposition ; rend le texte du resultat. Si `target` est
    un autre joueur, il decide lui-meme (carte d'evenement)."""
    verdict = evaluate(state, actor, target, action)
    if verdict.blocked:
        return verdict.blocked
    d = _d(state)
    names = state.tribes[target].name
    human = state.tribes[target].is_player and actor != target
    if action == "cadeau":
        carrier, receiver = gift_carrier(state, actor, target)
        amount = min(amount, max(0.0, carrier.stock - 2 * carrier.population))
        if amount <= 0:
            return "Pas assez de vivres à donner"
        carrier.stock -= amount
        receiver.stock = min(stock_max(receiver, state), receiver.stock + amount)
        add_mod(state, actor, target, "cadeau", gift_value(state, actor, target, amount), actor=actor)
        if tech.bonuses(state.tribes[actor]).obligations:
            # Biens de prestige : qui recoit doit.
            add_mod(state, actor, target, "oblige", 6.0, actor=actor)
        if human:
            _note(state, LogKind.POLITIQUE, f"Les {state.tribes[actor].name} vous offrent {amount:.0f} vivres.", receiver.position, to=target)
        return f"Les {names} acceptent vos {amount:.0f} vivres."
    if action == "present":
        tribe = state.tribes[actor]
        amount = min(float(amount), tribe.money)
        if amount <= 0:
            return "Le trésor est vide"
        tribe.money -= amount
        money.book(state, actor, "presents", -amount)
        if money.has_money(state, target):
            money.earn(state, target, "presents", amount)
        add_mod(state, actor, target, "cadeau", present_value(state, actor, target, amount), actor=actor)
        if tech.bonuses(tribe).obligations:
            add_mod(state, actor, target, "oblige", 6.0, actor=actor)
        if human:
            _note(state, LogKind.POLITIQUE, f"Les {tribe.name} vous offrent {amount:.0f} sicles.", to=target)
        return f"Les {names} acceptent vos {amount:.0f} sicles."
    if action == "guerre":
        return declare_war(state, actor, target)
    if action == "rompre":
        break_pact(state, actor, target)
        if human:
            _note(state, LogKind.POLITIQUE, f"Les {state.tribes[actor].name} rompent leur pacte avec vous.", to=target)
        return f"Pacte rompu avec les {names}."
    if human and action in HUMAN_OFFERS:
        found = gift_carrier(state, target, actor)
        band_id = found[0].id if found is not None else next(
            (x.id for x in sorted(state.bands.values(), key=lambda x: x.id) if x.tribe_id == target and x.population > 0), 0
        )
        if not events.hook(state, HUMAN_OFFERS[action], tribe_id=target, band_id=band_id, other=actor):
            return f"Les {names} ne peuvent pas examiner cette proposition pour l'instant."
        d.cooldown[f"{action}:{actor}:{target}"] = state.tick_count
        return f"Proposition portée aux {names} : à eux de décider."
    d.cooldown[f"{action}:{actor}:{target}"] = state.tick_count
    if not verdict.accepted:
        if action == "tribut":
            add_mod(state, actor, target, "tribut_refuse", -10, actor=target)
            d.casus[(actor, target)] = state.tick_count + 52
            return f"Les {names} refusent de payer. Vous pouvez les raider sans trahir (1 an)."
        if action == "union":
            add_mod(state, actor, target, "union_refusee", -5, actor=target)
        if action == "confederer":
            add_mod(state, actor, target, "confed_refusee", -5, actor=target)
        return f"Les {names} refusent."
    if action == "treve":
        end_war(state, actor, target)
        add_pact(state, actor, target, "treve", TRUCE_WEEKS)
        return f"Trêve conclue avec les {names} (2 ans)."
    if action == "alliance":
        add_pact(state, actor, target, "alliance")
        add_mod(state, actor, target, "mariage", 15)
        chiefs.marriage_note(state, actor, target)
        return f"Alliance scellée avec les {names} par des mariages."
    if action == "tribut":
        add_pact(state, actor, target, "tribut", TRIBUTE_WEEKS, payer=target)
        return f"Les {names} paieront un tribut chaque saison (2 ans)."
    if action == "commerce":
        add_pact(state, actor, target, "commerce")
        add_mod(state, actor, target, "echanges", 5)
        return f"Accord commercial avec les {names} : vos villages échangeront leurs biens chaque mois."
    if action == "union":
        absorb(state, actor, target)
        return f"Les {names} rejoignent votre peuple."
    if action == "confederer":
        confed.form(state, actor, target)
        return f"Confédération conclue avec les {names} : un seul pays au dehors, chacun maître chez soi."
    if action == "proteger":
        chiefdom.make_vassal(state, actor, target, "protection")
        add_mod(state, actor, target, "protection", 5)
        return f"Les {names} se placent sous votre protection : ils deviennent vos tributaires."
    return ""


INVITE_RANGE = 12


def invitable(state, actor: int, target: int) -> list:
    """Clans du peuple `target` qui se detachent de leur chef, assez pres de
    chez vous pour qu'on sache leur mecontentement."""
    mine = [b.position for b in state.bands.values() if b.tribe_id == actor and b.population > 0]
    out = []
    for band in sorted(state.bands.values(), key=lambda b: b.id):
        if band.tribe_id != target or band.population <= 0 or chiefs.is_chief_band(state, band):
            continue
        if band.loyalty >= chiefs.OBEY:
            continue
        if state.tribes[actor].is_player and not is_visible(state, band.position, actor):
            continue
        near = influence.in_zone(state.world, band.position, actor) or any(
            state.world.distance(band.position, p) <= INVITE_RANGE for p in mine
        )
        if near:
            out.append(band)
    return out


def invite_chance(state, actor: int, band) -> float:
    target = band.tribe_id
    chance = (45.0 - band.loyalty) / 45.0 + (state.tribes[actor].prestige - state.tribes[target].prestige) / 100.0
    return max(0.05, min(0.9, chance))


def invite(state, actor: int, band_id: int) -> str:
    """Debaucher un clan indocile : il quitte son peuple pour le votre."""
    band = state.bands.get(band_id)
    if band is None or band not in invitable(state, actor, band.tribe_id):
        return "Ce clan ne peut pas être invite"
    tribe = state.tribes[actor]
    if tribe.prestige < INVITE_COST:
        return f"Il faut {INVITE_COST} de prestige"
    target = band.tribe_id
    tribe.prestige -= INVITE_COST
    who = band.leader.name if band.leader else "ce clan"
    if state.story_rng.random() < invite_chance(state, actor, band):
        band.tribe_id = actor
        band.loyalty = 55.0
        band.order = stay_order()
        band.path = []
        band.intent_prey = 0
        if band.leader is not None and state.tribes[target].heir == band.leader.pid:
            state.tribes[target].heir = 0
        add_mod(state, actor, target, "debauchage", -25, actor=actor)
        chiefs.ensure(state)
        return f"Le clan de {who} rejoint votre peuple !"
    add_mod(state, actor, target, "debauchage", -10, actor=actor)
    return f"Le clan de {who} refuse, et les {state.tribes[target].name} l'ont appris."


def on_cooldown(state, actor: int, target: int, action: str) -> int:
    """Semaines avant de pouvoir reproposer (0 = libre)."""
    last = _d(state).cooldown.get(f"{action}:{actor}:{target}")
    if last is None:
        return 0
    return max(0, OFFER_COOLDOWN - (state.tick_count - last))


def absorb(state, actor: int, target: int) -> None:
    """Un petit peuple se fond dans un autre : ses bandes, ses lieux, une
    partie de ses savoirs."""
    for band in state.bands.values():
        if band.tribe_id == target:
            band.tribe_id = actor
            band.order = stay_order()
            band.path = []
            band.loyalty = 55.0
            band.intent_prey = 0
    for site in getattr(state, "sites", {}).values():
        if site.tribe_id == target:
            site.tribe_id = actor
    a, t = state.tribes[actor], state.tribes[target]
    for tid in sorted(t.knowledge - a.knowledge):
        a.progress[tid] = max(a.progress.get(tid, 0.0), tech.TECHS[tid].cost * 0.5)
    gain_prestige(state, a, 8)
    chiefs.after_absorb(state, actor, target)
    forget(state, target)


def forget(state, tid: int) -> None:
    """Un peuple disparu : ses pactes tombent (les raisons s'useront)."""
    d = _d(state)
    for k in list(d.pacts):
        if tid in k:
            d.pacts.pop(k, None)


# --- IA ------------------------------------------------------------------------------


def ai_monthly(state) -> None:
    """Chaque mois, un peuple IA sur quatre regarde ses voisins (IA) :
    treve quand les raids coutent, alliance entre amis, tribut du fort au
    faible. Les propositions au joueur passent par les evenements."""
    alive = _living(state)
    for tid in sorted(alive):
        tribe = state.tribes.get(tid)
        if tribe is None or tribe.is_player or (state.tick_count // 4 + tid) % 4:
            continue
        for other in contacts_of(state, tid):
            if other not in alive:
                continue
            if state.tribes[other].is_player:
                _propose_to_player(state, tid, other)
                continue
            if on_cooldown(state, tid, other, "treve") or on_cooldown(state, tid, other, "alliance"):
                continue
            rel = relation(state, tid, other)
            fought = _recent_raid(state, tid, other, 52) is not None or _recent_raid(state, other, tid, 52) is not None
            war = next((p for p in _pacts(state, tid, other) if p.kind == WAR), None)
            weary = war is not None and state.tick_count - war.since >= AI_WAR_WEEKS
            if not at_peace(state, tid, other) and (fought or weary) and rel > -60:
                if evaluate(state, tid, other, "treve").accepted:
                    perform(state, tid, other, "treve")
                    continue
            if rel >= 45 + approach.factor(state, tid, "alliance_rel") and not allied(state, tid, other) and tech.bonuses(tribe).alliance:
                if evaluate(state, tid, other, "alliance").accepted:
                    perform(state, tid, other, "alliance")
                    continue
            if not on_cooldown(state, tid, other, "confederer") and confed.ai_wants(state, tid, other):
                if evaluate(state, tid, other, "confederer").accepted:
                    perform(state, tid, other, "confederer")
                    continue
                _d(state).cooldown[f"confederer:{tid}:{other}"] = state.tick_count
            if rel >= 10 + approach.factor(state, tid, "commerce_rel") and tech.bonuses(tribe).commerce and not has_pact(state, tid, other, "commerce"):
                if not on_cooldown(state, tid, other, "commerce") and evaluate(state, tid, other, "commerce").accepted:
                    perform(state, tid, other, "commerce")
                    continue
            # Prendre sous sa protection un voisin faible et ami (la chefferie).
            if (
                rel >= 0
                and gap(state, tid, other) <= 30
                and not on_cooldown(state, tid, other, "proteger")
                and power(state, tid) > chiefdom.protect_ratio(state, tid) * max(1.0, power(state, other))
                and state.story_rng.random() < 0.1 * approach.factor(state, tid, "protect")
                and evaluate(state, tid, other, "proteger").accepted
            ):
                perform(state, tid, other, "proteger")
                continue
            if (
                not has_pact(state, tid, other)
                and power(state, tid) > 2.5 * max(1.0, power(state, other))
                and rel <= 10
                and state.story_rng.random() < 0.15 * approach.factor(state, tid, "tribute")
            ):
                perform(state, tid, other, "tribut")
                continue
            # Un chef protecteur (ou genereux) fait des dons a ses voisins plus
            # faibles : ils lui seront obliges (Biens de prestige).
            if (
                rel < 60
                and approach.factor(state, tid, "gift") > 1.0
                and power(state, tid) > 1.5 * max(1.0, power(state, other))
                and not on_cooldown(state, tid, other, "cadeau")
                and state.story_rng.random() < 0.05 * approach.factor(state, tid, "gift")
                and gift_carrier(state, tid, other) is not None
            ):
                # Un tresor riche donne des sicles plutot que des vivres (le
                # meme don, en argent : AI_PRESENT sicles = 100 vivres).
                if money.has_money(state, tid) and tribe.money > 2 * money.reserve(state, tid) + AI_PRESENT:
                    perform(state, tid, other, "present", AI_PRESENT)
                    _d(state).cooldown[f"cadeau:{tid}:{other}"] = state.tick_count
                    continue
                found = gift_carrier(state, tid, other)
                spare = found[0].stock - 8 * found[0].population if found is not None else 0.0
                if spare >= 60:
                    perform(state, tid, other, "cadeau", min(150.0, spare / 2))
                    d_ = _d(state)
                    d_.cooldown[f"cadeau:{tid}:{other}"] = state.tick_count


AI_WAR_WEEKS = 78


PROPOSE_EVERY = 52


def _propose_to_player(state, ai: int, player: int) -> None:
    """Un peuple IA fait une proposition au joueur (un evenement a decider).
    Il ne propose que ce qu'il accepterait lui-meme."""
    d = _d(state)
    key = f"propose:{ai}:{player}"
    if state.tick_count - d.cooldown.get(key, -10**6) < PROPOSE_EVERY:
        return
    rel = relation(state, ai, player)
    fought = _recent_raid(state, ai, player, 52) is not None or _recent_raid(state, player, ai, 52) is not None
    kind = ""
    war = next((p for p in _pacts(state, ai, player) if p.kind == WAR), None)
    weary = war is not None and state.tick_count - war.since >= AI_WAR_WEEKS
    if not at_peace(state, ai, player) and (fought or weary) and rel > -60 and evaluate(state, player, ai, "treve").accepted:
        kind = "offre_treve"
    elif rel >= 45 + approach.factor(state, ai, "alliance_rel") and not allied(state, ai, player) and tech.bonuses(state.tribes[ai]).alliance:
        if evaluate(state, player, ai, "alliance").accepted or rel >= 60:
            kind = "offre_alliance"
    elif confed.ai_wants(state, ai, player) and not evaluate(state, ai, player, "confederer").blocked:
        kind = "offre_confederation"
    elif (
        rel >= 10 + approach.factor(state, ai, "commerce_rel")
        and tech.bonuses(state.tribes[ai]).commerce
        and not has_pact(state, ai, player, "commerce")
        and not evaluate(state, ai, player, "commerce").blocked
        and state.story_rng.random() < 0.5
    ):
        kind = "offre_commerce"
    elif (
        rel >= 0
        and power(state, ai) > 2.0 * max(1.0, power(state, player))
        and not evaluate(state, ai, player, "proteger").blocked
        and gap(state, ai, player) <= 30
        and state.story_rng.random() < 0.15 * approach.factor(state, ai, "protect")
    ):
        kind = "offre_protection"
    elif (
        not has_pact(state, ai, player)
        and power(state, ai) > 2.5 * max(1.0, power(state, player))
        and rel <= 10
        and gap(state, ai, player) <= 30
        and state.story_rng.random() < 0.2 * approach.factor(state, ai, "tribute")
    ):
        kind = "exige_tribut"
    elif (
        rel >= 25
        and money.has_money(state, ai)
        and state.tribes[ai].money > 2 * money.reserve(state, ai) + AI_PRESENT
        and gift_carrier(state, ai, player) is not None
        and state.story_rng.random() < 0.05 * approach.factor(state, ai, "gift")
    ):
        perform(state, ai, player, "present", AI_PRESENT)
        d.cooldown[key] = state.tick_count
        return
    elif rel >= 25 and state.story_rng.random() < 0.08 * approach.factor(state, ai, "gift") and gift_carrier(state, ai, player) is not None:
        carrier, receiver = gift_carrier(state, ai, player)
        spare = carrier.stock - 6 * carrier.population
        if spare >= 40:
            amount = min(150.0, spare)
            carrier.stock -= amount
            receiver.stock = min(stock_max(receiver, state), receiver.stock + amount)
            add_mod(state, ai, player, "cadeau", gift_value(state, ai, player, amount), actor=ai)
            _note(state, LogKind.POLITIQUE, f"Les {state.tribes[ai].name} vous offrent {amount:.0f} vivres.", receiver.position, to=player)
            d.cooldown[key] = state.tick_count
        return
    if not kind:
        return
    d.cooldown[key] = state.tick_count
    found = gift_carrier(state, player, ai)
    band_id = found[0].id if found is not None else 0
    events.hook(state, kind, tribe_id=player, band_id=band_id, other=ai)


# --- sauvegarde ------------------------------------------------------------------------


def to_json(d: Diplomacy) -> dict:
    return {
        "contacts": sorted([list(k) for k in d.contacts]),
        "mods": [[list(k), [[m.key, m.value, m.actor, m.year] for m in v]] for k, v in sorted(d.mods.items())],
        "pacts": [
            [list(k), [[p.kind, p.since, p.until, p.payer, p.paid] for p in v]] for k, v in sorted(d.pacts.items())
        ],
        "cooldown": dict(d.cooldown),
        "casus": [[a, b, v] for (a, b), v in sorted(d.casus.items())],
        "betrayed": {str(k): v for k, v in d.betrayed.items()},
        "raids": [[a, b, t, won] for (a, b), (t, won) in sorted(d.raids.items())],
        "neighbors": {str(k): v for k, v in d.neighbors.items()},
        "routes": [
            [r.exporter, r.importer, r.good, r.level, r.by, r.since, round(r.units, 3), round(r.paid, 2), r.status, r.idle]
            for r in d.routes
        ],
    }


def from_json(data) -> Diplomacy:
    d = Diplomacy()
    if not isinstance(data, dict):
        return d
    d.contacts = {tuple(int(x) for x in k) for k in data.get("contacts", [])}
    for k, rows in data.get("mods", []):
        d.mods[tuple(int(x) for x in k)] = [Mod(str(r[0]), float(r[1]), int(r[2]), int(r[3])) for r in rows]
    for k, rows in data.get("pacts", []):
        d.pacts[tuple(int(x) for x in k)] = [
            Pact(str(r[0]), int(r[1]), int(r[2]), int(r[3]), int(r[4])) for r in rows
        ]
    d.cooldown = {str(k): int(v) for k, v in data.get("cooldown", {}).items()}
    d.casus = {(int(a), int(b)): int(v) for a, b, v in data.get("casus", [])}
    d.betrayed = {int(k): int(v) for k, v in data.get("betrayed", {}).items()}
    d.raids = {(int(a), int(b)): (int(t), bool(w)) for a, b, t, w in data.get("raids", [])}
    d.neighbors = {int(k): [int(x) for x in v] for k, v in data.get("neighbors", {}).items()}
    for row in data.get("routes", []):
        try:
            exp, imp, good, level, by, since, units, paid, status, idle = row
            d.routes.append(TradeRoute(int(exp), int(imp), str(good), int(level), int(by), int(since), float(units), float(paid), str(status), int(idle)))
        except (TypeError, ValueError):
            continue
    return d


def _note(state, kind, text: str, where=None, to: int | None = None) -> None:
    """Au journal du joueur `to` (par defaut le joueur solo)."""
    note(state, kind, text, where, to=PLAYER_TRIBE_ID if to is None else to)
