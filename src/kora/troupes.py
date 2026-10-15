"""LES TROUPES DU VILLAGE : la levee, la milice, la marche, le retour.

Une troupe est une bande (Band.kind == "armee") : une pile de compagnies
[type, hommes, village] (units.py) ; Band.home est le village de sa premiere
compagnie (son chef de guerre y est ne). Elle nait d'une LEVEE dans un
village (raise_army ; LEVIES : une poignee, une troupe, en masse - une part
des LEVABLES : population.levable, des hommes valides seulement).

LA MILICE (militia, levy_plan) : chaque homme a sa categorie, celle de sa
vie de tous les jours, et la garde a la guerre ; on ne choisit pas : une
levee prend la meme part de chaque categorie (HUNTER_SHOT, HUNTER_SCOUT,
WORKER_SHOT, FARMER_GUARD, WARRIORS_GUARD), et ceux qui sont partis restent
dans la leur (men_away). Une troupe se detache, se dissout (chaque compagnie
rentre A PIED a son village : dissolve, _go_home ; une troupe sans village
d'un peuple nomade redevient un clan d'hommes : _to_clan ; un peuple
sedentaire ne refait jamais de bande nomade), se rappelle, se reequipe
(reequip : les unites de l'age). Les vivres : ARMY_SUPPLY_WEEKS emportees,
warn_supply previent le joueur (systems.WEEKLY) ; apres ARMY_TERM semaines,
des desertions (DESERTION). La Maison des guerriers fait leur qualite et
leur moral (army_quality, army_morale). L'ost des tributaires : ost.py.
N'importe pas pygame.
"""

from __future__ import annotations

from src.kora import chiefdom, chiefs, goods, population, systems, units, villages
from src.kora.bands import (
    _absorb,
    _ai_caches_changed,
    campaign_weeks,
    new_band_id,
    set_goto,
    stock_max,
    weeks_between,
)
from src.kora.gamestate import is_human
from src.kora.log import LogKind
from src.kora.places import band_of, has, name, site_of
from src.kora.population import _craft_take, ACTIVE_NORM
from src.kora.types import Band


# Troupes : part des habitants levee, vivres emportes, duree avant les
# desertions.
# Une levee prend une part des LEVABLES (population.levable : une part des
# hommes valides seulement).
LEVIES = (("poignee", 0.35, "Une poignée"), ("troupe", 0.7, "Une troupe"), ("masse", 1.0, "Tous les levables"))
LEVY_SHARE = {k: v for k, v, _l in LEVIES}
ARMY_MIN_VILLAGE = 40
ARMY_MIN = 5
# LA MILICE : chaque homme du village a sa categorie, celle de sa vie de
# tous les jours, et la garde a la guerre (on ne choisit pas : une levee
# prend la meme part de chacune).
#   les chasseurs  : la moitie tire (l'arc, sinon la fronde), un sur cinq
#                    piste (Pistes et reperes), les autres a la melee ;
#   les champs et  : la melee ; un sur cinq tire (l'arc du paysan) ; un
#   les metiers      sur quatre a la garde (les porteurs de boucliers :
#                    Palissades ; un sur trois avec la Maison des guerriers).
HUNTER_SHOT = 0.5
HUNTER_SCOUT = 0.2
WORKER_SHOT = 0.2
FARMER_GUARD = 0.25
WARRIORS_GUARD = 0.35
VILLAGE_KEEP = 20
ARMY_SUPPLY_WEEKS = 8
ARMY_TERM = 26
DESERTION = 0.05
ARMY_HOME = 1
WARRIORS_QUALITY = 1.25
WARRIORS_MORALE = 10.0


def _companies(band) -> list:
    return units.normalize(band)


def armies_of(state, site) -> list:
    """Troupes ou sert au moins une compagnie de ce village."""
    return sorted(
        (
            b
            for b in state.bands.values()
            if b.kind == "armee" and b.population > 0 and any(u[2] == site.id for u in _companies(b))
        ),
        key=lambda b: b.id,
    )


