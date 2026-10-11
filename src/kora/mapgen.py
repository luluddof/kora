"""Generation de la planete Kora (numpy).

Le jeu ne genere rien au lancement : il charge data/kora_map.json. Ce
module sert a recuire la carte (voir docs/code/carte-du-depot.txt).

Etapes, toutes sur la sphere (pas de couture sur la ligne de date, pas
d'etirement aux poles) :
  1. plaques tectoniques (frontieres deformees par du bruit), chacune
     continentale ou oceanique, avec un mouvement propre ;
  2. relief : socle des plaques + bruit fractal + collisions (chaines de
     montagnes, cordilleres cotieres, arcs d'iles) + rifts ;
  3. niveau de la mer choisi pour une part de terres donnee ;
  4. climat : temperature (latitude, altitude), pluie portee par les
     vents dominants, avec ombre pluviometrique derriere les reliefs ;
  5. bassins versants : les depressions deviennent des lacs, l'eau
     descend jusqu'a la mer ; les RIVIERES (0.20) : chaque case de riviere
     garde son sens (la case en aval) et sa taille (ruisseau, riviere,
     fleuve) ; elles creusent des vallees, s'etalent en marais ;
  6. biomes (toundra, savane, jungle, marais, 0.20), cotes, calottes de
     glace.
Les planetes du jeu (1536 x 768, data/planetes/) se cuisent avec
tools/cuire_planetes.py ; l'ancienne carte (768 x 384, data/kora_map.json)
reste pour les anciennes parties.
"""

from __future__ import annotations

import heapq
import math

import numpy as np

from src.kora.resources import BAKED, BAKED_V2, COVER, KINDS, PRESENT
from src.kora.types import Terrain
from src.kora.world import (
    CHAR_TO_TERRAIN,
    NEIGHBOR_DELTAS,
    World,
    axial_to_offset,
    offset_to_axial,
    save_world,
)
from src.kora.atlas import build_atlas_labels

# Les nouvelles planetes (0.20) : 4 fois l'ancienne carte (768 x 384).
PLANET_WIDTH = 1536
PLANET_HEIGHT = 768
LAND_SHARE = 0.36
# Les rivieres : la part des terres (debit le plus fort) qui porte un
# ruisseau, une riviere, un fleuve.
RIVER_SHARE = 0.034
RIVER_MID_SHARE = 0.011
RIVER_BIG_SHARE = 0.0035

_GRADS = np.array(
    [
        [1, 1, 0], [-1, 1, 0], [1, -1, 0], [-1, -1, 0],
        [1, 0, 1], [-1, 0, 1], [1, 0, -1], [-1, 0, -1],
        [0, 1, 1], [0, -1, 1], [0, 1, -1], [0, -1, -1],
    ],
    dtype=np.float64,
)


# --- bruit ---------------------------------------------------------------


class Noise3:
    """Bruit de gradient 3D (Perlin), vectorise."""

    def __init__(self, rng: np.random.Generator) -> None:
        perm = rng.permutation(256)
        self.perm = np.concatenate([perm, perm]).astype(np.int64)
        self.offset = rng.uniform(-1000.0, 1000.0, size=3)

    def __call__(self, x: np.ndarray, y: np.ndarray, z: np.ndarray) -> np.ndarray:
        x = x + self.offset[0]
        y = y + self.offset[1]
        z = z + self.offset[2]
        xi, yi, zi = np.floor(x), np.floor(y), np.floor(z)
        xf, yf, zf = x - xi, y - yi, z - zi
        xi = xi.astype(np.int64) & 255
        yi = yi.astype(np.int64) & 255
        zi = zi.astype(np.int64) & 255
        u = xf * xf * xf * (xf * (xf * 6 - 15) + 10)
        v = yf * yf * yf * (yf * (yf * 6 - 15) + 10)
        w = zf * zf * zf * (zf * (zf * 6 - 15) + 10)
        perm = self.perm

        def corner(dx, dy, dz):
            h = perm[perm[perm[xi + dx] + yi + dy] + zi + dz] % 12
            g = _GRADS[h]
            return g[..., 0] * (xf - dx) + g[..., 1] * (yf - dy) + g[..., 2] * (zf - dz)

        x00 = corner(0, 0, 0) + u * (corner(1, 0, 0) - corner(0, 0, 0))
        x10 = corner(0, 1, 0) + u * (corner(1, 1, 0) - corner(0, 1, 0))
        x01 = corner(0, 0, 1) + u * (corner(1, 0, 1) - corner(0, 0, 1))
        x11 = corner(0, 1, 1) + u * (corner(1, 1, 1) - corner(0, 1, 1))
        y0 = x00 + v * (x10 - x00)
        y1 = x01 + v * (x11 - x01)
        return y0 + w * (y1 - y0)


def fbm(noise: Noise3, p: np.ndarray, freq: float, octaves: int, gain: float = 0.5) -> np.ndarray:
    total = np.zeros(p.shape[:-1])
    amp = 1.0
    norm = 0.0
    for _ in range(octaves):
        total += amp * noise(p[..., 0] * freq, p[..., 1] * freq, p[..., 2] * freq)
        norm += amp
        amp *= gain
        freq *= 2.03
    return total / norm


def ridged(noise: Noise3, p: np.ndarray, freq: float, octaves: int) -> np.ndarray:
    total = np.zeros(p.shape[:-1])
    amp = 1.0
    norm = 0.0
    for _ in range(octaves):
        n = 1.0 - np.abs(noise(p[..., 0] * freq, p[..., 1] * freq, p[..., 2] * freq))
        total += amp * n * n
        norm += amp
        amp *= 0.5
        freq *= 2.1
    return total / norm


