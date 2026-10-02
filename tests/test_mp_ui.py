"""La boucle du jeu (app.play) en multijoueur, pour de vrai : l'ecran d'un
joueur tourne (touches, discussion, pause) pendant que l'autre machine
(l'hote ou l'ami) avance dans la meme boucle d'horloge. A la fin, les deux
parties doivent etre identiques. Aussi : le salon (app._multiplayer)."""

import os
import socket

os.environ.setdefault("SDL_VIDEODRIVER", "dummy")

import pygame

from src.kora import app, net, session
from src.kora.render import Renderer
from src.kora.types import Terrain
from src.kora.world import make_filled_world

HOST = {"name": "Aroha", "color": (220, 70, 70), "bonuses": ["bonus:conteurs", "bonus:froid"]}
FRIEND = {"name": "Tahu", "color": (60, 190, 190), "bonuses": ["bonus:guerriers", "bonus:fertiles"]}


def _port() -> int:
    s = socket.socket()
    s.bind(("127.0.0.1", 0))
    port = s.getsockname()[1]
    s.close()
    return port


def _world():
    return make_filled_world(48, 24, Terrain.PLAINE, wrap_x=True)


class Script:
    """Une horloge qui, a chaque image, fait aussi vivre l'autre machine et
    joue des touches a des images donnees."""

    def __init__(self, other, steps: dict):
        self.frame = 0
        self.other = other
        self.steps = steps

    def tick(self, _fps=60):
        self.frame += 1
        if self.other is not None:
            self.other()
        for action in self.steps.get(self.frame, ()):
            action()
        return 50


def key(k, ch=""):
    return lambda: pygame.event.post(pygame.event.Event(pygame.KEYDOWN, key=k, unicode=ch, mod=0))


def typed(text):
    return [key(pygame.K_a, c) for c in text]


def quit_():
    return pygame.event.post(pygame.event.Event(pygame.QUIT))


def _pair():
    port = _port()
    host = session.HostSession(HOST, port=port)
    client = session.ClientSession(net.connect("127.0.0.1", port), FRIEND)
    for _ in range(400):
        host.pump_lobby()
        client.pump_lobby()
        if client.me is not None and 2 in host.seats:
            break
        pygame.time.wait(5)
    client.set_ready(True)
    for _ in range(400):
        host.pump_lobby()
        client.pump_lobby()
        if host.can_start() == "":
            break
        pygame.time.wait(5)
    host.start(_world())
    for _ in range(400):
        client.pump_lobby()
        if client.snap is not None:
            break
        pygame.time.wait(5)
    client.begin(_world())
    return host, client


def _screen():
    pygame.init()
    return Renderer(pygame.display.set_mode((1280, 720)))


def test_friend_screen_plays_along(tmp_path, monkeypatch):
    monkeypatch.setattr(app, "multi_save_path", lambda: tmp_path / "multi.json")
    monkeypatch.setattr(app, "default_save_path", lambda: tmp_path / "solo.json")
    host, client = _pair()
    host.set_speed(5)
    r = _screen()
    pygame.event.clear()
    before = sum(1 for b in client.state.bands.values() if b.tribe_id == 2)
    steps = {
        5: [key(pygame.K_s)],  # scinder la bande choisie (un ordre par l'hote)
        12: [key(pygame.K_RETURN)] + typed("salut !") + [key(pygame.K_RETURN)],
        20: [key(pygame.K_c)],  # poser un campement
        40: [key(pygame.K_SPACE)],  # demander la pause
        70: [quit_],
    }
    clock = Script(lambda: host.pump(0.05), steps)
    boot = app._start_view(client.state, app._first_player_band(client.state), 1280, 720)
    outcome, _msg = app.play(r, clock, boot, client)
    assert outcome == "quit"
    assert host.state.clock.paused, "la pause demandee par l'ami arrête le temps de l'hôte"
    for _ in range(50):
        host.pump(0.05)
        client.pump(0.05)
        pygame.time.wait(2)
    cs, hs = client.state, host.state
    assert cs.tick_count == hs.tick_count > 0
    assert session.sync_digest(cs) == session.sync_digest(hs)
    assert sum(1 for b in hs.bands.values() if b.tribe_id == 2) == before + 1, "la scission de l'ami est arrivée chez l'hôte"
    assert any(c["text"] == "salut !" and c["from"] == "Tahu" for c in host.chat)
    assert not (tmp_path / "multi.json").exists(), "l'ami ne sauvegarde pas"
    host.close()


