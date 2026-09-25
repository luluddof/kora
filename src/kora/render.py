from __future__ import annotations

import math

import pygame

from src.kora.atlas import build_atlas_labels
from src.kora.globe import hex_to_globe_screen, view_params
from src.kora.globe_draw import (
    FAST_SAMPLES,
    FINE_SAMPLES,
    FOG_UNEXPLORED,
    POLY_HEX_PX,
    Planet,
    hex_screen_px,
)
from src.kora.log import FILTER_ALL, GameLog, LogKind
from src.kora.path import travel_weeks
from src.kora.peoples import color_of
from src.kora import chiefs, orders
from src.kora.sim import (
    PLAYER_TRIBE_ID,
    GameState,
    band_lines,
    band_summary,
    band_warn_from,
    fight_lines,
    inspect_lines,
)
from src.kora import tech
from src.kora.types import Hex, Season
from src.kora.vision import enemy_band_visible
from src.kora.world import axial_to_offset, offset_to_axial

HEX_SIZE = 8
MIN_ZOOM = 0.10
MAX_ZOOM = 4.8
OVERVIEW_HEX_PX = 3.2


SEASON_FR = {
    Season.PRINTEMPS: "Printemps",
    Season.ETE: "Ete",
    Season.AUTOMNE: "Automne",
    Season.HIVER: "Hiver",
}

HUD_HEIGHT = 48
# Au-dela de ce recul de camera, les chiffres des bandes deviennent du bruit.
LABEL_DIST = 1.9
JOURNAL_COLS = 38


def wrap_text(text: str, cols: int) -> list[str]:
    words = text.split(" ")
    lines: list[str] = []
    cur = ""
    for word in words:
        if cur and len(cur) + 1 + len(word) > cols:
            lines.append(cur)
            cur = word
        else:
            cur = f"{cur} {word}" if cur else word
    if cur:
        lines.append(cur)
    return lines or [""]
_SQUARE = 22
_GAP = 5


