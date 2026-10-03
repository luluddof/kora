"""Une partie a plusieurs (lockstep).

L'hote (HostSession) tient le temps : c'est lui qui decide quand passe
chaque semaine. Il recoit les ordres de chacun, les renvoie a tous (message
"cmds"), puis annonce les semaines ("tick"). Chaque machine applique ces
messages dans le meme ordre : toutes calculent la meme partie. L'hote
n'avance pas plus de LAG semaines devant le joueur le plus lent.

Toutes les DIGEST_EVERY semaines, chacun envoie l'empreinte de sa partie ; si
elle differe de celle de l'hote (une machine s'est ecartee), l'hote lui
renvoie la partie entiere ("resync") et elle repart de la.

Avant la partie : le salon. L'hote a la place 1 (la vallee) ; les amis
prennent la steppe (2), la foret (3), la cote (4). Les places libres
restent a l'IA. Un joueur qui part laisse son peuple en attente (ses
bandes ne bougent plus) ; s'il revient avec le meme nom, il le retrouve.
N'importe pas pygame.
"""

from __future__ import annotations

import hashlib
import json
import time
from dataclasses import dataclass, field

from src.kora import commands, tech
from src.kora.net import Listener, PORT, pack, unpack
from src.kora.sim import new_game, tick

PROTO = 1
LAG = 6
# L'empreinte coute ~50 ms en fin de partie : deux fois par an suffit.
DIGEST_EVERY = 26
# Au plus tant de semaines par image chez un joueur en retard (il rattrape
# sans figer son ecran).
CATCH_UP = 4
SLOTS = {1: "La vallée", 2: "La steppe", 3: "La forêt", 4: "La côte"}
SLOT_NOTE = {
    1: "Plaines et vallées fertiles, l'hôte y commence.",
    2: "Grands espaces : on y connaît déjà le troupeau.",
    3: "Bois profonds, gibier et cueillette.",
    4: "Le bord de la mer : on y connaît déjà le cabotage.",
}
MAX_CHAT = 40


@dataclass
class Seat:
    tid: int
    name: str
    color: tuple = (200, 200, 200)
    bonuses: list = field(default_factory=list)
    ready: bool = False
    host: bool = False
    present: bool = True

    def to_json(self) -> dict:
        return {
            "tid": self.tid,
            "name": self.name,
            "color": list(self.color),
            "bonuses": list(self.bonuses),
            "ready": self.ready,
            "host": self.host,
            "present": self.present,
        }

    @staticmethod
    def from_json(d: dict) -> "Seat":
        return Seat(
            int(d["tid"]),
            str(d.get("name", "?"))[:24],
            tuple(int(c) for c in d.get("color", (200, 200, 200)))[:3],
            [str(b) for b in d.get("bonuses", [])][:2],
            bool(d.get("ready", False)),
            bool(d.get("host", False)),
            bool(d.get("present", True)),
        )


def sync_digest(state) -> str:
    """L'empreinte de la partie, la meme sur chaque machine si elles
    calculent la meme chose. Ni la pause, ni la vitesse, ni la camera."""
    from src.kora.persist import game_to_json

    data = game_to_json(state)
    data.pop("view", None)
    clock = dict(data.get("clock", {}))
    clock.pop("paused", None)
    clock.pop("speed", None)
    data["clock"] = clock
    # Ce qui vient d'ensembles (cases explorees, terres qui se refont...) n'a
    # pas d'ordre : une partie rechargee les range autrement. On trie.
    for key in ("explored", "exhaustion", "influence", "pressure", "overlap"):
        data[key] = sorted(data.get(key, []), key=lambda it: (it[0], it[1]))
    data["presence"] = sorted([tid, sorted(spots)] for tid, spots in data.get("presence", []))
    for _tid, pov in data.get("povs", []):
        pov["explored"] = sorted(pov.get("explored", []))
    text = json.dumps(data, sort_keys=True, separators=(",", ":"), default=str)
    return hashlib.sha1(text.encode("utf-8")).hexdigest()


