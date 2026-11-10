"""Maquettes de l'onglet DECISIONS (a la Crusader Kings 3, Europa Universalis
5, Victoria 3) sur SA partie (copie) : des decisions qu'on prend QUAND on
veut, des que leurs conditions sont remplies (certaines remplacent des
evenements qui tombaient au hasard).
  A  Le registre : la liste par familles a gauche, la fiche a droite (ce
     qu'il faut, ce que ca coute, ce que ca fait, le bouton).
  B  Les cartes : toutes les decisions en cartes, ce qui manque en pastilles,
     la fiche au survol.
Les conditions sont lues dans sa partie (saison, grenier, prestige, peuples
cordiaux, tributaires, savoirs).
python maq_decisions.py RACINE SAUVEGARDE SORTIE"""
import sys

import maq_commun as commun
from maq_commun import C, H, W, pygame, theme

from src.kora import chiefdom, diplo
from src.kora.layout import HUD_HEIGHT

st, play, r = commun.load(sys.argv[2], sys.argv[3])
OUT = sys.argv[3]
me = st.viewer
tribe = st.tribes[me]
band = max((b for b in st.bands.values() if b.tribe_id == me), key=lambda b: b.population)
village = next((s.name for s in st.sites.values() if s.kind == "village" and s.tribe_id == me), "le village")
season = st.clock.season().name
grain = band.stock / max(1, band.population)
before_harvest = max(0, 33 - st.clock.week)
friends = diplo.friend_count(st, me)
contacts = diplo.contact_count(st, me)
vassals = len(chiefdom.vassals_of(st, me))
clans = sum(1 for b in st.bands.values() if b.tribe_id == me)
knows = tribe.knowledge
spring = season in ("PRINTEMPS", "ETE")

