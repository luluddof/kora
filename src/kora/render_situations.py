"""Les situations a l'ecran (situations.py), dans la charte « Feu et ocre ».

  LE BANDEAU : DANS la barre du haut, entre la date et le temps, un petit
  medaillon par situation du joueur (rouge : une crise, braise : une
  conjoncture), sa jauge en anneau, une pastille avec les mois qui restent ;
  le nom et le detail au survol. Une situation finie y reste quelques
  semaines, eteinte. Un clic ouvre sa fenetre.
  LA FENETRE : le recit, l'etape, la jauge de resolution (crise) ou le
  classement des peuples (conjoncture), ce qui pese, le prix, les actions
  avec leur cout et pourquoi on ne peut pas, les peuples touches.
  LA CARTE : le lieu de la situation, cercle de pointilles et medaillon.

Dessiner ne touche jamais a la partie (test_ui_pure).
"""

from __future__ import annotations

import pygame

from src.kora import diplo, situations, tech, theme
from src.kora.peoples import color_of
from src.kora.situations import CRISE, SPECS
from src.kora.theme import C
from src.kora.gamestate import seen_of
from src.kora.globe import hex_to_globe_screen, view_params
from src.kora.layout import HUD_HEIGHT, TAB_W, hud_layout

# Une case du bandeau (dans la barre du haut).
CARD_W, CARD_H = 40, 40
# Une situation finie reste au bandeau ce nombre de semaines.
RECENT = 8
# Une situation nouvelle brille ce nombre de semaines.
NEW = 4
OUTCOME = {"resolue": "Surmontée", "ratee": "Ratée", "finie": "Finie", "gagnee": "Gagnée"}


def _hover(rect) -> bool:
    mx, my = pygame.mouse.get_pos()
    x, y, w, h = rect
    return x <= mx <= x + w and y <= my <= y + h


def banner_items(state) -> list:
    """Les situations du joueur : en cours, puis finies depuis peu."""
    me = state.viewer
    out = [s for s in situations.of_tribe(state, me, ended=True) if not s.outcome or state.tick_count - s.ended <= RECENT]
    return sorted(out, key=lambda s: (bool(s.outcome), s.started, s.uid))[:5]


