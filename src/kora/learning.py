"""COMMENT UN PEUPLE APPREND : les conditions d'un savoir, son etat, le rythme.

tech.py porte l'arbre (les savoirs, leurs effets, les bonus) ; ici, ce qui
le fait avancer : ce qu'un peuple a vecu (update_practice : terrains,
ressources, hivers), ce qu'il remplit (cond_progress), l'etat de chaque
savoir (status, available), le rythme (learn_rate : population a l'ecoute,
chef, voisins qui savent), et la semaine (update_learning).
Etage des systemes (tools/dependances.py). N'importe pas pygame.
"""

from __future__ import annotations
from src.kora.gamestate import note
from src.kora.log import LogKind
from src.kora.peoples import children_alive, culture_of
from src.kora.tech import (
    Cond,
    LEARN_POP,
    PIROGUE_COAST_WEEKS,
    SEE_RADIUS,
    TECHS,
    TROUPEAU_STEPPE_WEEKS,
    Tech,
    _TICK_MEMO,
    _plural,
    bonuses,
    effect_lines,
    grant,
    missing_prereqs,
    pan_of,
    summary,
)
from src.kora.types import Season, Terrain
from src.kora.world import is_inshore
from src.kora import chiefdom, chiefs, diplo, draws, sites, turning
from src.kora.villages import land_profile


def _pop(state, tribe_id: int) -> int:
    return sum(b.population for b in state.bands.values() if b.tribe_id == tribe_id and b.population > 0)


def _lineage_all(state) -> dict:
    """Gens de chaque peuple et de tous les peuples nes de lui."""
    pop: dict = {}
    for b in state.bands.values():
        if b.population > 0:
            pop[b.tribe_id] = pop.get(b.tribe_id, 0) + b.population
    children: dict = {}
    for t in state.tribes.values():
        if t.origin and t.origin != t.id:
            children.setdefault(t.origin, []).append(t.id)
    out = {}
    for tid in state.tribes:
        total, seen, todo = 0, {tid}, [tid]
        while todo:
            cur = todo.pop()
            total += pop.get(cur, 0)
            for kid in children.get(cur, ()):
                if kid not in seen:
                    seen.add(kid)
                    todo.append(kid)
        out[tid] = total
    return out


def _lineage_pop(state, tribe_id: int) -> int:
    memo = _TICK_MEMO
    if memo is None:
        return _lineage_all(state).get(tribe_id, 0)
    pops = memo.get("lineage")
    if pops is None:
        pops = memo["lineage"] = _lineage_all(state)
    return pops.get(tribe_id, 0)


def _bands(state, tribe_id: int) -> int:
    return sum(1 for b in state.bands.values() if b.tribe_id == tribe_id and b.population > 0)


