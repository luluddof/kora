"""LES GRANDS TOURNANTS (a la maniere des institutions d'Europa Universalis V).

Un grand tournant (tech.Tech, kind="tournant" : le clan, la sedentarite,
la domestication, la terre des ancetres, le don et l'echange) est une grosse
recherche qui ouvre tout un pan de l'arbre (tech.pan_of). Il ne s'apprend
pas n'importe ou :
  - il ARRIVE chez un peuple (sa PRESENCE, Tribe.tournants, monte jusqu'a
    100 %) : de lui-meme, s'il en remplit les conditions (ses conds et ses
    prerequis : BIRTH par mois), ou de ses voisins qui l'ont deja adopte
    (voisins, accords commerciaux, alliances, meme pays, villages freres ;
    SPREAD_CAP par mois au plus) ;
  - arrive a 100 %, il peut etre ADOPTE : une recherche comme les autres
    (son prix, la diffusion des voisins qui l'ont adopte). Il n'est
    DECOUVERT qu'une fois la recherche terminee (on_adopted) : le PREMIER
    peuple du monde a la terminer en est le BERCEAU (state.research
    ["births"], Tribe.cradles) : prestige +BIRTH_PRESTIGE et un bonus pour
    toujours (CRADLE, des effets comme un savoir : systems.EFFECT_FIELDS
    "berceau:") ; la nouvelle court (le journal). Adopte, il ouvre son pan.
Une carte (« Voyageurs ») propose au joueur d'accelerer sa venue.
Les vieilles parties : migrate (au chargement) donne le tournant a qui sait
deja les savoirs de son pan.
N'importe pas pygame.
"""

from __future__ import annotations

from src.kora import chiefdom, chiefs, diplo, events, learning, tech
from src.kora.bands import gain_prestige
from src.kora.gamestate import humans, is_human, note
from src.kora.log import LogKind

# Presence gagnee par mois quand on en remplit soi-meme les conditions.
BIRTH = 12.0
# Ce que chaque peuple en contact apporte par mois, selon le lien.
SPREAD_CONTACT = 1.0
SPREAD_NEIGHBOR = 2.0
SPREAD_TRADE = 2.0
SPREAD_ALLY = 2.0
SPREAD_COUNTRY = 3.0
SPREAD_KIN = 1.0
# Un peuple qui l'a adopte le repand mieux qu'un peuple ou il est present.
ADOPTED = 1.5
SPREAD_CAP = 12.0
BIRTH_PRESTIGE = 20
# Le bonus du berceau : le premier peuple a adopter un tournant le garde
# pour toujours (des effets comme ceux d'un savoir).
CRADLE = {
    "clan": {"loyalty": 5, "chief_reach": 2},
    "sedentarite": {"village_growth": 1.1, "granary": 2},
    "domestication": {"village_food": 1.05, "winter_famine": 0.95},
    "terre_ancetres": {"stability": 4, "prestige_gain": 1.1},
    "don": {"diplo": 10, "trade_price": 1.05},
}
# La carte des voyageurs : quand la presence est entre ces bornes.
VISIT_RANGE = (15.0, 80.0)


def presence(tribe, tid: str) -> float:
    if tid in tribe.knowledge:
        return 100.0
    return float((getattr(tribe, "tournants", None) or {}).get(tid, 0.0))


def births(state) -> dict:
    return (getattr(state, "research", None) or {}).get("births", {})


def born(state, tid: str) -> bool:
    return tid in births(state)


def birthplace(state, tid: str):
    """(peuple, annee) du berceau ; (0, 0) : ne avant la memoire (une partie
    d'avant les grands tournants)."""
    hit = births(state).get(tid)
    return (int(hit[0]), int(hit[1])) if hit else None


def _living(state) -> set:
    return {b.tribe_id for b in state.bands.values() if b.population > 0}


def own_conditions(state, tribe, t) -> bool:
    """Le peuple remplit-il lui-meme les conditions de naissance ?"""
    if any(p not in tribe.knowledge for p in t.prereqs):
        return False
    for cond in t.conds:
        have, need, _label = learning.cond_progress(state, tribe, cond)
        if have < need:
            return False
    return True


