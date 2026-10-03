"""L'APPROCHE d'un dirigeant : comment le chef d'un peuple de l'IA voit ses
voisins, selon SA PERSONNALITE (ses traits) et la SITUATION de son pays.

  Conquerant   il veut des tributaires, et les prend par les armes s'il le
               faut (ambitieux, guerrier ; fort face a des voisins faibles)
  Protecteur   il gagne ses voisins par les dons, les fetes et sa protection
               (genereux, rassembleur ; fort, avec un village)
  Marchand     il cherche des routes et des partenaires (sage ; des accords
               commerciaux deja ouverts)
  Paisible     il reste chez lui, ses champs, ses betes (sage, prudent ;
               personne a craindre ni a soumettre)
  Mefiant      des voisins trop forts : il cherche des allies et menage les
               puissants (prudent ; un voisin bien plus fort, des raids subis)
  Aux abois    la faim : il raidera qui il pourra
  Soumis /     un tributaire : il paie et suit son suzerain, ou il cherche
  Retif        a s'en defaire (selon son agitation)

Chaque mois, chaque approche recoit des points (traits, culture, forces des
voisins, vivres, commerce, raids subis, tributaires) ; le chef garde la
sienne tant qu'une autre ne la depasse pas nettement (HYSTERESIS) ; un
nouveau chef choisit la sienne. Tribe.approach / approach_since /
approach_chief (sauves).

Ce que change l'approche (PROFILES) : l'envie de raider et de lever des
troupes (ai.py), d'exiger un tribut, d'offrir sa protection, de faire des
dons et des fetes, le seuil des alliances et du commerce (diplo.ai_monthly,
les propositions au joueur) ; et ce que le peuple REPOND aux propositions
(ACCEPT : une raison de plus dans diplo.evaluate, "Leur chef : ...").
Les peuples joueurs n'ont pas d'approche : le joueur decide.
N'importe pas pygame.
"""

from __future__ import annotations

from src.kora import battle, chiefdom, chiefs, diplo, peoples, tech
from src.kora.gamestate import humans, is_human, note
from src.kora.log import LogKind

APPROACHES = {
    "conquerant": ("Conquérant", "Il veut des tributaires, et les prend par les armes s'il le faut."),
    "protecteur": ("Protecteur", "Il gagne ses voisins par les dons, les fêtes et sa protection."),
    "marchand": ("Marchand", "Il cherche des routes et des partenaires : la guerre gâche le commerce."),
    "paisible": ("Paisible", "Il reste chez lui : ses champs, ses bêtes, ses morts."),
    "mefiant": ("Méfiant", "Ses voisins l'inquiètent : il cherche des alliés et ménage les puissants."),
    "affame": ("Aux abois", "La faim : il raidera qui il pourra."),
    "soumis": ("Soumis", "Tributaire, il paie et suit son suzerain."),
    "retif": ("Rétif", "Tributaire, il cherche à se défaire de son suzerain."),
}
ORDER = tuple(APPROACHES)
# Ce que l'approche change pour ses voisins (l'ecran Peuples).
BEHAVIOR = {
    "conquerant": ("Raide et lève des troupes deux fois plus souvent", "Exige des tributs aux plus faibles", "Soumet les villages qu'il prend"),
    "protecteur": ("Offre sa protection aux plus faibles", "Fait des dons et des fêtes", "Raide peu"),
    "marchand": ("Propose des échanges même à des voisins peu amis", "Toujours prêt à signer un accord commercial", "Raide peu"),
    "paisible": ("Raide rarement", "Prêt à faire la trêve"),
    "mefiant": ("Cherche des alliés", "Prêt à se ranger sous la protection d'un plus fort", "Lève des troupes pour se défendre"),
    "affame": ("Raide qui il peut", "Met à sac les villages qu'il prend"),
    "soumis": ("Paie son tribut", "Raide peu"),
    "retif": ("Refuse toute protection", "Cherche des alliés contre son suzerain"),
}
FREE = ("conquerant", "protecteur", "marchand", "paisible", "mefiant", "affame")
PEACE = ("paisible", "marchand", "protecteur", "mefiant", "conquerant", "affame")

