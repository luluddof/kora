"""Chefs, clans et emprise.

Chaque bande a un chef de bande (nom, age, traits, renommee). Le chef de
la tribu est le chef d'UNE de ces bandes : sa bande est le coeur de la
tribu. Les autres clans lui sont plus ou moins attaches (Band.loyalty) :
chaque mois l'attachement va vers une cible (distance au chef, zone
d'influence, prestige, traits, famine, savoirs...). Trop bas, le clan
n'obeit plus (indocile), puis il part : il fonde son peuple, ou rejoint
le peuple dans la zone duquel il vit.
Les chefs vieillissent et meurent ; l'heritier (ou le plus renomme)
succede. N'importe ni pygame ni render.
"""

from __future__ import annotations

import copy
from dataclasses import dataclass, field

from src.kora import tech
from src.kora.log import LogKind
from src.kora.types import Person

OBEY = 40.0
LEAVE = 20.0
VISIT_RANGE = 3
VISIT_GAIN = 10.0
HONOR_COST = 5
HONOR_GAIN = 20.0
HONOR_EVERY = 26
DRIFT = 0.25
# Apres le premier village, le chef gouverne le village et perd la main sur
# les clans restes nomades : leur independance monte chaque mois (plus vite
# loin des villages et hors de l'emprise du chef, moitie moins pres d'un
# village) ; a 100, le clan s'en va fonder un peuple de la meme
# civilisation, qui aura ses propres villages. Honorer la fait baisser.
AUTONOMY_MONTH = 1.5
AUTONOMY_FAR = 1.0
AUTONOMY_REACH = 0.5
AUTONOMY_NEAR = 0.5
AUTONOMY_WARN = 75.0
# Chaque village de plus du peuple : le chef gouverne ses villages, les
# clans s'eloignent d'autant plus vite (x1,5 avec 2 villages, x2,5 avec 4).
AUTONOMY_VILLAGE_PULL = 0.5
# Un clan indocile (il n'obeit plus) prend son independance plus vite.
AUTONOMY_INDOCILE = 1.0
HONOR_AUTONOMY = 15.0
NEAR_VILLAGE = 5.0
MAX_NOTABLES = 3
AMBITIOUS_NOTABLE = -6.0
BATTLE_DEATH = 0.08
START_LOYALTY = 80.0


@dataclass(frozen=True)
class Trait:
    id: str
    name: str
    weight: float
    effects: dict = field(default_factory=dict)


TRAITS: dict[str, Trait] = {
    t.id: t
    for t in (
        Trait("chasseur", "Grand chasseur", 1.0, {"food": 1.08}),
        Trait("guerrier", "Guerrier", 1.0, {"combat": 1.10}),
        Trait("sage", "Sage", 0.8, {"learn": 1.10}),
        Trait("rassembleur", "Rassembleur", 0.7, {"loyalty_all": 10, "loyalty_own": 5}),
        Trait("genereux", "Genereux", 0.8, {"loyalty_own": 5, "gifts": 1.25, "relations": 3}),
        Trait("prudent", "Prudent", 0.9, {"famine": 0.85}),
        Trait("ambitieux", "Ambitieux", 0.8, {"loyalty_own": -15, "winter_prestige": 1}),
        Trait("querelleur", "Querelleur", 0.5, {"loyalty_all": -5, "relations": -5}),
        Trait("robuste", "Robuste", 0.8, {"death": 0.5}),
        Trait("fragile", "De sante fragile", 0.5, {"death": 2.0}),
        Trait("conteur", "Conteur", 0.6, {"winter_prestige": 1, "loyalty_all": 3}),
        Trait("fidele", "Fidele", 0.8, {"loyalty_own": 15}),
        Trait("tueur_loups", "Tueur de loups", 0.0, {"loyalty_own": 5}),
    )
}


def trait_lines(trait: Trait) -> list[str]:
    e = trait.effects
    out = []
    if "food" in e:
        out.append(f"Sa bande : {tech._pct(e['food'])} de nourriture")
    if "combat" in e:
        out.append(f"Sa bande : {tech._pct(e['combat'])} de force au combat")
    if "famine" in e:
        out.append(f"Sa bande : {tech._pct(e['famine'])} de morts de faim")
    if "loyalty_own" in e:
        v = e["loyalty_own"]
        out.append(f"Son clan : {'+' if v >= 0 else ''}{v} d'attachement")
    if "death" in e:
        out.append("Vit plus longtemps" if e["death"] < 1 else "Risque de mourir plus tot")
    if "learn" in e:
        out.append(f"Chef de la tribu : {tech._pct(e['learn'])} d'apprentissage")
    if "loyalty_all" in e:
        v = e["loyalty_all"]
        out.append(f"Chef de la tribu : {'+' if v >= 0 else ''}{v} d'attachement pour tous les clans")
    if "gifts" in e:
        out.append(f"Chef de la tribu : cadeaux {tech._pct(e['gifts'])}")
    if "relations" in e:
        v = e["relations"]
        out.append(f"Chef de la tribu : {'+' if v >= 0 else ''}{v} de relation avec tous les peuples")
    if "winter_prestige" in e:
        out.append(f"Chef de la tribu : +{e['winter_prestige']} prestige a la fin de l'hiver")
    return out


