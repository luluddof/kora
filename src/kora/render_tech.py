"""Ecran des savoirs, dans l'esprit de Victoria 3.

Un seul arbre vertical, dessine sur une TOILE qu'on parcourt (voir
layout.tech_panel_layout / tech_world / clamp_cam) : tout n'est pas a
l'ecran ; on glisse a la souris (n'importe quel bouton) ou aux fleches, on
zoome a la molette (autour du curseur) ou aux boutons ; "Recentrer" revient
a la recherche en cours.
  - une banniere par age, avec son chiffre romain et le nom des colonnes ;
  - des cartes de savoir dont le detail suit le zoom : medaillon et nom ;
    puis l'etat (cout, semaines, ce qui manque) ; puis le premier effet ;
  - des liens a angles droits qui passent dans les couloirs entre les
    cartes (layout.tree_links), jamais au travers : dores quand le chemin
    est connu, verts quand il mene a un savoir disponible ;
  - au survol d'un savoir (ou quand il est choisi), sa CHAINE s'eclaire :
    ce qu'il faut avant lui en or, ce qu'il ouvre en bleu ; le reste
    s'efface ;
  - en tete, la recherche en cours ; en bas, la fiche du savoir choisi ;
  - au survol d'une carte, une bulle avec ses premiers effets ;
  - les GRANDS TOURNANTS (turning.py) : de larges cartes sur leur rangee,
    avec leur presence chez vous (une barre) et leur berceau ;
  - les savoirs TIRES (draws.py) : une pastille (leur chance, "?" avant le
    tirage du peuple) ; ABSENTS (ils ne viendront pas) : eteints et barres.
Aucune image : tout est dessine avec pygame (surfaces mises en cache).
"""

from __future__ import annotations

import math

import pygame
import pygame.gfxdraw

