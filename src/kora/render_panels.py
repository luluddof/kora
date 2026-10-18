"""Panneaux Tribu (chef, clans, attachement) et Peuples (diplomatie),
cartes d'evenements.

Les rectangles cliquables sont enregistres pendant le dessin dans
layout["items"] (comme les lignes du journal) ; app.py lit side_hit.
"""

from __future__ import annotations

import pygame

from src.kora import (
    chiefs,
    diplo,
    diplo as _diplo,
    events,
    goods,
    influence,
    money,
    places,
    sites,
    tech,
    theme,
    villages as _v,
    villages,
)
from src.kora.peoples import civ_of, color_of
from src.kora.bands import civ_band_cap, civ_band_count, max_bands_of, tribe_band_count

from src.kora.theme import C
from src.kora.layout import (  # noqa: F401
    panel_box,
)
from src.kora.layout import HUD_HEIGHT
from src.kora import batiments
from src.kora import guerre

# L'icone d'un evenement : un mot de son nom, sinon son humeur.
EVENT_WORDS = (
    ("fievre", "epidemie"), ("mal", "epidemie"), ("loup", "loup"), ("ours", "danger"), ("hiver", "froid"),
    ("neige", "froid"), ("froid", "froid"), ("feu", "feu"), ("incendie", "incendie"), ("crue", "inondation"),
    ("seche", "secheresse"), ("chasse", "chasse"), ("gibier", "cerf"), ("troupeau", "troupeau"), ("bison", "bison"),
    ("mammouth", "mammouth"), ("peche", "peche"), ("poisson", "peche"), ("baie", "baies"), ("champignon", "champignon"),
    ("herbe", "herbes"), ("semence", "ble"), ("recolte", "ble"), ("grenier", "grenier"), ("village", "village"),
    ("offre", "peuples"), ("tribut", "balance"), ("contact", "peuples"), ("etranger", "peuples"), ("mariage", "couronne"),
    ("chef", "chef"), ("succession", "chef"), ("clan", "tribu"), ("cache", "cache"), ("camp", "camp"),
    ("esprit", "totem"), ("reve", "totem"), ("ancetre", "dolmen"), ("pierre", "menhir"), ("colporteur", "commerce"),
    ("marchand", "commerce"), ("porteur", "route"), ("route", "route"), ("raid", "combat"), ("guerre", "combat"),
)
MOOD_ICONS = {"chance": "collier", "danger": "danger", "esprit": "totem", "peuple": "peuples", "neutre": "feu"}
MOOD_STATE = {"danger": "danger", "chance": "connu", "esprit": "actif"}


def event_icon(ev) -> str:
    name = ev.id.lower()
    for word, key in EVENT_WORDS:
        if word in name:
            return key
    return MOOD_ICONS.get(ev.mood, "evenement")

# Les couleurs viennent de la charte (theme.C, docs/charte-graphique.txt).
BG = C.charbon
EDGE = C.bois
TEXT = C.os
SOFT = C.lin
NOTE = C.cendre
GOLD = C.ocre_jaune
GOOD = C.bon
BAD = C.mauvais
WARN = C.alerte


def _fonts(r):
    return theme.font("h1"), theme.font("h3")


def _box(r, rect, fill=None, edge=None, radius=8, width=1):
    """Une fenetre (peau) si on ne dit rien ; une carte sinon (un fond plus
    sombre que le cuir : un creux)."""
    if fill is None:
        theme.panel(r.screen, rect, "peau")
    elif sum(fill) < 60:
        theme.panel(r.screen, rect, "creux")
    else:
        theme.panel(r.screen, rect, "carte_choisie" if edge in (GOLD, C.ocre) else "carte")


def _text(r, font, text, color, x, y):
    surf = font.render(text, True, color)
    r.screen.blit(surf, (x, y))
    return surf.get_width()