def run_step(state, cmds, me: int, callbacks: dict, results: list, do_tick: bool) -> None:
    """Les ordres de la file, dans l'ordre, puis (do_tick) une semaine. Le
    meme code chez l'hote et chez chaque joueur."""
    for tid, seq, cmd in cmds:
        cmd = [int(tid)] + list(cmd[1:])
        res = commands.apply(state, cmd)
        if int(tid) == me:
            then = callbacks.pop(seq, None)
            results.append((then, res))
    if do_tick:
        paused, speed = state.clock.paused, state.clock.speed
        tick(state)
        # Une erreur dans la semaine met en pause (sim.tick) : le temps reste
        # a l'hote, on garde son etat.
        state.clock.paused, state.clock.speed = paused, speed


class _Base:
    role = ""

    def __init__(self) -> None:
        self.me = 1
        self.state = None
        self.seats: dict[int, Seat] = {}
        self.callbacks: dict = {}
        self.results: list = []
        self.seq = 0
        self.chat: list = []
        self.notes: list = []
        self.ended = ""
        self.waiting_for = ""
        self.resyncs = 0

    def _chat(self, who: str, text: str) -> None:
        self.chat.append({"from": who, "text": text[:200], "at": time.time()})
        del self.chat[:-MAX_CHAT]

    def take_results(self) -> list:
        out, self.results = self.results, []
        return out

    def take_notes(self) -> list:
        out, self.notes = self.notes, []
        return out

    def name_of(self, tid: int) -> str:
        seat = self.seats.get(tid)
        return seat.name if seat else f"joueur {tid}"


