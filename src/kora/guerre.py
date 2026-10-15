"""LA GUERRE DECLAREE : qui est en paix, qui est en guerre, pourquoi, et
comment elle finit.

Deux peuples qui connaissent la diplomatie (Messagers et serments, avec un
village : diplomatic) sont EN PAIX par defaut (at_peace) ; pour se battre,
l'un DECLARE LA GUERRE (declare_war : un pacte WAR entre les deux PAYS -
tributaires et confederes compris -, et les allies de la cible entrent en
guerre a ses cotes : war_pairs, war_allies). Avec un peuple qui n'a pas la
diplomatie, rien ne change : des raids libres, des accrochages entre bandes.
Un tributaire ne declare pas de guerre (may_start) : il suit son suzerain.

Un MOTIF (set_casus, motive_against ; casus.py en fait naitre : la terre,
une ressource, une succession, un tribut refuse) : declarer sans honte ;
sinon prestige -DECLARE_PRESTIGE et une reputation d'agresseur. Un BUT :
soumettre (goal_of, submit : on ne sert qu'un suzerain, l'ancien fait la
treve) ; l'AVANTAGE (add_score, score : batailles, sieges, villages pris)
decide si l'on peut exiger la soumission (submit_verdict). LA LASSITUDE
(weariness : +WEARY_STEP par saison, WEARY_CAP au plus) pousse a la paix
blanche (truce_mood, lu par diplo.evaluate "treve") ; apres un an
(long_war) la relation ne filtre plus les offres de paix. Une guerre sans
combat depuis WAR_FADE_WEEKS s'eteint (fade_wars, chaque mois). end_war :
la paix entre deux pays. Les pactes eux-memes (treve, alliance, tribut) :
diplo.py. N'importe pas pygame.
"""

from __future__ import annotations

from src.kora import approach, chiefdom, diplo, tech
from src.kora.bands import gain_prestige
from src.kora.gamestate import note
from src.kora.log import LogKind
from src.kora.types import Pact


WAR = "guerre"
# Sans combat entre les deux pays depuis ce temps, la guerre s'eteint.
WAR_FADE_WEEKS = 156
DECLARE_RELATION = -30
DECLARE_PRESTIGE = 5


def migrate(state) -> None:
    """Une partie d'avant 0.18 : la diplomatie venait de Dons et palabres ;
    elle vient desormais de Messagers et serments (avec les villages). Un
    peuple qui l'avait (palabres) et qui a un village la garde."""
    research = getattr(state, "research", None)
    if research is None or research.get("messagers"):
        return
    with_village = {s.tribe_id for s in state.sites.values() if s.kind == "village"}
    for tid, tribe in state.tribes.items():
        if "palabres" in tribe.knowledge and tid in with_village and "messagers" not in tribe.knowledge:
            tech.grant(tribe, "messagers")
    research["messagers"] = 1
    tech.invalidate()


def diplomatic(state, tid: int) -> bool:
    """Le peuple connait la diplomatie (on lui declare la guerre)."""
    tribe = state.tribes.get(tid)
    return tribe is not None and tech.bonuses(tribe).diplomacy


def needs_declaration(state, a: int, b: int) -> bool:
    """Entre eux, il faut declarer la guerre pour se battre."""
    return diplomatic(state, a) and diplomatic(state, b)


def declared_war(state, a: int, b: int) -> bool:
    return diplo.has_pact(state, a, b, WAR)


def at_peace(state, a: int, b: int) -> bool:
    """Treve, alliance, tribut, tributaire, confederation : pas de raid entre
    eux (l'accord commercial, lui, n'empeche pas la guerre) ; deux peuples
    qui ont la diplomatie sont en paix tant que la guerre n'est pas
    declaree."""
    if a == b:
        return True
    if declared_war(state, a, b):
        return False
    if diplo.peace_pact(state, a, b):
        return True
    return needs_declaration(state, a, b)


WAR_WEEKS = 52


def at_war(state, a: int, b: int) -> bool:
    """Les pays de a et de b sont en guerre declaree, ou se sont battus depuis
    un an (un raid, un accrochage), ou l'un a un pretexte contre l'autre."""
    d = diplo.of(state)
    if declared_war(state, a, b):
        return True
    ga, gb = chiefdom.country(state, a), chiefdom.country(state, b)
    for x in ga:
        for y in gb:
            for key in ((x, y), (y, x)):
                hit = d.raids.get(key)
                if hit is not None and state.tick_count - hit[0] <= WAR_WEEKS:
                    return True
                if d.casus.get(key, -1) >= state.tick_count:
                    return True
    return False