# --- geometrie -----------------------------------------------------------


def sphere_points(width: int, height: int) -> tuple[np.ndarray, np.ndarray]:
    """Point de la sphere sous chaque case (meme projection que le rendu)
    et latitude (radians)."""
    cols = np.arange(width)
    rows = np.arange(height)
    lon = 2.0 * math.pi * (cols + 0.5) / width - math.pi
    lat = (math.pi / 2.0) - math.pi * rows / max(1, height - 1)
    cl = np.cos(lat)[:, None]
    p = np.stack(
        [
            cl * np.sin(lon)[None, :],
            np.repeat(np.sin(lat)[:, None], width, axis=1),
            cl * np.cos(lon)[None, :],
        ],
        axis=-1,
    )
    return p, np.repeat(lat[:, None], width, axis=1)


def _hex_neighbors(width: int, height: int):
    """Pour chaque direction hexagonale (ordre de world.NEIGHBOR_DELTAS),
    les indices (rangee, colonne) du voisin, et un masque 'dans la carte'."""
    rows = np.arange(height)[:, None]
    cols = np.arange(width)[None, :]
    half = lambda r: (r - (r & 1)) // 2  # noqa: E731
    out = []
    for dq, dr in NEIGHBOR_DELTAS:
        nr = rows + dr
        nc = (cols + dq + half(nr) - half(rows)) % width
        ok = (nr >= 0) & (nr < height)
        out.append((np.clip(nr, 0, height - 1) + 0 * cols, nc + 0 * rows, ok + 0 * cols > 0))
    return out


# --- etapes --------------------------------------------------------------


def _plates(rng, p, noise_a, noise_b):
    n = int(rng.integers(22, 30))
    seeds = rng.normal(size=(n, 3))
    seeds /= np.linalg.norm(seeds, axis=1, keepdims=True)
    # Frontieres irregulieres : on deforme le point avant de chercher la graine.
    warp = np.stack([fbm(noise_a, p, 1.6, 4), fbm(noise_b, p, 1.6, 4), fbm(noise_a, p[..., ::-1], 1.6, 4)], axis=-1)
    q = p + 0.42 * warp
    q /= np.linalg.norm(q, axis=-1, keepdims=True)
    sims = q @ seeds.T  # (H, W, n)
    order = np.argsort(-sims, axis=-1)
    first, second = order[..., 0], order[..., 1]
    s1 = np.take_along_axis(sims, first[..., None], -1)[..., 0]
    s2 = np.take_along_axis(sims, second[..., None], -1)[..., 0]
    gap = np.arccos(np.clip(s2, -1, 1)) - np.arccos(np.clip(s1, -1, 1))
    # Plaques qui se touchent.
    edge = gap < 0.03
    touching = [set() for _ in range(n)]
    for a, b in set(zip(first[edge].tolist(), second[edge].tolist())):
        touching[a].add(b)
        touching[b].add(a)
    # Continents : un coeur, parfois soude a une plaque voisine (chaine de
    # collision au milieu). Deux continents differents ne se touchent
    # jamais : il reste toujours une plaque oceanique entre eux.
    owner = np.full(n, -1)
    wanted = int(rng.integers(5, 8))

    def free(plate: int, continent: int) -> bool:
        return owner[plate] < 0 and all(owner[t] in (-1, continent) for t in touching[plate])

    for plate in rng.permutation(n).tolist():
        if (owner >= 0).sum() >= wanted * 2 or len(set(owner[owner >= 0])) >= wanted:
            break
        continent = int(owner.max()) + 1
        if free(plate, continent):
            owner[plate] = continent
    for continent in sorted(set(owner[owner >= 0].tolist())):
        if rng.random() >= 0.6:
            continue
        core = int(np.nonzero(owner == continent)[0][0])
        mates = [t for t in touching[core] if free(t, continent)]
        if mates:
            owner[int(rng.choice(mates))] = continent
    continental = owner >= 0
    base = np.where(continental, rng.uniform(0.28, 0.5, n), rng.uniform(-0.55, -0.3, n))
    motion = rng.normal(size=(n, 3))
    motion -= (motion * seeds).sum(axis=1, keepdims=True) * seeds
    motion *= rng.uniform(0.35, 1.0, (n, 1)) / np.linalg.norm(motion, axis=1, keepdims=True)
    return {
        "seeds": seeds,
        "continental": continental,
        "base": base,
        "motion": motion,
        "first": first,
        "second": second,
        "gap": gap,
    }


