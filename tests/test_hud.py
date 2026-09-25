import os

from src.kora.render import (
    HUD_HEIGHT,
    FILTER_BY_HIT,
    fight_panel_layout,
    hud_hit,
    hud_layout,
    menu_hit,
    menu_layout,
    side_hit,
    side_layout,
)


def test_speed_squares_are_five_and_ordered():
    layout = hud_layout(1280)
    xs = [layout["speeds"][n][0] for n in range(1, 6)]
    assert xs == sorted(xs)
    pause = layout["pause"]
    assert pause[0] + pause[2] < layout["speeds"][1][0]


def test_hit_pause_and_speed():
    layout = hud_layout(1280)
    px, py, pw, ph = layout["pause"]
    assert hud_hit(layout, px + 2, py + 2) == "pause"
    sx, sy, sw, sh = layout["speeds"][3]
    assert hud_hit(layout, sx + 2, sy + 2) == ("speed", 3)
    assert hud_hit(layout, 10, HUD_HEIGHT + 20) is None
    assert "decisions" not in layout


def test_side_tabs_are_on_the_right_when_closed():
    layout = side_layout(1280, 720, panel=None)
    tx, ty, tw, th = layout["tab_savoirs"]
    assert tx + tw == 1280
    assert ty >= HUD_HEIGHT
    jx, jy, jw, jh = layout["tab_journal"]
    assert jx + jw == 1280
    assert jy >= ty + th
    assert not any(k.startswith("tech:") for k in layout["items"])
    assert side_hit(layout, tx + 2, ty + 2) == "tab_savoirs"
    assert side_hit(layout, jx + 2, jy + 2) == "tab_journal"
    assert side_hit(layout, 400, 400) is None


