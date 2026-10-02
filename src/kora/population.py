"""Qui sont les gens d'une bande : enfants, hommes, femmes, anciens, blesses.

Chaque bande garde la PART de chaque classe (Band.demo ; vide : la
structure ordinaire STRUCTURE) et le nombre de ses BLESSES (Band.wounded,
des adultes, d'abord des hommes, comptes dans la population). Une baisse
ordinaire de la population (maladie, depart, evenement) garde les parts ;
les changements qui touchent une classe passent par ce module :

  naissances (grow, des enfants), levee et retour des guerriers (take_men,
  add), morts au combat et blessures (kill_fighters, wound), famine (les
  plus faibles d'abord : kill), fusion de deux bandes (mix).

Chaque mois, la structure revient lentement vers STRUCTURE (les enfants
grandissent, les adultes vieillissent) et les blesses guerissent (ou
meurent).

Ce qui en sort :
  - les COMBATTANTS : les hommes valides (fit_men) ; une troupe n'a que des
    hommes ;
  - les LEVABLES : une part des hommes valides seulement (LEVY_MAX) ; les
    enfants, les femmes, les anciens et les blesses ne partent pas ;
  - les BRAS (workers) : les adultes valides, pour les champs et les
    metiers (labor_pop : en "population equivalente", pour que la
    structure ordinaire donne ce que donnait toute la population).

N'importe pas pygame.
"""

from __future__ import annotations

CLASSES = ("enfants", "hommes", "femmes", "anciens")
NAMES = {"enfants": "Enfants", "hommes": "Hommes", "femmes": "Femmes", "anciens": "Anciens", "blesses": "Blessés"}
# La structure d'un peuple du temps : beaucoup d'enfants, peu d'anciens.
STRUCTURE = {"enfants": 0.32, "hommes": 0.27, "femmes": 0.29, "anciens": 0.12}
ARMY = {"hommes": 1.0}
# Une part des hommes valides seulement peut partir en guerre (les autres
# chassent, gardent, travaillent). Plus tard : les lois.
LEVY_MAX = 0.7
# Les adultes valides de la structure ordinaire (pour labor_pop).
ACTIVE_NORM = STRUCTURE["hommes"] + STRUCTURE["femmes"]
# Chaque mois : la structure revient vers STRUCTURE de cette part ; les
# blesses guerissent (HEAL) ou meurent (WOUND_DEATH).
DRIFT = 0.03
HEAL = 0.3
WOUND_DEATH = 0.04
# La faim tue d'abord les plus faibles.
FAMINE_WEIGHTS = {"enfants": 1.4, "hommes": 0.7, "femmes": 0.8, "anciens": 1.8}


def shares(band) -> dict:
    demo = getattr(band, "demo", None)
    if demo:
        return demo
    return ARMY if band.kind == "armee" else STRUCTURE


def counts(band) -> dict:
    """Les gens de la bande par classe (entiers, leur somme = population),
    et les blesses (parmi les adultes)."""
    pop = max(0, band.population)
    sh = shares(band)
    raw = {c: pop * sh.get(c, 0.0) for c in CLASSES}
    out = {c: int(raw[c]) for c in CLASSES}
    left = pop - sum(out.values())
    for c in sorted(CLASSES, key=lambda c: (-(raw[c] - out[c]), CLASSES.index(c)))[: max(0, left)]:
        out[c] += 1
    hurt = min(max(0, getattr(band, "wounded", 0)), out["hommes"] + out["femmes"])
    out["blesses"] = hurt
    return out


def fit_men(band) -> int:
    c = counts(band)
    return max(0, c["hommes"] - min(c["blesses"], c["hommes"]))


def men_force(band) -> float:
    """Les hommes valides, sans arrondi (calculs de force : une petite bande
    ne doit pas sauter d'un combattant a l'autre)."""
    if band.kind == "armee":
        return float(max(0, band.population - getattr(band, "wounded", 0)))
    men = band.population * shares(band).get("hommes", 0.0)
    return max(0.0, men - min(getattr(band, "wounded", 0), men))


def women_force(band) -> float:
    women = band.population * shares(band).get("femmes", 0.0)
    men = band.population * shares(band).get("hommes", 0.0)
    over = max(0.0, getattr(band, "wounded", 0) - men)
    return max(0.0, women - over)


def fit_women(band) -> int:
    c = counts(band)
    over = max(0, c["blesses"] - c["hommes"])
    return max(0, c["femmes"] - over)


def workers(band) -> int:
    """Les adultes valides : les bras des champs, de la chasse, des metiers."""
    return fit_men(band) + fit_women(band)


def labor_pop(band) -> float:
    """Les bras, comptes comme une population ordinaire (la structure
    STRUCTURE donne exactement band.population)."""
    if band.kind == "armee":
        return float(workers(band))
    return workers(band) / ACTIVE_NORM


def levable(band) -> int:
    """Les hommes qui peuvent partir en guerre (une part des valides)."""
    if band.kind == "armee":
        return 0
    return int(fit_men(band) * LEVY_MAX)


