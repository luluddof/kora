"""Fenetres du village et des batailles, dans le style de l'ecran des
savoirs (cadre dore, cartes en degrade, graphes) :
  - "Fonder un village" : le lieu, ce qui change, le serment (un choix) ;
  - l'ecran du village : tuiles, terres (petite carte, recoltes), batiments,
    guerriers ;
  - le rapport de bataille : les deux camps, le moral passe par passe.
Les *_layout sont des fonctions pures (tests) ; le reste dessine.
"""

from __future__ import annotations

import math

import pygame
import pygame.gfxdraw

from src.kora import battle, villages
from src.kora.look import BIOME_COLORS
from src.kora.peoples import color_of
from src.kora.render import HUD_HEIGHT
from src.kora.render_tech import (
    BAD,
    GOLD,
    GOLD_DEEP,
    GOLD_DIM,
    GOOD,
    INK,
    NOTE,
    SOFT,
    _aacircle,
    _button,
    _check,
    _cross,
    _fit,
    _gradient_card,
    _lerp,
    _lock,
    _ornate_frame,
    _tick,
    _wrap,
)
from src.kora.sim import PLAYER_TRIBE_ID
from src.kora.types import Hex

WARN = (236, 170, 90)
CARD = {
    "bati": ((86, 70, 38), (54, 43, 24), (226, 190, 106), (246, 236, 208)),
    "chantier": ((36, 62, 90), (22, 38, 60), (124, 186, 240), (232, 240, 248)),
    "possible": ((36, 66, 42), (22, 42, 27), (132, 208, 120), (234, 244, 228)),
    "attente": ((40, 42, 48), (28, 30, 35), (96, 100, 108), (184, 186, 192)),
    "verrouille": ((27, 28, 32), (20, 21, 24), (58, 60, 66), (116, 118, 124)),
}
STATUS_LABEL = {"bati": "Bati", "chantier": "En chantier", "possible": "Possible", "attente": "Pas encore", "verrouille": "Verrouille"}


def _fonts(r):
    if not hasattr(r, "tech_title"):
        from src.kora.render_tech import _fonts as tf

        tf(r)
    return r.tech_title, r.tech_head


def _hover(rect, mx, my) -> bool:
    x, y, w, h = rect
    return x <= mx <= x + w and y <= my <= y + h


def _dim(r) -> None:
    w, h = r.screen.get_size()
    veil = pygame.Surface((w, h), pygame.SRCALPHA)
    veil.fill((6, 8, 12, 150))
    r.screen.blit(veil, (0, 0))


def _frame(r, rect) -> None:
    x, y, w, h = rect
    r.screen.blit(_gradient_card(w, h, (28, 32, 42), (13, 15, 20), 8), (x, y))
    _ornate_frame(r.screen, rect)


