"""L'EXISTANT : chaque interface du jeu telle qu'elle est aujourd'hui, sur SA
partie (copie), pour comparer avec les propositions du rework.
python maq_existant.py RACINE SAUVEGARDE SORTIE"""
import sys

import maq_commun as commun
from maq_commun import pygame

from src.kora import events, screens, troupes
from src.kora.events_data import EVENTS
from src.kora.partie import fresh_ui

st, play, r = commun.load(sys.argv[2], sys.argv[3])
OUT = sys.argv[3]
me = st.viewer
village = next(s for s in sorted(st.sites.values(), key=lambda s: s.id) if s.kind == "village" and s.tribe_id == me)


def shot(name, side=None, **ui):
    play.ui = fresh_ui()
    play.ui.update(ui)
    play.side_panel = side
    for _ in range(2):
        play._frame(1 / 60)
    commun.save(r.screen, f"{OUT}/{name}.png")


shot("01_carte")
for i, side in enumerate(("savoirs", "tribu", "peuples", "journal")):
    shot(f"02_panneau_{side}", side)
for page in ("village", "batiments", "metiers", "chef"):
    shot(f"03_village_{page}", village_open=village.id, village_page=page)
for name, key in (("commerce", "trade_open"), ("tresor", "treasury_open"), ("pays", "country_open"), ("decisions", "decisions_open")):
    shot(f"04_{name}", **{key: True})
shot("04_armee_guerres", wars_open=True, war_pick="armee")
# Une troupe choisie : la carte de l'unite en bas.
home = next(b for b in st.bands.values() if b.tribe_id == me and b.village)
army = troupes.raise_army(st, home.id)
if army is not None:
    play.selected = army.id
    shot("05_unite_choisie")
    play.selected = None
# Une carte d'evenement ouverte.
inst = events._new_instance(st, EVENTS["visiteurs"], me, home.id)
events.fire(st, inst)
shot("06_evenement", event_open=inst.uid)
shot("06_evenement_ferme")
play.menu_open = True if hasattr(play, "menu_open") else None
shot("07_menu")
