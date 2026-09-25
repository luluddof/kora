from src.kora.ai_war import (
    AI_RAID_EDGE,
    advance_plans,
    fair_game,
    plan_raid,
    recheck_hunts,
    start_plan,
    unsafe_spots,
)
from src.kora import chiefs, diplo, sites
from src.kora.peoples import culture_of
from src.kora.sim import (
    GameState,
    band_force,
    band_quality,
    bands_near,
    bonus_of,
    build_band_grid,
    can_split,
    defense_force,
    forage_hexes,
    is_shielded,
    set_goto,
    split_band,
)
from src.kora.types import Band, Terrain, stay_order
from src.kora.world import MOVE_COST, SEASONS_BY_CODE, food_production

AI_SPLIT_POP = 30
AI_REFINE = 16
AI_SPLIT_AWAY = 6
# Rassasiee, une IA prestigieuse ne raide qu'une decision sur trois ou quatre.
AI_RAID_WHIM = 0.3
AI_CONTENT = 1.15


def _herd(band: Band, state: GameState) -> bool:
    tribe = state.tribes.get(band.tribe_id)
    return bool(tribe and tribe.troupeau)


def _stock_weeks(band: Band) -> float:
    return band.stock / max(1, band.population)


def _forage_total(state: GameState, band: Band) -> float:
    herd = _herd(band, state)
    know = bonus_of(state, band.tribe_id)
    return sum(
        food_production(state.world, h, state.world.hex_season(h), herd=herd, bonus=know)
        for h in forage_hexes(state, band)
    )


def _local_yield(state: GameState, band: Band) -> float:
    hexes = forage_hexes(state, band)
    if not hexes:
        return 0.0
    herd = _herd(band, state)
    know = bonus_of(state, band.tribe_id)
    return sum(
        food_production(state.world, h, state.world.hex_season(h), herd=herd, bonus=know)
        for h in hexes
    ) / len(hexes)


def _pick_hex(
    state: GameState,
    band: Band,
    radius: int,
    prefer=None,
    avoid=None,
    min_dist: int = 0,
):
    avoid = avoid or set()
    tribe = state.tribes.get(band.tribe_id)
    water_ok = bool(tribe and tribe.cabotage)
    herd = _herd(band, state)
    know = bonus_of(state, band.tribe_id)
    world = state.world
    terrains = world._terrains
    seasons = world._hex_season
    scored: list[tuple[float, object]] = []
    around, dists = world.hexes_and_distances(band.position, radius)
    # Ne pas finir sa marche a cote d'une bande plus forte : ce serait un
    # combat perdu d'avance (accrochage).
    danger = unsafe_spots(state, band, radius)
    foreign_villages = [
        s.hex
        for s in state.sites.values()
        if s.kind == "village" and s.tribe_id != band.tribe_id and world.distance(s.hex, band.position) <= radius + FOREIGN_VILLAGE_ROOM
    ]
    # Grand rayon : un hex sur deux (sur trois au-dela de 15) suffit,
    # l'affinage regarde les voisins.
    stride = 3 if radius > 15 else 2 if radius > 12 else 1
    for i in range(0, len(around), stride):
        h = around[i]
        if h in avoid or h == band.position:
            continue
        row = h.r
        col = h.q + (row - (row & 1)) // 2
        terrain = terrains[row][col]
        if MOVE_COST.get(terrain) is None and not (
            water_ok and world.inshore_at(col, row)
        ):
            continue
        if min_dist and dists[i] < min_dist:
            continue
        if danger and any(world.distance(h, spot) <= 2 for spot in danger):
            continue
        if foreign_villages and any(world.distance(h, v) < FOREIGN_VILLAGE_ROOM for v in foreign_villages):
            # Au pied du village d'un autre peuple : ses champs, pas les notres.
            continue
        season = SEASONS_BY_CODE[seasons[row][col]]
        if prefer is not None and terrain not in prefer:
            val = food_production(world, h, season, herd=herd, bonus=know) - 0.01
        else:
            val = food_production(world, h, season, herd=herd, bonus=know)
            if prefer is not None and terrain in prefer:
                val += 0.5
        scored.append((val, h))
    if not scored:
        return None
    scored.sort(key=lambda it: it[0], reverse=True)
    # Affiner les meilleurs candidats avec la vraie collecte (rayon 2),
    # moins la part prise par les bandes deja proches.
    refined: list[tuple[float, object]] = []
    for val, h in scored[:AI_REFINE]:
        liking = val - food_production(
            state.world, h, state.world.hex_season(h), herd=herd, bonus=know
        )
        refined.append((_site_food(state, band, h, herd, know) + liking * 4, h))
    refined.sort(key=lambda it: it[0], reverse=True)
    best = refined[0][0]
    pool = [h for val, h in refined[:6] if val >= best - 2.0]
    return state.rng.choice(pool)


