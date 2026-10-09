"""Panneaux Tribu (chef, clans, attachement) et Peuples (diplomatie),
cartes d'evenements.

Les rectangles cliquables sont enregistres pendant le dessin dans
layout["items"] (comme les lignes du journal) ; app.py lit side_hit.
"""

from __future__ import annotations

import pygame

from src.kora import (
    approach,
    chiefs,
    confed,
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
    turning,
    units,
    villages as _v,
    villages,
)
from src.kora.peoples import civ_name, civ_of, color_of, label_of, living_tribe_ids
from src.kora.bands import civ_band_cap, civ_band_count, max_bands_of, tribe_band_count

from src.kora.theme import C
from src.kora.layout import (  # noqa: F401
    panel_box,
)
from src.kora.layout import HUD_HEIGHT

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
# La couleur de chaque approche des chefs (approach.py).
APPROACH_COLORS = {
    "conquerant": C.mauvais, "protecteur": C.ocre_jaune, "marchand": C.bon, "paisible": C.lin,
    "mefiant": C.alerte, "affame": C.braise, "soumis": C.cendre, "retif": C.alerte,
}


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
        work = f"chantier : {villages.BUILDINGS[job[0]].name.lower()} ({job[1]} sem.)" if job else "pas de chantier"
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


# --- Peuples ---------------------------------------------------------------------------


