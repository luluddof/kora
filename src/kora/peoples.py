"""Peuples : cultures, noms, couleurs.

Une culture dit ou un peuple aime vivre, ce qu'il sait au depart, quels
savoirs il prefere et quelle audace a son IA. Les identifiants 1 a 4
(joueur, steppe, foret, cote) gardent leur culture d'origine quand une
ancienne sauvegarde ne la precise pas.
N'importe ni sim ni pygame.
"""

from __future__ import annotations

from dataclasses import dataclass

from src.kora.types import Terrain

_T = Terrain
# Au-dela, un clan qui fait secession rejoint un voisin (ou un peuple frere)
# au lieu de fonder un peuple : la carte reste lisible. Assez haut pour les
# peuples nes des clans qui s'emancipent apres les villages.
MAX_LIVING_TRIBES = 120


@dataclass(frozen=True)
class Culture:
    id: str
    label: str
    start: frozenset
    min_forage: float
    # Terrains preferes pour camper et fuir la faim (None = la nourriture seule).
    prefer: frozenset | None
    # Terrains preferes pour errer (None = comme prefer).
    roam: frozenset | None
    raid_weeks: int
    raid_prestige: int
    # Ne raide pas quand la collecte locale suffit.
    shy: bool
    knowledge: tuple
    taste: tuple
    syllables: tuple


_SYL_STEPPE = ("ta", "vek", "kur", "gan", "bai", "sar", "khe", "tum", "or", "ul", "ak", "den")
_SYL_FORET = ("lu", "mi", "na", "ev", "ol", "ri", "sil", "wen", "ta", "o", "el", "ni")
_SYL_COTE = ("ma", "re", "su", "ka", "le", "po", "ni", "sa", "ai", "mo", "ea", "lin")
_SYL_VALLEE = ("ar", "an", "e", "li", "ne", "ur", "di", "ta", "sen", "ra", "il", "mae")
_SYL_COLLINES = ("dor", "ka", "bra", "ok", "hu", "mar", "tor", "ug", "ra", "ben", "gu", "rok")
_SYL_DESERT = ("ha", "zir", "am", "sa", "ke", "dun", "ra", "ib", "el", "sha", "tu", "na")
_SYL_NORD = ("sko", "ai", "ne", "ru", "va", "ki", "ol", "sa", "er", "tu", "hja", "rin")

CULTURES: dict[str, Culture] = {
    c.id: c
    for c in (
        Culture(
            "joueur", "votre peuple", frozenset({_T.VALLEE, _T.PLAINE}), 40.0,
            None, None, 3, 40, False, (), (), _SYL_VALLEE,
        ),
        # Clans partis du joueur apres l'age des villages : memes noms, memes
        # gouts, des sedentaires (chiefs.secede).
        Culture(
            "souche", "peuple de votre souche", frozenset({_T.VALLEE, _T.PLAINE}), 34.0,
            frozenset({_T.VALLEE, _T.PLAINE}), None, 3, 45, True,
            (),
            ("semis", "huttes", "poterie", "champs", "palissade", "maisons", "fumage"),
            _SYL_VALLEE,
        ),
        Culture(
            "steppe", "peuple des steppes", frozenset({_T.STEPPE}), 30.0,
            None, frozenset({_T.STEPPE, _T.PLAINE}), 4, 25, False,
            ("epieu", "troupeau"),
            ("arc", "peaux", "portage", "conte", "guetteurs", "fumage", "chefferie"),
            _SYL_STEPPE,
        ),
        Culture(
            "foret", "peuple des forets", frozenset({_T.FORET}), 32.0,
            None, None, 3, 40, True,
            ("cueillette",),
            ("fumage", "semis", "arc", "cueillette", "poterie", "conte"),
            _SYL_FORET,
        ),
        Culture(
            "cote", "peuple des rivages", frozenset({_T.COTE}), 24.0,
            frozenset({_T.COTE, _T.VALLEE}), None, 3, 40, False,
            ("peche", "pirogue"),
            ("filets", "fumage", "peche", "conte", "poterie", "chefferie"),
            _SYL_COTE,
        ),
        Culture(
            "vallee", "peuple des vallees", frozenset({_T.VALLEE, _T.PLAINE}), 34.0,
            frozenset({_T.VALLEE, _T.PLAINE}), None, 3, 45, True,
            ("cueillette",),
            ("fumage", "semis", "poterie", "conte", "huttes", "cueillette"),
            _SYL_VALLEE,
        ),
        Culture(
            "collines", "peuple des collines", frozenset({_T.COLLINE}), 22.0,
            frozenset({_T.COLLINE, _T.FORET}), None, 3, 35, False,
            ("peaux",),
            ("portage", "arc", "epieu", "fumage", "conte", "guetteurs"),
            _SYL_COLLINES,
        ),
        Culture(
            "desert", "nomades du desert", frozenset({_T.DESERT, _T.STEPPE}), 16.0,
            None, frozenset({_T.STEPPE, _T.DESERT, _T.PLAINE}), 4, 30, False,
            ("epieu",),
            ("troupeau", "arc", "fumage", "peaux", "conte"),
            _SYL_DESERT,
        ),
        Culture(
            "nord", "peuple du grand froid", frozenset({_T.FORET, _T.STEPPE, _T.COLLINE}), 18.0,
            None, None, 3, 40, True,
            ("peaux",),
            ("fumage", "portage", "huttes", "arc", "conte"),
            _SYL_NORD,
        ),
    )
}