def may_start(state, a: int, b: int) -> str:
    """Pourquoi a ne peut pas attaquer b de lui-meme ("" : il peut). Un
    TRIBUTAIRE suit son suzerain a la guerre mais n'en declare pas : il ne
    se bat que contre qui son pays combat deja (ou contre son suzerain : une
    revolte). Un confedere, lui, peut entrainer tout son pays."""
    if a == b or a not in state.tribes or b not in state.tribes:
        return ""
    lords = chiefdom.lords_of(state, a)
    if not lords or b in lords or b in chiefdom.country(state, a):
        return ""
    if at_war(state, a, b):
        return ""
    return f"Un tributaire ne déclare pas la guerre : les {state.tribes[lords[-1]].name} ne combattent pas les {state.tribes[b].name}"


# --- motifs, buts de guerre, avantage -----------------------------------------------
# Un MOTIF (casus) : declarer la guerre sans honte (pas de prestige perdu,
# pas d'agresseur) ; l'IA s'en sert (casus.py fait naitre les motifs : la
# terre, une ressource, une succession ; un tribut refuse en est un).
# Un BUT : soumettre un peuple (en faire son tributaire) ; atteint quand son
# village est pris et soumis, ou quand il accepte de se soumettre (action
# "soumission", selon l'AVANTAGE dans la guerre : batailles, sieges,
# villages pris).
WIN_SCORE = 10.0
VILLAGE_SCORE = 30.0
SIEGE_SCORE = 2.0
SCORE_CAP = 100.0
SUBMIT_BASE = -40
# LA LASSITUDE : plus une guerre declaree dure, plus les deux camps sont
# enclins a la paix blanche (une treve, sans soumission) : +WEARY_STEP
# points pour la treve par saison de guerre (13 semaines), WEARY_CAP au plus
# (atteint apres six ans : alors meme un conquerant s'y resout, sauf s'il
# gagne nettement - c'est alors la soumission qui finit la guerre). Le camp qui mene la guerre veut sa
# victoire (LEAD_PER points de moins par point d'avantage, LEAD_CAP au
# plus), celui qui la perd veut en sortir ; la lassitude finit par l'emporter.
WEARY_SEASON = 13
WEARY_STEP = 4
WEARY_CAP = 96
LEAD_PER = 0.25
LEAD_CAP = 20


def set_casus(state, a: int, b: int, weeks: int, why: str) -> None:
    """a a un motif contre b pendant `weeks` semaines."""
    d = diplo.of(state)
    until = state.tick_count + weeks
    if d.casus.get((a, b), -1) < until:
        d.casus[(a, b)] = until
    d.casus_why[(a, b)] = why


def motive_against(state, a: int, b: int) -> str:
    """Le motif de a contre b ou contre un peuple de son pays (une guerre
    contre l'un est une guerre contre tous)."""
    for t in [b] + sorted(chiefdom.country(state, b) - {b}):
        why = casus_of(state, a, t)
        if why:
            return why
    return ""


def casus_of(state, a: int, b: int) -> str:
    """Le motif de a contre b ("" : aucun)."""
    d = diplo.of(state)
    if d.casus.get((a, b), -1) < state.tick_count:
        return ""
    return d.casus_why.get((a, b), "Ils ont refusé votre tribut")


def add_score(state, a: int, b: int, v: float) -> None:
    """L'avantage de a sur b (et le contraire pour b), en guerre declaree."""
    if not v or not declared_war(state, a, b):
        return
    d = diplo.of(state)
    now = max(-SCORE_CAP, min(SCORE_CAP, d.scores.get((a, b), 0.0) + v))
    d.scores[(a, b)] = now
    d.scores[(b, a)] = -now


def score(state, a: int, b: int) -> float:
    return diplo.of(state).scores.get((a, b), 0.0) if declared_war(state, a, b) else 0.0