def _elevation(rng, p, lat, pl, noises):
    n_shape, n_detail, n_ridge, n_warp = noises
    first, second, gap = pl["first"], pl["second"], pl["gap"]
    base1 = pl["base"][first]
    base2 = pl["base"][second]
    # Socle. Entre deux plaques de meme nature : on adoucit la marche.
    # Entre continent et ocean : une "continentalite" continue (0.5 sur la
    # frontiere, 1 au coeur du continent, 0 au large), elevee au carre pour
    # que la cote tombe a l'interieur de la plaque continentale (plateau).
    blend = 0.5 * np.exp(-gap / 0.09)
    elev = base1 * (1.0 - blend) + base2 * blend
    c1 = pl["continental"][first]
    c2 = pl["continental"][second]
    taper = np.clip(gap / 0.22, 0.0, 1.0)
    taper = taper * taper * (3.0 - 2.0 * taper)
    mixed = c1 != c2
    land_level = np.where(c1, base1, base2)
    sea_level = np.where(c1, base2, base1)
    cont = np.where(c1, 0.5 + 0.5 * taper, 0.5 - 0.5 * taper)
    elev = np.where(mixed, sea_level + (land_level - sea_level) * cont * cont, elev)
    # Convergence : mouvement relatif projete sur l'axe entre les graines.
    seeds, motion = pl["seeds"], pl["motion"]
    axis = seeds[second] - seeds[first]
    axis /= np.maximum(1e-9, np.linalg.norm(axis, axis=-1, keepdims=True))
    conv = ((motion[first] - motion[second]) * axis).sum(axis=-1)
    cont1 = pl["continental"][first]
    cont2 = pl["continental"][second]
    near = np.exp(-((gap / 0.055) ** 2))
    # Cordillere de subduction : sur le continent, en retrait de la frontiere
    # (sinon elle surgit au large, en liseré parallele a la cote).
    inland = np.exp(-(((gap - 0.12) / 0.06) ** 2))
    rough = ridged(n_ridge, p, 5.0, 5)
    both = cont1 & cont2
    # Collision de continents : grande chaine, sinueuse grace au bruit en crete.
    uplift = np.where(both & (conv > 0), conv * near * (0.55 + 0.75 * rough), 0.0)
    # Ocean sous continent : cordillere cote continent, fosse cote ocean.
    sub = cont1 & ~cont2 & (conv > 0)
    uplift += np.where(sub, conv * inland * (0.35 + 0.5 * rough), 0.0)
    elev -= np.where(~cont1 & cont2 & (conv > 0), conv * near * 0.25, 0.0)
    # Deux oceans qui se heurtent : arc d'iles.
    arc = ~cont1 & ~cont2 & (conv > 0.25)
    broken = np.clip(fbm(n_detail, p, 16.0, 2) * 4.0 + 0.2, 0.0, 1.0)
    # Arcs et points chauds : des iles montagneuses, pas des murs de glace.
    # Ils comptent en entier pour l'altitude, a moitie pour le relief.
    islands = np.where(arc, conv * near * (0.45 + 0.9 * rough) * broken, 0.0)
    # Points chauds : chapelets d'iles volcaniques au milieu des oceans.
    for _ in range(int(rng.integers(5, 10))):
        spot = rng.normal(size=3)
        spot /= np.linalg.norm(spot)
        drift = rng.normal(size=3)
        drift -= drift.dot(spot) * spot
        drift /= np.linalg.norm(drift)
        for k in range(int(rng.integers(3, 8))):
            c = spot + drift * 0.045 * k
            c /= np.linalg.norm(c)
            size = rng.uniform(0.012, 0.026) * (1.0 - 0.08 * k)
            d = np.arccos(np.clip(p @ c, -1.0, 1.0))
            islands += 0.75 * np.exp(-((d / size) ** 2)) * (1.0 - 0.1 * k)
    # Ecartement : rift sur les continents, dorsale sous la mer.
    elev += np.where((conv < 0) & both, conv * near * 0.25, 0.0)
    elev += np.where((conv < 0) & ~cont1 & ~cont2, -conv * near * 0.12, 0.0)
    # Cotes fractales : bruit deforme (golfes, peninsules, iles).
    warp = np.stack([fbm(n_warp, p, 2.2, 3), fbm(n_warp, p + 3.7, 2.2, 3), fbm(n_warp, p - 5.1, 2.2, 3)], axis=-1)
    pw = p + 0.28 * warp
    elev += 0.34 * fbm(n_shape, pw, 2.4, 6) + 0.12 * fbm(n_detail, pw, 9.0, 4)
    # Plus de relief a l'interieur des terres que sur les plaines cotieres.
    elev += uplift + islands
    elev += 0.10 * np.where(elev > 0.1, rough - 0.5, 0.0)
    return elev, rough, uplift + 0.45 * islands


def _sea_level(elev, lat, share):
    temperate = np.abs(lat) < math.radians(66)
    return float(np.quantile(elev[temperate], 1.0 - share))


def _sweep(rise, land, from_west: bool) -> np.ndarray:
    """Un vent qui fait le tour de la planete sur chaque rangee : l'air se
    charge sur l'ocean, se vide sur les terres, surtout en montant, et se
    melange avec les rangees voisines."""
    height, width = rise.shape
    order = list(range(width)) if from_west else list(range(width - 1, -1, -1))
    rain = np.zeros_like(rise)
    air = np.ones(height)
    prev = rise[:, order[-1]]
    for lap in range(2):
        for col in order:
            here = rise[:, col]
            wet = ~land[:, col]
            uphill = np.maximum(0.0, here - prev)
            fall = np.minimum(air * (0.009 + 1.8 * uphill), air)
            if lap == 1:
                rain[:, col] = np.where(wet, air, fall * 9.0 + air * 0.25)
            air = np.where(wet, np.minimum(1.0, air + 0.08), air - fall)
            air[1:-1] = 0.5 * air[1:-1] + 0.25 * (air[:-2] + air[2:])
            prev = here
    return rain


