"""L'OST : le suzerain appelle les troupes de ses tributaires.

Une troupe d'un peuple qui a des tributaires (et leurs tributaires,
chiefdom.descendants) APPELLE L'OST [H] : les troupes de ces tributaires a
OST_RANGE cases ou moins marchent vers elle (Band.ost : la troupe qu'elles
rejoignent) et, arrivees, se fondent dans sa pile. Une seule grande troupe,
sous le chef du suzerain : il la mene et paie sa solde. Les compagnies
gardent leur village : dissoute, chacune rentre chez elle et y redevient
villageoise de son peuple (villages.dissolve).
Le lien se rompt (le tributaire s'est affranchi) : ses compagnies quittent
la troupe et rentrent chez elles (sauf si leur peuple est en guerre avec le
suzerain : elles sont prisonnieres de la pile, comme avant).
Un joueur tributaire peut reprendre sa troupe en chemin : un ordre de marche
annule l'appel (commands).
L'IA : un suzerain trop faible seul contre sa proie appelle l'ost
(ai_war.plan_raid) ; ses tributaires IA viennent toujours.
N'importe pas pygame.
"""

from __future__ import annotations

from src.kora import battle, chiefdom, siege, villages
from src.kora.bands import _absorb, merge_text, set_goto
from src.kora.gamestate import is_human, note
from src.kora.log import LogKind
from src.kora.types import stay_order

OST_RANGE = 20


def _ready(state, band) -> bool:
    return (
        band.kind == "armee"
        and band.population > 0
        and not band.homebound
        and not band.retreating
        and not battle.in_battle(state, band)
    )


def candidates(state, army) -> list:
    """Les troupes des tributaires qui peuvent venir (a OST_RANGE cases)."""
    if army is None or not _ready(state, army):
        return []
    vassals = set(chiefdom.descendants(state, army.tribe_id))
    if not vassals:
        return []
    world = state.world
    return sorted(
        (
            b
            for b in state.bands.values()
            if b.tribe_id in vassals
            and b.ost != army.id
            and _ready(state, b)
            and world.distance(b.position, army.position) <= OST_RANGE
        ),
        key=lambda b: (world.distance(b.position, army.position), b.id),
    )


def call_block(state, army_id: int) -> str:
    army = state.bands.get(army_id)
    if army is None or army.kind != "armee":
        return "Pas une troupe"
    if not chiefdom.descendants(state, army.tribe_id):
        return "L'ost : il faut des tributaires (leurs troupes viendraient)"
    if not _ready(state, army):
        return "La troupe ne peut pas recevoir l'ost maintenant"
    if not candidates(state, army):
        coming = sum(1 for b in state.bands.values() if b.ost == army.id)
        if coming:
            return f"L'ost est en route : {coming} troupe{'s' if coming > 1 else ''}"
        return f"Aucune troupe de vos tributaires à {OST_RANGE} cases"
    return ""


def call(state, army_id: int) -> int:
    """Appeler l'ost : rend le nombre de troupes qui viennent."""
    if call_block(state, army_id):
        return 0
    army = state.bands[army_id]
    come = candidates(state, army)
    lord = state.tribes[army.tribe_id]
    for b in come:
        b.ost = army.id
        b.intent_prey = 0
        b.intent_until = 0
        _walk(state, b, army)
        if is_human(state, b.tribe_id):
            note(state, LogKind.COMBAT, f"Votre suzerain, les {lord.name}, appelle l'ost : votre troupe le rejoint (un ordre de marche l'en retient).", b.position, to=b.tribe_id)
    if is_human(state, army.tribe_id):
        men = sum(b.population for b in come)
        note(state, LogKind.COMBAT, f"L'ost : {len(come)} troupe{'s' if len(come) > 1 else ''} de vos tributaires ({men} guerriers) vien{'nent' if len(come) > 1 else 't'} rejoindre la vôtre.", army.position, to=army.tribe_id)
    return len(come)


def _walk(state, band, army) -> None:
    if band.path and state.world.canonicalize(band.path[-1]) == army.position:
        return
    band.order = stay_order()
    set_goto(state, band.id, army.position, max_nodes=2000, max_cost=6000)


def coming(state, army) -> list:
    return sorted((b for b in state.bands.values() if b.ost == army.id), key=lambda b: b.id)


def _valid(state, band, army) -> bool:
    return (
        army is not None
        and _ready(state, army)
        and _ready(state, band)
        and band.tribe_id in chiefdom.descendants(state, army.tribe_id)
    )


def weekly(state) -> None:
    """L'ost en marche : arrivee, la troupe se fond dans celle du suzerain."""
    for band in sorted((b for b in state.bands.values() if b.ost), key=lambda b: b.id):
        if band.id not in state.bands:
            continue
        army = state.bands.get(band.ost)
        if not _valid(state, band, army):
            band.ost = 0
            continue
        if state.world.distance(band.position, army.position) <= 1:
            join(state, army, band)
            continue
        _walk(state, band, army)
    _release(state)


def join(state, army, band) -> None:
    """La troupe du tributaire se fond dans celle du suzerain."""
    band.ost = 0
    names = [band.leader.name] if band.leader is not None else []
    vassal = band.tribe_id
    _absorb(state, army, band)
    if is_human(state, army.tribe_id):
        note(state, LogKind.COMBAT, "L'ost arrive. " + merge_text(army, names), army.position, to=army.tribe_id)
    if is_human(state, vassal):
        note(state, LogKind.COMBAT, f"Votre troupe a rejoint l'ost des {state.tribes[army.tribe_id].name}.", army.position, to=vassal)


def foreign(state, army) -> dict[int, list]:
    """Les compagnies d'autres peuples dans cette troupe : peuple -> compagnies."""
    out: dict[int, list] = {}
    for comp in army.units:
        site = state.sites.get(comp[2])
        if site is None or site.tribe_id == army.tribe_id:
            continue
        out.setdefault(site.tribe_id, []).append(comp)
    return out


def _release(state) -> None:
    """Le lien rompu : les compagnies d'un ancien tributaire rentrent."""
    for army in sorted((b for b in state.bands.values() if b.kind == "armee" and b.population > 0), key=lambda b: b.id):
        if army.id not in state.bands or battle.in_battle(state, army):
            continue
        parts = foreign(state, army)
        if not parts:
            continue
        vassals = set(chiefdom.descendants(state, army.tribe_id))
        for tid, comps in sorted(parts.items()):
            if tid in vassals or siege.at_war(state, tid, army.tribe_id):
                continue
            if len(comps) >= len(villages._companies(army)):
                break
            villages.send_companies_home(state, army, comps)


def lines(state, army) -> list[str]:
    """Pour la fiche de la troupe : qui est venu, qui vient."""
    out = []
    parts = foreign(state, army)
    if parts:
        who = ", ".join(f"{sum(c[1] for c in comps)} guerriers des {state.tribes[t].name}" for t, comps in sorted(parts.items()) if t in state.tribes)
        out.append(f"L'ost : {who}")
    come = coming(state, army)
    if come:
        out.append(f"L'ost en route : {len(come)} troupe{'s' if len(come) > 1 else ''} ({sum(b.population for b in come)} guerriers)")
    return out
