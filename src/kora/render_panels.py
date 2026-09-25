"""Panneaux Tribu (chef, clans, attachement) et Peuples (diplomatie),
cartes d'evenements.

Les rectangles cliquables sont enregistres pendant le dessin dans
layout["items"] (comme les lignes du journal) ; app.py lit side_hit.
"""

from __future__ import annotations

import pygame

from src.kora import chiefs, diplo, influence, sites, tech
from src.kora.peoples import color_of, label_of
from src.kora.sim import PLAYER_TRIBE_ID, max_bands_of

BG = (16, 18, 22)
EDGE = (70, 74, 80)
TEXT = (230, 228, 220)
SOFT = (196, 196, 190)
NOTE = (150, 156, 166)
GOLD = (210, 180, 90)
GOOD = (150, 205, 140)
BAD = (225, 135, 115)
WARN = (235, 165, 80)


def panel_box(width: int, height: int, panel: str, tab_w: int = 32) -> tuple:
    top = 48 + 12
    if panel == "tribu":
        bw = max(520, min(660, width - tab_w - 24))
    else:
        bw = max(600, min(860, width - tab_w - 24))
    bh = max(420, min(640, height - top - 14))
    return (width - tab_w - bw - 8, top, bw, bh)


def _fonts(r):
    if not hasattr(r, "title_font"):
        r.title_font = pygame.font.SysFont("georgia", 22)
        r.head_font = pygame.font.SysFont("georgia", 17)
    return r.title_font, r.head_font


def _box(r, rect, fill=BG, edge=EDGE, radius=8, width=1):
    pygame.draw.rect(r.screen, fill, rect, border_radius=radius)
    pygame.draw.rect(r.screen, edge, rect, width, border_radius=radius)


def _text(r, font, text, color, x, y):
    surf = font.render(text, True, color)
    r.screen.blit(surf, (x, y))
    return surf.get_width()