def _moisture(elev, sea, lat, noise, p):
    """Pluie portee par les vents : alizes (d'est) pres de l'equateur,
    vents d'ouest aux latitudes moyennes, d'est pres des poles. Les deux
    regimes sont calcules partout puis fondus selon la latitude (pas de
    cassure a 30 ou 60 degres)."""
    alat = np.degrees(np.abs(lat[:, 0]))
    land = elev > sea
    rise = np.maximum(0.0, elev - sea)
    westerly = np.clip(1.0 - np.abs(alat - 45.0) / 22.0, 0.0, 1.0)
    westerly = westerly * westerly * (3.0 - 2.0 * westerly)
    rain = westerly[:, None] * _sweep(rise, land, True) + (1.0 - westerly[:, None]) * _sweep(
        rise, land, False
    )
    # Ceinture equatoriale humide, deserts subtropicaux, latitudes moyennes humides.
    band = (
        0.75
        + 0.55 * np.exp(-((alat / 11.0) ** 2))
        - 0.55 * np.exp(-(((alat - 26.0) / 8.0) ** 2))
        + 0.25 * np.exp(-(((alat - 55.0) / 11.0) ** 2))
    )
    rain *= band[:, None]
    # Pluie de convection, independante de la mer : orages des tropiques
    # (forets humides jusqu'au coeur des continents) et fronts des
    # latitudes moyennes.
    convection = 0.5 * np.exp(-((alat / 14.0) ** 2)) + 0.14 * np.exp(-(((alat - 50.0) / 12.0) ** 2))
    rain += np.where(land, convection[:, None], 0.0)
    # Chaque rangee a ete balayee seule : on lisse entre rangees (et un peu
    # en longitude) pour effacer les rayures, puis on ajoute du bruit.
    rain = _blur(rain, rows=14, cols=3)
    rain *= 1.0 + 0.45 * fbm(noise, p, 3.0, 4)
    return np.clip(rain, 0.0, None)


def _blur(a: np.ndarray, rows: int, cols: int) -> np.ndarray:
    for _ in range(rows):
        up = np.vstack([a[:1], a[:-1]])
        down = np.vstack([a[1:], a[-1:]])
        a = (up + a + down) / 3.0
    for _ in range(cols):
        a = (np.roll(a, 1, axis=1) + a + np.roll(a, -1, axis=1)) / 3.0
    return a


def _drainage(elev, sea, rain, width, height):
    """Remplit les cuvettes (lacs), puis fait couler l'eau vers la mer.
    Renvoie le debit de chaque case et le masque des lacs."""
    land = elev > sea
    filled = np.where(land, np.inf, elev)
    nbs = _hex_neighbors(width, height)
    # Remplissage par priorite depuis la mer (Barnes et al.).
    heap: list[tuple[float, int]] = []
    ocean = ~land
    border = np.zeros_like(land)
    for nr, nc, ok in nbs:
        border |= land & ok & ocean[nr, nc]
    border |= land & ((np.arange(height)[:, None] == 0) | (np.arange(height)[:, None] == height - 1))
    rows, cols = np.nonzero(border)
    for r, c in zip(rows.tolist(), cols.tolist()):
        filled[r, c] = elev[r, c]
        heapq.heappush(heap, (float(elev[r, c]), r * width + c))
    done = ~land | border
    receiver = np.full(height * width, -1, dtype=np.int64)
    order: list[int] = []
    deltas = [(nr, nc, ok) for nr, nc, ok in nbs]
    elev_flat = elev.ravel()
    filled_flat = filled.ravel()
    done_flat = done.ravel()
    nr_flat = [d[0].ravel() for d in deltas]
    nc_flat = [d[1].ravel() for d in deltas]
    ok_flat = [d[2].ravel() for d in deltas]
    while heap:
        level, cell = heapq.heappop(heap)
        order.append(cell)
        for k in range(6):
            if not ok_flat[k][cell]:
                continue
            nb = int(nr_flat[k][cell]) * width + int(nc_flat[k][cell])
            if done_flat[nb]:
                continue
            done_flat[nb] = True
            h = max(float(elev_flat[nb]), level + 1e-6)
            filled_flat[nb] = h
            receiver[nb] = cell
            heapq.heappush(heap, (h, nb))
    filled = filled_flat.reshape(height, width)
    lake = land & (filled - elev > 0.035)
    # Debit : chaque case envoie sa pluie a son receveur (vers la mer).
    flow = np.where(land, rain, 0.0).ravel().copy()
    for cell in reversed(order):
        to = receiver[cell]
        if to >= 0:
            flow[to] += flow[cell]
    return flow.reshape(height, width), lake, receiver


