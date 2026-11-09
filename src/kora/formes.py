"""LE MONDE EN FORMES (le monde sans grille, premier chantier ; 2026-11-09).

De la planete cuite (un sol par case, ses rivieres), on tire des FORMES
coherentes, dans cet ordre :
  1. LE RIVAGE d'abord : la terre et l'eau (la mer et les lacs). Le trait
     de cote est la courbe de niveau d'un champ lisse terre/eau ; les
     ilots de moins de MIN_ISLAND cases disparaissent. Chaque boucle du
     rivage a la terre a sa gauche.
  2. LES SOLS, sous le rivage : une partition du plan (chaque sol garde ses
     cases ; sous l'eau, le sol de la terre la plus proche), pour que rien
     ne manque au bord. L'eau passe par-dessus : un sol ne traverse jamais
     la cote. La COTE n'est pas un sol : la case de cote prend le sol de
     l'interieur voisin.
  3. LES PLAGES : des lignes le long du rivage, la ou la planete avait de
     la cote ; la plage est la bande de BEACH_WIDTH case, cote terre, le
     long de ces lignes. Elle ne peut pas flotter dans la mer.
  4. LES RIVIERES : des lignes de la source a l'embouchure (posee sur le
     trait de cote ou dans le lac) ; un affluent s'arrete sur la riviere
     qu'il rejoint.
Toutes les formes recoivent la meme dentelure douce (wobble : une fonction
de la position, donc la meme pour deux formes qui se touchent).
"Quel sol ici ?" (Shapes.soil_at) ne passe par aucune case : le bord le
plus proche et son cote ; une tuile sans aucun bord repond tout de suite.
Shapes.check mesure la coherence (tests/test_formes.py).
Coordonnees : (x, y) en colonnes et rangees de la planete, a virgule (x =
colonne, y = rangee), dans une fenetre (col0, row0, largeur, hauteur).
Pur : numpy, ni pygame ni partie.
"""

from __future__ import annotations

import math
import random
from dataclasses import dataclass, field

import numpy as np

from src.kora.types import Terrain
from src.kora.world import MOVE_COST, NEIGHBOR_DELTAS, axial_to_offset, offset_to_axial

TERR = tuple(Terrain)
CODE = {t: i for i, t in enumerate(TERR)}
WATER = CODE[Terrain.EAU]
COAST = CODE[Terrain.COTE]
# Le lissage du champ (en cases) : assez pour effacer l'escalier des cases,
# pas assez pour fondre un detroit d'une case.
SIGMA = 0.8
# Un ilot de moins de cases que ca disparait (un point de terre au large).
MIN_ISLAND = 3
# La plage : sa largeur cote terre (en cases), la part de cote qu'il faut
# autour pour qu'un bout de rivage soit une plage.
BEACH_WIDTH = 0.9
BEACH_MIN = 0.22
# La dentelure : (frequence en cases, amplitude en cases, graine), bornee.
WOBBLE_SCALES = ((0.42, 0.22, 5), (1.9, 0.16, 9))
WOBBLE_WAVES = 3
WOBBLE_MAX = 0.3
# Les tuiles de l'index des bords (en cases).
TILE = 2.0
# Une riviere qui finit a moins de ca du rivage (un delta, un marais) va
# jusqu'au rivage.
MOUTH_REACH = 4.0
# Chaque case garde sa nature en son centre (le lissage ne change que la
# forme ENTRE les centres) : un etang d'une case reste un etang, un isthme
# reste un isthme, une tache de foret reste une foret. L'eau plus fort :
# un etang d'une case garde un tiers de case de rayon.
PIN = 0.08
PIN_WATER = 0.2


# --- les briques -------------------------------------------------------------------


def blur(a: np.ndarray, sigma: float = SIGMA) -> np.ndarray:
    """Flou gaussien separable (bords prolonges)."""
    k = np.exp(-0.5 * (np.arange(-2, 3) / sigma) ** 2)
    k /= k.sum()
    out = a.astype(np.float64)
    for axis in (0, 1):
        pad = [(0, 0), (0, 0)]
        pad[axis] = (2, 2)
        p = np.pad(out, pad, mode="edge")
        acc = np.zeros_like(out)
        for i, w in enumerate(k):
            sl = [slice(None), slice(None)]
            sl[axis] = slice(i, i + out.shape[axis])
            acc += w * p[tuple(sl)]
        out = acc
    return out