def _site_food(state: GameState, band: Band, h, herd: bool, know=None) -> float:
    food = sum(
        food_production(state.world, x, state.world.hex_season(x), herd=herd, bonus=know)
        for x in state.world.hexes_in_radius(h, 2)
    )
    for other in bands_near(state, h, 4):
        if other.id == band.id:
            continue
        food -= other.population * 0.5
    return food


def _should_split(state: GameState, band: Band, weeks: float) -> bool:
    # Meme regle que le joueur (can_split), plus de la prudence :
    # bande grande, pas affamee, et pas juste avant l'hiver.
    if band.population < AI_SPLIT_POP or weeks < 2:
        return False
    if _settler(state, band):
        # Un clan parti fonder son peuple ne s'emiette pas avant d'avoir son
        # village (il faut 20 personnes pour le fonder).
        return False
    if sites.of_tribe(state, band.tribe_id, "village"):
        # Un peuple fixe : ses clans nomades ne se divisent plus ; ils
        # s'eloignent et fondent leur peuple (chiefs, independance).
        return False
    if state.clock.weeks_until_winter() < 10:
        return False
    return can_split(state, band.id)


def _camp_care(state: GameState, band: Band, weeks: float) -> bool:
    """Campements de l'IA : en poser un a l'automne la ou l'on mange bien,
    y revenir avant l'hiver, y laisser le surplus, y puiser en disette.
    Rend True si la bande a recu un ordre de marche."""
    know = bonus_of(state, band.tribe_id)
    if know.camps <= 0:
        return False
    here = sites.camp_at(state, band)
    # Un campement se leve quand on part : l'IA n'y laisse plus ses vivres,
    # elle y reprend ce qui reste.
    if here is not None and weeks < 3 and here.store >= 1:
        sites.withdraw(state, band.id)
    autumn = state.clock.weeks_until_winter() <= 10 and state.clock.week < 40
    mine = sites.of_tribe(state, band.tribe_id, "camp")
    if (
        here is None
        and autumn
        and len(mine) < know.camps
        and _forage_total(state, band) >= band.population * 0.9
        and all(state.world.distance(s.hex, band.position) > 12 for s in mine)
        and not sites.camp_block(state, band.id)
    ):
        sites.make_camp(state, band.id)
        return False
    if here is None and autumn and state.clock.weeks_until_winter() <= 6 and weeks < 8:
        near = [s for s in mine if state.world.distance(s.hex, band.position) <= 25]
        if near:
            goal = min(near, key=lambda s: state.world.distance(s.hex, band.position))
            set_goto(state, band.id, goal.hex, max_nodes=400, max_cost=800)
            return bool(band.path)
    return False


# Ordre des chantiers d'un village IA.
AI_BUILD_ORDER = ("palissade", "grenier", "puits", "guerriers", "tour", "autel", "maison_longue", "enclos", "atelier", "place", "pierre")
AI_ARMY_WHIM = 0.15
AI_ARMY_POP = 60
# Un voisin menacant : une bande sans pacte au moins aussi forte que la
# moitie des combattants du village (sans ses murs).
AI_THREAT = 0.5
AI_THREAT_RANGE = 8
AI_ARMY_REACH = 16
AI_BUILD_RESERVE = 12