def _button(r, rect, label, on=True, active=False, font=None):
    mx, my = pygame.mouse.get_pos()
    hover = on and rect[0] <= mx <= rect[0] + rect[2] and rect[1] <= my <= rect[1] + rect[3]
    role = "bouton_petit" if rect[3] < 30 else "bouton"
    f = theme.font(role)
    theme.button(r.screen, rect, theme.fit(f, label, rect[2] - 10), "second", on, hover, active=active, role=role)
    return hover


def _hover(rect) -> bool:
    mx, my = pygame.mouse.get_pos()
    return rect[0] <= mx <= rect[0] + rect[2] and rect[1] <= my <= rect[1] + rect[3]


def _tooltip(r, lines, x, y, avoid=None):
    """Petite fiche au survol : (texte, couleur) ; avoid : le bouton qu'elle
    ne doit pas cacher."""
    if lines:
        theme.tooltip(r.screen, lines, x, y, avoid=avoid)


def _signed(v: float) -> str:
    v = round(v)
    return f"+{v}" if v > 0 else str(v)


def _loyalty_bar(r, x, y, w, value, tint):
    theme.bar(r.screen, (x, y, w, 9), max(0.0, min(100.0, value)) / 100.0, tint, marks=(chiefs.LEAVE / 100.0, chiefs.OBEY / 100.0))


def _mood_color(value: float):
    if value < chiefs.LEAVE:
        return C.mauvais
    if value < chiefs.OBEY:
        return WARN
    if value < 60:
        return C.ocre_jaune
    return GOOD


def tribe_alert(state) -> bool:
    """L'onglet Tribu s'allume quand un clan n'obeit plus ; l'onglet des
    villages, quand un village est agite."""
    if not has_nomads(state):
        return any(
            villages.stability(state, s) < villages.UNREST
            for s in state.sites.values()
            if s.kind == "village" and s.tribe_id == state.viewer and places.band_of(state, s) is not None
        )
    return any(
        b.tribe_id == state.viewer and not chiefs.is_chief_band(state, b) and b.loyalty < chiefs.OBEY
        for b in state.bands.values()
    )


def has_nomads(state) -> bool:
    """Le peuple a encore des clans nomades (ni village, ni troupe)."""
    return any(
        b.tribe_id == state.viewer and b.population > 0 and not b.village and b.kind != "armee"
        for b in state.bands.values()
    )


def tribe_tab_label(state) -> str:
    """Plus de nomades : l'onglet Tribu devient celui des villages."""
    if has_nomads(state):
        return "Tribu"
    n = len(sites.of_tribe(state, state.viewer, "village"))
    if n == 0:
        return "Tribu"
    return "Village" if n == 1 else "Villages"


# --- Tribu ------------------------------------------------------------------------


def start_bonus_text(state, tribe) -> str:
    """Les bonus de depart encore actifs, et le temps qu'il leur reste."""
    if not getattr(tribe, "start_bonuses", None):
        return ""
    left = max(0, tribe.start_bonus_until - state.tick_count)
    years = left // 52
    if years >= 1:
        when = f"encore {years} an{'s' if years > 1 else ''}"
    else:
        when = f"encore {max(1, left)} semaine{'s' if left > 1 else ''}"
    names = ", ".join(tech.START_BONUSES[b].name for b in tribe.start_bonuses if b in tech.START_BONUSES)
    return f"Bonus de départ : {names} ({when})"


def _start_bonus_chip(r, state, tribe, right: int, y: int, ui) -> None:
    text = start_bonus_text(state, tribe)
    if not text:
        return
    w = r.tiny.size(text)[0]
    rect = (right - w, y, w, 14)
    _text(r, r.tiny, text, GOLD, rect[0], y)
    if _hover(rect):
        lines = []
        for bid in tribe.start_bonuses:
            bonus = tech.START_BONUSES.get(bid)
            if bonus is None:
                continue
            lines.append((bonus.name, GOLD))
            lines.extend((f"  {line}", SOFT) for line in tech.start_bonus_lines_for(tribe, bonus))
        lines.append((f"Choisis à la création du peuple, ils durent {tech.START_BONUS_YEARS} ans.", NOTE))
        ui.setdefault("_tips", []).append((lines, rect[0] - 120, y + 18))


