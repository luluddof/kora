"""IA : quand attaquer, et avec qui.

Une IA n'attaque que si elle gagne avec une marge (AI_RAID_EDGE), forces
comptees la ou le combat aura lieu : elle + ses allies deja pres de la
cible, contre la cible + ses renforts (rayon de renfort de chaque tribu).

Trop faible seule, elle cherche une bande soeur a AI_CALL_RANGE cases
ou moins qui ferait basculer le combat :
  - tout pres (AI_MERGE_RANGE) : elle la rejoint et fusionne ;
  - plus loin : elle l'appelle, l'attend, puis elles partent ensemble
    de la meme case (meme chemin, arrivee la meme semaine).
Un raid en cours est annule si la cible s'est renforcee entre-temps.
"""

from __future__ import annotations

from src.kora import chiefs, diplo
from src.kora.log import LogKind
from src.kora.path import MOVE_POINTS_PER_WEEK, astar, travel_weeks
from src.kora.sim import (
    GameState,
    band_force,
    bands_near,
    bonus_of,
    costs_of,
    defense_force,
    is_shielded,
    note,
    set_goto,
    set_march_to_band,
    side_force,
)
from src.kora.types import Band, OrderKind, stay_order

AI_RAID_REST = 12
AI_RAID_EDGE = 1.25
AI_CALL_RANGE = 10
AI_MERGE_RANGE = 3
AI_PLAN_WEEKS = 8
# Proie cherchee a portee de marche : 4 cases de plaine par semaine de raid.
RAID_REACH_PER_WEEK = MOVE_POINTS_PER_WEEK // 10


def force_at(state: GameState, bands: list[Band], spot) -> float:
    """Force de `bands` si elles combattent sur `spot`, avec les bandes de
    leur tribu deja a portee de renfort de ce point."""
    tribe_id = bands[0].tribe_id
    ids = {b.id for b in bands}
    force = sum(band_force(state, b) for b in bands)
    reach = bonus_of(state, tribe_id).reinforce
    for ally in bands_near(state, spot, reach):
        if ally.id in ids:
            continue
        if ally.tribe_id == tribe_id:
            if not chiefs.helps(state, ally):
                continue
        elif not diplo.allied(state, ally.tribe_id, tribe_id):
            continue
        force += band_force(state, ally)
    return force


def wins(state: GameState, bands: list[Band], prey: Band, edge: float = AI_RAID_EDGE) -> bool:
    # Moral de l'attaquant (battle.py) : des affames ou des etrangers au
    # pays se battent moins bien ; une troupe, mieux.
    from src.kora import battle

    morale, _parts = battle.start_morale(state, bands[0], attacker=True, h=prey.position)
    # Prudente : un bon moral ne lui fait pas oublier sa marge.
    mine = force_at(state, bands, prey.position) * min(1.1, morale / battle.MORALE_BASE)
    return mine > edge * defense_force(state, prey)


def fair_game(state: GameState, band: Band, prey: Band, hungry: bool) -> bool:
    """Un peuple qu'on peut raider : pas de pacte ; un voisin cordial,
    seulement quand on a faim."""
    if prey.tribe_id == band.tribe_id or diplo.at_peace(state, band.tribe_id, prey.tribe_id):
        return False
    if not hungry and diplo.relation(state, band.tribe_id, prey.tribe_id) >= 15:
        return False
    return True


def _free(state: GameState, band: Band) -> bool:
    return (
        band.population > 0
        and not band.retreating
        and not is_shielded(state, band)
        and state.tick_count - band.last_raid_tick >= AI_RAID_REST
    )


def _reachable(state: GameState, band: Band, prey: Band, max_weeks: int) -> bool:
    budget = max_weeks * MOVE_POINTS_PER_WEEK
    if state.world.distance(band.position, prey.position) * 10 > budget:
        return False
    tribe = state.tribes.get(band.tribe_id)
    water_ok = bool(tribe and tribe.cabotage)
    path = astar(
        state.world,
        band.position,
        prey.position,
        max_cost=budget,
        max_nodes=400,
        water_ok=water_ok,
        costs=costs_of(state, band.tribe_id),
    )
    if path is None:
        return False
    weeks = travel_weeks(
        state.world, band.position, path, water_ok=water_ok, costs=costs_of(state, band.tribe_id)
    )
    return weeks <= max_weeks


def _helper(state: GameState, band: Band, prey: Band) -> Band | None:
    best, best_d = None, None
    for ally in state.bands.values():
        if ally.id == band.id or ally.tribe_id != band.tribe_id:
            continue
        # Une troupe s'allie a une troupe, un clan a un clan ; un village ne
        # bouge pas.
        if ally.village or (ally.kind == "armee") != (band.kind == "armee"):
            continue
        if not _free(state, ally) or ally.intent_prey not in (0, prey.id):
            continue
        d = state.world.distance(band.position, ally.position)
        if d > AI_CALL_RANGE:
            continue
        if not wins(state, [band, ally], prey):
            continue
        if best_d is None or d < best_d:
            best, best_d = ally, d
    return best


