"""Dessin de la planete avec numpy.

LE MONDE EN FORMES (0.27.0, le monde sans grille) : un lancer de rayons par
pixel a tous les zooms, plus aucun polygone de case. De tres loin (une case
fait moins de SHAPE_MIN_PX pixels), la case la plus proche ; plus pres, les
FORMES : chaque point vote avec les neuf centres voisins (_stencil, _vote :
l'eau, chaque sol, la plage le long du rivage, les zones d'influence) ; la
frontiere est une courbe. Ces formes sont CUITES par tuiles a la premiere
vue (_tile, au grain choisi selon le zoom, TILE_GRAINS) : la carte ne change
pas en jeu ; les saisons, le brouillard (adouci, _soft_fog) et les zones
(recuites quand l'influence change, _zone_tile) se posent par-dessus. Les
RIVIERES en traits par-dessus (draw_rivers). terrain_at : le sol de la
forme sous un point (le survol).
Memes formules que l'ancien rendu Python pur (projection, ombrage
0.34 + 0.66 z, brouillard 0.45 / 0.55) ; le cout depend de l'ecran,
plus de la taille de la carte.
"""

from __future__ import annotations

import math

import numpy as np
import pygame

from src.kora.globe import HEX_ROW_SHIFT, HEX_ROW_SQUASH, look_center, visible_hex_radius
from src.kora import globe, look
from src.kora.look import season_color
from src.kora.types import Season, Terrain
from src.kora.vision import vision_of
from src.kora.world import NEIGHBOR_DELTAS, axial_to_offset
from src.kora.resources import COLORS, NAMES
from src.kora.influence import CORE_MIN, ZONE_MIN

FOG_UNEXPLORED = (8, 8, 10)
TERRAINS = tuple(Terrain)
TERRAIN_CODE = {t: i for i, t in enumerate(TERRAINS)}
SEASONS = (Season.PRINTEMPS, Season.ETE, Season.AUTOMNE, Season.HIVER)
# LE MONDE EN FORMES (0.27.0) : plus aucun polygone de case. Chaque point de
# l'ecran regarde les neuf centres de cases autour de lui, ponderes selon sa
# distance a chacun (une cloche de largeur SHAPE_SIGMA case) : chaque sol,
# l'eau, le brouillard, les zones "votent" ; la frontiere passe la ou les
# votes s'equilibrent - une courbe, plus le bord d'un hexagone. Une case
# seule (un etang, une tache de foret) garde son coeur.
SHAPE_SIGMA = 0.5
SHAPE_CHUNK = 400_000
# La cuisson par tuiles : TILE_SUB x TILE_SUB sous-cases ; le grain (sous-cases
# par case) selon la taille d'une case a l'ecran ; combien de tuiles gardees.
TILE_SUB = 128
TILE_GRAINS = (4, 8, 16, 32, 64)
# Une sous-case ne depasse pas tant de pixels (au-dela, un escalier se voit).
TILE_PX = 1.6
TILE_PX_FAST = 4.0
TILE_CACHE = 1500
# En dessous de tant de pixels par case, la case la plus proche suffit.
SHAPE_MIN_PX = 5.0
# La plage : la terre tout pres de l'eau, la ou la planete avait de la cote.
BEACH_WATER = 0.22
BEACH_COAST = 0.2
# Les rivieres en traits des que la case fait tant de pixels a l'ecran.
RIVER_LINE_PX = 5.0
# Pixels calcules par image : peu pendant que la camera bouge, beaucoup
# une fois qu'elle s'arrete (voir Renderer._draw_sphere).
FAST_SAMPLES = 90_000
FINE_SAMPLES = 600_000
_KEY = (255, 0, 255)
_PALETTE = np.array(
    [[season_color(t, s) for t in TERRAINS] for s in SEASONS], dtype=np.float32
)
_INFLATE = 1.12
RIVER_COLOR = np.array((62, 118, 196), dtype=np.float32)
# Les rivieres de loin : la part de bleu sur la case (ruisseau, riviere, fleuve).
RIVER_TINT = np.array((0.0, 0.0, 0.55, 0.8), dtype=np.float32)


def hex_screen_px(world, focal: float, dist: float) -> float:
    """Largeur d'un hexagone (a l'equateur, au centre de l'ecran), en pixels."""
    return focal * (2.0 * math.pi / max(1, world.width)) / max(1e-3, dist - 1.0)


def _rotate(x, y, z, yaw: float, pitch: float):
    cyw, syw = math.cos(yaw), math.sin(yaw)
    cp, sp = math.cos(pitch), math.sin(pitch)
    x1 = x * cyw + z * syw
    z1 = -x * syw + z * cyw
    return x1, y * cp - z1 * sp, y * sp + z1 * cp


def _normalize(v):
    return v / np.sqrt((v * v).sum(axis=-1, keepdims=True))


