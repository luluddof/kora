"""La confederation : plusieurs peuples qui forment un seul pays.

Chacun reste maitre chez lui (son chef, ses villages, ses reserves, son
commerce), mais ils :
  - se soutiennent a la guerre (leurs bandes viennent en renfort, comme des
    allies : battle.helpers_of, ai_war.force_at) ;
  - ont UNE diplomatie exterieure : une treve ou une alliance conclue par
    l'un avec un peuple du dehors engage tous les autres (et leurs
    tributaires) ; un pacte rompu, ou un raid contre le dehors, les engage
    aussi (diplo.add_pact, break_pact, on_fight) ; un raid contre l'un est
    un raid contre tout le pays (war_pairs : tributaires compris) ;
  - partagent leur vue (vision : systems.SIGHT) ;
  - se lisent comme un seul pays sur la carte (look.country_color).
Elle tient par un pacte "confederation" entre deux membres ; le groupe est
l'ensemble des peuples relies par ces pactes (au plus MAX_MEMBERS).
Elle se rompt si un membre devient le tributaire de quelqu'un
(chiefdom.make_vassal), ou par "Rompre le pacte".
Il faut que les deux connaissent Confederation (le bonus "union"), une
relation d'au moins REL_MIN et etre voisins (GAP_MAX cases). L'IA ne la
propose qu'a un allie de deux ans (AI_ALLIED_WEEKS), tres ami (AI_REL).
N'importe pas pygame.
"""

from __future__ import annotations

from src.kora import approach, chiefdom, diplo, tech
from src.kora.gamestate import is_human, note
from src.kora.log import LogKind

KIND = "confederation"
# Les pactes que partagent les confederes avec le dehors.
SHARED = ("treve", "alliance")
MAX_MEMBERS = 4
REL_MIN = 40
GAP_MAX = 40
# L'IA : des allies de longue date (deux ans), tres amis.
AI_ALLIED_WEEKS = 104
AI_REL = 60
AI_CHANCE = 0.02


def members(state, tid: int) -> tuple[int, ...]:
    """Le peuple et ses confederes (tous ceux relies par des pactes de
    confederation), tries ; (tid,) s'il est seul."""
    pacts = state.diplo.pacts
    seen = {tid}
    todo = [tid]
    while todo:
        t = todo.pop()
        for (a, b), ps in pacts.items():
            if t not in (a, b) or not any(p.kind == KIND for p in ps):
                continue
            o = b if a == t else a
            if o not in seen:
                seen.add(o)
                todo.append(o)
    return tuple(sorted(seen))


def groups(state) -> dict[int, tuple[int, ...]]:
    """Chaque peuple confedere -> son groupe (une seule passe : pour la carte)."""
    links: dict[int, set] = {}
    for (a, b), ps in state.diplo.pacts.items():
        if any(p.kind == KIND for p in ps):
            links.setdefault(a, set()).add(b)
            links.setdefault(b, set()).add(a)
    out: dict[int, tuple[int, ...]] = {}
    for start in sorted(links):
        if start in out:
            continue
        seen, todo = {start}, [start]
        while todo:
            for o in links.get(todo.pop(), ()):
                if o not in seen:
                    seen.add(o)
                    todo.append(o)
        group = tuple(sorted(seen))
        for t in group:
            out[t] = group
    return out


def same(state, a: int, b: int) -> bool:
    return a != b and b in members(state, a)


def leader(state, tid: int) -> int:
    """Celui qui a fonde la confederation (le plus ancien pacte : son
    proposant) ; sa couleur est celle du pays."""
    group = members(state, tid)
    if len(group) == 1:
        return tid
    best = None
    for (a, b), ps in state.diplo.pacts.items():
        if a in group and b in group:
            for p in ps:
                if p.kind == KIND:
                    key = (p.since, p.payer or min(a, b))
                    if best is None or key < best:
                        best = key
    founder = best[1] if best else group[0]
    return founder if founder in group else group[0]


