"""Les FICHES : sauver, relire et copier un dataclass d'apres ses champs.

Un champ de Tribe ou de Band (types.py) se declare UNE fois, avec son type
precis (dict[str, float], list[str], set[str], Optional[Person]...) et sa
valeur par defaut : sa sauvegarde (persist.py), sa relecture (une vieille
partie sans ce champ prend le defaut) et sa copie (sim.snapshot, a chaque
pas) s'en deduisent. Plus de listes de champs a tenir a la main en trois
endroits.

Les types connus :
  int, float, str, bool        convertis a la relecture (350 -> 350.0)
  Optional[T]                  None ou T
  set[T]                       une liste triee
  tuple[T, ...]                une liste
  list[T], dict[str, T]        element par element
  Hex, Order, Person           leurs propres codecs (register)
  un autre dataclass           sa propre fiche (imbriquee) ; s'il porte
                               COMPACT = True, seuls les champs differents
                               du defaut sont ecrits (sites.VillageData)
  Any                          une valeur JSON simple (nombre, texte, booleen)
  list[list]                   des rangees de valeurs simples ([id, semaine])
  dict, list (nus)             tels quels (JSON) ; copie profonde
Un champ peut preciser, par field(metadata=...) :
  "round": n                   arrondi a la sauvegarde
  "decode": fonction           relecture a la main (vieilles parties)
  "save": False                jamais sauve (cache, valeur derivee)
  "copy": fonction             copie a la main
N'importe pas pygame.
"""

from __future__ import annotations

import copy as _copy
import dataclasses
import typing
from typing import Any

from src.kora.types import Hex, Order, OrderKind, Person, copy_person, person_from_json, person_to_json

_CODECS: dict = {}
_PLANS: dict = {}


def json_copy(value):
    """Copie d'une donnee JSON (dicts, listes, nombres, textes) : meme
    resultat que deepcopy, bien plus vite (la sauvegarde du pas en fait une
    par lieu et par tribu)."""
    if isinstance(value, dict):
        return {k: json_copy(v) for k, v in value.items()}
    if isinstance(value, list):
        return [json_copy(v) for v in value]
    if isinstance(value, (int, float, str, bool, type(None))):
        return value
    return _copy.deepcopy(value)


def register(cls, to_json, from_json, copier=None) -> None:
    """Un type qui a sa propre forme en JSON (Hex, Order, Person)."""
    _CODECS[cls] = (to_json, from_json, copier)


_SCALARS = (int, float, str, bool)


def _immutable(hint) -> bool:
    if hint in _SCALARS or hint is type(None) or hint is Any:
        return True
    if hint in _CODECS:
        return _CODECS[hint][2] is None
    origin = typing.get_origin(hint)
    args = typing.get_args(hint)
    if origin is typing.Union:
        return all(_immutable(a) for a in args)
    if origin is tuple:
        return all(_immutable(a) for a in args if a is not Ellipsis)
    return False


def _nested(hint) -> bool:
    return isinstance(hint, type) and dataclasses.is_dataclass(hint) and hint not in _CODECS


def _encoder(hint):
    if hint in _SCALARS or hint is Any:
        return None
    if hint in _CODECS:
        return _CODECS[hint][0]
    if _nested(hint):
        return lambda v: plan(hint).to_json(v)
    origin = typing.get_origin(hint)
    args = typing.get_args(hint)
    if origin is typing.Union:
        inner = [a for a in args if a is not type(None)]
        enc = _encoder(inner[0]) if len(inner) == 1 else None
        return (lambda v: None if v is None else enc(v)) if enc else None
    if origin is set:
        enc = _encoder(args[0]) if args else None
        return (lambda v: sorted(enc(x) for x in v)) if enc else sorted
    if origin in (tuple, list):
        enc = _encoder(args[0]) if args else None
        return (lambda v: [enc(x) for x in v]) if enc else list
    if origin is dict:
        enc = _encoder(args[1]) if len(args) == 2 else None
        return (lambda v: {k: enc(x) for k, x in v.items()}) if enc else dict
    return None


def _decoder(hint):
    if hint in (int, float, str):
        return hint
    if hint is bool:
        return bool
    if hint is Any:
        return None
    if hint in _CODECS:
        return _CODECS[hint][1]
    if _nested(hint):
        return lambda v: plan(hint).from_json(v)
    origin = typing.get_origin(hint)
    args = typing.get_args(hint)
    if origin is typing.Union:
        inner = [a for a in args if a is not type(None)]
        dec = _decoder(inner[0]) if len(inner) == 1 else None
        return (lambda v: None if v is None else dec(v)) if dec else None
    if origin is set:
        dec = _decoder(args[0]) if args else None
        return (lambda v: {dec(x) for x in v}) if dec else set
    if origin is tuple:
        dec = _decoder(args[0]) if args else None
        return (lambda v: tuple(dec(x) for x in v)) if dec else tuple
    if origin is list:
        dec = _decoder(args[0]) if args else None
        return (lambda v: [dec(x) for x in v]) if dec else list
    if origin is dict:
        kd = _decoder(args[0]) if len(args) == 2 else None
        vd = _decoder(args[1]) if len(args) == 2 else None
        if kd or vd:
            kd = kd or (lambda k: k)
            vd = vd or (lambda x: x)
            return lambda v: {kd(k): vd(x) for k, x in v.items()}
        return dict
    return None


