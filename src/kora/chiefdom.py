"""La CHEFFERIE (age des villages) : le grenier du chef, les familles, les
tributaires.

LE GRENIER COMMUN. Le chef preleve une part de chaque recolte (Tribe.levy_rate :
0, 10, 20 ou 30 %) dans le grenier du peuple (Tribe.granary). Il nourrit les
villages en disette (de lui-meme), paie les fetes (feast), les vivres des
troupes levees et le grand monument. Prendre beaucoup (l'accaparement) :
du prestige, des guerriers mieux nourris, mais la stabilite baisse et les
familles grondent ; au-dela, la revolte (situations.Revolte).

LES FAMILLES. 2 a 4 familles comptent (Tribe.families), chacune avec un trait
(riches en betail, maitres potiers, lignee de guerriers, gardiens des rites,
familles marchandes) et une faveur (0 a 100). Le chef leur donne une CHARGE
(garde du grenier, chef de guerre, maitre des echanges, gardien des rites,
maitre des metiers) : la charge fait son effet, plus fort si la famille a le
trait qui va avec et si elle est contente. Une famille ecartee et un
prelevement lourd font baisser la faveur ; une famille furieuse peut partir
avec les siens.

LES TRIBUTAIRES. Un peuple vaincu dans son village (battle.py : le village est
pris, on ne tue pas ses familles) peut etre SOUMIS : il devient tributaire
(diplo, pacte "vassal") ; ou PILLE. Un peuple faible peut aussi se placer
sous la protection d'un plus grand (diplo "proteger" : la force, le
prestige, les mariages). Le tributaire paie chaque mois une part de ses
reserves, suit son suzerain a la guerre (sim.helpers_of) et peut se
revolter quand le suzerain faiblit.

N'importe pas pygame.
"""

from __future__ import annotations

from src.kora.log import LogKind
from src.kora.gamestate import is_human, note

RATES = (0, 10, 20, 30)
DEFAULT_RATE = 10
# Stabilite perdue par point de prelevement (au-dela de rien).
RATE_STABILITY = 0.4
GRANARY_ROT = 0.01
# Une fete : deux semaines de vivres de tous les villageois.
FEAST_WEEKS = 2.0
FEAST_STABILITY = 8
FEAST_TERM = 52
FEAST_PRESTIGE = 3
# Le grenier nourrit un village dont le grenier tombera sous RELIEF_WEEKS.
RELIEF_WEEKS = 2.0
RELIEF_GIVE = 4.0
# Le tributaire paie chaque mois cette part de ce qui depasse 6 semaines.
VASSAL_SHARE = 0.10
REVOLT_UNREST = 40.0

TRAITS = {
    "eleveurs": "Riches en bétail",
    "potiers": "Maîtres potiers",
    "guerriers": "Lignée de guerriers",
    "rites": "Gardiens des rites",
    "marchands": "Familles marchandes",
}
CHARGES = {
    "grenier": "Garde du grenier",
    "guerre": "Chef de guerre",
    "echanges": "Maître des échanges",
    "rites": "Gardien des rites",
    "metiers": "Maître des métiers",
}
CHARGE_TRAIT = {"grenier": "eleveurs", "guerre": "guerriers", "echanges": "marchands", "rites": "rites", "metiers": "potiers"}
CHARGE_TEXT = {
    "grenier": "Le grenier se gâte moins et rentre plus ; la stabilité souffre deux fois moins du prélèvement.",
    "guerre": "Vos troupes ont un meilleur général (+1, +2 pour une lignée de guerriers).",
    "echanges": "Vos ventes sur les routes : +5 % (+10 % pour des familles marchandes).",
    "rites": "Stabilité de vos villages : +3 (+6 pour des gardiens des rites).",
    "metiers": "Production des métiers : +5 % (+12 % pour des maîtres potiers).",
}


def kin_villages(state, tid: int) -> int:
    """Villages freres : ceux des autres peuples de sa civilisation, et ceux
    de ses tributaires."""
    from src.kora.peoples import civ_of

    tribe = state.tribes.get(tid)
    if tribe is None:
        return 0
    civ = civ_of(state, tribe)
    vs = set(vassals_of(state, tid))
    n = 0
    for s in state.sites.values():
        if s.kind != "village" or s.tribe_id == tid or s.tribe_id not in state.tribes:
            continue
        if s.tribe_id in vs or civ_of(state, state.tribes[s.tribe_id]) == civ:
            n += 1
    return n


