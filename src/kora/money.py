"""L'ARGENT d'un peuple : son tresor et son budget.

Avec Valeurs d'echange (neolithique), un peuple a un TRESOR (Tribe.money,
en sicles : d'abord des valeurs - perles, coquillages, haches polies -,
puis, avec Argent pese, le metal des collines, pese a la balance). Chaque
mois, son BUDGET (Tribe.budget) :

  RENTREES
    l'impot en argent  une part sur chaque villageois (Leger, Moyen, Lourd) :
                       la stabilite baisse d'autant ; Argent pese : +25 %
    les mines          les mineurs d'argent (goods.py : "mineurs", sur les
                       filons des collines : resources.derive_silver)
    le commerce        les routes vendues en argent (au lieu des vivres) quand
                       les deux peuples ont l'argent et que l'acheteur le veut
    le tribut          10 % du tresor de ses tributaires
    les peages         Droits de passage : les convois etrangers qui
                       traversent son pays (sa zone d'influence) paient un
                       demi-sicle par convoi et 10 % de leur charge
  DEPENSES
    la solde           payer les troupes levees : moral +5, deux fois moins de
                       fuyards ; promise et pas payee : moral -5, plus de fuyards
    les gages          payer les gens de metier : metiers +10 %, calculateurs
                       +25 % ; promis et pas payes : -10 %
    les presents       aux familles qui comptent (chiefdom.py) : 3 % du tresor
                       par mois (au moins un sicle par famille) ; leur faveur
                       monte, la stabilite des villages aussi (+3)

L'IA tient son budget selon son chef. Tout passe par commands.py ("budget").
N'importe pas pygame.
"""

from __future__ import annotations

from src.kora.log import LogKind
from src.kora.types import Hex
from src.kora.gamestate import is_human, note
from src.kora import chiefdom, chiefs, goods, influence, tech

# Vivres pour un sicle (payer une route en argent, convertir un peage).
VPS = 20.0
TAX = {0: 0.0, 1: 0.02, 2: 0.04, 3: 0.07}
TAX_STAB = {0: 0, 1: -3, 2: -6, 3: -10}
TAX_NAMES = {0: "Aucun", 1: "Léger", 2: "Moyen", 3: "Lourd"}
SILVER_TAX = 1.25
SOLDE = 0.08
GAGE = 0.06
TOLL = 0.10
# Et un droit fixe par convoi qui passe (sicles).
TOLL_FLAT = 0.5
SILVER_OUT = 0.6
VASSAL_SHARE = 0.10
DON_SHARE = 0.03
DON_MIN = 1.0
DON_FAVOUR = 1.5
DON_STABILITY = 3
HISTORY = 24
DEFAULT = {"tax": 0, "solde": False, "gages": False, "commerce": False, "dons": False}
TOGGLE_KEYS = ("solde", "gages", "commerce", "dons")


def has_money(state, tid: int) -> bool:
    tribe = state.tribes.get(tid)
    return tribe is not None and tech.bonuses(tribe).money


def budget(tribe) -> dict:
    b = dict(DEFAULT)
    b.update(getattr(tribe, "budget", None) or {})
    return b


def set_budget(state, tid: int, key: str, value) -> str:
    tribe = state.tribes.get(tid)
    if tribe is None or not has_money(state, tid):
        return "Il faut connaître Valeurs d'échange"
    b = budget(tribe)
    if key == "tax":
        v = int(value)
        if v not in TAX:
            return "?"
        b["tax"] = v
        msg = f"Impôt : {TAX_NAMES[v].lower()}."
    elif key in TOGGLE_KEYS:
        b[key] = bool(value)
        if key == "dons":
            msg = "Le chef fera des présents aux familles." if b[key] else "Plus de présents aux familles."
        else:
            msg = {"solde": "Les troupes", "gages": "Les gens de métier", "commerce": "Le commerce"}[key]
            msg += " seront payés en argent." if b[key] else (" ne seront plus payés." if key != "commerce" else " se paiera en vivres.")
    else:
        return "?"
    tribe.budget = b
    tech.invalidate()
    return msg


