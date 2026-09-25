import math

from src.kora.globe import (
    FOCUS_ZOOM,
    dist_from_zoom,
    globe_uses_texture,
    hex_corner_xyz,
    hex_to_globe_screen,
    hit_globe,
    lonlat_to_colrow,
    look_at_hex,
    look_at_offset,
    look_center,
    offset_to_xyz,
    pixel_to_hex_globe,
    view_params,
    visible_hex_radius,
)
from src.kora.types import Terrain
from src.kora.world import axial_to_offset, make_filled_world, offset_to_axial


def test_date_line_hexes_are_neighbors_on_the_sphere():
    width, height = 40, 20
    west = offset_to_xyz(0, 10, width, height)
    east = offset_to_xyz(width - 1, 10, width, height)
    far = offset_to_xyz(width // 2, 10, width, height)
    seam = math.dist(west, east)
    across = math.dist(west, far)
    assert seam < across * 0.25


def test_north_pole_sits_above_the_equator():
    north = offset_to_xyz(0, 0, 40, 20)
    equator = offset_to_xyz(0, 10, 40, 20)
    assert north[1] > equator[1]


def test_back_of_the_planet_is_hidden():
    world = make_filled_world(40, 20, Terrain.PLAINE)
    front = offset_to_axial(20, 10)
    back = offset_to_axial(0, 10)
    shown = hex_to_globe_screen(front, world, 0.0, 0.0, 200, 200, 180, 2.4)
    hidden = hex_to_globe_screen(back, world, 0.0, 0.0, 200, 200, 180, 2.4)
    assert shown is not None
    assert hidden is None


def test_click_on_globe_center_hits_the_facing_hex():
    world = make_filled_world(40, 20, Terrain.PLAINE, wrap_x=True)
    hx = pixel_to_hex_globe(200, 200, world, 0.0, 0.0, 200, 200, 180, 2.4)
    assert hx is not None
    col, row = axial_to_offset(hx)
    assert 16 <= col <= 24
    assert 8 <= row <= 12


def test_close_zoom_stays_on_the_sphere():
    world = make_filled_world(40, 20, Terrain.PLAINE, wrap_x=True)
    hx = pixel_to_hex_globe(200, 200, world, 0.0, 0.0, 200, 200, 400, 1.12)
    assert hx is not None
    hidden = hex_to_globe_screen(
        offset_to_axial(0, 10), world, 0.0, 0.0, 200, 200, 400, 1.12
    )
    assert hidden is None


def test_zoom_in_brings_the_camera_closer():
    assert dist_from_zoom(0.12) > dist_from_zoom(2.0)
    assert dist_from_zoom(2.0) < 1.4
    assert dist_from_zoom(4.0) < 1.12


def test_adjacent_hex_corners_meet():
    exact_a = hex_corner_xyz(10, 10, 40, 20, inflate=1.0)
    exact_b = hex_corner_xyz(11, 10, 40, 20, inflate=1.0)
    gap = min(math.dist(p, q) for p in exact_a for q in exact_b)
    assert gap < 1e-6
    grown = hex_corner_xyz(10, 10, 40, 20)
    center = offset_to_xyz(10, 10, 40, 20)
    assert max(math.dist(center, p) for p in grown) > max(
        math.dist(center, p) for p in exact_a
    )


def test_close_camera_only_needs_nearby_hexes():
    world = make_filled_world(384, 192, Terrain.PLAINE, wrap_x=True)
    close = visible_hex_radius(world, 1.12, 1280, 720, 660)
    assert close <= 28
    assert close < 40
    mid = visible_hex_radius(world, 1.80, 1280, 720, 660)
    assert mid >= close


def test_mid_zoom_keeps_sharp_hexes_not_a_tiny_texture():
    assert globe_uses_texture(440, 1280, 720) is False
    assert globe_uses_texture(200, 1280, 720) is True


def test_globe_center_ray_hits_facing_lonlat():
    hit = hit_globe(0.0, 0.0, 0.0, 0.0, 2.4)
    assert hit is not None
    lon, lat, z = hit
    assert abs(lon) < 0.12
    assert abs(lat) < 0.12
    assert z > 0.8
    assert hit_globe(4.0, 4.0, 0.0, 0.0, 2.4) is None


def test_look_at_offset_puts_hex_near_screen_center():
    world = make_filled_world(40, 20, Terrain.PLAINE, wrap_x=True)
    h = offset_to_axial(8, 12)
    col, row = axial_to_offset(h)
    yaw, pitch = look_at_offset(col, row, 40, 20)
    cx, cy, focal, dist = view_params(FOCUS_ZOOM, 400, 400, 48)
    pos = hex_to_globe_screen(h, world, yaw, pitch, cx, cy, focal, dist)
    assert pos is not None
    assert abs(pos[0] - cx) < 25
    assert abs(pos[1] - cy) < 25


def test_look_at_hex_matches_offset():
    h = offset_to_axial(8, 12)
    col, row = axial_to_offset(h)
    assert look_at_hex(h, 40, 20) == look_at_offset(col, row, 40, 20)


def test_look_at_matches_look_center():
    world = make_filled_world(40, 20, Terrain.PLAINE, wrap_x=True)
    h = offset_to_axial(8, 12)
    col, row = axial_to_offset(h)
    yaw, pitch = look_at_offset(col, row, 40, 20)
    ccol, crow = look_center(world, yaw, pitch)
    assert abs(ccol - col) < 0.6
    assert abs(crow - row) < 0.6


def test_lonlat_wraps_to_map_columns():
    col, row = lonlat_to_colrow(0.0, 0.0, 40, 20)
    assert 18 <= col <= 22
    assert 9 <= row <= 11
    west, _ = lonlat_to_colrow(-math.pi + 0.01, 0.0, 40, 20)
    east, _ = lonlat_to_colrow(math.pi - 0.01, 0.0, 40, 20)
    assert west <= 2
    assert east >= 37


def test_click_and_drawing_agree_on_the_hex_under_a_point():
    import random

    import numpy as np

    from src.kora.globe_draw import Planet

    world = make_filled_world(40, 20, Terrain.PLAINE, wrap_x=True)
    planet = Planet(world)
    rng = random.Random(3)
    lons = [rng.uniform(-math.pi, math.pi) for _ in range(400)]
    lats = [rng.uniform(-1.4, 1.4) for _ in range(400)]
    rows, cols = planet.cells_at(np.array(lons), np.array(lats))
    for lon, lat, row, col in zip(lons, lats, rows.tolist(), cols.tolist()):
        assert lonlat_to_colrow(lon, lat, 40, 20) == (col, row)