def _threat(state: GameState, band: Band, radius: int):
    """Bande etrangere sans pacte la plus forte a `radius` cases."""
    worst, worst_f = None, 0.0
    for foe in bands_near(state, band.position, radius):
        if foe.tribe_id == band.tribe_id or diplo.at_peace(state, foe.tribe_id, band.tribe_id):
            continue
        if is_shielded(state, foe):
            continue
        f = band_force(state, foe)
        if f > worst_f:
            worst, worst_f = foe, f
    return worst, worst_f


def _ai_levy_type(state: GameState, band: Band, site) -> str:
    """Premiere compagnie : la melee ; la suivante : des tireurs s'il y en a,
    sinon une garde."""
    from src.kora import units, villages

    tribe = state.tribes[band.tribe_id]
    if villages.companies_of(state, site) == 0:
        return units.best(tribe, "melee").id
    for role in ("tir", "garde", "melee"):
        u = units.best(tribe, role)
        if u is not None:
            return u.id
    return "guerriers"


# Un peuple qui sait semer et n'a pas encore de village (souvent un clan
# emancipe) s'installe des 20 personnes, sur une terre correcte.
AI_SETTLE_POP = 20
# Pas de village IA a moins de 10 cases d'un autre village ; une bande IA ne
# campe pas a moins de 4 cases du village d'un autre peuple.
VILLAGE_SPACING = 10
FOREIGN_VILLAGE_ROOM = 4
NEW_LAND_RADIUS = 30
# Pays plein : on cherche plus loin, puis on accepte d'etre plus pres des
# autres (jamais au pied d'un village) ; un peuple sans village depuis
# SETTLE_PATIENCE_YEARS ans se contente de CROWDED_SPACING.
NEW_LAND_FAR = 50
# Colons d'un village : une terre a fonder a COLONY_RADIUS cases au plus.
COLONY_RADIUS = 24
CROWDED_SPACING = 6
SETTLE_PATIENCE_YEARS = 1


def _villages_near(state: GameState, h, radius: int, other_than: int = 0) -> bool:
    for site in state.sites.values():
        if site.kind == "village" and site.tribe_id != other_than and state.world.distance(site.hex, h) < radius:
            return True
    return False


def _any_village_near(state: GameState, h, radius: int) -> bool:
    return any(site.kind == "village" and state.world.distance(site.hex, h) < radius for site in state.sites.values())


def find_new_land(state: GameState, band: Band):
    """Une terre ou fonder un village, loin de tout village (pour un clan qui
    part). Pays plein : on cherche plus loin, puis on se contente de moins
    de place (jamais au pied d'un village : CROWDED_SPACING)."""
    for radius, step, spacing in (
        (NEW_LAND_RADIUS, 3, VILLAGE_SPACING + 2),
        (NEW_LAND_FAR, 6, VILLAGE_SPACING),
        (NEW_LAND_RADIUS, 3, CROWDED_SPACING),
    ):
        spot = _new_land(state, band, radius, spacing, step)
        if spot is not None:
            return spot
    return None


FOUND_GOOD = 0.6
FOUND_GOOD_HEXES = 2


def _good_count(state: GameState, tribe_id: int, h) -> int:
    """Bonnes terres (fertilite 0,6) a portee d'un village fonde ici. Ne
    depend que de la carte et du defrichage : memorise."""
    from src.kora import villages

    world = state.world
    clearing = bool(bonus_of(state, tribe_id).clearing)
    memo = getattr(world, "_lands", None)
    if memo is None:
        memo = world._lands = {}
    key = ("good", world._index(h), clearing)
    hit = memo.get(key)
    if hit is None:
        if MOVE_COST.get(world.terrain(h)) is None or villages.fertility(state, tribe_id, h) <= FOUND_GOOD:
            # On fonde sur une bonne terre : le centre d'abord (le plus souvent,
            # un seul calcul suffit a ecarter la case).
            hit = 0
        else:
            hit = sum(1 for x in world.hexes_in_radius(h, villages.FIELD_RADIUS) if villages.fertility(state, tribe_id, x) > FOUND_GOOD)
        memo[key] = hit
    return hit


