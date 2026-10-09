"""LE PLACEMENT DE L'ARBRE DES SAVOIRS, comme un graphe (a la Victoria 3).

L'arbre reste vertical (les ages et leurs paliers descendent), mais les
savoirs ne sont plus ranges dans une grille de colonnes : ils sont places
pour que le graphe se lise.
  1. Une COUCHE par palier (tech.ERAS : 0, 1, 1,5, 2, 3 | 3,5, 4, 5, 6).
  2. Un lien qui saute des couches passe par des POINTS DE PASSAGE, un par
     couche traversee : ils occupent une place etroite dans la rangee, que
     personne d'autre ne prend (la place laissee aux liens).
  3. L'ORDRE dans chaque couche reduit les croisements (methode des
     barycentres, en descendant puis en remontant, plusieurs fois ; on
     garde le meilleur ordre) ; au depart, l'ordre des branches.
  4. La POSITION de chacun : sous ce dont il depend, au-dessus de ce qu'il
     ouvre (la moyenne de ses voisins), sans chevauchement, l'ordre garde.
  5. Les LIENS : d'une rangee a la suivante, une courbe douce qui reste
     dans le couloir entre les deux ; a travers une rangee, la verticale de
     leur point de passage. Ils ne passent jamais sur une carte, et chacun
     garde sa trace (pas de cables partages).
Tout est calcule une fois (layout.tech_world le garde). Deterministe.
Pur : ni pygame ni partie.
"""

from __future__ import annotations

from src.kora import tech

CARD_W = 214
CARD_H = 82
TURN_W = 380
TURN_H = 104
DUMMY_W = 16
# L'espace entre deux cartes d'une rangee, entre deux points de passage.
GAP = 34
DUMMY_GAP = 8
# Une rangee : sa plus haute carte, puis le couloir des liens dessous.
CHANNEL = 74
SWEEPS = 24
POS_PASSES = 30


def _layers() -> list:
    return [tier for _name, tiers, _b in tech.ERAS for tier in tiers]


def _width(nid) -> int:
    if isinstance(nid, tuple):
        return DUMMY_W
    return TURN_W if tech.TECHS[nid].turning else CARD_W


def _height(nid) -> int:
    return TURN_H if tech.TECHS[nid].turning else CARD_H


def build() -> dict:
    """Le graphe place : {"order": [[noeuds par couche]], "x": {noeud: centre},
    "layer_of": {noeud: couche}, "edges": {(prerequis, savoir): [noeuds]}}.
    Un point de passage est un tuple (prerequis, savoir, couche)."""
    layers = _layers()
    index = {tier: i for i, tier in enumerate(layers)}
    layer_of: dict = {t.id: index[t.tier] for t in tech.TECHS.values()}
    order: list[list] = [[] for _ in layers]
    for t in sorted(tech.TECHS.values(), key=lambda t: (t.branch, t.slot, t.id)):
        order[layer_of[t.id]].append(t.id)
    # Les liens, et leurs points de passage.
    edges: dict = {}
    up: dict = {}
    down: dict = {}

    def link(a, b) -> None:
        down.setdefault(a, []).append(b)
        up.setdefault(b, []).append(a)

    for t in sorted(tech.TECHS.values(), key=lambda t: t.id):
        for pid in sorted(t.prereqs):
            chain = [pid]
            for k in range(layer_of[pid] + 1, layer_of[t.id]):
                d = (pid, t.id, k)
                layer_of[d] = k
                order[k].append(d)
                chain.append(d)
            chain.append(t.id)
            for a, b in zip(chain, chain[1:]):
                link(a, b)
            edges[(pid, t.id)] = chain
    # Les points de passage partent pres de leur prerequis.
    for k in range(1, len(order)):
        _sort_by(order[k], order[k - 1], up, keep_ties=True)
    order = _min_crossings(order, up, down)
    x = _positions(order, up, down)
    return {"order": order, "x": x, "layer_of": layer_of, "edges": edges, "layers": layers}


def _bary(nid, ref_pos: dict, links: dict):
    near = [ref_pos[n] for n in links.get(nid, ()) if n in ref_pos]
    return sum(near) / len(near) if near else None


def _sort_by(layer: list, ref: list, links: dict, keep_ties: bool = False) -> None:
    pos = {n: i for i, n in enumerate(ref)}
    current = {n: i for i, n in enumerate(layer)}
    keys = {}
    for n in layer:
        b = _bary(n, pos, links)
        keys[n] = (b if b is not None else current[n] * len(ref) / max(1, len(layer)), current[n])
    layer.sort(key=lambda n: keys[n])


def crossings(order: list, down: dict) -> int:
    total = 0
    for k in range(len(order) - 1):
        pos = {n: i for i, n in enumerate(order[k + 1])}
        pairs = []
        for i, n in enumerate(order[k]):
            for m in down.get(n, ()):
                if m in pos:
                    pairs.append((i, pos[m]))
        pairs.sort()
        for a in range(len(pairs)):
            for b in range(a + 1, len(pairs)):
                if pairs[a][0] < pairs[b][0] and pairs[a][1] > pairs[b][1]:
                    total += 1
    return total


def _min_crossings(order: list, up: dict, down: dict) -> list:
    best = [list(layer) for layer in order]
    best_c = crossings(best, down)
    cur = [list(layer) for layer in order]
    for sweep in range(SWEEPS):
        if sweep % 2 == 0:
            for k in range(1, len(cur)):
                _sort_by(cur[k], cur[k - 1], up)
        else:
            for k in range(len(cur) - 2, -1, -1):
                _sort_by(cur[k], cur[k + 1], down)
        c = crossings(cur, down)
        if c < best_c:
            best, best_c = [list(layer) for layer in cur], c
    return best


