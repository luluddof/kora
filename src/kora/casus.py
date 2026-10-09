"""LES CAUSES DE GUERRE et les guerres de soumission.

Des MOTIFS naissent (diplo.set_casus ; ils durent CASUS_WEEKS et se
renouvellent chaque mois tant que la cause dure) :
  - LA TERRE : deux peuples a villages dont les zones se chevauchent sur
    LAND_CELLS cases ou plus : le plus nombreux, a l'etroit, a un motif
    ("Terres disputées").
  - UNE RESSOURCE : un peuple qui connait un metier (silex, sel, argile,
    argent) sans gisement sur ses terres, quand il y en a un a RES_RADIUS
    cases de son village dans la zone d'un voisin ("Le silex de leurs
    terres").
  - UNE SUCCESSION : un chef meurt ; les peuples dont les chefs sont lies
    au sien par des mariages (une alliance, des mariages passes) peuvent
    reclamer, un sur deux ("Succession disputée", SUCCESSION_WEEKS).
  Un motif : declarer la guerre sans honte (diplo._war_verdict), et l'IA
  raide un voisin meme cordial (ai_war.fair_game).
LES GUERRES DE SOUMISSION de l'IA (chaque mois, un peuple sur quatre) :
  - un chef CONQUERANT vise un voisin bien plus faible (WEAK_RATIO, son
    pays compte), a portee (AI_CONQUEST_GAP) : s'ils sont allies, il rompt
    l'alliance - une trahison (diplo.betray) - et lui declare la guerre
    pour le soumettre ;
  - les autres chefs, seulement avec un motif, selon leur envie de tribut
    (approach "tribute").
  En guerre, l'IA exige la soumission quand elle a l'avantage (diplo
  "soumission" ; un joueur recoit une carte).
N'importe pas pygame.
"""

from __future__ import annotations

from src.kora import approach, chiefdom, chiefs, diplo, goods, influence
from src.kora.gamestate import is_human
from src.kora.log import LogKind
from src.kora.resources import PRESENT

CASUS_WEEKS = 56
SUCCESSION_WEEKS = 104
LAND_CELLS = 12
RES_RADIUS = 8
# Les ressources qu'on se dispute (les betes et le poisson vont et viennent).
CLAIM_RES = {
    "silex": "Le silex de leurs terres",
    "sel": "Le sel de leurs terres",
    "argile": "L'argile de leurs terres",
    "argent": "L'argent de leurs collines",
}
SUCCESSION_CLAIM = 0.5
WEAK_RATIO = 2.0
AI_CONQUEST_GAP = 30
CONQUER_CHANCE = 0.08
MOTIVE_CHANCE = 0.05
AI_MAX_WARS = 2


def monthly(state) -> None:
    _land_claims(state)
    _resource_claims(state)
    _successions(state)
    with diplo.frozen_relations(state):
        _ai_wars(state)
    _ai_submissions(state)


# --- les motifs ----------------------------------------------------------------------


def _villagers(state) -> set:
    return {s.tribe_id for s in state.sites.values() if s.kind == "village" and s.tribe_id in state.tribes}


def _rivals(state, a: int, b: int) -> bool:
    """Deux peuples qui peuvent se disputer quelque chose."""
    return a != b and diplo.in_contact(state, a, b) and b not in chiefdom.country(state, a)


def _land_claims(state) -> None:
    owners = _villagers(state)
    for (a, b), n in sorted(getattr(state, "overlap", {}).items()):
        if n < LAND_CELLS or a not in owners or b not in owners or not _rivals(state, a, b):
            continue
        presser, other = (a, b) if diplo.pop_of(state, a) >= diplo.pop_of(state, b) else (b, a)
        _claim(state, presser, other, CASUS_WEEKS, "Terres disputées")


def _deposits_near(world, h, res: str) -> list:
    """Les gisements de `res` a RES_RADIUS cases (la carte ne change pas)."""
    memo = getattr(world, "_lands", None)
    if memo is None:
        memo = world._lands = {}
    key = ("claim", world._index(h), res)
    hit = memo.get(key)
    if hit is None:
        hit = memo[key] = [x for x in world.hexes_in_radius(h, RES_RADIUS) if world.resource(x, res) >= PRESENT] if world.resources else []
    return hit