def _button(r, rect, label, on=True, active=False, font=None):
    font = font or r.tiny
    mx, my = pygame.mouse.get_pos()
    hover = on and rect[0] <= mx <= rect[0] + rect[2] and rect[1] <= my <= rect[1] + rect[3]
    if active:
        fill = (196, 150, 60) if hover else (70, 90, 60)
    else:
        fill = (196, 150, 60) if hover else (44, 48, 56) if on else (28, 30, 34)
    pygame.draw.rect(r.screen, fill, rect, border_radius=4)
    pygame.draw.rect(r.screen, GOLD if on else (66, 70, 76), rect, 1, border_radius=4)
    col = (20, 18, 14) if hover else TEXT if on else (110, 112, 116)
    surf = font.render(r._fit(font, label, rect[2] - 8), True, col)
    r.screen.blit(surf, (rect[0] + (rect[2] - surf.get_width()) // 2, rect[1] + (rect[3] - surf.get_height()) // 2))
    return hover


def _hover(rect) -> bool:
    mx, my = pygame.mouse.get_pos()
    return rect[0] <= mx <= rect[0] + rect[2] and rect[1] <= my <= rect[1] + rect[3]


def _tooltip(r, lines, x, y):
    """Petite fiche au survol : (texte, couleur)."""
    if not lines:
        return
    w, h = r.screen.get_size()
    tw = max(r.tiny.size(t)[0] for t, _c in lines) + 18
    th = 10 + 16 * len(lines)
    x = min(x, w - tw - 8)
    y = min(y, h - th - 8)
    _box(r, (x, y, tw, th), fill=(24, 26, 32), edge=GOLD, radius=6)
    yy = y + 6
    for text, color in lines:
        _text(r, r.tiny, text, color, x + 9, yy)
        yy += 16


def _signed(v: float) -> str:
    v = round(v)
    return f"+{v}" if v > 0 else str(v)


def _loyalty_bar(r, x, y, w, value, tint):
    pygame.draw.rect(r.screen, (34, 36, 42), (x, y, w, 8), border_radius=3)
    fill = int(w * max(0.0, min(100.0, value)) / 100.0)
    pygame.draw.rect(r.screen, tint, (x, y, fill, 8), border_radius=3)
    for mark in (chiefs.LEAVE, chiefs.OBEY):
        mx = x + int(w * mark / 100.0)
        pygame.draw.line(r.screen, (120, 90, 70), (mx, y - 2), (mx, y + 9))


def _mood_color(value: float):
    if value < chiefs.LEAVE:
        return (220, 80, 70)
    if value < chiefs.OBEY:
        return WARN
    if value < 60:
        return (200, 190, 120)
    return GOOD


def tribe_alert(state) -> bool:
    """L'onglet Tribu s'allume quand un clan n'obeit plus ; l'onglet des
    villages, quand un village est agite."""
    if not has_nomads(state):
        from src.kora import villages

        return any(
            villages.stability(state, s) < villages.UNREST
            for s in state.sites.values()
            if s.kind == "village" and s.tribe_id == PLAYER_TRIBE_ID and villages.band_of(state, s) is not None
        )
    return any(
        b.tribe_id == PLAYER_TRIBE_ID and not chiefs.is_chief_band(state, b) and b.loyalty < chiefs.OBEY
        for b in state.bands.values()
    )


def has_nomads(state) -> bool:
    """Le peuple a encore des clans nomades (ni village, ni troupe)."""
    return any(
        b.tribe_id == PLAYER_TRIBE_ID and b.population > 0 and not b.village and b.kind != "armee"
        for b in state.bands.values()
    )


def tribe_tab_label(state) -> str:
    """Plus de nomades : l'onglet Tribu devient celui des villages."""
    if has_nomads(state):
        return "Tribu"
    n = len(sites.of_tribe(state, PLAYER_TRIBE_ID, "village"))
    if n == 0:
        return "Tribu"
    return "Village" if n == 1 else "Villages"


# --- Tribu ------------------------------------------------------------------------


def draw_tribe(r, state, layout, ui) -> None:
    title_font, head_font = _fonts(r)
    items = layout["items"]
    bx, by, bw, bh = layout["box"]
    tribe = state.tribes.get(PLAYER_TRIBE_ID)
    if tribe is None:
        return
    if tribe_tab_label(state) != "Tribu":
        draw_villages(r, state, layout, ui)
        return
    _box(r, (bx, by, bw, bh))
    color = color_of(tribe)
    pygame.draw.rect(r.screen, color, (bx, by + 10, 5, 44), border_radius=2)
    _text(r, title_font, tribe.name, TEXT, bx + 18, by + 10)
    bands = sorted(
        (b for b in state.bands.values() if b.tribe_id == PLAYER_TRIBE_ID and b.population > 0),
        key=lambda b: (not chiefs.is_chief_band(state, b), b.id),
    )
    pop = sum(b.population for b in bands)
    know = tech.bonuses(tribe)
    camps = len(sites.of_tribe(state, PLAYER_TRIBE_ID, "camp"))
    caches = len(sites.of_tribe(state, PLAYER_TRIBE_ID, "cache"))
    from src.kora.peoples import children_alive, civ_of, civ_villages

    cut = civ_villages(state, civ_of(state, tribe))
    gone = children_alive(state, PLAYER_TRIBE_ID)
    from src.kora.sim import tribe_band_count

    stats = (
        f"Prestige {tribe.prestige}  ·  {pop} personnes  ·  {tribe_band_count(state, PLAYER_TRIBE_ID)}/{max_bands_of(state, PLAYER_TRIBE_ID)} bandes"
        + (f" (-{cut} village{'s' if cut > 1 else ''}" + (f", -{gone} parti{'s' if gone > 1 else ''}" if gone else "") + ")" if cut or gone else "")
        + f"  ·  campements {camps}/{know.camps}  ·  caches {caches}/{know.caches}"
    )
    _text(r, r.tiny, stats, NOTE, bx + 18, by + 40)
    # Le chef.
    y = by + 64
    heart = chiefs.chief_band(state, PLAYER_TRIBE_ID)
    _box(r, (bx + 12, y, bw - 24, 62), fill=(22, 24, 30), edge=(60, 56, 44), radius=6)
    if heart is not None and heart.leader is not None:
        from src.kora.render import _draw_crown

        _draw_crown(r.screen, bx + 30, y + 16)
        lead = heart.leader
        _text(r, head_font, f"{lead.name}, chef de la tribu ({chiefs.age(state, lead)} ans)", TEXT, bx + 44, y + 6)
        effects = []
        names = []
        for t in lead.traits:
            trait = chiefs.TRAITS.get(t)
            if trait is None:
                continue
            names.append(trait.name)
            for line in chiefs.trait_lines(trait):
                # La bande du chef est toujours fidele : "Son clan" ne compte pas.
                if line.startswith("Son clan"):
                    continue
                line = line.replace("Chef de la tribu : ", "")
                if line not in effects:
                    effects.append(line)
        line = " · ".join(names) if names else "Sans trait particulier"
        _text(r, r.tiny, line, GOLD, bx + 44, y + 28)
        if effects:
            _text(r, r.tiny, r._fit(r.tiny, "  ;  ".join(effects), bw - 80), SOFT, bx + 44, y + 44)
    heir_band = next((b for b in bands if b.leader is not None and b.leader.pid == tribe.heir), None)
    heir = f"Heritier : {heir_band.leader.name} (clan de {heir_band.population})" if heir_band else "Heritier : aucun (le plus renomme succedera)"
    hw = r.tiny.size(heir)[0]
    _text(r, r.tiny, heir, NOTE, bx + bw - 24 - hw, y + 8)
    reach = know.chief_reach
    reach_line = f"Emprise du chef : {reach} cases"
    _text(r, r.tiny, reach_line, NOTE, bx + bw - 24 - r.tiny.size(reach_line)[0], y + 24)
    if tribe.settled_at >= 0:
        years = max(0, state.tick_count - tribe.settled_at) // 52
        since = f"depuis {years} an{'s' if years > 1 else ''}" if years else "depuis cette annee"
        settled = f"Peuple fixe {since} : les nomades s'emancipent"
        _text(r, r.tiny, settled, WARN, bx + bw - 24 - r.tiny.size(settled)[0], by + 16)
    # Les clans.
    y += 72
    cols = {"clan": bx + 20, "gens": bx + 206, "att": bx + 250, "dist": bx + 424, "act": bx + bw - 12 - 184}
    for key, label in (("clan", "Clan"), ("gens", "Gens"), ("att", "Attachement"), ("dist", "Distance")):
        _text(r, r.tiny, label, NOTE, cols[key], y)
    y += 18
    pick = ui.get("tribe_pick")
    row_h = 26
    bottom_rows = by + bh - 150
    for band in bands:
        if y + row_h > bottom_rows:
            _text(r, r.tiny, f"... et {len(bands) - bands.index(band)} autres clans", NOTE, cols["clan"], y + 4)
            y += row_h
            break
        row = (bx + 12, y, bw - 24, row_h - 2)
        chosen = band.id == pick
        if chosen or _hover(row):
            pygame.draw.rect(r.screen, (30, 34, 42) if not chosen else (40, 46, 58), row, border_radius=4)
        items[f"tribe_row:{band.id}"] = row
        is_heart = chiefs.is_chief_band(state, band)
        pygame.draw.circle(r.screen, color, (cols["clan"] + 5, y + 12), 5)
        name = band.leader.name if band.leader is not None else f"Bande {band.id}"
        if band.village:
            from src.kora import villages as _v

            site = _v.site_of(state, band)
            place = _v.name(site) if site is not None else "village"
            label = f"{place} ({name}, chef)" if is_heart else f"Village de {place}"
        elif band.kind == "armee":
            label = f"Troupe de {name}"
        else:
            label = f"{name} (chef)" if is_heart else f"Clan de {name}"
        _text(r, r.small, r._fit(r.small, label, 176), TEXT, cols["clan"] + 16, y + 4)
        _text(r, r.small, str(band.population), SOFT, cols["gens"], y + 4)
        if is_heart:
            _text(r, r.tiny, "coeur de la tribu", GOLD, cols["att"], y + 6)
        else:
            tint = _mood_color(band.loyalty)
            _loyalty_bar(r, cols["att"], y + 9, 80, band.loyalty, tint)
            if chiefs.gains_autonomy(state, band):
                fill = int(80 * min(100.0, band.autonomy) / 100.0)
                pygame.draw.rect(r.screen, (60, 40, 24), (cols["att"], y + 19, 80, 3))
                pygame.draw.rect(r.screen, WARN, (cols["att"], y + 19, fill, 3))
            _text(r, r.tiny, f"{band.loyalty:.0f} {chiefs.mood(state, band)}", tint, cols["att"] + 86, y + 5)
            if heart is not None:
                d = state.world.distance(band.position, heart.position)
                _text(r, r.tiny, f"{d} c.", WARN if d > reach else SOFT, cols["dist"], y + 5)
        ax = cols["act"]
        see = (ax, y + 2, 44, 20)
        items[f"tribe_see:{band.id}"] = see
        _button(r, see, "Voir")
        honor = (ax + 50, y + 2, 64, 20)
        why = chiefs.can_honor(state, band.id)
        items[f"tribe_honor:{band.id}"] = honor
        if _button(r, honor, "Honorer", on=not why) is False and _hover(honor) and why:
            ui.setdefault("_tips", []).append(([(why, WARN)], honor[0], honor[1] + 24))
        heir_rect = (ax + 120, y + 2, 64, 20)
        can_heir = not is_heart and band.leader is not None and tribe.heir != band.leader.pid
        items[f"tribe_heir:{band.id}"] = heir_rect
        _button(r, heir_rect, "Heritier", on=can_heir)
        y += row_h
    # Pourquoi (clan choisi).
    dy = by + bh - 140
    pygame.draw.line(r.screen, (50, 54, 60), (bx + 14, dy), (bx + bw - 14, dy))
    band = state.bands.get(pick) if pick is not None else None
    if band is None or band.tribe_id != PLAYER_TRIBE_ID or chiefs.is_chief_band(state, band):
        band = next((b for b in bands if not chiefs.is_chief_band(state, b)), None)
    if band is None:
        _text(r, r.small, "Un seul clan : la tribu suit son chef.", SOFT, bx + 18, dy + 10)
        _text(r, r.tiny, "Quand vous scindez, chaque nouveau clan a son chef de bande et son attachement.", NOTE, bx + 18, dy + 32)
        return
    who = band.leader.name if band.leader is not None else f"bande {band.id}"
    target = chiefs.loyalty_target(state, band)
    head = f"Clan de {who} : attachement {band.loyalty:.0f}, tend vers {target:.0f}"
    if chiefs.gains_autonomy(state, band):
        head = f"Clan de {who} : independance {band.autonomy:.0f} % (depart dans ~{chiefs.autonomy_months(state, band)} mois)"
    _text(r, r.small, r._fit(r.small, head, bw - 130), WARN if band.autonomy >= chiefs.AUTONOMY_WARN else TEXT, bx + 18, dy + 8)
    if band.leader is not None and band.leader.traits:
        tr = " · ".join(chiefs.TRAITS[t].name for t in band.leader.traits if t in chiefs.TRAITS)
        tw = r.tiny.size(tr)[0]
        _text(r, r.tiny, tr, GOLD, bx + bw - 20 - tw, dy + 10)
    parts = sorted(chiefs.loyalty_parts(state, band), key=lambda it: -abs(it[1]))
    parts = [p for p in parts if p[0] != "Base"]
    col_w = (bw - 36) // 2
    shown = 8 if band.notables else 10
    top = dy + 32
    if chiefs.gains_autonomy(state, band):
        # Pourquoi il s'eloigne : l'independance gagnee chaque mois.
        why = "  ;  ".join(f"{v} {label.lower()}" for label, v in chiefs.autonomy_parts(state, band))
        rate = f"{chiefs.autonomy_rate(state, band):.1f}".replace(".", ",")
        _text(r, r.tiny, r._fit(r.tiny, f"Independance {rate}/mois : {why}", bw - 36), WARN, bx + 18, top)
        top += 18
        shown -= 2
    for i, (label, value) in enumerate(parts[:shown]):
        cx = bx + 18 + (i % 2) * col_w
        cy = top + (i // 2) * 16
        _text(r, r.tiny, f"{_signed(value):>4}", GOOD if value > 0 else BAD, cx, cy)
        _text(r, r.tiny, r._fit(r.tiny, label, col_w - 44), SOFT, cx + 36, cy)
    if band.notables:
        # Les anciens (chefs des clans reunis) : on peut leur confier le clan.
        ny = dy + 32 + 4 * 16 + 2
        _text(r, r.tiny, "Anciens :", GOLD, bx + 18, ny + 3)
        nx = bx + 90
        for person in band.notables:
            label = f"{person.name} ({chiefs.age(state, person)} ans)"
            bwid = r.tiny.size(label)[0] + 16
            rect = (nx, ny, bwid, 20)
            items[f"promote:{band.id}:{person.pid}"] = rect
            _button(r, rect, label)
            if _hover(rect):
                traits = ", ".join(chiefs.TRAITS[t].name for t in person.traits if t in chiefs.TRAITS) or "sans trait"
                ui.setdefault("_tips", []).append(
                    ([(f"Lui confier le clan ({traits}, renommee {person.renown})", SOFT)], rect[0], rect[1] + 24)
                )
            nx += bwid + 6
    tip = "Obeit a 40 et plus, peut partir sous 20. Barre orange : independance (a 100, il part)."
    if tribe.settled_at < 0:
        tip = "Obeit a 40 et plus · indocile de 20 a 40 · sous 20, le clan peut partir. Le chef a 3 cases : +10 par mois."
    _text(r, r.tiny, r._fit(r.tiny, tip, bw - 36), NOTE, bx + 18, by + bh - 20)
    for lines, x, y2 in ui.pop("_tips", []):
        _tooltip(r, lines, x, y2)


# --- Villages (plus de nomades) --------------------------------------------------


def _chief_card(r, state, tribe, rect, head_font) -> None:
    """Le chef du peuple : nom, age, traits et leurs effets."""
    x, y, w, h = rect
    _box(r, rect, fill=(22, 24, 30), edge=(60, 56, 44), radius=6)
    heart = chiefs.chief_band(state, tribe.id)
    if heart is None or heart.leader is None:
        _text(r, r.small, "Pas de chef.", SOFT, x + 14, y + 8)
        return
    from src.kora.render import _draw_crown

    _draw_crown(r.screen, x + 18, y + 16)
    lead = heart.leader
    where = ""
    if heart.village:
        from src.kora import villages

        site = villages.site_of(state, heart)
        where = f", gouverne {villages.name(site)}" if site is not None else ""
    _text(r, head_font, r._fit(head_font, f"{lead.name}, chef du peuple ({chiefs.age(state, lead)} ans){where}", w - 44), TEXT, x + 32, y + 6)
    names, effects = [], []
    for t in lead.traits:
        trait = chiefs.TRAITS.get(t)
        if trait is None:
            continue
        names.append(trait.name)
        for line in chiefs.trait_lines(trait):
            if line.startswith("Son clan"):
                continue
            line = line.replace("Chef de la tribu : ", "")
            if line not in effects:
                effects.append(line)
    _text(r, r.tiny, " · ".join(names) if names else "Sans trait particulier", GOLD, x + 32, y + 28)
    if effects:
        _text(r, r.tiny, r._fit(r.tiny, "  ;  ".join(effects), w - 44), SOFT, x + 32, y + 44)


def draw_villages(r, state, layout, ui) -> None:
    """Le peuple n'a plus de nomades : ses villages, leur stabilite, leurs
    greniers, leurs metiers ; la reserve du peuple et ses echanges."""
    from src.kora import diplo as _diplo
    from src.kora import goods, villages

    title_font, head_font = _fonts(r)
    items = layout["items"]
    bx, by, bw, bh = layout["box"]
    tribe = state.tribes[PLAYER_TRIBE_ID]
    _box(r, (bx, by, bw, bh))
    color = color_of(tribe)
    pygame.draw.rect(r.screen, color, (bx, by + 10, 5, 44), border_radius=2)
    homes = [
        (s, villages.band_of(state, s))
        for s in sorted(state.sites.values(), key=lambda s: s.id)
        if s.kind == "village" and s.tribe_id == PLAYER_TRIBE_ID and villages.band_of(state, s) is not None
    ]
    _text(r, title_font, f"Les villages des {tribe.name}", TEXT, bx + 18, by + 10)
    pop = sum(b.population for b in state.bands.values() if b.tribe_id == PLAYER_TRIBE_ID and b.population > 0)
    troops = sum(b.population for b in state.bands.values() if b.tribe_id == PLAYER_TRIBE_ID and b.kind == "armee")
    know = tech.bonuses(tribe)
    stats = f"Prestige {tribe.prestige}  ·  {pop} personnes  ·  villages {len(homes)}/{know.villages}  ·  {troops} sous les armes"
    _text(r, r.tiny, stats, NOTE, bx + 18, by + 40)
    y = by + 60
    _chief_card(r, state, tribe, (bx + 12, y, bw - 24, 62), head_font)
    y += 72
    cols = {"nom": bx + 20, "gens": bx + 210, "stab": bx + 256, "grenier": bx + 424, "act": bx + bw - 12 - 110}
    for key, label in (("nom", "Village"), ("gens", "Gens"), ("stab", "Stabilite"), ("grenier", "Grenier")):
        _text(r, r.tiny, label, NOTE, cols[key], y)
    y += 18
    row_h = 40
    bottom = by + bh - 150
    for site, band in homes:
        if y + row_h > bottom:
            _text(r, r.tiny, "... et d'autres villages", NOTE, cols["nom"], y + 4)
            break
        row = (bx + 12, y, bw - 24, row_h - 4)
        if _hover(row):
            pygame.draw.rect(r.screen, (30, 34, 42), row, border_radius=4)
        items[f"vil_row:{site.id}"] = row
        is_heart = chiefs.is_chief_band(state, band)
        r.draw_village_icon(site, cols["nom"] + 5, y + 12, color, 6)
        label = villages.name(site) + (" (le chef)" if is_heart else "")
        _text(r, r.small, r._fit(r.small, label, 170), TEXT, cols["nom"] + 16, y + 3)
        _text(r, r.small, str(band.population), SOFT, cols["gens"], y + 3)
        stab = villages.stability(state, site, band)
        tint = GOOD if stab >= 50 else WARN if stab >= villages.UNREST else BAD
        _loyalty_bar(r, cols["stab"], y + 9, 80, stab, tint)
        _text(r, r.tiny, f"{stab:.0f} {villages.stability_word(stab)}", tint, cols["stab"] + 86, y + 5)
        weeks = band.stock / max(1, band.population)
        _left, margin = villages.food_outlook(state, site, band)
        grain = f"{weeks:.0f} sem." + ("  disette en vue" if margin < 0 else "")
        _text(r, r.tiny, grain, BAD if margin < 0 else GOOD if weeks >= 8 else WARN, cols["grenier"], y + 5)
        # Seconde ligne : rang, metiers, chantier.
        crafts = ", ".join(f"{goods.CRAFTS[c].name.lower()} {n}" for c, n in sorted(goods.teams(site).items()) if n)
        job = villages.works(site)
        work = f"chantier : {villages.BUILDINGS[job[0]].name.lower()} ({job[1]} sem.)" if job else "pas de chantier"
        second = f"{villages.rank_name(band.population)}  ·  {crafts or 'aucun metier'}  ·  {work}"
        _text(r, r.tiny, r._fit(r.tiny, second, cols["act"] - cols["nom"] - 24), NOTE, cols["nom"] + 16, y + 20)
        see = (cols["act"], y + 7, 44, 20)
        items[f"vil_see:{site.id}"] = see
        _button(r, see, "Voir")
        opn = (cols["act"] + 50, y + 7, 58, 20)
        items[f"vil_open:{site.id}"] = opn
        _button(r, opn, "Ouvrir")
        y += row_h
    # En bas : la reserve du peuple et les echanges.
    dy = by + bh - 140
    pygame.draw.line(r.screen, (50, 54, 60), (bx + 14, dy), (bx + bw - 14, dy))
    _text(r, r.small, "Reserve du peuple", TEXT, bx + 18, dy + 8)
    need = goods.need(state, PLAYER_TRIBE_ID)
    col_w = (bw - 36) // 2
    for i, good in enumerate(goods.GOODS):
        cx = bx + 18 + (i % 2) * col_w
        cy = dy + 32 + (i // 2) * 18
        have = goods.stock(state, PLAYER_TRIBE_ID, good)
        ok = goods.supplied(state, PLAYER_TRIBE_ID, good)
        made = goods.made(state, PLAYER_TRIBE_ID, good)
        made_s = f"{made:.1f}".replace(".", ",")
        line = f"{goods.GOOD_NAMES[good]} : {have:.0f}" + (f" (+{made_s}/sem.)" if made else "") + ("  pourvu" if ok else "  en manque")
        _text(r, r.tiny, r._fit(r.tiny, line, col_w - 8), GOOD if ok else NOTE, cx, cy)
    partners = [o for o in sorted(state.tribes) if o != PLAYER_TRIBE_ID and _diplo.has_pact(state, PLAYER_TRIBE_ID, o, "commerce")]
    ty = dy + 32 + 2 * 18 + 6
    if partners:
        names = ", ".join(state.tribes[o].name for o in partners[:4]) + ("..." if len(partners) > 4 else "")
        text = f"Accords commerciaux : {names}. Detail dans l'ecran d'un village (Metiers et echanges)."
    else:
        text = "Aucun accord commercial : proposez-en un dans Peuples (il faut Echanges lointains)."
    _text(r, r.tiny, r._fit(r.tiny, text, bw - 36), SOFT, bx + 18, ty)
    _text(r, r.tiny, r._fit(r.tiny, f"Besoin : {need:.1f} de chaque bien par semaine (tous vos villages). Metiers : ecran du village.".replace(".", ",", 1), bw - 36), NOTE, bx + 18, ty + 16)
    tip = "Plus de nomades : le peuple vit dans ses villages."
    _text(r, r.tiny, r._fit(r.tiny, tip, bw - 36), NOTE, bx + 18, by + bh - 20)


# --- Peuples ---------------------------------------------------------------------------


def known_peoples(state) -> list[int]:
    from src.kora.peoples import living_tribe_ids

    alive = living_tribe_ids(state)
    out = [t for t in diplo.contacts_of(state, PLAYER_TRIBE_ID) if t in alive]
    out.sort(key=lambda t: (not diplo.allied(state, PLAYER_TRIBE_ID, t), -diplo.relation(state, PLAYER_TRIBE_ID, t), t))
    return out


def _rel_color(rel: float):
    if rel <= -50:
        return (225, 90, 80)
    if rel <= -15:
        return (225, 140, 100)
    if rel < 15:
        return (200, 196, 170)
    if rel < 50:
        return (160, 210, 140)
    return (110, 220, 150)


def _relation_meter(r, x, y, w, rel):
    steps = 40
    for i in range(steps):
        t = i / (steps - 1)
        v = -100 + 200 * t
        c = _rel_color(v)
        c = tuple(int(ch * 0.55) for ch in c)
        pygame.draw.rect(r.screen, c, (x + int(w * i / steps), y, int(w / steps) + 1, 10))
    pygame.draw.rect(r.screen, (80, 84, 92), (x, y, w, 10), 1)
    mid = x + w // 2
    pygame.draw.line(r.screen, (120, 124, 132), (mid, y - 3), (mid, y + 12))
    px = x + int(w * (rel + 100) / 200)
    pygame.draw.polygon(r.screen, (245, 240, 225), [(px, y - 2), (px - 6, y - 10), (px + 6, y - 10)])
    pygame.draw.polygon(r.screen, (245, 240, 225), [(px, y + 12), (px - 6, y + 20), (px + 6, y + 20)])


def _verdict_line(v: diplo.Verdict) -> tuple[str, tuple]:
    if v.blocked:
        return v.blocked, NOTE
    if v.accepted:
        return f"Ils accepteraient ({_signed(v.score)})", GOOD
    return f"Ils refuseraient ({_signed(v.score)})", BAD


def draw_peoples(r, state, layout, ui) -> None:
    title_font, head_font = _fonts(r)
    items = layout["items"]
    bx, by, bw, bh = layout["box"]
    _box(r, (bx, by, bw, bh))
    _text(r, title_font, "Peuples", TEXT, bx + 16, by + 10)
    peoples = known_peoples(state)
    if not peoples:
        _text(r, r.small, "Vous ne connaissez encore aucun autre peuple.", SOFT, bx + 18, by + 56)
        _text(r, r.tiny, "Explorez : a 16 cases d'une de leurs bandes, vous les rencontrez.", NOTE, bx + 18, by + 78)
        return
    pick = ui.get("people_pick")
    if pick not in peoples:
        pick = peoples[0]
        ui["people_pick"] = pick
    # Liste a gauche.
    lx, ly, lw = bx + 12, by + 46, 250
    row_h = 46
    for tid in peoples:
        if ly + row_h > by + bh - 10:
            break
        t = state.tribes[tid]
        row = (lx, ly, lw, row_h - 4)
        items[f"people:{tid}"] = row
        chosen = tid == pick
        fill = (40, 46, 58) if chosen else (30, 34, 42) if _hover(row) else (22, 24, 30)
        pygame.draw.rect(r.screen, fill, row, border_radius=6)
        if chosen:
            pygame.draw.rect(r.screen, GOLD, row, 1, border_radius=6)
        pygame.draw.circle(r.screen, color_of(t), (lx + 16, ly + 20), 8)
        pygame.draw.circle(r.screen, (20, 20, 20), (lx + 16, ly + 20), 8, 1)
        _text(r, r.small, r._fit(r.small, t.name, 120), TEXT, lx + 32, ly + 5)
        nv = len(sites.of_tribe(state, tid, "village"))
        second = f"proto-pays, {nv} village{'s' if nv > 1 else ''}" if nv else label_of(t)
        _text(r, r.tiny, r._fit(r.tiny, second, 130), GOLD if nv else NOTE, lx + 32, ly + 23)
        rel = diplo.relation(state, PLAYER_TRIBE_ID, tid)
        lvl = diplo.level(state, PLAYER_TRIBE_ID, tid)
        val = _signed(rel)
        vw = r.small.size(val)[0]
        _text(r, r.small, val, _rel_color(rel), lx + lw - 10 - vw, ly + 5)
        lw2 = r.tiny.size(lvl)[0]
        _text(r, r.tiny, lvl, _rel_color(rel), lx + lw - 10 - lw2, ly + 23)
        ly += row_h
    # Fiche a droite.
    cx = lx + lw + 14
    cw = bx + bw - 12 - cx
    t = state.tribes[pick]
    cy = by + 46
    color = color_of(t)
    _box(r, (cx, cy, cw, 74), fill=(24, 26, 32), edge=(60, 64, 72), radius=8)
    pygame.draw.rect(r.screen, color, (cx, cy, 8, 74), border_top_left_radius=8, border_bottom_left_radius=8)
    _text(r, title_font, t.name, TEXT, cx + 20, cy + 6)
    nb = sum(1 for b in state.bands.values() if b.tribe_id == pick and b.population > 0)
    pop = diplo.pop_of(state, pick)
    approx = max(10, int(round(pop / 10.0)) * 10)
    culture = label_of(t)
    origin = ""
    if t.origin and t.origin in state.tribes:
        origin = f"  ·  issus des {state.tribes[t.origin].name}" if t.origin != PLAYER_TRIBE_ID else "  ·  issus de votre peuple"
    from src.kora.peoples import civ_name, civ_of

    civ = civ_of(state, t)
    if civ == civ_of(state, state.tribes[PLAYER_TRIBE_ID]):
        culture += "  ·  votre civilisation"
    elif civ != t.id:
        culture += f"  ·  civilisation des {civ_name(state, civ)}"
    homes = sites.of_tribe(state, pick, "village")
    if homes:
        names_v = ", ".join(s.name for s in homes[:3] if s.name) + ("..." if len(homes) > 3 else "")
        polity = f"Proto-pays : {len(homes)} village{'s' if len(homes) > 1 else ''} ({names_v})"
        pw = r.tiny.size(polity)[0]
        _text(r, r.tiny, polity, GOLD, cx + cw - 110 - pw, cy + 12)
    _text(r, r.tiny, r._fit(r.tiny, f"{culture}  ·  ~{approx} personnes  ·  {nb} bande{'s' if nb > 1 else ''}{origin}", cw - 40), SOFT, cx + 22, cy + 34)
    lead = chiefs.chief_of(state, pick)
    if lead is not None:
        _text(r, r.tiny, r._fit(r.tiny, "Chef : " + chiefs.describe(state, lead), cw - 40), GOLD, cx + 22, cy + 52)
    see = (cx + cw - 96, cy + 8, 84, 22)
    items["people_see"] = see
    _button(r, see, "Voir")
    # Relation.
    cy += 86
    rel = diplo.relation(state, PLAYER_TRIBE_ID, pick)
    lvl = diplo.level(state, PLAYER_TRIBE_ID, pick)
    _text(r, head_font, f"Relation : {_signed(rel)}  ·  {lvl}", _rel_color(rel), cx + 4, cy)
    status = diplo.status_line(state, PLAYER_TRIBE_ID, pick)
    if status:
        sw_ = r.small.size(status)[0]
        _text(r, r.small, status, GOLD, cx + cw - sw_ - 4, cy + 2)
    _relation_meter(r, cx + 10, cy + 34, cw - 20, rel)
    cy += 62
    reasons = diplo.reasons(state, PLAYER_TRIBE_ID, pick)
    _text(r, r.tiny, "Pourquoi :", NOTE, cx + 4, cy)
    cy += 16
    half = (cw - 8) // 2
    if not reasons:
        _text(r, r.tiny, "Rien de particulier : vous vous connaissez a peine.", SOFT, cx + 12, cy)
        cy += 16
    for i, (label, value) in enumerate(reasons[:8]):
        x = cx + 8 + (i % 2) * half
        y = cy + (i // 2) * 16
        _text(r, r.tiny, f"{_signed(value):>4}", GOOD if value > 0 else BAD, x, y)
        _text(r, r.tiny, r._fit(r.tiny, label, half - 46), SOFT, x + 38, y)
    cy += 16 * ((min(8, len(reasons)) + 1) // 2) + 8
    # Savoirs a apprendre d'eux.
    mine = state.tribes[PLAYER_TRIBE_ID].knowledge
    theirs = sorted(t.knowledge - mine, key=lambda k: (tech.TECHS[k].tier, k))
    teach = pick in getattr(state.diplo, "neighbors", {}).get(PLAYER_TRIBE_ID, [])
    if theirs:
        names = ", ".join(tech.TECHS[k].name for k in theirs[:6]) + ("..." if len(theirs) > 6 else "")
        _text(r, r.tiny, r._fit(r.tiny, "Ils savent : " + names, cw - 8), SOFT, cx + 4, cy)
        cy += 16
        note = (
            "Voisins en bons termes : ces savoirs s'apprennent plus vite chez vous."
            if teach
            else "Trop loin ou trop hostiles pour que leurs savoirs passent chez vous."
        )
        _text(r, r.tiny, note, GOOD if teach else NOTE, cx + 4, cy)
        cy += 22
    # Leurs rapports avec les autres peuples que vous connaissez.
    ties = []
    for other in known_peoples(state):
        if other == pick or not diplo.in_contact(state, pick, other):
            continue
        if diplo.allied(state, pick, other):
            ties.append(f"allies des {state.tribes[other].name}")
        elif diplo.has_pact(state, pick, other, "commerce"):
            ties.append(f"commercent avec les {state.tribes[other].name}")
        elif diplo.has_pact(state, pick, other):
            ties.append(f"en treve avec les {state.tribes[other].name}")
        elif diplo.relation(state, pick, other) <= -50:
            ties.append(f"ennemis des {state.tribes[other].name}")
    if ties:
        _text(r, r.tiny, r._fit(r.tiny, "Avec les autres : " + ", ".join(ties), cw - 8), SOFT, cx + 4, cy)
        cy += 20
    if diplo.has_pact(state, PLAYER_TRIBE_ID, pick, "commerce"):
        from src.kora import goods

        n = sum(1 for rt in goods.routes_of(state, PLAYER_TRIBE_ID) if pick in (rt.exporter, rt.importer))
        done = goods.summary(state, PLAYER_TRIBE_ID, pick)
        line = f"Routes : {n}" + (" · le mois dernier : " + done if done else " · rien porte le mois dernier")
        if goods.trade_distance(state, PLAYER_TRIBE_ID, pick) > goods.trade_range(state, PLAYER_TRIBE_ID, pick):
            line = "Commerce : vos villages sont trop loin l'un de l'autre"
        button = (cx + cw - 190, cy - 3, 186, 20)
        items["trade_with"] = button
        _button(r, button, "Routes commerciales [M]")
        _text(r, r.tiny, r._fit(r.tiny, line, cw - 200), GOLD if done else NOTE, cx + 4, cy)
        cy += 22
    # Actions : les vivres sur une ligne, puis les propositions.
    tips = []
    verdict = diplo.evaluate(state, PLAYER_TRIBE_ID, pick, "cadeau")
    _text(r, r.small, diplo.ACTION_LABELS["cadeau"], TEXT if not verdict.blocked else NOTE, cx + 4, cy + 3)
    sizes = diplo.gift_sizes(state, PLAYER_TRIBE_ID, pick) if not verdict.blocked else []
    gx = cx + 160
    for amount in diplo.GIFT_SIZES:
        rect = (gx, cy, 50, 22)
        items[f"gift:{amount}"] = rect
        on = amount in sizes
        _button(r, rect, str(amount), on=on)
        if on and _hover(rect):
            gain = diplo.gift_value(state, PLAYER_TRIBE_ID, pick, amount)
            tips.append(([(f"{amount} vivres, portes par votre bande la plus proche", TEXT), (f"Relation : +{gain:.0f}", GOOD)], rect[0] + rect[2] + 8, rect[1]))
        gx += 56
    if verdict.blocked:
        note = verdict.blocked
    elif not sizes:
        note = "Votre bande la plus proche n'a pas assez de vivres"
    else:
        note = "Toujours accepte"
    _text(r, r.tiny, r._fit(r.tiny, note, cx + cw - gx - 4), NOTE if verdict.blocked or not sizes else GOOD, gx + 4, cy + 5)
    cy += 34
    cols = 2
    aw = (cw - 12) // cols
    ah = 46
    for i, action in enumerate(["treve", "alliance", "commerce", "tribut", "union", "rompre"]):
        ax = cx + (i % cols) * (aw + 12)
        ay = cy + (i // cols) * ah
        if ay + ah > by + bh - 6:
            break
        verdict = diplo.evaluate(state, PLAYER_TRIBE_ID, pick, action)
        wait = diplo.on_cooldown(state, PLAYER_TRIBE_ID, pick, action) if action != "rompre" else 0
        line, tint = _verdict_line(verdict)
        if wait and not verdict.blocked:
            line, tint = f"Deja propose : attendez {wait} sem.", NOTE
        rect = (ax, ay, min(190, aw - 4), 22)
        items[f"diplo:{action}"] = rect
        on = not verdict.blocked and not wait
        _button(r, rect, diplo.ACTION_LABELS[action], on=on)
        _text(r, r.tiny, r._fit(r.tiny, line, aw - 6), tint, ax + 2, ay + 26)
        if _hover(rect) and verdict.reasons:
            rows = [(f"{_signed(v):>4}  {label}", GOOD if v > 0 else BAD if v < 0 else SOFT) for label, v in verdict.reasons]
            if action != "rompre":
                rows.append((f"Total : {_signed(verdict.score)} (il faut plus de 0)", TEXT))
            tips.append((rows, rect[0] + rect[2] + 10, rect[1] - 4))
    # Clans de ce peuple qui se detachent, pres de chez vous.
    iy = cy + 3 * ah + 4
    for band in diplo.invitable(state, PLAYER_TRIBE_ID, pick)[:2]:
        if iy + 26 > by + bh - 6:
            break
        who = band.leader.name if band.leader else f"bande {band.id}"
        chance = round(100 * diplo.invite_chance(state, PLAYER_TRIBE_ID, band))
        line = f"Clan de {who} ({band.population}) : attachement {band.loyalty:.0f}, il se detache de son chef"
        _text(r, r.tiny, r._fit(r.tiny, line, cw - 200), WARN, cx + 4, iy + 5)
        rect = (cx + cw - 190, iy, 186, 22)
        items[f"invite:{band.id}"] = rect
        on = state.tribes[PLAYER_TRIBE_ID].prestige >= diplo.INVITE_COST
        _button(r, rect, f"Inviter ({diplo.INVITE_COST} prest., ~{chance} %)", on=on)
        iy += 28
    for rows, x, y in tips:
        _tooltip(r, rows, x, y)


# --- evenements -------------------------------------------------------------------------


def draw_event_cards(r, state, ui) -> None:
    """Cartes "A decider" a gauche (voir events.py) ; rien s'il n'y en a pas."""
    r.event_hits = {}
    from src.kora import events

    pending = events.pending(state)
    if not pending:
        return
    w, h = r.screen.get_size()
    x, y = 10, 48 + 110
    for inst in pending[:5]:
        ev = events.EVENTS.get(inst.event_id)
        if ev is None:
            continue
        left = max(0, inst.deadline - state.tick_count)
        rect = (x, y, 270, 40)
        r.event_hits[inst.uid] = rect
        glow = (state.tick_count + inst.uid) % 2 == 0
        _box(r, rect, fill=(30, 26, 20) if _hover(rect) else (24, 22, 18), edge=GOLD if glow else (150, 120, 60), radius=6)
        _text(r, r.small, r._fit(r.small, ev.title, 250), (240, 220, 170), x + 10, y + 4)
        _text(r, r.tiny, f"A decider  ·  encore {left} sem.  ·  [E]", NOTE, x + 10, y + 22)
        y += 46


def event_modal_layout(width: int, height: int, n_options: int, text_lines: int = 4) -> dict:
    bw = min(660, width - 80)
    bh = min(height - 70, 54 + 19 * text_lines + 44 + 60 * n_options + 12)
    bx = (width - bw) // 2
    by = max(52, (height - bh) // 2)
    options = {}
    oy = by + bh - 12 - 60 * n_options
    for i in range(n_options):
        options[i] = (bx + 20, oy + i * 60, bw - 40, 54)
    close = (bx + bw - 110, by + 12, 96, 24)
    return {"box": (bx, by, bw, bh), "options": options, "close": close}


def draw_event_modal(r, state, ui) -> None:
    from src.kora import events
    from src.kora.render import wrap_text

    uid = ui.get("event_open")
    inst = events.find(state, uid)
    if inst is None:
        return
    ev = events.EVENTS.get(inst.event_id)
    if ev is None:
        return
    title_font, head_font = _fonts(r)
    w, h = r.screen.get_size()
    shade = pygame.Surface((w, h), pygame.SRCALPHA)
    shade.fill((6, 8, 12, 150))
    r.screen.blit(shade, (0, 0))
    opts = events.options_for(state, inst)
    text = events.text_for(state, inst)
    cols = max(40, (min(660, w - 80) - 40) // 8)
    lines = [line for para in text.split("\n") for line in wrap_text(para, cols)]
    lay = event_modal_layout(w, h, len(opts), len(lines))
    r.event_hits = {"modal": lay}
    bx, by, bw, bh = lay["box"]
    _box(r, (bx, by, bw, bh), fill=(22, 20, 17), edge=GOLD, radius=10, width=2)
    pygame.draw.rect(r.screen, events.MOOD_COLORS.get(ev.mood, GOLD), (bx + 2, by + 2, bw - 4, 6), border_radius=4)
    _text(r, title_font, ev.title, (245, 228, 185), bx + 20, by + 16)
    _button(r, lay["close"], "Plus tard")
    yy = by + 54
    for line in lines:
        _text(r, r.small, line, (225, 218, 200), bx + 20, yy)
        yy += 19
    yy += 6
    left = max(0, inst.deadline - state.tick_count)
    _text(r, r.tiny, f"Sans reponse dans {left} semaines, le choix par defaut sera fait.", NOTE, bx + 20, yy + 2)
    tips = []
    for i, opt in enumerate(opts):
        rect = lay["options"][i]
        on = not opt["blocked"]
        hover = on and _hover(rect)
        fill = (60, 48, 30) if hover else (34, 32, 28) if on else (26, 26, 26)
        pygame.draw.rect(r.screen, fill, rect, border_radius=6)
        pygame.draw.rect(r.screen, GOLD if on else (70, 70, 70), rect, 1, border_radius=6)
        _text(r, r.small, r._fit(r.small, opt["label"], rect[2] - 20), TEXT if on else (120, 120, 120), rect[0] + 12, rect[1] + 6)
        summary = opt["blocked"] or opt["summary"]
        _text(r, r.tiny, r._fit(r.tiny, summary, rect[2] - 20), NOTE if opt["blocked"] else (200, 196, 170), rect[0] + 12, rect[1] + 28)
        if hover and opt["details"]:
            rows = [(line, SOFT) for line in opt["details"]]
            tw = max(r.tiny.size(t)[0] for t, _c in rows) + 18
            if bx + bw + 8 + tw <= w:
                # A droite de la fenetre : on ne cache ni le texte ni les options.
                tips.append((rows, bx + bw + 8, rect[1]))
            elif bx - 8 - tw >= 0:
                tips.append((rows, bx - 8 - tw, rect[1]))
            else:
                tips.append((rows, rect[0] + 20, rect[1] - 12 - 16 * len(rows)))
    for rows, x, y in tips:
        _tooltip(r, rows, x, y)


# --- Armee ------------------------------------------------------------------------------
# L'onglet apparait avec le premier village : on y leve une compagnie par
# village (type, taille) et l'on suit toutes ses troupes.


LEVY_SHORT = {"poignee": "Poignee", "troupe": "Troupe", "masse": "Masse"}


def commerce_ready(state) -> bool:
    """L'onglet Commerce vient avec le premier village."""
    return bool(sites.of_tribe(state, PLAYER_TRIBE_ID, "village"))


def commerce_alert(state) -> bool:
    """L'onglet s'allume quand une route du joueur, ouverte par lui, ne porte
    plus rien."""
    from src.kora import goods

    return any(r.by == PLAYER_TRIBE_ID and r.idle >= 2 for r in goods.routes_of(state, PLAYER_TRIBE_ID))


def army_ready(state) -> bool:
    tribe = state.tribes.get(PLAYER_TRIBE_ID)
    if tribe is None:
        return False
    if sites.of_tribe(state, PLAYER_TRIBE_ID, "village"):
        return True
    return any(b.tribe_id == PLAYER_TRIBE_ID and b.kind == "armee" for b in state.bands.values())


def draw_army(r, state, layout, ui) -> None:
    from src.kora import units, villages

    title_font, head_font = _fonts(r)
    items = layout["items"]
    bx, by, bw, bh = layout["box"]
    tribe = state.tribes.get(PLAYER_TRIBE_ID)
    if tribe is None:
        return
    _box(r, (bx, by, bw, bh))
    pygame.draw.rect(r.screen, color_of(tribe), (bx, by + 10, 5, 44), border_radius=2)
    _text(r, title_font, "Armee", TEXT, bx + 18, by + 10)
    troops = sorted((b for b in state.bands.values() if b.tribe_id == PLAYER_TRIBE_ID and b.kind == "armee"), key=lambda b: b.id)
    homes = sites.of_tribe(state, PLAYER_TRIBE_ID, "village")
    men = sum(b.population for b in troops)
    comps = sum(len(units.normalize(b)) for b in troops)
    _text(r, r.tiny, f"{comps} compagnie{'s' if comps > 1 else ''} sous les armes  ·  {men} guerriers  ·  {len(homes)} village{'s' if len(homes) > 1 else ''}", NOTE, bx + 18, by + 40)
    tips = []
    y = by + 64
    _text(r, r.tiny, "LEVER DANS VOS VILLAGES", GOLD, bx + 18, y)
    pygame.draw.line(r.screen, (60, 56, 44), (bx + 14, y + 16), (bx + bw - 14, y + 16))
    y += 24
    roles = ui.setdefault("army_role", {})
    sizes = ui.setdefault("army_size", {})
    block_h = 84
    max_blocks = max(1, (bh - 250) // block_h)
    for site in homes[:max_blocks]:
        home = villages.band_of(state, site)
        if home is None:
            continue
        _box(r, (bx + 12, y, bw - 24, block_h - 6), fill=(22, 24, 30), edge=(60, 56, 44), radius=6)
        name_rect = (bx + 20, y + 5, 150, 20)
        items[f"avillage:{site.id}"] = name_rect
        _button(r, name_rect, villages.name(site))
        info = f"{home.population} habitants  ·  compagnies {villages.companies_of(state, site)}/{villages.army_cap(state, site)}"
        _text(r, r.tiny, info, SOFT, bx + 180, y + 8)
        role = roles.get(site.id, "melee")
        cw = (bw - 40 - 3 * 6) // 4
        for i, rl in enumerate(units.ROLES):
            rect = (bx + 20 + i * (cw + 6), y + 30, cw, 20)
            u = units.best(tribe, rl)
            label = u.short if u else f"{units.ROLE_LABEL[rl]} : verrouille"
            items[f"arole:{site.id}:{rl}"] = rect
            _button(r, rect, label, on=u is not None, active=rl == role and u is not None)
            if _hover(rect):
                if u is None:
                    first = units.ages_of(rl)[0]
                    need = tech.TECHS[first.needs].name if first.needs else "?"
                    tips.append(([(first.name, TEXT), (f"Il faut connaitre {need}", BAD)], rect[0], rect[1] + 24))
                else:
                    tips.append(([(u.name, TEXT), (u.text, SOFT)], rect[0], rect[1] + 24))
        key = sizes.get(site.id, "troupe")
        sx = bx + 20
        for k, _share, _label in villages.LEVIES:
            n = villages.levy_size(home, villages.LEVY_SHARE[k])
            rect = (sx, y + 54, 90, 20)
            items[f"asize:{site.id}:{k}"] = rect
            _button(r, rect, f"{LEVY_SHORT[k]} {n}", active=k == key)
            sx += 96
        kind = units.best(tribe, role) or units.best(tribe, "melee")
        share = villages.LEVY_SHARE.get(key, villages.LEVY_SHARE["troupe"])
        why = villages.army_block(state, home.id, share, kind.id) or ("" if chiefs.obeys(state, home) else "Ce clan n'obeit plus")
        raise_rect = (sx + 6, y + 52, 120, 24)
        items[f"araise:{site.id}"] = raise_rect
        _button(r, raise_rect, "Lever [L]", on=not why)
        if why:
            _text(r, r.tiny, r._fit(r.tiny, why, bx + bw - 24 - (raise_rect[0] + 128)), WARN, raise_rect[0] + 128, y + 57)
        y += block_h
    if len(homes) > max_blocks:
        _text(r, r.tiny, f"... et {len(homes) - max_blocks} autres villages (ecran du village)", NOTE, bx + 20, y)
        y += 18
    y += 6
    _text(r, r.tiny, "VOS TROUPES", GOLD, bx + 18, y)
    pygame.draw.line(r.screen, (60, 56, 44), (bx + 14, y + 16), (bx + bw - 14, y + 16))
    y += 24
    if not troops:
        _text(r, r.tiny, "Aucune troupe. Levez une compagnie dans un village.", NOTE, bx + 20, y)
    bottom = by + bh - 28
    for army in troops:
        if y + 42 > bottom:
            _text(r, r.tiny, f"... et {len(troops) - troops.index(army)} autres", NOTE, bx + 20, y)
            break
        lead = army.leader.name if army.leader else "?"
        home = villages.home_of(state, army)
        where = villages.name(home) if home is not None else "sans village"
        d = state.world.distance(home.hex, army.position) if home is not None else 0
        status = "rentre" if army.homebound else ("au village" if home is not None and d <= villages.ARMY_HOME else f"a {d} cases de {where}")
        _text(r, r.small, r._fit(r.small, f"{lead} · {army.population} guerriers · {status}", bw - 200), TEXT, bx + 20, y)
        comp = " · ".join(f"{m} {units.UNITS[t].short if t in units.UNITS else t}" for t, m, _h in units.normalize(army))
        _text(r, r.tiny, r._fit(r.tiny, comp, bw - 200), SOFT, bx + 20, y + 20)
        see = (bx + bw - 12 - 164, y + 4, 70, 20)
        items[f"asee:{army.id}"] = see
        _button(r, see, "Voir")
        dis = (bx + bw - 12 - 88, y + 4, 88, 20)
        items[f"adissolve:{army.id}"] = dis
        on = not villages.dissolve_block(state, army.id)
        _button(r, dis, "Dissoudre", on=on)
        if _hover(dis):
            tips.append(([("Chaque compagnie rentre a pied a son village", SOFT)], dis[0] - 120, dis[1] + 24))
        y += 44
    tip = "Dissoute, une compagnie rentre a pied a son village. Les savoirs apportent de nouveaux types d'unites."
    _text(r, r.tiny, r._fit(r.tiny, tip, bw - 36), NOTE, bx + 18, by + bh - 20)
    for lines, x, y2 in tips:
        _tooltip(r, lines, x, y2)