def _village_hexes(state: GameState) -> list:
    return [site.hex for site in state.sites.values() if site.kind == "village"]


def good_land(state: GameState, tribe_id: int, h, spacing: int, homes: list | None = None) -> int:
    """Nombre de bonnes terres (fertilite 0,6) a portee d'un village fonde
    ici, 0 si l'on ne peut pas s'y fixer (village trop pres, trop peu de
    bonnes terres) : les memes regles que la fondation."""
    good = _good_count(state, tribe_id, h)
    if good < FOUND_GOOD_HEXES:
        return 0
    world = state.world
    homes = _village_hexes(state) if homes is None else homes
    if any(world.distance(v, h) < spacing for v in homes):
        return 0
    return good


def _new_land(state: GameState, band: Band, radius: int, spacing: int, step: int = 3):
    world = state.world
    homes = _village_hexes(state)
    best, best_v = None, -1.0
    for h in world.hexes_in_radius(band.position, radius)[::step]:
        good = good_land(state, band.tribe_id, h, spacing, homes)
        if not good:
            continue
        v = good - 0.05 * world.distance(band.position, h)
        if v > best_v:
            best, best_v = h, v
    return best


def _settler(state: GameState, band: Band) -> bool:
    """Un peuple ne d'un autre (clan emancipe, secession) qui sait semer et
    n'a pas encore de village : il n'a qu'une idee, fonder le sien."""
    tribe = state.tribes.get(band.tribe_id)
    if tribe is None or tribe.is_player or not tribe.origin or band.village or band.kind == "armee":
        return False
    if bonus_of(state, band.tribe_id).villages <= 0:
        return False
    return not sites.of_tribe(state, band.tribe_id, "village")


def settle_spacing(state: GameState, tribe) -> int:
    """Place qu'un peuple sans village demande : large la premiere annee,
    puis il se contente de CROWDED_SPACING."""
    return VILLAGE_SPACING if state.clock.year - tribe.founded < SETTLE_PATIENCE_YEARS else CROWDED_SPACING


def _go_settle(state: GameState, band: Band, weeks: float) -> bool:
    """Le clan parti va a sa terre, y campe et y attend la belle saison
    pour fonder son village (_try_found_village). Affame, il va d'abord
    manger. Rend True s'il suit ce plan."""
    if not _settler(state, band) or weeks < 1.5:
        return False
    if band.path:
        return True
    tribe = state.tribes[band.tribe_id]
    if good_land(state, band.tribe_id, band.position, settle_spacing(state, tribe)):
        if sites.own_site_at(state, band) is None and not sites.camp_block(state, band.id):
            sites.make_camp(state, band.id)
        return True
    head_for_new_land(state, band)
    return bool(band.path)


def head_for_new_land(state: GameState, band: Band) -> None:
    spot = find_new_land(state, band)
    if spot is not None:
        set_goto(state, band.id, spot, max_nodes=1200, max_cost=3000)


def _settle_ai(state: GameState, band: Band) -> bool:
    """Un peuple qui sait semer et n'a pas encore de village (un clan parti,
    un petit peuple) : il campe sur une bonne terre pour s'y fixer."""
    from src.kora import villages

    know = bonus_of(state, band.tribe_id)
    if know.villages <= 0 or know.camps <= 0 or band.population < AI_SETTLE_POP:
        return False
    if sites.of_tribe(state, band.tribe_id, "village"):
        return False
    if state.world.hex_season(band.position).value not in ("printemps", "ete"):
        return False
    if sites.own_site_at(state, band) is not None:
        return False
    tribe = state.tribes[band.tribe_id]
    # Un peuple ne d'un autre, sans village depuis un an : moins exigeant.
    spacing = settle_spacing(state, tribe) if tribe.origin else VILLAGE_SPACING
    if band.path or _any_village_near(state, band.position, spacing):
        # En route vers sa terre, ou trop pres d'un village : pas ici.
        return False
    good = sum(1 for h in state.world.hexes_in_radius(band.position, villages.FIELD_RADIUS) if villages.fertility(state, band.tribe_id, h) > 0.6)
    if good < 2 or sites.camp_block(state, band.id):
        return False
    return sites.make_camp(state, band.id) is not None


