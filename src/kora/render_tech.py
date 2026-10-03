"""Ecran des savoirs, dans l'esprit de Victoria 3.

Un seul arbre vertical, dessine sur une TOILE qu'on parcourt (voir
layout.tech_panel_layout / tech_world / clamp_cam) : tout n'est pas a
l'ecran ; on glisse a la souris (n'importe quel bouton) ou aux fleches, on
zoome a la molette (autour du curseur) ou aux boutons ; "Recentrer" revient
a la recherche en cours.
  - une banniere par age, avec son chiffre romain et le nom des colonnes ;
  - des cartes de savoir dont le detail suit le zoom : medaillon et nom ;
    puis l'etat (cout, semaines, ce qui manque) ; puis le premier effet ;
  - des liens en courbes, dores quand le chemin est ouvert ;
  - en tete, la recherche en cours ; en bas, la fiche du savoir choisi ;
  - au survol d'une carte, une bulle avec ses premiers effets.
Aucune image : tout est dessine avec pygame (surfaces mises en cache).
"""

from __future__ import annotations

import math

import pygame
import pygame.gfxdraw

from src.kora import layout, learning, render_numbers, tech, theme
from src.kora.layout import TREE_GUTTER, TREE_PAD, TREE_ROW, cam_on, tech_panel_layout, to_screen
from src.kora.theme import C
from src.kora.theme import (  # noqa: F401
    _CACHE,
    _gradient_card,
    _lerp,
)

# La charte (theme.C) : ocre, os, lin, cendre.
GOLD = C.ocre_jaune
GOLD_DIM = C.bois_clair
GOLD_DEEP = C.bois
INK = C.os
SOFT = C.lin
NOTE = C.cendre
GOOD = C.bon
BAD = C.mauvais

STYLE = {
    "connu": {"top": (72, 54, 30), "bot": (48, 35, 21), "edge": C.ocre_jaune, "text": C.os, "icon": C.ocre_jaune},
    "en_cours": {"top": (92, 52, 26), "bot": (60, 33, 18), "edge": C.braise, "text": C.os, "icon": C.braise},
    "disponible": {"top": (32, 58, 54), "bot": (20, 38, 35), "edge": C.savoir, "text": C.os, "icon": C.savoir},
    "attente": {"top": (44, 34, 26), "bot": (31, 24, 19), "edge": C.bois_clair, "text": C.lin, "icon": C.cendre},
    "verrouille": {"top": (28, 22, 18), "bot": (21, 17, 13), "edge": (58, 46, 36), "text": C.cendre, "icon": (92, 80, 68)},
}
STATE_LABEL = {
    "connu": "Connu",
    "en_cours": "En cours",
    "disponible": "Disponible",
    "attente": "Pas encore",
    "verrouille": "Verrouillé",
}
# (fond des rangees, haut et bas de la banniere, couleur de l'age) : l'ocre
# du feu pour l'age tribal, la terre cuite pour l'age des villages.
ERA_STYLE = (
    ((22, 17, 13), (66, 44, 26), (34, 25, 18), C.ocre_jaune),
    ((24, 16, 13), (80, 40, 28), (40, 22, 16), (226, 132, 96)),
)
# Une icone par branche de l'arbre (game-icons, theme.ICON_FILES).
BRANCH_ICONS = (
    ("chasse", "baies", "cache", "peche", "froid", "camp", "feu", "gens", "tablette"),
    ("palissade", "ble", "grenier", "pieces", "boeuf", "hutte", "menhir", "commerce", "abaque"),
)
MEDAL_STATE = {"connu": "connu", "en_cours": "actif", "disponible": "normal", "attente": "normal", "verrouille": "eteint"}

ROMAN = ("I", "II", "III", "IV", "V", "VI")



def _fonts(r):
    return theme.font("titre"), theme.font("h3"), theme.font_file("sc-bold", 18), theme.font_file("sans-bold", 15)


def _era_font(r, name: str, width: int):
    """Le plus grand titre d'age qui tient dans la marge (chaque mot entier)."""
    font = None
    for size in (19, 17, 15, 13):
        font = theme.font_file("sc-bold", size)
        if all(font.size(word)[0] <= width for word in name.split(" ")):
            return font
    return font


def _band(screen, rect, top, bot) -> None:
    x, y, w, h = rect
    for k in range(h):
        pygame.draw.line(screen, _lerp(top, bot, k / max(1, h - 1)), (x, y + k), (x + w - 1, y + k))


def _aacircle(screen, cx, cy, r, color, fill=None) -> None:
    if fill is not None:
        pygame.gfxdraw.filled_circle(screen, cx, cy, r, fill)
    pygame.gfxdraw.aacircle(screen, cx, cy, r, color)


