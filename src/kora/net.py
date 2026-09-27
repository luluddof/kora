"""Le reseau du multijoueur : des connexions TCP qui s'echangent des
messages JSON, un par ligne.

Chaque connexion a deux fils : l'un lit (et range les messages recus dans
une file), l'autre ecrit (la boucle du jeu ne bloque jamais sur le
reseau). Les gros messages (la partie entiere, ~1 Mo de JSON) sont
compresses (pack/unpack). session.py s'en sert ; N'importe pas pygame.
"""

from __future__ import annotations

import base64
import json
import os
import queue
import socket
import threading
import zlib

# Le port de l'hote (KORA_PORT pour en prendre un autre).
PORT = int(os.environ.get("KORA_PORT", "45170") or 45170)
# L'hote ecoute sur toutes ses cartes reseau ; les essais et les tests,
# seulement sur la machine (KORA_BIND=127.0.0.1 : pas de fenetre du pare-feu).
BIND = os.environ.get("KORA_BIND", "0.0.0.0")
# Un message plus long est une erreur (ou une attaque) : on coupe.
MAX_LINE = 64 * 1024 * 1024


def pack(text: str) -> str:
    return base64.b64encode(zlib.compress(text.encode("utf-8"), 6)).decode("ascii")


def unpack(data: str) -> str:
    return zlib.decompress(base64.b64decode(data.encode("ascii"))).decode("utf-8")


class Conn:
    """Une connexion : send() met en file, poll() rend ce qui est arrive."""

    def __init__(self, sock: socket.socket, peer: str = "") -> None:
        self.sock = sock
        self.peer = peer
        self.alive = True
        self.why = ""
        self._inbox: queue.Queue = queue.Queue()
        self._outbox: queue.Queue = queue.Queue()
        try:
            sock.setsockopt(socket.IPPROTO_TCP, socket.TCP_NODELAY, 1)
        except OSError:
            pass
        sock.settimeout(None)
        self._reader = threading.Thread(target=self._read, daemon=True)
        self._writer = threading.Thread(target=self._write, daemon=True)
        self._reader.start()
        self._writer.start()

    def send(self, obj: dict) -> None:
        if self.alive:
            self._outbox.put(obj)

    def poll(self) -> list:
        out = []
        while True:
            try:
                out.append(self._inbox.get_nowait())
            except queue.Empty:
                return out

    def close(self, why: str = "") -> None:
        """Fermer apres avoir envoye ce qui attend (un refus, un au revoir) :
        c'est le fil d'ecriture qui ferme la socket."""
        if not self.alive:
            return
        self.alive = False
        self.why = self.why or why
        self._outbox.put(None)

    def _shut(self) -> None:
        try:
            self.sock.shutdown(socket.SHUT_RDWR)
        except OSError:
            pass
        try:
            self.sock.close()
        except OSError:
            pass

    def _read(self) -> None:
        buf = b""
        try:
            while self.alive:
                chunk = self.sock.recv(65536)
                if not chunk:
                    break
                buf += chunk
                if len(buf) > MAX_LINE:
                    raise ValueError("message trop long")
                while b"\n" in buf:
                    line, buf = buf.split(b"\n", 1)
                    if not line.strip():
                        continue
                    try:
                        msg = json.loads(line.decode("utf-8"))
                    except (ValueError, UnicodeDecodeError):
                        continue
                    if isinstance(msg, dict):
                        self._inbox.put(msg)
        except (OSError, ValueError) as exc:
            self.why = self.why or str(exc)
        self.alive = False
        self._inbox.put({"t": "_closed", "why": self.why or "connexion fermee"})

    def _write(self) -> None:
        try:
            while True:
                obj = self._outbox.get()
                if obj is None:
                    break
                data = (json.dumps(obj, separators=(",", ":")) + "\n").encode("utf-8")
                self.sock.sendall(data)
        except OSError as exc:
            self.why = self.why or str(exc)
        self.alive = False
        self._shut()


class Listener:
    """L'hote ecoute ; accepted() rend les nouvelles connexions."""

    def __init__(self, port: int = PORT) -> None:
        self.port = port
        self.sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        self.sock.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        self.sock.bind((BIND, port))
        self.sock.listen(8)
        self.alive = True
        self._new: queue.Queue = queue.Queue()
        threading.Thread(target=self._accept, daemon=True).start()

    def _accept(self) -> None:
        while self.alive:
            try:
                sock, addr = self.sock.accept()
            except OSError:
                break
            self._new.put(Conn(sock, f"{addr[0]}:{addr[1]}"))

    def accepted(self) -> list:
        out = []
        while True:
            try:
                out.append(self._new.get_nowait())
            except queue.Empty:
                return out

    def close(self) -> None:
        self.alive = False
        try:
            self.sock.close()
        except OSError:
            pass


def connect(host: str, port: int = PORT, timeout: float = 8.0) -> Conn:
    """Se connecter a un hote (bloquant : l'interface l'appelle dans un fil)."""
    sock = socket.create_connection((host, port), timeout=timeout)
    return Conn(sock, f"{host}:{port}")


def parse_address(text: str) -> tuple[str, int]:
    """ "1.2.3.4", "1.2.3.4:45170", "nom-du-pc" -> (hote, port)."""
    text = text.strip()
    if text.count(":") == 1:
        host, _sep, port = text.partition(":")
        try:
            return host.strip(), int(port)
        except ValueError:
            return host.strip(), PORT
    return text, PORT


def local_addresses() -> list[str]:
    """Les adresses de cette machine sur le reseau local (a donner aux amis)."""
    found = []
    try:
        s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        s.connect(("10.255.255.255", 1))
        found.append(s.getsockname()[0])
        s.close()
    except OSError:
        pass
    try:
        for info in socket.getaddrinfo(socket.gethostname(), None, socket.AF_INET):
            ip = info[4][0]
            if ip not in found and not ip.startswith("127."):
                found.append(ip)
    except OSError:
        pass
    return found or ["127.0.0.1"]