class HostSession(_Base):
    role = "host"

    def __init__(self, setup: dict, port: int = PORT, resume=None) -> None:
        super().__init__()
        from src.kora import __version__

        self.version = __version__
        self.listener = Listener(port)
        self.port = port
        self.setup = dict(setup)
        self.resume = resume
        self.conns: dict = {}  # Conn -> place (None avant "hello")
        self.acks: dict[int, int] = {}
        self.digests: dict[int, str] = {}
        self.pending: list = []
        self.acc = 0.0
        self.started = False
        self._want_share = False
        self.seats[1] = Seat(1, setup.get("name", "Hôte"), tuple(setup.get("color", (220, 70, 70))), list(setup.get("bonuses", [])), True, True, True)
        if resume is not None:
            # Reprendre une partie : les places sont celles des peuples joueurs.
            for tid, tribe in sorted(resume.tribes.items()):
                if tribe.is_player and tid != 1:
                    self.seats[tid] = Seat(tid, tribe.name, tuple(tribe.color), list(tribe.start_bonuses), False, False, False)
            self.seats[1].name = resume.tribes[1].name
            self.seats[1].color = tuple(resume.tribes[1].color)

    # --- le salon -----------------------------------------------------------------

    def _free_slot(self, wanted: int | None = None) -> int | None:
        if self.resume is not None:
            return None
        taken = {t for t, s in self.seats.items() if s.present}
        if wanted in (2, 3, 4) and wanted not in taken:
            return wanted
        return next((t for t in (2, 3, 4) if t not in taken), None)

    def lobby_json(self) -> dict:
        return {"t": "lobby", "seats": [s.to_json() for _t, s in sorted(self.seats.items())], "resume": self.resume is not None}

    def broadcast(self, obj: dict) -> None:
        for conn, tid in list(self.conns.items()):
            if tid is not None and conn.alive:
                conn.send(obj)

    def _hello(self, conn, msg: dict) -> None:
        if msg.get("proto") != PROTO or msg.get("version") != self.version:
            conn.send({"t": "refuse", "why": f"Versions différentes : l'hôte a Kora {self.version}, vous {msg.get('version', '?')}. Prenez la même version."})
            conn.close("version")
            return
        name = str(msg.get("name", "")).strip()[:24] or "Ami"
        tid = None
        if self.resume is not None or self.started:
            # Reprise, ou partie en cours : on retrouve sa place par son nom.
            tid = next((t for t, s in sorted(self.seats.items()) if not s.present and not s.host and s.name.lower() == name.lower()), None)
            if tid is None:
                tid = next((t for t, s in sorted(self.seats.items()) if not s.present and not s.host), None)
            if tid is None:
                conn.send({"t": "refuse", "why": "Toutes les places de cette partie sont prises."})
                conn.close("complet")
                return
        else:
            tid = self._free_slot(msg.get("slot"))
            if tid is None:
                conn.send({"t": "refuse", "why": "La partie est complète (4 joueurs)."})
                conn.close("complet")
                return
            bonuses = [b for b in msg.get("bonuses", []) if b in tech.START_BONUSES][: tech.START_BONUS_PICKS]
            self.seats[tid] = Seat(tid, name, tuple(int(c) for c in msg.get("color", (200, 200, 200)))[:3], bonuses, False, False, True)
        seat = self.seats[tid]
        seat.present = True
        self.conns[conn] = tid
        conn.send({"t": "welcome", "you": tid, "slots": {str(k): v for k, v in SLOTS.items()}})
        self.notes.append(f"{seat.name} rejoint la partie ({SLOTS.get(tid, '?').lower()}).")
        if self.started:
            self._want_share = True
        self.broadcast(self.lobby_json())

    def _seat_msg(self, tid: int, msg: dict) -> None:
        seat = self.seats.get(tid)
        if seat is None or self.started:
            return
        kind = msg.get("t")
        if kind == "seat" and self.resume is None:
            seat.name = str(msg.get("name", seat.name)).strip()[:24] or seat.name
            seat.color = tuple(int(c) for c in msg.get("color", seat.color))[:3]
            seat.bonuses = [b for b in msg.get("bonuses", []) if b in tech.START_BONUSES][: tech.START_BONUS_PICKS]
        elif kind == "ready":
            seat.ready = bool(msg.get("on", True))
        elif kind == "slot" and self.resume is None:
            want = int(msg.get("tid", 0))
            if want in (2, 3, 4) and want not in self.seats:
                del self.seats[tid]
                seat.tid = want
                self.seats[want] = seat
                for conn, t in self.conns.items():
                    if t == tid:
                        self.conns[conn] = want
                        conn.send({"t": "welcome", "you": want, "slots": {str(k): v for k, v in SLOTS.items()}})
        self.broadcast(self.lobby_json())

    def _left(self, conn) -> None:
        tid = self.conns.pop(conn, None)
        if tid is None:
            return
        seat = self.seats.get(tid)
        if seat is None:
            return
        self.notes.append(f"{seat.name} a quitte la partie.")
        if self.started or self.resume is not None:
            seat.present = False
            seat.ready = False
            self.acks.pop(tid, None)
        else:
            del self.seats[tid]
        self.broadcast(self.lobby_json())

    def _read_all(self) -> list:
        for conn in self.listener.accepted():
            self.conns[conn] = None
        out = []
        for conn, tid in list(self.conns.items()):
            for msg in conn.poll():
                out.append((conn, msg))
        return out

    def update_host_setup(self, setup: dict) -> None:
        if self.resume is None and not self.started:
            seat = self.seats[1]
            seat.name = str(setup.get("name", seat.name))[:24]
            seat.color = tuple(setup.get("color", seat.color))
            seat.bonuses = list(setup.get("bonuses", seat.bonuses))
            self.setup = dict(setup)
            self.broadcast(self.lobby_json())

    def pump_lobby(self) -> None:
        for conn, msg in self._read_all():
            kind = msg.get("t")
            tid = self.conns.get(conn)
            if kind == "_closed":
                self._left(conn)
            elif kind == "hello" and tid is None:
                self._hello(conn, msg)
            elif tid is None:
                continue
            elif kind == "chat":
                self._relay_chat(tid, msg)
            else:
                self._seat_msg(tid, msg)

    def _relay_chat(self, tid: int, msg: dict) -> None:
        text = str(msg.get("text", "")).strip()[:200]
        if text:
            who = self.name_of(tid)
            self._chat(who, text)
            self.broadcast({"t": "chat", "from": who, "text": text})

    def say(self, text: str) -> None:
        text = text.strip()[:200]
        if text:
            self._chat(self.name_of(1), text)
            self.broadcast({"t": "chat", "from": self.name_of(1), "text": text})

    def can_start(self) -> str:
        """"" : on peut lancer ; sinon, pourquoi pas encore."""
        others = [s for t, s in self.seats.items() if t != 1 and s.present]
        if not others:
            return "Attendez qu'un ami vous rejoigne."
        late = [s.name for s in others if not s.ready]
        if late:
            return "Pas encore prêts : " + ", ".join(late)
        return ""

    def start(self, world) -> object:
        """Lance la partie : la meme pour tous (la partie en texte, rechargee
        aussi par l'hote)."""
        from src.kora.persist import dumps_game, loads_game

        if self.resume is not None:
            base = self.resume
        else:
            others = {t: {"name": s.name, "color": s.color, "bonuses": s.bonuses} for t, s in self.seats.items() if t != 1 and s.present}
            base = new_game(world, setup=self.setup, others=others)
        text = dumps_game(base)
        state, _view = loads_game(text, base.world)
        state.viewer = 1
        state.clock.paused = True
        self.state = state
        self.started = True
        blob = pack(dumps_game(state))
        for conn, tid in self.conns.items():
            if tid is not None:
                conn.send({"t": "start", "you": tid, "tick": state.step, "snap": blob})
                self.acks[tid] = state.step
        self.broadcast(self.lobby_json())
        self.broadcast(self._clock_msg(""))
        return state

    def _share_game(self) -> None:
        """La partie de l'hote, RELUE par lui et envoyee a tous : chaque
        machine repart exactement du meme etat (memes nombres, meme
        rangement ; une partie relue range autrement, "350" devient
        "350.0"). Apres un ecart, ou quand un joueur revient."""
        from src.kora.persist import dumps_game, loads_game

        self._want_share = False
        self._flush()
        text = dumps_game(self.state)
        loaded = loads_game(text, self.state.world)
        if loaded is not None:
            paused, speed = self.state.clock.paused, self.state.clock.speed
            state = loaded[0]
            state.viewer = 1
            state.clock.paused, state.clock.speed = paused, speed
            self.state = state
        self.digests.clear()
        blob = pack(text)
        for conn, tid in self.conns.items():
            if tid is not None and conn.alive:
                conn.send({"t": "start", "you": tid, "tick": self.state.step, "snap": blob})
                conn.send(self._clock_msg(""))
                self.acks[tid] = self.state.step

    # --- en partie -----------------------------------------------------------------

    def issue(self, cmd: list, then=None) -> None:
        self.seq += 1
        self.callbacks[self.seq] = then
        self.pending.append([1, self.seq, [1] + list(cmd[1:])])

    def _clock_msg(self, by: str) -> dict:
        ck = self.state.clock
        return {"t": "clock", "paused": ck.paused, "speed": ck.speed, "by": by}

    def toggle_pause(self, by: str = "") -> None:
        self.state.clock.toggle_pause()
        self.broadcast(self._clock_msg(by or self.name_of(1)))

    def set_speed(self, n: int, by: str = "") -> None:
        self.state.clock.set_speed(n)
        self.broadcast(self._clock_msg(by or self.name_of(1)))

    def _flush(self) -> None:
        """Les ordres recus, tout de suite (entre deux semaines)."""
        if self.pending:
            cmds, self.pending = self.pending, []
            self.broadcast({"t": "cmds", "cmds": cmds})
            run_step(self.state, cmds, 1, self.callbacks, self.results, False)

    def pump(self, dt: float) -> None:
        state = self.state
        for conn, msg in self._read_all():
            kind = msg.get("t")
            tid = self.conns.get(conn)
            if kind == "_closed":
                self._left(conn)
            elif kind == "hello" and tid is None:
                self._hello(conn, msg)
            elif tid is None:
                continue
            elif kind == "cmd":
                cmd = msg.get("cmd")
                if isinstance(cmd, list) and len(cmd) >= 2:
                    # Chacun ne commande que son peuple : l'hote y veille.
                    self.pending.append([tid, msg.get("seq"), [tid] + cmd[1:]])
            elif kind == "ack":
                self.acks[tid] = max(self.acks.get(tid, 0), int(msg.get("n", 0)))
                self._check(conn, tid, msg)
            elif kind == "lost":
                self.resyncs += 1
                self._want_share = True
            elif kind == "pause":
                self.toggle_pause(self.name_of(tid))
            elif kind == "speed":
                self.set_speed(int(msg.get("n", 1)), self.name_of(tid))
            elif kind == "chat":
                self._relay_chat(tid, msg)
        self._flush()
        if self._want_share:
            self._share_game()
        state = self.state
        if state.clock.paused:
            self.acc = 0.0
            self.waiting_for = ""
            return
        self.acc = min(2.0, self.acc + dt * state.clock.ticks_per_second())
        if self.acc < 1.0:
            return
        late = [t for t, n in self.acks.items() if self.seats.get(t) and self.seats[t].present and state.step - n >= LAG]
        if late:
            self.waiting_for = ", ".join(self.name_of(t) for t in late)
            self.acc = min(self.acc, 1.0)
            return
        self.waiting_for = ""
        self.acc -= 1.0
        n = state.step
        self.broadcast({"t": "tick", "n": n})
        run_step(state, [], 1, self.callbacks, self.results, True)
        if state.step % DIGEST_EVERY == 0:
            self.digests[state.step] = sync_digest(state)
            for old in [k for k in self.digests if k < state.step - 8 * DIGEST_EVERY]:
                del self.digests[old]

    def _check(self, conn, tid: int, msg: dict) -> None:
        digest = msg.get("digest")
        n = int(msg.get("n", -1))
        mine = self.digests.get(n)
        if digest and mine and digest != mine:
            # Cette machine s'est ecartee : elle repart de la partie de l'hote.
            self.resyncs += 1
            self.notes.append(f"La partie de {self.name_of(tid)} s'était écartée : elle est recopiée.")
            self._want_share = True

    def close(self, why: str = "L'hôte a quitte la partie.") -> None:
        self.broadcast({"t": "bye", "why": why})
        for conn in list(self.conns):
            conn.close("fin")
        self.listener.close()


