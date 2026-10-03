"""Les batailles EN COURS a l'ecran (battle.py), charte « Feu et ocre ».

  LA DALLE : au centre, sous les situations, la bataille du joueur jour
  apres jour : les deux camps (combattants, morts, blesses, moral, general),
  ce qu'a fait le dernier jour (et la fortune de chacun), un bouton « Se
  replier » (un ordre : commands "battle_retreat") et « Voir ».
  LA CARTE : des epees qui battent sur chaque bataille que l'on voit.

Dessiner ne touche jamais a la partie (test_ui_pure).
"""

from __future__ import annotations

import pygame

from src.kora import battle, theme
from src.kora.peoples import color_of
from src.kora.theme import C
from src.kora.battle import fighters_now
from src.kora.vision import is_visible

PANEL_W, PANEL_H = 600, 262


def mine(state) -> list:
    """Les batailles en cours du joueur, la plus ancienne d'abord."""
    me = state.viewer
    out = []
    for bt in battle.battles(state):
        if bt.outcome:
            continue
        tids = {state.bands[b].tribe_id for b in bt.attackers + bt.defenders if b in state.bands}
        if me in tids:
            out.append(bt)
    return sorted(out, key=lambda b: b.uid)


def layout(width: int, height: int) -> dict:
    from src.kora.render import HUD_HEIGHT, TAB_W

    bw = min(PANEL_W, width - TAB_W - 40)
    bx = (width - TAB_W - bw) // 2
    by = HUD_HEIGHT + 52
    return {
        "box": (bx, by, bw, PANEL_H),
        "retreat": (bx + bw - 190, by + PANEL_H - 42, 170, 30),
        "see": (bx + bw - 290, by + PANEL_H - 42, 90, 30),
    }


def hit(lay: dict, mx: int, my: int):
    if not lay:
        return None
    for key in ("retreat", "see"):
        x, y, w, h = lay[key]
        if x <= mx <= x + w and y <= my <= y + h:
            return key
    x, y, w, h = lay["box"]
    if x <= mx <= x + w and y <= my <= y + h:
        return "box"
    return None


def _hover(rect) -> bool:
    mx, my = pygame.mouse.get_pos()
    x, y, w, h = rect
    return x <= mx <= x + w and y <= my <= y + h


def _sides(state, bt):
    """(mon camp, l'autre) : (bandes, est-ce l'attaquant)."""
    me = state.viewer
    att = [state.bands[b] for b in bt.attackers if b in state.bands]
    dfd = [state.bands[b] for b in bt.defenders if b in state.bands]
    if any(b.tribe_id == me for b in att):
        return (att, True), (dfd, False)
    return (dfd, False), (att, True)


def _column(r, state, bt, x, y, w, bands, attacker, mine_side) -> None:
    main = bands[0] if bands else None
    tribe = state.tribes.get(main.tribe_id) if main is not None else None
    col = color_of(tribe) if tribe is not None else C.cendre
    pygame.draw.polygon(r.screen, col, theme.chamfer((x, y + 2, 6, 22), 1))
    who = "Vous" if mine_side else (tribe.name if tribe else "?")
    role = "attaquent" if attacker else "défendent"
    theme.text(r.screen, f"{who} {role}", "h3", C.os, (x + 14, y), w - 14)
    fighters = sum(fighters_now(b, attacker) for b in bands if b.population > 0)
    start = bt.start_a if attacker else bt.start_d
    killed = sum(bt.killed.get(b.id, 0) for b in bands)
    hurt = sum(b.wounded for b in bands)
    key = "a" if attacker else "d"
    fled = sum(d.get("r" + key, 0) for d in bt.days)
    general = bt.general_a if attacker else bt.general_d
    morale = bt.morale_a if attacker else bt.morale_d
    yy = y + 26
    theme.text(r.screen, f"{round(fighters)} combattants sur {round(start)}", "petit", C.lin, (x, yy), w)
    theme.bar(r.screen, (x, yy + 20, w, 8), fighters / max(1.0, start), col)
    yy += 32
    theme.text(r.screen, f"{killed} morts  ·  {hurt} blessés" + (f"  ·  {fled} ont fui" if fled else ""), "petit", C.alerte if killed else C.lin, (x, yy), w)
    yy += 20
    theme.text(r.screen, f"Général : {general[0]} ({general[1]})" if general and general[0] else "Sans général", "mini", C.cendre, (x, yy), w)
    yy += 18
    theme.text(r.screen, f"Moral {round(morale)}", "mini", C.ocre_jaune if morale >= battle.ROUT + 15 else C.mauvais, (x, yy), w)
    bar = (x + 70, yy + 4, w - 70, 8)
    theme.bar(r.screen, bar, min(1.0, morale / 100.0), C.ocre_jaune if morale >= battle.ROUT + 15 else C.mauvais)
    rx = bar[0] + int(bar[2] * battle.ROUT / 100.0)
    pygame.draw.line(r.screen, C.mauvais, (rx, bar[1] - 3), (rx, bar[1] + bar[3] + 3), 2)


