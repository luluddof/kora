"""LE DESSIN DU TUTORIEL (tutoriel.py) : sa fiche en haut a gauche, sous la
barre du haut (les cartes d'evenements passent dessous), et le bouton Tuto,
a cote du bouton Carte ; ce que l'etape concerne s'eclaire (un onglet, le
bouton du temps, celui des cartes).

tuto_layout / tuto_hit et button_rect sont purs (testables sans fenetre) ;
draw et draw_button dessinent avec la charte (theme.py). Les rectangles
dessines restent sur le renderer : r.tuto_hits (la fiche), r.tuto_button.
"""

from __future__ import annotations

import pygame

from src.kora import theme, tutoriel
from src.kora.layout import HUD_HEIGHT, MAP_BUTTON_H, MAP_BUTTON_W
from src.kora.theme import C

CARD_W = 410
PAD = 14
HEAD = 46
FOOT = 48
BUTTON_W = 104


def button_rect(width: int, height: int) -> tuple:
    """Le bouton Tuto : a droite du bouton Carte, en bas a gauche."""
    return (12 + MAP_BUTTON_W + 8, height - MAP_BUTTON_H - 12, BUTTON_W, MAP_BUTTON_H)


def tuto_layout(width: int, height: int, body_h: int, first: bool) -> dict:
    """La fiche : sa boite, son texte (body), ses boutons."""
    x, y = 12, HUD_HEIGHT + 8
    h = HEAD + body_h + FOOT
    w = min(CARD_W, width - 24)
    by = y + h - FOOT + 6
    return {
        "box": (x, y, w, h),
        "body": (x + PAD, y + HEAD, w - 2 * PAD, body_h),
        "close": (x + w - 36, y + 10, 26, 26),
        "next": (x + w - PAD - 136, by, 136, 32),
        "prev": None if first else (x + PAD, by, 112, 32),
    }


def _inside(rect, mx: int, my: int) -> bool:
    return rect is not None and rect[0] <= mx <= rect[0] + rect[2] and rect[1] <= my <= rect[1] + rect[3]


def tuto_hit(lay: dict, mx: int, my: int):
    """"close", "next", "prev", "card" (la fiche, sans bouton) ou None."""
    if not lay:
        return None
    for key in ("close", "next", "prev"):
        if _inside(lay.get(key), mx, my):
            return key
    return "card" if _inside(lay.get("box"), mx, my) else None


def _target_rect(r, target: str):
    if target.startswith("tab:"):
        return (getattr(r, "side_hits", {}) or {}).get("tabs", {}).get(target[4:])
    if target == "hud:pause":
        return (getattr(r, "hud_hits", {}) or {}).get("pause")
    if target == "carte":
        return (getattr(r, "mode_hits", {}) or {}).get("button")
    if target == "tuto":
        return getattr(r, "tuto_button", None)
    return None


def _light(screen, rect, beat: float) -> None:
    """Ce que l'etape concerne : une lueur de braise et un liseré qui respire."""
    theme.glow(screen, rect, C.braise, 1.6 + 1.6 * beat)
    x, y, w, h = (int(v) for v in rect)
    ring = pygame.Surface((w + 12, h + 12), pygame.SRCALPHA)
    pygame.draw.rect(ring, (*C.braise, int(120 + 135 * beat)), (0, 0, w + 12, h + 12), 3, border_radius=8)
    screen.blit(ring, (x - 6, y - 6))


def draw_button(r, ui) -> None:
    w, h = r.screen.get_size()
    rect = button_rect(w, h)
    r.tuto_button = rect
    mx, my = pygame.mouse.get_pos()
    theme.button(r.screen, rect, "Tuto", "second", hover=_inside(rect, mx, my), icon_key="boussole", key_hint="F1", active=tutoriel.is_open(ui))


def draw(r, state, ui) -> None:
    step = tutoriel.current(ui)
    if step is None:
        r.tuto_hits = {}
        return
    screen = r.screen
    w, h = screen.get_size()
    g = ui["tuto"]
    idx = min(g.get("step", 0), len(tutoriel.STEPS) - 1)
    last = idx == len(tutoriel.STEPS) - 1
    mode = tutoriel.doing(ui)
    f_text, f_todo = theme.font("petit"), theme.font("petit_gras")
    inner = min(CARD_W, w - 24) - 2 * PAD
    lines = theme.wrap(f_text, step.text, inner)
    todo = ""
    if mode == "geste":
        todo = f"À faire : {step.todo}"
    elif mode == "fait":
        todo = "C'est fait !"
    todo_lines = theme.wrap(f_todo, todo, inner) if todo else []
    body_h = len(lines) * (f_text.get_height() + 1) + (10 + len(todo_lines) * (f_todo.get_height() + 1) if todo_lines else 0)
    lay = tuto_layout(w, h, body_h, idx == 0)
    r.tuto_hits = lay
    t = pygame.time.get_ticks() / 1000.0
    target = _target_rect(r, step.target)
    if target is not None:
        _light(screen, target, theme.pulse(t, 1.4))
    x, y, bw, _bh = lay["box"]
    theme.panel(screen, lay["box"], "pierre")
    screen.blit(theme.medallion("boussole", 16, "actif"), (x + 10, y + 8))
    theme.text(screen, step.title, "h3", C.os, (x + 52, y + 13), bw - 140)
    count = f"{idx + 1} / {len(tutoriel.STEPS)}"
    cf = theme.font("mini")
    screen.blit(cf.render(count, True, C.lin), (x + bw - 44 - cf.size(count)[0], y + 17))
    mx, my = pygame.mouse.get_pos()
    theme.button(screen, lay["close"], "", "second", hover=_inside(lay["close"], mx, my), icon_key="fermer")
    bx, yy = lay["body"][0], lay["body"][1]
    for line in lines:
        screen.blit(f_text.render(line, True, C.os), (bx, yy))
        yy += f_text.get_height() + 1
    if todo_lines:
        yy += 10
        color = C.bon if mode == "fait" else C.ocre_jaune
        for line in todo_lines:
            screen.blit(f_todo.render(line, True, color), (bx, yy))
            yy += f_todo.get_height() + 1
    if lay["prev"] is not None:
        theme.button(screen, lay["prev"], "Précédent", "discret", hover=_inside(lay["prev"], mx, my))
    label = "Terminer" if last else ("Suivant" if mode != "geste" else "Passer")
    rank = "principal" if mode != "geste" else "second"
    theme.button(screen, lay["next"], label, rank, hover=_inside(lay["next"], mx, my))