def marching(f: np.ndarray) -> list:
    """Les segments de la courbe f = 0 (lineaire dans chaque carre de quatre
    points voisins) ; (x, y) = (colonne, rangee) du tableau."""
    h, w = f.shape
    pos = f > 0
    idx = (pos[:-1, :-1].astype(np.int8) | (pos[:-1, 1:] << 1) | (pos[1:, 1:] << 2) | (pos[1:, :-1] << 3))
    segs = []
    for i, j in zip(*np.nonzero((idx != 0) & (idx != 15))):
        corners = ((j, i), (j + 1, i), (j + 1, i + 1), (j, i + 1))
        vals = (f[i, j], f[i, j + 1], f[i + 1, j + 1], f[i + 1, j])
        pts = []
        for k in range(4):
            p, q = k, (k + 1) % 4
            if (vals[p] > 0) != (vals[q] > 0):
                t = vals[p] / (vals[p] - vals[q])
                a, b = corners[p], corners[q]
                pts.append((a[0] + (b[0] - a[0]) * t, a[1] + (b[1] - a[1]) * t))
        if len(pts) == 2:
            segs.append((pts[0], pts[1]))
        elif len(pts) == 4:
            segs.append((pts[0], pts[1]))
            segs.append((pts[2], pts[3]))
    return segs


def link(segs: list) -> list:
    """Les segments bout a bout : des boucles fermees."""
    def key(p):
        return (round(p[0], 5), round(p[1], 5))
    ends: dict = {}
    for a, b in segs:
        ends.setdefault(key(a), []).append((key(b), b))
        ends.setdefault(key(b), []).append((key(a), a))
    used = set()
    loops = []
    for a, b in segs:
        ka, kb = key(a), key(b)
        if (ka, kb) in used or (kb, ka) in used:
            continue
        loop = [a]
        used.add((ka, kb))
        prev, cur, curp = ka, kb, b
        while cur != ka:
            loop.append(curp)
            nxt = [o for o in ends.get(cur, ()) if o[0] != prev and (cur, o[0]) not in used and (o[0], cur) not in used]
            if not nxt:
                break
            prev, (cur, curp) = cur, nxt[0]
            used.add((prev, cur))
        if len(loop) >= 3:
            loops.append(loop)
    return loops


def chaikin(pts: list, passes: int = 2, closed: bool = True) -> list:
    for _ in range(passes):
        n = len(pts)
        out = [] if closed else [pts[0]]
        for i in range(n if closed else n - 1):
            a, b = pts[i], pts[(i + 1) % n]
            out.append((a[0] * 0.75 + b[0] * 0.25, a[1] * 0.75 + b[1] * 0.25))
            out.append((a[0] * 0.25 + b[0] * 0.75, a[1] * 0.25 + b[1] * 0.75))
        if not closed:
            out.append(pts[-1])
        pts = out
    return pts


def simplify(pts: list, tol: float = 0.08) -> list:
    """Douglas-Peucker d'une ligne ouverte."""
    if len(pts) < 3:
        return list(pts)
    keep = [False] * len(pts)
    keep[0] = keep[-1] = True
    stack = [(0, len(pts) - 1)]
    while stack:
        i, j = stack.pop()
        a, b = pts[i], pts[j]
        dx, dy = b[0] - a[0], b[1] - a[1]
        length = math.hypot(dx, dy)
        best, bi = 0.0, -1
        for k in range(i + 1, j):
            if length < 1e-9:
                d = math.dist(a, pts[k])
            else:
                d = abs(dx * (a[1] - pts[k][1]) - dy * (a[0] - pts[k][0])) / length
            if d > best:
                best, bi = d, k
        if best > tol:
            keep[bi] = True
            stack += [(i, bi), (bi, j)]
    return [p for p, k in zip(pts, keep) if k]


