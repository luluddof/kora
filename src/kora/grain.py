"""LE GRAIN DES DISETTES : l'argent sauve des vies.

Un village en DISETTE (moins de DEARTH_WEEKS semaines de vivres, ou la faim
ce mois-ci) ACHETE DU GRAIN a un peuple qui en a de trop : un partenaire
(accord commercial), un allie, un peuple de son pays (suzerain, tributaire,
confedere) - meme sans route ouverte, a portee de porteurs (deux fois la
portee des routes, goods.trade_range). Les deux peuples connaissent les
Valeurs d'echange (un tresor : money.py) ; ils ne sont pas en guerre.

  Combien : de quoi remplir GRAIN_WEEKS semaines de vivres du village, ce
    que le vendeur peut ceder (au-dela de KEEP_WEEKS semaines de reserve
    dans chacun de ses villages) et ce que le tresor peut payer.
  Le prix : plus cher que le marche (money.VPS vivres pour un sicle) :
    un sicle ne donne plus que VPS / (MARKUP + SCARCITY x la part de ce que
    le vendeur a de trop qu'on lui prend + WINTER en hiver) vivres.
    Plus on lui prend, plus c'est cher : le grain est rare.
  Le vendeur gagne les sicles ; l'acheteur s'en souvient (+5, sans cumuler).

L'IA : un village IA qui a faim (ou moins d'AI_DEARTH_WEEKS semaine de
vivres) achete s'il a de quoi (money.reserve n'est pas garde : on sauve
d'abord des vies) ; un peuple IA
vend tant que l'acheteur ne lui est pas hostile (relation >= SELL_RELATION).
Tout passe par commands.py ("grain"). N'importe pas pygame.
"""

from __future__ import annotations

from src.kora import chiefdom, diplo, goods, money, places, siege
from src.kora.bands import stock_max
from src.kora.gamestate import is_human, note
from src.kora.log import LogKind
from src.kora.types import Season

DEARTH_WEEKS = 3
AI_DEARTH_WEEKS = 1
GRAIN_WEEKS = 8
KEEP_WEEKS = 10
MARKUP = 1.5
SCARCITY = 1.0
WINTER = 0.5
SELL_RELATION = -10
GRATITUDE = 5
MIN_BUY = 10.0
REACH = 2


def in_dearth(state, band) -> bool:
    if band is None or not band.village or band.population <= 0:
        return False
    return band.famine_in_period or band.stock < DEARTH_WEEKS * band.population


def _knows_money(state, tid: int) -> bool:
    return money.has_money(state, tid)


def sellers(state, tid: int) -> list[int]:
    """Les peuples qui pourraient lui vendre du grain."""
    country = chiefdom.country(state, tid)
    out = []
    for other in sorted(state.tribes):
        if other == tid or not goods.has_village(state, other) or not _knows_money(state, other):
            continue
        if siege.at_war(state, tid, other) or diplo.declared_war(state, tid, other):
            continue
        linked = diplo.has_pact(state, tid, other, "commerce") or diplo.allied(state, tid, other) or other in country
        if not linked:
            continue
        if diplo.relation(state, other, tid) < SELL_RELATION:
            continue
        out.append(other)
    return out


def spare(state, seller: int) -> float:
    """Ce que le vendeur peut ceder (au-dela de KEEP_WEEKS semaines)."""
    total = 0.0
    for band in goods._food_spare(state, seller):
        if not in_dearth(state, band):
            total += max(0.0, band.stock - KEEP_WEEKS * band.population)
    return total


def _near(state, site, seller: int) -> bool:
    reach = goods.trade_range(state, site.tribe_id, seller) * REACH
    return any(state.world.distance(site.hex, s.hex) <= reach for s in goods._village_sites(state, seller))


def _markup(state, site, take: float, have: float) -> float:
    m = MARKUP + SCARCITY * (take / have if have > 0 else 1.0)
    if state.world.hex_season(site.hex) is Season.HIVER:
        m += WINTER
    return m


