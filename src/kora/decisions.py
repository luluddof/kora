"""LES DECISIONS (l'onglet Decisions, a la Crusader Kings 3, Europa
Universalis 5, Victoria 3 ; sa demande du 2026-11-10).

Une decision se prend QUAND le peuple le veut, des que ses conditions sont
remplies (certaines remplacent des evenements qui tombaient au hasard). Elle
a un nom, une famille, un texte, des CONDITIONS lisibles (avec les chiffres
du peuple), un COUT, des EFFETS, un REPOS (on ne la reprend pas avant N
ans), parfois une CIBLE (un village, une route, un peuple). L'IA prend aussi
les siennes (ai_monthly), avec les memes regles.

  La soudure (les semaines avant la recolte, quand le grenier ne tiendra
  pas) : RATIONNER (chacun mange RATION de sa part : moins de naissances, un
  peu de grogne, mais le grenier dure plus), ACHETER DU GRAIN (grain.py),
  MANGER LES SEMENCES (pas de faim maintenant, moins de champs ensuite), une
  RAZZIA sur un village (une troupe part le prendre ; vaincu, on le pille ou
  on le soumet), PILLER LES ROUTES de commerce (une troupe se poste sur une
  route d'autres peuples et prend une part de ce qui passe : seize), une
  GRANDE CHASSE.
  Le peuple et ses chefs : la grande fete (chiefdom.feast), le conseil des
  clans (remplace l'evenement du grand rassemblement), les eclaireurs.
  Le sacre : la fete des morts, les recits des anciens (remplace
  l'evenement du dernier des anciens).
  Les voisins : proposer un mariage.
  Les grands desseins : devenir le chef des chefs.

Ce qu'une decision laisse : Tribe.decided (id -> semaine prise : le repos),
Tribe.decision_effects (effet -> semaine de fin : des effets comme des
savoirs, "dec:...", systems.EFFECT_FIELDS), Tribe.ration_until (le
rationnement), Band.raid_route (une troupe qui pille une route).
Tout passe par commands.py ("decide").
N'importe pas pygame.
"""

from __future__ import annotations

import math
from dataclasses import dataclass, field
from typing import Callable

from src.kora import chiefdom, chiefs, diplo, goods, grain, guerre, places, population, sites, tech, troupes, villages
from src.kora.bands import gain_prestige, set_goto, set_march_to_band, stock_max
from src.kora.gamestate import is_human, note
from src.kora.log import LogKind
from src.kora.resources import GAME, PRESENT
from src.kora.vision import vision_of
from src.kora.world import axial_to_offset, offset_to_axial

WEEKS_PER_YEAR = 52
# La soudure : la part de chacun quand on rationne ; les naissances.
RATION = villages.RATION
# La soudure se voit quand il restera moins de tant de semaines de vivres a
# la recolte (villages.food_outlook).
LEAN_MARGIN = grain.PLAN_MARGIN
RATION_GROWTH = 0.5
RATION_STABILITY = -2
# Razzia et routes : jusqu'ou une troupe va (cases du village).
RAID_RANGE = 15
ROUTE_REACH = 12
# Une troupe postee a moins de tant de cases d'une route la pille ; la part
# de chaque mois qu'elle prend.
ROUTE_POST = 2
ROUTE_SEIZE = 0.5
ROUTE_RELATION = -15
ROUTE_CASUS_WEEKS = 104
# La grande chasse : semaines de vivres (par personne), le gibier a portee.
HUNT_RADIUS = 6
HUNT_MIN_MEN = 40
HUNT_WEEKS = (2.0, 5.0)
# L'envie de l'IA, chaque mois ou elle le peut (dans la soudure).
HUNT_AI = 0.8
ROUTE_AI = 0.25
# Les autres.
COUNCIL_FOOD_WEEKS = 2.0
COUNCIL_LOYALTY = 10.0
SCOUTS_POP = 60
SCOUTS_FOOD = 80.0
SCOUTS_RADIUS = 22
SCOUTS_CONTACT = 34
DEAD_FEAST_FOOD_WEEKS = 1.0
MARRIAGE_FOOD_WEEKS = 2.0
MARRIAGE_RELATION = 20.0
# L'IA y pense un mois sur MARRIAGE_EVERY (decale d'un peuple a l'autre :
# chercher un peuple ami coute), avec cette envie.
MARRIAGE_EVERY = 6
MARRIAGE_AI = 0.9
FRIEND = 20.0
HIGH_CHIEF_VASSALS = 3
HIGH_CHIEF_PRESTIGE = 80
HIGH_CHIEF_COST = 20
TALES_WINTERS = 10
FOREVER = 10 ** 9

FAMILIES = ("Les vivres", "Le peuple et ses chefs", "Le sacré", "Les voisins", "Les grands desseins")

# Les effets "comme des savoirs" que laissent les decisions (EFFECT_SPECS).
EFFECTS = {
    "ration": ("Rationnement jusqu'à la récolte", {"stability": RATION_STABILITY, "growth": RATION_GROWTH}),
    "fete_morts": ("La fête des morts", {"stability": 4}),
    "recits": ("Les récits des anciens", {"learn": 1.1}),
    "chef_des_chefs": ("Chef des chefs", {"vassal_cap": 1, "loyalty": 5}),
}


