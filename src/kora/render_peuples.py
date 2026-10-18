"""LE CONSEIL DES PEUPLES (onglet Peuples ; 2026-10-18, la maquette A
choisie par le joueur : docs/maquettes/diplomatie/A_conseil.png).

Toute la largeur, comme l'ecran du village :
  - en haut, des filtres (Tous, Cordiaux, Mefiants, Hostiles, En guerre,
    avec leur nombre) et votre force ;
  - a gauche, la liste des peuples connus : le nom, la relation, l'humeur,
    des icones d'etat (leurs guerres, leurs accords, leur suzerain) et leur
    force par rapport a la votre ; elle DEFILE (molette, barre a glisser,
    clic dans la rainure : layout.people_rows / people_thumb) ;
  - a droite, la fiche : un en-tete (leur jeton, le chef et ses traits,
    l'approche), trois cartes - ENTRE VOUS (relation, ses raisons, vos
    accords), LEUR FORCE (eux / vous), LEURS LIENS (leurs guerres, leurs
    accords, leur pays) -, leurs grands tournants et leurs savoirs ;
  - les actions en quatre familles : DONNER, PROPOSER, LES SOUMETTRE, LA
    GUERRE ; ce qu'on peut faire en boutons, avec la reponse attendue (le
    detail au survol) ; le reste replie sous "Pas encore" (un cadenas : le
    savoir qu'il faut ; un tiret : sans objet).
Les clics : partie_ecrans.ScreenClicks.side_click ("people:", "pfilter:", "ptrack",
"pthumb", "gift:", "present:", "diplo:", "invite:", "people_see",
"trade_with") ; la mise en page : layout.peoples_layout.
"""

from __future__ import annotations

import pygame

from src.kora import approach, chiefdom, chiefs, confed, diplo, guerre, money, sites, tech, theme
from src.kora.layout import PEOPLE_FILTERS, people_rows, people_thumb, peoples_layout, clamp_people_top
from src.kora.look import country_color
from src.kora.peoples import civ_name, civ_of, color_of, label_of, living_tribe_ids
from src.kora.theme import C

# La couleur de chaque approche des chefs (approach.py).
APPROACH_COLORS = {
    "conquerant": C.mauvais, "protecteur": C.ocre_jaune, "marchand": C.bon, "paisible": C.lin,
    "mefiant": C.alerte, "affame": C.braise, "soumis": C.cendre, "retif": C.alerte,
}
# Les quatre familles d'actions : (titre, icone, medaillon, actions).
FAMILIES = (
    ("Donner", "vivres", "connu", ("cadeau", "present")),
    ("Proposer", "politique", "connu", ("treve", "commerce", "alliance", "confederer", "union")),
    ("Les soumettre", "couronne", "connu", ("affranchir", "tribut", "proteger", "soumission")),
    ("La guerre", "combat", "danger", ("revolte", "guerre", "guerre_pays", "rompre")),
)
# Les liens d'un peuple avec les autres : (icone, verbe), dans l'ordre.
TIES = (
    ("guerre", "combat", "En guerre contre"),
    ("vassal", "couronne", "Tributaires des"),
    ("suzerain", "couronne", "Suzerains des"),
    ("confederation", "politique", "Confédérés des"),
    ("alliance", "politique", "Alliés des"),
    ("treve", "politique", "En trêve avec"),
    ("tribut", "balance", "Tribut avec"),
    ("commerce", "commerce", "Commercent avec"),
)
TIE_COLORS = {"guerre": C.mauvais, "vassal": C.ocre_jaune, "suzerain": C.ocre_jaune, "tribut": C.ocre_jaune}
ROW_FILL = {False: "carte", True: "carte_choisie"}


def known_peoples(state) -> list[int]:
    alive = living_tribe_ids(state)
    out = [t for t in diplo.contacts_of(state, state.viewer) if t in alive]
    out.sort(key=lambda t: (not diplo.allied(state, state.viewer, t), -diplo.relation(state, state.viewer, t), t))
    return out


def in_filter(state, tid: int, key: str) -> bool:
    if key == "guerre":
        return guerre.declared_war(state, state.viewer, tid)
    rel = diplo.relation(state, state.viewer, tid)
    if key == "cordiaux":
        return rel >= 15 or diplo.allied(state, state.viewer, tid)
    if key == "mefiants":
        return -15 < rel < 15 and not diplo.allied(state, state.viewer, tid)
    if key == "hostiles":
        return rel <= -15
    return True


