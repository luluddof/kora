"""Menu de demarrage, creation du peuple et bonus de depart (5 ans)."""

import os
import random

os.environ.setdefault("SDL_VIDEODRIVER", "dummy")

import pygame

from src.kora import tech
from src.kora.persist import load_game, peek_save, save_game
from src.kora.sim import PLAYER_TRIBE_ID, new_game, tick
from src.kora.types import Terrain
from src.kora.world import make_filled_world


def _world():
    return make_filled_world(40, 20, Terrain.PLAINE, wrap_x=True)


def test_pool_has_twelve_bonuses_each_with_effects():
    assert len(tech.START_BONUSES) == 12
    for bonus in tech.START_BONUSES.values():
        assert bonus.name and bonus.about
        assert tech.start_bonus_lines(bonus), bonus.id


def test_setup_names_colors_and_grants_two_bonuses():
    st = new_game(_world(), setup={"name": "Aroha", "color": (60, 190, 190), "bonuses": ["bonus:conteurs", "bonus:froid", "bonus:fertiles"]})
    me = st.tribes[PLAYER_TRIBE_ID]
    assert me.name == "Aroha"
    assert me.color == (60, 190, 190)
    # Deux au plus : le troisieme est ignore.
    assert me.start_bonuses == ["bonus:conteurs", "bonus:froid"]
    assert me.start_bonus_until == tech.START_BONUS_WEEKS == 260
    b = tech.bonuses(me)
    assert b.learn == 1.3
    assert b.winter_famine == 0.6


def test_unknown_bonus_is_dropped_and_no_setup_changes_nothing():
    st = new_game(_world(), setup={"bonuses": ["bonus:rien", "bonus:fertiles"]})
    assert st.tribes[PLAYER_TRIBE_ID].start_bonuses == ["bonus:fertiles"]
    plain = new_game(_world())
    assert plain.tribes[PLAYER_TRIBE_ID].start_bonuses == []
    assert plain.tribes[PLAYER_TRIBE_ID].start_bonus_until == -1
    assert tech.bonuses(plain.tribes[PLAYER_TRIBE_ID]).growth == 1.0


def test_bonuses_speed_learning_and_growth():
    fast = new_game(_world(), setup={"bonuses": ["bonus:conteurs", "bonus:fertiles"]})
    slow = new_game(_world())
    assert tech.base_rate(fast, PLAYER_TRIBE_ID) > tech.base_rate(slow, PLAYER_TRIBE_ID) * 1.25
    assert tech.bonuses(fast.tribes[PLAYER_TRIBE_ID]).growth == 1.3


def test_bonuses_fade_after_five_years():
    st = new_game(_world(), setup={"bonuses": ["bonus:eclaireurs", "bonus:guerriers"]})
    me = st.tribes[PLAYER_TRIBE_ID]
    base_vision = tech.bonuses(new_game(_world()).tribes[PLAYER_TRIBE_ID]).vision
    assert tech.bonuses(me).vision == base_vision + 3
    st.tick_count = tech.START_BONUS_WEEKS - 1
    tech.update_start_bonuses(st)
    assert me.start_bonuses, "encore une semaine"
    st.tick_count = tech.START_BONUS_WEEKS
    tech.update_start_bonuses(st)
    assert me.start_bonuses == [] and me.start_bonus_until == -1
    assert tech.bonuses(me).vision == base_vision
    assert tech.bonuses(me).combat == 1.0
    assert any("bonus de départ s'éteignent" in e.text.lower() for e in st.log.entries)


def test_monthly_tick_ends_the_bonuses():
    st = new_game(_world(), setup={"bonuses": ["bonus:fertiles", "bonus:froid"]})
    me = st.tribes[PLAYER_TRIBE_ID]
    me.start_bonus_until = 3
    for _ in range(6):
        tick(st)
    assert me.start_bonuses == []


def test_bonuses_survive_save_and_load(tmp_path):
    world = _world()
    st = new_game(world, setup={"name": "Tahu", "color": (225, 110, 170), "bonuses": ["bonus:rivages", "bonus:prevoyants"]})
    path = tmp_path / "kora.json"
    save_game(st, path)
    loaded, _view = load_game(path, world)
    me = loaded.tribes[PLAYER_TRIBE_ID]
    assert me.start_bonuses == ["bonus:rivages", "bonus:prevoyants"]
    assert me.start_bonus_until == 260
    assert tech.bonuses(me).caches == tech.bonuses(st.tribes[PLAYER_TRIBE_ID]).caches
    info = peek_save(path)
    assert info["name"] == "Tahu"
    assert info["year"] == st.clock.year
    assert info["population"] == sum(b.population for b in st.bands.values() if b.tribe_id == PLAYER_TRIBE_ID)
    assert info["color"] == (225, 110, 170)


def test_peek_save_rejects_missing_or_foreign_files(tmp_path):
    assert peek_save(tmp_path / "rien.json") is None
    bad = tmp_path / "bad.json"
    bad.write_text('{"version": -5}', encoding="utf-8")
    assert peek_save(bad) is None
    bad.write_text("pas du json", encoding="utf-8")
    assert peek_save(bad) is None


# --- les ecrans --------------------------------------------------------------------


def test_title_buttons_hit_and_continue_needs_a_save():
    from src.kora import render_menu

    lay = render_menu.title_layout(1280, 720)
    for key in ("continuer", "nouvelle", "multijoueur", "quitter"):
        x, y, w, h = lay["buttons"][key]
        assert render_menu.title_hit(lay, x + 5, y + 5) == key
        assert y + h < 720
    x, y, _w, _h = lay["buttons"]["continuer"]
    assert render_menu.title_hit(lay, x + 5, y + 5, can_continue=False) is None
    assert render_menu.title_hit(lay, 2, 2) is None


