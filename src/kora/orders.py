"""Ordres du joueur a une bande : ce qu'elle peut faire, et sinon pourquoi.

Chaque action rend "" si elle est possible, sinon la raison (affichee au
survol du bouton de la fiche de bande). Un clan indocile n'obeit plus :
seuls "honorer" et "le chef vient ici" restent possibles (c'est ainsi
qu'on le regagne). Une troupe (villages.py) ne campe pas, ne se scinde
pas, ne fonde rien : elle se bat, rentre au village ou y est rappelee.
N'importe ni pygame ni render.
"""

from __future__ import annotations

from src.kora import ai_war, battle, chiefs, diplo, ost, places, sites, villages
from src.kora.path import astar, travel_weeks
from src.kora.bands import (
    campaign_weeks,
    SPLIT_MIN_POP,
    can_split,
    civ_band_cap,
    civ_band_count,
    max_bands_of,
    merge_bands,
    merge_mates,
    split_band,
    stock_max,
    tribe_band_count,
    welded_left,
)
from src.kora.peoples import civ_of

ACTIONS = ("split", "merge", "next", "chief", "village", "camp", "deposit", "withdraw", "honor", "army")
INDOCILE = "Ce clan n'obéit plus (attachement trop bas)"
GRANARY = "Au village, les vivres sont au grenier"
TROOP_CAMP = "Une troupe ne campe pas"


def obeys(state, band) -> bool:
    return chiefs.obeys(state, band)


def _mates(state, band) -> int:
    """Bandes a regrouper avec celle-ci (proches, meme genre ; merge_bands)."""
    return len(merge_mates(state, band))


HOMEBOUND = "Dissoute, la troupe rentre au village"


def _army_actions(state, band) -> dict[str, str]:
    own = sum(1 for b in state.bands.values() if b.tribe_id == band.tribe_id and b.population > 0)
    out = {
        "split": villages.detach_block(state, band.id),
        "next": "" if own > 1 else "Une seule bande",
        "chief": chiefs.can_move_chief(state, band.id),
        "village": "Une troupe ne fonde pas de village",
        "camp": TROOP_CAMP,
        "deposit": TROOP_CAMP,
        "withdraw": TROOP_CAMP,
        # Une troupe n'a pas a etre honoree : ce bouton appelle l'ost.
        "honor": ost.call_block(state, band.id),
        "army": villages.dissolve_block(state, band.id),
    }
    if band.homebound:
        for key in ("split", "merge", "chief", "army", "honor"):
            out[key] = HOMEBOUND
        return out
    if band.retreating:
        out["merge"] = "La troupe est en repli"
    elif villages.disband_block(state, band.id) == "" or _mates(state, band):
        out["merge"] = ""
    else:
        out["merge"] = "Aucune troupe sur cette case (au village : rentrer)"
    return out


def band_actions(state, band_id: int) -> dict[str, str]:
    band = state.bands.get(band_id)
    if band is None:
        return {k: "Pas de bande" for k in ACTIONS}
    if battle.in_battle(state, band):
        # En bataille : rien d'autre que le repli (fenetre de la bataille).
        out = {k: "En bataille : ordonnez le repli d'abord" for k in ACTIONS}
        out["next"] = ""
        return out
    if band.kind == "armee":
        return _army_actions(state, band)
    own = sum(1 for b in state.bands.values() if b.tribe_id == band.tribe_id and b.population > 0)
    out: dict[str, str] = {}
    listens = obeys(state, band)
    retreat = "La bande est en repli" if band.retreating else ""
    if not listens:
        out["split"] = INDOCILE
    elif retreat:
        out["split"] = retreat
    elif can_split(state, band_id):
        out["split"] = ""
    else:
        if welded_left(state, band):
            out["split"] = f"Le groupe vient d'être réuni (encore {welded_left(state, band)} sem.)"
        elif band.population < SPLIT_MIN_POP:
            out["split"] = f"Il faut {SPLIT_MIN_POP} personnes"
        else:
            civ = civ_of(state, state.tribes[band.tribe_id])
            out["split"] = (
                f"Votre civilisation est au complet : {civ_band_count(state, civ)}/{civ_band_cap(state, civ)} "
                "bandes et villages (tous ses peuples)"
            )
    out["merge"] = INDOCILE if not listens else retreat or ("" if _mates(state, band) else "Aucune bande de votre peuple à 5 cases")
    tribe = state.tribes.get(band.tribe_id)
    if tribe is not None and tribe.flags.get("isoles", -1) > state.tick_count and not out["merge"]:
        # Le mal qui court (situations.py) : les malades vivent a part.
        out["merge"] = "Les malades sont isolés : pas de réunion pour l'instant"
    out["next"] = "" if own > 1 else "Une seule bande"
    out["chief"] = chiefs.can_move_chief(state, band_id)
    if not listens:
        out["village"] = INDOCILE
    elif band.village:
        out["village"] = ""
    else:
        out["village"] = villages.found_block(state, band_id)
    if not listens:
        out["army"] = INDOCILE
    elif band.village:
        out["army"] = villages.army_block(state, band_id)
    else:
        out["army"] = "Seul un village leve des guerriers"
    here = sites.own_site_at(state, band)
    if not listens:
        out["camp"] = out["deposit"] = out["withdraw"] = INDOCILE
    elif band.village:
        out["camp"] = "Le village est fixe"
        out["deposit"] = out["withdraw"] = GRANARY
    else:
        if here is not None and here.kind == "camp":
            out["camp"] = ""
        else:
            out["camp"] = sites.camp_block(state, band_id)
        out["deposit"] = sites.deposit_block(state, band_id)
        out["withdraw"] = sites.withdraw_block(state, band_id)
    out["honor"] = chiefs.can_honor(state, band_id)
    return out