def weariness(state, a: int, b: int) -> int:
    """La lassitude de la guerre declaree entre a et b (0 : pas de guerre
    declaree, ou moins d'une saison)."""
    war = next((p for p in diplo.pacts_between(state, a, b) if p.kind == WAR), None)
    if war is None:
        return 0
    seasons = max(0, state.tick_count - war.since) // WEARY_SEASON
    return min(WEARY_CAP, seasons * WEARY_STEP)


def long_war(state, a: int, b: int) -> bool:
    """Une guerre declaree depuis un an : la lassitude se dit."""
    return weariness(state, a, b) >= 4 * WEARY_STEP


def truce_mood(state, actor: int, target: int) -> list[tuple[str, int]]:
    """Ce que la duree et le cours de la guerre declaree font a la reponse de
    `target` a une treve (la paix blanche)."""
    out = []
    worn = weariness(state, actor, target)
    if worn:
        war = next(p for p in diplo.pacts_between(state, actor, target) if p.kind == WAR)
        months = (state.tick_count - war.since) * 12 // 52
        out.append((f"Lassitude de la guerre ({months} mois)", worn))
    lead = score(state, target, actor)
    if lead >= 10:
        out.append(("Ils mènent la guerre", -min(LEAD_CAP, round(lead * LEAD_PER))))
    elif lead <= -10:
        out.append(("Ils perdent la guerre", min(LEAD_CAP, round(-lead * LEAD_PER))))
    return out


def goal_of(state, a: int, b: int) -> bool:
    """a fait la guerre pour soumettre b."""
    return (a, b) in diplo.of(state).goals and declared_war(state, a, b)


def goals_of(state, tid: int) -> list[int]:
    return sorted(b for (a, b) in diplo.of(state).goals if a == tid and declared_war(state, a, b))


def submit(state, actor: int, target: int, how: str = "soumission") -> None:
    """target devient le tributaire de actor (on ne sert qu'un suzerain :
    il quitte l'ancien). La guerre entre eux finit ; l'ancien suzerain, qui
    a perdu son tributaire, fait la treve."""
    old = chiefdom.top_lord(state, target)
    chiefdom.make_vassal(state, actor, target, "force")
    goal_done(state, actor, target, old if old != target else 0)
    if how == "soumission":
        tribe = state.tribes[actor]
        gain_prestige(state, tribe, 5)


def goal_done(state, actor: int, target: int, old_lord: int = 0) -> None:
    """Le but de guerre atteint : plus de guerre avec le pays vaincu."""
    d = diplo.of(state)
    had = (actor, target) in d.goals
    d.goals.pop((actor, target), None)
    for k in [k for k in d.scores if set(k) == {actor, target}]:
        d.scores.pop(k, None)
    if old_lord and old_lord in state.tribes and declared_war(state, actor, old_lord):
        end_war(state, actor, old_lord)
        diplo.add_pact(state, actor, old_lord, "treve", diplo.TRUCE_WEEKS)
        for me, other in ((actor, old_lord), (old_lord, actor)):
            if state.tribes[me].is_player:
                note(state, LogKind.POLITIQUE, f"La guerre avec les {state.tribes[other].name} s'achève : les {state.tribes[target].name} ont changé de suzerain. Trêve de 2 ans.", to=me)
    if had:
        for me in (actor, target):
            if state.tribes[me].is_player:
                text = (
                    f"But de guerre atteint : les {state.tribes[target].name} sont vos tributaires."
                    if me == actor
                    else f"Vous voilà tributaires des {state.tribes[actor].name}."
                )
                note(state, LogKind.POLITIQUE, text, to=me)