def test_setup_screen_fits_and_every_card_is_clickable():
    from src.kora import render_menu

    for w, h in ((1280, 720), (1600, 900), (1920, 1080)):
        lay = render_menu.setup_layout(w, h)
        bx, by, bw, bh = lay["box"]
        assert bx >= 0 and by >= 0 and bx + bw <= w and by + bh <= h
        for bid, (x, y, cw, ch) in lay["cards"].items():
            assert render_menu.setup_hit(lay, x + cw // 2, y + ch // 2) == f"bonus:{bid}"
            assert y + ch < lay["start"][1]
        for i, (x, y, cw, ch) in enumerate(lay["colors"]):
            assert render_menu.setup_hit(lay, x + 3, y + 3) == f"color:{i}"
            assert x + cw <= bx + bw
        for key in ("start", "back", "random", "name"):
            x, y, _cw, _ch = lay[key]
            assert render_menu.setup_hit(lay, x + 3, y + 3) == key


def test_setup_clicks_pick_at_most_two_and_toggle():
    from src.kora import render_menu

    rng = random.Random(3)
    setup = render_menu.new_setup(rng)
    assert not render_menu.setup_ready(setup)
    assert render_menu.setup_click(setup, "bonus:bonus:froid", rng) == ""
    assert render_menu.setup_click(setup, "bonus:bonus:conteurs", rng) == ""
    assert render_menu.setup_ready(setup)
    assert "retirez" in render_menu.setup_click(setup, "bonus:bonus:fertiles", rng)
    assert setup["bonuses"] == ["bonus:froid", "bonus:conteurs"]
    render_menu.setup_click(setup, "bonus:bonus:froid", rng)
    assert setup["bonuses"] == ["bonus:conteurs"]
    assert "encore 1" in render_menu.setup_missing(setup)
    render_menu.setup_click(setup, "color:6", rng)
    assert setup["color"] == render_menu.PALETTE[6]
    render_menu.setup_click(setup, "random", rng)
    assert setup["name"] and setup["name"] != "Kora" or setup["name"]
    game = render_menu.setup_for_game(setup)
    assert game == {"name": setup["name"].strip(), "color": render_menu.PALETTE[6], "bonuses": ["bonus:conteurs"]}


def test_typing_the_name():
    from src.kora import render_menu

    pygame.init()
    setup = render_menu.new_setup(random.Random(1))
    render_menu.setup_click(setup, "name", random.Random(1))
    assert setup["typing"]

    def key(k, ch=""):
        render_menu.setup_key(setup, pygame.event.Event(pygame.KEYDOWN, key=k, unicode=ch))

    for _ in range(10):
        key(pygame.K_BACKSPACE)
    assert setup["name"] == ""
    for ch in "Ika'ri 9!":
        key(pygame.K_a, ch)
    assert setup["name"] == "Ika'ri "
    for _ in range(40):
        key(pygame.K_a, "a")
    assert len(setup["name"]) == render_menu.NAME_MAX
    key(pygame.K_RETURN)
    assert not setup["typing"]
    assert not render_menu.setup_missing({"name": "  ", "bonuses": []}) == ""


def test_screens_draw_without_error():
    from src.kora import render_menu
    from src.kora.render import Renderer

    pygame.init()
    screen = pygame.display.set_mode((1280, 720))
    r = Renderer(screen)
    scene = render_menu.TitleScene(_world())
    info = {"name": "Kora", "year": 3, "week": 5, "population": 40, "villages": 0, "dead": False}
    render_menu.draw_title(r, scene, info, 1.0, "un message")
    render_menu.draw_title(r, scene, None, 2.0)
    setup = render_menu.new_setup(random.Random(1))
    setup["bonuses"] = ["bonus:froid", "bonus:conteurs"]
    render_menu.draw_setup(r, setup, 1.0, info)
    render_menu.draw_setup(r, setup, 1.0, None, "Choisissez encore 1 bonus de départ.")
    assert r.title_hits and r.setup_hits
    # La planete du menu ne touche pas celle de la partie (son brouillard).
    assert r._planet is None or r._planet is not r._title_planet


def test_tribe_panel_shows_remaining_years():
    from src.kora.render_panels import start_bonus_text

    st = new_game(_world(), setup={"bonuses": ["bonus:froid", "bonus:conteurs"]})
    me = st.tribes[PLAYER_TRIBE_ID]
    assert "encore 5 ans" in start_bonus_text(st, me)
    assert "Enfants du froid" in start_bonus_text(st, me)
    st.tick_count = 260 - 60
    assert "encore 1 an)" in start_bonus_text(st, me)
    st.tick_count = 258
    assert "encore 2 semaines" in start_bonus_text(st, me)
    me.start_bonuses = []
    assert start_bonus_text(st, me) == ""


def test_new_games_keep_only_the_last_set_aside_saves(tmp_path):
    from src.kora.persist import KEEP_ASIDE, set_aside_save

    for i in range(8):
        (tmp_path / f"kora-ancienne-20260101-00000{i}.json").write_text("{}", encoding="utf-8")
    save = tmp_path / "kora.json"
    save.write_text("{}", encoding="utf-8")
    moved = set_aside_save(save)
    assert moved is not None and moved.exists() and not save.exists()
    left = sorted(p.name for p in tmp_path.glob("kora-ancienne-*.json"))
    assert len(left) == KEEP_ASIDE
    assert moved.name in left
