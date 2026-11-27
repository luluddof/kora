"""LA COLONNE DE GAUCHE : ce qui attend le joueur (2026-11-19).

De haut en bas : les ALERTES (objectifs.alertes : une faim, un siege, un
clan qui part... chacune un clic vers ou agir), les cartes d'evenement
(render_panels.draw_event_cards, dessous), puis LE CHEMIN DU PREMIER
VILLAGE (objectifs.chemin), qui se replie d'un clic sur son titre.

Les rectangles cliquables : r.alert_hits [(rect, action)] (l'action est un
choix de panneau : Play.side_click, partie_ecrans.py) et r.goal_hits {"toggle": rect}.
"""

from __future__ import annotations

import pygame

from src.kora import objectifs, theme
from src.kora.layout import HUD_HEIGHT
from src.kora.theme import C

COL_X = 10
COL_W = 286
ALERT_H = 30
TONE_COLOR = {"danger": C.mauvais, "alerte": C.alerte, "info": C.braise}


def _hover(rect) -> bool:
    mx, my = pygame.mouse.get_pos()
    return rect[0] <= mx <= rect[0] + rect[2] and rect[1] <= my <= rect[1] + rect[3]


def column_top(r) -> int:
    """Le haut de la colonne : sous la barre (et ce qu'elle ecrit dessous :
    render.draw, "column_top"), sous la fiche du tutoriel."""
    y = getattr(r, "column_top", HUD_HEIGHT + 8)
    box = (getattr(r, "tuto_hits", None) or {}).get("box")
    if box is not None:
        y = max(y, box[1] + box[3] + 10)
    return y