def quote(state, tid: int, site_id: int) -> dict:
    """{"seller", "vivres", "sicles", "per_sicle", "why"} : le meilleur achat
    possible pour ce village ("why" : pourquoi rien, sinon "")."""
    out = {"seller": 0, "vivres": 0.0, "sicles": 0.0, "per_sicle": 0.0, "why": ""}
    site = state.sites.get(site_id)
    band = places.band_of(state, site) if site is not None else None
    if band is None or site.tribe_id != tid:
        out["why"] = "Pas votre village"
        return out
    if not _knows_money(state, tid):
        out["why"] = "Il faut un trésor (Valeurs d'échange) pour acheter du grain"
        return out
    if not in_dearth(state, band):
        out["why"] = f"Pas de disette : le village a plus de {DEARTH_WEEKS} semaines de vivres"
        return out
    want = min(GRAIN_WEEKS * band.population - band.stock, stock_max(band, state) - band.stock)
    if want < MIN_BUY:
        out["why"] = "Le grenier est plein"
        return out
    tribe = state.tribes[tid]
    best = None
    for other in sellers(state, tid):
        if not _near(state, site, other):
            continue
        have = spare(state, other)
        if have < MIN_BUY:
            continue
        take = min(want, have)
        m = _markup(state, site, take, have)
        cost = take * m / money.VPS
        if cost > tribe.money:
            take = tribe.money * money.VPS / m
            cost = tribe.money
        if take < MIN_BUY:
            continue
        rate = take / cost if cost > 0 else 0.0
        key = (-rate, -take, other)
        if best is None or key < best[0]:
            best = (key, other, take, cost, rate)
    if best is None:
        if not sellers(state, tid):
            out["why"] = "Aucun partenaire, allié ni peuple de votre pays n'a de trésor"
        elif tribe.money * money.VPS / (MARKUP + SCARCITY) < MIN_BUY:
            out["why"] = "Le trésor est vide"
        else:
            out["why"] = "Personne à portée n'a de grain de trop"
        return out
    _key, other, take, cost, rate = best
    out.update(seller=other, vivres=round(take, 1), sicles=round(cost, 2), per_sicle=round(rate, 1))
    return out


def buy(state, tid: int, site_id: int) -> str:
    """Acheter : rend "" ou pourquoi c'est impossible."""
    q = quote(state, tid, site_id)
    if q["why"]:
        return q["why"]
    site = state.sites[site_id]
    band = places.band_of(state, site)
    seller = q["seller"]
    take, cost = q["vivres"], q["sicles"]
    # Le grain quitte les greniers du vendeur, les mieux pourvus d'abord.
    left = take
    for b in sorted(goods._food_spare(state, seller), key=lambda b: (-(b.stock - KEEP_WEEKS * b.population), b.id)):
        if in_dearth(state, b):
            continue
        give = min(left, max(0.0, b.stock - KEEP_WEEKS * b.population))
        b.stock -= give
        left -= give
        if left <= 1e-9:
            break
    got = take - max(0.0, left)
    band.stock = min(stock_max(band, state), band.stock + got)
    buyer = state.tribes[tid]
    buyer.money -= cost
    money.book(state, tid, "grain", -cost)
    money.earn(state, seller, "grain", cost)
    diplo.add_mod(state, tid, seller, "grain", GRATITUDE, actor=seller)
    sname, bname = state.tribes[seller].name, buyer.name
    if is_human(state, tid):
        price = f"{cost:.1f}".replace(".", ",")
        note(state, LogKind.SURVIE, f"{places.name(site)} achète {got:.0f} vivres de grain aux {sname} pour {price} sicles.", site.hex, to=tid)
    if is_human(state, seller):
        price = f"{cost:.1f}".replace(".", ",")
        note(state, LogKind.POLITIQUE, f"Les {bname}, en disette, vous achètent {got:.0f} vivres de grain : {price} sicles.", site.hex, to=seller)
    return ""


def ai_weekly(state) -> None:
    """Les villages IA en disette achetent du grain s'ils le peuvent."""
    for site in sorted(state.sites.values(), key=lambda s: s.id):
        if site.kind != "village":
            continue
        tribe = state.tribes.get(site.tribe_id)
        if tribe is None or tribe.is_player or not _knows_money(state, tribe.id):
            continue
        band = places.band_of(state, site)
        if band is None or tribe.money < 1.0:
            continue
        # L'IA attend la vraie faim (ou moins d'AI_DEARTH_WEEKS de vivres).
        if band.famine_in_period or band.stock < AI_DEARTH_WEEKS * band.population:
            buy(state, tribe.id, site.id)


def tip_lines(state, tid: int, site_id: int) -> list[str]:
    """Pour la tuile du grenier (ecran du village)."""
    q = quote(state, tid, site_id)
    if q["why"]:
        return [q["why"]]
    sname = state.tribes[q["seller"]].name
    return [
        f"Acheter du grain aux {sname} : {q['vivres']:.0f} vivres pour {q['sicles']:.1f} sicles".replace(".", ","),
        f"{q['per_sicle']:.1f} vivres le sicle (le marché : {money.VPS:.0f}) : plus cher que le marché, et plus encore si l'on prend beaucoup de ce qu'ils ont de trop ou en hiver".replace(".", ","),
    ]
