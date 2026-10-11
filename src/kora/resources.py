"""Ressources du pays : des couches continues sur toute la planete.

Pas de "case a ressource" a la Civilization : chaque case porte une valeur
de 0 a 1 pour CHAQUE ressource, et une case peut en porter plusieurs
(cereales sauvages et aurochs dans une meme vallee, silex dans les
collines voisines...). Elles viennent du biome, du climat (temperature,
pluie, rivieres) et de grandes taches de bruit : la geographie fait que
chaque continent a ses richesses.

Elles comptent :
  - un peu dans la collecte (gibier, plantes, poisson : world.food_production) ;
  - dans les conditions des savoirs (semaines vecues pres du sel, des
    chevres, des cereales... : tech.Cond("res")) ;
  - plus tard dans les champs et les troupeaux des villages.

Generation (numpy) : a la cuisson de la carte seulement (mapgen.bake),
avec un hasard separe de celui du relief. En jeu : octets en Python pur
(world.set_resources / world.resource).

Les nouvelles planetes (0.20, mapgen.generate_layers_v2) : les ETRES
VIVANTS (KIND "plante", "gibier", "eau") vivent dans des AIRES de tailles
variees ; les MATIERES (KIND "matiere") sont des GISEMENTS de 1 a 4 cases.
Huit ressources de plus (fruits, miel, bois, ocre, obsidienne, ambre,
cuivre, etain) ; le cuivre et l'etain ne se voient qu'avec le savoir qui
les fait reconnaitre (hidden_for).
"""

from __future__ import annotations

import base64
import zlib
from src.kora.types import Terrain

RESOURCES = (
    ("cereales", "céréales sauvages", "plante"),
    ("racines", "racines et tubercules", "plante"),
    ("aurochs", "aurochs", "gibier"),
    ("chevaux", "chevaux sauvages", "gibier"),
    ("chevres", "chèvres sauvages", "gibier"),
    ("rennes", "rennes", "gibier"),
    ("poisson", "poisson", "eau"),
    ("silex", "silex", "matiere"),
    ("argile", "argile", "matiere"),
    ("sel", "sel", "matiere"),
    # L'argent-metal (derive_silver : tire du relief, sans recuire
    # l'ancienne carte ; cuit en gisements sur les nouvelles planetes).
    ("argent", "argent (métal)", "matiere"),
    # Les nouvelles planetes (0.20).
    ("fruits", "fruits et noix", "plante"),
    ("miel", "miel sauvage", "plante"),
    ("bois", "bois d'œuvre", "plante"),
    ("ocre", "ocre", "matiere"),
    ("obsidienne", "obsidienne", "matiere"),
    ("ambre", "ambre", "matiere"),
    ("cuivre", "cuivre natif", "matiere"),
    ("etain", "étain", "matiere"),
)
NAMES = tuple(r[0] for r in RESOURCES)
# Les couches de l'ancienne carte cuite (l'argent s'y tire du relief au
# chargement).
BAKED = ("cereales", "racines", "aurochs", "chevaux", "chevres", "rennes", "poisson", "silex", "argile", "sel")
# Les couches des nouvelles planetes.
BAKED_V2 = NAMES
# Ce qui ne se voit pas sans un savoir : ressource -> savoir qui la revele
# ("" : cachee pour l'instant ; l'etain sert au bronze, a l'age suivant).
REVEALED_BY = {"cuivre": "cuivre", "etain": ""}
LABELS = {r[0]: r[1] for r in RESOURCES}
KINDS = {r[0]: r[2] for r in RESOURCES}
GAME = ("aurochs", "chevaux", "chevres", "rennes")
PLANTS = ("cereales", "racines", "fruits", "miel")
# Une ressource "est la" (savoirs, fiche de case) a partir de 0,4.
PRESENT = 0.4
PRESENT_BYTE = int(PRESENT * 255)
# Collecte : x (1 + 0,12 gibier + 0,08 plantes + 0,08 poisson), au plus +28 %.
RICH_GAME = 0.12
RICH_PLANT = 0.08
RICH_FISH = 0.08
# Couleurs du calque "Ressources".
COLORS = {
    "cereales": (236, 206, 90),
    "racines": (190, 150, 70),
    "aurochs": (150, 90, 60),
    "chevaux": (205, 140, 90),
    "chevres": (225, 225, 205),
    "rennes": (160, 170, 190),
    "poisson": (80, 160, 230),
    "silex": (120, 120, 130),
    "argile": (200, 110, 80),
    "sel": (250, 250, 250),
    "argent": (196, 204, 222),
    "fruits": (220, 90, 120),
    "miel": (245, 170, 30),
    "bois": (120, 80, 40),
    "ocre": (205, 95, 40),
    "obsidienne": (40, 30, 50),
    "ambre": (255, 190, 60),
    "cuivre": (190, 110, 60),
    "etain": (170, 180, 175),
}


