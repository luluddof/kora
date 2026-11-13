"""LE REWORK DES INTERFACES, premiere serie (sa demande du 2026-11-12 : "rework
les interfaces de plein de choses ; pour chaque interface, des propositions,
je choisirai"). Ce qu'on voit a chaque minute de jeu, sur SA partie (copie) :
  HUD  la barre du haut et le rail   A le bandeau des comptes (EU5)
                                      B les alertes (Victoria 3)
                                      C le dock en bas (CK3)
  VIL  le panneau Village (B)        A le tableau   B le portrait du peuple
  UNI  l'unite choisie               A la fiche a jauges   B la fiche laterale
  EVE  la carte d'evenement          A le recit illustre   B la carte a jouer
                                      C dans le coin (sans arreter le jeu)
  JOU  le journal                    A la chronique   B a faire / nouvelles
python maq_rework1.py RACINE SAUVEGARDE SORTIE"""
import sys

import maq_commun as commun
from maq_commun import C, H, W, pygame, theme

from src.kora import chiefdom, chiefs, decisions, events, goods, grain, money, places, render_panels, sites, tech, troupes, villages
from src.kora.events_data import EVENTS
from src.kora.gamestate import log_of
from src.kora.layout import HUD_HEIGHT
from src.kora.log import LogKind

st, play, r = commun.load(sys.argv[2], sys.argv[3])
OUT = sys.argv[3]
me = st.viewer
tribe = st.tribes[me]
site = next(s for s in sorted(st.sites.values(), key=lambda s: s.id) if s.kind == "village" and s.tribe_id == me)
home = places.band_of(st, site)
pop = sum(b.population for b in st.bands.values() if b.tribe_id == me)
stab = villages.stability(st, site)
to_harvest, margin = villages.food_outlook(st, site, home)
weeks = home.stock / max(1, home.population)
chief_band = st.bands.get(tribe.chief_band)
chief = chief_band.leader if chief_band is not None else None
chief_age = chiefs.age(st, chief) if chief else 0
chief_traits = [chiefs.TRAITS[t].name for t in (chief.traits if chief else ()) if t in chiefs.TRAITS]
learning = tech.TECHS.get(tribe.learning) if tribe.learning else None
month_money = sum(tribe.money_month.values()) if tribe.money_month else 0.0
pending = [i for i in events.pending(st) if i.tribe_id == me]
n_decide = decisions.possible_count(st, me)
season = st.clock.season().name.capitalize().replace("Ete", "Été")
SEASON = {"PRINTEMPS": "Printemps", "ETE": "Été", "AUTOMNE": "Automne", "HIVER": "Hiver"}[st.clock.season().name]
fams = chiefdom.families(st, me)
log = list(reversed(log_of(st, me).entries))[:14]
KIND_ICON = {LogKind.COMBAT: "combat", LogKind.SURVIE: "survie", LogKind.SAISON: "printemps", LogKind.DECOUVERTE: "decouverte", LogKind.POLITIQUE: "politique"}
KIND_COL = {LogKind.COMBAT: C.mauvais, LogKind.SURVIE: C.alerte, LogKind.SAISON: C.bon, LogKind.DECOUVERTE: C.savoir, LogKind.POLITIQUE: C.ocre_jaune}
play.toasts = []
ev = EVENTS["visiteurs"]
army = inst = opts = None
_CARDS = render_panels.draw_event_cards


def backdrop(side=None, cards=True):
    """La carte du jeu (sans les messages qui passent) ; cards=False : sans
    les cartes d'evenement a gauche (une proposition les remplace)."""
    play.toasts = []
    render_panels.draw_event_cards = _CARDS if cards else (lambda *a, **k: None)
    try:
        return commun.backdrop(play, r, side).copy()
    finally:
        render_panels.draw_event_cards = _CARDS


BASE = backdrop()


def fire_event():
    global inst, opts
    if inst is None:
        inst = events._new_instance(st, ev, me, home.id)
        events.fire(st, inst)
        opts = events.options_for(st, inst)
        play.last_log_seq = log_of(st, me).seq


def raise_troop():
    global army
    if army is None:
        army = troupes.raise_army(st, home.id)
        play.last_log_seq = log_of(st, me).seq


def base(side=None, rail=True, top=True, cards=True):
    s = backdrop(side, cards) if (side or not cards) else BASE.copy()
    if not rail:
        # Le rail efface : la carte d'a cote recopiee par-dessus.
        strip = s.subsurface((W - 170, HUD_HEIGHT, 85, H - HUD_HEIGHT)).copy()
        s.blit(strip, (W - 85, HUD_HEIGHT))
    if not top:
        strip = s.subsurface((0, HUD_HEIGHT + 2, W, HUD_HEIGHT)).copy()
        s.blit(strip, (0, 0))
    return s


def text_wrap(s, text, role, color, x, y, width, gap=None, limit=99):
    f = theme.font(role)
    gap = gap or f.get_height() + 2
    for line in theme.wrap(f, text, width)[:limit]:
        theme.text(s, line, role, color, (x, y))
        y += gap
    return y


def chip(s, x, y, text, color, right=False):
    return commun.pill(s, x, y, text, color, right=right)


def gauge(s, x, y, w, label, value_text, frac, color, sub="", marks=()):
    theme.text(s, label, "mini", C.cendre, (x, y))
    vt = theme.font("mini_gras").size(value_text)[0]
    theme.text(s, value_text, "mini_gras", color, (x + w - vt, y))
    theme.bar(s, (x, y + 20, w, 8), max(0.0, min(1.0, frac)), color, marks=marks)
    if sub:
        theme.text(s, sub, "mini", C.cendre, (x, y + 32), w)
    return y + (52 if sub else 36)


