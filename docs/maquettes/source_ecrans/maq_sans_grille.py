"""Essai SANS GRILLE sur SA partie (copie) : des regions de sa planete
decrites en FORMES coherentes (formes.py : le rivage d'abord, les sols dans
les terres, la plage collee au rivage, les rivieres jusqu'a l'eau), a cote
de la carte d'aujourd'hui (des cases).
  - autour de son village : en plus, un chemin sans case (un nuage de points
    de passage, un A*, puis redresse) ;
  - trois autres regions de sa planete, choisies d'apres leurs sols
    (montagnes, marais et deltas, iles) : le brouillard y est leve sur la
    copie, le temps de l'image.
Sort pour chaque region une image cote a cote et les mesures (coherence,
temps) dans sans_grille_mesures.json.
python maq_sans_grille.py RACINE SAUVEGARDE SORTIE"""
import heapq
import json
import math
import random
import sys
import time
from collections import Counter

import numpy as np

import maq_commun as commun
from maq_commun import C, H, W, pygame, theme

from src.kora import events, formes, partie_carte
from src.kora.globe import offset_to_xyz, project_xyz, rotate_xyz, view_params
from src.kora.layout import HUD_HEIGHT
from src.kora.look import season_color
from src.kora.path import astar
from src.kora.types import Terrain
from src.kora.vision import vision_of
from src.kora.world import axial_to_offset, enter_cost_for, offset_to_axial

st, play, r = commun.load(sys.argv[2], sys.argv[3])
OUT = sys.argv[3]
me = st.viewer
WORLD = st.world
events._book(st).pending = []
home = max((b for b in st.bands.values() if b.tribe_id == me), key=lambda b: (b.village is not None, b.population))
HC, HR = axial_to_offset(home.position)
WIN_W, WIN_H = 141, 89
SEASON = st.clock.season()
SEA = season_color(Terrain.EAU, SEASON)
SAND = season_color(Terrain.COTE, SEASON)
RIVER = (62, 118, 196)
REPORT: dict = {}


def regions():
    """Son village, puis des regions variees de sa planete."""
    out = {"son village": (HC, HR)}
    best: dict = {}
    for row in range(120, WORLD.height - 120, 40):
        for col in range(0, WORLD.width, 60):
            cnt = Counter(WORLD._terrains[rr][cc % WORLD.width] for rr in range(row - 20, row + 20, 3) for cc in range(col - 30, col + 30, 3))
            # Les iles : plusieurs terres separees par la mer (sur un echantillon).
            sample = np.array([[WORLD._terrains[rr][cc % WORLD.width] is not Terrain.EAU for cc in range(col - 30, col + 30, 2)]
                               for rr in range(row - 20, row + 20, 2)])
            islands = sum(1 for part in formes._components(sample) if len(part) >= 3) if 0.15 < sample.mean() < 0.5 else 0
            for key, score in (
                ("montagnes", cnt[Terrain.MONTAGNE] + cnt[Terrain.SOMMET]),
                ("marais et deltas", cnt[Terrain.MARAIS]),
                ("iles", islands),
            ):
                if key not in best or score > best[key][0]:
                    best[key] = (score, (col, row))
    for key, (_s, pos) in best.items():
        out[key] = pos
    return out


class View:
    """La camera posee sur une region, et la projection d'un point de la
    fenetre des formes."""

    def __init__(self, shapes, center):
        self.sh = shapes
        play.globe_yaw, play.globe_pitch = partie_carte.look_hex(st, offset_to_axial(center[0] % WORLD.width, center[1]))
        play.selected = None
        # Le zoom : la fenetre deborde un peu de l'ecran (pas de bord vide).
        for z in [x / 8 for x in range(8, 120)]:
            play.zoom = z
            self.cam = (play.globe_yaw, play.globe_pitch, *view_params(play.zoom, W, H, HUD_HEIGHT))
            a, b = self.screen((10, shapes.height / 2)), self.screen((shapes.width - 10, shapes.height / 2))
            if a and b and b[0] - a[0] > W * 1.05:
                break
        p, q = self.screen((50, 40)), self.screen((51, 40))
        self.cell_px = math.dist(p, q) if p and q else 10.0

    def screen(self, p):
        c = self.cam
        x, y, z = offset_to_xyz(p[0] + self.sh.col0, p[1] + self.sh.row0, WORLD.width, WORLD.height)
        s = project_xyz(*rotate_xyz(x, y, z, c[0], c[1]), *c[2:])
        return None if s is None else (s[0], s[1])

    def poly(self, loop):
        pts = [self.screen(p) for p in loop]
        return None if any(p is None for p in pts) else pts


