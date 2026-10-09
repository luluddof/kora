"""IA : quand attaquer, et avec qui.

Une IA n'attaque que si elle gagne avec une marge (AI_RAID_EDGE), forces
comptees la ou le combat aura lieu : elle + ses allies deja pres de la
cible, contre la cible + ses renforts (rayon de renfort de chaque tribu).

Trop faible seule, elle cherche une bande soeur a AI_CALL_RANGE cases
ou moins qui ferait basculer le combat :
  - tout pres (AI_MERGE_RANGE) : elle la rejoint et fusionne ;
  - plus loin : elle l'appelle, l'attend, puis elles partent ensemble
    de la meme case (meme chemin, arrivee la meme semaine).
Une troupe d'un suzerain peut aussi appeler l'OST : une troupe de ses
tributaires (a ost.OST_RANGE cases) vient se fondre dans la sienne.
LES VIVRES DE CAMPAGNE : une troupe IA ne part que si ses vivres tiennent
l'aller, le retour au village et SUPPLY_MARGIN semaines ; en route (une
proie qui fuit l'entraine plus loin), elle rentre des que ses vivres ne
tiennent plus que le retour et la marge (short_of_food).
Un raid en cours est annule si la cible s'est renforcee entre-temps.
"""

from __future__ import annotations

from src.kora import battle, chiefdom, chiefs, diplo, ost, villages
from src.kora.log import LogKind
from src.kora.path import MOVE_POINTS_PER_WEEK, astar, travel_weeks
from src.kora.battle import band_force, defense_force, side_force
from src.kora.bands import bands_near, bonus_of, campaign_weeks, costs_of, is_shielded, set_goto, set_march_to_band, weeks_between
from src.kora.gamestate import GameState, humans, note
from src.kora.types import Band, OrderKind, stay_order
from src.kora.vision import is_visible

AI_RAID_REST = 12
SUPPLY_MARGIN = 2
# Avec un motif (casus.py), on raide un voisin jusqu'a cette relation.
MOTIVE_RELATION = 40
AI_RAID_EDGE = 1.25
AI_CALL_RANGE = 10
AI_MERGE_RANGE = 3
AI_PLAN_WEEKS = 8
# Proie cherchee a portee de marche : 4 cases de plaine par semaine de raid.
RAID_REACH_PER_WEEK = MOVE_POINTS_PER_WEEK // 10


def helpers_at(state: GameState, bands: list[Band], spot) -> list[Band]:
    """Les bandes qui viendraient en renfort de `bands` si elles combattent
    sur `spot` : de leur tribu (qui obeissent), de leurs allies, de leur
    pays, deja a portee de renfort de ce point."""
    tribe_id = bands[0].tribe_id
    ids = {b.id for b in bands}
    reach = bonus_of(state, tribe_id).reinforce
    out = []
    for ally in bands_near(state, spot, reach):
        if ally.id in ids:
            continue
        if ally.tribe_id == tribe_id:
            if not chiefs.helps(state, ally):
                continue
        elif not (diplo.allied(state, ally.tribe_id, tribe_id) or ally.tribe_id in chiefdom.country(state, tribe_id)):
            continue
        out.append(ally)
    return out


def force_at(state: GameState, bands: list[Band], spot) -> float:
    """Force de `bands` si elles combattent sur `spot`, avec les bandes de
    leur tribu deja a portee de renfort de ce point."""
    force = sum(band_force(state, b) for b in bands)
    for ally in helpers_at(state, bands, spot):
        force += band_force(state, ally)
    return force


def odds_at(state: GameState, band: Band, prey: Band) -> tuple[float, str]:
    """Le rapport de force d'une attaque de `band` sur `prey`, compte comme
    l'IA le compte (wins) : la force la ou le combat aura lieu, avec les
    renforts et le moral, contre la defense de la proie (abri, renforts,
    moral). (rapport, mot)."""
    morale, _parts = battle.start_morale(state, band, attacker=True, h=prey.position)
    mine = force_at(state, [band], prey.position) * min(1.1, morale / battle.MORALE_BASE)
    ratio = mine / max(0.1, defense_force(state, prey, band.tribe_id))
    if ratio >= 2.0:
        word = "écrasant"
    elif ratio >= 1.3:
        word = "favorable"
    elif ratio >= 0.85:
        word = "incertain"
    else:
        word = "défavorable"
    return ratio, word


