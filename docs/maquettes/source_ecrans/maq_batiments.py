"""Trois maquettes de l'ecran des batiments, sur SON village (copie) : une
page "Les batiments" a part dans la fenetre du village (toute la largeur).
  A. Le plan du village : les places autour du feu, ce qui y est bati, les
     places a venir ; la liste de ce qu'on peut y batir a droite ;
  B. Les familles : des cartes par usage (defense, vivres, le peuple et ses
     morts, metiers et echanges), l'effet ecrit sur chaque carte ;
  C. Ce qu'on batit ensuite : ce que le village a, le chantier en cours
     (exemple), et la suite classee.
python maq_batiments.py RACINE SAUVEGARDE SORTIE"""
import math
import sys

import maq_commun as commun
from maq_commun import C, H, W, pygame, theme

from src.kora import batiments, places, tech, villages
from src.kora.render_village import PAGES, _page_tab, village_layout

st, play, r = commun.load(sys.argv[2], sys.argv[3])
OUT = sys.argv[3]
me = st.viewer
SITE = next(s for s in st.sites.values() if s.kind == "village" and s.tribe_id == me)
BAND = places.band_of(st, SITE)

ICON = {"palissade": "palissade", "grenier": "grenier", "puits": "eau", "maison_longue": "hutte", "enclos": "troupeau",
        "guerriers": "armee", "tour": "tour", "autel": "totem", "pierre": "menhir", "atelier": "poterie",
        "place": "balance", "monument": "dolmen"}
FAMILIES = (
    ("Défense", "palissade", ("palissade", "tour", "guerriers")),
    ("Vivres", "grenier", ("grenier", "enclos", "puits")),
    ("Le peuple et ses morts", "totem", ("maison_longue", "autel", "pierre")),
    ("Métiers et échanges", "poterie", ("atelier", "place")),
)
STATE_RING = {"bati": "connu", "chantier": "actif", "possible": "actif", "attente": "normal", "verrouille": "eteint"}


def status(bid):
    return batiments.building_status(st, SITE, bid)


def why_short(bid):
    """La raison en peu de mots : le savoir, la place, les vivres."""
    b = batiments.BUILDINGS[bid]
    stt = status(bid)
    if stt == "verrouille":
        if bid == "monument":
            return "Pendant les grands travaux"
        return tech.TECHS[b.needs].name
    why = batiments.build_block_site(st, SITE, bid)
    if why.startswith("Plus de place"):
        return "Plus de place"
    return why


def next_place():
    pop = BAND.population
    need = (batiments.slots(st, SITE) - batiments.BASE_SLOTS + 1) * batiments.SLOT_POP
    return need, max(0, need - pop)


def base(page_label="Les bâtiments"):
    """La fenetre du village (titre, onglets, tuiles), son corps vide, et
    un onglet de plus : Les batiments."""
    play.side_panel = None
    play.ui["village_open"] = SITE.id
    play.ui["village_page"] = "village"
    for _ in range(2):
        play._frame(1 / 60)
    s = r.screen
    lay = village_layout(W, H, 0, "village")
    for key, label in PAGES:
        _page_tab(r, lay["pages"][key], label, False, False)
    last = lay["pages"][PAGES[-1][0]]
    tab = (last[0] + last[2] + 8, last[1], 190, last[3])
    _page_tab(r, tab, page_label, True, False)
    bx, by, bw, bh = lay["box"]
    body_y = lay["tiles"][0][1] + 56 + 14
    body = (bx + 18, body_y - 4, bw - 36, by + bh - 12 - (body_y - 4))
    pygame.draw.rect(s, (40, 35, 31), body)
    theme.panel(s, body, "creux")
    return s, body


def effect_lines(bid):
    return list(batiments.BUILDINGS[bid].lines)


def cost_text(bid):
    return f"{batiments.build_cost(st, SITE, bid):.0f} vivres · {batiments.build_weeks(SITE, bid)} sem."


# --- A. le plan du village ------------------------------------------------------------------------