# --- ce qui compte ---------------------------------------------------------------


def _villages(state, tid: int) -> list:
    return sorted((s for s in state.sites.values() if s.kind == "village" and s.tribe_id == tid), key=lambda s: s.id)


def villagers(state, tid: int) -> int:
    return goods.villagers(state, tid)


def soldiers(state, tid: int) -> int:
    return sum(b.population for b in state.bands.values() if b.tribe_id == tid and b.kind == "armee" and b.population > 0)


def specialists(state, tid: int) -> int:
    return sum(goods.TEAM * goods.total_teams(s) for s in _villages(state, tid))


def tax_income(state, tid: int) -> float:
    tribe = state.tribes.get(tid)
    if tribe is None or not has_money(state, tid):
        return 0.0
    level = budget(tribe)["tax"]
    b = tech.bonuses(tribe)
    return villagers(state, tid) * TAX[level] * b.tax * (SILVER_TAX if b.silver else 1.0)


def solde_cost(state, tid: int) -> float:
    return soldiers(state, tid) * SOLDE


def gage_cost(state, tid: int) -> float:
    return specialists(state, tid) * GAGE


def don_cost(state, tid: int) -> float:
    tribe = state.tribes.get(tid)
    if tribe is None or not tribe.families:
        return 0.0
    return max(DON_MIN * len(tribe.families), getattr(tribe, "money", 0.0) * DON_SHARE)


def stability_parts(state, tid: int) -> list[tuple[str, float]]:
    tribe = state.tribes.get(tid)
    if tribe is None or not has_money(state, tid):
        return []
    b = budget(tribe)
    level = b["tax"]
    out = [(f"Impôt {TAX_NAMES[level].lower()}", float(TAX_STAB[level]))] if level else []
    if b.get("etat_dons") == "payee":
        out.append(("Les présents du chef", float(DON_STABILITY)))
    return out


def _paid(tribe, key: str) -> str:
    return (getattr(tribe, "budget", None) or {}).get("etat_" + key, "")


def wage_mult(state, tid: int, kind: str = "metier") -> float:
    """Les gens de metier payes travaillent mieux ; promis et pas payes,
    moins bien."""
    tribe = state.tribes.get(tid)
    if tribe is None:
        return 1.0
    s = _paid(tribe, "gages")
    if s == "payee":
        return 1.25 if kind == "calcul" else 1.1
    if s == "impayee":
        return 0.9
    return 1.0


def craft_output(state, site, craft) -> float:
    """Les gages payes (systems.CRAFT_OUTPUT)."""
    return wage_mult(state, site.tribe_id)


def solde_morale(state, tid: int) -> float:
    tribe = state.tribes.get(tid)
    s = _paid(tribe, "solde") if tribe is not None else ""
    return 5.0 if s == "payee" else -5.0 if s == "impayee" else 0.0


def flee_mult(state, tid: int) -> float:
    tribe = state.tribes.get(tid)
    s = _paid(tribe, "solde") if tribe is not None else ""
    return 0.5 if s == "payee" else 1.3 if s == "impayee" else 1.0


def book(state, tid: int, key: str, amount: float) -> None:
    """Noter une rentree (+) ou une depense (-) du mois."""
    tribe = state.tribes.get(tid)
    if tribe is None or not amount:
        return
    month = tribe.money_month if getattr(tribe, "money_month", None) is not None else {}
    month[key] = round(month.get(key, 0.0) + amount, 3)
    tribe.money_month = month


def earn(state, tid: int, key: str, amount: float) -> None:
    tribe = state.tribes.get(tid)
    if tribe is None or amount <= 0:
        return
    tribe.money = getattr(tribe, "money", 0.0) + amount
    book(state, tid, key, amount)


# --- le commerce en argent, les peages ---------------------------------------------


def pays_in_money(state, payer: int, receiver: int) -> bool:
    tribe = state.tribes.get(payer)
    return bool(
        tribe is not None and has_money(state, payer) and has_money(state, receiver) and budget(tribe)["commerce"]
    )