def draw_tribe(r, state, layout, ui) -> None:
    title_font, head_font = _fonts(r)
    items = layout["items"]
    bx, by, bw, bh = layout["box"]
    tribe = state.tribes.get(state.viewer)
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
        (b for b in state.bands.values() if b.tribe_id == state.viewer and b.population > 0),
        key=lambda b: (not chiefs.is_chief_band(state, b), b.id),
    )
    pop = sum(b.population for b in bands)
    know = tech.bonuses(tribe)
    camps = len(sites.of_tribe(state, state.viewer, "camp"))
    caches = len(sites.of_tribe(state, state.viewer, "cache"))
    civ = civ_of(state, tribe)
    stats = (
        f"Prestige {tribe.prestige}  ·  {pop} personnes  ·  {tribe_band_count(state, state.viewer)}/{max_bands_of(state, state.viewer)} bandes"
        + f" (civilisation {civ_band_count(state, civ)}/{civ_band_cap(state, civ)})"
        + f"  ·  campements {camps}/{know.camps}  ·  caches {caches}/{know.caches}"
    )
    _text(r, r.tiny, stats, NOTE, bx + 18, by + 40)
    # Le chef.
    y = by + 64
    heart = chiefs.chief_band(state, state.viewer)
    _box(r, (bx + 12, y, bw - 24, 62), fill=(32, 24, 19), edge=(60, 56, 44), radius=6)
    if heart is not None and heart.leader is not None:
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
    heir = f"Héritier : {heir_band.leader.name} (clan de {heir_band.population})" if heir_band else "Héritier : aucun (le plus renommé succédera)"
    hw = r.tiny.size(heir)[0]
    _text(r, r.tiny, heir, NOTE, bx + bw - 24 - hw, y + 8)
    reach = know.chief_reach
    reach_line = f"Emprise du chef : {reach} cases"
    _text(r, r.tiny, reach_line, NOTE, bx + bw - 24 - r.tiny.size(reach_line)[0], y + 24)
    if tribe.settled_at >= 0:
        years = max(0, state.tick_count - tribe.settled_at) // 52
        since = f"depuis {years} an{'s' if years > 1 else ''}" if years else "depuis cette année"
        settled = f"Peuple fixé {since} : les nomades s'émancipent"
        _text(r, r.tiny, settled, WARN, bx + bw - 24 - r.tiny.size(settled)[0], by + 16)
    _start_bonus_chip(r, state, tribe, bx + bw - 24, by + (2 if tribe.settled_at >= 0 else 16), ui)
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
            pygame.draw.rect(r.screen, (45, 34, 26) if not chosen else (62, 47, 34), row, border_radius=4)
        items[f"tribe_row:{band.id}"] = row
        is_heart = chiefs.is_chief_band(state, band)
        pygame.draw.circle(r.screen, color, (cols["clan"] + 5, y + 12), 5)
        name = band.leader.name if band.leader is not None else f"Bande {band.id}"
        if band.village:
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
            _text(r, r.tiny, "cœur de la tribu", GOLD, cols["att"], y + 6)
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
        _button(r, heir_rect, "Héritier", on=can_heir)
        y += row_h
    # Pourquoi (clan choisi).
    dy = by + bh - 140
    pygame.draw.line(r.screen, (72, 53, 38), (bx + 14, dy), (bx + bw - 14, dy))
    band = state.bands.get(pick) if pick is not None else None
    if band is None or band.tribe_id != state.viewer or chiefs.is_chief_band(state, band):
        band = next((b for b in bands if not chiefs.is_chief_band(state, b)), None)
    if band is None:
        _text(r, r.small, "Un seul clan : la tribu suit son chef.", SOFT, bx + 18, dy + 10)
        _text(r, r.tiny, "Quand vous scindez, chaque nouveau clan a son chef de bande et son attachement.", NOTE, bx + 18, dy + 32)
        for tip in ui.pop("_tips", []):
            _tooltip(r, *tip)
        return
    who = band.leader.name if band.leader is not None else f"bande {band.id}"
    target = chiefs.loyalty_target(state, band)
    head = f"Clan de {who} : attachement {band.loyalty:.0f}, tend vers {target:.0f}"
    if chiefs.gains_autonomy(state, band):
        head = f"Clan de {who} : indépendance {band.autonomy:.0f} % (départ dans ~{chiefs.autonomy_months(state, band)} mois)"
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
        _text(r, r.tiny, r._fit(r.tiny, f"Indépendance {rate}/mois : {why}", bw - 36), WARN, bx + 18, top)
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
                    ([(f"Lui confier le clan ({traits}, renommée {person.renown})", SOFT)], rect[0], rect[1] + 24)
                )
            nx += bwid + 6
    tip = "Obéit à 40 et plus, peut partir sous 20. Barre orange : indépendance (à 100, il part)."
    if tribe.settled_at < 0:
        tip = "Obéit à 40 et plus · indocile de 20 à 40 · sous 20, le clan peut partir. Le chef à 3 cases : +10 par mois."
    _text(r, r.tiny, r._fit(r.tiny, tip, bw - 36), NOTE, bx + 18, by + bh - 20)
    for tip in ui.pop("_tips", []):
        _tooltip(r, *tip)


