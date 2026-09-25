from __future__ import annotations

import math

from src.kora.types import Hex
from src.kora.world import NEIGHBOR_DELTAS, axial_to_offset, offset_to_axial

HEX_SIZE = 8
PITCH_LIMIT = 1.25
NEAR_DIST = 1.32
FOCUS_ZOOM = 3.2


def land_draw_stride(dist: float) -> int:
    if dist >= 2.55:
        return 4
    if dist >= 1.95:
        return 3
    if dist > NEAR_DIST:
        return 2
    return 1


def lonlat_from_offset(col: float, row: float, width: int, height: int) -> tuple[float, float]:
    lon = (2.0 * math.pi * (col + 0.5) / max(1, width)) - math.pi
    if height <= 1:
        return lon, 0.0
    lat = (math.pi / 2.0) - (math.pi * row / (height - 1))
    return lon, lat


def xyz_from_lonlat(lon: float, lat: float) -> tuple[float, float, float]:
    cl = math.cos(lat)
    return cl * math.sin(lon), math.sin(lat), cl * math.cos(lon)


def offset_to_xyz(col: float, row: float, width: int, height: int) -> tuple[float, float, float]:
    lon, lat = lonlat_from_offset(col, row, width, height)
    return xyz_from_lonlat(lon, lat)


def rotate_xyz(
    x: float, y: float, z: float, yaw: float, pitch: float
) -> tuple[float, float, float]:
    cy, sy = math.cos(yaw), math.sin(yaw)
    x1 = x * cy + z * sy
    z1 = -x * sy + z * cy
    cp, sp = math.cos(pitch), math.sin(pitch)
    y2 = y * cp - z1 * sp
    z2 = y * sp + z1 * cp
    return x1, y2, z2


def inverse_rotate(
    x: float, y: float, z: float, yaw: float, pitch: float
) -> tuple[float, float, float]:
    cp, sp = math.cos(pitch), math.sin(pitch)
    y1 = y * cp + z * sp
    z1 = -y * sp + z * cp
    cy, sy = math.cos(yaw), math.sin(yaw)
    x2 = x * cy - z1 * sy
    z2 = x * sy + z1 * cy
    return x2, y1, z2


def dist_from_zoom(zoom: float) -> float:
    z = max(0.08, zoom)
    dist = 1.022 + 2.15 / (0.40 + (z**1.45) * 5.4)
    return max(1.028, min(3.20, dist))


def view_params(
    zoom: float, screen_w: int, screen_h: int, hud_height: int = 48
) -> tuple[float, float, float, float]:
    dist = dist_from_zoom(zoom)
    usable = min(screen_w, max(80, screen_h - hud_height))
    focal = 0.92 * usable
    cx = screen_w / 2.0
    cy = hud_height + (screen_h - hud_height) / 2.0
    return cx, cy, focal, dist


def project_xyz(
    x: float,
    y: float,
    z: float,
    cx: float,
    cy: float,
    focal: float,
    dist: float,
) -> tuple[float, float] | None:
    if z * dist < 0.98:
        return None
    depth = dist - z
    if depth <= 0.04:
        return None
    return cx + focal * x / depth, cy - focal * y / depth


def hex_to_globe_screen(
    h: Hex,
    world,
    yaw: float,
    pitch: float,
    cx: float,
    cy: float,
    focal: float,
    dist: float,
) -> tuple[float, float] | None:
    col, row = axial_to_offset(h)
    x, y, z = offset_to_xyz(col, row, world.width, world.height)
    x, y, z = rotate_xyz(x, y, z, yaw, pitch)
    return project_xyz(x, y, z, cx, cy, focal, dist)


def _norm3(x: float, y: float, z: float) -> tuple[float, float, float]:
    inv = 1.0 / math.sqrt(max(1e-12, x * x + y * y + z * z))
    return x * inv, y * inv, z * inv


def hex_corner_xyz(col: int, row: int, width: int, height: int, inflate: float = 1.12):
    cx, cy, cz = offset_to_xyz(col, row, width, height)
    origin = offset_to_axial(col, row)
    nxyz = []
    for dq, dr in NEIGHBOR_DELTAS:
        nc, nr = axial_to_offset(Hex(origin.q + dq, origin.r + dr))
        nc %= max(1, width)
        nr = max(0, min(height - 1, nr))
        nxyz.append(offset_to_xyz(nc, nr, width, height))
    pts = []
    for i in range(6):
        ax, ay, az = nxyz[i]
        bx, by, bz = nxyz[(i + 1) % 6]
        vx, vy, vz = _norm3(cx + ax + bx, cy + ay + by, cz + az + bz)
        ix = cx + (vx - cx) * inflate
        iy = cy + (vy - cy) * inflate
        iz = cz + (vz - cz) * inflate
        pts.append(_norm3(ix, iy, iz))
    return pts