def _copier(hint):
    """La copie la moins chere qui ne partage rien de modifiable."""
    if _immutable(hint):
        return None
    if hint in _CODECS:
        return _CODECS[hint][2]
    if _nested(hint):
        return lambda v: plan(hint).copy(v)
    origin = typing.get_origin(hint)
    args = typing.get_args(hint)
    if origin is typing.Union:
        inner = [a for a in args if a is not type(None)]
        cp = _copier(inner[0]) if len(inner) == 1 else json_copy
        return (lambda v: None if v is None else cp(v)) if cp else None
    if origin is set and args and _immutable(args[0]):
        return set
    if origin is list and args:
        if _immutable(args[0]):
            return list
        if args[0] is list:
            # Des rangees de valeurs simples.
            return lambda v: [list(x) for x in v]
        cp = _copier(args[0])
        return lambda v: [cp(x) for x in v]
    if origin is dict and len(args) == 2:
        if _immutable(args[1]):
            return dict
        cp = _copier(args[1])
        return lambda v: {k: cp(x) for k, x in v.items()}
    return json_copy


class _Plan:
    def __init__(self, cls) -> None:
        hints = typing.get_type_hints(cls, include_extras=False)
        self.cls = cls
        # COMPACT : n'ecrire que ce qui differe du defaut.
        self.defaults = None
        if getattr(cls, "COMPACT", False):
            blank = cls()
            self.defaults = {f.name: getattr(blank, f.name) for f in dataclasses.fields(cls)}
        self.fields = []
        self.copiers = []
        for f in dataclasses.fields(cls):
            hint = hints[f.name]
            meta = f.metadata or {}
            required = f.default is dataclasses.MISSING and f.default_factory is dataclasses.MISSING
            enc = _encoder(hint)
            dec = meta.get("decode") or _decoder(hint)
            if "round" in meta:
                n = meta["round"]
                base = enc
                if typing.get_origin(hint) is dict:
                    enc = lambda v, n=n: {k: round(x, n) for k, x in v.items()}
                else:
                    enc = lambda v, n=n, base=base: round(base(v) if base else v, n)
            self.fields.append((f.name, enc, dec, required, meta.get("save", True), f))
            cp = meta.get("copy") or _copier(hint)
            if cp is not None:
                self.copiers.append((f.name, cp))

    def to_json(self, obj) -> dict:
        out = {}
        for name, enc, _dec, _req, save, _f in self.fields:
            if not save:
                continue
            v = getattr(obj, name)
            if self.defaults is not None and v == self.defaults[name]:
                continue
            out[name] = enc(v) if enc is not None and v is not None else v
        return out

    def from_json(self, data: dict):
        kwargs = {}
        for name, _enc, dec, required, save, f in self.fields:
            if not save or name not in data:
                if required:
                    raise KeyError(name)
                continue
            v = data[name]
            try:
                kwargs[name] = dec(v) if dec is not None and v is not None else v
            except (TypeError, ValueError, AttributeError, KeyError, IndexError):
                # Une vieille partie au champ mal forme : la valeur par defaut.
                if required:
                    raise
        return self.cls(**kwargs)

    def copy(self, obj):
        out = _copy.copy(obj)
        for name, cp in self.copiers:
            v = getattr(obj, name)
            setattr(out, name, cp(v))
        return out


def plan(cls) -> _Plan:
    p = _PLANS.get(cls)
    if p is None:
        _setup()
        p = _PLANS[cls] = _Plan(cls)
    return p


def to_json(obj) -> dict:
    return plan(type(obj)).to_json(obj)


def from_json(cls, data: dict):
    return plan(cls).from_json(data)


def copy(obj):
    return plan(type(obj)).copy(obj)


_READY = False


def _setup() -> None:
    """Les codecs des types du jeu (Hex, Order, Person)."""
    global _READY
    if _READY:
        return
    _READY = True
    register(Hex, lambda h: [h.q, h.r], lambda v: Hex(int(v[0]), int(v[1])))
    register(
        Order,
        lambda o: {
            "kind": o.kind.value,
            "target_hex": [o.target_hex.q, o.target_hex.r] if o.target_hex is not None else None,
            "target_band_id": o.target_band_id,
        },
        lambda d: Order(
            kind=OrderKind(d["kind"]),
            target_hex=Hex(int(d["target_hex"][0]), int(d["target_hex"][1])) if d.get("target_hex") is not None else None,
            target_band_id=d.get("target_band_id"),
        ),
        _copy.copy,
    )
    register(Person, person_to_json, person_from_json, copy_person)