# Ce qu'une approche change aux decisions de l'IA (1.0 : comme avant).
#   raid, army      envie de raider, de lever une troupe sans menace
#   tribute         exiger un tribut d'un plus faible
#   protect         offrir sa protection a un plus faible
#   gift            faire des dons a ses voisins
#   feast           donner la grande fete plus tot (grenier moins plein)
#   alliance_rel, commerce_rel   la relation qu'il faut pour proposer
PROFILES = {
    "conquerant": {"raid": 2.0, "army": 2.0, "tribute": 2.0, "protect": 0.6, "gift": 0.3, "commerce_rel": 10, "confed": 0.4},
    "protecteur": {"raid": 0.5, "army": 0.8, "tribute": 0.4, "protect": 3.0, "gift": 2.0, "feast": 1.5},
    "marchand": {"raid": 0.5, "army": 0.7, "tribute": 0.5, "gift": 1.0, "commerce_rel": -15, "confed": 1.5},
    "paisible": {"raid": 0.3, "army": 0.6, "tribute": 0.2, "protect": 0.5, "confed": 1.5},
    "mefiant": {"raid": 0.7, "army": 1.3, "tribute": 0.3, "protect": 0.5, "alliance_rel": -15, "confed": 1.3},
    "affame": {"raid": 2.5, "army": 1.5, "tribute": 1.5, "protect": 0.2, "gift": 0.0},
    "soumis": {"raid": 0.5, "army": 0.8, "tribute": 0.2, "protect": 0.3},
    "retif": {"raid": 1.0, "army": 1.2, "tribute": 0.5, "protect": 0.3, "alliance_rel": -10},
}
# Ce que le peuple repond, selon l'approche de son chef (diplo.evaluate).
ACCEPT = {
    "conquerant": {"treve": -10, "tribut": -15, "proteger": -15, "confederer": -10},
    "protecteur": {"treve": 10, "alliance": 10, "commerce": 5, "proteger": -10},
    "marchand": {"commerce": 15, "treve": 10, "alliance": 5},
    "paisible": {"treve": 15, "tribut": 5, "proteger": 5, "confederer": 10},
    "mefiant": {"alliance": 15, "proteger": 15, "tribut": 10, "treve": 10, "confederer": 10},
    "affame": {"treve": -5, "proteger": 10},
    "soumis": {"tribut": 5},
    "retif": {"proteger": -20, "alliance": 10},
}
# La personnalite : ce que chaque trait du chef apporte a chaque approche.
TRAIT_WEIGHTS = {
    "ambitieux": {"conquerant": 3.0},
    "guerrier": {"conquerant": 2.0},
    "querelleur": {"conquerant": 1.0, "mefiant": 1.0},
    "chasseur": {"conquerant": 0.5},
    "genereux": {"protecteur": 3.0},
    "rassembleur": {"protecteur": 2.0},
    "conteur": {"protecteur": 1.0, "paisible": 0.5},
    "fidele": {"protecteur": 1.0},
    "sage": {"paisible": 2.0, "marchand": 1.0},
    "prudent": {"mefiant": 2.0, "paisible": 1.0},
}
NEIGHBOR_GAP = 40
STRONG_NEIGHBOR = 1.6
WEAK_NEIGHBOR = 2.5
HUNGRY_WEEKS = 3.0
HYSTERESIS = 1.5
MIN_WEEKS = 12
RETIF_UNREST = 40.0
TELL_GAP = 60


def of(state, tid: int) -> str:
    """L'approche du chef de ce peuple ("" : un joueur, ou pas encore)."""
    tribe = state.tribes.get(tid)
    if tribe is None or is_human(state, tid):
        return ""
    return getattr(tribe, "approach", "") or ""


