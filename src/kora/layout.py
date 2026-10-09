"""LES MISES EN PAGE de l'interface : ou est chaque chose a l'ecran.

Des fonctions PURES (rectangles, cases visees par la souris) : la barre du
haut, les onglets et panneaux lateraux, l'arbre des savoirs (sa toile et sa
camera), les cartes de bande, les nouvelles, la projection de la carte. Le
dessin est ailleurs (render.py, render_*.py) ; les tests s'en servent sans
fenetre. Le plus bas des modules de l'interface : il n'importe que la
simulation et theme.py.
"""

from __future__ import annotations

import math

from src.kora import numbers, tech, tree_graph
from src.kora.globe import hex_to_globe_screen
from src.kora.log import FILTER_ALL, LogKind
from src.kora.types import Hex
from src.kora.vision import enemy_band_visible
from src.kora.world import axial_to_offset


def page_layout(area) -> dict:
    """area : la place sous la barre des onglets (toile + fiche)."""
    x0, y0, w, h = area
    lw = int(w * 0.48)
    left = (x0, y0, lw, h)
    right = (x0 + lw + 16, y0, w - lw - 16, h)
    top = y0 + 52
    calc_h = 118
    card_h = max(52, min(96, (h - (top - y0) - calc_h - 14) // 4 - 8))
    bases = {}
    for i, base in enumerate(numbers.BASE_ORDER):
        cy = top + i * (card_h + 8)
        card = (x0, cy, lw, card_h)
        btn = (x0 + lw - 12 - 150, cy + (card_h - 28) // 2, 150, 28)
        bases[base] = {"card": card, "btn": btn}
    calc = (x0, top + 4 * (card_h + 8) + 6, lw, calc_h)
    rows = len(numbers.OPS) + 1
    row_top = y0 + 52
    row_h = max(48, min(86, (h - (row_top - y0) - 8) // rows - 6))
    ops = {}
    for i, op in enumerate(numbers.OPS):
        ops[op[0]] = (right[0], row_top + i * (row_h + 6), right[2], row_h)
    later = (right[0], row_top + len(numbers.OPS) * (row_h + 6), right[2], row_h)
    return {"left": left, "right": right, "bases": bases, "calc": calc, "ops": ops, "later": later}


def numbers_items(lay: dict) -> dict:
    """Le bouton de l'onglet des nombres : la base se choisit dans Pays, Lois."""
    return {"nlaws": lay["bases"][10]["btn"]}


def panel_box(width: int, height: int, panel: str, tab_w: int = 66) -> tuple:
    top = HUD_HEIGHT + 12
    if panel == "tribu":
        bw = max(540, min(680, width - tab_w - 24))
    else:
        bw = max(600, min(880, width - tab_w - 24))
    bh = max(420, min(660, height - top - 14))
    return (width - tab_w - bw - 8, top, bw, bh)


# Le rail des onglets (a droite) : une pastille par onglet, icone et nom.
TAB_W = 62


TAB_H = 66


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


BAND_HINT = "Clic : aller · clic droit sur un étranger : attaquer · Maj+clic allié : rejoindre"


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
    ("suzerains", "Suzerains [U]"),
    ("tournants", "Tournants [I]"),
    ("ressources", "Ressources [R]"),
    ("commerce", "Commerce [X]"),
)


MAP_BUTTON_W = 270
MAP_BUTTON_H = 34
MAP_ITEM_H = 32
# Les legendes des modes de carte : en haut a droite, sous la barre.
MAP_LEGEND_W = 620


def map_mode_layout(width: int, height: int, open_: bool = False) -> dict:
    """Le bouton des modes de carte, en bas a gauche de l'ecran ; ouvert, la
    liste des modes se deroule au-dessus de lui. "legend" : la place des
    legendes (en haut a droite, a gauche des onglets)."""
    button = (12, height - MAP_BUTTON_H - 12, MAP_BUTTON_W, MAP_BUTTON_H)
    items = {}
    if open_:
        y = button[1] - 6 - len(MAP_MODES) * MAP_ITEM_H
        for key, _label in MAP_MODES:
            items[key] = (12, y, MAP_BUTTON_W, MAP_ITEM_H - 2)
            y += MAP_ITEM_H
    right = width - TAB_W - 14
    lw = min(MAP_LEGEND_W, right - 12)
    return {"button": button, "items": items, "legend": (right - lw, HUD_HEIGHT + 8, lw)}


def map_mode_hit(layout: dict, mx: int, my: int):
    """Un mode de la liste ouverte, "menu" (le bouton), ou None."""
    if not layout:
        return None
    for key, rect in layout.get("items", {}).items():
        if _contains(rect, mx, my):
            return key
    if _contains(layout["button"], mx, my):
        return "menu"
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


# La rangee des grands tournants (turning.py) : plus haute, des cartes larges.
TREE_TURN_ROW = 136


TREE_TURN_H = 108


TREE_ZOOM_MAX = 1.6


TREE_ZOOM_STEP = 1.15


# Anciens noms (d'autres modules les lisent encore).
TECH_ROW_H = TREE_ROW


TECH_GUTTER = TREE_GUTTER


_TREE: dict = {}


def tech_world() -> dict:
    """La toile de l'arbre, a l'echelle 1 : place comme un GRAPHE
    (tree_graph.py : une couche par palier, l'ordre qui croise le moins,
    chacun sous ce dont il depend, la place laissee aux liens), une
    banniere par age ; la marge de gauche nomme les paliers."""
    if _TREE:
        return _TREE
    geo = tree_graph.geometry(TREE_PAD + TREE_GUTTER, TREE_PAD, {0: TREE_COLHEAD, 1: TREE_BAND})
    width, height = geo["size"]
    _TREE.update({
        "size": (width, height + TREE_PAD),
        "cols": [],
        "col_w": TREE_COL,
        "rows": geo["rows"],
        "heights": geo["heights"],
        "sections": geo["sections"],
        "nodes": geo["nodes"],
        "links": geo["links"],
    })
    return _TREE



def tree_zoom_min(view, world) -> float:
    """Tout l'arbre tient dans la vue."""
    ww, wh = world["size"]
    return max(0.12, min(view[2] / ww, view[3] / wh))


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
        numbers = page_layout((bx + 14, top + 6, bw - 28, by + bh - 12 - top - 6))
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


# Le pays et ses lois (render_country.py) : avec la premiere loi possible.
COUNTRY_TAB = ("pays", "Pays")


def side_tabs(army: bool = False, commerce: bool = False, treasury: bool = False, country: bool = False) -> tuple:
    return (
        SIDE_TABS
        + ((ARMY_TAB,) if army else ())
        + ((COMMERCE_TAB,) if commerce else ())
        + ((TREASURY_TAB,) if treasury else ())
        + ((COUNTRY_TAB,) if country else ())
    )


def side_layout(width: int, height: int, panel: str | None = None, era: int = 0, army: bool = False, commerce: bool = False, tech_cam=None, tech_tab: str = "arbre", treasury: bool = False, country: bool = False) -> dict:
    tab_w, gap = TAB_W, 6
    tab_x = width - tab_w - 4
    top = HUD_HEIGHT + 44
    shown = side_tabs(army, commerce, treasury, country)
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
            items.update(numbers_items(tech_panel["numbers"]))
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


def _hex_corners(cx: float, cy: float, zoom: float) -> list[tuple[float, float]]:
    size = HEX_SIZE * zoom
    pts = []
    for i in range(6):
        angle = math.radians(60 * i - 30)
        pts.append((cx + size * math.cos(angle), cy + size * math.sin(angle)))
    return pts
