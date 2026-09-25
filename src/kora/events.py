"""Evenements en chaines (voir la spec 2026-09-24, section 8).

Un evenement (events_data.EVENTS) a des conditions, un texte et des
options. Une option applique des effets, OU tire une issue parmi
plusieurs (chances modifiees par les savoirs, les traits, les forces).
Elle peut programmer des suites : (evenement, probabilite, delai). Une
suite n'est jamais sure : elle est tiree au sort, puis ses conditions
sont revues le jour ou elle arrive. Les drapeaux (Tribe.flags) gardent
la memoire d'un choix pour plus tard.

Declencheurs :
  - tirage mensuel par peuple (avec un delai minimum entre deux) ;
  - crochets de la simulation : hook("contact"), hook("clan_part"),
    hook("succession"), hook("cache_trouvee"), propositions de l'IA...
Le joueur voit une carte "A decider" ; le temps continue ; l'ouvrir met
en pause ; a l'echeance, l'option par defaut (la plus sage) est prise.
L'IA vit les memes evenements et choisit seule, tout de suite.

Le texte des effets affiche est tire des donnees (summarize), comme pour
les savoirs. N'importe ni pygame ni render ; sim est importe a la demande.
"""

from __future__ import annotations

import copy
from dataclasses import dataclass, field

from src.kora.log import LogKind

# Semaines minimum entre deux evenements "au hasard" pour un peuple.
PLAYER_GAP = 16
AI_GAP = 30
# Au plus cette chance par mois de tirer un evenement au hasard.
PULSE_CAP = 0.45
MAX_PENDING = 4

MOOD_COLORS = {
    "danger": (200, 90, 70),
    "chance": (120, 190, 110),
    "esprit": (150, 130, 210),
    "peuple": (90, 160, 220),
    "neutre": (210, 180, 90),
}


@dataclass(frozen=True)
class Follow:
    event: str
    prob: float
    delay: tuple = (2, 6)
    # "" : meme bande ; "other_band" : une autre bande du meme peuple.
    retarget: str = ""


@dataclass(frozen=True)
class Outcome:
    chance: float
    effects: tuple = ()
    follow: tuple = ()
    text: str = ""
    # (condition, +chance) : les savoirs et les traits changent les chances.
    mods: tuple = ()


@dataclass(frozen=True)
class Option:
    label: str
    effects: tuple = ()
    outcomes: tuple = ()
    follow: tuple = ()
    requires: tuple = ()
    ai: float = 1.0
    text: str = ""


@dataclass(frozen=True)
class Event:
    id: str
    title: str
    text: str
    scope: str = "band"  # "band" ou "tribe"
    trigger: str = "pulse"  # "pulse", "follow", ou le nom d'un crochet
    weight: float = 0.0
    conds: tuple = ()
    options: tuple = ()
    mood: str = "neutre"
    once: bool = False
    cooldown: int = 0
    player_only: bool = False
    deadline: int = 16
    # Options fabriquees a la volee (succession : un choix par candidat).
    special: str = ""


@dataclass
class Instance:
    uid: int
    event_id: str
    tribe_id: int
    band_id: int = 0
    other: int = 0
    site_id: int = 0
    rival: int = 0
    deadline: int = 0
    data: dict = field(default_factory=dict)


@dataclass
class Book:
    pending: list = field(default_factory=list)
    # (semaine, evenement, portee) : suites programmees.
    scheduled: list = field(default_factory=list)
    last: dict = field(default_factory=dict)
    fired: dict = field(default_factory=dict)
    next_uid: int = 1


def _book(state) -> Book:
    if not isinstance(state.events, Book):
        state.events = Book()
    return state.events


def _events():
    from src.kora.events_data import EVENTS as data

    return data


class _Lazy(dict):
    """EVENTS charge events_data a la premiere lecture (pas d'import croise)."""

    def _fill(self):
        if not dict.__len__(self):
            dict.update(self, _events())

    def get(self, key, default=None):
        self._fill()
        return dict.get(self, key, default)

    def __getitem__(self, key):
        self._fill()
        return dict.__getitem__(self, key)

    def __contains__(self, key):
        self._fill()
        return dict.__contains__(self, key)

    def values(self):
        self._fill()
        return dict.values(self)

    def items(self):
        self._fill()
        return dict.items(self)

    def __iter__(self):
        self._fill()
        return dict.__iter__(self)

    def __len__(self):
        self._fill()
        return dict.__len__(self)


EVENTS = _Lazy()


# --- portee ---------------------------------------------------------------------


def _band(state, inst):
    band = state.bands.get(inst.band_id)
    if band is None or band.population <= 0 or band.tribe_id != inst.tribe_id:
        return None
    return band


def _alive(state, tid: int) -> bool:
    return any(b.tribe_id == tid and b.population > 0 for b in state.bands.values())


def names(state, inst) -> dict:
    from src.kora import chiefs

    tribe = state.tribes.get(inst.tribe_id)
    band = _band(state, inst)
    chief = chiefs.chief_of(state, inst.tribe_id)
    other = state.tribes.get(inst.other)
    rival = state.bands.get(inst.rival)
    leader = band.leader.name if band is not None and band.leader is not None else "le chef de bande"
    count = sum(1 for b in state.bands.values() if b.tribe_id == inst.tribe_id and b.population > 0)
    if band is None:
        band_txt = "la tribu"
    elif count <= 1:
        band_txt = "votre bande"
    elif chiefs.is_chief_band(state, band):
        band_txt = "la bande du chef"
    else:
        band_txt = f"le clan de {leader}"
    if rival is not None and rival.leader is not None:
        leader_rival = rival.leader.name
    else:
        leader_rival = leader
    return {
        "band": band_txt,
        "Band": band_txt[:1].upper() + band_txt[1:],
        "leader": leader,
        "rival": leader_rival,
        "chief": chief.name if chief is not None else "le chef",
        "tribe": tribe.name if tribe is not None else "?",
        "other": other.name if other is not None else "etrangers",
        "pop": str(band.population) if band is not None else "?",
        **{k: str(v) for k, v in inst.data.items()},
    }