# Anciennes sauvegardes, tests : la culture se deduit de l'identifiant.
LEGACY_CULTURE = {1: "joueur", 2: "steppe", 3: "foret", 4: "cote"}
LEGACY_COLOR = {
    1: (220, 70, 70),
    2: (70, 140, 220),
    3: (80, 180, 90),
    4: (220, 180, 60),
}
PALETTE = (
    (170, 100, 210),
    (230, 130, 50),
    (70, 200, 200),
    (230, 110, 170),
    (170, 120, 80),
    (150, 150, 235),
    (160, 175, 60),
    (200, 60, 110),
    (120, 195, 245),
    (150, 215, 95),
    (235, 205, 150),
    (110, 130, 170),
    (215, 215, 215),
    (190, 150, 40),
)
GREY = (200, 200, 200)


def culture_of(tribe) -> Culture:
    key = getattr(tribe, "culture", "") or LEGACY_CULTURE.get(getattr(tribe, "id", 0), "vallee")
    return CULTURES.get(key, CULTURES["vallee"])


def color_of(tribe) -> tuple:
    if tribe is None:
        return GREY
    color = getattr(tribe, "color", None)
    if color:
        return tuple(color)
    return LEGACY_COLOR.get(tribe.id, GREY)


def label_of(tribe) -> str:
    return culture_of(tribe).label


def free_color(tribes) -> tuple:
    used = {color_of(t) for t in tribes}
    for color in PALETTE:
        if color not in used:
            return color
    # Plus de couleurs libres : on recycle (la carte n'en montre jamais autant).
    return PALETTE[len(used) % len(PALETTE)]


def make_name(rng, culture: Culture, taken=()) -> str:
    """Un nom de 2 ou 3 syllabes, tire au hasard du recit, jamais deja pris."""
    taken = {n.lower() for n in taken}
    syl = culture.syllables
    name = ""
    for _ in range(40):
        n = 2 if rng.random() < 0.6 else 3
        name = "".join(rng.choice(syl) for _ in range(n))
        if 3 <= len(name) <= 9 and name.lower() not in taken:
            break
    return name.capitalize()


def culture_for_place(world, h) -> str:
    """Culture d'un peuple ne sur cette case : son biome, et le froid."""
    terrain = world.terrain(h)
    row = world.canonicalize(h).r if world.canonicalize(h) is not None else 0
    lat = abs(row / max(1, world.height - 1) * 2.0 - 1.0)
    if lat > 0.62 and terrain in (_T.FORET, _T.STEPPE, _T.COLLINE, _T.PLAINE):
        return "nord"
    return {
        _T.STEPPE: "steppe",
        _T.FORET: "foret",
        _T.COTE: "cote",
        _T.VALLEE: "vallee",
        _T.PLAINE: "vallee",
        _T.COLLINE: "collines",
        _T.MONTAGNE: "collines",
        _T.DESERT: "desert",
    }.get(terrain, "vallee")


