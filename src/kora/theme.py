"""La charte graphique « Feu et ocre » (docs/charte-graphique.txt), en code.

Tous les ecrans dessinent avec ces outils : couleurs (C), polices
embarquees (font), icones teintees (icon, medallion), fenetres en pierre
taillee (panel), boutons a trois rangs (button), barres (bar), pointilles
(dotted), titres soulignes au charbon (title), infobulles (tooltip).
Les surfaces sont gardees en cache (le jeu redessine 60 fois par seconde).
"""

from __future__ import annotations

import math
import random
import sys
from pathlib import Path

import pygame
from src.kora import theme


class C:
    """Les couleurs de la charte (section 2)."""

    nuit = (14, 11, 9)
    charbon = (23, 18, 14)
    cuir = (36, 27, 21)
    cuir_clair = (51, 39, 30)
    bois = (74, 55, 39)
    bois_clair = (104, 79, 56)
    pierre = (52, 46, 41)
    pierre_clair = (78, 70, 62)
    os = (239, 228, 204)
    lin = (205, 187, 156)
    cendre = (142, 129, 114)
    ocre = (200, 102, 47)
    ocre_sombre = (128, 62, 28)
    braise = (242, 160, 61)
    ocre_jaune = (217, 164, 65)
    terre_cuite = (185, 88, 58)
    bon = (157, 191, 110)
    mauvais = (217, 87, 63)
    alerte = (232, 150, 58)
    savoir = (95, 176, 166)
    froid = (143, 180, 214)


# --- les lettres ------------------------------------------------------------------

FONT_FILES = {
    "sc": "AlegreyaSC-Regular.ttf",
    "sc-medium": "AlegreyaSC-Medium.ttf",
    "sc-bold": "AlegreyaSC-Bold.ttf",
    "sc-black": "AlegreyaSC-ExtraBold.ttf",
    "sans": "AlegreyaSans-Regular.ttf",
    "sans-medium": "AlegreyaSans-Medium.ttf",
    "sans-bold": "AlegreyaSans-Bold.ttf",
    "sans-black": "AlegreyaSans-ExtraBold.ttf",
    "sans-italic": "AlegreyaSans-Italic.ttf",
    "sans-medium-italic": "AlegreyaSans-MediumItalic.ttf",
}
# role -> (police, taille) : l'echelle de la charte (section 3).
ROLES = {
    "logo": ("sc-black", 96),
    "titre": ("sc-bold", 32),
    "h1": ("sc-bold", 26),
    "h2": ("sc-medium", 21),
    "h3": ("sans-bold", 18),
    "texte": ("sans", 18),
    "texte_gras": ("sans-bold", 18),
    "petit": ("sans", 16),
    "petit_gras": ("sans-bold", 16),
    "mini": ("sans", 14),
    "mini_gras": ("sans-bold", 14),
    "recit": ("sans-italic", 18),
    "recit_petit": ("sans-italic", 15),
    "bouton": ("sans-medium", 16),
    "bouton_petit": ("sans-medium", 15),
    "chiffre": ("sans-bold", 19),
    "chiffre_grand": ("sans-black", 26),
    "etiquette": ("sc-medium", 14),
}
_FONTS: dict = {}


def data_dir() -> Path:
    """data/ a cote du code, ou dans l'exe (PyInstaller)."""
    if getattr(sys, "frozen", False):
        base = Path(getattr(sys, "_MEIPASS", Path(sys.executable).resolve().parent))
        if (base / "data").exists():
            return base / "data"
        return Path(sys.executable).resolve().parent / "_internal" / "data"
    return Path(__file__).resolve().parents[2] / "data"


def font_file(name: str, size: int):
    key = (name, size)
    hit = _FONTS.get(key)
    if hit is not None:
        return hit
    path = data_dir() / "fonts" / FONT_FILES.get(name, "AlegreyaSans-Regular.ttf")
    try:
        f = pygame.font.Font(str(path), size)
    except (OSError, FileNotFoundError, pygame.error):
        f = pygame.font.SysFont("georgia", size, bold="bold" in name or "black" in name, italic="italic" in name)
    _FONTS[key] = f
    return f


