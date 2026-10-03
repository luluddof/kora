"""L'ecran du PAYS, onglet LOIS (laws.py), dans le style du tresor :
  - en tete, le pays : son nom, son suzerain, ses tributaires, sa
    confederation ;
  - les onglets du pays (pour l'instant : Lois) ;
  - une rangee par loi : ce qu'elle dit, puis ses options en cartes ; la
    carte de l'option tenue est doree ; "Adopter" (un second clic confirme
    une reforme des nombres).
country_layout et country_hit sont purs (tests) ; draw_country dessine.
Tout changement passe par commands.py ("law").
"""

from __future__ import annotations

import pygame

from src.kora import chiefdom, confed, laws, numbers, tech, theme
from src.kora.layout import HUD_HEIGHT
from src.kora.look import country_color
from src.kora.render_tech import GOLD, INK, NOTE, SOFT
from src.kora.render_village import _fonts, _frame, _hover, _section, _tip
from src.kora.theme import C, _gradient_card

GREEN = (157, 191, 110)
TABS = (("lois", "Lois"),)


def country_layout(width: int, height: int) -> dict:
    bx = 12
    by = HUD_HEIGHT + 6
    bw = max(760, width - 66 - 24)
    bh = max(480, height - HUD_HEIGHT - 14)
    close = (bx + bw - 24 - 136, by + 16, 136, 28)
    tabs = {key: (bx + 24 + i * 150, by + 70, 140, 30) for i, (key, _l) in enumerate(TABS)}
    y = by + 70 + 30 + 20
    inner = bw - 48
    rows = {}
    for law in laws.all_laws():
        n = len(law.options)
        h = 170
        cw = (inner - (n - 1) * 12) // n if law.id == "base" else min(420, (inner - (n - 1) * 12) // n)
        cards = {}
        for i, opt in enumerate(law.options):
            card = (bx + 24 + i * (cw + 12), y + 46, cw, h - 54)
            cards[opt.id] = {"card": card, "btn": (card[0] + card[2] - 128, card[1] + card[3] - 32, 118, 26)}
        rows[law.id] = {"row": (bx + 24, y, inner, h), "cards": cards}
        y += h + 22
    return {"box": (bx, by, bw, bh), "close": close, "tabs": tabs, "rows": rows}


def country_hit(lay: dict, mx: int, my: int):
    if not lay:
        return None
    if _hover(lay["close"], mx, my):
        return "lclose"
    for key, rect in lay["tabs"].items():
        if _hover(rect, mx, my):
            return f"ltab:{key}"
    for law_id, row in lay["rows"].items():
        for opt, rects in row["cards"].items():
            if _hover(rects["btn"], mx, my):
                return f"law:{law_id}:{opt}"
    if _hover(lay["box"], mx, my):
        return "panel"
    return None


def _ties(state, tid) -> str:
    """Le pays en une ligne : suzerain, tributaires, confederation."""
    parts = []
    lord = chiefdom.overlord_of(state, tid)
    if lord:
        parts.append(f"tributaires des {state.tribes[lord].name}")
    vass = chiefdom.vassals_of(state, tid)
    if vass:
        parts.append(f"{len(vass)} tributaire{'s' if len(vass) > 1 else ''} : " + ", ".join(state.tribes[v].name for v in vass[:4]))
    group = confed.members(state, tid)
    if len(group) > 1:
        parts.append(confed.name(state, tid) + " (avec les " + ", ".join(state.tribes[t].name for t in group if t != tid) + ")")
    if parts:
        parts.append("vous voyez ce qu'ils voient, eux aussi")
    if lord:
        parts.append("vous suivez votre suzerain à la guerre, sans en déclarer")
    return " · ".join(parts) or "Un pays libre : ni suzerain, ni tributaires, ni confédérés."