def test_host_screen_runs_the_game(tmp_path, monkeypatch):
    monkeypatch.setattr(app, "multi_save_path", lambda: tmp_path / "multi.json")
    monkeypatch.setattr(app, "default_save_path", lambda: tmp_path / "solo.json")
    host, client = _pair()
    r = _screen()
    pygame.event.clear()
    before = sum(1 for b in host.state.bands.values() if b.tribe_id == 1)
    steps = {
        3: [key(pygame.K_5)],  # vitesse 5 (l'hote)
        8: [key(pygame.K_s)],
        30: [key(pygame.K_SPACE)],
        45: [key(pygame.K_ESCAPE)],  # le menu : ne met pas en pause les autres
        50: [key(pygame.K_ESCAPE)],
        60: [quit_],
    }
    clock = Script(lambda: client.pump(0.05), steps)
    boot = app._start_view(host.state, app._first_player_band(host.state), 1280, 720)
    outcome, _msg = app.play(r, clock, boot, host)
    assert outcome == "quit"
    for _ in range(100):
        client.pump(0.05)
        if client.ended:
            break
        pygame.time.wait(5)
    assert client.state.tick_count == host.state.tick_count > 0
    assert session.sync_digest(client.state) == session.sync_digest(host.state)
    assert sum(1 for b in client.state.bands.values() if b.tribe_id == 1) == before + 1
    assert (tmp_path / "multi.json").exists(), "l'hôte sauvegarde la partie à plusieurs en partant"
    assert client.ended, "l'ami apprend que l'hôte est parti"


def test_lobby_screen_hosts_and_launches(monkeypatch):
    port = _port()
    monkeypatch.setattr(net, "PORT", port)
    r = _screen()
    pygame.event.clear()
    friend = {}

    def join():
        friend["s"] = session.ClientSession(net.connect("127.0.0.1", port), FRIEND)

    def ready():
        friend["s"].pump_lobby()
        friend["s"].set_ready(True)

    def click_go():
        lay = r.lobby_hits
        x, y, w, h = lay["go"]
        pygame.event.post(pygame.event.Event(pygame.MOUSEBUTTONDOWN, button=1, pos=(x + w // 2, y + h // 2)))

    steps = {3: [join], 10: [ready], 30: [click_go]}

    def pump_friend():
        if "s" in friend:
            friend["s"].pump_lobby()

    clock = Script(pump_friend, steps)

    class Worlds:
        shown = _world()

        def fresh(self):
            return _world()

    out = app._multiplayer(r, clock, Worlds(), ("host", dict(HOST)))
    assert out[0] == "play", out
    mp, state = out[1], out[2]
    assert state.tribes[2].name == "Tahu" and state.tribes[2].is_player
    for _ in range(200):
        friend["s"].pump_lobby()
        if friend["s"].snap is not None:
            break
        pygame.time.wait(5)
    assert friend["s"].snap is not None
    friend["s"].close()
    mp.close()


def test_joining_a_closed_address_comes_back_with_a_message(monkeypatch):
    port = _port()
    r = _screen()
    pygame.event.clear()

    class Worlds:
        shown = _world()

        def fresh(self):
            return _world()

    clock = Script(None, {})
    out = app._multiplayer(r, clock, Worlds(), ("join", dict(FRIEND) | {"address": f"127.0.0.1:{port}"}))
    assert out[0] == "back" and "Pas de réponse" in out[1]
