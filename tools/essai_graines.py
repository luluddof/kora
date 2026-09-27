"""Une partie avancee se calcule-t-elle pareil sur deux machines ?

Deux processus (graines de hachage Python differentes, comme deux PC)
chargent la meme sauvegarde (une COPIE : jamais la partie du joueur) et la
continuent N ans (le robot de tests/test_balance.py joue le peuple 1) ;
leurs empreintes (session.sync_digest) sont comparees chaque trimestre.

    .venv/Scripts/python.exe tools/essai_graines.py copie.json [annees]
"""
import json
import os
import random
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "tests"))


def run(path: str, years: int) -> None:
    from src.kora import session
    from src.kora.persist import load_game
    from src.kora.sim import _default_world, tick
    from test_balance import _robot

    st, _view = load_game(Path(path), _default_world())
    st.rng = random.Random(5)
    out = {}
    for _ in range(52 * years):
        _robot(st)
        tick(st)
        st.clock.paused = False
        if st.tick_count % 13 == 0:
            out[st.tick_count] = session.sync_digest(st)
    villages = sum(1 for s in st.sites.values() if s.kind == "village")
    print(json.dumps({"digests": out, "year": st.clock.year, "villages": villages, "error": st.last_error}))


def main(path: str, years: int) -> int:
    results = []
    for seed in ("3", "4"):
        env = dict(os.environ, PYTHONHASHSEED=seed)
        done = subprocess.run([sys.executable, __file__, "--run", path, str(years)], cwd=ROOT, env=env, capture_output=True, text=True, timeout=3000)
        line = [x for x in done.stdout.splitlines() if x.startswith("{")]
        if not line:
            print("ECHEC :", done.stderr[-2000:])
            return 1
        results.append(json.loads(line[-1]))
    a, b = results
    bad = [n for n in a["digests"] if a["digests"][n] != b["digests"].get(n)]
    print(f"an {a['year']}, {a['villages']} villages ; empreintes : {len(a['digests'])}, differentes : {len(bad)}" + (f" (la premiere a la semaine {bad[0]})" if bad else ""))
    print("IDENTIQUES" if not bad else "DIFFERENTES")
    return 0 if not bad else 1


if __name__ == "__main__":
    if sys.argv[1] == "--run":
        run(sys.argv[2], int(sys.argv[3]))
    else:
        sys.exit(main(sys.argv[1], int(sys.argv[2]) if len(sys.argv) > 2 else 3))