def simplify_loop(loop: list, tol: float = 0.08) -> list:
    """Une boucle se simplifie en deux moities (du premier point au plus
    eloigne, et retour)."""
    far = max(range(len(loop)), key=lambda i: math.dist(loop[0], loop[i]))
    return simplify(loop[: far + 1], tol)[:-1] + simplify(loop[far:] + [loop[0]], tol)[:-1]


def area(loop: list) -> float:
    s = 0.0
    for (x1, y1), (x2, y2) in zip(loop, loop[1:] + loop[:1]):
        s += x1 * y2 - x2 * y1
    return s / 2


def bilinear(a: np.ndarray, x: float, y: float) -> float:
    h, w = a.shape
    x = min(max(x, 0.0), w - 1.001)
    y = min(max(y, 0.0), h - 1.001)
    j, i = int(x), int(y)
    fx, fy = x - j, y - i
    return float(a[i, j] * (1 - fx) * (1 - fy) + a[i, j + 1] * fx * (1 - fy) + a[i + 1, j] * (1 - fx) * fy + a[i + 1, j + 1] * fx * fy)


_WOBBLE: dict = {}


def _wobble_terms(width: int) -> tuple:
    hit = _WOBBLE.get(width)
    if hit is not None:
        return hit
    out = []
    for axis in (0, 1):
        terms = []
        for freq, amp, seed in WOBBLE_SCALES:
            rnd = random.Random(seed * 13 + axis)
            for _ in range(WOBBLE_WAVES):
                # Un pas en colonnes qui tombe juste sur le tour du monde.
                k = max(1, round(freq * width / (2 * math.pi) * rnd.uniform(0.7, 1.3)))
                ang = rnd.uniform(0, 2 * math.pi)
                terms.append((2 * math.pi * k / width, freq * math.sin(ang), rnd.uniform(0, 2 * math.pi), amp / WOBBLE_WAVES))
        out.append(tuple(terms))
    _WOBBLE[width] = tuple(out)
    return _WOBBLE[width]


def wobble(x: float, y: float, width: int) -> tuple[float, float]:
    """La dentelure en (x, y) de la planete : un deplacement doux, borne a
    WOBBLE_MAX case, le meme pour toutes les formes."""
    tx, ty = _wobble_terms(width)
    dx = sum(w * math.sin(a * x + b * y + p) for a, b, p, w in tx)
    dy = sum(w * math.sin(a * x + b * y + p) for a, b, p, w in ty)
    m = math.hypot(dx, dy)
    k = 1.0 if m <= WOBBLE_MAX else WOBBLE_MAX / m
    return dx * k, dy * k


# --- les formes d'une fenetre -------------------------------------------------------