# --- Villages (plus de nomades) --------------------------------------------------


def _chief_card(r, state, tribe, rect, head_font) -> None:
    """Le chef du peuple : nom, age, traits et leurs effets."""
    x, y, w, h = rect
    _box(r, rect, fill=(32, 24, 19), edge=(60, 56, 44), radius=6)
    heart = chiefs.chief_band(state, tribe.id)
    if heart is None or heart.leader is None:
        _text(r, r.small, "Pas de chef.", SOFT, x + 14, y + 8)
        return
    _draw_crown(r.screen, x + 18, y + 16)
    lead = heart.leader
    where = ""
    if heart.village:
        site = places.site_of(state, heart)
        where = f", gouverne {places.name(site)}" if site is not None else ""
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
    title_font, head_font = _fonts(r)
    items = layout["items"]
    bx, by, bw, bh = layout["box"]
    tribe = state.tribes[state.viewer]
    _box(r, (bx, by, bw, bh))
    color = color_of(tribe)
    pygame.draw.rect(r.screen, color, (bx, by + 10, 5, 44), border_radius=2)
    homes = [
        (s, places.band_of(state, s))
        for s in sorted(state.sites.values(), key=lambda s: s.id)
        if s.kind == "village" and s.tribe_id == state.viewer and places.band_of(state, s) is not None
    ]
    _text(r, title_font, f"Les villages des {tribe.name}", TEXT, bx + 18, by + 10)
    pop = sum(b.population for b in state.bands.values() if b.tribe_id == state.viewer and b.population > 0)
    troops = sum(b.population for b in state.bands.values() if b.tribe_id == state.viewer and b.kind == "armee")
    know = tech.bonuses(tribe)
    stats = f"Prestige {tribe.prestige}  ·  {pop} personnes  ·  villages {len(homes)}/{know.villages}  ·  {troops} sous les armes"
    _text(r, r.tiny, stats, NOTE, bx + 18, by + 40)
    _start_bonus_chip(r, state, tribe, bx + bw - 24, by + 16, ui)
    y = by + 60
    _chief_card(r, state, tribe, (bx + 12, y, bw - 24, 62), head_font)
    y += 72
    cols = {"nom": bx + 20, "gens": bx + 210, "stab": bx + 256, "grenier": bx + 424, "act": bx + bw - 12 - 110}
    for key, label in (("nom", "Village"), ("gens", "Gens"), ("stab", "Stabilité"), ("grenier", "Grenier")):
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
            pygame.draw.rect(r.screen, (45, 34, 26), row, border_radius=4)
        items[f"vil_row:{site.id}"] = row
        is_heart = chiefs.is_chief_band(state, band)
        r.draw_village_icon(site, cols["nom"] + 5, y + 12, color, 6)
        label = places.name(site) + (" (le chef)" if is_heart else "")
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
        job = places.works(site)
        work = f"chantier : {batiments.BUILDINGS[job[0]].name.lower()} ({job[1]} sem.)" if job else "pas de chantier"
        second = f"{places.rank_name(band.population)}  ·  {crafts or 'aucun métier'}  ·  {work}"
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
    pygame.draw.line(r.screen, (72, 53, 38), (bx + 14, dy), (bx + bw - 14, dy))
    _text(r, r.small, "Réserve du peuple", TEXT, bx + 18, dy + 8)
    need = goods.need(state, state.viewer)
    col_w = (bw - 36) // 2
    for i, good in enumerate(goods.GOODS):
        cx = bx + 18 + (i % 2) * col_w
        cy = dy + 32 + (i // 2) * 18
        have = goods.stock(state, state.viewer, good)
        ok = goods.supplied(state, state.viewer, good)
        made = goods.made(state, state.viewer, good)
        made_s = f"{made:.1f}".replace(".", ",")
        line = f"{goods.GOOD_NAMES[good]} : {have:.0f}" + (f" (+{made_s}/sem.)" if made else "") + ("  pourvu" if ok else "  en manque")
        _text(r, r.tiny, r._fit(r.tiny, line, col_w - 8), GOOD if ok else NOTE, cx, cy)
    partners = [o for o in sorted(state.tribes) if o != state.viewer and _diplo.has_pact(state, state.viewer, o, "commerce")]
    ty = dy + 32 + 2 * 18 + 6
    if partners:
        names = ", ".join(state.tribes[o].name for o in partners[:4]) + ("..." if len(partners) > 4 else "")
        text = f"Accords commerciaux : {names}. Détail dans l'écran d'un village (Métiers et échanges)."
    else:
        text = "Aucun accord commercial : proposez-en un dans Peuples (il faut Échanges lointains)."
    _text(r, r.tiny, r._fit(r.tiny, text, bw - 36), SOFT, bx + 18, ty)
    _text(r, r.tiny, r._fit(r.tiny, f"Besoin : {need:.1f} de chaque bien par semaine (tous vos villages). Métiers : écran du village.".replace(".", ",", 1), bw - 36), NOTE, bx + 18, ty + 16)
    tip = "Plus de nomades : le peuple vit dans ses villages."
    _text(r, r.tiny, r._fit(r.tiny, tip, bw - 36), NOTE, bx + 18, by + bh - 20)
    for tip in ui.pop("_tips", []):
        _tooltip(r, *tip)


# --- Peuples : render_peuples.py (le conseil des peuples, 2026-10-18) ---------------------


# --- evenements -------------------------------------------------------------------------


def draw_event_cards(r, state, ui) -> None:
    """Cartes "A decider" a gauche (voir events.py) ; rien s'il n'y en a pas.
    Elles respirent : elles attendent une decision."""
    r.event_hits = {}
    # Multijoueur : une carte repondue attend que l'hote applique la reponse.
    answered = ui.get("answered", ()) if isinstance(ui, dict) else ()
    pending = [p for p in events.pending(state, state.viewer) if p.uid not in answered]
    if not pending:
        return
    x, y = 10, HUD_HEIGHT + 110
    # La fiche du tutoriel, ouverte, est en haut a gauche : les cartes passent dessous.
    box = (getattr(r, "tuto_hits", None) or {}).get("box")
    if box is not None:
        y = max(y, box[1] + box[3] + 10)
    t = pygame.time.get_ticks() / 1000.0
    for k, inst in enumerate(pending[:5]):
        ev = events.EVENTS.get(inst.event_id)
        if ev is None:
            continue
        left = max(0, inst.deadline - state.tick_count)
        rect = (x, y, 286, 48)
        r.event_hits[inst.uid] = rect
        theme.glow(r.screen, rect, C.mauvais if ev.mood == "danger" else C.braise, 0.25 + 0.5 * theme.pulse(t + k * 0.4))
        theme.panel(r.screen, rect, "carte_survol" if _hover(rect) else "carte")
        r.screen.blit(theme.medallion(event_icon(ev), 17, MOOD_STATE.get(ev.mood, "normal")), (x + 6, y + 5))
        theme.text(r.screen, ev.title, "petit_gras", C.os, (x + 50, y + 6), 226)
        theme.text(r.screen, f"À décider  ·  {deadline_text(left, short=True)}  ·  E", "mini", C.ocre_jaune if left > 4 else C.alerte, (x + 50, y + 26), 226)
        y += 54


def deadline_text(left: int, short: bool = False) -> str:
    """Le temps qu'il reste pour repondre a un evenement : a 0, le choix par
    defaut se fait a la fin de cette semaine (events : deadline <= tick)."""
    if left <= 0:
        return "dernière semaine" if short else "cette semaine"
    if short:
        return f"encore {left} sem."
    return f"dans {left} semaine{'s' if left > 1 else ''}"


def event_modal_layout(width: int, height: int, n_options: int, text_lines: int = 4) -> dict:
    bw = min(760, width - 80)
    body = max(2, text_lines)
    bh = min(height - 70, max(140, 70 + 22 * body + 32) + 64 * n_options + 18)
    bx = (width - bw) // 2
    by = max(56, (height - bh) // 2)
    options = {}
    oy = by + bh - 18 - 64 * n_options
    for i in range(n_options):
        options[i] = (bx + 28, oy + i * 64, bw - 56, 56)
    close = (bx + bw - 124, by + 18, 100, 26)
    return {"box": (bx, by, bw, bh), "options": options, "close": close}


def draw_event_modal(r, state, ui) -> None:
    """La dalle d'un evenement : son illustration dans un grand medaillon,
    le recit en italique, les choix en larges cartes (detail au survol)."""
    uid = ui.get("event_open")
    inst = events.find(state, uid)
    if inst is None:
        return
    ev = events.EVENTS.get(inst.event_id)
    if ev is None:
        return
    w, h = r.screen.get_size()
    theme.veil(r.screen, 150)
    opts = events.options_for(state, inst)
    text = events.text_for(state, inst)
    bw = min(760, w - 80)
    f = theme.font("recit")
    lines = theme.wrap(f, text, bw - 170)
    lay = event_modal_layout(w, h, len(opts), len(lines))
    r.event_hits = {"modal": lay}
    bx, by, bw, bh = lay["box"]
    theme.panel(r.screen, lay["box"], "pierre")
    r.screen.blit(theme.medallion(event_icon(ev), 46, MOOD_STATE.get(ev.mood, "normal")), (bx + 22, by + 22))
    theme.title(r.screen, ev.title, bx + 134, by + 20, "h1")
    mx, my = pygame.mouse.get_pos()
    theme.button(r.screen, lay["close"], "Plus tard", "discret", True, _hover(lay["close"]))
    yy = by + 66
    for line in lines:
        r.screen.blit(f.render(line, True, C.os), (bx + 134, yy))
        yy += 22
    yy += 8
    left = max(0, inst.deadline - state.tick_count)
    theme.text(r.screen, f"Sans réponse {deadline_text(left)}, le choix par défaut sera fait.", "mini", C.ocre_jaune if left <= 0 else C.cendre, (bx + 134, yy))
    tips = []
    for i, opt in enumerate(opts):
        rect = lay["options"][i]
        on = not opt["blocked"]
        hover = on and _hover(rect)
        if hover:
            theme.glow(r.screen, rect, C.braise, 0.6)
        theme.panel(r.screen, rect, "carte_survol" if hover else ("carte" if on else "creux"))
        theme.text(r.screen, f"{i + 1}.", "h2", C.ocre if on else C.cendre, (rect[0] + 14, rect[1] + 12))
        theme.text(r.screen, opt["label"], "texte_gras", C.os if on else C.cendre, (rect[0] + 46, rect[1] + 7), rect[2] - 60)
        summary = opt["blocked"] or opt["summary"]
        theme.text(r.screen, summary, "petit", C.cendre if opt["blocked"] else C.ocre_jaune, (rect[0] + 46, rect[1] + 31), rect[2] - 60)
        if hover and opt["details"]:
            rows = [(line, C.lin) for line in opt["details"]]
            tw = 340
            if bx + bw + 8 + tw <= w:
                # A droite de la fenetre : on ne cache ni le texte ni les options.
                tips.append((rows, bx + bw + 8, rect[1]))
            elif bx - 8 - tw >= 0:
                tips.append((rows, bx - 8 - tw, rect[1]))
            else:
                tips.append((rows, rect[0] + 20, rect[1] - 12 - 18 * len(rows)))
    for tip in tips:
        _tooltip(r, *tip)


# --- Armee ------------------------------------------------------------------------------
# L'onglet apparait avec le premier village : on y leve une compagnie par
# village (type, taille) et l'on suit toutes ses troupes.


def commerce_ready(state) -> bool:
    """L'onglet Commerce vient avec le premier village."""
    return bool(sites.of_tribe(state, state.viewer, "village"))


def treasury_alert(state) -> bool:
    """L'onglet Tresor s'allume quand la solde ou les gages ne sont pas payes."""
    tribe = state.tribes.get(state.viewer)
    if tribe is None or not money.has_money(state, state.viewer):
        return False
    b = money.budget(tribe)
    return "impayee" in (b.get("etat_solde"), b.get("etat_gages"))


def commerce_alert(state) -> bool:
    """L'onglet s'allume quand une route du joueur, ouverte par lui, ne porte
    plus rien."""
    return any(r.by == state.viewer and r.idle >= 2 for r in goods.routes_of(state, state.viewer))


def wars_ready(state) -> bool:
    """L'onglet des guerres : avec la diplomatie (on declare la guerre), ou
    des qu'on est en guerre."""
    return guerre.diplomatic(state, state.viewer) or bool(guerre.wars_of(state, state.viewer))


# On vous a declare la guerre depuis moins de WAR_NEWS semaines : l'onglet
# respire.
WAR_NEWS = 8


def wars_alert(state) -> bool:
    me = state.viewer
    for enemy in guerre.wars_of(state, me):
        pact = next((p for p in diplo.pacts_between(state, me, enemy) if p.kind == guerre.WAR), None)
        if pact is not None and pact.payer != me and state.tick_count - pact.since <= WAR_NEWS:
            return True
    return False


def army_ready(state) -> bool:
    tribe = state.tribes.get(state.viewer)
    if tribe is None:
        return False
    if sites.of_tribe(state, state.viewer, "village"):
        return True
    return any(b.tribe_id == state.viewer and b.kind == "armee" for b in state.bands.values())


def _draw_crown(surf: pygame.Surface, cx: int, cy: int) -> None:
    gold = (236, 196, 80)
    pts = [(cx - 6, cy + 3), (cx - 6, cy - 3), (cx - 3, cy), (cx, cy - 5), (cx + 3, cy), (cx + 6, cy - 3), (cx + 6, cy + 3)]
    pygame.draw.polygon(surf, gold, pts)
    pygame.draw.polygon(surf, (90, 64, 20), pts, 1)
