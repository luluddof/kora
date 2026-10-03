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
from src.kora import battle as _battle, chiefs, goods, money, money as _money, orders, tech, theme
from src.kora.sim import band_lines, band_summary, band_warn_from, fight_lines, inspect_lines
from src.kora.gamestate import GameState, human_dead, log_of
from src.kora.types import Hex, Season
from src.kora.vision import enemy_band_visible, is_explored, is_visible
from src.kora.world import axial_to_offset, offset_to_axial
from src.kora.theme import C
from src.kora.resources import COLORS, LABELS, NAMES
from src.kora.villages import palisade_state

# Le rail des onglets (a droite) : une pastille par onglet, icone et nom.
TAB_W = 62
TAB_H = 66
TAB_ICONS = {"savoirs": "savoir", "tribu": "tribu", "peuples": "peuples", "journal": "journal", "armee": "armee", "commerce": "commerce"}
SEASON_ICONS = {Season.PRINTEMPS: "printemps", Season.ETE: "ete", Season.AUTOMNE: "automne", Season.HIVER: "hiver"}
KIND_ICONS = {"combat": "combat", "survie": "survie", "saison": "printemps", "decouverte": "decouverte", "politique": "politique"}
BAND_ICONS = {
    "split": "scinder",
    "merge": "reunir",
    "next": "pas",
    "chief": "chef",
    "village": "hutte",
    "camp": "camp",
    "deposit": "deposer",
    "withdraw": "reprendre",
    "honor": "honorer",
    "army": "armee",
}
MAP_MODE_ICONS = {"relief": "relief", "zones": "zones", "ressources": "ressources", "commerce": "commerce"}


def split_hint(label: str) -> tuple:
    """ "Scinder [S]" -> ("Scinder", "S")."""
    if label.endswith("]") and "[" in label:
        head, _sep, key = label[:-1].rpartition("[")
        return head.strip(), key.strip()
    return label, ""

HEX_SIZE = 8
MIN_ZOOM = 0.10
MAX_ZOOM = 4.8
OVERVIEW_HEX_PX = 3.2


SEASON_FR = {
    Season.PRINTEMPS: "Printemps",
    Season.ETE: "Été",
    Season.AUTOMNE: "Automne",
    Season.HIVER: "Hiver",
}

HUD_HEIGHT = 52
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
    """Le bandeau du haut : la saison a gauche, le temps au centre, le peuple
    a droite. Rectangles cliquables : pause, vitesses, bandeau."""
    cy = (HUD_HEIGHT - 34) // 2
    pause_x = max(300, width // 2 - 110)
    pause = (pause_x, cy, 34, 34)
    speeds = {}
    x = pause_x + 34 + 10
    for n in range(1, 6):
        speeds[n] = (x, cy + 4, 26, 26)
        x += 26 + 4
    return {"pause": pause, "speeds": speeds, "bar": (0, 0, width, HUD_HEIGHT)}


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
    ("principal", "Menu principal"),
    ("quitter", "Quitter"),
)


def menu_layout(width: int, height: int) -> dict:
    n = len(MENU_ITEMS)
    box_w, box_h = 320, 104 + n * 48
    bx = (width - box_w) // 2
    by = (height - box_h) // 2
    items = {}
    y = by + 84
    for key, _label in MENU_ITEMS:
        items[key] = (bx + 30, y, box_w - 60, 38)
        y += 48
    return {"box": (bx, by, box_w, box_h), "items": items}


def menu_hit(layout: dict, mx: int, my: int):
    for key, rect in layout["items"].items():
        if _contains(rect, mx, my):
            return key
    return None


def fight_panel_layout(width: int, height: int, n_lines: int) -> dict:
    bw = 290
    bh = 22 + 24 + 18 * max(0, n_lines - 1) + 12
    bx, by = 12, HUD_HEIGHT + 12
    close = (bx + bw - 80, by + 8, 66, 22)
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
    ("merge", "Réunir [F]"),
    ("next", "Suivante"),
    ("chief", "Chef ici"),
    ("village", "Village [V]"),
    ("camp", "Camper [C]"),
    ("deposit", "Déposer [K]"),
    ("withdraw", "Reprendre"),
    ("honor", "Honorer [H]"),
    ("army", "Troupe [L]"),
)
BAND_ROW = 5
BAND_HINT = "Clic : aller · ennemi : raid · Maj+clic allié : rejoindre"


