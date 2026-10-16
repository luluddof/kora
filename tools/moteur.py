"""LE BANC DU MOTEUR : mesurer ce que coutent la semaine et l'image, avant
de toucher au moteur (et apres, pour prouver le gain).

    python tools/moteur.py semaines PARTIE [N]   la duree des N semaines (moyenne,
                                                 p95, max ; semaines de mois a part)
    python tools/moteur.py morceaux PARTIE [N]   les morceaux de semaine les plus
                                                 longs (sim.tick_steps : ou couper)
    python tools/moteur.py images PARTIE [N]     N images a l'ecran, sans fenetre,
                                                 a la vitesse 5 (sim.TickRunner)
    python tools/moteur.py profil PARTIE [ANS]   les fonctions les plus couteuses
    python tools/moteur.py vieillir PLANETE ANS SORTIE
                                                 une partie neuve jouee par l'IA,
                                                 sauvee : une partie mure a mesurer

PARTIE : une sauvegarde (TOUJOURS une copie : jamais celles du joueur
dans %APPDATA%), ou "planete:aurane" (une partie neuve). Les mesures du
chantier du 2026-10-16 (spec 2026-10-16-notes-decoupage-moteur-tutoriel) :
sa partie de l'an 70, 258 -> 101 ms par semaine, image la plus longue
552 -> 116 ms a la vitesse 5. N'ecrit rien dans le jeu.
"""
from __future__ import annotations

import cProfile
import io
import json
import os
import pathlib
import pstats
import statistics
import sys
import time

ROOT = pathlib.Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))


def load(what: str):
    from src.kora import persist, planets
    from src.kora.sim import new_game

    if what.startswith("planete:"):
        state = new_game(planets.load(what.split(":", 1)[1]), setup={"seed": 7})
        state.tribes[1].is_player = False
        state.story = True
        return state, None
    data = json.loads(pathlib.Path(what).read_text(encoding="utf-8"))
    state, view = persist.game_from_json(data, planets.load(persist.map_id(data)))
    state.story = True
    return state, view


def semaines(what: str, n: int = 52) -> None:
    from src.kora.sim import tick

    state, _ = load(what)
    week, month = [], []
    for _ in range(n):
        t = time.perf_counter()
        tick(state)
        dt = (time.perf_counter() - t) * 1000
        (month if state.tick_count % 4 == 0 else week).append(dt)
    every = sorted(week + month)
    print(f"{len(every)} semaines : moyenne {statistics.mean(every):.0f} ms, p95 {every[int(len(every) * 0.95)]:.0f} ms, max {every[-1]:.0f} ms")
    if week and month:
        print(f"  ordinaires : {statistics.mean(week):.0f} ms ; de mois : {statistics.mean(month):.0f} ms (max {max(month):.0f})")


def morceaux(what: str, n: int = 40) -> None:
    import inspect

    from src.kora import sim

    state, _ = load(what)
    src_lines, first = inspect.getsourcelines(sim._week_steps)

    def last_statement(lineno: int) -> str:
        """L'instruction juste avant le `yield` de la ligne lineno."""
        i = lineno - first
        while i > 0:
            i -= 1
            text = src_lines[i].strip()
            if text and text != "yield" and not text.startswith(("#", "for ", "if ")):
                return text
        return "?"

    worst: dict = {}
    for _ in range(n):
        gen = sim.tick_steps(state)
        while True:
            t = time.perf_counter()
            more = next(gen, StopIteration) is not StopIteration
            dt = (time.perf_counter() - t) * 1000
            inner = gen.gi_yieldfrom
            if more and inner is not None and inner.gi_frame is not None:
                key = last_statement(inner.gi_frame.f_lineno)
                if key.startswith("systems.fn(path)"):
                    key = f"{inner.gi_frame.f_locals.get('path')} (systems)"
            elif more:
                key = "le debut du pas"
            else:
                key = "la fin de la semaine (decide_ai)"
            worst[key] = max(worst.get(key, 0.0), dt)
            if not more:
                break
    print("Les morceaux les plus longs (le pire de chacun, nomme par sa derniere instruction) :")
    for k, v in sorted(worst.items(), key=lambda kv: -kv[1])[:15]:
        print(f"  {v:7.1f} ms  {k}")


