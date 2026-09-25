"""L'ecran Commerce (dans le style de l'ecran du village) :
  - tuiles : biens pourvus, convois, ventes, achats, balance, partenaires ;
  - a gauche, le MARCHE DU PEUPLE : chaque bien, sa reserve, ce qu'on en
    fait et en mange, son prix ici ; en dessous, le graphe des ventes et des
    achats des 24 derniers mois ;
  - au milieu, les ROUTES : sens, bien, partenaire, convois (1 a 3), ce
    qu'elles ont porte le dernier mois, fermer ;
  - a droite, OUVRIR UNE ROUTE : partenaire, bien, vendre ou acheter,
    convois, ce que la route rapporterait ; ce que le partenaire a de trop
    ou lui manque ; les peuples a qui proposer un accord.
trade_layout et trade_hit sont purs (tests) ; draw_trade dessine.
"""

from __future__ import annotations

import pygame

from src.kora import diplo, goods, tech
from src.kora.peoples import color_of
from src.kora.render import HUD_HEIGHT
from src.kora.render_tech import BAD, GOLD, GOLD_DEEP, GOLD_DIM, GOOD, INK, NOTE, SOFT, _button, _fit, _gradient_card, _wrap
from src.kora.render_village import WARN, _fonts, _frame, _hover, _section, _tile, _tip
from src.kora.sim import PLAYER_TRIBE_ID

MAX_ROUTES_SHOWN = 8
MAX_PARTNERS_SHOWN = 6
MAX_CANDIDATES = 4


