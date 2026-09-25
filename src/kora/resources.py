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
"""

from __future__ import annotations

import base64
import zlib

RESOURCES = (
    ("cereales", "cereales sauvages", "plante"),
    ("racines", "racines et tubercules", "plante"),
    ("aurochs", "aurochs", "gibier"),
    ("chevaux", "chevaux sauvages", "gibier"),
    ("chevres", "chevres sauvages", "gibier"),
    ("rennes", "rennes", "gibier"),
    ("poisson", "poisson", "eau"),
    ("silex", "silex", "matiere"),
    ("argile", "argile", "matiere"),
    ("sel", "sel", "matiere"),
)
NAMES = tuple(r[0] for r in RESOURCES)
LABELS = {r[0]: r[1] for r in RESOURCES}
KINDS = {r[0]: r[2] for r in RESOURCES}
GAME = ("aurochs", "chevaux", "chevres", "rennes")
PLANTS = ("cereales", "racines")
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
}


def level_word(value: float) -> str:
    if value >= 0.7:
        return "beaucoup"
    if value >= PRESENT:
        return "assez"
    if value >= 0.15:
        return "un peu"
    return ""


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


# --- generation (numpy, a la cuisson) ----------------------------------------------


def generate_layers(seed: int, grid, climate) -> dict:
    """Couches 0..255 (octets, rangee par rangee) pour chaque ressource."""
    import numpy as np

    from src.kora.mapgen import Noise3, _hex_neighbors, fbm

    rng = np.random.default_rng(seed + 7919)
    p = climate["p"]
    temp = climate["temp"]
    wet = climate["wet"]
    flow = climate["flow"]
    height, width = grid.shape
    terr = {ch: (grid == ch).astype(np.float64) for ch in "PVSFCMXEOD"}
    land = (grid != "E") & (grid != "X")
    water = grid == "E"
    shore = np.zeros_like(water)
    for nr, nc, ok in _hex_neighbors(width, height):
        shore |= ok & land[nr, nc]
    inshore = (water & shore).astype(np.float64)
    fq = np.quantile(flow[land], 0.9) if land.any() else 1.0
    river = np.clip(flow / max(1e-9, fq), 0.0, 1.0)

    def blobs(freq: float, cover: float, octaves: int = 4):
        n = fbm(Noise3(rng), p, freq, octaves)
        ref = n[land] if land.any() else n.ravel()
        lo = np.quantile(ref, 1.0 - cover)
        hi = np.quantile(ref, 0.985)
        v = np.clip((n - lo) / max(1e-6, hi - lo), 0.0, 1.0)
        return v * v * (3.0 - 2.0 * v)

    def band(x, lo: float, hi: float, soft: float = 0.12):
        return np.clip(np.minimum((x - lo) / soft + 1.0, (hi - x) / soft + 1.0), 0.0, 1.0)

    def suit(weights: dict):
        out = np.zeros((height, width))
        for ch, w in weights.items():
            out += w * terr[ch]
        return out

    layers = {
        "cereales": suit({"V": 1.0, "P": 0.8, "S": 0.35, "C": 0.25, "O": 0.25, "F": 0.1})
        * band(temp, 0.45, 0.8)
        * band(wet, 0.45, 1.3, 0.3)
        * blobs(2.5, 0.45),
        "racines": suit({"F": 1.0, "V": 0.8, "P": 0.4, "O": 0.3})
        * band(temp, 0.72, 1.3)
        * band(wet, 0.9, 5.0, 0.3)
        * blobs(3.0, 0.5),
        "aurochs": suit({"P": 1.0, "V": 0.8, "F": 0.55, "S": 0.35}) * band(temp, 0.35, 0.78) * blobs(2.2, 0.55),
        "chevaux": suit({"S": 1.0, "P": 0.55, "D": 0.2}) * band(temp, 0.25, 0.7) * blobs(2.0, 0.6),
        "chevres": suit({"C": 1.0, "M": 0.9, "D": 0.2, "S": 0.2}) * band(temp, 0.2, 0.95) * blobs(3.0, 0.6),
        "rennes": suit({"S": 0.9, "F": 0.8, "P": 0.7, "C": 0.6}) * band(temp, -1.0, 0.3) * blobs(2.0, 0.7),
        "poisson": (terr["O"] + 0.6 * terr["V"] * river + inshore) * (0.45 + 0.55 * blobs(3.0, 0.7)),
        "silex": suit({"C": 1.0, "M": 0.4, "P": 0.35, "V": 0.25, "S": 0.2}) * blobs(4.0, 0.25),
        "argile": suit({"V": 1.0, "O": 0.5, "P": 0.3, "F": 0.2}) * (0.4 + 0.6 * river) * blobs(3.0, 0.5),
        "sel": (
            terr["O"] * band(wet, 0.0, 0.7, 0.2)
            + 0.7 * terr["D"]
            + 0.5 * inshore * band(wet, 0.0, 0.6, 0.2)
            + 0.2 * terr["C"]
        )
        * blobs(3.5, 0.3),
    }
    out = {}
    for name in NAMES:
        raw = np.clip(layers[name], 0.0, None)
        # Chaque ressource couvre une part voulue des terres (seuil 0,4) :
        # le produit des facteurs la rendait sinon beaucoup trop rare.
        ref = raw[land]
        q = float(np.quantile(ref, 1.0 - COVER[name])) if ref.size else 0.0
        if q <= 1e-6:
            q = float(ref.max()) * 0.5 if ref.size and ref.max() > 0 else 1.0
        v = np.clip(raw * (PRESENT / q), 0.0, 1.0)
        out[name] = (v * 255.0 + 0.5).astype(np.uint8).tobytes()
    return out


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
}