def _set(band, by_class: dict) -> None:
    total = sum(max(0.0, v) for v in by_class.values())
    if total <= 0:
        band.demo = {}
        return
    band.demo = {c: round(max(0.0, by_class.get(c, 0.0)) / total, 6) for c in CLASSES if by_class.get(c, 0.0) > 0}


def _amounts(band) -> dict:
    sh = shares(band)
    return {c: band.population * sh.get(c, 0.0) for c in CLASSES}


def grow(band, n: int, who: str = "enfants") -> None:
    """n personnes de plus, toutes de cette classe (naissances : enfants)."""
    if n <= 0:
        return
    amounts = _amounts(band)
    amounts[who] = amounts.get(who, 0.0) + n
    band.population += n
    _set(band, amounts)


def add(band, n: int, who: str = "hommes", wounded: int = 0) -> None:
    """Des gens qui arrivent (guerriers qui rentrent : des hommes, et leurs
    blesses)."""
    grow(band, n, who)
    if wounded:
        band.wounded = getattr(band, "wounded", 0) + min(wounded, n)


def take_men(band, n: int) -> int:
    """La levee : n hommes valides quittent la bande (rend combien)."""
    n = max(0, min(n, fit_men(band)))
    if n <= 0:
        return 0
    amounts = _amounts(band)
    amounts["hommes"] = max(0.0, amounts["hommes"] - n)
    band.population -= n
    _set(band, amounts)
    return n


def kill(band, n: int, weights: dict | None = None) -> int:
    """n morts, repartis entre les classes selon leur nombre et `weights`
    (la faim : les faibles d'abord). Rend le nombre de morts."""
    n = max(0, min(n, band.population))
    if n <= 0:
        return 0
    if band.kind == "armee" or not weights:
        band.population -= n
        band.wounded = min(getattr(band, "wounded", 0), max(0, band.population))
        return n
    amounts = _amounts(band)
    w = {c: amounts[c] * weights.get(c, 1.0) for c in CLASSES}
    total = sum(w.values()) or 1.0
    for c in CLASSES:
        amounts[c] = max(0.0, amounts[c] - n * w[c] / total)
    band.population -= n
    _set(band, amounts)
    band.wounded = min(getattr(band, "wounded", 0), max(0, band.population))
    return n


def kill_fighters(band, n: int) -> int:
    """Morts au combat : des hommes valides (une troupe : ses guerriers)."""
    if band.kind == "armee":
        n = max(0, min(n, band.population - getattr(band, "wounded", 0)))
        band.population -= n
        return n
    n = max(0, min(n, fit_men(band)))
    if n <= 0:
        return 0
    amounts = _amounts(band)
    amounts["hommes"] = max(0.0, amounts["hommes"] - n)
    band.population -= n
    _set(band, amounts)
    return n


def wound(band, n: int) -> int:
    """Des combattants blesses : ils ne se battent plus, ne travaillent plus,
    jusqu'a guerir."""
    if band.kind == "armee":
        n = max(0, min(n, band.population - getattr(band, "wounded", 0)))
    else:
        n = max(0, min(n, fit_men(band)))
    band.wounded = getattr(band, "wounded", 0) + n
    return n


def lose_wounded(band, n: int) -> int:
    """n blesses meurent (ou restent sur le terrain) : des hommes. Rend leur
    nombre. Une troupe : ses compagnies perdent des hommes (units.remove)."""
    n = max(0, min(n, getattr(band, "wounded", 0), band.population))
    if n <= 0:
        return 0
    band.wounded -= n
    if band.kind == "armee":
        if band.units:
            from src.kora import units

            units.remove(band, n)
        else:
            band.population -= n
        return n
    amounts = _amounts(band)
    amounts["hommes"] = max(0.0, amounts["hommes"] - n)
    band.population -= n
    _set(band, amounts)
    return n


def mix(keep, gone) -> None:
    """Deux bandes qui se reunissent : leurs gens et leurs blesses (a
    appeler AVANT d'ajouter gone.population a keep)."""
    a, b = _amounts(keep), _amounts(gone)
    _set(keep, {c: a[c] + b[c] for c in CLASSES})
    keep.wounded = getattr(keep, "wounded", 0) + getattr(gone, "wounded", 0)


def split_wounded(band, new, moved: int, before: int) -> None:
    """Une bande qui se divise : la nouvelle part avec les memes parts et sa
    part des blesses."""
    new.demo = dict(band.demo) if band.demo else {}
    hurt = getattr(band, "wounded", 0)
    take = int(round(hurt * moved / max(1, before)))
    new.wounded = take
    band.wounded = hurt - take


def monthly(state) -> None:
    """Les enfants grandissent, les adultes vieillissent (retour lent a la
    structure ordinaire) ; les blesses guerissent ou meurent."""
    for band in sorted(state.bands.values(), key=lambda b: b.id):
        if band.population <= 0:
            continue
        hurt = min(getattr(band, "wounded", 0), band.population)
        if hurt:
            dead = int(round(hurt * WOUND_DEATH))
            healed = max(1, int(round(hurt * HEAL)))
            lose_wounded(band, dead)
            band.wounded = max(0, min(band.wounded - healed, band.population))
        if band.kind == "armee" or not band.demo:
            continue
        amounts = _amounts(band)
        _set(band, {c: amounts[c] + (STRUCTURE[c] * band.population - amounts[c]) * DRIFT for c in CLASSES})
        if all(abs(band.demo.get(c, 0.0) - STRUCTURE[c]) < 0.002 for c in CLASSES):
            band.demo = {}


