"""LE TUTORIEL : les premieres minutes guidees, une fiche a la fois.

Quatorze etapes (STEPS) : chacune dit une chose du jeu, et la plupart
demandent un geste (tourner la planete, choisir sa bande, la faire marcher,
lancer le temps, ouvrir les savoirs, scinder un clan...). La fiche passe
d'elle-meme a la suivante quand le geste est fait (Step.done, lu a chaque
image : guide_update), apres un court "C'est fait" ; une etape sans geste a
son bouton Suivant. Ce qui est concerne s'eclaire (Step.target : un onglet,
le bouton du temps, celui des cartes).

On l'ouvre par le menu (Tutoriel : une partie neuve, guidee), ou dans toute
partie par le bouton Tuto (a cote du bouton Carte) ou F1 ; il reprend ou on
l'avait laisse. Son etat est celui de l'ECRAN (Play.ui["tuto"]), pas de la
partie : il ne se sauve pas, ne passe pas par commands.py et ne change
rien au jeu (il lit la partie et ce que montre l'ecran). Le dessin :
render_tutoriel.py. N'importe pas pygame.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Callable

# Le temps du "C'est fait !" avant l'etape suivante (secondes d'ecran).
DONE_PAUSE = 1.2


@dataclass(frozen=True)
class Step:
    key: str
    title: str
    text: str
    todo: str = ""
    done: Callable | None = None
    target: str = ""
    # ce que l'ecran fait en arrivant a l'etape (choisir sa bande : on la
    # deselectionne, pour que le joueur la choisisse lui-meme)
    enter: Callable | None = None


def _mine(play) -> list:
    me = play.state.viewer
    return [b for b in play.state.bands.values() if b.tribe_id == me and b.population > 0]


def _nomads(play) -> list:
    return [b for b in _mine(play) if not b.village and b.kind != "armee"]


def mark(play) -> dict:
    """Ce qu'une etape compare pour savoir si le geste est fait."""
    return {
        "yaw": play.globe_yaw,
        "pitch": play.globe_pitch,
        "zoom": play.zoom,
        "tick": play.state.tick_count,
        "bands": len(_nomads(play)),
        "where": {b.id: b.position for b in _mine(play)},
        "map_mode": getattr(play.renderer, "map_mode", ""),
    }


def _turned(play, m) -> bool:
    return abs(play.globe_yaw - m["yaw"]) + abs(play.globe_pitch - m["pitch"]) > 0.05 or abs(play.zoom - m["zoom"]) > 0.15


def _unselect(play) -> None:
    """Choisir sa bande : on la deselectionne (le joueur la choisit lui-meme)
    et la camera revient sur elle (il a pu tourner la planete loin d'elle)."""
    play.selected = None
    mine = _nomads(play)
    if mine and hasattr(play, "show_place"):
        play.show_place(mine[0].position)
        play.pinned_hex = None


def _picked(play, m) -> bool:
    band = play.state.bands.get(play.selected) if play.selected is not None else None
    return band is not None and band.tribe_id == play.state.viewer


def _walking(play, m) -> bool:
    return any(b.path or b.position != m["where"].get(b.id, b.position) for b in _mine(play))


def _two_weeks(play, m) -> bool:
    return play.state.tick_count >= m["tick"] + 2


def _tree_open(play, m) -> bool:
    # Au debut, aucun savoir n'est encore a sa portee (il faut du vecu) :
    # ouvrir l'arbre suffit, la fiche dit ce que chacun demande.
    return play.side_panel == "savoirs"


def _split(play, m) -> bool:
    return len(_nomads(play)) > max(1, m["bands"])


def _peoples(play, m) -> bool:
    return play.side_panel == "peuples"


def _journal(play, m) -> bool:
    return play.side_panel == "journal"


def _other_map(play, m) -> bool:
    return getattr(play.renderer, "map_mode", "") != m["map_mode"]