def factor(state, tid: int, key: str) -> float:
    return PROFILES.get(of(state, tid), {}).get(key, 1.0 if not key.endswith("_rel") else 0)


def accept(state, target: int, action: str):
    """(raison, points) que l'approche du chef de `target` ajoute a sa reponse."""
    a = of(state, target)
    v = ACCEPT.get(a, {}).get(action, 0)
    return (f"Leur chef : {APPROACHES[a][0].lower()}", v) if v else None


def name(state, tid: int) -> str:
    a = of(state, tid)
    return APPROACHES[a][0] if a else ""


# --- les points de chaque approche ------------------------------------------------------


def _powers(state) -> dict:
    out: dict = {}
    for b in state.bands.values():
        if b.population > 0:
            out[b.tribe_id] = out.get(b.tribe_id, 0.0) + battle.band_force(state, b)
    return out


def _food_weeks(state, tid: int) -> float:
    pop = stock = 0.0
    for b in state.bands.values():
        if b.tribe_id == tid and b.population > 0:
            pop += b.population
            stock += b.stock
    return stock / pop if pop else 0.0


def scores(state, tid: int, powers: dict | None = None) -> dict:
    """approche -> (points, [(raison, points)]) pour un peuple libre."""
    tribe = state.tribes[tid]
    powers = powers if powers is not None else _powers(state)
    pts = {a: [0.0, []] for a in FREE}

    def add(a, v, why):
        pts[a][0] += v
        pts[a][1].append((why, v))

    add("paisible", 1.0, "Par défaut, on vit de son pays")
    chief = chiefs.chief_of(state, tid)
    for t in (chief.traits if chief is not None else ()):
        for a, v in TRAIT_WEIGHTS.get(t, {}).items():
            add(a, v, chiefs.TRAITS[t].name if t in chiefs.TRAITS else t)
    culture = peoples.culture_of(tribe)
    if culture.raid_prestige <= 30:
        add("conquerant", 1.0, "Peuple guerrier")
    if culture.shy:
        add("paisible", 1.0, "Peuple discret")
    mine = max(1.0, powers.get(tid, 0.0))
    near = [o for o in diplo.contacts_of(state, tid) if o in powers and diplo.gap(state, tid, o) <= NEIGHBOR_GAP]
    if not near:
        add("paisible", 1.0, "Personne à sa porte")
    else:
        strong = max(near, key=lambda o: (powers[o], -o))
        weak = min(near, key=lambda o: (powers[o], o))
        if powers[strong] >= STRONG_NEIGHBOR * mine:
            add("mefiant", 3.0, f"Les {state.tribes[strong].name} sont bien plus forts")
        if mine >= WEAK_NEIGHBOR * max(1.0, powers[weak]):
            who = f"Des voisins faibles : les {state.tribes[weak].name}"
            add("conquerant", 2.0, who)
            add("protecteur", 2.0, who)
    if _food_weeks(state, tid) < HUNGRY_WEEKS:
        add("affame", 5.0, "La faim")
    b = tech.bonuses(tribe)
    if b.commerce and any(diplo.has_pact(state, tid, o, "commerce") for o in diplo.contacts_of(state, tid)):
        add("marchand", 2.0, "Des routes ouvertes")
    elif b.trade:
        add("marchand", 1.0, "Des sentiers de commerce")
    if chiefdom.has_chiefdom(state, tid):
        if len(chiefdom.vassals_of(state, tid)) >= chiefdom.vassal_cap(state, tid):
            add("conquerant", -2.0, "Assez de tributaires")
            add("protecteur", -2.0, "Assez de tributaires")
    else:
        # Sans village, pas de protection a offrir ni de routes.
        pts["protecteur"][0] = -99.0
        pts["marchand"][0] = -99.0
    raider = next((o for o in diplo.contacts_of(state, tid) if diplo._recent_raid(state, o, tid, 52) is not None), None)
    if raider is not None:
        add("mefiant", 1.5, f"Raidés par les {state.tribes[raider].name}")
        add("conquerant", 1.0, f"Venger les raids des {state.tribes[raider].name}")
    if tribe.prestige >= 70:
        # Un grand nom attire les clients autant qu'il pousse a la conquete.
        add("conquerant", 0.5, "Grand prestige")
        add("protecteur", 0.5, "Grand prestige")
    elif tribe.prestige < 20:
        add("paisible", 1.0, "Peu de prestige")
    if chiefdom.has_chiefdom(state, tid):
        for known, label in (("festins", "Festins de prestige"), ("biens_prestige", "Biens de prestige")):
            if known in tribe.knowledge:
                add("protecteur", 1.0, label)
    return {a: (v[0], v[1]) for a, v in pts.items()}


