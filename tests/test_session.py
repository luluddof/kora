"""Multijoueur de bout en bout : un hote et un ami relies par TCP (sur cette
machine). Le salon, le lancement, les ordres, les semaines, l'ecart repare,
le depart et le retour d'un joueur."""

import socket
import time

from src.kora import net, session
from src.kora.commands import NOT_YOURS, make
from src.kora.types import Terrain
from src.kora.world import make_filled_world, offset_to_axial


def _port() -> int:
    s = socket.socket()
    s.bind(("127.0.0.1", 0))
    port = s.getsockname()[1]
    s.close()
    return port


def _world():
    return make_filled_world(48, 24, Terrain.PLAINE, wrap_x=True)


def _until(cond, *pumps, timeout=10.0):
    end = time.time() + timeout
    while time.time() < end:
        for pump in pumps:
            pump()
        if cond():
            return True
        time.sleep(0.005)
    return False


HOST = {"name": "Aroha", "color": (220, 70, 70), "bonuses": ["bonus:conteurs", "bonus:froid"]}
FRIEND = {"name": "Tahu", "color": (60, 190, 190), "bonuses": ["bonus:guerriers", "bonus:fertiles"]}


def _lobby(port=None):
    port = port or _port()
    host = session.HostSession(HOST, port=port)
    client = session.ClientSession(net.connect("127.0.0.1", port), FRIEND)
    assert _until(lambda: client.me is not None and len(host.seats) == 2, host.pump_lobby, client.pump_lobby)
    return host, client


def _started():
    host, client = _lobby()
    client.set_ready(True)
    assert _until(lambda: host.can_start() == "", host.pump_lobby, client.pump_lobby)
    host.start(_world())
    assert _until(lambda: client.snap is not None, client.pump_lobby)
    client.begin(_world())
    return host, client


def _close(host, client):
    client.close()
    host.close()


def test_lobby_seats_and_ready():
    host, client = _lobby()
    try:
        assert client.me == 2
        assert host.seats[2].name == "Tahu" and host.seats[2].bonuses == ["bonus:guerriers", "bonus:fertiles"]
        assert "prêts" in host.can_start()
        assert _until(lambda: 2 in client.seats and 1 in client.seats, client.pump_lobby)
        client.want_slot(4)
        assert _until(lambda: client.me == 4 and 4 in host.seats and 2 not in host.seats, host.pump_lobby, client.pump_lobby)
        client.say("salut")
        assert _until(lambda: any(c["text"] == "salut" for c in host.chat), host.pump_lobby)
    finally:
        _close(host, client)


def test_version_mismatch_is_refused():
    port = _port()
    host = session.HostSession(HOST, port=port)
    conn = net.connect("127.0.0.1", port)
    conn.send({"t": "hello", "proto": session.PROTO, "version": "0.0.0", "name": "X"})
    got = []
    assert _until(lambda: any(m.get("t") == "refuse" for m in got), host.pump_lobby, lambda: got.extend(conn.poll()))
    assert "Versions différentes" in next(m for m in got if m.get("t") == "refuse")["why"]
    host.close()


def test_both_machines_compute_the_same_game():
    host, client = _started()
    try:
        hs, cs = host.state, client.state
        assert cs.viewer == 2 and hs.viewer == 1
        assert session.sync_digest(hs) == session.sync_digest(cs)
        assert cs.tribes[2].name == "Tahu" and cs.tribes[2].is_player and hs.tribes[2].start_bonuses == ["bonus:guerriers", "bonus:fertiles"]
        # Des ordres des deux cotes, et un ordre illegal.
        hb = next(b for b in hs.bands.values() if b.tribe_id == 1)
        cb = next(b for b in cs.bands.values() if b.tribe_id == 2)
        goal1 = offset_to_axial((hb.position.q + 30) % 48, 12)
        goal2 = offset_to_axial(5, 5)
        start2 = cb.position
        host.issue(make(1, "goto", hb.id, goal1.q, goal1.r))
        answers = []
        client.issue(make(2, "goto", cb.id, goal2.q, goal2.r), answers.append)
        client.issue(make(2, "goto", hb.id, goal2.q, goal2.r), answers.append)
        host.set_speed(5)
        assert _until(lambda: hs.tick_count >= 40, lambda: host.pump(0.05), lambda: client.pump(0.05), timeout=30)
        host.toggle_pause()
        assert _until(lambda: cs.tick_count == hs.tick_count, lambda: host.pump(0.05), lambda: client.pump(0.05))
        for then, res in client.take_results():
            if then:
                then(res)
        assert [a["msg"] for a in answers] == ["", NOT_YOURS]
        assert start2 != goal2
        assert cs.bands[cb.id].position == goal2 or cs.bands[cb.id].path, "l'ordre de l'ami a été suivi"
        assert hs.bands[cb.id].position == cs.bands[cb.id].position
        assert session.sync_digest(hs) == session.sync_digest(cs)
        assert client.state is cs and client.resyncs == 0
    finally:
        _close(host, client)