def rel_color(rel: float):
    if rel <= -50:
        return (225, 90, 80)
    if rel <= -15:
        return (225, 140, 100)
    if rel < 15:
        return (200, 196, 170)
    if rel < 50:
        return (160, 210, 140)
    return (110, 220, 150)


def signed(v: float) -> str:
    return f"{v:+.0f}" if round(v) else "0"


def ties_of(state, tid: int, known: set) -> dict:
    """{genre: [peuples]} : les pactes de tid avec les peuples que vous
    connaissez (un tributaire : "vassal" ; son suzerain : "suzerain")."""
    out: dict = {}
    for o in sorted(diplo.contacts_of(state, tid)):
        if o not in known or o not in state.tribes:
            continue
        for p in diplo.pacts_between(state, tid, o):
            kind = p.kind
            if kind == "vassal":
                kind = "vassal" if p.payer == tid else "suzerain"
            elif kind == confed.KIND:
                kind = "confederation"
            out.setdefault(kind, []).append(o)
    return out


def tie_rows(state, tid: int, known: set) -> list:
    """[(icone, texte, couleur)] : les liens d'un peuple, en mots."""
    ties = ties_of(state, tid, known)
    rows = []
    for kind, icon, verb in TIES:
        names = [state.tribes[o].name for o in ties.get(kind, ())]
        if names:
            rows.append((icon, f"{verb} les " + ", les ".join(names), TIE_COLORS.get(kind, C.lin)))
    return rows


def power_text(mine: float, theirs: float) -> tuple[str, tuple]:
    q = mine / max(1.0, theirs)
    if q >= 1.8:
        return f"Vous êtes {q:.1f} fois plus forts".replace(".", ","), C.bon
    if q >= 1.15:
        return "Vous êtes plus forts", C.bon
    if q > 0.87:
        return "Forces égales", C.lin
    if q > 0.55:
        return "Ils sont plus forts", C.alerte
    return f"Ils sont {1 / max(0.01, q):.1f} fois plus forts".replace(".", ","), C.mauvais


def _hover(rect) -> bool:
    mx, my = pygame.mouse.get_pos()
    return rect[0] <= mx <= rect[0] + rect[2] and rect[1] <= my <= rect[1] + rect[3]


def _button(r, rect, label, on=True, rank="second", icon_key=None):
    hover = on and _hover(rect)
    role = "bouton_petit" if rect[3] < 30 else "bouton"
    theme.button(r.screen, rect, theme.fit(theme.font(role), label, rect[2] - (34 if icon_key else 10)), rank, on, hover, icon_key=icon_key, role=role)
    return hover


def _pill(surf, x, y, text, color, role="mini_gras") -> int:
    f = theme.font(role)
    w = f.size(text)[0] + 14
    h = f.get_height() + 4
    poly = theme.chamfer((x, y, w, h), 3)
    pygame.draw.polygon(surf, theme._mix(C.charbon, color, 0.22), poly)
    pygame.draw.polygon(surf, color, poly, 1)
    surf.blit(f.render(text, True, theme._mix(color, C.os, 0.35)), (x + 7, y + 2))
    return w


def _section(surf, x, y, w, label, color=None) -> None:
    f = theme.font("etiquette")
    surf.blit(f.render(label, True, color or C.ocre_jaune), (x, y))
    theme.dotted(surf, (x + f.size(label)[0] + 8, y + 9), (x + w, y + 9), C.ocre_sombre, 6)


def _lock(surf, x, y, color=C.cendre) -> None:
    pygame.draw.rect(surf, color, (x - 4, y - 1, 9, 7), border_radius=1)
    pygame.draw.arc(surf, color, (x - 3, y - 6, 7, 9), 0, 3.15, 2)


