"""LE RAVAGE : la guerre qui aboutit sans prendre les murs (0.29.0 ; sa
demande du 2026-11-14, apres la review : "la guerre", la piste M1).

Une levee ne prend pas un village fortifie (elle vaut 12 % de sa defense :
2026-11-13-review-profondeur-mesures.txt) ; les guerres se declaraient
puis s'eteignaient a 0-0. Comme au neolithique, on ne prend pas les murs :
on RUINE ce qui est dehors, jusqu'a ce que l'autre sorte ou plie.

  RAVAGER : une troupe postee a RANGE cases d'un village ennemi (la guerre
    declaree, ou une hostilite ouverte sans la diplomatie : siege.at_war),
    qui ne marche pas, avec l'ordre de ravager (Band.ravage : le lieu).
    Chaque semaine (weekly, systems.WEEKLY) :
      - LES CHAMPS : la recolte sur pied perd STEP par semaine pour MEN
        guerriers (STEP_MAX au plus, x FIRE avec Torches et brandons),
        jusqu'a MAX (VillageData.ravaged ; villages.expected_harvest le
        lit ; les semailles et la recolte le remettent a zero) ;
      - LE VILLAGE ne s'eloigne plus de ses murs : il ne trouve dehors que
        FOOD de ses vivres (food_mult, systems.VILLAGE_FORAGE) ;
      - LE TROUPEAU (un enclos) : HERD_CHANCE par semaine de l'emmener (la
        moitie avec une tour de guet : on rentre les betes a temps) ;
        l'enclos reste vide HERD_WEEKS semaines, la troupe gagne HERD_FOOD
        vivres par niveau ;
      - LA TROUPE vit sur le pays ennemi : LIVE ration par guerrier ;
      - L'AVANTAGE dans la guerre : +SCORE par semaine pour MEN guerriers
        ou plus (moins pour une poignee d'hommes ; guerre.add_score),
        +HERD_SCORE pour un troupeau ; il mene a la soumission ou au tribut
        (guerre.submit_verdict, diplo "tribut", casus : l'IA les exige) ;
      - la stabilite du village baisse (stability_parts).
    La troupe qui part, qui marche, la paix : le ravage cesse.
  LA SORTIE : le village leve ses hommes et attaque la troupe dans ses
    champs (une bataille en terrain ouvert, sans les murs) : l'IA le fait
    si elle la battrait (sortie_force, ai.py) ; le joueur recoit une carte
    ("ravage_subi" : sortir, tenir, payer un tribut).
  LA REDDITION : un village ASSIEGE (siege.py) et affame SURRENDER_WEEKS
    semaines de suite ouvre ses portes : il est pris sans assaut
    (chiefdom.village_taken : soumis ou pille).

L'IA (ai.py) : en guerre, un village leve pour ravager le village ennemi
dont il battrait la sortie (dares) ; la troupe se poste dans ses champs,
ravage tant qu'elle tient, se replie devant plus fort. Les donnees :
VillageData.ravage (semaines), ravager, ravaged, herd_lost, starved ;
Band.ravage. N'importe pas pygame.
"""

from __future__ import annotations

from src.kora import points
from src.kora import batiments, battle, chiefdom, diplo, events, guerre, places, siege, tech, troupes
from src.kora.bands import is_shielded, set_goto, set_march_to_band, stock_max
from src.kora.gamestate import is_human, note
from src.kora.log import LogKind
from src.kora.types import stay_order

# A portee des champs (villages.FIELD_RADIUS).
RANGE = 3
MEN = 20
STEP = 0.10
STEP_MAX = 0.20
MAX = 0.75
FIRE = 1.5
FOOD = 0.7
LIVE = 0.8
SCORE = 3.0
HERD_CHANCE = 0.25
HERD_TOWER = 0.5
HERD_WEEKS = 52
HERD_FOOD = 120.0
HERD_SCORE = 5.0
STABILITY = -6.0
HERD_STABILITY = -2.0
RELATION = -15
SURRENDER_WEEKS = 3
# Le joueur est prevenu de l'avancee du ravage toutes les TELL_EVERY semaines.
TELL_EVERY = 4


# --- qui ravage quoi -------------------------------------------------------------------


def _village_at_war(state, band, site) -> bool:
    return site is not None and site.kind == "village" and site.tribe_id != band.tribe_id and siege.at_war(state, band.tribe_id, site.tribe_id)