@dataclass
class Shapes:
    """Les formes d'une fenetre de la planete (coordonnees de la fenetre :
    x = colonne - col0, y = rangee - row0)."""

    col0: int
    row0: int
    width: int
    height: int
    planet_width: int
    # Les boucles du rivage (la terre a gauche).
    coast: list = field(default_factory=list)
    # (indice de Terrain, boucle) : la partition des sols (la region a gauche).
    soils: list = field(default_factory=list)
    # Les plages : des lignes le long du rivage.
    beaches: list = field(default_factory=list)
    # (taille 1-3, points) : les rivieres, de la source a l'embouchure.
    rivers: list = field(default_factory=list)
    # Ce qu'on a enleve (ilots) ; le sol par case de la fenetre (pour les
    # verifications seulement).
    removed_islands: int = 0
    labels: np.ndarray | None = None
    # Les champs lisses d'ou viennent les formes : ils repondent dans les
    # tuiles sans aucun bord (la reponse y est la meme partout).
    land_field: np.ndarray | None = None
    soil_fields: dict = field(default_factory=dict)
    _index: dict = field(default_factory=dict)

    # --- les questions -----------------------------------------------------------

    def soil_at(self, x: float, y: float) -> int:
        """Le sol (indice de Terrain) au point (x, y) de la fenetre."""
        if not self.is_land(x, y):
            return WATER
        if self.on_beach(x, y):
            return COAST
        return _side(self._idx("soils"), x, y)

    def is_land(self, x: float, y: float) -> bool:
        return _side(self._idx("coast"), x, y) == 1

    def on_beach(self, x: float, y: float) -> bool:
        idx = self._idx("beaches")
        tx, ty = int(math.floor(x / TILE)), int(math.floor(y / TILE))
        for dx in (-1, 0, 1):
            for dy in (-1, 0, 1):
                for a, b in idx["edges"].get((tx + dx, ty + dy), ()):
                    if _dist_seg(x, y, a, b) < BEACH_WIDTH:
                        return True
        return False

    def cost_at(self, x: float, y: float) -> int | None:
        """Le cout de marche du sol en ce point (None : l'eau, la glace)."""
        return MOVE_COST.get(TERR[self.soil_at(x, y)])

    def _idx(self, name: str) -> dict:
        hit = self._index.get(name)
        if hit is None:
            hit = self._index[name] = _build_index(self, name)
        return hit

    # --- la coherence ------------------------------------------------------------

    def coast_distance(self, x: float, y: float) -> float:
        """La distance au rivage le plus proche (en cases ; 99 au-dela de 6)."""
        return self.nearest_coast(x, y)[0]

    def nearest_coast(self, x: float, y: float) -> tuple:
        """(distance, point) : le point du rivage le plus proche (99 et None
        au-dela de 6 cases)."""
        edges = self._idx("coast")["edges"]
        tx, ty = int(math.floor(x / TILE)), int(math.floor(y / TILE))
        best = (99.0, None)
        for dx in range(-3, 4):
            for dy in range(-3, 4):
                for a, b, _tag in edges.get((tx + dx, ty + dy), ()):
                    vx, vy = b[0] - a[0], b[1] - a[1]
                    l2 = vx * vx + vy * vy
                    t = 0.0 if l2 < 1e-12 else max(0.0, min(1.0, ((x - a[0]) * vx + (y - a[1]) * vy) / l2))
                    q = (a[0] + vx * t, a[1] + vy * t)
                    d = math.dist((x, y), q)
                    if d < best[0]:
                        best = (d, q)
        return best

    def check(self, samples: int = 3000, seed: int = 1) -> dict:
        """La coherence des formes : chaque plage touche le rivage, chaque
        riviere finit dans l'eau, sur une autre riviere ou au bord de la
        fenetre, et le sol rendu est celui des cases (loin des bords)."""
        out: dict = {}
        far = 0
        for line in self.beaches:
            for p in line:
                if self.coast_distance(p[0], p[1]) > 0.05:
                    far += 1
        out["plages loin du rivage"] = far
        lost = 0
        for k, (_size, line) in enumerate(self.rivers):
            x, y = line[-1]
            if x < 1 or y < 1 or x > self.width - 2 or y > self.height - 2:
                continue
            if not self.is_land(x, y) or self.coast_distance(x, y) < 0.6:
                continue
            if self.soil_at(x, y) == CODE[Terrain.MARAIS]:
                # Elle se perd dans un marais (la planete les fait ainsi).
                continue
            others = [q for j, (_s, ln) in enumerate(self.rivers) if j != k for q in ln]
            if others and min(math.dist((x, y), q) for q in others) < 0.6:
                continue
            lost += 1
        out["rivières sans embouchure"] = lost
        rng = random.Random(seed)
        same = water_same = tested = 0
        lab = self.labels
        for _ in range(samples):
            x, y = rng.uniform(2, self.width - 3), rng.uniform(2, self.height - 3)
            dx, dy = wobble(x + self.col0, y + self.row0, self.planet_width)
            i, j = int(round(y - dy)), int(round(x - dx))
            want = int(lab[i, j])
            got = self.soil_at(x, y)
            water_same += (want == WATER) == (got == WATER)
            if want not in (WATER, COAST) and got not in (WATER, COAST):
                tested += 1
                same += want == got
        out["terre et eau comme les cases"] = round(100.0 * water_same / samples, 1)
        out["sols comme les cases (à l'intérieur)"] = round(100.0 * same / max(1, tested), 1)
        out["îlots enlevés"] = self.removed_islands
        return out


