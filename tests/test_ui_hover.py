"""La souris partout : chaque ecran se dessine sans erreur quel que soit ce
qu'elle survole (les fiches au survol n'apparaissent qu'ainsi ; une erreur
dans l'une d'elles faisait planter le jeu, ecran Peuples, 0.5.0)."""

import os

os.environ.setdefault("SDL_VIDEODRIVER", "dummy")

import pygame

from src.kora import battle, session, situations
from src.kora.app import _fresh_ui, _start_view, _first_player_band
from src.kora.render import Renderer
from src.kora.gamestate import PLAYER_TRIBE_ID
from test_ui_pure import _advanced

W, H = 1280, 720
STEP = 72


def test_every_screen_survives_the_mouse_everywhere(monkeypatch):
    st = _advanced()
    st.story = True
    pygame.init()
    r = Renderer(pygame.display.set_mode((W, H)))
    _s, sel, cx, cy, zoom, yaw, pitch = _start_view(st, _first_player_band(st), W, H)
    mine = [s for s in st.sites.values() if s.kind == "village" and s.tribe_id == PLAYER_TRIBE_ID]
    others = sorted(t for t in st.tribes if t != PLAYER_TRIBE_ID)[:3]
    home = next(b for b in st.bands.values() if b.tribe_id == PLAYER_TRIBE_ID)
    inst = situations._start(st, situations.SPECS["passage"], home.position, 6, [PLAYER_TRIBE_ID] + others[:1], {"dq": 1, "dr": 0})
    # Les nombres et l'argent (0.7.0) : une base, des operations, un tresor
    # qui a deja un mois de comptes.
    from src.kora import money, numbers, tech

    me = st.tribes[PLAYER_TRIBE_ID]
    me.knowledge.update(("comptage", "nombres", "valeurs", "argent_pese", "peages"))
    tech.invalidate()
    numbers.monthly(st)
    numbers.choose(st, PLAYER_TRIBE_ID, 60)
    me.operations = ["add", "sub"]
    me.math_progress = 12.0
    me.money = 42.0
    money.set_budget(st, PLAYER_TRIBE_ID, "impot", 4)
    money.set_budget(st, PLAYER_TRIBE_ID, "solde", 1.5)
    money.set_budget(st, PLAYER_TRIBE_ID, "chantiers", 1.0)
    # Une confederation et un tributaire (0.9.0) : les couleurs des pays.
    from src.kora import chiefdom, diplo

    diplo.add_pact(st, others[0], others[1], "confederation", payer=others[0])
    chiefdom.make_vassal(st, others[1], others[2], "force")
    money.monthly(st)
    money.earn(st, PLAYER_TRIBE_ID, "mines", 3.0)
    money.monthly(st)
    screens = [("savoirs", {"tech_tab": "nombres"}), (None, {"treasury_open": True})]
    screens.append((None, {"country_open": True, "law_confirm": ("base", "12")}))
    screens.append(("suzerains", {}))
    for pick in others[:2]:
        screens.append(("peuples", {"people_pick": pick}))
    for panel in ("tribu", "savoirs", "journal", "armee"):
        screens.append((panel, {}))
    for page in ("village", "metiers", "chef"):
        screens.append((None, {"village_open": mine[0].id, "village_page": page}))
    screens.append((None, {"trade_open": True, "trade_partner": others[0]}))
    screens.append((None, {"situation_open": inst.uid}))
    screens.append(("battle", {}))
    before = session.sync_digest(st)
    pos = {"xy": (0, 0)}
    monkeypatch.setattr(pygame.mouse, "get_pos", lambda: pos["xy"])
    for panel, extra in screens:
        ui = _fresh_ui()
        ui.update(extra)
        r.map_mode = "suzerains" if panel == "suzerains" else "zones"
        if panel == "suzerains":
            panel = None
        if panel == "battle":
            foe = next(b for b in st.bands.values() if b.tribe_id != PLAYER_TRIBE_ID and not b.village and b.population > 0)
            mine_band = next(b for b in st.bands.values() if b.tribe_id == PLAYER_TRIBE_ID and not b.village and b.kind != "armee")
            foe.position = mine_band.position
            bt = battle.start(st, foe, mine_band, mine_band.position, True)
            battle.day(st, bt)
            before = session.sync_digest(st)
            panel = None
        for x in range(4, W, STEP):
            for y in range(4, H, STEP):
                pos["xy"] = (x, y)
                r.draw(st, cx, cy, zoom, sel, False, yaw, pitch, panel, ui=ui)
    assert session.sync_digest(st) == before