def submit_verdict(state, actor: int, target: int) -> diplo.Verdict:
    if not declared_war(state, actor, target):
        return diplo.Verdict(blocked="Exiger leur soumission : il faut être en guerre contre eux")
    if target in chiefdom.country(state, actor):
        return diplo.Verdict(blocked="Ils sont de votre pays")
    if chiefdom.lords_of(state, actor):
        return diplo.Verdict(blocked="Un tributaire ne prend pas de tributaires")
    if not chiefdom.has_chiefdom(state, actor):
        return diplo.Verdict(blocked="Il vous faut un village")
    if not chiefdom.has_chiefdom(state, target):
        return diplo.Verdict(blocked="Ils n'ont pas de village")
    if len(chiefdom.vassals_of(state, actor)) >= chiefdom.vassal_cap(state, actor):
        return diplo.Verdict(blocked="Vous avez déjà autant de tributaires que vous pouvez en tenir")
    out = [("Base", SUBMIT_BASE)]
    out.append(("Votre avantage dans la guerre", round(score(state, actor, target))))
    ratio = max(1.0, diplo.power(state, actor)) / max(1.0, diplo.power(state, target))
    out.append(("Rapport de forces", max(-20, min(30, round((ratio - 1.0) * 15)))))
    site = next((s for s in state.sites.values() if s.kind == "village" and s.tribe_id == target and getattr(s.data, "siege", 0)), None)
    if site is not None:
        out.append(("Leur village est assiégé", 15))
    lord = chiefdom.overlord_of(state, target)
    if lord:
        out.append((f"Ils changeraient de suzerain (les {state.tribes[lord].name})", 5))
    if state.tribes[target].prestige >= 50:
        out.append(("Trop fiers pour plier", -10))
    seen = approach.accept(state, target, "proteger")
    if seen is not None:
        out.append(seen)
    out = [(label, v) for label, v in out if v]
    return diplo.Verdict(score=sum(v for _l, v in out), reasons=out)


def fade_wars(state) -> None:
    """Une guerre sans combat depuis WAR_FADE_WEEKS s'eteint d'elle-meme."""
    d = diplo.of(state)
    for (a, b), pacts in sorted(d.pacts.items()):
        war = next((p for p in pacts if p.kind == WAR), None)
        if war is None or state.tick_count - war.since < WAR_FADE_WEEKS:
            continue
        last = max(
            [h[0] for key in ((a, b), (b, a)) if (h := d.raids.get(key)) is not None] + [war.since]
        )
        if state.tick_count - last >= WAR_FADE_WEEKS:
            d.pacts[(a, b)] = [p for p in pacts if p.kind != WAR]
            if not d.pacts[(a, b)]:
                d.pacts.pop((a, b), None)
            for me, other in ((a, b), (b, a)):
                if state.tribes[me].is_player:
                    note(state, LogKind.POLITIQUE, f"La guerre avec les {state.tribes[other].name} s'éteint : plus un combat depuis trois ans.", to=me)


def war_allies(state, target: int, actor: int) -> list[int]:
    """Ceux qui entreraient en guerre aux cotes de target : ses allies (et
    leurs pays), qui ont la diplomatie, hors du pays de l'attaquant."""
    out: set = set()
    mine = chiefdom.country(state, actor)
    for t in sorted(chiefdom.country(state, target)):
        for other in diplo.contacts_of(state, t):
            if diplo.allied(state, t, other) and other not in mine and diplomatic(state, other):
                out |= chiefdom.country(state, other)
    return sorted(out - chiefdom.country(state, target) - mine)


def war_pairs(state, actor: int, target: int) -> list[tuple[int, int]]:
    """Les paires en guerre si actor la declare a target : son pays contre
    le pays de target et ses allies."""
    mine = chiefdom.country(state, actor)
    theirs = chiefdom.country(state, target) | set(war_allies(state, target, actor))
    return sorted((x, y) for x in mine for y in theirs if x != y)


