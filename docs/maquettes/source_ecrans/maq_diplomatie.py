"""Trois maquettes de l'ecran diplomatique, sur SA partie (copie) :
  A. Le conseil : la fiche d'aujourd'hui, rangee (liste a etats, trois
     cartes "entre vous / leur force / leurs liens", actions par familles) ;
  B. La toile des peuples : tous les peuples autour de vous, places par
     direction reelle et par relation, leurs liens dessines ;
  C. L'audience : le chef en face de vous, ce que son peuple pense en mots,
     et seulement ce que vous pouvez leur dire.
python maq_diplomatie.py RACINE SAUVEGARDE SORTIE"""
import math
import sys

import maq_commun as commun
from maq_commun import C, H, W, pygame, theme

from src.kora import approach, chiefs, diplo, guerre, money, sites, tech
from src.kora.look import country_color
from src.kora.peoples import color_of, label_of
from src.kora.render_panels import APPROACH_COLORS, known_peoples

st, play, r = commun.load(sys.argv[2], sys.argv[3])
OUT = sys.argv[3]
me = st.viewer
PICK = next(t for t in known_peoples(st) if st.tribes[t].name == "Maelita")

GROUPS = (
    ("Donner", "vivres", ("cadeau", "present")),
    ("Proposer", "politique", ("treve", "commerce", "alliance", "confederer", "union")),
    ("Les soumettre", "couronne", ("tribut", "proteger", "soumission")),
    ("La guerre", "combat", ("guerre", "guerre_pays", "rompre")),
)
TIE = {"commerce": ("commerce", "commercent avec"), "alliance": ("politique", "alliés des"), "guerre": ("combat", "en guerre contre"),
       "vassal": ("couronne", "tributaires des"), "treve": ("politique", "en trêve avec"), "tribut": ("balance", "paient tribut aux"),
       "confederation": ("politique", "confédérés des")}


def ties_of(t):
    """[(genre, autre)] : les pactes de t avec les peuples que vous connaissez."""
    known = set(known_peoples(st)) | {me}
    out = []
    for o in sorted(diplo.contacts_of(st, t)):
        if o not in known or o not in st.tribes:
            continue
        for p in diplo.pacts_between(st, t, o):
            kind = p.kind
            if kind == "vassal":
                kind = "vassal" if p.payer == t else "suzerain"
            out.append((kind, o))
    return out


def tie_lines(t):
    groups = {}
    for kind, o in ties_of(t):
        groups.setdefault(kind, []).append(st.tribes[o].name)
    rows = []
    for kind in ("guerre", "vassal", "suzerain", "alliance", "confederation", "treve", "tribut", "commerce"):
        names = groups.get(kind)
        if not names:
            continue
        if kind == "suzerain":
            rows.append(("couronne", f"suzerains des {', '.join(names)}", C.ocre_jaune))
            continue
        icon, verb = TIE[kind]
        col = C.mauvais if kind == "guerre" else C.ocre_jaune if kind in ("vassal", "tribut") else C.lin
        listed = ", les ".join(names)
        rows.append((icon, f"{verb.capitalize()} les {listed}", col))
    return rows


def verdict(action):
    """(peut, texte, couleur, cadenas)"""
    v = diplo.evaluate(st, me, PICK, action)
    if v.blocked:
        b = v.blocked
        if b.startswith("Il faut connaître "):
            return False, b.replace("Il faut connaître ", ""), C.cendre, True
        return False, b, C.cendre, False
    if action in ("guerre", "guerre_pays", "revolte"):
        return True, "Possible · survolez pour les conséquences", C.alerte, False
    if action in ("rompre", "affranchir"):
        return True, v.reasons[0][0] if v.reasons else "", C.alerte, False
    if v.accepted:
        return True, f"Ils accepteraient ({commun.signed(v.score)})", C.bon, False
    return True, f"Ils refuseraient ({commun.signed(v.score)})", C.mauvais, False


def power_ratio_text(t):
    a, b = diplo.power(st, me), diplo.power(st, t)
    q = a / max(1.0, b)
    if q >= 1.8:
        return f"Vous êtes {q:.1f} fois plus forts".replace(".", ",")
    if q >= 1.15:
        return "Vous êtes plus forts"
    if q > 0.87:
        return "Forces égales"
    if q > 0.55:
        return "Ils sont plus forts"
    return f"Ils sont {1 / q:.1f} fois plus forts".replace(".", ",")


def chief_bits(t):
    lead = chiefs.chief_of(st, t)
    if lead is None:
        return "", "", []
    traits = [chiefs.TRAITS[k].name for k in lead.traits if k in chiefs.TRAITS]
    return lead.name, f"{chiefs.age(st, lead)} ans", traits


