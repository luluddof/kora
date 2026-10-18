"""LA PAGE "LES BATIMENTS" de la fenetre du village (2026-10-18 : la
refonte demandee par le joueur, "une interface inspiree de Victoria 3 ou
d'Europa Universalis 5").

  - En tete, trois jauges : le TERRAIN (pris / du village, quand vient le
    suivant), les LOGES (habitants / logements ; vert, ambre a 90 %, rouge
    quand le village s'entasse, et ce que cela coute), le GRENIER (les
    chantiers se paient en vivres).
  - Les batiments en cartes, par familles (batiments.FAMILIES) sur trois
    colonnes : le medaillon et son NIVEAU, le nom du niveau atteint, ce que
    donnera le suivant, son prix et son temps, un point pour son genre de
    prix (peu couteux, moyen, couteux) ; "+" batit un niveau (ou le met en
    file), "-" en abat un (deux clics). Un chantier : la carte rougeoie, sa
    barre avance ; verrouille : le savoir qu'il faut.
  - A droite, LES CHANTIERS : celui en cours (sa barre, ses semaines), la
    file (QUEUE_MAX ; ce que chacun attend ; une croix le retire) ; puis la
    FICHE du batiment choisi : son recit, ses niveaux un par un (l'atteint
    en or, le suivant en braise), batir ou abattre.
page_layout et page_hit sont purs (tests) ; draw_page dessine. Les clics :
partie_ecrans.ScreenClicks.village_click ("bplus:", "bminus:", "bpick:",
"bunq:", "bdo", "bdemo").
"""

from __future__ import annotations

import pygame

from src.kora import batiments, places, tech, theme, villages
from src.kora.theme import C

# Les familles en trois colonnes (les cartes tiennent sans defiler).
COLUMNS = (("logements", "defense"), ("vivres", "metiers"), ("peuple",))
TIER_COLORS = {"peu": C.bon, "moyen": C.ocre_jaune, "cher": C.braise}
STATE_RING = {"possible": "actif", "chantier": "actif", "haut": "connu", "attente": "normal", "verrouille": "eteint"}


def _fam(fid: str):
    return next(f for f in batiments.FAMILIES if f[0] == fid)