def cond_progress(state, tribe, cond: Cond, eased: bool = False) -> tuple[int, int, str]:
    """(valeur, besoin, libelle) d'une condition pour cette tribu.
    eased : savoir vu chez un voisin, les semaines vecues comptent double."""
    kind = cond.kind
    if kind == "pop":
        # Les peuples nes du votre (clans partis fonder le leur) comptent :
        # un peuple fixe, reduit a ses villages, n'est pas sans savoirs.
        own = _pop(state, tribe.id)
        have = max(own, _lineage_pop(state, tribe.id))
        label = f"Peuple {cond.need}" + (" (avec les peuples nés du votre)" if have > own else "")
        return have, cond.need, label
    if kind in ("weeks", "res"):
        need = -(-cond.need // 2) if eased else cond.need
        prefix = "res:" if kind == "res" else ""
        have = sum(tribe.practice.get(prefix + _key(t), 0) for t in cond.terrains)
        if cond.label == "hiver local":
            return have, need, f"{need} sem. d'hiver local"
        if kind == "res":
            return have, need, f"{need} sem. {cond.label}"
        return have, need, f"{need} sem. en {cond.label}"
    if kind == "winters":
        return tribe.practice.get("hivers", 0), cond.need, f"{_plural(cond.need, 'hiver')} traversé{'s' if cond.need > 1 else ''}"
    if kind == "prestige":
        return tribe.prestige, cond.need, f"Prestige {cond.need}"
    if kind == "bands":
        # Les bandes qu'on a eues comptent : un peuple fixe n'en forme plus,
        # et ses clans partis etaient les siens.
        have = max(tribe.practice.get("bandes", 0), _bands(state, tribe.id) + children_alive(state, tribe.id))
        return have, cond.need, f"Avoir eu {_plural(cond.need, 'bande')}"
    if kind == "seen":
        seen = tribe.shore_seen if cond.label == "rivage" else tribe.steppe_seen
        return int(seen), 1, f"{cond.label.capitalize()} en vue"
    if kind == "flag":
        flags = getattr(tribe, "flags", {}) or {}
        have = 1 if cond.label in flags else 0
        return have, 1, _FLAG_LABELS.get(cond.label, cond.label)
    if kind == "camp_years":
        return sites.oldest_camp_years(state, tribe.id), cond.need, f"Un campement tenu {cond.need} ans"
    if kind in ("contacts", "friends", "allies"):
        have = {
            "contacts": diplo.contact_count,
            "friends": diplo.friend_count,
            "allies": diplo.ally_count,
        }[kind](state, tribe.id)
        label = {
            "contacts": f"Connaître {_plural(cond.need, 'autre peuple')}",
            "friends": f"{_plural(cond.need, 'peuple')} cordia{'ux' if cond.need > 1 else 'l'} (relation 20)",
            "allies": _plural(cond.need, "allié"),
        }[kind]
        return have, cond.need, label
    if kind == "vassals":
        n = len(chiefdom.vassals_of(state, tribe.id))
        return n, cond.need, f"{_plural(cond.need, 'tributaire')}"
    if kind == "kin_villages":
        return chiefdom.kin_villages(state, tribe.id), cond.need, f"{_plural(cond.need, 'village frère')} (de votre civilisation, ou tributaire)"
    if kind in ("villages", "village_years"):
        if kind == "villages":
            return sites.village_count(state, tribe.id), cond.need, _plural(cond.need, "village")
        return sites.oldest_village_years(state, tribe.id), cond.need, f"Un village tenu {cond.need} ans"
    return 0, 1, "?"


# Drapeaux poses par les evenements, lus par les conditions de savoirs.
_FLAG_LABELS = {
    "louveteaux": "Avoir apprivoisé des louveteaux (événement)",
}


def _key(terrain) -> str:
    return terrain if isinstance(terrain, str) else terrain.value


def _neighbors_know(state, tribe_id: int, tech_id: str) -> list:
    return diplo.teachers(state, tribe_id, tech_id)


def conditions_met(state, tribe, tech: Tech) -> bool:
    eased = bool(_neighbors_know(state, tribe.id, tech.id))
    for cond in tech.conds:
        have, need, _label = cond_progress(state, tribe, cond, eased)
        if have < need:
            return False
    return True


def status(state, tribe_id: int, tech_id: str) -> str:
    """"connu", "en_cours", "disponible", "attente" (prerequis OK, pas les
    conditions ; un grand tournant : pas encore arrive chez lui),
    "verrouille" (prerequis manquants) ou "absent" (un tirage : il ne
    viendra pas, draws.py)."""
    tribe = state.tribes[tribe_id]
    tech = TECHS[tech_id]
    if tech_id in tribe.knowledge:
        return "connu"
    # Un savoir commence se finit : les conditions (terrains, bandes...)
    # ne comptent que pour le commencer.
    if tribe.learning == tech_id:
        return "en_cours"
    if tribe.progress.get(tech_id, 0.0) > 0:
        return "disponible"
    if draws.absent(state, tribe_id, tech_id):
        return "absent"
    if missing_prereqs(tribe, tech):
        return "verrouille"
    if tech.turning:
        # Un grand tournant s'adopte quand il est arrive chez soi.
        return "disponible" if turning.presence(tribe, tech_id) >= 100.0 else "attente"
    if not conditions_met(state, tribe, tech):
        return "attente"
    return "disponible"


def available(state, tribe_id: int) -> list[str]:
    return [tid for tid in TECHS if status(state, tribe_id, tid) in ("disponible", "en_cours")]


def _learning_pop(state, tribe_id: int) -> int:
    """Les clans indociles n'apportent plus rien a la tribu."""
    return sum(
        b.population
        for b in state.bands.values()
        if b.tribe_id == tribe_id and b.population > 0 and chiefs.obeys(state, b)
    )


def base_rate(state, tribe_id: int) -> float:
    learn = bonuses(state.tribes[tribe_id]).learn if tribe_id in state.tribes else 1.0
    return (1.0 + _learning_pop(state, tribe_id) / LEARN_POP) * chiefs.learn_mult(state, tribe_id) * learn


def diffusion_bonus(state, tribe_id: int, tech_id: str | None) -> float:
    """Part d'apprentissage en plus quand des voisins connaissent le savoir."""
    if tech_id is None:
        return 0.0
    return diplo.diffusion_bonus(state, tribe_id, tech_id)


def learn_rate(state, tribe_id: int, tech_id: str | None = None) -> float:
    rate = base_rate(state, tribe_id)
    if tech_id is not None:
        rate *= 1.0 + diffusion_bonus(state, tribe_id, tech_id)
    return rate


def weeks_left(state, tribe_id: int, tech_id: str) -> int:
    tribe = state.tribes[tribe_id]
    left = max(0.0, TECHS[tech_id].cost - tribe.progress.get(tech_id, 0.0))
    rate = learn_rate(state, tribe_id, tech_id)
    return int(-(-left // rate)) if rate > 0 else 999


def choose(state, tribe_id: int, tech_id: str) -> bool:
    """Commencer (ou reprendre) l'apprentissage d'un savoir disponible."""
    if tech_id not in TECHS or status(state, tribe_id, tech_id) != "disponible":
        return False
    state.tribes[tribe_id].learning = tech_id
    return True


def auto_choose(state, tribe_id: int) -> str | None:
    """Choix de l'IA (et du robot des tests) : son gout, sinon le moins cher."""
    tribe = state.tribes[tribe_id]
    if tribe.learning:
        return tribe.learning
    ready = [tid for tid in TECHS if status(state, tribe_id, tid) == "disponible"]
    if not ready:
        return None
    taste = culture_of(tribe).taste
    # Un grand tournant arrive chez soi passe avant tout : il ouvre un pan.
    ready.sort(key=lambda tid: (not TECHS[tid].turning, taste.index(tid) if tid in taste else 99, TECHS[tid].cost, tid))
    choose(state, tribe_id, ready[0])
    return ready[0]


def update_practice(state, count: bool = True) -> None:
    """Ce que chaque tribu a vecu cette semaine : terrains sous ses bandes,
    hiver local, rivage et steppe en vue, ressources du pays."""
    world = state.world
    by_tribe: dict[int, list] = {}
    for b in state.bands.values():
        if b.population > 0:
            by_tribe.setdefault(b.tribe_id, []).append(b)
    has_res = bool(getattr(world, "resources", None))
    for tribe in state.tribes.values():
        bands = by_tribe.get(tribe.id, [])
        if not tribe.shore_seen or not tribe.steppe_seen:
            for band in bands:
                # La carte ne change pas : une position deja examinee n'a
                # rien de neuf a montrer.
                memo = (tribe.id, band.position)
                if memo in state.scan_memo:
                    continue
                state.scan_memo.add(memo)
                for h in world.hexes_in_radius(band.position, SEE_RADIUS):
                    if not tribe.shore_seen and is_inshore(world, h):
                        tribe.shore_seen = True
                    if not tribe.steppe_seen and world.terrain(h) is Terrain.STEPPE:
                        tribe.steppe_seen = True
                    if tribe.shore_seen and tribe.steppe_seen:
                        break
        if not count:
            continue
        seen = set()
        winter = False
        near: set = set()
        for band in bands:
            if band.village:
                # Un village vit de ses terres : chasse, peche, cueillette et
                # glaise de tout son pays (villages.FIELD_RADIUS).
                terrains, found = land_profile(world, band.position)
                seen |= terrains
                if has_res:
                    near |= found
            else:
                seen.add(world.terrain(band.position))
                if has_res:
                    near |= world.resources_near(band.position)
            if world.hex_season(band.position) is Season.HIVER:
                winter = True
        if len(bands) > tribe.practice.get("bandes", 0):
            tribe.practice["bandes"] = len(bands)
        goods = getattr(tribe, "goods", None)
        if goods and has_res:
            # Le sel, les pots, les haches qui arrivent par l'echange : on
            # apprend a connaitre ce qu'on n'a pas chez soi.
            for good, res in _GOOD_RESOURCE.items():
                if goods.get(good, 0.0) > 0:
                    near.add(res)
        for terrain in seen:
            tribe.practice[terrain.value] = min(999, tribe.practice.get(terrain.value, 0) + 1)
        for res in near:
            key = "res:" + res
            tribe.practice[key] = min(999, tribe.practice.get(key, 0) + 1)
        if winter:
            tribe.practice["hiver"] = min(999, tribe.practice.get("hiver", 0) + 1)
        # Compteurs historiques de la pirogue et du troupeau (bornes).
        if Terrain.COTE in seen and tribe.coast_weeks < PIROGUE_COAST_WEEKS:
            tribe.coast_weeks += 1
        if Terrain.STEPPE in seen and tribe.steppe_weeks < TROUPEAU_STEPPE_WEEKS:
            tribe.steppe_weeks += 1


_GOOD_RESOURCE = {"sel": "sel", "poteries": "argile", "haches": "silex", "etoffes": "chevres", "cuirs": "aurochs"}


def count_winter(state) -> None:
    """Fin de l'hiver : chaque tribu vivante a traverse un hiver de plus."""
    living = {b.tribe_id for b in state.bands.values() if b.population > 0}
    for tribe in state.tribes.values():
        if tribe.id in living:
            tribe.practice["hivers"] = tribe.practice.get("hivers", 0) + 1


def update_learning(state) -> None:
    """Chaque semaine : l'apprentissage avance ; l'IA choisit le suivant (une
    semaine sur quatre, decalee selon le peuple ; un peuple eteint ne
    cherche plus)."""
    with diplo.frozen_relations(state):
        _update_learning(state)


def _update_learning(state) -> None:
    living = {b.tribe_id for b in state.bands.values() if b.population > 0}
    for tribe in state.tribes.values():
        if tribe.id not in living:
            continue
        if not tribe.is_player and not tribe.learning and (state.tick_count + tribe.id) % 4 == 0:
            auto_choose(state, tribe.id)
        tid = tribe.learning
        if not tid:
            continue
        if tid in tribe.knowledge or tid not in TECHS:
            tribe.learning = None
            continue
        tribe.progress[tid] = tribe.progress.get(tid, 0.0) + learn_rate(state, tribe.id, tid)
        if tribe.progress[tid] >= TECHS[tid].cost:
            grant(tribe, tid)
            if tribe.is_player:
                tech = TECHS[tid]
                note(state, LogKind.DECOUVERTE, f"Nouveau savoir : {tech.name}. {summary(tech)}", to=tribe.id)


def detail_lines(state, tribe_id: int, tech_id: str) -> list[tuple[str, str]]:
    """Fiche d'un savoir pour le panneau : (texte, style) ; style parmi
    "titre", "texte", "effet", "ok", "manque", "note"."""
    tribe = state.tribes[tribe_id]
    tech = TECHS[tech_id]
    st = status(state, tribe_id, tech_id)
    out: list[tuple[str, str]] = [(tech.name, "titre"), (tech.about, "texte")]
    out.append(("Effets :", "note"))
    out.extend((f"  {line}", "effet") for line in effect_lines(tech))
    if tech.turning:
        out.extend(("  " + text, "effet") for text, kind in turning.lines(state, tribe_id, tech_id)[:1])
    else:
        after = pan_of(tech_id)
        if after:
            out.append(("  Mène à : " + ", ".join(t.name for t in after), "effet"))
    if st == "connu":
        out.append(("Savoir connu.", "ok"))
        return out
    if st == "absent":
        out.append(("Il ne viendra pas :", "note"))
        out.append(("  " + draws.why_absent(state, tribe_id, tech_id), "manque"))
        return out
    if tech.drawn:
        out.append(("Il faut le sort :", "note"))
        out.extend(("  " + text, kind if kind != "note" else "info") for text, kind in draws.lines(state, tribe_id, tech_id))
    if tech.turning:
        out.append(("Il faut qu'il soit arrivé chez vous :", "note"))
        out.extend(("  " + text, kind if kind != "note" else "info") for text, kind in turning.lines(state, tribe_id, tech_id)[1:])
    if tech.prereqs:
        out.append(("Il faut connaître :", "note"))
        for pid in tech.prereqs:
            out.append((f"  {TECHS[pid].name}", "ok" if pid in tribe.knowledge else "manque"))
    teachers = _neighbors_know(state, tribe_id, tech_id)
    if tech.conds:
        out.append(("Pour qu'il naisse chez vous :" if tech.turning else "Il faut avoir vécu :", "note"))
        for cond in tech.conds:
            have, need, label = cond_progress(state, tribe, cond, bool(teachers))
            shown = f"  {label}  ({min(have, need)}/{need})" if cond.kind not in ("seen", "flag") else f"  {label}"
            out.append((shown, "ok" if have >= need else "manque"))
    if teachers:
        names = ", ".join(state.tribes[t].name for t in teachers[:3])
        bonus = round(100 * diffusion_bonus(state, tribe_id, tech_id))
        out.append((f"Connu de : {names}  -  apprentissage +{bonus} %, semaines vécues divisées par 2", "ok"))
    if st in ("disponible", "en_cours"):
        done = tribe.progress.get(tech_id, 0.0)
        out.append(
            (
                f"Apprentissage : {int(100 * done / tech.cost)} %  -  encore ~{weeks_left(state, tribe_id, tech_id)} sem.",
                "note",
            )
        )
    return out
