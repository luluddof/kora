"""LES POINTS ET LA MARCHE (le monde sans grille, 0.28.0 ; sa demande du
2026-11-13 : "supprimer la grille dans le code, en gardant le fait que selon
le terrain, et meme sur un meme terrain, la proximite et donc l'influence
peuvent varier").

Une unite est a un POINT, n'importe ou : (fu, fv) en entiers FINS (FINE par
largeur de case ; le meme calcul sur chaque machine : le multijoueur,
l'empreinte). Le plan : u = 2 x colonne (+1 sur les rangees impaires), v =
rangee ; la vraie longueur entre deux points est racine((du^2 + 3 dv^2) / 4).
La case n'est plus qu'un RELEVE du monde sous le point (le sol, son cout de
marche et sa variation locale world.cost_pct, la nourriture) : cell_of.

LA MARCHE (march) : chaque semaine, l'unite avance le long de son chemin
(les centres des lieux du chemin, puis le point vise) d'autant que le sol
le permet : chaque bout de chemin coute le sol ou il passe (et le courant
d'une riviere a la traversee), a proportion de sa longueur. Elle s'arrete
ou son elan s'arrete, entre deux lieux ; plus d'elan perdu.
LE CHEMIN REDRESSE (0.30.0 ; ses mots du 2026-11-09 : "elle glisse en
tenant compte de la proximite, pas forcement en ligne droite") : le chemin
cherche de lieu en lieu fait un escalier ; en marchant, l'unite regarde
LOOK lieux devant elle et va TOUT DROIT vers le plus lointain qu'elle
rejoint sans payer plus qu'en suivant l'escalier (_far) : droit quand ca
ne coute pas plus, sinon elle contourne comme le chemin. route : le trajet
qu'elle fera (le chemin trace a l'ecran) ; `trail`, note sur la bande (pas sauve) : celui
qu'elle vient de faire (le glissement).
LA LIGNE DROITE SE VERIFIE PAR ECHANTILLONS (tous les STEP) ; revue du
2026-11-27 : l'unite ne s'arrete que dans un lieu verifie (_leg), et une
ligne coupee par un coin d'eau se rabat sur les centres du chemin (_relink,
un court A* si l'unite n'y touche plus) avant d'annuler l'ordre. Une unite
restee dans l'eau (une vieille partie) en sort (path.astar part de partout).
weeks_along : la duree d'un trajet, la marche rejouee (path.travel_weeks).
LES RENCONTRES (0.30.0) : deux unites se rencontrent a MEET ou moins l'une
de l'autre (apart), plus "dans le meme lieu" ; crossed : deux unites qui se
sont croisees pendant la semaine (Band.pu, pv : son point au debut de la
marche). NEAR : etre tout pres (rejoindre une bande amie).
LES LIEUX A UN POINT (0.30.0) : un village, un camp, une cache sont au
point ou la bande etait (Site.u, v ; site_point) ; un village est au point
de son lieu.
Band.position reste la case sous le point (les systemes qui lisent le monde
par releves la lisent). point_of : le point d'une unite (le centre de sa
case si rien d'autre ne le dit : une partie d'avant, une unite posee par le
code).
N'importe pas pygame.
"""

from __future__ import annotations

import math

# points et path s'appellent l'un l'autre (la marche coupee cherche un
# detour ; la duree d'un trajet rejoue la marche) : modules entiers.
from src.kora import path as paths
from src.kora.types import Hex
from src.kora.world import axial_to_offset, enter_cost_for, offset_to_axial, step_cost

FINE = 64
# La marche avance par petits pas (un quart de case) : le sol est lu a
# chaque pas.
STEP = FINE // 4
# LES RENCONTRES : deux unites se rencontrent a MEET ou moins (trois quarts
# d'une largeur de lieu) ; tout pres (rejoindre les siens) : NEAR.
MEET = 3 * FINE // 4
NEAR = 5 * FINE // 4
# LE CHEMIN REDRESSE : l'unite regarde LOOK lieux devant elle (cinq
# semaines de marche en plaine : un chemin en "L" se redresse d'un coup).
LOOK = 24


def center(h: Hex) -> tuple[int, int]:
    """Le point au centre d'une case."""
    col, row = axial_to_offset(h)
    return (2 * col + (row & 1)) * FINE, row * FINE


