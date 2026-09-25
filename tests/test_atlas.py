from src.kora.atlas import build_atlas_labels
from src.kora.types import Terrain
from src.kora.world import World


def test_wrapping_land_is_one_continent():
    width, height = 20, 10
    grid = [[Terrain.EAU for _ in range(width)] for _ in range(height)]
    for row in range(2, 8):
        for col in (0, 1, 18, 19):
            grid[row][col] = Terrain.PLAINE
    world = World(grid, wrap_x=True)
    labels = build_atlas_labels(world)
    lands = [lab for lab in labels if lab.kind == "land"]
    assert len(lands) == 1
    assert lands[0].name
    assert 0 <= lands[0].col < width


def test_large_ocean_is_named_in_french():
    width, height = 24, 12
    grid = [[Terrain.EAU for _ in range(width)] for _ in range(height)]
    for row in range(3, 9):
        for col in range(4, 10):
            grid[row][col] = Terrain.PLAINE
    world = World(grid, wrap_x=True)
    labels = build_atlas_labels(world)
    seas = [lab for lab in labels if lab.kind == "sea"]
    assert seas
    assert any(" " in lab.name or lab.name.lower().startswith("mer") or "ocean" in lab.name.lower() or "océan" in lab.name.lower() for lab in seas)
