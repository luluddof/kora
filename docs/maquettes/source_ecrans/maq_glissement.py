"""Maquette SANS CASES : des trajets de sa bande, sur SA partie (copie),
1) comme aujourd'hui (le chemin du jeu, A* de case en case ; la bande saute
   d'un coup, une fois par semaine, au bout de sa marche) ;
2) sans cases (le meme chemin redresse - on va droit tant que ca ne coute
   pas plus, sinon on contourne - puis lisse ; la bande glisse, a la vitesse
   du sol sous elle).
Deux trajets : en terrain egal (tout droit) ; un obstacle (elle contourne :
sur une seconde sauvegarde si la premiere n'en a pas pres de sa bande).
Sort leurs images (les etapes de la marche) et une page animee (les deux
deplacements cote a cote, au rythme du jeu).
python maq_glissement.py RACINE SAUVEGARDE SORTIE [SAUVEGARDE_DU_DETOUR]"""
import base64
import io
import json
import math
import sys

import maq_commun as commun
from maq_commun import C, H, W, pygame, theme

from src.kora import partie_carte
from src.kora.bands import _water_ok, costs_of
from src.kora.globe import offset_to_xyz, project_xyz, rotate_xyz, view_params
from src.kora.layout import HUD_HEIGHT
from src.kora.look import country_color
from src.kora.path import MOVE_POINTS_PER_WEEK, astar
from src.kora.vision import is_explored
from src.kora.world import axial_to_offset, enter_cost_for, offset_to_axial, step_cost

OUT = sys.argv[3]


def use(save):
    """La partie (copie) d'ou partent les trajets : sa bande nomade, sinon
    une troupe partie de son village."""
    global st, play, r, me, WORLD, band, WATER, COSTS, COLOR, START
    st, play, r = commun.load(save, OUT)
    me = st.viewer
    WORLD = st.world
    mine = [b for b in st.bands.values() if b.tribe_id == me and b.population > 0]
    band = max(mine, key=lambda b: (not b.village, b.population))
    WATER = _water_ok(st, me)
    COSTS = costs_of(st, me)
    COLOR = country_color(st, me)
    START = axial_to_offset(band.position)
    # Les cartes d'evenement de la copie cacheraient la carte.
    from src.kora import events
    events._book(st).pending = []


def unwrap(col, ref):
    while col - ref > WORLD.width / 2:
        col -= WORLD.width
    while ref - col > WORLD.width / 2:
        col += WORLD.width
    return col


def plane(h):
    col, row = axial_to_offset(h)
    return float(unwrap(col, START[0])), float(row)


def hex_at(p):
    col = int(round(p[0])) % WORLD.width
    return offset_to_axial(col, int(round(p[1])))


def cost_at(p):
    return enter_cost_for(WORLD, hex_at(p), WATER, COSTS)


def turns(path):
    pts = [plane(h) for h in path]
    out = 0
    for a, b, c in zip(pts, pts[1:], pts[2:]):
        if (b[0] - a[0], b[1] - a[1]) != (c[0] - b[0], c[1] - b[1]):
            out += 1
    return out


def weekly_stops(start, path):
    """Ou la bande s'arrete chaque semaine (la marche du jeu : sim)."""
    pos, stops, i = start, [start], 0
    while i < len(path):
        points = MOVE_POINTS_PER_WEEK
        while i < len(path):
            cost = step_cost(WORLD, pos, path[i], WATER, COSTS)
            if cost is None or cost > points:
                break
            points -= cost
            pos = path[i]
            i += 1
        stops.append(pos)
    return stops


def cost_near(p):
    """Le cout du sol en p, ou None si l'une des cases qui l'entourent ne se
    marche pas : le chemin redresse garde une marge avec l'eau (la cote est
    dessinee deformee, il ne doit jamais sembler marcher dessus)."""
    for col in (math.floor(p[0]), math.ceil(p[0])):
        for row in (math.floor(p[1]), math.ceil(p[1])):
            if enter_cost_for(WORLD, offset_to_axial(col % WORLD.width, row), WATER, COSTS) is None:
                return None
    return cost_at(p)


def segment_cost(a, b):
    """Le cout du segment a-b, echantillonne tous les quarts de case (None :
    il passe par l'eau ou ailleurs ou l'on ne marche pas, ou la frole)."""
    n = max(1, int(math.dist(a, b) * 4))
    total = 0.0
    for k in range(n):
        t = (k + 0.5) / n
        c = cost_near((a[0] + (b[0] - a[0]) * t, a[1] + (b[1] - a[1]) * t))
        if c is None:
            return None
        total += c * math.dist(a, b) / n
    return total


