from dataclasses import dataclass, field

from src.kora.gamestate import GameState, PLAYER_TRIBE_ID, humans, note, pov_of
from src.kora.log import LogKind
from src.kora.types import Hex
from src.kora import places, systems, tech

VISION_RADIUS = 8
TOWER_SIGHT = 3


@dataclass
class PlayerVision:
    explored: set[Hex] = field(default_factory=set)
    visible: set[Hex] = field(default_factory=set)
    # Positions des bandes du joueur au dernier calcul : si rien n'a bouge,
    # la vue est la meme (meme objet, le rendu n'a rien a resynchroniser).
    key: tuple | None = None
    # La memoire du brouillard (memory.py) : les lieux tels qu'on les a vus
    # (id -> [q, r, genre, peuple, palissade, suzerain]), les zones ((col, ligne) ->
    # [peuple, influence]) ; mem_gen change quand elle change.
    sites: dict = field(default_factory=dict)
    zones: dict = field(default_factory=dict)
    mem_gen: int = 0


def vision_of(state: GameState, tid: int = PLAYER_TRIBE_ID):
    """La vue d'un peuple joueur (None si elle n'est pas encore calculee).
    Le joueur solo garde la sienne dans state.vision, les autres dans
    state.povs (multijoueur)."""
    if tid == PLAYER_TRIBE_ID:
        vis = state.vision
    else:
        pov = state.povs.get(tid)
        vis = pov.vision if pov is not None else None
    return vis if isinstance(vis, PlayerVision) else None


def sharers(state: GameState, tid: int) -> list[int]:
    """Le peuple et ceux dont il partage la vue (systems.SIGHT : son
    suzerain, ses tributaires, ses confederes)."""
    out = [tid]
    for t in systems.parts(systems.SIGHT, state, tid):
        if t not in out and t in state.tribes:
            out.append(t)
    return out


def _recompute_for(state: GameState, tid: int, vis) -> PlayerVision:
    vis = vis if isinstance(vis, PlayerVision) else PlayerVision()
    eyes = sharers(state, tid)
    spots = sorted(
        (band.tribe_id, band.position.q, band.position.r)
        for band in state.bands.values()
        if band.tribe_id in eyes and band.population > 0
    )
    # Chacun voit a la portee de ses savoirs.
    radius = {t: tech.bonuses(state.tribes[t]).vision if t in state.tribes else VISION_RADIUS for t in eyes}
    # Tours de guet des villages : on voit plus loin autour.
    towers: list = []
    if state.sites:
        towers = [(t, h) for t in eyes for h in places.watch_spots(state, t)]
    key = (id(state.world), tuple(sorted(radius.items())), tuple(spots), tuple((t, h.q, h.r) for t, h in towers))
    if vis.key == key:
        return vis
    visible: set[Hex] = set()
    for band in state.bands.values():
        if band.tribe_id not in eyes or band.population <= 0:
            continue
        visible.update(state.world.hexes_in_radius(band.position, radius[band.tribe_id]))
    for t, h in towers:
        visible.update(state.world.hexes_in_radius(h, radius[t] + TOWER_SIGHT))
    vis.visible = visible
    vis.explored |= visible
    vis.key = key
    return vis


def recompute_vision(state: GameState) -> PlayerVision:
    """La vue de chaque peuple joueur ; rend celle du joueur solo."""
    vis = _recompute_for(state, PLAYER_TRIBE_ID, state.vision)
    state.vision = vis
    for tid in humans(state)[1:]:
        pov = pov_of(state, tid)
        pov.vision = _recompute_for(state, tid, pov.vision)
    return vis


def is_visible(state: GameState, h: Hex, tid: int = PLAYER_TRIBE_ID) -> bool:
    vis = vision_of(state, tid)
    if vis is None:
        return False
    return h in vis.visible


def is_explored(state: GameState, h: Hex, tid: int = PLAYER_TRIBE_ID) -> bool:
    vis = vision_of(state, tid)
    if vis is None:
        return False
    return h in vis.explored


def enemy_band_visible(state: GameState, band, tid: int = PLAYER_TRIBE_ID) -> bool:
    if band.tribe_id == tid:
        return True
    return is_visible(state, band.position, tid)


def note_seen(state: GameState, kind: LogKind, text, where: Hex, but=()) -> None:
    """A chaque joueur qui voit cette case (sauf `but`). text : une chaine,
    ou une fonction du joueur qui lit (tid -> chaine)."""
    for tid in humans(state):
        if tid in but or not is_visible(state, where, tid):
            continue
        note(state, kind, text(tid) if callable(text) else text, where, to=tid)