def _fmt(state, inst, text: str) -> str:
    try:
        return text.format(**names(state, inst))
    except (KeyError, IndexError, ValueError):
        return text


# --- conditions -------------------------------------------------------------------


def check(state, inst, cond) -> bool:
    """Une condition (nom, arguments...) sur la portee de l'evenement."""
    from src.kora import chiefs, sites
    from src.kora.sim import local_winter_weeks, max_bands_of, tribe_band_count

    kind, *args = cond
    tribe = state.tribes.get(inst.tribe_id)
    if tribe is None:
        return False
    band = _band(state, inst)
    world = state.world
    if kind == "chance":
        return state.story_rng.random() < args[0]
    if kind == "knows":
        return args[0] in tribe.knowledge
    if kind == "not_knows":
        return args[0] not in tribe.knowledge
    if kind == "flag":
        return args[0] in tribe.flags
    if kind == "no_flag":
        return args[0] not in tribe.flags
    if kind == "prestige_ge":
        return tribe.prestige >= args[0]
    if kind == "prestige_lt":
        return tribe.prestige < args[0]
    if kind == "week_between":
        return args[0] <= state.clock.week <= args[1]
    if kind == "bands_ge":
        return tribe_band_count(state, tribe.id) >= args[0]
    if kind == "can_split":
        return band is not None and tribe_band_count(state, tribe.id) < max_bands_of(state, tribe.id)
    if kind == "other_alive":
        return inst.other in state.tribes and _alive(state, inst.other)
    if kind == "other_teaches":
        other = state.tribes.get(inst.other)
        return other is not None and bool(other.knowledge - tribe.knowledge)
    if kind == "has_rival":
        return _rival_band(state, inst.tribe_id) is not None
    if kind == "chief_trait":
        chief = chiefs.chief_of(state, tribe.id)
        return chief is not None and args[0] in chief.traits
    if kind == "learning":
        return bool(tribe.learning)
    if band is None:
        return False
    if kind == "season":
        return world.hex_season(band.position).value in args
    if kind == "terrain":
        return world.terrain(band.position).value in args
    if kind == "stock_lt":
        return band.stock < args[0] * band.population
    if kind == "stock_ge":
        return band.stock >= args[0] * band.population
    if kind == "pop_ge":
        return band.population >= args[0]
    if kind == "pop_lt":
        return band.population < args[0]
    if kind == "winter_long":
        return local_winter_weeks(world, band.position) >= args[0]
    if kind == "chief_band":
        return chiefs.is_chief_band(state, band)
    if kind == "not_chief_band":
        return not chiefs.is_chief_band(state, band)
    if kind == "at_camp":
        return sites.camp_at(state, band) is not None
    if kind == "crowded":
        mates = [
            b
            for b in state.bands.values()
            if b.id != band.id and b.tribe_id == band.tribe_id and world.distance(b.position, band.position) <= 3
        ]
        return len(mates) >= args[0]
    if kind == "leader_trait":
        return band.leader is not None and args[0] in band.leader.traits
    if kind == "leader_not_trait":
        return band.leader is None or args[0] not in band.leader.traits
    if kind == "loyalty_lt":
        return band.loyalty < args[0]
    if kind == "near_chief":
        heart = chiefs.chief_band(state, tribe.id)
        return heart is not None and world.distance(heart.position, band.position) <= args[0]
    if kind == "chief_stronger":
        heart = chiefs.chief_band(state, tribe.id)
        return heart is not None and heart.id != band.id and heart.population > band.population
    if kind == "site_alive":
        return inst.site_id in state.sites
    if kind == "is_rival":
        rival = _rival_band(state, tribe.id)
        return rival is not None and rival.id == band.id
    if kind == "village":
        return bool(band.village)
    if kind == "not_village":
        return not band.village
    if kind == "crafts":
        # Des gens de metier au village (goods.py).
        from src.kora import goods, villages

        return goods.total_teams(villages.site_of(state, band)) > 0
    if kind == "trade_partner":
        # Un partenaire dont une route a porte le dernier mois : "l'autre".
        from src.kora import goods

        active = sorted(
            (r.importer if r.exporter == tribe.id else r.exporter)
            for r in goods.routes_of(state, tribe.id)
            if r.units > 0
        )
        if not active:
            return False
        inst.other = active[0]
        return True
    if kind == "no_trade":
        from src.kora import diplo

        return not any(
            diplo.has_pact(state, tribe.id, other, "commerce") for other in state.tribes if other != tribe.id
        )
    if kind == "foreign_near":
        # Une bande etrangere (pas en paix) tout pres : elle devient "l'autre".
        from src.kora import diplo

        near = [
            b
            for b in state.bands.values()
            if b.tribe_id != tribe.id
            and b.population > 0
            and not diplo.at_peace(state, b.tribe_id, tribe.id)
            and world.distance(b.position, band.position) <= args[0]
        ]
        if not near:
            return False
        near.sort(key=lambda b: (world.distance(b.position, band.position), b.id))
        inst.other = near[0].tribe_id
        return True
    return False


def _rival_band(state, tid: int):
    from src.kora import chiefs

    chief = chiefs.chief_of(state, tid)
    if chief is None:
        return None
    for b in sorted(state.bands.values(), key=lambda b: b.id):
        if b.tribe_id != tid or b.leader is None or chiefs.is_chief_band(state, b):
            continue
        if b.leader.renown >= chief.renown + 10 and "fidele" not in b.leader.traits:
            return b
    return None


def conds_ok(state, inst, conds) -> bool:
    return all(check(state, inst, c) for c in conds)