STEPS = (
    Step(
        "bienvenue", "Bienvenue",
        "Vous guidez un peuple qui vient de maîtriser le feu et la pierre taillée. Le monde est grand et "
        "vous en voyez peu : le reste dort dans le brouillard.",
        "Tournez la planète (clic droit maintenu, puis glisser) ou zoomez (molette).",
        _turned,
    ),
    Step(
        "bande", "Vos gens",
        "Le rond à votre couleur, c'est une bande : vos gens, leurs réserves, leur chef (la couronne). "
        "Sa fiche, en bas de l'écran, dit tout d'elle.",
        "Cliquez sur votre bande pour la choisir.",
        _picked,
        "",
        _unselect,
    ),
    Step(
        "marcher", "Marcher",
        "Une bande choisie, un clic sur la carte l'y envoie. La marche est lente : quatre cases de plaine "
        "par semaine, moins en forêt et en montagne ; le long d'une rivière, le courant aide.",
        "Envoyez votre bande quelque part (clic gauche sur la carte).",
        _walking,
    ),
    Step(
        "temps", "Le temps",
        "Le temps est arrêté. Espace le lance ou l'arrête ; les touches 1 à 5 règlent sa vitesse. "
        "Une semaine passe à chaque pas.",
        "Lancez le temps et laissez passer deux semaines.",
        _two_weeks,
        "hud:pause",
    ),
    Step(
        "manger", "Manger",
        "La fiche de la bande dit ce qu'elle a en réserve (Stock), ce qu'elle trouve autour d'elle "
        "(Collecte) et ce qu'il lui faut (besoin). Une terre trop cueillie s'épuise : il faut bouger. "
        "Survolez une case : ce qu'elle donne, ce que coûte la marche.",
    ),
    Step(
        "hiver", "L'hiver",
        "L'hiver tue. Faites des réserves à l'automne et cherchez les vallées et le bord des rivières ; "
        "la saison avance sur la carte, elle n'arrive pas partout en même temps.",
    ),
    Step(
        "savoirs", "Les savoirs",
        "Votre peuple apprend en vivant : ce qu'il chasse, les terres qu'il traverse, les hivers qu'il "
        "passe. Un savoir s'étudie quand ses conditions sont remplies : survolez-le pour savoir ce qu'il "
        "lui faut, puis choisissez-le.",
        "Ouvrez les Savoirs (T, ou l'onglet à droite).",
        _tree_open,
        "tab:savoirs",
    ),
    Step(
        "clans", "Les clans",
        "Une bande peut se diviser : un clan part chercher sa nourriture ailleurs, plus de terres et "
        "moins de faim. Réunir (F) rassemble les bandes proches. Trop loin du chef, un clan vous échappe.",
        "Scindez votre bande (touche S, ou Scinder sur sa fiche).",
        _split,
    ),
    Step(
        "peuples", "Les autres peuples",
        "Vous n'êtes pas seuls. L'onglet Peuples montre ceux que vous avez rencontrés, ce qu'ils pensent "
        "de vous et pourquoi ; un clic sur un peuple, sa diplomatie.",
        "Ouvrez l'onglet Peuples (P).",
        _peoples,
        "tab:peuples",
    ),
    Step(
        "combats", "Les combats",
        "Une de vos bandes choisie, un clic droit sur une bande étrangère l'attaque ; au survol, le "
        "rapport de force. Les combats sont durs : le vaincu perd ses vivres et se replie à pied.",
    ),
    Step(
        "journal", "Le journal",
        "Le journal raconte ce qui arrive ; les nouvelles passent en bas à droite et un clic y emmène la "
        "caméra. Les cartes d'événements, à gauche, attendent votre choix (E).",
        "Ouvrez le Journal (J).",
        _journal,
        "tab:journal",
    ),
    Step(
        "cartes", "Les cartes",
        "Le bouton Carte, en bas à gauche, change ce que montre la planète : le relief, l'influence de "
        "chaque peuple, les ressources, plus tard le commerce et les suzerains.",
        "Choisissez une autre carte (bouton Carte, ou les touches Z et R).",
        _other_map,
        "carte",
    ),
    Step(
        "village", "Vers le village",
        "Après quelques années, les savoirs du néolithique (la sédentarité, les semailles) permettent de "
        "fonder un village (V, sur un campement) : un tournant. Vos clans nomades prendront alors leur "
        "indépendance, et viendront les champs, les métiers, le commerce, la guerre.",
    ),
    Step(
        "fin", "À vous",
        "Le tutoriel est fini. Le bouton Tuto (ou F1) le rouvre ; Échap ouvre le menu ; F5 sauvegarde "
        "(le jeu sauvegarde aussi tout seul). Bonne chasse !",
        "",
        None,
        "tuto",
    ),
)
BY_KEY = {s.key: s for s in STEPS}


# --- l'etat de l'ecran (Play.ui["tuto"]) ----------------------------------------------


def is_open(ui) -> bool:
    return bool(ui.get("tuto", {}).get("open"))


def current(ui) -> Step | None:
    g = ui.get("tuto")
    if not g or not g.get("open"):
        return None
    return STEPS[min(g["step"], len(STEPS) - 1)]


def guide_open(play, step: int | None = None) -> None:
    """Ouvre la fiche : a l'etape donnee, sinon la ou on l'avait laissee."""
    g = play.ui.setdefault("tuto", {"step": 0})
    if step is not None:
        g["step"] = step
    g["open"] = True
    _arrive(play, g)


def _arrive(play, g) -> None:
    """Une etape commence : son action d'entree, puis ce qu'on comparera."""
    step = STEPS[min(g.get("step", 0), len(STEPS) - 1)]
    if step.enter is not None:
        step.enter(play)
    g["mark"] = mark(play)
    g["wait"] = None


def guide_close(play) -> None:
    g = play.ui.get("tuto")
    if g:
        g["open"] = False


def guide_toggle(play) -> None:
    if is_open(play.ui):
        guide_close(play)
    else:
        guide_open(play)


def go(play, delta: int) -> None:
    """L'etape suivante (+1) ou precedente (-1) ; apres la derniere, fermer
    (et repartir du debut la prochaine fois)."""
    g = play.ui.setdefault("tuto", {"step": 0})
    nxt = g.get("step", 0) + delta
    if nxt >= len(STEPS):
        g["step"] = 0
        guide_close(play)
        return
    g["step"] = max(0, nxt)
    _arrive(play, g)


def guide_update(play, dt: float) -> None:
    """Chaque image : le geste de l'etape est-il fait ? Alors "C'est fait"
    un instant, puis l'etape suivante."""
    g = play.ui.get("tuto")
    if not g or not g.get("open"):
        return
    step = current(play.ui)
    if g.get("wait") is not None:
        g["wait"] -= dt
        if g["wait"] <= 0:
            go(play, 1)
        return
    if step.done is not None and step.done(play, g["mark"]):
        g["wait"] = DONE_PAUSE


def doing(ui) -> str:
    """Ce que la fiche montre sous le texte : "fait" (le geste est fait),
    "geste" (un geste attendu), "lire" (le bouton Suivant)."""
    g = ui.get("tuto") or {}
    step = current(ui)
    if step is None:
        return ""
    if g.get("wait") is not None:
        return "fait"
    return "geste" if step.done is not None else "lire"
