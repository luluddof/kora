"""Metiers des villages, marche du peuple, routes commerciales.

METIERS. Un village met des EQUIPES de villageois (TEAM gens) a un metier :
exploiter une ressource de ses terres (a villages.FIELD_RADIUS cases ou
moins), avec un savoir.

  Metier       Ressource des terres       Savoir             Produit
  Potiers      argile                     Poterie            poteries
  Sauniers     sel                        Salaison           sel
  Tisserands   chevres sauvages, ou vos   Tissage            etoffes
               troupeaux (Chevres)
  Pelletiers   gibier (aurochs, chevaux,  Vetements de peau  cuirs et fourrures
               chevres, rennes)
  Tailleurs    silex                      Haches polies      haches polies
  Pecheurs     poisson                    Peche au harpon    vivres, au grenier

Une equipe par gisement (case ou la ressource est la), MAX_TEAMS au plus par
metier, une equipe par TEAM_POP habitants en tout. Plus la ressource est
riche, plus l'equipe produit ; l'Atelier du village : x1,25. Les gens de
metier ne sont pas aux champs (bras de la recolte) et chassent moins.

MARCHE DU PEUPLE. Les biens vont a la reserve du PEUPLE (Tribe.goods) : tous
ses villages en consomment (NEED par 100 habitants et par semaine). Tant que
la reserve en a, le peuple est POURVU et l'effet joue (supplied). Chaque bien
a un PRIX chez chaque peuple : sa valeur, plus chere quand on en manque, bon
marche quand on en a trop (price).

ROUTES COMMERCIALES (diplo.TradeRoute). Entre deux peuples lies par un
accord commercial (pacte "commerce" ; il faut Echanges lointains), un peuple
ouvre une route : vendre ou acheter un bien, avec 1 a 3 convois de porteurs
(LOAD charges par convoi et par mois). Chaque mois, la route porte ce que le
vendeur a de trop vers l'acheteur, qui le paie en vivres, au prix moyen des
deux marches (la Place d'echange du vendeur : +10 %). Un peuple a des
CONVOIS en nombre limite : 1, plus 1 par village, 2 par Place d'echange, 2
avec les Routes du sel et du silex (qui doublent aussi les charges et la
portee). Il faut un village de chaque cote, a TRADE_RANGE cases au plus.
Les porteurs apportent aussi les savoirs (diplo : voisins qui enseignent) et
la carte du chemin (le joueur voit le pays entre les deux villages). L'IA
ouvre ses routes, y compris avec le joueur, qui peut les fermer.
N'importe ni pygame ni render.
"""

from __future__ import annotations

from dataclasses import dataclass

from src.kora import tech
from src.kora.log import LogKind

TEAM = 10
TEAM_POP = 30
MAX_TEAMS = 3
# Charges par equipe et par semaine : x (0,5 + richesse), 0,9 a 1,5.
OUTPUT = 1.0
WORKSHOP = 1.25
# Consommation : charges par 100 villageois et par semaine.
NEED = 0.5
CAP = 80.0
# Ce qu'un peuple garde pour lui avant de vendre (semaines de besoin) ;
# celui qui a choisi de vendre ne garde que SELL_KEEP_WEEKS.
RESERVE_WEEKS = 12
SELL_KEEP_WEEKS = 4
# Un acheteur qui n'a rien demande n'achete pas au-dela de BUY_UP_TO fois
# sa reserve ; celui qui a ouvert la route achete jusqu'au plein (CAP).
BUY_UP_TO = 1.5
TRADE_RANGE = 40
# Routes : charges par convoi et par mois, convois par route.
LOAD = 2.0
MAX_LEVEL = 3
CONVOYS_BASE = 1
CONVOYS_PLACE = 2
CONVOYS_ROUTES = 2
PLACE_PRICE = 1.1
# Prix : x1,6 quand on n'en a pas, x0,5 quand on en a trop.
PRICE_HIGH = 1.6
PRICE_LOW = 0.5
PRICE_NONE = 0.6
# Une route que son ouvreur IA laisse vide IDLE_CLOSE mois : fermee.
IDLE_CLOSE = 4
HISTORY = 24
# Les gens de metier chassent et cueillent moins (part de leur collecte).
FORAGE_LOSS = 0.4
FISH_NETS = 1.5
# Vivres gardes au grenier quand on paie (semaines).
PAY_KEEP_WEEKS = 6
REVEAL_WIDTH = 1


@dataclass(frozen=True)
class Craft:
    id: str
    name: str
    good: str  # "" : le metier donne des vivres (pecheurs)
    good_name: str
    res: tuple  # ressources des terres (une seule suffit)
    needs: str
    text: str
    lines: tuple
    herd: str = ""  # savoir qui tient lieu de ressource (laine des troupeaux)
    value: float = 0.0  # vivres par charge, prix de base aux echanges
    food: float = 0.0  # vivres par equipe et par semaine


