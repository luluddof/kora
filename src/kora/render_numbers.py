"""L'onglet LES NOMBRES de l'ecran des savoirs (numbers.py).

A gauche, la BASE de la civilisation : quatre cartes (dix, douze, vingt,
soixante), leur avantage, le bouton pour la choisir (deux clics : le choix
est definitif, ou presque : une reforme coute cher) ; dessous, les
CALCULATEURS (equipes, points par mois, gages).
A droite, les OPERATIONS que la civilisation connait (+ au depart, puis
celles que trouvent les calculateurs), leur effet ; la numeration de
position viendra a un autre age.
"""

from __future__ import annotations

import pygame

from src.kora import money, numbers, tech, theme
from src.kora.theme import C

GREEN = (178, 205, 140)


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


def items(lay: dict) -> dict:
    return {f"nbase:{b}": r["btn"] for b, r in lay["bases"].items()}


def _hover(rect, mx, my) -> bool:
    x, y, w, h = rect
    return x <= mx <= x + w and y <= my <= y + h


def _card(screen, rect, top, bot, edge) -> None:
    from src.kora.render_tech import _gradient_card

    x, y, w, h = (int(v) for v in rect)
    screen.blit(_gradient_card(w, h, top, bot, 6), (x, y))
    pygame.draw.rect(screen, edge, (x, y, w, h), 1, border_radius=6)