def images(what: str, n: int = 600) -> None:
    os.environ.setdefault("SDL_VIDEODRIVER", "dummy")
    os.environ.setdefault("SDL_AUDIODRIVER", "dummy")
    import pygame

    from src.kora import app, partie, partie_carte
    from src.kora.render import Renderer

    pygame.init()
    renderer = Renderer(pygame.display.set_mode((1600, 900)))
    state, _ = load(what)
    boot = app._start_view(state, partie_carte.first_player_band(state), 1600, 900)
    tmp = pathlib.Path(os.environ.get("TEMP", ".")) / "kora-banc-moteur.json"
    play = partie.Play(renderer, pygame.time.Clock(), boot, save_path=tmp)
    pygame.event.get = lambda *a, **k: []
    play.state.clock.paused = False
    play.state.clock.speed = 5
    play.last_auto = 10**9
    for _ in range(30):  # l'echauffement : la premiere image peint la planete
        play._frame(1 / 60)
    start = play.state.tick_count
    times = []
    t0 = time.perf_counter()
    for _ in range(n):
        t = time.perf_counter()
        play._frame(1 / 60)
        times.append((time.perf_counter() - t) * 1000)
    total = time.perf_counter() - t0
    times.sort()
    done = play.state.tick_count - start
    print(
        f"{n} images : moyenne {statistics.mean(times):.0f} ms, p95 {times[int(n * 0.95)]:.0f} ms, max {times[-1]:.0f} ms ; "
        f"{done} semaines en {total:.1f} s ({done / total:.1f} par seconde)"
    )


def profil(what: str, years: float = 1.0) -> None:
    from src.kora.sim import tick

    state, _ = load(what)
    pr = cProfile.Profile()
    pr.enable()
    for _ in range(int(years * 52)):
        tick(state)
    pr.disable()
    for key in ("tottime", "cumulative"):
        s = io.StringIO()
        pstats.Stats(pr, stream=s).sort_stats(key).print_stats(30)
        print(f"===== {key}")
        for line in s.getvalue().splitlines()[6:40]:
            cols = line.split(None, 5)
            if len(cols) == 6:
                name = cols[5].replace("\\", "/").split("/kora/")[-1]
                print(f"{cols[0]:>14} propre {cols[1]:>7} total {cols[3]:>7}  {name[:80]}")


def vieillir(pid: str, years: int, out: str) -> None:
    from src.kora import persist
    from src.kora.sim import tick

    state, _ = load(f"planete:{pid}")
    for y in range(years):
        t = time.perf_counter()
        for _ in range(52):
            tick(state)
        villages = sum(1 for s in state.sites.values() if s.kind == "village")
        print(f"an {y + 1} : {time.perf_counter() - t:.1f} s ; {len(state.tribes)} peuples, {len(state.bands)} bandes, {villages} villages", flush=True)
    persist.save_game(state, pathlib.Path(out))
    print("sauvee :", out)


def main(argv: list[str]) -> int:
    if not argv or argv[0] not in ("semaines", "morceaux", "images", "profil", "vieillir"):
        print(__doc__)
        return 2
    cmd, args = argv[0], argv[1:]
    if cmd == "semaines":
        semaines(args[0], int(args[1]) if len(args) > 1 else 52)
    elif cmd == "morceaux":
        morceaux(args[0], int(args[1]) if len(args) > 1 else 40)
    elif cmd == "images":
        images(args[0], int(args[1]) if len(args) > 1 else 600)
    elif cmd == "profil":
        profil(args[0], float(args[1]) if len(args) > 1 else 1.0)
    else:
        vieillir(args[0], int(args[1]), args[2])
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