def _sep(a, b) -> float:
    """L'ecart minimal entre les centres de deux voisins d'une rangee."""
    gap = DUMMY_GAP if isinstance(a, tuple) or isinstance(b, tuple) else GAP
    return (_width(a) + _width(b)) / 2 + gap


def _place(layer: list, want: dict) -> dict:
    """Chacun au plus pres de sa place voulue, l'ordre garde, sans
    chevauchement : deux passes (vers la droite, vers la gauche), et leur
    moyenne, puis on repousse ce qui se touche encore."""
    if not layer:
        return {}
    right = {}
    prev = None
    for n in layer:
        right[n] = want[n] if prev is None else max(want[n], right[prev] + _sep(prev, n))
        prev = n
    left = {}
    nxt = None
    for n in reversed(layer):
        left[n] = want[n] if nxt is None else min(want[n], left[nxt] - _sep(n, nxt))
        nxt = n
    out = {n: (right[n] + left[n]) / 2 for n in layer}
    prev = None
    for n in layer:
        if prev is not None and out[n] < out[prev] + _sep(prev, n):
            out[n] = out[prev] + _sep(prev, n)
        prev = n
    return out


def _positions(order: list, up: dict, down: dict) -> dict:
    x: dict = {}
    for layer in order:
        pos = 0.0
        prev = None
        for n in layer:
            pos = 0.0 if prev is None else pos + _sep(prev, n)
            x[n] = pos
            prev = n
    for p in range(POS_PASSES):
        layers = range(1, len(order)) if p % 2 == 0 else range(len(order) - 2, -1, -1)
        for k in layers:
            layer = order[k]
            want = {}
            for n in layer:
                near = [x[m] for m in up.get(n, ())] + [x[m] for m in down.get(n, ())]
                # Un savoir se place surtout sous ses prerequis ; un point de
                # passage, sur la droite qui joint ses deux bouts.
                want[n] = sum(near) / len(near) if near else x[n]
            x.update(_place(layer, want))
    lo = min(x[n] - _width(n) / 2 for n in x)
    return {n: v - lo for n, v in x.items()}


def geometry(left: float, top: float, heads: dict) -> dict:
    """Les rectangles a l'echelle 1 de la toile, a partir de (left, top) ;
    heads : {age: hauteur de sa banniere}. Rend nodes, rows, heights,
    sections, links, size."""
    g = build()
    order, x, layers = g["order"], g["x"], g["layers"]
    width = max(x[n] + _width(n) / 2 for n in x)
    rows: dict = {}
    heights: dict = {}
    sections = []
    y = top
    k = 0
    for era, (_name, tiers, _b) in enumerate(tech.ERAS):
        head_h = heads.get(era, 0)
        head = (0, y, left + width + left, head_h)
        y += head_h
        body_top = y
        for tier in tiers:
            card_h = max((_height(n) for n in order[k] if not isinstance(n, tuple)), default=CARD_H)
            rows[tier] = y
            heights[tier] = card_h + CHANNEL
            y += card_h + CHANNEL
            k += 1
        sections.append({"era": era, "head": head, "body": (0, body_top, left + width + left, y - body_top)})
    nodes: dict = {}
    centers: dict = {}
    for k, layer in enumerate(order):
        tier = layers[k]
        row_h = heights[tier] - CHANNEL
        for n in layer:
            cx = left + x[n]
            if isinstance(n, tuple):
                centers[n] = (cx, rows[tier], rows[tier] + row_h)
                continue
            w, h = _width(n), _height(n)
            ny = rows[tier] + (row_h - h) / 2
            nodes[n] = (cx - w / 2, ny, w, h)
    links = _routes(g, nodes, centers, rows, heights, layers)
    return {"nodes": nodes, "rows": rows, "heights": heights, "sections": sections, "links": links,
            "size": (left + width + left, y)}


def _curve(a, b, steps: int = 10) -> list:
    """Une courbe douce de a (bas d'une carte) a b (haut de la suivante) :
    elle part et arrive a la verticale, et reste dans le couloir entre les
    deux rangees."""
    (x0, y0), (x1, y1) = a, b
    if abs(x0 - x1) < 0.5:
        return [a, b]
    out = []
    for i in range(steps + 1):
        t = i / steps
        # Bezier cubique, points de controle a la verticale des bouts.
        u = 1 - t
        y = u * u * u * y0 + 3 * u * u * t * (y0 + (y1 - y0) * 0.55) + 3 * u * t * t * (y1 - (y1 - y0) * 0.55) + t * t * t * y1
        x = u * u * u * x0 + 3 * u * u * t * x0 + 3 * u * t * t * x1 + t * t * t * x1
        out.append((round(x, 2), round(y, 2)))
    return out


def _routes(g, nodes, centers, rows, heights, layers) -> dict:
    """Les liens : une courbe douce dans chaque couloir, et, d'une rangee a
    l'autre, la verticale de leur point de passage (que personne d'autre
    n'occupe)."""
    out: dict = {}
    for (pid, tid), chain in sorted(g["edges"].items()):
        px, py, pw, ph = nodes[pid]
        cx, cy, cw, _ch = nodes[tid]
        pts = [(px + pw / 2, py + ph)]
        for d in chain[1:-1]:
            dx, top, bottom = centers[d]
            pts += _curve(pts[-1], (dx, top))[1:]
            pts.append((dx, bottom))
        pts += _curve(pts[-1], (cx + cw / 2, cy))[1:]
        out[(pid, tid)] = pts
    return out
