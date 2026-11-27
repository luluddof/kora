"""CE QUI ATTEND LE JOUEUR (2026-11-19, la critique des interfaces : "le
debut ne dit pas quoi faire", "l'essentiel se noie").

Deux choses, lues dans la partie sans la changer (comme le tutoriel :
l'ecran les montre, elles ne se sauvent pas, ne passent pas par
commands.py ; render_objectifs.py les dessine, a gauche) :

  LE CHEMIN DU PREMIER VILLAGE (chemin) : tant que le peuple n'a pas de
    village, ses quatre etapes, avec ce qui manque a chacune, en mots et en
    chiffres (le savoir des campements ; Premieres semailles et ses
    conditions : le peuple, les hivers, les cereales sauvages ; un campement
    sur une terre a cultiver ; la fondation). Le premier village vient vers
    l'an 10 chez l'IA ; ses trois parties neuves du 13 novembre s'etaient
    arretees a l'an 1 a 3, faute de savoir ce qu'on cherchait.

  LES ALERTES (alertes) : ce qui menace et demande un geste, le plus grave
    d'abord : une bande qui a faim, un village en disette ou assiege ou qui
    s'agite, un clan pret a partir, la solde impayee, une guerre declaree.
    Chacune dit ou cliquer (son "action" : les choix des panneaux,
    Play.side_click, partie_ecrans.py).

N'importe pas pygame. Les deux se gardent le temps d'une semaine (rangees
sur la partie elle-meme, jamais selon une adresse).
"""

from __future__ import annotations

from src.kora import learning, points, sites, tech, villages
from src.kora import chiefs, diplo, guerre, money, siege
from src.kora.sim import band_hunger

# Les savoirs du chemin (tech.py) : les campements, les semailles.
CAMP_TECH = "huttes"
VILLAGE_TECH = "semis"
# Au plus tant d'alertes a la fois (les plus graves).
MAX_ALERTS = 4
GRAVITY = {"danger": 0, "alerte": 1, "info": 2}


def _memo(state, key: str, stamp, make):
    box = state.__dict__.setdefault("_objectifs", {})
    hit = box.get(key)
    if hit is not None and hit[0] == stamp:
        return hit[1]
    value = make()
    box[key] = (stamp, value)
    return value


def _stamp(state, tribe) -> tuple:
    return (
        state.tick_count,
        state.viewer,
        tribe.learning,
        len(tribe.knowledge),
        len(state.sites),
        sum(1 for b in state.bands.values() if b.tribe_id == state.viewer),
    )


# --- le chemin du premier village ------------------------------------------------------


def _tech_detail(state, tribe, tid: str) -> list[tuple[str, bool]]:
    """Ce qu'il faut encore pour un savoir : (ligne, faite)."""
    t = tech.TECHS.get(tid)
    if t is None:
        return []
    status = learning.status(state, tribe.id, tid)
    if status == "en_cours":
        weeks = learning.weeks_left(state, tribe.id, tid)
        return [(f"À l'étude : encore {weeks} semaine{'s' if weeks > 1 else ''}", True)]
    if status == "disponible":
        return [("Possible : choisissez-le (Savoirs, T)", True)]
    out = []
    missing = tech.missing_prereqs(tribe, t)
    if missing:
        names = ", ".join(m.name for m in missing)
        out.append((f"D'abord : {names}", False))
    eased = bool(learning._neighbors_know(state, tribe.id, tid))
    for cond in t.conds:
        have, need, label = learning.cond_progress(state, tribe, cond, eased)
        if have >= need:
            out.append((label, True))
        else:
            out.append((f"{label} : {have} sur {need}", False))
    return out


def _good_camp(state, tid: int):
    """Un campement du peuple avec de la terre a cultiver autour (la meme
    regle que la fondation : villages.found_block)."""
    for camp in sorted(sites.of_tribe(state, tid, "camp"), key=lambda s: s.id):
        if any(villages.fertility(state, tid, h) > 0.35 for h in points.around(state.world, camp, villages.FIELD_RADIUS)):
            return camp
    return None


def chemin(state) -> dict | None:
    """Le chemin du premier village, ou None (le peuple a son village, ou
    n'est plus). {"title", "steps": [{"title", "done", "lines"}], "current"}."""
    tribe = state.tribes.get(state.viewer)
    if tribe is None:
        return None
    return _memo(state, "chemin", _stamp(state, tribe), lambda: _chemin(state, tribe))