def _village_ai(state: GameState, band: Band, weeks: float) -> None:
    """Un village IA : batit (palissade d'abord), leve une troupe s'il est
    menace ou s'il voit une proie, envoie des colons quand il deborde."""
    from src.kora import villages

    site = villages.site_of(state, band)
    if site is not None:
        from src.kora import goods

        goods.ai_crafts(state, site, band, weeks)
    warm = state.world.hex_season(band.position).value in ("printemps", "ete")
    if site is not None and warm and villages.works(site) is None:
        # On batit au printemps et en ete, sur le surplus : pas avec les
        # vivres de l'hiver.
        for bid in AI_BUILD_ORDER:
            if weeks < AI_BUILD_RESERVE + villages.BUILDINGS[bid].cost_weeks:
                continue
            if not villages.build_block(state, band.id, bid):
                villages.build(state, band.id, bid)
                break
    if site is not None and not villages.army_block(state, band.id):
        foe, foe_f = _threat(state, band, AI_THREAT_RANGE)
        raise_it = foe is not None and foe_f >= AI_THREAT * band_force(state, band)
        if not raise_it and weeks >= 8 and band.population >= AI_ARMY_POP and state.rng.random() < AI_ARMY_WHIM:
            tribe = state.tribes[band.tribe_id]
            culture = culture_of(tribe)
            if tribe.prestige >= culture.raid_prestige - 10:
                est = villages.levy_size(band, villages.LEVY_SHARE["troupe"]) * band_quality(state, band)
                for prey in bands_near(state, band.position, AI_ARMY_REACH):
                    if fair_game(state, band, prey, hungry=False) and not is_shielded(state, prey):
                        if est > AI_RAID_EDGE * defense_force(state, prey):
                            raise_it = True
                            break
        if raise_it:
            villages.raise_army(state, band.id, type_id=_ai_levy_type(state, band, site))
    season = state.world.hex_season(band.position)
    if band.population >= 90 and weeks >= 8 and season.value in ("printemps", "ete") and can_split(state, band.id):
        # Des colons, seulement pour fonder un autre village du peuple (s'il
        # en a le droit), sur une terre ou ils le pourront : pas des clans
        # qui erreraient.
        allowed = bonus_of(state, band.tribe_id).villages
        if len(sites.of_tribe(state, band.tribe_id, "village")) < allowed:
            homes = _village_hexes(state)
            spot = None
            best = -1.0
            for h in state.world.hexes_in_radius(band.position, COLONY_RADIUS)[::2]:
                if state.world.distance(h, band.position) < VILLAGE_SPACING:
                    continue
                good = good_land(state, band.tribe_id, h, VILLAGE_SPACING, homes)
                v = good - 0.1 * state.world.distance(h, band.position)
                if good and v > best:
                    spot, best = h, v
            if spot is not None:
                nid = split_band(state, band.id)
                if nid is not None:
                    set_goto(state, nid, spot, max_nodes=800, max_cost=1500)