def banner_layout(width: int, n: int) -> dict:
    """Les medaillons, dans la barre du haut, entre la date (a gauche) et les
    boutons du temps ; s'il y en a trop, la suite passe juste dessous."""
    left = 236
    right = hud_layout(width)["pause"][0] - 12
    per_row = max(1, (right - left + 6) // (CARD_W + 6))
    out = {}
    for i in range(n):
        row, col = divmod(i, per_row)
        x = left + col * (CARD_W + 6)
        y = (HUD_HEIGHT - CARD_H) // 2 if row == 0 else HUD_HEIGHT + 4 + (row - 1) * (CARD_H + 4)
        out[i] = (x, y, CARD_W, CARD_H)
    return out


def people_name(state, tid: int) -> str:
    me = state.viewer
    tribe = state.tribes.get(tid)
    if tid == me:
        return "Vous"
    if tribe is None:
        return "Un peuple disparu"
    if diplo.in_contact(state, me, tid) or tid in seen_of(state, me):
        return tribe.name
    return "Un peuple inconnu"


def _rank_of(inst, tid: int) -> tuple[int, int]:
    order = [t for t, _p in situations.ranking(inst)]
    return (order.index(tid) + 1 if tid in order else 0), len(order)


def _status(state, inst) -> tuple[str, tuple]:
    """La deuxieme ligne d'une dalle, et sa couleur."""
    spec = SPECS[inst.sid]
    me = state.viewer
    if inst.outcome:
        if inst.outcome == "gagnee":
            if inst.winner == me:
                return "Vous l'emportez", C.bon
            return f"Gagnée par : {people_name(state, inst.winner)}", C.ocre_jaune
        return OUTCOME.get(inst.outcome, "Finie"), C.bon if inst.outcome == "resolue" else C.cendre
    left = situations.months_left(state, inst)
    time = f"{left} mois" if left > 1 else "dernier mois"
    if spec.kind == CRISE:
        return f"Résolution {int(inst.progress)} %  ·  {time}", C.ocre_jaune if left > 2 else C.alerte
    rank, n = _rank_of(inst, me)
    place = "1er" if rank == 1 else f"{rank}e"
    return f"Vous : {place} sur {n}  ·  {time}", C.ocre_jaune if rank == 1 else C.lin


def _gauge(surf, cx: int, cy: int, radius: int, frac: float, color) -> None:
    """Une jauge en anneau autour d'un medaillon, partant du haut."""
    import math

    pygame.draw.circle(surf, C.charbon, (cx, cy), radius, 3)
    frac = max(0.0, min(1.0, frac))
    if frac <= 0:
        return
    steps = max(2, int(40 * frac))
    pts = []
    for k in range(steps + 1):
        a = -math.pi / 2 + 2 * math.pi * frac * k / steps
        pts.append((cx + radius * math.cos(a), cy + radius * math.sin(a)))
    pygame.draw.lines(surf, color, False, pts, 3)


def _frac(state, inst) -> float:
    spec = SPECS[inst.sid]
    if spec.kind == CRISE:
        return inst.progress / 100.0
    if not inst.participants:
        return 0.0
    best = max(p["score"] for p in inst.participants.values()) or 1.0
    mine = inst.participants.get(state.viewer, {}).get("score", 0.0)
    return mine / best


def _badge(r, x: int, y: int, text: str, color) -> None:
    """Une petite pastille (les mois qui restent) au coin d'un medaillon."""
    f = theme.font("mini")
    w = max(16, f.size(text)[0] + 6)
    rect = (x - w, y - 14, w, 14)
    pygame.draw.rect(r.screen, C.nuit, rect, border_radius=4)
    pygame.draw.rect(r.screen, color, rect, 1, border_radius=4)
    r.screen.blit(f.render(text, True, C.os), (rect[0] + (w - f.size(text)[0]) // 2, rect[1] - 1))


def draw_banner(r, state) -> None:
    """Les medaillons : les situations du joueur, puis les crises qui le
    menacent (RISQUES, en ambre : on les voit venir) ; tout le detail au
    survol."""
    r.situation_hits = {}
    r.situation_hover = None
    items = banner_items(state)
    risks = situations.risks_of(state, state.viewer)[: max(0, 8 - len(items))]
    n = len(items) + len(risks)
    if not n:
        return
    w, _h = r.screen.get_size()
    lay = banner_layout(w, n)
    t = pygame.time.get_ticks() / 1000.0
    hovered = None
    for i, inst in enumerate(items):
        spec = SPECS[inst.sid]
        rect = lay[i]
        x, y, cw, ch = rect
        cx, cy = x + cw // 2, y + ch // 2
        r.situation_hits[inst.uid] = rect
        crisis = spec.kind == CRISE
        col = C.mauvais if crisis else C.braise
        over = _hover(rect)
        if not inst.outcome and state.tick_count - inst.started <= NEW:
            pygame.draw.circle(r.screen, col, (cx, cy), 20 + int(2 * theme.pulse(t + i * 0.5)), 2)
        state_key = "eteint" if inst.outcome else ("danger" if crisis else "actif")
        med = theme.medallion(spec.icon, 14, state_key)
        r.screen.blit(med, (cx - med.get_width() // 2, cy - med.get_height() // 2))
        if not inst.outcome:
            _gauge(r.screen, cx, cy, 18, _frac(state, inst), C.bon if crisis else C.ocre_jaune)
            left = situations.months_left(state, inst)
            _badge(r, x + cw + 2, y + ch + 2, str(left), C.alerte if left <= 2 else col)
        if over:
            pygame.draw.circle(r.screen, C.os, (cx, cy), 19, 1)
            hovered = ("sit", inst, rect)
            r.situation_hover = inst.uid
    for k, (sid, text) in enumerate(risks):
        spec = SPECS[sid]
        rect = lay[len(items) + k]
        x, y, cw, ch = rect
        cx, cy = x + cw // 2, y + ch // 2
        over = _hover(rect)
        med = theme.medallion(spec.icon, 13, "connu", C.alerte)
        r.screen.blit(med, (cx - med.get_width() // 2, cy - med.get_height() // 2))
        _badge(r, x + cw + 2, y + ch + 2, "!", C.alerte)
        if over:
            pygame.draw.circle(r.screen, C.os, (cx, cy), 18, 1)
            hovered = ("risk", (spec, text), rect)
    if hovered is None:
        return
    what, obj, (x, y, cw, ch) = hovered
    if what == "sit":
        inst = obj
        spec = SPECS[inst.sid]
        kind = "Crise" if spec.kind == CRISE else "Conjoncture"
        line, lcol = _status(state, inst)
        lines = [(f"{kind} : {spec.name}", C.os, "petit_gras"), (line, lcol)]
        if not inst.outcome and spec.stages:
            lines.append((spec.stage_name(inst), C.ocre_jaune))
        lines.append((spec.goal, C.lin))
        lines.append(("Clic : ouvrir.", C.cendre, "mini"))
    else:
        spec, text = obj
        lines = [(f"Risque de crise : {spec.name}", C.alerte, "petit_gras"), (text, C.lin), (spec.about, C.cendre, "mini")]
    theme.tooltip(r.screen, lines, x, y + ch + 8, 360)


# --- la fenetre ------------------------------------------------------------------------


def window_layout(width: int, height: int, n_actions: int, story_lines: int = 3) -> dict:
    bw = min(860, width - TAB_W - 60)
    action_h = 62
    head = 112
    story = 24 * max(2, story_lines) + 14
    mid = 168
    foot = 58
    bh = min(height - 60, head + story + mid + 30 + action_h * n_actions + foot)
    bx = max(10, (width - TAB_W - bw) // 2)
    by = max(56, (height - bh) // 2)
    ay = by + bh - foot - action_h * n_actions
    actions = {i: (bx + 28, ay + i * action_h, bw - 56, action_h - 8) for i in range(n_actions)}
    close = (bx + bw - 124, by + 18, 100, 28)
    place = (bx + bw - 200, by + bh - 46, 172, 30)
    return {"box": (bx, by, bw, bh), "actions": actions, "close": close, "place": place,
            "story_y": by + head, "mid_y": by + head + story}


def _action_text(action) -> str:
    if action.progress:
        return f"+{int(action.progress)} à la résolution"
    if action.score >= 1:
        return f"+{int(action.score)} au score"
    if 0 < action.score < 1:
        return f"Score +{int(round(action.score * 100))} %"
    if action.score < 0:
        return f"Score {int(round(action.score * 100))} %"
    return ""


def _prize_lines(spec) -> tuple[str, list]:
    eff = tech.situation_effect(f"sit:{spec.id}:prix")
    if eff is None:
        return "", []
    return eff.name, tech.effect_lines(eff)


def draw_window(r, state, ui) -> None:
    uid = ui.get("situation_open")
    r.situation_open_uid = uid
    inst = situations.find(state, uid)
    if inst is None:
        r.situation_window = {}
        return
    spec = SPECS[inst.sid]
    me = state.viewer
    w, h = r.screen.get_size()
    theme.veil(r.screen, 140)
    bw0 = min(860, w - 66 - 60)
    f_story = theme.font("recit")
    story = spec.about + ("  " + spec.stage_text(inst) if spec.stages and not inst.outcome else "")
    lines = theme.wrap(f_story, story, bw0 - 64)
    lay = window_layout(w, h, len(spec.actions), len(lines))
    r.situation_window = lay
    bx, by, bw, bh = lay["box"]
    crisis = spec.kind == CRISE
    theme.panel(r.screen, lay["box"], "pierre")
    state_key = "eteint" if inst.outcome else ("danger" if crisis else "actif")
    r.screen.blit(theme.medallion(spec.icon, 40, state_key), (bx + 24, by + 20))
    if not inst.outcome:
        _gauge(r.screen, bx + 66, by + 62, 46, _frac(state, inst), C.bon if crisis else C.ocre_jaune)
    kind_col = C.mauvais if crisis else C.braise
    cx = bx + 128
    cx += theme.chip(r.screen, cx, by + 20, "CRISE" if crisis else "CONJONCTURE", kind_col) + 8
    left = situations.months_left(state, inst)
    if inst.outcome:
        line, lcol = _status(state, inst)
        theme.chip(r.screen, cx, by + 20, line, lcol)
    else:
        theme.chip(r.screen, cx, by + 20, f"Encore {left} mois" if left > 1 else "Dernier mois", C.alerte if left <= 2 else C.ocre_jaune, "sablier")
    theme.title(r.screen, spec.name, bx + 128, by + 44, "h1")
    if spec.stages and len(spec.stages) > 1:
        st_line = f"Étape {min(inst.stage, len(spec.stages) - 1) + 1} sur {len(spec.stages)} : {spec.stage_name(inst)}"
    else:
        st_line = spec.stage_name(inst)
    theme.text(r.screen, st_line, "petit", C.ocre_jaune, (bx + 128, by + 82), bw - 160)
    theme.button(r.screen, lay["close"], "Fermer", "discret", True, _hover(lay["close"]))
    yy = lay["story_y"]
    for ln in lines:
        r.screen.blit(f_story.render(ln, True, C.lin), (bx + 32, yy))
        yy += 24
    # --- le milieu : a gauche ce qui pese (ou le prix), a droite la jauge ou le classement.
    my_ = lay["mid_y"]
    half = (bw - 84) // 2
    lx, rx = bx + 32, bx + 52 + half
    theme.text(r.screen, "CE QUI PÈSE" if crisis else "LE PRIX DU PREMIER", "etiquette", C.ocre, (lx, my_))
    theme.dotted(r.screen, (lx, my_ + 20), (lx + half, my_ + 20), C.bois_clair)
    ly = my_ + 28
    if crisis:
        eff = situations.effect_lines(inst) if not inst.outcome else []
        for e in eff[:4] or ["Plus rien : la crise est derrière vous." if inst.outcome == "resolue" else "Rien de plus que ses morts."]:
            theme.text(r.screen, e, "petit", C.alerte if eff else C.lin, (lx, ly), half)
            ly += 20
        if spec.fail and not inst.outcome:
            ly += 4
            for part in theme.wrap(theme.font("mini"), spec.fail, half)[:2]:
                theme.text(r.screen, part, "mini", C.cendre, (lx, ly))
                ly += 17
        if not inst.outcome:
            theme.text(r.screen, "Surmontée : tout redevient comme avant.", "mini", C.bon, (lx, ly + 2), half)
    else:
        name, eff = _prize_lines(spec)
        theme.text(r.screen, name, "petit_gras", C.os, (lx, ly), half)
        ly += 22
        for e in eff[:3]:
            theme.text(r.screen, e, "petit", C.bon, (lx, ly), half)
            ly += 20
        theme.text(r.screen, "Seulement si plusieurs peuples y prennent part.", "mini", C.cendre, (lx, ly + 2), half)
    theme.text(r.screen, "RÉSOLUTION" if crisis else "LE CLASSEMENT", "etiquette", C.ocre, (rx, my_))
    theme.dotted(r.screen, (rx, my_ + 20), (rx + half, my_ + 20), C.bois_clair)
    ry = my_ + 30
    if crisis:
        theme.bar(r.screen, (rx, ry, half, 14), inst.progress / 100.0, C.bon)
        theme.text(r.screen, f"{int(inst.progress)} / 100", "chiffre", C.os, (rx, ry + 20))
        gy = ry + 46
        for part in theme.wrap(theme.font("mini"), spec.goal, half)[:4]:
            theme.text(r.screen, part, "mini", C.lin, (rx, gy))
            gy += 17
        if len(inst.participants) > 1:
            names = ", ".join(people_name(state, t) for t in sorted(inst.participants)[:6])
            theme.text(r.screen, f"Touchés : {names}", "mini", C.cendre, (rx, gy + 4), half)
    else:
        ranked = situations.ranking(inst)
        best = max((p["score"] for _t, p in ranked), default=0.0) or 1.0
        for k, (tid, p) in enumerate(ranked[:5]):
            colr = color_of(state.tribes.get(tid)) if tid in state.tribes else C.cendre
            pygame.draw.polygon(r.screen, colr, theme.chamfer((rx, ry + 2, 6, 16), 1))
            label = people_name(state, tid)
            mine = tid == me
            theme.text(r.screen, f"{k + 1}. {label}", "petit_gras" if mine else "petit", C.os if mine else C.lin, (rx + 12, ry), half // 2)
            theme.bar(r.screen, (rx + 12 + half // 2, ry + 5, half // 2 - 60, 9), p["score"] / best, C.ocre_jaune if k == 0 else C.ocre)
            theme.text(r.screen, str(int(p["score"])), "mini", C.lin, (rx + half - 40, ry + 1))
            ry += 22
        if len(ranked) > 5:
            theme.text(r.screen, f"… et {len(ranked) - 5} autres peuples", "mini", C.cendre, (rx + 12, ry))
            ry += 18
        for part in theme.wrap(theme.font("mini"), spec.goal, half)[:2]:
            theme.text(r.screen, part, "mini", C.cendre, (rx, ry + 4))
            ry += 17
    # --- les actions
    theme.text(r.screen, "QUE FAIRE", "etiquette", C.ocre, (bx + 32, lay["actions"][0][1] - 26) if lay["actions"] else (bx + 32, by + bh - 80))
    tip = None
    for i, action in enumerate(spec.actions):
        rect = lay["actions"][i]
        ax, ay, aw, ah = rect
        why = situations.action_block(state, inst, me, action.id)
        on = not why
        over = _hover(rect)
        theme.panel(r.screen, rect, "carte_survol" if (over and on) else ("carte" if on else "creux"))
        theme.text(r.screen, action.label, "h3", C.os if on else C.cendre, (ax + 14, ay + 6), aw // 2)
        theme.text(r.screen, action.about, "mini", C.lin if on else C.cendre, (ax + 14, ay + 31), aw - 300)
        cx2 = ax + aw - 14
        chips = []
        if action.prestige:
            chips.append((f"{action.prestige}", C.ocre_jaune, "prestige"))
        if action.vivres:
            chips.append((f"{action.vivres}", C.ocre_jaune, "vivres"))
        effect = _action_text(action)
        if effect:
            chips.append((effect, C.bon if (action.progress or action.score > 0) else C.cendre, None))
        f = theme.font("mini_gras")
        for label, col, key in chips:
            cw2 = f.size(label)[0] + 14 + (16 if key else 0)
            cx2 -= cw2
            theme.chip(r.screen, cx2, ay + 8, label, col, key)
            cx2 -= 6
        if why:
            theme.text(r.screen, why, "mini", C.alerte, (ax + aw - 280, ay + 31), 266)
        else:
            wait = action.cooldown
            theme.text(r.screen, f"Puis {wait // 4} mois avant de recommencer" if wait >= 8 else "Peut se refaire chaque mois", "mini", C.cendre, (ax + aw - 280, ay + 31), 266)
        if over:
            tip = (action, why, rect)
    # --- le pied : les peuples, le lieu
    fy = by + bh - 44
    x = bx + 32
    for tid in sorted(inst.participants)[:7]:
        colr = color_of(state.tribes.get(tid)) if tid in state.tribes else C.cendre
        x += theme.chip(r.screen, x, fy + 6, people_name(state, tid), colr) + 6
        if x > bx + bw - 260:
            break
    if inst.center is not None:
        theme.button(r.screen, lay["place"], "Voir sur la carte", "second", True, _hover(lay["place"]), "voir")
    if tip is not None:
        action, why, (ax, ay, aw, ah) = tip
        rows = [(action.label, C.os, "petit_gras"), (action.about, C.lin)]
        if why:
            rows.append((why, C.alerte))
        theme.tooltip(r.screen, rows, ax + aw // 2, ay + ah + 4, 360)


def window_hit(lay: dict, mx: int, my: int):
    """'close', 'place', ('action', i), 'box' ou None (hors de la fenetre)."""
    if not lay:
        return None

    def inside(rect):
        x, y, w, h = rect
        return x <= mx <= x + w and y <= my <= y + h

    if inside(lay["close"]):
        return "close"
    if inside(lay["place"]):
        return "place"
    for i, rect in lay["actions"].items():
        if inside(rect):
            return ("action", i)
    if inside(lay["box"]):
        return "box"
    return None


def banner_hit(hits: dict, mx: int, my: int):
    for uid, (x, y, w, h) in hits.items():
        if x <= mx <= x + w and y <= my <= y + h:
            return uid
    return None


# --- la carte ------------------------------------------------------------------------------

_RINGS: dict = {}


def _ring_hexes(world, center, radius: int) -> list:
    key = (center.q, center.r, radius, world.width, world.height)
    hit = _RINGS.get(key)
    if hit is None:
        hit = [h for h in world.hexes_in_radius(center, radius) if world.distance(h, center) == radius]
        if len(_RINGS) > 64:
            _RINGS.clear()
        _RINGS[key] = hit
    return hit


def draw_on_map(r, state, yaw, pitch, zoom) -> None:
    """Le lieu d'une situation du joueur, seulement quand on la regarde (son
    medaillon survole, ou sa fenetre ouverte) : un cercle de pointilles a son
    rayon et le medaillon au centre. Le reste du temps, la carte est libre."""
    shown = {getattr(r, "situation_hover", None), getattr(r, "situation_open_uid", None)}
    items = [s for s in situations.of_tribe(state, state.viewer) if s.center is not None and s.radius > 0 and s.uid in shown]
    if not items:
        return
    w, h = r.screen.get_size()
    gcx, gcy, focal, dist = view_params(zoom, w, h, HUD_HEIGHT)
    t = pygame.time.get_ticks() / 1000.0
    for inst in items:
        spec = SPECS[inst.sid]
        col = C.mauvais if spec.kind == CRISE else C.braise
        ring = _ring_hexes(state.world, inst.center, inst.radius)
        step = 1 if len(ring) < 90 else 2
        a = int(150 + 90 * theme.pulse(t))
        for k, hx in enumerate(ring[::step]):
            pos = hex_to_globe_screen(hx, state.world, yaw, pitch, gcx, gcy, focal, dist)
            if pos is None:
                continue
            x, y = int(pos[0]), int(pos[1])
            if x < 0 or y < HUD_HEIGHT or x > w or y > h:
                continue
            pygame.draw.circle(r.screen, C.nuit, (x, y), 4)
            pygame.draw.circle(r.screen, col if k % 2 == 0 else theme._mix(col, C.os, 0.35), (x, y), 3)
        pos = hex_to_globe_screen(inst.center, state.world, yaw, pitch, gcx, gcy, focal, dist)
        if pos is not None:
            x, y = int(pos[0]), int(pos[1])
            if 0 <= x <= w and HUD_HEIGHT <= y <= h:
                med = theme.medallion(spec.icon, 13, "danger" if spec.kind == CRISE else "actif")
                med.set_alpha(a)
                # Au-dessus du lieu, pour ne pas cacher la bande qui s'y trouve.
                lift = 26 + 30 * items.index(inst) % 60
                pygame.draw.line(r.screen, col, (x, y - 8), (x, y - lift + 14), 2)
                r.screen.blit(med, (x - med.get_width() // 2, y - lift - med.get_height() // 2))
                med.set_alpha(None)