def sources(state, tribe_id: int, tid: str) -> list[tuple[str, float, int]]:
    """D'ou vient la presence d'un tournant chez un peuple, ce mois :
    [(raison, points par mois, peuple d'ou il vient : 0 pour soi)]."""
    tribe = state.tribes[tribe_id]
    t = tech.TECHS[tid]
    out: list = []
    if own_conditions(state, tribe, t):
        out.append(("Vous en remplissez les conditions" if is_human(state, tribe_id) else "Ses conditions", BIRTH, 0))
    if not born(state, tid):
        return out
    d = state.diplo
    near = set(d.neighbors.get(tribe_id, []))
    country = chiefdom.country(state, tribe_id)
    kin = chiefdom.kin_of(state, tribe_id)
    alive = _living(state)
    for other in diplo.contacts_of(state, tribe_id):
        o = state.tribes.get(other)
        # Il ne se repand que de ceux qui l'ont adopte (decouvert).
        if o is None or other not in alive or tid not in o.knowledge:
            continue
        value, why = SPREAD_CONTACT, []
        if other in near:
            value += SPREAD_NEIGHBOR
            why.append("voisins")
        if diplo.has_pact(state, tribe_id, other, "commerce"):
            value += SPREAD_TRADE
            why.append("échanges")
        if diplo.allied(state, tribe_id, other):
            value += SPREAD_ALLY
            why.append("alliés")
        if other in country:
            value += SPREAD_COUNTRY
            why.append("même pays")
        if other in kin:
            value += SPREAD_KIN
            why.append("frères")
        value *= ADOPTED
        label = f"Les {o.name}" + (f" ({', '.join(why)})" if why else "")
        out.append((label, round(value, 2), other))
    out.sort(key=lambda x: (-x[1], x[2]))
    return out


def monthly_gain(state, tribe_id: int, tid: str) -> float:
    rows = sources(state, tribe_id, tid)
    own = sum(v for _l, v, who in rows if who == 0)
    spread = sum(v for _l, v, who in rows if who != 0)
    return own + min(SPREAD_CAP, spread)


def monthly(state) -> None:
    """La presence de chaque tournant chez chaque peuple vivant
    (systems.MONTHLY) ; les naissances ; les cartes des voyageurs."""
    alive = _living(state)
    turns = tech.turnings()
    gains: list = []
    for tribe_id in sorted(alive):
        tribe = state.tribes.get(tribe_id)
        if tribe is None:
            continue
        for t in turns:
            if t.id in tribe.knowledge or presence(tribe, t.id) >= 100.0:
                continue
            gain = monthly_gain(state, tribe_id, t.id)
            if gain > 0:
                gains.append((tribe_id, t.id, gain))
    # Tout le monde gagne en meme temps (l'ordre des peuples ne compte pas).
    for tribe_id, tid, gain in gains:
        tribe = state.tribes[tribe_id]
        value = min(100.0, presence(tribe, tid) + gain)
        tribe.tournants[tid] = round(value, 2)
        if value >= 100.0:
            _arrived(state, tribe, tid)
        elif is_human(state, tribe_id):
            _visitors(state, tribe, tid)


def _arrived(state, tribe, tid: str) -> None:
    """Arrive a 100 % : il peut etre adopte (le journal le dit au joueur)."""
    t = tech.TECHS[tid]
    if not is_human(state, tribe.id):
        return
    if born(state, tid):
        text = f"Le grand tournant {t.name} est arrivé chez vous : vous pouvez l'adopter (Savoirs)."
    else:
        text = (
            f"Un grand tournant est à votre portée : {t.name}. Encore jamais découvert : "
            f"le premier peuple à l'adopter (Savoirs) en sera le berceau ({cradle_text(tid)})."
        )
    note(state, LogKind.DECOUVERTE, text, to=tribe.id)