def hidden_for(tribe) -> frozenset:
    """Les ressources que ce peuple ne reconnait pas encore (carte, fiches,
    villages) ; tout est visible sans peuple (tests, outils)."""
    if tribe is None:
        return frozenset()
    known = tribe.knowledge
    return frozenset(n for n, by in REVEALED_BY.items() if not by or by not in known)


def level_word(value: float) -> str:
    if value >= 0.7:
        return "beaucoup"
    if value >= PRESENT:
        return "assez"
    if value >= 0.15:
        return "un peu"
    return ""


# --- l'argent-metal ----------------------------------------------------------------
#
# Les filons d'argent ne sont pas dans la carte cuite : on les tire du relief
# (collines, montagnes, sommets), par grandes taches (un filon tous les
# quelques massifs), avec un hasard fixe (crc32 des coordonnees) : le meme
# sur chaque machine, sans recuire la carte ni changer les parties.

SILVER_CELL = 7
SILVER_VEINS = 0.45


def _unit(text: str) -> float:
    return zlib.crc32(text.encode("ascii")) / 4294967295.0


def derive_silver(width: int, height: int, terrains) -> bytes:
    """La couche d'argent (octets 0..255, rangee par rangee) a partir des
    terrains (terrains[row][col])."""
    hills = (Terrain.COLLINE, Terrain.MONTAGNE, Terrain.SOMMET)
    out = bytearray(width * height)
    for row in range(height):
        line = terrains[row]
        for col in range(width):
            if line[col] not in hills:
                continue
            cx, cy = col // SILVER_CELL, row // SILVER_CELL
            if _unit(f"ag:{cx}:{cy}") >= SILVER_VEINS:
                continue
            strength = 0.45 + 0.55 * _unit(f"agf:{cx}:{cy}")
            fine = _unit(f"ag:{col}:{row}")
            v = strength * (0.5 + 0.5 * fine) if fine < 0.65 else 0.15 * fine
            out[row * width + col] = min(255, int(v * 255 + 0.5))
    return bytes(out)


# --- stockage ------------------------------------------------------------------


def encode(layer: bytes) -> str:
    return base64.b64encode(zlib.compress(bytes(layer), 9)).decode("ascii")


def decode(text: str) -> bytes:
    return zlib.decompress(base64.b64decode(text.encode("ascii")))


def richness(layers: dict, width: int, height: int) -> bytes:
    """Multiplicateur de collecte de chaque case, code sur un octet
    (0 = x1, 255 = x(1 + RICH_GAME + RICH_PLANT + RICH_FISH))."""
    top = RICH_GAME + RICH_PLANT + RICH_FISH
    n = width * height
    game = [0] * n
    for name in GAME:
        layer = layers.get(name)
        if layer:
            game = [a if a >= b else b for a, b in zip(game, layer)]
    plant = [0] * n
    for name in PLANTS:
        layer = layers.get(name)
        if layer:
            plant = [a if a >= b else b for a, b in zip(plant, layer)]
    fish = layers.get("poisson") or bytes(n)
    out = bytearray(n)
    scale = 1.0 / (255.0 * top)
    for i in range(n):
        v = (RICH_GAME * game[i] + RICH_PLANT * plant[i] + RICH_FISH * fish[i]) * scale
        out[i] = min(255, int(v * 255 + 0.5))
    return bytes(out)


# (La cuisson des couches : mapgen.generate_layers.)


# Part des terres ou chaque ressource est "presente" (0,4 et plus).
COVER = {
    "cereales": 0.08,
    "racines": 0.07,
    "aurochs": 0.12,
    "chevaux": 0.08,
    "chevres": 0.08,
    "rennes": 0.08,
    "poisson": 0.12,
    "silex": 0.06,
    "argile": 0.06,
    "sel": 0.03,
    # Pas cuit : derive_silver (filons des collines), environ 5 % des terres.
    "argent": 0.05,
    # Les aires des nouvelles planetes (les gisements, eux, se comptent :
    # mapgen.DEPOSITS).
    "fruits": 0.07,
    "miel": 0.05,
    "bois": 0.14,
}