MINOR_START = 6
MINOR_POP = (18, 26)
MINOR_SPACING = 40
# Un petit peuple garde au plus 4 bandes (8 avec la Chefferie).
MINOR_BAND_CUT = 4


def pick_minor_spots(world, taken: list, count: int, rng, avoid=None) -> list:
    """Departs des petits peuples : loin de tous les autres (point le plus
    eloigne, tire parmi les meilleurs), sur une terre qui nourrit, hors des
    poles. avoid : cases a eviter (deja explorees par le joueur)."""
    from src.kora.world import offset_to_axial, spawn_forage

    good = {_T.PLAINE, _T.VALLEE, _T.STEPPE, _T.FORET, _T.COLLINE, _T.COTE, _T.DESERT}
    pool = []
    step = 7
    for row in range(int(world.height * 0.2), int(world.height * 0.8), 3):
        for col in range(row % step, world.width, step):
            if world._terrains[row][col] not in good:
                continue
            h = offset_to_axial(col, row)
            if avoid and h in avoid:
                continue
            pool.append(h)
    pool = [h for h in pool if spawn_forage(world, h) >= 16.0]
    chosen: list = []
    others = list(taken)
    for _ in range(count):
        scored = []
        for h in pool:
            near = min((world.distance(h, o) for o in others), default=10**6)
            if near >= MINOR_SPACING:
                scored.append((near, h))
        if not scored:
            break
        scored.sort(key=lambda it: (-it[0], it[1].q, it[1].r))
        top = scored[: max(1, len(scored) // 12)]
        pick = rng.choice(top)[1]
        chosen.append(pick)
        others.append(pick)
    return chosen


def civ_of(state, tribe) -> int:
    """Civilisation d'un peuple : celle du peuple dont il est ne, de
    lignee en lignee (sinon la sienne)."""
    seen = set()
    while tribe is not None and not tribe.civ and tribe.origin and tribe.origin not in seen:
        seen.add(tribe.id)
        parent = state.tribes.get(tribe.origin)
        if parent is None:
            break
        tribe = parent
    if tribe is None:
        return 0
    return tribe.civ or tribe.id


def kin_color(state, civ: int) -> tuple:
    """Couleur d'un peuple ne d'une civilisation : une nuance de la sienne
    (plus claire, plus sombre), pour que les civilisations se lisent en
    familles de couleurs sur la carte."""
    root = state.tribes.get(civ)
    base = color_of(root) if root is not None else GREY
    n = sum(1 for t in state.tribes.values() if t.id != civ and civ_of(state, t) == civ)
    shades = (0.35, -0.3, 0.55, -0.45, 0.2, -0.18, 0.7, -0.6)
    t = shades[n % len(shades)]
    target = (255, 255, 255) if t > 0 else (0, 0, 0)
    t = abs(t)
    return tuple(int(base[i] + (target[i] - base[i]) * t) for i in range(3))


def civ_name(state, civ: int) -> str:
    root = state.tribes.get(civ)
    return root.name if root is not None else "?"


def civ_villages(state, civ: int) -> int:
    """Villages de tous les peuples de cette civilisation."""
    n = 0
    for site in state.sites.values():
        if site.kind == "village":
            owner = state.tribes.get(site.tribe_id)
            if owner is not None and civ_of(state, owner) == civ:
                n += 1
    return n


def children_alive(state, tribe_id: int) -> int:
    """Peuples nes de ce peuple (clans partis) encore vivants."""
    living = {b.tribe_id for b in state.bands.values() if b.population > 0}
    return sum(1 for t in state.tribes.values() if t.origin == tribe_id and t.id in living)


def living_tribe_ids(state) -> set[int]:
    # Les villageois sont une bande installee : les bandes suffisent.
    return {b.tribe_id for b in state.bands.values() if b.population > 0}