def hit_globe(
    dx: float, dy: float, yaw: float, pitch: float, dist: float
) -> tuple[float, float, float] | None:
    lx, ly, lz = dx, dy, -1.0
    inv = 1.0 / math.sqrt(lx * lx + ly * ly + lz * lz)
    lx, ly, lz = lx * inv, ly * inv, lz * inv
    b = 2.0 * dist * lz
    c = dist * dist - 1.0
    disc = b * b - 4.0 * c
    if disc < 0:
        return None
    root = math.sqrt(disc)
    t = None
    t1 = (-b - root) / 2.0
    t2 = (-b + root) / 2.0
    if t1 > 1e-4:
        t = t1
    if t2 > 1e-4 and (t is None or t2 < t):
        t = t2
    if t is None:
        return None
    hx, hy, hz = lx * t, ly * t, dist + lz * t
    x, y, z = inverse_rotate(hx, hy, hz, yaw, pitch)
    lon = math.atan2(x, z)
    lat = math.asin(max(-1.0, min(1.0, y)))
    return lon, lat, hz


# Les hexagones dessines ont leur centre a col - 1/6 (rangee paire) ou
# col + 1/6 (rangee impaire). La case sous un point est la plus proche de
# ces centres parmi les deux rangees voisines ; globe_draw.Planet.cells_at
# applique la meme regle a tous les pixels d'un coup.
HEX_ROW_SHIFT = 1.0 / 6.0
HEX_ROW_SQUASH = 0.87


def lonlat_to_colrow(
    lon: float, lat: float, width: int, height: int
) -> tuple[int, int]:
    width = max(1, width)
    xf = (lon + math.pi) * (width / (2.0 * math.pi)) - 0.5
    if height <= 1:
        return int(math.floor(xf + 0.5)) % width, 0
    yf = ((math.pi / 2.0) - lat) * ((height - 1) / math.pi)
    r0 = max(0, min(height - 1, int(math.floor(yf))))
    best = None
    for row in (r0, min(r0 + 1, height - 1)):
        shift = HEX_ROW_SHIFT if row & 1 else -HEX_ROW_SHIFT
        col = math.floor(xf - shift + 0.5)
        dx = xf - (col + shift)
        dy = (yf - row) * HEX_ROW_SQUASH
        d = dx * dx + dy * dy
        if best is None or d < best[0]:
            best = (d, col % width, row)
    return best[1], best[2]


def pixel_to_hex_globe(
    mx: float,
    my: float,
    world,
    yaw: float,
    pitch: float,
    cx: float,
    cy: float,
    focal: float,
    dist: float,
) -> Hex | None:
    if focal <= 1e-6:
        return None
    hit = hit_globe((mx - cx) / focal, (cy - my) / focal, yaw, pitch, dist)
    if hit is None:
        return None
    lon, lat, _z = hit
    col, row = lonlat_to_colrow(lon, lat, world.width, world.height)
    return offset_to_axial(col, row)


def look_at_offset(col: float, row: float, width: int, height: int) -> tuple[float, float]:
    lon, lat = lonlat_from_offset(col, row, width, height)
    return -lon, clamp_pitch(lat)


def look_at_hex(h: Hex, width: int, height: int) -> tuple[float, float]:
    col, row = axial_to_offset(h)
    return look_at_offset(col, row, width, height)


def look_center(world, yaw: float, pitch: float):
    x, y, z = inverse_rotate(0.0, 0.0, 1.0, yaw, pitch)
    lon = math.atan2(x, z)
    lat = math.asin(max(-1.0, min(1.0, y)))
    col = ((lon + math.pi) / (2.0 * math.pi)) * world.width - 0.5
    if world.height <= 1:
        row = 0.0
    else:
        row = ((math.pi / 2.0) - lat) / math.pi * (world.height - 1)
    return col % world.width, max(0.0, min(world.height - 1.0, row))


def visible_hex_radius(
    world,
    dist: float,
    screen_w: int = 1280,
    screen_h: int = 720,
    focal: float = 600.0,
) -> int:
    depth = max(0.05, dist - 1.0)
    px = focal / depth * (2.0 * math.pi / max(1, world.width))
    nx = screen_w / max(1.2, px)
    ny = max(80, screen_h - 48) / max(1.2, px * 0.87)
    rad = int(0.58 * max(nx, ny) + 6)
    cap = 28 if dist <= 1.28 else 42
    return max(6, min(rad, cap))


def globe_uses_texture(limb: float, screen_w: int, screen_h: int, hud_height: int = 48) -> bool:
    usable = min(screen_w, max(80, screen_h - hud_height))
    return limb < usable * 0.42


def clamp_pitch(pitch: float) -> float:
    return max(-PITCH_LIMIT, min(PITCH_LIMIT, pitch))


def orbit_sensitivity(dist: float) -> float:
    return 0.0024 + 0.0062 * min(1.0, max(0.0, (dist - 1.03) / 1.7))
