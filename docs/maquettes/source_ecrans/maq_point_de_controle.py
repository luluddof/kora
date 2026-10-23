"""Maquette du POINT DE CONTROLE (age du bronze, proposition B3) sur SA
partie (copie) : 1) le mode de placement (les cases de la zone du village
ou on peut l'etablir, en vert ; la zone qu'il aurait, en pointilles) ;
2) le point etabli (un camp d'exploitation : l'argile, le bois et les
chevaux sauvages hors des terres du village) : sa zone reduite, ses terres.
python maq_point_de_controle.py RACINE SAUVEGARDE SORTIE"""
import sys

import maq_commun as commun
from maq_commun import C, H, W, pygame, theme

from src.kora import influence, places
from src.kora.globe import hex_corner_xyz, project_xyz, rotate_xyz, view_params
from src.kora.layout import HUD_HEIGHT
from src.kora.look import country_color
from src.kora.resources import LABELS, NAMES
from src.kora.world import axial_to_offset

st, play, r = commun.load(sys.argv[2], sys.argv[3])
OUT = sys.argv[3]
me = st.viewer
SITE = next(s for s in st.sites.values() if s.kind == "village" and s.tribe_id == me)
WORLD = st.world
POST_RADIUS = 3
LANDS = 2
METALS = ("cuivre", "etain", "argent", "sel", "silex", "argile", "bois", "chevaux", "obsidienne")
FIELD_RADIUS = 3


def hex_poly(h, yaw, pitch, gcx, gcy, focal, dist):
    col, row = axial_to_offset(h)
    pts = []
    for x, y, z in hex_corner_xyz(col, row, WORLD.width, WORLD.height, 1.0):
        p = project_xyz(*rotate_xyz(x, y, z, yaw, pitch), gcx, gcy, focal, dist)
        if p is None:
            return None
        pts.append(p)
    return pts


def allowed_cells():
    radius = places.influence_radius(SITE, influence.VILLAGE_RADIUS)
    cells, _costs = influence.projection(WORLD, SITE.hex, radius)
    out = []
    for h in cells:
        if WORLD.distance(h, SITE.hex) < 2:
            continue
        if not influence.in_zone(WORLD, h, me):
            continue
        other = influence.foreign_zone(WORLD, h, me)
        if other and influence.in_core(WORLD, h, other):
            continue
        out.append(h)
    return out, cells


def gained(h):
    """Les ressources que les terres du point ajoutent (hors des terres du village)."""
    out = {}
    for x in WORLD.hexes_in_radius(h, LANDS):
        if WORLD.distance(x, SITE.hex) <= FIELD_RADIUS:
            continue
        for n in METALS:
            if n in NAMES and WORLD.resource(x, n) > 0.3:
                out[n] = out.get(n, 0) + 1
    return out


def pick_post(allowed):
    best, best_v = None, -1.0
    for h in allowed:
        d = WORLD.distance(h, SITE.hex)
        if d < 3:
            continue
        v = sum(gained(h).values()) + 0.05 * d
        if v > best_v:
            best, best_v = h, v
    return best


def metal_here(h):
    g = gained(h)
    return ", ".join(LABELS.get(n, n).lower() for n, _c in sorted(g.items(), key=lambda kv: -kv[1])[:3])


def view():
    play.globe_yaw, play.globe_pitch = __import__("src.kora.partie_carte", fromlist=["look_hex"]).look_hex(st, SITE.hex)
    play.zoom = max(play.zoom, 5.0)
    r.map_mode = "zones"
    s = commun.backdrop(play, r)
    gcx, gcy, focal, dist = view_params(play.zoom, W, H, HUD_HEIGHT)
    return s, (play.globe_yaw, play.globe_pitch, gcx, gcy, focal, dist)


def fill_cells(s, cells, cam, color, alpha, outline=None):
    layer = pygame.Surface((W, H), pygame.SRCALPHA)
    for h in cells:
        poly = hex_poly(h, *cam)
        if poly is None:
            continue
        pygame.draw.polygon(layer, (*color, alpha), poly)
        if outline is not None:
            pygame.draw.polygon(layer, (*outline, 200), poly, 1)
    s.blit(layer, (0, 0))


def screen_of(h, cam):
    col, row = axial_to_offset(h)
    from src.kora.globe import offset_to_xyz
    x, y, z = offset_to_xyz(col, row, WORLD.width, WORLD.height)
    return project_xyz(*rotate_xyz(x, y, z, cam[0], cam[1]), *cam[2:])