def companies_of(state, site) -> int:
    """Les troupes ou servent des hommes de ce village (la limite du village :
    army_cap ; une levee faite au village rejoint la troupe qui y est)."""
    return len(armies_of(state, site))


def army_cap(state, site) -> int:
    """Compagnies qu'un village peut avoir sous les armes en meme temps."""
    return 2 + (1 if has(site, "guerriers") else 0)


def _village_alive(state, site_id: int):
    site = state.sites.get(site_id)
    if site is None or site.kind != "village" or band_of(state, site) is None:
        return None
    return site


def home_of(state, band):
    if band is None or band.kind != "armee":
        return None
    return _village_alive(state, band.home)


# Le journal previent le joueur quand une troupe n'a plus de vivres que
# pour rentrer (et SUPPLY_WARN_MARGIN semaines) ; une fois par
# SUPPLY_WARN_EVERY semaines.
SUPPLY_WARN_MARGIN = 2
SUPPLY_WARN_EVERY = 8


def warn_supply(state) -> None:
    """Chaque semaine (systems.WEEKLY) : les troupes du joueur loin de chez
    elles et a court de vivres."""
    for army in sorted(state.bands.values(), key=lambda b: b.id):
        if army.kind != "armee" or army.population <= 0 or army.homebound:
            continue
        tribe = state.tribes.get(army.tribe_id)
        if tribe is None or not is_human(state, tribe.id):
            continue
        home = home_of(state, army)
        back = weeks_home(state, army)
        left = campaign_weeks(state, army)
        if home is None or back <= 0 or left >= back + SUPPLY_WARN_MARGIN:
            continue
        flags = tribe.flags if tribe.flags is not None else {}
        key = f"vivres_troupe:{army.id}"
        if state.tick_count - flags.get(key, -10**6) < SUPPLY_WARN_EVERY:
            continue
        flags[key] = state.tick_count
        tribe.flags = flags
        who = army.leader.name if army.leader is not None else "la troupe"
        villages._note(state, LogKind.COMBAT, f"La troupe de {who} n'a plus que {left:.0f} semaine{'s' if left >= 2 else ''} de vivres, et {name(home)} est à {back} semaine{'s' if back > 1 else ''} : rentrez, ou elle aura faim.", army.position, to=tribe.id)


def weeks_home(state, band, start=None) -> int:
    """Semaines de marche d'une troupe jusqu'a son village (depuis `start`,
    sinon d'ou elle est) ; 0 sans village."""
    site = home_of(state, band)
    if site is None:
        return 0
    return weeks_between(state, start if start is not None else band.position, site.hex)


def _warrior_share(state, band) -> float:
    comps = _companies(band)
    total = sum(u[1] for u in comps)
    if total <= 0:
        return 0.0
    trained = sum(u[1] for u in comps if has(_village_alive(state, u[2]), "guerriers"))
    return trained / total


def army_quality(state, band) -> float:
    return (1.0 + (WARRIORS_QUALITY - 1.0) * _warrior_share(state, band)) * goods.army_mult(state, band.tribe_id)


def army_morale(state, band) -> float:
    # Et ce que chaque systeme y ajoute (systems.ARMY_MORALE).
    return WARRIORS_MORALE * _warrior_share(state, band) + systems.total(systems.ARMY_MORALE, state, band.tribe_id)


def men_away(state, site) -> dict[str, int]:
    """Les hommes de ce village deja sous les armes, par role."""
    out: dict[str, int] = {}
    if site is None:
        return out
    for a in state.bands.values():
        if a.kind != "armee" or a.population <= 0:
            continue
        for type_id, men, home in _companies(a):
            if home == site.id:
                role = units.UNITS[type_id].role if type_id in units.UNITS else "melee"
                out[role] = out.get(role, 0) + men
    return out