CRAFTS = {
    c.id: c
    for c in (
        Craft(
            "potiers", "Potiers", "poteries", "Poteries", ("argile",), "poterie",
            "On cuit l'argile des berges : jarres, pots, lampes.",
            ("Grain gate x0,6", "+4 semaines de grenier"),
            value=6.0,
        ),
        Craft(
            "sauniers", "Sauniers", "sel", "Sel", ("sel",), "salaison",
            "On fait bouillir l'eau salee, on gratte les croutes : le sel garde tout.",
            ("Famines d'hiver x0,8", "+3 semaines de grenier", "Stabilite +3"),
            value=12.0,
        ),
        Craft(
            "tisserands", "Tisserands", "etoffes", "Etoffes", ("chevres",), "tissage",
            "La laine filee, tissee, teinte : des habits chauds et des parures.",
            ("Stabilite +6", "Famines d'hiver x0,85", "+1 prestige a chaque fin d'hiver"),
            herd="chevres",
            value=12.0,
        ),
        Craft(
            "pelletiers", "Pelletiers", "cuirs", "Cuirs et fourrures", ("aurochs", "chevaux", "chevres", "rennes"), "peaux",
            "Peaux tannees, fourrures cousues : on les porte, on les troque.",
            ("Famines d'hiver x0,9", "Stabilite +2"),
            value=8.0,
        ),
        Craft(
            "tailleurs", "Tailleurs de haches", "haches", "Haches polies", ("silex",), "haches",
            "Le silex des minieres, taille puis poli des jours durant.",
            ("Recolte +10 %", "Troupes : force x1,1", "Chantiers 25 % moins chers"),
            value=12.0,
        ),
        Craft(
            "pecheurs", "Pecheurs", "", "Poisson seche", ("poisson",), "peche",
            "Nasses, harpons, claies de sechage : le poisson nourrit le village.",
            ("12 vivres par equipe et par semaine", "Filets et nasses : x1,5"),
            food=12.0,
        ),
    )
}
CRAFT_ORDER = ("potiers", "sauniers", "tisserands", "pelletiers", "tailleurs", "pecheurs")
GOODS = tuple(CRAFTS[c].good for c in CRAFT_ORDER if CRAFTS[c].good)
GOOD_NAMES = {c.good: c.good_name for c in CRAFTS.values() if c.good}
GOOD_CRAFT = {c.good: c.id for c in CRAFTS.values() if c.good}
# Couleur de chaque bien (routes sur la carte, graphes).
GOOD_COLORS = {
    "poteries": (206, 120, 80),
    "sel": (238, 238, 232),
    "etoffes": (190, 140, 210),
    "cuirs": (170, 120, 70),
    "haches": (140, 170, 190),
}


# "du sel", "des poteries" : pour les phrases du journal.
GOOD_SOME = {"poteries": "des poteries", "sel": "du sel", "etoffes": "des etoffes", "cuirs": "des cuirs et fourrures", "haches": "des haches polies"}


def value(good: str) -> float:
    return CRAFTS[GOOD_CRAFT[good]].value


# --- terres ------------------------------------------------------------------------


def riches(world, h) -> dict:
    """Ressources des terres d'un village : nom -> (gisements, meilleure
    valeur). La carte ne change pas : memorise."""
    from src.kora.resources import NAMES, PRESENT
    from src.kora.villages import FIELD_RADIUS

    memo = getattr(world, "_lands", None)
    if memo is None:
        memo = world._lands = {}
    key = ("riches", world._index(h))
    hit = memo.get(key)
    if hit is not None:
        return hit
    out: dict = {}
    if world.resources:
        for x in world.hexes_in_radius(h, FIELD_RADIUS):
            for n in NAMES:
                v = world.resource(x, n)
                if v >= PRESENT:
                    count, best = out.get(n, (0, 0.0))
                    out[n] = (count + 1, max(best, v))
    memo[key] = out
    return out


def deposits(state, site, cid: str) -> tuple[int, float]:
    """(gisements, richesse) d'un metier pour ce village : la mieux fournie
    de ses ressources."""
    craft = CRAFTS[cid]
    found = riches(state.world, site.hex)
    count, best = 0, 0.0
    for res in craft.res:
        c, b = found.get(res, (0, 0.0))
        if c > count or (c == count and b > best):
            count, best = c, b
    if count == 0 and craft.herd and craft.herd in state.tribes[site.tribe_id].knowledge:
        # La laine de vos troupeaux : deux equipes, richesse moyenne.
        return 2, 0.5
    return count, best


def wild_source(state, site, cid: str) -> str:
    """La ressource des terres qui fait vivre le metier ("" : troupeaux)."""
    from src.kora.resources import LABELS

    found = riches(state.world, site.hex)
    best = max(CRAFTS[cid].res, key=lambda r: found.get(r, (0, 0.0)))
    return LABELS.get(best, best) if found.get(best) else ""


def res_label(cid: str) -> str:
    from src.kora.resources import LABELS

    labels = [LABELS.get(r, r) for r in CRAFTS[cid].res]
    return labels[0] if len(labels) == 1 else "gibier (" + ", ".join(labels) + ")"


# --- equipes -----------------------------------------------------------------------


def teams(site) -> dict:
    if site is None:
        return {}
    return site.data.get("teams") or {}


def teams_of(site, cid: str) -> int:
    return int(teams(site).get(cid, 0))


def total_teams(site) -> int:
    return sum(int(n) for n in teams(site).values())