@dataclass(frozen=True)
class Decision:
    id: str
    family: str
    icon: str
    name: str
    text: str
    # (state, tid, cible) -> [(condition, remplie)]
    needs: Callable
    # (state, tid, cible) -> texte
    cost: Callable
    # (state, tid, cible) -> [lignes]
    effects: Callable
    # (state, tid, cible) -> message (la decision est prise)
    take: Callable
    repose_years: int = 0
    # (state, tid) -> [cibles] ; None : sans cible.
    targets: Callable | None = None
    # (state, tid, cible) -> son nom
    target_name: Callable | None = None
    # (state, tid) -> envie de l'IA (0 : jamais) ; la meme cible que le joueur.
    ai: Callable | None = None
    # L'evenement qu'elle remplace (il ne tombe plus au hasard).
    replaces: str = ""
    extra: dict = field(default_factory=dict)


# --- les briques ------------------------------------------------------------------
# Les recherches lourdes (le village, les cibles) se gardent le temps d'une
# semaine : l'IA et l'ecran les demandent plusieurs fois. Une decision prise
# ou un ordre du joueur les oublie (forget).
_MEMO: dict = {}


def forget() -> None:
    _MEMO.clear()


def _memo(state, key, fn):
    stamp = (id(state), state.tick_count)
    if _MEMO.get("stamp") != stamp:
        _MEMO.clear()
        _MEMO["stamp"] = stamp
    if key not in _MEMO:
        _MEMO[key] = fn()
    return _MEMO[key]


def _village(state, tid: int):
    """(lieu, bande) du village du peuple, ou (None, None)."""
    return _memo(state, ("village", tid), lambda: _find_village(state, tid))


def _find_village(state, tid: int):
    for site in sites.of_tribe(state, tid, "village"):
        band = places.band_of(state, site)
        if band is not None and band.population > 0:
            return site, band
    return None, None


def _weeks(band) -> float:
    return band.stock / max(1, band.population)


def _to_harvest(state, site, band) -> int:
    return villages.food_outlook(state, site, band)[0]


def _margin(state, site, band) -> float:
    """Les semaines de vivres qui resteront a la recolte (negatif : il en
    manquera)."""
    return villages.food_outlook(state, site, band)[1]


def _lean(state, site, band) -> bool:
    """La soudure : le grenier ne tiendra pas (ou tout juste) jusqu'a la
    recolte."""
    return _margin(state, site, band) < LEAN_MARGIN


def _margin_text(state, site, band) -> str:
    m = _margin(state, site, band)
    if m < 0:
        return f"il manquera {-m:.0f} sem. de vivres à la récolte"
    return f"il restera {m:.1f} sem. de vivres à la récolte"


def _now(state) -> int:
    return state.tick_count


def resting(state, tid: int, did: str) -> int:
    """Les semaines de repos qui restent (0 : on peut la reprendre)."""
    d = DECISIONS[did]
    if not d.repose_years:
        return 0
    taken = state.tribes[tid].decided.get(did)
    if taken is None:
        return 0
    return max(0, taken + d.repose_years * WEEKS_PER_YEAR - _now(state))


def rationing(state, tid: int) -> bool:
    tribe = state.tribes.get(tid)
    return tribe is not None and _now(state) < tribe.ration_until


def _set_effect(state, tid: int, key: str, weeks: int) -> None:
    tribe = state.tribes[tid]
    tribe.decision_effects[key] = FOREVER if weeks >= FOREVER else _now(state) + weeks
    tech.invalidate()


def _men(band) -> int:
    return int(population.men_force(band))


def _feed(band, weeks: float) -> None:
    band.stock = max(0.0, band.stock - weeks * band.population)


def _log(state, tid: int, text: str, where=None, kind=LogKind.POLITIQUE) -> None:
    if is_human(state, tid):
        note(state, kind, text, where=where, to=tid)


# --- la soudure -------------------------------------------------------------------


def _ration_needs(state, tid, _t):
    site, band = _village(state, tid)
    if band is None:
        return [("Un village", False)]
    left = _to_harvest(state, site, band)
    return [
        (f"Avant la récolte (dans {left} sem.)", 0 < left < 40),
        (f"Un grenier trop juste pour la récolte, moins de {LEAN_MARGIN:.0f} sem. de marge ({_margin_text(state, site, band)})", _lean(state, site, band)),
        ("Pas déjà en rationnement", not rationing(state, tid)),
    ]


def _ration_take(state, tid, _t):
    site, band = _village(state, tid)
    weeks = max(1, _to_harvest(state, site, band))
    tribe = state.tribes[tid]
    tribe.ration_until = _now(state) + weeks
    tribe.decision_effects["ration"] = tribe.ration_until
    tech.invalidate()
    _log(state, tid, f"Rationnement : chacun mange les trois quarts de sa part jusqu'à la récolte ({weeks} semaines).", site.hex, LogKind.SURVIE)
    return "Le rationnement commence."


def _ration_ai(state, tid):
    site, band = _village(state, tid)
    return 1.0 if band is not None and _margin(state, site, band) < 0 else 0.0


def _grain_needs(state, tid, _t):
    site, band = _village(state, tid)
    if band is None:
        return [("Un village", False)]
    q = grain.quote(state, tid, site.id)
    out = [(f"La disette, ou la soudure en vue ({_margin_text(state, site, band)})", grain.in_dearth(state, band) or _lean(state, site, band))]
    sell = "Un peuple qui vend (accord de commerce, allié, votre pays), à portée"
    out.append((sell + (f" : {q['why']}" if q["why"] else ""), not q["why"]))
    return out