def target_of(state, band):
    """Le village ennemi que cette troupe peut ravager d'ou elle est : le
    plus proche a RANGE cases (None : aucun)."""
    best, best_d = None, None
    for site in sorted(state.sites.values(), key=lambda s: s.id):
        if not _village_at_war(state, band, site) or places.band_of(state, site) is None:
            continue
        d = points.lieux(state.world, band, site)
        if d <= RANGE and (best_d is None or d < best_d):
            best, best_d = site, d
    return best


def block(state, band) -> str:
    """Pourquoi cette troupe ne peut pas ravager ("" : elle le peut)."""
    if band is None or band.kind != "armee":
        return "Seule une troupe ravage"
    if band.homebound:
        return "Dissoute, la troupe rentre au village"
    if band.retreating:
        return "La troupe est en repli"
    if target_of(state, band) is not None:
        return ""
    for site in sorted(state.sites.values(), key=lambda s: s.id):
        if site.kind == "village" and site.tribe_id != band.tribe_id and points.lieux(state.world, band, site) <= RANGE:
            who = state.tribes[site.tribe_id].name if site.tribe_id in state.tribes else "?"
            return f"Vous êtes en paix avec les {who} : déclarez-leur d'abord la guerre (écran Peuples)"
    return f"Aucun village ennemi à {RANGE} cases : postez la troupe dans ses champs"


def start(state, band) -> str:
    """La troupe se met a ravager le village a sa portee ; rend son nom."""
    site = target_of(state, band)
    if site is None:
        return ""
    band.ravage = site.id
    band.path = []
    band.order = stay_order()
    return places.name(site)


def send(state, band, site, max_nodes: int = 2000, max_cost: int | None = None) -> bool:
    """La troupe part ravager ce village : elle va se poster a cote de lui ;
    le ravage commence a son arrivee (weekly). Rend False sans chemin."""
    d = points.lieux(state.world, band, site)
    if 0 < d <= RANGE:
        band.ravage = site.id
        band.order = stay_order()
        band.path = []
        return True
    spot = next(
        (h for h in sorted(state.world.neighbors(site.hex), key=lambda h: (points.lieux(state.world, h, band), h.q, h.r)) if state.world.passable(h)),
        None,
    )
    if spot is None:
        return False
    if max_cost is None:
        set_goto(state, band.id, spot, max_nodes=max_nodes)
    else:
        set_goto(state, band.id, spot, max_nodes=max_nodes, max_cost=max_cost)
    if not band.path:
        return False
    band.ravage = site.id
    return True


def stop(band) -> None:
    band.ravage = 0


def toggle(state, band) -> str:
    """L'ordre du joueur (orders.perform) : ravager, ou cesser."""
    if band.ravage:
        stop(band)
        return "La troupe cesse de ravager."
    name = start(state, band)
    return f"La troupe ravage les champs de {name}." if name else block(state, band)


def _posted(state, band, site) -> bool:
    """La troupe est encore la pour ravager ce village (une bataille en
    cours la retient sans lui faire lacher son ordre)."""
    if band.kind != "armee" or band.population <= 0 or band.homebound or band.retreating or band.path:
        return False
    if points.lieux(state.world, band, site) > RANGE:
        return False
    return _village_at_war(state, band, site)


def ravagers(state, site) -> list:
    """Les troupes qui ravagent ce village cette semaine (pas celles qu'une
    bataille occupe)."""
    out = [
        b for b in state.bands.values()
        if b.ravage == site.id and _posted(state, b, site) and not battle.in_battle(state, b)
    ]
    return sorted(out, key=lambda b: b.id)


def foes_at(state, site) -> list:
    """Les troupes ennemies devant ce village : celles qui le ravagent ou
    l'assiegent (la sortie les vise)."""
    seen = {b.id: b for b in ravagers(state, site)}
    for b in siege.besiegers(state, site):
        seen.setdefault(b.id, b)
    return [seen[k] for k in sorted(seen)]


# --- ce que le ravage fait au village ---------------------------------------------------