def choose(state, tid: int, powers: dict | None = None) -> tuple[str, list]:
    """L'approche que prendrait ce chef maintenant, et pourquoi."""
    lord = chiefdom.overlord_of(state, tid)
    if lord:
        u = chiefdom.unrest(state, tid, lord)
        why = [(f"Tributaire des {state.tribes[lord].name}", 0.0), (f"Agitation {u:.0f}", 0.0)]
        return ("retif" if u >= RETIF_UNREST else "soumis"), why
    pts = scores(state, tid, powers)
    current = getattr(state.tribes[tid], "approach", "")
    # A egalite, la voie la plus paisible.
    best = max(FREE, key=lambda a: (pts[a][0], -PEACE.index(a)))
    if current in pts and pts[best][0] < pts[current][0] + HYSTERESIS:
        best = current
    return best, sorted(pts[best][1], key=lambda r: -abs(r[1]))


def reasons(state, tid: int) -> list:
    """Pourquoi ce chef a cette approche (pour l'ecran Peuples)."""
    a = of(state, tid)
    if not a:
        return []
    if a in ("soumis", "retif"):
        return choose(state, tid)[1]
    return sorted(scores(state, tid)[a][1], key=lambda r: -abs(r[1]))


# --- le mois ---------------------------------------------------------------------------


def monthly(state) -> None:
    powers = _powers(state)
    living = {b.tribe_id for b in state.bands.values() if b.population > 0}
    for tid in sorted(living):
        tribe = state.tribes.get(tid)
        if tribe is None or is_human(state, tid):
            continue
        chief = chiefs.chief_of(state, tid)
        pid = chief.pid if chief is not None else 0
        before = getattr(tribe, "approach_chief", 0)
        new_chief = pid != before
        if not new_chief and state.tick_count - getattr(tribe, "approach_since", -10**6) < MIN_WEEKS:
            continue
        if new_chief:
            tribe.approach = ""
        a, _why = choose(state, tid, powers)
        tribe.approach_chief = pid
        if a == tribe.approach:
            continue
        old = tribe.approach
        tribe.approach = a
        tribe.approach_since = state.tick_count
        # Un vrai changement (pas le premier choix d'une vieille partie).
        if old or (new_chief and before):
            _tell(state, tid, a, new_chief)


def _tell(state, tid: int, a: str, new_chief: bool) -> None:
    """Les joueurs qui connaissent ce peuple l'apprennent."""
    tribe = state.tribes[tid]
    chief = chiefs.chief_of(state, tid)
    who = chief.name if chief is not None else "leur chef"
    label, about = APPROACHES[a]
    text = (
        f"Chez les {tribe.name}, le nouveau chef {who} se montre {label.lower()} : {about[0].lower()}{about[1:]}"
        if new_chief
        else f"Chez les {tribe.name}, {who} se fait {label.lower()} : {about[0].lower()}{about[1:]}"
    )
    for h in humans(state):
        # Les voisins seulement : un chef lointain ne fait pas la nouvelle.
        if diplo.in_contact(state, h, tid) and diplo.gap(state, h, tid) <= TELL_GAP:
            note(state, LogKind.POLITIQUE, text, to=h)
