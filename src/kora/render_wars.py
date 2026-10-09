"""L'ECRAN DES GUERRES (touche W, onglet Guerres) : wars.py en donne le
contenu.
  - a gauche, VOS GUERRES (une carte par pays ennemi : depuis quand,
    l'avantage, les buts), puis les guerres AILLEURS dans le monde ;
  - a droite, la guerre choisie : qui l'a declaree, la barre de
    l'AVANTAGE (et ce qui le fait), les buts, les deux CAMPS, les troupes
    EN CAMPAGNE (les leurs : celles que vous voyez), les SIEGES, les
    derniers COMBATS ; en bas, exiger leur soumission, proposer une treve,
    leur fiche (Peuples).
La mise en page est faite au dessin (r.wars_hits) ; wars_hit la lit.
Tout changement passe par commands.py ("diplo").
"""

from __future__ import annotations

import pygame

from src.kora import diplo, places, siege, theme, wars
from src.kora.layout import HUD_HEIGHT
from src.kora.look import country_color
from src.kora.render_tech import GOLD, INK, NOTE, SOFT
from src.kora.render_village import _fonts, _frame, _hover, _section, _tip
from src.kora.theme import C, _gradient_card

LIST_W = 340
CARD_H = 70
ROW_H = 22
MAX_ROWS = 5


def wars_hit(lay: dict, mx: int, my: int):
    if not lay:
        return None
    if _hover(lay["close"], mx, my):
        return "wclose"
    for key, rect in lay.get("buttons", {}).items():
        if _hover(rect, mx, my):
            return key
    if _hover(lay["box"], mx, my):
        return "panel"
    return None


def _signed(v: float) -> str:
    return f"{'+' if v > 0 else ''}{v:.0f}"


def _tone(v: float):
    return C.bon if v > 5 else C.mauvais if v < -5 else C.lin


def _name(state, tid: int) -> str:
    t = state.tribes.get(tid)
    return t.name if t is not None else "?"


def _box(width: int, height: int) -> tuple:
    bx = 12
    by = HUD_HEIGHT + 6
    return (bx, by, max(760, width - 66 - 24), max(480, height - HUD_HEIGHT - 14))


def _declared(state, me: int, front) -> str:
    who = front.declared_by
    if who == me:
        return "vous la leur avez déclarée"
    if who in front.their_side:
        return f"les {_name(state, who)} vous l'ont déclarée"
    if who:
        return f"déclarée par les {_name(state, who)}"
    return ""