def _chemin(state, tribe) -> dict | None:
    tid = tribe.id
    if sites.of_tribe(state, tid, "village"):
        return None
    mine = [b for b in state.bands.values() if b.tribe_id == tid and b.population > 0 and not b.village and b.kind != "armee"]
    if not mine:
        return None
    know = tech.bonuses(tribe)
    steps = []
    # 1. Camper : le savoir des campements.
    camp_ok = know.camps > 0
    steps.append({
        "title": "Savoir camper (Huttes et campements)",
        "done": camp_ok,
        "lines": [] if camp_ok else _tech_detail(state, tribe, CAMP_TECH),
    })
    # 2. Premieres semailles.
    sow_ok = know.villages > 0
    steps.append({
        "title": f"Apprendre {tech.TECHS[VILLAGE_TECH].name}",
        "done": sow_ok,
        "lines": [] if sow_ok else _tech_detail(state, tribe, VILLAGE_TECH),
    })
    # 3. Un campement sur une terre a cultiver.
    camp = _good_camp(state, tid)
    if camp is not None:
        lines = []
    elif not camp_ok:
        lines = [("Après le savoir des campements", False)]
    else:
        lines = [
            ("Une vallée ou une plaine, près de l'eau : survolez la carte", False),
            ("Posez-y un campement : Camper [C] sur la fiche de la bande", False),
        ]
    steps.append({"title": "Un campement sur une terre à cultiver", "done": camp is not None, "lines": lines})
    # 4. Fonder.
    biggest = max(mine, key=lambda b: (b.population, -b.id))
    lines = []
    if camp is not None and sow_ok:
        here = [b for b in mine if sites.own_site_at(state, b) is camp]
        if not here:
            lines.append(("Amenez une bande sur ce campement", False))
        elif max(b.population for b in here) < villages.MIN_FOUND_POP:
            lines.append((f"Il faut {villages.MIN_FOUND_POP} personnes dans la bande", False))
        else:
            lines.append(("Tout est prêt : Village [V] sur la fiche de la bande", True))
    elif biggest.population < villages.MIN_FOUND_POP:
        lines.append((f"Une bande de {villages.MIN_FOUND_POP} personnes au moins (la plus grande : {biggest.population})", False))
    steps.append({"title": "Fonder le village [V]", "done": False, "lines": lines})
    current = next((i for i, s in enumerate(steps) if not s["done"]), len(steps) - 1)
    return {"title": "Le chemin du premier village", "steps": steps, "current": current}


# --- les alertes -------------------------------------------------------------------------


def treasury_alert(state) -> bool:
    """La solde ou les gages ne sont pas payes (l'onglet Tresor s'allume)."""
    tribe = state.tribes.get(state.viewer)
    if tribe is None or not money.has_money(state, state.viewer):
        return False
    b = money.budget(tribe)
    return "impayee" in (b.get("etat_solde"), b.get("etat_gages"))


# On vous a declare la guerre depuis moins de WAR_NEWS semaines : l'onglet
# respire.
WAR_NEWS = 8


def wars_alert(state) -> bool:
    me = state.viewer
    for enemy in guerre.wars_of(state, me):
        pact = next((p for p in diplo.pacts_between(state, me, enemy) if p.kind == guerre.WAR), None)
        if pact is not None and pact.payer != me and state.tick_count - pact.since <= WAR_NEWS:
            return True
    return False


def alertes(state) -> list[dict]:
    """[{key, text, tone ("danger", "alerte"), icon, action}] : les plus
    graves d'abord, MAX_ALERTS au plus (le compte entier : "more")."""
    tribe = state.tribes.get(state.viewer)
    if tribe is None:
        return []
    return _memo(state, "alertes", _stamp(state, tribe), lambda: _alertes(state, tribe))


def _alertes(state, tribe) -> list[dict]:
    tid = tribe.id
    out = []
    for band in sorted(state.bands.values(), key=lambda b: b.id):
        if band.tribe_id != tid or band.population <= 0:
            continue
        if band.village:
            site = villages.site_of(state, band)
            if site is None:
                continue
            name = villages.name(site)
            if siege.lines(state, site):
                out.append({"key": f"siege:{site.id}", "text": f"{name} est assiégé", "tone": "danger", "icon": "combat", "action": f"vil_open:{site.id}"})
            hunger = band_hunger(state, band)
            if hunger == "famine":
                out.append({"key": f"faim:{band.id}", "text": f"{name} meurt de faim", "tone": "danger", "icon": "famine", "action": f"vil_open:{site.id}"})
            elif hunger == "disette":
                out.append({"key": f"faim:{band.id}", "text": f"Disette en vue à {name}", "tone": "alerte", "icon": "grenier", "action": f"vil_open:{site.id}"})
            if villages.stability(state, site, band) < villages.UNREST:
                out.append({"key": f"agite:{site.id}", "text": f"Agitation à {name}", "tone": "alerte", "icon": "danger", "action": f"vil_open:{site.id}"})
            continue
        who = band.leader.name if band.leader is not None else f"bande {band.id}"
        what = "La troupe" if band.kind == "armee" else ("La bande" if chiefs.is_chief_band(state, band) else "Le clan")
        hunger = band_hunger(state, band)
        if hunger == "famine":
            out.append({"key": f"faim:{band.id}", "text": f"{what} de {who} meurt de faim", "tone": "danger", "icon": "famine", "action": f"tribe_see:{band.id}"})
        elif hunger == "disette":
            weeks = band.stock / max(1, band.population)
            out.append({"key": f"faim:{band.id}", "text": f"{what} de {who} : {weeks:.0f} sem. de vivres", "tone": "alerte", "icon": "famine", "action": f"tribe_see:{band.id}"})
        if not chiefs.is_chief_band(state, band) and band.kind != "armee" and band.loyalty < chiefs.LEAVE:
            out.append({"key": f"part:{band.id}", "text": f"Le clan de {who} veut partir", "tone": "danger", "icon": "tribu", "action": "tab_tribu"})
    if treasury_alert(state):
        out.append({"key": "solde", "text": "La solde n'est pas payée", "tone": "danger", "icon": "pieces", "action": "tab_tresor"})
    if wars_alert(state):
        out.append({"key": "guerre", "text": "On vous a déclaré la guerre", "tone": "danger", "icon": "combat", "action": "tab_guerres"})
    out.sort(key=lambda a: GRAVITY.get(a["tone"], 3))
    return out