def wins(state: GameState, bands: list[Band], prey: Band, edge: float = AI_RAID_EDGE) -> bool:
    # Moral de l'attaquant (battle.py) : des affames ou des etrangers au
    # pays se battent moins bien ; une troupe, mieux.
    morale, _parts = battle.start_morale(state, bands[0], attacker=True, h=prey.position)
    # Prudente : un bon moral ne lui fait pas oublier sa marge.
    mine = force_at(state, bands, prey.position) * min(1.1, morale / battle.MORALE_BASE)
    return mine > edge * defense_force(state, prey, bands[0].tribe_id)


def fair_game(state: GameState, band: Band, prey: Band, hungry: bool) -> bool:
    """Un peuple qu'on peut raider : pas de pacte de paix (un accord
    commercial n'en est pas un) ; un voisin cordial, seulement quand on a
    faim ou qu'on a un motif (casus.py). Entre peuples qui ont la diplomatie,
    il faut pouvoir lui declarer la guerre (go_to_war le fera au depart du
    raid)."""
    a, b = band.tribe_id, prey.tribe_id
    if a == b or diplo.peace_pact(state, a, b):
        return False
    if diplo.may_start(state, a, b):
        return False
    if diplo.needs_declaration(state, a, b) and not diplo.declared_war(state, a, b) and diplo.evaluate(state, a, b, "guerre").blocked:
        return False
    if not hungry and diplo.relation(state, band.tribe_id, prey.tribe_id) >= (MOTIVE_RELATION if diplo.casus_of(state, a, b) else 15):
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


def short_of_food(state: GameState, band: Band, target=None) -> bool:
    """Une troupe dont les vivres ne tiennent pas (l'aller jusqu'a `target`,
    s'il y en a un) puis le retour au village et SUPPLY_MARGIN semaines.
    Un clan, lui, vit du pays : jamais."""
    if band.kind != "armee":
        return False
    need = SUPPLY_MARGIN
    if target is not None:
        need += weeks_between(state, band.position, target) + villages.weeks_home(state, band, target)
    else:
        need += villages.weeks_home(state, band)
    return campaign_weeks(state, band) < need


def _helper(state: GameState, band: Band, prey: Band) -> Band | None:
    best, best_d = None, None
    # L'ost : les troupes des tributaires viennent a la troupe du suzerain.
    vassals = set(chiefdom.descendants(state, band.tribe_id)) if band.kind == "armee" else set()
    for ally in state.bands.values():
        if ally.id == band.id or (ally.tribe_id != band.tribe_id and ally.tribe_id not in vassals):
            continue
        if ally.tribe_id != band.tribe_id and (ally.ost or ally.path):
            continue
        # Une troupe s'allie a une troupe, un clan a un clan ; un village ne
        # bouge pas.
        if ally.village or (ally.kind == "armee") != (band.kind == "armee"):
            continue
        if not _free(state, ally) or ally.intent_prey not in (0, prey.id):
            continue
        d = state.world.distance(band.position, ally.position)
        if d > (AI_CALL_RANGE if ally.tribe_id == band.tribe_id else ost.OST_RANGE):
            continue
        if not wins(state, [band, ally], prey):
            continue
        if best_d is None or d < best_d:
            best, best_d = ally, d
    return best


def plan_raid(state: GameState, band: Band, max_weeks: int, hungry: bool = True):
    """("attack", proie) | ("merge", allie, proie) | ("call", allie, proie)
    | ("ost", troupe d'un tributaire, proie) | None."""
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
        if short_of_food(state, band, prey.position):
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
        if ally.tribe_id != band.tribe_id:
            return ("ost", ally, prey)
        near = state.world.distance(band.position, ally.position) <= AI_MERGE_RANGE
        return ("merge" if near else "call", ally, prey)
    return None