def levy_size(band, share: float, state=None) -> int:
    """Combien d'hommes part une levee : une part des LEVABLES (une part des
    hommes valides, population.py), jamais les enfants, les femmes, les
    anciens ni les blesses. Avec `state` : ceux deja partis comptent (un
    village ne met jamais sous les armes plus que LEVY_MAX de ses hommes)."""
    free = population.levable(band)
    if state is not None:
        away = sum(men_away(state, site_of(state, band)).values())
        if away:
            free = min(free, max(0, int((population.fit_men(band) + away) * population.LEVY_MAX) - away))
    return int(free * share)


def militia(state, band) -> list[tuple]:
    """Les hommes du village, chacun dans sa categorie : [(type, hommes)]
    pour ceux qui sont encore au village (ceux deja partis sont dans leurs
    compagnies). Les parts sont celles du village entier : une levee
    d'archers laisse moins d'archers au village."""
    site = site_of(state, band)
    tribe = state.tribes[band.tribe_id]
    away = men_away(state, site)
    men = population.fit_men(band) + sum(away.values())
    women = population.fit_women(band)
    crafts = fields = 0
    if site is not None:
        m_left, w_left = men, women
        for cid, n in sorted(goods.teams(site).items()):
            if n <= 0 or cid not in goods.CRAFTS:
                continue
            m, w = _craft_take(cid, goods.TEAM * n, m_left, w_left)
            m_left -= m
            w_left -= w
            crafts += m
        need = int(round(len(site.data.fields) * villages.FIELD_HANDS * ACTIVE_NORM))
        free = m_left + w_left
        if need > 0 and free > 0:
            fields = int(round(min(need, free) * m_left / free))
    hunters = max(0, men - crafts - fields)
    workers = men - hunters
    target = {"melee": 0.0, "tir": hunters * HUNTER_SHOT + workers * WORKER_SHOT, "garde": 0.0, "eclaireurs": 0.0}
    if units.best(tribe, "eclaireurs") is not None:
        target["eclaireurs"] = hunters * HUNTER_SCOUT
    if units.best(tribe, "garde") is not None:
        target["garde"] = workers * (WARRIORS_GUARD if site is not None and has(site, "guerriers") else FARMER_GUARD)
    target["melee"] = men - sum(target.values())
    pool = {role: max(0.0, target[role] - away.get(role, 0)) for role in units.ROLES}
    out = []
    for role in units.ROLES:
        u = units.best(tribe, role)
        if u is not None and pool[role] > 0:
            out.append((u, pool[role]))
    return out


def split_by(parts: list[tuple], n: int) -> list[tuple]:
    """n hommes repartis comme `parts` (plus forts restes)."""
    total = sum(w for _u, w in parts)
    if total <= 0 or n <= 0:
        return []
    shares = [n * w / total for _u, w in parts]
    cut = [int(s) for s in shares]
    left = n - sum(cut)
    for i in sorted(range(len(parts)), key=lambda i: (-(shares[i] - cut[i]), i))[:left]:
        cut[i] += 1
    return [(u, c) for (u, _w), c in zip(parts, cut) if c > 0]


def levy_plan(state, band, share: float) -> list[tuple]:
    """Qui part dans cette levee : la meme part de chaque categorie."""
    return split_by(militia(state, band), levy_size(band, share, state))


def militia_text(state, band) -> str:
    """La milice du village : "12 archers · 30 épieux · ..." (tous les levables)."""
    plan = split_by(militia(state, band), levy_size(band, 1.0, state))
    return " · ".join(f"{n} {u.short.lower() if u.short else u.name.lower()}" for u, n in plan)


def plan_text(plan: list[tuple]) -> str:
    return ", ".join(f"{n} {u.name.lower()}" for u, n in plan)