def war_verdict(state, actor: int, target: int) -> diplo.Verdict:
    if not diplomatic(state, actor):
        return diplo.Verdict(blocked="Il faut connaître Messagers et serments (la diplomatie vient avec les villages)")
    if not diplomatic(state, target):
        return diplo.Verdict(blocked="Ils ne connaissent pas la diplomatie : attaquez-les au clic droit, sans déclaration")
    if declared_war(state, actor, target):
        return diplo.Verdict(blocked="Vous êtes déjà en guerre")
    if target in chiefdom.country(state, actor):
        return diplo.Verdict(blocked="Ils sont de votre pays")
    why = may_start(state, actor, target)
    if chiefdom.lords_of(state, actor):
        return diplo.Verdict(blocked=why or "Un tributaire ne déclare pas la guerre")
    if diplo.allied(state, actor, target):
        return diplo.Verdict(blocked="Vous êtes alliés : rompez d'abord l'alliance")
    if diplo.has_pact(state, actor, target, "treve"):
        return diplo.Verdict(blocked="Une trêve vous lie : rompez-la d'abord")
    out = [(f"Relation {DECLARE_RELATION}", 0)]
    if chiefdom.has_chiefdom(state, actor) and chiefdom.has_chiefdom(state, target):
        out.append(("But : les soumettre (prendre leur village, ou exiger leur soumission)", 0))
    lord = chiefdom.top_lord(state, target)
    if lord != target:
        vassals = len(chiefdom.descendants(state, lord))
        out.append(
            (
                f"Ils sont tributaires des {state.tribes[lord].name} : on ne sert qu'un suzerain, c'est la guerre "
                f"à tout leur pays ({state.tribes[lord].name} et {vassals} tributaire{'s' if vassals > 1 else ''})",
                0,
            )
        )
    why = motive_against(state, actor, target)
    if why:
        out.append((f"Vous avez un motif ({why[0].lower() + why[1:]}) : pas de honte", 0))
    else:
        out.append((f"Sans motif : prestige -{DECLARE_PRESTIGE}, et les autres peuples s'en souviennent", 0))
    if diplo.has_pact(state, actor, target, "commerce"):
        out.append(("L'accord commercial tombe", 0))
    allies = war_allies(state, target, actor)
    if allies:
        out.append(("Leurs alliés entrent en guerre : " + ", ".join(state.tribes[t].name for t in allies[:5]), 0))
    mine = sorted(chiefdom.country(state, actor) - {actor})
    if mine:
        out.append(("Votre pays vous suit : " + ", ".join(state.tribes[t].name for t in mine[:5]), 0))
    return diplo.Verdict(score=1, reasons=out)


def declare_war(state, actor: int, target: int, goal: int = 0) -> str:
    """actor declare la guerre a target : les deux pays (et les allies de
    target) sont en guerre ; la paix et le commerce entre eux tombent.
    goal : le peuple qu'il veut soumettre (target, ou son grand suzerain)."""
    d = diplo.of(state)
    pairs = war_pairs(state, actor, target)
    motive = bool(motive_against(state, actor, target))
    for x, y in pairs:
        diplo.drop_for_war(state, x, y)
        k = diplo.pair(x, y)
        if not declared_war(state, x, y):
            d.pacts.setdefault(k, []).append(Pact(WAR, state.tick_count, 0, actor, state.tick_count))
        diplo.make_contact(state, x, y, quiet=True)
        d.scores.pop((x, y), None)
        d.scores.pop((y, x), None)
    if goal:
        d.goals[(actor, goal)] = state.tick_count
    diplo.add_mod(state, actor, target, "guerre_declaree", DECLARE_RELATION, actor=actor)
    tribe = state.tribes[actor]
    if not motive:
        tribe.prestige = max(0, tribe.prestige - DECLARE_PRESTIGE)
        for other in diplo.contacts_of(state, actor):
            if other != target:
                diplo.add_mod(state, actor, other, "agresseur", -5, actor=actor)
    names = (tribe.name, state.tribes[target].name)
    involved = sorted({x for p_ in pairs for x in p_})
    for t in involved:
        if not state.tribes[t].is_player or t == actor:
            continue
        side = "vous" if t == target else ("votre pays" if t in chiefdom.country(state, target) else "vos alliés")
        note(state, LogKind.COMBAT, f"Les {names[0]} déclarent la guerre aux {names[1]} : {side} entrez en guerre contre eux.", to=t)
    if tribe.is_player:
        joined = sorted({y for _x, y in pairs} - {target})
        extra = f" Leurs alliés et leur pays les suivent : {', '.join(state.tribes[t].name for t in joined[:5])}." if joined else ""
        return f"Vous déclarez la guerre aux {names[1]}.{extra}"
    return ""


def end_war(state, a: int, b: int) -> None:
    """La paix (une treve) entre les deux pays : plus de guerre entre eux."""
    for x in chiefdom.country(state, a) | {a}:
        for y in chiefdom.country(state, b) | {b}:
            k = diplo.pair(x, y)
            kept = [p for p in diplo.of(state).pacts.get(k, []) if p.kind != WAR]
            if kept:
                diplo.of(state).pacts[k] = kept
            else:
                diplo.of(state).pacts.pop(k, None)


def wars_of(state, tid: int) -> list[int]:
    """Les peuples en guerre declaree avec tid."""
    return sorted(o for o in diplo.contacts_of(state, tid) if declared_war(state, tid, o))