def trade_layout(width: int, height: int, n_routes: int = 0, n_partners: int = 0, n_candidates: int = 0) -> dict:
    bx = 12
    by = HUD_HEIGHT + 6
    bw = max(760, width - 32 - 24)
    bh = max(480, height - HUD_HEIGHT - 14)
    close = (bx + bw - 24 - 136, by + 16, 136, 28)
    tiles_y = by + 62
    n = 6
    tw = (bw - 48 - (n - 1) * 10) // n
    tiles = [(bx + 24 + i * (tw + 10), tiles_y, tw, 56) for i in range(n)]
    body_y = tiles_y + 56 + 14
    body_h = by + bh - 14 - body_y
    inner = bw - 48
    lw = int(inner * 0.30)
    mw = int(inner * 0.37)
    rw = inner - lw - mw - 32
    left = (bx + 24, body_y, lw, body_h)
    mid = (left[0] + lw + 16, body_y, mw, body_h)
    right = (mid[0] + mw + 16, body_y, rw, body_h)
    # Marche : une rangee par bien, puis le graphe.
    goods_rows = {}
    y = body_y + 24
    for g in goods.GOODS:
        goods_rows[g] = (left[0], y, lw, 42)
        y += 48
    graph = (left[0], y + 22, lw, max(70, body_y + body_h - (y + 22) - 4))
    # Routes : une carte par route.
    routes = []
    ry = body_y + 24
    for i in range(min(n_routes, MAX_ROUTES_SHOWN)):
        card = (mid[0], ry, mw, 54)
        lx = mid[0] + mw - 10 - 3 * 26 - 70
        levels = [(lx + k * 26, ry + 28, 22, 20) for k in range(goods.MAX_LEVEL)]
        close_r = (mid[0] + mw - 10 - 62, ry + 28, 62, 20)
        routes.append({"card": card, "levels": levels, "close": close_r})
        ry += 60
    # Ouvrir une route.
    x0 = right[0]
    y = body_y + 24 + 16
    chip_w = (rw - 8) // 2
    partners = []
    for i in range(min(n_partners, MAX_PARTNERS_SHOWN)):
        partners.append((x0 + (i % 2) * (chip_w + 8), y + (i // 2) * 26, chip_w, 22))
    y += max(1, -(-min(n_partners, MAX_PARTNERS_SHOWN) // 2)) * 26 + 20
    gw = (rw - 2 * 6) // 3
    goods_chips = {}
    for i, g in enumerate(goods.GOODS):
        goods_chips[g] = (x0 + (i % 3) * (gw + 6), y + (i // 3) * 26, gw, 22)
    y += -(-len(goods.GOODS) // 3) * 26 + 6
    dw = (rw - 8) // 2
    dirs = {"sell": (x0, y, dw, 22), "buy": (x0 + dw + 8, y, dw, 22)}
    y += 30
    lvw = 30
    levels = [(x0 + 90 + k * (lvw + 6), y, lvw, 22) for k in range(goods.MAX_LEVEL)]
    y += 30
    preview = (x0, y, rw, 60)
    y += 64
    open_r = (x0, y, rw, 30)
    y += 54
    theirs = (x0, y, rw, 20 + 16 * len(goods.GOODS))
    y += theirs[3] + 8
    candidates = []
    for i in range(min(n_candidates, MAX_CANDIDATES)):
        candidates.append({"row": (x0, y + 18 + i * 28, rw, 24), "ask": (x0 + rw - 96, y + 18 + i * 28 + 2, 96, 20)})
    return {
        "box": (bx, by, bw, bh),
        "close": close,
        "tiles": tiles,
        "left": left,
        "mid": mid,
        "right": right,
        "goods": goods_rows,
        "graph": graph,
        "routes": routes,
        "partners": partners,
        "goods_chips": goods_chips,
        "dirs": dirs,
        "levels": levels,
        "preview": preview,
        "open": open_r,
        "theirs": theirs,
        "candidates": candidates,
        "cand_top": y,
    }


def trade_hit(lay: dict, mx: int, my: int, partners: list | None = None, n_routes: int = 0, candidates: list | None = None):
    if not lay:
        return None
    if _hover(lay["close"], mx, my):
        return "tclose"
    for i, row in enumerate(lay["routes"][:n_routes]):
        for k, rect in enumerate(row["levels"]):
            if _hover(rect, mx, my):
                return f"rlevel:{i}:{k + 1}"
        if _hover(row["close"], mx, my):
            return f"rclose:{i}"
    for i, rect in enumerate(lay["partners"]):
        if partners is not None and i < len(partners) and _hover(rect, mx, my):
            return f"tpartner:{partners[i]}"
    for g, rect in lay["goods_chips"].items():
        if _hover(rect, mx, my):
            return f"tgood:{g}"
    for key, rect in lay["dirs"].items():
        if _hover(rect, mx, my):
            return f"tdir:{key}"
    for k, rect in enumerate(lay["levels"]):
        if _hover(rect, mx, my):
            return f"tlevel:{k + 1}"
    if _hover(lay["open"], mx, my):
        return "topen"
    for i, row in enumerate(lay["candidates"]):
        if candidates is not None and i < len(candidates) and _hover(row["ask"], mx, my):
            return f"tpropose:{candidates[i]}"
    if _hover(lay["box"], mx, my):
        return "panel"
    return None


def candidates(state) -> list[int]:
    """Peuples connus, avec un village, sans accord commercial : a qui
    proposer des echanges (les plus proches d'abord)."""
    alive = {b.tribe_id for b in state.bands.values() if b.population > 0}
    out = []
    for t in diplo.contacts_of(state, PLAYER_TRIBE_ID):
        if t in alive and not diplo.has_pact(state, PLAYER_TRIBE_ID, t, "commerce") and goods.has_village(state, t):
            out.append(t)
    out.sort(key=lambda t: (goods.trade_distance(state, PLAYER_TRIBE_ID, t), t))
    return out


def routes_shown(state) -> list:
    return sorted(goods.routes_of(state, PLAYER_TRIBE_ID), key=lambda r: (r.exporter != PLAYER_TRIBE_ID, r.good, r.exporter, r.importer))


def _chip(r, rect, label, active, on=True, mx=0, my=0) -> None:
    x, y, w, h = rect
    hover = on and _hover(rect, mx, my)
    if active:
        top, bot, edge, text = (150, 118, 58), (96, 72, 34), GOLD, INK
    elif on:
        top, bot, edge, text = ((58, 60, 68) if hover else (42, 44, 52)), (30, 32, 38), GOLD_DEEP if hover else (84, 86, 94), SOFT
    else:
        top, bot, edge, text = (30, 31, 36), (24, 25, 28), (58, 60, 66), (110, 112, 118)
    r.screen.blit(_gradient_card(w, h, top, bot, 5), (x, y))
    pygame.draw.rect(r.screen, edge, rect, 1, border_radius=5)
    surf = r.tiny.render(_fit(r.tiny, label, w - 8), True, text)
    r.screen.blit(surf, (x + (w - surf.get_width()) // 2, y + (h - surf.get_height()) // 2))


def _dot(r, color, x, y, radius=5) -> None:
    pygame.draw.circle(r.screen, color, (x, y), radius)
    pygame.draw.circle(r.screen, (20, 20, 20), (x, y), radius, 1)


def draw_trade(r, state, ui) -> None:
    tribe = state.tribes.get(PLAYER_TRIBE_ID)
    if tribe is None:
        r.trade_hits = {}
        return
    title_font, head_font = _fonts(r)
    screen = r.screen
    mx, my = pygame.mouse.get_pos()
    partners = goods.partners(state, PLAYER_TRIBE_ID)
    routes = routes_shown(state)
    cands = candidates(state)
    w, h = screen.get_size()
    lay = trade_layout(w, h, len(routes), len(partners), len(cands))
    r.trade_hits = lay
    r.trade_partners = partners[:MAX_PARTNERS_SHOWN]
    r.trade_routes = routes[:MAX_ROUTES_SHOWN]
    r.trade_candidates = cands[:MAX_CANDIDATES]
    _frame(r, lay["box"])
    bx, by, bw, bh = lay["box"]
    pygame.draw.rect(screen, color_of(tribe), (bx + 22, by + 18, 6, 34), border_radius=2)
    screen.blit(title_font.render(f"Commerce des {tribe.name}", True, GOLD), (bx + 36, by + 12))
    used, cap = goods.convoys_used(state, PLAYER_TRIBE_ID), goods.convoys(state, PLAYER_TRIBE_ID)
    sub = f"Accords commerciaux : {len(partners)}  ·  convois de porteurs {used}/{cap} (1, +1 par village, +2 par Place d'echange)"
    screen.blit(r.tiny.render(_fit(r.tiny, sub, bw - 240), True, NOTE), (bx + 38, by + 42))
    _button(screen, r.small, lay["close"], "Fermer [Echap]", True, _hover(lay["close"], mx, my))
    tips: list = []
    # Tuiles.
    month = goods.last_month(state, PLAYER_TRIBE_ID)
    ok = sum(1 for g in goods.GOODS if goods.supplied(state, PLAYER_TRIBE_ID, g))
    balance = month["sold"] - month["bought"]
    tiles = (
        ("BIENS POURVUS", f"{ok}/{len(goods.GOODS)}", "leurs effets jouent", GOOD if ok else INK),
        ("CONVOIS", f"{used}/{cap}", f"{len(routes)} route{'s' if len(routes) > 1 else ''}", INK),
        ("VENTES DU MOIS", f"+{month['sold']:.0f}", "vivres recus", GOOD if month["sold"] else INK),
        ("ACHATS DU MOIS", f"-{month['bought']:.0f}", "vivres payes", WARN if month["bought"] else INK),
        ("BALANCE", f"{'+' if balance >= 0 else ''}{balance:.0f}", "vivres, dernier mois", GOOD if balance > 0 else BAD if balance < 0 else INK),
        ("PARTENAIRES", f"{len(partners)}", "accords commerciaux", INK),
    )
    for rect, (label, value, sub_t, col) in zip(lay["tiles"], tiles):
        _tile(r, rect, label, value, sub_t, col)
    _draw_market(r, state, lay, tips, mx, my)
    _draw_routes(r, state, lay, routes, ui, tips, mx, my)
    _draw_new(r, state, lay, ui, partners, cands, head_font, tips, mx, my)
    for rows, tx, ty in tips:
        _tip(r, rows, tx, ty)


def _draw_market(r, state, lay, tips, mx, my) -> None:
    screen = r.screen
    x, y, w, _h = lay["left"]
    _section(r, x, y, w, "MARCHE DU PEUPLE  ·  reserve, prix chez vous")
    need = goods.need(state, PLAYER_TRIBE_ID)
    for g, rect in lay["goods"].items():
        gx, gy, gw, gh = rect
        have = goods.stock(state, PLAYER_TRIBE_ID, g)
        made = goods.made(state, PLAYER_TRIBE_ID, g)
        ok = goods.supplied(state, PLAYER_TRIBE_ID, g)
        pygame.draw.circle(screen, goods.GOOD_COLORS[g], (gx + 6, gy + 9), 5)
        screen.blit(r.small.render(goods.GOOD_NAMES[g], True, INK if have or made else SOFT), (gx + 16, gy))
        p = goods.price(state, PLAYER_TRIBE_ID, g)
        word = goods.price_word(state, PLAYER_TRIBE_ID, g)
        ptxt = f"{p:.1f} vivres · {word}".replace(".", ",", 1)
        ps = r.tiny.render(ptxt, True, WARN if word in ("cher", "tres cher") else GOOD if word == "bon marche" else SOFT)
        screen.blit(ps, (gx + gw - ps.get_width(), gy + 3))
        bar = (gx + 16, gy + 22, gw - 16 - 70, 5)
        pygame.draw.rect(screen, (14, 16, 20), bar, border_radius=2)
        pygame.draw.rect(screen, GOLD if ok else (90, 80, 60), (bar[0], bar[1], int(bar[2] * min(1.0, have / goods.CAP)), bar[3]), border_radius=2)
        ts = r.tiny.render(f"{have:.0f} en reserve", True, SOFT)
        screen.blit(ts, (gx + gw - ts.get_width(), gy + 18))
        line = f"fait {made:.1f} · mange {need:.1f} / sem. · ".replace(".", ",") + ("pourvu" if ok else "en manque")
        screen.blit(r.tiny.render(_fit(r.tiny, line, gw - 16), True, GOOD if ok else NOTE), (gx + 16, gy + 28))
        if _hover(rect, mx, my):
            craft = goods.CRAFTS[goods.GOOD_CRAFT[g]]
            rows = [(goods.GOOD_NAMES[g], INK), ("Pourvu : " + " · ".join(craft.lines), (184, 222, 168)),
                    (f"Valeur {goods.value(g):.0f} vivres la charge ; ici x{p / goods.value(g):.2f} (plus cher quand on en manque).".replace(".", ",", 1), SOFT),
                    (f"Metier : {craft.name.lower()} ({goods.res_label(craft.id)}, savoir {tech.TECHS[craft.needs].name}).", NOTE)]
            tips.append((rows, mx, my))
    # Graphe : ventes (haut) et achats (bas) des derniers mois.
    gx, gy, gw, gh = lay["graph"]
    screen.blit(r.tiny.render("VENTES ET ACHATS DES DERNIERS MOIS (vivres)", True, GOLD), (gx, gy - 18))
    screen.blit(_gradient_card(gw, gh, (20, 24, 28), (14, 16, 20), 6), (gx, gy))
    hist = goods.history(state, PLAYER_TRIBE_ID)
    mid_y = gy + gh // 2
    pygame.draw.line(screen, (60, 64, 72), (gx + 6, mid_y), (gx + gw - 6, mid_y))
    if not hist:
        t = r.tiny.render("Pas encore de commerce.", True, NOTE)
        screen.blit(t, (gx + (gw - t.get_width()) // 2, mid_y - 20))
        return
    top = max([max(s, b) for _y, _w, s, b in hist] + [20.0])
    slot = (gw - 12) / goods.HISTORY
    n = len(hist)
    for i, (_yr, _wk, sold, bought) in enumerate(hist):
        x0 = int(gx + 6 + (goods.HISTORY - n + i) * slot)
        hs = int((gh / 2 - 8) * sold / top)
        hb = int((gh / 2 - 8) * bought / top)
        if hs:
            pygame.draw.rect(screen, (120, 190, 110), (x0 + 1, mid_y - hs, max(2, int(slot) - 2), hs))
        if hb:
            pygame.draw.rect(screen, (210, 110, 90), (x0 + 1, mid_y + 1, max(2, int(slot) - 2), hb))
    screen.blit(r.tiny.render(f"ventes (max {top:.0f})", True, (120, 190, 110)), (gx + 8, gy + 4))
    screen.blit(r.tiny.render("achats", True, (210, 110, 90)), (gx + 8, gy + gh - 17))


def _draw_routes(r, state, lay, routes, ui, tips, mx, my) -> None:
    screen = r.screen
    x, y, w, h = lay["mid"]
    used, cap = goods.convoys_used(state, PLAYER_TRIBE_ID), goods.convoys(state, PLAYER_TRIBE_ID)
    _section(r, x, y, w, f"ROUTES  ·  convois {used}/{cap}")
    if not routes:
        text = (
            "Aucune route. Une route porte chaque mois un bien de chez vous vers un partenaire (vendre) "
            "ou de chez lui vers vous (acheter) ; l'acheteur paie en vivres, au prix moyen des deux marches. "
            "Ouvrez-en une a droite."
        )
        yy = y + 30
        for part in _wrap(r.tiny, text, w)[:6]:
            screen.blit(r.tiny.render(part, True, NOTE), (x, yy))
            yy += 15
        return
    for route, row in zip(routes, lay["routes"]):
        cx, cy, cw, ch = row["card"]
        selling = route.exporter == PLAYER_TRIBE_ID
        other = route.importer if selling else route.exporter
        o = state.tribes.get(other)
        top = (40, 52, 38) if selling else (52, 40, 34)
        screen.blit(_gradient_card(cw, ch, top, (24, 26, 28), 6), (cx, cy))
        pygame.draw.rect(screen, GOLD_DEEP, row["card"], 1, border_radius=6)
        pygame.draw.circle(screen, goods.GOOD_COLORS[route.good], (cx + 12, cy + 12), 6)
        if o is not None:
            _dot(r, color_of(o), cx + 26, cy + 12, 4)
        head = goods.route_text(state, PLAYER_TRIBE_ID, route)
        screen.blit(r.small.render(_fit(r.small, head, cw - 50), True, INK), (cx + 36, cy + 3))
        mine = route.by == PLAYER_TRIBE_ID
        if route.units > 0:
            verb = "vendu" if selling else "achete"
            last = f"{verb} {route.units:.1f} · {'+' if selling else '-'}{route.paid:.0f} vivres".replace(".", ",", 1)
            color = GOOD if selling else WARN
        else:
            last = route.status or "pas encore partie"
            color = NOTE
        opener = "" if mine else " (leur route)"
        screen.blit(r.tiny.render(_fit(r.tiny, last + opener, row["levels"][0][0] - cx - 12), True, color), (cx + 10, cy + 31))
        for k, rect in enumerate(row["levels"]):
            _chip(r, rect, str(k + 1), route.level == k + 1, on=mine, mx=mx, my=my)
            if _hover(rect, mx, my):
                why = goods.level_block(state, PLAYER_TRIBE_ID, route, k + 1)
                load = goods.trade_load(state, route.exporter, route.importer)
                tips.append(([(f"{k + 1} convoi{'s' if k else ''} : {load * (k + 1):.0f} charges par mois au plus", SOFT)] + ([(why, WARN)] if why and route.level != k + 1 else []), mx, my))
        _chip(r, row["close"], "Fermer", False, on=True, mx=mx, my=my)
        if _hover(row["close"], mx, my) and not mine:
            tips.append(([("C'est leur route : la fermer les froissera (relation -3).", WARN)], mx, my))
    extra = len(goods.routes_of(state, PLAYER_TRIBE_ID)) - len(routes)
    if extra > 0:
        screen.blit(r.tiny.render(f"... et {extra} autres routes", True, NOTE), (x, lay["routes"][-1]["card"][1] + 60))


def _draw_new(r, state, lay, ui, partners, cands, head_font, tips, mx, my) -> None:
    screen = r.screen
    x, y, w, h = lay["right"]
    _section(r, x, y, w, "OUVRIR UNE ROUTE")
    if not partners:
        hint = "Il faut un accord commercial (Peuples [P], il faut Echanges lointains) avec un peuple qui a un village."
        if not tech.bonuses(state.tribes[PLAYER_TRIBE_ID]).commerce:
            hint = "Il faut connaitre Echanges lointains pour conclure des accords commerciaux."
        yy = y + 26
        for part in _wrap(r.tiny, hint, w)[:3]:
            screen.blit(r.tiny.render(part, True, NOTE), (x, yy))
            yy += 15
    else:
        screen.blit(r.tiny.render("Avec :", True, NOTE), (x, y + 22))
    pick = ui.get("trade_partner")
    if pick not in partners:
        pick = partners[0] if partners else None
        ui["trade_partner"] = pick
    for tid, rect in zip(partners, lay["partners"]):
        _chip(r, rect, state.tribes[tid].name, tid == pick, mx=mx, my=my)
    good = ui.get("trade_good") or goods.GOODS[0]
    sell = ui.get("trade_sell", True)
    level = ui.get("trade_level") or 1
    if pick is not None:
        gy0 = min(rect[1] for rect in lay["goods_chips"].values())
        screen.blit(r.tiny.render("Bien :", True, NOTE), (x, gy0 - 16))
    for g, rect in lay["goods_chips"].items():
        _chip(r, rect, goods.GOOD_NAMES[g], g == good, on=pick is not None, mx=mx, my=my)
    _chip(r, lay["dirs"]["sell"], "Vendre", sell, on=pick is not None, mx=mx, my=my)
    _chip(r, lay["dirs"]["buy"], "Acheter", not sell, on=pick is not None, mx=mx, my=my)
    lx, ly = lay["levels"][0][0], lay["levels"][0][1]
    screen.blit(r.tiny.render("Convois :", True, NOTE), (x, ly + 4))
    for k, rect in enumerate(lay["levels"]):
        _chip(r, rect, str(k + 1), level == k + 1, on=pick is not None, mx=mx, my=my)
    px, py, pw, _ph = lay["preview"]
    why = "Choisissez un partenaire" if pick is None else goods.open_block(state, PLAYER_TRIBE_ID, pick, good, sell, level)
    if pick is not None:
        pv = goods.preview(state, PLAYER_TRIBE_ID, pick, good, sell, level)
        other = state.tribes[pick].name
        rows = [
            (f"Prix : {pv['mine']:.1f} chez vous, {pv['theirs']:.1f} chez les {other} -> {pv['price']:.1f} la charge".replace(".", ","), SOFT),
        ]
        if pv["units"] > 0:
            verb = "rapporterait" if sell else "couterait"
            rows.append((f"Le mois prochain : {pv['units']:.1f} charges, {verb} ~{pv['vivres']:.0f} vivres".replace(".", ",", 1), GOOD if sell else WARN))
        else:
            rows.append((f"Le mois prochain : rien ({pv['why']})", NOTE))
        yy = py
        for text, color in rows:
            for part in _wrap(r.tiny, text, pw)[:2]:
                screen.blit(r.tiny.render(part, True, color), (px, yy))
                yy += 14
    on = not why
    _button(screen, r.small, lay["open"], "Ouvrir la route", on, on and _hover(lay["open"], mx, my))
    if why and pick is not None and _hover(lay["open"], mx, my):
        tips.append(([(why, WARN)], mx, my))
    elif why and pick is not None:
        s = r.tiny.render(_fit(r.tiny, why, w), True, WARN)
        screen.blit(s, (x, lay["open"][1] + 32))
    # Chez le partenaire.
    tx, ty, tw, _th = lay["theirs"]
    if pick is not None:
        other = state.tribes[pick]
        screen.blit(r.tiny.render(f"CHEZ LES {other.name.upper()}", True, GOLD), (tx, ty))
        pygame.draw.line(screen, GOLD_DEEP, (tx, ty + 15), (tx + tw, ty + 15))
        yy = ty + 20
        for g in goods.GOODS:
            s_have = goods.spare(state, pick, g)
            s_want = goods.wants(state, pick, g)
            if s_have >= 1:
                state_txt, col = f"en ont de trop ({s_have:.0f})", GOOD
            elif s_want >= 1:
                state_txt, col = f"en manquent ({s_want:.0f})", WARN
            else:
                state_txt, col = "pourvus", NOTE
            p = goods.price(state, pick, g)
            line = f"{goods.GOOD_NAMES[g]} : {state_txt} · {p:.1f}".replace(".", ",")
            screen.blit(r.tiny.render(_fit(r.tiny, line, tw), True, col), (tx, yy))
            yy += 16
    # A qui proposer un accord.
    cy0 = lay["cand_top"]
    if cands and cy0 + 30 < y + h:
        screen.blit(r.tiny.render("PROPOSER DES ECHANGES", True, GOLD), (x, cy0))
        pygame.draw.line(screen, GOLD_DEEP, (x, cy0 + 15), (x + w, cy0 + 15))
        for tid, row in zip(cands, lay["candidates"]):
            rx, ry, rw_, rh = row["row"]
            if ry + rh > y + h:
                break
            t = state.tribes[tid]
            _dot(r, color_of(t), rx + 6, ry + 11, 5)
            dist = goods.trade_distance(state, PLAYER_TRIBE_ID, tid)
            rel = diplo.relation(state, PLAYER_TRIBE_ID, tid)
            screen.blit(r.tiny.render(_fit(r.tiny, f"{t.name} · {dist} cases · relation {rel:+.0f}", rw_ - 110), True, SOFT), (rx + 16, ry + 5))
            v = diplo.evaluate(state, PLAYER_TRIBE_ID, tid, "commerce")
            wait = diplo.on_cooldown(state, PLAYER_TRIBE_ID, tid, "commerce")
            ok = not v.blocked and not wait
            _chip(r, row["ask"], "Proposer", False, on=ok, mx=mx, my=my)
            if _hover(row["ask"], mx, my):
                if v.blocked:
                    rows = [(v.blocked, WARN)]
                elif wait:
                    rows = [(f"Deja propose : attendez {wait} sem.", NOTE)]
                else:
                    rows = [(f"{'+' if val >= 0 else ''}{val}  {label}", GOOD if val > 0 else BAD if val < 0 else SOFT) for label, val in v.reasons]
                    rows.append((("Ils accepteraient" if v.accepted else "Ils refuseraient") + f" ({v.score:+d})", GOOD if v.accepted else BAD))
                tips.append((rows, mx, my))