def name(state, tid: int) -> str:
    """"Confédération des Akor" (du nom de son fondateur)."""
    return f"Confédération des {state.tribes[leader(state, tid)].name}"


def outside_pairs(state, a: int, b: int) -> list[tuple[int, int]]:
    """Les paires engagees par un pacte entre a et b : ceux que la
    diplomatie de a engage (ses confederes, leurs tributaires) avec ceux que
    celle de b engage (sauf a-b lui-meme) ; rien s'ils sont du meme pays."""
    ga, gb = chiefdom.followers(state, a), chiefdom.followers(state, b)
    if b in ga or a in gb:
        return []
    return sorted((x, y) for x in ga for y in gb if (x, y) != (a, b) and x != y)


def war_pairs(state, a: int, b: int) -> list[tuple[int, int]]:
    """Une guerre entre a et b : chaque peuple du pays de a contre chaque
    peuple du pays de b (sauf a-b lui-meme)."""
    ga, gb = chiefdom.country(state, a), chiefdom.country(state, b)
    if b in ga or a in gb:
        return []
    return sorted((x, y) for x in ga for y in gb if (x, y) != (a, b) and x != y)


def sight_partners(state, tid: int) -> list[int]:
    """La vue partagee entre confederes (systems.SIGHT)."""
    return [m for m in members(state, tid) if m != tid]


def block(state, actor: int, target: int) -> str:
    """Pourquoi actor ne peut pas proposer la confederation a target ("" : il peut)."""
    if not tech.bonuses(state.tribes[actor]).union:
        return "Il faut connaître Confédération"
    if not tech.bonuses(state.tribes[target]).union:
        return "Ils ne connaissent pas Confédération"
    if same(state, actor, target):
        return "Vous êtes déjà confédérés"
    if chiefdom.overlord_of(state, actor) or chiefdom.overlord_of(state, target):
        return "Un tributaire n'entre pas dans une confédération"
    if target in chiefdom.vassals_of(state, actor) or actor in chiefdom.vassals_of(state, target):
        return "Un suzerain et son tributaire ne se confédèrent pas"
    if len(members(state, actor)) + len(members(state, target)) > MAX_MEMBERS:
        return f"Une confédération compte {MAX_MEMBERS} peuples au plus"
    rel = diplo.relation(state, actor, target)
    if rel < REL_MIN:
        return f"Relation trop basse ({rel:.0f}, il faut {REL_MIN})"
    if diplo.gap(state, actor, target) > GAP_MAX:
        return f"Trop loin l'un de l'autre ({GAP_MAX} cases au plus)"
    return ""


def reasons(state, actor: int, target: int) -> list[tuple[str, int]]:
    """Ce qui pese dans la reponse de target (diplo.evaluate)."""
    rel = diplo.relation(state, actor, target)
    ratio = max(1.0, diplo.power(state, actor)) / max(1.0, diplo.power(state, target))
    out = [("Base", -15), ("Relation", round((rel - REL_MIN) * 0.6))]
    if diplo.allied(state, actor, target):
        out.append(("Déjà alliés", 15))
    if 0.5 <= ratio <= 2.0:
        out.append(("De force comparable", 10))
    elif ratio > 3.0:
        out.append(("Ils craignent d'être avalés", -15))
    if diplo._other_enemy(state, target, actor):
        out.append(("Un ennemi les menace", 10))
    if state.tribes[target].prestige >= 70:
        out.append(("Fiers de leur indépendance", -10))
    return out


