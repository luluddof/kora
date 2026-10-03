from src.kora import chiefdom, confed
from src.kora.peoples import color_of
from src.kora.types import Season, Terrain

BIOME_COLORS = {
    Terrain.PLAINE: (186, 196, 120),
    Terrain.VALLEE: (88, 142, 92),
    Terrain.STEPPE: (210, 190, 120),
    Terrain.FORET: (46, 100, 56),
    Terrain.COLLINE: (140, 130, 90),
    Terrain.MONTAGNE: (110, 110, 115),
    Terrain.SOMMET: (230, 230, 235),
    Terrain.EAU: (40, 80, 140),
    Terrain.COTE: (210, 190, 130),
    Terrain.DESERT: (214, 176, 96),
}

_SNOW = (235, 240, 245)
_ICE = (180, 210, 230)
_SPRING_GREEN = (70, 150, 80)
_SUMMER_GOLD = (230, 190, 70)
_SUMMER_SAND = (230, 140, 60)
_AUTUMN_LEAF = (160, 90, 40)
_AUTUMN_GOLD = (200, 140, 60)


def _mix(a: tuple[int, int, int], b: tuple[int, int, int], t: float) -> tuple[int, int, int]:
    t = max(0.0, min(1.0, t))
    return (
        int(a[0] + (b[0] - a[0]) * t),
        int(a[1] + (b[1] - a[1]) * t),
        int(a[2] + (b[2] - a[2]) * t),
    )


def _scale(color: tuple[int, int, int], r: float, g: float, b: float) -> tuple[int, int, int]:
    return (
        min(255, int(color[0] * r)),
        min(255, int(color[1] * g)),
        min(255, int(color[2] * b)),
    )


def season_color(terrain: Terrain, season: Season) -> tuple[int, int, int]:
    base = BIOME_COLORS[terrain]
    if season is Season.HIVER:
        if terrain is Terrain.EAU:
            return _mix(base, _ICE, 0.35)
        if terrain is Terrain.SOMMET:
            return (245, 246, 250)
        snow = {
            Terrain.MONTAGNE: 0.55,
            Terrain.COLLINE: 0.45,
            Terrain.PLAINE: 0.42,
            Terrain.STEPPE: 0.38,
            Terrain.FORET: 0.40,
            Terrain.COTE: 0.35,
            Terrain.VALLEE: 0.32,
            Terrain.DESERT: 0.18,
        }.get(terrain, 0.40)
        return _mix(base, _SNOW, snow)
    if season is Season.PRINTEMPS:
        if terrain in (Terrain.VALLEE, Terrain.FORET, Terrain.PLAINE):
            return _mix(base, _SPRING_GREEN, 0.18)
        if terrain is Terrain.STEPPE:
            return _mix(base, _SPRING_GREEN, 0.08)
        if terrain is Terrain.EAU:
            return _mix(base, (60, 110, 160), 0.10)
        return base
    if season is Season.ETE:
        if terrain is Terrain.STEPPE:
            return _mix(base, _SUMMER_GOLD, 0.28)
        if terrain is Terrain.PLAINE:
            return _mix(base, (200, 190, 80), 0.18)
        if terrain is Terrain.DESERT:
            return _mix(base, _SUMMER_SAND, 0.22)
        if terrain is Terrain.FORET:
            return _scale(base, 0.92, 1.05, 0.85)
        if terrain is Terrain.EAU:
            return _mix(base, (30, 90, 160), 0.12)
        return base
    if terrain is Terrain.FORET:
        return _mix(base, _AUTUMN_LEAF, 0.45)
    if terrain is Terrain.VALLEE:
        return _mix(base, (140, 110, 50), 0.25)
    if terrain is Terrain.STEPPE:
        return _mix(base, _AUTUMN_GOLD, 0.30)
    if terrain is Terrain.PLAINE:
        return _mix(base, (190, 150, 70), 0.22)
    if terrain is Terrain.COTE:
        return _mix(base, (180, 140, 80), 0.15)
    return base


# --- la couleur des pays (tributaires, confederations) ----------------------------------
# Un tributaire prend une nuance claire de la couleur de son grand suzerain ;
# un confedere, une nuance de celle du fondateur : la carte montre des pays.
# Libre, chacun reprend sa couleur a lui (tribe.color ne change jamais).
VASSAL_OWN = 0.22    # ce qu'un tributaire garde de sa couleur
VASSAL_LIGHT = 0.14  # et l'eclaircie
CONFED_OWN = 0.3

_COUNTRY_CACHE: dict = {}


def _ties_key(state) -> tuple:
    out = []
    for k, ps in state.diplo.pacts.items():
        for p in ps:
            if p.kind in ("vassal", "confederation"):
                out.append((k, p.kind, p.payer, p.since))
    return (id(state), len(state.tribes), tuple(sorted(out)))


def _countries(state) -> dict:
    """{"color": peuple -> couleur affichee, "realm": peuple -> pays (son
    grand suzerain, ou le fondateur de sa confederation), "members": pays ->
    ses peuples} ; recalcule quand un lien change."""
    key = _ties_key(state)
    hit = _COUNTRY_CACHE.get("key")
    if hit == key:
        return _COUNTRY_CACHE["value"]
    groups = confed.groups(state)
    realm: dict[int, int] = {}
    for tid in state.tribes:
        root = chiefdom.top_lord(state, tid)
        if root in groups:
            root = confed.leader(state, root)
        realm[tid] = root
    members: dict[int, list] = {}
    for tid, root in realm.items():
        members.setdefault(root, []).append(tid)
    color: dict[int, tuple] = {}
    for tid, root in realm.items():
        own = color_of(state.tribes[tid])
        if root == tid:
            color[tid] = own
            continue
        base = color_of(state.tribes.get(root))
        if chiefdom.overlord_of(state, tid):
            color[tid] = _mix(_mix(base, own, VASSAL_OWN), (255, 255, 255), VASSAL_LIGHT)
        else:
            color[tid] = _mix(base, own, CONFED_OWN)
    value = {"color": color, "realm": realm, "members": {r: sorted(m) for r, m in members.items()}}
    _COUNTRY_CACHE["key"] = key
    _COUNTRY_CACHE["value"] = value
    return value


def country_color(state, tid) -> tuple:
    """La couleur d'un peuple sur la carte (celle de son pays)."""
    if tid not in state.tribes:
            return color_of(None)
    return _countries(state)["color"].get(tid) or (128, 128, 128)


def realm_of(state, tid) -> int:
    return _countries(state)["realm"].get(tid, tid)


def great_realms(state) -> list[tuple[int, list]]:
    """Les pays de plusieurs peuples (un suzerain et ses tributaires, une
    confederation), du plus grand au plus petit : (pays, ses peuples)."""
    out = [(root, m) for root, m in _countries(state)["members"].items() if len(m) > 1]
    out.sort(key=lambda x: (-len(x[1]), x[0]))
    return out


def members_of(state, tid) -> list:
    """Les peuples du pays de tid (lui seul s'il n'a ni suzerain, ni
    tributaire, ni confederes)."""
    c = _countries(state)
    return c["members"].get(c["realm"].get(tid, tid), [tid])


def seen_color(state, tid, lord) -> tuple:
    """La couleur d'un lieu tel qu'on l'a vu (memory.py) : son peuple, en
    nuance de son suzerain d'alors s'il en avait un."""
    own = color_of(state.tribes.get(tid))
    if not lord or lord not in state.tribes:
        return own
    base = color_of(state.tribes[lord])
    return _mix(_mix(base, own, VASSAL_OWN), (255, 255, 255), VASSAL_LIGHT)
