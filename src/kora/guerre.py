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
treve) ; l'AVANTAGE (add_score, score : batailles, champs ravages -
ravage.py -, sieges, villages pris) decide si l'on peut exiger la soumission
(submit_verdict) ou un tribut de guerre (tribute_peace : il finit la guerre). LA LASSITUDE
(weariness : +WEARY_STEP par saison, WEARY_CAP au plus) pousse a la paix
blanche (truce_mood, lu par diplo.evaluate "treve") ; apres un an
(long_war) la relation ne filtre plus les offres de paix. Une guerre sans
combat depuis WAR_FADE_WEEKS s'eteint (fade_wars, chaque mois). LA PAIX,
une seule regle : make_peace (la guerre des deux pays tombe, une treve les
lie ; traiter avec un tributaire, c'est traiter avec son suzerain) ; end_war
ne fait que retirer la guerre. Pas de guerre dans un pays (end_inner_wars,
apres une soumission ou une confederation). Ce qui lie au pays vise (bond :
alliance, treve, tribut) empeche de declarer ; attack_block dit si une
attaque sera une bataille (battle._will_fight). Les pactes eux-memes
(treve, alliance, tribut) : diplo.py. N'importe pas pygame.
"""

from __future__ import annotations

from src.kora import approach, battle, chiefdom, diplo, ost, tech, troupes, units
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


def hostiles(state, a: int) -> set:
    """Ce que dit le lisere rouge des unites sur la carte : les peuples en
    guerre declaree avec a, ou dont le pays s'est battu avec le sien depuis
    un an (un raid, un accrochage) sans avoir fait la paix depuis. Un simple
    motif n'est pas une guerre (at_war le compte : il ouvre la guerre). Une
    seule passe sur les raids : la carte le relit deux fois par seconde."""
    if a not in state.tribes:
        return set()
    out = set(wars_of(state, a))
    mine = chiefdom.country(state, a)
    countries: dict = {}
    for (x, y), hit in diplo.of(state).raids.items():
        if state.tick_count - hit[0] > WAR_WEEKS:
            continue
        for us, them in ((x, y), (y, x)):
            if us in mine and them not in mine and them in state.tribes:
                if them not in countries:
                    countries[them] = chiefdom.country(state, them)
                out |= countries[them]
    return {t for t in out if t not in mine and t in state.tribes and (declared_war(state, a, t) or not diplo.peace_pact(state, a, t))}


def hostile(state, a: int, b: int) -> bool:
    return b in hostiles(state, a)


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


def attack_block(state, a: int, b: int) -> str:
    """Pourquoi une bande de a, lancee contre une bande de b, ne livrerait pas
    bataille ("" : elle la livrera). La regle de la bataille (battle._will_fight)
    : entre peuples qui ont la diplomatie, il faut une guerre DECLAREE (un
    motif ou un raid recent, at_war, ne suffisent pas) ; et un tributaire ne
    combat que ceux que son pays combat (may_start). L'ordre d'attaque
    (commands), son apercu (orders.attack_preview) et la marche (sim) la
    lisent : sans elle, la troupe attendait sans fin au contact."""
    if a == b or a not in state.tribes or b not in state.tribes:
        return ""
    why = may_start(state, a, b)
    if why:
        return why
    if needs_declaration(state, a, b) and not declared_war(state, a, b):
        who = state.tribes[b].name
        if motive_against(state, a, b):
            return f"Vous avez un motif contre les {who}, mais pas de guerre déclarée : déclarez-leur d'abord la guerre (écran Peuples)"
        return f"Vous êtes en paix avec les {who} : déclarez-leur d'abord la guerre (écran Peuples)"
    return ""


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
    # Le but se lit avant : la soumission fait un seul pays, ses guerres
    # internes et leurs buts tombent (end_inner_wars).
    had = (actor, target) in diplo.of(state).goals
    chiefdom.make_vassal(state, actor, target, "force")
    goal_done(state, actor, target, old if old != target else 0, had)
    if how == "soumission":
        tribe = state.tribes[actor]
        gain_prestige(state, tribe, 5)


def goal_done(state, actor: int, target: int, old_lord: int = 0, had: bool | None = None) -> None:
    """Le but de guerre atteint : plus de guerre avec le pays vaincu (had :
    actor avait pour but de soumettre target ; par defaut, lu ici)."""
    d = diplo.of(state)
    if had is None:
        had = (actor, target) in d.goals
    d.goals.pop((actor, target), None)
    for k in [k for k in d.scores if set(k) == {actor, target}]:
        d.scores.pop(k, None)
    if old_lord and old_lord in state.tribes and declared_war(state, actor, old_lord):
        make_peace(state, actor, old_lord)
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
    leurs pays), qui ont la diplomatie, hors du pays de l'attaquant ; un
    allie lie lui-meme a l'attaquant (alliance, treve, tribut : bond) reste
    hors de la guerre."""
    out: set = set()
    mine = chiefdom.country(state, actor)
    for t in sorted(chiefdom.country(state, target)):
        for other in diplo.contacts_of(state, t):
            if diplo.allied(state, t, other) and other not in mine and diplomatic(state, other) and not bond(state, actor, other):
                out |= chiefdom.country(state, other)
    return sorted(out - chiefdom.country(state, target) - mine)


# Les pactes qui lient l'attaquant au pays vise : une declaration de guerre
# les ferait tomber en silence (drop_for_war) ; il faut les rompre d'abord.
BONDS = {
    "alliance": ("Vous êtes alliés : rompez d'abord l'alliance", "Vous êtes alliés des {who}, de leur pays : rompez d'abord l'alliance"),
    "treve": ("Une trêve vous lie : rompez-la d'abord", "Une trêve vous lie aux {who}, de leur pays : rompez-la d'abord"),
    "tribut": ("Un tribut vous lie : rompez-le d'abord", "Un tribut vous lie aux {who}, de leur pays : rompez-le d'abord"),
}


def bond(state, actor: int, target: int) -> str:
    """Pourquoi actor ne peut pas declarer la guerre a target ("" : rien ne
    le lie) : une alliance, une treve ou un tribut avec target, ou avec un
    peuple de son pays (la guerre vise tout le pays)."""
    for t in [target] + sorted(chiefdom.country(state, target) - {target}):
        for kind, (direct, other) in BONDS.items():
            if diplo.has_pact(state, actor, t, kind):
                return direct if t == target else other.format(who=state.tribes[t].name)
    return ""


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
    tie = bond(state, actor, target)
    if tie:
        return diplo.Verdict(blocked=tie)
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
        # Les pactes de votre pays avec le leur tombent (drop_for_war) : le dire.
        lost = [(x, y) for x, y in war_pairs(state, actor, target) if x != actor and any(p.kind in BONDS for p in diplo.pacts_between(state, x, y))]
        if lost:
            out.append(("Ces pactes tombent : " + ", ".join(f"{state.tribes[x].name} et {state.tribes[y].name}" for x, y in lost[:4]), 0))
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


def make_peace(state, a: int, b: int) -> bool:
    """LA PAIX entre deux pays, une seule regle (l'ecran Peuples :
    diplo.perform "treve" ; la carte d'un evenement : events._eff_pact ; le
    tribut de guerre : tribute_peace ; le suzerain qui perd son tributaire :
    goal_done). Plus de guerre declaree entre aucun de leurs peuples
    (end_war), plus de but ni d'avantage entre eux, et une TREVE
    (diplo.TRUCE_WEEKS) entre les deux pays : entre chacun de leurs peuples
    qui se connaissent (grands suzerains, confederes, tributaires ; ceux
    qui etaient en guerre se connaissent tous), sauf ceux qu'un pacte de paix
    lie deja. Traiter avec un tributaire, c'est donc traiter avec son grand
    suzerain : sinon celui-ci redeclarerait la guerre la semaine suivante.
    Rend True s'il y avait une guerre declaree entre les deux pays."""
    d = diplo.of(state)
    ca = sorted(chiefdom.country(state, a) | {a})
    cb = sorted(chiefdom.country(state, b) | {b})
    if a == b or b in ca:
        # Un seul pays : pas de treve entre ses peuples.
        end_inner_wars(state, a)
        return False
    fought = any(declared_war(state, x, y) for x in ca for y in cb)
    end_war(state, a, b)
    for x in ca:
        for y in cb:
            if x == y:
                continue
            for key in ((x, y), (y, x)):
                d.goals.pop(key, None)
                d.scores.pop(key, None)
            if diplo.in_contact(state, x, y) and not diplo.peace_pact(state, x, y):
                diplo.add_pact(state, x, y, "treve", diplo.TRUCE_WEEKS, shared=False)
    return fought


def tribute_peace(state, a: int, b: int) -> bool:
    """Le tribut de guerre : l'un paie, la guerre declaree entre les deux
    pays finit comme toute paix (make_peace : le but et l'avantage tombent,
    une treve lie les deux pays). Rend True s'il y avait une guerre."""
    if not declared_war(state, a, b):
        return False
    make_peace(state, a, b)
    return True


def end_inner_wars(state, tid: int) -> None:
    """Pas de guerre a l'interieur d'un pays : quand deux pays n'en font plus
    qu'un (une soumission, une protection, une conquete : chiefdom.make_vassal
    ; une confederation : confed.form), les guerres entre leurs peuples
    tombent, avec leurs buts et leur avantage (sans treve : ils sont du meme
    pays)."""
    d = diplo.of(state)
    members = sorted(chiefdom.country(state, tid))
    for i, x in enumerate(members):
        for y in members[i + 1 :]:
            k = diplo.pair(x, y)
            pacts = d.pacts.get(k)
            if pacts and any(p.kind == WAR for p in pacts):
                kept = [p for p in pacts if p.kind != WAR]
                if kept:
                    d.pacts[k] = kept
                else:
                    d.pacts.pop(k, None)
            for key in ((x, y), (y, x)):
                d.goals.pop(key, None)
                d.scores.pop(key, None)


def wars_of(state, tid: int) -> list[int]:
    """Les peuples en guerre declaree avec tid."""
    return sorted(o for o in diplo.contacts_of(state, tid) if declared_war(state, tid, o))


# --- la revolte d'un tributaire (la guerre d'independance) -----------------------------
# On ne rompt pas un serment de tributaire comme un accord : il faut se
# REVOLTER. Le serment tient un temps (tech.VASSAL_OATH_WEEKS, plus avec Otages
# et serments : Bonuses.vassal_oath) ; se revolter, c'est un parjure (du
# prestige), et son suzerain - tout son pays, avec ses autres tributaires -
# lui fait aussitot la guerre pour le soumettre a nouveau (un but de guerre,
# un motif : pas de honte pour lui). Le rebelle n'est libre pour de bon que
# s'il tient : une paix blanche (la lassitude y pousse), ou trois ans sans
# combat. Pris (son village) ou force a la soumission, il redevient
# tributaire. Ses propres tributaires le suivent.
PERJURY_PRESTIGE = 10
HOSTAGES_PRESTIGE = 10
REBEL_MOTIVE_WEEKS = 156


def vassal_pact(state, vassal: int, lord: int):
    """Le pacte par lequel vassal sert lord (None : il ne le sert pas)."""
    return next((p for p in diplo.pacts_between(state, vassal, lord) if p.kind == "vassal" and p.payer == vassal), None)


def oath_weeks(state, lord: int) -> int:
    """Combien de temps tient le serment des tributaires de lord."""
    tribe = state.tribes.get(lord)
    mult = tech.bonuses(tribe).vassal_oath if tribe is not None else 1.0
    return int(round(tech.VASSAL_OATH_WEEKS * mult))


def oath_left(state, vassal: int, lord: int) -> int:
    """Les semaines avant que vassal puisse se revolter (0 : il le peut)."""
    pact = vassal_pact(state, vassal, lord)
    if pact is None:
        return 0
    return max(0, pact.since + oath_weeks(state, lord) - state.tick_count)


def revolt_odds(state, vassal: int, lord: int) -> tuple[int, float]:
    """La guerre d'independance : combien de peuples du pays du suzerain
    entreraient en guerre, et la force du rebelle (et de ses propres
    tributaires) face a la leur."""
    mine = {vassal} | set(chiefdom.descendants(state, vassal))
    country = chiefdom.country(state, lord) - mine
    theirs_power = sum(diplo.power(state, t) for t in country)
    mine_power = sum(diplo.power(state, t) for t in mine)
    return len(country), mine_power / max(1.0, theirs_power)


def revolt_verdict(state, vassal: int, lord: int) -> diplo.Verdict:
    """Se revolter contre son suzerain : possible ou non, et ce qu'il en
    coutera (la fiche de l'ecran Peuples, la decision de l'IA)."""
    if vassal_pact(state, vassal, lord) is None:
        return diplo.Verdict(blocked="Vous n'êtes pas leurs tributaires")
    left = oath_left(state, vassal, lord)
    if left > 0:
        hostages = tech.bonuses(state.tribes[lord]).vassal_oath > 1.0
        more = " (ils gardent vos otages)" if hostages else ""
        return diplo.Verdict(blocked=f"Votre serment est trop récent{more} : encore {left} semaines")
    mine = {vassal} | set(chiefdom.descendants(state, vassal))
    n, ratio = revolt_odds(state, vassal, lord)
    out = [
        (f"Leur pays entre en guerre contre vous : {n} peuple{'s' if n > 1 else ''}", 0),
        (f"Votre force face à la leur : {ratio:.1f}".replace(".", ","), 0),
        (f"Le parjure : prestige -{PERJURY_PRESTIGE}", 0),
    ]
    if tech.bonuses(state.tribes[lord]).vassal_oath > 1.0:
        out.append((f"Vos otages paient pour vous : prestige -{HOSTAGES_PRESTIGE}", 0))
    if len(mine) > 1:
        out.append((f"Vos tributaires vous suivent : {len(mine) - 1}", 0))
    out.append(("Libres pour de bon : tenir jusqu'à la paix (la lassitude y pousse)", 0))
    return diplo.Verdict(score=1, reasons=out)


def _drop_oath(state, vassal: int, lord: int) -> None:
    """Le pacte de tributaire tombe ; les guerriers du tributaire (et de ses
    propres tributaires) venus dans l'ost de l'autre camp rentrent chez eux."""
    pacts = diplo.of(state).pacts
    k = diplo.pair(vassal, lord)
    kept = [p for p in pacts.get(k, []) if not (p.kind == "vassal" and p.payer == vassal)]
    if kept:
        pacts[k] = kept
    else:
        pacts.pop(k, None)
    leaving = {vassal} | set(chiefdom.descendants(state, vassal))
    for army in sorted((b for b in state.bands.values() if b.kind == "armee" and b.population > 0 and b.tribe_id not in leaving), key=lambda b: b.id):
        if battle.in_battle(state, army):
            continue
        parts = ost.foreign(state, army)
        for tid in sorted(parts):
            if tid in leaving and len(parts[tid]) < len(units.normalize(army)):
                troupes.send_companies_home(state, army, parts[tid])


def rebel(state, vassal: int, lord: int) -> str:
    """vassal se revolte contre lord : le pacte tombe, le parjure coute, et
    le pays de lord lui fait la guerre pour le soumettre a nouveau."""
    rebel_t, lord_t = state.tribes[vassal], state.tribes[lord]
    # Ses guerriers venus dans l'ost du suzerain rentrent chez eux : ils ne se
    # battront pas contre les leurs.
    _drop_oath(state, vassal, lord)
    loss = PERJURY_PRESTIGE + (HOSTAGES_PRESTIGE if tech.bonuses(lord_t).vassal_oath > 1.0 else 0)
    rebel_t.prestige = max(0, rebel_t.prestige - loss)
    diplo.add_mod(state, lord, vassal, "revolte", -25, actor=vassal)
    set_casus(state, lord, vassal, REBEL_MOTIVE_WEEKS, "Ils se sont révoltés")
    note(state, LogKind.POLITIQUE, f"Les {rebel_t.name} se révoltent : ils ne paient plus. Leur guerre d'indépendance commence : soumettez-les.", to=lord)
    note(state, LogKind.POLITIQUE, f"Vous rejetez le joug des {lord_t.name} (prestige -{loss}). Ils vont vous faire la guerre : tenez jusqu'à la paix.", to=vassal)
    if diplomatic(state, lord) and diplomatic(state, vassal):
        declare_war(state, lord, vassal, goal=vassal)
    return f"Vous vous révoltez contre les {lord_t.name} : leur pays vous fait la guerre."


# --- affranchir un tributaire (le suzerain le rend libre) -------------------------------
# Le geste inverse de la revolte : le suzerain delie son tributaire de son
# serment. Pas de parjure ni de rupture : un bienfait, dont on se souvient
# (FREED_RELATION, le souvenir "affranchi"). Le tribut et ses guerriers
# s'en vont ; ses propres tributaires restent les siens.
FREED_RELATION = 15


def free_verdict(state, lord: int, vassal: int) -> diplo.Verdict:
    """Affranchir son tributaire : possible ou non, et ce que cela change."""
    if vassal_pact(state, vassal, lord) is None:
        return diplo.Verdict(blocked="Ils ne sont pas vos tributaires")
    under = chiefdom.descendants(state, vassal)
    out = [
        (f"Ils vous en sauront gré : relation +{FREED_RELATION}", FREED_RELATION),
        ("Leur tribut cesse, leurs guerriers quittent votre ost", 0),
    ]
    if under:
        out.append((f"Leurs tributaires les suivent : {len(under)}", 0))
    return diplo.Verdict(score=1, reasons=out)


def free(state, lord: int, vassal: int) -> str:
    """lord affranchit vassal : le serment tombe, sans honte ni rupture."""
    if vassal_pact(state, vassal, lord) is None:
        return ""
    _drop_oath(state, vassal, lord)
    diplo.add_mod(state, lord, vassal, "affranchi", FREED_RELATION, actor=lord)
    lord_t, vassal_t = state.tribes[lord], state.tribes[vassal]
    note(state, LogKind.POLITIQUE, f"Les {lord_t.name} vous affranchissent : vous voilà libres, sans guerre.", to=vassal)
    note(state, LogKind.POLITIQUE, f"Vous affranchissez les {vassal_t.name} : ils ne vous doivent plus rien, et s'en souviendront.", to=lord)
    return f"Vous affranchissez les {vassal_t.name}."