def token(surf, name: str, color, cx: int, cy: int, radius: int, chosen: bool = False) -> None:
    """Le jeton d'un peuple : un disque a la couleur de son pays, son initiale
    en petites capitales (une tete de totem, petite, faisait un crane)."""
    if chosen:
        theme.glow(surf, (cx - radius - 10, cy - radius - 10, 2 * radius + 20, 2 * radius + 20), C.braise, 0.9)
    pygame.draw.circle(surf, (0, 0, 0), (cx, cy + 2), radius + 1)
    pygame.draw.circle(surf, theme._mix(C.nuit, color, 0.5), (cx, cy), radius)
    pygame.draw.circle(surf, theme._mix(C.nuit, color, 0.62), (cx, cy - radius // 5), int(radius * 0.7))
    pygame.draw.circle(surf, theme._mix(C.nuit, color, 0.5), (cx, cy + radius // 6), int(radius * 0.68))
    pygame.draw.circle(surf, C.braise if chosen else color, (cx, cy), radius, 3 if chosen else 2)
    pygame.draw.circle(surf, C.nuit, (cx, cy), radius - 3, 1)
    f = theme.font_file("sc-bold", max(12, int(radius * 1.15)))
    letter = (name or "?")[:1].upper()
    img = f.render(letter, True, C.os)
    surf.blit(f.render(letter, True, C.nuit), (cx - img.get_width() // 2 + 1, cy - img.get_height() // 2 + 1))
    surf.blit(img, (cx - img.get_width() // 2, cy - img.get_height() // 2))


def meter(surf, x, y, w, rel, h=8) -> None:
    """La relation de -100 a +100 : la rainure teintee, le curseur."""
    for i in range(0, w, 2):
        c = rel_color(-100 + 200 * i / max(1, w - 1))
        pygame.draw.rect(surf, theme._mix(C.nuit, c, 0.55), (x + i, y, 2, h))
    pygame.draw.rect(surf, C.bois, (x - 1, y - 1, w + 2, h + 2), 1)
    mid = x + w // 2
    pygame.draw.line(surf, C.cendre, (mid, y - 3), (mid, y + h + 2))
    px = x + int(w * (max(-100, min(100, rel)) + 100) / 200)
    pygame.draw.polygon(surf, C.os, [(px, y + h // 2 - 1), (px - 5, y - 7), (px + 5, y - 7)])
    pygame.draw.polygon(surf, C.nuit, [(px, y + h // 2 - 1), (px - 5, y - 7), (px + 5, y - 7)], 1)


def verdict_line(state, pick: int, action: str, verdict) -> tuple[str, tuple]:
    if verdict.blocked:
        return verdict.blocked, C.cendre
    if action in ("guerre", "guerre_pays", "revolte"):
        return "Possible : survolez", C.alerte
    if action in ("rompre", "affranchir") and verdict.reasons:
        return verdict.reasons[0][0], (C.bon if action == "affranchir" else C.alerte)
    if state.tribes[pick].is_player and action in diplo.HUMAN_OFFERS:
        return "Un joueur : il décidera lui-même", C.ocre_jaune
    if verdict.accepted:
        return f"Ils accepteraient ({signed(verdict.score)})", C.bon
    return f"Ils refuseraient ({signed(verdict.score)})", C.mauvais


def _relevant(state, pick: int, action: str) -> bool:
    """Une action qui n'a pas de sens ici ne se montre pas du tout (affranchir
    un peuple libre, se revolter sans suzerain) ; les autres, oui (grisees)."""
    me = state.viewer
    if action == "affranchir":
        return guerre.vassal_pact(state, pick, me) is not None
    if action == "revolte":
        return guerre.vassal_pact(state, me, pick) is not None
    if action == "guerre":
        return guerre.vassal_pact(state, me, pick) is None and guerre.vassal_pact(state, pick, me) is None
    if action == "soumission":
        return guerre.declared_war(state, me, pick)
    if action == "guerre_pays":
        return chiefdom.top_lord(state, pick) != pick
    return True


def draw_peoples(r, state, layout, ui) -> None:
    s = r.screen
    items = layout["items"]
    lay = peoples_layout(layout["box"])
    bx, by, bw, bh = lay["box"]
    theme.panel(s, lay["box"], "peau")
    theme.title(s, "Peuples", bx + 26, by + 12, "titre")
    me = state.viewer
    peoples = known_peoples(state)
    tips = ui.setdefault("_ptips", [])
    tips.clear()
    if not peoples:
        theme.text(s, "Vous ne connaissez encore aucun autre peuple.", "texte", C.lin, (bx + 30, by + 80))
        theme.text(s, "Explorez : à 16 cases d'une de leurs bandes, vous les rencontrez.", "petit", C.cendre, (bx + 30, by + 110))
        r.people_list = None
        return
    # Les filtres.
    flt = ui.get("people_filter") or "tous"
    for key, label in PEOPLE_FILTERS:
        rect = lay["filters"][key]
        n = sum(1 for t in peoples if in_filter(state, t, key))
        items[f"pfilter:{key}"] = rect
        on = key == flt
        col = {"cordiaux": C.bon, "hostiles": C.mauvais, "guerre": C.mauvais}.get(key, C.braise if on else C.lin)
        poly = theme.chamfer(rect, 4)
        hover = _hover(rect)
        pygame.draw.polygon(s, theme._mix(C.charbon, col, 0.35 if on else (0.2 if hover else 0.1)), poly)
        pygame.draw.polygon(s, C.braise if on else (col if hover else theme._mix(C.charbon, col, 0.6)), poly, 2 if on else 1)
        f = theme.font("mini_gras")
        text = f"{label}  {n}"
        s.blit(f.render(text, True, C.os if on else theme._mix(col, C.os, 0.3)), (rect[0] + (rect[2] - f.size(text)[0]) // 2, rect[1] + 5))
    mine_power = diplo.power(state, me)
    force = f"Votre force : {mine_power:.0f}"
    fw_ = theme.font("petit_gras").size(force)[0]
    theme.text(s, force, "petit_gras", C.lin, (bx + bw - 26 - fw_, by + 26))
    s.blit(theme.icon("armee", 18, C.lin), (bx + bw - 50 - fw_, by + 26))
    # La liste.
    shown = [t for t in peoples if in_filter(state, t, flt)]
    pick = ui.get("people_pick")
    if pick not in peoples:
        pick = (shown or peoples)[0]
        ui["people_pick"] = pick
    top = clamp_people_top(lay, len(shown), ui.get("people_scroll", 0))
    ui["people_scroll"] = top
    r.people_list = lay["list"]
    r.people_scroll_info = (lay, len(shown))
    known = set(peoples) | {me}
    if not shown:
        theme.text(s, "Aucun peuple ici.", "petit", C.cendre, (lay["list"][0] + 12, lay["list"][1] + 10))
    for i, row in people_rows(lay, len(shown), top):
        tid = shown[i]
        t = state.tribes[tid]
        x, y, w, h = row
        items[f"people:{tid}"] = row
        chosen = tid == pick
        theme.panel(s, row, "carte_choisie" if chosen else ("carte_survol" if _hover(row) else "carte"))
        pygame.draw.circle(s, country_color(state, tid), (x + 18, y + 25), 9)
        pygame.draw.circle(s, C.nuit, (x + 18, y + 25), 9, 1)
        name = t.name + ("  (joueur)" if t.is_player else "")
        theme.text(s, name, "petit_gras", C.os, (x + 36, y + 5), w - 110)
        rel = diplo.relation(state, me, tid)
        val = signed(rel)
        f = theme.font("chiffre")
        s.blit(f.render(val, True, rel_color(rel)), (x + w - 12 - f.size(val)[0], y + 3))
        at_war = guerre.declared_war(state, me, tid)
        lvl = "En guerre" if at_war else diplo.level(state, me, tid)
        x2 = x + 36 + theme.text(s, lvl, "mini", C.mauvais if at_war else rel_color(rel), (x + 36, y + 28)) + 10
        ties = ties_of(state, tid, known)
        for kind, icon, _verb in TIES:
            if ties.get(kind) and x2 < x + w - 110:
                s.blit(theme.icon(icon, 14, TIE_COLORS.get(kind, C.lin)), (x2, y + 30))
                x2 += 18
        q = diplo.power(state, tid) / max(1.0, mine_power)
        ftxt = f"force x{q:.1f}".replace(".", ",")
        fm = theme.font("mini")
        s.blit(fm.render(ftxt, True, C.mauvais if q > 1.3 else C.cendre), (x + w - 12 - fm.size(ftxt)[0], y + 29))
    thumb = people_thumb(lay, len(shown), top)
    if thumb is not None:
        tx, ty, tw, th = lay["track"]
        pygame.draw.rect(s, (40, 31, 24), lay["track"], border_radius=3)
        items["ptrack"] = (tx - 4, ty, tw + 8, th)
        grab = ui.get("people_drag") is not None or _hover(thumb)
        pygame.draw.rect(s, C.braise if grab else C.ocre_jaune, thumb, border_radius=3)
        items["pthumb"] = thumb
        below = len(shown) - top - lay["visible"]
        text = (f"{top} plus haut" if top else "") + ("  ·  " if top and below > 0 else "") + (f"{below} plus bas" if below > 0 else "")
        if text:
            fm = theme.font("mini")
            theme.text(s, text, "mini", C.cendre, (lay["list"][0] + lay["list"][2] - fm.size(text)[0], lay["list"][1] - 18))
    _draw_card(r, state, lay, items, pick, known, tips)
    for tip in tips:
        theme.tooltip(s, tip[0], tip[1], tip[2], 360, avoid=tip[3] if len(tip) > 3 else None)


def _draw_card(r, state, lay, items, pick: int, known: set, tips: list) -> None:
    s = r.screen
    me = state.viewer
    t = state.tribes[pick]
    hx, hy, hw, hh = lay["head"]
    # L'en-tete.
    theme.panel(s, lay["head"], "carte")
    rad = 30 if hh < 100 else 34
    token(s, t.name, country_color(state, pick), hx + 16 + rad, hy + hh // 2, rad)
    tx = hx + 2 * rad + 34
    theme.text(s, t.name, "titre", C.os, (tx, hy + 6))
    homes = sites.of_tribe(state, pick, "village")
    pop = diplo.pop_of(state, pick)
    approx = max(10, int(round(pop / 10.0)) * 10)
    bands = sum(1 for b in state.bands.values() if b.tribe_id == pick and b.population > 0)
    bits = [label_of(t), f"~{approx} personnes"]
    if homes:
        names = ", ".join(x.name for x in homes[:3] if x.name) + ("..." if len(homes) > 3 else "")
        bits.append(f"{len(homes)} village{'s' if len(homes) > 1 else ''}" + (f" : {names}" if names else ""))
    else:
        bits.append(f"{bands} bande{'s' if bands > 1 else ''}")
    civ = civ_of(state, t)
    if civ == civ_of(state, state.tribes[me]):
        bits.append("votre civilisation")
    elif civ != t.id:
        bits.append(f"civilisation des {civ_name(state, civ)}")
    if t.origin and t.origin in state.tribes:
        bits.append("issus de votre peuple" if t.origin == me else f"issus des {state.tribes[t.origin].name}")
    if t.is_player:
        bits.append("mené par un joueur")
    right_w = 330
    theme.text(s, "  ·  ".join(bits), "petit", C.lin, (tx + 2, hy + 42), hw - (tx - hx) - right_w)
    way = approach.of(state, pick)
    if way:
        label, about = approach.APPROACHES[way]
        tint = APPROACH_COLORS.get(way, C.lin)
        ax = tx + 2
        cw_ = theme.chip(s, ax, hy + hh - 30, label, tint)
        theme.text(s, about, "mini", C.cendre, (ax + cw_ + 10, hy + hh - 28), hw - (ax + cw_ + 10 - hx) - right_w)
        arect = (ax, hy + hh - 32, cw_ + 10 + theme.font("mini").size(about)[0], 24)
        items["people_approach"] = arect
        if _hover(arect):
            rows = [(f"{label} : {about}", C.os, "petit_gras")]
            why = approach.reasons(state, pick)
            if why:
                rows.append(("Pourquoi :", C.cendre))
                rows += [(f"  {text}", C.lin) for text, _v in why[:5]]
            rows.append(("Ce que cela change :", C.cendre))
            rows += [(f"  {line}", tint) for line in approach.BEHAVIOR.get(way, ())]
            rows.append(("Elle change avec sa situation, et avec un nouveau chef.", C.cendre))
            tips.append((rows, arect[0], arect[1] + arect[3], arect))
    elif t.is_player:
        theme.text(s, "Mené par un joueur : il décide lui-même de son approche.", "mini", C.cendre, (tx + 2, hy + hh - 28))
    lead = chiefs.chief_of(state, pick)
    see = (hx + hw - 176, hy + 10, 164, 28)
    items["people_see"] = see
    _button(r, see, "Voir sur la carte", icon_key="voir")
    if lead is not None:
        traits = [chiefs.TRAITS[k].name for k in lead.traits if k in chiefs.TRAITS]
        theme.text(s, f"Chef : {lead.name}, {chiefs.age(state, lead)} ans", "petit_gras", C.ocre_jaune, (hx + hw - right_w, hy + 44), right_w - 16)
        cx_ = hx + hw - right_w
        for tr in traits[:3]:
            cx_ += theme.chip(s, cx_, hy + hh - 30, tr, C.ocre_jaune) + 6
    # Trois cartes.
    rel = diplo.relation(state, me, pick)
    c0, c1, c2 = lay["cards"]
    big = c0[3] >= 140
    # 1. Entre vous.
    x, y, w, h = c0
    theme.panel(s, c0, "creux")
    _section(s, x + 14, y + 10, w - 28, "Entre vous")
    f = theme.font("chiffre_grand")
    s.blit(f.render(signed(rel), True, rel_color(rel)), (x + 16, y + 30))
    lvl = "En guerre" if guerre.declared_war(state, me, pick) else diplo.level(state, me, pick)
    theme.text(s, lvl, "h3", C.mauvais if lvl == "En guerre" else rel_color(rel), (x + 24 + f.size(signed(rel))[0], y + 34))
    meter(s, x + 16, y + 72, w - 32, rel)
    yy = y + 88
    status = diplo.status_line(state, me, pick)
    if status:
        theme.text(s, status, "mini", C.ocre_jaune, (x + 16, yy), w - 32)
        yy += 18
    rx = x + 16
    reasons = diplo.reasons(state, me, pick)
    for label, v in reasons[: 3 if big else 2]:
        text = f"{signed(v)}  {label}"
        pw = theme.font("mini_gras").size(text)[0] + 14
        if rx + pw > x + w - 10:
            break
        rx += _pill(s, rx, yy, text, C.bon if v > 0 else C.mauvais) + 6
    why_rect = (x, y, w, h)
    if _hover(why_rect) and reasons:
        rows = [("Pourquoi cette relation", C.os, "petit_gras")]
        rows += [(f"{signed(v):>4}  {label}", C.bon if v > 0 else C.mauvais) for label, v in reasons]
        tips.append((rows, x + w + 8, y, why_rect))
    if diplo.has_pact(state, me, pick, "commerce"):
        button = (x + w - 186, y + 6, 176, 22)
        items["trade_with"] = button
        _button(r, button, "Routes commerciales [M]")
    # 2. Leur force.
    x, y, w, h = c1
    theme.panel(s, c1, "creux")
    _section(s, x + 14, y + 10, w - 28, "Leur force")
    theirs = diplo.power(state, pick)
    mine_power = diplo.power(state, me)
    peak = max(mine_power, theirs, 1.0)
    for i, (who, v, col) in enumerate((("Eux", theirs, color_of(t)), ("Vous", mine_power, C.braise))):
        by_ = y + 38 + i * 28
        theme.text(s, who, "petit_gras", C.lin, (x + 16, by_ - 4))
        theme.bar(s, (x + 70, by_, w - 150, 12), v / peak, col)
        theme.text(s, f"{v:.0f}", "chiffre", C.os, (x + w - 66, by_ - 6))
    text, col = power_text(mine_power, theirs)
    theme.text(s, text, "petit", col, (x + 16, y + 96))
    if big:
        theme.text(s, "Guerriers, villages, palissades : la force qu'ils montrent.", "mini", C.cendre, (x + 16, y + 120), w - 30)
    # 3. Leurs liens.
    x, y, w, h = c2
    theme.panel(s, c2, "creux")
    _section(s, x + 14, y + 10, w - 28, "Leurs liens")
    rows = tie_rows(state, pick, known)
    rows += [("politique", line + " (paix et guerre partagées)", C.ocre_jaune) for line in confed.lines(state, pick)]
    yy = y + 34
    if not rows:
        theme.text(s, "Aucun accord, aucune guerre connus.", "mini", C.cendre, (x + 16, yy))
    for icon, text, col in rows:
        parts = theme.wrap(theme.font("mini"), text, w - 56)
        if yy + 16 * len(parts[:2]) > y + h - 6:
            theme.text(s, "...", "mini", C.cendre, (x + 42, yy - 4))
            break
        s.blit(theme.icon(icon, 16, col), (x + 16, yy))
        for k, part in enumerate(parts[:2]):
            theme.text(s, part, "mini", col, (x + 40, yy + 16 * k))
        yy += 16 * len(parts[:2]) + 8
    # Leurs grands tournants, leurs savoirs.
    kx, ky, kw, _kh = lay["know"]
    mine = state.tribes[me].knowledge
    # Les grands tournants d'abord (en or), puis les savoirs.
    turns = {tt.id for tt in tech.turnings()}
    theirs_k = sorted((k for k in t.knowledge - mine if k in tech.TECHS), key=lambda k: (k not in turns, tech.TECHS[k].tier, k))
    teach = pick in getattr(state.diplo, "neighbors", {}).get(me, [])
    head = f"Ils savent ce que vous ignorez ({len(theirs_k)}) :" if theirs_k else "Ils ne savent rien que vous ignoriez."
    hw_ = theme.text(s, head, "petit", C.lin, (kx + 4, ky + 2))
    note = "voisins en bons termes : leurs savoirs passent chez vous" if teach else "trop loin ou trop hostiles pour l'apprendre d'eux"
    nw = theme.font("mini").size(note)[0]
    if theirs_k:
        theme.text(s, note, "mini", C.bon if teach else C.cendre, (kx + kw - nw - 4, ky + 4))
    cx_ = kx + hw_ + 14
    stop = kx + kw - nw - 18
    chips = [(tech.TECHS[k].name, C.ocre_jaune if k in turns else C.savoir, "couronne" if k in turns else "savoir") for k in theirs_k]
    for i, (name, col, icon) in enumerate(chips):
        cw_ = theme.font("mini_gras").size(name)[0] + 30
        if cx_ + cw_ > stop:
            rest = [n for n, _c, _i in chips[i:]]
            more = (cx_, ky + 2, 30, 22)
            theme.text(s, "...", "petit", C.savoir, (cx_ + 4, ky))
            if _hover(more):
                tips.append(([(", ".join(rest), C.lin)], cx_, ky + 24, more))
            break
        cx_ += theme.chip(s, cx_, ky + 3, name, col, icon_key=icon) + 6
    _draw_actions(r, state, lay, items, pick, tips)


def _draw_actions(r, state, lay, items, pick: int, tips: list) -> None:
    s = r.screen
    me = state.viewer
    t = state.tribes[pick]
    for (title, icon, med, acts), col in zip(FAMILIES, lay["cols"]):
        x, y, w, h = col
        bottom = y + h - 8
        theme.panel(s, col, "creux")
        s.blit(theme.medallion(icon, 13, med), (x + 10, y + 8))
        theme.text(s, title, "h2", C.os, (x + 44, y + 7))
        yy = y + 44
        locks = []
        for act in acts:
            if not _relevant(state, pick, act):
                continue
            if act == "cadeau":
                yy = _gifts(r, state, items, pick, x, yy, w, tips)
                continue
            if act == "present":
                if not money.has_money(state, me):
                    locks.append(("Offrir des sicles", tech.TECHS["argent_pese"].name, True))
                else:
                    yy = _presents(r, state, items, pick, x, yy, w, tips)
                continue
            verdict = diplo.evaluate(state, me, pick, act)
            wait = diplo.on_cooldown(state, me, pick, act) if act not in diplo.NO_COOLDOWN else 0
            label = diplo.ACTION_LABELS[act]
            if verdict.blocked:
                b = verdict.blocked
                if b.startswith("Il faut connaître "):
                    locks.append((label, b.replace("Il faut connaître ", ""), True))
                else:
                    locks.append((label, b, False))
                continue
            line, tint = verdict_line(state, pick, act, verdict)
            if t.is_player and act in diplo.HUMAN_OFFERS:
                verdict = diplo.Verdict(score=verdict.score)
            if wait:
                line, tint = f"Déjà proposé : attendez {wait} sem.", C.cendre
            if yy + 50 > bottom:
                locks.append((label, line, False))
                continue
            rect = (x + 12, yy, w - 24, 28)
            items[f"diplo:{act}"] = rect
            _button(r, rect, label, on=not wait)
            theme.text(s, line, "mini", tint, (x + 14, yy + 31), w - 28)
            if _hover(rect) and verdict.reasons:
                if act in ("guerre", "guerre_pays", "revolte"):
                    whom = t.name if act != "guerre_pays" else state.tribes[chiefdom.top_lord(state, pick)].name
                    head = ("Se révolter contre les " if act == "revolte" else "Déclarer la guerre aux ") + whom
                    rows = [(head, C.os, "petit_gras")] + [(f"  {lab}", C.alerte) for lab, _v in verdict.reasons]
                else:
                    rows = [(f"{signed(v):>4}  {lab}", C.bon if v > 0 else C.mauvais if v < 0 else C.lin) for lab, v in verdict.reasons]
                    if act not in ("rompre", "affranchir"):
                        rows.append((f"Total : {signed(verdict.score)} (il faut plus de 0)", C.os))
                tips.append((rows, rect[0] + rect[2] + 10, rect[1] - 4, rect))
            yy += 54
        invites = diplo.invitable(state, me, pick)[:2] if title == "Les soumettre" else []
        if invites:
            for band in invites:
                if yy + 50 > bottom:
                    break
                who = band.leader.name if band.leader else f"bande {band.id}"
                chance = round(100 * diplo.invite_chance(state, me, band))
                rect = (x + 12, yy, w - 24, 28)
                items[f"invite:{band.id}"] = rect
                _button(r, rect, f"Inviter le clan de {who}", on=state.tribes[me].prestige >= diplo.INVITE_COST)
                theme.text(s, f"{diplo.INVITE_COST} prestige · ~{chance} % · attachement {band.loyalty:.0f}", "mini", C.alerte, (x + 14, yy + 31), w - 28)
                yy += 54
        if locks and yy + 30 < bottom:
            _section(s, x + 12, yy + 2, w - 24, "Pas encore", C.cendre)
            yy += 26
            for k, (label, why, is_lock) in enumerate(locks):
                if yy + 34 > bottom:
                    rest = len(locks) - k
                    theme.text(s, f"et {rest} de plus", "mini", C.cendre, (x + 30, yy))
                    break
                if is_lock:
                    _lock(s, x + 18, yy + 8)
                else:
                    pygame.draw.line(s, C.cendre, (x + 14, yy + 9), (x + 22, yy + 9), 2)
                theme.text(s, label, "mini_gras", C.cendre, (x + 30, yy))
                theme.text(s, why, "mini", (128, 116, 102), (x + 30, yy + 16), w - 42)
                row = (x + 8, yy - 2, w - 16, 34)
                if _hover(row) and theme.font("mini").size(why)[0] > w - 42:
                    tips.append(([(label, C.os, "petit_gras"), (why, C.lin)], row[0] + row[2] + 8, row[1], row))
                yy += 36


def _gifts(r, state, items, pick, x, yy, w, tips) -> int:
    s = r.screen
    me = state.viewer
    verdict = diplo.evaluate(state, me, pick, "cadeau")
    theme.text(s, diplo.ACTION_LABELS["cadeau"], "petit_gras", C.os if not verdict.blocked else C.cendre, (x + 14, yy))
    sizes = diplo.gift_sizes(state, me, pick) if not verdict.blocked else []
    bw_ = (w - 24 - 2 * 8) // 3
    for i, amount in enumerate(diplo.GIFT_SIZES):
        rect = (x + 12 + i * (bw_ + 8), yy + 22, bw_, 28)
        items[f"gift:{amount}"] = rect
        on = amount in sizes
        _button(r, rect, str(amount), on=on, icon_key="vivres" if bw_ >= 80 else None)
        if on:
            gain = diplo.gift_value(state, me, pick, amount)
            theme.text(s, f"+{gain:.0f}", "mini_gras", C.bon, (rect[0] + rect[2] // 2 - 8, yy + 52))
            if _hover(rect):
                tips.append(([(f"{amount} vivres, portés par votre bande la plus proche", C.os), (f"Relation : +{gain:.0f}", C.bon)], rect[0] + rect[2] + 8, rect[1], rect))
    if verdict.blocked or not sizes:
        note = verdict.blocked or "Votre bande la plus proche n'a pas assez de vivres"
        theme.text(s, note, "mini", C.alerte, (x + 14, yy + 54), w - 28)
    return yy + 78


def _presents(r, state, items, pick, x, yy, w, tips) -> int:
    s = r.screen
    me = state.viewer
    verdict = diplo.evaluate(state, me, pick, "present")
    theme.text(s, diplo.ACTION_LABELS["present"], "petit_gras", C.os if not verdict.blocked else C.cendre, (x + 14, yy))
    sizes = diplo.present_sizes(state, me)
    bw_ = (w - 24 - 2 * 8) // 3
    for i, amount in enumerate(diplo.PRESENT_SIZES):
        rect = (x + 12 + i * (bw_ + 8), yy + 22, bw_, 28)
        items[f"present:{amount}"] = rect
        on = amount in sizes and not verdict.blocked
        _button(r, rect, str(amount), on=on, icon_key="pieces" if bw_ >= 80 else None)
        if on:
            gain = diplo.present_value(state, me, pick, amount)
            theme.text(s, f"+{gain:.0f}", "mini_gras", C.bon, (rect[0] + rect[2] // 2 - 8, yy + 52))
            if _hover(rect):
                rows = [(f"{amount} sicles, portés par des envoyés", C.os), (f"Relation : +{gain:.0f}", C.bon)]
                rows += [(label, C.lin) for label, _v in verdict.reasons[1:]]
                tips.append((rows, rect[0] + rect[2] + 8, rect[1], rect))
    note = verdict.blocked or ("" if money.has_money(state, pick) else "Ils ne connaissent pas l'argent : moitié moins")
    if note:
        theme.text(s, note, "mini", C.cendre, (x + 14, yy + 54), w - 28)
    return yy + 78