from src.kora import draws, layout, learning, render_numbers, tech, theme, turning
from src.kora.layout import TREE_GUTTER, TREE_PAD, TREE_ROW, TREE_TURN_ROW, cam_on, tech_panel_layout, to_screen  # noqa: F401
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
    "absent": {"top": (22, 18, 16), "bot": (17, 14, 12), "edge": (74, 48, 44), "text": (112, 96, 88), "icon": (80, 64, 58)},
}
STATE_LABEL = {
    "connu": "Connu",
    "en_cours": "En cours",
    "disponible": "Disponible",
    "attente": "Pas encore",
    "verrouille": "Verrouillé",
    "absent": "Ne viendra pas",
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
MEDAL_STATE = {"connu": "connu", "en_cours": "actif", "disponible": "normal", "attente": "normal", "verrouille": "eteint", "absent": "eteint"}
# Les grands tournants : leur or.
TURN_GOLD = (236, 196, 110)

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
    if st == "absent":
        return draws.short_why(state, state.viewer, tid), STYLE["absent"]["text"]
    if t.turning and st == "connu":
        return "Adopté", STYLE["connu"]["edge"]
    if t.turning and st == "attente":
        pres = turning.presence(tribe, tid)
        if not turning.born(state, tid) and pres <= 0:
            return "Pas encore né dans le monde", STYLE["attente"]["text"]
        gain = turning.monthly_gain(state, state.viewer, tid)
        more = f" · +{gain:g}/mois" if gain > 0 else " · rien ne l'apporte"
        return f"Arrive chez vous : {pres:.0f} %{more}", STYLE["attente"]["text"]
    if t.turning and st == "disponible":
        return f"Arrivé chez vous · à adopter · {t.cost} pts · ~{learning.weeks_left(state, state.viewer, tid)} sem.", STYLE["disponible"]["edge"]
    if st == "connu":
        return "Connu", STYLE["connu"]["edge"]
    if st == "en_cours":
        done = int(100 * tribe.progress.get(tid, 0.0) / t.cost) if t.cost else 100
        return f"En cours · {done} % · ~{learning.weeks_left(state, state.viewer, tid)} sem.", STYLE["en_cours"]["edge"]
    if st == "disponible":
        return f"{t.cost} pts · ~{learning.weeks_left(state, state.viewer, tid)} sem.", STYLE["disponible"]["edge"]
    if st == "verrouille":
        missing = tech.missing_prereqs(tribe, t)
        text = ("Il faut : " + ", ".join(m.name for m in missing[:2])) if missing else "Verrouillé"
        if t.turning and turning.presence(tribe, tid) > 0:
            text += f" · chez vous {turning.presence(tribe, tid):.0f} %"
        return text, STYLE["verrouille"]["text"]
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
            if tier in tech.TURNING_TIERS:
                # La rangee des grands tournants : un bandeau plus chaud.
                band = [int(v) for v in to_screen(cam, view, (0, rows[tier], sec["body"][2], world["heights"][tier]))]
                pygame.draw.rect(screen, _lerp(tint, (90, 62, 30), 0.35), band)
            ry = int(sy(rows[tier] + world["heights"][tier])) - 1
            pygame.draw.line(screen, _lerp(tint, (255, 255, 255), 0.06), (body[0] + 6, ry), (body[0] + body[2] - 6, ry))
        for i in range(len(cols)):
            x = int(sx(cols[i]))
            pygame.draw.line(screen, _lerp(tint, (255, 255, 255), 0.035), (x, body[1]), (x, body[1] + body[3]))
    nodes = lay["nodes"]
    # Le savoir montre : celui sous la souris, sinon celui qu'on a choisi ;
    # sa chaine (ce qu'il faut avant, ce qu'il ouvre) s'eclaire.
    focus = None
    if vx <= mx <= vx + vw and vy <= my <= vy + vh:
        focus = next((tid for tid, (x_, y_, w_, h_) in nodes.items() if tid in lay["visible"] and x_ <= mx <= x_ + w_ and y_ <= my <= y_ + h_), None)
    focus = focus or pick
    up, down = layout.chain_of(focus) if focus in tech.TECHS else (set(), set())
    _links(screen, world, states, cam, view, z, focus, up, down)
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
            if ry > vy + vh or ry + world["heights"][tier] * z < vy:
                continue
            font = r.small if z >= 1.0 else r.tiny
            label = _wrap(font, tech.TIER_NAMES[tier], int(gutter) - 18)[:2]
            if tier in tech.TURNING_TIERS:
                cost = "naissent, se répandent"
            else:
                cost = f"{tech.TIER_COST[tier]} pts" if tech.TIER_COST[tier] else "au départ"
            lh = font.get_height()
            ty = int(ry + (min(world["heights"][tier], TREE_TURN_ROW) * z - lh * (len(label) + 1)) / 2)
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
        if t.turning:
            _turning_card(r, state, tribe, t, st, (x, y, w, h), z, pick, hover, head_font)
            continue
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
        elif st == "absent":
            pygame.draw.line(screen, (120, 70, 60), (x + 6, y + h - 6), (x + w - 6, y + 6), 1)
        if t.drawn and st != "connu":
            _chance_pill(r, state, tribe, t, st, x + w, y, z)
    if focus is not None:
        # Hors de la chaine : effaces ; dans la chaine : un liseré de sa couleur.
        veil = None
        for tid, rect in nodes.items():
            if tid not in lay["visible"] or tid == focus:
                continue
            x, y, w, h = (int(v) for v in rect)
            if tid in up or tid in down:
                pygame.draw.rect(screen, CHAIN_UP if tid in up else CHAIN_DOWN, (x - 2, y - 2, w + 4, h + 4), 2, border_radius=7)
                continue
            if veil is None or veil.get_size() != (w, h):
                veil = pygame.Surface((w, h), pygame.SRCALPHA)
                veil.fill((12, 9, 7, 150))
            screen.blit(veil, (x, y))
    screen.set_clip(None)
    pygame.draw.rect(screen, GOLD_DEEP, view, 1)
    _controls(r, lay, mx, my)
    sx0, sy0, _sw, sh0 = lay["strip"]
    zoom = f"zoom {int(round(100 * z))} %"
    hint = r.tiny.render(f"Survolez un savoir : en or ce qu'il faut avant, en bleu ce qu'il ouvre  ·  glisser : se déplacer  ·  molette : zoomer  ·  {zoom}", True, NOTE)
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


# La chaine d'un savoir : ce qu'il faut avant lui (or), ce qu'il ouvre (bleu).
CHAIN_UP = (246, 200, 96)
CHAIN_DOWN = (104, 182, 232)


def _links(screen, world, states, cam, view, z, focus, up, down) -> None:
    """Les liens de l'arbre (layout.tree_links), a angles droits. Sans
    savoir montre : dores (connus), verts (ils menent a un savoir
    disponible), sombres (pas encore). Un savoir montre : sa chaine en or
    (avant lui) et en bleu (apres lui), plus epaisse ; le reste en filigrane."""
    vx, vy, vw, vh = view
    x0, y0, _z = cam
    arrow = max(3, int(5 * min(1.3, z)))
    order = []
    for (pid, tid), pts in world["links"].items():
        if focus is not None and (pid == focus or pid in up) and (tid == focus or tid in up):
            rank, color, width = 2, CHAIN_UP, 3
        elif focus is not None and (pid == focus or pid in down) and (tid in down):
            rank, color, width = 2, CHAIN_DOWN, 3
        else:
            known = states[pid] == "connu"
            child = states[tid]
            if known and child == "connu":
                rank, color, width = 1, (190, 156, 88), 2
            elif known and child in ("disponible", "en_cours"):
                rank, color, width = 1, STYLE[child]["edge"], 2
            elif child == "absent":
                rank, color, width = 0, (72, 52, 46), 1
            else:
                rank, color, width = 0, (104, 84, 62), 1
            if focus is not None:
                rank, color, width = 0, _lerp(color, (20, 16, 12), 0.7), 1
        order.append((rank, pid, tid, pts, color, width))
    # Les liens montres par-dessus les autres.
    for rank, _pid, _tid, pts, color, width in sorted(order, key=lambda o: (o[0], o[1], o[2])):
        sp = [(vx + (px - x0) * z, vy + (py - y0) * z) for px, py in pts]
        if max(p[1] for p in sp) < vy or min(p[1] for p in sp) > vy + vh:
            continue
        w = max(1, int(round(width * min(1.3, z))))
        if w > 1:
            pygame.draw.lines(screen, _lerp(color, (0, 0, 0), 0.6), False, sp, w + 2)
        pygame.draw.lines(screen, color, False, sp, w)
        end = sp[-1]
        pygame.draw.polygon(screen, color, [(end[0] - arrow, end[1] - arrow - 1), (end[0] + arrow, end[1] - arrow - 1), (end[0], end[1])])


def _chance_pill(r, state, tribe, t, st, right: int, top: int, z: float) -> None:
    """La pastille d'un savoir tire : sa chance (un "?" avant le tirage de
    votre peuple), "monde" s'il depend du monde, rien de lisible s'il est
    absent (la carte est barree)."""
    if z < 0.7:
        return
    if st == "absent":
        text, col = "absent", (150, 96, 84)
    elif t.chance < 1.0 and draws.revealed(tribe, t.id):
        text, col = "le sort a souri", C.bon
    elif t.chance < 1.0:
        text, col = f"{round(100 * t.chance)} % ?", (220, 190, 120)
    elif t.group:
        text, col = "né ici (unique)", C.bon
    else:
        text, col = "né dans ce monde", C.bon
    surf = r.tiny.render(text, True, col)
    pw = surf.get_width() + 10
    px = right - pw - (22 if st == "verrouille" else 6)
    pygame.draw.rect(r.screen, (24, 19, 15), (px, top + 3, pw, 15), border_radius=7)
    pygame.draw.rect(r.screen, _lerp(col, (0, 0, 0), 0.4), (px, top + 3, pw, 15), 1, border_radius=7)
    r.screen.blit(surf, (px + 5, top + 3))


def _turning_card(r, state, tribe, t, st, rect, z, pick, hover, head_font) -> None:
    """Une carte de grand tournant : un cadre double, son nom en grand, son
    etat, sa presence chez vous, son berceau, ce qu'il ouvre."""
    screen = r.screen
    x, y, w, h = rect
    gold = TURN_GOLD if st != "verrouille" else (120, 100, 70)
    pygame.draw.rect(screen, _lerp(gold, (0, 0, 0), 0.45), (x + 3, y + 3, w - 6, h - 6), 1, border_radius=5)
    for cx_, cy_ in ((x + 6, y + 6), (x + w - 7, y + 6), (x + 6, y + h - 7), (x + w - 7, y + h - 7)):
        pygame.draw.circle(screen, gold, (cx_, cy_), max(2, int(3 * min(1.2, z))))
    rad = max(10, min(30, int(24 * z)))
    med = medallion(tech.era_of(t), t.branch, st, rad)
    screen.blit(med, (x + 10, y + h // 2 - med.get_height() // 2))
    tx = x + 2 * rad + 22
    tw = w - (tx - x) - 14
    big = head_font if z >= 0.8 else r.small
    yy = y + max(4, int(8 * z))
    screen.blit(r.tiny.render("GRAND TOURNANT", True, _lerp(gold, (0, 0, 0), 0.2)), (tx, yy))
    yy += r.tiny.get_height()
    screen.blit(big.render(_fit(big, t.name, tw), True, INK if st != "verrouille" else STYLE["verrouille"]["text"]), (tx, yy))
    yy += big.get_height()
    if z >= 0.7:
        text, color = _status_line(state, tribe, t.id, st)
        screen.blit(r.tiny.render(_fit(r.tiny, text, tw), True, color), (tx, yy))
        yy += r.tiny.get_height() + 1
    if z >= 0.95:
        if turning.born(state, t.id):
            line = f"{turning.born_text(state, state.viewer, t.id)} · {len(turning.adopted_by(state, t.id))} peuples l'ont adopté"
        else:
            line = "Ouvre : " + ", ".join(p.name for p in tech.pan_of(t.id))
        screen.blit(r.tiny.render(_fit(r.tiny, line, tw), True, NOTE), (tx, yy))
    # La presence chez vous (avant l'adoption), ou l'adoption en cours.
    if st in ("attente", "disponible", "en_cours", "verrouille"):
        done = tribe.progress.get(t.id, 0.0) / t.cost if t.cost else 0.0
        if st == "en_cours" or done > 0:
            frac, col = done, STYLE["en_cours"]["edge"]
        else:
            frac, col = turning.presence(tribe, t.id) / 100.0, gold
        bar = (tx, y + h - max(9, int(12 * z)), tw, max(3, int(5 * z)))
        pygame.draw.rect(screen, (23, 18, 14), bar, border_radius=2)
        pygame.draw.rect(screen, col, (bar[0], bar[1], int(bar[2] * min(1.0, frac)), bar[3]), border_radius=2)
    if st == "connu":
        _check(screen, x + w - 12, y + 12, GOLD, r=max(5, int(7 * min(1.2, z))))
    elif st == "verrouille":
        _lock(screen, x + w - 12, y + 12, STYLE["verrouille"]["edge"])


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
    turns = tech.turnings()
    pace += f"  ·  grands tournants adoptés : {sum(1 for t in turns if t.id in tribe.knowledge)} / {len(turns)}"
    screen.blit(r.tiny.render(pace, True, NOTE), (bx + 22, by + 42))
    # Legende.
    lx = bx + 140
    for key in ("connu", "en_cours", "disponible", "attente", "verrouille", "absent"):
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
    if t.turning:
        sub = f"{tech.ERAS[tech.era_of(t)][0]}  ·  Grand tournant"
    elif t.drawn:
        sub += "  ·  " + draws.chance_text(state, state.viewer, shown)
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
        # Une section : une note qui annonce une liste (« Il faut... : »).
        if style_key == "note" and text.rstrip().endswith(":") and text != "Effets :":
            mode = "need"
            need.append((text, "section"))
            continue
        if style_key == "note" and text.startswith("Apprentissage"):
            continue
        if mode == "need" or (style_key == "ok" and text.startswith("Connu de")):
            if style_key in ("ok", "manque", "info"):
                need.append((text.strip(), style_key))
    _column(r, left, "CE QU'IL FAIT", what)
    if st == "connu":
        done = "Votre peuple l'a adopté : son pan est ouvert." if t.turning else "Votre peuple sait déjà faire cela."
        _column(r, right, "SAVOIR ACQUIS", [(done, "ok")])
    elif st == "absent":
        _column(r, right, "IL NE VIENDRA PAS", need)
    else:
        _column(r, right, "CE QU'IL DEMANDE", need)
    if st != "connu":
        mx, my = pygame.mouse.get_pos()
        rect = lay["learn"]
        on = st == "disponible"
        hover = on and rect[0] <= mx <= rect[0] + rect[2] and rect[1] <= my <= rect[1] + rect[3]
        label = {"disponible": "Adopter" if t.turning else "Apprendre", "en_cours": "En cours"}.get(st, "Jamais" if st == "absent" else "Pas encore")
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
        color = {"texte": SOFT, "effet": (178, 205, 140), "ok": GOOD, "manque": BAD, "info": SOFT}.get(kind, SOFT)
        indent = 18 if kind in ("effet", "ok", "manque", "info") else 0
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
    if t.prereqs:
        lines.append(("Il faut : " + ", ".join(tech.TECHS[p].name for p in t.prereqs), CHAIN_UP))
    after = tech.pan_of(tid)
    if after and not t.turning:
        lines.append(("Mène à : " + ", ".join(a.name for a in after), CHAIN_DOWN))
    if t.turning:
        lines.append(("Ouvre : " + ", ".join(p.name for p in tech.pan_of(t.id)), TURN_GOLD))
    if t.drawn:
        lines.append((draws.chance_text(state, state.viewer, tid), (220, 190, 120)))
        if st == "absent":
            lines.append((draws.why_absent(state, state.viewer, tid), STYLE["absent"]["text"]))
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
