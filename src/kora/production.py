"""Le SAVOIR-FAIRE des villages : l'efficacite de la production.

Avec les villages seulement. Chaque genre de production a son efficacite
(Tribe.efficiency, 1,0 au depart, EFF_MAX au plus) :

  collecte      chasse et cueillette autour des villages
  agriculture   la recolte des champs
  peche         les pecheurs
  potiers, sauniers, tisserands, pelletiers, tailleurs   les metiers

Elle monte lentement, un peu chaque mois, quand le peuple a BESOIN de
produire plus : pour la nourriture, quand le grenier sera presque vide a la
prochaine recolte (moins de FOOD_TIGHT_WEEKS semaines, villages.food_outlook) ; pour un bien, quand ce qu'on
en fait ne suffit pas a ce qu'on en use et a ce que les routes voudraient
vendre (la reserve est sous son niveau ou une route de vente part a vide).
Sans besoin, elle ne bouge pas : le savoir-faire durement gagne reste, sauf
une crise (situations.py : la surproduction ratee, l'effondrement du
commerce).

SURPRODUCTION : un bien manufacture dont la reserve deborde (CAP), que l'on
fait bien plus vite qu'on ne l'use ou le vend, avec un savoir-faire eleve :
chaque mois ainsi compte (Tribe.glut). Au bout de GLUT_RISK mois, le joueur
est PREVENU (situations : risque) ; au bout de GLUT_CRISIS, la crise peut
naitre (situations.Surproduction).

N'importe pas pygame.
"""

from __future__ import annotations

KINDS = ("collecte", "agriculture", "peche", "potiers", "sauniers", "tisserands", "pelletiers", "tailleurs")
KIND_NAMES = {
    "collecte": "Chasse et cueillette",
    "agriculture": "Agriculture",
    "peche": "Pêche",
    "potiers": "Poterie",
    "sauniers": "Sel",
    "tisserands": "Tissage",
    "pelletiers": "Peaux et fourrures",
    "tailleurs": "Haches polies",
}
EFF_MAX = 1.30
# Gain par mois sous pleine pression : +0,5 % pour un metier, +0,3 % pour
# la nourriture (les greniers manquent souvent : elle monte plus lentement).
EFF_STEP = 0.005
FOOD_STEP = 0.003
# La nourriture ne pousse que si le grenier tombera sous ce nombre de
# semaines avant la recolte.
FOOD_TIGHT_WEEKS = 3.0
EFF_MIN = 1.0
# Surproduction : reserve pleine a GLUT_FULL de CAP, production au moins
# GLUT_RATIO fois ce qu'on use et vend, savoir-faire au moins GLUT_EFF.
GLUT_FULL = 0.85
GLUT_RATIO = 1.5
GLUT_EFF = 1.08
GLUT_RISK = 3
GLUT_CRISIS = 6


def _villages(state, tid: int) -> list:
    return sorted((s for s in state.sites.values() if s.kind == "village" and s.tribe_id == tid), key=lambda s: s.id)


def efficiency(tribe, kind: str) -> float:
    if tribe is None:
        return 1.0
    eff = getattr(tribe, "efficiency", None)
    return eff.get(kind, 1.0) if eff else 1.0


def of(state, tid: int, kind: str) -> float:
    return efficiency(state.tribes.get(tid), kind)


def craft_kind(cid: str) -> str:
    return "peche" if cid == "pecheurs" else cid


def craft_mult(state, site, craft) -> float:
    """Le savoir-faire du peuple pour ce metier (systems.CRAFT_OUTPUT)."""
    return of(state, site.tribe_id, craft_kind(craft.id))


def adjust(tribe, kind: str, delta: float) -> None:
    """Changer un savoir-faire (borne a EFF_MIN..EFF_MAX)."""
    now = efficiency(tribe, kind)
    new = round(max(EFF_MIN, min(EFF_MAX, now + delta)), 5)
    if new <= EFF_MIN + 1e-9:
        tribe.efficiency.pop(kind, None)
    else:
        tribe.efficiency[kind] = new
    from src.kora import tech

    tech.invalidate()


def demand(state, tid: int, good: str) -> tuple[float, float]:
    """(ce que le peuple use et vend d'un bien par semaine, ce que ses
    routes de vente auraient voulu en plus)."""
    from src.kora import goods

    use = goods.need(state, tid)
    sold = 0.0
    unmet = 0.0
    for r in goods.routes_of(state, tid):
        if r.exporter != tid or r.good != good:
            continue
        sold += r.units
        if r.status == "le vendeur n'a rien de trop":
            unmet += r.level * goods.trade_load(state, r.exporter, r.importer)
    return use + sold / 4.0, unmet / 4.0