def _biomes(elev, sea, lat, rain, flow, lake, rough, uplift, noise, p, rivers=None):
    height, width = elev.shape
    alat = np.abs(lat) / (math.pi / 2.0)
    land = elev > sea
    # Altitude au-dessus de la mer, a echelle fixe (pas relative au point
    # culminant : sinon une planete sans grande chaine se couvre de collines).
    hgt = np.clip((elev - sea) / 0.9, 0.0, 1.0)
    temp = 1.0 - alat ** 1.35 - 0.55 * hgt + 0.07 * fbm(noise, p, 4.0, 3)
    mid = np.quantile(rain[land], 0.5) if land.any() else 1.0
    wet = rain / max(1e-6, mid)
    grid = np.full((height, width), "E", dtype="<U1")
    g = grid
    g[land] = "P"
    g[land & (wet < 0.62)] = "S"
    g[land & (wet < 0.33) & (temp > 0.52)] = "D"
    g[land & (wet > 1.25) & (temp > 0.2)] = "F"
    if rivers is None:
        # L'ancienne carte (sans les sols de 0.20).
        g[land & (temp < 0.2) & (wet >= 0.8)] = "F"
        g[land & (temp < 0.2) & (wet < 0.8)] = "S"
    else:
        # 0.20 : la temperature des sols depend moins de l'altitude (les
        # terres sont hautes : sinon la toundra couvre les plateaux) ; elle
        # sert aussi aux ressources (climate["temp"]).
        temp = 1.0 - alat ** 1.35 - 0.3 * np.clip(hgt - 0.45, 0.0, None) + 0.07 * fbm(noise, p, 4.0, 3)
        g[land] = "P"
        g[land & (wet < 0.62)] = "S"
        g[land & (wet < 0.33) & (temp > 0.52)] = "D"
        g[land & (wet > 1.25) & (temp > 0.2)] = "F"
        # Les tropiques : la savane (saison seche), la jungle (pluies toute
        # l'annee), avec un bord irregulier.
        edge = 0.04 * fbm(noise, p * 1.3 + 2.0, 6.0, 3)
        hot = land & (temp + edge > 0.76)
        # La jungle : les plus humides des tropiques chauds (la ceinture des
        # pluies) ; la savane : le reste, sauf le desert.
        rainy = np.quantile(wet[hot], 0.62) if hot.any() else 1.5
        g[hot & (wet >= 0.33)] = "A"
        g[hot & (temp + edge > 0.84) & (wet >= max(1.3, rainy))] = "J"
        # Le grand nord : la taiga (foret) la ou il pleut, la toundra
        # au-dela, jusqu'aux calottes.
        north = temp + edge < 0.3
        g[land & north & (wet >= 0.8) & (temp + edge >= 0.2)] = "F"
        g[land & north & ~((wet >= 0.8) & (temp + edge >= 0.2))] = "T"
    # Relief : les chaines suivent les collisions de plaques (soulevement),
    # avec des collines au pied ; sommets rares et morceles (des cols
    # restent franchissables en montagne).
    upland = np.quantile(elev[land], 0.88) if land.any() else sea
    g[land & ((uplift > 0.2) | ((elev > upland) & (rough > 0.55)))] = "C"
    g[land & (uplift > 0.3)] = "M"
    g[land & (uplift > 0.62) & (rough > 0.68)] = "X"
    lowland = land & (hgt < 0.45)
    if rivers is None:
        # Rivieres : les plus gros debits creusent des vallees ; en plaine,
        # les grands fleuves s'elargissent (plaines alluviales).
        river = lowland & (flow > np.quantile(flow[land], 0.94))
        big = lowland & (flow > np.quantile(flow[land], 0.985)) & (hgt < 0.25)
        wide = big.copy()
        for nr, nc, ok in _hex_neighbors(width, height):
            wide |= ok & big[nr, nc] & lowland
        g[river | wide] = "V"
        g[lake] = "E"
        return g, temp
    # Les rivieres de 0.20 (_rivers) : une riviere ou un fleuve creuse sa
    # vallee dans les basses terres ; les fleuves s'elargissent en plaines
    # alluviales ; un ruisseau garde le sol qu'il traverse.
    size = rivers >> 3
    # Les terres sont hautes : "basses" et "plates" se mesurent par rapport
    # aux terres de la planete (quantiles), pas en absolu.
    q_low = np.quantile(hgt[land], 0.55) if land.any() else 0.45
    q_plain = np.quantile(hgt[land], 0.35) if land.any() else 0.25
    q_flat = np.quantile(hgt[land], 0.09) if land.any() else 0.07
    hard = np.isin(g, ("M", "X", "C", "J", "T"))
    # Une riviere ou un fleuve creuse sa vallee (meme au desert : les oasis
    # des grands fleuves) ; sa vallee borde ses deux rives dans les basses
    # terres ; un fleuve s'etale sur deux rangs de chaque cote en plaine.
    course = (size >= 2) & ~np.isin(g, ("M", "X"))
    banks = np.zeros_like(land)
    for nr, nc, ok in _hex_neighbors(width, height):
        banks |= ok & (size[nr, nc] >= 2)
    banks &= land & (hgt < q_low) & ~np.isin(g, ("M", "X", "T"))
    wide = (size >= 3) & (hgt < q_plain)
    for _ in range(2):
        grown = wide.copy()
        for nr, nc, ok in _hex_neighbors(width, height):
            grown |= ok & wide[nr, nc] & land & (hgt < q_plain) & ~hard
        wide = grown
    # Un ruisseau de plaine a aussi son fond de vallee.
    brook = (size == 1) & (hgt < q_plain) & ~hard
    g[(course | banks | wide | brook) & land & ~lake] = "V"
    # Les MARAIS : les plats humides au bord de l'eau, et les deltas.
    flat = land & (hgt < q_flat)
    near_water = lake | (rivers > 0)
    for _ in range(2):
        grown = near_water.copy()
        for nr, nc, ok in _hex_neighbors(width, height):
            grown |= ok & near_water[nr, nc]
        near_water = grown
    blotch = fbm(noise, p * 1.7 + 5.0, 9.0, 3) > -0.05
    marsh = flat & near_water & (wet > 0.9) & blotch & (temp > 0.2)
    delta = flat & (size >= 3)
    for nr, nc, ok in _hex_neighbors(width, height):
        delta |= ok & (size[nr, nc] >= 3) & flat & blotch
    g[(marsh | delta) & ~np.isin(g, ("M", "X", "C"))] = "Z"
    g[lake] = "E"
    return g, temp


def _rivers(flow, lake, receiver, land, width, height, hgt=None):
    """La couche des rivieres (octets, rangee par rangee) : pour une case de
    riviere, (sens + 1) | (taille << 3) ; le sens est l'indice de la case en
    aval dans world.NEIGHBOR_DELTAS, la taille 1 ruisseau, 2 riviere,
    3 fleuve. Le debit grandit vers l'aval : les rivieres vont toujours
    jusqu'a la mer ou un lac."""
    out = np.zeros(height * width, dtype=np.uint8)
    on_land = land & ~lake
    ref = flow[on_land]
    if not ref.size:
        return out.reshape(height, width)
    t1 = np.quantile(ref, 1.0 - RIVER_SHARE)
    t2 = np.quantile(ref, 1.0 - RIVER_MID_SHARE)
    t3 = np.quantile(ref, 1.0 - RIVER_BIG_SHARE)
    nbs = _hex_neighbors(width, height)
    nr_flat = [d[0].ravel() for d in nbs]
    nc_flat = [d[1].ravel() for d in nbs]
    ok_flat = [d[2].ravel() for d in nbs]
    flow_f = flow.ravel()
    river = (on_land & (flow > t1)).ravel()
    for cell in np.nonzero(river)[0].tolist():
        to = int(receiver[cell])
        if to < 0:
            continue
        for k in range(6):
            if ok_flat[k][cell] and int(nr_flat[k][cell]) * width + int(nc_flat[k][cell]) == to:
                f = flow_f[cell]
                size = 3 if f > t3 else 2 if f > t2 else 1
                out[cell] = (k + 1) | (size << 3)
                break
    return out.reshape(height, width)