def draw_wars(r, state, ui) -> None:
    me = state.viewer
    tribe = state.tribes.get(me)
    if tribe is None:
        r.wars_hits = {}
        return
    screen = r.screen
    w, h = screen.get_size()
    box = _box(w, h)
    bx, by, bw, bh = box
    close = (bx + bw - 24 - 136, by + 16, 136, 28)
    lay = {"box": box, "close": close, "buttons": {}}
    r.wars_hits = lay
    mx, my = pygame.mouse.get_pos()
    title_font, _head = _fonts(r)
    _frame(r, box)
    fronts = wars.fronts(state, me)
    others = wars.others(state, me)
    pygame.draw.rect(screen, C.mauvais if fronts else C.bois_clair, (bx + 22, by + 18, 6, 34), border_radius=2)
    screen.blit(title_font.render("Les guerres", True, GOLD), (bx + 36, by + 12))
    sub = (
        f"{len(fronts)} guerre{'s' if len(fronts) > 1 else ''} en cours" if fronts else "Vous n'êtes en guerre contre personne"
    ) + f"  ·  {len(others)} ailleurs dans le monde"
    theme.text(screen, sub, "mini", NOTE, (bx + 38, by + 42))
    theme.button(screen, close, "Fermer [Échap]", "second", True, _hover(close, mx, my))
    tips: list = []
    # --- a gauche : la liste ---------------------------------------------------------
    x, y = bx + 24, by + 74
    y = _section(r, x, y, LIST_W, "VOS GUERRES")
    keys = [f.key for f in fronts]
    pick = ui.get("war_pick")
    if pick not in keys:
        pick = keys[0] if keys else None
        ui["war_pick"] = pick
    if not fronts:
        for line in (
            "Pour déclarer une guerre : l'écran Peuples [P], sur le peuple visé.",
            "Une guerre se fait contre tout un pays : son suzerain, ses tributaires, ses confédérés.",
        ):
            theme.text(screen, line, "petit", SOFT, (x, y), LIST_W)
            y += 40
    for front in fronts:
        rect = (x, y, LIST_W, CARD_H)
        lay["buttons"][f"wpick:{front.key}"] = rect
        on = front.key == pick
        top, bot = ((78, 40, 30), (52, 26, 20)) if on else ((48, 34, 28), (32, 24, 20))
        screen.blit(_gradient_card(LIST_W, CARD_H, top, bot, 8), (x, y))
        pygame.draw.rect(screen, C.ocre_jaune if on else C.bois, rect, 2 if on else 1, border_radius=8)
        pygame.draw.rect(screen, country_color(state, front.key), (x + 8, y + 10, 5, CARD_H - 20), border_radius=2)
        theme.text(screen, theme.fit(theme.font("petit_gras"), f"Le pays des {_name(state, front.key)}", LIST_W - 30), "petit_gras", INK, (x + 20, y + 6))
        theme.text(screen, f"depuis {state.tick_count - front.since} sem.", "mini", NOTE, (x + 20, y + 28))
        score = front.score
        chip = f"avantage {_signed(score)}"
        theme.text(screen, chip, "mini_gras", _tone(score), (x + LIST_W - 14 - theme.font("mini_gras").size(chip)[0], y + 28))
        goal = (
            "Pour les soumettre" if front.my_goals else "Ils veulent vous soumettre" if front.their_goals else "Sans but déclaré"
        )
        theme.text(screen, goal, "mini", C.alerte if front.their_goals and not front.my_goals else SOFT, (x + 20, y + 46))
        y += CARD_H + 8
    y += 8
    y = _section(r, x, y, LIST_W, "AILLEURS DANS LE MONDE")
    if not others:
        theme.text(screen, "Aucune guerre connue entre les autres peuples.", "mini", NOTE, (x, y))
    shown = 0
    for a, b, since in others:
        if y + ROW_H > by + bh - 14:
            theme.text(screen, f"... et {len(others) - shown} autres", "mini", NOTE, (x, y))
            break
        pygame.draw.circle(screen, country_color(state, a), (x + 5, y + 9), 4)
        pygame.draw.circle(screen, country_color(state, b), (x + 15, y + 9), 4)
        line = f"{_name(state, a)} contre {_name(state, b)} · {state.tick_count - since} sem."
        theme.text(screen, theme.fit(theme.font("mini"), line, LIST_W - 28), "mini", SOFT, (x + 26, y + 1))
        y += ROW_H
        shown += 1
    # --- a droite : la guerre choisie -------------------------------------------------
    front = next((f for f in fronts if f.key == pick), None)
    dx = x + LIST_W + 28
    dw = bx + bw - 24 - dx
    if front is None:
        theme.text(screen, "Choisissez une guerre à gauche.", "petit", NOTE, (dx, by + 80))
        for tip in tips:
            _tip(r, *tip)
        return
    _draw_front(r, state, me, front, (dx, by + 74, dw, by + bh - 14 - (by + 74)), lay, mx, my, tips)
    for tip in tips:
        _tip(r, *tip)