# --- personnes ----------------------------------------------------------------


def _new_pid(state) -> int:
    pid = max(getattr(state, "next_person_id", 1), 1)
    state.next_person_id = pid + 1
    return pid


def new_person(state, tribe, age: int | None = None, traits: tuple | None = None, renown: int | None = None) -> Person:
    from src.kora.peoples import culture_of, make_name

    rng = state.story_rng
    taken = [b.leader.name for b in state.bands.values() if b.leader is not None and b.tribe_id == tribe.id]
    name = make_name(rng, culture_of(tribe), taken)
    if age is None:
        age = rng.randint(20, 38)
    if traits is None:
        traits = _roll_traits(rng)
    if renown is None:
        renown = rng.randint(3, 15)
    return Person(_new_pid(state), name, state.clock.year - age, tuple(traits), renown)


def _roll_traits(rng) -> tuple:
    pool = [t for t in TRAITS.values() if t.weight > 0]
    count = 1 if rng.random() < 0.7 else 2
    out: list[str] = []
    for _ in range(count):
        total = sum(t.weight for t in pool if t.id not in out)
        pick = rng.random() * total
        for t in pool:
            if t.id in out:
                continue
            pick -= t.weight
            if pick <= 0:
                out.append(t.id)
                break
    # Deux traits contraires : on garde le premier.
    clash = ({"robuste", "fragile"}, {"fidele", "ambitieux"}, {"genereux", "querelleur"})
    for pair in clash:
        if pair <= set(out):
            out = out[:1]
    return tuple(out)


def age(state, person: Person) -> int:
    return state.clock.year - person.born


def describe(state, person: Person | None) -> str:
    if person is None:
        return "?"
    traits = ", ".join(TRAITS[t].name for t in person.traits if t in TRAITS)
    base = f"{person.name} ({age(state, person)} ans)"
    return f"{base} · {traits}" if traits else base


def _trait(person: Person | None, key: str, default):
    if person is None:
        return default
    value = default
    for t in person.traits:
        e = TRAITS.get(t)
        if e is None or key not in e.effects:
            continue
        v = e.effects[key]
        value = value * v if isinstance(default, float) else value + v
    return value


# --- qui est chef --------------------------------------------------------------


def chief_band(state, tid: int):
    tribe = state.tribes.get(tid)
    if tribe is None or not tribe.chief_band:
        return None
    band = state.bands.get(tribe.chief_band)
    if band is None or band.tribe_id != tid or band.population <= 0:
        return None
    return band


def chief_of(state, tid: int) -> Person | None:
    band = chief_band(state, tid)
    return band.leader if band is not None else None


def is_chief_band(state, band) -> bool:
    tribe = state.tribes.get(band.tribe_id)
    return tribe is not None and tribe.chief_band == band.id


def obeys(state, band) -> bool:
    """Le joueur (ou l'IA de la tribu) peut donner des ordres a cette bande."""
    if is_chief_band(state, band):
        return True
    tribe = state.tribes.get(band.tribe_id)
    if tribe is None or not tribe.chief_band:
        return True
    return band.loyalty >= OBEY


def helps(state, band) -> bool:
    """Vient en renfort de ses soeurs (un clan indocile ne vient pas)."""
    return obeys(state, band)


def mood(state, band) -> str:
    if is_chief_band(state, band):
        return "bande du chef"
    if band.loyalty >= 60:
        return "fidele"
    if band.loyalty >= OBEY:
        return "distant"
    if band.loyalty >= LEAVE:
        return "indocile"
    return "au depart"


# --- effets des traits ------------------------------------------------------------


def band_food(band) -> float:
    return _trait(band.leader, "food", 1.0)


def band_combat(band) -> float:
    return _trait(band.leader, "combat", 1.0)


def band_famine(band) -> float:
    return _trait(band.leader, "famine", 1.0)


def learn_mult(state, tid: int) -> float:
    return _trait(chief_of(state, tid), "learn", 1.0)


def gifts_mult(state, tid: int) -> float:
    return _trait(chief_of(state, tid), "gifts", 1.0)