def army_block(state, band_id: int, share: float = LEVY_SHARE["troupe"], type_id: str | None = None) -> str:
    """type_id : ignore (vieilles commandes) ; la levee suit la milice."""
    band = state.bands.get(band_id)
    site = site_of(state, band)
    if site is None:
        return "Seul un village leve des guerriers"
    if band.population < ARMY_MIN_VILLAGE:
        return f"Il faut {ARMY_MIN_VILLAGE} habitants"
    n = levy_size(band, share, state)
    if n < ARMY_MIN:
        if men_away(state, site) and population.levable(band) * share >= ARMY_MIN:
            return f"Vos hommes sont déjà sous les armes ({n} de plus au plus)"
        return f"Trop peu de guerriers ({n}, il en faut {ARMY_MIN})"
    if band.population - n < VILLAGE_KEEP:
        return "Le village se viderait"
    count, cap = companies_of(state, site), army_cap(state, site)
    if count >= cap and _home_army(state, band, site) is None:
        return f"Déjà {count}/{cap} troupes levées (Maison des guerriers : une de plus)"
    return ""


def raise_army(state, band_id: int, share: float = LEVY_SHARE["troupe"], type_id: str | None = None):
    """Le village leve une compagnie : ses hommes partent avec des vivres du
    grenier. Une troupe du village est au village : la compagnie la rejoint ;
    sinon, c'est une nouvelle troupe, menee par un chef de guerre."""
    if army_block(state, band_id, share):
        return None
    band = state.bands[band_id]
    site = site_of(state, band)
    tribe = state.tribes[band.tribe_id]
    # Chacun part dans sa categorie (la milice du village) : une compagnie
    # par categorie.
    plan = levy_plan(state, band, share)
    n = population.take_men(band, sum(c for _u, c in plan))
    plan = split_by(plan, n)
    if not plan:
        return None
    # Les vivres des guerriers : le grenier du chef d'abord, puis le village.
    supply = chiefdom.granary_pay(state, band.tribe_id, float(ARMY_SUPPLY_WEEKS * n))
    extra = min(band.stock, float(ARMY_SUPPLY_WEEKS * n) - supply)
    band.stock -= extra
    supply += extra
    here = _home_army(state, band, site)
    if here is not None:
        for u, men in plan:
            units.add(here, u.id, men, site.id)
        here.stock = min(stock_max(here, state), here.stock + supply)
        if tribe.is_player:
            villages._note(state, LogKind.COMBAT, f"{name(site)} leve {plan_text(plan)} : ils rejoignent la troupe.", site.hex, to=tribe.id)
        return here
    nid = new_band_id(state)
    army = Band(
        nid, band.tribe_id, site.hex, n, supply, kind="armee", home=site.id, raised=state.tick_count,
        units=[[u.id, men, site.id] for u, men in plan],
    )
    army.leader = chiefs.new_person(state, tribe)
    army.loyalty = 100.0
    state.bands[nid] = army
    _ai_caches_changed(state)
    if tribe.is_player:
        villages._note(state, LogKind.COMBAT, f"{name(site)} leve une troupe : {plan_text(plan)}, menés par {army.leader.name}.", site.hex, to=tribe.id)
    return army


def _home_army(state, band, site):
    """La troupe de ce peuple qui est au village (une levee la rejoint)."""
    return next(
        (
            a
            for a in armies_of(state, site)
            if a.tribe_id == band.tribe_id
            and not a.homebound
            and not a.retreating
            and state.world.distance(a.position, site.hex) <= ARMY_HOME
        ),
        None,
    )


def detach_block(state, band_id: int) -> str:
    band = state.bands.get(band_id)
    if band is None or band.kind != "armee":
        return "Pas une troupe"
    if band.homebound:
        return "La troupe rentre au village"
    if band.retreating:
        return "La troupe est en repli"
    if len(_companies(band)) < 2:
        return "Une seule compagnie : rien a détacher"
    return ""