def _grain_cost(state, tid, _t):
    site, _band = _village(state, tid)
    if site is None:
        return "—"
    q = grain.quote(state, tid, site.id)
    if q["why"]:
        return q["why"]
    seller = state.tribes.get(q["seller"])
    return f"{q['sicles']:.0f} sicles aux {seller.name if seller else '?'}, pour {q['vivres']:.0f} vivres"


def _grain_take(state, tid, _t):
    site, _band = _village(state, tid)
    why = grain.buy(state, tid, site.id)
    return why or "Le grain est acheté."


def _seed_needs(state, tid, _t):
    site, band = _village(state, tid)
    if band is None:
        return [("Un village", False)]
    return [
        (f"Des semences au grenier ({site.data.seed:.0f})", site.data.seed > 0),
        (f"La faim, ou la soudure en vue ({_margin_text(state, site, band)})", grain.in_dearth(state, band) or _lean(state, site, band)),
    ]


def _seed_take(state, tid, _t):
    _site, band = _village(state, tid)
    got = villages.eat_seed(state, band)
    _log(state, tid, f"On mange les semences ({got:.0f} vivres) : il faudra en trouver d'autres pour semer.", band.position, LogKind.SURVIE)
    return "Les semences sont mangées."


def _raid_targets(state, tid):
    """Les villages d'autres peuples a portee, qu'on peut attaquer."""
    return _memo(state, ("razzia", tid), lambda: _find_raid_targets(state, tid))


def _find_raid_targets(state, tid):
    site, band = _village(state, tid)
    if band is None:
        return []
    out = []
    for other in sorted(state.sites.values(), key=lambda s: s.id):
        if other.kind != "village" or other.tribe_id == tid or other.tribe_id not in state.tribes:
            continue
        if state.world.distance(site.hex, other.hex) > RAID_RANGE:
            continue
        if places.band_of(state, other) is None:
            continue
        if guerre.may_start(state, tid, other.tribe_id) and not guerre.at_war(state, tid, other.tribe_id):
            continue
        out.append(other.id)
    out.sort(key=lambda sid: (state.world.distance(site.hex, state.sites[sid].hex), sid))
    return out


def _raid_name(state, tid, sid):
    other = state.sites.get(sid)
    if other is None:
        return "?"
    people = state.tribes[other.tribe_id].name
    site, _b = _village(state, tid)
    d = state.world.distance(site.hex, other.hex) if site is not None else 0
    return f"{other.name or 'un village'} (les {people}, à {d} cases)"


def _raid_needs(state, tid, sid):
    site, band = _village(state, tid)
    if band is None:
        return [("Un village", False)]
    why = troupes.army_block(state, band.id)
    return [
        ("Une troupe à lever au village" + (f" ({why})" if why else ""), not why),
        (f"Un village à prendre à moins de {RAID_RANGE} cases", sid is not None and sid in _raid_targets(state, tid)),
    ]


def _raid_cost(state, tid, sid):
    other = state.sites.get(sid) if sid is not None else None
    text = "Une troupe part (le quart des hommes du village), avec des vivres"
    if other is not None and guerre.needs_declaration(state, tid, other.tribe_id) and not guerre.at_war(state, tid, other.tribe_id):
        text += f" ; la guerre est déclarée aux {state.tribes[other.tribe_id].name} et à leur pays"
    return text


def _raid_take(state, tid, sid):
    site, band = _village(state, tid)
    other = state.sites[sid]
    them = other.tribe_id
    if guerre.needs_declaration(state, tid, them) and not guerre.at_war(state, tid, them):
        why = guerre.declare_war(state, tid, them)
        if why and not guerre.at_war(state, tid, them):
            return why
    army = troupes.raise_army(state, band.id)
    if army is None:
        return "Personne ne part"
    target = places.band_of(state, other)
    set_march_to_band(state, army.id, target.id)
    _log(state, tid, f"Une razzia part sur {other.name or 'leur village'} : vaincu, le village sera pillé ou soumis.", other.hex, LogKind.COMBAT)
    return "La troupe part."


def _route_key(route) -> str:
    return f"{route.exporter}:{route.importer}:{route.good}"


def _route_line(state, route) -> list:
    """Les cases d'une route (la ligne entre ses deux villages)."""
    ends = goods.trade_ends(state, route.exporter, route.importer)
    if ends is None:
        return []
    world = state.world
    (ca, ra), (cb, rb) = axial_to_offset(ends[0]), axial_to_offset(ends[1])
    dc = cb - ca
    if world.wrap_x and abs(dc) > world.width / 2:
        dc -= world.width if dc > 0 else -world.width
    steps = max(1, world.distance(ends[0], ends[1]))
    out = []
    for i in range(steps + 1):
        t = i / steps
        h = world.canonicalize(offset_to_axial(int(round(ca + dc * t)) % world.width, int(round(ra + (rb - ra) * t))))
        if h is not None and (not out or out[-1] != h):
            out.append(h)
    return out


