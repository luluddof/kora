"""LES GUERRES vues par un peuple (l'ecran des guerres : render_wars.py).

Une GUERRE, pour le joueur, c'est un FRONT : tous les peuples d'un meme
pays ennemi (chiefdom.country : un suzerain, ses tributaires, ses
confederes) avec qui il est en guerre declaree. Pour chacune :
  - qui l'a declaree, depuis quand ; les buts (le sien, le leur) ;
  - l'AVANTAGE (diplo.score) : le sien contre chaque peuple ennemi ;
  - les deux CAMPS : son pays et ses allies en guerre / leur pays et leurs
    allies en guerre ;
  - les troupes EN CAMPAGNE : les siennes et celles de son pays ; celles de
    l'ennemi qu'il VOIT (le brouillard compte) ; l'ost en route ;
  - les SIEGES en cours, des deux cotes ;
  - les derniers COMBATS entre les deux camps (state.fights : six mois) ;
  - ce qu'il peut faire : exiger leur soumission, proposer une treve.
Ailleurs dans le monde : les guerres entre pays qu'il connait.
Lecture seule, pure (tests). N'importe pas pygame.
"""

from __future__ import annotations

from dataclasses import dataclass, field

from src.kora import chiefdom, diplo, places, villages
from src.kora.vision import is_visible


@dataclass
class Front:
    key: int  # le grand suzerain du pays ennemi
    enemies: list  # les peuples ennemis (du pays) en guerre avec nous
    since: int  # la semaine ou la guerre a commence
    declared_by: int  # qui l'a declaree (le premier pacte de guerre)
    my_side: list  # notre pays et nos allies en guerre contre eux
    their_side: list  # leur pays et leurs allies en guerre contre nous
    my_goals: list  # les peuples que nous voulons soumettre
    their_goals: list  # les peuples qui veulent nous soumettre
    scores: dict  # peuple ennemi -> notre avantage
    armies: list = field(default_factory=list)  # [(bande, camp, ce qu'elle fait)]
    sieges: list = field(default_factory=list)  # [(site, semaines, qui assiege)]
    fights: list = field(default_factory=list)  # FightMark entre les camps

    @property
    def score(self) -> float:
        """L'avantage contre le pays : contre le peuple ou il compte le plus."""
        return max(self.scores.values(), key=abs, default=0.0)

    @property
    def target(self) -> int:
        """A qui l'on exige la soumission : notre but, sinon leur suzerain."""
        return self.my_goals[0] if self.my_goals else self.key


def _war_pact(state, a: int, b: int):
    return next((p for p in diplo._pacts(state, a, b) if p.kind == diplo.WAR), None)


def fronts(state, me: int) -> list[Front]:
    """Les guerres de `me`, une par pays ennemi, les plus anciennes d'abord."""
    by_key: dict[int, list[int]] = {}
    for enemy in diplo.wars_of(state, me):
        by_key.setdefault(chiefdom.top_lord(state, enemy), []).append(enemy)
    out = []
    mine = chiefdom.country(state, me) | {me}
    for key, enemies in by_key.items():
        pacts = [p for p in (_war_pact(state, me, e) for e in enemies) if p is not None]
        first = min(pacts, key=lambda p: p.since) if pacts else None
        theirs = set(enemies)
        # Leur camp : les ennemis, leur pays, leurs allies en guerre contre nous.
        their_side = sorted(
            t for t in state.tribes
            if t in theirs
            or (diplo.declared_war(state, t, me) and (chiefdom.top_lord(state, t) == key or any(diplo.allied(state, t, e) for e in enemies)))
        )
        # Le notre : nous, notre pays, nos allies en guerre contre eux.
        my_side = sorted(
            t for t in state.tribes
            if t in mine or (diplo.allied(state, t, me) and any(diplo.declared_war(state, t, e) for e in enemies))
        )
        front = Front(
            key=key,
            enemies=sorted(enemies),
            since=first.since if first else state.tick_count,
            declared_by=first.payer if first else 0,
            my_side=my_side,
            their_side=their_side,
            my_goals=[t for t in diplo.goals_of(state, me) if t in theirs],
            their_goals=[e for e in their_side if diplo.goal_of(state, e, me)],
            scores={e: diplo.score(state, me, e) for e in enemies},
        )
        _fill(state, me, front)
        out.append(front)
    out.sort(key=lambda f: (f.since, f.key))
    return out