def camp_label(state, band_id: int) -> str:
    band = state.bands.get(band_id)
    if band is not None:
        here = sites.own_site_at(state, band)
        if here is not None and here.kind == "camp":
            return "Lever le camp"
    return "Camper [C]"


def hints(state, band_id: int) -> dict:
    """Ce que fait une action possible (au survol du bouton), quand son nom
    ne suffit pas."""
    band = state.bands.get(band_id)
    if band is not None and band.kind == "armee":
        return {
            "honor": f"Appeler l'ost : les troupes de vos tributaires à {ost.OST_RANGE} cases viennent se fondre dans celle-ci (vous les menez, vous payez leur solde)",
        }
    return {}


def labels(state, band_id: int) -> dict:
    """Libelles qui changent selon la bande (village, troupe, campement)."""
    band = state.bands.get(band_id)
    out = {"camp": camp_label(state, band_id)}
    if band is not None and band.village:
        out["split"] = "Former bande"
        out["village"] = "Gérer [V]"
        out["army"] = "Lever [L]"
    elif band is not None and band.kind == "armee":
        out["split"] = "Détacher [S]"
        at_home = villages.disband_block(state, band_id) == "" and not _mates(state, band)
        out["merge"] = "Rentrer [F]" if at_home else "Réunir [F]"
        out["army"] = "Dissoudre [L]"
        out["honor"] = "Ost [H]"
    return out


def perform(state, band_id: int, key: str):
    """Execute l'action ; rend (bande a selectionner, message ou "")."""
    if key == "leave":
        # Quitter le village (ecran du village), a confirmer dans l'app.
        band = state.bands.get(band_id)
        reason = villages.leave_block(state, band_id)
        if not reason and not obeys(state, band):
            reason = INDOCILE
    else:
        reason = band_actions(state, band_id).get(key, "?")
    if reason:
        return band_id, reason
    band = state.bands[band_id]

    if key == "split":
        if band.kind == "armee":
            part = villages.detach(state, band_id)
            return (part.id if part is not None else band_id), ""
        nid = split_band(state, band_id)
        return (nid if nid is not None else band_id), ""
    if key == "merge":
        if band.kind == "armee" and villages.disband_block(state, band_id) == "" and not _mates(state, band):
            site = villages._village_near(state, band)
            villages.disband(state, band_id)
            home = places.band_of(state, site) if site is not None else None
            return (home.id if home is not None else band_id), ""
        merge_bands(state, band_id)
        return band_id, ""
    if key == "chief":
        chiefs.move_chief(state, band_id)
        return band_id, ""
    if key == "camp":
        here = sites.own_site_at(state, band)
        if here is not None and here.kind == "camp":
            back = min(here.store, max(0.0, stock_max(band, state) - band.stock))
            band.stock += back
            sites.abandon(state, here.id)
            return band_id, ""
        sites.make_camp(state, band_id)
        return band_id, ""
    if key == "deposit":
        sites.deposit(state, band_id)
        return band_id, ""
    if key == "withdraw":
        sites.withdraw(state, band_id)
        return band_id, ""
    if key == "honor":
        if band.kind == "armee":
            n = ost.call(state, band_id)
            return band_id, "" if n else "Personne ne vient"
        chiefs.honor(state, band_id)
        return band_id, ""
    if key == "village":
        # Le village se gere dans son ecran (app) ; ici, fonder sans serment
        # (IA, tests : la fenetre de fondation passe par villages.found).
        if not band.village:
            villages.found(state, band_id)
        return band_id, ""
    if key == "army":
        if band.kind == "armee":
            site = villages._village_near(state, band)
            villages.dissolve(state, band_id)
            home = places.band_of(state, site) if site is not None and band_id not in state.bands else None
            return (home.id if home is not None else band_id), ""
        army = villages.raise_army(state, band_id)
        return (army.id if army is not None else band_id), ""
    if key == "leave":
        villages.leave(state, band_id)
        return band_id, ""
    return band_id, ""