def reveal(shapes):
    """Leve le brouillard de la copie sur la fenetre (le temps de l'image)."""
    vis = vision_of(st, me)
    if vis is None:
        return
    cells = {offset_to_axial((shapes.col0 + j) % WORLD.width, shapes.row0 + i) for i in range(shapes.height) for j in range(shapes.width)}
    vis.explored |= cells
    vis.visible = set(vis.visible) | cells


def today_image():
    saved = home.population
    home.population = 0
    r.map_mode = "relief"
    img = commun.backdrop(play, r).copy()
    home.population = saved
    return img


def shapes_image(view, today, fog):
    """La carte en formes : les sols, la plage, les rivieres, puis l'eau
    par-dessus (le masque du rivage) et le trait de cote."""
    sh = view.sh
    land_layer = pygame.Surface((W, H))
    land_layer.fill(season_color(Terrain.PLAINE, SEASON))
    for k, loop in sorted(sh.soils, key=lambda kl: -abs(formes.area(kl[1]))):
        if formes.area(loop) <= 0:
            continue
        pts = view.poly(loop)
        if pts:
            pygame.draw.polygon(land_layer, season_color(formes.TERR[k], SEASON), pts)
    for line in sh.beaches:
        pts = [view.screen(p) for p in line]
        pts = [p for p in pts if p]
        if len(pts) >= 2:
            w = max(2, int(2 * formes.BEACH_WIDTH * view.cell_px))
            pygame.draw.lines(land_layer, SAND, False, pts, w)
            for p in pts:
                pygame.draw.circle(land_layer, SAND, (int(p[0]), int(p[1])), w // 2)
    for size, line in sh.rivers:
        pts = [view.screen(p) for p in line]
        pts = [p for p in pts if p]
        if len(pts) >= 2:
            pygame.draw.lines(land_layer, RIVER, False, pts, max(1, int((0.12 + 0.1 * size) * view.cell_px)))
    # Le masque de la terre : les boucles du rivage, des plus grandes aux
    # plus petites (une ile dans un lac dans une ile...).
    mask = pygame.Surface((W, H))
    mask.fill((0, 0, 0))
    for loop in sorted(sh.coast, key=lambda lp: -abs(formes.area(lp))):
        pts = view.poly(loop)
        if pts:
            pygame.draw.polygon(mask, (255, 255, 255) if formes.area(loop) > 0 else (0, 0, 0), pts)
    land_only = land_layer.copy()
    land_only.blit(mask, (0, 0), special_flags=pygame.BLEND_RGB_MIN)
    out = pygame.Surface((W, H))
    out.fill(SEA)
    a_land = pygame.surfarray.pixels3d(land_only)
    a_mask = pygame.surfarray.pixels3d(mask)
    a_out = pygame.surfarray.pixels3d(out)
    on = a_mask[:, :, 0] > 0
    a_out[on] = a_land[on]
    del a_land, a_mask, a_out
    for loop in sh.coast:
        pts = view.poly(loop)
        if pts:
            pygame.draw.aalines(out, theme._mix(SEA, (255, 255, 255), 0.3), True, pts)
    if fog:
        a_today = pygame.surfarray.pixels3d(today)
        unseen = a_today.max(axis=2) < 16
        a_out = pygame.surfarray.pixels3d(out)
        a_out[unseen] = a_today[unseen]
        del a_today, a_out
    out.blit(today, (0, 0), (0, 0, W, HUD_HEIGHT))
    return out


def path_on(shapes):
    """Un chemin sans case : un nuage de points de passage (au hasard, a au
    moins 0,9 case les uns des autres), relies a leurs voisins (le cout du
    sol le long), un A*, puis le chemin redresse et lisse."""
    stats = {}
    t = time.perf_counter()
    spacing, cell = 0.9, 0.9 / math.sqrt(2)
    rnd = random.Random(11)
    first = (float(HC - shapes.col0), float(HR - shapes.row0))
    pts, grid, active = [first], {(int(first[0] / cell), int(first[1] / cell)): 0}, [first]
    while active:
        i = rnd.randrange(len(active))
        px, py = active[i]
        for _ in range(12):
            ang, rad = rnd.uniform(0, 2 * math.pi), rnd.uniform(spacing, 2 * spacing)
            x, y = px + rad * math.cos(ang), py + rad * math.sin(ang)
            if not (0 <= x < shapes.width - 1 and 0 <= y < shapes.height - 1):
                continue
            gx, gy = int(x / cell), int(y / cell)
            near = (grid.get((ax, ay)) for ax in range(gx - 2, gx + 3) for ay in range(gy - 2, gy + 3))
            if any(k is not None and math.dist(pts[k], (x, y)) < spacing for k in near):
                continue
            grid[(gx, gy)] = len(pts)
            pts.append((x, y))
            active.append((x, y))
            break
        else:
            active.pop(i)
    land = [i for i, p in enumerate(pts) if shapes.cost_at(*p) is not None]
    stats["points de passage"] = len(land)
    bucket: dict = {}
    for i in land:
        bucket.setdefault((int(pts[i][0] / 2), int(pts[i][1] / 2)), []).append(i)
    adj = {i: [] for i in land}
    for i in land:
        x, y = pts[i]
        for ax in range(int(x / 2) - 1, int(x / 2) + 2):
            for ay in range(int(y / 2) - 1, int(y / 2) + 2):
                for j in bucket.get((ax, ay), ()):
                    if j <= i or math.dist(pts[i], pts[j]) > 2.0:
                        continue
                    cs = [shapes.cost_at(x + (pts[j][0] - x) * k, y + (pts[j][1] - y) * k) for k in (0.25, 0.5, 0.75)]
                    if None in cs:
                        continue
                    w = math.dist(pts[i], pts[j]) * sum(cs) / 3
                    adj[i].append((j, w))
                    adj[j].append((i, w))
    stats["liens"] = sum(len(v) for v in adj.values()) // 2
    stats["nuage et liens (s)"] = round(time.perf_counter() - t, 2)

    def search(s, g):
        openq, best, came, seq = [(0.0, 0, s)], {s: 0.0}, {}, 0
        while openq:
            _f, _q, u = heapq.heappop(openq)
            if u == g:
                out = [u]
                while u in came:
                    u = came[u]
                    out.append(u)
                return out[::-1]
            for v, w in adj[u]:
                nd = best[u] + w
                if nd < best.get(v, 1e18):
                    best[v], came[v], seq = nd, u, seq + 1
                    heapq.heappush(openq, (nd + 10 * math.dist(pts[v], pts[g]), seq, v))
        return None

    def seg(a, b):
        n = max(1, int(math.dist(a, b) * 4))
        tot = 0.0
        for k in range(n):
            c = shapes.cost_at(a[0] + (b[0] - a[0]) * (k + 0.5) / n, a[1] + (b[1] - a[1]) * (k + 0.5) / n)
            if c is None:
                return None
            tot += c * math.dist(a, b) / n
        return tot

    start = min(land, key=lambda i: math.dist(pts[i], first))
    cands = [i for i in land if 18 <= math.dist(pts[i], pts[start]) <= 34]
    rnd.shuffle(cands)
    best = None
    for g in cands[:300]:
        route = search(start, g)
        if route:
            line = [pts[i] for i in route]
            ratio = sum(math.dist(a, b) for a, b in zip(line, line[1:])) / math.dist(line[0], line[-1])
            if ratio < 2.2 and (best is None or ratio > best[0]):
                best = (ratio, g)
    t = time.perf_counter()
    line = [pts[i] for i in search(start, best[1])]
    stats["A* (ms)"] = round(1000 * (time.perf_counter() - t), 2)
    acc = [0.0]
    for a, b in zip(line, line[1:]):
        acc.append(acc[-1] + (seg(a, b) or 1e9))
    out, i = [line[0]], 0
    while i < len(line) - 1:
        j = i + 1
        for k in range(len(line) - 1, i + 1, -1):
            c = seg(line[i], line[k])
            if c is not None and c <= (acc[k] - acc[i]) * 1.02:
                j = k
                break
        out.append(line[j])
        i = j
    smooth = formes.chaikin(out, 3, closed=False)
    gx, gy = line[-1]
    goal = offset_to_axial(int(round(gx + shapes.col0)) % WORLD.width, int(round(gy + shapes.row0)))
    hex_path = astar(WORLD, home.position, goal, max_nodes=20000) if enter_cost_for(WORLD, goal, False) else None
    stats["chemin sans case (cases)"] = round(sum(math.dist(a, b) for a, b in zip(smooth, smooth[1:])), 1)
    stats["chemin d'aujourd'hui (pas)"] = len(hex_path) if hex_path else None
    return smooth, hex_path, stats


def draw_line(surf, view, line, dotted=False):
    pts = [view.screen(p) for p in line]
    pts = [p for p in pts if p]
    if dotted:
        for a, b in zip(pts, pts[1:]):
            theme.dotted(surf, a, b, C.nuit, 7, 3)
            theme.dotted(surf, a, b, C.os, 7, 2)
        return
    glow = pygame.Surface((W, H), pygame.SRCALPHA)
    pygame.draw.lines(glow, (*C.ocre_jaune, 90), False, [(int(x), int(y)) for x, y in pts], 9)
    surf.blit(glow, (0, 0))
    pygame.draw.aalines(surf, C.os, False, pts)


def side_by_side(name, title, left, right):
    half = W // 2
    x0 = W // 4
    out = pygame.Surface((W, H))
    out.blit(left, (0, 0), (x0, 0, half, H))
    out.blit(right, (half, 0), (x0, 0, half, H))
    pygame.draw.line(out, C.ocre, (half, HUD_HEIGHT), (half, H), 3)
    for x, text in ((16, "Aujourd'hui : des cases"), (half + 16, "Sans grille : des formes")):
        theme.panel(out, (x, H - 64, 300, 40), "infobulle")
        theme.text(out, text, "petit_gras", C.os, (x + 14, H - 56))
    theme.panel(out, (16, HUD_HEIGHT + 12, 600, 40), "infobulle")
    theme.text(out, title, "petit_gras", C.os, (30, HUD_HEIGHT + 20))
    commun.save(out, f"{OUT}/sans_grille_{name}.png")


FILE = {"son village": "village", "montagnes": "montagnes", "marais et deltas": "deltas", "iles": "iles"}
TITLES = {"son village": f"Autour de son village (sa partie, an {st.clock.year}), et un chemin",
          "montagnes": "Des montagnes de sa planète", "marais et deltas": "Des marais et des deltas de sa planète",
          "iles": "Des îles de sa planète"}
for name, center in regions().items():
    t = time.perf_counter()
    shapes = formes.build(WORLD, center[0] - WIN_W // 2, center[1] - WIN_H // 2, WIN_W, WIN_H)
    report = {"formes (s)": round(time.perf_counter() - t, 2), "regions de sol": len(shapes.soils), "boucles du rivage": len(shapes.coast),
              "plages": len(shapes.beaches), "rivieres": len(shapes.rivers), **shapes.check()}
    rnd = random.Random(3)
    t = time.perf_counter()
    for _ in range(4000):
        shapes.soil_at(rnd.uniform(0, WIN_W), rnd.uniform(0, WIN_H))
    report["quel sol ici (microsecondes)"] = round(1e6 * (time.perf_counter() - t) / 4000, 1)
    village = name == "son village"
    if not village:
        reveal(shapes)
    view = View(shapes, center)
    today = today_image()
    vec = shapes_image(view, today, fog=village)
    old = today.copy()
    if village:
        smooth, hex_path, stats = path_on(shapes)
        report.update(stats)
        draw_line(vec, view, smooth)

        def local(h):
            col, row = axial_to_offset(h)
            return ((col - shapes.col0 + WORLD.width // 2) % WORLD.width - WORLD.width // 2, row - shapes.row0)
        if hex_path:
            draw_line(old, view, [local(h) for h in [home.position] + hex_path], dotted=True)
        for surf in (old, vec):
            p = view.screen(local(home.position))
            pygame.draw.circle(surf, C.braise, (int(p[0]), int(p[1])), 7)
    REPORT[name] = report
    side_by_side(FILE[name], TITLES[name], old, vec)
    print(name, report, flush=True)

with open(f"{OUT}/sans_grille_mesures.json", "w", encoding="utf-8") as fh:
    json.dump(REPORT, fh, ensure_ascii=False, indent=1)