def path_cost(pts):
    return sum(cost_at(b) * math.dist(a, b) for a, b in zip(pts, pts[1:]))


def straighten(pts):
    """Le chemin redresse : depuis chaque point, le plus loin qu'on puisse
    viser en ligne droite sans payer plus que le chemin des cases (sinon on
    garde le detour : l'eau, la montagne, la foret epaisse)."""
    acc = [0.0]
    for a, b in zip(pts, pts[1:]):
        acc.append(acc[-1] + cost_at(b) * math.dist(a, b))
    out, i = [pts[0]], 0
    while i < len(pts) - 1:
        j = i + 1
        for k in range(len(pts) - 1, i + 1, -1):
            c = segment_cost(pts[i], pts[k])
            if c is not None and c <= (acc[k] - acc[i]) * 1.02:
                j = k
                break
        out.append(pts[j])
        i = j
    return out


def chaikin(pts, passes=3):
    for _ in range(passes):
        nxt = [pts[0]]
        for a, b in zip(pts, pts[1:]):
            nxt.append((a[0] * 0.75 + b[0] * 0.25, a[1] * 0.75 + b[1] * 0.25))
            nxt.append((a[0] * 0.25 + b[0] * 0.75, a[1] * 0.25 + b[1] * 0.75))
        nxt.append(pts[-1])
        pts = nxt
    return pts


def resample(pts):
    """Points tous les dixiemes de case, chacun avec le cout cumule (le
    temps de marche : la bande glisse a la vitesse du sol sous elle)."""
    out, spent = [(pts[0], 0.0)], 0.0
    for a, b in zip(pts, pts[1:]):
        n = max(1, int(math.dist(a, b) * 10))
        for k in range(1, n + 1):
            t = k / n
            p = (a[0] + (b[0] - a[0]) * t, a[1] + (b[1] - a[1]) * t)
            spent += (cost_at(p) or 10) * math.dist(a, b) / n
            out.append((p, spent))
    return out


def deviation(pts):
    """L'ecart le plus grand (en cases) entre un trajet et la ligne droite."""
    a, b = pts[0], pts[-1]
    length = math.dist(a, b) or 1.0
    return max(abs((b[0] - a[0]) * (a[1] - p[1]) - (a[0] - p[0]) * (b[1] - a[1])) / length for p in pts)


def pick_detour():
    """Un depart et un but, dans ce qu'il a explore (autour de sa bande, a
    40 cases au plus), que l'eau ou le relief separent : le chemin du jeu
    fait le plus long detour par rapport a la distance (lac, cretes)."""
    global START
    best, best_key = None, None
    land = [h for h in WORLD.hexes_in_radius(band.position, 40)
            if (h.q % 6, h.r % 6) == (0, 0) and is_explored(st, h, me) and enter_cost_for(WORLD, h, WATER, COSTS) is not None]
    for a in land:
        for b in WORLD.hexes_in_radius(a, 14):
            d = WORLD.distance(a, b)
            if d < 10 or (b.q % 3, b.r % 3) != (0, 0) or not is_explored(st, b, me) or enter_cost_for(WORLD, b, WATER, COSTS) is None:
                continue
            path = astar(WORLD, a, b, water_ok=WATER, costs=COSTS, max_nodes=3000)
            if not path or len(path) > 2.5 * d or sum(1 for x in path if is_explored(st, x, me)) < 0.9 * len(path):
                continue
            centers = [plane(a)] + [plane(x) for x in path]
            straight = segment_cost(centers[0], centers[-1])
            if straight is not None and straight < path_cost(centers) * 1.15:
                # La ligne droite passe, et a bon prix : pas d'obstacle.
                continue
            key = (round(deviation(chaikin(straighten(centers))), 1), -len(path), a.q, a.r, b.q, b.r)
            if best_key is None or key > best_key:
                best, best_key = (a, b, path), key
    START = axial_to_offset(best[0])
    return best


