"""Essai du multijoueur en vrai : deux processus (comme deux PC : graines de
hachage Python differentes), la vraie carte, un robot par joueur qui ne
passe que par des ordres (src/kora/essai.py). A la fin, les deux parties
doivent etre identiques, sans resynchronisation.

    .venv/Scripts/python.exe tools/essai_reseau.py [annees]
    .venv/Scripts/python.exe tools/essai_reseau.py [annees] --exe dist-unfichier/Kora.exe

Avec --exe : deux Kora.exe (APPDATA isole), l'exe tel que les amis le lancent.
"""
import json
import os
import socket
import subprocess
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))


def _port() -> int:
    s = socket.socket()
    s.bind(("127.0.0.1", 0))
    port = s.getsockname()[1]
    s.close()
    return port


def main(years: int, exe: str | None = None) -> int:
    from src.kora import essai

    port = _port()
    work = Path(tempfile.mkdtemp(prefix="kora-essai-"))
    procs = []
    for role, seed in (("hote", "11"), ("ami", "22")):
        out = work / f"{role}.json"
        env = dict(os.environ, PYTHONHASHSEED=seed, KORA_ESSAI=role, KORA_ESSAI_PORT=str(port), KORA_ESSAI_ANS=str(years), KORA_ESSAI_SORTIE=str(out), KORA_BIND="127.0.0.1")
        if exe:
            env["APPDATA"] = str(work / f"appdata-{role}")
            cmd = [str(Path(exe).resolve())]
        else:
            cmd = [sys.executable, str(ROOT / "main.py")]
        procs.append((subprocess.Popen(cmd, cwd=work, env=env, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True), out))
    results = []
    for p, out in procs:
        _stdout, stderr = p.communicate(timeout=1800)
        if not out.exists():
            print("ECHEC d'un processus :\n", stderr[-3000:])
            return 1
        results.append(json.loads(out.read_text(encoding="utf-8")))
    ok, text = essai.compare(*results)
    print(("exe : " + exe + "\n" if exe else "") + text)
    return 0 if ok else 1


if __name__ == "__main__":
    args = sys.argv[1:]
    exe = None
    if "--exe" in args:
        i = args.index("--exe")
        exe = args[i + 1]
        del args[i : i + 2]
    sys.exit(main(int(args[0]) if args else 3, exe))
