"""Essai SANS GRILLE sur SA partie (copie) : la region de son village decrite
en FORMES au lieu de cases, et ce qu'on en fait sans jamais passer par une
case.
  1. LES FORMES : chaque sol (plaine, foret, eau...) devient des regions aux
     bords courbes (les courbes de niveau d'un champ lisse : "marching
     squares"), lissees, avec la meme dentelure douce que le dessin
     d'aujourd'hui (globe.warp) ; les rivieres deviennent des lignes.
  2. LE SOL SOUS UN POINT : on cherche le bord de region le plus proche et
     de quel cote on est (un index par tuiles des bords : rapide) ; compare
     au sol de la case d'aujourd'hui.
  3. UN CHEMIN SANS CASE : un nuage de points de passage tires au hasard
     (pas un damier), relies a leurs voisins, un A*, puis le chemin redresse
     (droit tant que ca ne coute pas plus) et lisse ; compare au A* des
     cases d'aujourd'hui.
Mesure tout (temps, nombres) ; dessine la carte d'aujourd'hui et la carte en
formes, au meme endroit, le chemin dessus.
python maq_sans_grille.py RACINE SAUVEGARDE SORTIE"""
import heapq
import json
import math
import random
import sys
import time

import numpy as np

import maq_commun as commun
from maq_commun import C, H, W, pygame, theme

from src.kora import partie_carte
from src.kora.globe import offset_to_xyz, project_xyz, rotate_xyz, view_params, warp
from src.kora.layout import HUD_HEIGHT
from src.kora.look import season_color
from src.kora.path import astar
from src.kora.types import Terrain
from src.kora.world import MOVE_COST, axial_to_offset, enter_cost_for, offset_to_axial

st, play, r = commun.load(sys.argv[2], sys.argv[3])
OUT = sys.argv[3]
me = st.viewer
WORLD = st.world
from src.kora import events  # noqa: E402

events._book(st).pending = []
home = max((b for b in st.bands.values() if b.tribe_id == me), key=lambda b: (b.village is not None, b.population))
C0, R0 = axial_to_offset(home.position)
HALF_W, HALF_H = 70, 44
TERR = list(Terrain)
CODE = {t: i for i, t in enumerate(TERR)}
SEASON = st.clock.season()
STATS = {}


def timed(name):
    class T:
        def __enter__(self):
            self.t = time.perf_counter()

        def __exit__(self, *a):
            STATS[name] = round(time.perf_counter() - self.t, 3)
    return T()


# --- 1. les formes ---------------------------------------------------------------

def window_labels():
    rows = range(max(0, R0 - HALF_H), min(WORLD.height, R0 + HALF_H + 1))
    cols = range(C0 - HALF_W, C0 + HALF_W + 1)
    lab = np.zeros((len(rows), len(cols)), dtype=np.int16)
    for i, row in enumerate(rows):
        line = WORLD._terrains[row]
        for j, col in enumerate(cols):
            lab[i, j] = CODE[line[col % WORLD.width]]
    return lab, rows.start, cols.start


def blur(a, sigma=0.8):
    k = np.exp(-0.5 * (np.arange(-2, 3) / sigma) ** 2)
    k /= k.sum()
    out = a
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


def marching(field):
    """Les segments de la courbe field = 0 (lineaire dans chaque carre de 4
    points), orientes la region positive a gauche (on le verifie apres)."""
    h, w = field.shape
    segs = []
    f = field
    for i in range(h - 1):
        for j in range(w - 1):
            a, b, c, d = f[i, j], f[i, j + 1], f[i + 1, j + 1], f[i + 1, j]
            idx = (a > 0) | ((b > 0) << 1) | ((c > 0) << 2) | ((d > 0) << 3)
            if idx in (0, 15):
                continue

            def lerp(p, q, vp, vq):
                t = vp / (vp - vq)
                return (p[0] + (q[0] - p[0]) * t, p[1] + (q[1] - p[1]) * t)
            # Les coins : (x, y) = (colonne, rangee).
            P = ((j, i), (j + 1, i), (j + 1, i + 1), (j, i + 1))
            V = (a, b, c, d)
            pts = []
            for k in range(4):
                p, q = k, (k + 1) % 4
                if (V[p] > 0) != (V[q] > 0):
                    pts.append(lerp(P[p], P[q], V[p], V[q]))
            if len(pts) == 2:
                segs.append((pts[0], pts[1]))
            elif len(pts) == 4:
                segs.append((pts[0], pts[1]))
                segs.append((pts[2], pts[3]))
    return segs