def draw_country(r, state, ui) -> None:
    tid = state.viewer
    tribe = state.tribes.get(tid)
    if tribe is None:
        r.country_hits = {}
        return
    title_font, _head = _fonts(r)
    screen = r.screen
    mx, my = pygame.mouse.get_pos()
    w, h = screen.get_size()
    lay = country_layout(w, h)
    r.country_hits = lay
    _frame(r, lay["box"])
    bx, by, bw, _bh = lay["box"]
    pygame.draw.rect(screen, country_color(state, tid), (bx + 22, by + 18, 6, 34), border_radius=2)
    screen.blit(title_font.render(f"Le pays des {tribe.name}", True, GOLD), (bx + 36, by + 12))
    screen.blit(r.tiny.render(theme.fit(r.tiny, _ties(state, tid), bw - 240), True, NOTE), (bx + 38, by + 42))
    theme.button(screen, lay["close"], "Fermer [Échap]", "second", True, _hover(lay["close"], mx, my))
    for key, label in TABS:
        rect = lay["tabs"][key]
        theme.button(screen, rect, label, "second", True, _hover(rect, mx, my), active=ui.get("country_tab", "lois") == key)
    tips: list = []
    pending = ui.get("law_confirm")
    for law in laws.all_laws():
        row = lay["rows"][law.id]
        x, y, rw, _rh = row["row"]
        ok = laws.known(state, tid, law.id)
        yy = _section(r, x, y, rw, law.name.upper())
        cur = laws.get(tribe, law.id)
        head = law.text if ok else f"Il faut connaître {law.needs}."
        if ok and law.id == "base":
            reform = max(0, getattr(tribe, "base_reform_until", -1) - state.tick_count)
            if not cur:
                head += " Pas encore choisie."
            elif reform:
                head += f" Réforme en cours : encore {reform} semaines sans l'avantage de la base."
            else:
                head += f" Changer : {numbers.REFORM_PRESTIGE} de prestige, trois ans sans l'avantage, une fois tous les 30 ans."
        screen.blit(r.tiny.render(theme.fit(r.tiny, head, rw), True, SOFT if ok else NOTE), (x, yy))
        for opt in law.options:
            rects = row["cards"][opt.id]
            cx, cy, cw, ch = rects["card"]
            mine = ok and cur == opt.id
            why = laws.block(state, tid, law.id, opt.id) if ok else f"Il faut connaître {law.needs}"
            if mine:
                top, bot, edge = (78, 58, 30), (52, 38, 21), C.ocre_jaune
            elif ok and not why:
                top, bot, edge = (32, 58, 54), (20, 38, 35), C.savoir
            else:
                top, bot, edge = (36, 28, 22), (26, 20, 16), C.bois
            screen.blit(_gradient_card(cw, ch, top, bot, 8), (cx, cy))
            pygame.draw.rect(screen, edge, rects["card"], 2 if mine else 1, border_radius=8)
            tx = cx + 12
            if law.id == "base":
                big = theme.font("chiffre_grand").render(opt.id, True, edge)
                screen.blit(big, (cx + 12, cy + 8))
                tx = cx + 16 + big.get_width()
            theme.text(screen, opt.name, "petit_gras", C.os if ok else C.lin, (tx, cy + 6), cx + cw - tx - 8)
            lines = theme.wrap(r.tiny, opt.text, cx + cw - tx - 10)
            if law.id == "base":
                eff = tech.effect_lines(tech.math_effect(f"base:{opt.id}"))
            else:
                eff = []
            ly = cy + 28
            for part in lines:
                if ly + 15 > rects["btn"][1] - 2:
                    break
                screen.blit(r.tiny.render(part, True, INK if ok else NOTE), (tx, ly))
                ly += 15
            for e in eff[:2]:
                if ly + 15 > rects["btn"][1]:
                    break
                screen.blit(r.tiny.render(theme.fit(r.tiny, e, cx + cw - tx - 10), True, GREEN), (tx, ly))
                ly += 15
            btn = rects["btn"]
            hover = _hover(btn, mx, my)
            if mine:
                label, on = "Votre loi", False
            elif pending == (law.id, opt.id) and not why:
                label, on = "Confirmer", True
            else:
                label, on = ("Adopter" if law.id != "base" or not cur else "Réformer"), ok and not why
            theme.button(screen, btn, label, "principal" if pending == (law.id, opt.id) and on else "second", on, hover and on, active=mine)
            if hover and why and not mine:
                tips.append(([(why, C.alerte)], btn))
            elif hover and on:
                hint = "Un second clic confirme : la base est presque définitive." if law.id == "base" else "La loi change tout de suite."
                tips.append(([(opt.name, C.os, "petit_gras"), (opt.text, C.lin)] + [(e, GREEN) for e in eff] + [(hint, C.cendre)], btn))
    for lines, avoid in tips:
        _tip(r, lines, mx, my, avoid)