# --- effets ---------------------------------------------------------------------


def _deaths(state, band, lo: int, hi: int) -> int:
    n = state.story_rng.randint(min(lo, hi), max(lo, hi))
    n = max(-band.population, n)
    band.population += n
    return n


def apply(state, inst, effect) -> None:
    from src.kora import chiefs, diplo, sites, tech
    from src.kora.sim import set_goto, split_band, stock_max

    kind, *args = effect
    tribe = state.tribes.get(inst.tribe_id)
    band = _band(state, inst)
    if tribe is None:
        return
    if kind == "prestige":
        tribe.prestige = max(0, min(100, tribe.prestige + args[0]))
    elif kind == "flag":
        weeks = args[1] if len(args) > 1 else -1
        tribe.flags[args[0]] = -1 if weeks < 0 else state.tick_count + weeks
    elif kind == "unflag":
        tribe.flags.pop(args[0], None)
    elif kind == "loyalty_all":
        for b in state.bands.values():
            if b.tribe_id == tribe.id and not chiefs.is_chief_band(state, b):
                b.loyalty = max(0.0, min(100.0, b.loyalty + args[0]))
    elif kind == "loyalty_near":
        if band is not None:
            for b in state.bands.values():
                if b.tribe_id == tribe.id and state.world.distance(b.position, band.position) <= 3:
                    if not chiefs.is_chief_band(state, b):
                        b.loyalty = max(0.0, min(100.0, b.loyalty + args[0]))
    elif kind == "stock_all":
        for b in state.bands.values():
            if b.tribe_id == tribe.id:
                b.stock = max(0.0, min(stock_max(b, state), b.stock + args[0] * b.population))
    elif kind == "stock_near":
        if band is not None:
            for b in state.bands.values():
                if b.tribe_id == tribe.id and state.world.distance(b.position, band.position) <= 3:
                    b.stock = max(0.0, min(stock_max(b, state), b.stock + args[0] * b.population))
    elif kind == "chief_renown":
        chief = chiefs.chief_of(state, tribe.id)
        if chief is not None:
            chief.renown = max(0, chief.renown + args[0])
    elif kind == "chief_trait":
        chief = chiefs.chief_of(state, tribe.id)
        if chief is not None and args[0] not in chief.traits:
            chief.traits = chief.traits + (args[0],)
    elif kind == "relation":
        if inst.other in state.tribes:
            key = "accueil" if args[0] > 0 else "chasses"
            diplo.make_contact(state, tribe.id, inst.other, quiet=True)
            diplo.add_mod(state, tribe.id, inst.other, key, args[0], actor=tribe.id)
    elif kind == "pact":
        if inst.other in state.tribes and _alive(state, inst.other):
            what = args[0]
            if what == "treve":
                diplo.add_pact(state, tribe.id, inst.other, "treve", diplo.TRUCE_WEEKS)
            elif what == "alliance":
                diplo.add_pact(state, tribe.id, inst.other, "alliance")
                diplo.add_mod(state, tribe.id, inst.other, "mariage", 15)
            elif what == "tribut_paye":
                diplo.add_pact(state, tribe.id, inst.other, "tribut", diplo.TRIBUTE_WEEKS, payer=tribe.id)
            elif what == "commerce":
                diplo.add_pact(state, tribe.id, inst.other, "commerce")
                diplo.add_mod(state, tribe.id, inst.other, "echanges", 5)
    elif kind == "casus":
        if inst.other in state.tribes:
            state.diplo.casus[(inst.other, tribe.id)] = state.tick_count + 52
            diplo.add_mod(state, inst.other, tribe.id, "tribut_refuse", -10, actor=tribe.id)
    elif kind == "tech_progress":
        # Une part d'un savoir que l'autre peuple connait et pas vous.
        other = state.tribes.get(inst.other)
        pool = sorted(other.knowledge - tribe.knowledge) if other is not None else []
        pool = [t for t in pool if not [p for p in tech.TECHS[t].prereqs if p not in tribe.knowledge]] or pool
        if pool:
            tid = state.story_rng.choice(pool)
            cost = tech.TECHS[tid].cost
            tribe.progress[tid] = min(cost - 1.0, tribe.progress.get(tid, 0.0) + cost * args[0])
            inst.data["savoir"] = tech.TECHS[tid].name
    elif kind == "tech_progress_id":
        tid, share = args
        if tid in tech.TECHS and tid not in tribe.knowledge:
            cost = tech.TECHS[tid].cost
            tribe.progress[tid] = min(cost - 1.0, tribe.progress.get(tid, 0.0) + cost * share)
    elif kind == "reveal":
        _reveal(state, inst, args[0])
    elif kind == "provoke":
        _provoke(state, inst)
    elif kind == "crown":
        target = state.bands.get(args[0]) if args else band
        if target is not None and target.tribe_id == tribe.id:
            chiefs.crown(state, tribe.id, target.id, quiet=True)
    elif kind == "learn_boost":
        # Le savoir en cours d'apprentissage avance.
        tid = tribe.learning
        if tid and tid in tech.TECHS:
            cost = tech.TECHS[tid].cost
            tribe.progress[tid] = min(cost - 1.0, tribe.progress.get(tid, 0.0) + cost * args[0])
            inst.data["savoir"] = tech.TECHS[tid].name
    elif kind == "rival_loyalty":
        rival = state.bands.get(inst.rival)
        if rival is not None and rival.tribe_id == tribe.id:
            rival.loyalty = max(0.0, min(100.0, rival.loyalty + args[0]))
    elif band is None:
        return
    elif kind == "stock":
        band.stock = max(0.0, min(stock_max(band, state), band.stock + args[0] * band.population))
    elif kind == "good":
        from src.kora import goods

        tribe.goods[args[0]] = min(goods.CAP, tribe.goods.get(args[0], 0.0) + args[1])
    elif kind == "lose_goods":
        # Une charge perdue : du bien dont le peuple a le plus.
        if tribe.goods:
            good = max(sorted(tribe.goods), key=lambda g: tribe.goods[g])
            left = tribe.goods[good] - args[0]
            if left > 1e-6:
                tribe.goods[good] = left
            else:
                del tribe.goods[good]
    elif kind == "craft_bonus":
        # Une belle veine : de chaque bien que fait le village.
        from src.kora import goods, villages

        site = villages.site_of(state, band)
        for cid, n in sorted(goods.teams(site).items()):
            craft = goods.CRAFTS.get(cid)
            if n and craft is not None and craft.good:
                tribe.goods[craft.good] = min(goods.CAP, tribe.goods.get(craft.good, 0.0) + args[0])
    elif kind == "pop":
        _deaths(state, band, args[0], args[1])
    elif kind == "pop_pct":
        band.population = max(1, int(round(band.population * (1.0 + args[0]))))
    elif kind == "loyalty":
        if not chiefs.is_chief_band(state, band):
            band.loyalty = max(0.0, min(100.0, band.loyalty + args[0]))
    elif kind == "loyalty_set":
        if not chiefs.is_chief_band(state, band):
            band.loyalty = float(args[0])
    elif kind == "renown":
        if band.leader is not None:
            band.leader.renown = max(0, band.leader.renown + args[0])
    elif kind == "trait":
        if band.leader is not None and args[0] not in band.leader.traits:
            band.leader.traits = band.leader.traits + (args[0],)
    elif kind == "heir":
        chiefs.set_heir(state, band.id)
    elif kind == "stop":
        from src.kora.types import stay_order

        if not band.retreating:
            band.path = []
            band.order = stay_order()
    elif kind == "goto_far":
        spot = _far_spot(state, band, args[0], args[1])
        if spot is not None:
            set_goto(state, band.id, spot, max_nodes=600, max_cost=1200)
    elif kind == "goto_warm":
        spot = _warm_spot(state, band, args[0])
        if spot is not None:
            set_goto(state, band.id, spot, max_nodes=800, max_cost=1500)
    elif kind == "split":
        nid = split_band(state, band.id)
        if nid is not None and len(args) >= 2:
            child = state.bands[nid]
            spot = _far_spot(state, child, args[0], args[1])
            if spot is not None:
                set_goto(state, nid, spot, max_nodes=800, max_cost=1500)
    elif kind == "secede":
        chiefs.secede(state, band.id, hostile=bool(args and args[0]))
    elif kind == "camp":
        sites.make_camp(state, band.id)
    elif kind == "stock_pct":
        band.stock = max(0.0, band.stock * (1.0 + args[0]))
    elif kind == "seed_pct":
        from src.kora import villages

        site = villages.site_of(state, band)
        if site is not None:
            site.data["seed"] = max(0.0, site.data.get("seed", 0.0) * (1.0 + args[0]))
    elif kind == "eat_seed":
        from src.kora import villages

        inst.data["butin"] = int(villages.eat_seed(state, band))
    elif kind == "burn":
        from src.kora import villages

        villages.pillaged(state, band)
    elif kind == "steal_cache":
        site = state.sites.get(inst.site_id)
        if site is not None and site.store >= 1:
            take = min(site.store, max(0.0, stock_max(band, state) - band.stock))
            band.stock += take
            site.store -= take
            inst.data["butin"] = int(take)