# --- avant l'attaque : le rapport de force (le survol d'un etranger) --------------------
# Une de vos bandes choisie, la souris sur une bande etrangere : ce que
# donnerait l'attaque (le clic droit), compte comme l'IA le compte
# (ai_war.odds_at), et ce qui l'empeche ou la rend risquee.


def _fmt(x: float) -> str:
    return f"{x:.2f}".rstrip("0").rstrip(".").replace(".", ",")


def attack_preview(state, band_id: int, prey_id: int) -> dict | None:
    """{"title", "ratio", "word", "rows": [(texte, sorte)], "blocked"} ; sorte :
    "bon", "mauvais", "note", "alerte". None si ce n'est pas une attaque."""
    band, prey = state.bands.get(band_id), state.bands.get(prey_id)
    if band is None or prey is None or prey.population <= 0 or band.tribe_id == prey.tribe_id:
        return None
    me, them = band.tribe_id, prey.tribe_id
    tribe = state.tribes.get(them)
    who = tribe.name if tribe is not None else "?"
    what = places.name(places.site_of(state, prey)) if prey.village and places.site_of(state, prey) else (
        "leur troupe" if prey.kind == "armee" else "leur clan"
    )
    out = {"title": f"Attaquer les {who} ({what}) : clic droit", "rows": [], "blocked": ""}
    # Ce qui l'empeche (comme l'ordre de marche : commands._march).
    if not chiefs.obeys(state, band):
        out["blocked"] = INDOCILE
    elif band.village:
        out["blocked"] = "Un village ne bouge pas : formez une bande [S] pour attaquer"
    elif band.homebound:
        out["blocked"] = HOMEBOUND
    elif diplo.may_start(state, me, them):
        out["blocked"] = diplo.may_start(state, me, them)
    elif diplo.needs_declaration(state, me, them) and not diplo.declared_war(state, me, them) and not diplo.at_war(state, me, them):
        out["blocked"] = f"Vous êtes en paix avec les {who} : déclarez-leur d'abord la guerre (écran Peuples)"
    ratio, word = ai_war.odds_at(state, band, prey)
    out["ratio"], out["word"] = ratio, word
    rows = out["rows"]
    tone = "bon" if ratio >= 1.3 else "mauvais" if ratio < 0.85 else "alerte"
    rows.append((f"Rapport de force : {_fmt(ratio)} contre 1, {word}", tone))
    helpers = ai_war.helpers_at(state, [band], prey.position)
    mine = round(battle.fighters_now(band, True) + sum(battle.fighters_now(b, True) for b in helpers))
    rows.append((f"Vos combattants : {mine}" + (f" (dont {len(helpers)} bande{'s' if len(helpers) > 1 else ''} en renfort près d'eux)" if helpers else ""), "note"))
    guards = battle.helpers_of(state, prey)
    theirs = round(battle.fighters_now(prey, False) + sum(battle.fighters_now(b, False) for b in guards))
    rows.append((f"Les leurs : {theirs}" + (f" (dont {len(guards)} bande{'s' if len(guards) > 1 else ''} en renfort)" if guards else ""), "note"))
    cover = battle.cover_parts(state, prey, prey.position, me)
    if cover:
        rows.append(("Leur abri : " + " · ".join(f"{label} x{_fmt(m)}" for label, m in cover), "note"))
    m_me, _p = battle.start_morale(state, band, attacker=True, h=prey.position)
    m_them, _p2 = battle.start_morale(state, prey, attacker=False, h=prey.position)
    rows.append((f"Moral : le vôtre {m_me:.0f}, le leur {m_them:.0f}", "note"))
    # Le trajet et les vivres.
    water = bool(state.tribes[me].cabotage) if me in state.tribes else False
    path = astar(state.world, band.position, prey.position, max_nodes=4000, water_ok=water, costs=ai_war.costs_of(state, me))
    food = campaign_weeks(state, band)
    if path is None:
        rows.append(("Pas de chemin connu jusqu'à eux", "alerte"))
    else:
        weeks = travel_weeks(state.world, band.position, path, water_ok=water, costs=ai_war.costs_of(state, me))
        text = f"Trajet : ~{weeks} sem."
        if band.kind == "armee":
            back = villages.weeks_home(state, band, prey.position)
            stock = f"{food:.0f} sem." if food >= 1 else "moins d'une semaine"
            text += f" ; vivres : {stock} ; retour au village : ~{back} sem."
            rows.append((text, "alerte" if food < weeks + back else "note"))
            if food < weeks + back:
                rows.append(("Vos vivres ne tiendront pas l'aller et le retour : la troupe aura faim", "mauvais"))
        else:
            rows.append((text, "note"))
    if prey.kind != "armee" and not prey.village:
        rows.append(("Un clan peut fuir avant votre arrivée", "note"))
    if not out["blocked"] and diplo.peace_pact(state, me, them):
        rows.append(("Un pacte vous lie : attaquer serait une trahison (prestige -10)", "mauvais"))
    return out