def _route_post(state, tid, route):
    """La case de la route la plus proche du village (ou None si trop loin)."""
    site, _band = _village(state, tid)
    if site is None:
        return None
    line = _route_line(state, route)
    if not line:
        return None
    best = min(line, key=lambda h: (state.world.distance(site.hex, h), h.q, h.r))
    return best if state.world.distance(site.hex, best) <= ROUTE_REACH else None


def _route_targets(state, tid):
    return _memo(state, ("routes", tid), lambda: _find_route_targets(state, tid))


def _find_route_targets(state, tid):
    site, _band = _village(state, tid)
    if site is None:
        return []
    world = state.world
    out = []
    for r in sorted(goods.all_routes(state), key=lambda r: (r.exporter, r.importer, r.good)):
        if tid in (r.exporter, r.importer):
            continue
        ends = _memo(state, ("bouts", r.exporter, r.importer), lambda r=r: goods.trade_ends(state, r.exporter, r.importer))
        if ends is None:
            continue
        # Trop loin de toute la route (le point le plus proche est a moins
        # d'une demi-route d'un des bouts) : pas besoin de la tracer.
        near = min(world.distance(site.hex, ends[0]), world.distance(site.hex, ends[1]))
        if near - world.distance(ends[0], ends[1]) / 2 > ROUTE_REACH:
            continue
        if any(diplo.allied(state, tid, x) or diplo.has_pact(state, tid, x, "vassal") for x in (r.exporter, r.importer)):
            continue
        if _route_post(state, tid, r) is not None:
            out.append(_route_key(r))
    return out


def _route_of(state, key):
    for r in goods.all_routes(state):
        if _route_key(r) == key:
            return r
    return None


def _route_name(state, tid, key):
    r = _route_of(state, key)
    if r is None:
        return "?"
    a, b = state.tribes.get(r.exporter), state.tribes.get(r.importer)
    good = goods.GOOD_NAMES.get(r.good, r.good).lower()
    post = _route_post(state, tid, r)
    site, _b = _village(state, tid)
    d = state.world.distance(site.hex, post) if post is not None and site is not None else 0
    return f"{good}, des {a.name if a else '?'} aux {b.name if b else '?'} (à {d} cases)"


def _route_needs(state, tid, key):
    _site, band = _village(state, tid)
    if band is None:
        return [("Un village", False)]
    why = troupes.army_block(state, band.id)
    return [
        ("Une troupe à lever au village" + (f" ({why})" if why else ""), not why),
        (f"Une route d'autres peuples à moins de {ROUTE_REACH} cases (ni alliés ni tributaires)", key is not None and key in _route_targets(state, tid)),
    ]


def _route_take(state, tid, key):
    _site, band = _village(state, tid)
    r = _route_of(state, key)
    post = _route_post(state, tid, r)
    army = troupes.raise_army(state, band.id)
    if army is None:
        return "Personne ne part"
    army.raid_route = key
    set_goto(state, army.id, post, max_nodes=6000)
    _log(state, tid, f"Une troupe part se poster sur la route ({_route_name(state, tid, key)}) : elle prendra une part de ce qui passe.", post, LogKind.COMBAT)
    return "La troupe part."


def seize(state, route) -> float:
    """Le pillage d'une route (goods.monthly, apres le passage des convois) :
    une troupe postee pres de la route prend ROUTE_SEIZE de ce qui est passe
    ce mois ; les deux peuples s'en souviennent (et ont un motif de guerre)."""
    if route.units <= 0:
        return 0.0
    key = _route_key(route)
    raiders = [
        b for b in sorted(state.bands.values(), key=lambda b: b.id)
        if b.raid_route == key and b.population > 0 and not b.path
    ]
    if not raiders:
        return 0.0
    line = _route_line(state, route)
    raiders = [b for b in raiders if any(state.world.distance(b.position, h) <= ROUTE_POST for h in line)]
    if not raiders:
        return 0.0
    thief = raiders[0].tribe_id
    importer = state.tribes.get(route.importer)
    taken = route.units * ROUTE_SEIZE
    if importer is not None:
        have = importer.goods.get(route.good, 0.0)
        taken = min(taken, have)
        importer.goods[route.good] = have - taken
    if taken <= 0:
        return 0.0
    tribe = state.tribes[thief]
    tribe.goods[route.good] = min(goods.CAP, tribe.goods.get(route.good, 0.0) + taken)
    route.status = "pillée"
    for victim in (route.exporter, route.importer):
        diplo.add_mod(state, victim, thief, "routes_pillees", ROUTE_RELATION, actor=thief)
        guerre.set_casus(state, victim, thief, ROUTE_CASUS_WEEKS, "pillage")
        if is_human(state, victim):
            note(state, LogKind.COMBAT, f"Les {tribe.name} pillent la route : {taken:.0f} charges de {goods.GOOD_NAMES.get(route.good, route.good).lower()} perdues.", where=raiders[0].position, to=victim)
    _log(state, thief, f"La troupe a pillé la route : {taken:.0f} charges de {goods.GOOD_NAMES.get(route.good, route.good).lower()}.", raiders[0].position, LogKind.COMBAT)
    return taken


def _lean_ai(state, tid) -> bool:
    site, band = _village(state, tid)
    return band is not None and _lean(state, site, band)


def _hunt_ai(state, tid):
    return HUNT_AI if _lean_ai(state, tid) else 0.0


