from src.kora.clock import Clock
from src.kora.sim import GameState
from src.kora.types import Band, Terrain, Tribe
from src.kora.vision import recompute_vision
from src.kora.world import hex_distance, make_filled_world, offset_to_axial


def test_vision_radius_hides_far_enemy():
    world = make_filled_world(40, 40, Terrain.PLAINE)
    p = offset_to_axial(10, 10)
    far = offset_to_axial(10, 35)
    near = offset_to_axial(12, 12)
    pb = Band(id=1, tribe_id=1, position=p, population=10, stock=40)
    enemy_far = Band(id=2, tribe_id=2, position=far, population=10, stock=40)
    enemy_near = Band(id=3, tribe_id=2, position=near, population=10, stock=40)
    st = GameState(
        world=world,
        clock=Clock(),
        tribes={
            1: Tribe(1, "p", 20, True),
            2: Tribe(2, "e", 20, False),
        },
        bands={1: pb, 2: enemy_far, 3: enemy_near},
    )
    vis = recompute_vision(st)
    assert hex_distance(p, far) >= 20
    assert far not in vis.visible
    assert hex_distance(p, near) <= 8
    assert near in vis.visible