def food_mult(state, site) -> float:
    """Les vivres que le village trouve dehors (systems.VILLAGE_FORAGE) : on ne
    s'eloigne plus des murs ; un troupeau vole ne donne plus rien. Assiege,
    le village est deja enferme (siege.food_mult)."""
    mult = 1.0
    if site.data.ravage > 0 and not site.data.siege:
        mult *= FOOD
    if site.data.herd_lost > state.tick_count:
        mult /= max(1.0, batiments.value(site, "enclos", "vivres", 1.0))
    return mult


def stability_parts(state, tribe_id: int) -> list[tuple[str, float]]:
    """Ce que le ravage fait a la stabilite (systems.STABILITY)."""
    out = []
    for site in state.sites.values():
        if site.kind != "village" or site.tribe_id != tribe_id:
            continue
        if site.data.ravage > 0 or site.data.ravaged >= 0.2:
            out.append(("Champs ravagés", STABILITY))
        if site.data.herd_lost > state.tick_count:
            out.append(("Troupeau volé", HERD_STABILITY))
        break
    return out


def _step(state, here) -> float:
    men = sum(battle.fighters_now(b, True) for b in here)
    fire = FIRE if any(tech.bonuses(state.tribes[b.tribe_id]).siege_fire for b in here if b.tribe_id in state.tribes) else 1.0
    return min(STEP_MAX, STEP * fire * men / MEN)


def _tell(state, tids, text: str, where) -> None:
    for tid in sorted(set(tids)):
        if tid and is_human(state, tid):
            note(state, LogKind.COMBAT, text, where, to=tid)


def _herd(state, site, here, by: int) -> None:
    if places.level(site, "enclos") <= 0 or site.data.herd_lost > state.tick_count:
        return
    men = sum(battle.fighters_now(b, True) for b in here)
    chance = HERD_CHANCE * min(1.5, men / MEN) * (HERD_TOWER if places.has(site, "tour") else 1.0)
    if state.rng.random() >= chance:
        return
    site.data.herd_lost = state.tick_count + HERD_WEEKS
    food = HERD_FOOD * places.level(site, "enclos")
    army = here[0]
    army.stock = min(stock_max(army, state), army.stock + food)
    guerre.add_score(state, by, site.tribe_id, HERD_SCORE)
    who = state.tribes[by].name
    _tell(state, [site.tribe_id], f"Les {who} emmènent le troupeau de {places.name(site)} : l'enclos restera vide un an.", site.hex)
    _tell(state, [by], f"Votre troupe emmène le troupeau de {places.name(site)} : {food:.0f} vivres.", site.hex)


def _ravage_week(state, site, band, here) -> None:
    data = site.data
    by = here[0].tribe_id
    first = data.ravage == 0
    data.ravage += 1
    data.ravager = by
    victim = site.tribe_id
    name = places.name(site)
    who = state.tribes[by].name
    if data.sown_ratio > 0 and data.fields:
        data.ravaged = round(min(MAX, data.ravaged + _step(state, here)), 3)
    for army in here:
        army.stock = min(stock_max(army, state), army.stock + LIVE * army.population)
    _herd(state, site, here, by)
    # L'avantage : une poignee d'hommes ne pese pas comme une troupe.
    men = sum(battle.fighters_now(b, True) for b in here)
    guerre.add_score(state, by, victim, round(SCORE * min(1.0, men / MEN), 2))
    # Un ravage est un acte de guerre : la guerre ne s'eteint pas, et sans la
    # diplomatie les deux peuples se savent ennemis.
    diplo.make_contact(state, by, victim, quiet=True)
    diplo.of(state).raids[(by, victim)] = (state.tick_count, True)
    if first:
        diplo.add_mod(state, by, victim, "ravage", RELATION, actor=by)
        _tell(state, [by], f"Votre troupe ravage les champs de {name}.", site.hex)
        if is_human(state, victim):
            if not events.hook(state, "ravage_subi", tribe_id=victim, band_id=band.id, other=by, site_id=site.id):
                _tell(state, [victim], f"Les {who} ravagent les champs de {name} : sortez les chasser, ou la récolte brûlera.", site.hex)
    elif data.ravage % TELL_EVERY == 0:
        lost = f" : {round(100 * data.ravaged)} % de la récolte perdue" if data.ravaged > 0 else ""
        _tell(state, [victim], f"Les {who} ravagent toujours les champs de {name}{lost}.", site.hex)
        _tell(state, [by], f"Les champs de {name} sont ravagés depuis {data.ravage} semaines{lost}.", site.hex)