def test_a_machine_that_drifts_is_copied_back():
    host, client = _started()
    try:
        band = next(b for b in client.state.bands.values() if b.tribe_id == 3)
        band.population += 7  # l'ecart (un bug, une machine differente...)
        host.set_speed(5)
        assert _until(lambda: client.resyncs >= 1 and host.state.tick_count >= 2 * session.DIGEST_EVERY, lambda: host.pump(0.05), lambda: client.pump(0.05), timeout=40)
        host.toggle_pause()
        assert _until(lambda: client.state.tick_count == host.state.tick_count, lambda: host.pump(0.05), lambda: client.pump(0.05))
        assert session.sync_digest(host.state) == session.sync_digest(client.state)
        assert host.resyncs >= 1 and any("écartée" in n for n in host.take_notes())
        # Apres la recopie, plus d'ecart : l'hote a relu la meme partie
        # (sinon "300" chez lui et "300.0" chez l'ami differeraient a jamais).
        before = host.resyncs
        start = host.state.tick_count
        host.set_speed(5)
        assert _until(lambda: host.state.tick_count >= start + 2 * session.DIGEST_EVERY + 1, lambda: host.pump(0.05), lambda: client.pump(0.05), timeout=40)
        assert host.resyncs == before
    finally:
        _close(host, client)


def test_a_reread_game_matches_an_int_valued_one():
    """Une partie en memoire (un stock entier) et la meme relue : l'hote
    relit avant d'envoyer, les deux machines ont donc la meme empreinte."""
    host, client = _started()
    try:
        for st in (host.state, client.state):
            next(b for b in st.bands.values() if b.tribe_id == 3).stock = 300
        client.state.bands[1].population += 3  # un ecart pour forcer la recopie
        host.set_speed(5)
        assert _until(lambda: client.resyncs >= 1, lambda: host.pump(0.05), lambda: client.pump(0.05), timeout=40)
        host.toggle_pause()
        assert _until(lambda: client.state.tick_count == host.state.tick_count, lambda: host.pump(0.05), lambda: client.pump(0.05))
        assert session.sync_digest(host.state) == session.sync_digest(client.state)
    finally:
        _close(host, client)


def test_a_player_can_leave_and_come_back():
    host, client = _started()
    port = host.port
    try:
        client.close()
        assert _until(lambda: not host.seats[2].present, lambda: host.pump(0.0))
        back = session.ClientSession(net.connect("127.0.0.1", port), FRIEND)
        assert _until(lambda: back.snap is not None, lambda: host.pump(0.0), back.pump_lobby)
        assert back.me == 2
        back.begin(_world())
        assert session.sync_digest(back.state) == session.sync_digest(host.state)
        assert host.seats[2].present
        back.close()
    finally:
        host.close()


def test_host_waits_for_a_slow_player():
    host, client = _started()
    try:
        host.set_speed(5)
        # L'ami ne lit plus rien : l'hote s'arrete a LAG semaines devant lui.
        assert _until(lambda: host.waiting_for == "Tahu", lambda: host.pump(0.05), timeout=20)
        assert host.state.tick_count - client.state.tick_count == session.LAG
        assert _until(lambda: client.state.tick_count >= session.LAG, lambda: client.pump(0.05))
    finally:
        _close(host, client)


def test_host_can_resume_a_saved_multiplayer_game():
    host, client = _started()
    try:
        host.set_speed(5)
        assert _until(lambda: host.state.tick_count >= 5, lambda: host.pump(0.05), lambda: client.pump(0.05))
        saved = host.state
    finally:
        _close(host, client)
    port = _port()
    again = session.HostSession(HOST, port=port, resume=saved)
    assert again.seats[2].name == "Tahu" and not again.seats[2].present
    friend = session.ClientSession(net.connect("127.0.0.1", port), {"name": "tahu"})
    assert _until(lambda: friend.me == 2 and again.seats[2].present, again.pump_lobby, friend.pump_lobby)
    friend.set_ready(True)
    assert _until(lambda: again.can_start() == "", again.pump_lobby, friend.pump_lobby)
    again.start(saved.world)
    assert _until(lambda: friend.snap is not None, friend.pump_lobby)
    friend.begin(_world())
    assert friend.state.tick_count == saved.tick_count
    assert session.sync_digest(friend.state) == session.sync_digest(again.state)
    _close(again, friend)


def test_a_situation_is_lived_the_same_on_both_machines():
    """Une crise touche les deux joueurs : chacun agit par un ordre, l'IA
    agit, les mois passent ; les deux machines restent identiques."""
    from src.kora import situations

    host, client = _started()
    try:
        hs, cs = host.state, client.state
        for st in (hs, cs):
            st.story = True
            centre = next(b.position for b in st.bands.values() if b.tribe_id == 1)
            situations._start(st, situations.SPECS["mal"], centre, 40, [1, 2, 3], {})
            st.tribes[2].prestige = 30
        uid = hs.situations[0].uid
        assert session.sync_digest(hs) == session.sync_digest(cs)
        answers = []
        client.issue(make(2, "situation", uid, "rites"), answers.append)
        host.issue(make(1, "situation", uid, "isoler"))
        client.issue(make(2, "situation", uid, "isoler"), answers.append)
        host.set_speed(5)
        assert _until(lambda: hs.tick_count >= 24, lambda: host.pump(0.05), lambda: client.pump(0.05), timeout=30)
        host.toggle_pause()
        assert _until(lambda: cs.tick_count == hs.tick_count, lambda: host.pump(0.05), lambda: client.pump(0.05))
        for then, res in client.take_results():
            if then:
                then(res)
        assert [a["msg"] for a in answers] == ["Rites de guérison : fait.", "Isoler les malades : fait."]
        inst = situations.find(cs, uid)
        assert set(inst.participants[2]["acted"]) == {"rites", "isoler"} and "isoler" in inst.participants[1]["acted"]
        assert cs.tribes[2].prestige < 30
        assert session.sync_digest(hs) == session.sync_digest(cs)
        assert client.resyncs == 0
    finally:
        _close(host, client)