def winter_prestige(state, tid: int) -> int:
    return _trait(chief_of(state, tid), "winter_prestige", 0)


# --- attachement --------------------------------------------------------------------


def loyalty_parts(state, band) -> list[tuple[str, float]]:
    """Raisons de la cible d'attachement d'un clan, lisibles."""
    from src.kora import influence, sites

    tribe = state.tribes.get(band.tribe_id)
    if tribe is None:
        return []
    bonus = tech.bonuses(tribe)
    parts: list[tuple[str, float]] = [("Base", 70.0)]
    heart = chief_band(state, band.tribe_id)
    chief = heart.leader if heart is not None else None
    if heart is None:
        parts.append(("Pas de chef", -15.0))
    else:
        reach = bonus.chief_reach
        d = state.world.distance(band.position, heart.position)
        if d > reach:
            parts.append((f"Loin du chef ({d} cases, emprise {reach})", -min(40.0, 0.8 * (d - reach))))
        if band.population > heart.population:
            parts.append(("Plus nombreux que le clan du chef", -10.0))
    world = state.world
    if influence.in_core(world, band.position, band.tribe_id):
        parts.append(("Au coeur de vos terres", 15.0))
    elif influence.in_zone(world, band.position, band.tribe_id):
        parts.append(("Dans vos terres", 10.0))
    other = influence.foreign_zone(world, band.position, band.tribe_id)
    if other and other in state.tribes:
        parts.append((f"Chez les {state.tribes[other].name}", -10.0))
    parts.append(("Prestige de la tribu", (tribe.prestige - 40) * 0.2))
    if chief is not None:
        v = _trait(chief, "loyalty_all", 0)
        if v:
            parts.append((f"Chef {', '.join(TRAITS[t].name.lower() for t in chief.traits if t in TRAITS)}", float(v)))
    own = _trait(band.leader, "loyalty_own", 0)
    if own:
        names = ", ".join(TRAITS[t].name.lower() for t in band.leader.traits if t in TRAITS)
        parts.append((f"Chef de bande {names}", float(own)))
    if state.tick_count - band.famine_tick <= 8:
        parts.append(("Famine recente", -10.0))
    if state.sites:
        from src.kora import villages

        parts.extend(villages.loyalty_parts(state, band))
        if tribe.settled_at >= 0 and not band.village and band.kind != "armee":
            near = villages.nearest_village(state, band, villages.NEAR)
            if near is not None:
                parts.append((f"Pres de {villages.name(near)}", NEAR_VILLAGE))
    for notable in band.notables:
        if "ambitieux" in notable.traits:
            parts.append((f"Un ancien ambitieux ({notable.name})", AMBITIOUS_NOTABLE))
            break
    count = sum(1 for b in state.bands.values() if b.tribe_id == band.tribe_id and b.population > 0 and b.kind != "armee")
    if count > 4:
        parts.append(("Tribu tres etendue", -2.0 * (count - 4)))
    if bonus.loyalty:
        parts.append(("Savoirs (rites, chefferie...)", float(bonus.loyalty)))
    if band.village and state.sites:
        from src.kora import villages

        site = villages.site_of(state, band)
        if site is not None:
            s = (villages.stability(state, site, band) - villages.STABILITY_BASE) * 0.3
            if abs(s) >= 1:
                parts.append(("Stabilite du village", s))
    if band.leader is not None and tribe.heir == band.leader.pid:
        parts.append(("Heritier designe", 10.0))
    if sites.camp_at(state, band) is not None:
        parts.append(("Au campement", 5.0))
    return [(label, round(v, 1)) for label, v in parts if abs(v) >= 0.5]


def loyalty_target(state, band) -> float:
    return max(0.0, min(100.0, sum(v for _l, v in loyalty_parts(state, band))))


def monthly(state) -> None:
    """Attachement des clans, visites du chef, departs ; morts des chefs."""
    for tid in sorted(state.tribes):
        tribe = state.tribes[tid]
        bands = [b for b in state.bands.values() if b.tribe_id == tid and b.population > 0]
        if not bands:
            continue
        heart = chief_band(state, tid)
        if heart is None:
            _succession(state, tid, dead=None)
            heart = chief_band(state, tid)
        for band in sorted(bands, key=lambda b: b.id):
            if (heart is not None and band.id == heart.id) or band.kind == "armee":
                # Une troupe obeit : c'est ce qui la fait troupe.
                band.loyalty = 100.0
                continue
            target = loyalty_target(state, band)
            band.loyalty += (target - band.loyalty) * DRIFT
            if heart is not None and state.world.distance(band.position, heart.position) <= VISIT_RANGE:
                band.loyalty = min(100.0, band.loyalty + VISIT_GAIN)
            band.loyalty = max(0.0, min(100.0, band.loyalty))
        for band in sorted(bands, key=lambda b: b.id):
            if band.id not in state.bands or is_chief_band(state, band) or band.kind == "armee":
                continue
            if (
                not tribe.is_player
                and band.loyalty < 35
                and tribe.prestige >= 20
                and not can_honor(state, band.id)
                and state.story_rng.random() < 0.5
            ):
                # L'IA tient ses clans : elle honore celui qui s'eloigne.
                honor(state, band.id)
            if band.loyalty < LEAVE and state.story_rng.random() < (LEAVE - band.loyalty) / 40.0:
                _wants_to_leave(state, band)
        if tribe.settled_at >= 0:
            _grow_autonomy(state, tribe)
    _deaths(state)


