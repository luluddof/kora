from src.kora.render import hex_to_pixel, pixel_to_hex, terrain_draw_mode, wrap_camera
from src.kora.types import Terrain
from src.kora.world import axial_to_offset, make_filled_world, offset_to_axial


def test_pixel_roundtrip_centerish():
    w = make_filled_world(20, 20, Terrain.PLAINE)
    h = offset_to_axial(5, 5)
    x, y = hex_to_pixel(h, 0, 0, 1.0)
    back = pixel_to_hex(x, y, 0, 0, 1.0, w)
    assert back is not None
    assert back == h


def test_pixel_to_hex_canonicalizes_wrapped_column():
    w = make_filled_world(10, 8, Terrain.PLAINE, wrap_x=True)
    drawn = offset_to_axial(10, 4)
    x, y = hex_to_pixel(drawn, 0, 0, 1.0)
    back = pixel_to_hex(x, y, 0, 0, 1.0, w)
    assert back is not None
    assert axial_to_offset(back)[0] == 0


def test_camera_x_wraps_when_map_wider_than_screen():
    w = make_filled_world(10, 8, Terrain.PLAINE, wrap_x=True)
    cx, cy = wrap_camera(w, -5.0, 10.0, 2.0, 200, 150)
    assert cx >= 0
    north = pixel_to_hex(10, 10, cx, cy, 2.0, w)
    if north is not None:
        assert axial_to_offset(north)[1] >= 0


def test_every_zoom_stays_on_the_sphere():
    assert terrain_draw_mode(0.6) == "sphere"
    assert terrain_draw_mode(1.0) == "sphere"
    assert terrain_draw_mode(2.0) == "sphere"