def page_layout(body: tuple) -> dict:
    """Ou est chaque chose dans la page (body : le corps de la fenetre)."""
    x0, y0, w0, h0 = body
    # Une petite fenetre (1280 x 720) : des jauges basses, des cartes sur deux
    # lignes (le prix passe au survol et dans la fiche), une file serree.
    compact = h0 < 560
    # La plus petite fenetre (1024 x 640) : des jauges sur une ligne, des
    # cartes basses, serrees.
    tiny = h0 < 440
    right_w = max(280 if tiny else 300, min(420, int(w0 * 0.3)))
    main_w = w0 - right_w - 16
    gauges = []
    gw = (main_w - 2 * 12) // 3
    gh = 26 if tiny else (40 if compact else 58)
    for i in range(3):
        gauges.append((x0 + i * (gw + 12), y0, gw, gh))
    top = y0 + gh + 10
    col_w = (main_w - 2 * 12) // 3
    n_rows = max(sum(len([b for b in batiments.BUILD_ORDER if batiments.BUILDINGS[b].family == f]) for f in col) for col in COLUMNS)
    n_heads = max(len(col) for col in COLUMNS)
    head_h, gap = (24, 4) if tiny else (28, 6)
    card_h = max(36, min(80, (y0 + h0 - top - n_heads * head_h - n_rows * gap) // n_rows))
    cards, heads = {}, {}
    for ci, col in enumerate(COLUMNS):
        cx = x0 + ci * (col_w + 12)
        y = top
        for fid in col:
            heads[fid] = (cx, y, col_w, head_h - 4)
            y += head_h
            for bid in (b for b in batiments.BUILD_ORDER if batiments.BUILDINGS[b].family == fid):
                card = (cx, y, col_w, card_h)
                btn = min(26, (card_h - 8) // 2)
                plus = (cx + col_w - 8 - 30, y + 3, 30, btn)
                minus = (cx + col_w - 8 - 30, y + card_h - 3 - btn, 30, btn)
                cards[bid] = {"card": card, "plus": plus, "minus": minus}
                y += card_h + gap
    rx = x0 + main_w + 16
    row_h, cur_h = (28, 46) if tiny else ((30, 50) if compact else (38, 62))
    queue_h = 34 + cur_h + batiments.QUEUE_MAX * row_h + 6
    queue = (rx, y0, right_w, queue_h)
    rows = [(rx + 10, y0 + 34 + cur_h + i * row_h, right_w - 20, row_h - 4) for i in range(batiments.QUEUE_MAX)]
    unq = [(r[0] + r[2] - 28, r[1] + (r[3] - 22) // 2, 24, 22) for r in rows]
    detail = (rx, y0 + queue_h + 12, right_w, y0 + h0 - (y0 + queue_h + 12))
    dx, dy, dw, dh = detail
    build = (dx + 12, dy + dh - 44, dw - 24 - 150, 32)
    demo = (dx + dw - 12 - 140, dy + dh - 44, 140, 32)
    return {"body": body, "gauges": gauges, "heads": heads, "cards": cards, "queue": queue, "rows": rows,
            "unq": unq, "detail": detail, "build": build, "demo": demo, "card_h": card_h, "compact": compact,
            "current": (rx + 10, y0 + 34, right_w - 20, cur_h - 6)}


def _in(rect, mx, my) -> bool:
    x, y, w, h = rect
    return x <= mx <= x + w and y <= my <= y + h


def page_hit(lay: dict, mx: int, my: int):
    for i, rect in enumerate(lay["unq"]):
        if _in(rect, mx, my):
            return f"bunq:{i}"
    if _in(lay["build"], mx, my):
        return "bdo"
    if _in(lay["demo"], mx, my):
        return "bdemo"
    for bid, rects in lay["cards"].items():
        if _in(rects["plus"], mx, my):
            return f"bplus:{bid}"
        if _in(rects["minus"], mx, my):
            return f"bminus:{bid}"
        if _in(rects["card"], mx, my):
            return f"bpick:{bid}"
    return None


# --- ce que dit chaque niveau ---------------------------------------------------------------


def gain_text(bid: str, n: int) -> str:
    """Ce que donne le niveau n de plus que le niveau n-1, en peu de mots."""
    if bid == "monument":
        return "Une étape de plus"
    parts = []
    for key in batiments.VALUES.get(bid, {}):
        now = batiments.value_at(bid, key, n)
        before = batiments.value_at(bid, key, n - 1)
        if now == before:
            continue
        short = SHORT.get(key, key)
        if isinstance(now, float) and isinstance(before, (int, float)):
            if before:
                parts.append(f"{short} x{_n(before)} → x{_n(now)}")
            else:
                parts.append(f"{short} x{_n(now)}")
        else:
            parts.append(f"{short} +{_n(now - (before or 0))}")
    return " · ".join(parts)


SHORT = {
    "logement": "logés", "croissance": "croissance", "stabilite": "stabilité", "reserve": "sem. de réserve",
    "gate": "grain gâté", "vivres": "vivres", "fievres": "fièvres", "defense": "défense", "vue": "vue",
    "qualite": "force des troupes", "compagnies": "compagnies", "attachement": "attachement", "prestige": "prestige/hiver",
    "influence": "influence", "metiers": "métiers", "convois": "convois", "prix": "prix de vente",
}


def _n(v) -> str:
    if isinstance(v, float) and v != int(v):
        return f"{v:.2f}".rstrip("0").replace(".", ",")
    return f"{int(v)}"


def next_level(site, bid: str) -> int:
    return batiments._next_level(site, bid)


def why_short(state, site, bid: str) -> str:
    st = batiments.building_status(state, site, bid)
    if st == "haut":
        return "Au plus haut"
    why = batiments.build_block_site(state, site, bid)
    if why.startswith("Il faut connaître "):
        return why.replace("Il faut connaître ", "")
    return why


# --- le dessin ------------------------------------------------------------------------------


def _hover(rect) -> bool:
    mx, my = pygame.mouse.get_pos()
    return _in(rect, mx, my)


def _lock(surf, x, y, color=C.cendre) -> None:
    pygame.draw.rect(surf, color, (x - 4, y - 1, 9, 7), border_radius=1)
    pygame.draw.arc(surf, color, (x - 3, y - 6, 7, 9), 0, 3.15, 2)


def _badge(surf, x, y, n: int, color) -> None:
    """Le niveau, dans une pastille au pied du medaillon."""
    f = theme.font("mini_gras")
    text = str(n)
    w = max(18, f.size(text)[0] + 8)
    rect = (x - w // 2, y - 9, w, 18)
    pygame.draw.rect(surf, C.nuit, rect, border_radius=9)
    pygame.draw.rect(surf, color, rect, 1, border_radius=9)
    surf.blit(f.render(text, True, C.os), (x - f.size(text)[0] // 2, y - 8))


def _gauge(surf, rect, label: str, value: str, frac: float, color, sub: str, sub_color, tips=None) -> None:
    x, y, w, h = rect
    theme.panel(surf, rect, "creux")
    if h < 30:
        lw = theme.text(surf, label, "etiquette", C.ocre_jaune, (x + 10, y + 4))
        f = theme.font("mini_gras")
        surf.blit(f.render(value, True, C.os), (x + w - 10 - f.size(value)[0], y + 5))
        theme.bar(surf, (x + 18 + lw, y + 10, w - 36 - lw - f.size(value)[0], 7), frac, color)
        if tips is not None and _hover(rect):
            tips.append(([(label, C.os, "petit_gras"), (sub, sub_color if sub_color != C.cendre else C.lin)], x, y + h + 4, rect))
        return
    theme.text(surf, label, "etiquette", C.ocre_jaune, (x + 12, y + 5))
    f = theme.font("chiffre")
    surf.blit(f.render(value, True, C.os), (x + w - 12 - f.size(value)[0], y + 2))
    theme.bar(surf, (x + 12, y + 26, w - 24, 8), frac, color)
    if h >= 56:
        theme.text(surf, sub, "mini", sub_color, (x + 12, y + 38), w - 24)
    elif tips is not None and _hover(rect):
        tips.append(([(label, C.os, "petit_gras"), (sub, sub_color if sub_color != C.cendre else C.lin)], x, y + h + 4, rect))


def draw_page(r, state, site, band, vlay, ui, tips: list) -> None:
    s = r.screen
    lay = vlay["bpage"]
    pick = ui.get("village_pick")
    if pick not in batiments.BUILDINGS:
        pick = next((b for b in batiments.BUILD_ORDER if batiments.building_status(state, site, b) == "possible"), "huttes")
        ui["village_pick"] = pick
    _gauges(r, state, site, band, lay, tips)
    for fid, rect in lay["heads"].items():
        _fid, title, icon = _fam(fid)
        x, y, w, _h = rect
        s.blit(theme.medallion(icon, 11, "connu"), (x, y))
        theme.text(s, title, "etiquette", C.ocre_jaune, (x + 30, y + 4))
        f = theme.font("etiquette")
        theme.dotted(s, (x + 38 + f.size(title)[0], y + 13), (x + w, y + 13), C.ocre_sombre, 6)
    job = places.works(site)
    for bid, rects in lay["cards"].items():
        _card(r, state, site, bid, rects, bid == pick, job, ui, tips)
    _queue(r, state, site, band, lay, tips)
    _detail(r, state, site, band, lay, pick, ui)


def _gauges(r, state, site, band, lay, tips) -> None:
    s = r.screen
    used, room = batiments.used_space(site), batiments.space(state, site)
    nxt = (room + 1 - batiments.BASE_SPACE) * batiments.SPACE_POP
    _gauge(s, lay["gauges"][0], "Terrain", f"{used} / {room}", used / max(1, room), C.ocre,
           f"un de plus à {nxt} habitants (encore {max(0, nxt - band.population)})", C.cendre, tips)
    cap = batiments.housing(site)
    pop = band.population
    crowd = batiments.crowding(state, site, band)
    if crowd:
        g = villages.crowd_growth(state, site, band)
        color, sub = C.mauvais, f"{crowd} sans toit : croissance x{_n(round(g, 2))}, stabilité, fièvres"
    elif pop >= 0.9 * cap:
        color, sub = C.alerte, "Presque plein : bâtissez des logements"
    else:
        color, sub = C.bon, f"Chacun a son toit ({cap - pop} places libres)"
    _gauge(s, lay["gauges"][1], "Logés", f"{pop} / {cap}", min(1.0, pop / max(1, cap)), color, sub, color if crowd else C.cendre, tips)
    weeks = band.stock / max(1, band.population)
    _gauge(s, lay["gauges"][2], "Vivres au grenier", f"{band.stock:.0f}", min(1.0, weeks / 26.0), C.ocre_jaune,
           f"{weeks:.0f} semaines · les chantiers se paient en vivres", C.cendre, tips)


def _card(r, state, site, bid, rects, chosen, job, ui, tips) -> None:
    s = r.screen
    b = batiments.BUILDINGS[bid]
    x, y, w, h = rects["card"]
    st = batiments.building_status(state, site, bid)
    n = places.level(site, bid)
    hover = _hover(rects["card"])
    kind = "carte_choisie" if chosen else ("carte_survol" if hover else ("creux" if st == "verrouille" else "carte"))
    theme.panel(s, rects["card"], kind)
    if st == "chantier":
        theme.glow(s, rects["card"], C.braise, 0.5)
    rad = max(14, min(20, h // 2 - 8))
    mx_, my_ = x + 8 + rad, y + h // 2 - 2
    s.blit(theme.medallion(b.icon, rad, STATE_RING.get(st, "normal")), (mx_ - rad - 2, my_ - rad - 2))
    if n > 0:
        _badge(s, mx_ + rad - 2, my_ + rad - 2, n, C.ocre_jaune)
    tx = x + 2 * rad + 18
    tw = w - (tx - x) - 46
    name = batiments.building_name(site, bid, short=True) if n else b.name
    low = h < 46
    theme.text(s, name, "mini_gras" if low else "petit_gras", C.os if st != "verrouille" else C.lin, (tx, y + (2 if low else 4)), tw)
    line_y = y + (19 if low else 24)
    nxt = next_level(site, bid)
    if st == "haut":
        theme.text(s, "Au plus haut", "mini_gras", C.ocre_jaune, (tx, line_y), tw)
    elif st == "verrouille":
        _lock(s, tx + 5, line_y + 8)
        theme.text(s, why_short(state, site, bid), "mini", C.cendre, (tx + 14, line_y), tw - 14)
    elif st == "chantier" and job:
        # Le chantier : sa barre et ses semaines, a la place de la suite.
        total = max(1, batiments.build_weeks(site, bid, places.level(site, bid) + 1))
        done = 1.0 - job[1] / total
        theme.bar(s, (tx, line_y + 5, tw - 86, 7), done, C.braise)
        theme.text(s, f"encore {job[1]} sem.", "mini_gras", C.braise, (tx + tw - 80, line_y), 80)
    else:
        theme.text(s, f"Niv. {nxt} : {gain_text(bid, nxt)}", "mini", (178, 205, 140), (tx, line_y), tw)
    if h >= 62 and st not in ("haut", "chantier"):
        cost = f"{batiments.build_cost(state, site, bid):.0f} vivres · {batiments.build_weeks(site, bid)} sem."
        if b.size:
            cost += f" · terrain {b.size}"
        cy = y + h - 18
        pygame.draw.circle(s, TIER_COLORS[b.tier], (tx + 4, cy + 8), 4)
        theme.text(s, cost, "mini", C.cendre, (tx + 13, cy), tw - 13)
    queued = sum(1 for q in site.data.queue if q == bid)
    if queued:
        f = theme.font("mini_gras")
        text = f"+{queued}"
        qw = f.size(text)[0] + 8
        qx, qy = mx_ + rad - qw // 2, my_ - rad - 4
        pygame.draw.rect(s, C.braise, (qx, qy, qw, 16), border_radius=8)
        s.blit(f.render(text, True, C.nuit), (qx + 4, qy))
    # Les boutons : + (batir), - (abattre).
    can = st in ("possible", "chantier") or (job and st == "attente" and not batiments.build_block_site(state, site, bid))
    theme.button(s, rects["plus"], "+", "principal" if can and st == "possible" else "second", on=bool(can), hover=bool(can) and _hover(rects["plus"]), role="bouton")
    if n > 0 and bid != "monument":
        confirm = ui.get("demolish_confirm")
        armed = confirm is not None and confirm[0] == bid
        theme.button(s, rects["minus"], "−", "second", on=not batiments.demolish_block(state, site, bid), hover=_hover(rects["minus"]), role="bouton", active=armed)
    if hover:
        rows = [(batiments.title_of(bid, max(1, n)) + (f" · niveau {n}" if n else " · pas bâti"), C.os, "petit_gras")]
        if n:
            rows += [(f"  {line}", C.bon) for line in batiments.effect_lines(bid, n)]
        if st not in ("haut",):
            rows.append((f"Niveau {nxt} :", C.lin))
            rows += [(f"  {line}", (178, 205, 140)) for line in batiments.effect_lines(bid, nxt)]
            why = batiments.build_block_site(state, site, bid)
            if why:
                rows.append((why, C.alerte))
            rows.append((f"Prix : {batiments.build_cost(state, site, bid):.0f} vivres · {batiments.build_weeks(site, bid)} semaines", C.lin))
        if queued:
            rows.append((f"{queued} niveau{'x' if queued > 1 else ''} de plus en file", C.braise))
        rows.append((f"{batiments.TIER_NAMES[b.tier]} · terrain {b.size} · au plus {b.top} niveau{'x' if b.top > 1 else ''}", C.cendre))
        tips.append((rows, x + w + 8, y, rects["card"]))


def _queue(r, state, site, band, lay, tips) -> None:
    s = r.screen
    x, y, w, h = lay["queue"]
    theme.panel(s, lay["queue"], "creux")
    theme.text(s, "Les chantiers", "h3", C.os, (x + 12, y + 8))
    theme.text(s, f"file {len(site.data.queue)}/{batiments.QUEUE_MAX}", "mini", C.cendre, (x + w - 74, y + 12))
    job = places.works(site)
    cur = lay["current"]
    theme.panel(s, cur, "carte_choisie" if job else "carte")
    if job:
        bid, left = job
        n = places.level(site, bid) + 1
        total = max(1, batiments.build_weeks(site, bid, n))
        s.blit(theme.medallion(batiments.BUILDINGS[bid].icon, 16 if lay["compact"] else 18, "actif"), (cur[0] + 8, cur[1] + 6))
        label = batiments.title_of(bid, n) + (f" · niv. {n}" if bid != "monument" else f" · étape {places.monument_stages(site) + 1}")
        theme.text(s, label, "petit_gras", C.os, (cur[0] + 54, cur[1] + 6), cur[2] - 64)
        by_ = cur[1] + cur[3] - 16
        theme.bar(s, (cur[0] + 54, by_ + 3, cur[2] - 150, 8), 1.0 - left / total, C.braise)
        theme.text(s, f"encore {left} sem.", "mini_gras", C.braise, (cur[0] + cur[2] - 88, by_ - 2))
    else:
        theme.text(s, "Aucun chantier : « + » sur un bâtiment le lance.", "mini", C.cendre, (cur[0] + 12, cur[1] + 19), cur[2] - 24)
    for i, row in enumerate(lay["rows"]):
        if i >= len(site.data.queue):
            if i == 0:
                theme.text(s, "La file est vide : les suivants attendront ici.", "mini", C.cendre, (row[0] + 4, row[1] + 9), row[2] - 8)
            break
        bid = site.data.queue[i]
        theme.panel(s, row, "carte")
        s.blit(theme.icon(batiments.BUILDINGS[bid].icon, 18, C.lin), (row[0] + 8, row[1] + 8))
        why = batiments.queue_block(state, site, i)
        if lay["compact"]:
            line = f"{i + 1}. {batiments.BUILDINGS[bid].name}" + (f" · {why}" if why and not why.startswith("Attend") else "")
            theme.text(s, line, "mini_gras", C.alerte if why and not why.startswith("Attend") else C.os, (row[0] + 32, row[1] + 5), row[2] - 70)
        else:
            theme.text(s, f"{i + 1}. {batiments.BUILDINGS[bid].name}", "mini_gras", C.os, (row[0] + 32, row[1] + 2), row[2] - 70)
            theme.text(s, why or "Prêt à commencer", "mini", C.alerte if why and not why.startswith("Attend") else C.cendre, (row[0] + 32, row[1] + 17), row[2] - 70)
        unq = lay["unq"][i]
        theme.button(s, unq, "×", "second", hover=_hover(unq), role="bouton_petit")
        if _hover(unq):
            tips.append(([("Retirer de la file (rien n'était payé)", C.os)], unq[0] + unq[2] + 6, unq[1], unq))


def _detail(r, state, site, band, lay, pick: str, ui) -> None:
    s = r.screen
    b = batiments.BUILDINGS[pick]
    x, y, w, h = lay["detail"]
    theme.panel(s, lay["detail"], "carte")
    n = places.level(site, pick)
    st = batiments.building_status(state, site, pick)
    s.blit(theme.medallion(b.icon, 24, STATE_RING.get(st, "normal")), (x + 12, y + 12))
    theme.text(s, batiments.building_name(site, pick) if n else b.name, "h3", C.os, (x + 70, y + 10), w - 82)
    cx = x + 70
    cx += theme.chip(s, cx, y + 36, batiments.TIER_NAMES[b.tier], TIER_COLORS[b.tier]) + 6
    cx += theme.chip(s, cx, y + 36, f"terrain {b.size}", C.lin) + 6
    if b.needs:
        theme.chip(s, cx, y + 36, tech_name(b.needs), C.savoir, icon_key="savoir")
    yy = y + 64
    if not lay["compact"]:
        for part in theme.wrap(theme.font("recit_petit"), b.text, w - 28)[:2]:
            theme.text(s, part, "recit_petit", C.lin, (x + 14, yy))
            yy += 18
        yy += 4
    theme.text(s, "Les niveaux", "etiquette", C.ocre_jaune, (x + 14, yy))
    yy += 20
    top = b.top if pick != "monument" else batiments.MONUMENT_STAGES
    shown = range(max(1, n - 1), min(top, n + 3) + 1) if top > 5 else range(1, top + 1)
    bottom = lay["build"][1] - 8
    for k in shown:
        if yy + 18 > bottom:
            break
        col = C.ocre_jaune if k == n else (C.braise if k == n + 1 else C.cendre)
        need = batiments.needs_for(pick, k)
        text = gain_text(pick, k) if k > 1 or pick == "monument" else " · ".join(batiments.effect_lines(pick, 1))
        line = f"{k}. {text}"
        if need and need not in state.tribes[site.tribe_id].knowledge:
            line += f" (il faut {tech_name(need)})"
        theme.text(s, line, "mini_gras" if k in (n, n + 1) else "mini", col, (x + 14, yy), w - 28)
        yy += 18
    if top > 5 and n + 3 < top and yy + 18 <= bottom:
        theme.text(s, f"... jusqu'au niveau {top}", "mini", C.cendre, (x + 14, yy))
    # Batir, abattre.
    why = batiments.build_block_site(state, site, pick) if st != "haut" else "Au plus haut"
    job = places.works(site)
    nxt = next_level(site, pick)
    if st == "haut":
        label = "Au plus haut"
    elif job:
        label = f"Mettre en file (niv. {nxt})"
    else:
        label = f"Bâtir le niveau {nxt}"
    if not why and st != "haut" and not lay["compact"]:
        label += f" · {batiments.build_cost(state, site, pick):.0f} vivres"
    label = theme.fit(theme.font("bouton"), label, lay["build"][2] - 16)
    theme.button(s, lay["build"], label, "principal" if not why else "second", on=not why, hover=not why and _hover(lay["build"]))
    if why and st != "haut":
        theme.text(s, why, "mini", C.alerte, (lay["build"][0], lay["build"][1] - 18), w - 24)
    confirm = ui.get("demolish_confirm")
    armed = confirm is not None and confirm[0] == pick
    no = batiments.demolish_block(state, site, pick)
    theme.button(s, lay["demo"], "Confirmer ?" if armed else "Démolir un niveau", "second", on=not no, hover=not no and _hover(lay["demo"]), active=armed)


def tech_name(tid: str) -> str:
    return tech.TECHS[tid].name if tid in tech.TECHS else tid