def tip(s, lines, x, y, width=360):
    """Une fiche au survol : (texte, "titre" | "alerte" | "")."""
    style = {"titre": (C.os, "petit_gras"), "alerte": (C.mauvais, "petit"), "": (C.lin, "petit")}
    theme.tooltip(s, [(t, *style[k]) for t, k in lines], x, y, width)


def key_cap(s, x, y, letter, color=C.cendre):
    f = theme.font("mini_gras")
    w = max(16, f.size(letter)[0] + 8)
    pygame.draw.rect(s, C.nuit, (x, y, w, 16), border_radius=3)
    pygame.draw.rect(s, color, (x, y, w, 16), 1, border_radius=3)
    s.blit(f.render(letter, True, color), (x + (w - f.size(letter)[0]) // 2, y))
    return w


def save(s, name, label):
    commun.tag(s, label)
    commun.save(s, f"{OUT}/{name}.png")


# --- HUD -----------------------------------------------------------------------------------


def date_block(s, x=10, y=6):
    s.blit(theme.medallion("printemps", 18, "actif"), (x, y))
    theme.text(s, SEASON, "h2", C.os, (x + 46, y - 2), shadow=True)
    theme.text(s, f"an {st.clock.year} · semaine {st.clock.week}", "petit", C.lin, (x + 47, y + 22))


def speed_block(s, cx, y=10):
    x = cx - 100
    theme.icon_button(s, (x, y, 34, 30), "jouer", True, False, active=True)
    for i in range(5):
        rect = (x + 44 + i * 30, y + 3, 26, 24)
        theme.button(s, rect, str(i + 1), "second", True, False, role="mini_gras", active=i == 0)


def hud_a():
    """A : le bandeau des comptes. Chaque compte : son icone, son chiffre, ce
    qui le fait bouger, en couleur s'il inquiete ; le survol detaille."""
    s = base(top=False)
    th = 66
    theme.panel(s, (0, 0, W, th), "bandeau")
    pygame.draw.line(s, C.ocre_sombre, (0, th - 1), (W, th - 1), 2)
    date_block(s, 10, 10)
    theme.text(s, "Néolithique", "mini_gras", C.braise, (172, 10))
    speed_block(s, 360, 18)
    blocks = [
        ("gens", "Gens", f"{pop}", "+0 % par an", C.os),
        ("vivres", "Vivres", f"{weeks:.0f} sem.", f"−{-margin:.0f} sem. à la récolte" if margin < 0 else f"{margin:.1f} sem. de marge", C.mauvais if margin < 0 else C.os),
        ("tresor", "Trésor", f"{tribe.money:.0f} sicles", f"{month_money:+.1f} le mois dernier", C.os),
        ("prestige", "Prestige", f"{tribe.prestige}", "chef des chefs à 80", C.ocre_jaune),
        ("village", "Stabilité", f"{stab:.0f}", "florissant", C.bon),
    ]
    x = 480
    bw = 168
    mouse = None
    for i, (ic, name, val, sub, col) in enumerate(blocks):
        rect = (x, 6, bw - 8, th - 12)
        theme.panel(s, rect, "carte_survol" if i == 1 else "carte")
        s.blit(theme.icon(ic, 22, col if col is not C.os else C.ocre_jaune), (x + 8, 10))
        theme.text(s, name.upper(), "etiquette", C.cendre, (x + 36, 8))
        theme.text(s, val, "chiffre", col, (x + 36, 24))
        theme.text(s, sub, "mini", C.mauvais if col is C.mauvais else C.cendre, (x + 8, 46), bw - 20)
        if i == 1:
            mouse = (x + 60, 40)
        x += bw
    # Le savoir en cours, avec sa barre.
    sx = x + 6
    theme.panel(s, (sx, 6, W - sx - 10, th - 12), "carte")
    s.blit(theme.icon("savoir", 22, C.savoir), (sx + 8, 10))
    theme.text(s, "SAVOIR", "etiquette", C.cendre, (sx + 36, 8))
    theme.text(s, learning.name if learning else "À choisir [T]", "petit_gras", C.os if learning else C.braise, (sx + 36, 24), W - sx - 60)
    theme.bar(s, (sx + 8, 48, W - sx - 30, 6), 0.4 if learning else 0.0, C.savoir)
    # Le survol des vivres : d'ou vient le chiffre.
    lines = [
        ("Vivres d'Ilsen", "titre"),
        (f"Au grenier : {home.stock:.0f} ({weeks:.1f} semaines pour {home.population} personnes)", ""),
        (f"La récolte : dans {to_harvest} semaines", ""),
        (f"La cueillette et la pêche couvrent une part de ce qu'on mange", ""),
        (f"À la récolte, il manquera {-margin:.1f} semaine de vivres" if margin < 0 else f"À la récolte, il restera {margin:.1f} semaines", "alerte" if margin < 2 else ""),
        ("Que faire : Décisions [D] (rationner, acheter du grain...)", ""),
    ]
    tip(s, lines, mouse[0], th + 6, 380)
    # Le rail : des pastilles a compte.
    rail_badges(s)
    save(s, "HUD_A_bandeau_des_comptes", "HUD A · Le bandeau des comptes (chaque chiffre dit ce qui le fait bouger ; survol : d'où il vient)")


def rail_badges(s):
    tabs = r.side_hits.get("tabs", {}) if hasattr(r, "side_hits") else {}
    marks = {"decisions": (str(n_decide), C.bon), "peuples": ("2", C.braise), "savoirs": ("!", C.braise)}
    for key, (txt, col) in marks.items():
        rect = tabs.get(key)
        if rect is None:
            continue
        x, y, w, h = rect
        f = theme.font("mini_gras")
        bw = max(18, f.size(txt)[0] + 10)
        pygame.draw.circle(s, col, (x + w - 8, y + 8), 10)
        pygame.draw.circle(s, C.nuit, (x + w - 8, y + 8), 10, 2)
        s.blit(f.render(txt, True, C.nuit), (x + w - 8 - f.size(txt)[0] // 2, y + 8 - f.get_height() // 2))


def hud_b():
    """B : les alertes. Sous la barre, une rangee de pastilles : ce qui
    demande votre attention, par ordre d'urgence ; un clic y mene. Le rail
    range ses onglets par familles."""
    s = base(rail=False, cards=False)
    alerts = [
        ("famine", f"La soudure : il manquera {-margin:.0f} sem. de vivres à la récolte" if margin < 0 else "La soudure arrive", C.mauvais, "Décisions"),
        ("evenement", f"{len(pending)} événements à décider", C.braise, "E"),
        ("savoir", "Choisir un savoir", C.savoir, "T"),
        ("couronne", f"{n_decide} décisions possibles", C.bon, "D"),
        ("peuples", "Les Lilimae proposent une alliance", C.ocre_jaune, "P"),
    ]
    x, y = 12, HUD_HEIGHT + 8
    for ic, text, col, k in alerts:
        f = theme.font("petit_gras")
        w = f.size(text)[0] + 64
        rect = (x, y, w, 34)
        theme.panel(s, rect, "infobulle")
        pygame.draw.rect(s, col, (x, y + 4, 4, 26))
        s.blit(theme.icon(ic, 20, col), (x + 12, y + 7))
        theme.text(s, text, "petit_gras", C.os, (x + 38, y + 7))
        x += w + 8
    # Le rail par familles.
    groups = [("GOUVERNER", [("village", "Village", "B"), ("couronne", "Décisions", "D"), ("balance", "Pays", "N"), ("tresor", "Trésor", "G")]),
              ("LE MONDE", [("peuples", "Peuples", "P"), ("commerce", "Commerce", "M"), ("combat", "Guerre", "W")]),
              ("SAVOIR", [("savoir", "Savoirs", "T"), ("journal", "Journal", "J")])]
    rx, ry = W - 84, HUD_HEIGHT + 56
    for title, items in groups:
        theme.text(s, title, "etiquette", C.ocre_jaune, (rx - 2, ry))
        ry += 20
        for ic, name, k in items:
            rect = (rx, ry, 78, 54)
            theme.panel(s, rect, "carte_choisie" if name == "Décisions" else "carte")
            s.blit(theme.icon(ic, 24, C.ocre_jaune if name == "Décisions" else C.lin), (rx + 27, ry + 5))
            theme.text(s, name, "mini_gras", C.lin, (rx + 39 - theme.font("mini_gras").size(name)[0] // 2, ry + 32))
            key_cap(s, rx + 2, ry + 2, k, C.cendre)
            ry += 58
        ry += 8
    save(s, "HUD_B_les_alertes", "HUD B · Les alertes (ce qui demande votre attention, sous la barre ; le rail rangé par familles)")


def hud_c():
    """C : le dock en bas. La barre du haut ne garde que le temps et les
    comptes ; les onglets deviennent des medaillons en bas a droite, avec
    leur touche ; la droite de l'ecran est libre pour les panneaux."""
    s = base(rail=False, cards=False)
    items = [("savoir", "T"), ("village", "B"), ("peuples", "P"), ("journal", "J"), ("couronne", "D"), ("combat", "W"), ("commerce", "M"), ("tresor", "G"), ("balance", "N")]
    n = len(items)
    dock_w = n * 64 + 24
    dx, dy = W - dock_w - 12, H - 96
    theme.panel(s, (dx, dy, dock_w, 84), "peau")
    for i, (ic, k) in enumerate(items):
        cx = dx + 16 + i * 64
        state = "actif" if ic == "couronne" else "normal"
        s.blit(theme.medallion(ic, 24, state), (cx, dy + 8))
        key_cap(s, cx + 18, dy + 62, k, C.ocre_jaune if ic == "couronne" else C.cendre)
    # Badges.
    for i, (ic, k) in enumerate(items):
        badge = {"couronne": (str(n_decide), C.bon), "savoir": ("!", C.braise), "peuples": ("2", C.braise)}.get(ic)
        if badge:
            cx = dx + 16 + i * 64 + 46
            pygame.draw.circle(s, badge[1], (cx, dy + 12), 10)
            f = theme.font("mini_gras")
            s.blit(f.render(badge[0], True, C.nuit), (cx - f.size(badge[0])[0] // 2, dy + 12 - f.get_height() // 2))
    # Au survol : le nom de l'onglet.
    tip(s, [("Décisions [D]", "titre"), (f"{n_decide} possibles maintenant", ""), ("La soudure : rationner, acheter du grain...", "alerte")], dx + 4 * 64 - 60, dy - 110, 300)
    # Les evenements en attente : des medaillons qui respirent, au-dessus du bouton Carte.
    ex, ey = 18, H - 130
    for i, (ic, title) in enumerate((("peuples", "Une offre d'alliance"), ("epidemie", "La fièvre au village"), ("gens", "Une famille errante"))):
        theme.glow(s, (ex + i * 58 - 6, ey - 6, 60, 60), C.braise, 0.5)
        s.blit(theme.medallion(ic, 22, "danger" if ic == "epidemie" else "actif"), (ex + i * 58, ey))
    theme.text(s, "3 événements à décider", "mini_gras", C.braise, (ex, ey + 52))
    save(s, "HUD_C_le_dock", "HUD C · Le dock en bas (médaillons et touches ; la droite libre pour les panneaux ; événements en médaillons)")


# --- le panneau Village -------------------------------------------------------------------


def panel_box(s, x=850, w=None, h=None):
    w = w or (W - 90 - x)
    box = (x, HUD_HEIGHT + 16, w, h or (H - HUD_HEIGHT - 30))
    theme.panel(s, box, "peau")
    return box


def goods_grid(s, x, y, w, cols=3):
    cw = (w - (cols - 1) * 8) // cols
    for i, g in enumerate(goods.GOODS):
        have = tribe.goods.get(g, 0.0)
        cx = x + (i % cols) * (cw + 8)
        cy = y + (i // cols) * 34
        theme.panel(s, (cx, cy, cw, 28), "creux" if have <= 0 else "carte")
        pygame.draw.circle(s, goods.GOOD_COLORS[g], (cx + 12, cy + 14), 6)
        theme.text(s, goods.GOOD_NAMES[g], "mini", C.lin if have > 0 else C.cendre, (cx + 24, cy + 6), cw - 60)
        txt = f"{have:.0f}"
        theme.text(s, txt, "mini_gras", C.bon if have > 0 else C.mauvais, (cx + cw - 8 - theme.font("mini_gras").size(txt)[0], cy + 6))
    return y + ((len(goods.GOODS) + cols - 1) // cols) * 34


def vil_a():
    """A : le tableau. Le chef en tete ; chaque village en carte a jauges
    (gens, grenier jusqu'a la recolte, stabilite) ; la reserve en grille."""
    s = base("tribu")
    box = panel_box(s, h=600)
    bx, by, bw, bh = box
    theme.title(s, f"Les Utopie", bx + 20, by + 12, "h1")
    theme.text(s, f"{pop} personnes · 1 village · prestige {tribe.prestige} · 0 sous les armes", "mini", C.cendre, (bx + 22, by + 48))
    # Le chef.
    cy = by + 78
    theme.panel(s, (bx + 16, cy, bw - 32, 76), "carte")
    s.blit(theme.medallion("couronne", 26, "connu"), (bx + 26, cy + 10))
    theme.text(s, f"{chief.name if chief else '?'}, chef du peuple", "h3", C.os, (bx + 90, cy + 10))
    theme.text(s, f"{chief_age} ans · {', '.join(chief_traits) or 'sans trait'} · renommée {chief.renown if chief else 0}", "petit", C.ocre_jaune, (bx + 90, cy + 34))
    theme.text(s, "Héritier : à désigner · sa bande : −15 % de morts de faim", "mini", C.cendre, (bx + 90, cy + 54))
    # Le village.
    vy = cy + 92
    commun.section(s, bx + 18, vy, bw - 36, "VOS VILLAGES")
    vy += 26
    theme.panel(s, (bx + 16, vy, bw - 32, 170), "carte")
    s.blit(theme.medallion("village", 20, "actif"), (bx + 26, vy + 10))
    theme.text(s, f"{site.name} (le chef)", "h3", C.os, (bx + 78, vy + 10))
    theme.text(s, "Gros village · bûcherons 1, pêcheurs 2 · pas de chantier", "mini", C.cendre, (bx + 78, vy + 32))
    theme.button(s, (bx + bw - 210, vy + 10, 80, 26), "Voir", "second", True, False, role="bouton_petit")
    theme.button(s, (bx + bw - 122, vy + 10, 90, 26), "Ouvrir", "principal", True, False, role="bouton_petit")
    gw = (bw - 32 - 70) // 3
    gx = bx + 30
    gauge(s, gx, vy + 62, gw, "Gens", f"{home.population} / 220 logés", home.population / 220, C.os, "croissance ~0 %")
    harvest_mark = min(1.0, to_harvest / 52)
    gauge(s, gx + gw + 20, vy + 62, gw, "Grenier", f"{weeks:.0f} sem.", min(1.0, weeks / 24), C.mauvais if margin < 0 else C.ocre_jaune, f"récolte dans {to_harvest} sem. : il manquera {-margin:.0f}" if margin < 0 else f"récolte dans {to_harvest} sem.", marks=(min(1.0, to_harvest / 24),))
    gauge(s, gx + 2 * (gw + 20), vy + 62, gw, "Stabilité", f"{stab:.0f} florissant", stab / 100, C.bon, "fête, ancêtres, terre +")
    theme.text(s, "La soudure arrive : Décisions [D] (rationner, acheter du grain, une razzia...)", "mini_gras", C.mauvais, (bx + 30, vy + 140), bw - 60)
    # La reserve.
    ry = vy + 186
    commun.section(s, bx + 18, ry, bw - 36, "LA RÉSERVE DU PEUPLE")
    ry = goods_grid(s, bx + 18, ry + 26, bw - 36)
    theme.text(s, "Accords : Lilimae, Tadiil · besoin : 1 charge de chaque bien par semaine (tous vos villages)", "mini", C.cendre, (bx + 20, ry + 8), bw - 40)
    save(s, "VIL_A_le_tableau", "Village A · Le tableau (le chef ; chaque village en jauges ; la réserve en grille)")


def vil_b():
    """B : le portrait du peuple. Deux colonnes : a gauche les gens (le chef,
    l'heritier, les familles qui comptent et leur charge), a droite les
    villages et la reserve ; les chiffres du peuple en tete."""
    s = base("tribu")
    box = panel_box(s, 640, h=500)
    bx, by, bw, bh = box
    theme.title(s, "Le peuple des Utopie", bx + 20, by + 12, "h1")
    # Les chiffres en tete.
    stats = [("gens", "Gens", f"{pop}"), ("village", "Villages", "1"), ("prestige", "Prestige", f"{tribe.prestige}"), ("combat", "Sous les armes", "0"), ("tresor", "Trésor", f"{tribe.money:.0f}")]
    sw = (bw - 40) // len(stats)
    for i, (ic, name, val) in enumerate(stats):
        x = bx + 20 + i * sw
        theme.panel(s, (x, by + 56, sw - 8, 54), "creux")
        s.blit(theme.icon(ic, 22, C.ocre_jaune), (x + 10, by + 70))
        theme.text(s, val, "chiffre", C.os, (x + 40, by + 60))
        theme.text(s, name, "mini", C.cendre, (x + 40, by + 86))
    lx, ly = bx + 20, by + 130
    lw = (bw - 60) // 2
    commun.section(s, lx, ly, lw, "LES GENS QUI COMPTENT")
    yy = ly + 28
    theme.panel(s, (lx, yy, lw, 92), "carte_choisie")
    s.blit(theme.medallion("couronne", 24, "connu"), (lx + 10, yy + 12))
    theme.text(s, chief.name if chief else "?", "h2", C.os, (lx + 72, yy + 8))
    theme.text(s, f"chef du peuple · {chief_age} ans", "petit", C.lin, (lx + 72, yy + 34))
    for i, t in enumerate(chief_traits[:2]):
        chip(s, lx + 72 + i * 100, yy + 60, t, C.ocre_jaune)
    yy += 104
    theme.panel(s, (lx, yy, lw, 52), "carte")
    s.blit(theme.medallion("gens", 16, "eteint"), (lx + 10, yy + 9))
    theme.text(s, "Héritier : personne", "petit_gras", C.cendre, (lx + 56, yy + 6))
    theme.text(s, "Désigner un héritier (une décision, à venir)", "mini", C.cendre, (lx + 56, yy + 28), lw - 70)
    yy += 66
    for f in fams[:4]:
        theme.panel(s, (lx, yy, lw, 60), "carte")
        s.blit(theme.medallion("tribu", 16, "normal"), (lx + 10, yy + 12))
        theme.text(s, f"La famille {f.get('name', '?')}", "petit_gras", C.os, (lx + 56, yy + 6))
        trait = chiefdom.TRAITS.get(f.get("trait"), "")
        charge = chiefdom.CHARGES.get(f.get("charge"), "sans charge")
        theme.text(s, f"{trait} · {charge}", "mini", C.lin, (lx + 56, yy + 28), lw - 70)
        theme.bar(s, (lx + 56, yy + 48, lw - 70, 5), f.get("favour", 50) / 100, C.bon)
        yy += 68
    if not fams:
        theme.text(s, "Les familles viennent avec le premier village.", "mini", C.cendre, (lx, yy))
    rx = lx + lw + 20
    commun.section(s, rx, ly, lw, "LES VILLAGES")
    yy = ly + 28
    theme.panel(s, (rx, yy, lw, 110), "carte")
    theme.text(s, site.name, "h3", C.os, (rx + 12, yy + 8))
    chip(s, rx + lw - 12, yy + 10, "La soudure", C.mauvais, right=True)
    rows = [(f"{home.population} gens", "sur 220 logés"), (f"{weeks:.0f} sem. de vivres", f"récolte dans {to_harvest} sem."), (f"stabilité {stab:.0f}", "florissant")]
    for i, (a, b) in enumerate(rows):
        theme.text(s, a, "petit_gras", C.mauvais if i == 1 and margin < 0 else C.lin, (rx + 12, yy + 36 + i * 22))
        theme.text(s, b, "mini", C.cendre, (rx + 190, yy + 38 + i * 22))
    yy += 124
    commun.section(s, rx, yy, lw, "LA RÉSERVE")
    goods_grid(s, rx, yy + 28, lw, cols=2)
    save(s, "VIL_B_le_portrait", "Village B · Le portrait du peuple (les gens qui comptent à gauche ; villages et réserve à droite)")


# --- l'unite choisie ------------------------------------------------------------------------


def unit_a():
    """A : la fiche a jauges. Le nom, les hommes, la force ; quatre jauges
    (vivres, collecte, attachement, marche) ; les ordres en icones avec leur
    touche ; le detail au survol."""
    raise_troop()
    s = backdrop()
    w, h = 620, 200
    x, y = (W - w) // 2, H - h - 14
    theme.panel(s, (x, y, w, h), "peau")
    s.blit(theme.medallion("armee", 24, "actif"), (x + 14, y + 12))
    theme.text(s, f"Troupe d'{site.name}", "h2", C.os, (x + 76, y + 10))
    theme.text(s, f"{army.population} guerriers · force 53 · chef de guerre Ilmaee (38 ans, fidèle)", "petit", C.lin, (x + 76, y + 36))
    gx, gy = x + 16, y + 70
    gw = (w - 32 - 3 * 14) // 4
    gauge(s, gx, gy, gw, "Vivres", "8 sem.", 8 / 12, C.ocre_jaune)
    gauge(s, gx + (gw + 14), gy, gw, "Collecte", "33 / 18", 1.0, C.bon)
    gauge(s, gx + 2 * (gw + 14), gy, gw, "Attachement", "fidèle", 0.9, C.bon)
    gauge(s, gx + 3 * (gw + 14), gy, gw, "Compagnies", "8 · 4 · 6", 0.6, C.lin)
    acts = [("scinder", "S"), ("pas", "F"), ("voir", "Tab"), ("chef", ""), ("village", "V"), ("camp", "C"), ("deposer", "K"), ("reprendre", ""), ("armee", "H"), ("fermer", "L")]
    ax = x + 16
    for i, (ic, k) in enumerate(acts):
        rect = (ax + i * 59, y + 120, 52, 52)
        on = ic not in ("village", "camp", "deposer", "reprendre", "armee")
        theme.icon_button(s, rect, ic, on, i == 9)
        if k:
            key_cap(s, rect[0] + 2, rect[1] + 36, k, C.cendre)
    theme.text(s, "Clic : aller · clic droit sur un étranger : attaquer · Maj+clic : rejoindre", "mini", C.cendre, (x + 16, y + h - 22))
    tip(s, [("Dissoudre [L]", "titre"), ("Chaque compagnie rentre à pied à son village et y redevient villageoise.", "")], ax + 9 * 59 - 120, y - 70, 300)
    save(s, "UNI_A_la_fiche_a_jauges", "Unité A · La fiche à jauges (quatre jauges, les ordres en icônes avec leur touche)")


def unit_b():
    """B : la fiche laterale. A gauche, une colonne : qui (les compagnies en
    petits soldats), ou (terrain, saison), les vivres, les ordres en liste."""
    raise_troop()
    s = backdrop(cards=False)
    x, y, w = 12, HUD_HEIGHT + 12, 330
    h = H - y - 80
    theme.panel(s, (x, y, w, h), "peau")
    s.blit(theme.medallion("armee", 22, "actif"), (x + 12, y + 12))
    theme.text(s, f"Troupe d'{site.name}", "h2", C.os, (x + 66, y + 12))
    theme.text(s, f"{army.population} guerriers · force 53", "petit", C.lin, (x + 66, y + 38))
    yy = y + 76
    yy = commun.section(s, x + 14, yy, w - 28, "QUI") + 4
    for ic, name, n in (("hache", "Haches polies", 8), ("arc", "Frondeurs", 4), ("palissade", "Porteurs de boucliers", 6)):
        s.blit(theme.icon(ic, 20, C.ocre_jaune), (x + 16, yy))
        theme.text(s, name, "petit", C.lin, (x + 44, yy))
        theme.text(s, str(n), "petit_gras", C.os, (x + w - 30, yy))
        for k in range(n):
            pygame.draw.circle(s, C.ocre, (x + 46 + k * 9, yy + 26), 3)
        yy += 38
    theme.text(s, "Chef de guerre : Ilmaee, 38 ans, fidèle", "mini", C.ocre_jaune, (x + 16, yy))
    yy += 28
    yy = commun.section(s, x + 14, yy, w - 28, "OÙ") + 4
    theme.text(s, "Vallée · printemps · au village d'Ilsen", "petit", C.lin, (x + 16, yy))
    yy += 34
    yy = commun.section(s, x + 14, yy, w - 28, "VIVRES") + 6
    theme.bar(s, (x + 16, yy, w - 32, 8), 8 / 12, C.ocre_jaune)
    theme.text(s, "8 semaines emportées · la collecte nourrit la troupe ici", "mini", C.cendre, (x + 16, yy + 14), w - 32)
    yy += 44
    yy = commun.section(s, x + 14, yy, w - 28, "ORDRES") + 6
    for ic, name, k, on in (("pas", "Rentrer libérer les guerriers", "F", True), ("scinder", "Détacher une compagnie", "S", True), ("armee", "Appeler l'ost", "H", False), ("fermer", "Dissoudre", "L", True)):
        rect = (x + 14, yy, w - 28, 32)
        theme.button(s, rect, "", "second", on, False)
        s.blit(theme.icon(ic, 18, C.lin if on else C.cendre), (x + 24, yy + 7))
        theme.text(s, name, "bouton_petit", C.os if on else C.cendre, (x + 52, yy + 6))
        key_cap(s, x + w - 46, yy + 8, k)
        yy += 38
    save(s, "UNI_B_la_fiche_laterale", "Unité B · La fiche latérale (qui, où, vivres, ordres : une colonne à gauche)")


# --- la carte d'evenement --------------------------------------------------------------------


def effect_chips(s, x, y, summary, maxw):
    parts = [p.strip() for p in summary.split(",") if p.strip()]
    for p in parts:
        bad = p.startswith("-") or p.startswith("−")
        col = C.mauvais if bad else (C.bon if p[:1] in "+" else C.lin)
        w = chip(s, x, y, p, col)
        x += w + 6
    return x


def event_a():
    """A : le recit illustre. A gauche une grande image (la scene, aux
    couleurs de l'humeur), a droite le recit ; les choix en cartes, leurs
    effets en pastilles vertes ou rouges ; le temps qui reste en barre."""
    fire_event()
    s = backdrop()
    commun.veil(s, 150)
    w, h = 900, 400
    x, y = (W - w) // 2, (H - h) // 2
    theme.panel(s, (x, y, w, h), "pierre")
    iw = 300
    scene = pygame.Surface((iw, h - 24))
    for i in range(h - 24):
        t = i / (h - 24)
        scene.fill(theme._mix((86, 58, 34), (24, 18, 14), t), (0, i, iw, 1))
    s.blit(scene, (x + 12, y + 12))
    big = theme.icon("gens", 150, theme._mix(C.ocre_jaune, C.os, 0.3))
    s.blit(big, (x + 12 + (iw - 150) // 2, y + 70))
    pygame.draw.rect(s, C.ocre_sombre, (x + 12, y + 12, iw, h - 24), 2)
    theme.text(s, "LA CHANCE", "etiquette", C.ocre_jaune, (x + 30, y + h - 50))
    tx = x + iw + 36
    tw = w - iw - 60
    theme.title(s, ev.title, tx, y + 22, "h1")
    yy = text_wrap(s, events._fmt(st, inst, ev.text) if hasattr(events, "_fmt") else ev.text, "recit", C.lin, tx, y + 70, tw)
    yy += 14
    for i, o in enumerate(opts):
        rect = (tx, yy, tw, 66)
        theme.panel(s, rect, "carte_survol" if i == 0 else "carte")
        theme.text(s, f"{i + 1}.", "h3", C.ocre_jaune, (tx + 12, yy + 10))
        theme.text(s, o["label"], "texte_gras", C.os, (tx + 40, yy + 8))
        effect_chips(s, tx + 40, yy + 38, o["summary"], tw - 60)
        yy += 76
    theme.text(s, "Sans réponse dans 16 semaines : le premier choix", "mini", C.cendre, (tx, y + h - 40))
    theme.bar(s, (tx, y + h - 20, tw, 5), 1.0, C.ocre)
    theme.button(s, (x + w - 130, y + 18, 110, 26), "Plus tard", "second", True, False, role="bouton_petit")
    save(s, "EVE_A_le_recit_illustre", "Événement A · Le récit illustré (une grande image, les effets en pastilles)")


def event_b():
    """B : la carte a jouer. Une carte haute et etroite, comme une carte de
    jeu : l'image en haut, le recit, les choix empiles ; les autres
    evenements en attente en eventail derriere."""
    fire_event()
    s = backdrop()
    commun.veil(s, 160)
    w, h = 440, 560
    x, y = (W - w) // 2, (H - h) // 2 + 20
    for k, ang in ((2, -8), (1, -4)):
        back = pygame.Surface((w, h), pygame.SRCALPHA)
        theme.panel(back, (0, 0, w, h), "carte")
        rot = pygame.transform.rotate(back, ang)
        s.blit(rot, (x - 40 * k, y - 10 * k))
    theme.panel(s, (x, y, w, h), "pierre")
    ih = 210
    scene = pygame.Surface((w - 24, ih))
    for i in range(ih):
        scene.fill(theme._mix((92, 64, 36), (28, 22, 16), i / ih), (0, i, w - 24, 1))
    s.blit(scene, (x + 12, y + 12))
    s.blit(theme.icon("gens", 130, theme._mix(C.ocre_jaune, C.os, 0.3)), (x + (w - 130) // 2, y + 36))
    theme.title(s, ev.title, x + 24, y + ih + 26, "h1")
    yy = text_wrap(s, events._fmt(st, inst, ev.text), "recit_petit", C.lin, x + 24, y + ih + 66, w - 48)
    yy += 14
    for i, o in enumerate(opts):
        rect = (x + 20, yy, w - 40, 58)
        theme.panel(s, rect, "carte_survol" if i == 0 else "carte")
        theme.text(s, o["label"], "texte_gras", C.os, (x + 34, yy + 6))
        effect_chips(s, x + 34, yy + 32, o["summary"], w - 80)
        yy += 66
    theme.text(s, "1 / 3 · encore 16 semaines", "mini", C.cendre, (x + 24, y + h - 28))
    save(s, "EVE_B_la_carte_a_jouer", "Événement B · La carte à jouer (une carte haute, les autres en éventail derrière)")


def event_c():
    """C : dans le coin. Le jeu ne s'arrete pas : l'evenement s'ouvre en bas a
    gauche, ses choix en boutons ; les autres restent en petites cartes
    au-dessus ; on peut agir sur la carte en meme temps."""
    fire_event()
    s = backdrop(cards=False)
    x, w = 14, 470
    y = H - 372
    for i, title in enumerate(("Une offre d'alliance", "La fièvre au village")):
        ry = y - 104 + i * 50
        theme.panel(s, (x, ry, w, 42), "toast")
        s.blit(theme.medallion("peuples" if i == 0 else "epidemie", 14, "actif"), (x + 8, ry + 5))
        theme.text(s, title, "petit_gras", C.os, (x + 50, ry + 4))
        theme.text(s, "encore 10 sem. · clic pour ouvrir", "mini", C.cendre, (x + 50, ry + 22))
    theme.panel(s, (x, y, w, 270), "peau")
    s.blit(theme.medallion("gens", 22, "actif"), (x + 12, y + 12))
    theme.title(s, ev.title, x + 66, y + 14, "h2")
    theme.text(s, "encore 16 sem.", "mini", C.cendre, (x + w - 110, y + 16))
    yy = text_wrap(s, events._fmt(st, inst, ev.text), "recit_petit", C.lin, x + 18, y + 64, w - 36)
    yy += 10
    for i, o in enumerate(opts):
        rect = (x + 14, yy, w - 28, 54)
        theme.panel(s, rect, "carte_survol" if i == 0 else "carte")
        theme.text(s, o["label"], "petit_gras", C.os, (x + 26, yy + 5))
        effect_chips(s, x + 26, yy + 28, o["summary"], w - 60)
        yy += 60
    theme.text(s, "Le temps continue · Espace : pause", "mini", C.braise, (x + 18, y + 248))
    save(s, "EVE_C_dans_le_coin", "Événement C · Dans le coin (le jeu continue ; les autres en petites cartes au-dessus)")


# --- le journal -------------------------------------------------------------------------------


def journal_a():
    """A : la chronique. Ce qui attend une reponse en tete ; puis les
    nouvelles par saison, avec leur icone et leur couleur ; filtres en
    icones ; chaque ligne : Voir sur la carte."""
    s = base("journal")
    box = panel_box(s, 1060)
    bx, by, bw, bh = box
    theme.title(s, "La chronique", bx + 18, by + 12, "h1")
    fx = bx + 20
    for ic, col in (("journal", C.ocre_jaune), ("combat", C.mauvais), ("survie", C.alerte), ("printemps", C.bon), ("decouverte", C.savoir), ("politique", C.ocre_jaune)):
        theme.icon_button(s, (fx, by + 52, 40, 32), ic, True, False, active=ic == "journal")
        fx += 46
    yy = by + 98
    yy = commun.section(s, bx + 18, yy, bw - 36, "À DÉCIDER", C.braise) + 4
    for title, ic in (("Une offre d'alliance", "peuples"), ("La fièvre au village", "epidemie"), ("Une famille errante", "gens")):
        theme.panel(s, (bx + 16, yy, bw - 32, 36), "carte_survol")
        s.blit(theme.icon(ic, 20, C.braise), (bx + 24, yy + 8))
        theme.text(s, title, "petit_gras", C.os, (bx + 52, yy + 8))
        theme.text(s, "10 sem.", "mini", C.cendre, (bx + bw - 80, yy + 10))
        yy += 40
    yy += 8
    head = None
    for e in log:
        if yy > by + bh - 40:
            break
        season_of = ("PRINTEMPS", "ÉTÉ", "AUTOMNE", "HIVER")[min(3, (e.week - 1) // 13)]
        if (e.year, season_of) != head:
            head = (e.year, season_of)
            yy = commun.section(s, bx + 18, yy + 4, bw - 36, f"{season_of} DE L'AN {e.year}") + 6
        col = KIND_COL.get(e.kind, C.lin)
        pygame.draw.rect(s, col, (bx + 18, yy + 2, 3, 30))
        s.blit(theme.icon(KIND_ICON.get(e.kind, "journal"), 18, col), (bx + 28, yy + 2))
        lines = theme.wrap(theme.font("mini"), e.text, bw - 140)[:2]
        for i, line in enumerate(lines):
            theme.text(s, line, "mini", C.lin, (bx + 54, yy + i * 16))
        theme.text(s, f"sem. {e.week}", "mini", C.cendre, (bx + bw - 66, yy))
        yy += max(20, 16 * len(lines)) + 10
    save(s, "JOU_A_la_chronique", "Journal A · La chronique (à décider en tête, puis les nouvelles par saison)")


def journal_b():
    """B : a faire et nouvelles. Un panneau plus large en deux colonnes : a
    gauche ce qui attend (evenements, decisions possibles, conseils), a
    droite le fil des nouvelles, les importantes en grand."""
    s = base("journal")
    box = panel_box(s, 760)
    bx, by, bw, bh = box
    theme.title(s, "Journal", bx + 18, by + 12, "h1")
    lw = 300
    lx, ly = bx + 18, by + 60
    commun.section(s, lx, ly, lw, "À FAIRE", C.braise)
    yy = ly + 28
    todo = [("evenement", "3 événements à décider", C.braise), ("famine", f"La soudure : il manquera {-margin:.0f} sem." if margin < 0 else "La soudure arrive", C.mauvais), ("savoir", "Choisir un savoir", C.savoir), ("couronne", f"{n_decide} décisions possibles", C.bon), ("tribu", "Un héritier à désigner", C.cendre)]
    for ic, text, col in todo:
        theme.panel(s, (lx, yy, lw, 44), "carte")
        pygame.draw.rect(s, col, (lx, yy + 6, 4, 32))
        s.blit(theme.icon(ic, 22, col), (lx + 12, yy + 11))
        theme.text(s, text, "petit_gras", C.os, (lx + 44, yy + 12), lw - 56)
        yy += 50
    rx = lx + lw + 24
    rw = bx + bw - 18 - rx
    commun.section(s, rx, ly, rw, "NOUVELLES")
    yy = ly + 28
    for i, e in enumerate(log):
        if yy > by + bh - 40:
            break
        col = KIND_COL.get(e.kind, C.lin)
        big = i < 2
        hgt = 62 if big else 40
        theme.panel(s, (rx, yy, rw, hgt), "carte" if big else "creux")
        s.blit(theme.icon(KIND_ICON.get(e.kind, "journal"), 22 if big else 18, col), (rx + 10, yy + 10))
        role = "petit" if big else "mini"
        for k, line in enumerate(theme.wrap(theme.font(role), e.text, rw - 230)[: 2 if big else 1]):
            theme.text(s, line, role, C.os if big else C.lin, (rx + 42, yy + 8 + k * 20))
        theme.text(s, f"an {e.year}, sem. {e.week}", "mini", C.cendre, (rx + rw - 172, yy + 10))
        if e.hex is not None:
            theme.button(s, (rx + rw - 62, yy + (hgt - 22) // 2, 52, 22), "Voir", "second", True, False, role="mini_gras")
        yy += hgt + 6
    save(s, "JOU_B_a_faire_et_nouvelles", "Journal B · À faire et nouvelles (deux colonnes ; les nouvelles importantes en grand)")


for fn in (hud_a, hud_b, hud_c, vil_a, vil_b, journal_a, journal_b, event_a, event_b, event_c, unit_a, unit_b):
    fn()
