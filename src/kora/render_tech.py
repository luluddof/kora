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


def _blit_fit(screen, font, text: str, color, x: int, y: int, width: int) -> int:
    """Une ligne qui tient dans `width` : un peu resserree s'il le faut (au
    plus 25 %), sinon coupee avec "…". Rend sa hauteur."""
    surf = font.render(text, True, color)
    if surf.get_width() > width > 0:
        if surf.get_width() * 0.75 <= width:
            surf = pygame.transform.smoothscale(surf, (int(width), surf.get_height()))
        else:
            surf = font.render(_fit(font, text, width), True, color)
    screen.blit(surf, (x, y))
    return surf.get_height()


def _line_h(font) -> int:
    """L'interligne d'un nom : la police a beaucoup d'air, on la serre."""
    return max(1, int(font.get_height() * 0.88))


def SMALL_FONTS() -> list:
    """De loin, le nom d'une carte descend en taille plutot que d'etre coupe."""
    return [theme.font_file("sans", size) for size in (13, 12, 11, 10, 9)]


def _name_block(fonts, name: str, width: int, height: int):
    """(police, lignes) du nom d'une carte : la plus grande police ou il
    tient en deux lignes au plus, dans la largeur et la hauteur donnees ;
    sinon la plus petite (les lignes seront resserrees ou coupees)."""
    for font in fonts:
        parts = _wrap(font, name, width)
        if len(parts) <= 2 and len(parts) * _line_h(font) <= height and all(font.size(p)[0] <= width for p in parts):
            return font, parts
    font = fonts[-1]
    lines = max(1, min(2, height // max(1, _line_h(font))))
    parts = _wrap(font, name, width)
    if len(parts) > lines:
        parts = parts[: lines - 1] + [" ".join(parts[lines - 1:])]
    return font, parts


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
    _links(screen, world, states, cam, view, z)
    # Noms des ages, des colonnes, des paliers (par-dessus les liens).
    gutter = TREE_GUTTER * z
    small = z < 0.62
    for sec in world["sections"]:
        era = sec["era"]
        era_name, tiers, _branches = tech.ERAS[era]
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
        # Le medaillon a la taille de la carte (rien de loin : la place au nom) ;
        # a droite, la place de la coche ou du cadenas.
        icon = max(6, int(13 * min(1.2, z)))
        if z >= 0.55:
            rad = max(8, min(22, int(17 * z)))
            med = medallion(tech.era_of(t), t.branch, st, rad)
            screen.blit(med, (x + 5, y + h // 2 - med.get_height() // 2))
            tx = x + 2 * rad + 12
        else:
            tx = x + 5
        text_w = w - (tx - x) - icon - 6
        extra = []
        if z >= 0.8:
            text, color = _status_line(state, tribe, tid, st)
            extra.append((text, r.tiny, color))
        if z >= 1.05:
            first = tech.summary(t)
            if first:
                extra.append((first, r.tiny, (178, 205, 140) if st != "verrouille" else (130, 113, 96)))
        room = h - 4 - sum(f.get_height() for _t, f, _c in extra)
        # La plus grande police ou le nom tient (deux lignes au plus) : celle
        # qui convient a la taille de la carte a ce zoom.
        fonts = [f for f in (head_font, r.small, r.tiny) if _line_h(f) * 2 <= max(h - 4, 1) * 1.15 or f is r.tiny] + SMALL_FONTS()
        font, parts = _name_block(fonts, t.name, text_w, room)
        lines = [(p_, font, style["text"], _line_h(font)) for p_ in parts] + [(t_, f_, c_, f_.get_height()) for t_, f_, c_ in extra]
        total = sum(lh for *_rest, lh in lines)
        ty = y + max(1, (h - total) // 2)
        for text, font_, color, lh in lines:
            if ty + lh > y + h:
                break
            _blit_fit(screen, font_, text, color, tx, ty - (font_.get_height() - lh) // 2, text_w)
            ty += lh
        done = tribe.progress.get(tid, 0.0) / t.cost if t.cost else 0.0
        if st != "connu" and done > 0:
            bar = (tx, y + h - max(5, int(7 * z)), w - (tx - x) - 10, max(2, int(3 * z)))
            pygame.draw.rect(screen, (23, 18, 14), bar)
            pygame.draw.rect(screen, STYLE["en_cours"]["edge"] if st == "en_cours" else (143, 130, 115), (bar[0], bar[1], int(bar[2] * min(1.0, done)), bar[3]))
        if st == "connu":
            _check(screen, x + w - icon // 2 - 3, y + icon // 2 + 3, GOLD, r=max(3, icon // 2))
        elif st == "verrouille" and z >= 0.55:
            _lock(screen, x + w - 10, y + 10, style["edge"])
        elif st == "absent":
            pygame.draw.line(screen, (120, 70, 60), (x + 6, y + h - 6), (x + w - 6, y + 6), 1)
        if t.drawn and st != "connu":
            # En bas a droite : le nom reste lisible.
            _chance_pill(r, state, tribe, t, st, x + w, y + h - 20, z)
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


def _links(screen, world, states, cam, view, z) -> None:
    """Les liens de l'arbre (tree_graph.py) : dores (chemin connu), de la
    couleur du savoir quand ils menent a un savoir disponible ou en cours,
    sombres (pas encore), rouge sombre (vers un savoir absent)."""
    vx, vy, vw, vh = view
    x0, y0, _z = cam
    arrow = max(3, int(5 * min(1.3, z)))
    order = []
    for (pid, tid), pts in world["links"].items():
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
        order.append((rank, pid, tid, pts, color, width))
    # Les chemins ouverts par-dessus les autres.
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
    if z < 0.9:
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
    icon = max(7, int(15 * min(1.2, z)))
    if z >= 0.5:
        rad = max(8, min(30, int(24 * z)))
        med = medallion(tech.era_of(t), t.branch, st, rad)
        screen.blit(med, (x + 10, y + h // 2 - med.get_height() // 2))
        tx = x + 2 * rad + 22
    else:
        tx = x + 8
    tw = w - (tx - x) - icon - 10
    bar_h = max(9, int(12 * z))
    head = []
    if z >= 0.6:
        head.append(("GRAND TOURNANT", r.tiny, _lerp(gold, (0, 0, 0), 0.2), r.tiny.get_height()))
    tail = []
    if z >= 0.7:
        text, color = _status_line(state, tribe, t.id, st)
        tail.append((text, r.tiny, color, r.tiny.get_height()))
    if z >= 0.95:
        if turning.born(state, t.id):
            line = f"{turning.born_text(state, state.viewer, t.id)} · {len(turning.adopted_by(state, t.id))} peuples l'ont adopté"
        else:
            line = "Ouvre : " + ", ".join(p.name for p in tech.pan_of(t.id))
        tail.append((line, r.tiny, NOTE, r.tiny.get_height()))
    big_fonts = [f for f in (head_font, r.small, r.tiny) if _line_h(f) * 2 <= h * 0.6 or f is r.tiny] + SMALL_FONTS()
    room = h - bar_h - 4 - sum(row[3] for row in head + tail)
    big, parts = _name_block(big_fonts, t.name, tw, max(_line_h(big_fonts[-1]), room))
    name_color = INK if st != "verrouille" else STYLE["verrouille"]["text"]
    rows = head + [(p_, big, name_color, _line_h(big)) for p_ in parts] + tail
    yy = y + max(2, (h - bar_h - sum(row[3] for row in rows)) // 2)
    for text, font, color, lh in rows:
        if yy + lh > y + h - bar_h + 2:
            break
        _blit_fit(screen, font, text, color, tx, yy - (font.get_height() - lh) // 2, tw)
        yy += lh
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
        _check(screen, x + w - icon // 2 - 6, y + icon // 2 + 6, GOLD, r=max(3, icon // 2))
    elif st == "verrouille" and z >= 0.5:
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
        lines.append(("Il faut : " + ", ".join(tech.TECHS[p].name for p in t.prereqs), SOFT))
    after = tech.pan_of(tid)
    if after and not t.turning:
        lines.append(("Mène à : " + ", ".join(a.name for a in after), SOFT))
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
