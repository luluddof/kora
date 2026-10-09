"""Les sauvegardes (une par partie, charger, supprimer, copier) et la
musique de guerre (elle ne joue qu'en guerre ; le volume)."""

import os
import time

os.environ.setdefault("SDL_VIDEODRIVER", "dummy")
os.environ.setdefault("SDL_AUDIODRIVER", "dummy")

import pygame

from src.kora import diplo, music, persist, render_menu
from src.kora.persist import save_game
from test_war_goals import _three


def _saves_in(monkeypatch, tmp_path):
    monkeypatch.setattr(persist, "default_save_path", lambda: tmp_path / "kora.json")
    return tmp_path


def test_each_game_has_its_own_save_and_the_latest_readable_continues(monkeypatch, tmp_path):
    _saves_in(monkeypatch, tmp_path)
    st = _three()
    old = tmp_path / "kora.json"
    save_game(st, old, {})
    time.sleep(0.02)
    newer = persist.new_save_path()
    assert newer.name.startswith("partie-") and newer != old
    st.clock.year = 99
    save_game(st, newer, {})
    os.utime(newer, (time.time() + 5, time.time() + 5))
    broken = tmp_path / "partie-casse.json"
    broken.write_text("{pas du json", encoding="utf-8")
    os.utime(broken, (time.time() + 10, time.time() + 10))
    (tmp_path / "reglages.json").write_text("{}", encoding="utf-8")
    saves = persist.list_saves()
    assert [s["path"].name for s in saves][:1] == ["partie-casse.json"], "la plus récente d'abord"
    assert all(s["path"].name != "reglages.json" for s in saves)
    assert saves[0]["info"] is None, "elle ne se lit pas : montree, grisee"
    assert persist.latest_save() == newer, "Continuer : la plus récente qui se lit"
    assert persist.peek_save(newer)["year"] == 99 and persist.peek_save(newer)["game_version"]
    assert persist.new_save_path() != newer


def test_deleting_a_save_sends_it_to_the_bin(monkeypatch, tmp_path):
    _saves_in(monkeypatch, tmp_path)
    st = _three()
    path = persist.new_save_path()
    save_game(st, path, {})
    assert persist.trash_save(path)
    assert not path.exists() and (tmp_path / persist.CORBEILLE / path.name).exists()
    assert persist.list_saves() == []


def test_the_load_page_plays_and_deletes_with_a_second_click():
    saves = [{"path": persist.Path("a.json"), "time": 0.0, "info": {"name": "Kora", "year": 3, "population": 40, "villages": 0}},
             {"path": persist.Path("b.json"), "time": 0.0, "info": None}]
    lay = render_menu.load_layout(1280, 720, len(saves))
    play = lay["rows"][0]["play"]
    assert render_menu.load_hit(lay, play[0] + 3, play[1] + 3, saves) == "jouer:0"
    bad = lay["rows"][1]["play"]
    assert render_menu.load_hit(lay, bad[0] + 3, bad[1] + 3, saves) is None, "une sauvegarde illisible ne se joue pas"
    trash = lay["rows"][1]["trash"]
    assert render_menu.load_hit(lay, trash[0] + 3, trash[1] + 3, saves) == "suppr:1"
    title = render_menu.title_layout(1280, 720)
    x, y, _w, _h = title["buttons"]["charger"]
    assert render_menu.title_hit(title, x + 3, y + 3, can_load=False) is None
    assert render_menu.title_hit(title, x + 3, y + 3, can_load=True) == "charger"


def test_war_music_plays_only_while_the_player_is_at_war():
    st = _three()
    assert not music.wants_war_music(st)
    diplo.declare_war(st, 2, 1)
    assert music.wants_war_music(st)
    pygame.init()
    d = music.Director({"music_volume": 0.5})
    d.update(st, 1.0)
    if d.broken:
        return  # pas de carte son : rien ne joue, rien ne plante
    assert d.playing and abs(d.channel.get_volume() - 0.5) < 0.01
    diplo.end_war(st, 1, 2)
    d.update(st, 1.0)
    assert d.playing, "elle attend un peu (HOLD) avant de s'eteindre"
    d.update(st, music.HOLD + 0.1)
    assert not d.playing
    d.set_volume(0.0)
    diplo.declare_war(st, 2, 1)
    d.update(st, 1.0)
    assert not d.playing, "volume a zero : rien"


def test_the_settings_change_the_volume_and_remember_it(monkeypatch, tmp_path):
    from src.kora import app

    _saves_in(monkeypatch, tmp_path)
    monkeypatch.setattr(app, "load_prefs", persist.load_prefs)
    monkeypatch.setattr(app, "save_prefs", persist.save_prefs)
    pygame.init()
    screen = pygame.display.set_mode((1280, 720))

    class R:
        pass

    r = R()
    r.screen = screen
    d = music.Director({"music_volume": 0.5})
    s = app.Settings(d)
    s.show()
    render_menu.draw_settings(r, d.volume, d.on, d.listening)
    lay = r.settings_hits

    def click(key, dx=3):
        x, y, w, h = lay[key]
        s.handle(r, pygame.event.Event(pygame.MOUSEBUTTONDOWN, pos=(x + dx, y + h // 2), button=1))

    click("plus")
    assert abs(d.volume - 0.6) < 1e-6 and persist.load_prefs()["music_volume"] == 0.6
    click("track", dx=0)
    s.handle(r, pygame.event.Event(pygame.MOUSEBUTTONUP, pos=(0, 0), button=1))
    assert d.volume == 0.0
    click("toggle")
    assert d.on is False and persist.load_prefs()["music_on"] is False
    s.handle(r, pygame.event.Event(pygame.KEYDOWN, key=pygame.K_ESCAPE, mod=0, unicode="", scancode=0))
    assert not s.open