def _wrap(font, text: str, width: int) -> list[str]:
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


def _fit(font, text: str, width: int) -> str:
    return theme.fit(font, text, width)


# --- medaillons : un dessin par branche --------------------------------------------


def _glyph(surf, era: int, col: int, color, s: int) -> None:
    """Dessin de la branche `col` (age `era`) dans une case de s x s."""
    c = s // 2
    w = max(2, s // 9)
    line = pygame.draw.line
    poly = pygame.draw.polygon
    if col == 0 and era == 0:  # epieux croises
        line(surf, color, (s * 0.2, s * 0.85), (s * 0.8, s * 0.2), w)
        line(surf, color, (s * 0.8, s * 0.85), (s * 0.2, s * 0.2), w)
        poly(surf, color, [(s * 0.8, s * 0.08), (s * 0.9, s * 0.28), (s * 0.68, s * 0.24)])
        poly(surf, color, [(s * 0.2, s * 0.08), (s * 0.1, s * 0.28), (s * 0.32, s * 0.24)])
    elif col == 0:  # bouclier
        poly(surf, color, [(s * 0.2, s * 0.18), (s * 0.8, s * 0.18), (s * 0.78, s * 0.55), (c, s * 0.9), (s * 0.22, s * 0.55)], w)
        line(surf, color, (c, s * 0.24), (c, s * 0.8), w)
    elif col == 1:  # epi de ble
        line(surf, color, (c, s * 0.92), (c, s * 0.18), w)
        for k in range(3):
            y = s * (0.3 + 0.18 * k)
            pygame.draw.ellipse(surf, color, (c - s * 0.3, y, s * 0.26, s * 0.14))
            pygame.draw.ellipse(surf, color, (c + s * 0.04, y, s * 0.26, s * 0.14))
        pygame.draw.ellipse(surf, color, (c - s * 0.08, s * 0.08, s * 0.16, s * 0.2))
        if era == 1:
            line(surf, color, (s * 0.12, s * 0.92), (s * 0.88, s * 0.92), w)
    elif col == 2:  # jarre / grenier
        if era == 0:
            pygame.draw.ellipse(surf, color, (s * 0.2, s * 0.32, s * 0.6, s * 0.58), w)
            pygame.draw.rect(surf, color, (s * 0.36, s * 0.14, s * 0.28, s * 0.2), w)
            line(surf, color, (s * 0.28, s * 0.14), (s * 0.72, s * 0.14), w)
        else:
            poly(surf, color, [(s * 0.15, s * 0.42), (c, s * 0.12), (s * 0.85, s * 0.42)], w)
            pygame.draw.rect(surf, color, (s * 0.24, s * 0.42, s * 0.52, s * 0.32), w)
            line(surf, color, (s * 0.3, s * 0.74), (s * 0.3, s * 0.92), w)
            line(surf, color, (s * 0.7, s * 0.74), (s * 0.7, s * 0.92), w)
    elif col == 3:  # poisson
        pygame.draw.ellipse(surf, color, (s * 0.12, s * 0.3, s * 0.56, s * 0.4))
        poly(surf, color, [(s * 0.62, c), (s * 0.92, s * 0.26), (s * 0.92, s * 0.74)])
        pygame.draw.circle(surf, (0, 0, 0, 0), (int(s * 0.28), int(s * 0.46)), max(1, s // 14))
    elif col == 4 and era == 0:  # flocon
        for k in range(3):
            a = math.pi / 3 * k
            dx, dy = math.cos(a) * s * 0.4, math.sin(a) * s * 0.4
            line(surf, color, (c - dx, c - dy), (c + dx, c + dy), w)
        pygame.draw.circle(surf, color, (c, c), max(2, s // 8))
    elif col == 4:  # tete de boeuf
        pygame.draw.ellipse(surf, color, (s * 0.3, s * 0.3, s * 0.4, s * 0.52))
        pygame.draw.arc(surf, color, (s * 0.02, s * 0.08, s * 0.4, s * 0.4), math.pi * 0.9, math.pi * 1.7, w)
        pygame.draw.arc(surf, color, (s * 0.58, s * 0.08, s * 0.4, s * 0.4), -math.pi * 0.7, math.pi * 0.1, w)
    elif col == 5 and era == 0:  # tente
        poly(surf, color, [(c, s * 0.1), (s * 0.1, s * 0.88), (s * 0.9, s * 0.88)], w)
        line(surf, color, (c, s * 0.1), (c, s * 0.88), w)
    elif col == 5:  # maison
        poly(surf, color, [(s * 0.1, s * 0.46), (c, s * 0.12), (s * 0.9, s * 0.46)])
        pygame.draw.rect(surf, color, (s * 0.2, s * 0.46, s * 0.6, s * 0.42), w)
        pygame.draw.rect(surf, color, (s * 0.44, s * 0.62, s * 0.14, s * 0.26))
    elif col == 6 and era == 0:  # flamme
        poly(surf, color, [(c, s * 0.08), (s * 0.78, s * 0.52), (s * 0.7, s * 0.8), (c, s * 0.92), (s * 0.3, s * 0.8), (s * 0.22, s * 0.52)])
    elif col == 6:  # pierres levees
        pygame.draw.rect(surf, color, (s * 0.16, s * 0.3, s * 0.2, s * 0.62), border_radius=2)
        pygame.draw.rect(surf, color, (s * 0.64, s * 0.3, s * 0.2, s * 0.62), border_radius=2)
        pygame.draw.rect(surf, color, (s * 0.08, s * 0.14, s * 0.84, s * 0.14), border_radius=2)
    elif col == 7 and era == 0:  # deux personnes
        for x0 in (0.32, 0.68):
            pygame.draw.circle(surf, color, (int(s * x0), int(s * 0.32)), max(2, s // 7))
            pygame.draw.arc(surf, color, (s * (x0 - 0.2), s * 0.5, s * 0.4, s * 0.5), 0, math.pi, w)
    else:  # echange : deux fleches
        line(surf, color, (s * 0.15, s * 0.35), (s * 0.85, s * 0.35), w)
        poly(surf, color, [(s * 0.85, s * 0.2), (s * 0.98, s * 0.35), (s * 0.85, s * 0.5)])
        line(surf, color, (s * 0.85, s * 0.68), (s * 0.15, s * 0.68), w)
        poly(surf, color, [(s * 0.15, s * 0.53), (s * 0.02, s * 0.68), (s * 0.15, s * 0.83)])


def medallion(era: int, col: int, state: str, radius: int) -> pygame.Surface:
    """Le medaillon d'une branche : son icone, la couleur de son etat."""
    icons = BRANCH_ICONS[min(era, len(BRANCH_ICONS) - 1)]
    ring = C.savoir if state == "disponible" else None
    return theme.medallion(icons[col % len(icons)], radius, MEDAL_STATE.get(state, "normal"), ring)


def _check(screen, cx, cy, color, r=6) -> None:
    _aacircle(screen, cx, cy, r, GOLD_DEEP, fill=GOLD)
    pygame.draw.lines(screen, (40, 30, 14), False, [(cx - 3, cy), (cx - 1, cy + 3), (cx + 3, cy - 3)], 2)


def _cross(screen, cx, cy, r=5) -> None:
    pygame.draw.line(screen, BAD, (cx - r, cy - r), (cx + r, cy + r), 2)
    pygame.draw.line(screen, BAD, (cx - r, cy + r), (cx + r, cy - r), 2)


def _tick(screen, cx, cy) -> None:
    pygame.draw.lines(screen, GOOD, False, [(cx - 5, cy), (cx - 1, cy + 4), (cx + 6, cy - 5)], 2)


def _lock(screen, cx, cy, color) -> None:
    pygame.draw.rect(screen, color, (cx - 5, cy - 1, 10, 8), border_radius=2)
    pygame.draw.arc(screen, color, (cx - 4, cy - 7, 8, 10), 0, math.pi, 2)


def _ornate_frame(screen, rect) -> None:
    """Le bord d'une fenetre de la charte : bois, fil d'ocre, encoches."""
    x, y, w, h = rect
    pygame.draw.polygon(screen, C.bois, theme.chamfer(rect, 10), 2)
    pygame.draw.polygon(screen, C.ocre_sombre, theme.chamfer((x + 5, y + 5, w - 10, h - 10), 7), 1)
    for cx, cy in ((x + 5, y + 5), (x + w - 6, y + 5), (x + 5, y + h - 6), (x + w - 6, y + h - 6)):
        pygame.draw.polygon(screen, C.ocre, [(cx, cy - 4), (cx + 4, cy), (cx, cy + 4), (cx - 4, cy)])


def _bezier(p0, p3, steps: int = 14) -> list:
    x0, y0 = p0
    x3, y3 = p3
    dy = (y3 - y0) * 0.55
    p1 = (x0, y0 + dy)
    p2 = (x3, y3 - dy)
    pts = []
    for i in range(steps + 1):
        t = i / steps
        u = 1 - t
        x = u * u * u * x0 + 3 * u * u * t * p1[0] + 3 * u * t * t * p2[0] + t * t * t * x3
        y = u * u * u * y0 + 3 * u * u * t * p1[1] + 3 * u * t * t * p2[1] + t * t * t * y3
        pts.append((x, y))
    return pts


def _button(screen, font, rect, label: str, on: bool, hover: bool) -> None:
    """Le bouton principal de la charte (ocre plein)."""
    theme.button(screen, rect, label, "principal", on, hover, role="bouton" if rect[3] >= 30 else "bouton_petit")


# --- l'ecran --------------------------------------------------------------------------


def focus_cam(state, width: int, height: int) -> tuple:
    """La vue posee sur la recherche en cours (sinon un savoir disponible)."""
    tribe = state.tribes.get(state.viewer)
    lay = tech_panel_layout(width, height)
    focus = tribe.learning if tribe is not None else None
    if focus is None:
        focus = next(iter(learning.available(state, state.viewer)), None)
    return cam_on(lay["view"], lay["world"], focus, 1.0)


def _status_line(state, tribe, tid: str, st: str) -> tuple[str, tuple]:
    """Une ligne sous le nom : ou en est ce savoir."""
    t = tech.TECHS[tid]
    if st == "connu":
        return "Connu", STYLE["connu"]["edge"]
    if st == "en_cours":
        done = int(100 * tribe.progress.get(tid, 0.0) / t.cost) if t.cost else 100
        return f"En cours · {done} % · ~{learning.weeks_left(state, state.viewer, tid)} sem.", STYLE["en_cours"]["edge"]
    if st == "disponible":
        return f"{t.cost} pts · ~{learning.weeks_left(state, state.viewer, tid)} sem.", STYLE["disponible"]["edge"]
    if st == "verrouille":
        missing = tech.missing_prereqs(tribe, t)
        return ("Il faut : " + ", ".join(m.name for m in missing[:2])) if missing else "Verrouillé", STYLE["verrouille"]["text"]
    for cond in t.conds:
        have, need, label = learning.cond_progress(state, tribe, cond)
        if have < need:
            shown = f"{label} ({min(have, need)}/{need})" if cond.kind not in ("seen", "flag") else label
            return shown, STYLE["attente"]["text"]
    return "Pas encore", STYLE["attente"]["text"]


def _tabs(r, lay, mx, my) -> None:
    for key, label in (("arbre", "L'arbre"), ("nombres", "Les nombres")):
        rect = lay["tabs"][key]
        hover = rect[0] <= mx <= rect[0] + rect[2] and rect[1] <= my <= rect[1] + rect[3]
        theme.button(r.screen, rect, label, "second", True, hover, icon_key="abaque" if key == "nombres" else "savoir", active=lay.get("tab", "arbre") == key)


def draw(r, state, lay: dict, pick: str | None, ui: dict | None = None) -> None:
    tribe = state.tribes.get(state.viewer)
    if tribe is None or lay is None:
        return
    screen = r.screen
    title_font, head_font, era_font, num_font = _fonts(r)
    bx, by, bw, bh = lay["box"]
    back = _gradient_card(bw, bh, (41, 31, 24), (20, 15, 12), 8)
    screen.blit(back, (bx, by))
    _ornate_frame(screen, (bx, by, bw, bh))
    mx, my = pygame.mouse.get_pos()
    world = lay["world"]
    states = {tid: learning.status(state, state.viewer, tid) for tid in world["nodes"]}
    _header(r, state, tribe, lay, states, title_font, head_font)
    if lay.get("tabs"):
        _tabs(r, lay, mx, my)
    if lay.get("numbers") is not None:
        render_numbers.draw(r, state, lay, ui)
        return
    view, cam = lay["view"], lay["cam"]
    z = cam[2]
    vx, vy, vw, vh = view
    screen.set_clip(view)
    pygame.draw.rect(screen, (20, 16, 12), view)
    cols, rows = world["cols"], world["rows"]
    col_w = world["col_w"]

    def sx(x):
        return vx + (x - cam[0]) * z

    def sy(y):
        return vy + (y - cam[1]) * z

    # Ages : fond des rangees, bannieres, colonnes.
    for sec in world["sections"]:
        era = sec["era"]
        tint, top, bot, accent = ERA_STYLE[era % len(ERA_STYLE)]
        body = [int(v) for v in to_screen(cam, view, sec["body"])]
        pygame.draw.rect(screen, tint, body)
        head = [int(v) for v in to_screen(cam, view, sec["head"])]
        if head[3] > 1:
            _band(screen, head, top, bot)
        pygame.draw.line(screen, _lerp(accent, (0, 0, 0), 0.25), (head[0], head[1]), (head[0] + head[2] - 1, head[1]), 2 if era else 1)
        for tier in tech.ERAS[era][1]:
            ry = int(sy(rows[tier] + TREE_ROW)) - 1
            pygame.draw.line(screen, _lerp(tint, (255, 255, 255), 0.06), (body[0] + 6, ry), (body[0] + body[2] - 6, ry))
        for i in range(len(cols)):
            x = int(sx(cols[i]))
            pygame.draw.line(screen, _lerp(tint, (255, 255, 255), 0.035), (x, body[1]), (x, body[1] + body[3]))
    nodes = lay["nodes"]
    # Liens en courbes : dores si le prerequis est connu.
    arrow = max(3, int(5 * z))
    for t in tech.TECHS.values():
        for pid in t.prereqs:
            ax, ay, aw, ah = nodes[pid]
            cx, cy, cw, _ch = nodes[t.id]
            p0 = (ax + aw / 2, ay + ah)
            p3 = (cx + cw / 2, cy - 1)
            if max(p0[1], p3[1]) < vy or min(p0[1], p3[1]) > vy + vh:
                continue
            known = states[pid] == "connu"
            child = states[t.id]
            if known and child == "connu":
                color, width = (200, 164, 92), 2
            elif known and child in ("disponible", "en_cours"):
                color, width = STYLE[child]["edge"], 2
            elif known:
                color, width = (110, 104, 88), 1
            else:
                color, width = (80, 60, 42), 1
            width = max(1, int(round(width * min(1.4, z))))
            pts = _bezier(p0, p3) if abs(p0[0] - p3[0]) > 1 else [p0, p3]
            if width > 1:
                pygame.draw.lines(screen, _lerp(color, (0, 0, 0), 0.55), False, pts, width + 2)
                pygame.draw.lines(screen, color, False, pts, width)
            pygame.draw.aalines(screen, color, False, pts)
            pygame.draw.polygon(screen, color, [(p3[0] - arrow + 1, p3[1] - arrow), (p3[0] + arrow - 1, p3[1] - arrow), (p3[0], p3[1])])
    # Noms des ages, des colonnes, des paliers (par-dessus les liens).
    gutter = TREE_GUTTER * z
    small = z < 0.62
    for sec in world["sections"]:
        era = sec["era"]
        era_name, tiers, branches = tech.ERAS[era]
        _tint, _top, _bot, accent = ERA_STYLE[era % len(ERA_STYLE)]
        hx, hy, hw, hh = to_screen(cam, view, sec["head"])
        left = sx(TREE_PAD)
        rad = max(8, int(14 * min(1.2, z)))
        mcx, mcy = int(left + rad + 4), int(hy + hh / 2)
        _aacircle(screen, mcx, mcy, rad, accent, fill=_lerp(accent, (0, 0, 0), 0.7))
        _aacircle(screen, mcx, mcy, max(4, rad - 3), _lerp(accent, (0, 0, 0), 0.4))
        num = (num_font if not small else r.tiny).render(ROMAN[era], True, accent)
        screen.blit(num, (mcx - num.get_width() // 2, mcy - num.get_height() // 2))
        room = int(gutter - 2 * rad - 16)
        if room > 30:
            font = _era_font(r, era_name, room) if not small else r.tiny
            parts = _wrap(font, era_name, room)[:2]
            line_h = font.get_height()
            for k, part in enumerate(parts):
                screen.blit(font.render(part, True, accent), (int(left + 2 * rad + 12), int(hy + (hh - line_h * len(parts)) / 2 + line_h * k)))
        for i, name in enumerate(branches):
            if not name:
                continue
            gx = int(sx(cols[i])) + 6
            if gx > vx + vw or gx + col_w * z < vx:
                continue
            font = r.small if z >= 1.0 else r.tiny
            parts = _wrap(font, name, int(col_w * z) - 34)[:2]
            lh = font.get_height()
            if era > 0:
                tw = max(font.size(p_)[0] for p_ in parts) + 30
                screen.blit(_gradient_card(tw, max(4, int(hh) - 8), _top, _bot, 6), (gx - 4, int(hy) + 4))
            icon = medallion(era, i, "attente", max(6, int(8 * min(1.3, z))))
            screen.blit(icon, (gx, int(hy + hh / 2) - icon.get_height() // 2))
            ty = int(hy + (hh - lh * len(parts)) / 2)
            for part in parts:
                screen.blit(font.render(part, True, (214, 208, 188)), (gx + 22, ty))
                ty += lh
        for tier in tiers:
            ry = sy(rows[tier])
            if ry > vy + vh or ry + TREE_ROW * z < vy:
                continue
            font = r.small if z >= 1.0 else r.tiny
            label = _wrap(font, tech.TIER_NAMES[tier], int(gutter) - 18)[:2]
            cost = f"{tech.TIER_COST[tier]} pts" if tech.TIER_COST[tier] else "au départ"
            lh = font.get_height()
            ty = int(ry + (TREE_ROW * z - lh * (len(label) + 1)) / 2)
            for part in label:
                screen.blit(font.render(part, True, (176, 172, 160)), (int(left) + 6, ty))
                ty += lh
            screen.blit(r.tiny.render(cost, True, _lerp(accent, (0, 0, 0), 0.25)), (int(left) + 6, ty))
    # Cartes : le detail suit le zoom.
    hovered = None
    pulse = 0.5 + 0.5 * math.sin(pygame.time.get_ticks() / 380.0)
    name_font = head_font if z >= 1.2 else r.small if z >= 0.8 else r.tiny
    for tid, rect in nodes.items():
        if tid not in lay["visible"]:
            continue
        t = tech.TECHS[tid]
        st = states[tid]
        style = STYLE[st]
        x, y, w, h = (int(v) for v in rect)
        hover = x <= mx <= x + w and y <= my <= y + h and vx <= mx <= vx + vw and vy <= my <= vy + vh
        if hover:
            hovered = tid
        if st in ("disponible", "en_cours") or hover or tid == pick:
            pad = max(3, int(6 * z))
            glow = pygame.Surface((w + 2 * pad, h + 2 * pad), pygame.SRCALPHA)
            alpha = int(40 + 50 * pulse) if st in ("disponible", "en_cours") else 70
            pygame.draw.rect(glow, style["edge"] + (alpha,), (0, 0, w + 2 * pad, h + 2 * pad), border_radius=10)
            screen.blit(glow, (x - pad, y - pad))
        screen.blit(_gradient_card(w, h, style["top"], style["bot"], 6), (x, y))
        edge = (239, 228, 204) if tid == pick else style["edge"]
        pygame.draw.rect(screen, edge, (x, y, w, h), 2 if (tid == pick or hover) else 1, border_radius=6)
        rad = max(8, min(22, int(17 * z)))
        med = medallion(tech.era_of(t), t.branch, st, rad)
        screen.blit(med, (x + 5, y + h // 2 - med.get_height() // 2))
        tx = x + 2 * rad + 12
        text_w = w - (tx - x) - 12
        lines = []
        parts = _wrap(name_font, t.name, text_w)
        if len(parts) > 2:
            parts = parts[:1] + [_fit(name_font, " ".join(parts[1:]), text_w)]
        lines += [(p_, name_font, style["text"]) for p_ in parts]
        if z >= 0.8:
            text, color = _status_line(state, tribe, tid, st)
            lines.append((_fit(r.tiny, text, text_w), r.tiny, color))
        if z >= 1.05:
            first = tech.summary(t)
            if first:
                lines.append((_fit(r.tiny, first, text_w), r.tiny, (178, 205, 140) if st != "verrouille" else (130, 113, 96)))
        total = sum(f.get_height() for _t, f, _c in lines)
        ty = y + max(2, (h - total) // 2 - 2)
        for text, font, color in lines:
            if ty + font.get_height() > y + h - 2:
                break
            screen.blit(font.render(text, True, color), (tx, ty))
            ty += font.get_height()
        done = tribe.progress.get(tid, 0.0) / t.cost if t.cost else 0.0
        if st != "connu" and done > 0:
            bar = (tx, y + h - max(5, int(7 * z)), w - (tx - x) - 10, max(2, int(3 * z)))
            pygame.draw.rect(screen, (23, 18, 14), bar)
            pygame.draw.rect(screen, STYLE["en_cours"]["edge"] if st == "en_cours" else (143, 130, 115), (bar[0], bar[1], int(bar[2] * min(1.0, done)), bar[3]))
        if st == "connu":
            _check(screen, x + w - 9, y + 9, GOLD, r=max(4, int(6 * min(1.2, z))))
        elif st == "verrouille":
            _lock(screen, x + w - 10, y + 10, style["edge"])
    screen.set_clip(None)
    pygame.draw.rect(screen, GOLD_DEEP, view, 1)
    _controls(r, lay, mx, my)
    sx0, sy0, _sw, sh0 = lay["strip"]
    zoom = f"zoom {int(round(100 * z))} %"
    hint = r.tiny.render(f"Glisser (n'importe quel bouton) : se déplacer  ·  molette : zoomer  ·  flèches, + et -  ·  {zoom}", True, NOTE)
    hx = sx0 + 4
    if lay.get("tabs"):
        t = lay["tabs"]["nombres"]
        hx = t[0] + t[2] + 14
    room = lay["zoom_out"][0] - 10 - hx
    if hint.get_width() > room:
        hint = r.tiny.render(_fit(r.tiny, f"Glisser : se déplacer  ·  molette : zoomer  ·  {zoom}", room), True, NOTE)
    screen.blit(hint, (hx, sy0 + (sh0 - hint.get_height()) // 2))
    _detail(r, state, tribe, lay, pick, states, head_font)
    if hovered is not None and hovered != pick:
        _hover_tip(r, state, hovered, states[hovered], mx, my)


def _controls(r, lay, mx, my) -> None:
    for key, label in (("zoom_out", "-"), ("zoom_in", "+"), ("center", "Recentrer")):
        rect = lay[key]
        hover = rect[0] <= mx <= rect[0] + rect[2] and rect[1] <= my <= rect[1] + rect[3]
        _button(r.screen, r.small, rect, label, True, hover)


def _header(r, state, tribe, lay, states, title_font, head_font) -> None:
    screen = r.screen
    bx, by, bw, bh = lay["box"]
    screen.blit(title_font.render("Savoirs", True, GOLD), (bx + 20, by + 10))
    rate = learning.learn_rate(state, state.viewer)
    pop = learning._learning_pop(state, state.viewer)
    pace = f"Recherche : {rate:.1f} pts par semaine  ·  {pop} personnes à l'écoute des anciens".replace(".", ",", 1)
    screen.blit(r.tiny.render(pace, True, NOTE), (bx + 22, by + 42))
    # Legende.
    lx = bx + 140
    for key in ("connu", "en_cours", "disponible", "attente", "verrouille"):
        st = STYLE[key]
        screen.blit(_gradient_card(14, 12, st["top"], st["bot"], 3), (lx, by + 18))
        pygame.draw.rect(screen, st["edge"], (lx, by + 18, 14, 12), 1, border_radius=3)
        label = r.tiny.render(STATE_LABEL[key].lower(), True, st["edge"])
        screen.blit(label, (lx + 18, by + 17))
        lx += 26 + label.get_width()
    # Recherche en cours.
    cx, cy, cw, ch = lay["current"]
    card = _gradient_card(cw, ch, (58, 44, 33), (37, 28, 22), 6)
    screen.blit(card, (cx, cy))
    pygame.draw.rect(screen, GOLD_DIM, lay["current"], 1, border_radius=6)
    if tribe.learning:
        cur = tech.TECHS[tribe.learning]
        med = medallion(tech.era_of(cur), cur.branch, "en_cours", 16)
        screen.blit(med, (cx + 8, cy + ch // 2 - 17))
        done = tribe.progress.get(cur.id, 0.0) / cur.cost
        weeks = learning.weeks_left(state, state.viewer, cur.id)
        screen.blit(head_font.render(_fit(head_font, cur.name, cw - 170), True, INK), (cx + 48, cy + 4))
        info = f"{int(100 * done)} %  ·  encore ~{weeks} sem."
        surf = r.tiny.render(info, True, STYLE["en_cours"]["edge"])
        screen.blit(surf, (cx + cw - surf.get_width() - 10, cy + 8))
        bar = (cx + 48, cy + ch - 14, cw - 58, 6)
        pygame.draw.rect(screen, (18, 14, 11), bar, border_radius=3)
        pygame.draw.rect(screen, STYLE["en_cours"]["edge"], (bar[0], bar[1], int(bar[2] * min(1.0, done)), 6), border_radius=3)
    else:
        screen.blit(head_font.render("Aucun savoir en cours", True, (226, 196, 128)), (cx + 14, cy + 4))
        screen.blit(r.tiny.render("Choisissez un savoir disponible (en vert) puis Apprendre.", True, NOTE), (cx + 14, cy + 26))


def _detail(r, state, tribe, lay, pick, states, head_font) -> None:
    screen = r.screen
    dx, dy, dw, dh = lay["detail"]
    shown = pick or tribe.learning or next(iter(learning.available(state, state.viewer)), None)
    card = _gradient_card(dw, dh, (42, 32, 25), (26, 20, 15), 8)
    screen.blit(card, (dx, dy))
    pygame.draw.rect(screen, GOLD_DEEP, (dx, dy, dw, dh), 1, border_radius=8)
    if shown is None:
        screen.blit(r.small.render("Cliquez sur un savoir pour voir ce qu'il fait.", True, SOFT), (dx + 14, dy + 14))
        return
    t = tech.TECHS[shown]
    st = states.get(shown) or learning.status(state, state.viewer, shown)
    style = STYLE[st]
    screen.blit(medallion(tech.era_of(t), t.branch, st, 17), (dx + 10, dy + 6))
    screen.blit(head_font.render(t.name, True, INK), (dx + 52, dy + 6))
    branch = tech.branches_of(t)[t.branch]
    sub = f"{tech.ERAS[tech.era_of(t)][0]}  ·  {tech.TIER_NAMES[t.tier]}  ·  {branch}"
    if t.cost:
        sub += f"  ·  {t.cost} pts"
        if st in ("disponible", "en_cours"):
            sub += f" (~{learning.weeks_left(state, state.viewer, shown)} sem.)"
    screen.blit(r.tiny.render(sub, True, NOTE), (dx + 52, dy + 28))
    pill = r.tiny.render(STATE_LABEL[st], True, style["text"])
    pw = pill.get_width() + 18
    px = (lay["learn"][0] - pw - 12) if st != "connu" else dx + dw - pw - 12
    screen.blit(_gradient_card(pw, 20, style["top"], style["bot"], 10), (px, dy + 10))
    pygame.draw.rect(screen, style["edge"], (px, dy + 10, pw, 20), 1, border_radius=10)
    screen.blit(pill, (px + 9, dy + 13))
    pygame.draw.line(screen, GOLD_DEEP, (dx + 12, dy + 40), (dx + dw - 12, dy + 40))
    left, right = lay["detail_cols"]
    lines = learning.detail_lines(state, state.viewer, shown)
    what = [ln for ln in lines if ln[1] in ("texte", "effet")]
    need = []
    mode = None
    for text, style_key in lines:
        if style_key == "note" and text.startswith("Il faut"):
            mode = "need"
            need.append((text, "section"))
            continue
        if style_key == "note" and text.startswith("Apprentissage"):
            continue
        if mode == "need" or (style_key == "ok" and text.startswith("Connu de")):
            if style_key in ("ok", "manque"):
                need.append((text.strip(), style_key))
    _column(r, left, "CE QU'IL FAIT", what)
    if st == "connu":
        _column(r, right, "SAVOIR ACQUIS", [("Votre peuple sait déjà faire cela.", "ok")])
    else:
        _column(r, right, "CE QU'IL DEMANDE", need)
    if st != "connu":
        mx, my = pygame.mouse.get_pos()
        rect = lay["learn"]
        on = st == "disponible"
        hover = on and rect[0] <= mx <= rect[0] + rect[2] and rect[1] <= my <= rect[1] + rect[3]
        label = {"disponible": "Apprendre", "en_cours": "En cours"}.get(st, "Pas encore")
        _button(screen, head_font, rect, label, on, hover)


def _column(r, rect, title: str, rows: list) -> None:
    screen = r.screen
    x, y, w, h = rect
    screen.blit(r.tiny.render(title, True, GOLD), (x, y))
    yy = y + 18
    for text, kind in rows:
        if kind == "section":
            if yy + 16 > y + h:
                break
            screen.blit(r.tiny.render(text.rstrip(" :"), True, GOLD_DIM), (x, yy))
            yy += 16
            continue
        color = {"texte": SOFT, "effet": (178, 205, 140), "ok": GOOD, "manque": BAD}.get(kind, SOFT)
        indent = 18 if kind in ("effet", "ok", "manque") else 0
        for k, part in enumerate(_wrap(r.tiny, text.strip(), w - indent - 4)):
            if yy + 15 > y + h:
                return
            if k == 0 and kind == "effet":
                pygame.draw.polygon(screen, (178, 205, 140), [(x + 4, yy + 3), (x + 10, yy + 7), (x + 4, yy + 11)])
            elif k == 0 and kind == "ok":
                _tick(screen, x + 7, yy + 7)
            elif k == 0 and kind == "manque":
                _cross(screen, x + 7, yy + 7, 4)
            screen.blit(r.tiny.render(part, True, color), (x + indent, yy))
            yy += 15
        yy += 2


def _hover_tip(r, state, tid: str, st: str, mx: int, my: int) -> None:
    t = tech.TECHS[tid]
    lines = [(t.name, INK), (STATE_LABEL[st], STYLE[st]["edge"])]
    lines += [("+ " + line, (178, 205, 140)) for line in tech.effect_lines(t)[:3]]
    if st in ("attente", "verrouille"):
        lines.append(("Cliquez pour voir ce qu'il demande", NOTE))
    w = max(r.tiny.size(text)[0] for text, _c in lines) + 20
    h = 10 + 16 * len(lines)
    sw, sh = r.screen.get_size()
    x = min(mx + 16, sw - w - 8)
    y = min(my + 18, sh - h - 8)
    card = _gradient_card(w, h, (53, 41, 31), (34, 25, 20), 6)
    r.screen.blit(card, (x, y))
    pygame.draw.rect(r.screen, GOLD_DIM, (x, y, w, h), 1, border_radius=6)
    yy = y + 6
    for text, color in lines:
        r.screen.blit(r.tiny.render(text, True, color), (x + 10, yy))
        yy += 16
