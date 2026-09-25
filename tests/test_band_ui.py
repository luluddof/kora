from src.kora.app import _next_player_band, _refresh_selection
from src.kora.globe import FOCUS_ZOOM, look_at_hex, view_params
from src.kora.render import (
    BAND_BUTTONS,
    band_card_hit,
    band_card_layout,
    band_screen_positions,
    wrap_text,
)
from src.kora.sim import band_lines, band_summary, new_game, split_band
from src.kora.types import Terrain
from src.kora.world import make_filled_world


def _game():
    return new_game(make_filled_world(40, 24, Terrain.VALLEE, wrap_x=True))


def test_band_card_buttons_sit_inside_the_card_and_hit():
    layout = band_card_layout(1280, 720, 3)
    bx, by, bw, bh = layout["box"]
    assert by + bh <= 720
    for key, _label in BAND_BUTTONS:
        x, y, w, h = layout["buttons"][key]
        assert bx <= x and x + w <= bx + bw
        assert by <= y and y + h <= by + bh
        assert band_card_hit(layout, x + w // 2, y + h // 2) == key
    assert band_card_hit(layout, bx + 4, by + 4) == "card"
    assert band_card_hit(layout, 5, 5) is None
    assert band_card_hit({}, 5, 5) is None


def test_band_card_leaves_room_for_the_pinned_case_on_the_left():
    layout = band_card_layout(1280, 720, 4)
    assert layout["box"][0] >= 276


def test_band_lines_show_stock_food_and_local_winter():
    st = _game()
    lines = band_lines(band_summary(st, 1))
    assert "40 personnes" in lines[0]
    assert "Collecte" in lines[1]
    assert "hiver ici" in lines[2]


def test_stacked_bands_get_distinct_screen_spots():
    st = _game()
    nid = split_band(st, 1)
    yaw, pitch = look_at_hex(st.bands[1].position, st.world.width, st.world.height)
    gcx, gcy, focal, dist = view_params(FOCUS_ZOOM, 1280, 720, 48)
    spots = band_screen_positions(st, yaw, pitch, gcx, gcy, focal, dist)
    assert spots[1][:2] != spots[nid][:2]


def test_selection_can_be_empty_and_falls_back_when_the_band_is_gone():
    st = _game()
    assert _refresh_selection(st, None) is None
    nid = split_band(st, 1)
    assert _refresh_selection(st, nid) == nid
    del st.bands[nid]
    assert _refresh_selection(st, nid) == 1


def test_tab_cycles_through_player_bands_only():
    st = _game()
    nid = split_band(st, 1)
    assert _next_player_band(st, 1) == nid
    assert _next_player_band(st, nid) == 1
    assert _next_player_band(st, None) == 1


def test_wrap_text_keeps_every_word():
    text = "an 3 s.12  Raid de Steppe contre vous : vous perdez."
    lines = wrap_text(text, 38)
    assert all(len(line) <= 38 for line in lines)
    assert " ".join(lines).split() == text.split()


def test_only_placed_toasts_are_clickable():
    from src.kora.render import toast_hit

    placed = {"text": "Raid", "hex": (1, 2)}
    hits = [((10, 60, 200, 20), placed)]
    assert toast_hit(hits, 50, 70) is placed
    assert toast_hit(hits, 50, 90) is None
    assert toast_hit([], 50, 70) is None
