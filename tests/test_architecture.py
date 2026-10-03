"""Les REGLES DU CODE de Kora, verifiees (docs/code/ajouter-un-systeme.txt).

Un test qui casse ici dit ce qu'un ajout a oublie : un champ qui ne se
sauve pas, un systeme mal branche, un import de pygame dans la simulation,
un texte sans accents, une icone absente..."""

import ast
import dataclasses
import importlib
import pathlib
import subprocess
import sys
import typing

from src.kora import records, screens, systems, tech
from src.kora.places import Site, VillageData
from src.kora.types import Band, Hex, Order, OrderKind, Person, Tribe

ROOT = pathlib.Path(__file__).resolve().parents[1]
SRC = ROOT / "src" / "kora"
# La presentation (pygame permis) ; tout le reste est la simulation et ses
# outils, en python pur.
PRESENTATION = {
    "app", "render", "theme", "look", "globe", "globe_draw", "screens", "layout",
} | {p.stem for p in SRC.glob("render_*.py")}


def _imports(path: pathlib.Path) -> set:
    tree = ast.parse(path.read_text(encoding="utf-8"))
    out = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            out.update(a.name for a in node.names)
        elif isinstance(node, ast.ImportFrom) and node.module:
            out.add(node.module)
            if node.module == "src.kora":
                out.update(f"src.kora.{a.name}" for a in node.names)
    return out


def test_the_simulation_never_imports_pygame_nor_the_screens():
    for path in sorted(SRC.glob("*.py")):
        if path.stem in PRESENTATION or path.stem == "__init__":
            continue
        bad = {m for m in _imports(path) if m.startswith("pygame") or m.split(".")[-1] in PRESENTATION}
        assert not bad, f"{path.name} (simulation) importe {sorted(bad)}"


# --- les fiches : chaque champ se sauve, se relit et se copie ---------------------


def _sample(hint, i: int):
    """Une valeur de ce type, differente du defaut."""
    origin, args = typing.get_origin(hint), typing.get_args(hint)
    if hint is bool:
        return True
    if hint is int:
        return 7 + i
    if hint is float:
        return 2.5 + i
    if hint is str:
        return f"x{i}"
    if hint is typing.Any:
        return 3
    if hint is Hex:
        return Hex(4, i)
    if hint is Order:
        return Order(OrderKind.GOTO, Hex(1, 2), None)
    if hint is Person:
        return Person(10 + i, "Iltaur", 3, ("sage",), 2)
    if origin is typing.Union:
        return _sample([a for a in args if a is not type(None)][0], i)
    if origin is set:
        return {_sample(args[0], i), _sample(args[0], i + 1)}
    if origin is tuple:
        return (_sample(args[0], i), _sample(args[0], i + 1))
    if origin is list:
        if args and args[0] is list:
            return [["a", 1], ["b", 2]]
        if args and typing.get_origin(args[0]) is dict:
            return [{"id": 1, "name": "f", "trait": "t", "charge": "", "favour": 30.0, "village": 2}]
        return [_sample(args[0], i), _sample(args[0], i + 1)] if args else [[1, 2.5, {"k": 1.0}]]
    if origin is dict:
        return {"k": _sample(args[1], i)} if args else {"k": {"j": [1, 2]}}
    if hint is dict:
        return {"k": {"j": [1, 2]}}
    if hint is list:
        return [[1, 2.5, {"k": 1.0}]]
    if isinstance(hint, type) and dataclasses.is_dataclass(hint):
        return _filled(hint)
    raise AssertionError(f"type inconnu de records.py : {hint}")


def _filled(cls):
    hints = typing.get_type_hints(cls)
    return cls(**{f.name: _sample(hints[f.name], i) for i, f in enumerate(dataclasses.fields(cls))})


def _mutables(obj, seen=None):
    seen = set() if seen is None else seen
    out = []
    if isinstance(obj, (list, dict, set)) or dataclasses.is_dataclass(obj):
        if id(obj) not in seen:
            seen.add(id(obj))
            out.append(obj)
    if isinstance(obj, dict):
        for v in obj.values():
            out += _mutables(v, seen)
    elif isinstance(obj, (list, tuple, set)):
        for v in obj:
            out += _mutables(v, seen)
    elif dataclasses.is_dataclass(obj) and not isinstance(obj, type):
        for f in dataclasses.fields(obj):
            out += _mutables(getattr(obj, f.name), seen)
    return out