def _dist_seg(x: float, y: float, a, b) -> float:
    vx, vy = b[0] - a[0], b[1] - a[1]
    l2 = vx * vx + vy * vy
    t = 0.0 if l2 < 1e-12 else max(0.0, min(1.0, ((x - a[0]) * vx + (y - a[1]) * vy) / l2))
    return math.hypot(x - a[0] - vx * t, y - a[1] - vy * t)


def _build_index(shapes: Shapes, name: str) -> dict:
    """Les bords par tuile ; pour les tuiles sans bord, la reponse toute
    faite (calculee une fois, au centre de la tuile)."""
    edges: dict = {}

    def add(a, b, tag):
        for tx in range(int(math.floor(min(a[0], b[0]) / TILE)), int(math.floor(max(a[0], b[0]) / TILE)) + 1):
            for ty in range(int(math.floor(min(a[1], b[1]) / TILE)), int(math.floor(max(a[1], b[1]) / TILE)) + 1):
                edges.setdefault((tx, ty), []).append((a, b, tag) if tag is not None else (a, b))

    if name == "coast":
        for loop in shapes.coast:
            for a, b in zip(loop, loop[1:] + loop[:1]):
                add(a, b, 1)
    elif name == "soils":
        for k, loop in shapes.soils:
            for a, b in zip(loop, loop[1:] + loop[:1]):
                add(a, b, k)
    else:
        for line in shapes.beaches:
            for a, b in zip(line, line[1:]):
                add(a, b, None)
        return {"edges": edges}
    idx = {"edges": edges, "uniform": {}, "coast": name == "coast", "fallback": lambda x, y: _from_fields(shapes, name, x, y)}
    for tx in range(-2, int(shapes.width / TILE) + 3):
        for ty in range(-2, int(shapes.height / TILE) + 3):
            if (tx, ty) not in edges:
                idx["uniform"][(tx, ty)] = _from_fields(shapes, name, (tx + 0.5) * TILE, (ty + 0.5) * TILE)
    return idx


def _from_fields(shapes: Shapes, name: str, x: float, y: float):
    """La reponse des champs lisses (la ou aucun bord n'est pres : elle est
    la meme que celle des formes)."""
    dx, dy = wobble(x + shapes.col0, y + shapes.row0, shapes.planet_width)
    qx, qy = x - dx, y - dy
    if name == "coast":
        return 1 if bilinear(shapes.land_field, qx, qy) > 0 else 0
    return max(shapes.soil_fields, key=lambda k: bilinear(shapes.soil_fields[k], qx, qy))


def _side(idx: dict, x: float, y: float):
    hit = idx["uniform"].get((int(math.floor(x / TILE)), int(math.floor(y / TILE))))
    if hit is not None:
        return hit
    return _side_slow(idx, x, y)


def _side_slow(idx: dict, x: float, y: float):
    """Le bord le plus proche dont le point est a gauche : sa region (ses
    bords ont la region a gauche)."""
    edges = idx["edges"]
    tx, ty = int(math.floor(x / TILE)), int(math.floor(y / TILE))
    for ring in (1, 3):
        best = None
        nearest_any = None
        for dx in range(-ring, ring + 1):
            for dy in range(-ring, ring + 1):
                for a, b, tag in edges.get((tx + dx, ty + dy), ()):
                    d = _dist_seg(x, y, a, b)
                    left = (b[0] - a[0]) * (y - a[1]) - (b[1] - a[1]) * (x - a[0]) > 0
                    if nearest_any is None or d < nearest_any[0]:
                        nearest_any = (d, left, tag)
                    if left and (best is None or d < best[0]):
                        best = (d, tag)
        if nearest_any is not None:
            if idx["coast"]:
                # Le rivage : terre (1) a gauche du bord le plus proche, sinon l'eau (0).
                return 1 if nearest_any[1] else 0
            if best is not None:
                return best[1]
    return idx["fallback"](x, y)