def _surrender(state, site, band) -> None:
    """Le village assiege et affame ouvre ses portes : pris sans assaut."""
    winners = siege.besiegers(state, site)
    if not winners:
        return
    winner = max(winners, key=lambda b: (battle.band_force(state, b), -b.id))
    name = places.name(site)
    who = state.tribes[winner.tribe_id].name
    data = site.data
    data.siege = data.besieger = data.starved = 0
    data.ravage = data.ravager = 0
    for b in winners:
        b.ravage = 0
    band.shield_until = state.tick_count + battle.VILLAGE_SHIELD
    _tell(state, [site.tribe_id], f"{name}, affamé, ouvre ses portes aux {who}.", site.hex)
    _tell(state, [winner.tribe_id], f"{name}, affamé, vous ouvre ses portes.", site.hex)
    if winner.tribe_id in state.tribes and band.tribe_id in state.tribes:
        chiefdom.village_taken(state, winner, band, site.id)


def weekly(state) -> None:
    """Chaque semaine (apres les marches et les sieges) : les ravages
    commencent, durent ou cessent ; les villages assieges et affames se
    rendent."""
    posted: dict = {}
    for b in sorted(state.bands.values(), key=lambda b: b.id):
        if not b.ravage:
            continue
        site = state.sites.get(b.ravage)
        if site is None or b.kind != "armee" or b.population <= 0 or b.homebound or b.retreating or not _village_at_war(state, b, site):
            b.ravage = 0
            continue
        if b.path:
            # En route vers ses champs : l'ordre tient, le ravage attend.
            continue
        if points.lieux(state.world, b, site) > RANGE:
            b.ravage = 0
            continue
        posted.setdefault(site.id, []).append(b)
    for site in sorted(state.sites.values(), key=lambda s: s.id):
        if site.kind != "village":
            continue
        band = places.band_of(state, site)
        if band is None:
            continue
        data = site.data
        there = posted.get(site.id, [])
        if there and is_shielded(state, band):
            # Le village vient d'etre pris (son repit) : on ne le ravage plus.
            for b in there:
                b.ravage = 0
            there = []
        here = [b for b in there if not battle.in_battle(state, b)]
        if here:
            _ravage_week(state, site, band, here)
        elif data.ravage and not there:
            _tell(state, [site.tribe_id, data.ravager], f"Le ravage des champs de {places.name(site)} a cessé.", site.hex)
            data.ravage = data.ravager = 0
        if data.siege > 0 and not is_shielded(state, band):
            hungry = band.stock < 0.5 * band.population or band.famine_tick >= state.tick_count - 1
            data.starved = data.starved + 1 if hungry else 0
            if data.starved >= SURRENDER_WEEKS:
                _surrender(state, site, band)
        elif data.starved:
            data.starved = 0


# --- ce que l'IA en pense (ai.py) -------------------------------------------------------


def sortie_force(state, village) -> float:
    """La force que ce village mettrait dehors pour chasser une troupe de ses
    champs : tous ses levables, et ses troupes deja levees qui sont chez
    elles."""
    site = places.site_of(state, village)
    force = troupes.levy_size(village, troupes.LEVY_SHARE["masse"], state) * battle.band_quality(state, village)
    if site is not None:
        for army in troupes.armies_of(state, site):
            if not army.homebound and points.lieux(state.world, army, site) <= troupes.ARMY_HOME:
                force += battle.band_force(state, army)
    return force


def field_force(state, band, share: float | None = None) -> float:
    """La force que ce peuple met dans les champs de l'autre : sa troupe, ou
    la levee que ferait son village (share : la part des levables)."""
    if band.kind == "armee":
        return battle.band_force(state, band)
    part = troupes.LEVY_SHARE["masse"] if share is None else share
    return troupes.levy_size(band, part, state) * battle.band_quality(state, band)


def dares(state, band, prey, edge: float) -> bool:
    """Cette troupe (ou la levee de ce village) tiendrait-elle dans les
    champs de `prey` (un village) si celui-ci sortait ?"""
    return field_force(state, band) >= edge * max(1.0, sortie_force(state, prey))