def pick_target(mode):
    """"droit" : un but a 12-16 cases, dans ce qu'il a explore, que le
    chemin du jeu atteint en tournant le plus (l'escalier des cases) ;
    "detour" : pick_detour."""
    if mode == "detour":
        return pick_detour()
    best, best_key = None, None
    for h in WORLD.hexes_in_radius(band.position, 16):
        d = WORLD.distance(h, band.position)
        if d < 12 or enter_cost_for(WORLD, h, WATER, COSTS) is None or not is_explored(st, h, me):
            continue
        path = astar(WORLD, band.position, h, water_ok=WATER, costs=COSTS, max_nodes=12000)
        if not path or sum(1 for x in path if is_explored(st, x, me)) < 0.85 * len(path):
            continue
        key = (turns(path) / len(path), len(path), h.q, h.r)
        if best_key is None or key > best_key:
            best, best_key = (band.position, h, path), key
    return best


def cam():
    gcx, gcy, focal, dist = view_params(play.zoom, W, H, HUD_HEIGHT)
    return play.globe_yaw, play.globe_pitch, gcx, gcy, focal, dist


def screen(p, c=None):
    c = c or cam()
    x, y, z = offset_to_xyz(p[0], p[1], WORLD.width, WORLD.height)
    s = project_xyz(*rotate_xyz(x, y, z, c[0], c[1]), *c[2:])
    return None if s is None else (s[0], s[1])