def _components(mask: np.ndarray) -> list:
    """Les morceaux d'un masque (voisins par les cotes), en listes de cases."""
    h, w = mask.shape
    seen = np.zeros_like(mask, dtype=bool)
    out = []
    for i0, j0 in zip(*np.nonzero(mask)):
        if seen[i0, j0]:
            continue
        stack = [(i0, j0)]
        seen[i0, j0] = True
        part = []
        while stack:
            i, j = stack.pop()
            part.append((i, j))
            for di, dj in ((1, 0), (-1, 0), (0, 1), (0, -1)):
                a, b = i + di, j + dj
                if 0 <= a < h and 0 <= b < w and mask[a, b] and not seen[a, b]:
                    seen[a, b] = True
                    stack.append((a, b))
        out.append(part)
    return out


def _fill_nearest(lab: np.ndarray, hole: np.ndarray) -> np.ndarray:
    """Chaque case de `hole` prend le sol de la case pleine la plus proche
    (par vagues : haut, bas, gauche, droite)."""
    out = lab.copy()
    todo = hole.copy()
    for _ in range(max(lab.shape)):
        if not todo.any():
            break
        for di, dj in ((1, 0), (-1, 0), (0, 1), (0, -1)):
            src = np.roll(out, (di, dj), axis=(0, 1))
            ok = np.roll(~todo, (di, dj), axis=(0, 1))
            take = todo & ok
            out[take] = src[take]
            todo &= ~take
    return out