def _route_ai(state, tid):
    """Piller une route : seulement affame, et sans grain a acheter."""
    site, band = _village(state, tid)
    if band is None or _margin(state, site, band) >= 0:
        return 0.0
    return ROUTE_AI if grain.quote(state, tid, site.id)["why"] else 0.0


def _hunt_game(state, site) -> int:
    world = state.world
    return sum(1 for h in world.hexes_in_radius(site.hex, HUNT_RADIUS) if any(world.resource(h, g) >= PRESENT for g in GAME))


def _hunt_needs(state, tid, _t):
    site, band = _village(state, tid)
    if band is None:
        return [("Un village", False)]
    game = _hunt_game(state, site)
    return [
        (f"Du gibier à moins de {HUNT_RADIUS} cases ({game} lieux)", game >= 3),
        (f"{HUNT_MIN_MEN} chasseurs ({_men(band)} hommes valides)", _men(band) >= HUNT_MIN_MEN),
    ]


def _hunt_take(state, tid, _t):
    site, band = _village(state, tid)
    lo, hi = HUNT_WEEKS
    rich = min(1.0, _hunt_game(state, site) / 20.0)
    weeks = lo + (hi - lo) * (0.5 * rich + 0.5 * state.rng.random())
    got = weeks * band.population
    band.stock = min(stock_max(band, state), band.stock + got)
    hurt = population.kill(band, max(0, int(state.rng.random() * 3)))
    _log(state, tid, f"La grande chasse rapporte {got:.0f} vivres" + (f" ; {hurt} chasseurs ne reviennent pas." if hurt else "."), site.hex, LogKind.SURVIE)
    return "Les chasseurs reviennent."


# --- le peuple et ses chefs ---------------------------------------------------------


def _feast_needs(state, tid, _t):
    why = chiefdom.feast_block(state, tid)
    return [(why or "Le grenier du chef peut la payer", not why)]


def _feast_cost(state, tid, _t):
    return f"{chiefdom.feast_cost(state, tid):.0f} vivres du grenier du chef"


def _feast_ai(state, tid):
    return 0.0  # l'IA donne ses fetes elle-meme (chiefdom)


def _clans(state, tid) -> list:
    return [b for b in state.bands.values() if b.tribe_id == tid and b.population > 0 and b.kind != "armee"]


def _council_needs(state, tid, _t):
    n = len(_clans(state, tid))
    return [(f"Au moins 2 clans ({n})", n >= 2)]


def _council_take(state, tid, _t):
    for b in _clans(state, tid):
        _feed(b, COUNCIL_FOOD_WEEKS)
        if not chiefs.is_chief_band(state, b):
            b.loyalty = min(100.0, b.loyalty + COUNCIL_LOYALTY)
    _log(state, tid, "Le conseil des clans s'est tenu : les chefs de clan repartent avec des présents et des promesses.")
    return "Le conseil s'est tenu."


def _council_ai(state, tid):
    clans = [b for b in _clans(state, tid) if not chiefs.is_chief_band(state, b)]
    return 1.0 if clans and min(b.loyalty for b in clans) < 50 else 0.0


def _scouts_needs(state, tid, _t):
    site, band = _village(state, tid)
    pop = band.population if band is not None else max((b.population for b in _clans(state, tid)), default=0)
    return [(f"{SCOUTS_POP} personnes au moins ({pop})", pop >= SCOUTS_POP), (f"{SCOUTS_FOOD:.0f} vivres", (band.stock if band else 0) >= SCOUTS_FOOD)]


def _scouts_take(state, tid, _t):
    site, band = _village(state, tid)
    band.stock -= SCOUTS_FOOD
    world = state.world
    vis = vision_of(state, tid)
    if vis is not None:
        vis.explored.update(world.hexes_in_radius(site.hex, SCOUTS_RADIUS))
    met = []
    for other in sorted({b.tribe_id for b in state.bands.values() if b.population > 0}):
        if other == tid or other in diplo.contacts_of(state, tid):
            continue
        near = min((world.distance(site.hex, b.position) for b in state.bands.values() if b.tribe_id == other and b.population > 0), default=999)
        if near <= SCOUTS_CONTACT:
            diplo.make_contact(state, tid, other)
            met.append(state.tribes[other].name)
    lost = population.kill(band, int(state.rng.random() * 3))
    text = "Les éclaireurs sont revenus : la carte se découvre loin."
    if met:
        text += " Ils ont rencontré les " + ", ".join(met) + "."
    if lost:
        text += f" {lost} ne sont pas revenus."
    _log(state, tid, text, site.hex, LogKind.DECOUVERTE)
    return "Les éclaireurs sont revenus."


# --- le sacre -----------------------------------------------------------------------


def _dead_needs(state, tid, _t):
    known = state.tribes[tid].knowledge
    _site, band = _village(state, tid)
    return [
        ("Culte des ancêtres", "ancetres" in known),
        ("Un village", band is not None),
    ]


def _dead_take(state, tid, _t):
    _site, band = _village(state, tid)
    _feed(band, DEAD_FEAST_FOOD_WEEKS)
    _set_effect(state, tid, "fete_morts", 2 * WEEKS_PER_YEAR)
    gain_prestige(state, state.tribes[tid], 3)
    _log(state, tid, "La fête des morts : on a ouvert la tombe des ancêtres, on leur a parlé. Ils veillent sur le village.")
    return "La fête des morts est faite."


