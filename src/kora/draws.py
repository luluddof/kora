"""LES TIRAGES DES SAVOIRS (a la Terra Invicta) : certains savoirs peuvent ne
pas venir.

Trois sortes (tech.Tech : chance, world, group) :
  - par PEUPLE (chance) : chaque peuple, le joueur compris, a cette chance de
    voir venir le savoir ; le tirage se fait quand il en connait les
    prerequis (le savoir pourrait alors lui venir), et on l'apprend ;
  - par MONDE (world) : une fois par partie, le monde a cette chance de voir
    naitre le savoir ; s'il n'y nait pas, personne ne l'aura. Certains sont
    ensuite tires par peuple (world et chance) ;
  - EXCLUSIFS (group, tech.GROUPS) : un seul savoir du groupe nait dans le
    monde (ou aucun, selon le groupe) ; les autres y sont impossibles.
Un savoir qui ne vient pas est ABSENT, et tout ce qui en depend aussi.

Les tirages sont fixes par la GRAINE de la partie (state.research["seed"]) :
un hasard propre, tire du nom du savoir et du peuple (comme les situations),
jamais state.rng ni story_rng : rien ne change le reste de la partie, le
multijoueur tire pareil sur chaque machine, et recharger ne change rien.
Ce qui a deja ete revele a un peuple est note (Tribe.revealed) : le journal
l'annonce une fois.
N'importe pas pygame.
"""

from __future__ import annotations

import hashlib
import random

from src.kora import tech
from src.kora.gamestate import is_human, note
from src.kora.log import LogKind

_WORLD: dict = {}


def seed_of(state) -> int:
    return int((getattr(state, "research", None) or {}).get("seed", 1))


def set_seed(state, seed: int) -> None:
    state.research = dict(getattr(state, "research", None) or {})
    state.research["seed"] = int(seed)


def seed_from(state) -> int:
    """Une graine pour une vieille partie (qui n'en avait pas) : tiree de ce
    qui ne change pas (les noms des premiers peuples, la carte)."""
    names = ":".join(f"{tid}={state.tribes[tid].name}" for tid in sorted(state.tribes)[:4])
    key = f"{names}:{state.world.width}x{state.world.height}"
    return int(hashlib.sha256(key.encode("utf-8")).hexdigest()[:8], 16)


def _roll(*keys) -> float:
    return random.Random("kora-tirage:" + ":".join(str(k) for k in keys)).random()


def world_draw(state) -> dict:
    """Ce que le monde de cette partie a tire : {savoir: ne ou pas}. Les
    savoirs sans tirage du monde n'y sont pas."""
    seed = seed_of(state)
    hit = _WORLD.get(seed)
    if hit is not None:
        return hit
    out: dict = {}
    for t in sorted(tech.TECHS.values(), key=lambda t: t.id):
        if t.world < 1.0 and not t.group:
            out[t.id] = _roll(seed, "monde", t.id) < t.world
    for group, (_name, none_chance) in sorted(tech.GROUPS.items()):
        members = sorted((t for t in tech.TECHS.values() if t.group == group), key=lambda t: t.id)
        if not members:
            continue
        r = _roll(seed, "groupe", group)
        chosen = None
        if r >= none_chance:
            # Chacun pese son poids (world) dans le reste du tirage.
            weights = [m.world for m in members]
            x = (r - none_chance) / max(1e-9, 1.0 - none_chance) * sum(weights)
            for m, w in zip(members, weights):
                if x < w:
                    chosen = m.id
                    break
                x -= w
            chosen = chosen or members[-1].id
        for m in members:
            out[m.id] = m.id == chosen
    _WORLD[seed] = out
    return out


def hidden(state) -> frozenset:
    """Les savoirs qu'on ne montre pas dans l'arbre : ceux d'un groupe
    EXCLUSIF dont un autre membre est ne dans ce monde (ils ne viendront
    jamais), et ce qui depend d'eux. Un groupe ou rien n'est ne reste
    visible (barre : "le sort a dit non")."""
    drawn = world_draw(state)
    born = {tech.TECHS[t].group for t, ok in drawn.items() if ok and tech.TECHS[t].group}
    out = {t for t, ok in drawn.items() if not ok and tech.TECHS[t].group in born}
    grew = True
    while grew:
        grew = False
        for t in tech.TECHS.values():
            if t.id not in out and any(p in out for p in t.prereqs):
                out.add(t.id)
                grew = True
    return frozenset(out)


def in_world(state, tid: str) -> bool:
    return world_draw(state).get(tid, True)


def comes_to(state, tribe_id: int, tid: str) -> bool:
    """Le tirage du peuple (sans regarder le monde) : le savoir lui vient-il ?"""
    t = tech.TECHS[tid]
    if t.chance >= 1.0:
        return True
    tribe = state.tribes.get(tribe_id)
    if tribe is not None and tid in tribe.knowledge:
        return True
    return _roll(seed_of(state), "peuple", tribe_id, tid) < t.chance


def why_absent(state, tribe_id: int, tid: str) -> str:
    """Pourquoi un savoir ne viendra pas a ce peuple ("" : il peut venir).
    Tout ce qui depend d'un savoir absent l'est aussi."""
    tribe = state.tribes.get(tribe_id)
    if tribe is not None and tid in tribe.knowledge:
        return ""
    return _why(state, tribe_id, tid, set())