def go_to_war(state: GameState, band: Band, prey: Band) -> None:
    """Le raid part : entre peuples qui ont la diplomatie, l'IA declare
    d'abord la guerre (diplo.declare_war)."""
    a, b = band.tribe_id, prey.tribe_id
    if diplo.needs_declaration(state, a, b) and not diplo.declared_war(state, a, b):
        # Un chef qui a des villages fait la guerre pour soumettre (sauf un
        # affame : il veut du grain).
        wants = chiefdom.has_chiefdom(state, a) and chiefdom.has_chiefdom(state, b) and chiefdom.ai_choice(state, a, b) == "soumettre"
        diplo.declare_war(state, a, b, b if wants else 0)


def start_plan(state: GameState, band: Band, plan) -> None:
    if plan[0] == "attack":
        go_to_war(state, band, plan[1])
        set_march_to_band(state, band.id, plan[1].id)
        return
    kind, ally, prey = plan
    until = state.tick_count + AI_PLAN_WEEKS
    if kind == "ost":
        # Le suzerain attend sur place ; l'ost vient a lui (ost.weekly).
        band.intent_prey = prey.id
        band.intent_until = until + AI_PLAN_WEEKS
        band.order = stay_order()
        band.path = []
        ost.call(state, band.id)
        return
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
    tribe = state.tribes.get(band.tribe_id)
    name = tribe.name if tribe else "ennemis"
    for me in humans(state):
        if me != band.tribe_id and (is_visible(state, band.position, me) or is_visible(state, ally.position, me)):
            note(state, LogKind.COMBAT, f"Des {name} se regroupent.", where=band.position, to=me)


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
            or not fair_game(state, band, prey, hungry=True)
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
            go_to_war(state, band, prey)
            for b in here:
                _drop_plan(b)
                set_march_to_band(state, b.id, prey.id)
            continue
        travelling = [b for b in mates if b not in here]
        # L'ost en route compte : on l'attend.
        travelling += [b for b in state.bands.values() if b.ost and b.ost in {h.id for h in here}]
        if not travelling:
            # Tout le monde est la et ca ne suffit plus : on renonce.
            for b in here:
                _drop_plan(b)


def recheck_hunts(state: GameState) -> None:
    """Chaque semaine : une IA en route pour un raid qui le perdrait
    maintenant (renforts arrives, cible a l'abri) fait demi-tour ; une
    troupe dont les vivres ne tiennent plus l'aller et le retour rentre."""
    for band in list(state.bands.values()):
        if band.id not in state.bands or band.order.kind is not OrderKind.MARCH_TO_BAND:
            continue
        tribe = state.tribes.get(band.tribe_id)
        if tribe is None or tribe.is_player:
            continue
        target = state.bands.get(band.order.target_band_id)
        if target is None or target.tribe_id == band.tribe_id:
            continue
        if short_of_food(state, band, target.position) and not battle.in_battle(state, band):
            # La proie fuit et l'entraine trop loin : on rentre avant la faim.
            band.order = stay_order()
            band.path = []
            villages.dissolve(state, band.id)
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
            or diplo.may_start(state, band.tribe_id, target.tribe_id)
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


# --- ce que l'IA de guerre ajoute aux evenements (events.vocabulary) ----------------


def _ev_provoke(state, inst, tribe, band) -> None:
    """Le peuple offense prepare un raid s'il peut le gagner."""
    if band is None or inst.other not in state.tribes:
        return
    theirs = [b for b in state.bands.values() if b.tribe_id == inst.other and b.population > 0]
    theirs.sort(key=lambda b: (state.world.distance(b.position, band.position), b.id))
    for foe in theirs[:2]:
        plan = plan_raid(state, foe, 6)
        if plan is not None:
            start_plan(state, foe, plan)
            return


EVENT_EFFECTS = {"provoke": _ev_provoke}
EVENT_TEXTS = {"provoke": lambda a: "ils pourraient venir se venger"}