def worth(state, site) -> bool:
    """Y a-t-il encore quelque chose a ravager ici : une recolte sur pied, un
    troupeau, ou des gens a enfermer."""
    data = site.data
    crop = data.sown_ratio > 0 and bool(data.fields) and data.ravaged < MAX
    herd = places.level(site, "enclos") > 0 and data.herd_lost <= state.tick_count
    return crop or herd or data.ravage < 2 * TELL_EVERY


def sortie(state, village):
    """Le village sort : il leve tous ses hommes et marche sur la troupe qui
    est dans ses champs. Rend la troupe levee (None : il ne peut pas)."""
    site = places.site_of(state, village)
    foes = foes_at(state, site) if site is not None else []
    if not foes:
        return None
    army = troupes.raise_army(state, village.id, troupes.LEVY_SHARE["masse"])
    if army is None:
        army = troupes.raise_army(state, village.id, troupes.LEVY_SHARE["troupe"])
    if army is None:
        # Des hommes deja leves, restes au village : ce sont eux qui sortent.
        army = next(
            (a for a in troupes.armies_of(state, site) if a.tribe_id == village.tribe_id and not a.homebound and not a.retreating and not battle.in_battle(state, a)),
            None,
        )
    if army is None:
        return None
    foe = max(foes, key=lambda b: (battle.band_force(state, b), -b.id))
    set_march_to_band(state, army.id, foe.id)
    return army


# --- ce que l'ecran en dit --------------------------------------------------------------


def lines(state, site) -> list[str]:
    """Pour la fiche du village."""
    data = site.data
    out = []
    if data.ravage > 0:
        who = state.tribes.get(data.ravager)
        name = who.name if who is not None else "?"
        food = "" if data.siege else f" : on ne s'éloigne plus des murs (vivres trouvés x{FOOD:.1f})".replace(".", ",")
        out.append(f"Champs ravagés par les {name} depuis {data.ravage} sem.{food}")
    if data.ravaged > 0:
        out.append(f"Récolte sur pied : {round(100 * data.ravaged)} % perdue")
    left = data.herd_lost - state.tick_count
    if left > 0:
        out.append(f"Troupeau volé : l'enclos reste vide encore {left} sem.")
    if data.siege > 0 and data.starved > 0:
        out.append(f"La faim derrière les murs : {data.starved} sem. sur {SURRENDER_WEEKS} avant la reddition")
    return out


def band_lines(state, band) -> list[str]:
    """Pour la fiche d'une troupe."""
    site = state.sites.get(band.ravage) if band.ravage else None
    if site is None:
        return []
    lost = f" ({round(100 * site.data.ravaged)} % de la récolte perdue)" if site.data.ravaged > 0 else ""
    return [f"Ravage les champs de {places.name(site)}{lost} : votre avantage monte chaque semaine"]


def hint(state, band) -> str:
    """Ce que fait le bouton Ravager (au survol)."""
    site = target_of(state, band)
    where = places.name(site) if site is not None else "un village ennemi"
    return f"Ravager les champs de {where} : sa récolte brûle, votre avantage dans la guerre monte ; ils peuvent sortir vous combattre"


# --- les evenements (events.vocabulary) --------------------------------------------------


def _ev_can_sortie(state, inst, tribe, band, *args) -> bool:
    return band is not None and band.village and (
        not troupes.army_block(state, band.id, troupes.LEVY_SHARE["masse"])
        or not troupes.army_block(state, band.id, troupes.LEVY_SHARE["troupe"])
    )


def _ev_sortie(state, inst, tribe, band, *args) -> None:
    if band is not None and band.village:
        sortie(state, band)


def _ev_war_tribute(state, inst, tribe, band, *args) -> None:
    """Le peuple paie un tribut a celui qui le ravage : la guerre finit."""
    other = inst.other
    if other not in state.tribes:
        return
    guerre.tribute_peace(state, tribe.id, other)
    diplo.add_pact(state, tribe.id, other, "tribut", diplo.TRIBUTE_WEEKS, payer=tribe.id)


EVENT_CONDITIONS = {"can_sortie": _ev_can_sortie}
EVENT_EFFECTS = {"sortie": _ev_sortie, "war_tribute": _ev_war_tribute}
EVENT_TEXTS = {
    "sortie": lambda a: "tous vos hommes sortent attaquer la troupe dans vos champs",
    "war_tribute": lambda a: "vous payez un tribut (2 ans) ; la guerre finit",
}