def maquette_a():
    s, (x0, y0, w0, h0) = base()
    # Le plan, a gauche.
    pw = int(w0 * 0.6)
    cx, cy = x0 + pw // 2, y0 + h0 // 2 + 30
    R = min(pw, h0) // 2 - 58
    theme.text(s, "Le plan de Netali", "h2", C.os, (x0 + 18, y0 + 12))
    theme.text(s, "Chaque place autour du feu est un bâtiment ; une place de plus vient avec 40 habitants.", "mini", C.cendre, (x0 + 20, y0 + 42))
    ground = pygame.Surface((2 * R + 40, 2 * R + 40), pygame.SRCALPHA)
    for k in range(18, 0, -1):
        t = k / 18
        col = theme._mix((92, 74, 48), (58, 46, 32), t)
        pygame.draw.circle(ground, (*col, 255), (R + 20, R + 20), int(R * (0.25 + 0.75 * t)))
    s.blit(ground, (cx - R - 20, cy - R - 20))
    # La palissade (batie) : des pieux en cercle.
    if batiments.palisade_state(SITE) == "built":
        n = 120
        for i in range(n):
            a = 2 * math.pi * i / n
            px, py = cx + (R + 6) * math.cos(a), cy + (R + 6) * math.sin(a)
            pygame.draw.line(s, (122, 92, 60), (px, py), (cx + (R + 15) * math.cos(a), cy + (R + 15) * math.sin(a)), 4)
            pygame.draw.circle(s, (160, 124, 84), (int(cx + (R + 15) * math.cos(a)), int(cy + (R + 15) * math.sin(a))), 2)
    # Les sentiers et les huttes.
    order = list(batiments.BUILD_ORDER)
    built = [b for b in order if status(b) in ("bati", "chantier")]
    rest = [b for b in order if b not in built]
    nplots = len(order)
    ring = R * 0.62
    for i in range(nplots):
        a = -math.pi / 2 + 2 * math.pi * i / nplots
        theme.dotted(s, (cx, cy), (int(cx + ring * math.cos(a)), int(cy + ring * math.sin(a))), (130, 104, 72), 7)
    for i in range(nplots):
        a = -math.pi / 2 + 2 * math.pi * (i + 0.5) / nplots
        hx, hy = cx + R * 0.86 * math.cos(a), cy + R * 0.86 * math.sin(a)
        s.blit(theme.icon("hutte", 22, (150, 120, 84)), (hx - 11, hy - 11))
    theme.glow(s, (cx - 40, cy - 40, 80, 80), C.braise, 0.9)
    s.blit(theme.medallion("feu", 26, "actif"), (cx - 28, cy - 28))
    # Les places.
    slots = batiments.slots(st, SITE)
    need, missing = next_place()
    plots = built + [None] * max(0, slots - len(built))
    plots += ["future"] * (nplots - len(plots))
    hover_i = built.index("tour") if "tour" in built else 0
    for i, what in enumerate(plots):
        a = -math.pi / 2 + 2 * math.pi * i / nplots
        px, py = int(cx + ring * math.cos(a)), int(cy + ring * math.sin(a))
        if what == "future":
            for k in range(0, 360, 20):
                aa = math.radians(k)
                pygame.draw.circle(s, (120, 100, 78), (int(px + 26 * math.cos(aa)), int(py + 26 * math.sin(aa))), 2)
            commun.lock(s, px, py - 2, (140, 120, 96))
            lab = f"à {need + (i - slots) * batiments.SLOT_POP} hab."
            f = theme.font("mini")
            s.blit(f.render(lab, True, (150, 130, 106)), (px - f.size(lab)[0] // 2, py + 30))
            continue
        if what is None:
            pygame.draw.circle(s, C.bon, (px, py), 26, 2)
            theme.text(s, "+", "h1", C.bon, (px - 7, py - 18))
            continue
        stt = status(what)
        if i == hover_i:
            theme.glow(s, (px - 36, py - 36, 72, 72), C.braise, 0.8)
        s.blit(theme.medallion(ICON[what], 26, STATE_RING[stt]), (px - 28, py - 28))
        name = batiments.building_name(SITE, what, short=True)
        f = theme.font("mini_gras")
        tw = f.size(name)[0]
        pygame.draw.rect(s, (24, 18, 14), (px - tw // 2 - 5, py + 29, tw + 10, 19), border_radius=3)
        s.blit(f.render(name, True, C.os), (px - tw // 2, py + 30))
    pick = built[hover_i]
    # A droite : batir.
    rx, rw = x0 + pw + 10, w0 - pw - 28
    yy = y0 + 14
    theme.text(s, "Bâtir", "h2", C.os, (rx, yy))
    yy += 40
    used = batiments.used_slots(SITE)
    theme.text(s, f"Places : {used} sur {slots}", "texte_gras", C.os, (rx, yy))
    theme.text(s, f"une de plus à {need} habitants", "petit", C.lin, (rx + 170, yy + 2))
    yy += 30
    theme.bar(s, (rx, yy, rw - 10, 12), BAND.population / need, C.ocre_jaune)
    theme.text(s, f"{BAND.population} habitants · encore {missing}", "mini", C.cendre, (rx, yy + 16))
    yy += 44
    theme.text(s, "Aucun chantier en cours.", "petit", C.cendre, (rx, yy))
    yy += 34
    commun.section(s, rx, yy, rw - 10, "Dès qu'une place s'ouvre")
    yy += 26
    for bid in rest:
        stt = status(bid)
        if stt not in ("attente", "possible"):
            continue
        yy = _row(s, rx, yy, rw - 10, bid)
    yy += 6
    commun.section(s, rx, yy, rw - 10, "Il faut un savoir", C.cendre)
    yy += 26
    for bid in rest:
        if status(bid) == "verrouille":
            yy = _row(s, rx, yy, rw - 10, bid, compact=True)
    # La place choisie (un clic sur le plan).
    yy += 4
    commun.section(s, rx, yy, rw - 10, "La place choisie")
    yy += 26
    card = (rx, yy, rw - 10, 70)
    theme.panel(s, card, "carte_choisie")
    s.blit(theme.medallion(ICON[pick], 22, "connu"), (rx + 10, yy + 12))
    theme.text(s, batiments.BUILDINGS[pick].name, "petit_gras", C.os, (rx + 64, yy + 10))
    commun.check(s, rx + 70, yy + 42)
    theme.text(s, "Bâtie", "mini_gras", C.ocre_jaune, (rx + 82, yy + 34))
    ey = yy + 8
    for line in effect_lines(pick):
        theme.text(s, f"›  {line}", "mini", C.bon, (rx + 210, ey), rw - 230)
        ey += 18
    commun.tag(s, "Maquette A · Le plan du village (Netali, an 44)")
    commun.save(s, f"{OUT}/batiments_A_plan.png")


def _row(s, x, y, w, bid, compact=False):
    stt = status(bid)
    h = 62 if compact else 92
    theme.panel(s, (x, y, w, h), "carte")
    s.blit(theme.medallion(ICON[bid], 20, STATE_RING[stt]), (x + 10, y + 10))
    theme.text(s, batiments.building_name(SITE, bid), "petit_gras", C.os if stt != "verrouille" else C.lin, (x + 60, y + 8))
    why = why_short(bid)
    if stt == "verrouille":
        commun.lock(s, x + 66, y + 39)
        theme.text(s, why, "mini", C.cendre, (x + 78, y + 32), w - 230)
        theme.text(s, effect_lines(bid)[0], "mini", (150, 168, 120), (x + w - 12 - min(240, theme.font("mini").size(effect_lines(bid)[0])[0]), y + 32), 240)
        return y + h + 8
    theme.text(s, cost_text(bid), "mini", C.lin, (x + 60, y + 30))
    for k, line in enumerate(effect_lines(bid)[:2]):
        theme.text(s, f"›  {line}", "mini", C.bon, (x + 60, y + 50 + 17 * k), w - 200)
    btn = (x + w - 130, y + 12, 118, 28)
    theme.button(s, btn, "Construire", "principal" if stt == "possible" else "second", on=stt == "possible")
    if stt != "possible":
        commun.pill(s, x + w - 12, y + 50, why, C.alerte, right=True)
    return y + h + 8


# --- B. les familles ------------------------------------------------------------------------------


def maquette_b():
    s, (x0, y0, w0, h0) = base()
    # Le bandeau : les places, le chantier.
    slots = batiments.slots(st, SITE)
    used = batiments.used_slots(SITE)
    need, missing = next_place()
    theme.text(s, "Places", "etiquette", C.ocre_jaune, (x0 + 18, y0 + 16))
    px = x0 + 80
    for i in range(len(batiments.BUILD_ORDER)):
        rect = (px + i * 26, y0 + 14, 20, 20)
        poly = theme.chamfer(rect, 4)
        if i < used:
            pygame.draw.polygon(s, C.ocre_jaune, poly)
        elif i < slots:
            pygame.draw.polygon(s, C.bon, poly, 2)
        else:
            pygame.draw.polygon(s, (70, 58, 46), poly, 1)
    theme.text(s, f"{used} sur {slots} · une de plus à {need} habitants (encore {missing})", "petit", C.lin, (px + 26 * 12 + 10, y0 + 15))
    chx = x0 + w0 - 520
    theme.panel(s, (chx, y0 + 8, 500, 34), "carte")
    s.blit(theme.icon("sablier", 18, C.cendre), (chx + 10, y0 + 16))
    theme.text(s, "Aucun chantier · le prochain : Autel des ancêtres, dès qu'une place s'ouvre", "mini", C.lin, (chx + 36, y0 + 17), 456)
    # Les familles.
    top = y0 + 56
    cols = len(FAMILIES)
    gap = 14
    cw = (w0 - 36 - gap * (cols - 1)) // cols
    for ci, (fname, ficon, bids) in enumerate(FAMILIES):
        fx = x0 + 18 + ci * (cw + gap)
        s.blit(theme.medallion(ficon, 15, "connu"), (fx, top))
        theme.text(s, fname, "h2", C.os, (fx + 42, top + 4))
        yy = top + 46
        for bid in bids:
            yy = _card(s, fx, yy, cw, bid)
        if ci == cols - 1:
            _monument(s, fx, yy, cw)
    commun.tag(s, "Maquette B · Les familles de bâtiments (Netali, an 44)")
    commun.save(s, f"{OUT}/batiments_B_familles.png")


def _card(s, x, y, w, bid):
    stt = status(bid)
    h = 168
    kind = {"bati": "carte", "possible": "carte_survol", "chantier": "carte_choisie"}.get(stt, "carte")
    theme.panel(s, (x, y, w, h), kind)
    if stt == "verrouille":
        veil = pygame.Surface((w, h), pygame.SRCALPHA)
        veil.fill((14, 11, 9, 90))
        s.blit(veil, (x, y))
    s.blit(theme.medallion(ICON[bid], 24, STATE_RING[stt]), (x + 12, y + 12))
    theme.text(s, batiments.building_name(SITE, bid), "petit_gras", C.os if stt != "verrouille" else C.lin, (x + 70, y + 12), w - 80)
    if stt == "bati":
        commun.check(s, x + 76, y + 44, C.ocre_jaune)
        theme.text(s, "Bâti", "mini_gras", C.ocre_jaune, (x + 88, y + 36))
    elif stt == "verrouille":
        commun.lock(s, x + 76, y + 43)
        theme.text(s, why_short(bid), "mini", C.cendre, (x + 88, y + 36), w - 100)
    else:
        commun.pill(s, x + 70, y + 36, why_short(bid) or "Possible", C.alerte if stt == "attente" else C.bon)
    theme.text(s, batiments.BUILDINGS[bid].text, "recit_petit", C.lin if stt != "verrouille" else C.cendre, (x + 14, y + 72), w - 28)
    yy = y + 98
    for line in effect_lines(bid)[:3]:
        theme.text(s, f"›  {line}", "mini", C.bon if stt == "bati" else (150, 168, 120), (x + 14, yy), w - 28)
        yy += 18
    if stt != "bati":
        theme.text(s, cost_text(bid), "mini", C.cendre, (x + w - 12 - theme.font("mini").size(cost_text(bid))[0], y + 12))
    return y + h + 10


def _monument(s, x, y, w):
    bid = "monument"
    stt = status(bid)
    h = 168
    theme.panel(s, (x, y, w, h), "pierre")
    s.blit(theme.medallion(ICON[bid], 24, STATE_RING[stt]), (x + 12, y + 12))
    theme.text(s, "Grand monument", "petit_gras", C.os, (x + 70, y + 12))
    commun.lock(s, x + 76, y + 43)
    theme.text(s, "Pendant les grands travaux", "mini", C.cendre, (x + 88, y + 36))
    n = places.monument_stages(SITE)
    for i in range(batiments.MONUMENT_STAGES):
        rect = (x + 14 + i * 30, y + 74, 24, 30)
        pygame.draw.polygon(s, C.ocre_jaune if i < n else (70, 58, 46), theme.chamfer(rect, 5), 0 if i < n else 1)
    theme.text(s, f"{n} étape sur {batiments.MONUMENT_STAGES}", "mini", C.lin, (x + 14 + 6 * 30 + 8, y + 82))
    yy = y + 114
    for line in effect_lines(bid)[1:3]:
        theme.text(s, f"›  {line}", "mini", (150, 168, 120), (x + 14, yy), w - 28)
        yy += 18
    return y + h + 10


# --- C. ce qu'on batit ensuite ---------------------------------------------------------------------


def maquette_c():
    # Exemple : 290 habitants (une 9e place), l'autel en chantier (4 semaines sur 6).
    real_pop = BAND.population
    BAND.population = 290
    SITE.data.build = ["autel", 4]
    s, (x0, y0, w0, h0) = base()
    lw = 430
    cw = 520
    rw = w0 - lw - cw - 60
    # 1. ce que le village a.
    x = x0 + 18
    theme.text(s, "Ce que Netali a", "h2", C.os, (x, y0 + 12))
    built = [b for b in batiments.BUILD_ORDER if status(b) == "bati"]
    for i, bid in enumerate(built):
        col, row = i % 4, i // 4
        px, py = x + col * 104, y0 + 56 + row * 96
        s.blit(theme.medallion(ICON[bid], 24, "connu"), (px + 26, py))
        name = batiments.building_name(SITE, bid, short=True)
        for k, part in enumerate(theme.wrap(theme.font("mini"), name, 100)[:2]):
            f = theme.font("mini")
            s.blit(f.render(part, True, C.lin), (px + 52 - f.size(part)[0] // 2, py + 54 + 15 * k))
    yy = y0 + 56 + 2 * 96 + 14
    commun.section(s, x, yy, lw - 10, "Ce que cela fait")
    yy += 28
    parts = villages.defense_parts(st, BAND)
    dm = 1.0
    for _lab, m in parts:
        dm *= m
    rows = [
        ("palissade", f"Défense x{dm:.2f}".replace(".", ","), " · ".join(f"{lab} x{m:.2f}".replace(".", ",") for lab, m in parts)),
        ("grenier", "Grenier : +8 semaines", "le grain se gâte x0,6"),
        ("hutte", "Croissance x1,2", "maison longue"),
        ("troupeau", "Vivres x1,1", "enclos"),
        ("eau", "Fièvres x0,6", "puits"),
        ("armee", "Troupes : force x1,25, moral +10", "une compagnie de plus"),
        ("poterie", "Métiers x1,25", "ateliers"),
        ("tour", "Vue +3, alerte", "tour de guet"),
    ]
    for icon, main, sub in rows:
        s.blit(theme.icon(icon, 18, C.ocre_jaune), (x, yy))
        theme.text(s, main, "petit", C.os, (x + 28, yy - 1))
        theme.text(s, sub, "mini", C.cendre, (x + 28 + theme.font("petit").size(main)[0] + 10, yy + 1), lw - 40 - theme.font("petit").size(main)[0])
        yy += 26
    # 2. le chantier.
    cx0 = x0 + 18 + lw + 20
    theme.text(s, "Le chantier", "h2", C.os, (cx0, y0 + 12))
    card = (cx0, y0 + 52, cw, 330)
    theme.glow(s, card, C.braise, 0.5)
    theme.panel(s, card, "carte_choisie")
    bid, left = SITE.data.build
    total = batiments.build_weeks(SITE, bid)
    done = (total - left) / total
    mx, my = cx0 + 90, y0 + 52 + 100
    pygame.draw.circle(s, (30, 22, 16), (mx, my), 62, 8)
    pygame.draw.arc(s, C.braise, (mx - 62, my - 62, 124, 124), math.pi / 2 - 2 * math.pi * done, math.pi / 2, 8)
    s.blit(theme.medallion(ICON[bid], 46, "actif"), (mx - 48, my - 48))
    theme.text(s, batiments.BUILDINGS[bid].name, "h1", C.os, (cx0 + 176, y0 + 70))
    theme.text(s, f"encore {left} semaines sur {total}", "texte", C.braise, (cx0 + 178, y0 + 108))
    theme.text(s, batiments.BUILDINGS[bid].text, "recit_petit", C.lin, (cx0 + 178, y0 + 138), cw - 200)
    yy = y0 + 52 + 190
    commun.section(s, cx0 + 20, yy, cw - 40, "Quand il sera fini")
    yy += 28
    for line in effect_lines(bid):
        theme.text(s, f"›  {line}", "petit", C.bon, (cx0 + 24, yy), cw - 50)
        yy += 22
    theme.button(s, (cx0 + 20, y0 + 52 + 330 - 46, 250, 32), "Payer des bâtisseurs (sicles)", "second", on=False, icon_key="pieces")
    theme.text(s, "Il faut L'argent pesé", "mini", C.cendre, (cx0 + 284, y0 + 52 + 330 - 38))
    # Le journal du village : ce qui a ete bati.
    yy = y0 + 52 + 350
    commun.section(s, cx0, yy, cw, "Les places")
    yy += 28
    slots = batiments.slots(st, SITE)
    used = batiments.used_slots(SITE)
    need, missing = next_place()
    theme.text(s, f"{used} sur {slots} prises (le chantier en tient une)", "petit", C.os, (cx0, yy))
    yy += 26
    theme.bar(s, (cx0, yy, cw, 12), BAND.population / need, C.ocre_jaune)
    theme.text(s, f"Une place de plus à {need} habitants : encore {missing}", "mini", C.cendre, (cx0, yy + 16))
    # 3. ensuite.
    rx = cx0 + cw + 24
    theme.text(s, "Ensuite", "h2", C.os, (rx, y0 + 12))
    yy = y0 + 52
    for bid in [b for b in batiments.BUILD_ORDER if status(b) not in ("bati", "chantier")]:
        stt = status(bid)
        h = 132
        theme.panel(s, (rx, yy, rw, h), "carte")
        s.blit(theme.medallion(ICON[bid], 20, STATE_RING[stt]), (rx + 10, yy + 10))
        theme.text(s, batiments.building_name(SITE, bid), "petit_gras", C.os, (rx + 58, yy + 8), rw - 70)
        if stt == "verrouille":
            commun.lock(s, rx + 64, yy + 38)
            theme.text(s, "Il faut : " + why_short(bid), "mini", C.cendre, (rx + 76, yy + 31), rw - 90)
        else:
            commun.pill(s, rx + 58, yy + 31, why_short(bid) or "Possible", C.alerte)
        theme.text(s, "Ce qu'il changera ici :", "mini", C.lin, (rx + 14, yy + 60))
        y2 = yy + 78
        for line in effect_lines(bid)[:2]:
            theme.text(s, f"›  {line}", "mini", C.bon, (rx + 14, y2), rw - 28)
            y2 += 17
        if bid != "monument":
            theme.text(s, cost_text(bid), "mini", C.cendre, (rx + rw - 12 - theme.font("mini").size(cost_text(bid))[0], yy + 10))
        yy += h + 10
    SITE.data.build = None
    BAND.population = real_pop
    commun.tag(s, "Maquette C · Ce qu'on bâtit ensuite (Netali, an 44 ; exemple : 290 habitants, l'autel en chantier)")
    commun.save(s, f"{OUT}/batiments_C_ensuite.png")


maquette_a()
maquette_b()
maquette_c()