def _dead_ai(state, tid):
    site, band = _village(state, tid)
    if band is None:
        return 0.0
    return 1.0 if villages.stability(state, site) < 50 else 0.0


def _tales_needs(state, tid, _t):
    tribe = state.tribes[tid]
    winters = tribe.practice.get("hivers", 0)
    return [
        ("Récits autour du feu", "conte" in tribe.knowledge),
        (f"Un peuple qui a traversé {TALES_WINTERS} hivers ({winters})", winters >= TALES_WINTERS),
    ]


def _tales_take(state, tid, _t):
    _set_effect(state, tid, "recits", WEEKS_PER_YEAR)
    _log(state, tid, "Les plus vieux racontent, les enfants retiennent : le peuple apprend plus vite cette année.", kind=LogKind.DECOUVERTE)
    return "Les récits sont recueillis."


# --- les voisins --------------------------------------------------------------------


def _marriage_targets(state, tid):
    return _memo(state, ("mariage", tid), lambda: _find_marriage_targets(state, tid))


def _find_marriage_targets(state, tid):
    out = [o for o in sorted(diplo.contacts_of(state, tid)) if o in state.tribes and diplo.relation(state, tid, o) >= FRIEND and not guerre.at_war(state, tid, o)]
    out.sort(key=lambda o: (-diplo.relation(state, tid, o), o))
    return out


def _marriage_name(state, tid, o):
    t = state.tribes.get(o)
    return f"les {t.name} (relation {diplo.relation(state, tid, o):.0f})" if t else "?"


def _marriage_needs(state, tid, o):
    _site, band = _village(state, tid)
    return [
        ("Mariages entre clans", "mariages" in state.tribes[tid].knowledge),
        ("Un peuple cordial (relation 20)", o is not None and o in _marriage_targets(state, tid)),
        ("Un village (la dot)", band is not None),
    ]


def _marriage_take(state, tid, o):
    _site, band = _village(state, tid)
    _feed(band, MARRIAGE_FOOD_WEEKS)
    diplo.add_mod(state, tid, o, "mariage", MARRIAGE_RELATION, actor=tid)
    diplo.add_mod(state, o, tid, "mariage", MARRIAGE_RELATION, actor=tid)
    them = state.tribes[o]
    _log(state, tid, f"Un mariage lie votre chef aux {them.name} : deux familles, puis deux peuples.")
    if is_human(state, o):
        note(state, LogKind.POLITIQUE, f"Un mariage lie votre chef aux {state.tribes[tid].name}.", to=o)
    return "Le mariage est fait."