# (famille, icone, nom, texte, [(condition, remplie)], cout, [effets], etat)
# etat : "" (selon les conditions), ou "repos:N" (deja prise, attendre N ans).
DECISIONS = [
    ("Les vivres", "grenier", "Rationner jusqu'à la récolte",
     "Le grenier ne tiendra pas jusqu'à la moisson. Chacun mangera moins, mais tout le monde verra l'été.",
     [("Avant la récolte (printemps, été)", spring),
      (f"Le grenier ne tient pas jusqu'à la récolte ({grain:.0f} sem. pour {before_harvest})", grain < before_harvest),
      ("Pas déjà rationné cette année", True)],
     "Naissances −50 % et stabilité −2, jusqu'à la récolte",
     ["Le grenier dure un tiers de plus", "La famine tue deux fois moins"], ""),
    ("Les vivres", "ble", "La grande fête des moissons",
     "Le grain est rentré : tout le pays mange, danse, et se souvient de qui l'a nourri.",
     [("La récolte est rentrée (automne)", season == "AUTOMNE"),
      (f"Au moins 30 semaines au grenier ({grain:.0f})", grain >= 30)],
     "4 semaines de vivres",
     ["Prestige +8", "Attachement des clans +5", "Naissances +10 % pendant un an"], ""),
    ("Les vivres", "chasse", "Organiser une grande chasse",
     "Tous les chasseurs ensemble, une semaine durant : la viande de toute une saison, si les bêtes sont là.",
     [("Du gibier à moins de 6 cases", True), (f"40 chasseurs ({band.population // 4} hommes valides)", band.population // 4 >= 40)],
     "Les champs perdent une semaine de travail",
     ["Vivres : 3 à 8 semaines", "Quelques blessés"], ""),
    ("Le peuple et ses chefs", "couronne", "Désigner un héritier",
     "Que chacun sache, avant qu'il soit trop tard, qui mènera le peuple.",
     [("Un chef", True), ("Un candidat de renommée 10 dans un clan", clans > 1)],
     "Le clan écarté gronde (attachement −5)",
     ["La succession se fait sans querelle"], ""),
    ("Le peuple et ses chefs", "reunir", "Réunir le conseil des clans",
     "Les chefs de clan viennent au village du chef ; on parle, on promet, on échange des présents.",
     [(f"Au moins 2 clans ({clans})", clans >= 2)],
     "2 semaines de vivres par clan",
     ["Attachement des clans +10", "Un clan rival s'apaise"], ""),
    ("Le peuple et ses chefs", "boussole", "Envoyer des éclaireurs",
     "Dix jeunes partent vers l'horizon ; ils reviendront avec des nouvelles, ou ne reviendront pas.",
     [(f"10 jeunes ({band.population} habitants)", band.population >= 60), ("Pas d'éclaireurs déjà partis", True)],
     "10 personnes absentes 8 semaines",
     ["La carte se découvre loin", "Une chance de rencontrer un peuple"], ""),
    ("Le sacré", "dolmen", "La fête des morts",
     "On ouvre la tombe des ancêtres, on leur parle, on leur donne à manger : ils veillent sur nous.",
     [("Culte des ancêtres", "ancetres" in knows), ("Rites des morts", "rites" in knows)],
     "1 semaine de vivres",
     ["Stabilité +4 pendant deux ans", "Prestige +3"], ""),
    ("Le sacré", "honorer", "Recueillir les récits des anciens",
     "Les plus vieux racontent ; les enfants retiennent. Un peuple qui se souvient apprend plus vite.",
     [("Un ancien de plus de 60 ans", True)],
     "—", ["Recherche +10 % pendant un an"], "repos:3"),
    ("Les voisins", "gens", "Proposer un mariage",
     "Une fille ou un fils du chef pour un peuple ami : deux familles, puis deux peuples, liés.",
     [("Mariages entre clans", "mariages" in knows), (f"Un peuple cordial ({friends})", friends > 0), ("Pas de mariage depuis 5 ans", True)],
     "Une dot : 2 semaines de vivres",
     ["Relation +20 avec ce peuple", "L'alliance lui plaira plus"], ""),
    ("Les voisins", "commerce", "Envoyer un présent au loin",
     "Des perles, du sel, de l'ambre portés par des messagers, chez un peuple qu'on connaît à peine.",
     [(f"Un peuple connu au-delà des voisins ({contacts} connus)", contacts >= 4)],
     "30 sicles ou 3 semaines de vivres",
     ["Relation +10", "Leurs savoirs s'apprennent un peu plus vite"], ""),
    ("Les grands desseins", "couronne", "Devenir le chef des chefs",
     "Les chefs de trois villages au moins ploient le genou : le chef devient le premier d'entre eux.",
     [("Chef des chefs (savoir)", "grand_chef" in knows), (f"3 tributaires ({vassals})", vassals >= 3), (f"Prestige 80 ({tribe.prestige})", tribe.prestige >= 80)],
     "Prestige −20 (une grande fête)",
     ["Un titre pour toujours", "Un tributaire de plus possible", "L'IA des voisins le craint"], ""),
]


def state_of(d):
    if d[7].startswith("repos"):
        return "repos", f"En repos : {d[7].split(':')[1]} ans"
    missing = sum(1 for _c, ok in d[4] if not ok)
    if missing == 0:
        return "possible", "Possible"
    return "manque", f"Il manque {missing}"


COLORS = {"possible": C.bon, "manque": C.cendre, "repos": C.ocre}


def mark(surf, x, y, ok):
    if ok:
        pygame.draw.lines(surf, C.bon, False, [(x - 5, y), (x - 1, y + 4), (x + 6, y - 4)], 2)
    else:
        pygame.draw.line(surf, C.mauvais, (x - 4, y - 4), (x + 4, y + 4), 2)
        pygame.draw.line(surf, C.mauvais, (x + 4, y - 4), (x - 4, y + 4), 2)


def frame():
    s = commun.backdrop(play, r).copy()
    commun.veil(s, 170)
    box = (24, HUD_HEIGHT + 12, W - 110, H - HUD_HEIGHT - 28)
    theme.panel(s, box, "peau")
    bx, by, bw, bh = box
    theme.title(s, "Décisions", bx + 22, by + 12, "h1")
    theme.text(s, f"{tribe.name} · {village} · an {st.clock.year}, {season.lower()} · prestige {tribe.prestige}", "mini", C.cendre, (bx + 24, by + 52))
    counts = {"possible": 0, "manque": 0, "repos": 0}
    for d in DECISIONS:
        counts[state_of(d)[0]] += 1
    chips = [(f"Toutes ({len(DECISIONS)})", True), (f"Possibles ({counts['possible']})", False), (f"Il manque peu ({counts['manque']})", False), (f"En repos ({counts['repos']})", False)]
    x = bx + 380
    for label, on in chips:
        w = theme.font("mini_gras").size(label)[0] + 26
        theme.button(s, (x, by + 18, w, 28), label, "principal" if on else "second", role="mini_gras")
        x += w + 8
    return s, box


def detail(s, d, rect):
    x, y, w, h = rect
    theme.panel(s, rect, "carte")
    s.blit(theme.medallion(d[1], 26, "actif" if state_of(d)[0] == "possible" else "normal"), (x + 18, y + 16))
    theme.title(s, d[2], x + 84, y + 18, "h2")
    st_key, st_txt = state_of(d)
    commun.pill(s, x + 86, y + 54, st_txt, COLORS[st_key])
    theme.text(s, d[3], "petit", C.lin, (x + 22, y + 92), w - 44)
    yy = y + 160
    theme.text(s, "CE QU'IL FAUT", "mini_gras", C.ocre, (x + 22, yy))
    yy += 24
    for cond, ok in d[4]:
        mark(s, x + 32, yy + 9, ok)
        theme.text(s, cond, "petit", C.lin if ok else C.cendre, (x + 48, yy))
        yy += 26
    yy += 10
    theme.text(s, "CE QUE ÇA COÛTE", "mini_gras", C.ocre, (x + 22, yy))
    theme.text(s, d[5], "petit", C.lin, (x + 22, yy + 22), w - 44)
    yy += 62
    theme.text(s, "CE QUE ÇA FAIT", "mini_gras", C.ocre, (x + 22, yy))
    yy += 24
    for e in d[6]:
        theme.text(s, "› " + e, "petit", C.bon, (x + 30, yy))
        yy += 24
    yy += 8
    theme.text(s, "Les autres peuples prennent aussi cette décision quand elle leur va.", "mini", C.cendre, (x + 22, yy), w - 44)
    on = st_key == "possible"
    theme.button(s, (x + w - 230, y + h - 54, 208, 36), "Décider" if on else st_txt, "principal" if on else "second", on=on)


def registre():
    s, (bx, by, bw, bh) = frame()
    list_rect = (bx + 18, by + 78, 520, bh - 96)
    theme.panel(s, list_rect, "infobulle")
    lx, ly, lw, lh = list_rect
    yy = ly + 12
    chosen = DECISIONS[0]
    family = None
    for d in DECISIONS:
        if d[0] != family:
            family = d[0]
            theme.text(s, family.upper(), "mini_gras", C.ocre, (lx + 16, yy))
            yy += 24
        row = (lx + 8, yy, lw - 16, 44)
        if d is chosen:
            theme.panel(s, row, "carte_choisie")
        st_key, st_txt = state_of(d)
        s.blit(theme.medallion(d[1], 15, "actif" if st_key == "possible" else "eteint"), (lx + 16, yy + 6))
        theme.text(s, d[2], "petit_gras", C.os if st_key == "possible" else C.lin, (lx + 58, yy + 4))
        theme.text(s, ", ".join(c for c, ok in d[4] if not ok)[:58] or d[6][0], "mini", C.cendre, (lx + 58, yy + 24))
        commun.pill(s, lx + lw - 16, yy + 12, st_txt, COLORS[st_key], right=True)
        yy += 48
    detail(s, chosen, (lx + lw + 18, ly, bw - lw - 54, lh))
    commun.tag(s, "Maquette A · Décisions : le registre (sa partie, an %d)" % st.clock.year)
    commun.save(s, f"{OUT}/decisions_A_registre.png")


def cartes():
    s, (bx, by, bw, bh) = frame()
    cols, cw, ch, gap = 4, (bw - 36 - 3 * 14) // 4, 178, 14
    x0, y0 = bx + 18, by + 80
    hover = None
    for i, d in enumerate(DECISIONS):
        cx, cy = x0 + (i % cols) * (cw + gap), y0 + (i // cols) * (ch + gap)
        st_key, st_txt = state_of(d)
        theme.panel(s, (cx, cy, cw, ch), "carte_choisie" if st_key == "possible" else "carte")
        s.blit(theme.medallion(d[1], 20, "actif" if st_key == "possible" else "eteint"), (cx + 14, cy + 14))
        theme.text(s, d[2], "petit_gras", C.os, (cx + 66, cy + 14), cw - 80)
        theme.text(s, d[0], "mini", C.cendre, (cx + 66, cy + 54))
        theme.text(s, d[6][0], "mini", C.bon, (cx + 14, cy + 82), cw - 28)
        dots_x = cx + 14
        for _c, ok in d[4]:
            pygame.draw.circle(s, C.bon if ok else C.mauvais, (dots_x + 6, cy + ch - 26), 6)
            dots_x += 18
        commun.pill(s, cx + cw - 12, cy + ch - 36, st_txt, COLORS[st_key], right=True)
        if d[2] == "Proposer un mariage":
            hover = (cx, cy, d)
    if hover:
        cx, cy, d = hover
        rows = [(d[2], C.os, "petit_gras"), (d[3], C.lin)]
        rows += [(("✓ " if ok else "✗ ") + c, C.bon if ok else C.mauvais) for c, ok in d[4]]
        rows = [(t.replace("✓ ", "› ").replace("✗ ", "× "), col, *rest) for t, col, *rest in rows]
        rows += [("Coût : " + d[5], C.ocre)] + [("› " + e, C.bon) for e in d[6]] + [("Clic : décider", C.braise)]
        theme.tooltip(s, rows, cx + cw // 2, cy + 40, 420)
    commun.tag(s, "Maquette B · Décisions : les cartes, la fiche au survol (sa partie, an %d)" % st.clock.year)
    commun.save(s, f"{OUT}/decisions_B_cartes.png")


registre()
cartes()