def form(state, actor: int, target: int) -> None:
    """Le pacte, puis la paix partagee : chaque treve ou alliance de l'un
    avec le dehors vaut pour l'autre (et pour tout le groupe)."""
    before = (members(state, actor), members(state, target))
    diplo.add_pact(state, actor, target, KIND, payer=actor)
    group = members(state, actor)
    for (a, b), ps in list(state.diplo.pacts.items()):
        for p in list(ps):
            if p.kind not in SHARED:
                continue
            inside, outside = (a, b) if a in group else (b, a)
            if inside not in group or outside in group:
                continue
            weeks = max(1, p.until - state.tick_count) if p.until else 0
            for m in group:
                if m != inside and not diplo.has_pact(state, m, outside, p.kind):
                    diplo.add_pact(state, m, outside, p.kind, weeks, shared=False)
    for side, other in ((before[0], before[1]), (before[1], before[0])):
        for t in side:
            if is_human(state, t):
                names = ", ".join(state.tribes[o].name for o in other)
                note(state, LogKind.POLITIQUE, f"Confédération avec les {names} : vous vous soutiendrez à la guerre et vos pactes avec le dehors vous engagent tous.", to=t)


def leave(state, tid: int, why: str) -> None:
    """tid quitte sa confederation (ses pactes de confederation tombent)."""
    group = members(state, tid)
    if len(group) == 1:
        return
    for o in group:
        k = diplo.pair(tid, o)
        kept = [p for p in state.diplo.pacts.get(k, []) if p.kind != KIND]
        if o == tid or len(kept) == len(state.diplo.pacts.get(k, [])):
            continue
        if kept:
            state.diplo.pacts[k] = kept
        else:
            state.diplo.pacts.pop(k, None)
    for t in group:
        if is_human(state, t):
            who = "Vous quittez" if t == tid else f"Les {state.tribes[tid].name} quittent"
            note(state, LogKind.POLITIQUE, f"{who} la confédération : {why}.", to=t)


def on_vassal(state, vassal: int) -> None:
    """Un membre devient tributaire : la confederation est rompue pour lui."""
    leave(state, vassal, "un tributaire ne parle plus pour lui-même")


def shared_note(state, a: int, b: int, kind: str, pairs) -> None:
    """Un joueur engage par le pacte d'un confedere l'apprend."""
    word = {"treve": "une trêve", "alliance": "une alliance"}.get(kind, kind)
    ga = members(state, a)
    for x, y in pairs:
        for me, other in ((x, y), (y, x)):
            signer = a if me in ga else b
            if signer != me and is_human(state, me):
                note(state, LogKind.POLITIQUE, f"Vos confédérés les {state.tribes[signer].name} ont conclu {word} avec les {state.tribes[other].name} : elle vous engage aussi.", to=me)


def monthly(state) -> None:
    """Un chef de l'IA quitte une confederation ou il n'a plus d'amis (relation
    negative avec tous les autres) ; un tributaire n'y reste jamais."""
    seen = set()
    for tid, group in sorted(groups(state).items()):
        if tid in seen:
            continue
        seen.update(group)
        for t in group:
            if chiefdom.overlord_of(state, t):
                on_vassal(state, t)
            elif not is_human(state, t) and all(diplo.relation(state, t, o) < 0 for o in group if o != t):
                leave(state, t, "plus aucune amitié entre ses chefs")


def ai_wants(state, tid: int, other: int) -> bool:
    """Un chef de l'IA propose la confederation a un allie proche et sur."""
    since = next((p.since for p in state.diplo.pacts.get(diplo.pair(tid, other), []) if p.kind == "alliance"), None)
    if since is None or state.tick_count - since < AI_ALLIED_WEEKS or diplo.relation(state, tid, other) < AI_REL:
        return False
    if block(state, tid, other):
        return False
    return state.story_rng.random() < AI_CHANCE * approach.factor(state, tid, "confed")


def lines(state, tid: int) -> list[str]:
    """Pour l'ecran Peuples : la confederation d'un peuple."""
    group = members(state, tid)
    if len(group) == 1:
        return []
    others = ", ".join(state.tribes[t].name for t in group if t != tid)
    return [f"{name(state, tid)} : avec les {others}"]