def team_cap(band) -> int:
    """Equipes qu'un village peut nourrir de ses bras."""
    return max(0, band.population // TEAM_POP) if band is not None else 0


def max_teams(state, site, cid: str) -> int:
    count, _best = deposits(state, site, cid)
    return min(MAX_TEAMS, count)


def workers(site, band) -> int:
    """Villageois aux metiers (pas aux champs)."""
    if band is None:
        return 0
    return min(band.population, TEAM * total_teams(site))


def craft_status(state, site, cid: str) -> str:
    """"verrouille" (savoir), "absent" (pas de gisement), "actif" (au moins
    une equipe) ou "possible"."""
    craft = CRAFTS[cid]
    if craft.needs not in state.tribes[site.tribe_id].knowledge:
        return "verrouille"
    if max_teams(state, site, cid) <= 0:
        return "absent"
    return "actif" if teams_of(site, cid) > 0 else "possible"


def add_block(state, site, cid: str) -> str:
    from src.kora import villages

    if cid not in CRAFTS:
        return "?"
    craft = CRAFTS[cid]
    band = villages.band_of(state, site)
    if band is None:
        return "Le village est vide"
    if craft.needs not in state.tribes[site.tribe_id].knowledge:
        return f"Il faut connaitre {tech.TECHS[craft.needs].name}"
    top = max_teams(state, site, cid)
    if top <= 0:
        return f"Pas de {res_label(cid)} dans les terres du village"
    if teams_of(site, cid) >= top:
        return f"Tous les gisements sont pris ({top})"
    if total_teams(site) >= team_cap(band):
        return f"Plus de bras (une equipe par {TEAM_POP} habitants)"
    return ""


def set_teams(state, site, cid: str, n: int) -> bool:
    """Mettre n equipes a un metier (0 : on arrete)."""
    if cid not in CRAFTS or n < 0:
        return False
    now = teams_of(site, cid)
    while now < n:
        if add_block(state, site, cid):
            break
        now += 1
        site.data.setdefault("teams", {})[cid] = now
    if n < now:
        now = n
        t = site.data.setdefault("teams", {})
        if now:
            t[cid] = now
        else:
            t.pop(cid, None)
    return teams_of(site, cid) == n


def _fit_teams(state, site, band) -> None:
    """Un village qui a perdu du monde (ou un savoir) garde ce qu'il peut."""
    t = teams(site)
    if not t:
        return
    cap = team_cap(band)
    for cid in list(t):
        top = max_teams(state, site, cid) if cid in CRAFTS else 0
        if cid not in CRAFTS or CRAFTS[cid].needs not in state.tribes[site.tribe_id].knowledge:
            top = 0
        if t[cid] > top:
            t[cid] = top
    while sum(t.values()) > cap:
        # On retire d'abord le dernier metier de la liste.
        last = max((c for c in t if t[c] > 0), key=lambda c: CRAFT_ORDER.index(c) if c in CRAFT_ORDER else 99)
        t[last] -= 1
    for cid in [c for c, n in t.items() if n <= 0]:
        del t[cid]


def output(state, site, cid: str) -> float:
    """Production d'une semaine : charges (ou vivres pour les pecheurs)."""
    from src.kora import villages

    n = teams_of(site, cid)
    if n <= 0:
        return 0.0
    craft = CRAFTS[cid]
    _count, best = deposits(state, site, cid)
    rich = 0.5 + best
    shop = WORKSHOP if villages.has(site, "atelier") else 1.0
    if craft.food:
        mult = FISH_NETS if "filets" in state.tribes[site.tribe_id].knowledge else 1.0
        return n * craft.food * rich * mult * shop
    return n * OUTPUT * rich * shop


# --- reserve du peuple -------------------------------------------------------------


def stock(state, tribe_id: int, good: str) -> float:
    tribe = state.tribes.get(tribe_id)
    goods = getattr(tribe, "goods", None) if tribe is not None else None
    return goods.get(good, 0.0) if goods else 0.0


def supplied(state, tribe_id: int, good: str) -> bool:
    """Le peuple a de ce bien en reserve : son effet joue."""
    return stock(state, tribe_id, good) > 0.0


def villagers(state, tribe_id: int) -> int:
    from src.kora import villages

    total = 0
    for site in state.sites.values():
        if site.kind == "village" and site.tribe_id == tribe_id:
            band = villages.band_of(state, site)
            if band is not None:
                total += band.population
    return total


def need(state, tribe_id: int) -> float:
    """Charges consommees par semaine, par bien."""
    return villagers(state, tribe_id) / 100.0 * NEED


def made(state, tribe_id: int, good: str) -> float:
    """Production d'une semaine de tous les villages du peuple."""
    cid = GOOD_CRAFT[good]
    return sum(
        output(state, s, cid) for s in state.sites.values() if s.kind == "village" and s.tribe_id == tribe_id
    )


def update(state) -> None:
    """Chaque semaine : les equipes produisent, les villages consomment."""
    from src.kora import villages
    from src.kora.sim import stock_max

    users: dict[int, int] = {}
    for site in sorted(state.sites.values(), key=lambda s: s.id):
        if site.kind != "village":
            continue
        band = villages.band_of(state, site)
        if band is None:
            continue
        users[band.tribe_id] = users.get(band.tribe_id, 0) + band.population
        _fit_teams(state, site, band)
        tribe = state.tribes[band.tribe_id]
        for cid, n in sorted(teams(site).items()):
            if n <= 0 or cid not in CRAFTS:
                continue
            craft = CRAFTS[cid]
            got = output(state, site, cid)
            if craft.food:
                band.stock = min(stock_max(band, state), band.stock + got)
            else:
                tribe.goods[craft.good] = min(CAP, tribe.goods.get(craft.good, 0.0) + got)
    for tid, pop in sorted(users.items()):
        tribe = state.tribes.get(tid)
        if tribe is None or not tribe.goods:
            continue
        use = pop / 100.0 * NEED
        for good in list(tribe.goods):
            left = tribe.goods[good] - use
            if left > 1e-6:
                tribe.goods[good] = left
            else:
                del tribe.goods[good]


# --- effets ------------------------------------------------------------------------


def rot_mult(state, tribe_id: int) -> float:
    return 0.6 if supplied(state, tribe_id, "poteries") else 1.0


def store_weeks(state, tribe_id: int) -> float:
    return (4.0 if supplied(state, tribe_id, "poteries") else 0.0) + (3.0 if supplied(state, tribe_id, "sel") else 0.0)


def winter_famine(state, tribe_id: int) -> float:
    mult = 1.0
    if supplied(state, tribe_id, "sel"):
        mult *= 0.8
    if supplied(state, tribe_id, "etoffes"):
        mult *= 0.85
    if supplied(state, tribe_id, "cuirs"):
        mult *= 0.9
    return mult


def stability_parts(state, tribe_id: int) -> list[tuple[str, float]]:
    out = []
    if supplied(state, tribe_id, "sel"):
        out.append(("Sel", 3.0))
    if supplied(state, tribe_id, "etoffes"):
        out.append(("Etoffes", 6.0))
    if supplied(state, tribe_id, "cuirs"):
        out.append(("Cuirs et fourrures", 2.0))
    return out


def yield_mult(state, tribe_id: int) -> float:
    return 1.1 if supplied(state, tribe_id, "haches") else 1.0


def army_mult(state, tribe_id: int) -> float:
    return 1.1 if supplied(state, tribe_id, "haches") else 1.0


def build_mult(state, tribe_id: int) -> float:
    return 0.75 if supplied(state, tribe_id, "haches") else 1.0


def winter_prestige(state, tribe_id: int) -> int:
    return 1 if supplied(state, tribe_id, "etoffes") else 0


def forage_mult(site, band) -> float:
    """Les gens de metier chassent et cueillent moins."""
    if band is None or band.population <= 0:
        return 1.0
    return 1.0 - FORAGE_LOSS * workers(site, band) / band.population


# --- marche : prix -----------------------------------------------------------------


def _village_sites(state, tribe_id: int) -> list:
    from src.kora import villages

    return [
        s
        for s in sorted(state.sites.values(), key=lambda s: s.id)
        if s.kind == "village" and s.tribe_id == tribe_id and villages.band_of(state, s) is not None
    ]


def _village_hexes(state, tribe_id: int) -> list:
    return [s.hex for s in _village_sites(state, tribe_id)]


def has_village(state, tribe_id: int) -> bool:
    return bool(_village_hexes(state, tribe_id))


def reserve(state, tribe_id: int) -> float:
    return need(state, tribe_id) * RESERVE_WEEKS


def spare(state, tribe_id: int, good: str) -> float:
    return max(0.0, stock(state, tribe_id, good) - reserve(state, tribe_id))


def wants(state, tribe_id: int, good: str) -> float:
    if not has_village(state, tribe_id):
        return 0.0
    return max(0.0, reserve(state, tribe_id) - stock(state, tribe_id, good))


def offers(state, giver: int, taker: int) -> list[str]:
    """Biens que `giver` a en trop et qui manquent a `taker`."""
    return [g for g in GOODS if spare(state, giver, g) >= 0.5 and wants(state, taker, g) >= 0.5]


def price(state, tribe_id: int, good: str) -> float:
    """Prix d'une charge chez ce peuple : sa valeur, x1,6 quand il n'en a
    pas, x0,5 quand il en a deux fois sa reserve."""
    base = value(good)
    target = reserve(state, tribe_id)
    if target <= 0:
        return round(base * PRICE_NONE, 2)
    ratio = stock(state, tribe_id, good) / target
    return round(base * max(PRICE_LOW, min(PRICE_HIGH, PRICE_HIGH - 0.6 * ratio)), 2)


def price_word(state, tribe_id: int, good: str) -> str:
    r = price(state, tribe_id, good) / value(good)
    if r >= 1.4:
        return "tres cher"
    if r >= 1.1:
        return "cher"
    if r <= 0.75:
        return "bon marche"
    return "prix moyen"


# --- routes ------------------------------------------------------------------------


def _d(state):
    from src.kora import diplo

    return diplo._d(state)


def _pact(state, a: int, b: int) -> bool:
    from src.kora import diplo

    return diplo.has_pact(state, a, b, "commerce")


def all_routes(state) -> list:
    return _d(state).routes


def routes_of(state, tribe_id: int) -> list:
    """Routes ou ce peuple vend ou achete (accord commercial en place)."""
    return [
        r
        for r in all_routes(state)
        if tribe_id in (r.exporter, r.importer) and _pact(state, r.exporter, r.importer)
    ]


def partners(state, tribe_id: int) -> list[int]:
    """Peuples lies a celui-ci par un accord commercial."""
    from src.kora import diplo

    alive = {b.tribe_id for b in state.bands.values() if b.population > 0}
    return [t for t in sorted(state.tribes) if t != tribe_id and t in alive and diplo.has_pact(state, tribe_id, t, "commerce")]


def find_route(state, exporter: int, importer: int, good: str):
    return next((r for r in all_routes(state) if r.exporter == exporter and r.importer == importer and r.good == good), None)


def trade_distance(state, a: int, b: int) -> int:
    xs, ys = _village_hexes(state, a), _village_hexes(state, b)
    world = state.world
    return min((world.distance(x, y) for x in xs for y in ys), default=10**6)


def trade_ends(state, a: int, b: int):
    """Les deux villages les plus proches (bouts de la route) ou None."""
    xs, ys = _village_hexes(state, a), _village_hexes(state, b)
    world = state.world
    best = None
    for x in xs:
        for y in ys:
            d = world.distance(x, y)
            if best is None or d < best[0]:
                best = (d, x, y)
    return None if best is None else (best[1], best[2])


def _routes_tech(state, a: int, b: int) -> bool:
    ta, tb = state.tribes.get(a), state.tribes.get(b)
    return any(t is not None and tech.bonuses(t).trade for t in (ta, tb))


def trade_range(state, a: int, b: int) -> int:
    return TRADE_RANGE * (2 if _routes_tech(state, a, b) else 1)


def trade_load(state, a: int, b: int) -> float:
    """Charges d'un convoi par mois entre ces deux peuples."""
    return LOAD * (2 if _routes_tech(state, a, b) else 1)


def places(state, tribe_id: int) -> int:
    from src.kora import villages

    return sum(1 for s in _village_sites(state, tribe_id) if villages.has(s, "place"))


def convoys(state, tribe_id: int) -> int:
    """Convois de porteurs dont dispose ce peuple."""
    tribe = state.tribes.get(tribe_id)
    if tribe is None:
        return 0
    n = CONVOYS_BASE + len(_village_sites(state, tribe_id)) + CONVOYS_PLACE * places(state, tribe_id)
    if tech.bonuses(tribe).trade:
        n += CONVOYS_ROUTES
    return n


def convoys_used(state, tribe_id: int) -> int:
    return sum(r.level for r in routes_of(state, tribe_id) if r.by == tribe_id)


def open_block(state, tribe_id: int, partner: int, good: str, sell: bool, level: int = 1) -> str:
    """Pourquoi ce peuple ne peut pas ouvrir cette route ("" : il peut)."""
    if good not in GOODS:
        return "Bien inconnu"
    if partner not in state.tribes or partner == tribe_id:
        return "Choisissez un partenaire"
    if not _pact(state, tribe_id, partner):
        return f"Pas d'accord commercial avec les {state.tribes[partner].name} (Peuples)"
    if not has_village(state, tribe_id):
        return "Il vous faut un village"
    if not has_village(state, partner):
        return "Ils n'ont pas de village"
    dist, reach = trade_distance(state, tribe_id, partner), trade_range(state, tribe_id, partner)
    if dist > reach:
        return f"Trop loin : {dist} cases entre vos villages ({reach} au plus)"
    exporter, importer = (tribe_id, partner) if sell else (partner, tribe_id)
    if find_route(state, exporter, importer, good) is not None:
        return "Cette route existe deja"
    free = convoys(state, tribe_id) - convoys_used(state, tribe_id)
    if free < level:
        return f"Plus de convois ({convoys_used(state, tribe_id)}/{convoys(state, tribe_id)} : un par village, deux par Place d'echange)"
    return ""


def open_route(state, tribe_id: int, partner: int, good: str, sell: bool, level: int = 1, quiet: bool = False):
    from src.kora.diplo import TradeRoute

    if open_block(state, tribe_id, partner, good, sell, level):
        return None
    exporter, importer = (tribe_id, partner) if sell else (partner, tribe_id)
    route = TradeRoute(exporter, importer, good, level, tribe_id, state.tick_count)
    all_routes(state).append(route)
    if not quiet:
        _note_opened(state, route)
    return route


def level_block(state, tribe_id: int, route, level: int) -> str:
    if route.by != tribe_id:
        return "Cette route est la leur : ils choisissent ses convois"
    if level < 1 or level > MAX_LEVEL:
        return f"De 1 a {MAX_LEVEL} convois"
    extra = level - route.level
    if extra > 0 and convoys(state, tribe_id) - convoys_used(state, tribe_id) < extra:
        return f"Plus de convois ({convoys_used(state, tribe_id)}/{convoys(state, tribe_id)})"
    return ""


def set_level(state, tribe_id: int, route, level: int) -> bool:
    if level_block(state, tribe_id, route, level):
        return False
    route.level = level
    return True


def close_route(state, tribe_id: int, route) -> bool:
    """Fermer une route ; fermer celle que l'autre a ouverte le froisse."""
    from src.kora import diplo

    routes = all_routes(state)
    if route not in routes or tribe_id not in (route.exporter, route.importer):
        return False
    routes.remove(route)
    other = route.importer if tribe_id == route.exporter else route.exporter
    if route.by == other:
        diplo.add_mod(state, tribe_id, other, "route_fermee", -3, actor=tribe_id)
    return True


def route_price(state, route) -> float:
    """Prix d'une charge sur cette route : le prix moyen des deux marches,
    +10 % si le vendeur a une Place d'echange."""
    p = (price(state, route.exporter, route.good) + price(state, route.importer, route.good)) / 2.0
    if places(state, route.exporter):
        p *= PLACE_PRICE
    return round(p, 2)


def _flow(state, route) -> tuple[float, str]:
    """Ce que la route peut porter ce mois (avant paiement) et pourquoi pas."""
    exp, imp = route.exporter, route.importer
    if not has_village(state, exp) or not has_village(state, imp):
        return 0.0, "plus de village d'un cote"
    if trade_distance(state, exp, imp) > trade_range(state, exp, imp):
        return 0.0, "villages trop loin"
    keep = (SELL_KEEP_WEEKS if route.by == exp else RESERVE_WEEKS) * need(state, exp)
    have = stock(state, exp, route.good) - keep
    if have < 0.25:
        return 0.0, "le vendeur n'a rien de trop"
    if route.by == imp:
        room = CAP - stock(state, imp, route.good)
    else:
        room = BUY_UP_TO * reserve(state, imp) - stock(state, imp, route.good)
    if room < 0.25:
        return 0.0, "l'acheteur en a assez"
    return min(route.level * trade_load(state, exp, imp), have, room), ""


def preview(state, tribe_id: int, partner: int, good: str, sell: bool, level: int = 1) -> dict:
    """Ce que rapporterait (ou couterait) cette route le mois prochain."""
    from src.kora.diplo import TradeRoute

    exporter, importer = (tribe_id, partner) if sell else (partner, tribe_id)
    route = find_route(state, exporter, importer, good) or TradeRoute(exporter, importer, good, level, tribe_id, state.tick_count)
    units, why = _flow(state, TradeRoute(exporter, importer, good, level, route.by, route.since))
    p = route_price(state, route)
    return {"units": units, "price": p, "vivres": units * p, "why": why, "mine": price(state, tribe_id, good), "theirs": price(state, partner, good)}


def _food_spare(state, tribe_id: int) -> list:
    from src.kora import villages

    out = []
    for site in _village_sites(state, tribe_id):
        band = villages.band_of(state, site)
        if band is not None:
            out.append(band)
    return out


def _can_pay(state, tribe_id: int) -> float:
    return sum(max(0.0, b.stock - PAY_KEEP_WEEKS * b.population) for b in _food_spare(state, tribe_id))


def _pay(state, payer: int, receiver: int, amount: float) -> float:
    from src.kora.sim import stock_max

    paid = 0.0
    for band in sorted(_food_spare(state, payer), key=lambda b: (-(b.stock - PAY_KEEP_WEEKS * b.population), b.id)):
        take = min(amount - paid, max(0.0, band.stock - PAY_KEEP_WEEKS * band.population))
        if take <= 0:
            continue
        band.stock -= take
        paid += take
        if paid >= amount - 1e-9:
            break
    left = paid
    for band in sorted(_food_spare(state, receiver), key=lambda b: (-(stock_max(b, state) - b.stock), b.id)):
        room = max(0.0, stock_max(band, state) - band.stock)
        put = min(room, left)
        band.stock += put
        left -= put
        if left <= 0:
            break
    return paid


def _book(state, tribe_id: int, key: str, amount: float) -> None:
    tribe = state.tribes.get(tribe_id)
    if tribe is None:
        return
    month = tribe.trade.setdefault("month", {})
    month[key] = round(month.get(key, 0.0) + amount, 2)


def _run_pair(state, routes: list) -> None:
    """Un mois sur les routes entre deux peuples : les biens passent dans les
    deux sens et se compensent (troc) ; seul le solde se paie en vivres. Qui
    ne peut pas payer son solde achete moins."""
    flows = []
    for r in routes:
        units, why = _flow(state, r)
        flows.append([r, units, route_price(state, r), why])
    a, b = routes[0].exporter, routes[0].importer
    for _pass in range(2):
        owe = {a: 0.0, b: 0.0}
        for r, units, p, _why in flows:
            owe[r.importer] += units * p
        payer = a if owe[a] >= owe[b] else b
        receiver = b if payer == a else a
        due = owe[payer] - owe[receiver]
        can = _can_pay(state, payer)
        if due <= can + 1e-9 or owe[payer] <= 0:
            break
        # Il ne peut pas payer tout son solde : il prend moins.
        cut = max(0.0, 1.0 - (due - can) / owe[payer])
        for f in flows:
            if f[0].importer == payer:
                f[1] *= cut
                if f[1] < 0.25:
                    f[3] = "l'acheteur ne peut pas payer"
    for r, units, p, why in flows:
        if units < 0.25:
            r.units, r.paid, r.status = 0.0, 0.0, why or "rien ce mois-ci"
            r.idle += 1
            continue
        exp, imp = state.tribes[r.exporter], state.tribes[r.importer]
        exp.goods[r.good] = exp.goods.get(r.good, 0.0) - units
        if exp.goods[r.good] <= 1e-6:
            del exp.goods[r.good]
        imp.goods[r.good] = min(CAP, imp.goods.get(r.good, 0.0) + units)
        r.units, r.paid, r.status, r.idle = round(units, 2), round(units * p, 1), "", 0
        _book(state, r.exporter, "sold", r.paid)
        _book(state, r.importer, "bought", r.paid)
        _book(state, r.exporter, "out", units)
        _book(state, r.importer, "in", units)
    owe = {a: 0.0, b: 0.0}
    for r in routes:
        owe[r.importer] += r.paid
    payer = a if owe[a] >= owe[b] else b
    receiver = b if payer == a else a
    due = owe[payer] - owe[receiver]
    if due > 0:
        _pay(state, payer, receiver, due)


def monthly(state) -> None:
    """Un mois de commerce : routes sans accord fermees, l'IA gere ses
    routes, chaque route porte ses biens, on tient les comptes."""
    from src.kora import diplo

    d = getattr(state, "diplo", None)
    if d is None:
        return
    alive = {b.tribe_id for b in state.bands.values() if b.population > 0}
    d.routes[:] = [
        r
        for r in d.routes
        if r.exporter in alive and r.importer in alive and _pact(state, r.exporter, r.importer)
    ]
    for tid in sorted(alive):
        tribe = state.tribes.get(tid)
        if tribe is not None and not tribe.is_player and (state.tick_count // 4 + tid) % 2 == 0:
            ai_routes(state, tid)
    for tribe in state.tribes.values():
        trade = getattr(tribe, "trade", None)
        if trade is not None:
            for key in [k for k in trade if k not in ("month", "hist")]:
                # Anciennes sauvegardes (echanges automatiques) : oubliees.
                del trade[key]
            trade["month"] = {}
    delivered = set()
    by_pair: dict = {}
    for r in sorted(d.routes, key=lambda r: (r.exporter, r.importer, r.good)):
        by_pair.setdefault(diplo.pair(r.exporter, r.importer), []).append(r)
    for key in sorted(by_pair):
        _run_pair(state, by_pair[key])
        for r in by_pair[key]:
            if r.units > 0:
                delivered.add(key)
                if _player_in(state, r):
                    _reveal(state, r)
    for a, b in sorted(delivered):
        mods = d.mods.get((a, b), [])
        now = next((m.value for m in mods if m.key == "echanges"), 0.0)
        if now < 15.0:
            diplo.add_mod(state, a, b, "echanges", min(1.0, 15.0 - now))
    for tid in sorted(alive):
        tribe = state.tribes.get(tid)
        if tribe is None:
            continue
        month = tribe.trade.get("month", {})
        if month or tribe.trade.get("hist"):
            hist = tribe.trade.setdefault("hist", [])
            hist.append([state.clock.year, state.clock.week, round(month.get("sold", 0.0), 1), round(month.get("bought", 0.0), 1)])
            del hist[:-HISTORY]
    _note_player(state)


def _player_in(state, route) -> bool:
    return any(state.tribes[t].is_player for t in (route.exporter, route.importer) if t in state.tribes)


def _reveal(state, route) -> None:
    """Les porteurs racontent le chemin : le joueur voit le pays entre les
    deux villages."""
    from src.kora.world import axial_to_offset, offset_to_axial

    vis = getattr(state, "vision", None)
    ends = trade_ends(state, route.exporter, route.importer)
    if vis is None or ends is None or not hasattr(vis, "explored"):
        return
    world = state.world
    a, b = ends
    (ca, ra), (cb, rb) = axial_to_offset(a), axial_to_offset(b)
    dc = cb - ca
    if world.wrap_x and abs(dc) > world.width / 2:
        dc -= world.width if dc > 0 else -world.width
    steps = max(1, world.distance(a, b))
    for i in range(steps + 1):
        t = i / steps
        col = int(round(ca + dc * t)) % world.width
        row = int(round(ra + (rb - ra) * t))
        h = world.canonicalize(offset_to_axial(col, row))
        if h is not None:
            vis.explored.update(world.hexes_in_radius(h, REVEAL_WIDTH))


def history(state, tribe_id: int) -> list:
    tribe = state.tribes.get(tribe_id)
    return list(tribe.trade.get("hist", [])) if tribe is not None else []


def last_month(state, tribe_id: int) -> dict:
    tribe = state.tribes.get(tribe_id)
    hist = tribe.trade.get("hist", []) if tribe is not None else []
    if not hist:
        return {"sold": 0.0, "bought": 0.0}
    _y, _w, sold, bought = hist[-1]
    return {"sold": sold, "bought": bought}


def summary(state, me: int, other: int) -> str:
    """Ce que les routes entre ces deux peuples ont fait le dernier mois."""
    parts = []
    gain = 0.0
    for r in routes_of(state, me):
        if other not in (r.exporter, r.importer) or r.units <= 0:
            continue
        name = GOOD_NAMES[r.good].lower()
        if r.exporter == me:
            parts.append(f"vendu {r.units:.0f} {name}")
            gain += r.paid
        else:
            parts.append(f"achete {r.units:.0f} {name}")
            gain -= r.paid
    if not parts:
        return ""
    if gain >= 1:
        parts.append(f"+{gain:.0f} vivres")
    elif gain <= -1:
        parts.append(f"{gain:.0f} vivres")
    return ", ".join(parts)


def route_text(state, me: int, route) -> str:
    """Une route vue par `me` : sens, bien, partenaire."""
    other = route.importer if route.exporter == me else route.exporter
    name = GOOD_NAMES[route.good].lower()
    who = state.tribes[other].name if other in state.tribes else "?"
    return f"Vendre {name} aux {who}" if route.exporter == me else f"Acheter {name} aux {who}"


def _note_opened(state, route) -> None:
    by = state.tribes.get(route.by)
    if by is None or by.is_player:
        return
    other = route.importer if route.by == route.exporter else route.exporter
    if other not in state.tribes or not state.tribes[other].is_player:
        return
    some = GOOD_SOME.get(route.good, route.good)
    if route.by == route.exporter:
        text = f"Les {by.name} ouvrent une route : leurs porteurs vous vendront {some} chaque mois (Commerce [M] : vous pouvez la fermer)."
    else:
        text = f"Les {by.name} ouvrent une route : ils vous achetent {some} chaque mois (Commerce [M] : vous pouvez la fermer)."
    state.log.add(LogKind.POLITIQUE, text, state.clock.year, state.clock.week)


def _note_player(state) -> None:
    """Une ligne au journal par saison : ce que le commerce a rapporte."""
    if state.tick_count % 13 >= 4:
        return
    for tribe in state.tribes.values():
        if not tribe.is_player:
            continue
        month = last_month(state, tribe.id)
        if month["sold"] >= 1 or month["bought"] >= 1:
            state.log.add(
                LogKind.POLITIQUE,
                f"Commerce du mois : ventes +{month['sold']:.0f} vivres, achats -{month['bought']:.0f} vivres.",
                state.clock.year,
                state.clock.week,
            )


# --- IA ----------------------------------------------------------------------------

# Ce que l'IA met au travail, dans l'ordre : le sel et les pots d'abord.
AI_ORDER = ("sauniers", "potiers", "tisserands", "pelletiers", "tailleurs", "pecheurs")


def ai_crafts(state, site, band, weeks: float) -> None:
    """Un village IA met aux metiers les bras dont ses champs n'ont pas
    besoin ; les pecheurs quand le grenier est bas."""
    import math

    from src.kora import villages

    fields = min(villages.MAX_FIELDS, max(1, math.ceil(band.population / villages.FIELD_WORKERS)))
    free = int(band.population - fields * villages.FIELD_HANDS) // TEAM
    cap = min(team_cap(band), free)
    if cap <= 0:
        return
    for cid in AI_ORDER:
        if total_teams(site) >= cap:
            break
        if CRAFTS[cid].food and weeks >= 12:
            continue
        want = 1 if not CRAFTS[cid].food else 2
        if teams_of(site, cid) < want and not add_block(state, site, cid):
            set_teams(state, site, cid, teams_of(site, cid) + 1)


def ai_routes(state, tribe_id: int) -> None:
    """Un peuple IA gere ses routes : il ferme celles qui ne portent plus
    rien, vend ce qu'il a de trop a qui en manque (joueur compris), achete
    ce qui lui manque chez qui en a trop, ajoute un convoi a une route pleine."""
    if not has_village(state, tribe_id):
        return
    mine = [r for r in routes_of(state, tribe_id) if r.by == tribe_id]
    for r in mine:
        if r.idle >= IDLE_CLOSE:
            all_routes(state).remove(r)
    for r in [r for r in routes_of(state, tribe_id) if r.by == tribe_id]:
        full = r.units >= r.level * trade_load(state, r.exporter, r.importer) - 1e-6
        if full and r.level < MAX_LEVEL and not level_block(state, tribe_id, r, r.level + 1):
            r.level += 1
    for other in partners(state, tribe_id):
        if not has_village(state, other):
            continue
        for good in GOODS:
            if convoys(state, tribe_id) - convoys_used(state, tribe_id) <= 0:
                return
            if spare(state, tribe_id, good) >= 2.0 and wants(state, other, good) >= 1.0:
                open_route(state, tribe_id, other, good, sell=True)
            elif wants(state, tribe_id, good) >= 1.0 and spare(state, other, good) >= 2.0:
                open_route(state, tribe_id, other, good, sell=False)


# --- lecture -----------------------------------------------------------------------


def lines(state, site, band) -> list[str]:
    """Metiers du village, en quelques mots (fiches, panneau)."""
    out = []
    for cid in CRAFT_ORDER:
        n = teams_of(site, cid)
        if n:
            craft = CRAFTS[cid]
            out.append(f"{craft.name} : {n} equipe{'s' if n > 1 else ''}")
    return out