def _resource_claims(state) -> None:
    world = state.world
    owners = _villagers(state)
    for site in sorted(state.sites.values(), key=lambda s: s.id):
        if site.kind != "village" or site.tribe_id not in state.tribes:
            continue
        tribe = state.tribes[site.tribe_id]
        found = goods.riches(world, site.hex)
        for craft in goods.CRAFTS.values():
            wanted = [r for r in craft.res if r in CLAIM_RES]
            if not wanted or craft.needs not in tribe.knowledge or any(r in found for r in craft.res):
                continue
            for res in wanted:
                for h in _deposits_near(world, site.hex, res):
                    owner, v = influence.dominant(world, h)
                    if owner in owners and v >= influence.ZONE_MIN and _rivals(state, tribe.id, owner):
                        _claim(state, tribe.id, owner, CASUS_WEEKS, CLAIM_RES[res])
                        break


def _successions(state) -> None:
    """Un chef mort : les mariages donnent un droit sur sa succession."""
    for tid in sorted(state.tribes):
        tribe = state.tribes[tid]
        chief = chiefs.chief_of(state, tid)
        if chief is None:
            continue
        flags = tribe.flags if tribe.flags is not None else {}
        before = flags.get("chef_pid")
        flags["chef_pid"] = chief.pid
        tribe.flags = flags
        if before is None or before == chief.pid:
            continue
        for other in diplo.contacts_of(state, tid):
            if other not in state.tribes or not _rivals(state, other, tid):
                continue
            married = diplo.allied(state, tid, other) or any(m.key == "mariage" for m in diplo._d(state).mods.get(diplo.pair(tid, other), []))
            if not married or state.story_rng.random() >= SUCCESSION_CLAIM:
                continue
            _claim(state, other, tid, SUCCESSION_WEEKS, "Succession disputée : le sang de vos chefs")
            if is_human(state, other):
                diplo._note(state, LogKind.POLITIQUE, f"Le chef des {tribe.name} est mort : les mariages entre vos chefs vous donnent un droit sur leur succession (un motif de guerre, 2 ans).", to=other)


def _claim(state, a: int, b: int, weeks: int, why: str) -> None:
    new = not diplo.casus_of(state, a, b)
    diplo.set_casus(state, a, b, weeks, why)
    if new and is_human(state, a) and not why.startswith("Succession"):
        diplo._note(state, LogKind.POLITIQUE, f"Un motif de guerre contre les {state.tribes[b].name} : {why[0].lower() + why[1:]}.", to=a)


# --- les guerres de soumission de l'IA ------------------------------------------------------


def country_power(state, tid: int) -> float:
    return sum(diplo.power(state, t) for t in chiefdom.country(state, tid))


def _ai_wars(state) -> None:
    owners = _villagers(state)
    for tid in sorted(owners):
        tribe = state.tribes[tid]
        if tribe.is_player or (state.tick_count // 4 + tid) % 4:
            continue
        if chiefdom.lords_of(state, tid) or not diplo.diplomatic(state, tid):
            continue
        if len(diplo.wars_of(state, tid)) >= AI_MAX_WARS:
            continue
        if len(chiefdom.vassals_of(state, tid)) >= chiefdom.vassal_cap(state, tid):
            continue
        style = approach.of(state, tid)
        mine = country_power(state, tid)
        for other in diplo.contacts_of(state, tid):
            if other not in owners or not _rivals(state, tid, other) or diplo.declared_war(state, tid, other):
                continue
            if diplo.gap(state, tid, other) > AI_CONQUEST_GAP:
                continue
            theirs = country_power(state, other) + sum(country_power(state, t) for t in diplo.war_allies(state, other, tid))
            if mine < WEAK_RATIO * max(1.0, theirs):
                continue
            motive = diplo.motive_against(state, tid, other)
            if style == "conquerant":
                chance = CONQUER_CHANCE
            elif motive:
                chance = MOTIVE_CHANCE * approach.factor(state, tid, "tribute")
            else:
                continue
            if state.story_rng.random() >= chance:
                continue
            if diplo.allied(state, tid, other):
                if style != "conquerant":
                    continue
                # Le conquerant rompt sa parole : une trahison.
                diplo.break_pact(state, tid, other, "alliance")
                diplo.betray(state, tid, other)
            if diplo.evaluate(state, tid, other, "guerre").blocked:
                continue
            diplo.declare_war(state, tid, other, other)
            break


def _ai_submissions(state) -> None:
    """L'IA qui a l'avantage exige la soumission de ceux qu'elle combat."""
    for tid in sorted(state.tribes):
        tribe = state.tribes[tid]
        if tribe.is_player or (state.tick_count // 4 + tid) % 2:
            continue
        for other in diplo.wars_of(state, tid):
            if diplo.score(state, tid, other) <= 0 or diplo.on_cooldown(state, tid, other, "soumission"):
                continue
            verdict = diplo.evaluate(state, tid, other, "soumission")
            if verdict.blocked:
                continue
            if verdict.accepted or is_human(state, other):
                diplo.perform(state, tid, other, "soumission")
                break
