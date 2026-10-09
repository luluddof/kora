"""Mise en page des nouveaux panneaux (sans fenetre)."""

from src.kora.layout import HUD_HEIGHT, MAP_MODES, map_mode_hit, map_mode_layout, side_hit, side_layout
from src.kora.render_panels import event_modal_layout
from src.kora.layout import panel_box


def test_four_side_tabs_stack_on_the_right():
    layout = side_layout(1280, 720)
    tabs = layout["tabs"]
    assert list(tabs) == ["savoirs", "tribu", "peuples", "journal"]
    ys = [tabs[k][1] for k in tabs]
    assert ys == sorted(ys)
    for key, (x, y, w, h) in tabs.items():
        assert 1270 <= x + w <= 1280 and y >= HUD_HEIGHT and y + h <= 720
        assert side_hit(layout, x + 2, y + 2) == f"tab_{key}"


def test_panels_fit_on_small_and_large_screens():
    for w, h in ((1024, 640), (1280, 720), (1920, 1080)):
        for name in ("tribu", "peuples"):
            bx, by, bw, bh = panel_box(w, h, name)
            assert bx >= 0 and by >= HUD_HEIGHT and bx + bw <= w - 32 and by + bh <= h


def test_event_window_grows_with_its_text_and_options_fit():
    short = event_modal_layout(1280, 720, 2, 2)
    long = event_modal_layout(1280, 720, 4, 6)
    assert long["box"][3] > short["box"][3]
    bx, by, bw, bh = long["box"]
    for x, y, w, h in long["options"].values():
        assert bx <= x and x + w <= bx + bw and by <= y and y + h <= by + bh


def test_the_map_mode_button_opens_its_list():
    """Le bouton des modes de carte, en bas a gauche ; ouvert, la liste des
    modes au-dessus de lui."""
    shut = map_mode_layout(1280, 720)
    bx, by, bw, bh = shut["button"]
    assert by + bh <= 720 and bx < 100 and not shut["items"]
    assert map_mode_hit(shut, bx + 5, by + 5) == "menu"
    assert map_mode_hit(shut, 5, 400) is None
    layout = map_mode_layout(1280, 720, True)
    for key, _label in MAP_MODES:
        x, y, w, h = layout["items"][key]
        assert y + h <= by and y >= HUD_HEIGHT
        assert map_mode_hit(layout, x + 2, y + 2) == key