def _split_units(state, band, comps: list, leader=None, homebound: bool = False):
    """Une nouvelle troupe faite de ces compagnies (retirees de band)."""
    men = sum(u[1] for u in comps)
    share = men / max(1, band.population)
    stock = band.stock * share
    band.stock -= stock
    band.units = [u for u in band.units if not any(u is c for c in comps)]
    band.population -= men
    nid = new_band_id(state)
    out = Band(
        nid, band.tribe_id, band.position, men, stock, kind="armee", home=comps[0][2], raised=band.raised,
        units=[list(u) for u in comps], homebound=homebound,
    )
    out.leader = leader or chiefs.new_person(state, state.tribes[band.tribe_id])
    out.loyalty = 100.0
    state.bands[nid] = out
    _ai_caches_changed(state)
    return out


def detach(state, band_id: int):
    """La derniere compagnie forme une troupe a part."""
    if detach_block(state, band_id):
        return None
    band = state.bands[band_id]
    comp = _companies(band)[-1]
    return _split_units(state, band, [comp])


def disband_block(state, band_id: int) -> str:
    """Rentrer tout de suite : au village (sinon, dissoudre = rentrer a pied)."""
    band = state.bands.get(band_id)
    if band is None or band.kind != "armee":
        return "Pas une troupe"
    if band.retreating:
        return "La troupe est en repli"
    if village_near(state, band) is None:
        return "Rentrez au village pour libérer les guerriers"
    return ""


def dissolve_block(state, band_id: int) -> str:
    band = state.bands.get(band_id)
    if band is None or band.kind != "armee":
        return "Pas une troupe"
    if band.retreating:
        return "La troupe est en repli"
    if band.homebound:
        return "La troupe rentre déjà au village"
    return ""


def village_near(state, band):
    """Village de son peuple sur la case (ou a cote) : le sien d'abord."""
    best = None
    for site in state.sites.values():
        if site.kind != "village" or site.tribe_id != band.tribe_id or band_of(state, site) is None:
            continue
        if state.world.distance(site.hex, band.position) <= ARMY_HOME:
            if site.id == band.home:
                return site
            best = best or site
    return best


def _join_village(state, army, site) -> None:
    """Les hommes de la troupe redeviennent villageois de ce village."""
    home = band_of(state, site)
    keep = home.loyalty
    n = army.population
    army.units = []
    _absorb(state, home, army)
    if not chiefs.is_chief_band(state, home):
        home.loyalty = keep
    if state.tribes[home.tribe_id].is_player:
        villages._note(state, LogKind.COMBAT, f"La troupe rentre à {name(site)} : {n} guerriers retrouvent leurs champs.", site.hex, to=home.tribe_id)


def _to_clan(state, band) -> None:
    """Une troupe qui n'a plus son village. Un peuple sedentaire ne refait
    JAMAIS de tribu nomade : elle rentre au village le plus proche de son
    peuple (a pied ; sans chemin, ses hommes le rejoignent par d'autres
    voies). Seul un peuple sans aucun village en refait un clan."""
    homes = sorted(
        (s for s in state.sites.values() if s.kind == "village" and s.tribe_id == band.tribe_id and band_of(state, s) is not None),
        key=lambda s: (state.world.distance(s.hex, band.position), s.id),
    )
    if homes:
        site = homes[0]
        band.home = site.id
        for u in band.units:
            u[2] = site.id
        band.homebound = False
        if state.world.distance(site.hex, band.position) <= ARMY_HOME:
            _join_village(state, band, site)
            return
        set_goto(state, band.id, site.hex, max_nodes=8000, max_cost=40000)
        if band.path:
            band.homebound = True
            if state.tribes[band.tribe_id].is_player:
                villages._note(state, LogKind.COMBAT, f"La troupe rentre à {name(site)}.", band.position, to=band.tribe_id)
            return
        # Aucun chemin : les hommes rentrent par d'autres voies.
        if state.tribes[band.tribe_id].is_player:
            villages._note(state, LogKind.COMBAT, f"Sans chemin praticable, les guerriers rentrent à {name(site)} par d'autres voies.", site.hex, to=band.tribe_id)
        band.position = site.hex
        _join_village(state, band, site)
        return
    # Un clan d'hommes (ni femmes ni enfants ne sortent de nulle part).
    band.demo = dict(band.demo) if band.demo else {"hommes": 1.0}
    band.kind = ""
    band.home = 0
    band.units = []
    band.homebound = False
    if state.tribes[band.tribe_id].is_player:
        who = band.leader.name if band.leader else "?"
        villages._note(state, LogKind.COMBAT, f"La troupe de {who} n'a plus aucun village où rentrer : elle devient un clan errant.", band.position, to=band.tribe_id)