def cradle_text(tid: str) -> str:
    """Le bonus du berceau en une ligne."""
    effects = tech.effect_lines(tech.spec_effect("berceau:" + tid)) if tid in CRADLE else []
    return f"prestige +{BIRTH_PRESTIGE}" + ("" if not effects else ", et pour toujours : " + ", ".join(e[:1].lower() + e[1:] for e in effects))


def on_adopted(state, tribe, tid: str) -> None:
    """La recherche d'un tournant est terminee chez ce peuple : il l'a
    decouvert. Le premier du monde en est le berceau."""
    t = tech.TECHS[tid]
    if born(state, tid):
        if is_human(state, tribe.id):
            note(state, LogKind.DECOUVERTE, f"Votre peuple a adopté le grand tournant {t.name} : tout un pan de savoirs s'ouvre.", to=tribe.id)
        return
    state.research.setdefault("births", {})[tid] = [tribe.id, state.clock.year]
    gain_prestige(state, tribe, BIRTH_PRESTIGE)
    if tid in CRADLE and tid not in tribe.cradles:
        tribe.cradles.append(tid)
        tech.invalidate()
    for h in humans(state):
        if h == tribe.id:
            text = f"Vous êtes les premiers au monde à découvrir le grand tournant {t.name} : votre peuple en est le berceau ({cradle_text(tid)})."
        elif tribe.id in diplo.contacts_of(state, h):
            text = f"Les {tribe.name} ont découvert le grand tournant {t.name}, les premiers au monde. Il se répandra chez leurs voisins."
        else:
            text = f"On raconte qu'au loin un peuple a découvert un grand tournant : {t.name}."
        note(state, LogKind.DECOUVERTE, text, to=h)


def effect_ids(tribe) -> list:
    """Les bonus de berceau du peuple (systems.EFFECT_FIELDS)."""
    return ["berceau:" + t for t in (getattr(tribe, "cradles", None) or [])]


def effect_specs() -> dict:
    return {f"berceau:{t}": (f"Berceau : {tech.TECHS[t].name}", eff) for t, eff in CRADLE.items()}


def _visitors(state, tribe, tid: str) -> None:
    """Une fois par tournant : des voyageurs en parlent (une carte)."""
    lo, hi = VISIT_RANGE
    if not (lo <= presence(tribe, tid) <= hi):
        return
    told = state.research.setdefault("told", [])
    key = f"{tribe.id}:{tid}"
    if key in told:
        return
    src = next((who for _l, _v, who in sources(state, tribe.id, tid) if who), 0)
    if not src:
        return
    band = chiefs.chief_band(state, tribe.id)
    t = tech.TECHS[tid]
    if events.hook(state, "tournant_voyageurs", tribe_id=tribe.id, band_id=band.id if band else 0, other=src,
                   data={"tournant_id": tid, "tournant": t.name}):
        told.append(key)


def born_text(state, viewer: int, tid: str) -> str:
    """"Découvert par les Akor, an 23" ; "Découvert avant les mémoires"."""
    place = birthplace(state, tid)
    if place is None:
        return "Pas encore découvert"
    if not place[0]:
        return "Découvert avant que l'on s'en souvienne"
    who = state.tribes.get(place[0])
    by = "par vous" if place[0] == viewer else (f"par les {who.name}" if who else "par un peuple disparu")
    return f"Découvert {by}, an {place[1]}"


def adopted_by(state, tid: str) -> list[int]:
    return sorted(t for t in _living(state) if tid in state.tribes[t].knowledge)