def font(role: str):
    name, size = ROLES.get(role, ROLES["texte"])
    return font_file(name, size)


def reset() -> None:
    """Apres un pygame.quit (les tests) : les polices et surfaces sont a refaire."""
    _FONTS.clear()
    _ICONS.clear()
    _PANELS.clear()
    _GRAIN.clear()


# --- les icones -----------------------------------------------------------------------

# cle -> game-icons.net (auteur/nom) ; tools/recuperer_assets.py les range
# dans data/icons/<cle>.svg.
ICON_FILES = {
    # le temps
    "printemps": "lorc/sprout",
    "ete": "lorc/sun",
    "automne": "lorc/falling-leaf",
    "hiver": "lorc/snowflake-2",
    "pause": "guard13007/pause-button",
    "jouer": "guard13007/play-button",
    "vite": "delapouite/fast-forward-button",
    "sablier": "lorc/hourglass",
    # le peuple
    "prestige": "lorc/palm",
    "gens": "delapouite/meeple-group",
    "vivres": "lorc/meat",
    "savoir": "lorc/spiral-bloom",
    "chef": "lorc/two-feathers",
    "tribu": "lorc/totem-head",
    "peuples": "delapouite/shaking-hands",
    "journal": "lorc/scroll-unfurled",
    "armee": "lorc/spears",
    "commerce": "lorc/trade",
    "village": "delapouite/huts-village",
    "hutte": "delapouite/hut",
    "camp": "delapouite/tipi",
    "cache": "delapouite/basket",
    "grenier": "delapouite/granary",
    "palissade": "delapouite/palisade",
    "tour": "delapouite/watchtower",
    "feu": "lorc/campfire",
    "torche": "delapouite/primitive-torch",
    "homme": "delapouite/caveman",
    # les actions
    "scinder": "delapouite/split-arrows",
    "reunir": "delapouite/join",
    "pas": "skoll/footsteps",
    "honorer": "lorc/laurels",
    "deposer": "delapouite/basket",
    "reprendre": "lorc/meat",
    "fermer": "lorc/cross-mark",
    "voir": "delapouite/hunter-eyes",
    # la carte
    "relief": "lorc/mountains",
    "zones": "delapouite/flag-objective",
    "ressources": "lorc/wheat",
    "route": "delapouite/trail",
    # le journal et les choses du jeu
    "combat": "lorc/crossed-axes",
    "survie": "lorc/campfire",
    "decouverte": "lorc/spiral-bloom",
    "politique": "delapouite/shaking-hands",
    "danger": "lorc/broken-skull",
    "evenement": "delapouite/ceremonial-mask",
    "chasse": "lorc/stone-spear",
    "hache": "lorc/stone-axe",
    "arc": "delapouite/bow-arrow",
    "peche": "lorc/fishing-net",
    "pirogue": "delapouite/canoe",
    "ble": "lorc/wheat",
    "faucille": "delapouite/sickle",
    "poterie": "delapouite/painted-pottery",
    "troupeau": "skoll/goat",
    "boeuf": "delapouite/cow",
    "bison": "delapouite/bison",
    "mammouth": "delapouite/mammoth",
    "cerf": "caro-asercion/deer",
    "loup": "lorc/wolf-head",
    "baies": "delapouite/berry-bush",
    "champignon": "lorc/mushroom",
    "herbes": "delapouite/herbs-bundle",
    "dolmen": "delapouite/dolmen",
    "menhir": "delapouite/menhir",
    "totem": "delapouite/totem",
    "pierre": "lorc/rock",
    "eau": "lorc/drop",
    "riviere": "delapouite/river",
    "vagues": "lorc/waves",
    "montagne": "lorc/mountains",
    "sel": "lorc/salt-shaker",
    "collier": "delapouite/primitive-necklace",
    "balance": "lorc/scales",
    "carte_monde": "lorc/treasure-map",
    "boussole": "lorc/compass",
    # les situations
    "crise": "lorc/burning-embers",
    "conjoncture": "lorc/sands-of-time",
    "secheresse": "lorc/sun",
    "inondation": "delapouite/flood",
    "incendie": "lorc/wildfires",
    "froid": "lorc/snowflake-2",
    "epidemie": "lorc/vomiting",
    "famine": "lorc/wheat",
    "migration": "delapouite/bison",
    "volcan": "delapouite/smoking-volcano",
    "couronne": "lorc/laurel-crown",
    # les nombres et l'argent
    "abaque": "delapouite/abacus",
    "tablette": "lorc/stone-tablet",
    "pieces": "delapouite/two-coins",
    "tresor": "lorc/locked-chest",
    "mine": "lorc/mining",
}
_ICONS: dict = {}