def _doing(state, band) -> str:
    """Ce que fait une troupe, en quelques mots."""
    if band.homebound:
        return "rentre au village"
    if band.ost:
        lord = state.bands.get(band.ost)
        return f"rejoint l'ost des {state.tribes[lord.tribe_id].name}" if lord is not None else "rejoint l'ost"
    target = state.bands.get(band.order.target_band_id) if band.order.target_band_id else None
    if target is not None and target.tribe_id != band.tribe_id:
        site = places.site_of(state, target) if target.village else None
        what = places.name(site) if site is not None else f"une bande des {state.tribes[target.tribe_id].name}"
        return f"marche sur {what}"
    for site in state.sites.values():
        if site.kind == "village" and getattr(site.data, "siege", 0) and state.world.distance(site.hex, band.position) <= 1 and site.tribe_id != band.tribe_id:
            return f"assiège {places.name(site)}"
    home = villages.home_of(state, band)
    if home is not None and state.world.distance(home.hex, band.position) <= villages.ARMY_HOME:
        return "au village"
    return "en campagne" if not band.path else "en marche"


def _fill(state, me: int, front: Front) -> None:
    mine, theirs = set(front.my_side), set(front.their_side)
    for band in sorted(state.bands.values(), key=lambda b: b.id):
        if band.kind != "armee" or band.population <= 0:
            continue
        if band.tribe_id in mine:
            front.armies.append((band, "nous", _doing(state, band)))
        elif band.tribe_id in theirs and is_visible(state, band.position, me):
            front.armies.append((band, "eux", _doing(state, band)))
    for site in sorted(state.sites.values(), key=lambda s: s.id):
        weeks = getattr(site.data, "siege", 0) if site.kind == "village" else 0
        if not weeks:
            continue
        by = site.data.besieger
        if (site.tribe_id in mine and by in theirs) or (site.tribe_id in theirs and by in mine):
            front.sieges.append((site, weeks, by))
    for mark in reversed(state.fights):
        sides = {mark.winner_tribe, mark.loser_tribe}
        if sides & mine and sides & theirs:
            front.fights.append(mark)


def others(state, me: int) -> list[tuple[int, int, int]]:
    """Les guerres entre pays que `me` connait (hors les siennes) :
    [(grand suzerain, grand suzerain, depuis)], une par paire de pays."""
    known = set(diplo.contacts_of(state, me))
    mine = chiefdom.country(state, me) | {me}
    seen: dict = {}
    for (a, b), pacts in diplo._d(state).pacts.items():
        war = next((p for p in pacts if p.kind == diplo.WAR), None)
        if war is None or a in mine or b in mine or a not in known or b not in known:
            continue
        ka, kb = chiefdom.top_lord(state, a), chiefdom.top_lord(state, b)
        key = (min(ka, kb), max(ka, kb))
        if key[0] == key[1]:
            continue
        seen[key] = min(seen.get(key, war.since), war.since)
    return sorted(((a, b, since) for (a, b), since in seen.items()), key=lambda r: (r[2], r[0], r[1]))


def score_text() -> str:
    return (
        f"+{diplo.WIN_SCORE:.0f} par combat gagné, -{diplo.WIN_SCORE:.0f} par combat perdu, "
        f"+{diplo.VILLAGE_SCORE:.0f} par village pris, +{diplo.SIEGE_SCORE:.0f} par semaine de siège "
        f"(de -{diplo.SCORE_CAP:.0f} à +{diplo.SCORE_CAP:.0f})"
    )