def gains_autonomy(state, band) -> bool:
    """Un clan nomade d'un peuple fixe (ni village, ni troupe, ni le chef)."""
    tribe = state.tribes.get(band.tribe_id)
    return (
        tribe is not None
        and tribe.settled_at >= 0
        and not band.village
        and band.kind != "armee"
        and band.population > 0
        and not is_chief_band(state, band)
    )


def autonomy_parts(state, band) -> list[tuple[str, str]]:
    """Pourquoi le clan s'eloigne : (raison, effet lisible), et le taux."""
    return _autonomy(state, band)[1]


def _autonomy(state, band) -> tuple[float, list]:
    from src.kora import sites, villages

    if not gains_autonomy(state, band):
        return 0.0, []
    parts = [("Le chef gouverne le village", f"+{AUTONOMY_MONTH:.1f}")]
    rate = AUTONOMY_MONTH
    if villages.nearest_village(state, band, villages.NEAR) is None:
        rate += AUTONOMY_FAR
        parts.append((f"Loin de vos villages (plus de {villages.NEAR} cases)", f"+{AUTONOMY_FAR:.1f}"))
    heart = chief_band(state, band.tribe_id)
    reach = tech.bonuses(state.tribes[band.tribe_id]).chief_reach
    if heart is not None and state.world.distance(band.position, heart.position) > reach:
        rate += AUTONOMY_REACH
        parts.append((f"Hors de l'emprise du chef ({reach} cases)", f"+{AUTONOMY_REACH:.1f}"))
    if band.loyalty < OBEY:
        rate += AUTONOMY_INDOCILE
        parts.append(("Indocile : il n'obeit plus", f"+{AUTONOMY_INDOCILE:.1f}"))
    if villages.nearest_village(state, band, villages.NEAR) is not None:
        rate *= AUTONOMY_NEAR
        parts.append(("Pres d'un de vos villages", f"x{AUTONOMY_NEAR:.1f}"))
    count = len(sites.of_tribe(state, band.tribe_id, "village"))
    if count > 1:
        pull = 1.0 + AUTONOMY_VILLAGE_PULL * (count - 1)
        rate *= pull
        parts.append((f"{count} villages : le chef a d'autres soucis", f"x{pull:.1f}"))
    return rate, [(label, v.replace(".", ",")) for label, v in parts]


def autonomy_rate(state, band) -> float:
    """Independance gagnee par mois."""
    return _autonomy(state, band)[0]