def _try_found_village(state: GameState, band: Band) -> bool:
    """Une bande IA sur son campement, au printemps ou en ete, sur une
    bonne terre : elle s'installe."""
    from src.kora import villages

    first = not sites.of_tribe(state, band.tribe_id, "village")
    if bonus_of(state, band.tribe_id).villages <= 0 or band.population < (AI_SETTLE_POP if first else 25):
        return False
    if state.world.hex_season(band.position).value not in ("printemps", "ete"):
        return False
    if villages.found_block(state, band.id):
        return False
    tribe = state.tribes[band.tribe_id]
    # Un peuple ne d'un autre, toujours sans village : moins exigeant passe
    # la premiere annee (le pays se remplit de villages).
    spacing = settle_spacing(state, tribe) if first and tribe.origin else VILLAGE_SPACING
    if _any_village_near(state, band.position, spacing):
        return False
    here = sites.own_site_at(state, band)
    # Memes regles pour tous les villages (colons compris) : ils visent une
    # terre qui les remplit (good_land).
    good = sum(1 for h in state.world.hexes_in_radius(here.hex, villages.FIELD_RADIUS) if villages.fertility(state, band.tribe_id, h) > FOUND_GOOD)
    if good < FOUND_GOOD_HEXES:
        return False
    return villages.found(state, band.id, oath=villages.ai_oath(state, band.tribe_id)) is not None


def _army_ai(state: GameState, band: Band, weeks: float) -> None:
    """Une troupe IA : defendre son village, raider une proie qu'elle bat,
    sinon rentrer et redevenir villageois."""
    from src.kora import villages

    if band.path or band.homebound:
        return
    home = villages.home_of(state, band)
    if home is None:
        return
    village = villages.band_of(state, home)
    at_home = state.world.distance(home.hex, band.position) <= villages.ARMY_HOME
    foe, foe_f = _threat(state, village, AI_THREAT_RANGE) if village is not None else (None, 0.0)
    if foe is not None and not at_home and state.world.distance(home.hex, band.position) > AI_THREAT_RANGE:
        set_goto(state, band.id, home.hex, max_nodes=500, max_cost=1000)
        return
    culture = culture_of(state.tribes[band.tribe_id])
    plan = plan_raid(state, band, max(6, culture.raid_weeks), hungry=weeks < 3)
    if plan is not None and plan[0] == "attack":
        start_plan(state, band, plan)
        return
    if at_home and foe is not None:
        return
    # Rien a faire : la troupe est dissoute, ses hommes rentrent (a pied).
    villages.dissolve(state, band.id)


AI_CACHE_SEEK = 8


def _seek_cache(state: GameState, band: Band, weeks: float) -> bool:
    """Une cache d'un peuple sans pacte, a portee : on va la vider."""
    if weeks >= 16:
        return False
    best, best_d = None, AI_CACHE_SEEK + 1
    for site in state.sites.values():
        if site.kind != "cache" or site.tribe_id == band.tribe_id or site.store < 20:
            continue
        if diplo.at_peace(state, site.tribe_id, band.tribe_id):
            continue
        d = state.world.distance(site.hex, band.position)
        if d < best_d or (d == best_d and best is not None and site.id < best.id):
            best, best_d = site, d
    if best is None or best.hex == band.position:
        return False
    set_goto(state, band.id, best.hex, max_nodes=400, max_cost=800)
    return bool(band.path)


def _regroup(state: GameState, band: Band, weeks: float) -> bool:
    """Un clan qui se detache (mais obeit encore) revient vers le chef."""
    if weeks < 3 or chiefs.is_chief_band(state, band) or not chiefs.obeys(state, band):
        return False
    if band.loyalty >= 55:
        return False
    heart = chiefs.chief_band(state, band.tribe_id)
    if heart is None or state.world.distance(heart.position, band.position) <= 6:
        return False
    set_goto(state, band.id, heart.position, max_nodes=500, max_cost=900)
    return bool(band.path)


def decide_ai(state: GameState) -> None:
    # Pendant les decisions, les bandes ne bougent pas : grille de voisinage
    # et forces calculees une fois (voir sim.bands_near, sim.side_force).
    state.band_grid = build_band_grid(state)
    state.force_memo = {}
    try:
        with diplo.frozen_relations(state):
            _decide(state)
    finally:
        state.band_grid = None
        state.force_memo = None