def maquette_placement():
    s, cam = view()
    allowed, _cells = allowed_cells()
    post = pick_post(allowed)
    fill_cells(s, allowed, cam, (120, 220, 90), 105, (190, 255, 150))
    # La case survolee : la zone qu'aurait le point, en pointilles.
    zone, _c = influence.projection(WORLD, post, POST_RADIUS)
    fill_cells(s, zone, cam, C.braise, 45)
    for h in zone:
        poly = hex_poly(h, *cam)
        if poly:
            for i in range(6):
                theme.dotted(s, (int(poly[i][0]), int(poly[i][1])), (int(poly[(i + 1) % 6][0]), int(poly[(i + 1) % 6][1])), C.braise, 5)
    poly = hex_poly(post, *cam)
    if poly:
        pygame.draw.polygon(s, C.braise, poly, 3)
    # Une case refusee, a cote : sa raison au survol.
    # La case refusee : de l'autre cote du village, loin du point.
    far = max((h for h in WORLD.hexes_in_radius(SITE.hex, 8) if WORLD.distance(h, SITE.hex) >= 7 and h not in allowed),
              key=lambda h: (WORLD.distance(h, post), -h.q, -h.r), default=None)
    if far is not None:
        pf = hex_poly(far, *cam)
        if pf:
            pygame.draw.polygon(s, C.mauvais, pf, 3)
            px, py = screen_of(far, cam)
            theme.tooltip(s, [("Hors de la zone de Netali", C.mauvais, "petit_gras"), ("Un point de contrôle s'établit dans la zone du village dont il dépend.", C.lin)], int(px) - 150, int(py) + 26, 300)
    px, py = screen_of(post, cam)
    metal = metal_here(post)
    rows = [("Établir ici", C.os, "petit_gras"), (f"À {WORLD.distance(post, SITE.hex)} cases de Netali, dans sa zone", C.bon)]
    if metal:
        rows.append((f"Ses terres gagnent : {metal}", C.ocre_jaune))
    rows.append((f"Sa zone : {len(zone)} cases (rayon {POST_RADIUS})", C.braise))
    theme.tooltip(s, rows, int(px) - 300, int(py) - 130, 280)
    # Le panneau du choix (a gauche).
    box = (16, HUD_HEIGHT + 14, 360, 430)
    theme.panel(s, box, "peau")
    bx, by, bw, bh = box
    theme.title(s, "Point de contrôle", bx + 18, by + 12, "h1")
    theme.text(s, "Netali · gros village · 1 point sur 1", "mini", C.cendre, (bx + 20, by + 50))
    kinds = (
        ("village", "Hameau", "Des champs de plus pour Netali, des familles logées.", "380 vivres · 8 sem."),
        ("palissade", "Fortin", "Une garnison ; il tient un gué, un col, la frontière.", "520 vivres · 10 sem."),
        ("mine", "Camp d'exploitation", f"Ses terres pour Netali{(' : ' + metal) if metal else ''}.", "450 vivres · 9 sem."),
        ("commerce", "Comptoir", "Un convoi de plus, un péage, des échanges sûrs.", "400 vivres · 8 sem."),
    )
    yy = by + 76
    for i, (icon, name, text, cost) in enumerate(kinds):
        rect = (bx + 14, yy, bw - 28, 74)
        theme.panel(s, rect, "carte_choisie" if icon == "mine" else "carte")
        s.blit(theme.medallion(icon, 18, "actif" if icon == "mine" else "normal"), (bx + 24, yy + 16))
        theme.text(s, name, "petit_gras", C.os, (bx + 70, yy + 6))
        theme.text(s, text, "mini", C.lin, (bx + 70, yy + 28), bw - 100)
        theme.text(s, cost, "mini", C.cendre, (bx + 70, yy + 48))
        yy += 82
    theme.button(s, (bx + 14, by + bh - 44, bw - 28, 32), "Établir le camp", "principal")
    commun.tag(s, "Maquette B3 · Le point de contrôle : le placement (Netali, an 44)")
    commun.save(s, f"{OUT}/point_de_controle_placement.png")
    return post


def maquette_etabli(post):
    s, cam = view()
    zone, _c = influence.projection(WORLD, post, POST_RADIUS)
    village_zone, _c2 = influence.projection(WORLD, SITE.hex, places.influence_radius(SITE, influence.VILLAGE_RADIUS))
    extra = [h for h in zone if h not in set(village_zone) and not influence.in_zone(WORLD, h, me)]
    col = country_color(st, me)
    fill_cells(s, zone, cam, col, 70, theme._mix(col, C.os, 0.4))
    fill_cells(s, extra, cam, C.braise, 60, C.braise)
    lands = [h for h in WORLD.hexes_in_radius(post, LANDS)]
    for h in lands:
        p = screen_of(h, cam)
        if p:
            pygame.draw.circle(s, C.ocre_jaune, (int(p[0]), int(p[1])), 3)
    px, py = screen_of(post, cam)
    theme.glow(s, (int(px) - 26, int(py) - 26, 52, 52), C.braise, 0.8)
    s.blit(theme.medallion("mine", 18, "actif", ring=col), (int(px) - 20, int(py) - 20))
    vx, vy = screen_of(SITE.hex, cam)
    theme.dotted(s, (int(vx), int(vy)), (int(px), int(py)), C.ocre_jaune, 8)
    metal = metal_here(post)
    rows = [
        ("Camp de Netali", C.os, "petit_gras"),
        (f"Niveau 1 · garnison 10 · à {WORLD.distance(post, SITE.hex)} cases du village", C.lin),
        (f"Sa zone : rayon {POST_RADIUS} ({len(zone)} cases, dont {len(extra)} gagnées)", C.braise),
        (f"Ses terres : {LANDS} cases (points jaunes)", C.ocre_jaune),
    ]
    if metal:
        rows.append((f"Exploités par Netali : {metal}", C.bon))
    rows.append(("Si Netali tombe, le camp est perdu ; en guerre, on peut le prendre.", C.cendre))
    theme.tooltip(s, rows, int(px) + 30, int(py) - 40, 340)
    # La legende.
    lx, ly = 16, H - 150
    theme.panel(s, (lx, ly, 330, 110), "infobulle")
    items = ((col, "La zone de Netali (le village)"), (C.braise, "Ce que le point de contrôle ajoute"), (C.ocre_jaune, "Ses terres (champs, gisement)"))
    for i, (c, t) in enumerate(items):
        pygame.draw.rect(s, c, (lx + 14, ly + 16 + i * 28, 18, 14))
        theme.text(s, t, "mini", C.lin, (lx + 42, ly + 14 + i * 28))
    commun.tag(s, "Maquette B3 · Le point de contrôle établi (Netali, an 44)")
    commun.save(s, f"{OUT}/point_de_controle_etabli.png")


post = maquette_placement()
maquette_etabli(post)