def villages_line(t):
    homes = sites.of_tribe(st, t, "village")
    pop = diplo.pop_of(st, t)
    approx = max(10, int(round(pop / 10.0)) * 10)
    names = ", ".join(s.name for s in homes[:3] if s.name)
    return f"{label_of(st.tribes[t]).capitalize()}  ·  ~{approx} personnes  ·  {len(homes)} village{'s' if len(homes) > 1 else ''}" + (f" : {names}" if names else "")


def pacts_with_me(t):
    return [p.kind for p in diplo.pacts_between(st, me, t) if p.kind != guerre.WAR]


# --- A. le conseil --------------------------------------------------------------------------------


def maquette_a():
    s = commun.backdrop(play, r)
    commun.veil(s, 170)
    box = (16, 60, 1508, 828)
    bx, by, bw, bh = box
    theme.panel(s, box, "peau")
    theme.title(s, "Peuples", bx + 26, by + 14, "titre")
    peoples = known_peoples(st)
    levels = {}
    for t in peoples:
        levels.setdefault(diplo.level(st, me, t), []).append(t)
    cx = bx + 210
    cx += theme.chip(s, cx, by + 26, f"Tous  {len(peoples)}", C.braise) + 8
    for lvl in ("Cordiaux", "Méfiants", "Hostiles"):
        n = len(levels.get(lvl, []))
        if n:
            cx += theme.chip(s, cx, by + 26, f"{lvl}  {n}", commun.rel_color({"Cordiaux": 20, "Méfiants": 0, "Hostiles": -50}[lvl])) + 8
    cx += theme.chip(s, cx, by + 26, "En guerre  0", C.mauvais) + 8
    mine = f"Votre force : {diplo.power(st, me):.0f}"
    theme.text(s, mine, "petit_gras", C.lin, (bx + bw - 30 - theme.font("petit_gras").size(mine)[0], by + 26))
    s.blit(theme.icon("armee", 18, C.lin), (bx + bw - 54 - theme.font("petit_gras").size(mine)[0], by + 26))
    # La liste.
    lx, ly, lw = bx + 16, by + 70, 300
    order = sorted(peoples, key=lambda t: -diplo.relation(st, me, t))
    for t in order[:13]:
        T = st.tribes[t]
        row = (lx, ly, lw, 50)
        theme.panel(s, row, "carte_choisie" if t == PICK else "carte")
        pygame.draw.circle(s, country_color(st, t), (lx + 18, ly + 25), 9)
        pygame.draw.circle(s, C.nuit, (lx + 18, ly + 25), 9, 1)
        theme.text(s, T.name, "petit_gras", C.os, (lx + 36, ly + 5))
        rel = diplo.relation(st, me, t)
        val = commun.signed(rel)
        f = theme.font("chiffre")
        s.blit(f.render(val, True, commun.rel_color(rel)), (lx + lw - 12 - f.size(val)[0], ly + 4))
        # La seconde ligne : l'humeur, puis des icones d'etat.
        lvl = diplo.level(st, me, t)
        x2 = lx + 36
        x2 += theme.text(s, lvl, "mini", commun.rel_color(rel), (x2, ly + 27)) + 10
        for icon, text, col in tie_lines(t)[:3]:
            s.blit(theme.icon(icon, 14, col), (x2, ly + 29))
            x2 += 18
        q = diplo.power(st, t) / max(1.0, diplo.power(st, me))
        ftxt = f"force x{q:.1f}".replace(".", ",")
        fm = theme.font("mini")
        s.blit(fm.render(ftxt, True, C.mauvais if q > 1.3 else C.cendre), (lx + lw - 12 - fm.size(ftxt)[0], ly + 28))
        ly += 54
    # La fiche.
    fx, fw = lx + lw + 18, bx + bw - 16 - (lx + lw + 18)
    fy = by + 70
    T = st.tribes[PICK]
    col = color_of(T)
    theme.panel(s, (fx, fy, fw, 100), "carte")
    commun.token(s, T.name, country_color(st, PICK), fx + 50, fy + 50, 34)
    theme.text(s, T.name, "titre", C.os, (fx + 96, fy + 8))
    theme.text(s, villages_line(PICK), "petit", C.lin, (fx + 98, fy + 46))
    way = approach.of(st, PICK)
    label, about = approach.APPROACHES[way]
    ax = fx + 98
    ax += theme.chip(s, ax, fy + 72, label, APPROACH_COLORS.get(way, C.lin)) + 10
    theme.text(s, about, "mini", C.cendre, (ax, fy + 74), fw - (ax - fx) - 330)
    name, age, traits = chief_bits(PICK)
    theme.text(s, f"Chef : {name}, {age}", "petit_gras", C.ocre_jaune, (fx + fw - 310, fy + 46))
    tx = fx + fw - 310
    for tr in traits:
        tx += theme.chip(s, tx, fy + 72, tr, C.ocre_jaune) + 6
    theme.button(s, (fx + fw - 170, fy + 10, 156, 28), "Voir sur la carte", "second", icon_key="voir")
    # Trois cartes.
    cy = fy + 114
    cw3 = (fw - 24) // 3
    rel = diplo.relation(st, me, PICK)
    # 1. entre vous
    x0 = fx
    theme.panel(s, (x0, cy, cw3, 150), "creux")
    commun.section(s, x0 + 14, cy + 10, cw3 - 28, "Entre vous")
    f = theme.font("chiffre_grand")
    s.blit(f.render(commun.signed(rel), True, commun.rel_color(rel)), (x0 + 16, cy + 34))
    theme.text(s, diplo.level(st, me, PICK), "h3", commun.rel_color(rel), (x0 + 70, cy + 38))
    accords = pacts_with_me(PICK)
    theme.text(s, "Accords : " + (", ".join(accords) if accords else "aucun"), "mini", C.cendre, (x0 + cw3 - 150, cy + 42))
    commun.meter(s, x0 + 16, cy + 82, cw3 - 32, rel)
    rx = x0 + 16
    for lab, v in diplo.reasons(st, me, PICK)[:3]:
        rx += commun.pill(s, rx, cy + 104, f"{commun.signed(v)}  {lab}", C.bon if v > 0 else C.mauvais) + 6
    # 2. leur force
    x1 = fx + cw3 + 12
    theme.panel(s, (x1, cy, cw3, 150), "creux")
    commun.section(s, x1 + 14, cy + 10, cw3 - 28, "Leur force")
    a, b = diplo.power(st, me), diplo.power(st, PICK)
    top = max(a, b)
    for i, (who, v, c) in enumerate((("Eux", b, col), ("Vous", a, C.braise))):
        yy = cy + 42 + i * 30
        theme.text(s, who, "petit_gras", C.lin, (x1 + 16, yy - 3))
        theme.bar(s, (x1 + 70, yy, cw3 - 150, 12), v / top, c)
        theme.text(s, f"{v:.0f}", "chiffre", C.os, (x1 + cw3 - 66, yy - 5))
    theme.text(s, power_ratio_text(PICK), "petit", C.bon, (x1 + 16, cy + 104))
    theme.text(s, "Guerriers, villages, palissades : la force qu'ils montrent.", "mini", C.cendre, (x1 + 16, cy + 124), cw3 - 30)
    # 3. leurs liens
    x2 = fx + 2 * (cw3 + 12)
    theme.panel(s, (x2, cy, cw3, 150), "creux")
    commun.section(s, x2 + 14, cy + 10, cw3 - 28, "Leurs liens")
    yy = cy + 38
    for icon, text, c in tie_lines(PICK)[:4]:
        s.blit(theme.icon(icon, 18, c), (x2 + 16, yy))
        for k, part in enumerate(theme.wrap(theme.font("mini"), text, cw3 - 60)[:2]):
            theme.text(s, part, "mini", c, (x2 + 42, yy + 1 + 16 * k))
        yy += 40
    # Les savoirs.
    sy = cy + 162
    mine = st.tribes[me].knowledge
    theirs = sorted((k for k in T.knowledge - mine if k in tech.TECHS), key=lambda k: (tech.TECHS[k].tier, k))
    theme.text(s, f"Ils savent ce que vous ignorez ({len(theirs)}) :", "petit", C.lin, (fx + 4, sy))
    kx = fx + 250
    stop = fx + fw - 230
    for k in theirs:
        lab = tech.TECHS[k].name
        w_ = theme.font("mini_gras").size(lab)[0] + 30
        if kx + w_ > stop:
            theme.text(s, "...", "petit", C.savoir, (kx, sy))
            break
        kx += theme.chip(s, kx, sy + 1, lab, C.savoir, icon_key="savoir") + 6
    theme.text(s, "trop loin pour l'apprendre d'eux", "mini", C.cendre, (fx + fw - 214, sy + 3))
    # Les actions, par familles.
    ay = sy + 34
    gw = (fw - 36) // 4
    for gi, (gname, gicon, acts) in enumerate(GROUPS):
        gx = fx + gi * (gw + 12)
        theme.panel(s, (gx, ay, gw, bh - (ay - by) - 16), "creux")
        s.blit(theme.medallion(gicon, 13, "connu" if gi < 3 else "danger"), (gx + 10, ay + 8))
        theme.text(s, gname, "h2", C.os, (gx + 44, ay + 8))
        yy = ay + 48
        locks = []
        for act in acts:
            if act == "cadeau":
                theme.text(s, "Offrir des vivres", "petit_gras", C.os, (gx + 14, yy))
                sizes = diplo.gift_sizes(st, me, PICK)
                bx2 = gx + 14
                for amount in diplo.GIFT_SIZES:
                    on = amount in sizes
                    theme.button(s, (bx2, yy + 24, 70, 28), str(amount), "second", on=on, icon_key="vivres")
                    if on:
                        gain = diplo.gift_value(st, me, PICK, amount)
                        theme.text(s, f"+{gain:.0f}", "mini_gras", C.bon, (bx2 + 26, yy + 56))
                    bx2 += 78
                if not sizes:
                    why = diplo.evaluate(st, me, PICK, "cadeau").blocked or "Aucune de vos bandes à moins de 30 cases d'eux"
                    theme.text(s, why, "mini", C.alerte, (gx + 16, yy + 58), gw - 30)
                yy += 84
                continue
            if act == "present":
                if not money.has_money(st, me):
                    locks.append(("Offrir des sicles", "L'argent pesé", True))
                    continue
            can, txt, c, is_lock = verdict(act)
            label = diplo.ACTION_LABELS[act]
            if not can:
                locks.append((label, txt, is_lock))
                continue
            rank = "principal" if act == "guerre" and False else "second"
            theme.button(s, (gx + 14, yy, gw - 28, 30), label, rank)
            theme.text(s, txt, "mini", c, (gx + 16, yy + 34), gw - 30)
            yy += 60
        if locks:
            yy = max(yy, ay + 48)
            commun.section(s, gx + 14, yy, gw - 28, "Pas encore", C.cendre)
            yy += 24
            for label, why, is_lock in locks:
                if is_lock:
                    commun.lock(s, gx + 20, yy + 8)
                else:
                    pygame.draw.line(s, C.cendre, (gx + 16, yy + 9), (gx + 24, yy + 9), 2)
                theme.text(s, label, "mini_gras", C.cendre, (gx + 32, yy))
                theme.text(s, why, "mini", (110, 100, 88), (gx + 32, yy + 16), gw - 46)
                yy += 38
    v = guerre.war_verdict(st, me, PICK)
    gx = fx + 3 * (gw + 12)
    rows = [(f"Déclarer la guerre aux {T.name}", C.os, "petit_gras")] + [(f"  {lab}", C.alerte) for lab, _v in v.reasons]
    theme.tooltip(s, rows, gx - 330, ay + 90, 340)
    commun.tag(s, "Maquette A · Le conseil (sa partie, an 44)")
    commun.save(s, f"{OUT}/diplo_A_conseil.png")


