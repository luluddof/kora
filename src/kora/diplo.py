"""Diplomatie : contacts, relations, pactes, propositions, diffusion.

Relation entre deux peuples en contact : de -100 a +100, somme de raisons
lisibles (Mod), chacune avec sa valeur et son usure mensuelle, plus des
raisons "du moment" recalculees (terres qui se chevauchent, pactes,
ennemi commun). La relation est la meme dans les deux sens ; le libelle
d'une raison depend de qui l'a causee (actor).

Pactes : treve (2 ans), alliance (sans fin), tribut (2 ans, le payeur
donne une semaine de vivres par saison). Raider un peuple avec qui l'on
a un pacte : trahison.

Propositions : evaluate() rend le score de l'autre peuple et ses raisons
(le panneau les montre AVANT de cliquer), perform() l'execute.
Diffusion : un savoir connu d'un voisin en contact (pas ennemi) s'apprend
plus vite, ses semaines vecues comptent double (tech.py).
N'importe ni pygame ni render.
"""

from __future__ import annotations

from dataclasses import dataclass, field

from src.kora import tech
from src.kora.log import LogKind

CONTACT_RANGE = 16
NEIGHBOR_RANGE = 40
TRUCE_WEEKS = 104
TRIBUTE_WEEKS = 104
TRIBUTE_EVERY = 13
GIFT_RANGE = 30
GIFT_SIZES = (50, 150, 400)
INVITE_COST = 10
BETRAYAL_PRESTIGE = 10
DIFFUSE_NEIGHBOR = 0.35
DIFFUSE_ALLY = 0.70
DIFFUSE_CAP = 1.0
OFFER_COOLDOWN = 26

# key -> (vu par celui qui a agi, vu par l'autre, usure par mois)
MOD_TEXT = {
    "raid": ("Vous les avez attaques", "Ils vous ont attaques", 1.0),
    "accrochage": ("Accrochage", "Accrochage", 1.0),
    "cadeau": ("Vos cadeaux", "Leurs cadeaux", 1.0),
    "meme_souche": ("Meme souche", "Meme souche", 0.2),
    "separation": ("Separation", "Separation", 0.5),
    "trahison": ("Vous les avez trahis", "Ils vous ont trahis", 0.4),
    "reputation": ("Votre reputation de traitre", "Leur reputation de traitres", 0.3),
    "mariage": ("Mariages entre vos chefs", "Mariages entre vos chefs", 0.3),
    "pillage": ("Vous avez pille leurs vivres", "Ils ont pille vos vivres", 1.0),
    "tribut_refuse": ("Ils ont refuse votre tribut", "Vous avez refuse leur tribut", 0.8),
    "debauchage": ("Vous avez pris leurs gens", "Ils ont pris vos gens", 0.6),
    "rupture": ("Vous avez rompu un pacte", "Ils ont rompu un pacte", 0.6),
    "accueil": ("Vous les avez bien accueillis", "Ils vous ont bien accueillis", 0.8),
    "chasses": ("Vous les avez chasses", "Ils vous ont chasses", 0.8),
    "entraide": ("Entraide", "Entraide", 0.6),
    "echanges": ("Echanges reguliers", "Echanges reguliers", 0.3),
    "route_fermee": ("Vous avez ferme une de leurs routes", "Ils ont ferme une de vos routes", 0.5),
    "union_refusee": ("Union refusee", "Union refusee", 0.8),
}


@dataclass
class Mod:
    key: str
    value: float
    actor: int = 0
    year: int = 0


@dataclass
class Pact:
    kind: str  # "treve", "alliance", "tribut", "commerce"
    since: int
    until: int = 0  # 0 = sans fin
    payer: int = 0
    paid: int = 0


@dataclass
class TradeRoute:
    """Une route commerciale (goods.py) : `exporter` envoie chaque mois un
    bien a `importer`, qui le paie en vivres. level : nombre de convois de
    porteurs (1 a 3). by : le peuple qui l'a ouverte. Le reste : ce que la
    route a fait le dernier mois."""

    exporter: int
    importer: int
    good: str
    level: int = 1
    by: int = 0
    since: int = 0
    units: float = 0.0
    paid: float = 0.0
    status: str = ""
    idle: int = 0