def _send_home(state, band, site) -> None:
    band.homebound = False
    set_goto(state, band.id, site.hex, max_nodes=1200, max_cost=4000)
    if not band.path and state.world.distance(site.hex, band.position) > ARMY_HOME:
        # Loin : on cherche plus longtemps avant de renoncer.
        set_goto(state, band.id, site.hex, max_nodes=8000, max_cost=40000)
    if band.path:
        band.homebound = True
    elif state.world.distance(site.hex, band.position) > ARMY_HOME:
        _to_clan(state, band)


def dissolve(state, band_id: int) -> bool:
    """Dissoudre la troupe : chaque compagnie rentre a son village (a pied)
    et y redevient villageoise a l'arrivee ; au village, tout de suite."""
    if dissolve_block(state, band_id):
        return False
    army = state.bands[band_id]
    comps = _companies(army)
    groups: dict[int, list] = {}
    for u in comps:
        groups.setdefault(u[2], []).append(u)
    here = village_near(state, army)
    main = here.id if here is not None and here.id in groups else (army.home if army.home in groups else max(groups, key=lambda k: sum(u[1] for u in groups[k])))
    for home, us in sorted(groups.items()):
        if home == main:
            continue
        _go_home(state, _split_units(state, army, us), home)
    site = _village_alive(state, main)
    if site is None and here is not None:
        site = here
    if site is None:
        _to_clan(state, army)
    elif state.world.distance(site.hex, army.position) <= ARMY_HOME:
        _join_village(state, army, site)
    else:
        army.home = site.id
        _send_home(state, army, site)
        if army.homebound and state.tribes[army.tribe_id].is_player:
            villages._note(state, LogKind.COMBAT, f"La troupe est dissoute : ses hommes rentrent à {name(site)}.", army.position, to=army.tribe_id)
    return True


def _go_home(state, part, home: int) -> None:
    """Des compagnies rentrent a leur village ; celles d'un autre peuple
    (l'ost d'un tributaire, ost.py) redeviennent une troupe de leur peuple."""
    site = _village_alive(state, home)
    if site is None:
        _to_clan(state, part)
        return
    if site.tribe_id != part.tribe_id and site.tribe_id in state.tribes:
        part.tribe_id = site.tribe_id
        part.leader = chiefs.new_person(state, state.tribes[site.tribe_id])
        part.home = site.id
    if state.world.distance(site.hex, part.position) <= ARMY_HOME:
        _join_village(state, part, site)
    else:
        _send_home(state, part, site)


def send_companies_home(state, army, comps: list) -> None:
    """Ces compagnies quittent la troupe et rentrent chez elles (ost.py)."""
    groups: dict[int, list] = {}
    for u in comps:
        groups.setdefault(u[2], []).append(u)
    for home, us in sorted(groups.items()):
        if sum(u[1] for u in army.units) <= sum(u[1] for u in us):
            return
        _go_home(state, _split_units(state, army, us), home)


def disband(state, band_id: int) -> bool:
    """La troupe est au village : ses guerriers redeviennent villageois (les
    compagnies d'autres villages rentrent chez elles)."""
    if disband_block(state, band_id):
        return False
    return dissolve(state, band_id) if not state.bands[band_id].homebound else _arrive(state, state.bands[band_id])


def _arrive(state, band) -> bool:
    site = _village_alive(state, band.home)
    if site is None:
        _to_clan(state, band)
        return False
    band.homebound = False
    _join_village(state, band, site)
    return True