class ClientSession(_Base):
    role = "client"

    def __init__(self, conn, setup: dict, slot: int | None = None) -> None:
        super().__init__()
        from src.kora import __version__

        self.conn = conn
        self.setup = dict(setup)
        self.me = None
        self.snap = None
        self.refused = ""
        self.resume = False
        self.backlog: list = []
        self._lost = False
        conn.send(
            {
                "t": "hello",
                "proto": PROTO,
                "version": __version__,
                "name": setup.get("name", "Ami"),
                "color": list(setup.get("color", (200, 200, 200))),
                "bonuses": list(setup.get("bonuses", [])),
                "slot": slot,
            }
        )

    def send_seat(self, setup: dict) -> None:
        self.setup = dict(setup)
        self.conn.send({"t": "seat", "name": setup.get("name"), "color": list(setup.get("color", ())), "bonuses": list(setup.get("bonuses", []))})

    def set_ready(self, on: bool) -> None:
        self.conn.send({"t": "ready", "on": bool(on)})

    def want_slot(self, tid: int) -> None:
        self.conn.send({"t": "slot", "tid": int(tid)})

    def say(self, text: str) -> None:
        text = text.strip()[:200]
        if text:
            self.conn.send({"t": "chat", "text": text})

    def _common(self, msg: dict) -> bool:
        kind = msg.get("t")
        if kind == "welcome":
            self.me = int(msg["you"])
        elif kind == "lobby":
            self.seats = {int(s["tid"]): Seat.from_json(s) for s in msg.get("seats", [])}
            self.resume = bool(msg.get("resume"))
        elif kind == "refuse":
            self.refused = str(msg.get("why", "Refuse par l'hôte"))
            self.ended = self.refused
        elif kind == "chat":
            self._chat(str(msg.get("from", "?")), str(msg.get("text", "")))
        elif kind in ("bye", "_closed"):
            self.ended = self.ended or str(msg.get("why", "La connexion est coupee."))
        else:
            return False
        return True

    def pump_lobby(self) -> None:
        for msg in self.conn.poll():
            if msg.get("t") == "start":
                self.me = int(msg.get("you", self.me or 0))
                self.snap = msg
                # La suite (semaines deja annoncees...) attend la partie.
                continue
            if self.snap is not None and msg.get("t") in ("tick", "cmds", "clock", "resync", "start"):
                self.backlog.append(msg)
                continue
            self._common(msg)

    def begin(self, world):
        """La partie recue de l'hote."""
        from src.kora.persist import loads_game

        loaded = loads_game(unpack(self.snap["snap"]), world)
        if loaded is None:
            self.ended = "La partie reçue ne se lit pas (versions différentes ?)."
            return None
        state, _view = loaded
        state.viewer = self.me
        self.state = state
        self.snap = None
        return state

    def issue(self, cmd: list, then=None) -> None:
        self.seq += 1
        self.callbacks[self.seq] = then
        self.conn.send({"t": "cmd", "seq": self.seq, "cmd": [self.me] + list(cmd[1:])})

    def toggle_pause(self, by: str = "") -> None:
        self.conn.send({"t": "pause"})

    def set_speed(self, n: int, by: str = "") -> None:
        self.conn.send({"t": "speed", "n": int(n)})

    def pump(self, dt: float) -> None:
        from src.kora.persist import loads_game

        msgs = self.backlog + self.conn.poll()
        self.backlog = []
        ran = 0
        for i, msg in enumerate(msgs):
            kind = msg.get("t")
            state = self.state
            if kind == "tick":
                if ran >= CATCH_UP:
                    self.backlog = msgs[i:]
                    break
                if int(msg.get("n", -1)) != state.step:
                    # Une semaine sautee ou deja faite : on demande la partie
                    # de l'hote (une fois ; elle arrive dans l'ordre).
                    if not self._lost:
                        self._lost = True
                        self.conn.send({"t": "lost", "n": state.step})
                    continue
                run_step(state, [], self.me, self.callbacks, self.results, True)
                ran += 1
                ack = {"t": "ack", "n": state.step}
                if state.step % DIGEST_EVERY == 0:
                    ack["digest"] = sync_digest(state)
                self.conn.send(ack)
            elif kind == "cmds":
                run_step(state, msg.get("cmds", []), self.me, self.callbacks, self.results, False)
            elif kind == "clock":
                state.clock.paused = bool(msg.get("paused", True))
                state.clock.speed = int(msg.get("speed", 1))
                by = msg.get("by")
                if by:
                    self.notes.append(f"{by} : {'pause' if state.clock.paused else 'le temps reprend'}.")
            elif kind == "start":
                # La partie de l'hote (reprise apres un ecart, ou retour).
                loaded = loads_game(unpack(msg["snap"]), state.world)
                if loaded is not None:
                    paused, speed = state.clock.paused, state.clock.speed
                    self.state, _view = loaded
                    self.state.viewer = self.me
                    self.state.clock.paused, self.state.clock.speed = paused, speed
                    self.resyncs += 1
                    self._lost = False
                    self.conn.send({"t": "ack", "n": self.state.step})
            else:
                self._common(msg)

    def close(self, why: str = "") -> None:
        self.conn.close(why or "depart")