def lines(band) -> list[str]:
    """Pour l'ecran : qui sont les gens de la bande."""
    c = counts(band)
    parts = [f"{c[k]} {NAMES[k].lower()}" for k in ("enfants", "hommes", "femmes", "anciens") if c[k]]
    out = [" · ".join(parts)]
    extra = []
    if c["blesses"]:
        extra.append(f"{c['blesses']} blessés")
    if band.kind != "armee" and band.village:
        extra.append(f"{levable(band)} hommes levables")
    if extra:
        out.append(" · ".join(extra))
    return out


# --- qui fait quoi : les metiers de la population active ---------------------------
#
# Les adultes valides travaillent : la chasse (des hommes), la cueillette
# (des femmes), les champs (les deux), les metiers (chacun selon son metier),
# et, le temps d'une levee, la guerre (des hommes : soldat est un metier tant
# que la troupe existe ; dissoute, ils retournent a leurs autres travaux).

# Les metiers et le sexe de ceux qui les font ("" : les deux).
CRAFT_SEX = {"potiers": "femmes", "tisserands": "femmes", "tailleurs": "hommes", "pecheurs": "hommes", "sauniers": "", "pelletiers": "", "calculateurs": "", "mineurs": "hommes"}
CRAFT_WORKERS = {"potiers": "potières", "tisserands": "tisserandes", "tailleurs": "tailleurs de silex", "pecheurs": "pêcheurs", "sauniers": "sauniers", "pelletiers": "pelletiers", "calculateurs": "calculateurs", "mineurs": "mineurs"}
SEX_WORD = {"hommes": "des hommes", "femmes": "des femmes", "": "hommes et femmes"}


def _craft_take(cid: str, need: int, men: int, women: int) -> tuple[int, int]:
    """(hommes, femmes) pris par une equipe de ce metier."""
    sex = CRAFT_SEX.get(cid, "")
    if sex == "hommes":
        return min(need, men), 0
    if sex == "femmes":
        return 0, min(need, women)
    m = min(men, need // 2)
    w = min(women, need - m)
    m = min(men, need - w)
    return m, w


def occupations(state, band) -> dict:
    """Qui fait quoi dans une bande : {"chasse", "cueillette", "champs",
    "metiers" (metier -> gens), "soldats" (partis a la guerre), "valides"}."""
    men, women = fit_men(band), fit_women(band)
    out = {"chasse": 0, "cueillette": 0, "champs": 0, "metiers": {}, "soldats": 0, "valides": men + women}
    if band.kind == "armee":
        out["soldats"] = men
        return out
    if band.village:
        from src.kora import goods, villages

        site = villages.site_of(state, band)
        if site is not None:
            for cid, n in sorted(goods.teams(site).items()):
                if n <= 0 or cid not in goods.CRAFTS:
                    continue
                m, w = _craft_take(cid, goods.TEAM * n, men, women)
                men -= m
                women -= w
                out["metiers"][cid] = m + w
            fields = len(site.data.get("fields", []))
            need = int(round(fields * villages.FIELD_HANDS * ACTIVE_NORM))
            free = men + women
            take = min(need, free)
            if take > 0 and free > 0:
                m = int(round(take * men / free))
                w = take - m
                men -= m
                women -= w
                out["champs"] = take
            out["soldats"] = sum(
                u[1] for a in state.bands.values() if a.kind == "armee" and a.tribe_id == band.tribe_id for u in a.units if u[2] == site.id
            )
    out["chasse"] = men
    out["cueillette"] = women
    return out


def free_for_craft(state, band, cid: str) -> int:
    """Combien de gens du bon sexe pourraient encore entrer a ce metier."""
    from src.kora import goods, villages

    men, women = fit_men(band), fit_women(band)
    site = villages.site_of(state, band)
    if site is not None:
        for other, n in sorted(goods.teams(site).items()):
            if n <= 0 or other not in goods.CRAFTS:
                continue
            m, w = _craft_take(other, goods.TEAM * n, men, women)
            men -= m
            women -= w
    sex = CRAFT_SEX.get(cid, "")
    return men if sex == "hommes" else women if sex == "femmes" else men + women


def occupation_lines(state, band) -> list[str]:
    o = occupations(state, band)
    parts = []
    if o["chasse"]:
        parts.append(f"{o['chasse']} à la chasse")
    if o["cueillette"]:
        parts.append(f"{o['cueillette']} à la cueillette")
    if o["champs"]:
        parts.append(f"{o['champs']} aux champs")
    for cid, n in o["metiers"].items():
        parts.append(f"{n} {CRAFT_WORKERS.get(cid, cid)}")
    if o["soldats"] and band.kind != "armee":
        parts.append(f"{o['soldats']} à la guerre")
    return [" · ".join(parts)] if parts else []