def recall(state, band_id: int) -> bool:
    """Ancien ordre "Rappeler" : c'est desormais dissoudre (rentrer a pied)."""
    return dissolve(state, band_id)


def reequip_block(state, band_id: int) -> str:
    band = state.bands.get(band_id)
    if band is None or band.kind != "armee":
        return "Pas une troupe"
    site = village_near(state, band)
    if site is None:
        return "Au village seulement"
    tribe = state.tribes[band.tribe_id]
    old = [u for u in _companies(band) if u[2] == site.id and units.outdated(tribe, u[0])]
    if not old:
        return "Rien a rééquiper"
    cost = units.REEQUIP_COST * sum(u[1] for u in old)
    if band_of(state, site).stock < cost:
        return f"Il faut {cost:.0f} vivres au grenier"
    return ""


def reequip(state, band_id: int) -> bool:
    """Un age nouveau : les compagnies de ce village prennent les armes de leur
    temps (meilleur type de leur role)."""
    if reequip_block(state, band_id):
        return False
    band = state.bands[band_id]
    site = village_near(state, band)
    tribe = state.tribes[band.tribe_id]
    village = band_of(state, site)
    for u in _companies(band):
        if u[2] == site.id and units.outdated(tribe, u[0]):
            new = units.best(tribe, units.UNITS[u[0]].role)
            village.stock -= units.REEQUIP_COST * u[1]
            u[0] = new.id
    if tribe.is_player:
        villages._note(state, LogKind.COMBAT, f"{name(site)} rééquipe ses compagnies.", site.hex, to=tribe.id)
    return True


def update_armies(state) -> None:
    """Troupes qui rentrent, troupes sans village, desertions."""
    for band in sorted(state.bands.values(), key=lambda b: b.id):
        if band.kind != "armee" or band.population <= 0 or band.id not in state.bands:
            continue
        comps = _companies(band)
        if band.homebound:
            site = _village_alive(state, band.home)
            if site is None:
                _to_clan(state, band)
            elif state.world.distance(site.hex, band.position) <= ARMY_HOME:
                _arrive(state, band)
            elif not band.path:
                _send_home(state, band, site)
            continue
        if not any(_village_alive(state, u[2]) is not None for u in comps):
            _to_clan(state, band)
            continue
        site = home_of(state, band) or next(_village_alive(state, u[2]) for u in comps if _village_alive(state, u[2]) is not None)
        away = state.world.distance(site.hex, band.position) > 2
        if not away or state.tick_count - band.raised <= ARMY_TERM or state.tick_count % 4:
            continue
        gone = max(1, round(band.population * DESERTION))
        band.population -= gone
        band.wounded = min(band.wounded, band.population)
        population.add(band_of(state, site), gone, "hommes")
        if state.tribes[band.tribe_id].is_player and state.tick_count % 12 == 0:
            villages._note(state, LogKind.COMBAT, f"Trop longtemps loin de {name(site)} : des guerriers désertent et rentrent chez eux.", band.position, to=band.tribe_id)


def army_lines(state, band) -> list[str]:
    """Lignes de la fiche d'une troupe."""
    if band.kind != "armee":
        return []
    site = home_of(state, band)
    home = name(site) if site is not None else "sans village"
    out = [f"Troupe de {home}  ·  {band.population} guerriers  ·  levée il y a {state.tick_count - band.raised} sem."]
    out += units.lines(state, band)
    if band.homebound:
        out.append(f"Dissoute : elle rentre à {home}, on ne la commande plus")
    elif site is not None:
        d = state.world.distance(site.hex, band.position)
        if d > 2 and state.tick_count - band.raised > ARMY_TERM:
            out.append("Trop longtemps loin du village : des guerriers désertent")
        elif d <= ARMY_HOME:
            out.append("Au village : [F] Rentrer libère les guerriers")
    return out