def _contours(field_: np.ndarray, planet_width: int, col0: int, row0: int, min_area: float = 0.05) -> list:
    """Les boucles de field_ = 0, la region positive a gauche, simplifiees,
    lissees, dentelees."""
    D = np.pad(field_, 1, constant_values=-1.0)
    out = []
    for loop in link(marching(D)):
        loop = [(x - 1, y - 1) for x, y in loop]
        votes = 0
        for i in range(0, len(loop), max(1, len(loop) // 15)):
            (x1, y1), (x2, y2) = loop[i], loop[(i + 1) % len(loop)]
            mx, my = (x1 + x2) / 2, (y1 + y2) / 2
            if not (0.5 < mx < field_.shape[1] - 1.5 and 0.5 < my < field_.shape[0] - 1.5):
                continue
            nx, ny = -(y2 - y1), (x2 - x1)
            n = math.hypot(nx, ny) or 1e-9
            votes += 1 if bilinear(field_, mx + nx / n * 0.05, my + ny / n * 0.05) > 0 else -1
        if votes < 0 or (votes == 0 and area(loop) < 0):
            # (Une boucle qui ne suit que le cadre : celle du dehors.)
            loop.reverse()
        loop = simplify_loop(loop)
        if len(loop) < 3 or abs(area(loop)) < min_area:
            continue
        loop = chaikin(loop, 2)
        dent = []
        for x, y in loop:
            dx, dy = wobble(x + col0, y + row0, planet_width)
            dent.append((x + dx, y + dy))
        out.append(dent)
    return out


def build(world, col0: int, row0: int, width: int, height: int) -> Shapes:
    """Les formes coherentes de la fenetre (col0, row0, width, height) de la
    planete (les colonnes font le tour du monde)."""
    rows = range(max(0, row0), min(world.height, row0 + height))
    row0 = rows.start
    lab = np.zeros((len(rows), width), dtype=np.int16)
    for i, row in enumerate(rows):
        line = world._terrains[row]
        for j in range(width):
            lab[i, j] = CODE[line[(col0 + j) % world.width]]
    shapes = Shapes(col0, row0, width, len(rows), world.width, labels=lab.copy())
    pw = world.width

    # 1. Le rivage (sans les ilots minuscules).
    land = lab != WATER
    for part in _components(land):
        if len(part) < MIN_ISLAND and all(0 < i < land.shape[0] - 1 and 0 < j < land.shape[1] - 1 for i, j in part):
            for i, j in part:
                land[i, j] = False
            shapes.removed_islands += 1
    lf = blur(land.astype(np.float64)) - 0.5
    lf[land] = np.maximum(lf[land], PIN)
    lf[~land] = np.minimum(lf[~land], -PIN_WATER)
    shapes.land_field = lf
    shapes.coast = _contours(lf, pw, col0, row0)

    # 2. Les sols : la cote prend le sol de l'interieur voisin ; sous l'eau,
    # le sol de la terre la plus proche.
    soil = lab.copy()
    soil = _fill_nearest(soil, (lab == COAST) | ~land)
    still = (soil == COAST) | (soil == WATER)
    if still.any():
        soil[still] = CODE[Terrain.PLAINE]
    present = sorted(int(v) for v in np.unique(soil))
    F = {k: blur((soil == k).astype(np.float64)) for k in present}
    if len(present) > 1:
        top = np.max(np.stack([F[k] for k in present]), axis=0)
        for k in present:
            own = soil == k
            F[k][own] = np.maximum(F[k][own], top[own] + PIN)
    shapes.soil_fields = F
    for k in present:
        others = np.max(np.stack([F[j] for j in present if j != k]), axis=0) if len(present) > 1 else np.full_like(F[k], -1.0)
        for loop in _contours(F[k] - others, pw, col0, row0):
            shapes.soils.append((k, loop))

    # 3. Les plages : les bouts de rivage ou la planete avait de la cote.
    beach_field = blur((lab == COAST).astype(np.float64))
    for loop in shapes.coast:
        run: list = []
        for p in loop + loop[:1]:
            dx, dy = wobble(p[0] + col0, p[1] + row0, pw)
            if bilinear(beach_field, p[0] - dx, p[1] - dy) >= BEACH_MIN:
                run.append(p)
            else:
                if len(run) >= 3:
                    shapes.beaches.append(run)
                run = []
        if len(run) >= 3:
            shapes.beaches.append(run)

    # 4. Les rivieres : de la source a l'embouchure ; un delta qui s'arrete
    # pres de la mer va jusqu'au rivage.
    rivers = []
    for size, line in _rivers(world, lab, land, col0, row0, pw):
        x, y = line[-1]
        if shapes.is_land(x, y):
            d, q = shapes.nearest_coast(x, y)
            if q is not None and d <= MOUTH_REACH:
                line = line + [((x + q[0]) / 2, (y + q[1]) / 2), q]
        rivers.append((size, line))
    shapes.rivers = rivers
    return shapes


def _rivers(world, lab, land, col0, row0, pw) -> list:
    h, w = lab.shape
    nxt: dict = {}
    size: dict = {}
    mouth: dict = {}
    for i in range(h):
        row = row0 + i
        for j in range(w):
            col = (col0 + j) % pw
            v = world.river_at(col, row)
            if not v:
                continue
            dq, dr = NEIGHBOR_DELTAS[(v & 7) - 1]
            hx = offset_to_axial(col, row)
            c2, r2 = axial_to_offset(type(hx)(hx.q + dq, hx.r + dr))
            dj = (c2 - col + pw // 2) % pw - pw // 2
            to = (j + dj, r2 - row0)
            size[(j, i)] = v >> 3
            ti, tj = to[1], to[0]
            if 0 <= ti < h and 0 <= tj < w and not land[ti, tj]:
                # L'embouchure : a mi-chemin de la case d'eau (le rivage).
                mouth[(j, i)] = ((j + tj) / 2, (i + ti) / 2)
            else:
                nxt[(j, i)] = to
    heads = sorted(set(size) - set(nxt.values()), key=lambda p: (p[1], p[0]))

    def length(p):
        n, seen = 0, set()
        while p in nxt and p not in seen:
            seen.add(p)
            p = nxt[p]
            n += 1
        return n
    heads.sort(key=lambda p: -length(p))
    taken: set = set()
    out = []
    for head in heads:
        line = [head]
        cur = head
        taken.add(head)
        end = None
        while True:
            if cur in mouth:
                end = mouth[cur]
                break
            if cur not in nxt:
                break
            cur = nxt[cur]
            line.append(cur)
            if cur in taken:
                break
            taken.add(cur)
        pts = [(float(x), float(y)) for x, y in line]
        if end is not None:
            pts.append(end)
        if len(pts) < 2:
            continue
        smooth = chaikin(pts, 3, closed=False)
        dent = []
        for x, y in smooth:
            dx, dy = wobble(x + col0, y + row0, pw)
            dent.append((x + dx, y + dy))
        out.append((max(size.get(p, 1) for p in line), dent))
    return out
