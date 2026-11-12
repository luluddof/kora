"""L'ONGLET DECISIONS, un grand ecran (touche D ; la maquette A, "le
registre", qu'il a choisie le 2026-11-10) ; decisions.py en donne le
contenu.
  - en haut, les filtres : toutes, possibles, il manque, en repos ;
  - a gauche, LA LISTE par familles (les vivres, le peuple et ses chefs, le
    sacre, les voisins, les grands desseins) : chaque decision, son icone,
    ce qui manque, son etat (Possible, Il manque 2, En repos : 3 ans) ;
  - a droite, LA FICHE de la decision choisie : son texte, CE QU'IL FAUT
    (coche ou croix, avec les chiffres du peuple), la CIBLE (un village, une
    route, un peuple : les fleches pour changer), CE QUE CA COUTE, CE QUE CA
    FAIT, le bouton Decider.
La mise en page est faite au dessin (r.decisions_hits) ; decisions_hit la
lit. Le contenu est calcule une fois par semaine de jeu (et quand la cible
change), pas a chaque image. Tout changement passe par commands.py
("decide").
"""

from __future__ import annotations

import pygame

from src.kora import decisions, places, sites, theme
from src.kora.layout import HUD_HEIGHT
from src.kora.log import season_fr
from src.kora.render_tech import GOLD, INK, NOTE, SOFT
from src.kora.render_village import _fonts, _frame, _hover, _section, _tip
from src.kora.theme import C

LIST_W = 470
FILTERS = (("toutes", "Toutes"), ("possible", "Possibles"), ("manque", "Il manque"), ("repos", "En repos"))
COLORS = {"possible": C.bon, "manque": C.cendre, "repos": C.ocre}


def decisions_hit(lay: dict, mx: int, my: int):
    if not lay:
        return None
    if _hover(lay["close"], mx, my):
        return "dclose"
    for key, rect in lay.get("buttons", {}).items():
        if _hover(rect, mx, my):
            return key
    if _hover(lay["box"], mx, my):
        return "panel"
    return None


def _box(width: int, height: int) -> tuple:
    bx = 12
    by = HUD_HEIGHT + 6
    return (bx, by, max(760, width - 66 - 24), max(480, height - HUD_HEIGHT - 14))


def target_of(state, ui, did: str):
    """La cible choisie pour cette decision (ui["dec_target"]), ou la
    premiere possible."""
    want = (ui.get("dec_target") or {}).get(did)
    return decisions.pick_target(state, state.viewer, did, want)


def cycle_target(state, ui, did: str, step: int) -> None:
    """Les fleches de la cible : la suivante, la precedente."""
    options = decisions.targets_of(state, state.viewer, did)
    if not options:
        return
    now = target_of(state, ui, did)
    i = options.index(now) if now in options else 0
    ui.setdefault("dec_target", {})[did] = options[(i + step) % len(options)]


def _rows(r, state, ui) -> dict:
    """did -> la fiche (etat, conditions, cout, effets, cible...), calculee
    une fois par semaine et par choix de cibles."""
    me = state.viewer
    chosen = tuple(sorted((ui.get("dec_target") or {}).items(), key=lambda kv: kv[0]))
    key = (state.tick_count, me, chosen, id(state))
    cache = getattr(r, "_decisions_cache", None)
    if cache is not None and cache[0] == key:
        return cache[1]
    out = {}
    for did, d in decisions.DECISIONS.items():
        target = target_of(state, ui, did)
        status, label = decisions.status(state, me, did, target)
        targets = decisions.targets_of(state, me, did) if d.targets is not None else []
        out[did] = {
            "status": status,
            "label": label,
            "needs": decisions.needs(state, me, did, target),
            "cost": d.cost(state, me, target),
            "effects": d.effects(state, me, target),
            "target": target,
            "targets": len(targets),
            "index": targets.index(target) + 1 if target in targets else 0,
            "target_name": d.target_name(state, me, target) if d.target_name is not None and target is not None else "",
        }
    r._decisions_cache = (key, out)
    return out


def decisions_ready(r, state, ui) -> bool:
    """L'onglet vient avec le premier village, ou une decision possible."""
    if sites.of_tribe(state, state.viewer, "village"):
        return True
    return possible_count(r, state, ui) > 0


def decisions_alert(r, state, ui) -> bool:
    """L'onglet respire : la soudure est la (rationner, acheter, piller...)."""
    rows = _rows(r, state, ui)
    return rows["rationner"]["status"] == "possible"


def possible_count(r, state, ui) -> int:
    return sum(1 for row in _rows(r, state, ui).values() if row["status"] == "possible")


def _pill(surf, x, y, text, color, right=False) -> int:
    """Une pastille d'etat (pierre taillee), alignee a droite si right."""
    f = theme.font("mini_gras")
    w = f.size(text)[0] + 14
    h = f.get_height() + 4
    if right:
        x -= w
    poly = theme.chamfer((x, y, w, h), 3)
    pygame.draw.polygon(surf, theme._mix(C.charbon, color, 0.22), poly)
    pygame.draw.polygon(surf, color, poly, 1)
    surf.blit(f.render(text, True, theme._mix(color, C.os, 0.35)), (x + 7, y + 2))
    return w


