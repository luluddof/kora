"""Ordres du joueur a une bande : ce qu'elle peut faire, et sinon pourquoi.

Chaque action rend "" si elle est possible, sinon la raison (affichee au
survol du bouton de la fiche de bande). Un clan indocile n'obeit plus :
seuls "honorer" et "le chef vient ici" restent possibles (c'est ainsi
qu'on le regagne). Une troupe (villages.py) ne campe pas, ne se scinde
pas, ne fonde rien : elle se bat, rentre au village ou y est rappelee.
N'importe ni pygame ni render.
"""

from __future__ import annotations

from src.kora import chiefs, sites
from src.kora.sim import can_split, merge_bands, split_band

ACTIONS = ("split", "merge", "next", "chief", "village", "camp", "deposit", "withdraw", "honor", "army")
INDOCILE = "Ce clan n'obeit plus (attachement trop bas)"
GRANARY = "Au village, les vivres sont au grenier"
TROOP_CAMP = "Une troupe ne campe pas"


def obeys(state, band) -> bool:
    return chiefs.obeys(state, band)


def _mates(state, band) -> int:
    """Bandes a regrouper avec celle-ci (proches, meme genre ; merge_bands)."""
    from src.kora.sim import merge_mates

    return len(merge_mates(state, band))


HOMEBOUND = "Dissoute, la troupe rentre au village"


def _army_actions(state, band) -> dict[str, str]:
    from src.kora import villages

    own = sum(1 for b in state.bands.values() if b.tribe_id == band.tribe_id and b.population > 0)
    out = {
        "split": villages.detach_block(state, band.id),
        "next": "" if own > 1 else "Une seule bande",
        "chief": chiefs.can_move_chief(state, band.id),
        "village": "Une troupe ne fonde pas de village",
        "camp": TROOP_CAMP,
        "deposit": TROOP_CAMP,
        "withdraw": TROOP_CAMP,
        "honor": "Une troupe obeit sans qu'on l'honore",
        "army": villages.dissolve_block(state, band.id),
    }
    if band.homebound:
        for key in ("split", "merge", "chief", "army"):
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
        from src.kora.sim import SPLIT_MIN_POP, max_bands_of, tribe_band_count, welded_left

        if welded_left(state, band):
            out["split"] = f"Le groupe vient d'etre reuni (encore {welded_left(state, band)} sem.)"
        elif band.population < SPLIT_MIN_POP:
            out["split"] = f"Il faut {SPLIT_MIN_POP} personnes"
        else:
            from src.kora.peoples import civ_of
            from src.kora.sim import civ_band_cap, civ_band_count

            civ = civ_of(state, state.tribes[band.tribe_id])
            out["split"] = (
                f"Votre civilisation est au complet : {civ_band_count(state, civ)}/{civ_band_cap(state, civ)} "
                "bandes et villages (tous ses peuples)"
            )
    out["merge"] = INDOCILE if not listens else retreat or ("" if _mates(state, band) else "Aucune bande de votre peuple a 5 cases")
    out["next"] = "" if own > 1 else "Une seule bande"
    out["chief"] = chiefs.can_move_chief(state, band_id)
    from src.kora import villages

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


def labels(state, band_id: int) -> dict:
    """Libelles qui changent selon la bande (village, troupe, campement)."""
    band = state.bands.get(band_id)
    out = {"camp": camp_label(state, band_id)}
    if band is not None and band.village:
        out["split"] = "Former bande"
        out["village"] = "Gerer [V]"
        out["army"] = "Lever [L]"
    elif band is not None and band.kind == "armee":
        from src.kora import villages

        out["split"] = "Detacher [S]"
        at_home = villages.disband_block(state, band_id) == "" and not _mates(state, band)
        out["merge"] = "Rentrer [F]" if at_home else "Reunir [F]"
        out["army"] = "Dissoudre [L]"
    return out


def perform(state, band_id: int, key: str):
    """Execute l'action ; rend (bande a selectionner, message ou "")."""
    from src.kora import villages

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
            home = villages.band_of(state, site) if site is not None else None
            return (home.id if home is not None else band_id), ""
        merge_bands(state, band_id)
        return band_id, ""
    if key == "chief":
        chiefs.move_chief(state, band_id)
        return band_id, ""
    if key == "camp":
        here = sites.own_site_at(state, band)
        if here is not None and here.kind == "camp":
            from src.kora.sim import stock_max

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
            home = villages.band_of(state, site) if site is not None and band_id not in state.bands else None
            return (home.id if home is not None else band_id), ""
        army = villages.raise_army(state, band_id)
        return (army.id if army is not None else band_id), ""
    if key == "leave":
        villages.leave(state, band_id)
        return band_id, ""
    return band_id, ""