def link(segs):
    """Les segments bout a bout : des boucles fermees."""
    def key(p):
        return (round(p[0], 4), round(p[1], 4))
    nxt = {}
    for a, b in segs:
        nxt.setdefault(key(a), []).append((key(b), b))
        nxt.setdefault(key(b), []).append((key(a), a))
    used = set()
    loops = []
    for a, b in segs:
        ka = key(a)
        if (ka, key(b)) in used or (key(b), ka) in used:
            continue
        loop = [a]
        prev, cur, curp = ka, key(b), b
        used.add((ka, key(b)))
        while cur != ka and len(loop) < 200000:
            loop.append(curp)
            options = [o for o in nxt.get(cur, []) if o[0] != prev and (cur, o[0]) not in used and (o[0], cur) not in used]
            if not options:
                break
            prev, (cur, curp) = cur, options[0]
            used.add((prev, cur))
        if len(loop) >= 4:
            loops.append(loop)
    return loops


def chaikin(pts, passes=2, closed=True):
    for _ in range(passes):
        out = []
        n = len(pts)
        rng = range(n) if closed else range(n - 1)
        if not closed:
            out.append(pts[0])
        for i in rng:
            a, b = pts[i], pts[(i + 1) % n]
            out.append((a[0] * 0.75 + b[0] * 0.25, a[1] * 0.75 + b[1] * 0.25))
            out.append((a[0] * 0.25 + b[0] * 0.75, a[1] * 0.25 + b[1] * 0.75))
        if not closed:
            out.append(pts[-1])
        pts = out
    return pts


def simplify(pts, tol=0.08):
    """Douglas-Peucker (garde la forme, enleve les points inutiles)."""
    if len(pts) < 4:
        return pts
    keep = [False] * len(pts)
    keep[0] = keep[-1] = True
    stack = [(0, len(pts) - 1)]
    while stack:
        i, j = stack.pop()
        a, b = pts[i], pts[j]
        dx, dy = b[0] - a[0], b[1] - a[1]
        L = math.hypot(dx, dy) or 1e-9
        best, bi = 0.0, -1
        for k in range(i + 1, j):
            d = abs(dx * (a[1] - pts[k][1]) - dy * (a[0] - pts[k][0])) / L
            if d > best:
                best, bi = d, k
        if best > tol and bi > 0:
            keep[bi] = True
            stack += [(i, bi), (bi, j)]
    return [p for p, k in zip(pts, keep) if k]


def bilinear(a, x, y):
    h, w = a.shape
    x = min(max(x, 0.0), w - 1.001)
    y = min(max(y, 0.0), h - 1.001)
    j, i = int(x), int(y)
    fx, fy = x - j, y - i
    return (a[i, j] * (1 - fx) * (1 - fy) + a[i, j + 1] * fx * (1 - fy)
            + a[i + 1, j] * (1 - fx) * fy + a[i + 1, j + 1] * fx * fy)


def area(loop):
    s = 0.0
    for (x1, y1), (x2, y2) in zip(loop, loop[1:] + loop[:1]):
        s += x1 * y2 - x2 * y1
    return s / 2