def test_savoirs_tree_is_a_canvas_you_pan_and_zoom():
    from src.kora import tech
    from src.kora.render import pan, tech_world, tree_zoom_min, zoom_at

    world = tech_world()
    for w, h in ((1280, 720), (1024, 640), (1920, 1080)):
        layout = side_layout(w, h, panel="savoirs")
        bx, by, bw, bh = layout["box"]
        assert bx >= 0 and bx + bw <= w - 32
        assert by >= HUD_HEIGHT and by + bh <= h
        view = layout["tech"]["view"]
        # Tout l'arbre, vu de loin : chaque savoir se clique, rien ne se
        # chevauche, les paliers descendent, chaque branche garde sa colonne.
        far = side_layout(w, h, panel="savoirs", tech_cam=(0.0, 0.0, 0.01))
        assert far["tech"]["cam"][2] == tree_zoom_min(view, world)
        rects = {}
        for tid in tech.TECHS:
            x, y, rw, rh = far["items"][f"tech:{tid}"]
            vx, vy, vw, vh = far["tech"]["view"]
            assert vx <= x and x + rw <= vx + vw and vy <= y and y + rh <= vy + vh
            assert side_hit(far, x + rw // 2, y + rh // 2) == f"tech:{tid}"
            rects[tid] = (x, y, rw, rh)
        values = list(rects.values())
        for i, a in enumerate(values):
            for b in values[i + 1:]:
                assert a[0] + a[2] <= b[0] or b[0] + b[2] <= a[0] or a[1] + a[3] <= b[1] or b[1] + b[3] <= a[1]
        for t in tech.TECHS.values():
            for pid in t.prereqs:
                assert rects[pid][1] < rects[t.id][1]
        assert rects["semis"][0] == rects["champs"][0]
        assert rects["poterie"][0] == rects["greniers"][0]
        neo_top = min(rects[t.id][1] for t in tech.TECHS.values() if t.tier >= 4)
        assert all(rects[t.id][1] < neo_top for t in tech.TECHS.values() if t.tier <= 3)
        # A l'echelle 1, tout ne tient pas : on se deplace.
        near = side_layout(w, h, panel="savoirs", tech_cam=(0.0, 0.0, 1.0))
        assert len(near["tech"]["visible"]) < len(tech.TECHS)
        cam = near["tech"]["cam"]
        moved = pan(cam, view, world, -300, -200)
        assert moved[0] > cam[0] and moved[1] > cam[1]
        # On ne sort pas de la toile.
        corner = pan(cam, view, world, 10**6, 10**6)
        assert corner[0] == 0.0 and corner[1] == 0.0
        # Zoomer garde sous le curseur le meme point de la toile.
        mx, my = view[0] + 200, view[1] + 100
        zoomed = zoom_at(moved, view, world, mx, my, 1.15)
        before = (moved[0] + (mx - view[0]) / moved[2], moved[1] + (my - view[1]) / moved[2])
        after = (zoomed[0] + (mx - view[0]) / zoomed[2], zoomed[1] + (my - view[1]) / zoomed[2])
        assert abs(before[0] - after[0]) < 1e-6 and abs(before[1] - after[1]) < 1e-6
        # Les commandes de la vue passent avant ce qu'il y a dessous.
        for key in ("tzoom_in", "tzoom_out", "tcenter"):
            x, y, rw, rh = near["items"][key]
            assert side_hit(near, x + 3, y + 3) == key
        if near["tech"]["minimap_on"]:
            x, y, rw, rh = near["items"]["tminimap"]
            assert side_hit(near, x + 3, y + 3) == "tminimap"
        # Un clic sur la toile vide : on la glisse.
        detail = near["tech"]["detail"]
        assert detail[1] > view[1] + view[3]
        lx, ly, lw, lh = near["items"]["learn"]
        assert side_hit(near, lx + 2, ly + 2) == "learn"


def test_the_tree_draws_at_every_zoom():
    os.environ.setdefault("SDL_VIDEODRIVER", "dummy")
    import pygame

    from src.kora.render import Renderer
    from src.kora.sim import _default_world, new_game

    st = new_game(_default_world(), minor_peoples=0)
    pygame.init()
    try:
        r = Renderer(pygame.display.set_mode((1280, 720)))
        for z in (0.01, 0.7, 1.0, 1.6):
            ui = {"tech_cam": (100.0, 100.0, z)}
            r.draw(st, 0, 0, 1.0, None, side_panel="savoirs", ui=ui, tech_pick="feu")
            assert r.side_hits["tech"]["cam"][2] >= 0.25
    finally:
        pygame.quit()


def test_journal_panel_has_filters_and_sort():
    layout = side_layout(1280, 720, panel="journal")
    bx, by, bw, bh = layout["box"]
    assert bx > 1280 // 2
    for key in FILTER_BY_HIT:
        assert key in layout["items"]
        x, y, w, h = layout["items"][key]
        assert side_hit(layout, x + 2, y + 2) == key
    assert "sort_recent" in layout["items"]
    assert "sort_ancien" in layout["items"]
    rx, ry, rw, rh = layout["items"]["sort_recent"]
    assert side_hit(layout, rx + 2, ry + 2) == "sort_recent"
    ax, ay, aw, ah = layout["items"]["sort_ancien"]
    assert side_hit(layout, ax + 2, ay + 2) == "sort_ancien"
    assert side_hit(layout, bx + 8, by + 8) == "panel"


def test_escape_menu_has_resume_save_new_quit():
    layout = menu_layout(1280, 720)
    keys = set(layout["items"])
    assert keys == {"reprendre", "sauvegarder", "nouvelle", "quitter"}
    rx, ry, rw, rh = layout["items"]["reprendre"]
    assert menu_hit(layout, rx + 2, ry + 2) == "reprendre"
    sx, sy, sw, sh = layout["items"]["sauvegarder"]
    assert menu_hit(layout, sx + 2, sy + 2) == "sauvegarder"
    nx, ny, nw, nh = layout["items"]["nouvelle"]
    assert menu_hit(layout, nx + 2, ny + 2) == "nouvelle"
    qx, qy, qw, qh = layout["items"]["quitter"]
    assert menu_hit(layout, qx + 2, qy + 2) == "quitter"
    assert menu_hit(layout, 2, 2) is None


def test_fight_panel_sits_under_hud():
    layout = fight_panel_layout(1280, 720, 8)
    bx, by, bw, bh = layout["box"]
    assert by >= HUD_HEIGHT
    assert bw >= 200
    assert bh >= 80
    assert layout["close"][1] >= by