def _polar(grid, lat, noise, p, ice: str = "X"):
    # Calottes : les terres gelent plus tot que la mer, bords dechiquetes.
    # ice : "X" (l'ancienne carte : des sommets), "G" (0.20 : la glace).
    alat = np.abs(lat) / (math.pi / 2.0)
    wobble = fbm(noise, p, 3.0, 5)
    land_edge = (0.8 if ice == "X" else 0.85) + 0.12 * wobble
    sea_edge = 0.91 + 0.09 * wobble
    grid[(alat > land_edge) & (grid != "E")] = ice
    grid[(alat > sea_edge) & (grid == "E")] = ice
    grid[alat > 0.985] = ice


def _coasts(grid, width, height):
    water = grid == "E"
    touch = np.zeros_like(water)
    for nr, nc, ok in _hex_neighbors(width, height):
        touch |= ok & water[nr, nc]
    # Les embouchures restent des vallees (deltas fertiles).
    coast = touch & ~water & ~np.isin(grid, ("M", "X", "V", "G", "Z"))
    grid[coast] = "O"


def _generate(seed: int, width: int, height: int, v2: bool = True):
    """v2 (0.20) : rivieres, glace, toundra, savane, jungle, marais ; sinon
    l'ancienne carte (les tests du generateur d'origine)."""
    rng = np.random.default_rng(seed)
    p, lat = sphere_points(width, height)
    noises = [Noise3(rng) for _ in range(8)]
    plates = _plates(rng, p, noises[0], noises[1])
    elev, rough, uplift = _elevation(rng, p, lat, plates, noises[2:6])
    sea = _sea_level(elev, lat, LAND_SHARE if v2 else 0.32)
    rain = _moisture(elev, sea, lat, noises[6], p)
    # L'eau coule sur un relief legerement bruite : sur les plats, les
    # rivieres serpentent au lieu de filer en lignes droites paralleles.
    flow, lake, receiver = _drainage(elev + 0.03 * fbm(noises[6], p, 14.0, 3), sea, rain, width, height)
    land = elev > sea
    rivers = _rivers(flow, lake, receiver, land, width, height) if v2 else None
    grid, temp = _biomes(elev, sea, lat, rain, flow, lake, rough, uplift, noises[7], p, rivers)
    _polar(grid, lat, noises[7], p * 1.7, "G" if v2 else "X")
    _coasts(grid, width, height)
    if rivers is not None:
        # Pas de riviere sur la glace, les sommets, l'eau.
        rivers[np.isin(grid, ("G", "X", "E"))] = 0
    mid = np.quantile(rain[land], 0.5) if land.any() else 1.0
    hgt = np.clip((elev - sea) / 0.9, 0.0, 1.0)
    climate = {
        "temp": temp, "wet": rain / max(1e-6, mid), "flow": flow, "p": p, "lat": lat,
        "rivers": rivers, "hgt": hgt, "uplift": uplift, "rough": rough, "lake": lake,
    }
    return grid, climate


def generate_world(seed: int = 42, width: int = PLANET_WIDTH, height: int = PLANET_HEIGHT, resources: bool = False, v2: bool = True):
    grid, climate = _generate(seed, width, height, v2)
    terrains = [[CHAR_TO_TERRAIN[ch] for ch in row] for row in grid.tolist()]
    world = World(terrains, wrap_x=True)
    if climate.get("rivers") is not None:
        world.set_rivers(climate["rivers"].astype(np.uint8).tobytes())
    if resources:
        layers = generate_layers_v2(seed, grid, climate) if v2 else generate_layers(seed, grid, climate)
        world.set_resources(layers)
    return world


def bake(seed: int = 42, path=None, width: int = PLANET_WIDTH, height: int = PLANET_HEIGHT):
    """Recuire la carte du jeu : generation, ressources du pays, noms de
    l'atlas, dans data/kora_map.json. Usage : python -m src.kora.mapgen [graine]"""
    from pathlib import Path

    world = generate_world(seed, width, height, resources=True)
    if path is None:
        path = Path(__file__).resolve().parents[2] / "data" / "kora_map.json"
    save_world(world, Path(path), build_atlas_labels(world))
    return world


# --- mesures (tests, atlas) --------------------------------------------------


def _is_polar_cap(world, col: int, row: int) -> bool:
    if world.height <= 1:
        return False
    if world._terrains[row][col] is Terrain.GLACE:
        return True
    lat = abs((row / (world.height - 1)) * 2.0 - 1.0)
    return lat > 0.80 and world._terrains[row][col] is Terrain.SOMMET


