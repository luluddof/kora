"""Les LOIS d'un pays (l'ecran Pays, onglet Lois).

Une loi a des options ; le pays en tient une. Pour l'instant deux lois
(sa demande : "aucune autre pour l'instant") :

  Paiement en argent   (il faut Valeurs d'echange)
      En vivres   le commerce se paie en vivres (par defaut)
      En argent   vos achats sur les routes se paient en sicles quand
                  l'autre peuple connait aussi l'argent (money.pays_in_money)
  La base des nombres  (il faut Nombres additifs ; numbers.py)
      Dix, douze, vingt, soixante : la premiere fois, on choisit tout de
      suite ; en changer est une reforme (prestige, trois ans sans
      l'avantage de la base, une fois en trente ans).

Les options choisies vivent dans Tribe.laws (la base : Tribe.base, que
numbers.py tient). Tout passe par commands.py ("law"). L'IA : money._ai
(le paiement), numbers.ai_base (la base).
N'importe pas pygame.
"""

from __future__ import annotations

from dataclasses import dataclass

from src.kora import money, numbers, tech


@dataclass(frozen=True)
class Option:
    id: str
    name: str
    text: str


@dataclass(frozen=True)
class Law:
    id: str
    name: str
    text: str
    needs: str  # ce qu'il faut savoir (le texte)
    options: tuple
    default: str


_LAWS: list = []


def _build() -> tuple:
    return (
        Law(
            "paiement",
            "Paiement en argent",
            "Comment vos villages paient ce qu'ils achètent sur les routes.",
            "Valeurs d'échange",
            (
                Option("vivres", "En vivres", "Le commerce se paie en vivres, pris au grenier des villages."),
                Option(
                    "argent",
                    "En argent",
                    f"Vos achats se paient en sicles (un sicle vaut {money.VPS:.0f} vivres) quand l'autre peuple "
                    "connaît aussi l'argent ; les vivres restent au grenier. Sans sicles, on paie en vivres.",
                ),
            ),
            "vivres",
        ),
        Law(
            "base",
            "La base des nombres",
            "Comment votre peuple compte : on choisit sa base une fois ; en changer est une réforme très lourde.",
            "Nombres additifs",
            tuple(Option(str(b), numbers.BASES[b][0], numbers.BASES[b][1]) for b in numbers.BASE_ORDER),
            "",
        ),
    )


def all_laws() -> tuple:
    """Les lois (construites a la premiere demande : money et numbers, qui
    les nourrissent, s'importent en cercle avec ce module)."""
    if not _LAWS:
        _LAWS.extend(_build())
    return tuple(_LAWS)


def law(law_id: str):
    return next((x for x in all_laws() if x.id == law_id), None)


def known(state, tid: int, law_id: str) -> bool:
    """Le pays peut-il tenir cette loi (il sait ce qu'il faut) ?"""
    tribe = state.tribes.get(tid)
    if tribe is None:
        return False
    if law_id == "paiement":
        return money.has_money(state, tid)
    if law_id == "base":
        return tech.bonuses(tribe).numbers
    return False


def available(state, tid: int) -> list:
    return [x for x in all_laws() if known(state, tid, x.id)]


def get(tribe, law_id: str) -> str:
    """L'option tenue ("" : pas encore choisie). Une vieille partie gardait
    le paiement en argent dans le budget."""
    if law_id == "base":
        return str(tribe.base) if tribe.base else ""
    laws = getattr(tribe, "laws", None) or {}
    if law_id in laws:
        return laws[law_id]
    if law_id == "paiement" and (getattr(tribe, "budget", None) or {}).get("commerce"):
        return "argent"
    return law(law_id).default


def block(state, tid: int, law_id: str, option: str) -> str:
    """Pourquoi on ne peut pas tenir cette option ("" : on peut)."""
    x = law(law_id)
    if x is None or option not in {o.id for o in x.options}:
        return "?"
    if not known(state, tid, law_id):
        return f"Il faut connaître {x.needs}"
    tribe = state.tribes[tid]
    if get(tribe, law_id) == option:
        return "C'est déjà votre loi"
    if law_id == "base":
        return numbers.choose_block(state, tid, int(option))
    return ""


def enact(state, tid: int, law_id: str, option: str) -> str:
    why = block(state, tid, law_id, option)
    if why:
        return why
    tribe = state.tribes[tid]
    if law_id == "base":
        return numbers.choose(state, tid, int(option))
    tribe.laws = {**(tribe.laws or {}), law_id: option}
    b = dict(tribe.budget or {})
    if b.pop("commerce", None) is not None:
        tribe.budget = b
    name = next(o.name for o in law(law_id).options if o.id == option)
    return f"{law(law_id).name} : {name.lower()}."


def option_name(tribe, law_id: str) -> str:
    cur = get(tribe, law_id)
    return next((o.name for o in law(law_id).options if o.id == cur), "à choisir")