def plan_raid(state: GameState, band: Band, max_weeks: int, hungry: bool = True):
    """("attack", proie) | ("merge", allie, proie) | ("call", allie, proie) | None."""
    if not _free(state, band) or band.intent_prey:
        return None
    solo = None
    group = None
    reach = max_weeks * RAID_REACH_PER_WEEK
    for prey in bands_near(state, band.position, reach):
        if not fair_game(state, band, prey, hungry):
            continue
        if is_shielded(state, prey):
            continue
        if state.world.distance(band.position, prey.position) > reach:
            continue
        alone = wins(state, [band], prey)
        ally = None if alone else _helper(state, band, prey)
        if not alone and ally is None:
            continue
        if not _reachable(state, band, prey, max_weeks):
            continue
        if alone:
            if solo is None or prey.population < solo.population:
                solo = prey
        elif group is None or prey.population < group[1].population:
            group = (ally, prey)
    if solo is not None:
        return ("attack", solo)
    if group is not None:
        ally, prey = group
        near = state.world.distance(band.position, ally.position) <= AI_MERGE_RANGE
        return ("merge" if near else "call", ally, prey)
    return None


def start_plan(state: GameState, band: Band, plan) -> None:
    from src.kora.vision import is_visible

    if plan[0] == "attack":
        set_march_to_band(state, band.id, plan[1].id)
        return
    kind, ally, prey = plan
    until = state.tick_count + AI_PLAN_WEEKS
    for b in (band, ally):
        b.intent_prey = prey.id
        b.intent_until = until
    if kind == "merge":
        # Rejoindre = fusion a l'arrivee (resolve_joins).
        set_march_to_band(state, band.id, ally.id)
    else:
        band.order = stay_order()
        band.path = []
        set_goto(state, ally.id, band.position)
    if is_visible(state, band.position) or is_visible(state, ally.position):
        tribe = state.tribes.get(band.tribe_id)
        name = tribe.name if tribe else "ennemis"
        note(state, LogKind.COMBAT, f"Des {name} se regroupent.", where=band.position)


def _drop_plan(band: Band) -> None:
    band.intent_prey = 0
    band.intent_until = 0


def advance_plans(state: GameState) -> None:
    """Chaque semaine : les bandes qui preparent un raid a plusieurs."""
    for band in list(state.bands.values()):
        if band.id not in state.bands or not band.intent_prey:
            continue
        tribe = state.tribes.get(band.tribe_id)
        if tribe is None or tribe.is_player:
            _drop_plan(band)
            continue
        prey = state.bands.get(band.intent_prey)
        if (
            prey is None
            or prey.population <= 0
            or band.retreating
            or state.tick_count > band.intent_until
            or diplo.at_peace(state, band.tribe_id, prey.tribe_id)
        ):
            _drop_plan(band)
            continue
        joining = band.order.kind is OrderKind.MARCH_TO_BAND
        if joining or band.path:
            continue  # en route vers le point de ralliement
        mates = [
            b
            for b in state.bands.values()
            if b.tribe_id == band.tribe_id and b.intent_prey == prey.id
        ]
        here = [
            b
            for b in mates
            if b.position == band.position and not b.path and not b.retreating
        ]
        if band.id != min(b.id for b in here):
            continue  # un seul chef par groupe
        if is_shielded(state, prey):
            continue
        if wins(state, here, prey):
            for b in here:
                _drop_plan(b)
                set_march_to_band(state, b.id, prey.id)
            continue
        travelling = [b for b in mates if b not in here]
        if not travelling:
            # Tout le monde est la et ca ne suffit plus : on renonce.
            for b in here:
                _drop_plan(b)


def recheck_hunts(state: GameState) -> None:
    """Chaque semaine : une IA en route pour un raid qui le perdrait
    maintenant (renforts arrives, cible a l'abri) fait demi-tour."""
    for band in list(state.bands.values()):
        if band.order.kind is not OrderKind.MARCH_TO_BAND:
            continue
        tribe = state.tribes.get(band.tribe_id)
        if tribe is None or tribe.is_player:
            continue
        target = state.bands.get(band.order.target_band_id)
        if target is None or target.tribe_id == band.tribe_id:
            continue
        hunters = [
            b
            for b in state.bands.values()
            if b.tribe_id == band.tribe_id
            and b.order.kind is OrderKind.MARCH_TO_BAND
            and b.order.target_band_id == target.id
            and b.position == band.position
        ]
        if (
            is_shielded(state, target)
            or diplo.at_peace(state, band.tribe_id, target.tribe_id)
            or not wins(state, hunters, target, edge=1.0)
        ):
            band.order = stay_order()
            band.path = []


def unsafe_spots(state: GameState, band: Band, radius: int) -> list:
    """Positions des bandes etrangeres qu'il ne faut pas croiser : plus
    fortes que cette bande seule, et pas a l'abri (elles combattraient)."""
    mine = band_force(state, band)
    reach = radius + bonus_of(state, band.tribe_id).reinforce + 1
    spots = []
    for foe in bands_near(state, band.position, reach):
        if foe.tribe_id == band.tribe_id:
            continue
        if is_shielded(state, foe) or diplo.at_peace(state, foe.tribe_id, band.tribe_id):
            continue
        if side_force(state, foe) >= mine:
            spots.append(foe.position)
    return spots