def food_pressure(state, tid: int) -> float:
    """0 a 1 : les greniers des villages ne tiendront pas jusqu'a la recolte."""
    from src.kora import villages

    total, weight = 0.0, 0
    for site in _villages(state, tid):
        band = villages.band_of(state, site)
        if band is None or band.population <= 0:
            continue
        _weeks, margin = villages.food_outlook(state, site, band)
        lack = max(0.0, min(1.0, (FOOD_TIGHT_WEEKS - margin) / villages.FOOD_SAFE_WEEKS))
        total += lack * band.population
        weight += band.population
    return total / weight if weight else 0.0


def craft_pressure(state, tid: int, cid: str) -> float:
    """0 a 1 : on ne fait pas assez de ce bien pour ce qu'on en use et vend."""
    from src.kora import goods

    good = goods.CRAFTS[cid].good
    use, unmet = demand(state, tid, good)
    want = use + unmet
    made = goods.made(state, tid, good)
    if want <= 0:
        return 0.0
    short = goods.stock(state, tid, good) < goods.reserve(state, tid) or unmet > 0
    if not short:
        return 0.0
    return max(0.0, min(1.0, 1.0 - made / want))


def glutted(state, tid: int, good: str) -> bool:
    from src.kora import goods

    cid = goods.GOOD_CRAFT[good]
    made = goods.made(state, tid, good)
    if made <= 0:
        return False
    use, _unmet = demand(state, tid, good)
    return (
        goods.stock(state, tid, good) >= goods.CAP * GLUT_FULL
        and made >= GLUT_RATIO * max(use, 0.05)
        and of(state, tid, craft_kind(cid)) >= GLUT_EFF
    )


def active_kinds(state, tid: int) -> list[str]:
    """Les genres de production que ce peuple pratique dans ses villages."""
    from src.kora import goods

    out = {"collecte"}
    for site in _villages(state, tid):
        if site.data.get("fields"):
            out.add("agriculture")
        for cid, n in goods.teams(site).items():
            if n > 0 and cid in goods.CRAFTS:
                out.add(craft_kind(cid))
    return [k for k in KINDS if k in out]


def monthly(state) -> None:
    """Chaque mois : le savoir-faire monte la ou il le faut ; on compte les
    mois de surproduction de chaque bien."""
    from src.kora import goods

    for tid in sorted(state.tribes):
        tribe = state.tribes[tid]
        if not _villages(state, tid):
            continue
        kinds = active_kinds(state, tid)
        food = food_pressure(state, tid)
        for kind in kinds:
            if kind in ("collecte", "agriculture", "peche"):
                push, step = food, FOOD_STEP
            else:
                push, step = craft_pressure(state, tid, kind), EFF_STEP
            if push > 0.05:
                adjust(tribe, kind, step * push)
        for good in goods.GOODS:
            if glutted(state, tid, good):
                tribe.glut[good] = tribe.glut.get(good, 0) + 1
            elif tribe.glut.get(good):
                tribe.glut[good] -= 1
                if tribe.glut[good] <= 0:
                    del tribe.glut[good]


def lines(state, tid: int) -> list[tuple[str, float, str]]:
    """Pour l'ecran : (nom, efficacite, ce qui la pousse) de chaque genre
    pratique."""
    from src.kora import goods

    out = []
    food = food_pressure(state, tid)
    for kind in active_kinds(state, tid):
        eff = of(state, tid, kind)
        if kind in ("collecte", "agriculture", "peche"):
            why = "les greniers manquent : on apprend à en tirer plus" if food > 0.05 else ""
        else:
            push = craft_pressure(state, tid, kind)
            good = goods.CRAFTS[kind].good
            if push > 0.05:
                why = "on en manque pour l'usage et la vente : on apprend à en faire plus"
            elif tribe_glut(state, tid, good) >= GLUT_RISK:
                why = "la réserve déborde : on en fait trop"
            else:
                why = ""
        out.append((KIND_NAMES[kind], eff, why))
    return out


def tribe_glut(state, tid: int, good: str) -> int:
    tribe = state.tribes.get(tid)
    return tribe.glut.get(good, 0) if tribe is not None else 0
