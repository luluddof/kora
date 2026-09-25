"""Dessin de la planete avec numpy.

Loin : lancer de rayons par pixel (une case hexagonale par pixel touche).
Pres : polygones des hexagones, geometrie calculee en bloc.
Memes formules que l'ancien rendu Python pur (projection, ombrage
0.34 + 0.66 z, brouillard 0.45 / 0.55) ; le cout depend de l'ecran,
plus de la taille de la carte.
"""

from __future__ import annotations

import math

import numpy as np
import pygame

from src.kora.globe import HEX_ROW_SHIFT, HEX_ROW_SQUASH, look_center, visible_hex_radius
from src.kora.look import season_color
from src.kora.types import Season, Terrain
from src.kora.vision import PlayerVision
from src.kora.world import NEIGHBOR_DELTAS, axial_to_offset

FOG_UNEXPLORED = (8, 8, 10)
TERRAINS = tuple(Terrain)
TERRAIN_CODE = {t: i for i, t in enumerate(TERRAINS)}
SEASONS = (Season.PRINTEMPS, Season.ETE, Season.AUTOMNE, Season.HIVER)
# Au-dessus de cette taille d'hexagone a l'ecran, on dessine des polygones.
POLY_HEX_PX = 22.0
# Pixels calcules par image : peu pendant que la camera bouge, beaucoup
# une fois qu'elle s'arrete (voir Renderer._draw_sphere).
FAST_SAMPLES = 90_000
FINE_SAMPLES = 600_000
_KEY = (255, 0, 255)
_PALETTE = np.array(
    [[season_color(t, s) for t in TERRAINS] for s in SEASONS], dtype=np.float32
)
_INFLATE = 1.12


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
        self._zone_key = None
        self.zone_owner = np.full((self.height, self.width), -1, dtype=np.int16)
        self.zone_alpha = np.zeros((self.height, self.width), dtype=np.float32)
        self.zone_colors = np.zeros((1, 3), dtype=np.float32)
        self._nb = None
        # Calque "Ressources" : couleur de la ressource la plus forte.
        self.res_on = False
        # Mode Commerce : le terrain s'efface, les routes ressortent.
        self.trade_on = False
        self._res_color = None
        self._res_alpha = None

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
        # nouvel objet que si une bande du joueur a bouge.
        vis = state.vision if isinstance(state.vision, PlayerVision) else None
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
        if self._nb is None:
            rows = np.arange(self.height)[:, None]
            cols = np.arange(self.width)[None, :]

            def half(r):
                return (r - (r & 1)) // 2

            out = []
            for dq, dr in NEIGHBOR_DELTAS:
                nr = rows + dr
                nc = (cols + dq + half(nr) - half(rows)) % self.width
                out.append((np.clip(nr, 0, self.height - 1) + 0 * cols, nc + 0 * rows))
            self._nb = out
        return self._nb

    def sync_zones(self, state) -> tuple:
        """Refait le calque quand l'influence a change (une fois par mois)."""
        from src.kora.influence import CORE_MIN, ZONE_MIN
        from src.kora.peoples import color_of

        world = self.world
        tids = sorted(state.tribes)
        key = (getattr(world, "_influence_gen", 0), len(world._influence), tuple(tids))
        if key == self._zone_key:
            return key
        self._zone_key = key
        index = {tid: i for i, tid in enumerate(tids)}
        self.zone_colors = np.array(
            [color_of(state.tribes[t]) for t in tids] or [(0, 0, 0)], dtype=np.float32
        )
        owner = np.full((self.height, self.width), -1, dtype=np.int16)
        value = np.zeros((self.height, self.width), dtype=np.float32)
        for (col, row), cell in world._influence.items():
            best_t, best_v = 0, 0.0
            for t, v in cell.items():
                if v > best_v:
                    best_t, best_v = t, v
            if best_v >= ZONE_MIN and best_t in index:
                owner[row, col] = index[best_t]
                value[row, col] = best_v
        edge = np.zeros((self.height, self.width), dtype=bool)
        for nr, nc in self._neighbors():
            edge |= owner[nr, nc] != owner
        inside = owner >= 0
        strength = np.clip((value - ZONE_MIN) / max(1e-6, CORE_MIN - ZONE_MIN), 0.0, 1.0)
        alpha = np.where(edge, 0.36, 0.08 + 0.12 * strength).astype(np.float32)
        self.zone_owner = owner
        self.zone_alpha = np.where(inside, alpha, 0.0).astype(np.float32)
        return key

    def zone_key(self) -> tuple:
        return (self.zones_on, self._zone_key, self.res_on, self.trade_on)

    def _resources(self):
        if self._res_color is None:
            from src.kora.resources import COLORS, NAMES

            world = self.world
            color = np.zeros((self.height, self.width, 3), dtype=np.float32)
            best = np.zeros((self.height, self.width), dtype=np.float32)
            for name in NAMES:
                layer = world.resources.get(name)
                if not layer:
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
            rows, cols = self.cells_at(lon, lat)
            base, fog = self._colors(rows, cols)
            lit = np.float32(0.34) + np.float32(0.66) * np.clip(hz, 0.0, 1.0)
            lit = np.where(fog == 1, lit * np.float32(0.55), lit)
            rgb = np.minimum(255.0, np.floor(base * lit[:, None])).astype(np.uint8)
            rgb[fog == 0] = FOG_UNEXPLORED
            img[flat] = rgb
        surf = pygame.Surface((nx, ny))
        pygame.surfarray.blit_array(surf, img.reshape(ny, nx, 3).transpose(1, 0, 2))
        surf.set_colorkey(_KEY)
        if step > 1:
            surf = pygame.transform.scale(surf, (nx * step, ny * step))
        return surf, (x0, y0)

    # --- pres : polygones ------------------------------------------------

    def _mesh(self):
        if self._centers is not None:
            return self._centers, self._corners
        width, height = self.width, self.height
        cols = np.arange(width)
        rows = np.arange(height)
        lon = 2.0 * math.pi * (cols + 0.5) / width - math.pi
        lat = (math.pi / 2.0) - (math.pi * rows / (height - 1)) if height > 1 else rows * 0.0
        cl = np.cos(lat)[:, None]
        centers = np.stack(
            [
                cl * np.sin(lon)[None, :],
                np.repeat(np.sin(lat)[:, None], width, axis=1),
                cl * np.cos(lon)[None, :],
            ],
            axis=-1,
        )

        def half(x):
            return (x - (x & 1)) // 2

        nbs = []
        for dq, dr in NEIGHBOR_DELTAS:
            raw_r = rows + dr
            dc = dq + half(raw_r) - half(rows)
            nc = (cols[None, :] + dc[:, None]) % width
            nr = np.clip(raw_r, 0, height - 1)
            nbs.append(centers[nr[:, None], nc])
        corners = np.empty((height, width, 6, 3), dtype=np.float32)
        for k in range(6):
            v = _normalize(centers + nbs[k] + nbs[(k + 1) % 6])
            corners[:, :, k, :] = _normalize(centers + (v - centers) * _INFLATE)
        self._centers = centers
        self._corners = corners
        return centers, corners

    def draw_hexes(self, screen, state, yaw, pitch, cx, cy, focal, dist) -> None:
        self.sync_fog(state)
        centers, corners = self._mesh()
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
        seen = self.fog[rr, cc] != 0
        rr, cc = rr[seen], cc[seen]
        if not len(rr):
            return
        cen = centers[rr, cc]
        x, y, z = _rotate(cen[:, 0], cen[:, 1], cen[:, 2], yaw, pitch)
        depth = dist - z
        ok = (z * dist >= 0.98) & (depth > 0.04)
        sx = cx + focal * x / np.where(ok, depth, 1.0)
        sy = cy - focal * y / np.where(ok, depth, 1.0)
        ok &= (sx >= -40) & (sy >= -40) & (sx <= sw + 40) & (sy <= sh + 40)
        rr, cc = rr[ok], cc[ok]
        if not len(rr):
            return
        cor = corners[rr, cc].astype(np.float64)
        x, y, z = _rotate(cor[..., 0], cor[..., 1], cor[..., 2], yaw, pitch)
        depth = dist - z
        good = ((z * dist >= 0.98) & (depth > 0.04)).all(axis=1)
        depth = np.where(depth > 0.04, depth, 1.0)
        pts = np.stack([cx + focal * x / depth, cy - focal * y / depth], axis=-1)
        base, fog = self._colors(rr, cc)
        base = np.where((fog == 1)[:, None], np.floor(base * 0.45), base)
        lit = 0.34 + 0.66 * np.clip(z.mean(axis=1), 0.0, 1.0)
        colors = np.minimum(255.0, np.floor(base * lit[:, None])).astype(np.int64)
        draw = pygame.draw.polygon
        for i in np.nonzero(good)[0].tolist():
            draw(screen, colors[i].tolist(), pts[i].tolist())
