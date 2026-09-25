from dataclasses import dataclass, field

from src.kora.sim import PLAYER_TRIBE_ID, GameState
from src.kora.types import Hex

VISION_RADIUS = 8
TOWER_SIGHT = 3


@dataclass
class PlayerVision:
    explored: set[Hex] = field(default_factory=set)
    visible: set[Hex] = field(default_factory=set)
    # Positions des bandes du joueur au dernier calcul : si rien n'a bouge,
    # la vue est la meme (meme objet, le rendu n'a rien a resynchroniser).
    key: tuple | None = None


def recompute_vision(state: GameState) -> PlayerVision:
    vis = state.vision if isinstance(state.vision, PlayerVision) else PlayerVision()
    spots = sorted(
        (band.position.q, band.position.r)
        for band in state.bands.values()
        if band.tribe_id == PLAYER_TRIBE_ID and band.population > 0
    )
    radius = VISION_RADIUS
    player = state.tribes.get(PLAYER_TRIBE_ID)
    if player is not None:
        from src.kora import tech

        radius = tech.bonuses(player).vision
    # Tours de guet des villages : on voit plus loin autour.
    towers: list = []
    if state.sites:
        from src.kora import villages

        towers = villages.watch_spots(state, PLAYER_TRIBE_ID)
    key = (id(state.world), radius, tuple(spots), tuple(towers))
    if vis.key == key:
        state.vision = vis
        return vis
    visible: set[Hex] = set()
    for band in state.bands.values():
        if band.tribe_id != PLAYER_TRIBE_ID or band.population <= 0:
            continue
        visible.update(state.world.hexes_in_radius(band.position, radius))
    for h in towers:
        visible.update(state.world.hexes_in_radius(h, radius + TOWER_SIGHT))
    vis.visible = visible
    vis.explored |= visible
    vis.key = key
    state.vision = vis
    return vis


def is_visible(state: GameState, h: Hex) -> bool:
    vis = state.vision
    if not isinstance(vis, PlayerVision):
        return False
    return h in vis.visible


def is_explored(state: GameState, h: Hex) -> bool:
    vis = state.vision
    if not isinstance(vis, PlayerVision):
        return False
    return h in vis.explored


def enemy_band_visible(state: GameState, band) -> bool:
    if band.tribe_id == PLAYER_TRIBE_ID:
        return True
    return is_visible(state, band.position)