# --- B. la toile ----------------------------------------------------------------------------------


def _home(t):
    homes = sites.of_tribe(st, t, "village")
    if homes:
        return homes[0].hex
    b = next((b for b in st.bands.values() if b.tribe_id == t and b.population > 0), None)
    return b.position if b else None


def maquette_b():
    from src.kora.world import axial_to_offset
    s = commun.backdrop(play, r)
    commun.veil(s, 185)
    box = (16, 60, 1508, 828)
    bx, by, bw, bh = box
    theme.panel(s, box, "peau")
    theme.title(s, "La toile des peuples", bx + 26, by + 14, "titre")
    theme.text(s, "Placés selon leur direction depuis chez vous ; plus ils sont proches du centre, meilleure est la relation.", "mini", C.cendre, (bx + 30, by + 58))
    x = bx + 960
    for k, lab in enumerate(("Par relation", "Par distance réelle")):
        x += theme.chip(s, x, by + 24, lab, C.braise if k == 0 else C.cendre) + 8
    cxm, cym = bx + 560, by + 450
    # Les anneaux de l'humeur.
    def rad(rel):
        rel = max(-60, min(60, rel))
        return 120 + (60 - rel) / 120 * 250
    bands = pygame.Surface((W, H), pygame.SRCALPHA)
    for rr, col, a in ((int(rad(-60)) + 30, C.mauvais, 26), (int(rad(-30)), C.lin, 10), (int(rad(10)), C.bon, 22)):
        pygame.draw.circle(bands, (*col, a), (cxm, cym), rr)
    s.blit(bands, (0, 0))
    for rel in (10, -10, -30):
        rr = int(rad(rel))
        n = 160
        for i in range(0, n, 2):
            a0 = 2 * math.pi * i / n
            pygame.draw.circle(s, (92, 72, 54), (int(cxm + rr * math.cos(a0)), int(cym + rr * math.sin(a0))), 1)
    # Les positions : la direction reelle (monde qui boucle en largeur), le rayon par la relation.
    home = _home(me)
    hc, hr = axial_to_offset(home)
    pos = {}
    for t in known_peoples(st):
        h = _home(t)
        if h is None:
            continue
        c, rr_ = axial_to_offset(h)
        dc = (c - hc + st.world.width // 2) % st.world.width - st.world.width // 2
        dr = rr_ - hr
        ang = math.atan2(dr, dc)
        rad_ = rad(diplo.relation(st, me, t))
        pos[t] = [cxm + rad_ * math.cos(ang), cym + rad_ * math.sin(ang), rad_]
    # Les directions, reparties tout autour (dans leur ordre) : ses voisins
    # sont presque tous a l'ouest, la toile pencherait.
    order_ = sorted(pos, key=lambda t: math.atan2(pos[t][1] - cym, pos[t][0] - cxm))
    for i, t in enumerate(order_):
        ang = -math.pi + 2 * math.pi * (i + 0.5) / len(order_)
        pos[t][0] = cxm + pos[t][2] * math.cos(ang)
        pos[t][1] = cym + pos[t][2] * math.sin(ang)
    # Ecarter les medaillons qui se touchent (le long de leur cercle).
    for _ in range(200):
        moved = False
        keys = sorted(pos)
        for i, a in enumerate(keys):
            for b in keys[i + 1:]:
                dx = pos[b][0] - pos[a][0]
                dy = pos[b][1] - pos[a][1]
                d = math.hypot(dx, dy)
                if d < 66:
                    moved = True
                    for k, sgn in ((a, -1), (b, 1)):
                        ang = math.atan2(pos[k][1] - cym, pos[k][0] - cxm) + sgn * 0.035
                        pos[k][0] = cxm + pos[k][2] * math.cos(ang)
                        pos[k][1] = cym + pos[k][2] * math.sin(ang)
        if not moved:
            break
    pos[me] = [cxm, cym, 0]
    # Les liens.
    drawn = set()
    for t in list(pos):
        for kind, o in ties_of(t):
            if o not in pos or (min(t, o), max(t, o), kind) in drawn:
                continue
            drawn.add((min(t, o), max(t, o), kind))
            a, b = pos[t], pos[o]
            hot = PICK in (t, o)
            if kind == "guerre":
                c = C.mauvais
                pygame.draw.line(s, c if hot else theme._mix(C.nuit, c, 0.55), a[:2], b[:2], 3 if hot else 2)
            elif kind == "commerce":
                c = C.ocre_jaune if hot else theme._mix(C.nuit, C.ocre_jaune, 0.45)
                theme.dotted(s, (int(a[0]), int(a[1])), (int(b[0]), int(b[1])), c, 7, 2 if hot else 1)
            elif kind in ("alliance", "confederation"):
                pygame.draw.line(s, C.bon if hot else theme._mix(C.nuit, C.bon, 0.55), a[:2], b[:2], 3)
            elif kind in ("vassal", "suzerain"):
                lord, vas = (o, t) if kind == "vassal" else (t, o)
                p1, p2 = pos[vas], pos[lord]
                c = C.lin
                pygame.draw.line(s, c, p1[:2], p2[:2], 2)
                ang = math.atan2(p2[1] - p1[1], p2[0] - p1[0])
                tip = (p2[0] - 26 * math.cos(ang), p2[1] - 26 * math.sin(ang))
                pygame.draw.polygon(s, c, [tip, (tip[0] - 10 * math.cos(ang - 0.45), tip[1] - 10 * math.sin(ang - 0.45)), (tip[0] - 10 * math.cos(ang + 0.45), tip[1] - 10 * math.sin(ang + 0.45))])
    # Les medaillons.
    for t, (px, py, _rr) in pos.items():
        T = st.tribes[t]
        if t == me:
            commun.token(s, T.name, country_color(st, t), px, py, 32)
            theme.text(s, f"{T.name} (vous)", "petit_gras", C.os, (px - theme.font("petit_gras").size(f"{T.name} (vous)")[0] // 2, py + 36))
            continue
        rad_m = 22 if t == PICK else 18
        commun.token(s, T.name, country_color(st, t), px, py, rad_m, t == PICK)
        rel = diplo.relation(st, me, t)
        f = theme.font("mini_gras")
        nm = T.name
        s.blit(f.render(nm, True, C.os), (px - f.size(nm)[0] // 2, py + rad_m + 2))
        v = commun.signed(rel)
        fm = theme.font("mini")
        s.blit(fm.render(v, True, commun.rel_color(rel)), (px - fm.size(v)[0] // 2, py + rad_m + 18))
        if any(k == "guerre" for k, _o in ties_of(t)):
            s.blit(theme.icon("combat", 14, C.mauvais), (px + rad_m - 4, py - rad_m - 6))
    # La legende.
    lx, ly = bx + 26, by + bh - 162
    theme.panel(s, (lx, ly, 300, 140), "infobulle")
    rows = (("guerre", "En guerre"), ("commerce", "Commercent"), ("alliance", "Alliés, confédérés"), ("vassal", "Tributaire -> suzerain"), ("anneaux", "Anneaux : cordiaux, méfiants, hostiles"))
    for i, (kind, lab) in enumerate(rows):
        yy = ly + 14 + i * 24
        if kind == "guerre":
            pygame.draw.line(s, C.mauvais, (lx + 14, yy + 8), (lx + 54, yy + 8), 3)
        elif kind == "commerce":
            theme.dotted(s, (lx + 14, yy + 8), (lx + 54, yy + 8), C.ocre_jaune, 7, 2)
        elif kind == "alliance":
            pygame.draw.line(s, C.bon, (lx + 14, yy + 8), (lx + 54, yy + 8), 3)
        elif kind == "vassal":
            pygame.draw.line(s, C.lin, (lx + 14, yy + 8), (lx + 54, yy + 8), 2)
            pygame.draw.polygon(s, C.lin, [(lx + 58, yy + 8), (lx + 50, yy + 3), (lx + 50, yy + 13)])
        else:
            for k, col in enumerate((C.bon, C.lin, C.mauvais)):
                pygame.draw.circle(s, theme._mix(C.charbon, col, 0.5), (lx + 20 + 14 * k, yy + 8), 6)
        theme.text(s, lab, "mini", C.lin, (lx + 66, yy))
    # La carte du peuple choisi, a droite.
    cx0, cw = bx + bw - 400, 384
    cy0 = by + 90
    T = st.tribes[PICK]
    theme.panel(s, (cx0, cy0, cw, bh - 106), "carte")
    commun.token(s, T.name, country_color(st, PICK), cx0 + 42, cy0 + 42, 26)
    theme.text(s, T.name, "h1", C.os, (cx0 + 76, cy0 + 12))
    way = approach.of(st, PICK)
    theme.chip(s, cx0 + 78, cy0 + 46, approach.APPROACHES[way][0], APPROACH_COLORS.get(way, C.lin))
    name, age, traits = chief_bits(PICK)
    theme.text(s, f"Chef : {name}, {age} · {', '.join(traits)}", "mini", C.ocre_jaune, (cx0 + 16, cy0 + 80), cw - 30)
    rel = diplo.relation(st, me, PICK)
    yy = cy0 + 108
    theme.text(s, f"Relation {commun.signed(rel)} · {diplo.level(st, me, PICK)}", "h3", commun.rel_color(rel), (cx0 + 16, yy))
    commun.meter(s, cx0 + 18, yy + 34, cw - 36, rel)
    yy += 52
    for lab, v in diplo.reasons(st, me, PICK)[:2]:
        commun.pill(s, cx0 + 16, yy, f"{commun.signed(v)}  {lab}", C.bon if v > 0 else C.mauvais)
        yy += 26
    yy += 6
    a, b = diplo.power(st, me), diplo.power(st, PICK)
    theme.text(s, f"Force : eux {b:.0f} · vous {a:.0f}", "petit", C.lin, (cx0 + 16, yy))
    theme.text(s, power_ratio_text(PICK), "mini", C.bon, (cx0 + 16, yy + 20))
    yy += 48
    commun.section(s, cx0 + 16, yy, cw - 32, "Leurs liens")
    yy += 24
    for icon, text, c in tie_lines(PICK):
        s.blit(theme.icon(icon, 16, c), (cx0 + 16, yy))
        for k, part in enumerate(theme.wrap(theme.font("mini"), text, cw - 60)[:2]):
            theme.text(s, part, "mini", c, (cx0 + 40, yy + 16 * k))
        yy += 38
    commun.section(s, cx0 + 16, yy, cw - 32, "Ce que vous pouvez faire")
    yy += 26
    for act in ("cadeau", "tribut", "guerre"):
        if act == "cadeau":
            theme.button(s, (cx0 + 16, yy, cw - 32, 30), "Offrir 150 vivres", "second", icon_key="vivres")
            gain = diplo.gift_value(st, me, PICK, 150)
            theme.text(s, f"Relation +{gain:.0f} · toujours accepté", "mini", C.bon, (cx0 + 18, yy + 33))
        else:
            can, txt, c, _l = verdict(act)
            theme.button(s, (cx0 + 16, yy, cw - 32, 30), diplo.ACTION_LABELS[act], "second", icon_key="combat" if act == "guerre" else "couronne")
            theme.text(s, txt, "mini", c, (cx0 + 18, yy + 33), cw - 36)
        yy += 58
    theme.button(s, (cx0 + 16, cy0 + bh - 106 - 44, cw - 32, 30), "Toute la fiche", "discret")
    commun.tag(s, "Maquette B · La toile des peuples (sa partie, an 44)")
    commun.save(s, f"{OUT}/diplo_B_toile.png")


# --- C. l'audience -------------------------------------------------------------------------------


def speech(t):
    T = st.tribes[t]
    lvl = diplo.level(st, me, t)
    opening = {
        "Cordiaux": f"Les {T.name} accueillent vos envoyés près du feu, et l'on vous sert à manger.",
        "Méfiants": f"Les {T.name} vous regardent avec méfiance ; on écoute vos envoyés sans les faire asseoir.",
        "Hostiles": f"Les {T.name} vous tiennent pour des ennemis : vos envoyés restent à la lisière du camp.",
    }.get(lvl, f"Les {T.name} vous reçoivent.")
    parts = [opening]
    rs = diplo.reasons(st, me, t)
    if rs:
        lab, v = max(rs, key=lambda x: abs(x[1]))
        parts.append(f"Ce qu'ils retiennent de vous : {lab[0].lower() + lab[1:]}" + (" ; cela compte." if v > 0 else " ; ils ne l'oublient pas."))
    a, b = diplo.power(st, me), diplo.power(st, t)
    if a >= 1.8 * b:
        parts.append("Vos guerriers sont deux fois plus nombreux que les leurs, et ils le savent.")
    elif b >= 1.8 * a:
        parts.append("Leurs guerriers sont deux fois plus nombreux que les vôtres.")
    ties = ties_of(t)
    war = [st.tribes[o].name for k, o in ties if k == "guerre"]
    trade = [st.tribes[o].name for k, o in ties if k == "commerce"]

    def names(xs):
        xs = [f"les {x}" for x in xs]
        return xs[0] if len(xs) == 1 else ", ".join(xs[:-1]) + " et " + xs[-1]
    if war and trade:
        parts.append(f"Ils sont en guerre contre {names(war)}, et commercent avec {names(trade)}.")
    elif war:
        parts.append(f"Ils sont en guerre contre {names(war)}.")
    elif trade:
        parts.append(f"Ils commercent avec {names(trade)}.")
    name, age, traits = chief_bits(t)
    way = approach.of(st, t)
    if name:
        parts.append(f"Leur chef, {name}, est un {approach.APPROACHES[way][0].lower()} : {approach.APPROACHES[way][1][0].lower() + approach.APPROACHES[way][1][1:]}")
    return " ".join(parts)


def maquette_c():
    s = commun.backdrop(play, r)
    commun.veil(s, 200)
    # La rangee des peuples, en haut.
    peoples = sorted(known_peoples(st), key=lambda t: -diplo.relation(st, me, t))
    n = len(peoples)
    step = 74
    x0 = (W - 80 - step * n) // 2 + 20
    y0 = 66
    theme.button(s, (x0 - 44, y0 + 10, 30, 30), "‹", "second")
    for i, t in enumerate(peoples):
        px = x0 + i * step + step // 2
        rad_m = 22 if t == PICK else 17
        commun.token(s, st.tribes[t].name, country_color(st, t), px, y0 + 26, rad_m, t == PICK)
        f = theme.font("mini_gras" if t == PICK else "mini")
        nm = st.tribes[t].name
        s.blit(f.render(nm, True, C.os if t == PICK else C.lin), (px - f.size(nm)[0] // 2, y0 + 52))
        rel = diplo.relation(st, me, t)
        v = commun.signed(rel)
        s.blit(theme.font("mini").render(v, True, commun.rel_color(rel)), (px - theme.font("mini").size(v)[0] // 2, y0 + 68))
    theme.button(s, (x0 + n * step + 14, y0 + 10, 30, 30), "›", "second")
    # La dalle.
    box = (150, 166, 1230, 716)
    bx, by, bw, bh = box
    theme.glow(s, box, C.braise, 0.25)
    theme.panel(s, box, "pierre")
    T = st.tribes[PICK]
    col = color_of(T)
    name, age, traits = chief_bits(PICK)
    s.blit(theme.medallion("chef", 70, "normal", ring=col), (bx + 50, by + 40))
    theme.text(s, name, "h1", C.os, (bx + 122 - theme.font("h1").size(name)[0] // 2, by + 196))
    sub = f"chef des {T.name} · {age}"
    theme.text(s, sub, "petit", C.lin, (bx + 122 - theme.font("petit").size(sub)[0] // 2, by + 230))
    ty = by + 258
    for tr in traits:
        w_ = theme.font("mini_gras").size(tr)[0] + 14
        theme.chip(s, bx + 122 - w_ // 2, ty, tr, C.ocre_jaune)
        ty += 26
    way = approach.of(st, PICK)
    lab = approach.APPROACHES[way][0]
    w_ = theme.font("mini_gras").size(lab)[0] + 14
    theme.chip(s, bx + 122 - w_ // 2, ty + 4, lab, APPROACH_COLORS.get(way, C.lin))
    # Le recit.
    rx, rw = bx + 250, bw - 290
    theme.title(s, f"Chez les {T.name}", rx, by + 30, "h1")
    yy = by + 78
    for part in theme.wrap(theme.font("recit"), speech(PICK), rw):
        theme.text(s, part, "recit", C.os, (rx, yy))
        yy += 26
    # Entre vous.
    yy += 12
    rel = diplo.relation(st, me, PICK)
    theme.text(s, f"Entre vous : {commun.signed(rel)} · {diplo.level(st, me, PICK)}", "h3", commun.rel_color(rel), (rx, yy))
    commun.meter(s, rx + 260, yy + 8, 300, rel)
    px_ = rx + 590
    for labr, v in diplo.reasons(st, me, PICK)[:2]:
        px_ += commun.pill(s, px_, yy + 2, f"{commun.signed(v)}  {labr}", C.bon if v > 0 else C.mauvais) + 6
    yy += 44
    commun.section(s, rx, yy, rw, "Que leur dire ?")
    yy += 30
    options = []
    gain = diplo.gift_value(st, me, PICK, 150)
    options.append(("Leur offrir 150 vivres", f"Relation +{gain:.0f} · toujours accepté", C.bon, "vivres"))
    for act in ("tribut", "guerre", "treve", "commerce", "alliance", "proteger", "soumission", "confederer", "union", "rompre"):
        can, txt, c, _l = verdict(act)
        if can:
            label = {"tribut": "Exiger un tribut", "guerre": "Leur déclarer la guerre"}.get(act, diplo.ACTION_LABELS[act])
            options.append((label, txt, c, "couronne" if act == "tribut" else "combat" if act == "guerre" else "politique"))
    for i, (label, txt, c, icon) in enumerate(options):
        rect = (rx, yy, rw, 58)
        theme.panel(s, rect, "carte_survol" if i == 0 else "carte")
        if i == 0:
            theme.glow(s, rect, C.braise, 0.5)
        theme.text(s, f"{i + 1}.", "h2", C.ocre, (rx + 14, yy + 14))
        s.blit(theme.icon(icon, 22, C.lin), (rx + 46, yy + 17))
        theme.text(s, label, "texte_gras", C.os, (rx + 80, yy + 7))
        theme.text(s, txt, "petit", c, (rx + 80, yy + 31), rw - 100)
        yy += 66
    yy += 4
    locked = []
    for act in ("treve", "commerce", "alliance", "proteger", "confederer", "union", "present"):
        if act == "present":
            if not money.has_money(st, me):
                locked.append("des sicles (L'argent pesé)")
            continue
        can, txt, c, is_lock = verdict(act)
        if not can and is_lock:
            locked.append(f"{diplo.ACTION_LABELS[act].lower()} ({txt})")
    if locked:
        line = "D'autres paroles viendront avec vos savoirs : " + " · ".join(locked)
        for part in theme.wrap(theme.font("mini"), line, rw)[:3]:
            theme.text(s, part, "mini", C.cendre, (rx, yy))
            yy += 17
    band_y = by + bh - 170
    theme.dotted(s, (bx + 30, band_y - 14), (bx + bw - 30, band_y - 14), C.ocre_sombre, 6)
    cw3 = (bw - 80) // 3
    x0 = bx + 30
    commun.section(s, x0, band_y, cw3 - 20, "Leur force")
    a, b = diplo.power(st, me), diplo.power(st, PICK)
    for i, (who, v, c) in enumerate((("Eux", b, color_of(T)), ("Vous", a, C.braise))):
        yy2 = band_y + 32 + i * 28
        theme.text(s, who, "petit_gras", C.lin, (x0, yy2 - 4))
        theme.bar(s, (x0 + 52, yy2, cw3 - 130, 12), v / max(a, b), c)
        theme.text(s, f"{v:.0f}", "chiffre", C.os, (x0 + cw3 - 70, yy2 - 6))
    theme.text(s, power_ratio_text(PICK), "mini", C.bon, (x0, band_y + 88))
    x1 = x0 + cw3 + 10
    commun.section(s, x1, band_y, cw3 - 20, "Leurs liens")
    yy2 = band_y + 28
    for icon, text, c in tie_lines(PICK)[:3]:
        s.blit(theme.icon(icon, 16, c), (x1, yy2))
        for k, part in enumerate(theme.wrap(theme.font("mini"), text, cw3 - 50)[:2]):
            theme.text(s, part, "mini", c, (x1 + 24, yy2 + 16 * k))
        yy2 += 38
    x2 = x1 + cw3 + 10
    commun.section(s, x2, band_y, cw3 - 20, "Ils savent ce que vous ignorez")
    mine = st.tribes[me].knowledge
    theirs = sorted((k for k in T.knowledge - mine if k in tech.TECHS), key=lambda k: (tech.TECHS[k].tier, k))
    kx, ky = x2, band_y + 28
    for k in theirs:
        lab = tech.TECHS[k].name
        w_ = theme.font("mini_gras").size(lab)[0] + 30
        if kx + w_ > x2 + cw3 - 20:
            kx, ky = x2, ky + 26
            if ky > band_y + 84:
                break
        kx += theme.chip(s, kx, ky, lab, C.savoir, icon_key="savoir") + 6
    theme.button(s, (bx + bw - 190, by + bh - 50, 170, 32), "Plus tard  [Échap]", "discret")
    commun.tag(s, "Maquette C · L'audience (sa partie, an 44)")
    commun.save(s, f"{OUT}/diplo_C_audience.png")


maquette_a()
maquette_b()
maquette_c()