def _mark(surf, x, y, ok: bool) -> None:
    """Une coche verte, ou une croix rouge (les glyphes ne s'affichent pas)."""
    if ok:
        pygame.draw.lines(surf, C.bon, False, [(x - 5, y), (x - 1, y + 4), (x + 6, y - 4)], 2)
    else:
        pygame.draw.line(surf, C.mauvais, (x - 4, y - 4), (x + 4, y + 4), 2)
        pygame.draw.line(surf, C.mauvais, (x + 4, y - 4), (x - 4, y + 4), 2)


def _shown(rows: dict, flt: str) -> list:
    return [did for did in decisions.DECISIONS if flt == "toutes" or rows[did]["status"] == flt]


def draw_decisions(r, state, ui) -> None:
    me = state.viewer
    tribe = state.tribes.get(me)
    if tribe is None:
        r.decisions_hits = {}
        return
    screen = r.screen
    w, h = screen.get_size()
    box = _box(w, h)
    bx, by, bw, bh = box
    close = (bx + bw - 24 - 136, by + 16, 136, 28)
    lay = {"box": box, "close": close, "buttons": {}}
    r.decisions_hits = lay
    mx, my = pygame.mouse.get_pos()
    title_font, _head = _fonts(r)
    _frame(r, box)
    rows = _rows(r, state, ui)
    pygame.draw.rect(screen, C.ocre_jaune, (bx + 22, by + 18, 6, 34), border_radius=2)
    screen.blit(title_font.render("Décisions", True, GOLD), (bx + 36, by + 12))
    homes = sites.of_tribe(state, me, "village")
    where = f" · {places.name(homes[0])}" if homes else ""
    sub = f"{tribe.name}{where} · an {state.clock.year}, {season_fr(state.world.hex_season(homes[0].hex) if homes else state.clock.season()).lower()} · prestige {tribe.prestige}  ·  [D]"
    theme.text(screen, sub, "mini", NOTE, (bx + 38, by + 42))
    theme.button(screen, close, "Fermer [Échap]", "second", True, _hover(close, mx, my))
    tips: list = []
    # --- les filtres -------------------------------------------------------------------
    flt = ui.get("dec_filter", "toutes")
    counts = {k: sum(1 for row in rows.values() if row["status"] == k) for k in ("possible", "manque", "repos")}
    fx = bx + 260
    for key, label in FILTERS:
        text = f"{label} ({len(rows) if key == 'toutes' else counts[key]})"
        fw = theme.font("mini_gras").size(text)[0] + 26
        rect = (fx, by + 18, fw, 28)
        if fx + fw > close[0] - 12:
            break
        lay["buttons"][f"dfilt:{key}"] = rect
        theme.button(screen, rect, text, "principal" if key == flt else "second", True, _hover(rect, mx, my), role="mini_gras")
        fx += fw + 8
    # --- a gauche : la liste par familles ------------------------------------------------
    shown = _shown(rows, flt)
    pick = ui.get("dec_pick")
    if pick not in shown:
        pick = next((d for d in shown if rows[d]["status"] == "possible"), shown[0] if shown else None)
        ui["dec_pick"] = pick
    lx, ly = bx + 22, by + 78
    lh = by + bh - 16 - ly
    theme.panel(screen, (lx, ly, LIST_W, lh), "infobulle")
    families = [f for f in decisions.FAMILIES if any(decisions.DECISIONS[d].family == f for d in shown)]
    # Les rangees se serrent si la fenetre est basse.
    row_h = max(30, min(48, (lh - 16 - 24 * len(families)) // max(1, len(shown))))
    sub_line = row_h >= 40
    y = ly + 10
    if not shown:
        theme.text(screen, "Aucune décision ici.", "petit", NOTE, (lx + 16, y + 4))
    for fam in families:
        theme.text(screen, fam.upper(), "mini_gras", C.ocre, (lx + 16, y))
        y += 24
        for did in shown:
            d = decisions.DECISIONS[did]
            if d.family != fam:
                continue
            row = rows[did]
            rect = (lx + 8, y, LIST_W - 16, row_h - 4)
            lay["buttons"][f"dpick:{did}"] = rect
            if did == pick:
                theme.panel(screen, rect, "carte_choisie")
            elif _hover(rect, mx, my):
                theme.panel(screen, rect, "carte_survol")
            on = row["status"] == "possible"
            rad = 15 if sub_line else 11
            screen.blit(theme.medallion(d.icon, rad, "actif" if on else "eteint"), (lx + 16, y + (row_h - 4) // 2 - rad - 2))
            pill_w = theme.font("mini_gras").size(row["label"])[0] + 14
            name_w = LIST_W - 74 - pill_w - 20
            theme.text(screen, d.name, "petit_gras", C.os if on else C.lin, (lx + 58, y + (4 if sub_line else (row_h - 26) // 2)), name_w)
            if sub_line:
                missing = [c for c, ok in row["needs"] if not ok]
                line = ", ".join(missing) if missing else (row["target_name"] or (row["effects"][0] if row["effects"] else ""))
                theme.text(screen, line, "mini", C.cendre, (lx + 58, y + 24), LIST_W - 90)
            _pill(screen, lx + LIST_W - 20, y + (4 if sub_line else (row_h - 24) // 2), row["label"], COLORS[row["status"]], right=True)
            y += row_h
    # --- a droite : la fiche ---------------------------------------------------------------
    dx = lx + LIST_W + 18
    dw = bx + bw - 22 - dx
    if pick is not None:
        _detail(r, state, ui, pick, rows[pick], (dx, ly, dw, lh), lay, mx, my, tips)
    for tip in tips:
        _tip(r, *tip)


def _detail(r, state, ui, did, row, rect, lay, mx, my, tips) -> None:
    screen = r.screen
    d = decisions.DECISIONS[did]
    x, y, w, h = rect
    theme.panel(screen, rect, "carte")
    on = row["status"] == "possible"
    screen.blit(theme.medallion(d.icon, 26, "actif" if on else "normal"), (x + 18, y + 16))
    theme.title(screen, theme.fit(theme.font("h2"), d.name, w - 110), x + 84, y + 18, "h2")
    _pill(screen, x + 86, y + 54, row["label"], COLORS[row["status"]])
    yy = y + 88
    for line in theme.wrap(theme.font("petit"), d.text, w - 44):
        theme.text(screen, line, "petit", C.lin, (x + 22, yy))
        yy += 22
    yy += 12
    bottom = y + h - 64
    theme.text(screen, "CE QU'IL FAUT", "mini_gras", C.ocre, (x + 22, yy))
    yy += 24
    for cond, ok in row["needs"]:
        if yy > bottom - 60:
            break
        _mark(screen, x + 32, yy + 9, ok)
        for i, line in enumerate(theme.wrap(theme.font("petit"), cond, w - 70)[:2]):
            theme.text(screen, line, "petit", C.lin if ok else C.cendre, (x + 48, yy))
            yy += 22
        yy += 4
    # La cible : un village, une route, un peuple.
    if d.targets is not None:
        yy += 8
        theme.text(screen, "LA CIBLE", "mini_gras", C.ocre, (x + 22, yy))
        yy += 24
        if row["targets"]:
            prev = (x + 22, yy, 30, 26)
            nxt = (x + w - 52, yy, 30, 26)
            lay["buttons"][f"dtarget:{did}:-1"] = prev
            lay["buttons"][f"dtarget:{did}:1"] = nxt
            theme.button(screen, prev, "‹", "second", row["targets"] > 1, _hover(prev, mx, my), role="bouton_petit")
            theme.button(screen, nxt, "›", "second", row["targets"] > 1, _hover(nxt, mx, my), role="bouton_petit")
            label = f"{row['target_name']}  ({row['index']}/{row['targets']})"
            theme.text(screen, label, "petit_gras", INK, (x + 62, yy + 3), w - 124)
            if _hover(prev, mx, my) or _hover(nxt, mx, my):
                tips.append(([("Changer de cible", SOFT)], mx, my, nxt))
        else:
            theme.text(screen, "Aucune cible possible pour l'instant.", "petit", C.cendre, (x + 22, yy + 3))
        yy += 36
    yy += 6
    theme.text(screen, "CE QUE ÇA COÛTE", "mini_gras", C.ocre, (x + 22, yy))
    yy += 22
    for line in theme.wrap(theme.font("petit"), row["cost"], w - 44)[:3]:
        theme.text(screen, line, "petit", C.lin, (x + 22, yy))
        yy += 22
    yy += 12
    theme.text(screen, "CE QUE ÇA FAIT", "mini_gras", C.ocre, (x + 22, yy))
    yy += 24
    for e in row["effects"]:
        if yy > bottom - 24:
            break
        theme.text(screen, "› " + e, "petit", C.bon, (x + 30, yy), w - 52)
        yy += 24
    if d.repose_years and yy < bottom - 20:
        yy += 6
        theme.text(screen, f"Ensuite, on ne la reprend pas avant {d.repose_years} an{'s' if d.repose_years > 1 else ''}.", "mini", NOTE, (x + 22, yy), w - 44)
        yy += 20
    if yy < bottom - 4:
        theme.text(screen, "Les autres peuples prennent aussi leurs décisions, quand elles leur vont.", "mini", C.cendre, (x + 22, yy), w - 44)
    btn = (x + w - 230, y + h - 54, 208, 36)
    lay["buttons"][f"ddecide:{did}"] = btn
    theme.button(screen, btn, "Décider" if on else row["label"], "principal" if on else "second", on, _hover(btn, mx, my))
    if not on and _hover(btn, mx, my):
        missing = [(c, SOFT) for c, ok in row["needs"] if not ok]
        if missing:
            tips.append(([("Il manque :", INK)] + missing, mx, my, btn))
