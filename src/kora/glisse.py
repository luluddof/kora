"""LE GLISSEMENT (le monde sans grille, 0.27.0 ; sa demande du 2026-11-09 :
"le mouvement glisserait au lieu d'aller de case en case", et "pas forcement
en ligne droite").

A l'ecran, une unite ne saute plus d'un point a l'autre : quand sa position
change (une semaine de jeu), elle glisse le long du chemin qu'elle vient de
faire, LISSE en courbe (une spline qui passe par les points du chemin : elle
contourne comme le chemin, sans les angles de l'escalier), pendant la duree
reelle d'une semaine a la vitesse choisie (MAX_SECONDS au plus). Le chemin
dessine (Renderer.draw_path) suit la meme courbe (smooth).
Interface seulement : la partie ne change pas, le temps de l'ecran ne
compte que pour l'image (le jeu reste deterministe). N'importe pas pygame.
"""

from __future__ import annotations

import math
import time

from src.kora.world import axial_to_offset

MAX_SECONDS = 1.2
# Au-dela de tant de cases d'un coup, ce n'est pas une marche (une partie
# chargee, une fondation) : pas de glissement.
MAX_JUMP = 14
# Points de la courbe entre deux points du chemin.
STEPS = 6
_TRACK: dict = {}
_GLIDE: dict = {}


def _points(world, hexes) -> list:
    """Les points (colonne, rangee) du chemin, deroules autour du monde."""
    out = []
    width = world.width
    for h in hexes:
        c, r = axial_to_offset(h)
        c = float(c)
        if out and world.wrap_x:
            prev = out[-1][0]
            while c - prev > width / 2:
                c -= width
            while prev - c > width / 2:
                c += width
        out.append((c, float(r)))
    return out


def smooth(pts: list, steps: int = STEPS) -> list:
    """La courbe (Catmull-Rom) qui passe par les points."""
    if len(pts) < 3:
        return list(pts)
    out = []
    ext = [pts[0]] + list(pts) + [pts[-1]]
    for i in range(1, len(ext) - 2):
        p0, p1, p2, p3 = ext[i - 1], ext[i], ext[i + 1], ext[i + 2]
        for k in range(steps):
            t = k / steps
            t2, t3 = t * t, t * t * t
            out.append(tuple(
                0.5 * (2 * p1[j] + (-p0[j] + p2[j]) * t + (2 * p0[j] - 5 * p1[j] + 4 * p2[j] - p3[j]) * t2 + (-p0[j] + 3 * p1[j] - 3 * p2[j] + p3[j]) * t3)
                for j in (0, 1)
            ))
    out.append(pts[-1])
    return out


def _along(curve: list, frac: float):
    """Le point a la fraction `frac` de la longueur de la courbe."""
    lengths = [math.dist(a, b) for a, b in zip(curve, curve[1:])]
    total = sum(lengths)
    if total <= 1e-9:
        return curve[-1]
    goal = max(0.0, min(1.0, frac)) * total
    for (a, b), d in zip(zip(curve, curve[1:]), lengths):
        if goal <= d and d > 0:
            t = goal / d
            return (a[0] + (b[0] - a[0]) * t, a[1] + (b[1] - a[1]) * t)
        goal -= d
    return curve[-1]


def observe(state, band, now: float | None = None) -> None:
    """A chaque image : une position qui a change lance un glissement le long
    du chemin fait (le chemin d'avant, jusqu'a la nouvelle position)."""
    key = (id(state), band.id)
    pos = band.position
    last = _TRACK.get(key)
    if last is not None and last[0] != pos:
        old, path = last
        world = state.world
        if world.distance(old, pos) <= MAX_JUMP:
            trail = [old]
            if pos in path:
                trail += list(path[: path.index(pos) + 1])
            else:
                trail.append(pos)
            rate = state.clock.ticks_per_second() if not state.clock.paused else 0.0
            dur = min(MAX_SECONDS, 1.0 / rate) if rate > 0 else 0.4
            now = time.perf_counter() if now is None else now
            _GLIDE[key] = (smooth(_points(world, trail)), now, dur)
        else:
            _GLIDE.pop(key, None)
    _TRACK[key] = (pos, tuple(band.path))
    if len(_TRACK) > 20000:
        _TRACK.clear()
        _GLIDE.clear()


def place(state, band, now: float | None = None):
    """(colonne, rangee) a virgule ou montrer l'unite, ou None (a sa
    position)."""
    key = (id(state), band.id)
    glide = _GLIDE.get(key)
    if glide is None:
        return None
    curve, t0, dur = glide
    now = time.perf_counter() if now is None else now
    frac = (now - t0) / dur if dur > 0 else 1.0
    if frac >= 1.0:
        del _GLIDE[key]
        return None
    return _along(curve, frac)


def gliding() -> bool:
    """Une unite glisse encore (l'ecran doit se redessiner)."""
    return bool(_GLIDE)