def _draw_front(r, state, me, front, area, lay, mx, my, tips) -> None:
    screen = r.screen
    x, y, w, h = area
    bottom = y + h
    head = f"Contre le pays des {_name(state, front.key)}"
    theme.text(screen, head, "h3", INK, (x, y - 4))
    info = f"depuis {state.tick_count - front.since} semaines"
    told = _declared(state, me, front)
    if told:
        info += f"  ·  {told}"
    theme.text(screen, info, "mini", NOTE, (x, y + 24))
    y += 48
    # L'avantage : une barre de -100 a +100.
    score = front.score
    bar = (x, y + 4, w, 14)
    pygame.draw.rect(screen, C.cuir, bar, border_radius=7)
    mid = x + w // 2
    span = (w // 2) * min(1.0, abs(score) / diplo.SCORE_CAP)
    fill = (mid, bar[1], span, bar[3]) if score >= 0 else (mid - span, bar[1], span, bar[3])
    if span >= 1:
        pygame.draw.rect(screen, _tone(score), fill, border_radius=7)
    pygame.draw.line(screen, C.os, (mid, bar[1] - 3), (mid, bar[1] + bar[3] + 3), 2)
    pygame.draw.rect(screen, C.bois_clair, bar, 1, border_radius=7)
    lay["buttons"]["wscore"] = bar
    y += 24
    per = "  ·  ".join(f"{_name(state, e)} {_signed(v)}" for e, v in sorted(front.scores.items()) if v)
    theme.text(screen, f"Votre avantage : {_signed(score)}" + (f"  ({per})" if per and len(front.scores) > 1 else ""), "petit_gras", _tone(score), (x, y))
    theme.text(screen, theme.fit(theme.font("mini"), wars.score_text(), w), "mini", NOTE, (x, y + 22))
    if _hover(bar, mx, my):
        tips.append(([("L'avantage dans la guerre", INK), (wars.score_text(), SOFT), ("Il décide s'ils acceptent de se soumettre.", NOTE)], mx, my, bar))
    y += 44
    # Les buts.
    goals = []
    if front.my_goals:
        goals.append(("Votre but : soumettre les " + ", ".join(_name(state, t) for t in front.my_goals) + " (prendre leur village, ou exiger leur soumission)", C.lin))
    if front.their_goals:
        goals.append(("Leur but : vous soumettre (" + ", ".join(_name(state, t) for t in front.their_goals) + ")", C.alerte))
    if not goals:
        goals.append(("Ni vous ni eux n'avez déclaré de but : la guerre finira par une trêve, ou s'éteindra sans combat.", NOTE))
    for text, col in goals:
        theme.text(screen, text, "mini", col, (x, y), w)
        y += 18
    y += 8
    # Les deux camps.
    half = (w - 20) // 2
    for cx, title, side in ((x, "VOTRE CAMP", front.my_side), (x + half + 20, "LEUR CAMP", front.their_side)):
        yy = _section(r, cx, y, half, title)
        for tid in side[:MAX_ROWS]:
            pygame.draw.circle(screen, country_color(state, tid), (cx + 6, yy + 9), 5)
            label = _name(state, tid) + (" (vous)" if tid == me else "")
            theme.text(screen, theme.fit(theme.font("mini"), label, half - 90), "mini", INK if tid == me else SOFT, (cx + 18, yy + 1))
            power = f"force {diplo.power(state, tid):.0f}"
            theme.text(screen, power, "mini", NOTE, (cx + half - theme.font("mini").size(power)[0], yy + 1))
            yy += ROW_H
        if len(side) > MAX_ROWS:
            theme.text(screen, f"... et {len(side) - MAX_ROWS} autres", "mini", NOTE, (cx + 18, yy + 1))
    y += 24 + ROW_H * (min(MAX_ROWS, max(len(front.my_side), len(front.their_side))) + (1 if max(len(front.my_side), len(front.their_side)) > MAX_ROWS else 0)) + 8
    # Les troupes en campagne.
    y = _section(r, x, y, w, "EN CAMPAGNE")
    if not front.armies:
        theme.text(screen, "Aucune troupe levée, ni chez vous ni chez eux (de ce que vous voyez).", "mini", NOTE, (x, y))
        y += ROW_H
    for band, side, doing in front.armies[:MAX_ROWS]:
        col = C.bon if side == "nous" else C.mauvais
        pygame.draw.circle(screen, country_color(state, band.tribe_id), (x + 6, y + 9), 5)
        lead = band.leader.name if band.leader is not None else "?"
        text = f"{_name(state, band.tribe_id)} · {band.population} guerriers · {lead} · {doing}"
        theme.text(screen, theme.fit(theme.font("mini"), text, w - 90), "mini", col if side == "eux" else INK, (x + 18, y + 1))
        see = (x + w - 60, y - 1, 60, 20)
        lay["buttons"][f"wsee:{band.id}"] = see
        theme.button(screen, see, "Voir", "second", True, _hover(see, mx, my), role="bouton_petit")
        y += ROW_H
    if len(front.armies) > MAX_ROWS:
        theme.text(screen, f"... et {len(front.armies) - MAX_ROWS} autres troupes", "mini", NOTE, (x + 18, y))
        y += ROW_H
    y += 8
    # Les sieges.
    if front.sieges:
        y = _section(r, x, y, w, "SIÈGES")
        for site, weeks, by in front.sieges[:3]:
            text = f"{places.name(site)} ({_name(state, site.tribe_id)}) assiégé par les {_name(state, by)} depuis {weeks} sem. · défense x{siege.erosion(weeks):.2f}".replace(".", ",")
            theme.text(screen, theme.fit(theme.font("mini"), text, w - 70), "mini", INK, (x, y + 1))
            see = (x + w - 60, y - 1, 60, 20)
            lay["buttons"][f"wsite:{site.id}"] = see
            theme.button(screen, see, "Voir", "second", True, _hover(see, mx, my), role="bouton_petit")
            y += ROW_H
        y += 8
    # Les derniers combats.
    actions_y = bottom - 74
    if y + 24 < actions_y:
        y = _section(r, x, y, w, "DERNIERS COMBATS (six mois)")
        if not front.fights:
            theme.text(screen, "Aucun combat entre vous depuis six mois.", "mini", NOTE, (x, y))
        for mark in front.fights:
            if y + ROW_H > actions_y - 6:
                break
            ours = mark.winner_tribe in front.my_side
            text = f"an {mark.year}, sem. {mark.week} · les {mark.winner_name} battent les {mark.loser_name} · pertes {mark.winner_loss} contre {mark.loser_loss}"
            theme.text(screen, theme.fit(theme.font("mini"), text, w - 70), "mini", C.bon if ours else C.mauvais, (x, y + 1))
            see = (x + w - 60, y - 1, 60, 20)
            lay["buttons"][f"whex:{mark.hex.q}:{mark.hex.r}"] = see
            theme.button(screen, see, "Voir", "second", True, _hover(see, mx, my), role="bouton_petit")
            y += ROW_H
    # Les actions.
    pygame.draw.line(screen, C.bois, (x, actions_y - 8), (x + w, actions_y - 8))
    target = front.target
    bw3 = (w - 24) // 3
    acts = (
        ("soumission", f"Exiger la soumission des {_name(state, target)}", target),
        ("treve", f"Proposer une trêve aux {_name(state, front.key)}", front.key),
        ("fiche", "Leur fiche (Peuples)", front.key),
    )
    for i, (key, label, tid) in enumerate(acts):
        rect = (x + i * (bw3 + 12), actions_y, bw3, 32)
        lay["buttons"][f"wact:{key}:{tid}"] = rect
        if key == "fiche":
            theme.button(screen, rect, label, "second", True, _hover(rect, mx, my), role="bouton_petit")
            continue
        verdict = diplo.evaluate(state, me, tid, key)
        wait = diplo.on_cooldown(state, me, tid, key)
        on = not verdict.blocked and not wait
        theme.button(screen, rect, theme.fit(theme.font("petit_gras"), label, bw3 - 16), "second", on, on and _hover(rect, mx, my), role="bouton_petit")
        if verdict.blocked:
            line, col = verdict.blocked, NOTE
        elif wait:
            line, col = f"Déjà proposé : attendez {wait} sem.", NOTE
        else:
            line, col = (f"Ils accepteraient ({_signed(verdict.score)})", C.bon) if verdict.accepted else (f"Ils refuseraient ({_signed(verdict.score)})", C.mauvais)
        theme.text(screen, theme.fit(theme.font("mini"), line, bw3), "mini", col, (rect[0], rect[1] + 36))
        if _hover(rect, mx, my) and verdict.reasons:
            rows = [(label, INK)] + [(f"{_signed(v):>4}  {text}", C.bon if v > 0 else C.mauvais if v < 0 else SOFT) for text, v in verdict.reasons]
            rows.append((f"Total : {_signed(verdict.score)} (il faut plus de 0)", INK))
            tips.append((rows, mx, my, rect))