lab, ROW0, COL0 = window_labels()
present = sorted(set(int(v) for v in np.unique(lab)))
with timed("formes : champs et courbes"):
    F = {k: blur((lab == k).astype(np.float64)) for k in present}
    regions = []  # (classe, boucle orientee : la region a gauche)
    for k in present:
        others = np.max(np.stack([F[j] for j in present if j != k]), axis=0) if len(present) > 1 else np.zeros_like(F[k])
        D = np.pad(F[k] - others, 1, constant_values=-1.0)
        for loop in link(marching(D)):
            loop = [(x - 1, y - 1) for x, y in loop]
            # Orientation : un point juste a gauche d'un bord doit etre dans la
            # region ; on vote sur des bords loin du cadre (au cadre, le champ
            # est ecrase).
            votes = 0
            for i in range(0, len(loop), max(1, len(loop) // 15)):
                (x1, y1), (x2, y2) = loop[i], loop[(i + 1) % len(loop)]
                mx, my = (x1 + x2) / 2 + 1, (y1 + y2) / 2 + 1
                if not (1.5 < mx < D.shape[1] - 2.5 and 1.5 < my < D.shape[0] - 2.5):
                    continue
                nx, ny = -(y2 - y1), (x2 - x1)
                n = math.hypot(nx, ny) or 1e-9
                votes += 1 if bilinear(D, mx + nx / n * 0.05, my + ny / n * 0.05) > 0 else -1
            if votes < 0:
                loop.reverse()
            # Une boucle fermee se simplifie en deux moities (de son premier
            # point au plus eloigne, et retour).
            far = max(range(len(loop)), key=lambda i: math.dist(loop[0], loop[i]))
            loop = simplify(loop[:far + 1])[:-1] + simplify(loop[far:] + [loop[0]])[:-1]
            if len(loop) < 3:
                continue
            loop = chaikin(loop, 2)
            regions.append((k, loop))
with timed("formes : dentelure (warp)"):
    shaped = []
    for k, loop in regions:
        out = []
        for x, y in loop:
            gx, gy = x + COL0, y + ROW0
            dx, dy = warp(gx, gy, WORLD.width)
            out.append((x - dx, y - dy))
        shaped.append((k, out))
    regions = shaped
vertices = sum(len(lp) for _k, lp in regions)
STATS["regions"] = len(regions)
STATS["sommets"] = vertices
STATS["fenetre (cases d'aujourd'hui)"] = int(lab.size)


# Les rivieres : des lignes (de chaque case de riviere vers sa voisine en aval).
def rivers():
    from src.kora.world import NEIGHBOR_DELTAS
    nxt = {}
    size = {}
    for i in range(lab.shape[0]):
        row = ROW0 + i
        for j in range(lab.shape[1]):
            col = (COL0 + j) % WORLD.width
            v = WORLD.river_at(col, row)
            if not v:
                continue
            dq, dr = NEIGHBOR_DELTAS[(v & 7) - 1]
            h = offset_to_axial(col, row)
            c2, r2 = axial_to_offset(type(h)(h.q + dq, h.r + dr))
            nxt[(j, i)] = (j + (c2 - col + WORLD.width // 2) % WORLD.width - WORLD.width // 2, r2 - ROW0)
            size[(j, i)] = v >> 3
    heads = set(nxt) - set(nxt.values())
    lines = []
    for hd in sorted(heads):
        line, cur, seen = [hd], hd, {hd}
        while cur in nxt and nxt[cur] not in seen:
            cur = nxt[cur]
            seen.add(cur)
            line.append(cur)
        if len(line) >= 2:
            pts = []
            for x, y in chaikin([(float(x), float(y)) for x, y in line], 3, closed=False):
                dx, dy = warp(x + COL0, y + ROW0, WORLD.width)
                pts.append((x - dx, y - dy))
            lines.append((max(size.get(p, 1) for p in line), pts))
    return lines


with timed("rivieres en lignes"):
    RIVERS = rivers()
STATS["rivieres"] = len(RIVERS)


# --- 2. le sol sous un point -------------------------------------------------------

TILE = 2.0
EDGES = {}
for idx, (k, loop) in enumerate(regions):
    for a, b in zip(loop, loop[1:] + loop[:1]):
        x0, x1 = sorted((a[0], b[0]))
        y0, y1 = sorted((a[1], b[1]))
        for tx in range(int(math.floor(x0 / TILE)), int(math.floor(x1 / TILE)) + 1):
            for ty in range(int(math.floor(y0 / TILE)), int(math.floor(y1 / TILE)) + 1):
                EDGES.setdefault((tx, ty), []).append((a, b, k))


def nearest_side(x, y, ring=1):
    tx, ty = int(math.floor(x / TILE)), int(math.floor(y / TILE))
    best = None
    for dx in range(-ring, ring + 1):
        for dy in range(-ring, ring + 1):
            for a, b, k in EDGES.get((tx + dx, ty + dy), ()):
                vx, vy = b[0] - a[0], b[1] - a[1]
                L2 = vx * vx + vy * vy or 1e-12
                t = max(0.0, min(1.0, ((x - a[0]) * vx + (y - a[1]) * vy) / L2))
                px, py = a[0] + vx * t, a[1] + vy * t
                d = (x - px) ** 2 + (y - py) ** 2
                left = vx * (y - a[1]) - vy * (x - a[0]) > 0
                cand = (d, not left, k)
                if best is None or cand < best:
                    best = cand
    return best


# Les regions qui ne touchent aucun bord pres du point : le sol "par defaut"
# de la tuile (le plus courant), calcule une fois.
FILL = {}


def soil_at(x, y):
    """Le sol (indice de Terrain) sous le point (x, y) de la fenetre, sans
    case : une tuile tout entiere dans une region repond tout de suite
    (UNIFORM) ; sinon le bord de region le plus proche, et de quel cote on
    est."""
    hit = UNIFORM.get((int(math.floor(x / TILE)), int(math.floor(y / TILE))))
    if hit is not None:
        return hit
    return _soil_slow(x, y)


def _soil_slow(x, y):
    for ring in (1, 3, 6):
        hit = nearest_side(x, y, ring)
        if hit is not None:
            d, outside, k = hit
            if not outside:
                return k
            # Dehors du bord le plus proche : le bord le plus proche dont on
            # est a gauche (la region voisine).
            tx, ty = int(math.floor(x / TILE)), int(math.floor(y / TILE))
            best = None
            for dx in range(-ring, ring + 1):
                for dy in range(-ring, ring + 1):
                    for a, b, kk in EDGES.get((tx + dx, ty + dy), ()):
                        vx, vy = b[0] - a[0], b[1] - a[1]
                        if vx * (y - a[1]) - vy * (x - a[0]) <= 0:
                            continue
                        L2 = vx * vx + vy * vy or 1e-12
                        t = max(0.0, min(1.0, ((x - a[0]) * vx + (y - a[1]) * vy) / L2))
                        dd = (x - a[0] - vx * t) ** 2 + (y - a[1] - vy * t) ** 2
                        if best is None or dd < best[0]:
                            best = (dd, kk)
            if best is not None:
                return best[1]
    return int(lab[int(min(max(y, 0), lab.shape[0] - 1)), int(min(max(x, 0), lab.shape[1] - 1))])


# Les tuiles sans aucun bord : tout entieres dans une region (une seule
# question, a leur centre, une fois pour toutes).
UNIFORM = {}
with timed("tuiles uniformes (une fois)"):
    for tx in range(-1, int(lab.shape[1] / TILE) + 2):
        for ty in range(-1, int(lab.shape[0] / TILE) + 2):
            if (tx, ty) not in EDGES:
                UNIFORM[(tx, ty)] = _soil_slow((tx + 0.5) * TILE, (ty + 0.5) * TILE)
STATS["tuiles : uniformes / avec un bord"] = f"{len(UNIFORM)} / {len(EDGES)}"

rng = random.Random(7)
probe =[(rng.uniform(2, lab.shape[1] - 3), rng.uniform(2, lab.shape[0] - 3)) for _ in range(4000)]
with timed("sol sous 4000 points (sans case)"):
    got = [soil_at(x, y) for x, y in probe]
def todays_soil(x, y):
    """Le sol que le jeu d'aujourd'hui montre en ce point : la case sous le
    point deplace par la dentelure (globe.lonlat_to_colrow)."""
    dx, dy = warp(x + COL0, y + ROW0, WORLD.width)
    i = int(round(y + dy))
    j = int(round(x + dx))
    return int(lab[min(max(i, 0), lab.shape[0] - 1), min(max(j, 0), lab.shape[1] - 1)])


agree = sum(1 for (x, y), k in zip(probe, got) if todays_soil(x, y) == k)
STATS["sol : accord avec la case d'aujourd'hui"] = f"{100 * agree / len(probe):.1f} %"
STATS["sol : microsecondes par point"] = round(1e6 * STATS["sol sous 4000 points (sans case)"] / len(probe), 1)


# --- 3. un chemin sans case -----------------------------------------------------------

def cost_at(x, y):
    t = TERR[soil_at(x, y)]
    return MOVE_COST.get(t)


SPACING = 0.9
with timed("points de passage (nuage, sans damier)"):
    # Bridson : des points a au moins SPACING les uns des autres, au hasard.
    cell = SPACING / math.sqrt(2)
    gw, gh = int(lab.shape[1] / cell) + 1, int(lab.shape[0] / cell) + 1
    grid = {}
    pts = []
    rr = random.Random(11)
    first = (float(C0 - COL0), float(R0 - ROW0))
    active = [first]
    pts.append(first)
    grid[(int(first[0] / cell), int(first[1] / cell))] = 0
    while active:
        i = rr.randrange(len(active))
        px, py = active[i]
        placed = False
        for _ in range(12):
            ang = rr.uniform(0, 2 * math.pi)
            rad = rr.uniform(SPACING, 2 * SPACING)
            x, y = px + rad * math.cos(ang), py + rad * math.sin(ang)
            if not (0 <= x < lab.shape[1] - 1 and 0 <= y < lab.shape[0] - 1):
                continue
            gx, gy = int(x / cell), int(y / cell)
            ok = True
            for ax in range(gx - 2, gx + 3):
                for ay in range(gy - 2, gy + 3):
                    k = grid.get((ax, ay))
                    if k is not None and (pts[k][0] - x) ** 2 + (pts[k][1] - y) ** 2 < SPACING * SPACING:
                        ok = False
                        break
                if not ok:
                    break
            if ok:
                grid[(gx, gy)] = len(pts)
                pts.append((x, y))
                active.append((x, y))
                placed = True
                break
        if not placed:
            active.pop(i)
    land = [i for i, (x, y) in enumerate(pts) if cost_at(x, y) is not None]
STATS["points de passage (terre)"] = len(land)

with timed("liens entre voisins (cout du sol le long)"):
    LINK = 2.0
    bucket = {}
    for i in land:
        x, y = pts[i]
        bucket.setdefault((int(x / LINK), int(y / LINK)), []).append(i)
    adj = {i: [] for i in land}
    for i in land:
        x, y = pts[i]
        bx, by = int(x / LINK), int(y / LINK)
        for ax in range(bx - 1, bx + 2):
            for ay in range(by - 1, by + 2):
                for j in bucket.get((ax, ay), ()):
                    if j <= i:
                        continue
                    d = math.dist(pts[i], pts[j])
                    if d > LINK:
                        continue
                    cs = [cost_at(x + (pts[j][0] - x) * t, y + (pts[j][1] - y) * t) for t in (0.25, 0.5, 0.75)]
                    if any(c is None for c in cs):
                        continue
                    w = d * sum(cs) / 3
                    adj[i].append((j, w))
                    adj[j].append((i, w))
STATS["liens"] = sum(len(v) for v in adj.values()) // 2


def nearest_point(x, y):
    return min(land, key=lambda i: (pts[i][0] - x) ** 2 + (pts[i][1] - y) ** 2)


def graph_astar(s, g):
    gx, gy = pts[g]
    openq = [(0.0, 0, s)]
    best = {s: 0.0}
    came = {}
    seq = 0
    while openq:
        _f, _s, u = heapq.heappop(openq)
        if u == g:
            out = [u]
            while u in came:
                u = came[u]
                out.append(u)
            return out[::-1]
        for v, w in adj[u]:
            nd = best[u] + w
            if nd < best.get(v, 1e18):
                best[v] = nd
                came[v] = u
                seq += 1
                heapq.heappush(openq, (nd + 10 * math.dist(pts[v], (gx, gy)), seq, v))
    return None


def seg_cost(a, b):
    n = max(1, int(math.dist(a, b) * 4))
    tot = 0.0
    for k in range(n):
        t = (k + 0.5) / n
        c = cost_at(a[0] + (b[0] - a[0]) * t, a[1] + (b[1] - a[1]) * t)
        if c is None:
            return None
        tot += c * math.dist(a, b) / n
    return tot


def straighten(line):
    acc = [0.0]
    for a, b in zip(line, line[1:]):
        acc.append(acc[-1] + (seg_cost(a, b) or 1e9))
    out, i = [line[0]], 0
    while i < len(line) - 1:
        j = i + 1
        for k in range(len(line) - 1, i + 1, -1):
            c = seg_cost(line[i], line[k])
            if c is not None and c <= (acc[k] - acc[i]) * 1.02:
                j = k
                break
        out.append(line[j])
        i = j
    return out


# Le but : a 18-34 cases du village, celui que la ligne droite atteint le plus
# mal (de l'autre cote de l'eau, d'un relief) : le chemin le plus long par
# rapport a la distance.
start = nearest_point(C0 - COL0, R0 - ROW0)
cands = [i for i in land if 18 <= math.dist(pts[i], pts[start]) <= 34]
rng.shuffle(cands)
best = None
for g in cands[:400]:
    path = graph_astar(start, g)
    if not path:
        continue
    line = [pts[i] for i in path]
    length = sum(math.dist(a, b) for a, b in zip(line, line[1:]))
    ratio = length / math.dist(line[0], line[-1])
    if ratio > 2.2:
        continue
    if best is None or ratio > best[0]:
        best = (ratio, g, path)
_ratio, goal, path = best
line = [pts[i] for i in path]
a, b = line[0], line[-1]
dev = max(abs((b[0] - a[0]) * (a[1] - q[1]) - (a[0] - q[0]) * (b[1] - a[1])) / math.dist(a, b) for q in line)
with timed("chemin sans case : A* sur le nuage"):
    path = graph_astar(start, goal)
line = [pts[i] for i in path]
with timed("chemin sans case : redresse"):
    smooth = chaikin(straighten(line), 3, closed=False)
STATS["chemin : ecart a la ligne droite (cases)"] = round(dev, 1)
STATS["chemin : longueur (cases)"] = round(sum(math.dist(a, b) for a, b in zip(smooth, smooth[1:])), 1)
gx, gy = pts[goal]
goal_hex = offset_to_axial(int(round(gx + COL0)) % WORLD.width, int(round(gy + ROW0)))
with timed("chemin d'aujourd'hui : A* des cases"):
    hex_path = astar(WORLD, home.position, goal_hex, max_nodes=20000) if enter_cost_for(WORLD, goal_hex, False) else None
STATS["chemin d'aujourd'hui : pas"] = len(hex_path) if hex_path else None


# --- 4. le dessin ----------------------------------------------------------------------

xs_, ys_ = [q[0] for q in smooth], [q[1] for q in smooth]
mid = ((min(xs_) + max(xs_)) / 2 + COL0, (min(ys_) + max(ys_)) / 2 + ROW0)
play.globe_yaw, play.globe_pitch = partie_carte.look_hex(st, offset_to_axial(int(round(mid[0])) % WORLD.width, int(round(mid[1]))))
play.selected = None
for z in [x / 4 for x in range(48, 4, -1)]:
    play.zoom = z
    gcx, gcy, focal, dist = view_params(play.zoom, W, H, HUD_HEIGHT)
    cam = (play.globe_yaw, play.globe_pitch, gcx, gcy, focal, dist)

    def screen(p, c=cam):
        x, y, zz = offset_to_xyz(p[0] + COL0, p[1] + ROW0, WORLD.width, WORLD.height)
        s = project_xyz(*rotate_xyz(x, y, zz, c[0], c[1]), *c[2:])
        return None if s is None else (s[0], s[1])
    span = [screen(p) for p in smooth]
    if all(span):
        xs, ys = [p[0] for p in span], [p[1] for p in span]
        if max(xs) - min(xs) < W * 0.62 and max(ys) - min(ys) < (H - HUD_HEIGHT) * 0.62:
            break
saved = home.population
home.population = 0
r.map_mode = "relief"
today = commun.backdrop(play, r).copy()
home.population = saved


def panel(surf, title, lines):
    box = (16, HUD_HEIGHT + 14, 520, 34 + 22 * len(lines))
    theme.panel(surf, box, "infobulle")
    theme.text(surf, title, "petit_gras", C.os, (box[0] + 16, box[1] + 10))
    for i, (text, col) in enumerate(lines):
        theme.text(surf, text, "mini", col, (box[0] + 16, box[1] + 36 + 22 * i), box[2] - 30)


def draw_path(s, line, color):
    p = [screen(q) for q in line]
    p = [q for q in p if q]
    glow = pygame.Surface((W, H), pygame.SRCALPHA)
    pygame.draw.lines(glow, (*color, 90), False, [(int(x), int(y)) for x, y in p], 9)
    s.blit(glow, (0, 0))
    pygame.draw.aalines(s, C.os, False, p)


with timed("dessin de la carte en formes"):
    vec = today.copy()
    sea = season_color(Terrain.EAU, SEASON)
    pygame.draw.rect(vec, sea, (0, HUD_HEIGHT, W, H - HUD_HEIGHT))
    order = sorted(regions, key=lambda kl: -abs(area(kl[1])))
    for k, loop in order:
        if area(loop) < 0:
            continue
        poly = [screen(p) for p in loop]
        if any(q is None for q in poly) or len(poly) < 3:
            continue
        pygame.draw.polygon(vec, season_color(TERR[k], SEASON), poly)
        if TERR[k] is Terrain.EAU:
            pygame.draw.aalines(vec, theme._mix(sea, (255, 255, 255), 0.25), True, poly)
    for size, line in RIVERS:
        p = [screen(q) for q in line]
        p = [q for q in p if q]
        if len(p) >= 2:
            pygame.draw.lines(vec, (62, 118, 196), False, p, 1 + size)
    # Le brouillard de sa partie : ce qu'il n'a jamais vu reste noir.
    a_today = pygame.surfarray.pixels3d(today)
    unseen = a_today.max(axis=2) < 16
    a_vec = pygame.surfarray.pixels3d(vec)
    a_vec[unseen] = a_today[unseen]
    del a_today, a_vec
    # Le bandeau et le rail du jeu restent par-dessus (on ne redessine que la carte).
    vec.blit(today, (0, 0), (0, 0, W, HUD_HEIGHT))
    rail = 1530
    vec.blit(today, (rail, HUD_HEIGHT), (rail, HUD_HEIGHT, W - rail, H - HUD_HEIGHT))

draw_path(vec, smooth, C.ocre_jaune)
v0 = screen((C0 - COL0, R0 - ROW0))
pygame.draw.circle(vec, C.braise, (int(v0[0]), int(v0[1])), 7)
vec_clean = vec.copy()
n_cells = STATS["fenetre (cases d'aujourd'hui)"]
n_steps = STATS["chemin d'aujourd'hui : pas"]
def side_by_side():
    """Les deux cartes, moitie gauche et moitie droite autour du trajet."""
    pts_s = [screen(q) for q in smooth]
    cx = int(sum(q[0] for q in pts_s) / len(pts_s))
    half = W // 2
    x0 = max(0, min(W - half, cx - half // 2))
    out = pygame.Surface((W, H))
    out.blit(old_clean, (0, 0), (x0, 0, half, H))
    out.blit(vec_clean, (half, 0), (x0, 0, half, H))
    pygame.draw.line(out, C.ocre, (half, HUD_HEIGHT), (half, H), 3)
    for x, text in ((16, "Aujourd'hui : des cases"), (half + 16, "Sans grille : des formes")):
        theme.panel(out, (x, H - 64, 300, 40), "infobulle")
        theme.text(out, text, "petit_gras", C.os, (x + 14, H - 56))
    commun.save(out, f"{OUT}/sans_grille_comparaison.png")


panel(vec, "Sans grille : la carte en formes", [
    (f"{STATS['regions']} régions de sol aux bords courbes ({STATS['sommets']} points) et {STATS['rivieres']} rivières", C.lin),
    (f"en lignes, au lieu de {n_cells} cases. Le chemin : un nuage de points de passage,", C.lin),
    ("puis redressé : il contourne ce qui coûte, en courbe. Rien ne passe par une case.", C.bon),
])
commun.tag(vec, f"Essai · Sans grille : la région de son village en formes (sa partie, an {st.clock.year})")
commun.save(vec, f"{OUT}/sans_grille_formes.png")

old = today.copy()
def local(h):
    col, row = axial_to_offset(h)
    dc = (col - COL0 + WORLD.width // 2) % WORLD.width - WORLD.width // 2
    return (float(dc), float(row - ROW0))


if hex_path:
    hp = [screen(local(h)) for h in [home.position] + hex_path]
    hp = [q for q in hp if q]
    for a, b in zip(hp, hp[1:]):
        theme.dotted(old, a, b, C.nuit, 7, 3)
        theme.dotted(old, a, b, C.os, 7, 2)
pygame.draw.circle(old, C.braise, (int(v0[0]), int(v0[1])), 7)
old_clean = old.copy()
panel(old, "Aujourd'hui : la carte en cases", [
    ("Le sol est une case (1 536 x 768 sur la planète), dessinée avec une dentelure ;", C.lin),
    (f"le chemin du jeu : {n_steps} pas d'une case à sa voisine, six directions.", C.lin),
])
commun.tag(old, f"Essai · Sans grille : la même région, comme aujourd'hui (sa partie, an {st.clock.year})")
commun.save(old, f"{OUT}/sans_grille_aujourdhui.png")

side_by_side()
with open(f"{OUT}/sans_grille_mesures.json", "w", encoding="utf-8") as fh:
    json.dump(STATS, fh, ensure_ascii=False, indent=1)
for k, v in STATS.items():
    print(f"{k} : {v}")