def _far_spot(state, band, lo: int, hi: int):
    from src.kora.world import enter_cost_for, food_production

    world = state.world
    around, dists = world.hexes_and_distances(band.position, hi)
    best = None
    tribe = state.tribes.get(band.tribe_id)
    water = bool(tribe and tribe.cabotage)
    for h, d in zip(around[::3], dists[::3]):
        if d < lo or enter_cost_for(world, h, water) is None:
            continue
        v = food_production(world, h, world.hex_season(h)) + state.story_rng.random() * 0.3
        if best is None or v > best[0]:
            best = (v, h)
    return None if best is None else best[1]


def _warm_spot(state, band, reach: int):
    from src.kora.world import axial_to_offset, enter_cost_for, offset_to_axial

    world = state.world
    col, row = axial_to_offset(world.canonicalize(band.position))
    mid = world.height // 2
    step = reach if row < mid else -reach
    target_row = row + step if abs(row - mid) > reach else mid
    for dc in (0, 3, -3, 6, -6, 9, -9):
        h = offset_to_axial((col + dc) % world.width, max(0, min(world.height - 1, target_row)))
        if enter_cost_for(world, h, False) is not None:
            return h
    return None


def _reveal(state, inst, radius: int) -> None:
    from src.kora.vision import PlayerVision

    tribe = state.tribes.get(inst.tribe_id)
    if tribe is None or not tribe.is_player or not isinstance(state.vision, PlayerVision):
        return
    band = _band(state, inst)
    if band is None:
        return
    world = state.world
    # Un pays lointain : le peuple inconnu le plus proche, sinon au hasard.
    unknown = [
        b for b in state.bands.values()
        if b.tribe_id != tribe.id and b.population > 0 and b.position not in state.vision.explored
    ]
    unknown.sort(key=lambda b: (world.distance(b.position, band.position), b.id))
    if unknown:
        center = unknown[0].position
    else:
        from src.kora.world import offset_to_axial

        center = offset_to_axial(state.story_rng.randrange(world.width), world.height // 2)
    state.vision.explored |= set(world.hexes_in_radius(center, radius))
    inst.data["lieu"] = "vers le soleil levant" if center.q > band.position.q else "vers le couchant"


def _provoke(state, inst) -> None:
    """Le peuple offense prepare un raid s'il peut le gagner."""
    from src.kora.ai_war import plan_raid, start_plan

    band = _band(state, inst)
    if band is None or inst.other not in state.tribes:
        return
    theirs = [b for b in state.bands.values() if b.tribe_id == inst.other and b.population > 0]
    theirs.sort(key=lambda b: (state.world.distance(b.position, band.position), b.id))
    for foe in theirs[:2]:
        plan = plan_raid(state, foe, 6)
        if plan is not None:
            start_plan(state, foe, plan)
            return


# --- options ---------------------------------------------------------------------


def _chance(state, inst, outcome: Outcome) -> float:
    c = outcome.chance
    for cond, delta in outcome.mods:
        if check(state, inst, cond):
            c += delta
    return max(0.0, c)


def _roll(state, inst, outcomes: tuple) -> Outcome:
    weights = [_chance(state, inst, o) for o in outcomes]
    total = sum(weights) or 1.0
    pick = state.story_rng.random() * total
    for o, w in zip(outcomes, weights):
        pick -= w
        if pick <= 0:
            return o
    return outcomes[-1]


def options_for(state, inst) -> list[dict]:
    """Options pour l'affichage : libelle, raison si bloquee, resume des
    effets, details (issues et chances)."""
    ev = EVENTS.get(inst.event_id)
    if ev is None:
        return []
    if ev.special == "succession":
        return _succession_options(state, inst)
    out = []
    for opt in ev.options:
        blocked = ""
        for cond in opt.requires:
            if not check(state, inst, cond):
                blocked = _require_text(cond)
                break
        out.append(
            {
                "label": _fmt(state, inst, opt.label),
                "blocked": blocked,
                "summary": summarize(state, inst, opt),
                "details": details(state, inst, opt),
            }
        )
    return out


def _require_text(cond) -> str:
    kind, *args = cond
    return {
        "prestige_ge": f"Il faut {args[0] if args else ''} de prestige",
        "not_chief_band": "Pas pour la bande du chef",
        "chief_band": "Seulement pour la bande du chef",
        "stock_ge": f"Il faut {args[0] if args else ''} semaines de vivres",
        "can_split": "Trop de bandes deja",
        "knows": "Il faut un savoir",
    }.get(kind, "Impossible pour l'instant")


EFFECT_TEXT = {
    "prestige": lambda a: f"{'+' if a[0] >= 0 else ''}{a[0]} prestige",
    "stock": lambda a: f"{'+' if a[0] >= 0 else ''}{a[0]:g} sem. de vivres",
    "stock_all": lambda a: f"{'+' if a[0] >= 0 else ''}{a[0]:g} sem. de vivres pour toute la tribu",
    "stock_near": lambda a: f"{'+' if a[0] >= 0 else ''}{a[0]:g} sem. de vivres pour les clans presents",
    "pop": lambda a: (f"{-a[1]} a {-a[0]} morts" if a[0] < 0 else f"+{a[0]} a {a[1]} personnes"),
    "pop_pct": lambda a: f"{round(-a[0] * 100)} % de la bande meurt" if a[0] < 0 else f"+{round(a[0] * 100)} % de monde",
    "loyalty": lambda a: f"attachement {'+' if a[0] >= 0 else ''}{a[0]}",
    "loyalty_set": lambda a: f"attachement ramene a {a[0]}",
    "loyalty_all": lambda a: f"attachement de tous les clans {'+' if a[0] >= 0 else ''}{a[0]}",
    "loyalty_near": lambda a: f"attachement des clans presents {'+' if a[0] >= 0 else ''}{a[0]}",
    "rival_loyalty": lambda a: f"attachement de son clan {'+' if a[0] >= 0 else ''}{a[0]}",
    "renown": lambda a: f"renommee {'+' if a[0] >= 0 else ''}{a[0]}",
    "chief_renown": lambda a: f"renommee du chef {'+' if a[0] >= 0 else ''}{a[0]}",
    "relation": lambda a: f"relation {'+' if a[0] >= 0 else ''}{a[0]}",
    "stop": lambda a: "la bande s'arrete",
    "goto_far": lambda a: f"la bande part ({a[0]} a {a[1]} cases)",
    "goto_warm": lambda a: "la bande part vers un hiver plus court",
    "split": lambda a: "une partie de la bande part fonder un clan",
    "secede": lambda a: "le clan quitte la tribu",
    "heir": lambda a: "il devient l'heritier",
    "crown": lambda a: "il devient chef",
    "camp": lambda a: "un campement ici",
    "steal_cache": lambda a: "les vivres de la cache",
    "tech_progress": lambda a: f"un de leurs savoirs avance de {round(a[0] * 100)} %",
    "tech_progress_id": lambda a: f"{_tech_name(a[0])} avance de {round(a[1] * 100)} %",
    "learn_boost": lambda a: f"le savoir en cours avance de {round(a[0] * 100)} %",
    "reveal": lambda a: "une contree lointaine apparait sur la carte",
    "provoke": lambda a: "ils pourraient venir se venger",
    "pact": lambda a: {"treve": "treve de 2 ans", "alliance": "alliance", "tribut_paye": "vous payez un tribut (2 ans)", "commerce": "accord commercial : echanges chaque mois"}.get(a[0], a[0]),
    "casus": lambda a: "ils pourront vous raider sans trahir",
    "stock_pct": lambda a: f"{round(a[0] * 100)} % du grenier" if a[0] < 0 else f"+{round(a[0] * 100)} % au grenier",
    "seed_pct": lambda a: f"{round(a[0] * 100)} % des semences",
    "eat_seed": lambda a: "on mange les semences : pas de champs au printemps",
    "burn": lambda a: "la prochaine recolte sera maigre",
    "good": lambda a: f"+{a[1]} {_good_name(a[0])} a la reserve du peuple",
    "craft_bonus": lambda a: f"+{a[0]} de chaque bien que fait le village",
    "lose_goods": lambda a: f"-{a[0]} charges de votre reserve",
}


def _good_name(good: str) -> str:
    from src.kora import goods

    return goods.GOOD_NAMES.get(good, good).lower()


def _tech_name(tid: str) -> str:
    from src.kora import tech

    t = tech.TECHS.get(tid)
    return t.name if t else tid


def _trait_name(tid: str) -> str:
    from src.kora import chiefs

    t = chiefs.TRAITS.get(tid)
    return t.name if t else tid


def effect_text(effect) -> str:
    kind, *args = effect
    if kind in ("trait", "chief_trait"):
        who = "le chef de bande" if kind == "trait" else "le chef"
        return f"{who} devient {_trait_name(args[0])}"
    if kind in ("flag", "unflag"):
        return ""
    fn = EFFECT_TEXT.get(kind)
    return fn(args) if fn else ""


def _effects_text(effects) -> str:
    parts = [effect_text(e) for e in effects]
    return ", ".join(p for p in parts if p)


def summarize(state, inst, opt: Option) -> str:
    if opt.outcomes:
        chunks = []
        weights = [_chance(state, inst, o) for o in opt.outcomes]
        total = sum(weights) or 1.0
        for o, w in zip(opt.outcomes, weights):
            what = _effects_text(o.effects) or "rien de plus"
            chunks.append(f"{round(100 * w / total)} % : {what}")
        head = _effects_text(opt.effects)
        return (head + " ; " if head else "") + " / ".join(chunks)
    text = _effects_text(opt.effects)
    if opt.follow and not text:
        return "Qui sait ce qui suivra..."
    return text or "Rien de plus"


def details(state, inst, opt: Option) -> list[str]:
    out = []
    if opt.outcomes:
        weights = [_chance(state, inst, o) for o in opt.outcomes]
        total = sum(weights) or 1.0
        for o, w in zip(opt.outcomes, weights):
            out.append(f"{round(100 * w / total)} % : {_effects_text(o.effects) or 'rien de plus'}")
            for cond, delta in o.mods:
                if check(state, inst, cond):
                    out.append(f"    {_mod_text(cond)} : {'+' if delta >= 0 else ''}{round(delta * 100)} %")
    elif opt.effects:
        out.append(_effects_text(opt.effects))
    if opt.follow or any(o.follow for o in opt.outcomes):
        out.append("Cela pourrait avoir des suites.")
    return out


def _mod_text(cond) -> str:
    kind, *args = cond
    if kind == "knows":
        return f"Vous connaissez {_tech_name(args[0])}"
    if kind in ("leader_trait", "chief_trait"):
        who = "Chef de bande" if kind == "leader_trait" else "Chef"
        return f"{who} {_trait_name(args[0]).lower()}"
    if kind == "near_chief":
        return "Le chef est tout pres"
    if kind == "chief_stronger":
        return "La bande du chef est plus nombreuse"
    return kind


def _succession_options(state, inst) -> list[dict]:
    from src.kora import chiefs

    out = []
    for bid in inst.data.get("candidates", []):
        band = state.bands.get(bid)
        if band is None or band.leader is None or band.tribe_id != inst.tribe_id:
            continue
        traits = ", ".join(chiefs.TRAITS[t].name for t in band.leader.traits if t in chiefs.TRAITS) or "sans trait"
        out.append(
            {
                "label": f"{band.leader.name} ({chiefs.age(state, band.leader)} ans, {traits})",
                "blocked": "",
                "summary": f"Mene un clan de {band.population} personnes · renommee {band.leader.renown}",
                "details": [line for t in band.leader.traits if t in chiefs.TRAITS for line in chiefs.trait_lines(chiefs.TRAITS[t])],
                "band": bid,
            }
        )
    return out


# --- tirer, choisir -----------------------------------------------------------------


def _new_instance(state, ev: Event, tribe_id: int, band_id: int = 0, scope: dict | None = None) -> Instance:
    scope = scope or {}
    book = _book(state)
    inst = Instance(
        uid=book.next_uid,
        event_id=ev.id,
        tribe_id=tribe_id,
        band_id=int(band_id or 0),
        other=int(scope.get("other", 0) or 0),
        site_id=int(scope.get("site_id", 0) or 0),
        rival=int(scope.get("rival", 0) or 0),
        data=dict(scope.get("data", {})),
    )
    book.next_uid += 1
    return inst


def _eligible(state, ev: Event, inst: Instance) -> bool:
    book = _book(state)
    tribe = state.tribes.get(inst.tribe_id)
    if tribe is None:
        return False
    if ev.player_only and not tribe.is_player:
        return False
    key = f"{inst.tribe_id}:{ev.id}"
    last = book.fired.get(key)
    if ev.once and last is not None:
        return False
    if ev.cooldown and last is not None and state.tick_count - last < ev.cooldown:
        return False
    return conds_ok(state, inst, ev.conds)


def fire(state, inst: Instance) -> bool:
    """L'evenement arrive. Joueur : carte a decider (True). IA : choix
    immediat (False)."""
    ev = EVENTS.get(inst.event_id)
    tribe = state.tribes.get(inst.tribe_id)
    if ev is None or tribe is None:
        return False
    book = _book(state)
    book.fired[f"{inst.tribe_id}:{ev.id}"] = state.tick_count
    if tribe.is_player:
        if len(book.pending) >= MAX_PENDING:
            # Trop de cartes : on decide d'office la plus ancienne.
            decide_default(state, book.pending[0].uid)
        inst.deadline = state.tick_count + ev.deadline
        book.pending.append(inst)
        state.log.add(LogKind.DECOUVERTE, f"A decider : {ev.title}.", state.clock.year, state.clock.week)
        return True
    opts = options_for(state, inst)
    choices = [i for i, o in enumerate(opts) if not o["blocked"]]
    if not choices:
        return False
    if ev.special:
        index = choices[0]
    else:
        weights = [ev.options[i].ai for i in choices]
        total = sum(weights) or 1.0
        pick = state.story_rng.random() * total
        index = choices[-1]
        for i, w in zip(choices, weights):
            pick -= w
            if pick <= 0:
                index = i
                break
    resolve(state, inst, index)
    return False


def resolve(state, inst: Instance, index: int) -> str:
    """Applique l'option choisie ; rend le texte du resultat."""
    ev = EVENTS.get(inst.event_id)
    tribe = state.tribes.get(inst.tribe_id)
    if ev is None or tribe is None:
        return ""
    if ev.special == "succession":
        opts = _succession_options(state, inst)
        if not opts:
            return ""
        index = max(0, min(index, len(opts) - 1))
        bid = opts[index]["band"]
        apply(state, inst, ("crown", bid))
        band = state.bands.get(bid)
        text = f"{band.leader.name} mene desormais la tribu." if band is not None and band.leader else ""
        if tribe.is_player and text:
            state.log.add(LogKind.POLITIQUE, text, state.clock.year, state.clock.week)
        # Un ambitieux ecarte peut contester.
        from src.kora import chiefs

        for other in inst.data.get("candidates", []):
            ob = state.bands.get(other)
            if ob is None or other == bid or ob.leader is None:
                continue
            if "ambitieux" in ob.leader.traits and state.story_rng.random() < 0.6:
                _schedule(state, Follow("succession_contestee", 1.0, (3, 10)), inst, band_id=other, rival=other)
                break
        return text
    options = ev.options
    if not options:
        return ""
    index = max(0, min(index, len(options) - 1))
    opt = options[index]
    for effect in opt.effects:
        apply(state, inst, effect)
    follow = list(opt.follow)
    text = opt.text
    if opt.outcomes:
        outcome = _roll(state, inst, opt.outcomes)
        for effect in outcome.effects:
            apply(state, inst, effect)
        follow.extend(outcome.follow)
        text = outcome.text or text
    for f in follow:
        if state.story_rng.random() < f.prob:
            _schedule(state, f, inst)
    shown = _fmt(state, inst, text) if text else ""
    if tribe.is_player and shown:
        where = None
        band = state.bands.get(inst.band_id)
        if band is not None:
            where = band.position
        state.log.add(LogKind.DECOUVERTE, shown, state.clock.year, state.clock.week, where=where)
    return shown


def _schedule(state, f: Follow, inst: Instance, band_id: int | None = None, rival: int | None = None) -> None:
    lo, hi = f.delay
    when = state.tick_count + state.story_rng.randint(min(lo, hi), max(lo, hi))
    scope = {
        "tribe_id": inst.tribe_id,
        "band_id": inst.band_id if band_id is None else band_id,
        "other": inst.other,
        "site_id": inst.site_id,
        "rival": inst.rival if rival is None else rival,
        "retarget": f.retarget,
        "data": {k: v for k, v in inst.data.items() if isinstance(v, (int, str, float))},
    }
    _book(state).scheduled.append([when, f.event, scope])


def choose(state, uid: int, index: int) -> str:
    """Le joueur choisit une option d'une carte en attente."""
    book = _book(state)
    inst = find(state, uid)
    if inst is None:
        return ""
    opts = options_for(state, inst)
    if 0 <= index < len(opts) and opts[index]["blocked"]:
        return opts[index]["blocked"]
    book.pending = [p for p in book.pending if p.uid != uid]
    return resolve(state, inst, index)


def default_index(state, inst) -> int:
    ev = EVENTS.get(inst.event_id)
    opts = options_for(state, inst)
    choices = [i for i, o in enumerate(opts) if not o["blocked"]]
    if not choices:
        return 0
    if ev is None or ev.special:
        return choices[0]
    return max(choices, key=lambda i: (ev.options[i].ai, -i))


def decide_default(state, uid: int) -> None:
    inst = find(state, uid)
    if inst is None:
        return
    ev = EVENTS.get(inst.event_id)
    index = default_index(state, inst)
    opts = options_for(state, inst)
    label = opts[index]["label"] if index < len(opts) else "?"
    if ev is not None:
        state.log.add(
            LogKind.DECOUVERTE,
            f"Decide d'office ({ev.title}) : {label}.",
            state.clock.year,
            state.clock.week,
        )
    choose(state, uid, index)


def find(state, uid) -> Instance | None:
    if not isinstance(state.events, Book):
        return None
    return next((p for p in state.events.pending if p.uid == uid), None)


def pending(state) -> list:
    if not isinstance(state.events, Book):
        return []
    return list(state.events.pending)


def text_for(state, inst) -> str:
    ev = EVENTS.get(inst.event_id)
    return _fmt(state, inst, ev.text) if ev is not None else ""


# --- declencheurs -----------------------------------------------------------------


def hook(state, name: str, **scope) -> bool:
    """La simulation signale un moment ; rend True si un evenement du joueur
    attend sa decision (la simulation n'applique pas son choix par defaut)."""
    if not getattr(state, "story", False):
        return False
    tid = scope.get("tribe_id")
    if tid not in state.tribes:
        return False
    book = _book(state)
    band_id = scope.get("band_id", 0)
    if any(p.event_id == name and p.band_id == band_id and p.tribe_id == tid for p in book.pending):
        return True  # deja une carte ouverte pour ce moment
    fired = False
    for ev in sorted(EVENTS.values(), key=lambda e: e.id):
        if ev.trigger != name:
            continue
        if name == "succession":
            scope = dict(scope)
            from src.kora import chiefs

            ranked = chiefs.candidates(state, tid)
            scope["data"] = {
                "dead": scope.get("dead", "Le chef"),
                "cause": scope.get("cause", ""),
                "candidates": [b.id for b in ranked[:3]],
            }
        inst = _new_instance(state, ev, tid, scope.get("band_id", 0), scope)
        if not _eligible(state, ev, inst):
            continue
        fired = fire(state, inst)
        break
    return fired


def _rival_id(state, tid: int) -> int:
    band = _rival_band(state, tid)
    return band.id if band is not None else 0


def _band_scopes(state, tid: int) -> list:
    # Les histoires de clan (familles, camps, chasse) ne visent pas les troupes.
    bands = [b for b in state.bands.values() if b.tribe_id == tid and b.population > 0 and b.kind != "armee"]
    bands.sort(key=lambda b: b.id)
    state.story_rng.shuffle(bands)
    return bands


def monthly(state) -> None:
    """Tirage au hasard : au plus un evenement par peuple et par mois, avec
    un delai minimum entre deux."""
    if not getattr(state, "story", False):
        return
    book = _book(state)
    pulses = [e for e in sorted(EVENTS.values(), key=lambda e: e.id) if e.trigger == "pulse"]
    for tid in sorted(state.tribes):
        tribe = state.tribes[tid]
        if not _alive(state, tid):
            continue
        gap = PLAYER_GAP if tribe.is_player else AI_GAP
        if state.tick_count - book.last.get(tid, -1000) < gap:
            continue
        if not tribe.is_player and (state.tick_count // 4 + tid) % 2:
            continue  # l'IA tire un mois sur deux : moins de calcul
        found = []
        bands = _band_scopes(state, tid)
        for ev in pulses:
            if ev.scope == "tribe":
                inst = _new_instance(state, ev, tid, bands[0].id if bands else 0, {"rival": _rival_id(state, tid)})
                if _eligible(state, ev, inst):
                    found.append((ev, inst))
                continue
            for band in bands:
                inst = _new_instance(state, ev, tid, band.id, {"rival": _rival_id(state, tid)})
                if _eligible(state, ev, inst):
                    found.append((ev, inst))
                    break
        if not found:
            continue
        total = sum(ev.weight for ev, _i in found)
        if state.story_rng.random() >= min(PULSE_CAP, total):
            continue
        pick = state.story_rng.random() * total
        chosen = found[-1]
        for item in found:
            pick -= item[0].weight
            if pick <= 0:
                chosen = item
                break
        book.last[tid] = state.tick_count
        fire(state, chosen[1])


def weekly(state) -> None:
    """Suites programmees qui arrivent, echeances des cartes du joueur,
    drapeaux qui expirent."""
    for tribe in state.tribes.values():
        if tribe.flags:
            gone = [k for k, until in tribe.flags.items() if 0 <= until <= state.tick_count]
            for k in gone:
                del tribe.flags[k]
    if not isinstance(state.events, Book):
        return
    book = state.events
    due = [s for s in book.scheduled if s[0] <= state.tick_count]
    if due:
        book.scheduled = [s for s in book.scheduled if s[0] > state.tick_count]
        for _when, event_id, scope in due:
            ev = EVENTS.get(event_id)
            if ev is None:
                continue
            tid = scope.get("tribe_id")
            band_id = scope.get("band_id", 0)
            if scope.get("retarget") == "other_band":
                band_id = _other_band(state, tid, band_id)
                if not band_id:
                    continue
            inst = _new_instance(state, ev, tid, band_id, scope)
            if _eligible(state, ev, inst):
                fire(state, inst)
    for inst in list(book.pending):
        if inst.deadline <= state.tick_count:
            decide_default(state, inst.uid)
        elif inst.band_id and inst.band_id not in state.bands and EVENTS.get(inst.event_id, None) and EVENTS[inst.event_id].scope == "band":
            # La bande n'existe plus : l'evenement n'a plus d'objet.
            book.pending = [p for p in book.pending if p.uid != inst.uid]


def _other_band(state, tid, band_id) -> int:
    band = state.bands.get(band_id)
    others = [b for b in state.bands.values() if b.tribe_id == tid and b.id != band_id and b.population > 0]
    if band is not None:
        others = [b for b in others if state.world.distance(b.position, band.position) <= 25]
    others.sort(key=lambda b: b.id)
    return others[0].id if others else 0


# --- sauvegarde ------------------------------------------------------------------------


def copy_book(book):
    return copy.deepcopy(book) if isinstance(book, Book) else None


def to_json(book) -> dict:
    if not isinstance(book, Book):
        return {}
    return {
        "pending": [
            {
                "uid": p.uid,
                "event": p.event_id,
                "tribe": p.tribe_id,
                "band": p.band_id,
                "other": p.other,
                "site": p.site_id,
                "rival": p.rival,
                "deadline": p.deadline,
                "data": p.data,
            }
            for p in book.pending
        ],
        "scheduled": book.scheduled,
        "last": {str(k): v for k, v in book.last.items()},
        "fired": dict(book.fired),
        "next_uid": book.next_uid,
    }


def from_json(data):
    if not isinstance(data, dict) or not data:
        return None
    book = Book()
    for raw in data.get("pending", []):
        try:
            book.pending.append(
                Instance(
                    uid=int(raw["uid"]),
                    event_id=str(raw["event"]),
                    tribe_id=int(raw["tribe"]),
                    band_id=int(raw.get("band", 0)),
                    other=int(raw.get("other", 0)),
                    site_id=int(raw.get("site", 0)),
                    rival=int(raw.get("rival", 0)),
                    deadline=int(raw.get("deadline", 0)),
                    data=dict(raw.get("data", {})),
                )
            )
        except (KeyError, TypeError, ValueError):
            continue
    book.scheduled = [[int(s[0]), str(s[1]), dict(s[2])] for s in data.get("scheduled", []) if len(s) == 3]
    book.last = {int(k): int(v) for k, v in data.get("last", {}).items()}
    book.fired = {str(k): int(v) for k, v in data.get("fired", {}).items()}
    book.next_uid = int(data.get("next_uid", 1))
    return book