def continent_sizes(world) -> list[int]:
    visited = [[False] * world.width for _ in range(world.height)]
    sizes: list[int] = []
    for row in range(world.height):
        for col in range(world.width):
            if visited[row][col] or world._terrains[row][col] is Terrain.EAU:
                continue
            if _is_polar_cap(world, col, row):
                visited[row][col] = True
                continue
            stack = [(col, row)]
            visited[row][col] = True
            count = 0
            while stack:
                c, r = stack.pop()
                count += 1
                for nb in world.neighbors(offset_to_axial(c, r)):
                    nc, nr = axial_to_offset(nb)
                    if visited[nr][nc] or world._terrains[nr][nc] is Terrain.EAU:
                        continue
                    if _is_polar_cap(world, nc, nr):
                        visited[nr][nc] = True
                        continue
                    visited[nr][nc] = True
                    stack.append((nc, nr))
            sizes.append(count)
    sizes.sort(reverse=True)
    return sizes


if __name__ == "__main__":
    import sys

    bake(int(sys.argv[1]) if len(sys.argv) > 1 else 42)


# --- les ressources du pays (cuisson) ----------------------------------------------


def generate_layers(seed: int, grid, climate) -> dict:
    """Couches 0..255 (octets, rangee par rangee) pour chaque ressource."""
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
    for name in BAKED:
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


# --- les ressources des nouvelles planetes (0.20) ------------------------------------
#
# Les ETRES VIVANTS vivent dans des AIRES : le climat et les sols disent ou
# ils peuvent vivre, deux bruits (un large, un fin) decoupent des aires de
# tailles variees, avec des trous ; chaque ressource couvre COVER des terres.
# Les MATIERES sont des GISEMENTS : DEPOSITS[nom] = (nombre pour une planete
# de 1536 x 768, rayon le plus grand) ; chaque gisement a un coeur riche qui
# s'appauvrit vers ses bords (1 a 4 cases) ; ils se posent la ou la geologie
# les veut (poids), jamais trop pres l'un de l'autre.

DEPOSITS = {
    "silex": (1200, 3),
    "argile": (2200, 2),
    "sel": (520, 2),
    "ocre": (520, 2),
    "obsidienne": (170, 2),
    "ambre": (190, 2),
    "cuivre": (420, 2),
    "etain": (120, 1),
    "argent": (650, 2),
}
# La part des cases d'eau ou de rive qui portent du poisson.
FISH_COVER = 0.6
LIVING = ("cereales", "racines", "fruits", "miel", "bois", "aurochs", "chevaux", "chevres", "rennes", "poisson")


def _offsets(radius: int):
    """Les cases d'un disque hexagonal en (dcol, drow) selon la parite de la
    rangee du centre (rangees decalees : world.offset_to_axial)."""
    out = {0: [], 1: []}
    for parity in (0, 1):
        for dq in range(-radius, radius + 1):
            for dr in range(-radius, radius + 1):
                d = (abs(dq) + abs(dq + dr) + abs(dr)) // 2
                if d > radius:
                    continue
                row = parity + dr
                dcol = dq + (row - (row & 1)) // 2 - (parity - (parity & 1)) // 2
                out[parity].append((dcol, dr, d))
    return out


