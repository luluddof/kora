"""Les dependances entre modules de src/kora : qui importe qui, les
imports caches (dans une fonction), les cercles, les etages.

    python tools/dependances.py              le resume
    python tools/dependances.py cercles      les cercles et leurs aretes
    python tools/dependances.py caches       les imports caches, module par module
    python tools/dependances.py qui MODULE   qui importe MODULE, et quoi

tests/test_architecture.py s'en sert (etages, compteur d'imports caches).
"""
from __future__ import annotations

import ast
import collections
import pathlib
import sys

ROOT = pathlib.Path(__file__).resolve().parents[1]
SRC = ROOT / "src" / "kora"

# La presentation (pygame) ; le reste est la simulation et ses outils.
PRESENTATION = {"app", "render", "theme", "look", "globe", "globe_draw", "screens"}

# LES ETAGES, du plus bas au plus haut. Un module n'importe en tete que des
# etages plus bas ; un import cache (dans une fonction) ne vise que le meme
# etage ou plus bas, jamais plus haut (tests/test_architecture.py).
LAYERS = (
    # 0. les briques : les types du jeu, le francais, le reseau, le tableau
    ("types", "francais", "net", "systems"),
    # 1. le temps, le journal, les ressources, les fiches
    ("clock", "log", "resources", "records"),
    # 2. la planete
    ("world",),
    # 3. ce qui se pose dessus : chemins, atlas, cuisson, etat de la partie, peuples
    ("path", "atlas", "mapgen", "gamestate", "peoples"),
    # 4. les savoirs, les unites, la vue
    ("tech", "units", "vision"),
    # 5. les gens et les lieux : population, savoir-faire, lieux, chefs, influence
    ("population", "production", "sites", "chiefs", "influence"),
    # 6. les systemes (ils se parlent entre eux, de preference par systems.py)
    ("diplo", "goods", "money", "numbers", "chiefdom", "villages", "battle", "situations", "events"),
    # 7. les donnees des evenements ; la semaine du monde (sim)
    ("events_data", "sim"),
    # 8. ce qui la mene : l'IA, les ordres des bandes, les ordres des joueurs
    ("ai_war", "orders"),
    ("ai", "commands"),
    # 9. la sauvegarde, le multijoueur, les essais
    ("persist", "session", "essai"),
)
PRESENTATION_LAYER = len(LAYERS)


def layer_of() -> dict:
    out = {m: i for i, ms in enumerate(LAYERS) for m in ms}
    for m in presentation():
        out[m] = PRESENTATION_LAYER
    return out


def modules() -> set:
    return {p.stem for p in SRC.glob("*.py")} - {"__init__"}


def presentation() -> set:
    return PRESENTATION | {m for m in modules() if m.startswith("render_")}


class Edge:
    __slots__ = ("src", "dst", "names", "hidden", "lines")

    def __init__(self, src, dst):
        self.src, self.dst, self.names, self.hidden, self.lines = src, dst, set(), 0, []


def edges() -> dict:
    """(src, dst) -> Edge ; hidden : le nombre d'imports faits dans une
    fonction (les autres sont en tete du module)."""
    mods = modules()
    out: dict = {}
    for path in sorted(SRC.glob("*.py")):
        m = path.stem
        if m == "__init__":
            continue
        tree = ast.parse(path.read_text(encoding="utf-8"))
        hidden_nodes = set()
        for f in ast.walk(tree):
            if isinstance(f, (ast.FunctionDef, ast.AsyncFunctionDef)):
                for node in ast.walk(f):
                    hidden_nodes.add(id(node))
        for node in ast.walk(tree):
            if not (isinstance(node, ast.ImportFrom) and node.module and node.module.startswith("src.kora")):
                continue
            if node.module == "src.kora":
                pairs = [(a.name, "*") for a in node.names if a.name in mods]
            else:
                t = node.module.split(".")[-1]
                pairs = [(t, a.name) for a in node.names] if t in mods else []
            for dst, name in pairs:
                if dst == m:
                    continue
                e = out.setdefault((m, dst), Edge(m, dst))
                e.names.add(name)
                if id(node) in hidden_nodes:
                    e.hidden += 1
                e.lines.append(node.lineno)
    return out


def graph(only: set | None = None) -> dict:
    g = collections.defaultdict(set)
    for (a, b) in edges():
        if only is None or (a in only and b in only):
            g[a].add(b)
    return g


def cycles(g: dict) -> list:
    """Les composantes fortement connexes de plus d'un module."""
    sys.setrecursionlimit(10000)
    idx, low, st, on, out, c = {}, {}, [], set(), [], [0]
    nodes = set(g) | {w for v in g.values() for w in v}

    def visit(v):
        idx[v] = low[v] = c[0]
        c[0] += 1
        st.append(v)
        on.add(v)
        for w in g.get(v, ()):
            if w not in idx:
                visit(w)
                low[v] = min(low[v], low[w])
            elif w in on:
                low[v] = min(low[v], idx[w])
        if low[v] == idx[v]:
            comp = []
            while True:
                w = st.pop()
                on.discard(w)
                comp.append(w)
                if w == v:
                    break
            if len(comp) > 1:
                out.append(sorted(comp))

    for v in sorted(nodes):
        if v not in idx:
            visit(v)
    return sorted(out, key=len, reverse=True)


def hidden_count(only: set | None = None) -> int:
    return sum(e.hidden for (a, b), e in edges().items() if only is None or a in only)


def summary() -> None:
    sim = modules() - presentation()
    es = edges()
    print("modules :", len(modules()), "dont simulation", len(sim))
    print("imports caches :", hidden_count(), "dont simulation", hidden_count(sim))
    cyc = cycles(graph(sim))
    print("cercles de la simulation :", [len(c) for c in cyc])
    for c in cyc[:3]:
        print("  ", c)
    top = collections.Counter()
    for (a, b), e in es.items():
        top[b] += e.hidden
    print("les plus importes en cachette :", top.most_common(10))


def main(argv) -> int:
    if not argv:
        summary()
    elif argv[0] == "cercles":
        sim = modules() - presentation()
        es = edges()
        for c in cycles(graph(sim)):
            print(len(c), c)
            for (a, b), e in sorted(es.items()):
                if a in c and b in c:
                    print(f"   {a:12s} -> {b:12s} {'cache' if e.hidden else 'tete '} {sorted(e.names)[:8]}")
    elif argv[0] == "caches":
        per = collections.Counter()
        for (a, b), e in edges().items():
            per[a] += e.hidden
        for m, n in per.most_common():
            print(f"{m:16s} {n}")
    elif argv[0] == "qui":
        for (a, b), e in sorted(edges().items()):
            if b == argv[1]:
                print(f"{a:16s} {'cache' if e.hidden else 'tete '} {sorted(e.names)}")
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