def pay_route(state, payer: int, receiver: int, vivres: float) -> float:
    """Payer en argent une dette de route (en vivres) : rend ce qui a ete
    paye (en vivres equivalents) ; le reste se paiera en vivres."""
    tribe = state.tribes.get(payer)
    if tribe is None or vivres <= 0:
        return 0.0
    sicles = min(tribe.money, vivres / VPS)
    if sicles <= 0:
        return 0.0
    tribe.money -= sicles
    book(state, payer, "achats", -sicles)
    earn(state, receiver, "ventes", sicles)
    return sicles * VPS


def toll_owner(state, route) -> int:
    """Le peuple qui tient le passage d'une route : celui qui domine le
    milieu du chemin entre les deux villages (Droits de passage)."""
    ends = goods.trade_ends(state, route.exporter, route.importer)
    if ends is None:
        return 0
    a, b = ends
    for frac in (0.5, 0.33, 0.67):
        h = Hex(round(a.q + (b.q - a.q) * frac), round(a.r + (b.r - a.r) * frac))
        h = state.world.canonicalize(h)
        if h is None:
            continue
        tid, v = influence.dominant(state.world, h)
        if tid and tid not in (route.exporter, route.importer) and v >= influence.ZONE_MIN:
            other = state.tribes.get(tid)
            if other is not None and tech.bonuses(other).tolls:
                return tid
    return 0


def collect_tolls(state) -> None:
    """Chaque mois, apres les routes : les convois qui ont porte paient leur
    passage a qui tient le chemin."""
    for r in sorted(goods.all_routes(state), key=lambda r: (r.exporter, r.importer, r.good)):
        if r.paid <= 0:
            continue
        owner = toll_owner(state, r)
        if not owner:
            continue
        exp = state.tribes.get(r.exporter)
        if exp is None:
            continue
        sicles = r.paid * TOLL / VPS + TOLL_FLAT * max(1, getattr(r, "level", 1))
        due = sicles * VPS
        if getattr(exp, "money", 0.0) >= sicles:
            exp.money -= sicles
            book(state, r.exporter, "peages", -sicles)
            earn(state, owner, "peages", sicles)
        else:
            # Sans argent, le passage se paie en vivres.
            goods._pay(state, r.exporter, owner, due)


# --- le mois -----------------------------------------------------------------------


def monthly(state) -> None:
    """Le budget de chaque peuple qui a l'argent : l'impot, le tribut, la
    solde, les gages ; l'histoire du tresor."""
    for tid in sorted(state.tribes):
        tribe = state.tribes[tid]
        if not has_money(state, tid):
            continue
        if not tribe.is_player:
            _ai(state, tribe)
        if not tribe.money_hist:
            _note(state, tid, "Valeurs d'échange : votre peuple possède un trésor. Impôt, solde, gages, présents : l'écran du Trésor [G].")
        b = budget(tribe)
        earn(state, tid, "impot", tax_income(state, tid))
        # Le tribut en argent de ses tributaires.
        for v in chiefdom.vassals_of(state, tid):
            vt = state.tribes.get(v)
            if vt is not None and getattr(vt, "money", 0.0) > 1.0:
                part = vt.money * VASSAL_SHARE * tech.bonuses(tribe).vassal_tribute
                vt.money -= part
                book(state, v, "tribut", -part)
                earn(state, tid, "tribut", part)
        for key, cost in (("solde", solde_cost(state, tid)), ("gages", gage_cost(state, tid)), ("dons", don_cost(state, tid))):
            if not b[key] or cost <= 0:
                b["etat_" + key] = ""
                continue
            if tribe.money >= cost:
                tribe.money -= cost
                book(state, tid, key, -cost)
                b["etat_" + key] = "payee"
                if key == "dons":
                    for fam in tribe.families or []:
                        fam["favour"] = round(min(100.0, fam["favour"] + DON_FAVOUR), 2)
            elif key == "dons":
                # Pas de quoi faire des presents : on n'en fait pas (rien n'est promis).
                b["etat_" + key] = ""
            else:
                if b.get("etat_" + key) != "impayee":
                    what = "la solde des troupes" if key == "solde" else "les gages des gens de métier"
                    _note(state, tid, f"Le trésor est vide : {what} n'est pas payée.")
                b["etat_" + key] = "impayee"
        tribe.budget = b
        month = getattr(tribe, "money_month", None) or {}
        income = sum(v for v in month.values() if v > 0)
        spent = -sum(v for v in month.values() if v < 0)
        hist = list(getattr(tribe, "money_hist", None) or [])
        hist.append([state.clock.year, state.clock.week, round(income, 2), round(spent, 2), round(tribe.money, 2), dict(month)])
        tribe.money_hist = hist[-HISTORY:]
        tribe.money_month = {}