def icon(key: str, size: int, color=None):
    """La silhouette `key` a la taille `size`, teinte `color` (os par defaut)."""
    color = tuple(color or C.os)
    ck = (key, size, color)
    hit = _ICONS.get(ck)
    if hit is not None:
        return hit
    base_key = (key, size, None)
    base = _ICONS.get(base_key)
    if base is None:
        path = data_dir() / "icons" / f"{key}.svg"
        base = None
        if path.exists():
            try:
                base = pygame.image.load_sized_svg(str(path), (size, size)).convert_alpha()
            except (pygame.error, AttributeError, ValueError):
                base = None
        if base is None:
            base = pygame.Surface((size, size), pygame.SRCALPHA)
            pygame.draw.circle(base, (255, 255, 255), (size // 2, size // 2), max(2, size // 3))
        _ICONS[base_key] = base
    out = base.copy()
    out.fill((*color, 0), special_flags=pygame.BLEND_RGBA_MAX)
    out.fill((*color, 255), special_flags=pygame.BLEND_RGBA_MIN)
    _ICONS[ck] = out
    return out


def medallion(key: str, radius: int, state: str = "normal", ring=None):
    """Une icone dans un disque de cuir cercle d'ocre. state : normal,
    actif (braise), connu (ocre jaune), eteint (cendre), danger."""
    ck = ("medaillon", key, radius, state, ring)
    hit = _ICONS.get(ck)
    if hit is not None:
        return hit
    d = radius * 2 + 4
    surf = pygame.Surface((d, d), pygame.SRCALPHA)
    cx = cy = d // 2
    fill = {"actif": (70, 42, 22), "connu": (62, 48, 26), "eteint": (34, 29, 25), "danger": (70, 26, 20)}.get(state, C.cuir)
    edge = ring or {"actif": C.braise, "connu": C.ocre_jaune, "eteint": C.bois, "danger": C.mauvais}.get(state, C.ocre)
    tint = {"actif": C.braise, "connu": C.ocre_jaune, "eteint": C.cendre, "danger": C.os}.get(state, C.os)
    pygame.draw.circle(surf, (0, 0, 0, 120), (cx, cy + 2), radius + 1)
    pygame.draw.circle(surf, fill, (cx, cy), radius)
    # Un leger halo interieur, plus clair en haut (la lumiere du feu).
    pygame.draw.circle(surf, (*_mix(fill, C.os, 0.08), 255), (cx, cy - radius // 5), int(radius * 0.72))
    pygame.draw.circle(surf, fill, (cx, cy + radius // 6), int(radius * 0.7))
    pygame.draw.circle(surf, edge, (cx, cy), radius, 2)
    pygame.draw.circle(surf, (*C.nuit, 160), (cx, cy), radius - 3, 1)
    size = int(radius * 1.25)
    ic = icon(key, size, tint)
    surf.blit(ic, (cx - size // 2, cy - size // 2))
    _ICONS[ck] = surf
    return surf


# --- les matieres : grain, pierre taillee ----------------------------------------------

_GRAIN: dict = {}
_PANELS: dict = {}
PANEL_CACHE = 400


def _mix(a, b, t: float):
    return tuple(int(a[i] + (b[i] - a[i]) * t) for i in range(3))


def grain(strength: int = 18, size: int = 192):
    """Un carreau de grain (peau, pierre) : points clairs et sombres."""
    key = (strength, size)
    hit = _GRAIN.get(key)
    if hit is not None:
        return hit
    rng = random.Random(1789 + strength)
    surf = pygame.Surface((size, size), pygame.SRCALPHA)
    for _ in range(size * size // 6):
        x, y = rng.randrange(size), rng.randrange(size)
        if rng.random() < 0.5:
            surf.set_at((x, y), (255, 240, 210, rng.randint(2, strength)))
        else:
            surf.set_at((x, y), (0, 0, 0, rng.randint(4, strength + 10)))
    # Quelques fibres (la peau tannee) : de courts traits obliques.
    for _ in range(size // 3):
        x, y = rng.randrange(size), rng.randrange(size)
        ln = rng.randint(4, 12)
        a = rng.uniform(-0.5, 0.5)
        pygame.draw.line(surf, (0, 0, 0, strength // 2 + 4), (x, y), (x + int(ln * math.cos(a)), y + int(ln * math.sin(a))))
    _GRAIN[key] = surf
    return surf


def chamfer(rect, cut: int) -> list:
    """Le contour d'un rectangle aux coins coupes (pierre taillee)."""
    x, y, w, h = rect
    c = max(0, min(cut, w // 3, h // 3))
    return [(x + c, y), (x + w - 1 - c, y), (x + w - 1, y + c), (x + w - 1, y + h - 1 - c), (x + w - 1 - c, y + h - 1), (x + c, y + h - 1), (x, y + h - 1 - c), (x, y + c)]


PANEL_STYLE = {
    # kind : (fond haut, fond bas, bord, fil, coupe, grain, ombre)
    "peau": (C.charbon, (19, 15, 12), C.bois, C.ocre, 10, 16, True),
    "pierre": ((58, 51, 45), (40, 35, 31), C.pierre_clair, C.ocre, 12, 26, True),
    "carte": (C.cuir, (30, 23, 18), C.bois, None, 6, 12, False),
    "carte_survol": (C.cuir_clair, (40, 31, 24), C.braise, None, 6, 12, False),
    "carte_choisie": ((66, 44, 26), (48, 32, 20), C.ocre, None, 6, 12, False),
    "creux": ((16, 12, 10), (20, 16, 13), (46, 36, 28), None, 5, 8, False),
    "bandeau": ((30, 23, 18), (20, 15, 12), C.bois, None, 0, 18, False),
    "infobulle": ((26, 20, 16), (20, 16, 12), C.bois_clair, None, 5, 10, True),
    "toast": ((28, 22, 17), (22, 17, 13), C.bois, None, 5, 10, True),
}


def panel_surface(w: int, h: int, kind: str = "peau"):
    key = (w, h, kind)
    hit = _PANELS.get(key)
    if hit is not None:
        return hit
    top, bot, edge, line, cut, gstrength, shadow = PANEL_STYLE.get(kind, PANEL_STYLE["peau"])
    pad = 6 if shadow else 0
    surf = pygame.Surface((w + pad * 2, h + pad * 2), pygame.SRCALPHA)
    body = (pad, pad, w, h)
    poly = chamfer(body, cut)
    if shadow:
        sh = pygame.Surface(surf.get_size(), pygame.SRCALPHA)
        pygame.draw.polygon(sh, (0, 0, 0, 90), [(px, py + 4) for px, py in chamfer((pad - 2, pad, w + 4, h + 2), cut + 2)])
        surf.blit(sh, (0, 0))
    # Le fond : un degrade vertical, puis le grain, decoupes au contour.
    fill = pygame.Surface((w, h), pygame.SRCALPHA)
    for yy in range(h):
        t = yy / max(1, h - 1)
        pygame.draw.line(fill, _mix(top, bot, t), (0, yy), (w, yy))
    g = grain(gstrength)
    gw, gh = g.get_size()
    for gx in range(0, w, gw):
        for gy in range(0, h, gh):
            fill.blit(g, (gx, gy))
    mask = pygame.Surface((w, h), pygame.SRCALPHA)
    pygame.draw.polygon(mask, (255, 255, 255, 255), chamfer((0, 0, w, h), cut))
    fill.blit(mask, (0, 0), special_flags=pygame.BLEND_RGBA_MIN)
    surf.blit(fill, (pad, pad))
    # Les bords : bois dehors, un fil d'ocre dedans, des encoches aux angles.
    pygame.draw.polygon(surf, edge, poly, 2 if kind in ("peau", "pierre") else 1)
    if kind == "pierre":
        # Gravure : clair en haut, sombre en bas.
        pygame.draw.line(surf, (*C.os, 40), (pad + cut + 2, pad + 3), (pad + w - cut - 3, pad + 3))
        pygame.draw.line(surf, (0, 0, 0, 110), (pad + cut + 2, pad + h - 4), (pad + w - cut - 3, pad + h - 4))
    if line is not None:
        inner = chamfer((pad + 5, pad + 5, w - 10, h - 10), max(2, cut - 3))
        ls = pygame.Surface(surf.get_size(), pygame.SRCALPHA)
        pygame.draw.polygon(ls, (*line, 120), inner, 1)
        surf.blit(ls, (0, 0))
        for cx, cy in ((pad + 5, pad + 5), (pad + w - 6, pad + 5), (pad + 5, pad + h - 6), (pad + w - 6, pad + h - 6)):
            pygame.draw.polygon(surf, line, [(cx, cy - 3), (cx + 3, cy), (cx, cy + 3), (cx - 3, cy)])
    if len(_PANELS) > PANEL_CACHE:
        _PANELS.clear()
    _PANELS[key] = surf
    return surf


def panel(surf, rect, kind: str = "peau") -> None:
    x, y, w, h = (int(v) for v in rect)
    if w <= 2 or h <= 2:
        return
    s = panel_surface(w, h, kind)
    pad = (s.get_width() - w) // 2
    surf.blit(s, (x - pad, y - pad))


def glow(surf, rect, color=None, strength: float = 1.0) -> None:
    """La lueur du feu autour d'un rectangle (ce qui est actif, urgent)."""
    color = color or C.braise
    x, y, w, h = (int(v) for v in rect)
    g = pygame.Surface((w + 24, h + 24), pygame.SRCALPHA)
    for i in range(6, 0, -1):
        a = int(18 * strength * (7 - i) / 6)
        pygame.draw.rect(g, (*color, a), (12 - i * 2, 12 - i * 2, w + i * 4, h + i * 4), border_radius=6 + i)
    surf.blit(g, (x - 12, y - 12))


def pulse(t: float, period: float = 2.0) -> float:
    """0..1, lentement (ce qui attend une decision respire)."""
    return 0.5 + 0.5 * math.sin(t * 2 * math.pi / period)


# --- les traits ---------------------------------------------------------------------------


def dotted(surf, a, b, color=None, gap: int = 6, r: int = 1) -> None:
    """Des points d'ocre, comme sur les parois ornees."""
    color = color or C.ocre_sombre
    (x0, y0), (x1, y1) = a, b
    n = max(1, int(math.hypot(x1 - x0, y1 - y0) // gap))
    for i in range(n + 1):
        t = i / n
        pygame.draw.circle(surf, color, (int(x0 + (x1 - x0) * t), int(y0 + (y1 - y0) * t)), r)


def stroke(surf, x: int, y: int, w: int, color=None, thick: int = 3) -> None:
    """Un trait de charbon (ou d'ocre) qui s'effile aux deux bouts."""
    color = color or C.ocre
    for i in range(w):
        t = i / max(1, w - 1)
        k = math.sin(math.pi * t) ** 0.6
        hh = max(1, int(thick * k + 0.3))
        a = int(80 + 175 * k)
        s = pygame.Surface((1, hh), pygame.SRCALPHA)
        s.fill((*color, a))
        surf.blit(s, (x + i, y - hh // 2 + int(math.sin(i * 0.07) * 0.8)))


# --- les textes -------------------------------------------------------------------------------


def fit(f, text: str, width: int) -> str:
    if f.size(text)[0] <= width:
        return text
    while text and f.size(text + "…")[0] > width:
        text = text[:-1]
    return text.rstrip() + "…"


def wrap(f, text: str, width: int) -> list[str]:
    out: list[str] = []
    for para in str(text).split("\n"):
        line = ""
        for word in para.split(" "):
            test = (line + " " + word).strip()
            if f.size(test)[0] <= width or not line:
                line = test
            else:
                out.append(line)
                line = word
        out.append(line)
    return out


def text(surf, s: str, role: str, color, pos, width: int | None = None, shadow: bool = False):
    f = font(role) if isinstance(role, str) else role
    if width is not None:
        s = fit(f, s, width)
    img = f.render(s, True, color)
    if shadow:
        surf.blit(f.render(s, True, C.nuit), (pos[0] + 1, pos[1] + 2))
    surf.blit(img, pos)
    return img.get_width()


def title(surf, s: str, x: int, y: int, role: str = "titre", color=None, underline: int | None = None) -> int:
    """Un titre en petites capitales, souligne d'un trait de charbon ocre."""
    f = font(role)
    img = f.render(s, True, color or C.os)
    surf.blit(f.render(s, True, C.nuit), (x + 1, y + 2))
    surf.blit(img, (x, y))
    w = underline if underline is not None else img.get_width() + 12
    if w:
        stroke(surf, x - 2, y + img.get_height() + 1, w, C.ocre, 3)
    return img.get_height() + 6


# --- les boutons --------------------------------------------------------------------------------


def button(surf, rect, label: str, rank: str = "second", on: bool = True, hover: bool = False, icon_key: str | None = None, key_hint: str = "", role: str | None = None, active: bool = False) -> None:
    """Trois rangs (section 4) : principal (ocre plein), second (cuir),
    discret (texte seul). on=False : desactive. active : choisi."""
    x, y, w, h = (int(v) for v in rect)
    role = role or ("bouton" if h >= 30 else "bouton_petit")
    f = font(role)
    if rank == "discret":
        col = C.braise if hover and on else (C.lin if on else C.cendre)
        tw = f.size(label)[0]
        surf.blit(f.render(label, True, col), (x + (w - tw) // 2, y + (h - f.get_height()) // 2))
        if hover and on:
            pygame.draw.line(surf, C.braise, (x + (w - tw) // 2, y + h - 3), (x + (w + tw) // 2, y + h - 3))
        return
    cut = 5 if h >= 26 else 4
    poly = chamfer((x, y, w, h), cut)
    if not on:
        pygame.draw.polygon(surf, (30, 24, 20), poly)
        pygame.draw.polygon(surf, (52, 42, 34), poly, 1)
        fg = C.cendre
    elif rank == "principal":
        if hover:
            glow(surf, rect, C.braise, 0.9)
        top, bot = (_mix(C.ocre, C.braise, 0.55), C.ocre) if hover else (_mix(C.ocre, C.braise, 0.2), C.ocre_sombre)
        _vgrad_poly(surf, (x, y, w, h), poly, top, bot)
        pygame.draw.polygon(surf, C.braise if hover else _mix(C.ocre, C.os, 0.25), poly, 1)
        pygame.draw.line(surf, (*_mix(C.braise, C.os, 0.4),), (x + cut + 1, y + 1), (x + w - cut - 2, y + 1))
        fg = C.nuit
    else:
        top, bot = ((C.cuir_clair, C.cuir) if hover or active else ((44, 34, 26), (30, 23, 18)))
        if active:
            top, bot = (78, 52, 30), (52, 35, 21)
        _vgrad_poly(surf, (x, y, w, h), poly, top, bot)
        pygame.draw.polygon(surf, C.braise if hover else (C.ocre if active else C.bois), poly, 1)
        pygame.draw.line(surf, _mix(top, C.os, 0.12), (x + cut + 1, y + 1), (x + w - cut - 2, y + 1))
        fg = C.os
    cx = x + w // 2
    content = f.size(label)[0]
    isz = max(12, h - 10)
    if icon_key:
        content += isz + (6 if label else 0)
    hint_w = 0
    if key_hint:
        hf = font("mini")
        hint_w = hf.size(key_hint)[0] + 8
    left = cx - (content + hint_w) // 2
    if icon_key:
        surf.blit(icon(icon_key, isz, fg), (left, y + (h - isz) // 2))
        left += isz + (6 if label else 0)
    if label:
        surf.blit(f.render(label, True, fg), (left, y + (h - f.get_height()) // 2 - 1))
        left += f.size(label)[0]
    if key_hint:
        hf = font("mini")
        surf.blit(hf.render(key_hint, True, C.nuit if rank == "principal" and on else C.cendre), (left + 6, y + (h - hf.get_height()) // 2))


def _vgrad_poly(surf, rect, poly, top, bot) -> None:
    x, y, w, h = rect
    tmp = pygame.Surface((w, h), pygame.SRCALPHA)
    for yy in range(h):
        pygame.draw.line(tmp, _mix(top, bot, yy / max(1, h - 1)), (0, yy), (w, yy))
    mask = pygame.Surface((w, h), pygame.SRCALPHA)
    pygame.draw.polygon(mask, (255, 255, 255, 255), [(px - x, py - y) for px, py in poly])
    tmp.blit(mask, (0, 0), special_flags=pygame.BLEND_RGBA_MIN)
    surf.blit(tmp, (x, y))


def icon_button(surf, rect, icon_key: str, on: bool = True, hover: bool = False, active: bool = False) -> None:
    """Un bouton carre a icone (actions de bande, controles du temps)."""
    button(surf, rect, "", "second", on, hover, icon_key=icon_key, active=active)


# --- barres, pastilles, infobulles ---------------------------------------------------------------


def bar(surf, rect, frac: float, color=None, back=None, marks=()) -> None:
    """Une rainure sombre remplie de pigment (attachement, stabilite...)."""
    x, y, w, h = (int(v) for v in rect)
    color = color or C.ocre
    pygame.draw.rect(surf, back or (12, 9, 7), (x, y, w, h), border_radius=2)
    pygame.draw.rect(surf, (60, 47, 36), (x, y, w, h), 1, border_radius=2)
    fw = int((w - 2) * max(0.0, min(1.0, frac)))
    if fw > 0:
        pygame.draw.rect(surf, color, (x + 1, y + 1, fw, h - 2), border_radius=2)
        pygame.draw.line(surf, _mix(color, C.os, 0.45), (x + 2, y + 1), (x + fw - 1, y + 1))
    for m in marks:
        mx = x + int(w * m)
        pygame.draw.line(surf, (0, 0, 0), (mx, y - 1), (mx, y + h))


def chip(surf, x: int, y: int, label: str, color=None, icon_key: str | None = None, role: str = "mini_gras") -> int:
    """Une petite etiquette (etat, bonus) ; rend sa largeur."""
    f = font(role)
    color = color or C.ocre
    w = f.size(label)[0] + 14 + (16 if icon_key else 0)
    h = f.get_height() + 4
    poly = chamfer((x, y, w, h), 3)
    pygame.draw.polygon(surf, _mix(C.charbon, color, 0.22), poly)
    pygame.draw.polygon(surf, color, poly, 1)
    tx = x + 7
    if icon_key:
        surf.blit(icon(icon_key, 13, color), (tx - 1, y + (h - 13) // 2))
        tx += 16
    surf.blit(f.render(label, True, _mix(color, C.os, 0.45)), (tx, y + 2))
    return w


def tooltip(surf, lines, x: int, y: int, width: int = 360, avoid=None) -> None:
    """lines : [(texte, couleur)] ou [(texte, couleur, role)]. avoid : un
    rectangle (le bouton survole) que la fiche ne doit jamais cacher."""
    rows = []
    for item in lines:
        txt, col = item[0], item[1]
        role = item[2] if len(item) > 2 else "petit"
        f = font(role)
        for part in wrap(f, txt, width - 24):
            rows.append((part, col, f))
    if not rows:
        return
    h = sum(f.get_height() + 1 for _t, _c, f in rows) + 14
    w = min(width, max(f.size(t)[0] for t, _c, f in rows) + 26)
    sw, sh = surf.get_size()
    x = max(4, min(x, sw - w - 4))
    y = max(4, min(y, sh - h - 4))
    if avoid is not None:
        x, y = _beside(avoid, w, h, sw, sh, x, y)
    panel(surf, (x, y, w, h), "infobulle")
    pygame.draw.line(surf, C.braise, (x + 3, y + 6), (x + 3, y + h - 7), 2)
    yy = y + 7
    for t, c, f in rows:
        surf.blit(f.render(t, True, c), (x + 13, yy))
        yy += f.get_height() + 1


def _beside(rect, w: int, h: int, sw: int, sh: int, x: int, y: int) -> tuple[int, int]:
    """Une place pour une fiche w x h qui ne recouvre pas rect : la ou elle
    etait si elle ne le touche pas, sinon a gauche, a droite, au-dessus ou
    au-dessous du rectangle (le premier qui tient dans l'ecran)."""
    ax, ay, aw, ah = rect

    def clear(px, py):
        return px + w <= ax or px >= ax + aw or py + h <= ay or py >= ay + ah

    if clear(x, y):
        return x, y
    top = max(4, min(ay, sh - h - 4))
    tries = (
        (ax - w - 8, top),
        (ax + aw + 8, top),
        (max(4, min(ax + aw - w, sw - w - 4)), ay - h - 8),
        (max(4, min(ax + aw - w, sw - w - 4)), ay + ah + 8),
    )
    for px, py in tries:
        if 4 <= px and px + w <= sw - 4 and 4 <= py and py + h <= sh - 4 and clear(px, py):
            return px, py
    return x, y


def veil(surf, alpha: int = 150) -> None:
    """La penombre derriere une fenetre solennelle : un voile uni, plus
    sombre vers les bords (vignettage doux, sans cadre visible)."""
    w, h = surf.get_size()
    key = ("voile", w, h, alpha)
    v = _PANELS.get(key)
    if v is None:
        small = pygame.Surface((32, 18), pygame.SRCALPHA)
        for yy in range(18):
            for xx in range(32):
                dx, dy = (xx - 15.5) / 16, (yy - 8.5) / 9
                d = min(1.0, (dx * dx + dy * dy) ** 0.5)
                small.set_at((xx, yy), (*C.nuit, int(alpha + (235 - alpha) * d * d * 0.6)))
        v = pygame.transform.smoothscale(small, (w, h))
        _PANELS[key] = v
    surf.blit(v, (0, 0))


_CACHE: dict = {}


def _lerp(a, b, t):
    return tuple(int(a[i] + (b[i] - a[i]) * t) for i in range(3))


def _gradient_card(w: int, h: int, top, bot, radius: int) -> pygame.Surface:
    """Une carte en pierre taillee (theme.chamfer), degrade et grain."""
    key = ("card", w, h, top, bot, radius)
    hit = _CACHE.get(key)
    if hit is not None:
        return hit
    surf = pygame.Surface((w, h), pygame.SRCALPHA)
    for y in range(h):
        pygame.draw.line(surf, _lerp(top, bot, y / max(1, h - 1)) + (255,), (0, y), (w, y))
    g = theme.grain(12)
    for gx in range(0, w, g.get_width()):
        for gy in range(0, h, g.get_height()):
            surf.blit(g, (gx, gy))
    mask = pygame.Surface((w, h), pygame.SRCALPHA)
    pygame.draw.polygon(mask, (255, 255, 255, 255), theme.chamfer((0, 0, w, h), max(3, min(radius, 10))))
    surf.blit(mask, (0, 0), special_flags=pygame.BLEND_RGBA_MULT)
    if len(_CACHE) > 400:
        _CACHE.clear()
    _CACHE[key] = surf
    return surf