def _marriage_ai(state, tid):
    if "mariages" not in state.tribes[tid].knowledge or (state.tick_count // 4 + tid) % MARRIAGE_EVERY:
        return 0.0
    return MARRIAGE_AI if _marriage_targets(state, tid) else 0.0


# --- les grands desseins ------------------------------------------------------------


def _chief_needs(state, tid, _t):
    tribe = state.tribes[tid]
    n = len(chiefdom.vassals_of(state, tid))
    return [
        ("Chef des chefs (savoir)", "grand_chef" in tribe.knowledge),
        (f"{HIGH_CHIEF_VASSALS} tributaires ({n})", n >= HIGH_CHIEF_VASSALS),
        (f"Prestige {HIGH_CHIEF_PRESTIGE} ({tribe.prestige})", tribe.prestige >= HIGH_CHIEF_PRESTIGE),
        ("Pas déjà chef des chefs", "chef_des_chefs" not in tribe.decision_effects),
    ]


def _chief_take(state, tid, _t):
    tribe = state.tribes[tid]
    tribe.prestige = max(0, tribe.prestige - HIGH_CHIEF_COST)
    _set_effect(state, tid, "chef_des_chefs", FOREVER)
    _log(state, tid, "Les chefs des villages tributaires ont ployé le genou : votre chef est le chef des chefs.")
    for h in sorted(state.tribes):
        if h != tid and is_human(state, h) and tid in diplo.contacts_of(state, h):
            note(state, LogKind.POLITIQUE, f"Le chef des {tribe.name} est devenu le chef des chefs.", to=h)
    return "Votre chef est le chef des chefs."


def _always(_state, _tid):
    return 1.0


def _const(text):
    return lambda _s, _t, _x: text


def _lines(*lines):
    return lambda _s, _t, _x: list(lines)


def _build() -> dict:
    out = (
        Decision(
            "rationner", "Les vivres", "grenier", "Rationner jusqu'à la récolte",
            "Le grenier ne tiendra pas jusqu'à la moisson. Chacun mangera moins, mais tout le monde verra l'été.",
            _ration_needs, _const(f"Naissances −{100 - round(100 * RATION_GROWTH)} % et stabilité −{-RATION_STABILITY}, jusqu'à la récolte"),
            _lines("Chacun mange les trois quarts de sa part : le grenier dure un tiers de plus", "Moins de morts de faim avant la récolte"),
            _ration_take, ai=_ration_ai,
        ),
        Decision(
            "acheter_grain", "Les vivres", "pieces", "Acheter du grain",
            "Un voisin a du grain de trop : il le vend, plus cher quand on en manque, moins cher si l'on s'y prend d'avance.",
            _grain_needs, _grain_cost, _lines("Le grain arrive au grenier tout de suite"), _grain_take,
        ),
        Decision(
            "semences", "Les vivres", "ble", "Manger les semences",
            "Il reste les semences de l'an prochain, dans les jarres du fond du grenier.",
            _seed_needs, _const("Moins de champs aux prochaines semailles (sauf à trouver d'autres graines)"),
            _lines("Les semences vont au grenier : pas de faim tout de suite"), _seed_take,
        ),
        Decision(
            "razzia", "Les vivres", "combat", "Une razzia sur un village",
            "Une troupe part prendre ce que le grenier d'un voisin a de trop. Vaincu, son village sera pillé, ou soumis.",
            _raid_needs, _raid_cost,
            _lines("La troupe marche sur le village et l'attaque", "Victoire : le butin de leur grenier, puis piller ou soumettre", "Défaite : la troupe revient diminuée"),
            _raid_take, targets=_raid_targets, target_name=_raid_name,
        ),
        Decision(
            "piller_routes", "Les vivres", "commerce", "Piller les routes de commerce",
            "Les porteurs des autres passent près de chez vous, chargés. Une troupe postée sur leur chemin prend sa part.",
            _route_needs, _const("Une troupe part (le quart des hommes) ; les deux peuples de la route vous en voudront, et auront un motif de guerre"),
            _lines("Chaque mois, la moitié de ce qui passe sur la route", f"Relation {ROUTE_RELATION} avec les deux peuples, à chaque pillage"),
            _route_take, targets=_route_targets, target_name=_route_name, ai=_route_ai,
        ),
        Decision(
            "grande_chasse", "Les vivres", "chasse", "Organiser une grande chasse",
            "Tous les chasseurs ensemble, une semaine durant : la viande de toute une saison, si les bêtes sont là.",
            _hunt_needs, _const("Quelques chasseurs ne reviennent pas"),
            _lines(f"Vivres : {HUNT_WEEKS[0]:.0f} à {HUNT_WEEKS[1]:.0f} semaines (plus il y a de gibier, plus on en rapporte)"),
            _hunt_take, repose_years=1, ai=_hunt_ai,
        ),
        Decision(
            "grande_fete", "Le peuple et ses chefs", "feu", "Donner une grande fête",
            "Le grenier du chef nourrit tout le peuple : les familles s'en souviendront.",
            _feast_needs, _feast_cost,
            _lines(f"Stabilité +{chiefdom.FEAST_STABILITY} pendant un an", f"Prestige +{chiefdom.FEAST_PRESTIGE}, les familles contentes"),
            lambda s, t, _x: chiefdom.feast(s, t), ai=_feast_ai,
        ),
        Decision(
            "conseil_clans", "Le peuple et ses chefs", "reunir", "Réunir le conseil des clans",
            "Les chefs de clan viennent auprès du chef : on parle, on promet, on échange des présents.",
            _council_needs, _const(f"{COUNCIL_FOOD_WEEKS:.0f} semaines de vivres pour chaque clan"),
            _lines(f"Attachement de chaque clan +{COUNCIL_LOYALTY:.0f}"),
            _council_take, repose_years=3, ai=_council_ai, replaces="rassemblement",
        ),
        Decision(
            "eclaireurs", "Le peuple et ses chefs", "boussole", "Envoyer des éclaireurs",
            "Dix jeunes partent vers l'horizon ; ils reviendront avec des nouvelles, ou ne reviendront pas.",
            _scouts_needs, _const(f"{SCOUTS_FOOD:.0f} vivres ; parfois un ou deux ne reviennent pas"),
            _lines(f"La carte se découvre à {SCOUTS_RADIUS} cases", f"Les peuples à {SCOUTS_CONTACT} cases sont rencontrés"),
            _scouts_take, repose_years=2,
        ),
        Decision(
            "fete_morts", "Le sacré", "dolmen", "La fête des morts",
            "On ouvre la tombe des ancêtres, on leur parle, on leur donne à manger : ils veillent sur nous.",
            _dead_needs, _const(f"{DEAD_FEAST_FOOD_WEEKS:.0f} semaine de vivres"),
            _lines("Stabilité des villages +4 pendant deux ans", "Prestige +3"),
            _dead_take, repose_years=5, ai=_dead_ai,
        ),
        Decision(
            "recits", "Le sacré", "honorer", "Recueillir les récits des anciens",
            "Les plus vieux racontent ; les enfants retiennent. Un peuple qui se souvient apprend plus vite.",
            _tales_needs, _const("—"), _lines("Recherche +10 % pendant un an"),
            _tales_take, repose_years=5, ai=_always, replaces="ancien",
        ),
        Decision(
            "mariage", "Les voisins", "gens", "Proposer un mariage",
            "Une fille ou un fils du chef pour un peuple ami : deux familles, puis deux peuples, liés.",
            _marriage_needs, _const(f"Une dot : {MARRIAGE_FOOD_WEEKS:.0f} semaines de vivres"),
            _lines(f"Relation +{MARRIAGE_RELATION:.0f} avec ce peuple, des deux côtés", "Une alliance leur plaira plus"),
            _marriage_take, repose_years=5, targets=_marriage_targets, target_name=_marriage_name, ai=_marriage_ai,
        ),
        Decision(
            "chef_des_chefs", "Les grands desseins", "couronne", "Devenir le chef des chefs",
            "Les chefs de trois villages au moins ploient le genou : le chef devient le premier d'entre eux.",
            _chief_needs, _const(f"Prestige −{HIGH_CHIEF_COST} (une grande fête)"),
            _lines("Un titre pour toujours", "Un tributaire de plus possible", "Attachement des clans +5"),
            _chief_take, ai=_always,
        ),
    )
    return {d.id: d for d in out}


DECISIONS = _build()
REPLACED = {d.replaces for d in DECISIONS.values() if d.replaces}


# --- ce que l'ecran et les ordres demandent -----------------------------------------


def targets_of(state, tid: int, did: str) -> list:
    d = DECISIONS[did]
    return d.targets(state, tid) if d.targets is not None else []


def pick_target(state, tid: int, did: str, want=None):
    """La cible voulue si elle est possible, sinon la premiere (ou None)."""
    options = targets_of(state, tid, did)
    if want is not None and want in options:
        return want
    return options[0] if options else None


def needs(state, tid: int, did: str, target=None) -> list:
    d = DECISIONS[did]
    out = list(d.needs(state, tid, target))
    rest = resting(state, tid, did)
    if rest:
        out.append((f"En repos encore {math.ceil(rest / WEEKS_PER_YEAR)} an{'s' if rest > WEEKS_PER_YEAR else ''}", False))
    return out


def status(state, tid: int, did: str, target=None) -> tuple[str, str]:
    """("possible" | "manque" | "repos", texte)."""
    rest = resting(state, tid, did)
    if rest:
        years = math.ceil(rest / WEEKS_PER_YEAR)
        return "repos", f"En repos : {years} an{'s' if years > 1 else ''}"
    missing = sum(1 for _c, ok in DECISIONS[did].needs(state, tid, target) if not ok)
    if missing == 0:
        return "possible", "Possible"
    return "manque", f"Il manque {missing}"


def block(state, tid: int, did: str, target=None) -> str:
    """"" si la decision peut se prendre, sinon pourquoi."""
    if did not in DECISIONS or tid not in state.tribes:
        return "Décision inconnue"
    d = DECISIONS[did]
    if d.targets is not None and target is None:
        return "Il faut choisir une cible"
    for cond, ok in needs(state, tid, did, target):
        if not ok:
            return cond
    return ""


def take(state, tid: int, did: str, target=None) -> str:
    """Prend la decision (rend le message : ce qui s'est passe, ou pourquoi
    rien)."""
    why = block(state, tid, did, target)
    if why:
        return why
    d = DECISIONS[did]
    msg = d.take(state, tid, target)
    state.tribes[tid].decided[did] = _now(state)
    forget()
    return msg


def possible_count(state, tid: int) -> int:
    """Combien de decisions sont possibles maintenant (l'onglet)."""
    n = 0
    for did in DECISIONS:
        if status(state, tid, did, pick_target(state, tid, did))[0] == "possible":
            n += 1
    return n


def soudure_alert(state, tid: int) -> bool:
    """La soudure est la : rationner est possible et pas encore fait (l'onglet
    s'allume)."""
    return status(state, tid, "rationner")[0] == "possible"


# --- le mois : les effets qui finissent, l'IA ------------------------------------------


def monthly(state) -> None:
    """Les effets finis s'en vont ; l'IA prend ses decisions (systems.MONTHLY)."""
    forget()
    now = _now(state)
    changed = False
    for tribe in state.tribes.values():
        gone = [k for k, until in tribe.decision_effects.items() if until <= now]
        for k in gone:
            del tribe.decision_effects[k]
            changed = True
    if changed:
        tech.invalidate()
    _route_raiders(state)
    ai_monthly(state)


def _route_raiders(state) -> None:
    """Les troupes postees sur une route : la route disparue, elles n'ont
    plus rien a piller ; celles de l'IA rentrent quand la faim est passee."""
    keys = {_route_key(r) for r in goods.all_routes(state)}
    for band in sorted(state.bands.values(), key=lambda b: b.id):
        if not band.raid_route or band.population <= 0:
            continue
        gone = band.raid_route not in keys
        fed = not is_human(state, band.tribe_id) and not _lean_ai(state, band.tribe_id)
        if gone or fed:
            band.raid_route = ""
            if fed:
                troupes.dissolve(state, band.id)


def ai_monthly(state) -> None:
    """Chaque peuple de l'IA prend au plus une decision par mois : celle qui
    lui va le mieux, si elle est possible (les memes regles que le joueur)."""
    alive = sorted({b.tribe_id for b in state.bands.values() if b.population > 0})
    for tid in alive:
        tribe = state.tribes.get(tid)
        if tribe is None or is_human(state, tid):
            continue
        best = None
        for did in sorted(DECISIONS):
            d = DECISIONS[did]
            if d.ai is None or resting(state, tid, did):
                continue
            want = d.ai(state, tid)
            if want <= 0:
                continue
            target = pick_target(state, tid, did)
            if block(state, tid, did, target):
                continue
            if best is None or want > best[0]:
                best = (want, did, target)
        if best is not None and state.rng.random() < best[0]:
            take(state, tid, best[1], best[2])


# --- les effets comme des savoirs (systems.EFFECT_FIELDS, EFFECT_SPECS) ---------------


def effect_ids(tribe) -> list:
    return ["dec:" + k for k in sorted(tribe.decision_effects) if k in EFFECTS]


def effect_specs() -> dict:
    return {"dec:" + k: v for k, v in EFFECTS.items()}