def kin_of(state, tid: int) -> set:
    """Les peuples freres d'un peuple qui connait Villages freres : ceux de
    sa civilisation qui ne se sont pas razzies l'un l'autre depuis un an, et
    ses tributaires. (Pas la relation : elle compte deja les freres.)"""
    from src.kora import diplo, tech
    from src.kora.peoples import civ_of

    tribe = state.tribes.get(tid)
    if tribe is None or not tech.bonuses(tribe).kin:
        return set()
    civ = civ_of(state, tribe)
    alive = {b.tribe_id for b in state.bands.values() if b.population > 0}
    out = set(vassals_of(state, tid))
    for t, other in state.tribes.items():
        if t == tid or t not in alive or civ_of(state, other) != civ:
            continue
        if diplo._recent_raid(state, tid, t, 52) is None and diplo._recent_raid(state, t, tid, 52) is None:
            out.add(t)
    return out


def split_extra_villages(state) -> None:
    """En cet age, un peuple ne tient qu'un village (anciennes parties : il en
    avait plusieurs). Le village du chef reste le sien ; chacun des autres
    devient un peuple frere, tributaire du premier."""
    from src.kora import chiefs, villages

    for tid in sorted(state.tribes):
        mine = _village_bands(state, tid)
        if len(mine) <= 1:
            continue
        heart = chiefs.chief_band(state, tid)
        keep = heart if heart in mine else max(mine, key=lambda b: (b.population, -b.id))
        for band in sorted(mine, key=lambda b: b.id):
            if band is keep or chiefs.is_chief_band(state, band):
                continue
            site = villages.site_of(state, band)
            new = chiefs.secede(state, band.id, independence=True)
            if not new or site is None:
                continue
            site.tribe_id = band.tribe_id
            tribe = state.tribes[tid]
            tribe.families = [f for f in tribe.families if f.get("village") != site.id]
            make_vassal(state, tid, band.tribe_id, "fondation")
            _note(state, tid, LogKind.POLITIQUE, f"{villages.name(site)} a désormais son propre chef : un village frère, votre tributaire.", site.hex)


def has_chiefdom(state, tid: int) -> bool:
    return any(s.kind == "village" and s.tribe_id == tid for s in state.sites.values())


def _villages(state, tid: int) -> list:
    return sorted((s for s in state.sites.values() if s.kind == "village" and s.tribe_id == tid), key=lambda s: s.id)


def _village_bands(state, tid: int) -> list:
    from src.kora import villages

    out = []
    for site in _villages(state, tid):
        band = villages.band_of(state, site)
        if band is not None and band.population > 0:
            out.append(band)
    return out


# --- les familles -------------------------------------------------------------------


def families(state, tid: int) -> list:
    tribe = state.tribes.get(tid)
    return list(getattr(tribe, "families", None) or []) if tribe is not None else []


def holder(state, tid: int, charge: str):
    return next((f for f in families(state, tid) if f.get("charge") == charge), None)


def charge_power(state, tid: int, charge: str) -> float:
    """0 : personne ; 1 : la charge tenue ; 2 : par la famille qui a le trait
    ; x1,5 si elle est contente (faveur 70 et plus)."""
    fam = holder(state, tid, charge)
    if fam is None:
        return 0.0
    power = 2.0 if fam.get("trait") == CHARGE_TRAIT[charge] else 1.0
    if fam.get("favour", 50) >= 70:
        power *= 1.5
    return power


def war_chief_bonus(state, tid: int) -> int:
    return int(charge_power(state, tid, "guerre"))


def _effect(state, tid: int, charge: str, base: float, matched: float) -> float:
    """L'effet d'une charge : `base`, ou `matched` si la famille a le trait
    qui va avec ; une fois et demie si elle est contente."""
    fam = holder(state, tid, charge)
    if fam is None:
        return 0.0
    v = matched if fam.get("trait") == CHARGE_TRAIT[charge] else base
    return v * (1.5 if fam.get("favour", 50) >= 70 else 1.0)


def trade_mult(state, tid: int) -> float:
    return 1.0 + _effect(state, tid, "echanges", 0.05, 0.10)