def test_every_field_survives_a_save_and_a_copy():
    """Un champ ajoute a Tribe, Band ou Site (avec son type) se sauve, se
    relit, se copie sans rien partager : rien d'autre a ecrire."""
    import json

    for cls in (Tribe, Band, Site, VillageData):
        obj = _filled(cls)
        back = records.from_json(cls, json.loads(json.dumps(records.to_json(obj))))
        for f in dataclasses.fields(cls):
            if (f.metadata or {}).get("save", True):
                assert getattr(back, f.name) == getattr(obj, f.name), f"{cls.__name__}.{f.name} ne survit pas à la sauvegarde"
        twin = records.copy(obj)
        assert twin == obj
        shared = {id(m) for m in _mutables(obj)} & {id(m) for m in _mutables(twin)}
        assert not shared, f"{cls.__name__} : la copie partage des donnees modifiables"


def test_an_old_save_without_the_new_fields_still_loads():
    t = records.from_json(Tribe, {"id": 2, "name": "Akor", "prestige": 4, "is_player": False})
    assert t == Tribe(2, "Akor", 4, False)


# --- le tableau des systemes ---------------------------------------------------------


def test_every_system_hook_exists():
    # Tous les tableaux de systems.py (un tableau ajoute est verifie d'office).
    tables = {}
    for name in dir(systems):
        value = getattr(systems, name)
        if name.isupper() and not name.startswith("_") and name != "EVENT_VOCABULARY" and isinstance(value, (tuple, dict)):
            tables[name] = tuple(value.values()) if isinstance(value, dict) else value
    assert {"MONTHLY", "STABILITY", "BAND_SPLIT", "EMANCIPATED"} <= set(tables)
    for name, table in tables.items():
        assert len(set(table)) == len(table) or name == "EFFECT_SPECS", f"systems.{name} : une ligne en double"
        for path in table:
            assert callable(systems.fn(path)), f"systems.{name} : {path} n'existe pas"
    for mod in systems.EVENT_VOCABULARY:
        m = importlib.import_module(f"src.kora.{mod}")
        assert any(hasattr(m, a) for a in ("EVENT_CONDITIONS", "EVENT_EFFECTS")), mod


def test_every_effect_names_a_real_bonus():
    """Un effet ecrit dans un savoir, un bonus de depart, une situation, une
    base ou une operation doit exister dans tech.Bonuses (sinon il ne fait
    rien, en silence)."""
    # "base" (jeu de base), "herd" et "cabotage" (Tribe.troupeau, Tribe.cabotage,
    # poses par tech.grant) : des
    # marqueurs pour le texte des effets.
    fields = set(tech.Bonuses.__dataclass_fields__) | {"base", "herd", "cabotage"}
    sources = list(tech.TECHS.values()) + list(tech.START_BONUSES.values())
    for path in systems.EFFECT_SPECS.values():
        sources += [tech.spec_effect(k) for k in systems.fn(path)()]
    for src in sources:
        for key in src.effects:
            assert key in fields, f"{src.id} : l'effet « {key} » n'existe pas dans tech.Bonuses"


def test_every_command_has_a_handler():
    from src.kora import commands

    assert set(commands._HANDLERS) == set(commands.KINDS)


def test_every_big_screen_is_wired():
    for s in screens.SCREENS:
        mod, fn = s.draw.rsplit(".", 1)
        assert callable(getattr(importlib.import_module(f"src.kora.{mod}"), fn)), s.name
    app = (SRC / "app.py").read_text(encoding="utf-8")
    for s in screens.SCREENS:
        assert f'"{s.name}":' in app, f"app.play : pas de fonction de clic pour l'écran {s.name}"


# --- la charte -------------------------------------------------------------------------


def test_every_shown_text_is_accented():
    out = subprocess.run([sys.executable, str(ROOT / "tools" / "accents.py"), "--dry"], capture_output=True, text=True, cwd=ROOT)
    last = out.stdout.strip().splitlines()[-1]
    assert last.split()[0] == "0", out.stdout[-2000:]


def test_every_icon_named_in_the_code_is_there():
    from src.kora.theme import ICON_FILES

    for key in ICON_FILES:
        assert (ROOT / "data" / "icons" / f"{key}.svg").exists(), f"icone {key} : tools/recuperer_assets.py"
    used = set()
    for path in SRC.glob("*.py"):
        for node in ast.walk(ast.parse(path.read_text(encoding="utf-8"))):
            if isinstance(node, ast.Call) and getattr(node.func, "attr", "") in ("icon", "medallion") and node.args:
                a = node.args[0]
                if isinstance(a, ast.Constant) and isinstance(a.value, str):
                    used.add(a.value)
    missing = sorted(k for k in used if k not in ICON_FILES)
    assert not missing, f"icones sans fichier (theme.ICON_FILES) : {missing}"
