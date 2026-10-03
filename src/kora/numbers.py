"""Les NOMBRES d'une civilisation : sa base de numeration, ses operations.

  Comptage par batons (age tribal) : on compte. L'ADDITION (+) est connue.
  Nombres additifs (neolithique) : on ecrit les nombres ; on CHOISIT SA BASE,
    une fois pour toutes (une reforme est possible, tres couteuse) :
      base 10   doigts : apprendre est plus simple (savoirs +5 %)
      base 12   phalanges : douze se partage en 2, 3, 4, 6 (ventes +6 %)
      base 20   doigts et orteils : on denombre les gens (stabilite +3,
                famine moins cruelle)
      base 60   lunes et saisons : on mesure le grain (grain gate -20 %,
                +4 semaines de grenier)
    Et un METIER : les calculateurs (goods.py, "calculateurs"). Chaque
    equipe donne des points de calcul chaque mois ; ils font trouver les
    OPERATIONS suivantes, chacune avec son effet :
      -  soustraction     on sait ce qui manque : grain gate -10 %
      x  multiplication   tant de champs, tant de grain : recolte +5 %
      /  division         partager juste : stabilite +4
      1/2 fractions       les parts du tribut et de l'impot : ventes +4 %,
                          impot +10 %
  (Plus tard : la numeration de position, comme nos chiffres.)

Les effets passent par Tribe.math_effects (ids "base:10", "op:sub"...),
lus par tech.bonuses comme des savoirs. N'importe pas pygame.
"""

from __future__ import annotations

from src.kora.log import LogKind

BASES = {
    10: ("Base dix", "On compte sur ses doigts : les nombres s'apprennent vite.", {"learn": 1.05}),
    12: ("Base douze", "On compte les phalanges du pouce : douze se partage en 2, 3, 4 et 6, le commerce aime ça.", {"trade_price": 1.06}),
    20: ("Base vingt", "Doigts et orteils : on dénombre vite les gens et les bêtes.", {"stability": 3, "winter_famine": 0.95}),
    60: ("Base soixante", "Comme les lunes et les saisons : on mesure le grain et le temps.", {"grain_rot": 0.8, "granary": 4}),
}
BASE_ORDER = (10, 12, 20, 60)
# (id, nom, signe, points pour la trouver, effets, recit)
OPS = (
    ("add", "Addition", "+", 0, {"stock_weeks": 1}, "On ajoute les jarres et les bêtes : on sait ce qu'on a."),
    ("sub", "Soustraction", "−", 10, {"grain_rot": 0.9}, "On sait ce qui manque, ce qui reste : moins de grain perdu."),
    ("mul", "Multiplication", "×", 25, {"field_yield": 1.05}, "Tant de champs, tant de grain : on prévoit les semailles."),
    ("div", "Division", "÷", 50, {"stability": 4}, "Partager juste : les parts du grain et du butin."),
    ("frac", "Fractions", "½", 90, {"trade_price": 1.04, "tax": 1.1}, "Les parts du tribut, de l'impôt et des échanges."),
)
OP_IDS = tuple(o[0] for o in OPS)
OP_BY_ID = {o[0]: o for o in OPS}
# Points de calcul d'une equipe de calculateurs par mois.
TEAM_POINTS = 1.0
# Changer de base : tres couteux (son choix : "definitive ou tres compliquee
# a changer").
REFORM_PRESTIGE = 40
REFORM_WEEKS = 3 * 52
REFORM_EVERY = 30 * 52


def effect_ids(tribe) -> list:
    """La base et les operations en vigueur (systems.EFFECT_FIELDS)."""
    return getattr(tribe, "math_effects", None) or []


def effect_specs() -> dict:
    out = {}
    for b, (name, _text, eff) in BASES.items():
        out[f"base:{b}"] = (name, eff)
    for oid, name, sign, _cost, eff, _text in OPS:
        out[f"op:{oid}"] = (f"{name} ({sign})", eff)
    return out


def knows(tribe, oid: str) -> bool:
    return oid in (getattr(tribe, "operations", None) or [])


def next_op(tribe):
    for o in OPS:
        if not knows(tribe, o[0]):
            return o
    return None


def _sync(state, tribe) -> None:
    """Les effets en vigueur : la base (sauf pendant une reforme) et les
    operations connues."""
    from src.kora import tech

    ids = [f"op:{o}" for o in (tribe.operations or [])]
    if tribe.base and state.tick_count >= getattr(tribe, "base_reform_until", -1):
        ids.append(f"base:{tribe.base}")
    if ids != list(tribe.math_effects or []):
        tribe.math_effects = ids
        tech.invalidate()


def choose_block(state, tid: int, base: int) -> str:
    tribe = state.tribes.get(tid)
    from src.kora import tech

    if tribe is None or base not in BASES:
        return "?"
    if not tech.bonuses(tribe).numbers:
        return "Il faut connaître Nombres additifs"
    if tribe.base == base:
        return "C'est déjà votre base"
    if not tribe.base:
        return ""
    # Changer : une reforme, tres lourde.
    if state.tick_count - getattr(tribe, "base_changed", -10 ** 6) < REFORM_EVERY:
        return "Une réforme des nombres a eu lieu il y a moins de 30 ans"
    if tribe.prestige < REFORM_PRESTIGE:
        return f"Changer de base : il faut {REFORM_PRESTIGE} de prestige"
    return ""