def autonomy_months(state, band) -> int:
    rate = autonomy_rate(state, band)
    if rate <= 0:
        return 0
    return max(0, int(-(-(100.0 - band.autonomy) // rate)))


def _grow_autonomy(state, tribe) -> None:
    ready = []
    for band in sorted((b for b in state.bands.values() if b.tribe_id == tribe.id), key=lambda b: b.id):
        if not gains_autonomy(state, band):
            continue
        before = band.autonomy
        band.autonomy = min(100.0, before + autonomy_rate(state, band))
        if tribe.is_player and before < AUTONOMY_WARN <= band.autonomy:
            _note(
                state,
                LogKind.POLITIQUE,
                f"Le clan de {_name(band)} n'ecoute plus guere le village : il parle de partir fonder le sien.",
                band.position,
            )
        if band.autonomy >= 100.0:
            ready.append(band)
    if ready:
        # Un depart par peuple et par mois : les clans s'en vont l'un apres
        # l'autre, pas tous le meme jour.
        first = min(ready, key=lambda b: (-b.autonomy, b.id))
        emancipate(state, first.id)


def emancipate(state, band_id: int) -> int:
    """Le clan prend son independance : un peuple de la meme civilisation,
    sous son propre chef (secede sans rancune). Il s'en va chercher sa terre,
    loin des villages (ai.find_new_land) : il ne s'installe pas au pied du
    village qu'il quitte."""
    new = secede(state, band_id, independence=True)
    if new:
        from src.kora import ai

        ai.head_for_new_land(state, state.bands[band_id])
    return new


def _wants_to_leave(state, band) -> None:
    tribe = state.tribes[band.tribe_id]
    if tribe.is_player:
        from src.kora import events

        if events.hook(state, "clan_part", tribe_id=tribe.id, band_id=band.id):
            return
        secede(state, band.id)
        return
    # L'IA : honorer le clan si elle en a les moyens, sinon il part.
    if tribe.prestige >= 15 and state.story_rng.random() < 0.6 and can_honor(state, band.id) == "":
        honor(state, band.id)
        return
    secede(state, band.id)


# --- actions -------------------------------------------------------------------


def can_honor(state, band_id: int) -> str:
    band = state.bands.get(band_id)
    if band is None:
        return "Pas de bande"
    tribe = state.tribes[band.tribe_id]
    if is_chief_band(state, band):
        return "C'est la bande du chef"
    if tribe.prestige < HONOR_COST:
        return f"Il faut {HONOR_COST} de prestige"
    wait = HONOR_EVERY - (state.tick_count - band.honored)
    if wait > 0:
        return f"Deja honore (encore {wait} sem.)"
    return ""


def honor(state, band_id: int) -> bool:
    if can_honor(state, band_id):
        return False
    band = state.bands[band_id]
    tribe = state.tribes[band.tribe_id]
    tribe.prestige -= HONOR_COST
    band.loyalty = min(100.0, band.loyalty + HONOR_GAIN)
    band.autonomy = max(0.0, band.autonomy - HONOR_AUTONOMY)
    band.honored = state.tick_count
    if band.leader is not None:
        band.leader.renown += 3
    if tribe.is_player:
        who = band.leader.name if band.leader else "ce clan"
        _note(state, LogKind.POLITIQUE, f"Le clan de {who} est honore (+{HONOR_GAIN:.0f} attachement).", band.position)
    return True


def can_move_chief(state, band_id: int) -> str:
    band = state.bands.get(band_id)
    if band is None:
        return "Pas de bande"
    heart = chief_band(state, band.tribe_id)
    if heart is None or heart.id == band.id:
        return "Le chef est deja ici"
    if state.world.distance(heart.position, band.position) > 1:
        return "La bande du chef doit etre sur la meme case"
    return ""


def move_chief(state, band_id: int) -> bool:
    """Le chef rejoint cette bande (les deux chefs de bande echangent)."""
    if can_move_chief(state, band_id):
        return False
    band = state.bands[band_id]
    heart = chief_band(state, band.tribe_id)
    band.leader, heart.leader = heart.leader, band.leader
    heart.loyalty = band.loyalty
    band.loyalty = 100.0
    state.tribes[band.tribe_id].chief_band = band.id
    return True


def can_promote(state, band_id: int, pid: int) -> str:
    band = state.bands.get(band_id)
    if band is None:
        return "Pas de bande"
    if is_chief_band(state, band):
        return "Le chef de la tribu mene ce clan"
    if not any(p.pid == pid for p in band.notables):
        return "Pas un ancien de ce clan"
    return ""


def promote(state, band_id: int, pid: int) -> bool:
    """Confier le clan a un de ses anciens (l'ancien chef rejoint les anciens)."""
    if can_promote(state, band_id, pid):
        return False
    band = state.bands[band_id]
    new = next(p for p in band.notables if p.pid == pid)
    band.notables.remove(new)
    add_notable(band, band.leader)
    band.leader = new
    if state.tribes[band.tribe_id].is_player:
        _note(state, LogKind.POLITIQUE, f"{new.name} mene desormais son clan.", band.position)
    return True


def set_heir(state, band_id: int) -> bool:
    band = state.bands.get(band_id)
    if band is None or band.leader is None or is_chief_band(state, band):
        return False
    tribe = state.tribes[band.tribe_id]
    tribe.heir = band.leader.pid
    band.loyalty = min(100.0, band.loyalty + 10.0)
    for other in state.bands.values():
        if other.tribe_id == tribe.id and other.id != band.id and other.leader is not None:
            if "ambitieux" in other.leader.traits:
                other.loyalty = max(0.0, other.loyalty - 5.0)
    if tribe.is_player:
        _note(state, LogKind.POLITIQUE, f"{band.leader.name} est designe heritier.", band.position)
    return True


# --- depart d'un clan ------------------------------------------------------------------


def secede(state, band_id: int, hostile: bool = False, independence: bool = False) -> int:
    """Le clan quitte sa tribu. Rend le peuple qu'il rejoint ou fonde (0 :
    il reste, faute de place). Independance (apres les villages) : il ne
    rejoint pas un peuple etranger, il fonde le sien, de la meme
    civilisation (le monde plein : il attend)."""
    from src.kora import diplo, influence
    from src.kora.peoples import MAX_LIVING_TRIBES, civ_of, culture_for_place, free_color, kin_color, living_tribe_ids
    from src.kora.types import Tribe, stay_order

    band = state.bands.get(band_id)
    if band is None or is_chief_band(state, band):
        # Le chef ne quitte pas son peuple (une carte "le clan veut partir"
        # decidee apres coup peut viser la bande devenue celle du chef).
        return 0
    parent = state.tribes[band.tribe_id]
    if parent.settled_at >= 0:
        # Un peuple fixe : le clan qui part fonde le sien, de la meme
        # civilisation ; il ne passe pas chez un voisin.
        independence = True
    band.order = stay_order()
    band.path = []
    band.intent_prey = 0
    band.retreating = False
    host = 0 if independence else influence.foreign_zone(state.world, band.position, band.tribe_id)
    joined = 0
    civ = civ_of(state, parent)
    if (
        host
        and host in state.tribes
        and state.tribes[host].prestige >= parent.prestige - 10
        and not diplo.relation(state, host, parent.id) <= -50
    ):
        joined = host
        band.tribe_id = host
        band.loyalty = 60.0
        diplo.add_mod(state, host, parent.id, "debauchage", -20, actor=host)
        text = f"Le clan de {_name(band)} a rejoint les {state.tribes[host].name} !"
    elif len(living_tribe_ids(state)) < MAX_LIVING_TRIBES:
        from src.kora.peoples import CULTURES, make_name

        tid = max(state.next_tribe_id, max(state.tribes) + 1)
        state.next_tribe_id = tid + 1
        if parent.culture == "joueur":
            culture = "souche"
        else:
            culture = parent.culture if parent.culture else culture_for_place(state.world, band.position)
        name = make_name(state.story_rng, CULTURES[culture], [t.name for t in state.tribes.values()])
        tribe = Tribe(
            tid,
            name,
            max(5, parent.prestige // 2),
            False,
            knowledge=set(parent.knowledge),
            practice=dict(parent.practice),
            culture=culture,
            color=kin_color(state, civ) if independence else free_color(state.tribes.values()),
            minor=True,
            origin=parent.id,
            founded=state.clock.year,
            cabotage=parent.cabotage,
            troupeau=parent.troupeau,
            shore_seen=parent.shore_seen,
            steppe_seen=parent.steppe_seen,
            civ=civ,
        )
        state.tribes[tid] = tribe
        band.tribe_id = tid
        tribe.chief_band = band.id
        band.loyalty = 100.0
        band.autonomy = 0.0
        diplo.make_contact(state, tid, parent.id, quiet=True)
        diplo.add_mod(state, tid, parent.id, "meme_souche", 25)
        diplo.add_mod(state, tid, parent.id, "separation", -35 if hostile else -15, actor=tid)
        joined = tid
        if parent.settled_at >= 0:
            text = (
                f"Le clan de {_name(band)} ({band.population} personnes) prend son independance : "
                f"les {name}, de votre civilisation, fonderont leurs propres villages sous leur propre chef."
            )
        else:
            text = (
                f"Le clan de {_name(band)} ({band.population} personnes) s'en va "
                f"et fonde son propre peuple : les {name}."
            )
    else:
        # Le monde est plein : le clan attend d'avoir la place de partir
        # (son independance reste a 100, il n'obeit plus guere).
        band.loyalty = min(band.loyalty, 30.0)
        return 0
    if parent.heir and band.leader is not None and parent.heir == band.leader.pid:
        parent.heir = 0
    if parent.is_player or state.tribes[joined].is_player:
        _note(state, LogKind.POLITIQUE, text, band.position)
    return joined


def _name(band) -> str:
    return band.leader.name if band.leader is not None else f"la bande {band.id}"


# --- morts et successions ------------------------------------------------------------------


def _death_risk(state, person: Person) -> float:
    a = age(state, person)
    if a < 35:
        yearly = 0.01
    elif a < 45:
        yearly = 0.03
    elif a < 55:
        yearly = 0.06
    elif a < 65:
        yearly = 0.12
    else:
        yearly = 0.25
    return yearly * _trait(person, "death", 1.0) / 13.0


def _deaths(state) -> None:
    for band in sorted(state.bands.values(), key=lambda b: b.id):
        if band.leader is None or band.population <= 0:
            continue
        if state.story_rng.random() < _death_risk(state, band.leader):
            leader_dies(state, band, "de vieillesse" if age(state, band.leader) >= 55 else "de maladie")


def leader_dies(state, band, cause: str) -> None:
    """Le chef de bande meurt ; un proche le remplace. Si c'etait le chef de
    la tribu : succession."""
    tribe = state.tribes.get(band.tribe_id)
    if tribe is None or band.leader is None:
        return
    dead = band.leader
    was_chief = tribe.chief_band == band.id
    if band.notables:
        # Un des anciens du clan prend la tete.
        band.leader = band.notables.pop(0)
    else:
        heir_age = state.story_rng.randint(18, 30)
        band.leader = new_person(state, tribe, age=heir_age, renown=max(3, dead.renown // 3))
    if tribe.heir == dead.pid:
        tribe.heir = 0
    if was_chief:
        _succession(state, tribe.id, dead=dead, cause=cause)
    elif tribe.is_player:
        _note(
            state,
            LogKind.POLITIQUE,
            f"{dead.name}, chef de clan, est mort {cause}. {band.leader.name} mene le clan.",
            band.position,
        )


def candidates(state, tid: int, old_band: int = 0) -> list:
    """Bandes dont le chef peut succeder, du plus au moins legitime."""
    tribe = state.tribes[tid]
    bands = [b for b in state.bands.values() if b.tribe_id == tid and b.population > 0 and b.leader is not None]

    def score(b) -> float:
        s = b.leader.renown + b.population * 0.1
        if tribe.heir and b.leader.pid == tribe.heir:
            s += 40
        if b.id == old_band:
            s += 15
        return s

    return sorted(bands, key=lambda b: (-score(b), b.id))


def _succession(state, tid: int, dead: Person | None, cause: str = "") -> None:
    tribe = state.tribes[tid]
    old = tribe.chief_band
    ranked = candidates(state, tid, old)
    if not ranked:
        tribe.chief_band = 0
        return
    if tribe.is_player and dead is not None:
        from src.kora import events

        # Le joueur choisit parmi les meilleurs ; en attendant, le premier.
        crown(state, tid, ranked[0].id, quiet=True)
        if events.hook(state, "succession", tribe_id=tid, band_id=ranked[0].id, dead=dead.name, cause=cause):
            return
        _note(state, LogKind.POLITIQUE, f"{dead.name}, votre chef, est mort {cause}. {ranked[0].leader.name} lui succede.")
        return
    crown(state, tid, ranked[0].id, quiet=True)
    if dead is not None and _player_knows(state, tid):
        _note(state, LogKind.POLITIQUE, f"Les {tribe.name} ont un nouveau chef : {ranked[0].leader.name}.")


def crown(state, tid: int, band_id: int, quiet: bool = False) -> None:
    """band_id devient la bande du chef ; les ambitieux ecartes se detachent."""
    tribe = state.tribes[tid]
    band = state.bands.get(band_id)
    if band is None or band.tribe_id != tid:
        return
    previous = tribe.chief_band
    tribe.chief_band = band.id
    band.loyalty = 100.0
    if tribe.heir and band.leader is not None and band.leader.pid == tribe.heir:
        tribe.heir = 0
    for other in state.bands.values():
        if other.tribe_id != tid or other.id == band.id or other.leader is None:
            continue
        if other.id == previous:
            other.loyalty = min(other.loyalty, 75.0)
        if "ambitieux" in other.leader.traits and other.leader.renown >= band.leader.renown - 5:
            other.loyalty = max(0.0, other.loyalty - 15.0)
    if not quiet and tribe.is_player:
        _note(state, LogKind.POLITIQUE, f"{band.leader.name} mene desormais la tribu.", band.position)


def _player_knows(state, tid: int) -> bool:
    from src.kora import diplo

    player = next((t for t in state.tribes.values() if t.is_player), None)
    return player is not None and diplo.in_contact(state, player.id, tid)


# --- mise en place -----------------------------------------------------------------------


def ensure(state) -> None:
    """Chaque bande a un chef, chaque tribu vivante un chef (nouvelle partie,
    ancienne sauvegarde, bande ajoutee par un test)."""
    for band in sorted(state.bands.values(), key=lambda b: b.id):
        if band.leader is None and band.tribe_id in state.tribes:
            band.leader = new_person(state, state.tribes[band.tribe_id])
    for tid in sorted(state.tribes):
        tribe = state.tribes[tid]
        if chief_band(state, tid) is not None:
            continue
        bands = [b for b in state.bands.values() if b.tribe_id == tid and b.population > 0]
        if not bands:
            continue
        heart = max(bands, key=lambda b: (b.population, -b.id))
        tribe.chief_band = heart.id
        heart.loyalty = 100.0
        if heart.leader is not None:
            heart.leader.renown = max(heart.leader.renown, 30)


def add_notable(band, person) -> None:
    """Un ancien de plus dans le clan (les plus renommes restent)."""
    if person is None:
        return
    band.notables.append(person)
    band.notables.sort(key=lambda p: (-p.renown, p.pid))
    del band.notables[MAX_NOTABLES:]


def on_split(state, parent, child) -> None:
    tribe = state.tribes.get(parent.tribe_id)
    if tribe is None:
        return
    # Un ancien du clan mene ceux qui partent (sinon, un nouveau chef).
    child.leader = parent.notables.pop(0) if parent.notables else new_person(state, tribe)
    child.autonomy = 0.0 if parent.village else parent.autonomy
    child.loyalty = parent.loyalty if not is_chief_band(state, parent) else max(70.0, START_LOYALTY)


def on_merge(state, keep, gone) -> None:
    """Deux bandes reunies (keep.population compte deja celle de gone) : le
    chef de keep mene, celui de gone devient un ancien ; l'attachement est
    la moyenne ponderee par les gens."""
    tribe = state.tribes.get(keep.tribe_id)
    if tribe is None:
        return
    before = max(0, keep.population - gone.population)
    if tribe.chief_band == gone.id:
        add_notable(keep, keep.leader)
        keep.leader = gone.leader
        tribe.chief_band = keep.id
        keep.loyalty = 100.0
    else:
        if not is_chief_band(state, keep):
            total = max(1, before + gone.population)
            keep.loyalty = (keep.loyalty * before + gone.loyalty * gone.population) / total
        if not keep.village:
            total = max(1, before + gone.population)
            keep.autonomy = (keep.autonomy * before + gone.autonomy * gone.population) / total
        if tribe.heir and gone.leader is not None and tribe.heir == gone.leader.pid:
            tribe.heir = 0
        if keep.kind != "armee" and gone.kind != "armee":
            add_notable(keep, gone.leader)
    for person in gone.notables:
        add_notable(keep, person)


def on_band_lost(state, band) -> None:
    """Bande detruite : son chef meurt avec elle."""
    tribe = state.tribes.get(band.tribe_id)
    if tribe is None:
        return
    if tribe.heir and band.leader is not None and tribe.heir == band.leader.pid:
        tribe.heir = 0
    if tribe.chief_band == band.id:
        tribe.chief_band = 0
        dead = band.leader
        others = [b for b in state.bands.values() if b.tribe_id == tribe.id and b.id != band.id and b.population > 0]
        if others:
            _succession(state, tribe.id, dead=dead, cause="au combat")


def after_absorb(state, actor: int, target: int) -> None:
    ensure(state)
    tribe = state.tribes.get(target)
    if tribe is not None:
        tribe.chief_band = 0


def marriage_note(state, a: int, b: int) -> None:
    ca, cb = chief_of(state, a), chief_of(state, b)
    if ca is None or cb is None:
        return
    for x, y in ((a, b), (b, a)):
        if state.tribes[x].is_player:
            other = state.tribes[y]
            _note(state, LogKind.POLITIQUE, f"Des enfants de {ca.name if x == a else cb.name} epousent ceux de {cb.name if x == a else ca.name}, chef des {other.name}.")


def battle_death(state, band) -> bool:
    """Apres une defaite, le chef de bande peut tomber."""
    if band.leader is None or band.population <= 0:
        return False
    if state.story_rng.random() >= BATTLE_DEATH:
        return False
    leader_dies(state, band, "au combat")
    return True


def band_lines_extra(state, band) -> list[str]:
    """Lignes de la fiche de bande : chef, attachement."""
    if band.leader is None:
        return []
    lead = describe(state, band.leader)
    if is_chief_band(state, band):
        return [f"Chef de la tribu : {lead}"]
    if band.kind == "armee":
        return [f"Chef de guerre : {lead}"]
    out = [f"Clan de {lead}", f"Attachement : {band.loyalty:.0f} ({mood(state, band)})"]
    if gains_autonomy(state, band):
        months = autonomy_months(state, band)
        out[1] += f"  ·  independance {band.autonomy:.0f} % (~{months} mois)"
    if band.notables:
        out[1] += "  ·  anciens : " + ", ".join(p.name for p in band.notables)
    return out


def copy_person(p: Person | None) -> Person | None:
    return copy.copy(p) if p is not None else None


def person_to_json(p: Person | None):
    if p is None:
        return None
    return [p.pid, p.name, p.born, list(p.traits), p.renown]


def person_from_json(data) -> Person | None:
    if not data:
        return None
    return Person(int(data[0]), str(data[1]), int(data[2]), tuple(str(t) for t in data[3]), int(data[4]))


def _note(state, kind, text: str, where=None) -> None:
    state.log.add(kind, text, state.clock.year, state.clock.week, where=where)