def _decide(state: GameState) -> None:
    # Chaque semaine, pour toutes les bandes : raids en cours et ralliements.
    recheck_hunts(state)
    advance_plans(state)
    for band in list(state.bands.values()):
        tribe = state.tribes.get(band.tribe_id)
        if tribe is None or band.population <= 0:
            continue
        # Les bandes du joueur lui obeissent, sauf un clan indocile qui
        # vit alors sa vie (sans raider).
        if tribe.is_player and chiefs.obeys(state, band):
            continue
        if band.retreating or band.intent_prey:
            continue
        weeks = _stock_weeks(band)
        # Chaque bande decide une semaine sur quatre, en decale selon son id :
        # la charge est etalee au lieu d'un pic toutes les 4 semaines.
        if (state.tick_count + band.id) % 4 != 0:
            continue
        culture = culture_of(tribe)
        prefer = culture.prefer
        if band.village:
            if not tribe.is_player:
                _village_ai(state, band, weeks)
            continue
        if band.kind == "armee":
            if not tribe.is_player:
                _army_ai(state, band, weeks)
            continue
        if not tribe.is_player:
            if _try_found_village(state, band):
                continue
            if _settle_ai(state, band):
                continue
            if _go_settle(state, band, weeks):
                continue
            if _camp_care(state, band, weeks):
                continue
            if _seek_cache(state, band, weeks):
                continue
            if _regroup(state, band, weeks):
                continue
        if not tribe.is_player and _should_split(state, band, weeks):
            nid = split_band(state, band.id)
            if nid is not None:
                child = state.bands[nid]
                spot = _pick_hex(state, child, 16, prefer, min_dist=AI_SPLIT_AWAY)
                if spot is not None:
                    set_goto(state, nid, spot, max_nodes=400, max_cost=800)
                weeks = _stock_weeks(band)
        if band.path and weeks >= 2:
            continue
        r_weeks = culture.raid_weeks
        # Un petit peuple ne raide par audace que s'il est tres prestigieux.
        p_thr = culture.raid_prestige + (15 if tribe.minor else 0)
        recent = set(getattr(band, "recent_goals", [])[-8:])
        if weeks < 2:
            if _forage_total(state, band) >= band.population:
                band.path = []
                band.order = stay_order()
                continue
            target = _pick_hex(state, band, 24, prefer)
            if target is not None:
                set_goto(state, band.id, target, max_nodes=400, max_cost=800)
                if band.order.target_hex is not None:
                    band.recent_goals.append(band.order.target_hex)
                    band.recent_goals = band.recent_goals[-10:]
                continue
        if state.clock.weeks_until_winter() <= 4 and weeks < 6:
            valley = _pick_hex(
                state, band, 24, {Terrain.VALLEE}, avoid=recent, min_dist=2
            )
            if valley is not None:
                set_goto(state, band.id, valley, max_nodes=400, max_cost=800)
                if band.order.target_hex is not None:
                    band.recent_goals.append(band.order.target_hex)
                    band.recent_goals = band.recent_goals[-10:]
                continue
        skip_raid = False
        if culture.shy and _local_yield(state, band) >= 0.8 and weeks >= 2:
            skip_raid = True
        if tribe.is_player:
            skip_raid = True
        hungry = weeks < 4
        bold = tribe.prestige >= p_thr and state.rng.random() < AI_RAID_WHIM
        if not skip_raid and (hungry or bold):
            plan = plan_raid(state, band, r_weeks, hungry=hungry)
            if plan is not None:
                start_plan(state, band, plan)
                continue
        if weeks >= 4 and _forage_total(state, band) >= band.population * AI_CONTENT:
            # Bien nourrie et bien placee : on campe au lieu d'errer.
            if not band.path:
                band.order = stay_order()
            continue
        roam_pref = culture.roam if culture.roam is not None else prefer
        roam = _pick_hex(
            state, band, 14, roam_pref, avoid=recent, min_dist=4
        )
        if roam is not None:
            set_goto(state, band.id, roam, max_nodes=400, max_cost=800)
            if band.order.target_hex is not None:
                band.recent_goals.append(band.order.target_hex)
                band.recent_goals = band.recent_goals[-10:]
            continue
        if band.path:
            continue
        band.path = []
        band.order = stay_order()