@dataclass
class Diplomacy:
    contacts: set = field(default_factory=set)
    mods: dict = field(default_factory=dict)
    pacts: dict = field(default_factory=dict)
    cooldown: dict = field(default_factory=dict)
    # (qui, contre qui) -> semaine limite : raider sans trahir (tribut refuse).
    casus: dict = field(default_factory=dict)
    betrayed: dict = field(default_factory=dict)
    # (attaquant, defenseur) -> (semaine, l'attaquant a gagne)
    raids: dict = field(default_factory=dict)
    # Voisins qui peuvent enseigner, recalcule chaque mois : tid -> [tid]
    neighbors: dict = field(default_factory=dict)
    # Routes commerciales (goods.py).
    routes: list = field(default_factory=list)


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
    from src.kora.peoples import living_tribe_ids

    return living_tribe_ids(state)


def make_contact(state, a: int, b: int, quiet: bool = False) -> bool:
    if a == b or a not in state.tribes or b not in state.tribes:
        return False
    key = pair(a, b)
    d = _d(state)
    if key in d.contacts:
        return False
    d.contacts.add(key)
    player = next((t for t in (a, b) if state.tribes[t].is_player), None)
    if player is not None and not quiet:
        other = b if player == a else a
        from src.kora import events

        _note(state, LogKind.POLITIQUE, f"Premier contact avec les {state.tribes[other].name}.")
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
    return any(kind is None or p.kind == kind for p in _pacts(state, a, b))


def allied(state, a: int, b: int) -> bool:
    return has_pact(state, a, b, "alliance")


def at_peace(state, a: int, b: int) -> bool:
    """Treve, alliance, tribut ou accord commercial : pas de raid entre eux."""
    if a == b:
        return True
    return has_pact(state, a, b)


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
        if p.kind == "treve":
            out.append(("Treve", 10.0))
        elif p.kind == "alliance":
            out.append(("Alliance", 25.0))
        elif p.kind == "tribut":
            out.append(("Tribut", -5.0))
        elif p.kind == "commerce":
            out.append(("Accord commercial", 8.0))
    for t in (a, b):
        chief = _chief_traits(state, t)
        if "querelleur" in chief:
            out.append(("Chef querelleur", -5.0))
        if "genereux" in chief:
            out.append(("Chef genereux", 3.0))
    return out


def _chief_traits(state, tid: int) -> tuple:
    from src.kora import chiefs

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
        return "Mefiants"
    if rel < 50:
        return "Cordiaux"
    return "Amis"


def level(state, a: int, b: int) -> str:
    if allied(state, a, b):
        return "Allies"
    return level_of(relation(state, a, b))


def status_line(state, a: int, b: int) -> str:
    parts = []
    for p in _pacts(state, a, b):
        left = max(0, p.until - state.tick_count) if p.until else 0
        if p.kind == "treve":
            parts.append(f"Treve ({left} sem.)")
        elif p.kind == "alliance":
            parts.append("Alliance")
        elif p.kind == "tribut":
            who = "ils vous paient" if p.payer == b else "vous payez"
            parts.append(f"Tribut : {who} ({left} sem.)")
        elif p.kind == "commerce":
            parts.append("Accord commercial")
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
        _note(state, LogKind.POLITIQUE, f"Vous avez trahi les {names[1]} : prestige -{BETRAYAL_PRESTIGE}, tous s'en souviendront.")
    elif state.tribes[victim].is_player:
        _note(state, LogKind.POLITIQUE, f"Les {names[0]} ont trahi leur parole.")


def hostile_intent(state, a: int, b: int) -> bool:
    """Deux peuples qui se battraient en se croisant."""
    return not at_peace(state, a, b)


# --- pactes et paiements -------------------------------------------------------------


def add_pact(state, a: int, b: int, kind: str, weeks: int = 0, payer: int = 0) -> None:
    d = _d(state)
    k = pair(a, b)
    pacts = [p for p in d.pacts.get(k, []) if p.kind != kind]
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
    return True


def _pay_tribute(state, pact: Pact, a: int, b: int) -> None:
    payer = pact.payer
    receiver = b if payer == a else a
    from src.kora.sim import stock_max

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
        _note(state, LogKind.POLITIQUE, f"Tribut des {state.tribes[payer].name} : {paid:.0f} vivres.")
    elif state.tribes[payer].is_player:
        _note(state, LogKind.POLITIQUE, f"Tribut verse aux {state.tribes[receiver].name} : {paid:.0f} vivres.")


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
                if state.tribes[a].is_player or state.tribes[b].is_player:
                    other = b if state.tribes[a].is_player else a
                    what = {"treve": "La treve", "tribut": "Le tribut", "alliance": "L'alliance", "commerce": "L'accord commercial"}.get(p.kind, "Le pacte")
                    _note(state, LogKind.POLITIQUE, f"{what} avec les {state.tribes[other].name} prend fin.")
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
    from src.kora.sim import band_force

    return sum(band_force(state, b) for b in state.bands.values() if b.tribe_id == tid and b.population > 0)