class Planet:
    """Etat de dessin d'un monde : terrains, saisons, brouillard, maillage."""

    def __init__(self, world) -> None:
        self.world = world
        self.width = world.width
        self.height = world.height
        self.terr = np.array(
            [[TERRAIN_CODE[t] for t in row] for row in world._terrains], dtype=np.uint8
        )
        self.fog = np.zeros((self.height, self.width), dtype=np.uint8)
        self.fog_gen = 0
        self._fog_known_n = -1
        self._fog_known: set = set()
        self._fog_lit: set = set()
        self._fog_lit_ref = None
        self._season = np.zeros((self.height, self.width), dtype=np.uint8)
        self._season_gen = None
        self._centers = None
        self._corners = None
        self._rays: dict = {}
        # Calque "Zones" : peuple dominant de chaque case (-1 : personne),
        # opacite de la teinte (plus forte au bord et au coeur).
        self.zones_on = True
        self.realm_on = False
        # La carte des grands tournants : le tournant montre (None : autre carte).
        self.turn_pick = None
        self._zone_key = None
        self.zone_owner = np.full((self.height, self.width), -1, dtype=np.int16)
        self.zone_alpha = np.zeros((self.height, self.width), dtype=np.float32)
        # Pour les formes : le camp de la frontiere (le peuple, ou son pays sur
        # la carte des suzerains), l'opacite dedans, celle du bord.
        self.zone_group = np.full((self.height, self.width), -1, dtype=np.int16)
        self.zone_inner = np.zeros((self.height, self.width), dtype=np.float32)
        self.zone_edge = 0.36
        self.zone_colors = np.zeros((1, 3), dtype=np.float32)
        self._nb = None
        # Calque "Ressources" : couleur de la ressource la plus forte.
        self.res_on = False
        # Mode Commerce : le terrain s'efface, les routes ressortent.
        self.trade_on = False
        self._res_color = None
        self._res_alpha = None
        # Les ressources que le joueur ne reconnait pas encore (resources.hidden_for).
        self.res_hidden: frozenset = frozenset()
        self._res_key = None
        self._shape = None
        self._tiles: dict = {}
        self._zone_tiles: dict = {}
        # Les rivieres : la taille de chaque case (0 : sans riviere).
        rivers = world.rivers
        self.river_size = (
            (np.frombuffer(rivers, dtype=np.uint8).reshape(self.height, self.width) >> 3)
            if rivers else np.zeros((self.height, self.width), dtype=np.uint8)
        )

    # --- les formes ----------------------------------------------------

    def _shape_codes(self):
        """Par case : l'eau (1/0), la cote, et le SOL de la forme (une case
        de cote prend le sol de l'interieur voisin : la cote n'est pas un
        sol, c'est la plage le long du rivage ; formes.py, meme regle)."""
        if self._shape is not None:
            return self._shape
        terr = self.terr
        water_code = TERRAIN_CODE[Terrain.EAU]
        coast_code = TERRAIN_CODE[Terrain.COTE]
        water = terr == water_code
        coast = terr == coast_code
        soil = terr.copy()
        todo = coast.copy()
        for _round in range(3):
            if not todo.any():
                break
            for nr, nc in self._neighbors():
                nb = soil[nr, nc]
                ok = todo & (nb != water_code) & (nb != coast_code)
                soil[ok] = nb[ok]
                todo &= ~ok
        soil[todo] = TERRAIN_CODE[Terrain.PLAINE]
        self._shape = (water.astype(np.float32), coast.astype(np.float32), soil)
        return self._shape

    def _stencil(self, xf, yf):
        """Les neuf centres autour de chaque point : rangees, colonnes, poids
        (la cloche de SHAPE_SIGMA, normalisee)."""
        height, width = self.height, self.width
        rc = np.rint(yf).astype(np.int64)
        rows, cols, ws = [], [], []
        k = np.float32(-0.5 / (SHAPE_SIGMA * SHAPE_SIGMA))
        for drow in (-1, 0, 1):
            r = np.clip(rc + drow, 0, height - 1)
            shift = np.where(r & 1, HEX_ROW_SHIFT, -HEX_ROW_SHIFT)
            cc = np.rint(xf - shift).astype(np.int64)
            dy = (yf - r) * HEX_ROW_SQUASH
            dy2 = dy * dy
            for dcol in (-1, 0, 1):
                c = cc + dcol
                dx = xf - (c + shift)
                ws.append(np.exp((dx * dx + dy2) * k).astype(np.float32))
                rows.append(r)
                cols.append(c % width)
        w = np.stack(ws)
        w /= w.sum(axis=0, keepdims=True)
        return np.stack(rows), np.stack(cols), w

    @staticmethod
    def _vote(codes, w, ncls: int):
        """Le code qui l'emporte en chaque point, son score, et le second."""
        n = codes.shape[1]
        scores = np.zeros((n, ncls), dtype=np.float32)
        idx = np.arange(n)
        for k in range(codes.shape[0]):
            scores[idx, codes[k]] += w[k]
        win = scores.argmax(axis=1)
        top = scores[idx, win]
        scores[idx, win] = -1.0
        second = scores.max(axis=1)
        return win, top, second

    def _bake_codes(self, xf, yf):
        """Le sol de la forme (indice de TERRAINS ; l'eau ; la plage) aux
        points (xf, yf), deja deplaces par globe.warp ; et leur pochoir."""
        water, coast, soil = self._shape_codes()
        rows, cols, w = self._stencil(xf, yf)
        wet = (water[rows, cols] * w).sum(axis=0)
        sea = wet > 0.5
        land_w = w * (1.0 - water[rows, cols])
        code, _top, _second = self._vote(soil[rows, cols].astype(np.int64), land_w, len(TERRAINS))
        shore = (coast[rows, cols] * w).sum(axis=0) / np.maximum(1e-6, land_w.sum(axis=0))
        beach = (~sea) & (wet > BEACH_WATER) & (shore >= BEACH_COAST)
        code = np.where(sea, TERRAIN_CODE[Terrain.EAU], np.where(beach, TERRAIN_CODE[Terrain.COTE], code))
        return code.astype(np.uint8), rows, cols, w

    def _bake_zones(self, rows, cols, w):
        """Les zones en surfaces : le peuple qui l'emporte en chaque point et
        l'opacite de sa teinte (la frontiere la ou deux camps - ou un camp et
        personne - sont presque a egalite : une bande douce le long d'une
        courbe)."""
        owner = self.zone_owner[rows, cols]
        n = rows.shape[1]
        own = np.full(n, -1, dtype=np.int16)
        alpha = np.zeros(n, dtype=np.uint8)
        if not (owner >= 0).any():
            return own, alpha
        group = self.zone_group[rows, cols]
        uniq, compact = np.unique(group, return_inverse=True)
        _gwin, gtop, gsecond = self._vote(compact.reshape(group.shape), w, len(uniq))
        gid = uniq[_gwin]
        uo, oc = np.unique(owner, return_inverse=True)
        owin, _ot, _os = self._vote(oc.reshape(owner.shape), w, len(uo))
        win = uo[owin]
        inside = (gid >= 0) & (win >= 0)
        same = (owner == win[None, :]).astype(np.float32) * w
        inner = (self.zone_inner[rows, cols] * same).sum(axis=0) / np.maximum(1e-6, same.sum(axis=0))
        edge = (gtop - gsecond) < 0.45
        a = np.where(edge, self.zone_edge, inner)
        own[inside] = win[inside]
        alpha[inside] = np.clip(a[inside] * 255.0, 0, 255).astype(np.uint8)
        return own, alpha

    def _tile_points(self, level: int, tx: int, ty: int):
        """Les points d'une tuile (TILE_SUB x TILE_SUB sous-cases de 1/level
        case), deplaces par globe.warp."""
        n = TILE_SUB
        sub_ = (np.arange(n, dtype=np.float32) + np.float32(0.5)) / np.float32(level) - np.float32(0.5)
        xs = np.float32(tx * n / level) + sub_
        ys = np.float32(ty * n / level) + sub_
        xf, yf = np.meshgrid(xs, ys, indexing="xy")
        xf, yf = xf.ravel(), np.minimum(yf.ravel(), np.float32(self.height - 1))
        dx, dy = globe.warp(xf, yf, self.width, np.sin, np.sqrt, np.minimum)
        return (xf + dx).astype(np.float32), (yf + dy).astype(np.float32)

    def _tile(self, level: int, tx: int, ty: int) -> np.ndarray:
        """Les sols d'une tuile, cuits a la premiere vue (la carte ne change
        pas en jeu ; les saisons, le brouillard et les zones se posent par-
        dessus)."""
        key = (level, tx, ty)
        hit = self._tiles.get(key)
        if hit is not None:
            return hit
        xf, yf = self._tile_points(level, tx, ty)
        code, _r, _c, _w = self._bake_codes(xf, yf)
        if len(self._tiles) >= TILE_CACHE:
            for old in list(self._tiles)[: TILE_CACHE // 4]:
                del self._tiles[old]
        out = self._tiles[key] = code.reshape(TILE_SUB, TILE_SUB)
        return out

    def _zone_tile(self, level: int, tx: int, ty: int):
        """Les zones d'une tuile, recuites quand l'influence change."""
        key = (level, tx, ty)
        hit = self._zone_tiles.get(key)
        if hit is not None and hit[0] == self._zone_key:
            return hit[1], hit[2]
        xf, yf = self._tile_points(level, tx, ty)
        rows, cols, w = self._stencil(xf, yf)
        own, alpha = self._bake_zones(rows, cols, w)
        if len(self._zone_tiles) >= TILE_CACHE:
            for old in list(self._zone_tiles)[: TILE_CACHE // 4]:
                del self._zone_tiles[old]
        own, alpha = own.reshape(TILE_SUB, TILE_SUB), alpha.reshape(TILE_SUB, TILE_SUB)
        self._zone_tiles[key] = (self._zone_key, own, alpha)
        return own, alpha

    def _lookup(self, xf, yf, level: int, zones: bool):
        """Les sols (et les zones) cuits sous les points (xf, yf), NON
        deplaces : la tuile garde le deplacement de chaque sous-case."""
        n = TILE_SUB
        span_x = self.width * level
        sx = np.floor((xf + 0.5) * level).astype(np.int64) % span_x
        sy = np.clip(np.floor((yf + 0.5) * level).astype(np.int64), 0, self.height * level - 1)
        tx, ty = sx // n, sy // n
        ntx = -(-span_x // n)
        tid = ty * ntx + tx
        code = np.empty(len(xf), dtype=np.uint8)
        own = np.full(len(xf), -1, dtype=np.int16) if zones else None
        alpha = np.zeros(len(xf), dtype=np.uint8) if zones else None
        used = np.nonzero(np.bincount(tid))[0]
        for t in used.tolist():
            sel = tid == t
            a, b = t % ntx, t // ntx
            ly, lx = sy[sel] - b * n, sx[sel] - a * n
            code[sel] = self._tile(level, a, b)[ly, lx]
            if zones:
                zo, za = self._zone_tile(level, a, b)
                own[sel] = zo[ly, lx]
                alpha[sel] = za[ly, lx]
        return code, own, alpha

    def _soft_fog(self) -> np.ndarray:
        """Le brouillard adouci (un flou leger, refait quand il change) : pas
        de carres visibles entre ce qu'on a vu et le reste."""
        if getattr(self, "_soft_gen", None) != self.fog_gen:
            f = self.fog.astype(np.float32)
            k = np.array((0.08, 0.24, 0.36, 0.24, 0.08), dtype=np.float32)
            for axis in (0, 1):
                pad = [(0, 0), (0, 0)]
                pad[axis] = (2, 2)
                g = np.pad(f, pad, mode="wrap" if axis == 1 else "edge")
                acc = np.zeros_like(f)
                for i, w in enumerate(k):
                    acc += w * (g[i:i + f.shape[0]] if axis == 0 else g[:, i:i + f.shape[1]])
                f = acc
            self._soft = f
            self._soft_gen = self.fog_gen
        return self._soft

    def terrain_at(self, lon: float, lat: float) -> Terrain:
        """Le sol de la FORME sous un point (le survol dit ce qu'on voit, pas
        la case dessous)."""
        width, height = self.width, self.height
        xf = np.array([(lon + math.pi) * (width / (2.0 * math.pi)) - 0.5], dtype=np.float32)
        yf = np.array([(math.pi / 2.0 - lat) * ((height - 1) / math.pi)], dtype=np.float32)
        code, _o, _a = self._lookup(xf, yf, 16, False)
        return TERRAINS[int(code[0])]

    def _fog_at(self, xf, yf):
        """Le brouillard (0 a 2) entre les centres, en douceur."""
        height, width = self.height, self.width
        x0 = np.floor(xf)
        y0 = np.floor(yf)
        fx = xf - x0
        fy = yf - y0
        fx = fx * fx * (3.0 - 2.0 * fx)
        fy = fy * fy * (3.0 - 2.0 * fy)
        c0 = x0.astype(np.int64) % width
        c1 = (c0 + 1) % width
        r0 = np.clip(y0.astype(np.int64), 0, height - 1)
        r1 = np.minimum(r0 + 1, height - 1)
        f = self._soft_fog()
        top = f[r0, c0] * (1.0 - fx) + f[r0, c1] * fx
        bot = f[r1, c0] * (1.0 - fx) + f[r1, c1] * fx
        return (top * (1.0 - fy) + bot * fy).astype(np.float32)

    def _shade(self, xf, yf, level: int):
        """La couleur et le brouillard (0 a 2, doux) des points (xf, yf) non
        deplaces, au grain `level`."""
        zones = self.zones_on and not self.trade_on and not (self.res_on and self.world.resources)
        code, own, alpha = self._lookup(xf, yf, level, zones)
        height, width = self.height, self.width
        nr = np.clip(np.rint(yf).astype(np.int64), 0, height - 1)
        nc = np.rint(xf).astype(np.int64) % width
        base = _PALETTE[self.seasons()[nr, nc], code]
        fog = self._fog_at(xf, yf)
        if self.trade_on:
            grey = base.mean(axis=-1, keepdims=True)
            base = (base * 0.35 + grey * 0.65) * 0.55
        elif self.res_on and self.world.resources:
            color, ralpha = self._resources()
            a = ralpha[nr, nc][:, None]
            base = base * (0.55 * (1.0 - a)) + color[nr, nc] * a
        elif zones:
            if self.realm_on or self.turn_pick:
                grey = base.mean(axis=-1, keepdims=True)
                base = (base * 0.3 + grey * 0.7) * 0.75
            mine = own >= 0
            if mine.any():
                a = (alpha[mine].astype(np.float32) / np.float32(255.0))[:, None]
                base = base.copy()
                base[mine] = base[mine] * (1.0 - a) + self.zone_colors[own[mine]] * a
        return base, fog

    # --- saisons et brouillard ---------------------------------------

    def seasons(self) -> np.ndarray:
        world = self.world
        if self._season_gen != world._season_gen:
            rows = world._hex_season
            width = self.width
            if all(line.count(line[0]) == width for line in rows):
                first = np.fromiter((line[0] for line in rows), np.uint8, len(rows))
                self._season = np.repeat(first[:, None], width, axis=1)
            else:
                self._season = np.array(rows, dtype=np.uint8)
            self._season_gen = world._season_gen
        return self._season

    def season_gen(self) -> int:
        return self.world._season_gen

    def sync_fog(self, state) -> int:
        # 0 = inexplore, 1 = explore hors vue, 2 = en vue. Mise a jour par
        # differences : explored ne fait que grandir ; visible n'est un
        # nouvel objet que si une bande du joueur a bouge. La vue est celle
        # du joueur de cet ecran (multijoueur) ; le menu n'en a pas.
        vis = vision_of(state, state.viewer) if hasattr(state, "povs") else None
        if vis is None:
            return self.fog_gen
        fog = self.fog
        if len(vis.explored) != self._fog_known_n:
            if len(vis.explored) < self._fog_known_n:
                # Autre partie chargee sur la meme carte : on repart de zero.
                fog[:] = 0
                self._fog_known = set()
                self._fog_lit = set()
            fresh = vis.explored - self._fog_known
            if fresh:
                rows, cols = self._cells(fresh)
                seen = fog[rows, cols]
                fog[rows, cols] = np.where(seen == 0, 1, seen)
            self._fog_known = set(vis.explored)
            self._fog_known_n = len(vis.explored)
            self._fog_lit_ref = None
            self.fog_gen += 1
        if vis.visible is not self._fog_lit_ref:
            left = self._fog_lit - vis.visible
            if left:
                rows, cols = self._cells(left)
                fog[rows, cols] = 1
            if vis.visible:
                rows, cols = self._cells(vis.visible)
                fog[rows, cols] = 2
            self._fog_lit = set(vis.visible)
            self._fog_lit_ref = vis.visible
            self.fog_gen += 1
        return self.fog_gen

    def _cells(self, hexes) -> tuple[np.ndarray, np.ndarray]:
        pairs = [axial_to_offset(h) for h in hexes]
        cols = np.fromiter((c for c, _r in pairs), np.int64, len(pairs))
        rows = np.fromiter((r for _c, r in pairs), np.int64, len(pairs))
        ok = (rows >= 0) & (rows < self.height) & (cols >= 0) & (cols < self.width)
        return rows[ok], cols[ok]

    def explored_at(self, col: int, row: int) -> bool:
        return bool(self.fog[row, col])

    # --- zones d'influence -------------------------------------------

    def _neighbors(self):
        """Pour chaque direction : la rangee du voisin (une colonne, diffusee)
        et sa colonne (int32) - peu de memoire sur une grande planete."""
        if self._nb is None:
            rows = np.arange(self.height, dtype=np.int32)[:, None]
            cols = np.arange(self.width, dtype=np.int32)[None, :]

            def half(r):
                return (r - (r & 1)) // 2

            out = []
            for dq, dr in NEIGHBOR_DELTAS:
                nr = rows + dr
                nc = ((cols + dq + half(nr) - half(rows)) % self.width).astype(np.int32)
                out.append((np.clip(nr, 0, self.height - 1), nc))
            self._nb = out
        return self._nb

    def sync_zones(self, state) -> tuple:
        """Refait le calque quand l'influence a change (une fois par mois), ou
        un lien entre peuples (un tributaire prend la couleur de son pays).
        realm_on (la carte des suzerains) : seuls les pays de plusieurs
        peuples, leurs frontieres entre pays."""
        world = self.world
        tids = sorted(state.tribes)
        # Le brouillard : les zones telles que le joueur les a vues (memory.py).
        vis = vision_of(state, state.viewer) if hasattr(state, "povs") else None
        fog_key = (vis.mem_gen, id(vis.visible)) if vis is not None else None
        turn = (self.turn_pick, state.tick_count // 4) if self.turn_pick else None
        key = (getattr(world, "_influence_gen", 0), len(world._influence), tuple(tids), look._ties_key(state)[2], self.realm_on, fog_key, turn)
        if key == self._zone_key:
            return key
        self._zone_key = key
        index = {tid: i for i, tid in enumerate(tids)}
        if self.turn_pick:
            # La carte des grands tournants : chaque peuple a la couleur de
            # la presence du tournant choisi chez lui (look.turning_color).
            colors = [look.turning_color(state, t, self.turn_pick) for t in tids]
        else:
            colors = [look.country_color(state, t) for t in tids]
        self.zone_colors = np.array(colors or [(0, 0, 0)], dtype=np.float32)
        shown = None
        realm_ix = np.zeros(max(1, len(tids)), dtype=np.int16)
        if self.realm_on:
            shown = {t for _root, m in look.great_realms(state) for t in m}
            for t, i in index.items():
                realm_ix[i] = look.realm_of(state, t)
        owner = np.full((self.height, self.width), -1, dtype=np.int16)
        value = np.zeros((self.height, self.width), dtype=np.float32)
        for (col, row), cell in world._influence.items():
            best_t, best_v = 0, 0.0
            for t, v in cell.items():
                if v > best_v:
                    best_t, best_v = t, v
            if best_v >= ZONE_MIN and best_t in index and (shown is None or best_t in shown):
                owner[row, col] = index[best_t]
                value[row, col] = best_v
        if vis is not None and (vis.zones or vis.sites):
            seen_owner = np.full((self.height, self.width), -1, dtype=np.int16)
            seen_value = np.zeros((self.height, self.width), dtype=np.float32)
            for (col, row), (t, v) in vis.zones.items():
                if t in index and (shown is None or t in shown) and 0 <= row < self.height:
                    seen_owner[row, col % self.width] = index[t]
                    seen_value[row, col % self.width] = v
            if vis.visible:
                rows, cols = self._cells(vis.visible)
                seen_owner[rows, cols] = owner[rows, cols]
                seen_value[rows, cols] = value[rows, cols]
            owner, value = seen_owner, seen_value
        edge = np.zeros((self.height, self.width), dtype=bool)
        if shown is None:
            for nr, nc in self._neighbors():
                edge |= owner[nr, nc] != owner
        else:
            # La frontiere d'un pays, pas celle de chacun de ses peuples.
            realm = np.where(owner >= 0, realm_ix[np.maximum(owner, 0)], -1)
            for nr, nc in self._neighbors():
                edge |= realm[nr, nc] != realm
        inside = owner >= 0
        strength = np.clip((value - ZONE_MIN) / max(1e-6, CORE_MIN - ZONE_MIN), 0.0, 1.0)
        if self.turn_pick:
            alpha = np.where(edge, 0.75, 0.5 + 0.12 * strength).astype(np.float32)
        elif shown is None:
            alpha = np.where(edge, 0.36, 0.08 + 0.12 * strength).astype(np.float32)
        else:
            alpha = np.where(edge, 0.8, 0.45 + 0.15 * strength).astype(np.float32)
        self.zone_owner = owner
        self.zone_alpha = np.where(inside, alpha, 0.0).astype(np.float32)
        if self.turn_pick:
            inner, self.zone_edge = 0.5 + 0.12 * strength, 0.75
        elif shown is None:
            inner, self.zone_edge = 0.08 + 0.12 * strength, 0.36
        else:
            inner, self.zone_edge = 0.45 + 0.15 * strength, 0.8
        self.zone_inner = np.where(inside, inner, 0.0).astype(np.float32)
        if shown is None:
            self.zone_group = owner
        else:
            self.zone_group = np.where(owner >= 0, realm_ix[np.maximum(owner, 0)], -1).astype(np.int16)
        return key

    def zone_key(self) -> tuple:
        return (self.zones_on, self.realm_on, self.turn_pick, self._zone_key, self.res_on, self.trade_on, self.res_hidden)

    def _resources(self):
        if self._res_color is None or self._res_key != self.res_hidden:
            world = self.world
            self._res_key = self.res_hidden
            color = np.zeros((self.height, self.width, 3), dtype=np.float32)
            best = np.zeros((self.height, self.width), dtype=np.float32)
            for name in NAMES:
                layer = world.resources.get(name)
                if not layer or name in self.res_hidden:
                    continue
                v = np.frombuffer(layer, dtype=np.uint8).reshape(self.height, self.width) / np.float32(255.0)
                win = (v > best) & (v >= 0.15)
                color[win] = COLORS[name]
                best = np.where(win, v, best)
            self._res_color = color
            self._res_alpha = np.where(best >= 0.15, 0.25 + 0.55 * best, 0.0).astype(np.float32)
        return self._res_color, self._res_alpha

    # --- couleurs ----------------------------------------------------

    def _colors(self, rows, cols) -> tuple[np.ndarray, np.ndarray]:
        base = _PALETTE[self.seasons()[rows, cols], self.terr[rows, cols]]
        size = self.river_size[rows, cols]
        if size.any():
            a = RIVER_TINT[size][:, None]
            base = base * (1.0 - a) + RIVER_COLOR * a
        if self.trade_on:
            grey = base.mean(axis=-1, keepdims=True)
            base = (base * 0.35 + grey * 0.65) * 0.55
        elif self.res_on and self.world.resources:
            color, alpha = self._resources()
            a = alpha[rows, cols][:, None]
            # Le terrain assombri dessous, la ressource par-dessus.
            base = base * (0.55 * (1.0 - a)) + color[rows, cols] * a
        elif self.zones_on:
            owner = self.zone_owner[rows, cols]
            mine = owner >= 0
            if self.realm_on or self.turn_pick:
                # Carte politique : le terrain en gris, les pays par-dessus.
                grey = base.mean(axis=-1, keepdims=True)
                base = (base * 0.3 + grey * 0.7) * 0.75
            if mine.any():
                a = self.zone_alpha[rows, cols][mine][:, None]
                tint = self.zone_colors[owner[mine]]
                base = base.copy()
                base[mine] = base[mine] * (1.0 - a) + tint * a
        return base, self.fog[rows, cols]

    # --- loin : lancer de rayons -------------------------------------

    def cells_at(self, lon: np.ndarray, lat: np.ndarray):
        """Case sous chaque point (lon, lat) : meme regle que
        globe.lonlat_to_colrow (le clic), en bloc."""
        width, height = self.width, self.height
        xf = (lon + math.pi) * (width / (2.0 * math.pi)) - 0.5
        yf = (math.pi / 2.0 - lat) * ((height - 1) / math.pi)
        # Le terrain sans nid d'abeille (globe.warp) : le meme que le clic.
        dx, dy = globe.warp(xf, yf, width, np.sin, np.sqrt, np.minimum)
        xf = xf + dx
        yf = yf + dy
        r0 = np.clip(np.floor(yf), 0, height - 1).astype(np.int64)
        r1 = np.minimum(r0 + 1, height - 1)
        best_c = None
        best_r = r0
        best_d = None
        for rr in (r0, r1):
            shift = np.where(rr & 1, HEX_ROW_SHIFT, -HEX_ROW_SHIFT)
            cc = np.floor(xf - shift + 0.5)
            dx = xf - (cc + shift)
            dy = (yf - rr) * HEX_ROW_SQUASH
            d = dx * dx + dy * dy
            cc = cc.astype(np.int64) % width
            if best_d is None:
                best_c, best_d = cc, d
            else:
                closer = d < best_d
                best_c = np.where(closer, cc, best_c)
                best_r = np.where(closer, rr, best_r)
        return best_r, best_c

    def _ray_hits(self, x0, y0, nx, ny, step, cx, cy, focal, dist):
        key = (x0, y0, nx, ny, step, cx, cy, focal, dist)
        hit_rays = self._rays.get(key)
        if hit_rays is not None:
            return hit_rays
        px = x0 + (np.arange(nx, dtype=np.float64) + 0.5) * step
        py = y0 + (np.arange(ny, dtype=np.float64) + 0.5) * step
        lx, ly = np.meshgrid((px - cx) / focal, (cy - py) / focal, indexing="xy")
        inv = 1.0 / np.sqrt(lx * lx + ly * ly + 1.0)
        lx, ly, lz = lx * inv, ly * inv, -inv
        b = 2.0 * dist * lz
        disc = b * b - 4.0 * (dist * dist - 1.0)
        hit = disc >= 0.0
        root = np.sqrt(np.where(hit, disc, 0.0))
        t1 = (-b - root) / 2.0
        t2 = (-b + root) / 2.0
        t = np.where(t1 > 1e-4, t1, t2)
        hit &= t > 1e-4
        flat = np.nonzero(hit.ravel())[0]
        t = t.ravel()[flat]
        rays = (
            flat,
            (lx.ravel()[flat] * t).astype(np.float32),
            (ly.ravel()[flat] * t).astype(np.float32),
            (dist + lz.ravel()[flat] * t).astype(np.float32),
        )
        if len(self._rays) >= 4:
            self._rays.clear()
        self._rays[key] = rays
        return rays

    def texture(
        self, state, yaw, pitch, cx, cy, focal, dist, clip: pygame.Rect, samples=FINE_SAMPLES
    ):
        """Surface de la planete vue d'ici, et sa position a l'ecran."""
        self.sync_fog(state)
        limb = focal / math.sqrt(max(1e-4, dist * dist - 1.0))
        x0 = max(clip.left, int(cx - limb) - 1)
        x1 = min(clip.right, int(cx + limb) + 2)
        y0 = max(clip.top, int(cy - limb) - 1)
        y1 = min(clip.bottom, int(cy + limb) + 2)
        if x1 <= x0 or y1 <= y0:
            return None
        area = (x1 - x0) * (y1 - y0)
        step = max(1, math.ceil(math.sqrt(area / samples)))
        nx = -(-(x1 - x0) // step)
        ny = -(-(y1 - y0) // step)
        flat, hx, hy, hz = self._ray_hits(x0, y0, nx, ny, step, cx, cy, focal, dist)
        img = np.empty((ny * nx, 3), dtype=np.uint8)
        img[:] = _KEY
        if len(flat):
            cp, sp = np.float32(math.cos(pitch)), np.float32(math.sin(pitch))
            cyw, syw = np.float32(math.cos(yaw)), np.float32(math.sin(yaw))
            y1r = hy * cp + hz * sp
            z1 = -hy * sp + hz * cp
            x2 = hx * cyw - z1 * syw
            z2 = hx * syw + z1 * cyw
            lon = np.arctan2(x2, z2)
            lat = np.arcsin(np.clip(y1r, -1.0, 1.0))
            width, height = self.width, self.height
            xf = (lon + np.float32(math.pi)) * np.float32(width / (2.0 * math.pi)) - np.float32(0.5)
            yf = (np.float32(math.pi / 2.0) - lat) * np.float32((height - 1) / math.pi)
            px = hex_screen_px(self.world, focal, dist)
            lit = np.float32(0.34) + np.float32(0.66) * np.clip(hz, 0.0, 1.0)
            if px < SHAPE_MIN_PX:
                # De tres loin : la case la plus proche (une case < un pixel).
                rows, cols = self.cells_at(lon, lat)
                base, fog = self._colors(rows, cols)
                lit = np.where(fog == 1, lit * np.float32(0.55), lit)
                rgb = np.minimum(255.0, np.floor(base * lit[:, None])).astype(np.uint8)
                rgb[fog == 0] = FOG_UNEXPLORED
                img[flat] = rgb
            else:
                level = next((k for k in TILE_GRAINS if px / k <= TILE_PX), TILE_GRAINS[-1])
                if samples <= FAST_SAMPLES:
                    # La vue bouge : un grain plus gros (vite cuit), sans
                    # escalier trop visible.
                    level = next((k for k in TILE_GRAINS if px / k <= TILE_PX_FAST), TILE_GRAINS[-1])
                if self.zones_on:
                    self._zone_tiles_key = self._zone_key
                for a in range(0, len(flat), SHAPE_CHUNK):
                    b = a + SHAPE_CHUNK
                    base, fog = self._shade(xf[a:b], yf[a:b], level)
                    # Le brouillard doux : vu (2), connu (1), jamais vu (0).
                    seen = np.clip(fog - 1.0, 0.0, 1.0)
                    known = np.clip((fog - 0.35) / 0.3, 0.0, 1.0)[:, None]
                    li = lit[a:b] * (np.float32(0.55) + np.float32(0.45) * seen)
                    rgb = np.minimum(255.0, np.floor(base * li[:, None]))
                    rgb = rgb * known + np.array(FOG_UNEXPLORED, dtype=np.float32) * (1.0 - known)
                    img[flat[a:b]] = rgb.astype(np.uint8)
        surf = pygame.Surface((nx, ny))
        pygame.surfarray.blit_array(surf, img.reshape(ny, nx, 3).transpose(1, 0, 2))
        surf.set_colorkey(_KEY)
        if step > 1:
            surf = pygame.transform.scale(surf, (nx * step, ny * step))
        return surf, (x0, y0)

    # --- pres : polygones ------------------------------------------------

    def _centers_of(self, rr, cc) -> np.ndarray:
        """Le point de la sphere au centre des cases (rr, cc)."""
        lon = 2.0 * math.pi * (cc + 0.5) / self.width - math.pi
        lat = (math.pi / 2.0) - (math.pi * rr / (self.height - 1)) if self.height > 1 else rr * 0.0
        cl = np.cos(lat)
        return np.stack([cl * np.sin(lon), np.sin(lat), cl * np.cos(lon)], axis=-1)

    def _neighbor_of(self, rr, cc, k: int):
        dq, dr = NEIGHBOR_DELTAS[k]
        raw = rr + dr
        half = lambda x: (x - (x & 1)) // 2  # noqa: E731
        return np.clip(raw, 0, self.height - 1), (cc + dq + half(raw) - half(rr)) % self.width

    def draw_rivers(self, screen, state, yaw, pitch, cx, cy, focal, dist) -> None:
        """Les rivieres en traits par-dessus les formes (de pres) : les cases
        a l'ecran, leur cours."""
        if hex_screen_px(self.world, focal, dist) < SHAPE_MIN_PX or not self.world.rivers:
            return
        world = self.world
        sw, sh = screen.get_size()
        col_c, row_c = look_center(world, yaw, pitch)
        radius = visible_hex_radius(world, dist, sw, sh, focal)
        rad2 = radius * radius + 2
        r0 = max(0, int(row_c) - radius)
        r1 = min(self.height - 1, int(row_c) + radius)
        rr, dd = np.meshgrid(np.arange(r0, r1 + 1), np.arange(-radius, radius + 1), indexing="ij")
        rr = rr.ravel()
        dd = dd.ravel()
        keep = dd * dd + (rr - row_c) ** 2 <= rad2
        rr = rr[keep]
        cc = np.trunc(col_c + dd[keep]).astype(np.int64) % self.width
        fog = self.fog[rr, cc]
        seen = (fog != 0) & (self.river_size[rr, cc] > 0)
        rr, cc, fog = rr[seen], cc[seen], fog[seen]
        if len(rr):
            self._draw_rivers(screen, rr, cc, fog, yaw, pitch, cx, cy, focal, dist)

    def _draw_rivers(self, screen, rr, cc, fog, yaw, pitch, cx, cy, focal, dist) -> None:
        """Les rivieres des cases dessinees : un trait du centre de la case au
        centre de la case en aval (le terrain deforme, comme les cases)."""
        rivers = self.world.rivers
        if not rivers or not len(rr):
            return
        code = np.frombuffer(rivers, dtype=np.uint8).reshape(self.height, self.width)[rr, cc]
        on = code > 0
        if not on.any():
            return
        rr, cc, code, fog = rr[on], cc[on], code[on], fog[on]
        k = (code & 7).astype(np.int64) - 1
        nr = np.empty_like(rr)
        nc = np.empty_like(cc)
        for d in range(6):
            sel = k == d
            if sel.any():
                nr[sel], nc[sel] = self._neighbor_of(rr[sel], cc[sel], d)
        hex_px = focal * (2.0 * math.pi / max(1, self.width)) / max(1e-3, dist - 1.0)
        widths = np.maximum(1, np.round(hex_px * np.array((0.0, 0.07, 0.13, 0.22))[code >> 3])).astype(np.int64)
        ends = []
        for r_, c_ in ((rr, cc), (nr, nc)):
            p_ = self._warp_points(self._centers_of(r_, c_))
            x, y, z = _rotate(p_[:, 0], p_[:, 1], p_[:, 2], yaw, pitch)
            depth = dist - z
            ok = (z * dist >= 0.98) & (depth > 0.04)
            depth = np.where(ok, depth, 1.0)
            ends.append((cx + focal * x / depth, cy - focal * y / depth, ok))
        (ax, ay, aok), (bx, by, bok) = ends
        color = tuple(int(c) for c in RIVER_COLOR)
        dim = tuple(int(c * 0.55) for c in RIVER_COLOR)
        line = pygame.draw.line
        # Du centre de la case au centre de la case en aval.
        for i in np.nonzero(aok & bok)[0].tolist():
            line(screen, color if fog[i] == 2 else dim, (ax[i], ay[i]), (bx[i], by[i]), int(widths[i]))

    def _warp_points(self, p: np.ndarray) -> np.ndarray:
        """Des points de la sphere deplaces comme le terrain (globe.warp)."""
        width, height = self.width, self.height
        lon = np.arctan2(p[..., 0], p[..., 2])
        lat = np.arcsin(np.clip(p[..., 1], -1.0, 1.0))
        xf = (lon + math.pi) * (width / (2.0 * math.pi)) - 0.5
        yf = (math.pi / 2.0 - lat) * ((height - 1) / math.pi)
        dx, dy = globe.warp(xf, yf, width, np.sin, np.sqrt, np.minimum)
        lon = (xf - dx + 0.5) * (2.0 * math.pi / width) - math.pi
        lat = math.pi / 2.0 - (yf - dy) * (math.pi / max(1, height - 1))
        cl = np.cos(lat)
        return np.stack([cl * np.sin(lon), np.sin(lat), cl * np.cos(lon)], axis=-1)