def draw(r, state) -> None:
    r.battle_hits = {}
    live = mine(state)
    if not live:
        return
    bt = live[0]
    w, h = r.screen.get_size()
    lay = layout(w, h)
    r.battle_hits = dict(lay, uid=bt.uid)
    bx, by, bw, bh = lay["box"]
    t = pygame.time.get_ticks() / 1000.0
    theme.glow(r.screen, lay["box"], C.mauvais, 0.25 + 0.4 * theme.pulse(t))
    theme.panel(r.screen, lay["box"], "pierre")
    r.screen.blit(theme.medallion("combat", 18, "danger"), (bx + 14, by + 12))
    place = battle.place_of(state, bt.hex)
    theme.text(r.screen, f"Bataille {place}".strip(), "h2", C.os, (bx + 60, by + 10), bw - 260)
    n = bt.day + 1
    chip = f"{n}{'er' if n == 1 else 'e'} jour de bataille  ·  le temps passe en jours"
    theme.chip(r.screen, bx + 60, by + 38, chip, C.braise, "sablier")
    if len(live) > 1:
        theme.chip(r.screen, bx + bw - 150, by + 14, f"{len(live)} batailles", C.alerte)
    (mine_bands, mine_att), (their_bands, their_att) = _sides(state, bt)
    colw = (bw - 72) // 2
    _column(r, state, bt, bx + 24, by + 64, colw, mine_bands, mine_att, True)
    _column(r, state, bt, bx + 48 + colw, by + 64, colw, their_bands, their_att, False)
    if bt.days:
        d = bt.days[-1]
        me_key, them_key = ("a", "d") if mine_att else ("d", "a")
        line = (f"Jour {bt.day} : vous {d['k' + me_key]} morts, {d['w' + me_key]} blessés · eux {d['k' + them_key]} morts, "
                f"{d['w' + them_key]} blessés · fortune {d['f' + me_key]:.2f} / {d['f' + them_key]:.2f}").replace(".", ",")
        theme.text(r.screen, line, "mini", C.lin, (bx + 24, by + bh - 70), bw - 48)
    mine_tid = state.viewer
    side_key = "a" if mine_att else "d"
    village_def = (not mine_att) and any(b.village for b in mine_bands)
    if bt.retreat == side_key:
        theme.chip(r.screen, lay["retreat"][0], lay["retreat"][1] + 6, "Repli à la fin du jour", C.alerte)
    elif village_def:
        theme.text(r.screen, "Un village ne se replie pas : il tient ses murs.", "mini", C.cendre, (bx + 24, by + bh - 34), bw - 320)
    else:
        theme.button(r.screen, lay["retreat"], "Se replier", "second", True, _hover(lay["retreat"]), "pas")
    theme.button(r.screen, lay["see"], "Voir", "discret", True, _hover(lay["see"]), "voir")
    del mine_tid
    if _hover(lay["retreat"]) and bt.retreat != side_key and not village_def:
        theme.tooltip(r.screen, [("Se replier", C.os, "petit_gras"),
                                 ("Les vôtres se retirent en bon ordre à la fin du jour : moins de pertes qu'une déroute, mais la bataille est perdue.", C.lin)],
                      lay["retreat"][0], lay["retreat"][1] + 36, 340, avoid=lay["retreat"])


def draw_on_map(r, state, yaw, pitch, zoom) -> None:
    """Des epees qui battent sur chaque bataille en cours que l'on voit."""
    from src.kora.globe import hex_to_globe_screen
    from src.kora.render import HUD_HEIGHT, view_params
    w, h = r.screen.get_size()
    gcx, gcy, focal, dist = view_params(zoom, w, h, HUD_HEIGHT)
    t = pygame.time.get_ticks() / 1000.0
    me = state.viewer
    for bt in battle.battles(state):
        if bt.outcome:
            continue
        tids = {state.bands[b].tribe_id for b in bt.attackers + bt.defenders if b in state.bands}
        if me not in tids and not is_visible(state, bt.hex, me):
            continue
        pos = hex_to_globe_screen(bt.hex, state.world, yaw, pitch, gcx, gcy, focal, dist)
        if pos is None:
            continue
        x, y = int(pos[0]), int(pos[1]) - 22
        if not (0 <= x <= w and HUD_HEIGHT <= y <= h):
            continue
        size = int(14 + 4 * theme.pulse(t * 1.6))
        med = theme.medallion("combat", size, "danger")
        r.screen.blit(med, (x - med.get_width() // 2, y - med.get_height() // 2))