def draw_alerts(r, state) -> int:
    """Les alertes ; rend le y sous elles."""
    # Une liste (2026-11-27) : deux alertes peuvent mener au meme endroit.
    r.alert_hits = []
    y = column_top(r)
    items = objectifs.alertes(state)
    if not items:
        return y
    t = pygame.time.get_ticks() / 1000.0
    shown = items[: objectifs.MAX_ALERTS]
    floor = getattr(r, "left_floor", r.screen.get_height() - 60)
    shown = [a for i, a in enumerate(shown) if y + (i + 1) * (ALERT_H + 4) <= floor]
    for k, a in enumerate(shown):
        rect = (COL_X, y, COL_W, ALERT_H)
        col = TONE_COLOR.get(a["tone"], C.alerte)
        over = _hover(rect)
        if a["tone"] == "danger":
            theme.glow(r.screen, rect, col, 0.25 + 0.45 * theme.pulse(t + k * 0.3))
        theme.panel(r.screen, rect, "carte_survol" if over else "carte")
        # Le bord gauche a la couleur de la gravite ; une icone ; le texte.
        pygame.draw.rect(r.screen, col, (COL_X + 1, y + 3, 4, ALERT_H - 6), border_radius=2)
        r.screen.blit(theme.icon(a["icon"], 18, col), (COL_X + 12, y + (ALERT_H - 18) // 2))
        theme.text(r.screen, a["text"], "petit_gras" if a["tone"] == "danger" else "petit", C.os if over else theme._mix(col, C.os, 0.55), (COL_X + 38, y + 5), COL_W - 60)
        r.screen.blit(theme.icon("voir", 14, C.cendre if not over else C.braise), (COL_X + COL_W - 22, y + 8))
        r.alert_hits.append((rect, a["action"]))
        y += ALERT_H + 4
    if len(items) > len(shown):
        more = len(items) - len(shown)
        theme.text(r.screen, f"et {more} autre{'s' if more > 1 else ''} alerte{'s' if more > 1 else ''}", "mini", C.cendre, (COL_X + 12, y))
        y += 18
    return y + 4


def draw_goal(r, state, ui, top: int) -> None:
    """Le chemin du premier village, sous les cartes d'evenement."""
    r.goal_hits = {}
    r.goal_box = None
    goal = objectifs.chemin(state)
    if goal is None:
        return
    folded = bool(ui.get("goal_folded")) if isinstance(ui, dict) else False
    steps = goal["steps"]
    cur = goal["current"]
    f_line = theme.font("mini")
    # La hauteur : le titre, une ligne par etape, les details de l'etape en cours.
    details = steps[cur]["lines"][:4]
    h = 82 if folded else 34 + 22 * len(steps) + 17 * len(details) + 10
    # Le bas de la colonne : la fiche epinglee d'un lieu, sinon le bouton des cartes.
    floor = getattr(r, "left_floor", r.screen.get_height() - 60)
    if top + h > floor:
        # Pas la place sous les cartes : replie.
        folded = True
        h = 82
        if top + h > floor:
            return
    rect = (COL_X, top, COL_W, h)
    # Toute la fiche prend le clic (seul le titre agit) : rien ne passe a la carte.
    r.goal_box = rect
    theme.panel(r.screen, rect, "carte")
    head = (COL_X, top, COL_W, 30)
    r.goal_hits["toggle"] = head
    over = _hover(head)
    r.screen.blit(theme.icon("village", 18, C.braise), (COL_X + 10, top + 7))
    theme.text(r.screen, goal["title"], "petit_gras", C.os if over else C.ocre_jaune, (COL_X + 34, top + 6), COL_W - 64)
    # Le pli : une pointe (en bas : deplie ; a droite : replie).
    px, py = COL_X + COL_W - 20, top + 14
    tip = [(px - 5, py - 3), (px + 5, py - 3), (px, py + 3)] if not folded else [(px - 3, py - 5), (px - 3, py + 5), (px + 3, py)]
    pygame.draw.polygon(r.screen, C.braise if over else C.cendre, tip)
    done = sum(1 for s in steps if s["done"])
    theme.dotted(r.screen, (COL_X + 10, top + 30), (COL_X + COL_W - 10, top + 30), C.ocre_sombre, 5)
    y = top + 36
    rows = [(i, s) for i, s in enumerate(steps)] if not folded else [(cur, steps[cur])]
    for i, s in rows:
        cx, cy = COL_X + 18, y + 9
        if s["done"]:
            pygame.draw.circle(r.screen, C.bon, (cx, cy), 7)
            pygame.draw.lines(r.screen, C.nuit, False, [(cx - 4, cy), (cx - 1, cy + 3), (cx + 4, cy - 3)], 2)
            col, role = C.cendre, "mini"
        elif i == cur:
            pygame.draw.circle(r.screen, C.braise, (cx, cy), 7, 2)
            pygame.draw.circle(r.screen, C.braise, (cx, cy), 3)
            col, role = C.os, "mini_gras"
        else:
            pygame.draw.circle(r.screen, C.eteint, (cx, cy), 7, 1)
            col, role = C.lin, "mini"
        label = f"{i + 1}. {s['title']}"
        theme.text(r.screen, label, role, col, (COL_X + 32, y + 1), COL_W - 44)
        y += 22
        if i == cur and not folded:
            for text, ok in details:
                mark = C.bon if ok else C.alerte
                pygame.draw.circle(r.screen, mark, (COL_X + 38, y + 8), 2)
                r.screen.blit(f_line.render(theme.fit(f_line, text, COL_W - 58), True, C.lin if ok else C.os), (COL_X + 46, y))
                y += 17
    if folded:
        theme.text(r.screen, f"{done} étape{'s' if done > 1 else ''} sur {len(steps)} · clic : le détail", "mini", C.cendre, (COL_X + 32, y + 1), COL_W - 44)


def alert_hit(r, mx: int, my: int):
    for (x, y, w, h), action in getattr(r, "alert_hits", None) or ():
        if x <= mx <= x + w and y <= my <= y + h:
            return action
    return None


def goal_hit(r, mx: int, my: int):
    rect = (getattr(r, "goal_hits", None) or {}).get("toggle")
    if rect and rect[0] <= mx <= rect[0] + rect[2] and rect[1] <= my <= rect[1] + rect[3]:
        return "toggle"
    return None
