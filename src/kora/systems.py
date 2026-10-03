"""LE TABLEAU DES SYSTEMES : qui intervient, quand, et sur quoi.

Kora est fait de systemes (la chefferie, le commerce, l'argent, les
nombres, les situations...). Chacun vit dans son module ; ICI, et nulle
part ailleurs, on dit ou il se branche sur le reste du jeu :

  MONTHLY        le mois du monde (sim._week, une semaine sur quatre), dans
                 l'ordre ; (state) -> None
  STABILITY      ce qui fait la stabilite d'un village ; (state, tid) ->
                 [(raison, valeur)] (villages.stability_parts les ajoute)
  ARMY_MORALE    le moral d'une troupe ; (state, tid) -> points
  FLEE           les fuyards d'une bataille ; (state, tid) -> multiplicateur
  STOCK_WEEKS    les semaines de reserve d'une bande ; (state, band) -> semaines
  CRAFT_OUTPUT   la production d'un metier ; (state, site, craft) ->
                 multiplicateur (1.0 si le systeme ne s'en mele pas)
  EFFECT_FIELDS  les champs de Tribe qui portent des effets comme des
                 savoirs (lus par tech.bonuses) ; (tribe) -> ids
  EFFECT_SPECS   prefixe d'id -> fonction qui decrit ces effets ;
                 () -> {id: (nom, {effet: valeur})}
  EVENT_VOCABULARY  les modules qui ajoutent des conditions et des effets
                 aux evenements (events.vocabulary)

Un systeme nouveau : son module, puis UNE ligne dans chaque tableau ou il
intervient ; le reste du jeu n'a pas a l'importer. L'ordre des tableaux
est celui du calcul (le jeu est deterministe : on ne le change pas sans
re-enregistrer l'empreinte). Voir docs/code/ajouter-un-systeme.txt.
N'importe pas pygame.
"""

from __future__ import annotations

import importlib

MONTHLY = (
    "tech.update_start_bonuses",
    "diplo.monthly",
    "goods.monthly",
    "production.monthly",
    "chiefdom.monthly",
    "numbers.monthly",
    "money.monthly",
    "chiefs.monthly",
    "diplo.ai_monthly",
    "events.monthly",
    "situations.monthly",
)

STABILITY = (
    "goods.stability_parts",
    "chiefdom.stability_parts",
    "money.stability_parts",
)

ARMY_MORALE = (
    "chiefdom.army_morale",
    "money.solde_morale",
)

FLEE = ("money.flee_mult",)

# Semaines de reserve d'une bande, en plus de ses savoirs (bands.stock_max) ;
# (state, band) -> semaines (0 si le systeme ne s'en mele pas).
STOCK_WEEKS = ("villages.stock_weeks",)

CRAFT_OUTPUT = (
    "production.craft_mult",
    "chiefdom.craft_output",
    "money.craft_output",
)

EFFECT_FIELDS = (
    # Les bonus de depart comptent comme des savoirs tant qu'ils durent.
    "tech.start_bonus_ids",
    # Les situations (crises, prix des conjonctures).
    "situations.effect_ids",
    # La base des nombres et les operations connues.
    "numbers.effect_ids",
)

EFFECT_SPECS = {
    "sit:": "situations.effect_specs",
    "base:": "numbers.effect_specs",
    "op:": "numbers.effect_specs",
}

# Les modules qui ajoutent des conditions, des effets et leurs textes aux
# evenements (EVENT_CONDITIONS, EVENT_EFFECTS, EVENT_TEXTS ; events.vocabulary).
EVENT_VOCABULARY = ("goods", "money", "numbers")

_FN: dict = {}


def fn(path: str):
    """'module.fonction' -> la fonction (importee a la premiere demande)."""
    hit = _FN.get(path)
    if hit is None:
        mod, name = path.rsplit(".", 1)
        hit = _FN[path] = getattr(importlib.import_module(f"src.kora.{mod}"), name)
    return hit


def run(table, state) -> None:
    for path in table:
        fn(path)(state)


def parts(table, *args) -> list:
    out: list = []
    for path in table:
        out.extend(fn(path)(*args))
    return out


def total(table, *args):
    """La somme de ce que rend chaque systeme (0 s'il n'y en a pas)."""
    value = 0
    for path in table:
        value += fn(path)(*args)
    return value


def apply_mult(value: float, table, *args) -> float:
    """value multiplie par chaque systeme, l'un apres l'autre (meme ordre,
    memes arrondis que des multiplications ecrites a la suite)."""
    for path in table:
        value *= fn(path)(*args)
    return value
