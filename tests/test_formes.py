"""Le monde en formes (formes.py, le monde sans grille) : des formes
COHERENTES - le rivage d'abord, les sols dans les terres, la plage collee au
rivage, les rivieres jusqu'a l'eau ; un etang d'une case reste un etang ;
un ilot d'une case au large disparait ; "quel sol ici ?" sans case."""

from src.kora import formes
from src.kora.types import Terrain
from src.kora.world import World

T = Terrain


def _coast_world():
    """60 x 40 : la mer a l'ouest (colonnes < 20), la plage le long, une
    plaine, une foret, un etang d'une case, un ilot d'une case au large ; une
    riviere qui coule vers l'ouest et s'arrete deux cases avant la mer (un
    delta)."""
    w, h = 60, 40
    grid = [[T.PLAINE for _ in range(w)] for _ in range(h)]
    for row in range(h):
        for col in range(w):
            if col < 20:
                grid[row][col] = T.EAU
            elif col == 20:
                grid[row][col] = T.COTE
            elif 35 <= col < 45 and 5 <= row < 15:
                grid[row][col] = T.FORET
    grid[8][8] = T.PLAINE  # l'ilot d'une case, au large
    grid[30][40] = T.EAU  # l'etang d'une case
    world = World(grid)
    layer = bytearray(w * h)
    for col in range(23, 55):
        layer[25 * w + col] = (3 + 1) | (2 << 3)  # vers l'ouest, une riviere
    world.set_rivers(bytes(layer))
    return world


def test_shapes_are_coherent_on_a_coast():
    world = _coast_world()
    sh = formes.build(world, 0, 0, 60, 40)
    report = sh.check()
    assert report["plages loin du rivage"] == 0
    assert report["rivières sans embouchure"] == 0
    assert report["îlots enlevés"] == 1
    assert report["terre et eau comme les cases"] >= 97.0
    assert report["sols comme les cases (à l'intérieur)"] >= 95.0
    # La mer, la plage, la plaine, la foret : chacune a sa place.
    assert sh.soil_at(10.0, 20.0) == formes.WATER
    assert sh.soil_at(20.2, 20.0) == formes.COAST
    assert sh.soil_at(28.0, 30.0) == formes.CODE[T.PLAINE]
    assert sh.soil_at(40.0, 10.0) == formes.CODE[T.FORET]
    # L'ilot d'une case au large n'est plus la ; l'etang d'une case, si.
    assert not sh.is_land(8.0, 8.0)
    dx, dy = formes.wobble(40.0, 30.0, 60)
    assert not sh.is_land(40.0 + dx, 30.0 + dy)
    assert sh.is_land(42.0, 30.0)
    # La plage ne flotte jamais : chaque point est sur le rivage, et la plage
    # est toujours sur la terre.
    for line in sh.beaches:
        for x, y in line[::5]:
            assert sh.coast_distance(x, y) < 0.06
    for y in range(2, 38, 3):
        for dx in (-0.3, 0.3):
            x = 19.9 + dx
            if sh.soil_at(x, y) == formes.COAST:
                assert sh.is_land(x, y)
    # La riviere va jusqu'au rivage (le delta s'arretait deux cases avant).
    (_size, line), = sh.rivers
    assert sh.coast_distance(*line[-1]) < 0.06


def test_no_soil_crosses_the_water_and_the_cost_follows_the_soil():
    world = _coast_world()
    sh = formes.build(world, 0, 0, 60, 40)
    for y in range(1, 39):
        for x in range(1, 19, 2):
            if (x, y) != (8, 8):
                assert sh.soil_at(x + 0.5, y + 0.5) == formes.WATER
    assert sh.cost_at(10.0, 20.0) is None
    assert sh.cost_at(28.0, 30.0) < sh.cost_at(40.0, 10.0)


def test_shapes_hold_on_a_real_planet():
    """Une region d'Aurane (la planete livree) : coherente, et fidele aux
    cases loin des bords."""
    from src.kora import planets

    world = planets.load("aurane")
    sh = formes.build(world, 690, 270, 100, 70)
    report = sh.check(samples=1500)
    assert report["plages loin du rivage"] == 0
    assert report["rivières sans embouchure"] == 0
    assert report["terre et eau comme les cases"] >= 97.0
    assert report["sols comme les cases (à l'intérieur)"] >= 95.0