def token(surf, p, alpha=255, radius=11):
    layer = pygame.Surface((radius * 4, radius * 4), pygame.SRCALPHA)
    c = radius * 2
    pygame.draw.circle(layer, (0, 0, 0, alpha), (c + 1, c + 2), radius + 1)
    pygame.draw.circle(layer, (*theme._mix(COLOR, (0, 0, 0), 0.45), alpha), (c, c), radius + 1)
    pygame.draw.circle(layer, (*COLOR, alpha), (c, c), radius)
    hi = tuple(min(255, int(v + (255 - v) * 0.45)) for v in COLOR)
    pygame.draw.circle(layer, (*hi, alpha), (c - radius // 3, c - radius // 3), max(1, radius // 3))
    surf.blit(layer, (int(p[0]) - c, int(p[1]) - c))


def label(surf, p, text, color=C.os):
    f = theme.font("mini_gras")
    img = f.render(text, True, color)
    back = f.render(text, True, C.nuit)
    for dx, dy in ((1, 1), (-1, 1), (1, -1), (-1, -1)):
        surf.blit(back, (int(p[0]) + 14 + dx, int(p[1]) - 22 + dy))
    surf.blit(img, (int(p[0]) + 14, int(p[1]) - 22))


def panel(surf, title, lines):
    box = (16, HUD_HEIGHT + 14, 470, 34 + 22 * len(lines))
    theme.panel(surf, box, "infobulle")
    theme.text(surf, title, "petit_gras", C.os, (box[0] + 16, box[1] + 10))
    for i, (text, col) in enumerate(lines):
        theme.text(surf, text, "mini", col, (box[0] + 16, box[1] + 36 + 22 * i), box[2] - 30)


class Trip:
    """Un trajet : le chemin du jeu, ses arrets de chaque semaine, le meme
    redresse et lisse, la vue qui le montre."""

    def __init__(self, mode):
        self.mode = mode
        self.start, self.target, self.path = pick_target(mode)
        self.stops = weekly_stops(self.start, self.path)
        self.centers = [plane(self.start)] + [plane(h) for h in self.path]
        self.smooth = chaikin(straighten(self.centers))
        self.glide = resample(self.smooth)
        self.weeks = len(self.stops) - 1
        print(mode, ": but a", WORLD.distance(self.target, self.start), "cases ;", len(self.path), "pas ;",
              turns(self.path), "virages ;", self.weeks, "semaines ; ecart a la ligne droite",
              round(deviation(self.smooth), 1), "cases")
        pts = self.centers + [p for p, _c in self.glide]
        mid = hex_at(((min(p[0] for p in pts) + max(p[0] for p in pts)) / 2, (min(p[1] for p in pts) + max(p[1] for p in pts)) / 2))
        play.globe_yaw, play.globe_pitch = partie_carte.look_hex(st, mid)
        play.selected = None
        # Le zoom : le trajet tient dans la moitie de l'ecran.
        for z in [x / 4 for x in range(48, 4, -1)]:
            play.zoom = z
            spots = [screen(p) for p in pts]
            if all(spots):
                xs, ys = [p[0] for p in spots], [p[1] for p in spots]
                if max(xs) - min(xs) < W * 0.5 and max(ys) - min(ys) < (H - HUD_HEIGHT) * 0.62:
                    break
        saved_pop = band.population
        band.population = 0
        self.base = commun.backdrop(play, r).copy()
        band.population = saved_pop
        self.cam = cam()

    def at_cost(self, spent):
        g = self.glide
        for (p, c), (q, d) in zip(g, g[1:]):
            if d >= spent:
                t = 0.0 if d == c else (spent - c) / (d - c)
                return (p[0] + (q[0] - p[0]) * t, p[1] + (q[1] - p[1]) * t)
        return g[-1][0]

    def today(self, name, where):
        s = self.base.copy()
        pts = [screen(p, self.cam) for p in self.centers]
        for a, b in zip(pts, pts[1:]):
            theme.dotted(s, a, b, C.nuit, 7, 3)
            theme.dotted(s, a, b, C.os, 7, 2)
        for p in pts:
            pygame.draw.circle(s, C.os, (int(p[0]), int(p[1])), 2)
        stop_pts = [screen(plane(h), self.cam) for h in self.stops]
        for a, b in zip(stop_pts, stop_pts[1:]):
            # Le saut de la semaine : une fleche courbe au-dessus du chemin.
            mx, my = (a[0] + b[0]) / 2, (a[1] + b[1]) / 2 - 26
            arc = [(a[0] + (mx - a[0]) * t * 2, a[1] + (my - a[1]) * t * 2) if t <= 0.5 else
                   (mx + (b[0] - mx) * (t - 0.5) * 2, my + (b[1] - my) * (t - 0.5) * 2) for t in [i / 12 for i in range(13)]]
            pygame.draw.lines(s, C.braise, False, [(int(x), int(y)) for x, y in chaikin(arc, 2)], 2)
        for k, p in enumerate(stop_pts):
            token(s, p, 255 if k in (0, len(stop_pts) - 1) else 150)
            label(s, p, "départ" if k == 0 else f"sem. {k}", C.braise if k else C.os)
        panel(s, "Aujourd'hui : de case en case", [
            (f"Le chemin du jeu : {len(self.path)} pas d'une case à sa voisine, six directions seulement ;", C.lin),
            (f"il tourne {turns(self.path)} fois en escalier.", C.lin),
            (f"La bande ne bouge qu'une fois par semaine : {self.weeks} sauts de 2 à 4 cases.", C.braise),
        ])
        commun.tag(s, f"Maquette · Sans cases : {where}, comme aujourd'hui (sa partie, an {st.clock.year})")
        commun.save(s, f"{OUT}/{name}_aujourdhui.png")

    def without(self, name, where, lines):
        s = self.base.copy()
        pts = [screen(p, self.cam) for p, _c in self.glide]
        glow = pygame.Surface((W, H), pygame.SRCALPHA)
        pygame.draw.lines(glow, (*C.ocre_jaune, 70), False, [(int(x), int(y)) for x, y in pts], 9)
        s.blit(glow, (0, 0))
        pygame.draw.aalines(s, C.os, False, pts)
        total = self.glide[-1][1]
        steps = int(self.weeks * 6)
        for k in range(steps + 1):
            token(s, screen(self.at_cost(min(total, total * k / steps)), self.cam), 40 + int(150 * k / steps), 9)
        for k in range(1, self.weeks + 1):
            p = screen(self.at_cost(min(total, MOVE_POINTS_PER_WEEK * k)), self.cam)
            pygame.draw.circle(s, C.braise, (int(p[0]), int(p[1])), 4)
            label(s, p, f"sem. {k}", C.braise)
        token(s, screen(self.glide[0][0], self.cam))
        token(s, screen(self.glide[-1][0], self.cam))
        panel(s, "Sans cases : la bande glisse", lines)
        commun.tag(s, f"Maquette · Sans cases : {where}, glissé (sa partie, an {st.clock.year})")
        commun.save(s, f"{OUT}/{name}_sans_cases.png")

    def data(self, title, text):
        buf = io.BytesIO()
        pygame.image.save(self.base, buf, "map.png")
        hexes = [screen(p, self.cam) for p in self.centers]
        glide = [[round(x, 1), round(y, 1), round(c / MOVE_POINTS_PER_WEEK, 4)] for (x, y), c in
                 ((screen(p, self.cam), c) for p, c in self.glide)]
        xs = [p[0] for p in hexes] + [g[0] for g in glide]
        ys = [p[1] for p in hexes] + [g[1] for g in glide]
        crop = [max(0, int(min(xs)) - 140), max(HUD_HEIGHT, int(min(ys)) - 110), 0, 0]
        crop[2] = min(W - crop[0], int(max(xs)) - crop[0] + 140)
        crop[3] = min(H - crop[1], int(max(ys)) - crop[1] + 110)
        return {
            "title": title, "text": text, "img": base64.b64encode(buf.getvalue()).decode(), "crop": crop,
            "hexes": hexes, "stops": [screen(plane(h), self.cam) for h in self.stops], "glide": glide,
            "weeks": self.weeks, "total": round(self.glide[-1][1] / MOVE_POINTS_PER_WEEK, 4),
            "color": "rgb(%d,%d,%d)" % COLOR,
        }


PAGE = """<!doctype html>
<html lang="fr"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>Sans cases</title>
<style>
:root { --fond:#16110d; --panneau:#241a13; --bord:#6b4a2a; --os:#efe3c8; --lin:#cdbb98; --braise:#e2803f; --ocre:#d9a441; }
body { margin:0; background:var(--fond); color:var(--os); font-family: Georgia, serif; }
main { max-width: 1500px; margin: 0 auto; padding: 16px; }
h1 { font-size: 22px; margin: 4px 0 6px; color: var(--ocre); }
h2 { font-size: 18px; margin: 22px 0 4px; color: var(--ocre); }
p { color: var(--lin); margin: 4px 0 12px; font-size: 14px; max-width: 980px; }
.duo { display:flex; gap:14px; flex-wrap:wrap; }
figure { margin:0; flex:1 1 560px; background:var(--panneau); border:1px solid var(--bord); border-radius:6px; padding:10px; }
figcaption { font-size:15px; margin-bottom:8px; }
figcaption b { color: var(--braise); }
canvas { width:100%; height:auto; border-radius:4px; display:block; }
.barre { display:flex; gap:8px; align-items:center; margin:12px 0; flex-wrap:wrap; position: sticky; top: 0; background: var(--fond); padding: 6px 0; z-index: 2; }
button { background:#3a2818; color:var(--os); border:1px solid var(--bord); border-radius:4px; padding:5px 12px; font: inherit; cursor:pointer; }
button.on { background: var(--braise); color:#1a120c; }
.semaine { color: var(--ocre); font-size: 14px; margin-left: 6px; }
</style></head><body><main>
<h1>Sans cases : la même marche, deux façons de bouger</h1>
<p>Sur votre partie (copie), votre bande va au même endroit. À gauche, comme aujourd'hui : le chemin du jeu, de case en
case, et un saut par semaine. À droite, sans cases : le même chemin redressé et lissé ; la bande glisse à chaque image,
plus vite en plaine, plus lentement là où le sol coûte. Les semaines tombent aux mêmes endroits.</p>
<div class="barre"><span>Vitesse :</span>
<button data-v="1" class="on">1</button><button data-v="2">2</button><button data-v="3">3</button>
<button data-v="4">4</button><button data-v="5">5</button>
<button id="pause">Pause</button><button id="rejouer">Rejouer</button></div>
<div id="trajets"></div>
</main>
<script>
const TRIPS = __DATA__;
let weeksPerSecond = 2, t = 0, paused = false, last = null;
document.querySelectorAll('[data-v]').forEach(b => b.onclick = () => {
  weeksPerSecond = 2 * Number(b.dataset.v);
  document.querySelectorAll('[data-v]').forEach(x => x.classList.toggle('on', x === b));
});
document.getElementById('pause').onclick = e => { paused = !paused; e.target.textContent = paused ? 'Reprendre' : 'Pause'; };
document.getElementById('rejouer').onclick = () => { t = 0; };
const root = document.getElementById('trajets');
TRIPS.forEach((D, n) => {
  const sec = document.createElement('section');
  sec.innerHTML = `<h2>${n + 1}. ${D.title}<span class="semaine"></span></h2><p>${D.text}</p><div class="duo">
    <figure><figcaption><b>Aujourd'hui</b> : de case en case, un saut par semaine</figcaption><canvas></canvas></figure>
    <figure><figcaption><b>Sans cases</b> : elle glisse</figcaption><canvas></canvas></figure></div>`;
  root.appendChild(sec);
  D.canvases = sec.querySelectorAll('canvas');
  D.label = sec.querySelector('.semaine');
  const [cx, cy, cw, ch] = D.crop;
  D.canvases.forEach(c => { c.width = cw; c.height = ch; });
  D.image = new Image(); D.image.src = 'data:image/png;base64,' + D.img;
});
function token(g, x, y, color) {
  g.fillStyle = 'rgba(0,0,0,.8)'; g.beginPath(); g.arc(x + 1, y + 2, 12, 0, 7); g.fill();
  g.fillStyle = color; g.beginPath(); g.arc(x, y, 11, 0, 7); g.fill();
  g.strokeStyle = '#140e0a'; g.lineWidth = 1.5; g.stroke();
  g.fillStyle = 'rgba(255,255,255,.45)'; g.beginPath(); g.arc(x - 4, y - 4, 4, 0, 7); g.fill();
}
function at(D, w) {
  const G = D.glide;
  for (let i = 1; i < G.length; i++) if (G[i][2] >= w) {
    const a = G[i - 1], b = G[i], k = b[2] === a[2] ? 0 : (w - a[2]) / (b[2] - a[2]);
    return [a[0] + (b[0] - a[0]) * k, a[1] + (b[1] - a[1]) * k];
  }
  return [G[G.length - 1][0], G[G.length - 1][1]];
}
function draw(D) {
  if (!D.image.complete) return;
  const [cx, cy, cw, ch] = D.crop;
  const w = Math.min(t % (D.weeks + 1.5), D.weeks);
  const [ca, cb] = D.canvases;
  const ga = ca.getContext('2d'), gb = cb.getContext('2d');
  for (const g of [ga, gb]) { g.setTransform(1, 0, 0, 1, 0, 0); g.drawImage(D.image, cx, cy, cw, ch, 0, 0, cw, ch); g.translate(-cx, -cy); }
  ga.setLineDash([5, 6]); ga.strokeStyle = 'rgba(239,227,200,.85)'; ga.lineWidth = 2; ga.beginPath();
  D.hexes.forEach((p, i) => i ? ga.lineTo(p[0], p[1]) : ga.moveTo(p[0], p[1])); ga.stroke(); ga.setLineDash([]);
  const k = Math.min(D.stops.length - 1, Math.floor(w + 1e-9));
  token(ga, D.stops[k][0], D.stops[k][1], D.color);
  gb.strokeStyle = 'rgba(217,164,65,.35)'; gb.lineWidth = 7; gb.beginPath();
  D.glide.forEach((p, i) => i ? gb.lineTo(p[0], p[1]) : gb.moveTo(p[0], p[1])); gb.stroke();
  gb.strokeStyle = 'rgba(239,227,200,.9)'; gb.lineWidth = 1.5; gb.stroke();
  const p = at(D, Math.min(w, D.total));
  token(gb, p[0], p[1], D.color);
  D.label.textContent = ' · semaine ' + Math.min(D.weeks, Math.floor(w) + 1) + ' / ' + D.weeks;
}
function frame(now) {
  if (last !== null && !paused) t += (now - last) / 1000 * weeksPerSecond;
  last = now;
  if (t > 1000) t = 0;
  TRIPS.forEach(draw);
  requestAnimationFrame(frame);
}
requestAnimationFrame(frame);
</script></body></html>
"""

use(sys.argv[2])
straight = Trip("droit")
straight.today("glissement", "en terrain égal")
straight.without("glissement", "en terrain égal", [
    ("Le même chemin, redressé : ici le sol est égal, la ligne droite ne coûte pas plus ;", C.lin),
    ("la bande avance à chaque image, plus vite en plaine, plus lentement en forêt.", C.lin),
    ("Même durée qu'aujourd'hui, mêmes semaines.", C.bon),
])
if len(sys.argv) > 4:
    use(sys.argv[4])
detour = Trip("detour")
detour.today("contournement", "un obstacle")
detour.without("contournement", "un obstacle", [
    ("Pas en ligne droite : le chemin suit le sol. Il va droit quand ça ne coûte pas", C.lin),
    ("plus ; sinon il contourne (l'eau, le relief, la forêt épaisse), en courbe,", C.lin),
    ("et la bande ralentit là où le sol coûte. Mêmes semaines qu'aujourd'hui.", C.bon),
])
trips = [
    straight.data("En terrain égal : tout droit",
                  "Le chemin du jeu fait un escalier (six directions) ; sans cases, rien n'oblige à tourner : la bande va droit."),
    detour.data("Un obstacle : elle contourne",
                "La ligne droite passe par un sol qui coûte trop (ou ne se traverse pas) : sans cases, la bande contourne en courbe, "
                "là où le chemin du jeu contourne en escalier."),
]
with open(f"{OUT}/glissement.html", "w", encoding="utf-8") as fh:
    fh.write(PAGE.replace("__DATA__", json.dumps(trips)))
print("page :", f"{OUT}/glissement.html")