def _why(state, tribe_id: int, tid: str, seen: set) -> str:
    if tid in seen:
        return ""
    seen.add(tid)
    t = tech.TECHS[tid]
    tribe = state.tribes.get(tribe_id)
    if tribe is not None and tid in tribe.knowledge:
        return ""
    if t.drawn:
        if not in_world(state, tid):
            if t.group:
                other = next((m for m, ok in world_draw(state).items() if ok and tech.TECHS[m].group == t.group), None)
                if other:
                    return f"Ce monde a vu naître {tech.TECHS[other].name} : {t.name} n'y viendra pas"
            return "Ce savoir n'est pas né dans ce monde"
        # Le tirage du peuple n'est connu qu'une fois les prerequis appris.
        if tribe is not None and revealed(tribe, tid) and not comes_to(state, tribe_id, tid):
            return "Ce savoir n'est pas venu à votre peuple" if is_human(state, tribe_id) else "Ce savoir n'est pas venu à ce peuple"
    for p in t.prereqs:
        why = _why(state, tribe_id, p, seen)
        if why:
            return f"Il dépend de {tech.TECHS[p].name}, qui ne viendra pas"
    return ""


def short_why(state, tribe_id: int, tid: str) -> str:
    """Pour une carte de l'arbre : la raison en trois mots."""
    why = why_absent(state, tribe_id, tid)
    if why.startswith("Ce monde a vu"):
        return "L'autre est né ici"
    if why.startswith("Ce savoir n'est pas né"):
        return "Pas né dans ce monde"
    if why.startswith("Il dépend"):
        return "Dépend d'un absent"
    return "Le sort a dit non" if why else ""


def revealed(tribe, tid: str) -> bool:
    """Le tirage du peuple a-t-il eu lieu (il connait les prerequis) ?"""
    if tid in (getattr(tribe, "revealed", None) or ()):
        return True
    return all(p in tribe.knowledge for p in tech.TECHS[tid].prereqs)


def absent(state, tribe_id: int, tid: str) -> bool:
    return bool(why_absent(state, tribe_id, tid))


def chance_text(state, tribe_id: int, tid: str) -> str:
    """Ce que le joueur sait du tirage d'un savoir, en une ligne."""
    t = tech.TECHS[tid]
    if not t.drawn:
        return ""
    parts = []
    if t.group:
        parts.append(f"un seul savoir de « {tech.GROUPS[t.group][0]} » naît dans le monde")
    elif t.world < 1.0:
        parts.append(f"{round(100 * t.world)} % de naître dans le monde")
    if t.chance < 1.0:
        parts.append(f"puis {round(100 * t.chance)} % de venir à chaque peuple" if parts else f"{round(100 * t.chance)} % de venir à chaque peuple")
    return "Tirage : " + ", ".join(parts)


def lines(state, tribe_id: int, tid: str) -> list[tuple[str, str]]:
    """Pour la fiche d'un savoir : (texte, style) ; style "ok", "manque", "note"."""
    t = tech.TECHS[tid]
    if not t.drawn:
        return []
    out = [(chance_text(state, tribe_id, tid), "note")]
    if t.world < 1.0 or t.group:
        if in_world(state, tid):
            out.append(("Il est né dans ce monde.", "ok"))
        else:
            out.append((why_absent(state, tribe_id, tid), "manque"))
            return out
    if t.chance < 1.0:
        tribe = state.tribes[tribe_id]
        if tid in tribe.knowledge:
            out.append(("Il est venu à votre peuple.", "ok"))
        elif not revealed(tribe, tid):
            names = ", ".join(tech.TECHS[p].name for p in t.prereqs if p not in tribe.knowledge)
            out.append((f"Le tirage de votre peuple : quand vous connaîtrez {names}.", "note"))
        elif comes_to(state, tribe_id, tid):
            out.append(("Le sort vous a souri : il peut venir à votre peuple.", "ok"))
        else:
            out.append(("Le sort ne vous a pas souri : il ne viendra pas à votre peuple.", "manque"))
    return out


def monthly(state) -> None:
    """Les tirages des peuples dont les prerequis viennent d'etre appris : on
    les note, et le joueur l'apprend (systems.MONTHLY)."""
    living = {b.tribe_id for b in state.bands.values() if b.population > 0}
    for tid in sorted(state.tribes):
        tribe = state.tribes[tid]
        if tid not in living:
            continue
        for t in sorted(tech.TECHS.values(), key=lambda t: t.id):
            if t.chance >= 1.0 or t.id in tribe.revealed or t.id in tribe.knowledge:
                continue
            if not all(p in tribe.knowledge for p in t.prereqs):
                continue
            tribe.revealed.add(t.id)
            if not in_world(state, t.id) or not is_human(state, tid):
                continue
            if comes_to(state, tid, t.id):
                text = f"Le sort vous sourit : {t.name} peut venir à votre peuple (seulement {round(100 * t.chance)} % des peuples)."
            else:
                text = f"Le sort ne vous sourit pas : {t.name} ne viendra pas à votre peuple."
            note(state, LogKind.DECOUVERTE, text, to=tid)