def hud_layout(width: int) -> dict:
    bar_y = 0
    cy = 13
    pause_x = max(280, width // 2 - 90)
    pause = (pause_x, cy, _SQUARE, _SQUARE)
    speeds = {}
    x = pause_x + _SQUARE + 10
    for n in range(1, 6):
        speeds[n] = (x, cy, _SQUARE, _SQUARE)
        x += _SQUARE + _GAP
    return {"pause": pause, "speeds": speeds, "bar": (0, bar_y, width, HUD_HEIGHT)}


def _contains(rect: tuple[int, int, int, int], mx: int, my: int) -> bool:
    x, y, w, h = rect
    return x <= mx <= x + w and y <= my <= y + h


def hud_hit(layout: dict, mx: int, my: int):
    if _contains(layout["pause"], mx, my):
        return "pause"
    for n, rect in layout["speeds"].items():
        if _contains(rect, mx, my):
            return ("speed", n)
    if _contains(layout["bar"], mx, my):
        return "bar"
    return None


MENU_ITEMS = (
    ("reprendre", "Reprendre"),
    ("sauvegarder", "Sauvegarder"),
    ("nouvelle", "Nouvelle partie"),
    ("quitter", "Quitter"),
)


def menu_layout(width: int, height: int) -> dict:
    n = len(MENU_ITEMS)
    box_w, box_h = 300, 72 + n * 44
    bx = (width - box_w) // 2
    by = (height - box_h) // 2
    items = {}
    y = by + 56
    for key, _label in MENU_ITEMS:
        items[key] = (bx + 24, y, box_w - 48, 36)
        y += 44
    return {"box": (bx, by, box_w, box_h), "items": items}


def menu_hit(layout: dict, mx: int, my: int):
    for key, rect in layout["items"].items():
        if _contains(rect, mx, my):
            return key
    return None


def fight_panel_layout(width: int, height: int, n_lines: int) -> dict:
    bw = 268
    bh = 16 + 18 * max(1, n_lines) + 10
    bx, by = 12, HUD_HEIGHT + 12
    close = (bx + bw - 72, by + 6, 60, 22)
    return {"box": (bx, by, bw, bh), "close": close}


def fight_panel_hit(layout: dict, mx: int, my: int):
    if not layout:
        return None
    if _contains(layout["close"], mx, my):
        return "close"
    if _contains(layout["box"], mx, my):
        return "panel"
    return None


BAND_CARD_W = 530
BAND_BUTTONS = (
    ("split", "Scinder [S]"),
    ("merge", "Reunir [F]"),
    ("next", "Suivante"),
    ("chief", "Chef ici"),
    ("village", "Village [V]"),
    ("camp", "Camper [C]"),
    ("deposit", "Deposer [K]"),
    ("withdraw", "Reprendre"),
    ("honor", "Honorer [H]"),
    ("army", "Troupe [L]"),
)
BAND_ROW = 5
BAND_HINT = "Clic : aller · ennemi : raid · Maj+clic allie : rejoindre"


def band_card_layout(width: int, height: int, n_lines: int) -> dict:
    bw = BAND_CARD_W
    rows = -(-len(BAND_BUTTONS) // BAND_ROW)
    bh = 12 + 18 + 16 * max(0, n_lines - 1) + 10 + rows * 32 + 4 + 16 + 8
    bx = max(276, (width - bw) // 2)
    if bx + bw > width - 40:
        bx = max(8, width - 40 - bw)
    by = height - bh - 12
    buttons = {}
    gap = 6
    bwidth = (bw - 24 - gap * (BAND_ROW - 1)) // BAND_ROW
    top = by + bh - 8 - 16 - 4 - rows * 32
    for i, (key, _label) in enumerate(BAND_BUTTONS):
        col, row = i % BAND_ROW, i // BAND_ROW
        buttons[key] = (bx + 12 + col * (bwidth + gap), top + row * 32, bwidth, 26)
    return {"box": (bx, by, bw, bh), "buttons": buttons}


MAP_MODES = (
    ("relief", "Relief"),
    ("zones", "Zones [Z]"),
    ("ressources", "Ressources [R]"),
    ("commerce", "Commerce [X]"),
)


def map_mode_layout(width: int, height: int) -> dict:
    """Pastilles du mode de carte, en haut a droite sous la barre (a gauche
    des onglets) : rien d'autre ne s'y trouve quand les panneaux sont fermes."""
    out = {}
    x = width - 40
    for key, label in reversed(MAP_MODES):
        cw = 16 + 8 * len(label)
        x -= cw
        out[key] = (x, HUD_HEIGHT + 8, cw, 22)
        x -= 6
    return out


def map_mode_hit(layout: dict, mx: int, my: int):
    for key, rect in layout.items():
        if _contains(rect, mx, my):
            return key
    return None


def toast_hit(hits: list, mx: int, my: int):
    for rect, toast in hits:
        if _contains(rect, mx, my):
            return toast
    return None


def band_card_hit(layout: dict, mx: int, my: int):
    if not layout:
        return None
    for key, rect in layout["buttons"].items():
        if _contains(rect, mx, my):
            return key
    if _contains(layout["box"], mx, my):
        return "card"
    return None


FILTER_CHIPS = (
    ("filter_tous", "Tous", 48),
    ("filter_combat", "Combats", 70),
    ("filter_survie", "Survie", 58),
    ("filter_saison", "Saisons", 66),
    ("filter_decouverte", "Decouverte", 86),
    ("filter_politique", "Peuples", 64),
)
SORT_CHIPS = (
    ("sort_recent", "Plus recent", 100),
    ("sort_ancien", "Plus ancien", 100),
)
FILTER_BY_HIT = {
    "filter_tous": FILTER_ALL,
    "filter_combat": LogKind.COMBAT.value,
    "filter_survie": LogKind.SURVIE.value,
    "filter_saison": LogKind.SAISON.value,
    "filter_decouverte": LogKind.DECOUVERTE.value,
    "filter_politique": LogKind.POLITIQUE.value,
}


TECH_HEADER_H = 66
TECH_DETAIL_H = 176
# L'arbre des savoirs a la Victoria 3 : une TOILE qu'on parcourt a la souris
# (glisser) et qu'on zoome (molette, boutons) ; tout n'est pas a l'ecran.
# Geometrie de la toile a l'echelle 1 (render_tech la dessine).
TREE_PAD = 24
TREE_GUTTER = 170
TREE_COL = 250
TREE_ROW = 118
TREE_NODE_W = 214
TREE_NODE_H = 82
TREE_COLHEAD = 58
TREE_BAND = 62
TREE_ZOOM_MAX = 1.6
TREE_ZOOM_STEP = 1.15
TREE_MINI_W = 176
# Anciens noms (d'autres modules les lisent encore).
TECH_ROW_H = TREE_ROW
TECH_GUTTER = TREE_GUTTER

_TREE: dict = {}


def tech_world() -> dict:
    """La toile de l'arbre, a l'echelle 1 : une rangee par palier, une
    colonne par branche, une banniere par age."""
    if _TREE:
        return _TREE
    n_cols = max(len(b) for _n, _t, b in tech.ERAS)
    width = TREE_PAD + TREE_GUTTER + n_cols * TREE_COL + TREE_PAD
    y = TREE_PAD
    sections = []
    rows: dict[int, int] = {}
    for i, (_name, tiers, _branches) in enumerate(tech.ERAS):
        head_h = TREE_COLHEAD if i == 0 else TREE_BAND
        head = (0, y, width, head_h)
        y += head_h
        top = y
        for tier in tiers:
            rows[tier] = y
            y += TREE_ROW
        sections.append({"era": i, "head": head, "body": (0, top, width, y - top)})
    cols = [TREE_PAD + TREE_GUTTER + i * TREE_COL for i in range(n_cols)]
    nodes = {
        t.id: (cols[t.branch] + (TREE_COL - TREE_NODE_W) // 2, rows[t.tier] + (TREE_ROW - TREE_NODE_H) // 2, TREE_NODE_W, TREE_NODE_H)
        for t in tech.TECHS.values()
    }
    _TREE.update({"size": (width, y + TREE_PAD), "cols": cols, "col_w": TREE_COL, "rows": rows, "sections": sections, "nodes": nodes})
    return _TREE


def tree_zoom_min(view, world) -> float:
    """Tout l'arbre tient dans la vue."""
    ww, wh = world["size"]
    return max(0.25, min(view[2] / ww, view[3] / wh))


def clamp_cam(cam, view, world) -> tuple:
    """Camera (x, y, zoom) : x, y = point de la toile au coin haut-gauche de
    la vue. On ne sort pas de la toile ; plus petite que la vue, elle est
    centree."""
    x, y, z = cam
    z = max(tree_zoom_min(view, world), min(TREE_ZOOM_MAX, z))
    ww, wh = world["size"]
    vw, vh = view[2] / z, view[3] / z
    x = (ww - vw) / 2 if vw >= ww else max(0.0, min(ww - vw, x))
    y = (wh - vh) / 2 if vh >= wh else max(0.0, min(wh - vh, y))
    return (x, y, z)


def cam_on(view, world, tid: str | None, z: float = 1.0) -> tuple:
    """Camera centree sur un savoir (ou le haut de l'arbre)."""
    if tid in world["nodes"]:
        nx, ny, nw, nh = world["nodes"][tid]
        cx, cy = nx + nw / 2, ny + nh / 2
    else:
        cx, cy = world["size"][0] / 2, 0.0
    return clamp_cam((cx - view[2] / (2 * z), cy - view[3] / (2 * z), z), view, world)


def zoom_at(cam, view, world, mx: float, my: float, factor: float) -> tuple:
    """Zoomer autour du curseur : le point de la toile sous la souris reste
    sous la souris."""
    x, y, z = cam
    wx = x + (mx - view[0]) / z
    wy = y + (my - view[1]) / z
    nz = max(tree_zoom_min(view, world), min(TREE_ZOOM_MAX, z * factor))
    return clamp_cam((wx - (mx - view[0]) / nz, wy - (my - view[1]) / nz, nz), view, world)


def pan(cam, view, world, dx: float, dy: float) -> tuple:
    """Glisser la toile de (dx, dy) pixels."""
    x, y, z = cam
    return clamp_cam((x - dx / z, y - dy / z, z), view, world)


def to_screen(cam, view, rect) -> tuple:
    x, y, z = cam
    rx, ry, rw, rh = rect
    return (view[0] + (rx - x) * z, view[1] + (ry - y) * z, rw * z, rh * z)


def _clip(a, b):
    x0, y0 = max(a[0], b[0]), max(a[1], b[1])
    x1, y1 = min(a[0] + a[2], b[0] + b[2]), min(a[1] + a[3], b[1] + b[3])
    if x1 <= x0 or y1 <= y0:
        return None
    return (int(x0), int(y0), int(x1 - x0), int(y1 - y0))


def tech_panel_layout(width: int, height: int, tab_w: int = 32, era: int = 0, cam=None) -> dict:
    """Ecran des savoirs (a la Victoria 3) : en tete la recherche en cours,
    au milieu la VUE sur la toile de l'arbre (camera `cam` : glisser pour se
    deplacer, molette pour zoomer ; mini-carte et boutons dans un coin), en
    bas la fiche du savoir choisi et le bouton Apprendre.
    `era` ne sert plus (ancien decoupage en pages)."""
    bw = max(640, width - tab_w - 16)
    bh = max(440, height - HUD_HEIGHT - 14)
    bx = width - tab_w - bw - 8
    by = HUD_HEIGHT + 6
    detail_h = min(TECH_DETAIL_H, max(120, bh // 3))
    detail_top = by + bh - 12 - detail_h
    # Une barre au-dessus de la toile : l'aide a gauche, zoom et Recentrer a droite.
    strip = (bx + 10, by + TECH_HEADER_H - 4, bw - 20, 28)
    top = strip[1] + strip[3] + 2
    view = (bx + 10, top, bw - 20, detail_top - 8 - top)
    world = tech_world()
    cam = clamp_cam(cam, view, world) if cam is not None else cam_on(view, world, None)
    nodes = {tid: to_screen(cam, view, rect) for tid, rect in world["nodes"].items()}
    visible = {}
    for tid, rect in nodes.items():
        c = _clip(rect, view)
        if c is not None:
            visible[tid] = c
    ww, wh = world["size"]
    mini_w = TREE_MINI_W
    mini_h = max(40, int(mini_w * wh / ww))
    minimap = (view[0] + view[2] - mini_w - 10, view[1] + view[3] - mini_h - 10, mini_w, mini_h)
    bxs = strip[0] + strip[2]
    center = (bxs - 96, strip[1] + 2, 96, 24)
    zoom_in = (center[0] - 6 - 28, strip[1] + 2, 28, 24)
    zoom_out = (zoom_in[0] - 4 - 28, strip[1] + 2, 28, 24)
    # La mini-carte ne sert a rien quand tout l'arbre est a l'ecran.
    minimap_on = cam[2] > tree_zoom_min(view, world) + 1e-6
    half = (bw - 40) // 2
    detail = (bx + 14, detail_top, bw - 28, detail_h)
    learn = (bx + bw - 14 - 12 - 170, detail_top + 7, 170, 28)
    current = (bx + bw - 14 - 460, by + 10, 460, 46)
    return {
        "box": (bx, by, bw, bh),
        "view": view,
        "cam": cam,
        "world": world,
        "nodes": nodes,
        "visible": visible,
        "minimap": minimap,
        "minimap_on": minimap_on,
        "strip": strip,
        "zoom_in": zoom_in,
        "zoom_out": zoom_out,
        "center": center,
        "detail": detail,
        "detail_cols": (
            (bx + 24, detail_top + 44, half - 10, detail_h - 50),
            (bx + 26 + half, detail_top + 44, half - 20, detail_h - 50),
        ),
        "learn": learn,
        "current": current,
        "pages": {},
    }


SIDE_TABS = (
    ("savoirs", "Savoirs"),
    ("tribu", "Tribu"),
    ("peuples", "Peuples"),
    ("journal", "Journal"),
)


# L'onglet Armee n'apparait qu'avec le premier village (render_panels.draw_army),
# l'onglet Commerce aussi (il ouvre l'ecran du commerce, render_trade.py).
ARMY_TAB = ("armee", "Armee")
COMMERCE_TAB = ("commerce", "Commerce")


def side_tabs(army: bool = False, commerce: bool = False) -> tuple:
    return SIDE_TABS + ((ARMY_TAB,) if army else ()) + ((COMMERCE_TAB,) if commerce else ())


def side_layout(width: int, height: int, panel: str | None = None, era: int = 0, army: bool = False, commerce: bool = False, tech_cam=None) -> dict:
    tab_w, gap = 32, 6
    tab_x = width - tab_w
    top = HUD_HEIGHT + 40
    shown = side_tabs(army, commerce)
    n = len(shown)
    tab_h = max(60, min(104, (height - top - 8 - gap * (n - 1)) // n))
    tabs = {key: (tab_x, top + i * (tab_h + gap), tab_w, tab_h) for i, (key, _l) in enumerate(shown)}
    tab_d = tabs["savoirs"]
    tab_j = tabs["journal"]
    items: dict = {}
    box = (0, 0, 0, 0)
    tech_panel = None
    priority: tuple = ()
    if panel == "savoirs":
        tech_panel = tech_panel_layout(width, height, tab_w, era, tech_cam)
        box = tech_panel["box"]
        # Seuls les savoirs dans la vue se cliquent (la toile deborde).
        for tid, rect in tech_panel["visible"].items():
            items[f"tech:{tid}"] = rect
        items["learn"] = tech_panel["learn"]
        items["tview"] = tech_panel["view"]
        for key in ("zoom_in", "zoom_out", "center"):
            items["t" + key] = tech_panel[key]
        if tech_panel["minimap_on"]:
            items["tminimap"] = tech_panel["minimap"]
        priority = ("tminimap", "tzoom_in", "tzoom_out", "tcenter")
    elif panel in ("tribu", "peuples", "armee"):
        from src.kora.render_panels import panel_box

        box = panel_box(width, height, "tribu" if panel == "armee" else panel, tab_w)
    elif panel == "journal":
        box_w = 288
        box_h = min(420, max(280, height - HUD_HEIGHT - 28))
        bx = width - tab_w - box_w
        by = HUD_HEIGHT + 14
        if by + box_h > height - 12:
            box_h = max(240, height - by - 12)
        box = (bx, by, box_w, box_h)
        x = bx + 12
        y = by + 42
        row_right = bx + box_w - 12
        for key, _label, cw in FILTER_CHIPS:
            if x + cw > row_right:
                x = bx + 12
                y += 26
            items[key] = (x, y, cw, 22)
            x += cw + 6
        y += 32
        x = bx + 12
        for key, _label, cw in SORT_CHIPS:
            items[key] = (x, y, cw, 22)
            x += cw + 8
    return {
        "box": box,
        "tab": tab_d,
        "tab_savoirs": tab_d,
        "tab_journal": tab_j,
        "tabs": tabs,
        "items": items,
        "priority": priority,
        "panel": panel,
        "tech": tech_panel,
    }


def side_hit(layout: dict, mx: int, my: int):
    for key, rect in layout.get("tabs", {}).items():
        if _contains(rect, mx, my):
            return f"tab_{key}"
    if _contains(layout["tab_savoirs"], mx, my):
        return "tab_savoirs"
    if _contains(layout["tab_journal"], mx, my):
        return "tab_journal"
    # Les commandes posees sur la toile des savoirs passent avant.
    for key in layout.get("priority", ()):
        rect = layout["items"].get(key)
        if rect is not None and _contains(rect, mx, my):
            return key
    # Un bouton dans une rangee : le plus petit cadre sous la souris gagne.
    best, best_area = None, None
    for key, rect in layout["items"].items():
        if _contains(rect, mx, my):
            area = rect[2] * rect[3]
            if best_area is None or area < best_area:
                best, best_area = key, area
    if best is not None:
        return best
    box = layout["box"]
    if layout.get("panel") and box[2] > 0 and _contains(box, mx, my):
        return "panel"
    return None


def col_pixel_width(zoom: float) -> float:
    return HEX_SIZE * zoom * math.sqrt(3)


def row_pixel_height(zoom: float) -> float:
    return HEX_SIZE * zoom * 1.5


def world_pixel_size(world, zoom: float) -> tuple[float, float]:
    return col_pixel_width(zoom) * world.width, row_pixel_height(zoom) * world.height


def min_zoom_for(world, screen_w: int, screen_h: int) -> float:
    return 0.11


def terrain_draw_mode(zoom: float) -> str:
    return "sphere"


def wrap_camera(world, camera_x: float, camera_y: float, zoom: float, screen_w: int, screen_h: int):
    wpw, wph = world_pixel_size(world, zoom)
    if world.wrap_x and wpw > screen_w:
        camera_x %= wpw
        if camera_x < 0:
            camera_x += wpw
    elif wpw <= screen_w:
        camera_x = (wpw - screen_w) / 2.0
    if wph <= screen_h:
        camera_y = (wph - screen_h) / 2.0
    else:
        camera_y = max(0.0, min(camera_y, wph - screen_h))
    return camera_x, camera_y


def offset_to_pixel(
    col: int, row: int, camera_x: float, camera_y: float, zoom: float
) -> tuple[float, float]:
    size = HEX_SIZE * zoom
    x = size * math.sqrt(3) * (col + 0.5 * (row & 1)) - camera_x
    y = size * 1.5 * row - camera_y
    return x, y


def hex_to_pixel(
    h: Hex, camera_x: float, camera_y: float, zoom: float
) -> tuple[float, float]:
    col, row = axial_to_offset(h)
    return offset_to_pixel(col, row, camera_x, camera_y, zoom)


SWORD_LIFT = 18
STACK_SHIFT = 20


def band_radius(population: int, dist: float) -> int:
    # Taille fixe (le monde est grand) : seul le zoom la change, pas le nombre
    # de gens (il s'affiche a cote).
    return max(4, min(9, int(4 + 1.2 / max(0.2, dist - 1.0))))


def band_screen_positions(state, yaw, pitch, gcx, gcy, focal, dist) -> dict:
    # Bandes visibles par le joueur -> (x, y, rayon) a l'ecran. Plusieurs
    # bandes sur la meme case sont decalees pour rester cliquables une a une.
    out: dict = {}
    stack: dict = {}
    for band in sorted(state.bands.values(), key=lambda b: b.id):
        if band.population <= 0:
            continue
        if band.tribe_id != PLAYER_TRIBE_ID and not enemy_band_visible(state, band):
            continue
        pos = hex_to_globe_screen(
            band.position, state.world, yaw, pitch, gcx, gcy, focal, dist
        )
        if pos is None:
            continue
        k = stack.get(band.position, 0)
        stack[band.position] = k + 1
        radius = band_radius(band.population, dist)
        shift = max(STACK_SHIFT, radius * 1.3)
        out[band.id] = (pos[0] + k * shift, pos[1] + k * shift * 0.45, radius)
    return out


def fight_mark_screen_pos(
    mark, world, globe_yaw, globe_pitch, gcx, gcy, focal, dist
):
    pos = hex_to_globe_screen(
        mark.hex, world, globe_yaw, globe_pitch, gcx, gcy, focal, dist
    )
    if pos is None:
        return None
    return (pos[0], pos[1] - SWORD_LIFT)


def _draw_crown(surf: pygame.Surface, cx: int, cy: int) -> None:
    gold = (236, 196, 80)
    pts = [(cx - 6, cy + 3), (cx - 6, cy - 3), (cx - 3, cy), (cx, cy - 5), (cx + 3, cy), (cx + 6, cy - 3), (cx + 6, cy + 3)]
    pygame.draw.polygon(surf, gold, pts)
    pygame.draw.polygon(surf, (90, 64, 20), pts, 1)


def _draw_camp(surf: pygame.Surface, cx: int, cy: int, color, size: int) -> None:
    pts = [(cx, cy - size), (cx - size, cy + size * 0.7), (cx + size, cy + size * 0.7)]
    pygame.draw.polygon(surf, color, pts)
    pygame.draw.polygon(surf, (24, 20, 16), pts, 1)
    pygame.draw.line(surf, (24, 20, 16), (cx, cy - size), (cx, cy + size * 0.7), 1)


def _draw_cache(surf: pygame.Surface, cx: int, cy: int, color, size: int) -> None:
    rect = (cx - size, cy - size // 2, size * 2, size + 1)
    pygame.draw.rect(surf, (150, 110, 70), rect, border_radius=2)
    pygame.draw.rect(surf, (40, 28, 18), rect, 1, border_radius=2)
    pygame.draw.circle(surf, color, (cx, cy), max(1, size // 2))


def _ring(surf: pygame.Surface, color, cx: int, cy: int, r: int, square: bool) -> None:
    """Anneau de selection ou d'alerte : carre autour d'un village."""
    if square:
        pygame.draw.rect(surf, color, (cx - r, cy - r, 2 * r, 2 * r), 2)
    else:
        pygame.draw.circle(surf, color, (cx, cy), r, 2)


def _draw_troop(surf: pygame.Surface, cx: int, cy: int, color, size: int) -> None:
    s = size
    for dx in (-s // 2, s // 2):
        pygame.draw.line(surf, (60, 44, 28), (cx + dx - s // 3, cy + s), (cx + dx + s // 3, cy - s - 3), 2)
        tip = (cx + dx + s // 3, cy - s - 3)
        pygame.draw.polygon(surf, (220, 214, 200), [tip, (tip[0] - 3, tip[1] + 5), (tip[0] + 2, tip[1] + 5)])
    shield = [(cx - s, cy - s + 2), (cx + s, cy - s + 2), (cx + s - 1, cy + 2), (cx, cy + s + 2), (cx - s + 1, cy + 2)]
    pygame.draw.polygon(surf, color, shield)
    pygame.draw.polygon(surf, _darken(color, 0.4), shield, 2)
    pygame.draw.line(surf, _darken(color, 0.4), (cx, cy - s + 3), (cx, cy + s), 1)


def _draw_sword(surf: pygame.Surface, cx: int, cy: int, lit: bool) -> None:
    blade = (235, 230, 220) if lit else (210, 205, 195)
    guard = (196, 150, 60) if lit else (160, 120, 50)
    pygame.draw.line(surf, blade, (cx, cy - 11), (cx, cy + 7), 3)
    pygame.draw.line(surf, guard, (cx - 7, cy + 1), (cx + 7, cy + 1), 3)
    pygame.draw.circle(surf, guard, (cx, cy + 10), 3)


def hex_screen_positions(h: Hex, camera_x: float, camera_y: float, zoom: float, world):
    col, row = axial_to_offset(h)
    shifts = (0,)
    if world.wrap_x:
        shifts = (-world.width, 0, world.width)
    return [
        offset_to_pixel(col + dc, row, camera_x, camera_y, zoom) for dc in shifts
    ]


def _cube_round(q: float, r: float) -> Hex:
    s = -q - r
    rq, rr, rs = round(q), round(r), round(s)
    q_diff, r_diff, s_diff = abs(rq - q), abs(rr - r), abs(rs - s)
    if q_diff > r_diff and q_diff > s_diff:
        rq = -rr - rs
    elif r_diff > s_diff:
        rr = -rq - rs
    return Hex(int(rq), int(rr))


def pixel_to_hex(
    x: float,
    y: float,
    camera_x: float,
    camera_y: float,
    zoom: float,
    world,
) -> Hex | None:
    size = HEX_SIZE * zoom
    if size <= 0:
        return None
    px = x + camera_x
    py = y + camera_y
    r = py / (size * 1.5)
    q = px / (size * math.sqrt(3)) - r / 2.0
    h = _cube_round(q, r)
    return world.canonicalize(h)


def _lighten(color, factor: float) -> tuple[int, int, int]:
    return tuple(int(c + (255 - c) * factor) for c in color[:3])


def _darken(color: tuple[int, int, int], factor: float) -> tuple[int, int, int]:
    return (
        int(color[0] * factor),
        int(color[1] * factor),
        int(color[2] * factor),
    )


def _hex_corners(cx: float, cy: float, zoom: float) -> list[tuple[float, float]]:
    size = HEX_SIZE * zoom
    pts = []
    for i in range(6):
        angle = math.radians(60 * i - 30)
        pts.append((cx + size * math.cos(angle), cy + size * math.sin(angle)))
    return pts


class Renderer:
    def __init__(self, screen: pygame.Surface) -> None:
        self.screen = screen
        self.font = pygame.font.SysFont("consolas", 16)
        self.small = pygame.font.SysFont("consolas", 14)
        self.tiny = pygame.font.SysFont("consolas", 12)
        self.atlas_font = pygame.font.SysFont("georgia", 22)
        self.atlas_small = pygame.font.SysFont("georgia", 16)
        self.hud_hits = hud_layout(screen.get_width())
        self.menu_hits = menu_layout(screen.get_width(), screen.get_height())
        self.side_hits = side_layout(screen.get_width(), screen.get_height())
        self.decisions_hits = self.side_hits
        self.fight_hits: dict = {}
        self._atlas = None
        self._atlas_key = None
        self._planet: Planet | None = None
        self._layer: pygame.Surface | None = None
        self._layer_key = None
        self._layer_fine = False
        self.band_hits: dict = {}
        self.toast_hits: list = []
        # "zones" (teinte des zones d'influence) ou "relief".
        self.map_mode = "zones"
        self.mode_hits: dict = {}
        self.panel_hits: dict = {}
        self.event_hits: dict = {}
        # Ecran du village, fenetre de fondation (render_village.py).
        self.village_hits: dict = {}
        self.village_armies: list = []
        self.found_hits: dict = {}
        # Ecran du commerce (render_trade.py).
        self.trade_hits: dict = {}
        self.trade_partners: list = []
        self.trade_routes: list = []
        self.trade_candidates: list = []

    def _atlas_labels(self, world):
        key = (id(world), world.width, world.height, world.wrap_x)
        if self._atlas is None or self._atlas_key != key:
            self._atlas = build_atlas_labels(world)
            self._atlas_key = key
        return self._atlas

    def _outlined_text(self, font, text: str, color, cx: float, cy: float, target=None) -> None:
        target = self.screen if target is None else target
        shadow = (20, 18, 14)
        surf = font.render(text, True, color)
        x = int(cx - surf.get_width() / 2)
        y = int(cy - surf.get_height() / 2)
        outline = font.render(text, True, shadow)
        for ox, oy in ((-1, 0), (1, 0), (0, -1), (0, 1), (-1, -1), (1, 1)):
            target.blit(outline, (x + ox, y + oy))
        target.blit(surf, (x, y))

    def _planet_for(self, world) -> Planet:
        if self._planet is None or self._planet.world is not world:
            self._planet = Planet(world)
            self._layer_key = None
        return self._planet

    def _draw_sphere(self, state: GameState, yaw: float, pitch: float, zoom: float) -> None:
        # La planete est peinte dans un calque, repeint seulement si la vue,
        # le brouillard ou les saisons changent ; sinon on le recopie.
        planet = self._planet_for(state.world)
        sw, sh = self.screen.get_size()
        cx, cy, focal, dist = view_params(zoom, sw, sh, HUD_HEIGHT)
        planet.zones_on = self.map_mode == "zones"
        planet.res_on = self.map_mode == "ressources"
        planet.trade_on = self.map_mode == "commerce"
        if planet.zones_on:
            planet.sync_zones(state)
        key = (
            sw,
            sh,
            yaw,
            pitch,
            dist,
            planet.sync_fog(state),
            planet.season_gen(),
            planet.zone_key(),
        )
        layer = self._layer
        if layer is None or layer.get_size() != (sw, sh):
            layer = self._layer = pygame.Surface((sw, sh))
            self._layer_key = None
        if self._layer_key != key:
            # Vue qui change (glisser, zoom) : image rapide...
            self._paint_planet(layer, state, planet, yaw, pitch, cx, cy, focal, dist, FAST_SAMPLES)
            self._layer_key = key
            self._layer_fine = False
        elif not self._layer_fine:
            # ...puis nette des que la vue s'arrete.
            self._paint_planet(layer, state, planet, yaw, pitch, cx, cy, focal, dist, FINE_SAMPLES)
            self._layer_fine = True
        self.screen.blit(layer, (0, 0))

    def _paint_planet(
        self, target, state, planet, yaw, pitch, cx, cy, focal, dist, samples
    ) -> None:
        sw, sh = target.get_size()
        target.fill((6, 8, 14))
        limb = focal / math.sqrt(max(1e-4, dist * dist - 1.0))
        # Sous les cases : le noir du brouillard. L'eau exploree est dessinee
        # case par case, sinon l'ocean trahirait la forme des terres inconnues.
        if limb < max(sw, sh) * 2.4:
            pygame.draw.circle(target, (70, 110, 150), (int(cx), int(cy)), int(limb + 6))
            pygame.draw.circle(
                target, FOG_UNEXPLORED, (int(cx), int(cy)), max(1, int(limb + 1))
            )
        if hex_screen_px(state.world, focal, dist) >= POLY_HEX_PX:
            planet.draw_hexes(target, state, yaw, pitch, cx, cy, focal, dist)
        else:
            clip = pygame.Rect(0, HUD_HEIGHT, sw, sh - HUD_HEIGHT)
            painted = planet.texture(state, yaw, pitch, cx, cy, focal, dist, clip, samples)
            if painted is not None:
                surf, pos = painted
                target.blit(surf, pos)
        if limb < min(sw, sh) * 0.9:
            pygame.draw.circle(target, (170, 200, 230), (int(cx), int(cy)), int(limb + 1), 1)
        if dist >= 1.72:
            self._draw_atlas_globe(target, state, planet, yaw, pitch, cx, cy, focal, dist)

    def _draw_atlas_globe(self, target, state, planet, yaw, pitch, cx, cy, focal, dist) -> None:
        world = state.world
        for lab in self._atlas_labels(world):
            col = int(lab.col) % world.width
            row = max(0, min(world.height - 1, int(lab.row)))
            if not planet.explored_at(col, row):
                continue
            hx = offset_to_axial(col, row)
            pos = hex_to_globe_screen(hx, world, yaw, pitch, cx, cy, focal, dist)
            if pos is None:
                continue
            font = self.atlas_font if lab.kind in ("land", "ice") else self.atlas_small
            color = (190, 220, 240) if lab.kind == "sea" else (255, 244, 214)
            self._outlined_text(font, lab.name, color, pos[0], pos[1], target)

    def draw(
        self,
        state: GameState,
        camera_x: float,
        camera_y: float,
        zoom: float,
        selected_id: int | None,
        menu_open: bool = False,
        globe_yaw: float = 0.0,
        globe_pitch: float = 0.0,
        side_panel: str | None = None,
        log_filter: str = FILTER_ALL,
        log_newest: bool = True,
        toasts: list | None = None,
        hover_info: dict | None = None,
        pin_info: dict | None = None,
        tech_pick: str | None = None,
        open_fight=None,
        ui: dict | None = None,
    ) -> None:
        self.screen.fill((6, 8, 14))
        w, h = self.screen.get_size()
        self._draw_sphere(state, globe_yaw, globe_pitch, zoom)
        gcx, gcy, focal, dist = view_params(zoom, w, h, HUD_HEIGHT)
        if self.map_mode == "commerce":
            self.draw_trade_routes(state, globe_yaw, globe_pitch, gcx, gcy, focal, dist)
        self.draw_sites(state, globe_yaw, globe_pitch, gcx, gcy, focal, dist)
        if self.map_mode == "commerce":
            self.draw_trade_marks(state, globe_yaw, globe_pitch, gcx, gcy, focal, dist)
        spots = band_screen_positions(
            state, globe_yaw, globe_pitch, gcx, gcy, focal, dist
        )
        tags = []
        for band_id, (bx, by, radius) in spots.items():
            band = state.bands[band_id]
            if bx < -40 or by < -40 or bx > w + 40 or by > h + 40:
                continue
            colr = color_of(state.tribes.get(band.tribe_id))
            ix, iy = int(bx), int(by)
            if band.village:
                # Une bande installee se dessine en maisons : c'est un village.
                site = state.sites.get(band.village)
                if site is not None:
                    self.draw_village_icon(site, ix, iy, colr, max(6, radius + 2))
            elif band.kind == "armee":
                # Une troupe : un bouclier a la couleur du peuple, deux lances.
                _draw_troop(self.screen, ix, iy, colr, max(6, radius))
            else:
                pygame.draw.circle(self.screen, colr, (ix, iy), radius)
                pygame.draw.circle(self.screen, _darken(colr, 0.45), (ix, iy), radius, 1)
            if band.tribe_id == PLAYER_TRIBE_ID and not chiefs.is_chief_band(state, band):
                # Clan qui se detache : anneau orange (indocile), rouge (pret a partir).
                if band.loyalty < chiefs.LEAVE:
                    _ring(self.screen, (230, 70, 60), ix, iy, radius + 5, band.village)
                elif band.loyalty < chiefs.OBEY:
                    _ring(self.screen, (235, 160, 60), ix, iy, radius + 5, band.village)
            if chiefs.is_chief_band(state, band):
                _draw_crown(self.screen, ix, iy - radius - (8 if band.village else 5))
            if selected_id == band.id:
                _ring(self.screen, (255, 255, 255), ix, iy, radius + (5 if band.village else 3), band.village)
            if dist <= LABEL_DIST:
                tags.append((str(band.population), bx + radius + 4, by))
        self.draw_fight_marks(state, globe_yaw, globe_pitch, zoom, open_fight)
        self.draw_polity_labels(state, globe_yaw, globe_pitch, gcx, gcy, focal, dist)
        if selected_id is not None and selected_id in state.bands:
            self.draw_path(
                state,
                state.bands[selected_id],
                camera_x,
                camera_y,
                zoom,
                globe_yaw,
                globe_pitch,
            )
        for tag, tx, ty in tags:
            tw = self.tiny.size(tag)[0]
            self._outlined_text(self.tiny, tag, (250, 246, 232), tx + tw / 2, ty)
        self.draw_hud(state)
        self._legend_state = state
        extra_y = HUD_HEIGHT + 8
        if state.player_dead:
            extra_y += 22
        if state.last_error:
            extra_y += 18
        ui = ui or {}
        self.draw_map_modes()
        self.draw_toasts(toasts or [], extra_y)
        self.draw_inspect(hover_info, pin_info)
        self.draw_band_card(state, selected_id)
        self.draw_fight_panel(open_fight, state)
        from src.kora import render_panels

        # Les cartes d'evenement restent sous les panneaux ouverts.
        render_panels.draw_event_cards(self, state, ui)
        self.draw_side(state, side_panel, log_filter, log_newest, tech_pick, ui)
        from src.kora import render_village

        if ui.get("village_open") is not None:
            render_village.draw_village(self, state, ui)
        else:
            self.village_hits = {}
        if ui.get("found") is not None:
            render_village.draw_found(self, state, ui)
        else:
            self.found_hits = {}
        if ui.get("trade_open"):
            from src.kora import render_trade

            render_trade.draw_trade(self, state, ui)
        else:
            self.trade_hits = {}
        if ui.get("event_open") is not None:
            render_panels.draw_event_modal(self, state, ui)
        if menu_open:
            self.draw_menu()

    def draw_band_card(self, state: GameState, selected_id: int | None) -> None:
        band = state.bands.get(selected_id) if selected_id is not None else None
        if band is None or band.tribe_id != PLAYER_TRIBE_ID or band.village:
            # Un village se gere dans son ecran (render_village.py).
            self.band_hits = {}
            return
        info = band_summary(state, band.id)
        lines = band_lines(info)
        w, h = self.screen.get_size()
        layout = band_card_layout(w, h, len(lines))
        self.band_hits = layout
        bx, by, bw, bh = layout["box"]
        pygame.draw.rect(self.screen, (18, 20, 24), (bx, by, bw, bh), border_radius=5)
        pygame.draw.rect(
            self.screen, color_of(state.tribes.get(band.tribe_id)), (bx, by, bw, bh), 1, border_radius=5
        )
        warn_from = band_warn_from(info)
        yy = by + 10
        for i, line in enumerate(lines):
            font = self.small if i == 0 else self.tiny
            if i >= warn_from:
                color = (230, 170, 90)
            elif i >= 3:
                color = (190, 205, 225)
            else:
                color = (230, 228, 220) if i == 0 else (200, 198, 190)
            self.screen.blit(font.render(self._fit(font, line, bw - 24), True, color), (bx + 12, yy))
            yy += 18 if i == 0 else 16
        actions = orders.band_actions(state, band.id)
        mx, my = pygame.mouse.get_pos()
        labels = dict(BAND_BUTTONS)
        labels.update(orders.labels(state, band.id))
        hint = BAND_HINT
        for key, rect in layout["buttons"].items():
            on = not actions.get(key, "?")
            if _contains(rect, mx, my) and actions.get(key):
                hint = actions[key]
            hover = on and _contains(rect, mx, my)
            fill = (196, 150, 60) if hover else (42, 46, 52) if on else (28, 30, 34)
            pygame.draw.rect(self.screen, fill, rect, border_radius=3)
            pygame.draw.rect(
                self.screen,
                (210, 180, 90) if on else (70, 74, 80),
                rect,
                1,
                border_radius=3,
            )
            col = (20, 18, 14) if hover else (230, 228, 220) if on else (110, 112, 116)
            surf = self.tiny.render(labels[key], True, col)
            self.screen.blit(
                surf,
                (
                    rect[0] + (rect[2] - surf.get_width()) // 2,
                    rect[1] + (rect[3] - surf.get_height()) // 2,
                ),
            )
        warn = hint != BAND_HINT
        hint_s = self.tiny.render(self._fit(self.tiny, hint, bw - 24), True, (220, 170, 120) if warn else (140, 142, 146))
        self.screen.blit(hint_s, (bx + 12, by + bh - 8 - 16))

    def draw_trade_marks(self, state: GameState, yaw, pitch, gcx, gcy, focal, dist) -> None:
        """Mode Commerce : sur chaque village connu, les biens que son peuple
        a en reserve (pastilles ; plus grosses quand il en a de trop) ; vos
        partenaires entoures d'or ; la portee de vos porteurs autour de vos
        villages."""
        from src.kora import goods
        from src.kora.globe import offset_to_xyz, project_xyz, rotate_xyz
        from src.kora.vision import is_explored

        world = state.world
        w, h = self.screen.get_size()
        partners = set(goods.partners(state, PLAYER_TRIBE_ID))
        heart = chiefs.chief_band(state, PLAYER_TRIBE_ID)
        heart_hex = heart.position if heart is not None and heart.village else None
        reach = goods.trade_range(state, PLAYER_TRIBE_ID, PLAYER_TRIBE_ID)
        self._legend_world = world
        for site in sorted(state.sites.values(), key=lambda s: s.id):
            if site.kind != "village":
                continue
            own = site.tribe_id == PLAYER_TRIBE_ID
            if not own and not is_explored(state, site.hex):
                continue
            pos = hex_to_globe_screen(site.hex, world, yaw, pitch, gcx, gcy, focal, dist)
            if pos is None:
                continue
            x, y = int(pos[0]), int(pos[1])
            if x < -30 or y < HUD_HEIGHT or x > w + 30 or y > h + 30:
                continue
            if site.tribe_id in partners:
                pygame.draw.circle(self.screen, (226, 190, 106), (x, y), 12, 2)
            held = [g for g in goods.GOODS if goods.stock(state, site.tribe_id, g) >= 1.0]
            ox = x - (len(held) * 7) // 2 + 3
            for g in held:
                big = goods.spare(state, site.tribe_id, g) >= 1.0
                r_ = 4 if big else 3
                pygame.draw.circle(self.screen, goods.GOOD_COLORS[g], (ox, y - 14), r_)
                pygame.draw.circle(self.screen, (20, 20, 20), (ox, y - 14), r_, 1)
                ox += 7
            if not own and heart_hex is not None and world.distance(site.hex, heart_hex) <= reach and site.tribe_id not in partners:
                # A portee de vos porteurs : un petit repere.
                pygame.draw.circle(self.screen, (150, 190, 220), (x, y), 10, 1)
        if heart_hex is not None:
            self._draw_reach(heart_hex, reach, yaw, pitch, gcx, gcy, focal, dist)

    def _draw_reach(self, center, reach, yaw, pitch, gcx, gcy, focal, dist) -> None:
        """La portee des porteurs autour du village du chef : un anneau fin
        de points sur le globe."""
        from src.kora.globe import offset_to_xyz, project_xyz, rotate_xyz

        world = self._legend_world
        c, r_ = axial_to_offset(center)
        cx0, cy0, cz0 = offset_to_xyz(c, r_, world.width, world.height)
        ang = 2.0 * math.pi * reach / max(1, world.width)
        ux, uy, uz = (-cz0, 0.0, cx0) if abs(cy0) < 0.9 else (1.0, 0.0, 0.0)
        n = math.sqrt(ux * ux + uy * uy + uz * uz) or 1.0
        ux, uy, uz = ux / n, uy / n, uz / n
        vx, vy, vz = cy0 * uz - cz0 * uy, cz0 * ux - cx0 * uz, cx0 * uy - cy0 * ux
        ca, sa = math.cos(ang), math.sin(ang)
        for k in range(180):
            t = 2.0 * math.pi * k / 180
            px = cx0 * ca + (ux * math.cos(t) + vx * math.sin(t)) * sa
            py = cy0 * ca + (uy * math.cos(t) + vy * math.sin(t)) * sa
            pz = cz0 * ca + (uz * math.cos(t) + vz * math.sin(t)) * sa
            rx, ry, rz = rotate_xyz(px, py, pz, yaw, pitch)
            pos = project_xyz(rx, ry, rz, gcx, gcy, focal, dist)
            if pos is not None:
                pygame.draw.circle(self.screen, (150, 190, 220), (int(pos[0]), int(pos[1])), 1)

    def draw_polity_labels(self, state: GameState, yaw, pitch, gcx, gcy, focal, dist) -> None:
        """Les proto-pays : le nom de chaque peuple fixe, au-dessus de ses
        villages (ceux que vous connaissez), a sa couleur."""
        if dist > 2.9:
            return
        from src.kora.globe import offset_to_xyz, project_xyz, rotate_xyz
        from src.kora.vision import is_explored

        world = state.world
        homes: dict = {}
        for site in sorted(state.sites.values(), key=lambda s: s.id):
            if site.kind != "village":
                continue
            if site.tribe_id != PLAYER_TRIBE_ID and not is_explored(state, site.hex):
                continue
            homes.setdefault(site.tribe_id, []).append(site.hex)
        font = self.small if dist <= LABEL_DIST else self.tiny
        for tid, hexes in sorted(homes.items()):
            tribe = state.tribes.get(tid)
            if tribe is None:
                continue
            x = y = z = 0.0
            for h in hexes:
                c, r_ = axial_to_offset(h)
                px, py, pz = offset_to_xyz(c, r_, world.width, world.height)
                x, y, z = x + px, y + py, z + pz
            n = math.sqrt(x * x + y * y + z * z) or 1.0
            x, y, z = rotate_xyz(x / n, y / n, z / n, yaw, pitch)
            pos = project_xyz(x, y, z, gcx, gcy, focal, dist)
            if pos is None:
                continue
            label = " ".join(tribe.name.upper())
            color = _lighten(color_of(tribe), 0.35)
            self._outlined_text(font, label, color, pos[0], pos[1] - (22 if dist <= LABEL_DIST else 12))

    def draw_trade_routes(self, state: GameState, yaw, pitch, gcx, gcy, focal, dist) -> None:
        """Les routes commerciales : un chemin en pointilles a la couleur du
        bien, entre les deux villages ; un porteur y marche quand la route a
        porte quelque chose le dernier mois. Les votres partout ; celles des
        autres quand vous connaissez les deux villages."""
        d = getattr(state, "diplo", None)
        if d is None or not getattr(d, "routes", None):
            return
        from src.kora import goods
        from src.kora.globe import offset_to_xyz, project_xyz, rotate_xyz
        from src.kora.vision import is_explored

        world = state.world
        homes: dict = {}
        for site in state.sites.values():
            if site.kind == "village":
                homes.setdefault(site.tribe_id, []).append(site.hex)
        t_now = pygame.time.get_ticks() / 1000.0
        drawn = set()
        for i, route in enumerate(d.routes):
            if not goods._pact(state, route.exporter, route.importer):
                continue
            xs, ys = homes.get(route.exporter, []), homes.get(route.importer, [])
            if not xs or not ys:
                continue
            a, b = min(((x, y) for x in xs for y in ys), key=lambda p: world.distance(p[0], p[1]))
            mine = PLAYER_TRIBE_ID in (route.exporter, route.importer)
            if not mine and not (is_explored(state, a) and is_explored(state, b)):
                continue
            key = (a, b, route.good)
            if key in drawn:
                continue
            drawn.add(key)
            ca, ra = axial_to_offset(a)
            cb, rb = axial_to_offset(b)
            pa = offset_to_xyz(ca, ra, world.width, world.height)
            pb = offset_to_xyz(cb, rb, world.width, world.height)
            steps = max(6, min(40, world.distance(a, b)))
            pts = []
            for k in range(steps + 1):
                t = k / steps
                x = pa[0] * (1 - t) + pb[0] * t
                y = pa[1] * (1 - t) + pb[1] * t
                z = pa[2] * (1 - t) + pb[2] * t
                n = math.sqrt(x * x + y * y + z * z) or 1.0
                x, y, z = rotate_xyz(x / n, y / n, z / n, yaw, pitch)
                pts.append(project_xyz(x, y, z, gcx, gcy, focal, dist))
            color = goods.GOOD_COLORS.get(route.good, (220, 210, 170))
            if route.units <= 0:
                color = _darken(color, 0.55)
            if route.units > 0:
                # Une route qui porte : trait plein, epais selon la charge, et
                # des porteurs (un par convoi) qui vont du vendeur a l'acheteur.
                width = max(1, min(5, int(1 + route.units / 1.5))) if mine else max(1, min(3, int(route.units / 2)))
                for k in range(len(pts) - 1):
                    if pts[k] is not None and pts[k + 1] is not None:
                        pygame.draw.line(self.screen, _darken(color, 0.5), pts[k], pts[k + 1], width + 2)
                        pygame.draw.line(self.screen, color, pts[k], pts[k + 1], width)
                for c in range(max(1, route.level)):
                    t = (t_now * 0.10 + i * 0.37 + c / max(1, route.level)) % 1.0
                    idx = min(len(pts) - 1, int(t * (len(pts) - 1)))
                    if pts[idx] is not None:
                        px, py = int(pts[idx][0]), int(pts[idx][1])
                        pygame.draw.circle(self.screen, (250, 244, 226), (px, py), 3 if mine else 2)
                        pygame.draw.circle(self.screen, (20, 20, 20), (px, py), 3 if mine else 2, 1)
            else:
                # Rien porte le dernier mois : pointilles pales.
                for k in range(0, len(pts) - 1, 2):
                    if pts[k] is not None and pts[k + 1] is not None:
                        pygame.draw.line(self.screen, color, pts[k], pts[k + 1], 1)

    def draw_sites(self, state: GameState, yaw, pitch, gcx, gcy, focal, dist) -> None:
        """Campements et caches : les siens partout ou l'on est alle, ceux des
        autres seulement sous les yeux de vos bandes."""
        from src.kora.vision import is_explored, is_visible

        w, h = self.screen.get_size()
        size = 7 if dist <= LABEL_DIST else 4
        for site in sorted(state.sites.values(), key=lambda s: s.id):
            mine = site.tribe_id == PLAYER_TRIBE_ID
            seen = is_explored(state, site.hex) if mine else is_visible(state, site.hex)
            if not seen:
                continue
            if site.kind == "village":
                self.draw_fields(state, site, yaw, pitch, gcx, gcy, focal, dist)
            pos = hex_to_globe_screen(site.hex, state.world, yaw, pitch, gcx, gcy, focal, dist)
            if pos is None:
                continue
            x, y = int(pos[0]), int(pos[1])
            if x < -20 or y < HUD_HEIGHT or x > w + 20 or y > h + 20:
                continue
            color = color_of(state.tribes.get(site.tribe_id))
            if site.kind == "cache":
                _draw_cache(self.screen, x, y + size, color, max(3, size - 2))
            elif site.kind == "camp":
                _draw_camp(self.screen, x, y + size, color, size)
            # Le village lui-meme est dessine avec sa bande (draw).

    def draw_village_icon(self, site, x: int, y: int, color, size: int) -> None:
        """Un village : un carre a la couleur du peuple, bord sombre ; une
        palissade l'entoure d'un second cadre de bois."""
        from src.kora.villages import palisade_state

        half = max(4, size)
        rect = pygame.Rect(x - half, y - half, 2 * half, 2 * half)
        if palisade_state(site) == "built":
            outer = rect.inflate(8, 8)
            pygame.draw.rect(self.screen, (58, 42, 24), outer)
            pygame.draw.rect(self.screen, (168, 120, 64), outer, 2)
        pygame.draw.rect(self.screen, _darken(color, 0.35), rect.inflate(2, 2))
        pygame.draw.rect(self.screen, color, rect)
        inner = rect.inflate(-max(2, half // 2), -max(2, half // 2))
        pygame.draw.rect(self.screen, _darken(color, 0.7), inner, 1)

    def draw_fields(self, state, site, yaw, pitch, gcx, gcy, focal, dist) -> None:
        from src.kora.world import offset_to_axial

        w, h = self.screen.get_size()
        big = dist <= LABEL_DIST
        for col, row in site.data.get("fields", []):
            hx = offset_to_axial(col, row)
            pos = hex_to_globe_screen(hx, state.world, yaw, pitch, gcx, gcy, focal, dist)
            if pos is None:
                continue
            x, y = int(pos[0]), int(pos[1])
            if x < -10 or y < HUD_HEIGHT or x > w + 10 or y > h + 10:
                continue
            if big:
                rect = (x - 7, y - 4, 14, 9)
                pygame.draw.rect(self.screen, (196, 170, 80), rect, border_radius=2)
                for k in (-2, 1, 4):
                    pygame.draw.line(self.screen, (140, 116, 50), (x - 6, y + k - 1), (x + 6, y + k - 1), 1)
            else:
                pygame.draw.circle(self.screen, (206, 180, 90), (x, y), 2)

    def draw_map_modes(self) -> None:
        w, h = self.screen.get_size()
        layout = map_mode_layout(w, h)
        self.mode_hits = layout
        for key, label in MAP_MODES:
            self._draw_chip(layout[key], label, self.map_mode == key)
        if self.map_mode == "commerce":
            self._draw_trade_legend(layout, w)
        if self.map_mode == "ressources":
            from src.kora.resources import COLORS, LABELS, NAMES

            x0 = layout["relief"][0]
            y = layout["relief"][1] + 30
            bw = w - 40 - x0
            bh = 10 + 16 * ((len(NAMES) + 1) // 2)
            pygame.draw.rect(self.screen, (18, 20, 24), (x0, y, bw, bh), border_radius=5)
            pygame.draw.rect(self.screen, (70, 74, 80), (x0, y, bw, bh), 1, border_radius=5)
            for i, name in enumerate(NAMES):
                cx = x0 + 10 + (i % 2) * (bw // 2)
                cy = y + 6 + (i // 2) * 16
                pygame.draw.rect(self.screen, COLORS[name], (cx, cy + 2, 10, 10), border_radius=2)
                label = self._fit(self.tiny, LABELS[name], bw // 2 - 22)
                self.screen.blit(self.tiny.render(label, True, (210, 208, 200)), (cx + 14, cy))

    def _draw_trade_legend(self, layout, w) -> None:
        """Legende du mode Commerce : les biens, ce que disent les traits,
        et le commerce du mois."""
        from src.kora import goods

        state = getattr(self, "_legend_state", None)
        x0 = layout["relief"][0]
        y = layout["relief"][1] + 30
        bw = w - 40 - x0
        rows = [(goods.GOOD_COLORS[g], goods.GOOD_NAMES[g]) for g in goods.GOODS]
        notes = [
            "Trait plein : la route a porte le mois dernier",
            "Pointilles : rien porte",
            "Points blancs : les porteurs (un par convoi)",
            "Pastilles sur un village : biens en reserve",
            "Anneau dore : vos partenaires ; bleu : a portee",
            "Pointilles bleus : portee de vos porteurs",
        ]
        extra = []
        if state is not None:
            month = goods.last_month(state, PLAYER_TRIBE_ID)
            mine = goods.routes_of(state, PLAYER_TRIBE_ID)
            extra = [
                f"Vos routes : {len(mine)}, dont {sum(1 for r in mine if r.units > 0)} actives",
                f"Le mois dernier : +{month['sold']:.0f} / -{month['bought']:.0f} vivres",
                "Ecran du commerce : [M]",
            ]
        bh = 10 + 16 * ((len(rows) + 1) // 2) + 14 * (len(notes) + len(extra)) + 8
        pygame.draw.rect(self.screen, (18, 20, 24), (x0, y, bw, bh), border_radius=5)
        pygame.draw.rect(self.screen, (70, 74, 80), (x0, y, bw, bh), 1, border_radius=5)
        for i, (color, label) in enumerate(rows):
            cx = x0 + 10 + (i % 2) * (bw // 2)
            cy = y + 6 + (i // 2) * 16
            pygame.draw.circle(self.screen, color, (cx + 5, cy + 7), 5)
            self.screen.blit(self.tiny.render(self._fit(self.tiny, label, bw // 2 - 22), True, (210, 208, 200)), (cx + 14, cy))
        yy = y + 10 + 16 * ((len(rows) + 1) // 2)
        for text in notes:
            self.screen.blit(self.tiny.render(self._fit(self.tiny, text, bw - 20), True, (160, 162, 168)), (x0 + 10, yy))
            yy += 14
        yy += 4
        for text in extra:
            self.screen.blit(self.tiny.render(self._fit(self.tiny, text, bw - 20), True, (226, 190, 106)), (x0 + 10, yy))
            yy += 14

    def draw_fight_marks(
        self, state: GameState, globe_yaw, globe_pitch, zoom, open_fight
    ) -> None:
        w, h = self.screen.get_size()
        gcx, gcy, focal, dist = view_params(zoom, w, h, HUD_HEIGHT)
        for mark in state.fights:
            pos = fight_mark_screen_pos(
                mark, state.world, globe_yaw, globe_pitch, gcx, gcy, focal, dist
            )
            if pos is None:
                continue
            cx, cy = int(pos[0]), int(pos[1])
            if cx < -20 or cy < HUD_HEIGHT or cx > w + 20 or cy > h + 20:
                continue
            lit = open_fight is not None and open_fight.hex == mark.hex
            _draw_sword(self.screen, cx, cy, lit)

    def draw_fight_panel(self, mark, state: GameState | None = None) -> None:
        if mark is None:
            self.fight_hits = {}
            return
        if mark.report and state is not None:
            # Rapport de bataille (battle.py) : les camps, le moral, l'issue.
            from src.kora import render_village

            render_village.draw_battle(self, state, mark)
            return
        lines = fight_lines(mark)
        w, h = self.screen.get_size()
        layout = fight_panel_layout(w, h, len(lines))
        self.fight_hits = layout
        bx, by, bw, bh = layout["box"]
        pygame.draw.rect(self.screen, (18, 20, 24), (bx, by, bw, bh), border_radius=5)
        pygame.draw.rect(
            self.screen, (196, 80, 70), (bx, by, bw, bh), 1, border_radius=5
        )
        cx, cy, cw, ch = layout["close"]
        pygame.draw.rect(self.screen, (42, 46, 52), (cx, cy, cw, ch), border_radius=3)
        close_s = self.tiny.render("Fermer", True, (210, 208, 200))
        self.screen.blit(
            close_s,
            (
                cx + (cw - close_s.get_width()) // 2,
                cy + (ch - close_s.get_height()) // 2,
            ),
        )
        yy = by + 8
        for i, line in enumerate(lines):
            font = self.small if i == 0 else self.tiny
            color = (230, 228, 220) if i == 0 else (200, 198, 190)
            self.screen.blit(font.render(line, True, color), (bx + 10, yy))
            yy += 18 if i == 0 else 16

    def draw_path(
        self,
        state: GameState,
        band,
        camera_x: float,
        camera_y: float,
        zoom: float,
        globe_yaw: float = 0.0,
        globe_pitch: float = 0.0,
    ) -> None:
        if not band.path:
            return
        world = state.world
        sw, sh = self.screen.get_size()
        gcx, gcy, focal, dist = view_params(zoom, sw, sh, HUD_HEIGHT)
        pts = []
        for hx in [band.position, *band.path]:
            pos = hex_to_globe_screen(
                hx, world, globe_yaw, globe_pitch, gcx, gcy, focal, dist
            )
            if pos is not None:
                pts.append(pos)
        if len(pts) >= 2:
            pygame.draw.lines(self.screen, (255, 255, 240), False, pts, 2)
        if pts:
            tribe = state.tribes.get(band.tribe_id)
            weeks = travel_weeks(
                state.world,
                band.position,
                band.path,
                water_ok=bool(tribe and tribe.cabotage),
            )
            unit = "semaine" if weeks <= 1 else "semaines"
            label = self.small.render(f"{weeks} {unit}", True, (255, 255, 230))
            self.screen.blit(label, (pts[-1][0] + 8, pts[-1][1] - 12))

    def draw_menu(self) -> None:
        w, h = self.screen.get_size()
        overlay = pygame.Surface((w, h), pygame.SRCALPHA)
        overlay.fill((8, 10, 14, 160))
        self.screen.blit(overlay, (0, 0))
        layout = menu_layout(w, h)
        self.menu_hits = layout
        bx, by, bw, bh = layout["box"]
        pygame.draw.rect(self.screen, (22, 24, 28), (bx, by, bw, bh), border_radius=6)
        pygame.draw.rect(
            self.screen, (196, 150, 60), (bx, by, bw, bh), 1, border_radius=6
        )
        title = self.font.render("Kora", True, (230, 228, 220))
        self.screen.blit(title, (bx + (bw - title.get_width()) // 2, by + 18))
        mx, my = pygame.mouse.get_pos()
        labels = dict(MENU_ITEMS)
        for key, rect in layout["items"].items():
            x, y, rw, rh = rect
            hover = _contains(rect, mx, my)
            fill = (196, 150, 60) if hover else (42, 46, 52)
            pygame.draw.rect(self.screen, fill, (x, y, rw, rh), border_radius=3)
            pygame.draw.rect(
                self.screen, (210, 180, 90), (x, y, rw, rh), 1, border_radius=3
            )
            text_col = (20, 18, 14) if hover else (230, 228, 220)
            label = self.font.render(labels[key], True, text_col)
            self.screen.blit(
                label,
                (
                    x + (rw - label.get_width()) // 2,
                    y + (rh - label.get_height()) // 2,
                ),
            )

    def _draw_tab(self, rect, label: str, opened: bool, ready: bool = False) -> None:
        tx, ty, tw, th = rect
        mx, my = pygame.mouse.get_pos()
        hover_tab = _contains(rect, mx, my)
        if opened:
            fill = (196, 150, 60) if hover_tab else (48, 42, 32)
        elif ready:
            fill = (70, 90, 60) if hover_tab else (42, 46, 52)
        else:
            fill = (52, 56, 62) if hover_tab else (28, 30, 34)
        pygame.draw.rect(self.screen, fill, (tx, ty, tw, th), border_radius=4)
        pygame.draw.rect(
            self.screen,
            (210, 180, 90) if (opened or ready) else (90, 94, 100),
            (tx, ty, tw, th),
            1,
            border_radius=4,
        )
        tab_txt = self.small.render(label, True, (230, 228, 220))
        rotated = pygame.transform.rotate(tab_txt, 90)
        self.screen.blit(
            rotated,
            (
                tx + (tw - rotated.get_width()) // 2,
                ty + (th - rotated.get_height()) // 2,
            ),
        )

    def _draw_chip(self, rect, label: str, active: bool) -> None:
        x, y, rw, rh = rect
        mx, my = pygame.mouse.get_pos()
        hover = _contains(rect, mx, my)
        if active:
            fill = (196, 150, 60) if hover else (70, 90, 60)
            text_col = (20, 18, 14)
        else:
            fill = (52, 56, 62) if hover else (36, 40, 46)
            text_col = (210, 208, 200)
        pygame.draw.rect(self.screen, fill, (x, y, rw, rh), border_radius=3)
        pygame.draw.rect(
            self.screen, (210, 180, 90) if active else (70, 74, 80), (x, y, rw, rh), 1, border_radius=3
        )
        surf = self.tiny.render(label, True, text_col)
        self.screen.blit(
            surf,
            (
                x + (rw - surf.get_width()) // 2,
                y + (rh - surf.get_height()) // 2,
            ),
        )

    def draw_side(
        self,
        state: GameState,
        panel: str | None,
        log_filter: str = FILTER_ALL,
        log_newest: bool = True,
        tech_pick: str | None = None,
        ui: dict | None = None,
    ) -> None:
        ui = ui or {}
        w, h = self.screen.get_size()
        from src.kora import render_panels

        army = render_panels.army_ready(state)
        commerce = render_panels.commerce_ready(state)
        if panel == "savoirs" and ui.get("tech_cam") is None:
            # Premiere ouverture : la vue se pose sur la recherche en cours.
            from src.kora import render_tech

            ui["tech_cam"] = render_tech.focus_cam(state, w, h)
        layout = side_layout(
            w, h, panel=panel if (panel != "armee" or army) else None, era=ui.get("era", 0), army=army, commerce=commerce,
            tech_cam=ui.get("tech_cam"),
        )
        if layout.get("tech") is not None:
            ui["tech_cam"] = layout["tech"]["cam"]
        self.side_hits = layout
        if panel == "savoirs":
            self.draw_savoirs(state, layout["tech"], tech_pick)
        if panel in ("tribu", "peuples"):
            from src.kora import render_panels

            if panel == "tribu":
                render_panels.draw_tribe(self, state, layout, ui)
            else:
                render_panels.draw_peoples(self, state, layout, ui)
        if panel == "armee" and army:
            render_panels.draw_army(self, state, layout, ui)
        if panel == "journal":
            bx, by, bw, bh = layout["box"]
            pygame.draw.rect(self.screen, (18, 20, 24), (bx, by, bw, bh), border_radius=6)
            pygame.draw.rect(
                self.screen, (70, 74, 80), (bx, by, bw, bh), 1, border_radius=6
            )
            title = self.font.render("Journal", True, (230, 228, 220))
            self.screen.blit(title, (bx + 16, by + 14))
            labels = dict((k, lab) for k, lab, _w in FILTER_CHIPS)
            labels.update((k, lab) for k, lab, _w in SORT_CHIPS)
            for key, rect in layout["items"].items():
                if key.startswith("filter_"):
                    active = FILTER_BY_HIT[key] == log_filter
                elif key == "sort_recent":
                    active = log_newest
                else:
                    active = not log_newest
                self._draw_chip(rect, labels[key], active)
            log = state.log if isinstance(state.log, GameLog) else GameLog()
            rows = log.filtered(log_filter, newest_first=log_newest)
            list_y = layout["items"]["sort_recent"][1] + 30
            bottom = by + bh - 10
            for entry in rows:
                stamp = f"an {entry.year} s.{entry.week}"
                parts = wrap_text(f"{stamp}  {entry.text}", JOURNAL_COLS)
                if list_y + 16 * len(parts) > bottom:
                    break
                row_top = list_y
                placed = entry.hex is not None
                color = (240, 190, 150) if placed else (210, 208, 200)
                for k, part in enumerate(parts):
                    surf = self.tiny.render(
                        part if k == 0 else "   " + part, True, color
                    )
                    self.screen.blit(surf, (bx + 14, list_y))
                    list_y += 16
                if placed:
                    # Clic sur la ligne : la camera va sur place.
                    layout["items"][f"log_{entry.seq}"] = (
                        bx + 10,
                        row_top,
                        bw - 20,
                        list_y - row_top,
                    )
        player = state.tribes.get(PLAYER_TRIBE_ID)
        idle = player is not None and not player.learning
        ready = idle and bool(tech.available(state, PLAYER_TRIBE_ID))
        self._draw_tab(layout["tab_savoirs"], "Savoirs", panel == "savoirs", ready)
        if player is not None and player.learning:
            # Avancement du savoir en cours, en bas de l'onglet.
            tx, ty, tw, th = layout["tab_savoirs"]
            done = player.progress.get(player.learning, 0.0) / tech.TECHS[player.learning].cost
            pygame.draw.rect(self.screen, (40, 44, 50), (tx + 4, ty + th - 8, tw - 8, 4))
            pygame.draw.rect(
                self.screen, (110, 170, 220), (tx + 4, ty + th - 8, int((tw - 8) * min(1.0, done)), 4)
            )
        from src.kora import render_panels

        tabs = layout["tabs"]
        self._draw_tab(tabs["tribu"], render_panels.tribe_tab_label(state), panel == "tribu", render_panels.tribe_alert(state))
        self._draw_tab(tabs["peuples"], "Peuples", panel == "peuples", False)
        if "armee" in tabs:
            self._draw_tab(tabs["armee"], "Armee", panel == "armee", False)
        if "commerce" in tabs:
            self._draw_tab(tabs["commerce"], "Commerce", bool(ui.get("trade_open")), render_panels.commerce_alert(state))
        unread = False
        self._draw_tab(layout["tab_journal"], "Journal", panel == "journal", unread)

    _TECH_COLORS = {
        "connu": ((58, 50, 30), (212, 176, 90), (236, 226, 200)),
        "en_cours": ((30, 48, 66), (110, 170, 220), (226, 232, 240)),
        "disponible": ((30, 44, 32), (120, 190, 110), (226, 234, 222)),
        "attente": ((26, 28, 32), (84, 88, 96), (170, 172, 178)),
        "verrouille": ((20, 21, 24), (52, 55, 60), (110, 112, 118)),
    }
    # (fond des rangees, bande de l'age, couleur du marqueur et du nom)
    _ERA_COLORS = (
        ((21, 20, 18), (30, 28, 24), (214, 186, 120)),
        ((16, 24, 19), (34, 50, 34), (150, 206, 120)),
    )
    _TECH_LEGEND = (
        ("connu", "connu"),
        ("en_cours", "en cours"),
        ("disponible", "disponible"),
        ("attente", "pas encore"),
        ("verrouille", "verrouille"),
    )

    def _draw_tech_legend(self, right: int, y: int) -> None:
        x = right
        for key, label in reversed(self._TECH_LEGEND):
            fill, edge, _text = self._TECH_COLORS[key]
            surf = self.tiny.render(label, True, edge)
            x -= surf.get_width()
            self.screen.blit(surf, (x, y))
            x -= 16
            pygame.draw.rect(self.screen, fill, (x, y + 1, 12, 11), border_radius=2)
            pygame.draw.rect(self.screen, edge, (x, y + 1, 12, 11), 1, border_radius=2)
            x -= 12

    def _wrap_px(self, font, text: str, width: int) -> list[str]:
        """Coupe un texte en lignes qui tiennent dans `width` pixels."""
        words = text.split(" ")
        lines: list[str] = []
        cur = ""
        for word in words:
            trial = f"{cur} {word}" if cur else word
            if cur and font.size(trial)[0] > width:
                lines.append(cur)
                cur = word
            else:
                cur = trial
        if cur:
            lines.append(cur)
        return lines or [""]

    _DETAIL_COLORS = {
        "titre": (236, 226, 200),
        "texte": (196, 196, 190),
        "effet": (170, 214, 160),
        "ok": (150, 200, 140),
        "manque": (220, 150, 120),
        "note": (150, 156, 166),
    }

    def draw_savoirs(self, state: GameState, lay: dict, pick: str | None) -> None:
        # Ecran des savoirs a la maniere de Victoria 3 : voir render_tech.py.
        from src.kora import render_tech

        render_tech.draw(self, state, lay, pick)

    def _fit(self, font, text: str, width: int) -> str:
        if font.size(text)[0] <= width:
            return text
        while text and font.size(text + ".")[0] > width:
            text = text[:-1]
        return text.rstrip() + "."

    def draw_toasts(self, toasts: list, top: int) -> None:
        y = top
        self.toast_hits = []
        for toast in toasts:
            age = float(toast.get("age", 0.0))
            fade = 1.0 if age < 3.0 else max(0.0, 1.0 - (age - 3.0) / 1.0)
            if fade <= 0:
                continue
            text = str(toast.get("text", ""))
            color = (240, 150, 120) if toast.get("combat") else (235, 222, 170)
            if toast.get("hex") is not None:
                text += "  [voir]"
            surf = self.small.render(text, True, color)
            surf.set_alpha(int(230 * fade))
            # Fond sombre : sans lui, le texte se perd sur les plaines claires.
            back = pygame.Surface((surf.get_width() + 12, 20), pygame.SRCALPHA)
            back.fill((14, 16, 20, int(200 * fade)))
            self.screen.blit(back, (10, y - 1))
            self.screen.blit(surf, (16, y + 1))
            if toast.get("hex") is not None:
                self.toast_hits.append(((10, y - 1, surf.get_width() + 12, 20), toast))
            y += 22

    def draw_inspect(self, hover_info: dict | None, pin_info: dict | None) -> None:
        w, h = self.screen.get_size()
        if pin_info:
            pin_lines = inspect_lines(pin_info)
            ph = 16 + 18 + 16 * max(0, len(pin_lines) - 1)
            self._draw_inspect_card(pin_info, 12, h - ph - 12, 252, ph, pinned=True)
        if hover_info and (
            pin_info is None or hover_info.get("hex") != pin_info.get("hex")
        ):
            mx, my = pygame.mouse.get_pos()
            lines = self._inspect_lines(hover_info)
            tw = max(self.tiny.size(line)[0] for line in lines) + 16
            th = 8 + 16 * len(lines)
            tx = mx + 16
            ty = max(HUD_HEIGHT + 8, my + 18)
            if tx + tw > w - 8:
                tx = max(8, mx - tw - 12)
            if ty + th > h - 8:
                ty = max(HUD_HEIGHT + 8, my - th - 12)
            self._draw_inspect_card(hover_info, tx, ty, tw, th, pinned=False)

    def _inspect_lines(self, info: dict) -> list[str]:
        return inspect_lines(info)

    def _draw_inspect_card(
        self, info: dict, x: int, y: int, bw: int, bh: int, pinned: bool
    ) -> None:
        pygame.draw.rect(self.screen, (18, 20, 24), (x, y, bw, bh), border_radius=5)
        pygame.draw.rect(
            self.screen,
            (196, 150, 60) if pinned else (70, 74, 80),
            (x, y, bw, bh),
            1,
            border_radius=5,
        )
        lines = self._inspect_lines(info)
        yy = y + 8
        for i, line in enumerate(lines):
            font = self.small if i == 0 else self.tiny
            color = (230, 228, 220) if i == 0 else (200, 198, 190)
            surf = font.render(line, True, color)
            self.screen.blit(surf, (x + 10, yy))
            yy += 18 if i == 0 else 16

    def draw_hud(self, state: GameState) -> None:
        clock = state.clock
        width = self.screen.get_width()
        layout = hud_layout(width)
        self.hud_hits = layout
        pygame.draw.rect(self.screen, (18, 20, 24), (0, 0, width, HUD_HEIGHT))
        pygame.draw.line(
            self.screen, (50, 54, 60), (0, HUD_HEIGHT - 1), (width, HUD_HEIGHT - 1)
        )
        season = SEASON_FR[clock.season()]
        date = f"{season}  ·  an {clock.year}  ·  semaine {clock.week}"
        date_surf = self.font.render(date, True, (230, 228, 220))
        self.screen.blit(date_surf, (16, 15))

        px, py, pw, ph = layout["pause"]
        pause_on = clock.paused
        pygame.draw.rect(
            self.screen,
            (196, 150, 60) if pause_on else (42, 46, 52),
            (px, py, pw, ph),
            border_radius=3,
        )
        pygame.draw.rect(self.screen, (210, 180, 90), (px, py, pw, ph), 1, border_radius=3)
        if pause_on:
            pygame.draw.rect(self.screen, (20, 18, 14), (px + 6, py + 5, 4, 12))
            pygame.draw.rect(self.screen, (20, 18, 14), (px + 12, py + 5, 4, 12))
        else:
            pygame.draw.polygon(
                self.screen,
                (230, 220, 190),
                [(px + 7, py + 5), (px + 7, py + 17), (px + 17, py + 11)],
            )

        for n, (sx, sy, sw, sh) in layout["speeds"].items():
            lit = (not clock.paused) and n <= clock.speed
            fill = (70, 120, 150) if lit else (36, 40, 46)
            pygame.draw.rect(self.screen, fill, (sx, sy, sw, sh), border_radius=3)
            pygame.draw.rect(
                self.screen, (90, 130, 160) if lit else (70, 74, 80), (sx, sy, sw, sh), 1, border_radius=3
            )
            num = self.small.render(str(n), True, (235, 235, 230) if lit else (140, 144, 150))
            self.screen.blit(
                num, (sx + (sw - num.get_width()) // 2, sy + (sh - num.get_height()) // 2)
            )

        pop = sum(
            b.population for b in state.bands.values() if b.tribe_id == PLAYER_TRIBE_ID
        )
        stock = sum(
            b.stock for b in state.bands.values() if b.tribe_id == PLAYER_TRIBE_ID
        )
        prestige = state.tribes[PLAYER_TRIBE_ID].prestige
        stats = f"Prestige  {prestige}      Peuple  {pop}      Stocks  {stock:.0f}"
        stats_surf = self.font.render(stats, True, (210, 208, 200))
        self.screen.blit(stats_surf, (width - stats_surf.get_width() - 16, 15))

        extra_y = HUD_HEIGHT + 8
        if state.player_dead:
            dead = self.font.render("Votre peuple n'est plus", True, (220, 90, 80))
            self.screen.blit(dead, (16, extra_y))
            extra_y += 22
        if state.last_error:
            err = self.small.render(state.last_error, True, (220, 160, 80))
            self.screen.blit(err, (16, extra_y))