def cell_of(world, u: int, v: int) -> Hex:
    """La case sous un point (le centre le plus proche)."""
    span = 2 * world.width * FINE
    if world.wrap_x:
        u %= span
    r0 = v // FINE
    best = None
    for r in (r0, r0 + 1):
        if r < 0 or r >= world.height:
            continue
        odd = (r & 1) * FINE
        c = (u - odd + FINE) // (2 * FINE)
        du = u - (2 * c * FINE + odd)
        dv = v - r * FINE
        d = du * du + 3 * dv * dv
        if best is None or d < best[0]:
            best = (d, c, r)
    if best is None:
        r = min(max(r0, 0), world.height - 1)
        best = (0, (u + FINE) // (2 * FINE), r)
    _d, c, r = best
    if world.wrap_x:
        c %= world.width
    else:
        c = min(max(c, 0), world.width - 1)
    return offset_to_axial(c, r)


def delta(world, a: tuple[int, int], b: tuple[int, int]) -> tuple[int, int]:
    """b - a, le plus court autour du monde."""
    du = b[0] - a[0]
    if world.wrap_x:
        span = 2 * world.width * FINE
        du = (du + span // 2) % span - span // 2
    return du, b[1] - a[1]


def length(world, a: tuple[int, int], b: tuple[int, int]) -> int:
    """La vraie longueur de a a b, en FINE par largeur de case."""
    du, dv = delta(world, a, b)
    return math.isqrt(du * du + 3 * dv * dv) // 2


def point_of(world, band) -> tuple[int, int]:
    """Le point d'une unite : le sien s'il est sur sa case, sinon le centre
    de sa case (un village est au point de son lieu : villages.found le lui
    donne, persist le lui rend)."""
    fu, fv = band.fu, band.fv
    if fu < 0 or fv < 0:
        return center(band.position)
    # La case sous le point, verifiee une fois (gardee sur l'unite tant que
    # son point et sa case ne changent pas).
    seen = band.__dict__.get("_pt_ok")
    if seen is not None and seen[0] == fu and seen[1] == fv and seen[2] == band.position:
        return fu, fv
    if cell_of(world, fu, fv) == band.position:
        band.__dict__["_pt_ok"] = (fu, fv, band.position)
        return fu, fv
    return center(band.position)


def site_point(site) -> tuple[int, int]:
    """Le point d'un lieu (village, camp, cache) : la ou la bande etait
    quand elle l'a pose ; le centre de sa case pour un lieu d'avant."""
    if site.u >= 0 and site.v >= 0:
        return site.u, site.v
    return center(site.hex)


def where(world, x) -> tuple[int, int]:
    """Le point de n'importe quoi de pose sur le monde : une unite (son
    point), un lieu (village, camp, cache : site_point), une bataille (la ou
    elle se livre), ou une case (son centre)."""
    if isinstance(x, Hex):
        return center(x)
    if hasattr(x, "fu"):
        return point_of(world, x)
    if hasattr(x, "attackers"):
        if getattr(x, "u", -1) >= 0 and getattr(x, "v", -1) >= 0:
            return x.u, x.v
        return center(x.hex)
    if hasattr(x, "kind") and hasattr(x, "u"):
        return site_point(x)
    if getattr(x, "u", -1) >= 0 and getattr(x, "v", -1) >= 0:
        # Une marque de combat : le point de la bataille.
        return x.u, x.v
    if hasattr(x, "hex"):
        # Une ligne du journal, une marque d'avant : leur lieu.
        return center(x.hex)
    return center(x)


def lieux(world, a, b) -> int:
    """LA PROXIMITE ENTRE DEUX CHOSES (le monde sans grille, 0.31.0) : la
    vraie distance de point a point, en lieux (largeurs de case), arrondie ;
    une unite, un lieu, une bataille ou une case (where). Remplace la
    distance de centre de case a centre de case : deux unites dans le meme
    lieu peuvent etre a pres d'un lieu l'une de l'autre, et deux unites de
    part et d'autre d'une limite, cote a cote."""
    return (length(world, where(world, a), where(world, b)) + FINE // 2) // FINE


# La memoire des disques autour d'un point est bornee par le NOMBRE DE LIEUX
# gardes, pas d'entrees (revue du 2026-11-27 : des disques de rayon 16 a
# plusieurs centaines de lieux chacun, 68 Mo en un an avec ceux du monde).
NEAR_CACHE_CELLS = 150000


def cells_near(world, pt: tuple[int, int], radius: int) -> tuple[list, list]:
    """Les lieux dont le centre est a `radius` lieux ou moins du POINT pt (la
    vraie distance, arrondie), et leur distance : le disque autour d'une
    unite ou d'un lieu part de son point, plus du centre de sa case. Listes
    partagees (memoire) : ne pas les modifier."""
    # La memoire est gardee SUR le monde : un autre monde, meme a la meme
    # adresse en memoire, a la sienne (le multijoueur, les essais).
    cache = world.__dict__.get("_near")
    if cache is None:
        cache = world.__dict__["_near"] = {}
        world.__dict__["_near_cells"] = 0
    key = (pt, radius)
    hit = cache.get(key)
    if hit is not None:
        return hit
    base = cell_of(world, pt[0], pt[1])
    around, _d = world.hexes_and_distances(base, radius + 1)
    cells, dists = [], []
    half = FINE // 2
    for h in around:
        k = (length(world, pt, center(h)) + half) // FINE
        if k <= radius:
            cells.append(h)
            dists.append(k)
    kept = world.__dict__.get("_near_cells", 0) + len(cells)
    if kept > NEAR_CACHE_CELLS:
        # On oublie les plus anciens jusqu'aux trois quarts (vider tout d'un
        # coup faisait tout recalculer a la semaine suivante).
        for old in list(cache):
            kept -= len(cache.pop(old)[0])
            if kept <= NEAR_CACHE_CELLS * 3 // 4:
                break
        if not cache:
            kept = len(cells)
    world.__dict__["_near_cells"] = kept
    out = cache[key] = (cells, dists)
    return out


def around(world, x, radius: int) -> list:
    """Les lieux a `radius` lieux ou moins d'une unite, d'un lieu, d'une
    bataille (de son point)."""
    return cells_near(world, where(world, x), radius)[0]


def apart(world, a, b) -> int:
    """La vraie distance entre deux unites, en FINE."""
    return length(world, point_of(world, a), point_of(world, b))


def before(world, band) -> tuple[int, int]:
    """Le point de l'unite au debut de la marche de cette semaine (le sien
    si elle n'a pas marche)."""
    if band.pu >= 0 and band.pv >= 0:
        return band.pu, band.pv
    return point_of(world, band)


def crossed(world, a0, a1, b0, b1, reach: int) -> bool:
    """Deux unites qui ont marche cette semaine de a0 a a1 et de b0 a b1 (en
    meme temps, tout droit) sont-elles passees a `reach` ou moins l'une de
    l'autre ? Des entiers : la meme reponse sur chaque machine."""
    w0 = delta(world, b0, a0)
    w1 = delta(world, b1, a1)
    lim = 4 * reach * reach
    q0 = w0[0] * w0[0] + 3 * w0[1] * w0[1]
    q1 = w1[0] * w1[0] + 3 * w1[1] * w1[1]
    if q0 <= lim or q1 <= lim:
        return True
    du, dv = w1[0] - w0[0], w1[1] - w0[1]
    dd = du * du + 3 * dv * dv
    if dd == 0:
        return False
    dot = w0[0] * du + 3 * w0[1] * dv
    if dot >= 0 or -dot >= dd:
        # Au plus pres a un bout de la semaine : deja regarde.
        return False
    return q0 * dd - dot * dot <= lim * dd


def to_colrow(u: float, v: float) -> tuple[float, float]:
    """Le point en colonne et rangee a virgule (le dessin du globe)."""
    return u / (2.0 * FINE) - 0.25, v / FINE


def from_colrow(col: float, row: float) -> tuple[int, int]:
    """Un point du globe (colonne, rangee a virgule) en point fin."""
    return int(round((col + 0.25) * 2 * FINE)), int(round(row * FINE))


def aim_of(world, band):
    """Le point vise au bout du chemin (s'il est dans la derniere case du
    chemin), sinon None (le centre de la derniere case)."""
    if band.aim_u < 0 or band.aim_v < 0 or not band.path:
        return None
    if cell_of(world, band.aim_u, band.aim_v) != world.canonicalize(band.path[-1]):
        return None
    return band.aim_u, band.aim_v


def _leg(world, cur, cell, stay, target, water_ok, costs, left):
    """Un bout de marche TOUT DROIT de `cur` (dans le lieu `cell`, ou rester
    coute `stay`) vers `target`, le sol lu tous les STEP. left : l'elan qui
    reste (None : on mesure seulement). Rend (cout, point, lieu, stay,
    etat) ; etat : "" (arrive), "coupe" (un lieu infranchissable), "arret"
    (plus d'elan)."""
    du, dv = delta(world, cur, target)
    total = math.isqrt(du * du + 3 * dv * dv) // 2
    n = max(1, -(-total // STEP))
    done = 0
    start = cur
    spent = 0
    for k in range(1, n + 1):
        nu, nv = start[0] + du * k // n, start[1] + dv * k // n
        nxt = cell_of(world, nu, nv)
        if nxt != cell:
            c = step_cost(world, cell, nxt, water_ok, costs)
            if c is None:
                return spent, cur, cell, stay, "coupe"
        else:
            c = stay
        seg = total * k // n - done
        need = c * seg
        if left is not None and need > left - spent:
            # Le reste de l'elan : un bout du pas. On ne s'arrete que dans un
            # lieu deja verifie (le courant ou le suivant) : entre deux
            # echantillons, la ligne peut couper le coin d'un lac ou d'un
            # sommet, et l'unite y finissait sa semaine (revue du
            # 2026-11-27) ; sinon elle reste au dernier echantillon sur.
            rest = left - spent
            if need > 0 and rest > 0:
                stop = (cur[0] + (nu - cur[0]) * rest // need, cur[1] + (nv - cur[1]) * rest // need)
                landed = cell_of(world, stop[0], stop[1])
                if landed == cell or landed == nxt:
                    cur, cell = stop, landed
            return left, cur, cell, stay, "arret"
        spent += need
        done += seg
        cur = (nu, nv)
        if nxt != cell:
            cell, stay = nxt, c
    return spent, (start[0] + du, start[1] + dv), cell, stay, ""


def _far(world, cur, cell, stay, corners, i: int, water_ok, costs) -> int:
    """LE CHEMIN REDRESSE : parmi les LOOK prochains coins du chemin, le
    plus lointain qu'on rejoint tout droit sans payer plus qu'en suivant le
    chemin (i : rien a redresser)."""
    last = min(len(corners), i + LOOK)
    if last - i <= 1:
        return i
    along = []
    p, c, s, total = cur, cell, stay, 0
    for j in range(i, last):
        spent, _p, c, s, state = _leg(world, p, c, s, corners[j], water_ok, costs, None)
        if state:
            break
        total += spent
        along.append(total)
        p = corners[j]
    # Du plus loin au plus pres, a grands pas (le plus loin, les trois
    # quarts, la moitie, le quart, puis les deux prochains coins) : six
    # lignes droites au plus par decision.
    n = len(along)
    tried = set()
    for k in (n - 1, 3 * n // 4, n // 2, n // 4, 2, 1):
        if k <= 0 or k >= n or k in tried:
            continue
        tried.add(k)
        spent, _p, _c, _s, state = _leg(world, cur, cell, stay, corners[i + k], water_ok, costs, None)
        if not state and spent <= along[k]:
            return i + k
    return i


def _relink(world, path, cell, i: int, water_ok, costs):
    """Le repli d'une marche coupee : le chemin de lieu en lieu depuis le
    lieu de l'unite (`cell`) : path[i:] s'il part de son lieu ou d'un voisin,
    sinon un court chemin (A*) jusqu'a path[i], puis la suite. None : rien
    ne passe (le chemin est vraiment coupe)."""
    rest = list(path[i:])
    if not rest:
        return None
    first = world.canonicalize(rest[0]) or rest[0]
    if first == cell or first in world.neighbors(cell):
        return rest
    max_cost, max_nodes = paths.search_limits(world.distance(cell, first))
    link = paths.astar(world, cell, first, max_cost=max_cost, max_nodes=max_nodes, water_ok=water_ok, costs=costs)
    if not link:
        return None
    return link + rest[1:]


def _corners(world, band) -> list:
    corners = [center(h) for h in band.path]
    aim = aim_of(world, band)
    if aim is not None:
        corners[-1] = aim
    return corners


def route(world, band, water_ok: bool, costs) -> list:
    """Le trajet que l'unite fera (des points fins) : de son point, tout
    droit de coin en coin (le chemin redresse), jusqu'au bout du chemin."""
    cur = point_of(world, band)
    out = [cur]
    if not band.path:
        return out
    cell = world.canonicalize(band.position) or band.position
    stay = enter_cost_for(world, cell, water_ok, costs) or 10
    corners = _corners(world, band)
    i = 0
    while i < len(corners):
        j = _far(world, cur, cell, stay, corners, i, water_ok, costs)
        was = cell
        _spent, cur, cell, stay, state = _leg(world, cur, cell, stay, corners[j], water_ok, costs, None)
        if state == "coupe":
            # La marche s'y rabat sur les centres du chemin (march) : le
            # trace aussi.
            out.append(center(was))
            out.extend(corners[i:])
            break
        out.append(cur)
        if state:
            break
        i = j + 1
    return out


def march(world, band, budget: int, water_ok: bool, costs) -> bool:
    """Une semaine de marche avec `budget` points (MOVE_POINTS_PER_WEEK).
    Rend True si le chemin est coupe (un lieu infranchissable)."""
    if not band.path:
        return False
    cur = point_of(world, band)
    cell = world.canonicalize(band.position) or band.position
    stay = enter_cost_for(world, cell, water_ok, costs) or 10
    corners = _corners(world, band)
    left = budget * FINE
    trail = [cur]
    i = 0
    cut = False
    # Le repli de la semaine : de centre en centre, sans redresser.
    stairs = False
    while i < len(corners) and left > 0:
        # Tout droit vers le coin le plus lointain qui ne coute pas plus.
        j = i if stairs else _far(world, cur, cell, stay, corners, i, water_ok, costs)
        out = _leg(world, cur, cell, stay, corners[j], water_ok, costs, left)
        if out[4] == "coupe" and not stairs:
            # Les echantillons d'une ligne droite tombent ailleurs d'une
            # semaine a l'autre : le coin d'un lac evite la semaine d'avant
            # coupe celle-ci, et un chemin valide etait annule (revue du
            # 2026-11-27). On se rabat sur les CENTRES du chemin (rejoint
            # depuis son lieu s'il n'y touche pas) avant de l'annuler.
            stairs_path = _relink(world, band.path, cell, i, water_ok, costs)
            if stairs_path is not None:
                band.path = stairs_path
                corners = _corners(world, band)
                i = 0
                stairs = True
                # D'abord au centre de son lieu : tout droit dans son lieu,
                # rien a couper ; de la, de centre en centre (deux lieux
                # voisins : la ligne ne passe que par eux).
                spent, cur, cell, stay, state = _leg(world, cur, cell, stay, center(cell), water_ok, costs, left)
                left -= spent
                trail.append(cur)
                if state:
                    break
                continue
        spent, cur, cell, stay, state = out
        left -= spent
        trail.append(cur)
        if state == "coupe":
            cut = True
            break
        if state == "arret":
            # Les coins d'avant sont passes au large : le chemin reprend la.
            i = j
            break
        i = j + 1
    if world.wrap_x:
        cur = (cur[0] % (2 * world.width * FINE), cur[1])
    band.fu, band.fv = cur
    band.position = cell
    # Le trajet fait cette semaine (le glissement a l'ecran ; pas sauve).
    band.__dict__["trail"] = trail
    if cut:
        band.path = []
    else:
        band.path = band.path[i:]
    if not band.path:
        band.aim_u = band.aim_v = -1
    return cut


class _Walker:
    """Une unite fictive qui rejoue une marche (weeks_along)."""

    def __init__(self, position, path, point, aim):
        self.position = position
        self.path = list(path)
        self.fu, self.fv = point if point is not None else (-1, -1)
        self.aim_u, self.aim_v = aim if aim is not None else (-1, -1)


def weeks_along(world, start, path, budget: int, water_ok, costs, point=None, aim=None) -> int:
    """LA DUREE D'UN TRAJET (path.travel_weeks) : la marche rejouee semaine
    par semaine (march, `budget` points par semaine) sur une unite fictive
    partie de `point` (le centre de `start` sinon) : le trajet redresse,
    l'elan garde, un pas plus cher qu'une semaine fait en plusieurs. Un
    chemin coupe : les semaines faites jusque-la."""
    walker = _Walker(world.canonicalize(start) or start, path, point, aim)
    weeks = 0
    # Au pire (une montagne a contre-courant) : moins de 3 semaines par lieu.
    limit = 4 * len(path) + 8
    while walker.path and weeks < limit:
        before = point_of(world, walker)
        cut = march(world, walker, budget, water_ok, costs)
        if not cut or point_of(world, walker) != before:
            weeks += 1
        if cut:
            break
    return weeks