def known_peoples(state) -> list[int]:
    alive = living_tribe_ids(state)
    out = [t for t in diplo.contacts_of(state, state.viewer) if t in alive]
    out.sort(key=lambda t: (not diplo.allied(state, state.viewer, t), -diplo.relation(state, state.viewer, t), t))
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
    pygame.draw.rect(r.screen, (108, 84, 62), (x, y, w, 10), 1)
    mid = x + w // 2
    pygame.draw.line(r.screen, (139, 125, 110), (mid, y - 3), (mid, y + 12))
    px = x + int(w * (rel + 100) / 200)
    pygame.draw.polygon(r.screen, (239, 228, 204), [(px, y - 2), (px - 6, y - 10), (px + 6, y - 10)])
    pygame.draw.polygon(r.screen, (239, 228, 204), [(px, y + 12), (px - 6, y + 20), (px + 6, y + 20)])


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
        _text(r, r.tiny, "Explorez : à 16 cases d'une de leurs bandes, vous les rencontrez.", NOTE, bx + 18, by + 78)
        return
    pick = ui.get("people_pick")
    if pick not in peoples:
        pick = peoples[0]
        ui["people_pick"] = pick
    # Liste a gauche : elle defile a la molette (ui["people_scroll"]).
    lx, ly, lw = bx + 12, by + 46, 250
    row_h = 46
    list_rect = (lx, ly, lw, by + bh - 10 - ly)
    r.people_list = list_rect
    fits = max(1, list_rect[3] // row_h)
    top = max(0, min(int(ui.get("people_scroll", 0)), len(peoples) - fits))
    ui["people_scroll"] = top
    for tid in peoples[top:]:
        if ly + row_h > by + bh - 10:
            break
        t = state.tribes[tid]
        row = (lx, ly, lw, row_h - 4)
        items[f"people:{tid}"] = row
        chosen = tid == pick
        fill = (62, 47, 34) if chosen else (45, 34, 26) if _hover(row) else (32, 24, 19)
        pygame.draw.rect(r.screen, fill, row, border_radius=6)
        if chosen:
            pygame.draw.rect(r.screen, GOLD, row, 1, border_radius=6)
        pygame.draw.circle(r.screen, color_of(t), (lx + 16, ly + 20), 8)
        pygame.draw.circle(r.screen, (20, 20, 20), (lx + 16, ly + 20), 8, 1)
        _text(r, r.small, r._fit(r.small, t.name, 120), TEXT, lx + 32, ly + 5)
        nv = len(sites.of_tribe(state, tid, "village"))
        second = f"proto-pays, {nv} village{'s' if nv > 1 else ''}" if nv else label_of(t)
        if t.is_player:
            second = "un joueur  ·  " + second
        _text(r, r.tiny, r._fit(r.tiny, second, 130), GOLD if nv or t.is_player else NOTE, lx + 32, ly + 23)
        rel = diplo.relation(state, state.viewer, tid)
        lvl = diplo.level(state, state.viewer, tid)
        if diplo.declared_war(state, state.viewer, tid):
            lvl = "En guerre"
        val = _signed(rel)
        vw = r.small.size(val)[0]
        _text(r, r.small, val, _rel_color(rel), lx + lw - 10 - vw, ly + 5)
        lw2 = r.tiny.size(lvl)[0]
        _text(r, r.tiny, lvl, BAD if lvl == "En guerre" else _rel_color(rel), lx + lw - 10 - lw2, ly + 23)
        ly += row_h
    if len(peoples) > fits:
        # La barre de defilement : ou l'on est dans la liste.
        track = (lx + lw + 3, list_rect[1], 4, fits * row_h - 4)
        pygame.draw.rect(r.screen, (40, 31, 24), track, border_radius=2)
        th = max(16, int(track[3] * fits / len(peoples)))
        ty_ = track[1] + int((track[3] - th) * top / max(1, len(peoples) - fits))
        pygame.draw.rect(r.screen, GOLD, (track[0], ty_, 4, th), border_radius=2)
    # Fiche a droite.
    cx = lx + lw + 14
    cw = bx + bw - 12 - cx
    t = state.tribes[pick]
    cy = by + 46
    color = color_of(t)
    head_h = 92
    _box(r, (cx, cy, cw, head_h), fill=(35, 26, 20), edge=(85, 64, 45), radius=8)
    pygame.draw.rect(r.screen, color, (cx, cy, 8, head_h), border_top_left_radius=8, border_bottom_left_radius=8)
    _text(r, title_font, t.name, TEXT, cx + 20, cy + 6)
    nb = sum(1 for b in state.bands.values() if b.tribe_id == pick and b.population > 0)
    pop = diplo.pop_of(state, pick)
    approx = max(10, int(round(pop / 10.0)) * 10)
    culture = label_of(t) + ("  ·  mené par un joueur" if t.is_player else "")
    origin = ""
    if t.origin and t.origin in state.tribes:
        origin = f"  ·  issus des {state.tribes[t.origin].name}" if t.origin != state.viewer else "  ·  issus de votre peuple"
    civ = civ_of(state, t)
    if civ == civ_of(state, state.tribes[state.viewer]):
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
    # L'approche de son chef envers les autres peuples (approach.py).
    approach_tip = None
    way = approach.of(state, pick)
    if way:
        label, about = approach.APPROACHES[way]
        tint = APPROACH_COLORS.get(way, SOFT)
        head = f"Approche : {label}"
        hw = r.small.size(head)[0]
        _text(r, r.small, head, tint, cx + 22, cy + 68)
        _text(r, r.tiny, r._fit(r.tiny, about, cw - 60 - hw), SOFT, cx + 30 + hw, cy + 71)
        arect = (cx + 22, cy + 66, cw - 40, 22)
        items["people_approach"] = arect
        if _hover(arect):
            rows = [(f"{label} : {about}", TEXT, "petit_gras")]
            why = approach.reasons(state, pick)
            if why:
                rows.append(("Pourquoi :", NOTE))
                rows += [(f"  {text}", SOFT) for text, _v in why[:5]]
            rows.append(("Ce que cela change :", NOTE))
            rows += [(f"  {line}", tint) for line in approach.BEHAVIOR.get(way, ())]
            rows.append(("Elle change avec sa situation, et avec un nouveau chef.", NOTE))
            approach_tip = (rows, arect[0], arect[1] + arect[3], arect)
    elif t.is_player and pick != state.viewer:
        _text(r, r.tiny, "Mené par un joueur : il décide lui-même de son approche.", NOTE, cx + 22, cy + 70)
    see = (cx + cw - 96, cy + 8, 84, 22)
    items["people_see"] = see
    _button(r, see, "Voir")
    # Relation.
    cy += head_h + 12
    rel = diplo.relation(state, state.viewer, pick)
    lvl = diplo.level(state, state.viewer, pick)
    _text(r, head_font, f"Relation : {_signed(rel)}  ·  {lvl}", _rel_color(rel), cx + 4, cy)
    status = diplo.status_line(state, state.viewer, pick)
    if status:
        sw_ = r.small.size(status)[0]
        _text(r, r.small, status, GOLD, cx + cw - sw_ - 4, cy + 2)
    _relation_meter(r, cx + 10, cy + 34, cw - 20, rel)
    cy += 62
    # Leur pays : une confederation parle d'une seule voix au dehors.
    for line in confed.lines(state, pick):
        _text(r, r.tiny, r._fit(r.tiny, line + " (paix et guerre partagées)", cw - 8), GOLD, cx + 4, cy)
        cy += 16
    reasons = diplo.reasons(state, state.viewer, pick)
    _text(r, r.tiny, "Pourquoi :", NOTE, cx + 4, cy)
    cy += 16
    half = (cw - 8) // 2
    if not reasons:
        _text(r, r.tiny, "Rien de particulier : vous vous connaissez à peine.", SOFT, cx + 12, cy)
        cy += 16
    for i, (label, value) in enumerate(reasons[:8]):
        x = cx + 8 + (i % 2) * half
        y = cy + (i // 2) * 16
        _text(r, r.tiny, f"{_signed(value):>4}", GOOD if value > 0 else BAD, x, y)
        _text(r, r.tiny, r._fit(r.tiny, label, half - 46), SOFT, x + 38, y)
    cy += 16 * ((min(8, len(reasons)) + 1) // 2) + 8
    # Leurs grands tournants (turning.py) : adoptes, en chemin.
    them = state.tribes[pick]
    adopted = [t.name for t in tech.turnings() if t.id in them.knowledge]
    coming = [f"{t.name} {turning.presence(them, t.id):.0f} %" for t in tech.turnings() if t.id not in them.knowledge and turning.presence(them, t.id) > 0]
    if adopted or coming:
        line = "Grands tournants : " + (", ".join(adopted) if adopted else "aucun adopté") + (f" · en chemin : {', '.join(coming)}" if coming else "")
        _text(r, r.tiny, r._fit(r.tiny, line, cw - 8), (236, 196, 110), cx + 4, cy)
        cy += 16
    # Savoirs a apprendre d'eux.
    mine = state.tribes[state.viewer].knowledge
    theirs = sorted((k for k in t.knowledge - mine if k in tech.TECHS), key=lambda k: (tech.TECHS[k].tier, k))
    teach = pick in getattr(state.diplo, "neighbors", {}).get(state.viewer, [])
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
        if confed.same(state, pick, other):
            ties.append(f"confédérés des {state.tribes[other].name}")
        elif diplo.allied(state, pick, other):
            ties.append(f"alliés des {state.tribes[other].name}")
        elif diplo.has_pact(state, pick, other, "commerce"):
            ties.append(f"commercent avec les {state.tribes[other].name}")
        elif diplo.has_pact(state, pick, other):
            ties.append(f"en trêve avec les {state.tribes[other].name}")
        elif diplo.relation(state, pick, other) <= -50:
            ties.append(f"ennemis des {state.tribes[other].name}")
    if ties:
        _text(r, r.tiny, r._fit(r.tiny, "Avec les autres : " + ", ".join(ties), cw - 8), SOFT, cx + 4, cy)
        cy += 20
    if diplo.has_pact(state, state.viewer, pick, "commerce"):
        n = sum(1 for rt in goods.routes_of(state, state.viewer) if pick in (rt.exporter, rt.importer))
        done = goods.summary(state, state.viewer, pick)
        line = f"Routes : {n}" + (" · le mois dernier : " + done if done else " · rien porte le mois dernier")
        if goods.trade_distance(state, state.viewer, pick) > goods.trade_range(state, state.viewer, pick):
            line = "Commerce : vos villages sont trop loin l'un de l'autre"
        button = (cx + cw - 190, cy - 3, 186, 20)
        items["trade_with"] = button
        _button(r, button, "Routes commerciales [M]")
        _text(r, r.tiny, r._fit(r.tiny, line, cw - 200), GOLD if done else NOTE, cx + 4, cy)
        cy += 22
    # Actions : les vivres sur une ligne, puis les propositions.
    tips = []
    if approach_tip is not None:
        tips.append(approach_tip)
    verdict = diplo.evaluate(state, state.viewer, pick, "cadeau")
    _text(r, r.small, diplo.ACTION_LABELS["cadeau"], TEXT if not verdict.blocked else NOTE, cx + 4, cy + 3)
    sizes = diplo.gift_sizes(state, state.viewer, pick) if not verdict.blocked else []
    gx = cx + 160
    for amount in diplo.GIFT_SIZES:
        rect = (gx, cy, 50, 22)
        items[f"gift:{amount}"] = rect
        on = amount in sizes
        _button(r, rect, str(amount), on=on)
        if on and _hover(rect):
            gain = diplo.gift_value(state, state.viewer, pick, amount)
            tips.append(([(f"{amount} vivres, portes par votre bande la plus proche", TEXT), (f"Relation : +{gain:.0f}", GOOD)], rect[0] + rect[2] + 8, rect[1]))
        gx += 56
    if verdict.blocked:
        note = verdict.blocked
    elif not sizes:
        note = "Votre bande la plus proche n'a pas assez de vivres"
    else:
        note = "Toujours accepté"
    _text(r, r.tiny, r._fit(r.tiny, note, cx + cw - gx - 4), NOTE if verdict.blocked or not sizes else GOOD, gx + 4, cy + 5)
    cy += 30
    # Les presents en sicles (le tresor) : des envoyes les portent.
    if money.has_money(state, state.viewer):
        verdict = diplo.evaluate(state, state.viewer, pick, "present")
        _text(r, r.small, diplo.ACTION_LABELS["present"], TEXT if not verdict.blocked else NOTE, cx + 4, cy + 3)
        sizes = diplo.present_sizes(state, state.viewer)
        gx = cx + 160
        for amount in diplo.PRESENT_SIZES:
            rect = (gx, cy, 50, 22)
            items[f"present:{amount}"] = rect
            on = amount in sizes
            _button(r, rect, str(amount), on=on)
            if on and _hover(rect):
                gain = diplo.present_value(state, state.viewer, pick, amount)
                rows = [(f"{amount} sicles, portés par des envoyés", TEXT), (f"Relation : +{gain:.0f}", GOOD)]
                rows += [(label, SOFT) for label, _v in verdict.reasons[1:]]
                tips.append((rows, rect[0] + rect[2] + 8, rect[1]))
            gx += 56
        note = verdict.blocked or ("Toujours accepté" if money.has_money(state, pick) else "Ils ne connaissent pas l'argent : moitié moins")
        _text(r, r.tiny, r._fit(r.tiny, note, cx + cw - gx - 4), NOTE if verdict.blocked else GOOD, gx + 4, cy + 5)
        cy += 30
    cy += 4
    cols = 2
    aw = (cw - 12) // cols
    ah = 46
    for i, action in enumerate(["guerre", "treve", "alliance", "commerce", "tribut", "proteger", "confederer", "union", "rompre"]):
        ax = cx + (i % cols) * (aw + 12)
        ay = cy + (i // cols) * ah
        if ay + ah > by + bh - 6:
            break
        verdict = diplo.evaluate(state, state.viewer, pick, action)
        wait = diplo.on_cooldown(state, state.viewer, pick, action) if action != "rompre" else 0
        line, tint = _verdict_line(verdict)
        if action == "guerre" and not verdict.blocked:
            # Une declaration, pas une proposition : ses consequences au survol.
            line, tint = "Possible : survolez pour les conséquences", WARN
        if t.is_player and not verdict.blocked and action in diplo.HUMAN_OFFERS:
            # Un autre joueur : pas de calcul, il recevra une carte et choisira.
            line, tint = "Un joueur : il décidera lui-même", GOLD
            verdict = diplo.Verdict(score=verdict.score)
        if wait and not verdict.blocked:
            line, tint = f"Déjà propose : attendez {wait} sem.", NOTE
        rect = (ax, ay, min(190, aw - 4), 22)
        items[f"diplo:{action}"] = rect
        on = not verdict.blocked and not wait
        _button(r, rect, diplo.ACTION_LABELS[action], on=on)
        _text(r, r.tiny, r._fit(r.tiny, line, aw - 6), tint, ax + 2, ay + 26)
        if _hover(rect) and verdict.reasons and action == "guerre":
            rows = [("Déclarer la guerre aux " + t.name, TEXT)] + [(f"  {label}", WARN) for label, _v in verdict.reasons]
            tips.append((rows, rect[0] + rect[2] + 10, rect[1] - 4, rect))
        elif _hover(rect) and verdict.reasons:
            rows = [(f"{_signed(v):>4}  {label}", GOOD if v > 0 else BAD if v < 0 else SOFT) for label, v in verdict.reasons]
            if action != "rompre":
                rows.append((f"Total : {_signed(verdict.score)} (il faut plus de 0)", TEXT))
            tips.append((rows, rect[0] + rect[2] + 10, rect[1] - 4, rect))
    # Clans de ce peuple qui se detachent, pres de chez vous.
    iy = cy + 4 * ah + 4
    for band in diplo.invitable(state, state.viewer, pick)[:2]:
        if iy + 26 > by + bh - 6:
            break
        who = band.leader.name if band.leader else f"bande {band.id}"
        chance = round(100 * diplo.invite_chance(state, state.viewer, band))
        line = f"Clan de {who} ({band.population}) : attachement {band.loyalty:.0f}, il se détache de son chef"
        _text(r, r.tiny, r._fit(r.tiny, line, cw - 200), WARN, cx + 4, iy + 5)
        rect = (cx + cw - 190, iy, 186, 22)
        items[f"invite:{band.id}"] = rect
        on = state.tribes[state.viewer].prestige >= diplo.INVITE_COST
        _button(r, rect, f"Inviter ({diplo.INVITE_COST} prest., ~{chance} %)", on=on)
        iy += 28
    for tip in tips:
        _tooltip(r, *tip)


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
        theme.text(r.screen, f"À décider  ·  encore {left} sem.  ·  E", "mini", C.ocre_jaune if left > 4 else C.alerte, (x + 50, y + 26), 226)
        y += 54


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
    theme.text(r.screen, f"Sans réponse dans {left} semaines, le choix par défaut sera fait.", "mini", C.cendre, (bx + 134, yy))
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


LEVY_SHORT = {"poignee": "Poignee", "troupe": "Troupe", "masse": "Masse"}


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


def army_ready(state) -> bool:
    tribe = state.tribes.get(state.viewer)
    if tribe is None:
        return False
    if sites.of_tribe(state, state.viewer, "village"):
        return True
    return any(b.tribe_id == state.viewer and b.kind == "armee" for b in state.bands.values())


def draw_army(r, state, layout, ui) -> None:
    title_font, head_font = _fonts(r)
    items = layout["items"]
    bx, by, bw, bh = layout["box"]
    tribe = state.tribes.get(state.viewer)
    if tribe is None:
        return
    _box(r, (bx, by, bw, bh))
    pygame.draw.rect(r.screen, color_of(tribe), (bx, by + 10, 5, 44), border_radius=2)
    _text(r, title_font, "Armée", TEXT, bx + 18, by + 10)
    troops = sorted((b for b in state.bands.values() if b.tribe_id == state.viewer and b.kind == "armee"), key=lambda b: b.id)
    homes = sites.of_tribe(state, state.viewer, "village")
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
        home = places.band_of(state, site)
        if home is None:
            continue
        _box(r, (bx + 12, y, bw - 24, block_h - 6), fill=(32, 24, 19), edge=(60, 56, 44), radius=6)
        name_rect = (bx + 20, y + 5, 150, 20)
        items[f"avillage:{site.id}"] = name_rect
        _button(r, name_rect, places.name(site))
        info = f"{home.population} habitants  ·  compagnies {villages.companies_of(state, site)}/{villages.army_cap(state, site)}"
        _text(r, r.tiny, info, SOFT, bx + 180, y + 8)
        role = roles.get(site.id, "melee")
        cw = (bw - 40 - 3 * 6) // 4
        for i, rl in enumerate(units.ROLES):
            rect = (bx + 20 + i * (cw + 6), y + 30, cw, 20)
            u = units.best(tribe, rl)
            label = u.short if u else f"{units.ROLE_LABEL[rl]} : verrouillé"
            items[f"arole:{site.id}:{rl}"] = rect
            _button(r, rect, label, on=u is not None, active=rl == role and u is not None)
            if _hover(rect):
                if u is None:
                    first = units.ages_of(rl)[0]
                    need = tech.TECHS[first.needs].name if first.needs else "?"
                    tips.append(([(first.name, TEXT), (f"Il faut connaître {need}", BAD)], rect[0], rect[1] + 24))
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
        why = villages.army_block(state, home.id, share, kind.id) or ("" if chiefs.obeys(state, home) else "Ce clan n'obéit plus")
        raise_rect = (sx + 6, y + 52, 120, 24)
        items[f"araise:{site.id}"] = raise_rect
        _button(r, raise_rect, "Lever [L]", on=not why)
        if why:
            _text(r, r.tiny, r._fit(r.tiny, why, bx + bw - 24 - (raise_rect[0] + 128)), WARN, raise_rect[0] + 128, y + 57)
        y += block_h
    if len(homes) > max_blocks:
        _text(r, r.tiny, f"... et {len(homes) - max_blocks} autres villages (écran du village)", NOTE, bx + 20, y)
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
        where = places.name(home) if home is not None else "sans village"
        d = state.world.distance(home.hex, army.position) if home is not None else 0
        status = "rentre" if army.homebound else ("au village" if home is not None and d <= villages.ARMY_HOME else f"à {d} cases de {where}")
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
            tips.append(([("Chaque compagnie rentre à pied à son village", SOFT)], dis[0] - 120, dis[1] + 24))
        y += 44
    tip = "Dissoute, une compagnie rentre à pied à son village. Les savoirs apportent de nouveaux types d'unités."
    _text(r, r.tiny, r._fit(r.tiny, tip, bw - 36), NOTE, bx + 18, by + bh - 20)
    for tip in tips:
        _tooltip(r, *tip)


def _draw_crown(surf: pygame.Surface, cx: int, cy: int) -> None:
    gold = (236, 196, 80)
    pts = [(cx - 6, cy + 3), (cx - 6, cy - 3), (cx - 3, cy), (cx, cy - 5), (cx + 3, cy), (cx + 6, cy - 3), (cx + 6, cy + 3)]
    pygame.draw.polygon(surf, gold, pts)
    pygame.draw.polygon(surf, (90, 64, 20), pts, 1)