def lines(state, tribe_id: int, tid: str) -> list[tuple[str, str]]:
    """Pour la fiche d'un tournant : (texte, style) ; style "ok", "manque",
    "note", "section"."""
    tribe = state.tribes[tribe_id]
    out: list = []
    pan = tech.pan_of(tid)
    more = len(tech.descendants(tid)) - len(pan)
    out.append((f"Il ouvre : {', '.join(p.name for p in pan)}" + (f", et {more} autres savoirs après eux" if more > 0 else ""), "note"))
    place = birthplace(state, tid)
    if place is None:
        out.append((f"Encore jamais découvert : le premier peuple à l'adopter en sera le berceau ({cradle_text(tid)}).", "note"))
    else:
        out.append((f"{born_text(state, tribe_id, tid)} ; adopté par {len(adopted_by(state, tid))} peuples.", "note"))
    if tid in tribe.knowledge:
        return out
    pres = presence(tribe, tid)
    out.append((f"Chez vous : {pres:.0f} %" + (" (arrivé : il peut être adopté)" if pres >= 100 else ""), "ok" if pres >= 100 else "note"))
    if pres < 100:
        rows = sources(state, tribe_id, tid)
        if not rows:
            out.append(("Rien ne l'apporte encore : il faut en remplir les conditions, ou connaître un peuple qui l'a adopté.", "manque"))
        gain = monthly_gain(state, tribe_id, tid)
        for label, value, _who in rows[:4]:
            out.append((f"{label} : +{value:g} par mois", "ok"))
        if gain > 0:
            months = int(-(-(100.0 - pres) // gain))
            out.append((f"Au total +{gain:g} par mois : arrivé dans ~{months} mois.", "note"))
    return out


# --- les vieilles parties ------------------------------------------------------------


def migrate(state) -> None:
    """Une partie d'avant les grands tournants : chaque peuple qui sait deja
    des savoirs du pan d'un tournant l'a adopte (la sedentarite : qui a un
    village) ; les berceaux : le plus ancien peuple qui l'a."""
    research = dict(getattr(state, "research", None) or {})
    if research.get("turnings"):
        _migrate_cradles(state)
        return
    research.setdefault("births", {})
    villages = {s.tribe_id for s in state.sites.values() if s.kind == "village"}
    for t in tech.turnings():
        pan = {p.id for p in tech.pan_of(t.id)}
        for tribe_id in sorted(state.tribes):
            tribe = state.tribes[tribe_id]
            if t.id in tribe.knowledge:
                continue
            if tribe.knowledge & pan or (t.id == "sedentarite" and tribe_id in villages):
                tech.grant(tribe, t.id)
        have = sorted(tid for tid, tr in state.tribes.items() if t.id in tr.knowledge)
        if have and t.id not in research["births"]:
            # Ne avant la memoire : on ne sait plus ou (peuple 0).
            research["births"][t.id] = [0, 0]
    research["turnings"] = 1
    research["births_v"] = 2
    state.research = research
    tech.invalidate()


def _migrate_cradles(state) -> None:
    """Une partie de la 0.10 : un tournant y "naissait" a 100 % de presence ;
    desormais il n'est decouvert qu'adopte. Un berceau qui ne l'a pas adopte
    ne l'est plus ; un vrai berceau recoit son bonus."""
    research = state.research
    if research.get("births_v") == 2:
        return
    births = research.setdefault("births", {})
    for tid, (who, _year) in list(births.items()):
        tribe = state.tribes.get(int(who))
        if who and (tribe is None or tid not in tribe.knowledge):
            del births[tid]
        elif who and tid in CRADLE and tid not in tribe.cradles:
            tribe.cradles.append(tid)
    for t in tech.turnings():
        if t.id not in births and any(t.id in tr.knowledge for tr in state.tribes.values()):
            births[t.id] = [0, 0]
    research["births_v"] = 2
    tech.invalidate()


# --- ce que les tournants ajoutent aux evenements (events.vocabulary) ---------------


def _ev_tournant(state, inst, tribe, band, amount) -> None:
    tid = inst.data.get("tournant_id")
    if tid in tech.TECHS and tid not in tribe.knowledge:
        value = min(100.0, presence(tribe, tid) + amount)
        tribe.tournants[tid] = value
        if value >= 100.0:
            _arrived(state, tribe, tid)


EVENT_EFFECTS = {"tournant": _ev_tournant}
EVENT_TEXTS = {"tournant": lambda a: f"le grand tournant arrive plus vite (+{a[0]:g} %)"}