def generate_layers_v2(seed: int, grid, climate) -> dict:
    """Couches 0..255 (octets, rangee par rangee) des 19 ressources."""
    rng = np.random.default_rng(seed + 7919)
    p = climate["p"]
    temp = climate["temp"]
    wet = climate["wet"]
    rivers = climate["rivers"]
    hgt = climate["hgt"]
    uplift = climate["uplift"]
    height, width = grid.shape
    scale = (width * height) / (1536 * 768)
    terr = {ch: (grid == ch).astype(np.float64) for ch in "PVSFCMXEODTGZJA"}
    land = ~np.isin(grid, ("E", "G", "X"))
    water = grid == "E"
    shore = np.zeros_like(water)
    for nr, nc, ok in _hex_neighbors(width, height):
        shore |= ok & land[nr, nc]
    inshore = (water & shore).astype(np.float64)
    size = (rivers >> 3).astype(np.float64)
    river = np.clip(size / 3.0, 0.0, 1.0)
    riverside = np.zeros_like(land)
    for nr, nc, ok in _hex_neighbors(width, height):
        riverside |= ok & (rivers[nr, nc] > 0)
    riverside = (riverside | (rivers > 0)) & land

    def areas(big: float, fine: float, cover: float):
        """Des aires de tailles variees : un bruit large, perce par un fin."""
        a = fbm(Noise3(rng), p, big, 4)
        b = fbm(Noise3(rng), p, fine, 3)
        n = a + 0.55 * b
        ref = n[land] if land.any() else n.ravel()
        lo = np.quantile(ref, 1.0 - cover)
        hi = np.quantile(ref, 0.99)
        v = np.clip((n - lo) / max(1e-6, hi - lo), 0.0, 1.0)
        return v * v * (3.0 - 2.0 * v)

    def band(x, lo: float, hi: float, soft: float = 0.12):
        return np.clip(np.minimum((x - lo) / soft + 1.0, (hi - x) / soft + 1.0), 0.0, 1.0)

    def suit(weights: dict):
        out = np.zeros((height, width))
        for ch, w in weights.items():
            out += w * terr[ch]
        return out

    living = {
        "cereales": suit({"V": 1.0, "P": 0.8, "A": 0.55, "S": 0.35, "C": 0.25, "O": 0.25, "F": 0.1})
        * band(temp, 0.45, 0.82) * band(wet, 0.4, 1.3, 0.3) * areas(2.5, 9.0, 0.5),
        "racines": suit({"F": 1.0, "J": 0.8, "V": 0.8, "Z": 0.7, "P": 0.4, "O": 0.3})
        * band(temp, 0.6, 1.3) * band(wet, 0.85, 5.0, 0.3) * areas(3.0, 10.0, 0.5),
        "fruits": suit({"J": 1.0, "F": 0.7, "V": 0.5, "A": 0.4, "P": 0.3})
        * band(temp, 0.55, 1.4) * band(wet, 0.7, 5.0, 0.3) * areas(3.5, 12.0, 0.45),
        "miel": suit({"F": 0.9, "P": 0.7, "A": 0.6, "J": 0.5, "V": 0.6, "C": 0.4})
        * band(temp, 0.45, 1.2) * areas(4.0, 14.0, 0.35),
        "bois": suit({"F": 1.0, "J": 0.7, "V": 0.3, "Z": 0.2, "T": 0.1})
        * band(temp, 0.25, 0.9) * areas(2.2, 7.0, 0.6),
        "aurochs": suit({"P": 1.0, "V": 0.8, "F": 0.55, "A": 0.75, "S": 0.35})
        * band(temp, 0.35, 0.95) * areas(2.2, 7.0, 0.55),
        "chevaux": suit({"S": 1.0, "P": 0.55, "A": 0.35, "D": 0.2}) * band(temp, 0.25, 0.75) * areas(2.0, 6.0, 0.6),
        "chevres": suit({"C": 1.0, "M": 0.9, "D": 0.2, "S": 0.2}) * band(temp, 0.2, 0.95) * areas(3.0, 9.0, 0.6),
        "rennes": suit({"T": 1.0, "F": 0.6, "S": 0.5, "C": 0.5}) * band(temp, -1.0, 0.36) * areas(2.0, 6.0, 0.75),
        "poisson": (terr["O"] + river * riverside + 0.8 * terr["Z"] + inshore) * (0.5 + 0.5 * areas(3.0, 10.0, 0.7)),
    }
    out = {}
    for name in LIVING:
        raw = np.clip(living[name], 0.0, None)
        ref = raw[land]
        cover = COVER.get(name, 0.08)
        if name == "poisson":
            # Le poisson ne vit que pres de l'eau (rives, rivieres, marais,
            # eaux cotieres) : sa part se compte sur ces cases-la.
            ref = raw[raw > 0]
            cover = FISH_COVER
        q = float(np.quantile(ref, 1.0 - cover)) if ref.size else 0.0
        if q <= 1e-6:
            q = float(ref.max()) * 0.5 if ref.size and ref.max() > 0 else 1.0
        v = np.clip(raw * (PRESENT / q), 0.0, 1.0)
        out[name] = (v * 255.0 + 0.5).astype(np.uint8).tobytes()

    # --- les gisements ---
    coastal = (terr["O"] > 0) | shore
    weights = {
        "silex": suit({"C": 1.0, "P": 0.5, "V": 0.35, "S": 0.35, "A": 0.3, "D": 0.3, "T": 0.2}),
        "argile": riverside * 1.0 + 0.6 * terr["Z"] + 0.3 * terr["V"] + 0.15 * suit({"P": 1.0, "O": 1.0}),
        "sel": (terr["O"] * band(wet, 0.0, 0.75, 0.2) + 0.9 * terr["D"] + 0.25 * terr["C"] + 0.2 * terr["S"]),
        "ocre": suit({"C": 1.0, "D": 0.7, "A": 0.6, "S": 0.4, "M": 0.3}) * band(temp, 0.4, 1.4),
        "obsidienne": (land & (uplift > 0.22)) * (0.4 + hgt) + 0.4 * (land & (hgt > 0.3) & (temp > 0.3)),
        "ambre": coastal * land * band(temp, 0.28, 0.6) + 0.4 * terr["F"] * band(temp, 0.3, 0.55),
        "cuivre": suit({"C": 1.0, "M": 0.8, "D": 0.4, "S": 0.15}),
        "etain": suit({"C": 0.6, "M": 1.0}) * (hgt > 0.2),
        "argent": suit({"M": 1.0, "C": 0.6}) * (0.5 + hgt),
    }
    discs = {r: _offsets(r) for r in range(0, 5)}
    for name, (count, rmax) in DEPOSITS.items():
        layer = np.zeros(height * width, dtype=np.float64)
        w = np.asarray(weights[name], dtype=np.float64).ravel() * land.ravel()
        total = w.sum()
        n = max(4, int(round(count * scale)))
        if total <= 0:
            out[name] = layer.astype(np.uint8).tobytes()
            continue
        # Un tirage pondere, puis un ecart minimal (une grille grossiere).
        picks = rng.choice(w.size, size=n * 3, replace=True, p=w / total)
        cell = max(3, int(round(math.sqrt(land.sum() / max(1, n)) * 0.55)))
        taken: set = set()
        placed = 0
        for idx in picks.tolist():
            row, col = divmod(idx, width)
            key = (row // cell, col // cell)
            if key in taken:
                continue
            taken.add(key)
            placed += 1
            r = int(rng.choice(np.arange(rmax + 1), p=_radius_weights(rmax)))
            rich = float(rng.uniform(0.5, 1.0))
            for dcol, drow, d in discs[r][row & 1]:
                rr = row + drow
                if rr < 0 or rr >= height:
                    continue
                cc = (col + dcol) % width
                if not land[rr, cc]:
                    continue
                v = rich * (1.0 - 0.55 * d / (r + 1))
                i = rr * width + cc
                if v > layer[i]:
                    layer[i] = v
            if placed >= n:
                break
        out[name] = (np.clip(layer, 0.0, 1.0) * 255.0 + 0.5).astype(np.uint8).tobytes()
    assert set(out) == set(BAKED_V2), sorted(set(BAKED_V2) ^ set(out))
    assert all(KINDS[k] == "matiere" for k in DEPOSITS)
    return out


def _radius_weights(rmax: int):
    """Les petits gisements sont les plus nombreux."""
    w = np.array([1.0 / (1 + r) ** 1.3 for r in range(rmax + 1)])
    return w / w.sum()
