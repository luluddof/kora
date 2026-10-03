"""Les ordres des joueurs, par un seul canal (multijoueur).

Tout ce que l'interface change a la partie passe par un ordre. En solo, il
s'applique tout de suite. En reseau (net.py), il part chez l'hote, qui le
renvoie a tous avec la semaine ou l'appliquer : chaque machine applique les
memes ordres, dans le meme ordre, au meme moment, et calcule donc la meme
partie (lockstep).

Un ordre est une liste JSON : [peuple, genre, args...]. apply() verifie que
le joueur commande bien ce qui est a lui (un ordre refuse l'est pareil sur
chaque machine) et rend {"msg": texte, "sel": bande, "site": lieu}.
N'importe ni pygame ni render.
"""

from __future__ import annotations

from src.kora import (
    battle,
    chiefdom,
    chiefs,
    diplo,
    events,
    goods,
    learning,
    money,
    numbers,
    orders,
    situations,
    tech,
    villages,
)
from src.kora.types import Hex
from src.kora.bands import set_goto, set_march_to_band

KINDS = (
    "goto", "march", "band", "found", "route_open", "route_close", "route_level",
    "teams", "diplo", "invite", "build", "raise", "reequip", "dissolve",
    "honor", "promote", "heir", "learn", "event", "situation",
    "battle_retreat", "levy_rate", "feast", "charge", "base", "budget",
)
IN_BATTLE = "En bataille : ordonnez le repli d'abord"
NOT_YOURS = "Ce n'est pas à vous"


def make(tid: int, kind: str, *args) -> list:
    assert kind in KINDS, kind
    return [int(tid), kind, *args]


def _out(msg: str = "", sel=None, site=None) -> dict:
    return {"msg": msg or "", "sel": sel, "site": site}


def _own_band(state, tid: int, band_id):
    band = state.bands.get(int(band_id)) if band_id is not None else None
    if band is None or band.population <= 0:
        return None, "Cette bande n'existe plus"
    if band.tribe_id != tid:
        return None, NOT_YOURS
    return band, ""


def _route(state, key):
    exporter, importer, good = int(key[0]), int(key[1]), str(key[2])
    return next((r for r in goods.all_routes(state) if (r.exporter, r.importer, r.good) == (exporter, importer, good)), None)


def route_key(route) -> list:
    return [route.exporter, route.importer, route.good]


def apply(state, cmd) -> dict:
    """Applique un ordre ; rend ce que l'interface en dit (msg, sel, site)."""
    try:
        tid, kind, args = int(cmd[0]), str(cmd[1]), list(cmd[2:])
    except (TypeError, ValueError, IndexError):
        return _out("Ordre illisible")
    if tid not in state.tribes or not state.tribes[tid].is_player and tid != 1:
        return _out("Ce peuple n'est pas mené par un joueur")
    handler = _HANDLERS.get(kind)
    if handler is None:
        return _out("Ordre inconnu")
    try:
        return handler(state, tid, *args)
    except (TypeError, ValueError, KeyError, IndexError):
        # Un ordre mal forme (autre version ?) ne casse pas la partie.
        return _out("Ordre refuse")


# --- les bandes ------------------------------------------------------------------------


def _goto(state, tid, band_id, q, r):
    band, why = _own_band(state, tid, band_id)
    if band is None:
        return _out(why)
    if not chiefs.obeys(state, band):
        return _out(orders.INDOCILE + " : rapprochez le chef ou honorez le clan.")
    if band.village:
        return _out("Un village ne bouge pas : formez une bande [S] pour partir.")
    if band.homebound:
        return _out(orders.HOMEBOUND + ".")
    if battle.in_battle(state, band):
        return _out(IN_BATTLE + ".")
    set_goto(state, band.id, Hex(int(q), int(r)))
    return _out()