def _plain_button(r, rect, label: str, hover: bool, font=None) -> None:
    """Bouton discret (annuler, fermer) : sombre, filet dore au survol."""
    font = font or r.small
    x, y, w, h = rect
    r.screen.blit(_gradient_card(w, h, (58, 60, 68) if hover else (44, 46, 52), (34, 36, 40), 6), (x, y))
    pygame.draw.rect(r.screen, GOLD if hover else (96, 98, 106), rect, 1, border_radius=6)
    surf = font.render(_fit(font, label, w - 10), True, INK)
    r.screen.blit(surf, (x + (w - surf.get_width()) // 2, y + (h - surf.get_height()) // 2))


def _section(r, x, y, w, title) -> int:
    r.screen.blit(r.tiny.render(title, True, GOLD), (x, y))
    pygame.draw.line(r.screen, GOLD_DEEP, (x, y + 16), (x + w, y + 16))
    return y + 22


# --- dessins : batiments et serments ---------------------------------------------------


def glyph(surf, key: str, color, s: int) -> None:
    c = s // 2
    w = max(2, s // 10)
    line = pygame.draw.line
    poly = pygame.draw.polygon
    if key in ("palissade", "pieux"):
        for k in range(5):
            x = s * (0.14 + 0.18 * k)
            poly(surf, color, [(x - s * 0.06, s * 0.9), (x - s * 0.06, s * 0.3), (x, s * 0.14), (x + s * 0.06, s * 0.3), (x + s * 0.06, s * 0.9)])
        line(surf, color, (s * 0.06, s * 0.55), (s * 0.94, s * 0.55), w)
    elif key == "grenier":
        poly(surf, color, [(s * 0.14, s * 0.42), (c, s * 0.1), (s * 0.86, s * 0.42)])
        pygame.draw.rect(surf, color, (s * 0.24, s * 0.42, s * 0.52, s * 0.3), w)
        for x in (0.3, 0.5, 0.7):
            line(surf, color, (s * x, s * 0.72), (s * x, s * 0.92), w)
    elif key == "puits":
        pygame.draw.ellipse(surf, color, (s * 0.18, s * 0.5, s * 0.64, s * 0.36), w)
        line(surf, color, (s * 0.24, s * 0.66), (s * 0.24, s * 0.2), w)
        line(surf, color, (s * 0.76, s * 0.66), (s * 0.76, s * 0.2), w)
        line(surf, color, (s * 0.16, s * 0.2), (s * 0.84, s * 0.2), w)
        line(surf, color, (c, s * 0.2), (c, s * 0.46), 1)
    elif key == "maison_longue":
        poly(surf, color, [(s * 0.06, s * 0.52), (s * 0.28, s * 0.22), (s * 0.72, s * 0.22), (s * 0.94, s * 0.52)])
        pygame.draw.rect(surf, color, (s * 0.12, s * 0.52, s * 0.76, s * 0.34), w)
        pygame.draw.rect(surf, color, (s * 0.44, s * 0.64, s * 0.12, s * 0.22))
    elif key == "enclos":
        for x in (0.12, 0.37, 0.63, 0.88):
            line(surf, color, (s * x, s * 0.3), (s * x, s * 0.88), w)
        line(surf, color, (s * 0.08, s * 0.45), (s * 0.92, s * 0.45), w)
        line(surf, color, (s * 0.08, s * 0.7), (s * 0.92, s * 0.7), w)
    elif key == "guerriers":
        line(surf, color, (s * 0.18, s * 0.9), (s * 0.78, s * 0.1), w)
        poly(surf, color, [(s * 0.78, s * 0.04), (s * 0.9, s * 0.2), (s * 0.7, s * 0.18)])
        poly(surf, color, [(s * 0.26, s * 0.32), (s * 0.7, s * 0.32), (s * 0.68, s * 0.62), (s * 0.48, s * 0.86), (s * 0.28, s * 0.62)], w)
    elif key == "tour":
        pygame.draw.rect(surf, color, (s * 0.34, s * 0.3, s * 0.32, s * 0.6), w)
        poly(surf, color, [(s * 0.24, s * 0.3), (c, s * 0.06), (s * 0.76, s * 0.3)])
        line(surf, color, (s * 0.34, s * 0.9), (s * 0.18, s * 0.96), w)
        line(surf, color, (s * 0.66, s * 0.9), (s * 0.82, s * 0.96), w)
    elif key == "autel":
        pygame.draw.rect(surf, color, (s * 0.16, s * 0.6, s * 0.68, s * 0.14))
        pygame.draw.rect(surf, color, (s * 0.24, s * 0.74, s * 0.12, s * 0.18))
        pygame.draw.rect(surf, color, (s * 0.64, s * 0.74, s * 0.12, s * 0.18))
        poly(surf, color, [(c, s * 0.1), (s * 0.66, s * 0.38), (s * 0.6, s * 0.56), (s * 0.4, s * 0.56), (s * 0.34, s * 0.38)])
    elif key == "pierre":
        poly(surf, color, [(s * 0.36, s * 0.92), (s * 0.32, s * 0.2), (c, s * 0.06), (s * 0.66, s * 0.22), (s * 0.64, s * 0.92)])
        line(surf, color, (s * 0.12, s * 0.92), (s * 0.88, s * 0.92), w)
    elif key == "champs":
        line(surf, color, (c, s * 0.92), (c, s * 0.18), w)
        for k in range(3):
            y = s * (0.3 + 0.18 * k)
            pygame.draw.ellipse(surf, color, (c - s * 0.3, y, s * 0.26, s * 0.14))
            pygame.draw.ellipse(surf, color, (c + s * 0.04, y, s * 0.26, s * 0.14))
    elif key == "feu":
        poly(surf, color, [(c, s * 0.06), (s * 0.78, s * 0.5), (s * 0.7, s * 0.78), (c, s * 0.9), (s * 0.3, s * 0.78), (s * 0.22, s * 0.5)])
    elif key == "potiers":
        poly(surf, color, [(s * 0.36, s * 0.1), (s * 0.64, s * 0.1), (s * 0.58, s * 0.26), (s * 0.8, s * 0.5), (s * 0.66, s * 0.9), (s * 0.34, s * 0.9), (s * 0.2, s * 0.5), (s * 0.42, s * 0.26)])
    elif key == "sauniers":
        for x0, y0 in ((0.3, 0.62), (0.55, 0.5), (0.72, 0.68)):
            poly(surf, color, [(s * x0, s * (y0 - 0.26)), (s * (x0 + 0.14), s * y0), (s * x0, s * (y0 + 0.26)), (s * (x0 - 0.14), s * y0)])
    elif key == "tisserands":
        pygame.draw.circle(surf, color, (c, int(s * 0.44)), int(s * 0.3), w)
        line(surf, color, (s * 0.26, s * 0.3), (s * 0.74, s * 0.58), 1)
        line(surf, color, (s * 0.24, s * 0.46), (s * 0.76, s * 0.42), 1)
        line(surf, color, (c, s * 0.74), (c, s * 0.94), w)
    elif key == "tailleurs":
        line(surf, color, (s * 0.24, s * 0.92), (s * 0.66, s * 0.2), w + 1)
        poly(surf, color, [(s * 0.52, s * 0.08), (s * 0.9, s * 0.2), (s * 0.84, s * 0.46), (s * 0.58, s * 0.34)])
    elif key == "pecheurs":
        pygame.draw.ellipse(surf, color, (s * 0.1, s * 0.34, s * 0.6, s * 0.32))
        poly(surf, color, [(s * 0.66, s * 0.5), (s * 0.92, s * 0.3), (s * 0.92, s * 0.7)])
    elif key == "pelletiers":
        # Une peau tendue.
        poly(surf, color, [(s * 0.3, s * 0.1), (s * 0.7, s * 0.1), (s * 0.66, s * 0.3), (s * 0.9, s * 0.4), (s * 0.72, s * 0.56), (s * 0.8, s * 0.9),
                           (c, s * 0.76), (s * 0.2, s * 0.9), (s * 0.28, s * 0.56), (s * 0.1, s * 0.4), (s * 0.34, s * 0.3)])
    elif key == "atelier":
        # Un marteau et un pot.
        line(surf, color, (s * 0.16, s * 0.86), (s * 0.5, s * 0.42), w + 1)
        pygame.draw.rect(surf, color, (s * 0.4, s * 0.16, s * 0.3, s * 0.2))
        pygame.draw.ellipse(surf, color, (s * 0.56, s * 0.52, s * 0.32, s * 0.36), w)
    elif key == "place":
        # Deux paniers sous un auvent.
        poly(surf, color, [(s * 0.08, s * 0.4), (c, s * 0.12), (s * 0.92, s * 0.4)])
        pygame.draw.rect(surf, color, (s * 0.16, s * 0.56, s * 0.26, s * 0.3), w)
        pygame.draw.rect(surf, color, (s * 0.58, s * 0.56, s * 0.26, s * 0.3), w)
    else:
        pygame.draw.circle(surf, color, (c, c), s // 3, w)


def medal(key: str, edge, fill, radius: int) -> pygame.Surface:
    d = radius * 2 + 2
    surf = pygame.Surface((d, d), pygame.SRCALPHA)
    pygame.gfxdraw.filled_circle(surf, radius, radius, radius, _lerp(fill, (0, 0, 0), 0.35) + (255,))
    pygame.gfxdraw.aacircle(surf, radius, radius, radius, edge + (255,))
    s = int(radius * 1.2)
    icon = pygame.Surface((s, s), pygame.SRCALPHA)
    glyph(icon, key, edge + (255,), s)
    surf.blit(icon, (radius - s // 2 + 1, radius - s // 2 + 1))
    return surf


# --- fonder un village -----------------------------------------------------------------


def found_layout(width: int, height: int) -> dict:
    bw = min(940, width - 60)
    bh = min(600, height - HUD_HEIGHT - 30)
    bx = (width - bw) // 2
    by = HUD_HEIGHT + max(10, (height - HUD_HEIGHT - bh) // 2)
    left_w = int(bw * 0.40)
    right_x = bx + 24 + left_w + 18
    right_w = bx + bw - 24 - right_x
    top = by + 108
    card_w = (right_w - 12) // 2
    card_h = 150
    oaths = {}
    for i, oid in enumerate(villages.OATH_ORDER):
        col, row = i % 2, i // 2
        oaths[oid] = (right_x + col * (card_w + 12), top + 24 + row * (card_h + 10), card_w, card_h)
    ok = (bx + bw - 24 - 250, by + bh - 52, 250, 34)
    cancel = (ok[0] - 12 - 160, by + bh - 52, 160, 34)
    return {
        "box": (bx, by, bw, bh),
        "left": (bx + 24, top, left_w, bh - (top - by) - 70),
        "right": (right_x, top, right_w, 24 + 2 * (card_h + 10)),
        "oaths": oaths,
        "ok": ok,
        "cancel": cancel,
    }


def found_hit(lay: dict, mx: int, my: int):
    if not lay:
        return None
    for oid, rect in lay["oaths"].items():
        if _hover(rect, mx, my):
            return f"oath:{oid}"
    if _hover(lay["ok"], mx, my):
        return "found_ok"
    if _hover(lay["cancel"], mx, my):
        return "found_cancel"
    if _hover(lay["box"], mx, my):
        return "panel"
    return None


def draw_found(r, state, ui) -> None:
    band = state.bands.get(ui.get("found"))
    if band is None:
        r.found_hits = {}
        return
    w, h = r.screen.get_size()
    lay = found_layout(w, h)
    r.found_hits = lay
    title_font, head_font = _fonts(r)
    info = villages.found_preview(state, band.id)
    _dim(r)
    _frame(r, lay["box"])
    bx, by, bw, bh = lay["box"]
    screen = r.screen
    mx, my = pygame.mouse.get_pos()
    screen.blit(title_font.render("Fonder un village", True, GOLD), (bx + 24, by + 16))
    screen.blit(r.small.render("Un tournant : votre peuple cesse d'errer. On ne revient pas en arriere sans tout perdre.", True, SOFT), (bx + 26, by + 50))
    name_s = head_font.render(f"{info['name']}", True, INK)
    screen.blit(r.tiny.render("NOM DU VILLAGE", True, GOLD_DIM), (bx + 26, by + 76))
    screen.blit(name_s, (bx + 140, by + 72))
    count = f"Villages : {info['villages']}/{info['villages_max']}  ·  {info['population']} personnes s'installent"
    cs = r.tiny.render(count, True, NOTE)
    screen.blit(cs, (bx + bw - 26 - cs.get_width(), by + 78))
    # A gauche : le lieu, ce qui change.
    x, y, lw, lh = lay["left"]
    y = _section(r, x, y, lw, "LE LIEU")
    rows = [
        (f"Champs : {info['fields']} sur les {info['fields_max']} voulus  ·  fertilite {100 * info['fertility']:.0f} %", SOFT),
        (f"Premiere recolte : ~{info['harvest']:.0f} vivres (semences {100 * info['seed_ratio']:.0f} %)", SOFT),
    ]
    if info["resources"]:
        rows.append(("Autour : " + ", ".join(info["resources"]), SOFT))
    for text, color in rows:
        for part in _wrap(r.tiny, text, lw):
            screen.blit(r.tiny.render(part, True, color), (x, y))
            y += 15
    for risk in info["risks"]:
        for k, part in enumerate(_wrap(r.tiny, risk, lw - 16)):
            if k == 0:
                _cross(screen, x + 5, y + 7, 3)
            screen.blit(r.tiny.render(part, True, WARN), (x + 14, y))
            y += 15
    y += 8
    y = _section(r, x, y, lw, "CE QUI CHANGE")
    gains = [
        "Des champs sur les meilleures terres alentour, semes au printemps",
        f"Un grenier : {villages.STORE_WEEKS} semaines de reserve de plus",
        "La population croit plus vite (x1,4)",
        "Des batiments a construire au village",
        "Des guerriers a lever : les premieres armees",
    ]
    costs = [
        "Le village ne marche plus : il se defend sur place",
        "Le grain attire les pillards",
        "Les fievres guettent les gros villages",
    ]
    for text in gains:
        for k, part in enumerate(_wrap(r.tiny, text, lw - 16)):
            if k == 0:
                _tick(screen, x + 6, y + 7)
            screen.blit(r.tiny.render(part, True, (184, 222, 168)), (x + 16, y))
            y += 15
    for text in costs:
        for k, part in enumerate(_wrap(r.tiny, text, lw - 16)):
            if k == 0:
                _cross(screen, x + 6, y + 7, 3)
            screen.blit(r.tiny.render(part, True, (226, 160, 140)), (x + 16, y))
            y += 15
    # A droite : le serment.
    rx, ry, rw, _rh = lay["right"]
    _section(r, rx, ry, rw, "LE SERMENT DE FONDATION  ·  un choix pour toujours")
    pick = ui.get("found_oath")
    for oid, rect in lay["oaths"].items():
        oath = villages.OATHS[oid]
        cx, cy, cw, ch = rect
        on = oid == pick
        hover = _hover(rect, mx, my)
        top, bot, edge, text_c = CARD["bati" if on else ("possible" if hover else "attente")]
        if on:
            glow = pygame.Surface((cw + 12, ch + 12), pygame.SRCALPHA)
            pygame.draw.rect(glow, edge + (70,), (0, 0, cw + 12, ch + 12), border_radius=10)
            screen.blit(glow, (cx - 6, cy - 6))
        screen.blit(_gradient_card(cw, ch, top, bot, 6), (cx, cy))
        pygame.draw.rect(screen, (250, 244, 226) if on else edge, rect, 2 if on or hover else 1, border_radius=6)
        screen.blit(medal(oid, edge, top, 15), (cx + 8, cy + 8))
        screen.blit(r.small.render(_fit(r.small, oath.name, cw - 56), True, text_c), (cx + 46, cy + 14))
        yy = cy + 40
        for part in _wrap(r.tiny, oath.text, cw - 18)[:3]:
            screen.blit(r.tiny.render(part, True, SOFT), (cx + 10, yy))
            yy += 14
        yy += 4
        for eff in oath.lines:
            for k, part in enumerate(_wrap(r.tiny, eff, cw - 32)[:2]):
                if k == 0:
                    pygame.draw.polygon(screen, (184, 222, 168), [(cx + 12, yy + 3), (cx + 18, yy + 7), (cx + 12, yy + 11)])
                screen.blit(r.tiny.render(part, True, (184, 222, 168)), (cx + 22, yy))
                yy += 14
        if on:
            _check(screen, cx + cw - 10, cy + 10, GOLD)
    # Le premier village : un age commence.
    by2 = lay["right"][1] + lay["right"][3] + 6
    if info["first"]:
        band_rect = (rx, by2, rw, 50)
        screen.blit(_gradient_card(rw, 50, (70, 52, 26), (40, 30, 16), 6), (rx, by2))
        pygame.draw.rect(screen, GOLD, band_rect, 1, border_radius=6)
        screen.blit(r.small.render("PREMIER VILLAGE : l'age des villages commence", True, GOLD), (rx + 12, by2 + 6))
        screen.blit(r.tiny.render(f"+{villages.FIRST_VILLAGE_PRESTIGE} prestige  ·  vos villages pourront lever des troupes", True, INK), (rx + 12, by2 + 28))
    # Boutons.
    ok_on = pick in villages.OATHS
    _button(screen, head_font, lay["ok"], _fit(head_font, f"Fonder {info['name']}", lay["ok"][2] - 16), ok_on, ok_on and _hover(lay["ok"], mx, my))
    _plain_button(r, lay["cancel"], "Pas maintenant", _hover(lay["cancel"], mx, my))
    if not ok_on:
        hint = r.tiny.render("Choisissez d'abord le serment du village.", True, WARN)
        screen.blit(hint, (lay["cancel"][0] - hint.get_width() - 14, lay["ok"][1] + 10))


# --- l'ecran du village -----------------------------------------------------------------


PAGES = (("village", "Le village"), ("metiers", "Metiers et echanges"))


def village_layout(width: int, height: int, n_armies: int = 0, page: str = "village") -> dict:
    from src.kora import goods

    bx = 12
    by = HUD_HEIGHT + 6
    bw = max(760, width - 32 - 24)
    bh = max(480, height - HUD_HEIGHT - 14)
    close = (bx + bw - 24 - 136, by + 16, 136, 28)
    leave = (close[0] - 10 - 150, by + 16, 150, 28)
    split = (leave[0] - 10 - 180, by + 16, 180, 28)
    # Onglets de l'ecran : le village, ses metiers et ses echanges.
    pages = {}
    px = bx + 24
    for key, _label in PAGES:
        pw = 150 if key == "village" else 200
        pages[key] = (px, by + 60, pw, 26)
        px += pw + 8
    tiles_y = by + 94
    n = 7
    tw = (bw - 48 - (n - 1) * 10) // n
    tiles = [(bx + 24 + i * (tw + 10), tiles_y, tw, 56) for i in range(n)]
    body_y = tiles_y + 56 + 14
    body_h = by + bh - 14 - body_y
    inner = bw - 48
    lw = int(inner * 0.29)
    mw = int(inner * 0.45)
    rw = inner - lw - mw - 32
    left = (bx + 24, body_y, lw, body_h)
    mid = (left[0] + lw + 16, body_y, mw, body_h)
    right = (mid[0] + mw + 16, body_y, rw, body_h)
    # Batiments : 4 colonnes de cartes.
    per_row = 4
    rows_n = -(-len(villages.BUILD_ORDER) // per_row)
    card_w = (mw - (per_row - 1) * 8) // per_row
    card_h = max(58, min(78, (body_h - 24 - 190) // rows_n - 8))
    cards = {}
    for i, bid in enumerate(villages.BUILD_ORDER):
        col, row = i % per_row, i // per_row
        cards[bid] = (mid[0] + col * (card_w + 8), body_y + 24 + row * (card_h + 8), card_w, card_h)
    detail_y = body_y + 24 + rows_n * (card_h + 8) + 6
    detail = (mid[0], detail_y, mw, body_y + body_h - detail_y)
    half = (mw - 16) // 2
    build = (mid[0] + half - 12 - 160, detail[1] + detail[3] - 12 - 30, 160, 30)
    today = (mid[0] + half + 16, detail_y + 10, mw - half - 28, detail[3] - 20)
    # Guerriers : le type (un par role), la taille, puis les troupes.
    from src.kora import units as _units

    type_w = (rw - 8) // 2
    types = {}
    for i, role in enumerate(_units.ROLES):
        types[role] = (right[0] + (i % 2) * (type_w + 8), body_y + 52 + (i // 2) * 28, type_w, 24)
    chip_w = (rw - 2 * 8) // 3
    chips = {key: (right[0] + i * (chip_w + 8), body_y + 118, chip_w, 24) for i, (key, _s, _l) in enumerate(villages.LEVIES)}
    raise_ = (right[0], body_y + 190, rw, 30)
    rows = []
    y = raise_[1] + 84
    bw3 = (rw - 16 - 2 * 6) // 3
    for i in range(max(0, n_armies)):
        by3 = y + 38
        rows.append(
            {
                "row": (right[0], y, rw, 64),
                "see": (right[0] + 8, by3, bw3, 20),
                "reequip": (right[0] + 8 + bw3 + 6, by3, bw3, 20),
                "recall": (right[0] + 8 + 2 * (bw3 + 6), by3, bw3, 20),
            }
        )
        y += 70
    mini = (left[0], body_y + 24, lw, min(240, int(body_h * 0.46)))
    gy = mini[1] + mini[3] + 54
    graph = (left[0], gy, lw, max(80, body_y + body_h - gy - 26))
    # Page des metiers : une carte par metier a gauche ; reserve, bras et
    # echanges a droite.
    craft_w = int(inner * 0.58)
    crafts = {}
    row_h = max(48, min(96, (body_h - 24) // len(goods.CRAFT_ORDER) - 6))
    for i, cid in enumerate(goods.CRAFT_ORDER):
        rx = bx + 24
        ry = body_y + 24 + i * (row_h + 6)
        plus = (rx + craft_w - 12 - 26, ry + 10, 26, 22)
        minus = (plus[0] - 8 - 44 - 8 - 26, ry + 10, 26, 22)
        crafts[cid] = {"card": (rx, ry, craft_w, row_h), "minus": minus, "plus": plus}
    stores = (bx + 24 + craft_w + 16, body_y, inner - craft_w - 16, body_h)
    trade_btn = (stores[0], stores[1] + stores[3] - 30, stores[2], 28)
    return {
        "trade_btn": trade_btn,
        "page": page,
        "pages": pages,
        "crafts": crafts,
        "stores": stores,
        "box": (bx, by, bw, bh),
        "close": close,
        "leave": leave,
        "split": split,
        "tiles": tiles,
        "left": left,
        "mid": mid,
        "right": right,
        "cards": cards,
        "detail": detail,
        "build": build,
        "today": today,
        "chips": chips,
        "types": types,
        "raise": raise_,
        "armies": rows,
        "mini": mini,
        "graph": graph,
    }


def village_hit(lay: dict, mx: int, my: int, armies: list | None = None):
    if not lay:
        return None
    if _hover(lay["close"], mx, my):
        return "vclose"
    if _hover(lay["leave"], mx, my):
        return "vleave"
    if _hover(lay.get("split", (0, 0, 0, 0)), mx, my):
        return "vsplit"
    for key, rect in lay.get("pages", {}).items():
        if _hover(rect, mx, my):
            return f"vpage:{key}"
    if lay.get("page") == "metiers":
        if _hover(lay["trade_btn"], mx, my):
            return "vtrade"
        for cid, rects in lay["crafts"].items():
            if _hover(rects["minus"], mx, my):
                return f"vteam-:{cid}"
            if _hover(rects["plus"], mx, my):
                return f"vteam+:{cid}"
        return "panel" if _hover(lay["box"], mx, my) else None
    for bid, rect in lay["cards"].items():
        if _hover(rect, mx, my):
            return f"vb:{bid}"
    if _hover(lay["build"], mx, my):
        return "vbuild"
    for key, rect in lay["chips"].items():
        if _hover(rect, mx, my):
            return f"levy:{key}"
    for role, rect in lay.get("types", {}).items():
        if _hover(rect, mx, my):
            return f"ltype:{role}"
    if _hover(lay["raise"], mx, my):
        return "vraise"
    for i, row in enumerate(lay["armies"]):
        if armies is None or i >= len(armies):
            break
        if _hover(row["see"], mx, my):
            return f"vsee:{armies[i]}"
        if _hover(row["reequip"], mx, my):
            return f"vreequip:{armies[i]}"
        if _hover(row["recall"], mx, my):
            return f"vrecall:{armies[i]}"
    if _hover(lay["box"], mx, my):
        return "panel"
    return None


def _tile(r, rect, label, value, sub, color=INK) -> None:
    x, y, w, h = rect
    r.screen.blit(_gradient_card(w, h, (38, 42, 52), (24, 26, 32), 6), (x, y))
    pygame.draw.rect(r.screen, GOLD_DEEP, rect, 1, border_radius=6)
    r.screen.blit(r.tiny.render(label, True, GOLD_DIM), (x + 10, y + 5))
    r.screen.blit(r.font.render(_fit(r.font, value, w - 18), True, color), (x + 10, y + 19))
    if sub:
        r.screen.blit(r.tiny.render(_fit(r.tiny, sub, w - 18), True, NOTE), (x + 10, y + 39))


def draw_village(r, state, ui) -> None:
    site = state.sites.get(ui.get("village_open"))
    band = villages.band_of(state, site) if site is not None and site.kind == "village" else None
    if band is None:
        r.village_hits = {}
        return
    armies = villages.armies_of(state, site)
    w, h = r.screen.get_size()
    page = ui.get("village_page") or "village"
    lay = village_layout(w, h, len(armies), page)
    r.village_hits = lay
    r.village_armies = [a.id for a in armies]
    title_font, head_font = _fonts(r)
    screen = r.screen
    mx, my = pygame.mouse.get_pos()
    _frame(r, lay["box"])
    bx, by, bw, bh = lay["box"]
    tribe = state.tribes[band.tribe_id]
    color = color_of(tribe)
    pygame.draw.rect(screen, color, (bx + 22, by + 18, 6, 34), border_radius=2)
    screen.blit(title_font.render(villages.name(site), True, GOLD), (bx + 36, by + 12))
    oath = villages.OATHS.get(villages.oath_of(site))
    sub = f"{villages.rank_name(band.population)} des {tribe.name}  ·  fonde en l'an {site.founded or '?'}"
    sub += f"  ·  serment : {oath.name}" if oath else "  ·  sans serment"
    screen.blit(r.tiny.render(sub, True, NOTE), (bx + 38, by + 42))
    _button(screen, r.small, lay["close"], "Fermer [Echap]", True, _hover(lay["close"], mx, my))
    confirm = ui.get("leave_confirm")
    leave_label = "Confirmer ?" if confirm else "Abandonner"
    lx, ly, lw_, lh_ = lay["leave"]
    hover = _hover(lay["leave"], mx, my)
    screen.blit(_gradient_card(lw_, lh_, (110, 44, 34) if hover or confirm else (60, 30, 26), (70, 26, 20) if hover or confirm else (40, 20, 18), 6), (lx, ly))
    pygame.draw.rect(screen, (200, 110, 90), lay["leave"], 1, border_radius=6)
    ls = r.small.render(leave_label, True, INK)
    screen.blit(ls, (lx + (lw_ - ls.get_width()) // 2, ly + (lh_ - ls.get_height()) // 2))
    from src.kora import orders

    why_split = orders.band_actions(state, band.id).get("split", "?")
    _button(screen, r.small, lay["split"], "Former une bande [S]", not why_split, not why_split and _hover(lay["split"], mx, my))
    if why_split and _hover(lay["split"], mx, my):
        ui.setdefault("_vtips", []).append(([(why_split, WARN)], mx, my))
    # Tuiles.
    from src.kora.sim import band_force, stock_max

    cap = stock_max(band, state)
    weeks = band.stock / max(1, band.population)
    crop = villages.expected_harvest(state, site, band)
    step, left = villages.next_step(state, site)
    warriors = sum(a.population for a in armies)
    defense = villages.defense_mult(state, band)
    tiles = (
        ("HABITANTS", f"{band.population}", f"places a batir {villages.used_slots(site)}/{villages.slots(state, site)}", INK),
        ("GRENIER", f"{band.stock:.0f} / {cap:.0f}", f"{weeks:.0f} semaines de vivres", GOOD if weeks >= 8 else WARN),
        ("SEMENCES", f"{site.data.get('seed', 0.0):.0f}", f"{step} (~{left} sem.)", INK),
        ("RECOLTE ATTENDUE", f"~{crop:.0f}" if site.data.get("fields") else "-", f"{len(site.data.get('fields', []))} champs · sol {100 * villages.soil_avg(site):.0f} %", INK),
        ("DEFENSE", f"x{defense:.2f}".replace(".", ","), f"force {band_force(state, band):.0f} · {len(villages.defense_parts(state, band))} abri(s)", INK),
        ("GUERRIERS", f"{warriors}", f"compagnies {villages.companies_of(state, site)}/{villages.army_cap(state, site)}", INK),
    )
    stab = villages.stability(state, site, band)
    tiles = tiles + (
        ("STABILITE", f"{stab:.0f}", villages.stability_word(stab), GOOD if stab >= 50 else WARN if stab >= villages.UNREST else BAD),
    )
    for rect, (label, value, sub_t, col) in zip(lay["tiles"], tiles):
        _tile(r, rect, label, value, sub_t, col)
    stab_rect = lay["tiles"][-1]
    if _hover(stab_rect, mx, my):
        rows = [(f"Stabilite {stab:.0f} : {villages.stability_word(stab)}", INK)]
        for label, v in villages.stability_parts(state, site, band):
            if label != "Base":
                rows.append((f"{'+' if v >= 0 else ''}{v:.0f}  {label}", GOOD if v >= 0 else BAD))
        rows.append(("Stable : il grandit et se bat mieux. Sous 30 : des familles partent.", NOTE))
        ui.setdefault("_vtips", []).append((rows, mx, my))
    for key, label in PAGES:
        rect = lay["pages"][key]
        _page_tab(r, rect, label, key == page, _hover(rect, mx, my))
    if page == "metiers":
        _draw_crafts(r, state, site, band, lay, ui, head_font, mx, my)
        for tip, tx, ty in ui.pop("_vtips", []):
            _tip(r, tip, tx, ty)
        return
    _draw_lands(r, state, site, band, lay)
    _draw_buildings(r, state, site, band, lay, ui, head_font, mx, my)
    _draw_warriors(r, state, site, band, armies, lay, ui, mx, my)


def _page_tab(r, rect, label: str, active: bool, hover: bool) -> None:
    x, y, w, h = rect
    top = (74, 62, 36) if active else (46, 48, 56) if hover else (34, 36, 42)
    r.screen.blit(_gradient_card(w, h, top, (24, 24, 28), 6), (x, y))
    pygame.draw.rect(r.screen, GOLD if active else GOLD_DEEP, rect, 1, border_radius=6)
    if active:
        pygame.draw.line(r.screen, GOLD, (x + 8, y + h - 2), (x + w - 8, y + h - 2), 2)
    surf = r.small.render(_fit(r.small, label, w - 12), True, INK if active else SOFT)
    r.screen.blit(surf, (x + (w - surf.get_width()) // 2, y + (h - surf.get_height()) // 2))


CRAFT_CARD = {
    "actif": ((70, 60, 34), (44, 38, 24), (226, 190, 106), (246, 236, 208)),
    "possible": ((36, 66, 42), (22, 42, 27), (132, 208, 120), (234, 244, 228)),
    "absent": ((40, 42, 48), (28, 30, 35), (96, 100, 108), (184, 186, 192)),
    "verrouille": ((27, 28, 32), (20, 21, 24), (58, 60, 66), (116, 118, 124)),
}


def _draw_crafts(r, state, site, band, lay, ui, head_font, mx, my) -> None:
    from src.kora import diplo, goods, tech

    screen = r.screen
    first = lay["crafts"][goods.CRAFT_ORDER[0]]["card"]
    x0, cw = first[0], first[2]
    y0 = lay["stores"][1]
    busy = goods.workers(site, band)
    _section(r, x0, y0, cw, f"METIERS  ·  equipes {goods.total_teams(site)}/{goods.team_cap(band)} (une par {goods.TEAM_POP} habitants, {goods.TEAM} gens chacune)")
    for cid in goods.CRAFT_ORDER:
        craft = goods.CRAFTS[cid]
        rects = lay["crafts"][cid]
        cx, cy, cw_, ch = rects["card"]
        st = goods.craft_status(state, site, cid)
        top, bot, edge, text_c = CRAFT_CARD[st]
        screen.blit(_gradient_card(cw_, ch, top, bot, 6), (cx, cy))
        pygame.draw.rect(screen, edge, rects["card"], 1, border_radius=6)
        screen.blit(medal(cid, edge, top, 17), (cx + 8, cy + ch // 2 - 18))
        right = rects["minus"][0] - 12
        screen.blit(head_font.render(_fit(head_font, craft.name, right - cx - 52), True, text_c), (cx + 50, cy + (6 if ch >= 74 else 2)))
        count, best = goods.deposits(state, site, cid)
        if st == "verrouille":
            info, tint = f"Il faut connaitre {tech.TECHS[craft.needs].name}", BAD
        elif st == "absent":
            info, tint = f"Pas de {goods.res_label(cid)} dans les terres du village", NOTE
        else:
            src = goods.wild_source(state, site, cid) or "vos troupeaux"
            word = "riche" if best >= 0.7 else "correct" if best >= 0.55 else "maigre"
            info = f"{src.capitalize()} : {count} gisement{'s' if count > 1 else ''}, {word}"
            tint = SOFT
        screen.blit(r.tiny.render(_fit(r.tiny, info, right - cx - 52), True, tint), (cx + 50, cy + (28 if ch >= 74 else 20)))
        eff = " · ".join(craft.lines)
        green = (184, 222, 168) if st != "verrouille" else (110, 120, 110)
        if ch >= 74:
            screen.blit(r.tiny.render(_fit(r.tiny, craft.text, cw_ - 62), True, NOTE), (cx + 50, cy + 44))
            screen.blit(r.tiny.render(_fit(r.tiny, eff, cw_ - 62), True, green), (cx + 50, cy + min(ch - 16, 60)))
        else:
            # Petite fenetre : les effets seulement.
            screen.blit(r.tiny.render(_fit(r.tiny, eff, cw_ - 62), True, green), (cx + 50, cy + ch - 16))
        n = goods.teams_of(site, cid)
        top_n = goods.max_teams(state, site, cid)
        why = goods.add_block(state, site, cid)
        _button(screen, r.small, rects["minus"], "-", n > 0, n > 0 and _hover(rects["minus"], mx, my))
        _button(screen, r.small, rects["plus"], "+", not why, not why and _hover(rects["plus"], mx, my))
        mid_x = rects["minus"][0] + rects["minus"][2] + 8
        ls = r.small.render(f"{n}/{top_n}", True, INK if n else SOFT)
        screen.blit(ls, (mid_x + (44 - ls.get_width()) // 2, rects["minus"][1] + 2))
        if n:
            out = goods.output(state, site, cid)
            what = f"+{out:.0f} vivres / sem." if craft.food else f"+{_num(out)} {craft.good_name.lower()} / sem."
            ws = r.tiny.render(what, True, GOLD)
            screen.blit(ws, (rects["plus"][0] + rects["plus"][2] - ws.get_width(), rects["plus"][1] + 26))
        if why and _hover(rects["plus"], mx, my):
            ui.setdefault("_vtips", []).append(([(why, WARN)], mx, my))
    # A droite : la reserve du peuple, les bras, les echanges.
    sx, sy, sw, sh = lay["stores"]
    yy = _section(r, sx, sy, sw, "RESERVE DU PEUPLE (tous ses villages)")
    tid = band.tribe_id
    need = goods.need(state, tid)
    for good in goods.GOODS:
        have = goods.stock(state, tid, good)
        made = goods.made(state, tid, good)
        ok = goods.supplied(state, tid, good)
        screen.blit(r.small.render(goods.GOOD_NAMES[good], True, INK if have > 0 or made > 0 else SOFT), (sx, yy))
        ts = r.tiny.render(f"{have:.0f} / {goods.CAP:.0f}", True, SOFT)
        screen.blit(ts, (sx + sw - ts.get_width(), yy + 3))
        bar = (sx + 110, yy + 7, max(20, sw - 110 - ts.get_width() - 12), 6)
        pygame.draw.rect(screen, (14, 16, 20), bar, border_radius=3)
        pygame.draw.rect(screen, GOLD if ok else (90, 80, 60), (bar[0], bar[1], int(bar[2] * min(1.0, have / goods.CAP)), bar[3]), border_radius=3)
        text = f"fait {_num(made)} · mange {_num(need)} par semaine · " + ("pourvu : l'effet joue" if ok else "en manque")
        screen.blit(r.tiny.render(_fit(r.tiny, text, sw), True, GOOD if ok else NOTE), (sx, yy + 20))
        yy += 40
    yy = _section(r, sx, yy + 4, sw, "BRAS")
    hands = villages.field_hands_mult(site, band)
    rows = [
        (f"{busy} aux metiers, {band.population - busy} aux champs et a la chasse", SOFT),
        (f"Recolte rentree : x{hands:.2f}".replace(".", ",") + ("" if hands >= 1 else " (il manque des bras)"), SOFT if hands >= 1 else WARN),
        (f"Collecte du village : x{goods.forage_mult(site, band):.2f} (les gens de metier chassent moins)".replace(".", ","), SOFT),
    ]
    for text, color in rows:
        screen.blit(r.tiny.render(_fit(r.tiny, text, sw), True, color), (sx, yy))
        yy += 15
    yy = _section(r, sx, yy + 8, sw, "ECHANGES")
    _button(screen, r.small, lay["trade_btn"], "Routes commerciales [M]", True, _hover(lay["trade_btn"], mx, my))
    partners = [o for o in sorted(state.tribes) if o != tid and diplo.has_pact(state, tid, o, "commerce")]
    if not partners:
        hint = (
            "Aucun accord commercial. Proposez-en un dans Peuples [P] : vos surplus partiront chez eux, "
            "leurs biens viendront chez vous, le solde se paie en vivres."
        )
        if not tech.bonuses(state.tribes[tid]).commerce:
            hint = "Il faut connaitre Echanges lointains pour conclure des accords commerciaux (Peuples [P])."
        for part in _wrap(r.tiny, hint, sw)[:4]:
            screen.blit(r.tiny.render(part, True, NOTE), (sx, yy))
            yy += 14
        return
    for other in partners:
        if yy + 30 > sy + sh - 34:
            break
        o = state.tribes[other]
        pygame.draw.circle(screen, color_of(o), (sx + 6, yy + 8), 5)
        far = goods.trade_distance(state, tid, other) > goods.trade_range(state, tid, other)
        screen.blit(r.small.render(_fit(r.small, o.name, sw - 20), True, INK), (sx + 18, yy))
        done = goods.summary(state, tid, other)
        text = "trop loin de vos villages" if far else (done or "rien ce mois-ci")
        screen.blit(r.tiny.render(_fit(r.tiny, text, sw - 18), True, GOLD if done and not far else NOTE), (sx + 18, yy + 17))
        yy += 36


def _draw_lands(r, state, site, band, lay) -> None:
    screen = r.screen
    x, y, w, _h = lay["left"]
    _section(r, x, y, w, "TERRES")
    mx_, my_, mw, mh = lay["mini"]
    screen.blit(_gradient_card(mw, mh, (20, 24, 28), (14, 16, 20), 6), (mx_, my_))
    world = state.world
    radius = villages.FIELD_RADIUS
    size = min((mw - 16) / (math.sqrt(3) * (2 * radius + 1)), (mh - 16) / (1.5 * (2 * radius) + 2))
    cx0, cy0 = mx_ + mw / 2, my_ + mh / 2
    fields = {tuple(f) for f in site.data.get("fields", [])}
    soil = site.data.get("soil", {})
    center = site.hex
    for dq in range(-radius, radius + 1):
        for dr in range(max(-radius, -dq - radius), min(radius, -dq + radius) + 1):
            h = world.canonicalize(Hex(center.q + dq, center.r + dr))
            if h is None:
                continue
            px = cx0 + size * math.sqrt(3) * (dq + dr / 2)
            py = cy0 + size * 1.5 * dr
            corners = [(px + size * 0.95 * math.cos(math.radians(60 * k - 30)), py + size * 0.95 * math.sin(math.radians(60 * k - 30))) for k in range(6)]
            base = BIOME_COLORS.get(world.terrain(h), (90, 90, 90))
            idx = world._index(h)
            fert = villages.fertility(state, site.tribe_id, h)
            fill = _lerp(base, (0, 0, 0), 0.35)
            pygame.draw.polygon(screen, fill, corners)
            pygame.draw.polygon(screen, _lerp(base, (0, 0, 0), 0.6), corners, 1)
            key = f"{idx[0]},{idx[1]}" if idx else ""
            s = soil.get(key, 1.0)
            if idx and tuple(idx) in fields:
                gold = _lerp((120, 90, 40), (226, 196, 96), s)
                inner = [(px + (c[0] - px) * 0.7, py + (c[1] - py) * 0.7) for c in corners]
                pygame.draw.polygon(screen, gold, inner)
                for k in (-0.2, 0.1, 0.4):
                    pygame.draw.line(screen, _lerp(gold, (0, 0, 0), 0.35), (px - size * 0.45, py + size * k), (px + size * 0.45, py + size * k), 1)
            elif fert > 0.1:
                dot = _lerp((90, 110, 70), (170, 210, 120), min(1.0, fert))
                pygame.draw.circle(screen, dot, (int(px), int(py)), max(2, int(size * 0.18 * s + 1)))
            if dq == 0 and dr == 0:
                r.draw_village_icon(site, int(px), int(py) - 2, color_of(state.tribes.get(site.tribe_id)), max(5, int(size * 0.35)))
    legend = "Champs : dores au sol neuf, bruns au sol epuise. Points : bonnes terres."
    for k, part in enumerate(_wrap(r.tiny, legend, mw)[:2]):
        screen.blit(r.tiny.render(part, True, NOTE), (mx_, my_ + mh + 4 + 13 * k))
    # Recoltes : barres des dernieres annees.
    gx, gy, gw, gh = lay["graph"]
    screen.blit(r.tiny.render("RECOLTES DES DERNIERES ANNEES", True, GOLD), (gx, gy - 18))
    screen.blit(_gradient_card(gw, gh, (20, 24, 28), (14, 16, 20), 6), (gx, gy))
    history = site.data.get("history", [])
    need = band.population * 52
    top = max([c for _y, c in history] + [need * 0.6, 100])
    base_y = gy + gh - 18
    for k in range(1, 4):
        yy = int(base_y - (gh - 30) * k / 3)
        pygame.draw.line(screen, (34, 38, 46), (gx + 30, yy), (gx + gw - 8, yy))
        screen.blit(r.tiny.render(f"{top * k / 3:.0f}", True, (100, 104, 112)), (gx + 2, yy - 7))
    if not history:
        screen.blit(r.tiny.render("Pas encore de recolte.", True, NOTE), (gx + 36, gy + gh // 2 - 7))
        return
    n = len(history)
    slot = (gw - 44) / villages.HISTORY
    for i, (year, crop) in enumerate(history):
        bh_ = int((gh - 30) * crop / top)
        x0 = int(gx + 34 + (villages.HISTORY - n + i) * slot)
        bar = (x0 + 3, base_y - bh_, int(slot) - 6, bh_)
        last = i == n - 1
        pygame.draw.rect(screen, (214, 180, 104) if last else (150, 126, 72), bar, border_radius=2)
        lab = r.tiny.render(f"{year}", True, NOTE)
        screen.blit(lab, (x0 + (int(slot) - lab.get_width()) // 2, base_y + 3))
    # Ce que mange le village en un an : la recolte n'y suffit pas (encore).
    eat_y = int(base_y - (gh - 30) * min(1.0, need / top))
    pygame.draw.line(screen, (200, 110, 90), (gx + 30, eat_y), (gx + gw - 8, eat_y), 1)
    tag = r.tiny.render("ce que mange le village en un an", True, (200, 110, 90))
    screen.blit(tag, (gx + gw - 10 - tag.get_width(), max(gy + 2, eat_y - 15)))


def _draw_buildings(r, state, site, band, lay, ui, head_font, mx, my) -> None:
    screen = r.screen
    x, y, w, _h = lay["mid"]
    _section(r, x, y, w, f"BATIMENTS  ·  places {villages.used_slots(site)}/{villages.slots(state, site)} (une de plus par {villages.SLOT_POP} habitants)")
    pick = ui.get("village_pick") or next((b for b in villages.BUILD_ORDER if villages.building_status(state, site, b) == "possible"), villages.BUILD_ORDER[0])
    job = villages.works(site)
    for bid, rect in lay["cards"].items():
        b = villages.BUILDINGS[bid]
        st = villages.building_status(state, site, bid)
        top, bot, edge, text_c = CARD[st]
        cx, cy, cw, ch = rect
        hover = _hover(rect, mx, my)
        screen.blit(_gradient_card(cw, ch, top, bot, 6), (cx, cy))
        pygame.draw.rect(screen, (250, 244, 226) if bid == pick else edge, rect, 2 if bid == pick or hover else 1, border_radius=6)
        screen.blit(medal(bid, edge, top, 14), (cx + 6, cy + ch // 2 - 15))
        parts = _wrap(r.tiny, b.name, cw - 48)[:2]
        ty = cy + 10
        for part in parts:
            screen.blit(r.tiny.render(part, True, text_c), (cx + 40, ty))
            ty += 13
        if st == "chantier" and job:
            done = 1.0 - job[1] / max(1, villages.build_weeks(site, bid))
            bar = (cx + 40, cy + ch - 14, cw - 50, 5)
            pygame.draw.rect(screen, (12, 14, 18), bar, border_radius=2)
            pygame.draw.rect(screen, edge, (bar[0], bar[1], int(bar[2] * done), 5), border_radius=2)
            screen.blit(r.tiny.render(f"{job[1]} sem.", True, edge), (cx + 40, cy + ch - 30))
        else:
            screen.blit(r.tiny.render(STATUS_LABEL[st], True, edge), (cx + 40, cy + ch - 20))
        if st == "bati":
            _check(screen, cx + cw - 9, cy + 9, GOLD)
        elif st == "verrouille":
            _lock(screen, cx + cw - 11, cy + 11, edge)
    # Fiche du batiment choisi.
    dx, dy, dw, dh = lay["detail"]
    screen.blit(_gradient_card(dw, dh, (30, 32, 38), (18, 20, 24), 8), (dx, dy))
    pygame.draw.rect(screen, GOLD_DEEP, lay["detail"], 1, border_radius=8)
    b = villages.BUILDINGS[pick]
    st = villages.building_status(state, site, pick)
    top, _bot, edge, _t = CARD[st]
    half = lay["today"][0] - 16 - dx
    screen.blit(medal(pick, edge, top, 17), (dx + 10, dy + 8))
    screen.blit(head_font.render(_fit(head_font, b.name, half - 60), True, INK), (dx + 52, dy + 8))
    cost = villages.build_cost(state, site, pick)
    weeks = villages.build_weeks(site, pick)
    meta = f"{cost:.0f} vivres  ·  {weeks} semaines"
    screen.blit(r.tiny.render(_fit(r.tiny, meta, half - 60), True, NOTE), (dx + 52, dy + 30))
    yy = dy + 50
    if b.needs:
        from src.kora import tech

        known = b.needs in state.tribes[site.tribe_id].knowledge
        need = f"Savoir : {tech.TECHS[b.needs].name}"
        if known:
            _tick(screen, dx + 20, yy + 7)
        else:
            _cross(screen, dx + 20, yy + 7, 3)
        screen.blit(r.tiny.render(_fit(r.tiny, need, half - 40), True, GOOD if known else BAD), (dx + 30, yy))
        yy += 17
    for part in _wrap(r.tiny, b.text, half - 24)[:2]:
        screen.blit(r.tiny.render(part, True, SOFT), (dx + 14, yy))
        yy += 15
    yy += 3
    for eff in b.lines:
        for k, part in enumerate(_wrap(r.tiny, eff, half - 40)[:2]):
            if k == 0:
                pygame.draw.polygon(screen, (184, 222, 168), [(dx + 16, yy + 3), (dx + 22, yy + 7), (dx + 16, yy + 11)])
            screen.blit(r.tiny.render(part, True, (184, 222, 168)), (dx + 28, yy))
            yy += 15
    why = villages.build_block_site(state, site, pick)
    on = not why
    label = {"bati": "Bati", "chantier": "En chantier"}.get(st, "Construire")
    _button(screen, r.small, lay["build"], label, on, on and _hover(lay["build"], mx, my))
    if why and st != "bati":
        by_ = lay["build"][1]
        parts = _wrap(r.tiny, why, half - 24)[:2]
        for k, part in enumerate(parts):
            screen.blit(r.tiny.render(part, True, WARN), (dx + 14, by_ - 6 - 14 * (len(parts) - k)))
    pygame.draw.line(screen, GOLD_DEEP, (lay["today"][0] - 8, dy + 12), (lay["today"][0] - 8, dy + dh - 12))
    _today(r, state, site, band, lay["today"])


def _today(r, state, site, band, rect) -> None:
    """Ce que le village a deja : ses effets, en un coup d'oeil."""
    from src.kora.sim import GROWTH_RATE, bonus_of

    screen = r.screen
    x, y, w, h = rect
    screen.blit(r.tiny.render("LE VILLAGE AUJOURD'HUI", True, GOLD), (x, y))
    know = bonus_of(state, band.tribe_id)
    # GROWTH_RATE est mensuel (13 mois de 4 semaines).
    growth = ((1.0 + GROWTH_RATE * know.growth * villages.growth_mult(state, band)) ** 13 - 1.0) * 100
    parts = villages.defense_parts(state, band)
    stab = villages.stability(state, site, band)
    rows = [
        (f"Stabilite : {stab:.0f} ({villages.stability_word(stab)}), croissance x{villages.stability_growth(state, band):.2f}".replace(".", ","), GOOD if stab >= 50 else WARN),
        (f"Grenier : {know.stock_weeks + villages.store_weeks(state, band):.0f} semaines de reserve", SOFT),
        (f"Grain gate : {100 * villages.GRAIN_ROT * villages.rot_mult(state, site):.2f} % par semaine".replace(".", ","), SOFT),
        (f"Croissance : ~{growth:.0f} % par an sans famine", SOFT),
        (f"Recolte : x{villages.yield_mult(state, site):.2f}".replace(".", ",") + f"  ·  vivres x{villages.food_mult(state, band):.2f}".replace(".", ","), SOFT),
        ("Defense : " + (", ".join(f"{lab} x{m:.2f}".replace(".", ",") for lab, m in parts) if parts else "aucune"), SOFT),
        (f"Troupes : {villages.army_cap(state, site)} au plus", SOFT),
    ]
    oath = villages.OATHS.get(villages.oath_of(site))
    if oath is not None:
        rows.append((f"Serment : {oath.name}", GOLD_DIM))
    yy = y + 20
    for text, color in rows:
        for part in _wrap(r.tiny, text, w)[:2]:
            if yy + 14 > y + h:
                return
            screen.blit(r.tiny.render(part, True, color), (x, yy))
            yy += 14
        yy += 2


def _draw_warriors(r, state, site, band, armies, lay, ui, mx, my) -> None:
    from src.kora import units

    screen = r.screen
    x, y, w, _h = lay["right"]
    tribe = state.tribes[band.tribe_id]
    _section(r, x, y, w, f"GUERRIERS  ·  compagnies {villages.companies_of(state, site)}/{villages.army_cap(state, site)}")
    text = "Des villageois en armes ; dissoute, la compagnie rentre au village."
    yy = y + 22
    for part in _wrap(r.tiny, text, w)[:2]:
        screen.blit(r.tiny.render(part, True, SOFT), (x, yy))
        yy += 13
    role = ui.get("levy_role") or "melee"
    for rl, rect in lay["types"].items():
        u = units.best(tribe, rl)
        if u is None:
            first = units.ages_of(rl)[0]
            label = f"{units.ROLE_LABEL[rl]} : verrouille"
            _chip_off(r, rect, label)
            if _hover(rect, mx, my):
                from src.kora import tech

                need = tech.TECHS[first.needs].name if first.needs else "?"
                ui.setdefault("_vtips", []).append(([(first.name, INK), (f"Il faut connaitre {need}", BAD)], mx, my))
            continue
        r._draw_chip(rect, _fit(r.tiny, u.short or u.name, rect[2] - 6), rl == role)
        if _hover(rect, mx, my):
            tip = [(u.name, INK), (u.text, SOFT), (_stats(u), (184, 222, 168))]
            later = [v.name for v in units.ages_of(rl) if v.era > u.era]
            if later:
                tip.append(("Plus tard : " + ", ".join(later), NOTE))
            ui.setdefault("_vtips", []).append((tip, mx, my))
    key = ui.get("levy") or "troupe"
    share = villages.LEVY_SHARE.get(key, villages.LEVY_SHARE["troupe"])
    short = {"poignee": "Poignee", "troupe": "Troupe", "masse": "Masse"}
    for k, rect in lay["chips"].items():
        n = villages.levy_size(band, villages.LEVY_SHARE[k])
        r._draw_chip(rect, _fit(r.tiny, f"{short.get(k, k)} {n}", rect[2] - 6), k == key)
    kind = units.best(tribe, role) or units.best(tribe, "melee")
    n = villages.levy_size(band, share)
    ly = lay["chips"][key][1] + 30
    info = [
        (f"{n} {kind.name.lower()}", INK),
        (f"{min(band.stock, villages.ARMY_SUPPLY_WEEKS * n):.0f} vivres emportes · {band.population - n} restent", NOTE),
    ]
    for t, c in info:
        screen.blit(r.tiny.render(_fit(r.tiny, t, w), True, c), (x, ly))
        ly += 13
    why = villages.army_block(state, band.id, share, kind.id)
    on = not why
    _button(screen, r.small, lay["raise"], "Lever la compagnie [L]", on, on and _hover(lay["raise"], mx, my))
    if why:
        for k, part in enumerate(_wrap(r.tiny, why, w)[:2]):
            screen.blit(r.tiny.render(part, True, WARN), (x, lay["raise"][1] + 33 + 13 * k))
    top = lay["raise"][1] + 70
    screen.blit(r.tiny.render("TROUPES DU VILLAGE", True, GOLD), (x, top - 6))
    pygame.draw.line(screen, GOLD_DEEP, (x, top + 9), (x + w, top + 9))
    if not armies:
        screen.blit(r.tiny.render("Aucune troupe levee.", True, NOTE), (x, top + 14))
    for army, row in zip(armies, lay["armies"]):
        rx, ry, rw, rh = row["row"]
        screen.blit(_gradient_card(rw, rh, (40, 34, 30), (26, 22, 20), 6), (rx, ry))
        pygame.draw.rect(screen, GOLD_DEEP, row["row"], 1, border_radius=6)
        lead = army.leader.name if army.leader else "?"
        d = state.world.distance(site.hex, army.position)
        where = "au village" if d <= villages.ARMY_HOME else f"a {d} cases"
        if army.homebound:
            where = f"rentre ({d} c.)"
        head = f"{army.population} guerriers · {lead} · {where}"
        screen.blit(r.tiny.render(_fit(r.tiny, head, rw - 14), True, INK), (rx + 8, ry + 4))
        comp = " · ".join(f"{men} {units.UNITS[t].short if t in units.UNITS else t}" for t, men, _h in units.normalize(army))
        screen.blit(r.tiny.render(_fit(r.tiny, comp, rw - 14), True, SOFT), (rx + 8, ry + 20))
        _button(screen, r.tiny, row["see"], "Voir", True, _hover(row["see"], mx, my))
        re_on = not villages.reequip_block(state, army.id)
        _button(screen, r.tiny, row["reequip"], "Reequiper", re_on, re_on and _hover(row["reequip"], mx, my))
        if _hover(row["reequip"], mx, my):
            why_re = villages.reequip_block(state, army.id) or f"{units.REEQUIP_COST:.0f} vivres par homme : les armes de l'age"
            ui.setdefault("_vtips", []).append(([(why_re, WARN if not re_on else SOFT)], mx, my))
        home = d <= villages.ARMY_HOME and not army.homebound
        label = "Liberer" if home else "Dissoudre"
        on_d = not villages.dissolve_block(state, army.id)
        _button(screen, r.tiny, row["recall"], label, on_d, on_d and _hover(row["recall"], mx, my))
    for tip, tx, ty in ui.pop("_vtips", []):
        _tip(r, tip, tx, ty)


def _stats(u) -> str:
    parts = [f"attaque {_num(u.attack)}", f"tenue {_num(u.defense)}"]
    if u.ranged:
        parts.append(f"tir {_num(u.ranged)}")
    if u.pursuit != 1.0:
        parts.append(f"poursuite {_num(u.pursuit)}")
    if u.morale:
        parts.append(f"moral +{u.morale:.0f}")
    if u.forest != 1.0:
        parts.append(f"foret x{_num(u.forest)}")
    return " · ".join(parts)


def _num(v: float) -> str:
    return f"{v:.2f}".rstrip("0").rstrip(".").replace(".", ",")


def _chip_off(r, rect, label: str) -> None:
    x, y, w, h = rect
    pygame.draw.rect(r.screen, (26, 28, 32), rect, border_radius=3)
    pygame.draw.rect(r.screen, (58, 60, 66), rect, 1, border_radius=3)
    surf = r.tiny.render(_fit(r.tiny, label, w - 6), True, (110, 112, 118))
    r.screen.blit(surf, (x + (w - surf.get_width()) // 2, y + (h - surf.get_height()) // 2))


def _tip(r, lines, mx, my) -> None:
    width = min(360, max(r.tiny.size(t)[0] for t, _c in lines) + 20)
    rows = []
    for text, color in lines:
        for part in _wrap(r.tiny, text, width - 20):
            rows.append((part, color))
    h = 10 + 15 * len(rows)
    sw, sh = r.screen.get_size()
    x = min(mx + 16, sw - width - 8)
    y = min(my + 18, sh - h - 8)
    r.screen.blit(_gradient_card(width, h, (38, 40, 48), (24, 26, 30), 6), (x, y))
    pygame.draw.rect(r.screen, GOLD_DIM, (x, y, width, h), 1, border_radius=6)
    yy = y + 5
    for text, color in rows:
        r.screen.blit(r.tiny.render(text, True, color), (x + 10, yy))
        yy += 15


# --- le rapport de bataille ----------------------------------------------------------------


def battle_layout(width: int, height: int) -> dict:
    bw = min(820, width - 60)
    bh = min(420, height - HUD_HEIGHT - 30)
    bx = max(12, (width - bw) // 2 - 16)
    by = HUD_HEIGHT + 14
    close = (bx + bw - 24 - 100, by + 16, 100, 28)
    side_w = int((bw - 48) * 0.33)
    left = (bx + 24, by + 104, side_w, bh - 104 - 50)
    right = (bx + bw - 24 - side_w, by + 104, side_w, bh - 104 - 50)
    graph = (left[0] + side_w + 18, by + 118, right[0] - 18 - (left[0] + side_w + 18), bh - 118 - 64)
    return {"box": (bx, by, bw, bh), "close": close, "left": left, "right": right, "graph": graph}


def _side(r, state, rect, side: dict, won: bool, attacker: bool) -> None:
    screen = r.screen
    x, y, w, h = rect
    tribe = state.tribes.get(side["tribe"])
    color = color_of(tribe) if tribe is not None else (150, 150, 150)
    screen.blit(_gradient_card(w, h, (32, 34, 40), (20, 22, 26), 6), (x, y))
    pygame.draw.rect(screen, _lerp(color, (0, 0, 0), 0.3), rect, 1, border_radius=6)
    pygame.draw.rect(screen, color, (x, y, w, 6), border_top_left_radius=6, border_top_right_radius=6)
    who = "Vous" if side["tribe"] == PLAYER_TRIBE_ID else side["name"]
    role = "ATTAQUANT" if attacker else "DEFENSEUR"
    screen.blit(r.tiny.render(role, True, GOLD_DIM), (x + 10, y + 12))
    tag = r.tiny.render("VAINQUEUR" if won else "VAINCU", True, GOOD if won else BAD)
    screen.blit(tag, (x + w - 10 - tag.get_width(), y + 12))
    screen.blit(r.font.render(_fit(r.font, who, w - 20), True, INK), (x + 10, y + 28))
    kind = {"troupe": "Troupe", "village": "Village", "clan": "Clan"}.get(side["kind"], "Bande")
    lead = f" · {side['leader']}" if side.get("leader") else ""
    screen.blit(r.tiny.render(_fit(r.tiny, kind + lead, w - 20), True, NOTE), (x + 10, y + 48))
    yy = y + 68
    rows = [
        (f"Combattants : {side['fighters']} -> {side['fighters_left']}", SOFT),
        (f"Gens : {side['pop']} -> {side['left']}", SOFT),
        (f"Pertes : {side['lost']}" + (f" ({side['pursuit']} dans la fuite)" if side.get("pursuit") else ""), BAD if side["lost"] else SOFT),
        (f"Puissance : {side['power']:.0f}".replace(".", ","), SOFT),
    ]
    for text, color_ in rows:
        screen.blit(r.tiny.render(_fit(r.tiny, text, w - 20), True, color_), (x + 10, yy))
        yy += 15
    for name, men, left in side.get("units", [])[:4]:
        screen.blit(r.tiny.render(_fit(r.tiny, f"  {name} : {men} -> {left}", w - 20), True, (200, 190, 160)), (x + 10, yy))
        yy += 14
    yy += 4
    for text, sign in side.get("mods", [])[:8]:
        if yy + 14 > y + h - 4:
            break
        c = (184, 222, 168) if sign == "+" else (226, 160, 140)
        screen.blit(r.tiny.render(_fit(r.tiny, text, w - 20), True, c), (x + 10, yy))
        yy += 14


def draw_battle(r, state, mark) -> None:
    rep = mark.report if mark is not None else None
    if rep is None:
        return
    w, h = r.screen.get_size()
    lay = battle_layout(w, h)
    r.fight_hits = lay
    title_font, head_font = _fonts(r)
    screen = r.screen
    mx, my = pygame.mouse.get_pos()
    _frame(r, lay["box"])
    bx, by, bw, bh = lay["box"]
    place = rep.get("place", "")
    screen.blit(title_font.render(f"Bataille {place}".strip(), True, GOLD), (bx + 24, by + 12))
    screen.blit(r.tiny.render(f"An {mark.year}  ·  semaine {mark.week}  ·  {rep['rounds']} passe{'s' if rep['rounds'] > 1 else ''} d'armes", True, NOTE), (bx + 26, by + 44))
    _button(screen, r.small, lay["close"], "Fermer", True, _hover(lay["close"], mx, my))
    att, dfd = rep["attacker"], rep["defender"]
    att_won = rep["winner"] == "attacker"
    mine_won = (att["tribe"] if att_won else dfd["tribe"]) == PLAYER_TRIBE_ID
    mine_in = PLAYER_TRIBE_ID in (att["tribe"], dfd["tribe"])
    # Bandeau de l'issue.
    bar = (bx + 24, by + 64, bw - 48, 30)
    if rep.get("wiped"):
        top, bot = ((40, 70, 40), (24, 44, 26)) if mine_won else ((110, 36, 30), (70, 22, 18))
    elif not mine_in:
        top, bot = (52, 48, 40), (34, 30, 26)
    else:
        top, bot = ((36, 66, 42), (22, 42, 27)) if mine_won else ((90, 40, 32), (56, 26, 20))
    screen.blit(_gradient_card(bar[2], bar[3], top, bot, 6), (bar[0], bar[1]))
    pygame.draw.rect(screen, GOLD_DIM, bar, 1, border_radius=6)
    head = rep.get("headline", "")
    if rep.get("wiped"):
        head = head.upper()
    hs = head_font.render(_fit(head_font, head, bar[2] - 20), True, INK)
    screen.blit(hs, (bar[0] + (bar[2] - hs.get_width()) // 2, bar[1] + (bar[3] - hs.get_height()) // 2))
    _side(r, state, lay["left"], att, att_won, True)
    _side(r, state, lay["right"], dfd, not att_won, False)
    _graph(r, state, lay["graph"], rep)
    foot = [f"Butin : {rep.get('loot', 0)} vivres"]
    if rep.get("encircled"):
        foot.append("encercles, sans chemin de repli")
    if rep.get("building"):
        foot.append(f"batiment perdu : {rep['building']}")
    fs = r.tiny.render("  ·  ".join(foot), True, SOFT)
    screen.blit(fs, (bx + (bw - fs.get_width()) // 2, by + bh - 34))


def _graph(r, state, rect, rep) -> None:
    """Le moral passe par passe (deux courbes), les pertes en barres."""
    screen = r.screen
    x, y, w, h = rect
    screen.blit(r.tiny.render("MORAL AU FIL DES PASSES", True, GOLD), (x, y - 16))
    screen.blit(_gradient_card(w, h, (20, 24, 28), (14, 16, 20), 6), (x, y))
    att, dfd = rep["attacker"], rep["defender"]
    ma, md = att["morale"], dfd["morale"]
    n = max(len(ma), len(md))
    top = max(100.0, max(ma + md))
    bottom = min(0.0, min(ma + md))
    span = max(1.0, top - bottom)
    inner = (x + 26, y + 8, w - 34, h - 36)
    ix, iy, iw, ih = inner

    def py(v):
        return iy + ih - (v - bottom) / span * ih

    for level in (0, 25, 50, 75, 100):
        if bottom <= level <= top:
            yy = int(py(level))
            col = (120, 60, 50) if level == battle.ROUT else (34, 38, 46)
            pygame.draw.line(screen, col, (ix, yy), (ix + iw, yy))
            screen.blit(r.tiny.render(str(level), True, (100, 104, 112)), (x + 3, yy - 7))
    rout = r.tiny.render("deroute", True, (160, 80, 66))
    screen.blit(rout, (ix + iw - rout.get_width(), int(py(battle.ROUT)) + 1))
    step = iw / max(1, n - 1)
    # Pertes par passe (barres), sous les courbes.
    hits_a, hits_d = att["hits"], dfd["hits"]
    most = max(hits_a + hits_d + [1.0])
    for i in range(1, n):
        cx = ix + step * i
        for k, (hits, side) in enumerate(((hits_a, att), (hits_d, dfd))):
            if i - 1 >= len(hits):
                continue
            tribe = state.tribes.get(side["tribe"])
            col = _lerp(color_of(tribe) if tribe else (150, 150, 150), (0, 0, 0), 0.45)
            bh_ = int(28 * hits[i - 1] / most)
            pygame.draw.rect(screen, col, (int(cx - 9 + k * 9), iy + ih - bh_, 8, bh_))
    for side, vals in ((att, ma), (dfd, md)):
        tribe = state.tribes.get(side["tribe"])
        col = color_of(tribe) if tribe else (200, 200, 200)
        pts = [(ix + step * i, py(v)) for i, v in enumerate(vals)]
        if len(pts) == 1:
            pts.append((ix + step, pts[0][1]))
        pygame.draw.lines(screen, _lerp(col, (0, 0, 0), 0.5), False, pts, 4)
        pygame.draw.lines(screen, col, False, pts, 2)
        for p in pts[: len(vals)]:
            _aacircle(screen, int(p[0]), int(p[1]), 3, col, fill=col)
    for i in range(n):
        lab = r.tiny.render("depart" if i == 0 else str(i), True, NOTE)
        screen.blit(lab, (int(ix + step * i - lab.get_width() / 2), iy + ih + 6))