def choose(state, tid: int, base: int) -> str:
    """Choisir sa base (la premiere fois : tout de suite) ; en changer : une
    reforme (prestige, trois ans sans l'avantage de la base)."""
    why = choose_block(state, tid, base)
    if why:
        return why
    tribe = state.tribes[tid]
    name = BASES[base][0]
    if tribe.base:
        tribe.prestige -= REFORM_PRESTIGE
        tribe.base_reform_until = state.tick_count + REFORM_WEEKS
        tribe.base_changed = state.tick_count
        tribe.base = base
        _sync(state, tribe)
        _note(state, tid, f"Réforme des nombres : désormais la {name.lower()}. Trois ans pour réapprendre à compter.")
        return f"Réforme : {name.lower()} (trois ans sans son avantage)."
    tribe.base = base
    tribe.base_changed = state.tick_count
    _sync(state, tribe)
    _note(state, tid, f"Vos nombres se comptent désormais en {name.lower()}.")
    return f"Vos nombres : {name.lower()}."


def ai_base(state, tribe) -> int:
    """L'IA : sa base selon son pays (le commerce, le grain, les gens)."""
    from src.kora.peoples import culture_of

    label = culture_of(tribe).label.lower()
    if "steppe" in label or "côte" in label or "cote" in label:
        return 12
    if "vallée" in label or "vallee" in label:
        return 60
    if "forêt" in label or "foret" in label:
        return 20
    return 10


def points(state, tid: int) -> float:
    """Points de calcul par mois : les equipes de calculateurs du peuple (et
    la base dix, les gages payes)."""
    from src.kora import goods, money, tech

    tribe = state.tribes.get(tid)
    if tribe is None:
        return 0.0
    n = sum(
        goods.teams_of(s, "calculateurs")
        for s in state.sites.values()
        if s.kind == "village" and s.tribe_id == tid
    )
    return n * TEAM_POINTS * tech.bonuses(tribe).learn * money.wage_mult(state, tid, "calcul")


def monthly(state) -> None:
    from src.kora import tech

    for tid in sorted(state.tribes):
        tribe = state.tribes[tid]
        b = tech.bonuses(tribe)
        if b.math and not knows(tribe, "add"):
            tribe.operations = ["add"] + [o for o in (tribe.operations or []) if o != "add"]
        if b.numbers and not tribe.base and not tribe.is_player:
            choose(state, tid, ai_base(state, tribe))
        elif b.numbers and not tribe.base and (state.tick_count // 4) % 13 == 0:
            # Le joueur : un rappel, tous les ans, tant qu'il n'a pas choisi.
            _note(state, tid, "Vos nombres attendent leur base : Savoirs, onglet « Les nombres ».")
        nxt = next_op(tribe)
        if b.numbers and nxt is not None and nxt[3] > 0:
            tribe.math_progress = getattr(tribe, "math_progress", 0.0) + points(state, tid)
            if tribe.math_progress >= nxt[3]:
                tribe.math_progress = 0.0
                tribe.operations = list(tribe.operations or []) + [nxt[0]]
                _note(state, tid, f"Vos calculateurs ont trouvé la {nxt[1].lower()} ({nxt[2]}) : {nxt[5]}")
        _sync(state, tribe)


def lines(state, tid: int) -> list[str]:
    tribe = state.tribes.get(tid)
    if tribe is None:
        return []
    ops = " ".join(OP_BY_ID[o][2] for o in (tribe.operations or []) if o in OP_BY_ID)
    base = BASES[tribe.base][0] if tribe.base else "pas encore de base"
    return [f"Nombres : {base} · opérations {ops or 'aucune'}"]


def _note(state, tid: int, text: str) -> None:
    from src.kora.gamestate import is_human, note

    if is_human(state, tid):
        note(state, LogKind.DECOUVERTE, text, to=tid)


def teams(state, tid: int) -> int:
    from src.kora import goods

    return sum(
        goods.teams_of(s, "calculateurs") for s in state.sites.values() if s.kind == "village" and s.tribe_id == tid
    )


def page(state, tid: int) -> dict:
    """Ce que montre l'onglet des nombres (render_numbers.py)."""
    from src.kora import tech

    tribe = state.tribes.get(tid)
    if tribe is None:
        return {}
    b = tech.bonuses(tribe)
    nxt = next_op(tribe)
    ops = []
    for oid, name, sign, cost, eff, text in OPS:
        if knows(tribe, oid):
            st = "connue"
        elif nxt is not None and nxt[0] == oid and b.numbers:
            st = "en_cours"
        else:
            st = "a_trouver"
        ops.append({"id": oid, "name": name, "sign": sign, "cost": cost, "text": text, "state": st, "effect": f"op:{oid}"})
    reform = max(0, getattr(tribe, "base_reform_until", -1) - state.tick_count)
    return {
        "math": b.math,
        "numbers": b.numbers,
        "base": tribe.base,
        "reform_weeks": reform,
        "blocks": {base: choose_block(state, tid, base) for base in BASE_ORDER},
        "ops": ops,
        "progress": getattr(tribe, "math_progress", 0.0),
        "goal": nxt[3] if nxt is not None else 0,
        "points": points(state, tid),
        "teams": teams(state, tid),
    }


# --- ce que les nombres ajoutent aux evenements (events.vocabulary) -------------------


def _ev_math_points(state, inst, tribe, band, n) -> None:
    tribe.math_progress = getattr(tribe, "math_progress", 0.0) + n


EVENT_EFFECTS = {"math_points": _ev_math_points}
EVENT_TEXTS = {"math_points": lambda a: f"+{a[0]:g} points de calcul"}