def gap(state, a: int, b: int) -> int:
    """Distance entre les bandes les plus proches des deux peuples."""
    xs = [x.position for x in state.bands.values() if x.tribe_id == a and x.population > 0]
    ys = [y.position for y in state.bands.values() if y.tribe_id == b and y.population > 0]
    world = state.world
    return min((world.distance(x, y) for x in xs for y in ys), default=10**6)


def pop_of(state, tid: int) -> int:
    return sum(b.population for b in state.bands.values() if b.tribe_id == tid and b.population > 0)


# --- propositions -----------------------------------------------------------------------

ACTIONS = ("cadeau", "treve", "alliance", "commerce", "tribut", "union", "rompre")
ACTION_LABELS = {
    "cadeau": "Offrir des vivres",
    "treve": "Proposer une treve",
    "alliance": "Proposer une alliance",
    "commerce": "Proposer des echanges",
    "tribut": "Exiger un tribut",
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
    from src.kora.peoples import culture_of

    return culture_of(state.tribes[tid]).raid_prestige <= 30


def _recent_raid(state, attacker: int, defender: int, weeks: int = 26):
    hit = _d(state).raids.get((attacker, defender))
    if hit is None or state.tick_count - hit[0] > weeks:
        return None
    return hit[1]


def _other_enemy(state, tid: int, but: int) -> bool:
    return any(t != but and relation(state, tid, t) <= -40 for t in contacts_of(state, tid))


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
            return Verdict(blocked=f"Aucune de vos bandes a moins de {GIFT_RANGE} cases d'eux")
        return Verdict(score=1, reasons=[("Un cadeau est toujours accepte", 1)])
    if action == "rompre":
        if not has_pact(state, actor, target):
            return Verdict(blocked="Aucun pacte avec eux")
        return Verdict(score=1, reasons=[("Rompre coute du prestige (-3) et de la relation (-20)", 0)])
    if action == "treve":
        if at_peace(state, actor, target):
            return Verdict(blocked="Vous etes deja en paix")
        out.append(("Base", -10))
        out.append(("Relation", round(rel * 0.5)))
        if ratio > 1.3:
            out.append(("Vous etes plus forts", 15))
        elif ratio < 0.6:
            out.append(("Vous etes plus faibles", -10))
        if _recent_raid(state, target, actor):
            out.append(("Leurs raids reussissent", -15))
        if _recent_raid(state, actor, target):
            out.append(("Vos raids les epuisent", 15))
        if _other_enemy(state, target, actor):
            out.append(("Ils ont d'autres ennemis", 10))
        if _warlike(state, target):
            out.append(("Peuple guerrier", -5))
    elif action == "alliance":
        if not bonus.alliance:
            return Verdict(blocked="Il faut connaitre Mariages entre clans")
        if allied(state, actor, target):
            return Verdict(blocked="Vous etes deja allies")
        if rel < 20:
            return Verdict(blocked=f"Relation trop basse ({rel:.0f}, il faut 20)")
        out.append(("Base", -30))
        out.append(("Relation", round(rel * 0.8)))
        if _common_enemy(state, actor, target):
            out.append(("Ennemi commun", 20))
        if 0.5 <= ratio <= 2.0:
            out.append(("Forces comparables", 10))
        elif ratio < 0.5:
            out.append(("Vous etes trop faibles", -10))
        if ally_count(state, target) >= 2:
            out.append(("Ils ont deja deux allies", -15))
    elif action == "commerce":
        from src.kora import goods

        if not bonus.commerce:
            return Verdict(blocked="Il faut connaitre Echanges lointains")
        if has_pact(state, actor, target, "commerce"):
            return Verdict(blocked="Un accord commercial est deja en place")
        if not goods.has_village(state, actor):
            return Verdict(blocked="Il vous faut un village")
        if not goods.has_village(state, target):
            return Verdict(blocked="Ils n'ont pas de village : rien a echanger")
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
            out.append(("Ils connaissent les echanges", 10))
        if dist <= 20:
            out.append(("Voisins", 5))
        if _recent_raid(state, actor, target, 52):
            out.append(("Vos raids recents", -20))
    elif action == "tribut":
        if has_pact(state, actor, target, "tribut"):
            return Verdict(blocked="Un tribut est deja en place")
        if allied(state, actor, target):
            return Verdict(blocked="On n'exige rien d'un allie")
        out.append(("Base", -40))
        out.append(("Rapport de forces", max(-30, min(50, round((ratio - 1.0) * 25)))))
        dist = gap(state, actor, target)
        if dist <= 20:
            out.append(("Vous etes a leur porte", 10))
        elif dist > 40:
            out.append(("Vous etes loin", -20))
        out.append(("Relation", round(rel * 0.2)))
        if state.tribes[target].prestige >= 50:
            out.append(("Trop fiers pour payer", -10))
    elif action == "union":
        if not bonus.union:
            return Verdict(blocked="Il faut connaitre Confederation")
        if state.tribes[target].is_player:
            return Verdict(blocked="Impossible")
        if rel < 50:
            return Verdict(blocked=f"Relation trop basse ({rel:.0f}, il faut 50)")
        pa, pt = max(1, pop_of(state, actor)), pop_of(state, target)
        if pt > 0.4 * pa:
            return Verdict(blocked="Ils sont trop nombreux (40 % de votre peuple au plus)")
        out.append(("Base", -20))
        out.append(("Relation", round((rel - 50) * 0.8)))
        out.append(("Vous etes bien plus nombreux", round((1.0 - pt / pa) * 30)))
        out.append(("Fiers de leur nom", -round(state.tribes[target].prestige * 0.3)))
        if state.tribes[target].minor:
            out.append(("Petit peuple", 10))
    else:
        return Verdict(blocked="?")
    if bonus.diplo:
        out.append(("Dons et palabres", bonus.diplo))
    if _betrayer(state, actor):
        out.append(("Vous avez trahi une parole", -25))
    out = [(label, v) for label, v in out if v]
    return Verdict(score=sum(v for _l, v in out), reasons=out)


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


def gift_value(state, actor: int, target: int, amount: float) -> float:
    base = 40.0 * amount / (4.0 * max(1, pop_of(state, target)) + 40.0)
    return min(25.0, base) * tech.bonuses(state.tribes[actor]).gifts


def perform(state, actor: int, target: int, action: str, amount: float = 0.0) -> str:
    """Executer une proposition ; rend le texte du resultat."""
    verdict = evaluate(state, actor, target, action)
    if verdict.blocked:
        return verdict.blocked
    d = _d(state)
    names = state.tribes[target].name
    if action == "cadeau":
        carrier, receiver = gift_carrier(state, actor, target)
        from src.kora.sim import stock_max

        amount = min(amount, max(0.0, carrier.stock - 2 * carrier.population))
        if amount <= 0:
            return "Pas assez de vivres a donner"
        carrier.stock -= amount
        receiver.stock = min(stock_max(receiver, state), receiver.stock + amount)
        add_mod(state, actor, target, "cadeau", gift_value(state, actor, target, amount), actor=actor)
        return f"Les {names} acceptent vos {amount:.0f} vivres."
    if action == "rompre":
        break_pact(state, actor, target)
        return f"Pacte rompu avec les {names}."
    d.cooldown[f"{action}:{actor}:{target}"] = state.tick_count
    if not verdict.accepted:
        if action == "tribut":
            add_mod(state, actor, target, "tribut_refuse", -10, actor=target)
            d.casus[(actor, target)] = state.tick_count + 52
            return f"Les {names} refusent de payer. Vous pouvez les raider sans trahir (1 an)."
        if action == "union":
            add_mod(state, actor, target, "union_refusee", -5, actor=target)
        return f"Les {names} refusent."
    if action == "treve":
        add_pact(state, actor, target, "treve", TRUCE_WEEKS)
        return f"Treve conclue avec les {names} (2 ans)."
    if action == "alliance":
        add_pact(state, actor, target, "alliance")
        add_mod(state, actor, target, "mariage", 15)
        from src.kora import chiefs

        chiefs.marriage_note(state, actor, target)
        return f"Alliance scellee avec les {names} par des mariages."
    if action == "tribut":
        add_pact(state, actor, target, "tribut", TRIBUTE_WEEKS, payer=target)
        return f"Les {names} paieront un tribut chaque saison (2 ans)."
    if action == "commerce":
        add_pact(state, actor, target, "commerce")
        add_mod(state, actor, target, "echanges", 5)
        return f"Accord commercial avec les {names} : vos villages echangeront leurs biens chaque mois."
    if action == "union":
        absorb(state, actor, target)
        return f"Les {names} rejoignent votre peuple."
    return ""


INVITE_RANGE = 12


def invitable(state, actor: int, target: int) -> list:
    """Clans du peuple `target` qui se detachent de leur chef, assez pres de
    chez vous pour qu'on sache leur mecontentement."""
    from src.kora import chiefs, influence
    from src.kora.vision import is_visible

    mine = [b.position for b in state.bands.values() if b.tribe_id == actor and b.population > 0]
    out = []
    for band in sorted(state.bands.values(), key=lambda b: b.id):
        if band.tribe_id != target or band.population <= 0 or chiefs.is_chief_band(state, band):
            continue
        if band.loyalty >= chiefs.OBEY:
            continue
        if state.tribes[actor].is_player and not is_visible(state, band.position):
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
    from src.kora import chiefs
    from src.kora.types import stay_order

    band = state.bands.get(band_id)
    if band is None or band not in invitable(state, actor, band.tribe_id):
        return "Ce clan ne peut pas etre invite"
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
    from src.kora import chiefs
    from src.kora.types import stay_order

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
    a.prestige = min(100, a.prestige + 8)
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
            if not at_peace(state, tid, other) and fought and rel > -60:
                if evaluate(state, tid, other, "treve").accepted:
                    perform(state, tid, other, "treve")
                    continue
            if rel >= 45 and not allied(state, tid, other) and tech.bonuses(tribe).alliance:
                if evaluate(state, tid, other, "alliance").accepted:
                    perform(state, tid, other, "alliance")
                    continue
            if rel >= 10 and tech.bonuses(tribe).commerce and not has_pact(state, tid, other, "commerce"):
                if not on_cooldown(state, tid, other, "commerce") and evaluate(state, tid, other, "commerce").accepted:
                    perform(state, tid, other, "commerce")
                    continue
            if (
                not has_pact(state, tid, other)
                and power(state, tid) > 2.5 * max(1.0, power(state, other))
                and rel <= 10
                and state.story_rng.random() < 0.15
            ):
                perform(state, tid, other, "tribut")


PROPOSE_EVERY = 52


def _propose_to_player(state, ai: int, player: int) -> None:
    """Un peuple IA fait une proposition au joueur (un evenement a decider).
    Il ne propose que ce qu'il accepterait lui-meme."""
    from src.kora import events

    d = _d(state)
    key = f"propose:{ai}:{player}"
    if state.tick_count - d.cooldown.get(key, -10**6) < PROPOSE_EVERY:
        return
    rel = relation(state, ai, player)
    fought = _recent_raid(state, ai, player, 52) is not None or _recent_raid(state, player, ai, 52) is not None
    kind = ""
    if not at_peace(state, ai, player) and fought and rel > -60 and evaluate(state, player, ai, "treve").accepted:
        kind = "offre_treve"
    elif rel >= 45 and not allied(state, ai, player) and tech.bonuses(state.tribes[ai]).alliance:
        if evaluate(state, player, ai, "alliance").accepted or rel >= 60:
            kind = "offre_alliance"
    elif (
        rel >= 10
        and tech.bonuses(state.tribes[ai]).commerce
        and not has_pact(state, ai, player, "commerce")
        and not evaluate(state, ai, player, "commerce").blocked
        and state.story_rng.random() < 0.5
    ):
        kind = "offre_commerce"
    elif (
        not has_pact(state, ai, player)
        and power(state, ai) > 2.5 * max(1.0, power(state, player))
        and rel <= 10
        and gap(state, ai, player) <= 30
        and state.story_rng.random() < 0.2
    ):
        kind = "exige_tribut"
    elif rel >= 25 and state.story_rng.random() < 0.08 and gift_carrier(state, ai, player) is not None:
        carrier, receiver = gift_carrier(state, ai, player)
        spare = carrier.stock - 6 * carrier.population
        if spare >= 40:
            from src.kora.sim import stock_max

            amount = min(150.0, spare)
            carrier.stock -= amount
            receiver.stock = min(stock_max(receiver, state), receiver.stock + amount)
            add_mod(state, ai, player, "cadeau", gift_value(state, ai, player, amount), actor=ai)
            _note(state, LogKind.POLITIQUE, f"Les {state.tribes[ai].name} vous offrent {amount:.0f} vivres.", receiver.position)
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


def _note(state, kind, text: str, where=None) -> None:
    state.log.add(kind, text, state.clock.year, state.clock.week, where=where)