def band_card_layout(width: int, height: int, n_lines: int) -> dict:
    bw = BAND_CARD_W
    rows = -(-len(BAND_BUTTONS) // BAND_ROW)
    bh = 14 + 22 + 18 * max(0, n_lines - 1) + 12 + rows * 36 + 4 + 18 + 10
    bx = max(276, (width - bw) // 2)
    if bx + bw > width - TAB_W - 8:
        bx = max(8, width - TAB_W - 8 - bw)
    by = height - bh - 12
    buttons = {}
    gap = 6
    bwidth = (bw - 28 - gap * (BAND_ROW - 1)) // BAND_ROW
    top = by + bh - 10 - 18 - 4 - rows * 36
    for i, (key, _label) in enumerate(BAND_BUTTONS):
        col, row = i % BAND_ROW, i // BAND_ROW
        buttons[key] = (bx + 14 + col * (bwidth + gap), top + row * 36, bwidth, 30)
    return {"box": (bx, by, bw, bh), "buttons": buttons}


MAP_MODES = (
    ("relief", "Relief"),
    ("zones", "Influence [Z]"),
    ("ressources", "Ressources [R]"),
    ("commerce", "Commerce [X]"),
)


def map_mode_layout(width: int, height: int) -> dict:
    """Pastilles du mode de carte, en haut a droite sous la barre (a gauche
    des onglets) : rien d'autre ne s'y trouve quand les panneaux sont fermes."""
    out = {}
    x = width - TAB_W - 14
    for key, label in reversed(MAP_MODES):
        head, hint = split_hint(label)
        cw = 40 + 8 * len(head) + (16 if hint else 0)
        x -= cw
        out[key] = (x, HUD_HEIGHT + 8, cw, 28)
        x -= 6
    return out


def map_mode_hit(layout: dict, mx: int, my: int):
    for key, rect in layout.items():
        if _contains(rect, mx, my):
            return key
    return None


TOAST_W = 360


def toast_box(width: int, height: int, panel=None, card=None) -> tuple[int, int, int, int]:
    """Le bloc des nouvelles, en bas a droite : a gauche des onglets (et du
    panneau ouvert), a droite de la carte de bande (au-dessus d'elle si la
    place manque), sous le bandeau des situations. Les nouvelles s'y
    empilent depuis le bas."""
    right = width - TAB_W - 14
    if panel is not None:
        right = min(right, panel[0] - 12)
    card_right = max(276, (width - BAND_CARD_W) // 2) + BAND_CARD_W
    bw = max(220, min(TOAST_W, right - card_right - 12))
    top = HUD_HEIGHT + 104
    bottom = height - 14
    x = right - bw
    if card is not None and card[2] and x < card[0] + card[2] and x + bw > card[0]:
        bottom = min(bottom, card[1] - 10)
    return (x, top, bw, max(0, bottom - top))


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
    ("filter_decouverte", "Découverte", 86),
    ("filter_politique", "Peuples", 64),
)
SORT_CHIPS = (
    ("sort_recent", "Plus récent", 100),
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


def tech_panel_layout(width: int, height: int, tab_w: int = 66, era: int = 0, cam=None, tab: str = "arbre") -> dict:
    """Ecran des savoirs (a la Victoria 3) : en tete la recherche en cours,
    au milieu la VUE sur la toile de l'arbre (camera `cam` : glisser pour se
    deplacer, molette pour zoomer ; boutons dans la barre du haut), en
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
    bxs = strip[0] + strip[2]
    center = (bxs - 96, strip[1] + 2, 96, 24)
    zoom_in = (center[0] - 6 - 28, strip[1] + 2, 28, 24)
    zoom_out = (zoom_in[0] - 4 - 28, strip[1] + 2, 28, 24)
    half = (bw - 40) // 2
    detail = (bx + 14, detail_top, bw - 28, detail_h)
    learn = (bx + bw - 14 - 12 - 170, detail_top + 7, 170, 28)
    current = (bx + bw - 14 - 460, by + 10, 460, 46)
    # Deux onglets dans la barre : l'arbre, les nombres (render_numbers.py).
    tabs = {
        "arbre": (strip[0] + 2, strip[1] + 2, 96, 24),
        "nombres": (strip[0] + 2 + 96 + 6, strip[1] + 2, 124, 24),
    }
    numbers = None
    if tab == "nombres":
        from src.kora import render_numbers

        numbers = render_numbers.page_layout((bx + 14, top + 6, bw - 28, by + bh - 12 - top - 6))
    return {
        "tab": tab,
        "tabs": tabs,
        "numbers": numbers,
        "box": (bx, by, bw, bh),
        "view": view,
        "cam": cam,
        "world": world,
        "nodes": nodes,
        "visible": visible,
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
ARMY_TAB = ("armee", "Armée")
COMMERCE_TAB = ("commerce", "Commerce")
# L'onglet Tresor vient avec l'argent (Valeurs d'echange : render_treasury.py).
TREASURY_TAB = ("tresor", "Trésor")


def side_tabs(army: bool = False, commerce: bool = False, treasury: bool = False) -> tuple:
    return SIDE_TABS + ((ARMY_TAB,) if army else ()) + ((COMMERCE_TAB,) if commerce else ()) + ((TREASURY_TAB,) if treasury else ())


def side_layout(width: int, height: int, panel: str | None = None, era: int = 0, army: bool = False, commerce: bool = False, tech_cam=None, tech_tab: str = "arbre", treasury: bool = False) -> dict:
    tab_w, gap = TAB_W, 6
    tab_x = width - tab_w - 4
    top = HUD_HEIGHT + 44
    shown = side_tabs(army, commerce, treasury)
    n = len(shown)
    tab_h = max(54, min(TAB_H, (height - top - 8 - gap * (n - 1)) // n))
    tabs = {key: (tab_x, top + i * (tab_h + gap), tab_w, tab_h) for i, (key, _l) in enumerate(shown)}
    tab_d = tabs["savoirs"]
    tab_j = tabs["journal"]
    items: dict = {}
    box = (0, 0, 0, 0)
    tech_panel = None
    priority: tuple = ()
    rail = tab_w + 4
    if panel == "savoirs":
        tech_panel = tech_panel_layout(width, height, rail, era, tech_cam, tech_tab)
        box = tech_panel["box"]
        for key, rect in tech_panel["tabs"].items():
            items["ttab:" + key] = rect
        if tech_panel["numbers"] is not None:
            from src.kora import render_numbers

            items.update(render_numbers.items(tech_panel["numbers"]))
            priority = ("ttab:arbre", "ttab:nombres")
        else:
            # Seuls les savoirs dans la vue se cliquent (la toile deborde).
            for tid, rect in tech_panel["visible"].items():
                items[f"tech:{tid}"] = rect
            items["learn"] = tech_panel["learn"]
            items["tview"] = tech_panel["view"]
            for key in ("zoom_in", "zoom_out", "center"):
                items["t" + key] = tech_panel[key]
            priority = ("tzoom_in", "tzoom_out", "tcenter", "ttab:arbre", "ttab:nombres")
    elif panel in ("tribu", "peuples", "armee"):
        from src.kora.render_panels import panel_box

        box = panel_box(width, height, "tribu" if panel == "armee" else panel, rail)
    elif panel == "journal":
        box_w = 340
        box_h = min(560, max(300, height - HUD_HEIGHT - 28))
        bx = width - rail - box_w - 8
        by = HUD_HEIGHT + 14
        if by + box_h > height - 12:
            box_h = max(240, height - by - 12)
        box = (bx, by, box_w, box_h)
        x = bx + 16
        y = by + 54
        row_right = bx + box_w - 16
        for key, _label, cw in FILTER_CHIPS:
            if x + cw > row_right:
                x = bx + 16
                y += 30
            items[key] = (x, y, cw, 24)
            x += cw + 6
        y += 32
        x = bx + 16
        for key, _label, cw in SORT_CHIPS:
            items[key] = (x, y, cw, 24)
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
        if band.tribe_id != state.viewer and not enemy_band_visible(state, band, state.viewer):
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
    """Anneau de selection ou d'alerte (carre autour d'un village) ; la
    selection (blanc) devient une lueur de braise."""
    if tuple(color[:3]) == (255, 255, 255):
        color = C.braise
        g = pygame.Surface((r * 2 + 16, r * 2 + 16), pygame.SRCALPHA)
        for i in range(4, 0, -1):
            pygame.draw.circle(g, (*C.braise, 26 * (5 - i)), (r + 8, r + 8), r + i * 2, 2)
        surf.blit(g, (cx - r - 8, cy - r - 8))
    if square:
        pygame.draw.polygon(surf, color, theme.chamfer((cx - r, cy - r, 2 * r, 2 * r), 3), 2)
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
    guard = (200, 102, 47) if lit else (160, 120, 50)
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
        # Les lettres de la charte (theme.py : Alegreya, embarquees).
        self.font = theme.font("texte")
        self.small = theme.font("petit")
        self.tiny = theme.font("mini")
        self.atlas_font = theme.font_file("sc-bold", 22)
        self.atlas_small = theme.font_file("sans-italic", 17)
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
        # Le bandeau des situations (uid -> dalle) et leur fenetre.
        self.situation_hits: dict = {}
        self.situation_window: dict = {}
        # La bataille en cours du joueur (render_battle.py).
        self.battle_hits: dict = {}
        # Ecran du village, fenetre de fondation (render_village.py).
        self.village_hits: dict = {}
        self.village_armies: list = []
        self.found_hits: dict = {}
        # Ecran du commerce (render_trade.py).
        self.trade_hits: dict = {}
        self.treasury_hits: dict = {}
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
        target.fill((14, 11, 9))
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
        self.screen.fill((14, 11, 9))
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
                _draw_token(self.screen, ix, iy, colr, radius)
            if band.tribe_id == state.viewer and not chiefs.is_chief_band(state, band):
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
        from src.kora import render_situations

        render_situations.draw_on_map(self, state, globe_yaw, globe_pitch, zoom)
        from src.kora import render_battle

        render_battle.draw_on_map(self, state, globe_yaw, globe_pitch, zoom)
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
        if human_dead(state, state.viewer):
            extra_y += 22
        if state.last_error:
            extra_y += 18
        ui = ui or {}
        self.draw_map_modes()
        self.draw_toasts(toasts or [], extra_y)
        self.draw_inspect(hover_info, pin_info)
        self.draw_band_card(state, selected_id)
        from src.kora import render_panels

        # Les cartes d'evenement et le bandeau des situations restent sous
        # les panneaux ouverts.
        render_panels.draw_event_cards(self, state, ui)
        if open_fight is None:
            # La dalle de bataille d'abord : les fiches du bandeau passent dessus.
            render_battle.draw(self, state)
            render_situations.draw_banner(self, state)
        else:
            self.situation_hits, self.battle_hits = {}, {}
        # Le rapport de bataille ouvert passe par-dessus les cartes et le bandeau.
        self.draw_fight_panel(open_fight, state)
        self.draw_side(state, side_panel, log_filter, log_newest, tech_pick, ui)
        from src.kora import render_village, screens

        # Le grand ecran ouvert : village, commerce ou tresor (screens.py).
        screens.draw(self, state, ui)
        if ui.get("found") is not None:
            render_village.draw_found(self, state, ui)
        else:
            self.found_hits = {}
        if ui.get("situation_open") is not None:
            render_situations.draw_window(self, state, ui)
        else:
            self.situation_window = {}
            self.situation_open_uid = None
        if ui.get("event_open") is not None:
            render_panels.draw_event_modal(self, state, ui)
        if menu_open:
            self.draw_menu()

    def draw_band_card(self, state: GameState, selected_id: int | None) -> None:
        band = state.bands.get(selected_id) if selected_id is not None else None
        if band is None or band.tribe_id != state.viewer or band.village:
            # Un village se gere dans son ecran (render_village.py).
            self.band_hits = {}
            return
        info = band_summary(state, band.id)
        lines = band_lines(info)
        w, h = self.screen.get_size()
        layout = band_card_layout(w, h, len(lines))
        self.band_hits = layout
        bx, by, bw, bh = layout["box"]
        theme.panel(self.screen, layout["box"], "peau")
        color = color_of(state.tribes.get(band.tribe_id))
        pygame.draw.polygon(self.screen, color, theme.chamfer((bx + 10, by + 14, 5, 26), 1))
        warn_from = band_warn_from(info)
        yy = by + 12
        for i, line in enumerate(lines):
            if i == 0:
                theme.text(self.screen, line, "h3", C.os, (bx + 24, yy), bw - 40)
                yy += 24
                continue
            col = C.alerte if i >= warn_from else (C.lin if i < 3 else C.ocre_jaune)
            theme.text(self.screen, line, "petit", col, (bx + 24, yy), bw - 40)
            yy += 18
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
            head, key_hint = split_hint(labels[key])
            theme.button(self.screen, rect, head, "second", on, hover, icon_key=BAND_ICONS.get(key), key_hint=key_hint, role="bouton_petit")
        warn = hint != BAND_HINT
        theme.text(self.screen, hint, "mini", C.alerte if warn else C.cendre, (bx + 16, by + bh - 10 - 18), bw - 32)

    def draw_trade_marks(self, state: GameState, yaw, pitch, gcx, gcy, focal, dist) -> None:
        """Mode Commerce : sur chaque village connu, les biens que son peuple
        a en reserve (pastilles ; plus grosses quand il en a de trop) ; vos
        partenaires entoures d'or ; la portee de vos porteurs autour de vos
        villages."""
        from src.kora.globe import offset_to_xyz, project_xyz, rotate_xyz
        world = state.world
        w, h = self.screen.get_size()
        partners = set(goods.partners(state, state.viewer))
        heart = chiefs.chief_band(state, state.viewer)
        heart_hex = heart.position if heart is not None and heart.village else None
        reach = goods.trade_range(state, state.viewer, state.viewer)
        self._legend_world = world
        for site in sorted(state.sites.values(), key=lambda s: s.id):
            if site.kind != "village":
                continue
            own = site.tribe_id == state.viewer
            if not own and not is_explored(state, site.hex, state.viewer):
                continue
            pos = hex_to_globe_screen(site.hex, world, yaw, pitch, gcx, gcy, focal, dist)
            if pos is None:
                continue
            x, y = int(pos[0]), int(pos[1])
            if x < -30 or y < HUD_HEIGHT or x > w + 30 or y > h + 30:
                continue
            if site.tribe_id in partners:
                pygame.draw.circle(self.screen, (217, 164, 65), (x, y), 12, 2)
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
                pygame.draw.circle(self.screen, (95, 176, 166), (x, y), 10, 1)
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
                pygame.draw.circle(self.screen, (95, 176, 166), (int(pos[0]), int(pos[1])), 1)

    def draw_polity_labels(self, state: GameState, yaw, pitch, gcx, gcy, focal, dist) -> None:
        """Les proto-pays : le nom de chaque peuple fixe, au-dessus de ses
        villages (ceux que vous connaissez), a sa couleur."""
        if dist > 2.9:
            return
        from src.kora.globe import offset_to_xyz, project_xyz, rotate_xyz
        world = state.world
        homes: dict = {}
        for site in sorted(state.sites.values(), key=lambda s: s.id):
            if site.kind != "village":
                continue
            if site.tribe_id != state.viewer and not is_explored(state, site.hex, state.viewer):
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
        from src.kora.globe import offset_to_xyz, project_xyz, rotate_xyz
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
            mine = state.viewer in (route.exporter, route.importer)
            if not mine and not (is_explored(state, a, state.viewer) and is_explored(state, b, state.viewer)):
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
                        pygame.draw.circle(self.screen, (239, 228, 204), (px, py), 3 if mine else 2)
                        pygame.draw.circle(self.screen, (20, 20, 20), (px, py), 3 if mine else 2, 1)
            else:
                # Rien porte le dernier mois : pointilles pales.
                for k in range(0, len(pts) - 1, 2):
                    if pts[k] is not None and pts[k + 1] is not None:
                        pygame.draw.line(self.screen, color, pts[k], pts[k + 1], 1)

    def draw_sites(self, state: GameState, yaw, pitch, gcx, gcy, focal, dist) -> None:
        """Campements et caches : les siens partout ou l'on est alle, ceux des
        autres seulement sous les yeux de vos bandes."""
        w, h = self.screen.get_size()
        size = 7 if dist <= LABEL_DIST else 4
        for site in sorted(state.sites.values(), key=lambda s: s.id):
            mine = site.tribe_id == state.viewer
            seen = is_explored(state, site.hex, state.viewer) if mine else is_visible(state, site.hex, state.viewer)
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
        mx, my = pygame.mouse.get_pos()
        for key, label in MAP_MODES:
            head, hint = split_hint(label)
            rect = layout[key]
            theme.button(self.screen, rect, head, "second", True, _contains(rect, mx, my), icon_key=MAP_MODE_ICONS.get(key), key_hint=hint, role="bouton_petit", active=self.map_mode == key)
        if self.map_mode == "commerce":
            self._draw_trade_legend(layout, w)
        if self.map_mode == "ressources":
            x0 = layout["relief"][0]
            y = layout["relief"][1] + 36
            bw = w - TAB_W - 14 - x0
            bh = 14 + 18 * ((len(NAMES) + 1) // 2)
            theme.panel(self.screen, (x0, y, bw, bh), "infobulle")
            for i, name in enumerate(NAMES):
                cx = x0 + 12 + (i % 2) * (bw // 2)
                cy = y + 8 + (i // 2) * 18
                pygame.draw.polygon(self.screen, COLORS[name], theme.chamfer((cx, cy + 3, 11, 11), 2))
                theme.text(self.screen, LABELS[name], "mini", C.lin, (cx + 16, cy), bw // 2 - 26)

    def _draw_trade_legend(self, layout, w) -> None:
        """Legende du mode Commerce : les biens, ce que disent les traits,
        et le commerce du mois."""
        state = getattr(self, "_legend_state", None)
        x0 = layout["relief"][0]
        y = layout["relief"][1] + 36
        bw = w - TAB_W - 14 - x0
        rows = [(goods.GOOD_COLORS[g], goods.GOOD_NAMES[g]) for g in goods.GOODS]
        notes = [
            "Trait plein : la route a porté le mois dernier",
            "Pointillés : rien porté",
            "Points blancs : les porteurs (un par convoi)",
            "Pastilles sur un village : biens en réserve",
            "Anneau doré : vos partenaires ; bleu : à portée",
            "Pointillés bleus : portée de vos porteurs",
        ]
        extra = []
        if state is not None:
            month = goods.last_month(state, state.viewer)
            mine = goods.routes_of(state, state.viewer)
            extra = [
                f"Vos routes : {len(mine)}, dont {sum(1 for r in mine if r.units > 0)} actives",
                f"Le mois dernier : +{month['sold']:.0f} / -{month['bought']:.0f} vivres",
                "Écran du commerce : [M]",
            ]
        bh = 14 + 18 * ((len(rows) + 1) // 2) + 16 * (len(notes) + len(extra)) + 12
        theme.panel(self.screen, (x0, y, bw, bh), "infobulle")
        for i, (color, label) in enumerate(rows):
            cx = x0 + 12 + (i % 2) * (bw // 2)
            cy = y + 8 + (i // 2) * 18
            pygame.draw.circle(self.screen, color, (cx + 5, cy + 9), 5)
            theme.text(self.screen, label, "mini", C.lin, (cx + 16, cy), bw // 2 - 26)
        yy = y + 12 + 18 * ((len(rows) + 1) // 2)
        for t in notes:
            theme.text(self.screen, t, "mini", C.cendre, (x0 + 12, yy), bw - 24)
            yy += 16
        yy += 4
        for t in extra:
            theme.text(self.screen, t, "mini", C.ocre_jaune, (x0 + 12, yy), bw - 24)
            yy += 16

    def draw_fight_marks(
        self, state: GameState, globe_yaw, globe_pitch, zoom, open_fight
    ) -> None:
        w, h = self.screen.get_size()
        gcx, gcy, focal, dist = view_params(zoom, w, h, HUD_HEIGHT)
        me = state.viewer
        for mark in state.fights:
            # Multijoueur : les combats des autres, seulement la ou on est alle.
            if me not in (mark.winner_tribe, mark.loser_tribe) and not is_explored(state, mark.hex, me):
                continue
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
        lines = fight_lines(mark, state.viewer if state is not None else 1)
        w, h = self.screen.get_size()
        layout = fight_panel_layout(w, h, len(lines))
        self.fight_hits = layout
        bx, by, bw, bh = layout["box"]
        theme.panel(self.screen, layout["box"], "peau")
        mx, my = pygame.mouse.get_pos()
        theme.button(self.screen, layout["close"], "Fermer", "discret", True, _contains(layout["close"], mx, my))
        yy = by + 10
        for i, line in enumerate(lines):
            if i == 0:
                self.screen.blit(theme.icon("combat", 18, C.mauvais), (bx + 12, yy + 1))
                theme.text(self.screen, line, "h3", C.os, (bx + 36, yy))
                yy += 24
            else:
                theme.text(self.screen, line, "petit", C.lin, (bx + 14, yy), bw - 28)
                yy += 18

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
        """Le chemin d'une bande : une piste de points d'os, un repere au bout,
        la duree de la marche."""
        if not band.path:
            return
        world = state.world
        sw, sh = self.screen.get_size()
        gcx, gcy, focal, dist = view_params(zoom, sw, sh, HUD_HEIGHT)
        pts = []
        for hx in [band.position, *band.path]:
            pos = hex_to_globe_screen(hx, world, globe_yaw, globe_pitch, gcx, gcy, focal, dist)
            if pos is not None:
                pts.append(pos)
        for a, b in zip(pts, pts[1:]):
            theme.dotted(self.screen, a, b, C.nuit, 7, 3)
            theme.dotted(self.screen, a, b, C.os, 7, 2)
        if pts:
            ex, ey = int(pts[-1][0]), int(pts[-1][1])
            pygame.draw.circle(self.screen, C.nuit, (ex, ey), 7)
            pygame.draw.circle(self.screen, C.braise, (ex, ey), 6, 2)
            tribe = state.tribes.get(band.tribe_id)
            weeks = travel_weeks(state.world, band.position, band.path, water_ok=bool(tribe and tribe.cabotage))
            unit = "semaine" if weeks <= 1 else "semaines"
            self._outlined_text(theme.font("petit_gras"), f"{weeks} {unit}", C.os, ex + 10 + theme.font("petit_gras").size(f"{weeks} {unit}")[0] / 2, ey - 12)

    def draw_menu(self) -> None:
        w, h = self.screen.get_size()
        theme.veil(self.screen, 160)
        layout = menu_layout(w, h)
        self.menu_hits = layout
        bx, by, bw, bh = layout["box"]
        theme.panel(self.screen, layout["box"], "pierre")
        from src.kora import __version__

        logo = theme.font_file("sc-black", 40)
        img = logo.render("Kora", True, C.ocre)
        self.screen.blit(logo.render("Kora", True, C.nuit), (bx + (bw - img.get_width()) // 2 + 2, by + 14))
        self.screen.blit(img, (bx + (bw - img.get_width()) // 2, by + 12))
        theme.stroke(self.screen, bx + bw // 2 - 70, by + 64, 140, C.ocre, 3)
        theme.text(self.screen, f"version {__version__}", "mini", C.cendre, (bx + bw - 90, by + bh - 24))
        mx, my = pygame.mouse.get_pos()
        labels = dict(MENU_ITEMS)
        for key, rect in layout["items"].items():
            rank = "principal" if key == "reprendre" else "second"
            theme.button(self.screen, rect, labels[key], rank, True, _contains(rect, mx, my), role="bouton")

    def _draw_tab(self, rect, label: str, opened: bool, ready: bool = False, icon_key: str | None = None) -> None:
        """Une pastille du rail : l'icone, le nom en dessous. Ouverte : ocre ;
        a voir (un savoir a choisir, un clan qui s'en va) : elle respire."""
        tx, ty, tw, th = rect
        mx, my = pygame.mouse.get_pos()
        hover = _contains(rect, mx, my)
        if ready and not opened:
            theme.glow(self.screen, rect, C.braise, 0.4 + 0.6 * theme.pulse(pygame.time.get_ticks() / 1000.0))
        kind = "carte_choisie" if opened else ("carte_survol" if hover else "carte")
        theme.panel(self.screen, rect, kind)
        col = C.braise if (ready and not opened) else (C.ocre_jaune if opened else (C.os if hover else C.lin))
        isz = 28
        self.screen.blit(theme.icon(icon_key or "feu", isz, col), (tx + (tw - isz) // 2, ty + 8))
        f = theme.font("mini_gras")
        name = theme.fit(f, label, tw - 6)
        img = f.render(name, True, col)
        self.screen.blit(img, (tx + (tw - img.get_width()) // 2, ty + th - img.get_height() - 7))
        if opened:
            # La pastille ouverte touche sa fenetre : un trait d'ocre a gauche.
            pygame.draw.line(self.screen, C.ocre, (tx, ty + 6), (tx, ty + th - 7), 3)

    def _draw_chip(self, rect, label: str, active: bool) -> None:
        mx, my = pygame.mouse.get_pos()
        head, hint = split_hint(label)
        theme.button(self.screen, rect, head, "second", True, _contains(rect, mx, my), key_hint=hint, role="bouton_petit", active=active)

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
        treasury = money.has_money(state, state.viewer)
        if panel == "savoirs" and ui.get("tech_cam") is None:
            # Premiere ouverture : la vue se pose sur la recherche en cours.
            from src.kora import render_tech

            ui["tech_cam"] = render_tech.focus_cam(state, w, h)
        layout = side_layout(
            w, h, panel=panel if (panel != "armee" or army) else None, era=ui.get("era", 0), army=army, commerce=commerce,
            tech_cam=ui.get("tech_cam"), tech_tab=ui.get("tech_tab", "arbre"), treasury=treasury,
        )
        if layout.get("tech") is not None:
            ui["tech_cam"] = layout["tech"]["cam"]
        self.side_hits = layout
        if panel == "savoirs":
            self.draw_savoirs(state, layout["tech"], tech_pick, ui)
        if panel == "tribu":
            render_panels.draw_tribe(self, state, layout, ui)
        elif panel == "peuples":
            render_panels.draw_peoples(self, state, layout, ui)
        if panel == "armee" and army:
            render_panels.draw_army(self, state, layout, ui)
        if panel == "journal":
            draw_journal(self, state, layout, log_filter, log_newest)
        player = state.tribes.get(state.viewer)
        idle = player is not None and not player.learning
        ready = idle and bool(tech.available(state, state.viewer))
        tabs = layout["tabs"]
        self._draw_tab(tabs["savoirs"], "Savoirs", panel == "savoirs", ready, "savoir")
        if player is not None and player.learning and player.learning in tech.TECHS:
            # Avancement du savoir en cours, en bas de la pastille.
            tx, ty, tw, th = tabs["savoirs"]
            done = player.progress.get(player.learning, 0.0) / tech.TECHS[player.learning].cost
            theme.bar(self.screen, (tx + 8, ty + th - 6, tw - 16, 4), min(1.0, done), C.savoir)
        label = render_panels.tribe_tab_label(state)
        self._draw_tab(tabs["tribu"], label, panel == "tribu", render_panels.tribe_alert(state), "tribu" if label == "Tribu" else "village")
        self._draw_tab(tabs["peuples"], "Peuples", panel == "peuples", False, "peuples")
        if "armee" in tabs:
            self._draw_tab(tabs["armee"], "Armée", panel == "armee", False, "armee")
        if "commerce" in tabs:
            self._draw_tab(tabs["commerce"], "Commerce", bool(ui.get("trade_open")), render_panels.commerce_alert(state), "commerce")
        if "tresor" in tabs:
            self._draw_tab(tabs["tresor"], "Trésor", bool(ui.get("treasury_open")), render_panels.treasury_alert(state), "tresor")
        self._draw_tab(tabs["journal"], "Journal", panel == "journal", False, "journal")

    _TECH_COLORS = {
        "connu": ((58, 50, 30), (217, 164, 65), (239, 228, 204)),
        "en_cours": ((86, 50, 26), (242, 160, 61), (239, 228, 204)),
        "disponible": ((30, 58, 54), (157, 191, 110), (239, 228, 204)),
        "attente": ((36, 27, 21), (111, 88, 67), (194, 177, 148)),
        "verrouille": ((27, 21, 16), (73, 54, 38), (130, 113, 96)),
    }
    # (fond des rangees, bande de l'age, couleur du marqueur et du nom)
    _ERA_COLORS = (
        ((21, 20, 18), (30, 28, 24), (214, 186, 120)),
        ((24, 19, 14), (50, 38, 29), (150, 206, 120)),
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
        "titre": (239, 228, 204),
        "texte": (196, 196, 190),
        "effet": (170, 214, 160),
        "ok": (150, 200, 140),
        "manque": (220, 150, 120),
        "note": (175, 159, 136),
    }

    def draw_savoirs(self, state: GameState, lay: dict, pick: str | None, ui: dict | None = None) -> None:
        # Ecran des savoirs a la maniere de Victoria 3 : voir render_tech.py.
        from src.kora import render_tech

        render_tech.draw(self, state, lay, pick, ui)

    def _fit(self, font, text: str, width: int) -> str:
        return theme.fit(font, text, width)

    def draw_toasts(self, toasts: list, top: int = 0) -> None:
        """Les nouvelles : en bas a droite, dans un bloc invisible
        (toast_box) ; chacune une petite dalle qui glisse et s'eclaire, une
        icone par genre ; un texte long revient a la ligne et reste dans le
        bloc. La plus recente en bas. Un clic sur une nouvelle situee y
        emmene."""
        self.toast_hits = []
        w, h = self.screen.get_size()
        side = getattr(self, "side_hits", {}) or {}
        card = (getattr(self, "band_hits", {}) or {}).get("box")
        bx, by, bw, bh = toast_box(w, h, side.get("box") if side.get("box", (0, 0, 0, 0))[2] else None, card)
        f = theme.font("petit")
        line_h = f.get_linesize()
        shown = []
        for toast in toasts:
            age = float(toast.get("age", 0.0))
            fade = 1.0 if age < 3.0 else max(0.0, 1.0 - (age - 3.0) / 1.0)
            if fade <= 0:
                continue
            placed = toast.get("hex") is not None
            text_w = bw - 52 - (22 if placed else 0)
            lines = theme.wrap(f, str(toast.get("text", "")), text_w)
            if len(lines) > 6:
                lines = lines[:5] + [theme.fit(f, lines[5] + " " + " ".join(lines[6:]), text_w)]
            th = 12 + line_h * len(lines)
            shown.append((toast, age, fade, placed, lines, th))
        y = by + bh
        for toast, age, fade, placed, lines, th in reversed(shown):
            if y - th < by:
                break
            y -= th
            slide = int(max(0.0, 0.25 - age) / 0.25 * 30)
            kind = toast.get("kind") or ("combat" if toast.get("combat") else "survie")
            tw = max(f.size(line)[0] for line in lines)
            cw = min(bw, tw + 52 + (22 if placed else 0))
            x = bx + bw - cw + slide
            layer = pygame.Surface((cw + 12, th + 6), pygame.SRCALPHA)
            theme.panel(layer, (6, 3, cw, th), "toast")
            col = C.mauvais if kind == "combat" else C.ocre_jaune
            layer.blit(theme.icon(KIND_ICONS.get(kind, "feu"), 18, col), (16, 9))
            for k, line in enumerate(lines):
                layer.blit(f.render(line, True, C.os), (42, 8 + k * line_h))
            if placed:
                layer.blit(theme.icon("voir", 16, C.lin), (cw - 18, 9))
            layer.set_alpha(int(255 * fade))
            self.screen.blit(layer, (x - 6, y - 3))
            if placed:
                self.toast_hits.append(((x, y, cw, th), toast))
            y -= 6

    def draw_inspect(self, hover_info: dict | None, pin_info: dict | None) -> None:
        w, h = self.screen.get_size()
        if pin_info:
            pin_lines = inspect_lines(pin_info)
            ph = 18 + 24 + 18 * max(0, len(pin_lines) - 1)
            self._draw_inspect_card(pin_info, 12, h - ph - 12, 270, ph, pinned=True)
        if hover_info and (pin_info is None or hover_info.get("hex") != pin_info.get("hex")):
            mx, my = pygame.mouse.get_pos()
            lines = self._inspect_lines(hover_info)
            f0, f1 = theme.font("h3"), theme.font("petit")
            tw = max([f0.size(lines[0])[0]] + [f1.size(line)[0] for line in lines[1:]]) + 30
            th = 18 + 24 + 18 * max(0, len(lines) - 1)
            tx = mx + 18
            ty = max(HUD_HEIGHT + 8, my + 20)
            if tx + tw > w - 8:
                tx = max(8, mx - tw - 12)
            if ty + th > h - 8:
                ty = max(HUD_HEIGHT + 8, my - th - 12)
            self._draw_inspect_card(hover_info, tx, ty, tw, th, pinned=False)

    def _inspect_lines(self, info: dict) -> list[str]:
        return inspect_lines(info)

    def _draw_inspect_card(self, info: dict, x: int, y: int, bw: int, bh: int, pinned: bool) -> None:
        theme.panel(self.screen, (x, y, bw, bh), "peau" if pinned else "infobulle")
        lines = self._inspect_lines(info)
        yy = y + 9
        for i, line in enumerate(lines):
            if i == 0:
                theme.text(self.screen, line, "h3", C.os, (x + 14, yy), bw - 26)
                yy += 24
            else:
                theme.text(self.screen, line, "petit", C.lin, (x + 14, yy), bw - 26)
                yy += 18

    def draw_hud(self, state: GameState) -> None:
        """Le bandeau : la saison et la date ; le temps ; le peuple en icones."""
        clock = state.clock
        width = self.screen.get_width()
        layout = hud_layout(width)
        self.hud_hits = layout
        theme.panel(self.screen, (0, 0, width, HUD_HEIGHT), "bandeau")
        pygame.draw.line(self.screen, C.ocre_sombre, (0, HUD_HEIGHT - 2), (width, HUD_HEIGHT - 2))
        pygame.draw.line(self.screen, C.nuit, (0, HUD_HEIGHT - 1), (width, HUD_HEIGHT - 1))
        season = clock.season()
        self.screen.blit(theme.medallion(SEASON_ICONS.get(season, "printemps"), 18, "normal", C.froid if season is Season.HIVER else None), (8, (HUD_HEIGHT - 40) // 2))
        theme.text(self.screen, SEASON_FR[season], "h2", C.os, (56, 4), shadow=True)
        day = getattr(state, "day", 0)
        if _battle.slow(state):
            # Une bataille : le temps passe en jours.
            theme.text(self.screen, f"an {clock.year}  ·  semaine {clock.week}  ·  jour {day + 1}", "petit", C.braise, (57, 28))
        else:
            theme.text(self.screen, f"an {clock.year}  ·  semaine {clock.week}", "petit", C.lin, (57, 28))
        mx, my = pygame.mouse.get_pos()
        pause = layout["pause"]
        theme.icon_button(self.screen, pause, "jouer" if clock.paused else "pause", True, _contains(pause, mx, my), active=clock.paused)
        for n, rect in layout["speeds"].items():
            lit = (not clock.paused) and n <= clock.speed
            theme.button(self.screen, rect, str(n), "principal" if lit else "second", True, _contains(rect, mx, my), role="petit_gras")
        tribe = state.tribes[state.viewer]
        pop = sum(b.population for b in state.bands.values() if b.tribe_id == state.viewer)
        stock = sum(b.stock for b in state.bands.values() if b.tribe_id == state.viewer)
        x = width - 16
        num = theme.font("chiffre")
        chips = [("vivres", f"{stock:.0f}", C.lin), ("gens", str(pop), C.os)]
        if _money.has_money(state, state.viewer):
            # Le tresor (sicles) : un clic ou [G] ouvre l'ecran du tresor.
            chips.append(("pieces", f"{tribe.money:.0f}", (196, 204, 222)))
        chips.append(("prestige", str(tribe.prestige), C.ocre_jaune))
        for key, value, col in chips:
            img = num.render(value, True, col)
            x -= img.get_width()
            self.screen.blit(num.render(value, True, C.nuit), (x + 1, (HUD_HEIGHT - img.get_height()) // 2 + 2))
            self.screen.blit(img, (x, (HUD_HEIGHT - img.get_height()) // 2))
            x -= 28
            self.screen.blit(theme.icon(key, 24, col), (x, (HUD_HEIGHT - 24) // 2))
            x -= 22
        # Le savoir en cours : son nom et sa barre.
        if tribe.learning and tribe.learning in tech.TECHS:
            t = tech.TECHS[tribe.learning]
            done = tribe.progress.get(tribe.learning, 0.0) / max(1.0, t.cost)
            # Jamais sur les boutons du temps (petites fenetres).
            speeds_end = max(rx + rw for rx, _ry, rw, _rh in layout["speeds"].values())
            box_w = max(110, min(190, x - speeds_end - 16))
            x -= box_w
            self.screen.blit(theme.icon("savoir", 22, C.savoir), (x, 8))
            theme.text(self.screen, t.name, "mini_gras", C.os, (x + 28, 7), box_w - 32)
            theme.bar(self.screen, (x + 28, 28, box_w - 34, 8), done, C.savoir)
        elif tech.available(state, state.viewer):
            x -= 190
            self.screen.blit(theme.icon("savoir", 22, C.braise), (x, 14))
            theme.text(self.screen, "Choisir un savoir [T]", "petit_gras", C.braise, (x + 28, 15))
        extra_y = HUD_HEIGHT + 8
        if human_dead(state, state.viewer):
            theme.text(self.screen, "Votre peuple n'est plus", "h2", C.mauvais, (16, extra_y), shadow=True)
            extra_y += 26
        if state.last_error:
            theme.text(self.screen, state.last_error, "petit", C.alerte, (16, extra_y))


def draw_journal(self, state, layout, log_filter, log_newest) -> None:
    """Le journal : une icone par genre, la date en petit, le texte ;
    une ligne situee (un oeil) emmene la camera."""
    bx, by, bw, bh = layout["box"]
    theme.panel(self.screen, layout["box"], "peau")
    theme.title(self.screen, "Journal", bx + 18, by + 12, "h1")
    labels = dict((k, lab) for k, lab, _w in FILTER_CHIPS)
    labels.update((k, lab) for k, lab, _w in SORT_CHIPS)
    for key, rect in list(layout["items"].items()):
        if key.startswith("filter_"):
            active = FILTER_BY_HIT[key] == log_filter
        elif key == "sort_recent":
            active = log_newest
        else:
            active = not log_newest
        self._draw_chip(rect, labels[key], active)
    log = log_of(state, state.viewer) if isinstance(state.log, GameLog) else GameLog()
    rows = log.filtered(log_filter, newest_first=log_newest)
    list_y = layout["items"]["sort_recent"][1] + 36
    theme.dotted(self.screen, (bx + 16, list_y - 8), (bx + bw - 16, list_y - 8), C.ocre_sombre, 5)
    bottom = by + bh - 12
    f, fm = theme.font("petit"), theme.font("mini")
    text_w = bw - 64
    mx, my = pygame.mouse.get_pos()
    for entry in rows:
        parts = theme.wrap(f, entry.text, text_w)
        row_h = 16 + 18 * len(parts) + 6
        if list_y + row_h > bottom:
            break
        placed = entry.hex is not None
        rect = (bx + 10, list_y - 2, bw - 20, row_h)
        if placed and _contains(rect, mx, my):
            pygame.draw.polygon(self.screen, C.cuir_clair, theme.chamfer(rect, 4))
        kind = getattr(entry.kind, "value", str(entry.kind))
        col = C.mauvais if kind == "combat" else C.ocre_jaune
        self.screen.blit(theme.icon(KIND_ICONS.get(kind, "feu"), 18, col), (bx + 16, list_y + 2))
        self.screen.blit(fm.render(f"an {entry.year}, semaine {entry.week}", True, C.cendre), (bx + 42, list_y))
        if placed:
            self.screen.blit(theme.icon("voir", 15, C.lin), (bx + bw - 34, list_y))
        yy = list_y + 16
        for part in parts:
            self.screen.blit(f.render(part, True, C.os), (bx + 42, yy))
            yy += 18
        if placed:
            # Clic sur la ligne : la camera va sur place.
            layout["items"][f"log_{entry.seq}"] = rect
        list_y += row_h


def _draw_token(surf: pygame.Surface, cx: int, cy: int, color, radius: int) -> None:
    """Une bande : un jeton peint, ombre portee, reflet en haut, bord sombre."""
    pygame.draw.circle(surf, (0, 0, 0), (cx + 1, cy + 2), radius + 1)
    pygame.draw.circle(surf, _darken(color, 0.55), (cx, cy), radius + 1)
    pygame.draw.circle(surf, color, (cx, cy), radius)
    if radius >= 4:
        hi = tuple(min(255, int(c + (255 - c) * 0.45)) for c in color)
        pygame.draw.circle(surf, hi, (cx - radius // 3, cy - radius // 3), max(1, radius // 3))
    pygame.draw.circle(surf, C.nuit, (cx, cy), radius + 1, 1)