def _march(state, tid, band_id, target_id):
    band, why = _own_band(state, tid, band_id)
    if band is None:
        return _out(why)
    target = state.bands.get(int(target_id))
    if target is None or target.population <= 0:
        return _out("Cette bande n'est plus la")
    if not chiefs.obeys(state, band):
        return _out(orders.INDOCILE + ".")
    if band.village:
        return _out("Un village ne bouge pas : formez une bande [S] pour aller raider.")
    if band.homebound:
        return _out(orders.HOMEBOUND + ".")
    set_march_to_band(state, band.id, target.id)
    return _out()


def _band(state, tid, band_id, action):
    band, why = _own_band(state, tid, band_id)
    if band is None:
        return _out(why)
    if action not in orders.ACTIONS and action != "leave":
        return _out("?")
    sel, msg = orders.perform(state, band.id, action)
    return _out(msg, sel=sel)


def _found(state, tid, band_id, oath):
    band, why = _own_band(state, tid, band_id)
    if band is None:
        return _out(why)
    if oath not in villages.OATHS:
        return _out("Choisissez d'abord le serment du village.")
    why = villages.found_block(state, band.id)
    if why:
        return _out(why)
    name = villages.propose_name(state, band.id)
    site = villages.found(state, band.id, oath=oath, name_=name)
    return _out(site=site.id if site is not None else None)


# --- le commerce ---------------------------------------------------------------------------


def _route_open(state, tid, partner, good, sell, level):
    partner, sell, level = int(partner), bool(sell), int(level)
    why = goods.open_block(state, tid, partner, good, sell, level)
    if why:
        return _out(why)
    route = goods.open_route(state, tid, partner, good, sell, level)
    if route is None:
        return _out()
    return _out(f"Route ouverte : {goods.route_text(state, tid, route).lower()} (chaque mois).")


def _route_close(state, tid, key):
    route = _route(state, key)
    if route is None:
        return _out("Cette route n'existe plus")
    text = goods.route_text(state, tid, route).lower()
    if goods.close_route(state, tid, route):
        return _out(f"Route fermée : {text}.")
    return _out()


def _route_level(state, tid, key, level):
    route = _route(state, key)
    if route is None:
        return _out("Cette route n'existe plus")
    why = goods.level_block(state, tid, route, int(level))
    if why:
        return _out(why)
    goods.set_level(state, tid, route, int(level))
    return _out()


def _village_of(state, tid, site_id):
    site = state.sites.get(int(site_id))
    home = villages.band_of(state, site) if site is not None and site.kind == "village" else None
    if home is None:
        return None, None, "Ce village n'existe plus"
    if site.tribe_id != tid or home.tribe_id != tid:
        return None, None, NOT_YOURS
    return site, home, ""


def _teams(state, tid, site_id, cid, delta):
    site, home, why = _village_of(state, tid, site_id)
    if site is None:
        return _out(why)
    if not chiefs.obeys(state, home):
        return _out(orders.INDOCILE)
    n = goods.teams_of(site, cid)
    if int(delta) > 0:
        why = goods.add_block(state, site, cid)
        if why:
            return _out(why)
        goods.set_teams(state, site, cid, n + 1)
    elif n > 0:
        goods.set_teams(state, site, cid, n - 1)
    return _out()


# --- les autres peuples ------------------------------------------------------------------------


def _diplo(state, tid, target, action, amount=0.0):
    target = int(target)
    if target not in state.tribes:
        return _out("Ce peuple a disparu")
    if action not in diplo.ACTIONS:
        return _out("?")
    if action != "rompre" and action != "cadeau" and diplo.on_cooldown(state, tid, target, action):
        return _out("Vous avez déjà proposé cela récemment.")
    return _out(diplo.perform(state, tid, target, action, float(amount)))


def _invite(state, tid, band_id):
    return _out(diplo.invite(state, tid, int(band_id)))


# --- les villages, les troupes ------------------------------------------------------------------


def _build(state, tid, band_id, building):
    band, why = _own_band(state, tid, band_id)
    if band is None:
        return _out(why)
    why = villages.build_block(state, band.id, building) or ("" if chiefs.obeys(state, band) else orders.INDOCILE)
    if why:
        return _out(why)
    villages.build(state, band.id, building)
    return _out()