def craft_mult(state, tid: int) -> float:
    return 1.0 + _effect(state, tid, "metiers", 0.05, 0.12)


def craft_output(state, site, craft) -> float:
    """Le maitre des metiers aide les artisans, pas les pecheurs
    (systems.CRAFT_OUTPUT)."""
    return 1.0 if craft.food else craft_mult(state, site.tribe_id)


def _make_families(state, tribe) -> None:
    """Les familles qui comptent naissent avec les villages (2, puis une de
    plus tous les deux villages, 4 au plus)."""
    from src.kora.peoples import culture_of, make_name

    want = min(4, 2 + len(_villages(state, tribe.id)) // 2)
    fams = list(tribe.families or [])
    if len(fams) >= want:
        return
    rng = state.story_rng
    mine = _villages(state, tribe.id)
    taken = [f["name"] for f in fams]
    order = sorted(TRAITS)
    while len(fams) < want:
        free = [t for t in order if t not in {f["trait"] for f in fams}] or order
        trait = free[int(rng.random() * len(free)) % len(free)]
        name = make_name(rng, culture_of(tribe), taken)
        taken.append(name)
        nid = 1 + max([f["id"] for f in fams], default=0)
        home = mine[(nid - 1) % len(mine)].id if mine else 0
        fams.append({"id": nid, "name": name, "trait": trait, "charge": "", "favour": 50.0, "village": home})
    tribe.families = fams


def set_charge(state, tid: int, fam_id: int, charge: str) -> str:
    """Donner une charge a une famille ("" : la lui retirer). Celle qui la
    tenait la perd (et le prend mal)."""
    tribe = state.tribes.get(tid)
    if tribe is None:
        return "?"
    fams = tribe.families or []
    fam = next((f for f in fams if f["id"] == fam_id), None)
    if fam is None:
        return "Cette famille n'est plus là"
    if charge and charge not in CHARGES:
        return "?"
    if charge:
        for other in fams:
            if other is not fam and other.get("charge") == charge:
                other["charge"] = ""
                other["favour"] = max(0.0, other["favour"] - 10.0)
    if fam.get("charge") and not charge:
        fam["favour"] = max(0.0, fam["favour"] - 10.0)
    fam["charge"] = charge
    from src.kora import tech

    tech.invalidate()
    if charge:
        return f"La famille {fam['name']} devient {CHARGES[charge].lower()}."
    return f"La famille {fam['name']} n'a plus de charge."


def favour_word(v: float) -> str:
    if v >= 70:
        return "dévouée"
    if v >= 45:
        return "fidèle"
    if v >= 25:
        return "réservée"
    return "furieuse"


# --- le grenier ---------------------------------------------------------------------


def set_rate(state, tid: int, rate: int) -> str:
    tribe = state.tribes.get(tid)
    if tribe is None or rate not in RATES:
        return "?"
    tribe.levy_rate = rate
    from src.kora import tech

    tech.invalidate()
    return f"Le chef prélèvera {rate} % des récoltes." if rate else "Le chef ne prélève plus rien."


def take_from_harvest(state, band, amount: float) -> float:
    """Appele par villages.harvest : la part du chef part au grenier commun.
    Rend ce qui reste au village."""
    tribe = state.tribes.get(band.tribe_id)
    if tribe is None or amount <= 0:
        return amount
    rate = getattr(tribe, "levy_rate", 0)
    if not rate:
        return amount
    take = amount * rate / 100.0
    keep = 1.1 if holder(state, tribe.id, "grenier") else 1.0
    tribe.granary = getattr(tribe, "granary", 0.0) + take * keep
    return amount - take


def granary_pay(state, tid: int, amount: float) -> float:
    """Payer avec le grenier commun ce qu'il peut (rend ce qu'il a paye)."""
    tribe = state.tribes.get(tid)
    if tribe is None or amount <= 0:
        return 0.0
    paid = min(tribe.granary, amount)
    tribe.granary -= paid
    return paid


def feast_cost(state, tid: int) -> float:
    return FEAST_WEEKS * sum(b.population for b in _village_bands(state, tid))


def feast_block(state, tid: int) -> str:
    tribe = state.tribes.get(tid)
    if tribe is None or not has_chiefdom(state, tid):
        return "Il faut un village"
    if state.tick_count < getattr(tribe, "feast_until", -1) - FEAST_TERM + 26:
        return "Une fête a eu lieu il y a peu"
    cost = feast_cost(state, tid)
    if tribe.granary < cost:
        return f"Il faut {cost:.0f} vivres au grenier du chef"
    return ""


def feast(state, tid: int) -> str:
    """Une grande fete : le grenier du chef nourrit tout le peuple ; la
    stabilite monte un an, les familles sont contentes."""
    why = feast_block(state, tid)
    if why:
        return why
    from src.kora.sim import gain_prestige

    tribe = state.tribes[tid]
    tribe.granary -= feast_cost(state, tid)
    tribe.feast_until = state.tick_count + FEAST_TERM
    gain_prestige(state, tribe, FEAST_PRESTIGE)
    for fam in tribe.families or []:
        fam["favour"] = min(100.0, fam["favour"] + 15.0)
    _note(state, tid, LogKind.POLITIQUE, "Grande fête : le grenier du chef nourrit tout le peuple. Les familles s'en souviendront.")
    return "La fête est donnée."


def stability_parts(state, tid: int) -> list[tuple[str, float]]:
    """Ce que la chefferie fait a la stabilite des villages (villages.py)."""
    tribe = state.tribes.get(tid)
    if tribe is None:
        return []
    out = []
    rate = getattr(tribe, "levy_rate", 0)
    if rate:
        cut = RATE_STABILITY * rate * (0.5 if holder(state, tid, "grenier") else 1.0)
        out.append(("Le prélèvement du chef", -round(cut)))
    if state.tick_count < getattr(tribe, "feast_until", -1):
        out.append(("La grande fête", FEAST_STABILITY))
    p = charge_power(state, tid, "rites")
    if p:
        out.append(("Gardien des rites", round(3 * p)))
    angry = sum(1 for f in tribe.families or [] if f.get("favour", 50) < 25)
    if angry:
        out.append(("Des familles furieuses", -4 * angry))
    return out


def army_morale(state, tid: int) -> float:
    """Un chef qui preleve beaucoup nourrit bien ses guerriers."""
    tribe = state.tribes.get(tid)
    return 5.0 if tribe is not None and getattr(tribe, "levy_rate", 0) >= 20 else 0.0


# --- tributaires -----------------------------------------------------------------------


def overlord_of(state, tid: int) -> int:
    from src.kora import diplo

    for (a, b), pacts in getattr(state.diplo, "pacts", {}).items():
        for p in pacts:
            if p.kind == "vassal" and p.payer == tid and tid in (a, b):
                return b if a == tid else a
    return 0


def vassals_of(state, tid: int) -> list[int]:
    out = []
    for (a, b), pacts in getattr(state.diplo, "pacts", {}).items():
        for p in pacts:
            if p.kind == "vassal" and tid in (a, b) and p.payer != tid:
                out.append(p.payer)
    return sorted(set(out))


def make_vassal(state, lord: int, vassal: int, how: str = "force") -> None:
    from src.kora import diplo

    d = state.diplo

    def drop(a: int, b: int, kinds) -> None:
        k = diplo.pair(a, b)
        kept = [p for p in d.pacts.get(k, []) if p.kind not in kinds]
        if kept:
            d.pacts[k] = kept
        else:
            d.pacts.pop(k, None)

    drop(lord, vassal, ("tribut", "treve", "vassal"))
    # Le vaincu change de suzerain : il quitte l'ancien (il garde ses propres
    # tributaires).
    old = overlord_of(state, vassal)
    if old:
        drop(old, vassal, ("vassal",))
    # Pas de cercle : si le vaincu etait au-dessus du vainqueur (son suzerain,
    # ou celui de son suzerain), le vainqueur s'en libere.
    chain = []
    up = overlord_of(state, lord)
    while up and up not in chain:
        chain.append(up)
        up = overlord_of(state, up)
    if vassal in chain:
        # Il conquiert un peuple au-dessus de lui : il se libere de son
        # propre suzerain d'abord.
        drop(lord, chain[0], ("vassal",))
    diplo.add_pact(state, lord, vassal, "vassal", 0, payer=vassal)
    if how == "force":
        diplo.add_mod(state, lord, vassal, "soumis", -15, actor=lord)
    elif how == "fondation":
        diplo.add_mod(state, lord, vassal, "freres", 30, actor=lord)
    lname, vname = state.tribes[lord].name, state.tribes[vassal].name
    _note(state, lord, LogKind.POLITIQUE, f"Les {vname} sont vos tributaires : ils paieront chaque mois et vous suivront à la guerre.")
    _note(state, vassal, LogKind.POLITIQUE, f"Vous voilà tributaires des {lname} : vous leur paierez chaque mois une part de vos réserves.")


def village_taken(state, winner, loser, site_id: int) -> str:
    """Le village de `loser` est pris par `winner` (battle._end). Un joueur
    choisit (carte : soumettre ou piller) ; l'IA decide. Rend le batiment
    perdu (pillage tout de suite)."""
    from src.kora import events
    w, l = winner.tribe_id, loser.tribe_id
    if overlord_of(state, l) == w:
        # Deja son tributaire (il s'etait dresse contre lui) : on pille.
        return conquer(state, w, l, site_id, "piller")
    if is_human(state, w):
        if events.hook(state, "conquete", tribe_id=w, band_id=winner.id, other=l, site_id=site_id):
            return ""
        return conquer(state, w, l, site_id, "piller")
    return conquer(state, w, l, site_id, ai_choice(state, w, l))


def ai_choice(state, w: int, l: int) -> str:
    from src.kora import diplo

    if diplo.relation(state, w, l) < -60:
        return "piller"
    return "soumettre" if has_chiefdom(state, w) else "piller"


def conquer(state, w: int, l: int, site_id: int, choice: str) -> str:
    """Soumettre (tributaire) ou piller le village pris."""
    from src.kora import villages
    from src.kora.sim import gain_prestige

    site = state.sites.get(site_id)
    band = villages.band_of(state, site) if site is not None else None
    if l not in state.tribes or w not in state.tribes:
        return ""
    if choice == "soumettre":
        make_vassal(state, w, l, "force")
        gain_prestige(state, state.tribes[w], 5)
        return ""
    if band is None:
        return ""
    lost = villages.pillaged(state, band, state.story_rng)
    tribe = state.tribes[l]
    if getattr(tribe, "granary", 0.0) > 0:
        stolen = tribe.granary * 0.5
        tribe.granary -= stolen
        lord = state.tribes[w]
        lord.granary = getattr(lord, "granary", 0.0) + stolen
    name = villages.name(site)
    _note(state, w, LogKind.COMBAT, f"{name} est pillé" + (f" ({lost} perdu)." if lost else "."), site.hex)
    _note(state, l, LogKind.COMBAT, f"Les {state.tribes[w].name} pillent {name}" + (f" : {lost} perdu." if lost else "."), site.hex)
    return lost


def protection_power(state, a: int, b: int) -> float:
    from src.kora import diplo

    return diplo.power(state, a) / max(1.0, diplo.power(state, b))


def unrest(state, vassal: int, lord: int) -> float:
    """Ce qui pousse un tributaire a se revolter (0 a 100)."""
    from src.kora import diplo

    u = 0.0
    rel = diplo.relation(state, vassal, lord)
    if rel < 0:
        u += -rel / 2.0
    ratio = protection_power(state, vassal, lord)
    if ratio > 0.8:
        u += 30.0 * min(2.0, ratio / 0.8)
    if state.tribes[lord].prestige < state.tribes[vassal].prestige:
        u += 10.0
    lord_near = any(
        b.tribe_id == lord and b.kind == "armee" and any(state.world.distance(b.position, s.hex) <= 12 for s in _villages(state, vassal))
        for b in state.bands.values()
    )
    if lord_near:
        u -= 20.0
    return max(0.0, min(100.0, u))


def _pay_vassal(state, vassal: int, lord: int) -> float:
    bands = _village_bands(state, vassal) or [b for b in state.bands.values() if b.tribe_id == vassal and b.population > 0]
    paid = 0.0
    for band in sorted(bands, key=lambda b: b.id):
        spare = band.stock - 6.0 * band.population
        if spare > 0:
            take = spare * VASSAL_SHARE
            band.stock -= take
            paid += take
    if paid > 0:
        lord_t = state.tribes[lord]
        if has_chiefdom(state, lord):
            lord_t.granary = getattr(lord_t, "granary", 0.0) + paid
        else:
            from src.kora.sim import stock_max

            mine = [b for b in state.bands.values() if b.tribe_id == lord and b.population > 0]
            if mine:
                t = max(mine, key=lambda b: (stock_max(b, state) - b.stock, -b.id))
                t.stock = min(stock_max(t, state), t.stock + paid)
    return paid


def _revolt(state, vassal: int, lord: int) -> None:
    from src.kora import diplo

    while diplo.has_pact(state, vassal, lord, "vassal"):
        diplo.break_pact(state, vassal, lord, "vassal")
    diplo.add_mod(state, lord, vassal, "revolte", -25, actor=vassal)
    vname, lname = state.tribes[vassal].name, state.tribes[lord].name
    _note(state, lord, LogKind.POLITIQUE, f"Les {vname} se révoltent : ils ne paient plus. À vous de les soumettre à nouveau.")
    _note(state, vassal, LogKind.POLITIQUE, f"Vous rejetez le joug des {lname}.")


# --- le mois ---------------------------------------------------------------------------


def monthly(state) -> None:
    from src.kora import diplo, villages
    from src.kora.sim import gain_prestige
    split_extra_villages(state)
    for tid in sorted(state.tribes):
        tribe = state.tribes[tid]
        if not has_chiefdom(state, tid):
            continue
        _make_families(state, tribe)
        # Le grenier se gate un peu (moins avec son garde).
        if tribe.granary > 0 and not holder(state, tid, "grenier"):
            tribe.granary *= 1.0 - GRANARY_ROT
        # Il nourrit les villages qui vont manquer.
        for band in _village_bands(state, tid):
            site = villages.site_of(state, band)
            if site is None or tribe.granary <= 0:
                continue
            _weeks, margin = villages.food_outlook(state, site, band)
            if margin < RELIEF_WEEKS:
                give = min(tribe.granary, RELIEF_GIVE * band.population)
                if give > 1:
                    from src.kora.sim import stock_max

                    room = max(0.0, stock_max(band, state) - band.stock)
                    give = min(give, room)
                    band.stock += give
                    tribe.granary -= give
                    if state.tick_count % 12 == 0:
                        _note(state, tid, LogKind.SURVIE, f"Le grenier du chef nourrit {villages.name(site)} ({give:.0f} vivres).", site.hex)
        # L'accaparement : du prestige.
        if tribe.levy_rate >= 20 and (state.tick_count // 4) % 2 == 0:
            gain_prestige(state, tribe, 1)
        # Les familles.
        for fam in tribe.families or []:
            f = fam["favour"]
            f += 2.0 if fam.get("charge") else -1.0
            rate = tribe.levy_rate
            if rate > 10:
                f -= (rate - 10) / 10.0 * (0.5 if fam.get("charge") == "grenier" else 1.0)
            elif rate < 10:
                f += 0.5
            if state.tick_count < getattr(tribe, "feast_until", -1):
                f += 1.0
            fam["favour"] = round(max(0.0, min(100.0, f)), 2)
        # Une famille furieuse peut partir avec les siens.
        for fam in list(tribe.families or []):
            if fam["favour"] >= 20:
                continue
            from src.kora.situations import _rand

            if _rand(state, "famille", tid, fam["id"]) < 0.04:
                _family_leaves(state, tribe, fam)
        if not is_human(state, tid):
            _ai(state, tribe)
    # Les tributaires paient ; ceux qui grondent se revoltent.
    for (a, b), pacts in sorted(getattr(state.diplo, "pacts", {}).items()):
        for p in list(pacts):
            if p.kind != "vassal":
                continue
            vassal = p.payer
            lord = b if a == vassal else a
            if vassal not in state.tribes or lord not in state.tribes:
                continue
            paid = _pay_vassal(state, vassal, lord)
            if paid and state.tick_count % 12 == 0:
                _note(state, lord, LogKind.POLITIQUE, f"Le tribut des {state.tribes[vassal].name} : {paid:.0f} vivres.")
            # Qui gronde : une crise du suzerain (situations.RevolteTributaires).
    del diplo


def overthrow(state, tid: int) -> None:
    """Une revolte ratee, dans un peuple d'un seul village : le chef est
    renverse. Un autre prend sa place ; le prelevement est aboli, la moitie
    du grenier revient au village ; le peuple perd du prestige."""
    from src.kora import chiefs, villages

    tribe = state.tribes.get(tid)
    if tribe is None:
        return
    heart = chiefs.chief_band(state, tid)
    tribe.prestige = max(0, tribe.prestige - 15)
    tribe.levy_rate = 0
    give = tribe.granary / 2.0
    tribe.granary -= give
    bands = _village_bands(state, tid)
    if bands:
        bands[0].stock += give
    for fam in tribe.families or []:
        fam["favour"] = max(fam["favour"], 50.0)
    site = villages.site_of(state, bands[0]) if bands else None
    _note(state, tid, LogKind.POLITIQUE, "La révolte l'emporte : le chef est renversé. Le nouveau chef abolit le prélèvement.", site.hex if site else None)
    if heart is not None and heart.leader is not None:
        chiefs.leader_dies(state, heart, "renversé par les siens")


def village_secedes(state, tid: int) -> int:
    """Une revolte ratee : le plus grand village qui n'est pas celui du chef
    fait secession, avec ses familles. Rend le peuple ne (0 : aucun)."""
    from src.kora import chiefs, villages

    tribe = state.tribes.get(tid)
    cands = [b for b in _village_bands(state, tid) if not chiefs.is_chief_band(state, b)]
    if tribe is None or not cands:
        return 0
    band = max(cands, key=lambda b: (b.population, -b.id))
    site = villages.site_of(state, band)
    new = chiefs.secede(state, band.id, independence=True)
    if not new or site is None:
        return 0
    site.tribe_id = band.tribe_id
    tribe.families = [f for f in tribe.families if f.get("village") != site.id]
    _note(state, tid, LogKind.POLITIQUE, f"{villages.name(site)} fait sécession : ses familles ne reconnaissent plus votre chef.", site.hex)
    return new


def _family_leaves(state, tribe, fam) -> None:
    from src.kora import population, villages

    site = state.sites.get(fam.get("village", 0))
    band = villages.band_of(state, site) if site is not None else None
    tribe.families = [f for f in tribe.families if f["id"] != fam["id"]]
    if band is None:
        return
    gone = max(1, round(band.population * 0.08))
    population.kill(band, gone)
    _note(state, tribe.id, LogKind.POLITIQUE, f"La famille {fam['name']}, furieuse, quitte {villages.name(site)} avec les siens ({gone} personnes).", site.hex)


def _ai(state, tribe) -> None:
    """L'IA : son prelevement selon son chef, ses charges aux familles qui
    ont le trait qui va avec."""
    from src.kora import chiefs

    chief = chiefs.chief_of(state, tribe.id)
    traits = chief.traits if chief is not None else ()
    want = 20 if "ambitieux" in traits else 0 if "genereux" in traits else 10
    if tribe.levy_rate != want:
        tribe.levy_rate = want
    fams = tribe.families or []
    free = set(CHARGES) - {f["charge"] for f in fams if f.get("charge")}
    for fam in sorted(fams, key=lambda f: f["id"]):
        if fam.get("charge"):
            continue
        match = next((c for c in sorted(free) if CHARGE_TRAIT[c] == fam["trait"]), None) or (sorted(free)[0] if free else None)
        if match:
            fam["charge"] = match
            free.discard(match)
    if tribe.granary > feast_cost(state, tribe.id) * 3 and not feast_block(state, tribe.id):
        feast(state, tribe.id)


def _note(state, tid: int, kind, text: str, where=None) -> None:
    if tid in state.tribes and is_human(state, tid):
        note(state, kind, text, where, to=tid)


def lines(state, tid: int) -> list[str]:
    tribe = state.tribes.get(tid)
    if tribe is None:
        return []
    out = [f"Grenier du chef : {tribe.granary:.0f} vivres · prélèvement {tribe.levy_rate} %"]
    lord = overlord_of(state, tid)
    if lord:
        out.append(f"Tributaires des {state.tribes[lord].name}")
    vs = vassals_of(state, tid)
    if vs:
        out.append("Tributaires : " + ", ".join(state.tribes[v].name for v in vs if v in state.tribes))
    return out