def reserve(state, tid: int) -> float:
    """Ce qu'un tresor prudent garde : un an de solde et de gages."""
    return 12.0 * (solde_cost(state, tid) + gage_cost(state, tid)) + 30.0


def _ai(state, tribe) -> None:
    """L'IA : l'impot selon son chef et ce qu'elle a deja (un tresor plein
    n'a pas besoin d'impot), la solde quand elle a des troupes, les gages
    quand le tresor le permet, les presents quand il deborde, le commerce en
    argent toujours."""
    b = budget(tribe)
    chief = chiefs.chief_of(state, tribe.id)
    traits = chief.traits if chief is not None else ()
    tax = 2 if "ambitieux" in traits else 0 if "genereux" in traits else 1
    keep = reserve(state, tribe.id)
    if tribe.money > 4 * keep:
        tax = 0
    elif tribe.money > 2 * keep:
        tax = min(tax, 1)
    b["tax"] = tax
    b["solde"] = soldiers(state, tribe.id) > 0 and tribe.money > solde_cost(state, tribe.id) * 3
    b["gages"] = tribe.money > (gage_cost(state, tribe.id) + solde_cost(state, tribe.id)) * 6
    b["dons"] = bool(tribe.families) and tribe.money > 2 * keep
    b["commerce"] = True
    tribe.budget = b


def last_month(tribe) -> dict:
    hist = getattr(tribe, "money_hist", None) or []
    return dict(hist[-1][5]) if hist else {}


def _note(state, tid: int, text: str) -> None:
    if is_human(state, tid):
        note(state, LogKind.POLITIQUE, text, to=tid)


KEY_NAMES = {
    "impot": "Impôt",
    "mines": "Mines d'argent",
    "ventes": "Ventes en argent",
    "achats": "Achats en argent",
    "tribut": "Tribut",
    "peages": "Droits de passage",
    "solde": "Solde des troupes",
    "gages": "Gages des gens de métier",
    "evenements": "Événements",
    "dons": "Présents aux familles",
}


# --- ce que l'argent ajoute aux evenements (events.vocabulary) ----------------------


def _ev_has_money(state, inst, tribe, band) -> bool:
    return has_money(state, tribe.id)


def _ev_money_ge(state, inst, tribe, band, n) -> bool:
    return getattr(tribe, "money", 0.0) >= n


def _ev_money(state, inst, tribe, band, amount) -> None:
    if amount > 0:
        earn(state, tribe.id, "evenements", amount)
    else:
        take = min(getattr(tribe, "money", 0.0), -amount)
        tribe.money -= take
        book(state, tribe.id, "evenements", -take)


def _ev_money_pct(state, inst, tribe, band, pct) -> None:
    take = getattr(tribe, "money", 0.0) * -pct
    if take > 0:
        tribe.money -= take
        book(state, tribe.id, "evenements", -take)


EVENT_CONDITIONS = {"has_money": _ev_has_money, "money_ge": _ev_money_ge}
EVENT_EFFECTS = {"money": _ev_money, "money_pct": _ev_money_pct}
EVENT_TEXTS = {
    "money": lambda a: f"{'+' if a[0] >= 0 else ''}{a[0]:g} sicles au trésor",
    "money_pct": lambda a: f"{round(a[0] * 100)} % du trésor",
}