def _raise(state, tid, band_id, size, type_id):
    band, why = _own_band(state, tid, band_id)
    if band is None:
        return _out(why)
    share = villages.LEVY_SHARE.get(size, villages.LEVY_SHARE["troupe"])
    why = villages.army_block(state, band.id, share, type_id) or ("" if chiefs.obeys(state, band) else orders.INDOCILE)
    if why:
        return _out(why)
    army = villages.raise_army(state, band.id, share, type_id)
    return _out(sel=army.id if army is not None else None)


def _reequip(state, tid, band_id):
    band, why = _own_band(state, tid, band_id)
    if band is None:
        return _out(why)
    why = villages.reequip_block(state, band.id)
    if why:
        return _out(why)
    villages.reequip(state, band.id)
    return _out()


def _dissolve(state, tid, band_id):
    band, why = _own_band(state, tid, band_id)
    if band is None:
        return _out(why)
    why = villages.dissolve_block(state, band.id)
    if why:
        return _out(why)
    villages.dissolve(state, band.id)
    return _out()


# --- les clans, les savoirs, les cartes -------------------------------------------------------------


def _honor(state, tid, band_id):
    band, why = _own_band(state, tid, band_id)
    if band is None:
        return _out(why)
    why = chiefs.can_honor(state, band.id)
    if why:
        return _out(why)
    chiefs.honor(state, band.id)
    return _out()


def _promote(state, tid, band_id, pid):
    band, why = _own_band(state, tid, band_id)
    if band is None:
        return _out(why)
    why = chiefs.can_promote(state, band.id, int(pid))
    if why:
        return _out(why)
    chiefs.promote(state, band.id, int(pid))
    return _out()


def _heir(state, tid, band_id):
    band, why = _own_band(state, tid, band_id)
    if band is None:
        return _out(why)
    chiefs.set_heir(state, band.id)
    return _out()


def _learn(state, tid, tech_id):
    learning.choose(state, tid, str(tech_id))
    return _out()


def _event(state, tid, uid, index):
    inst = events.find(state, int(uid))
    if inst is None:
        return _out()
    if inst.tribe_id != tid:
        return _out(NOT_YOURS)
    return _out(events.choose(state, inst.uid, int(index)))


def _situation(state, tid, uid, action):
    return _out(situations.act(state, int(uid), tid, str(action)))


def _battle_retreat(state, tid, band_id):
    band, why = _own_band(state, tid, band_id)
    if band is None:
        return _out(why)
    return _out(battle.ask_retreat(state, tid, band.id))


def _levy_rate(state, tid, rate):
    return _out(chiefdom.set_rate(state, tid, int(rate)))


def _feast(state, tid):
    return _out(chiefdom.feast(state, tid))


def _charge(state, tid, fam_id, charge):
    return _out(chiefdom.set_charge(state, tid, int(fam_id), str(charge)))


def _base(state, tid, base):
    return _out(numbers.choose(state, tid, int(base)))


def _budget(state, tid, key, value):
    return _out(money.set_budget(state, tid, str(key), value))


_HANDLERS = {
    "base": _base,
    "budget": _budget,
    "battle_retreat": _battle_retreat,
    "levy_rate": _levy_rate,
    "feast": _feast,
    "charge": _charge,
    "goto": _goto,
    "march": _march,
    "band": _band,
    "found": _found,
    "route_open": _route_open,
    "route_close": _route_close,
    "route_level": _route_level,
    "teams": _teams,
    "diplo": _diplo,
    "invite": _invite,
    "build": _build,
    "raise": _raise,
    "reequip": _reequip,
    "dissolve": _dissolve,
    "honor": _honor,
    "promote": _promote,
    "heir": _heir,
    "learn": _learn,
    "event": _event,
    "situation": _situation,
}
assert set(_HANDLERS) == set(KINDS)