def draw(r, state, lay: dict, ui: dict | None) -> None:
    ui = ui if ui is not None else {}
    screen = r.screen
    tid = state.viewer
    data = numbers.page(state, tid)
    if not data:
        return
    page = lay["numbers"]
    mx, my = pygame.mouse.get_pos()
    tips = []
    lx, ly, lw, _lh = page["left"]
    rx, ry, rw, _rh = page["right"]
    # --- la base ---------------------------------------------------------------
    theme.title(screen, "La base des nombres", lx, ly, "h2", C.ocre_jaune)
    if not data["numbers"]:
        sub = "Il faut connaître Nombres additifs (âge des villages) pour choisir sa base."
    elif not data["base"]:
        sub = "Choisissez-la une fois pour toutes : la changer plus tard est une lourde réforme."
    elif data["reform_weeks"]:
        sub = f"Réforme en cours : encore {data['reform_weeks']} semaines sans l'avantage de la base."
    else:
        sub = f"Changer : une réforme ({numbers.REFORM_PRESTIGE} de prestige, trois ans sans l'avantage, une fois tous les 30 ans)."
    theme.text(screen, sub, "mini", C.cendre, (lx, ly + 30), lw)
    pending = ui.get("base_confirm")
    for base in numbers.BASE_ORDER:
        rects = page["bases"][base]
        name, about, _eff = numbers.BASES[base]
        mine = data["base"] == base
        why = data["blocks"][base]
        if mine:
            top, bot, edge = (78, 58, 30), (52, 38, 21), C.ocre_jaune
        elif data["numbers"] and not why:
            top, bot, edge = (32, 58, 54), (20, 38, 35), C.savoir
        else:
            top, bot, edge = (36, 28, 22), (26, 20, 16), C.bois
        _card(screen, rects["card"], top, bot, edge)
        cx, cy, cw, ch = rects["card"]
        big = theme.font("chiffre_grand").render(str(base), True, edge)
        screen.blit(big, (cx + 12, cy + (ch - big.get_height()) // 2))
        tx = cx + 64
        room = rects["btn"][0] - tx - 10
        theme.text(screen, name, "petit_gras", C.os, (tx, cy + 5), room)
        eff = tech.effect_lines(tech.math_effect(f"base:{base}"))
        yy = cy + 25
        if ch >= 74:
            theme.text(screen, about, "mini", C.lin, (tx, yy), room)
            yy += 17
        for line in eff:
            if yy + 16 > cy + ch:
                break
            theme.text(screen, line, "mini", GREEN, (tx, yy), room)
            yy += 16
        btn = rects["btn"]
        if mine:
            label, on = ("Votre base" if not data["reform_weeks"] else "En réforme"), False
        elif pending == base and not why:
            label, on = ("Confirmer la réforme" if data["base"] else "Confirmer ce choix"), True
        else:
            label, on = ("Réformer" if data["base"] else "Choisir"), bool(data["numbers"]) and not why
        hover = _hover(btn, mx, my)
        theme.button(screen, btn, label, "principal" if pending == base and on else "second", on, hover and on, active=mine)
        if hover and why and not mine:
            tips.append(([(why, C.alerte)], btn))
        elif hover and on:
            hint = "Un second clic confirme." if pending != base else "La base est presque définitive."
            tips.append(([(name, C.os, "petit_gras"), (about, C.lin)] + [(e, GREEN) for e in eff] + [(hint, C.cendre)], btn))
    # --- les calculateurs ------------------------------------------------------
    cx, cy, cw, ch = page["calc"]
    _card(screen, page["calc"], (40, 31, 24), (28, 21, 16), C.bois)
    screen.blit(theme.icon("abaque", 34, C.ocre_jaune), (cx + 12, cy + 12))
    tx = cx + 58
    theme.text(screen, "Les calculateurs", "petit_gras", C.os, (tx, cy + 8), cw - 70)
    if not data["numbers"]:
        rows = [("Un métier du village, avec Nombres additifs.", C.cendre)]
    else:
        n, pts = data["teams"], data["points"]
        rows = [
            (f"{n} équipe{'s' if n > 1 else ''} au travail · {_num(pts)} points de calcul par mois", C.lin if n else C.alerte),
            ("Mettez-les au travail dans un village (page Métiers)." if not n else "Ils cherchent la prochaine opération.", C.cendre),
        ]
        paid = money.wage_mult(state, tid, "calcul")
        if paid > 1.0:
            rows.append(("Gages payés : +25 % de points", C.bon))
        elif paid < 1.0:
            rows.append(("Gages promis et pas payés : -10 % de points", C.mauvais))
        elif money.has_money(state, tid):
            rows.append(("Payer leurs gages (Trésor) : +25 % de points", C.cendre))
        if data["goal"]:
            rows.append((f"Prochaine opération : {_num(data['progress'])} / {data['goal']} points", C.ocre_jaune))
    yy = cy + 32
    for text, col in rows:
        if yy + 16 > cy + ch:
            break
        theme.text(screen, text, "mini", col, (tx, yy), cw - 70)
        yy += 17
    # --- les operations --------------------------------------------------------
    theme.title(screen, "Les opérations de la civilisation", rx, ry, "h2", C.ocre_jaune)
    known = sum(1 for o in data["ops"] if o["state"] == "connue")
    theme.text(screen, f"{known} sur {len(data['ops'])} connues · les calculateurs trouvent les suivantes", "mini", C.cendre, (rx, ry + 30), rw)
    for op in data["ops"]:
        rect = page["ops"][op["id"]]
        st = op["state"]
        if st == "connue":
            top, bot, edge, sign_c = (72, 54, 30), (48, 35, 21), C.ocre_jaune, C.ocre_jaune
        elif st == "en_cours":
            top, bot, edge, sign_c = (92, 52, 26), (60, 33, 18), C.braise, C.braise
        else:
            top, bot, edge, sign_c = (30, 24, 19), (22, 17, 13), (66, 52, 40), C.cendre
        _card(screen, rect, top, bot, edge)
        x, y, w, h = rect
        sign = theme.font("chiffre_grand").render(op["sign"], True, sign_c)
        screen.blit(sign, (x + 24 - sign.get_width() // 2, y + (h - sign.get_height()) // 2))
        tx = x + 52
        status = {"connue": "Connue", "en_cours": "En recherche", "a_trouver": "À trouver"}[st]
        if st == "en_cours" and op["cost"]:
            status += f" · {_num(data['progress'])}/{op['cost']} points"
        elif st == "a_trouver" and op["cost"]:
            status += f" · {op['cost']} points"
        stw = theme.font("mini").size(status)[0]
        theme.text(screen, status, "mini", edge if st != "a_trouver" else C.cendre, (x + w - stw - 10, y + 6))
        theme.text(screen, op["name"], "petit_gras", C.os if st != "a_trouver" else C.lin, (tx, y + 4), w - 72 - stw)
        eff = tech.effect_lines(tech.math_effect(op["effect"]))
        yy = y + 24
        if h >= 66:
            theme.text(screen, op["text"], "mini", C.lin if st != "a_trouver" else C.cendre, (tx, yy), w - 62)
            yy += 17
        theme.text(screen, " · ".join(eff), "mini", GREEN if st == "connue" else (130, 140, 110), (tx, yy), w - 62)
        if st == "en_cours" and op["cost"]:
            theme.bar(screen, (tx, y + h - 8, w - 62, 4), data["progress"] / op["cost"], C.braise)
        if _hover(rect, mx, my):
            tips.append(([(f"{op['name']} ({op['sign']})", C.os, "petit_gras"), (op["text"], C.lin)] + [(e, GREEN) for e in eff], rect))
    x, y, w, h = page["later"]
    _card(screen, page["later"], (26, 21, 17), (20, 16, 12), (58, 46, 36))
    sign = theme.font("chiffre_grand").render("0", True, (92, 80, 68))
    screen.blit(sign, (x + 24 - sign.get_width() // 2, y + (h - sign.get_height()) // 2))
    theme.text(screen, "Numération de position", "petit_gras", C.cendre, (x + 52, y + 4), w - 62)
    theme.text(screen, "Un autre âge : le chiffre vaut selon sa place, et le zéro.", "mini", (110, 98, 84), (x + 52, y + 24), w - 62)
    for lines, avoid in tips:
        theme.tooltip(screen, lines, mx + 14, my + 16, 380, avoid=avoid)


def _num(v: float) -> str:
    return f"{v:.1f}".replace(".", ",") if v < 10 else f"{v:.0f}"
