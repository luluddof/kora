from __future__ import annotations

import pygame

from src.kora import chiefs, diplo, events, orders, tech
from src.kora.globe import (
    FOCUS_ZOOM,
    clamp_pitch,
    look_at_hex,
    orbit_sensitivity,
    pixel_to_hex_globe,
    view_params,
)
from src.kora.log import FILTER_ALL, LogKind
from src.kora.persist import default_save_path, load_game, save_game, set_aside_save
from src.kora.render import (
    HUD_HEIGHT,
    MAX_ZOOM,
    FILTER_BY_HIT,
    Renderer,
    band_card_hit,
    band_screen_positions,
    map_mode_hit,
    toast_hit,
    fight_mark_screen_pos,
    fight_panel_hit,
    hud_hit,
    menu_hit,
    min_zoom_for,
    side_hit,
)
from src.kora.sim import (
    PLAYER_TRIBE_ID,
    _default_world,
    consume_ticks,
    fight_at,
    hex_inspect,
    new_game,
    note,
    player_home_hex,
    set_goto,
    set_march_to_band,
)


TOAST_LIFE = 4.0
MAX_TOASTS = 4
# Deux clics sur la meme bande d'un peuple ami en moins de ce temps : on
# confirme le raid (et la trahison du pacte).
CONFIRM_SECONDS = 3.0
PANEL_KEYS = {
    pygame.K_t: "savoirs",
    pygame.K_b: "tribu",
    pygame.K_p: "peuples",
    pygame.K_j: "journal",
    pygame.K_a: "armee",
}
ACTION_KEYS = {
    pygame.K_s: "split",
    pygame.K_f: "merge",
    pygame.K_TAB: "next",
    pygame.K_c: "camp",
    pygame.K_k: "deposit",
    pygame.K_h: "honor",
    pygame.K_v: "village",
    pygame.K_l: "army",
}


def _look_hex(state, h):
    return look_at_hex(h, state.world.width, state.world.height)


def _look_band(state, selected):
    if selected is not None and selected in state.bands:
        return _look_hex(state, state.bands[selected].position)
    home = player_home_hex(state)
    if home is None:
        return 0.0, 0.0
    return _look_hex(state, home)


def _tribe_start_view(state, selected):
    return (*_look_band(state, selected), FOCUS_ZOOM)


def _band_at_pixel(state, x, y, zoom, globe_yaw, globe_pitch, sw, sh):
    hit = None
    best = 16.0
    gcx, gcy, focal, dist = view_params(zoom, sw, sh, HUD_HEIGHT)
    spots = band_screen_positions(state, globe_yaw, globe_pitch, gcx, gcy, focal, dist)
    for band_id, (bx, by, _radius) in spots.items():
        d = ((bx - x) ** 2 + (by - y) ** 2) ** 0.5
        if d < best:
            best = d
            hit = state.bands[band_id]
    return hit


def _fight_at_pixel(state, x, y, zoom, globe_yaw, globe_pitch, sw, sh):
    hit = None
    best = 16.0
    gcx, gcy, focal, dist = view_params(zoom, sw, sh, HUD_HEIGHT)
    for mark in state.fights:
        pos = fight_mark_screen_pos(
            mark, state.world, globe_yaw, globe_pitch, gcx, gcy, focal, dist
        )
        if pos is None:
            continue
        d = ((pos[0] - x) ** 2 + (pos[1] - y) ** 2) ** 0.5
        if d < best:
            best = d
            hit = mark
    return hit


def _player_band_ids(state) -> list[int]:
    return sorted(b.id for b in state.bands.values() if b.tribe_id == PLAYER_TRIBE_ID)


def _first_player_band(state):
    ids = _player_band_ids(state)
    return ids[0] if ids else None


def _refresh_selection(state, selected):
    # None = rien de selectionne, voulu par le joueur : un clic sur la carte
    # montre alors la case sans deplacer personne. Une bande disparue
    # (reunie, detruite, partie) passe la selection a une autre bande.
    if selected is None or (selected in state.bands and state.bands[selected].tribe_id == PLAYER_TRIBE_ID):
        return selected
    return _first_player_band(state)


def _next_player_band(state, selected):
    # Les villages se gerent dans leur ecran : Tab passe d'une bande a l'autre.
    ids = [i for i in _player_band_ids(state) if not state.bands[i].village] or _player_band_ids(state)
    if not ids:
        return None
    if selected not in ids:
        return ids[0]
    return ids[(ids.index(selected) + 1) % len(ids)]


def _view(camera_x, camera_y, zoom, selected, globe_yaw=0.0, globe_pitch=0.0):
    return {
        "camera_x": camera_x,
        "camera_y": camera_y,
        "zoom": zoom,
        "selected": selected,
        "globe_yaw": globe_yaw,
        "globe_pitch": globe_pitch,
    }


def _boot_state(sw: int, sh: int):
    path = default_save_path()
    world = _default_world()
    loaded = load_game(path, world)
    if loaded is None:
        moved = set_aside_save(path)
        # Un chargement rate a pu toucher le monde : on repart d'une carte propre.
        state = new_game(_default_world() if moved else world)
        if moved is not None:
            note(state, LogKind.DECOUVERTE, f"Ancienne sauvegarde mise de cote : {moved.name}")
        selected = _first_player_band(state)
        yaw, pitch, zoom = _tribe_start_view(state, selected)
        return state, selected, 0.0, 0.0, zoom, yaw, pitch
    state, _view_saved = loaded
    selected = _refresh_selection(state, _view_saved.get("selected"))
    yaw, pitch, zoom = _tribe_start_view(state, selected)
    zmin = min_zoom_for(state.world, sw, sh)
    zoom = min(MAX_ZOOM, max(zmin, zoom))
    return state, selected, 0.0, 0.0, zoom, yaw, pitch


def _nearest_band_of(state, tid: int, near):
    bands = [b for b in state.bands.values() if b.tribe_id == tid and b.population > 0]
    if not bands:
        return None
    if near is None:
        return min(bands, key=lambda b: b.id)
    return min(bands, key=lambda b: (state.world.distance(b.position, near), b.id))


def _settle_memory() -> None:
    """Le monde fait ~3 millions d'objets Python : un passage complet du
    ramasse-miettes coutait jusqu'a 0,5 s (une saccade). On les met a part
    une fois charges (gc.freeze) ; rien ne change au jeu."""
    import gc

    gc.unfreeze()
    gc.collect()
    gc.freeze()


def _in_rect(rect, mx, my) -> bool:
    x, y, w, h = rect
    return x <= mx <= x + w and y <= my <= y + h


def _fresh_ui() -> dict:
    # found : bande dont on fonde le village (fenetre de fondation) ;
    # village_open : lieu dont l'ecran est ouvert (render_village.py).
    return {
        "era": 0,
        "tribe_pick": None,
        "people_pick": None,
        "event_open": None,
        "found": None,
        "found_oath": None,
        "village_open": None,
        "village_pick": None,
        "village_page": "village",
        "trade_open": False,
        "trade_partner": None,
        "trade_good": None,
        "trade_sell": True,
        "trade_level": 1,
        "tech_cam": None,
        "levy": "troupe",
        "levy_role": "melee",
        "leave_confirm": 0.0,
    }


def run() -> None:
    pygame.init()
    pygame.display.set_caption("Kora")
    screen = pygame.display.set_mode((1280, 720), pygame.RESIZABLE)
    clock = pygame.time.Clock()
    sw, sh = screen.get_size()
    state, selected, camera_x, camera_y, zoom, globe_yaw, globe_pitch = _boot_state(
        sw, sh
    )
    _settle_memory()
    renderer = Renderer(screen)
    dragging = False
    drag_button = 0
    last_mouse = (0, 0)
    # La toile des savoirs se deplace a la souris (render.tech_panel_layout) :
    # on glisse depuis n'importe ou ; sans bouger, un clic choisit le savoir.
    tech_drag = 0
    tech_press = {"at": (0, 0), "moved": False, "pick": None}
    acc = 0.0
    save_path = default_save_path()
    last_auto = -1
    menu_open = False
    side_panel = None
    tech_pick = None
    log_filter = FILTER_ALL
    log_newest = True
    pinned_hex = None
    open_fight = None
    toasts: list[dict] = []
    last_log_seq = state.log.seq
    ui: dict = _fresh_ui()
    resume_after_event = False
    resume_after_found = False
    confirm = {"band": None, "until": 0.0}
    now = 0.0
    running = True

    def persist() -> None:
        save_game(
            state,
            save_path,
            _view(camera_x, camera_y, zoom, selected, globe_yaw, globe_pitch),
        )

    def toast(text: str, combat: bool = False) -> None:
        nonlocal toasts
        toasts.append({"text": text, "age": 0.0, "seq": -1, "hex": None, "combat": combat})
        toasts = toasts[-MAX_TOASTS:]

    def show_place(where) -> None:
        nonlocal globe_yaw, globe_pitch, open_fight, pinned_hex
        if where is None:
            return
        globe_yaw, globe_pitch = _look_hex(state, where)
        mark = fight_at(state, where)
        if mark is not None:
            open_fight = mark
        else:
            pinned_hex = where if hex_inspect(state, where) is not None else None

    def band_action(action: str, band_id=None) -> None:
        nonlocal selected, globe_yaw, globe_pitch
        target = selected if band_id is None else band_id
        if action == "next":
            selected = _next_player_band(state, selected)
            if selected is not None:
                globe_yaw, globe_pitch = _look_hex(state, state.bands[selected].position)
            return
        if target is None or target not in state.bands:
            return
        band = state.bands[target]
        if action == "village":
            why = orders.band_actions(state, target).get("village", "?")
            if why:
                toast(why)
            elif band.village:
                open_village(band.village)
            else:
                open_found(target)
            return
        new_sel, message = orders.perform(state, target, action)
        if message:
            toast(message)
        elif band_id is None:
            selected = new_sel

    def open_found(band_id) -> None:
        """Fonder un village : un choix qui arrete le temps."""
        nonlocal resume_after_found, side_panel
        if ui["found"] is None:
            resume_after_found = not state.clock.paused
            state.clock.paused = True
        ui["found"] = band_id
        ui["found_oath"] = None
        side_panel = None

    def close_found() -> None:
        nonlocal resume_after_found
        ui["found"] = None
        ui["found_oath"] = None
        if resume_after_found:
            state.clock.paused = False
        resume_after_found = False

    def open_village(site_id) -> None:
        nonlocal side_panel
        ui["village_open"] = site_id
        ui["village_pick"] = None
        ui["leave_confirm"] = 0.0
        ui["trade_open"] = False
        side_panel = None

    def trade_click(choice) -> None:
        """Clic dans l'ecran du commerce."""
        from src.kora import goods

        if choice == "tclose":
            ui["trade_open"] = False
            return
        if choice.startswith("tpartner:"):
            ui["trade_partner"] = int(choice.split(":")[1])
            return
        if choice.startswith("tgood:"):
            ui["trade_good"] = choice.split(":")[1]
            return
        if choice.startswith("tdir:"):
            ui["trade_sell"] = choice.endswith("sell")
            return
        if choice.startswith("tlevel:"):
            ui["trade_level"] = int(choice.split(":")[1])
            return
        if choice == "topen":
            partner = ui["trade_partner"]
            good = ui["trade_good"] or goods.GOODS[0]
            if partner is None:
                toast("Choisissez un partenaire (il faut un accord commercial).")
                return
            why = goods.open_block(state, PLAYER_TRIBE_ID, partner, good, ui["trade_sell"], ui["trade_level"])
            if why:
                toast(why)
                return
            route = goods.open_route(state, PLAYER_TRIBE_ID, partner, good, ui["trade_sell"], ui["trade_level"])
            if route is not None:
                toast(f"Route ouverte : {goods.route_text(state, PLAYER_TRIBE_ID, route).lower()} (chaque mois).")
            return
        if choice.startswith(("rlevel:", "rclose:")):
            parts = choice.split(":")
            idx = int(parts[1])
            if idx >= len(renderer.trade_routes):
                return
            route = renderer.trade_routes[idx]
            if choice.startswith("rclose:"):
                if goods.close_route(state, PLAYER_TRIBE_ID, route):
                    toast(f"Route fermee : {goods.route_text(state, PLAYER_TRIBE_ID, route).lower()}.")
                return
            level = int(parts[2])
            why = goods.level_block(state, PLAYER_TRIBE_ID, route, level)
            if why:
                toast(why)
            else:
                goods.set_level(state, PLAYER_TRIBE_ID, route, level)
            return
        if choice.startswith("tpropose:"):
            tid = int(choice.split(":")[1])
            if diplo.on_cooldown(state, PLAYER_TRIBE_ID, tid, "commerce"):
                toast("Vous avez deja propose cela recemment.")
            else:
                toast(diplo.perform(state, PLAYER_TRIBE_ID, tid, "commerce"))
            return

    def village_click(choice) -> None:
        """Clic dans l'ecran du village."""
        nonlocal selected, globe_yaw, globe_pitch
        from src.kora import villages

        site = state.sites.get(ui["village_open"])
        home = villages.band_of(state, site) if site is not None and site.kind == "village" else None
        if home is None or choice == "vclose":
            ui["village_open"] = None
            return
        if choice == "vleave":
            if now > ui["leave_confirm"]:
                ui["leave_confirm"] = now + CONFIRM_SECONDS
                toast("Abandonner le village ? Cliquez encore pour confirmer (champs et batiments perdus).", True)
                return
            ui["leave_confirm"] = 0.0
            _sel, message = orders.perform(state, home.id, "leave")
            if message:
                toast(message)
            else:
                ui["village_open"] = None
            return
        if choice.startswith("vb:"):
            ui["village_pick"] = choice[3:]
            return
        if choice.startswith("vpage:"):
            ui["village_page"] = choice[6:]
            return
        if choice == "vtrade":
            ui["village_open"] = None
            ui["trade_open"] = True
            return
        if choice.startswith(("vteam+:", "vteam-:")):
            from src.kora import goods

            cid = choice.split(":")[1]
            if not chiefs.obeys(state, home):
                toast(orders.INDOCILE)
                return
            n = goods.teams_of(site, cid)
            if choice.startswith("vteam+:"):
                why = goods.add_block(state, site, cid)
                if why:
                    toast(why)
                else:
                    goods.set_teams(state, site, cid, n + 1)
            elif n > 0:
                goods.set_teams(state, site, cid, n - 1)
            return
        if choice == "vsplit":
            new_sel, message = orders.perform(state, home.id, "split")
            if message:
                toast(message)
            elif new_sel != home.id:
                selected = new_sel
                ui["village_open"] = None
                toast(f"Une bande part de {villages.name(site)} : {state.bands[new_sel].population} personnes.")
            return
        if choice == "vbuild":
            pick = ui["village_pick"] or next(
                (b for b in villages.BUILD_ORDER if villages.building_status(state, site, b) == "possible"), None
            )
            if pick is None:
                return
            why = villages.build_block(state, home.id, pick) or ("" if chiefs.obeys(state, home) else orders.INDOCILE)
            if why:
                toast(why)
            else:
                villages.build(state, home.id, pick)
            return
        if choice.startswith("levy:"):
            ui["levy"] = choice[5:]
            return
        if choice.startswith("ltype:"):
            from src.kora import units

            role = choice[6:]
            if units.best(state.tribes[home.tribe_id], role) is None:
                toast("Aucune unite de ce role pour l'instant (voir les savoirs).")
            else:
                ui["levy_role"] = role
            return
        if choice == "vraise":
            from src.kora import units

            share = villages.LEVY_SHARE.get(ui["levy"], villages.LEVY_SHARE["troupe"])
            kind = units.best(state.tribes[home.tribe_id], ui.get("levy_role") or "melee")
            type_id = kind.id if kind is not None else None
            why = villages.army_block(state, home.id, share, type_id) or ("" if chiefs.obeys(state, home) else orders.INDOCILE)
            if why:
                toast(why)
            else:
                villages.raise_army(state, home.id, share, type_id)
            return
        if choice.startswith(("vsee:", "vrecall:", "vreequip:")):
            bid = int(choice.split(":")[1])
            army = state.bands.get(bid)
            if army is None:
                return
            if choice.startswith("vsee:"):
                selected = bid
                ui["village_open"] = None
                globe_yaw, globe_pitch = _look_hex(state, army.position)
            elif choice.startswith("vreequip:"):
                why = villages.reequip_block(state, bid)
                if why:
                    toast(why)
                else:
                    villages.reequip(state, bid)
            else:
                why = villages.dissolve_block(state, bid)
                if why:
                    toast(why)
                else:
                    villages.dissolve(state, bid)
            return

    def army_click(choice) -> None:
        """Clic dans le panneau Armee."""
        nonlocal selected, globe_yaw, globe_pitch, side_panel
        from src.kora import units, villages

        kind, _sep, rest = choice.partition(":")
        if kind == "arole":
            sid, role = rest.split(":")
            if units.best(state.tribes[PLAYER_TRIBE_ID], role) is None:
                toast("Aucune unite de ce role pour l'instant (voir les savoirs).")
            else:
                ui.setdefault("army_role", {})[int(sid)] = role
            return
        if kind == "asize":
            sid, key = rest.split(":")
            ui.setdefault("army_size", {})[int(sid)] = key
            return
        if kind in ("araise", "avillage"):
            site = state.sites.get(int(rest))
            home = villages.band_of(state, site) if site is not None and site.kind == "village" else None
            if home is None:
                return
            if kind == "avillage":
                side_panel = None
                open_village(site.id)
                return
            role = ui.get("army_role", {}).get(site.id, "melee")
            key = ui.get("army_size", {}).get(site.id, "troupe")
            unit = units.best(state.tribes[PLAYER_TRIBE_ID], role) or units.best(state.tribes[PLAYER_TRIBE_ID], "melee")
            share = villages.LEVY_SHARE.get(key, villages.LEVY_SHARE["troupe"])
            why = villages.army_block(state, home.id, share, unit.id) or ("" if chiefs.obeys(state, home) else orders.INDOCILE)
            if why:
                toast(why)
            else:
                villages.raise_army(state, home.id, share, unit.id)
            return
        bid = int(rest)
        army = state.bands.get(bid)
        if army is None:
            return
        if kind == "asee":
            selected = bid
            globe_yaw, globe_pitch = _look_hex(state, army.position)
            return
        why = villages.dissolve_block(state, bid)
        if why:
            toast(why)
        else:
            villages.dissolve(state, bid)

    def found_click(choice) -> None:
        from src.kora import villages

        if choice is None:
            return
        if choice == "found_cancel":
            close_found()
            return
        if choice.startswith("oath:"):
            ui["found_oath"] = choice[5:]
            return
        if choice == "found_ok":
            bid = ui["found"]
            if ui["found_oath"] not in villages.OATHS:
                toast("Choisissez d'abord le serment du village.")
                return
            why = villages.found_block(state, bid) if bid in state.bands else "Pas de bande"
            if why:
                toast(why)
                close_found()
                return
            name = villages.propose_name(state, bid)
            site = villages.found(state, bid, oath=ui["found_oath"], name_=name)
            close_found()
            if site is not None:
                open_village(site.id)

    def open_event(uid) -> None:
        nonlocal resume_after_event
        if events.find(state, uid) is None:
            return
        if ui["event_open"] is None:
            # Lire un evenement met en pause ; on reprend en le fermant.
            resume_after_event = not state.clock.paused
            state.clock.paused = True
        ui["event_open"] = uid

    def close_event() -> None:
        nonlocal resume_after_event
        ui["event_open"] = None
        if resume_after_event and not events.pending(state):
            state.clock.paused = False
        elif resume_after_event:
            state.clock.paused = False
        resume_after_event = False

    def order_move(hx) -> bool:
        band = state.bands.get(selected) if selected is not None else None
        if band is None:
            return False
        if not chiefs.obeys(state, band):
            toast(orders.INDOCILE + " : rapprochez le chef ou honorez le clan.")
            return False
        if band.village:
            toast("Un village ne bouge pas : formez une bande [S] pour partir.")
            return False
        if band.homebound:
            toast(orders.HOMEBOUND + ".")
            return False
        set_goto(state, selected, hx)
        return True

    def order_raid(target) -> None:
        band = state.bands.get(selected) if selected is not None else None
        if band is None:
            return
        if not chiefs.obeys(state, band):
            toast(orders.INDOCILE + ".")
            return
        if band.village:
            toast("Un village ne bouge pas : formez une bande [S] pour aller raider.")
            return
        if band.homebound:
            toast(orders.HOMEBOUND + ".")
            return
        if target.tribe_id != PLAYER_TRIBE_ID and diplo.at_peace(state, PLAYER_TRIBE_ID, target.tribe_id):
            name = state.tribes[target.tribe_id].name
            if confirm["band"] != target.id or now > confirm["until"]:
                confirm["band"] = target.id
                confirm["until"] = now + CONFIRM_SECONDS
                toast(f"Pacte avec les {name} : cliquez encore pour attaquer (trahison, prestige -10).", True)
                return
            confirm["band"] = None
        set_march_to_band(state, selected, target.id)

    def start_new() -> None:
        nonlocal state, selected, camera_x, camera_y, zoom, acc, last_auto
        nonlocal menu_open, globe_yaw, globe_pitch, side_panel
        nonlocal log_filter, log_newest, pinned_hex, toasts, last_log_seq, open_fight
        nonlocal tech_pick, ui
        state = new_game()
        _settle_memory()
        selected = _first_player_band(state)
        globe_yaw, globe_pitch, zoom = _tribe_start_view(state, selected)
        camera_x = 0.0
        camera_y = 0.0
        acc = 0.0
        last_auto = -1
        menu_open = False
        side_panel = None
        tech_pick = None
        log_filter = FILTER_ALL
        log_newest = True
        pinned_hex = None
        open_fight = None
        toasts = []
        last_log_seq = state.log.seq
        ui = _fresh_ui()
        persist()

    def side_click(choice) -> bool:
        """Clic dans un panneau lateral ; True si traite."""
        nonlocal side_panel, tech_pick, log_filter, log_newest, selected, globe_yaw, globe_pitch, tech_drag, last_mouse
        if not isinstance(choice, str):
            return False
        if choice in ("tview", "tminimap", "tzoom_in", "tzoom_out", "tcenter"):
            from src.kora import render_tech
            from src.kora.render import TREE_ZOOM_STEP, zoom_at

            lay = renderer.side_hits.get("tech")
            if not lay:
                return True
            mx, my = pygame.mouse.get_pos()
            view, world, cam = lay["view"], lay["world"], lay["cam"]
            if choice == "tview":
                # Glisser la toile (le clic gauche sur un savoir le choisit).
                tech_drag = 1
                last_mouse = (mx, my)
            elif choice == "tminimap":
                mx0, my0, mw, _mh = lay["minimap"]
                k = mw / world["size"][0]
                wx, wy = (mx - mx0) / k, (my - my0) / k
                ui["tech_cam"] = (wx - view[2] / (2 * cam[2]), wy - view[3] / (2 * cam[2]), cam[2])
            elif choice == "tcenter":
                ui["tech_cam"] = render_tech.focus_cam(state, *screen.get_size())
            else:
                factor = TREE_ZOOM_STEP if choice == "tzoom_in" else 1.0 / TREE_ZOOM_STEP
                ui["tech_cam"] = zoom_at(cam, view, world, view[0] + view[2] / 2, view[1] + view[3] / 2, factor)
            return True
        if choice.startswith("log_"):
            seq = int(choice[4:])
            entry = next((e for e in state.log.entries if e.seq == seq), None)
            if entry is not None:
                show_place(entry.hex)
            return True
        if choice.startswith("tab_"):
            key = choice[4:]
            if key == "commerce":
                ui["trade_open"] = not ui["trade_open"]
                ui["village_open"] = None
                side_panel = None
                return True
            side_panel = None if side_panel == key else key
            ui["village_open"] = None
            ui["trade_open"] = False
            return True
        if choice == "trade_with":
            ui["trade_open"] = True
            ui["trade_partner"] = ui.get("people_pick")
            side_panel = None
            return True
        if choice.startswith(("vil_open:", "vil_see:", "vil_row:")):
            sid = int(choice.split(":")[1])
            site = state.sites.get(sid)
            if site is not None and site.kind == "village":
                if choice.startswith("vil_see:"):
                    show_place(site.hex)
                else:
                    open_village(sid)
            return True
        if choice.startswith("tech:"):
            tech_pick = choice[5:]
            return True
        if choice.startswith("era:"):
            ui["era"] = int(choice[4:])
            tech_pick = None
            return True
        if choice == "learn":
            if tech_pick is not None:
                tech.choose(state, PLAYER_TRIBE_ID, tech_pick)
            return True
        if choice in FILTER_BY_HIT:
            log_filter = FILTER_BY_HIT[choice]
            return True
        if choice == "sort_recent":
            log_newest = True
            return True
        if choice == "sort_ancien":
            log_newest = False
            return True
        if choice.startswith("tribe_row:"):
            bid = int(choice.split(":")[1])
            ui["tribe_pick"] = bid
            return True
        if choice.startswith("tribe_see:"):
            bid = int(choice.split(":")[1])
            if bid in state.bands:
                selected = bid
                ui["tribe_pick"] = bid
                globe_yaw, globe_pitch = _look_hex(state, state.bands[bid].position)
            return True
        if choice.startswith("tribe_honor:"):
            bid = int(choice.split(":")[1])
            why = chiefs.can_honor(state, bid)
            if why:
                toast(why)
            else:
                chiefs.honor(state, bid)
            return True
        if choice.startswith(("arole:", "asize:", "araise:", "avillage:", "asee:", "adissolve:")):
            army_click(choice)
            return True
        if choice.startswith("promote:"):
            _k, bid, pid = choice.split(":")
            why = chiefs.can_promote(state, int(bid), int(pid))
            if why:
                toast(why)
            else:
                chiefs.promote(state, int(bid), int(pid))
            return True
        if choice.startswith("tribe_heir:"):
            bid = int(choice.split(":")[1])
            chiefs.set_heir(state, bid)
            return True
        if choice.startswith("people:"):
            ui["people_pick"] = int(choice.split(":")[1])
            return True
        if choice == "people_see":
            tid = ui.get("people_pick")
            home = state.bands[selected].position if selected in state.bands else player_home_hex(state)
            band = _nearest_band_of(state, tid, home) if tid is not None else None
            if band is not None:
                globe_yaw, globe_pitch = _look_hex(state, band.position)
            return True
        if choice.startswith("gift:"):
            tid = ui.get("people_pick")
            if tid is not None:
                toast(diplo.perform(state, PLAYER_TRIBE_ID, tid, "cadeau", float(choice.split(":")[1])))
            return True
        if choice.startswith("invite:"):
            toast(diplo.invite(state, PLAYER_TRIBE_ID, int(choice.split(":")[1])))
            return True
        if choice.startswith("diplo:"):
            tid = ui.get("people_pick")
            action = choice.split(":")[1]
            if tid is not None:
                if diplo.on_cooldown(state, PLAYER_TRIBE_ID, tid, action) and action not in ("rompre",):
                    toast("Vous avez deja propose cela recemment.")
                else:
                    toast(diplo.perform(state, PLAYER_TRIBE_ID, tid, action))
            return True
        return choice == "panel"

    while running:
        dt = clock.tick(60) / 1000.0
        now += dt
        sw, sh = screen.get_size()
        for event in pygame.event.get():
            if event.type == pygame.QUIT:
                persist()
                running = False
            elif event.type == pygame.KEYDOWN:
                if event.key == pygame.K_ESCAPE:
                    if ui["event_open"] is not None:
                        close_event()
                    elif ui["found"] is not None:
                        close_found()
                    elif ui["village_open"] is not None:
                        ui["village_open"] = None
                    elif ui["trade_open"]:
                        ui["trade_open"] = False
                    elif open_fight is not None:
                        open_fight = None
                    elif side_panel:
                        side_panel = None
                    elif pinned_hex is not None:
                        pinned_hex = None
                    else:
                        menu_open = not menu_open
                elif menu_open or ui["event_open"] is not None or ui["found"] is not None:
                    pass
                elif side_panel == "savoirs" and event.key in (
                    pygame.K_LEFT, pygame.K_RIGHT, pygame.K_UP, pygame.K_DOWN,
                    pygame.K_PLUS, pygame.K_KP_PLUS, pygame.K_EQUALS, pygame.K_MINUS, pygame.K_KP_MINUS,
                ):
                    # Fleches : se deplacer dans l'arbre ; + et - : zoomer.
                    from src.kora.render import TREE_ZOOM_STEP, pan, zoom_at

                    tlay = renderer.side_hits.get("tech")
                    if tlay:
                        view = tlay["view"]
                        step = {pygame.K_LEFT: (120, 0), pygame.K_RIGHT: (-120, 0), pygame.K_UP: (0, 90), pygame.K_DOWN: (0, -90)}.get(event.key)
                        if step is not None:
                            ui["tech_cam"] = pan(tlay["cam"], view, tlay["world"], *step)
                        else:
                            zin = event.key in (pygame.K_PLUS, pygame.K_KP_PLUS, pygame.K_EQUALS)
                            ui["tech_cam"] = zoom_at(tlay["cam"], view, tlay["world"], view[0] + view[2] / 2, view[1] + view[3] / 2, TREE_ZOOM_STEP if zin else 1.0 / TREE_ZOOM_STEP)
                elif event.key == pygame.K_SPACE:
                    state.clock.toggle_pause()
                elif event.key == pygame.K_F5:
                    persist()
                elif event.key in ACTION_KEYS:
                    band_action(ACTION_KEYS[event.key])
                elif event.key in PANEL_KEYS:
                    key = PANEL_KEYS[event.key]
                    from src.kora.render_panels import army_ready

                    if key == "armee" and not army_ready(state):
                        toast("L'armee vient avec le premier village.")
                        continue
                    side_panel = None if side_panel == key else key
                    ui["village_open"] = None
                elif event.key == pygame.K_m:
                    from src.kora.render_panels import commerce_ready

                    if not commerce_ready(state):
                        toast("Le commerce vient avec le premier village.")
                        continue
                    ui["trade_open"] = not ui["trade_open"]
                    ui["village_open"] = None
                    side_panel = None
                elif event.key == pygame.K_z:
                    renderer.map_mode = "relief" if renderer.map_mode == "zones" else "zones"
                elif event.key == pygame.K_r:
                    renderer.map_mode = "relief" if renderer.map_mode == "ressources" else "ressources"
                elif event.key == pygame.K_x:
                    renderer.map_mode = "relief" if renderer.map_mode == "commerce" else "commerce"
                elif event.key == pygame.K_e:
                    waiting = events.pending(state)
                    if waiting:
                        open_event(waiting[0].uid)
                elif event.key in (
                    pygame.K_1,
                    pygame.K_2,
                    pygame.K_3,
                    pygame.K_4,
                    pygame.K_5,
                ):
                    state.clock.set_speed(event.key - pygame.K_0)
            elif event.type == pygame.VIDEORESIZE:
                screen = pygame.display.set_mode((event.w, event.h), pygame.RESIZABLE)
                renderer.screen = screen
            elif menu_open:
                if event.type == pygame.MOUSEBUTTONDOWN and event.button == 1:
                    choice = menu_hit(renderer.menu_hits, event.pos[0], event.pos[1])
                    if choice == "reprendre":
                        menu_open = False
                    elif choice == "sauvegarder":
                        persist()
                    elif choice == "nouvelle":
                        start_new()
                    elif choice == "quitter":
                        persist()
                        running = False
            elif ui["event_open"] is not None:
                if event.type == pygame.MOUSEBUTTONDOWN and event.button == 1:
                    lay = renderer.event_hits.get("modal") if isinstance(renderer.event_hits, dict) else None
                    if lay is None:
                        close_event()
                        continue
                    mx, my = event.pos
                    cx, cy, cw, ch = lay["close"]
                    if cx <= mx <= cx + cw and cy <= my <= cy + ch:
                        close_event()
                        continue
                    for i, (ox, oy, ow, oh) in lay["options"].items():
                        if ox <= mx <= ox + ow and oy <= my <= oy + oh:
                            result = events.choose(state, ui["event_open"], i)
                            if events.find(state, ui["event_open"]) is None:
                                close_event()
                            elif result:
                                toast(result)
                            break
            elif ui["found"] is not None:
                if event.type == pygame.MOUSEBUTTONDOWN and event.button == 1:
                    from src.kora.render_village import found_hit

                    found_click(found_hit(renderer.found_hits, event.pos[0], event.pos[1]))
            elif event.type == pygame.MOUSEWHEEL:
                tlay = renderer.side_hits.get("tech") if side_panel == "savoirs" else None
                wx_, wy_ = pygame.mouse.get_pos()
                if tlay and _in_rect(tlay["view"], wx_, wy_):
                    # La molette zoome l'arbre des savoirs, autour du curseur.
                    from src.kora.render import TREE_ZOOM_STEP, zoom_at

                    factor = TREE_ZOOM_STEP if event.y > 0 else 1.0 / TREE_ZOOM_STEP
                    ui["tech_cam"] = zoom_at(tlay["cam"], tlay["view"], tlay["world"], wx_, wy_, factor)
                    continue
                zmin = min_zoom_for(state.world, sw, sh)
                zoom = min(MAX_ZOOM, max(zmin, zoom * (1.1 if event.y > 0 else 0.9)))
            elif event.type == pygame.MOUSEBUTTONDOWN:
                selected = _refresh_selection(state, selected)
                tlay = renderer.side_hits.get("tech") if side_panel == "savoirs" else None
                if event.button in (2, 3) and tlay and _in_rect(tlay["view"], *event.pos):
                    tech_drag = event.button
                    last_mouse = event.pos
                    continue
                if event.button in (2, 3):
                    mx, my = event.pos
                    in_village = (ui["village_open"] is not None and bool(renderer.village_hits) and _in_rect(renderer.village_hits["box"], mx, my)) or (
                        ui["trade_open"] and bool(renderer.trade_hits) and _in_rect(renderer.trade_hits["box"], mx, my)
                    )
                    if side_hit(renderer.side_hits, mx, my) is None and not in_village:
                        dragging = True
                        drag_button = event.button
                        last_mouse = event.pos
                elif event.button == 1:
                    mx, my = event.pos
                    ui_hit = hud_hit(renderer.hud_hits, mx, my)
                    if ui_hit == "pause":
                        state.clock.toggle_pause()
                        continue
                    if isinstance(ui_hit, tuple) and ui_hit[0] == "speed":
                        state.clock.set_speed(ui_hit[1])
                        continue
                    if ui_hit == "bar":
                        continue
                    if ui["trade_open"] and renderer.trade_hits:
                        from src.kora.render_trade import trade_hit

                        tchoice = trade_hit(renderer.trade_hits, mx, my, renderer.trade_partners, len(renderer.trade_routes), renderer.trade_candidates)
                        if tchoice is not None:
                            if tchoice != "panel":
                                trade_click(tchoice)
                            continue
                        if side_hit(renderer.side_hits, mx, my) is None:
                            ui["trade_open"] = False
                            continue
                    if ui["village_open"] is not None:
                        from src.kora.render_village import village_hit

                        vchoice = village_hit(renderer.village_hits, mx, my, renderer.village_armies)
                        if vchoice is not None:
                            if vchoice != "panel":
                                village_click(vchoice)
                            continue
                        if side_hit(renderer.side_hits, mx, my) is None:
                            # Un clic hors de l'ecran du village le ferme.
                            ui["village_open"] = None
                            continue
                    choice = side_hit(renderer.side_hits, mx, my)
                    if side_panel == "savoirs" and isinstance(choice, str) and (choice.startswith("tech:") or choice == "tview"):
                        tech_drag = 1
                        last_mouse = (mx, my)
                        tech_press.update({"at": (mx, my), "moved": False, "pick": choice if choice.startswith("tech:") else None})
                        continue
                    if choice is not None:
                        side_click(choice)
                        continue
                    mode = map_mode_hit(renderer.mode_hits, mx, my)
                    if mode is not None:
                        renderer.map_mode = mode
                        continue
                    card_uid = next(
                        (uid for uid, rect in renderer.event_hits.items() if isinstance(uid, int)
                         and rect[0] <= mx <= rect[0] + rect[2] and rect[1] <= my <= rect[1] + rect[3]),
                        None,
                    ) if isinstance(renderer.event_hits, dict) else None
                    if card_uid is not None:
                        open_event(card_uid)
                        continue
                    if open_fight is None:
                        hit_toast = toast_hit(renderer.toast_hits, mx, my)
                        if hit_toast is not None:
                            show_place(hit_toast.get("hex"))
                            continue
                    card = band_card_hit(renderer.band_hits, mx, my)
                    if card in orders.ACTIONS:
                        band_action(card)
                        continue
                    if card == "card":
                        continue
                    if open_fight is not None:
                        fhit = fight_panel_hit(renderer.fight_hits, mx, my)
                        if fhit == "close" or fhit == "panel":
                            if fhit == "close":
                                open_fight = None
                            continue
                    sword = _fight_at_pixel(state, mx, my, zoom, globe_yaw, globe_pitch, sw, sh)
                    if sword is not None:
                        open_fight = sword
                        continue
                    if open_fight is not None:
                        open_fight = None
                        continue
                    hit = _band_at_pixel(state, mx, my, zoom, globe_yaw, globe_pitch, sw, sh)
                    shift = pygame.key.get_mods() & pygame.KMOD_SHIFT
                    if hit is not None and hit.tribe_id == PLAYER_TRIBE_ID and hit.village and not shift:
                        # Un clic sur un de vos villages ouvre son ecran.
                        selected = hit.id
                        open_village(hit.village)
                        continue
                    if hit is not None and hit.tribe_id == PLAYER_TRIBE_ID:
                        if shift and selected not in (None, hit.id):
                            # Rejoindre : les deux bandes se reunissent.
                            band = state.bands.get(selected)
                            if band is not None and chiefs.obeys(state, band):
                                set_march_to_band(state, selected, hit.id)
                            else:
                                toast(orders.INDOCILE + ".")
                        elif selected == hit.id:
                            selected = None
                        else:
                            selected = hit.id
                    elif hit is not None and selected is not None:
                        order_raid(hit)
                    else:
                        gcx, gcy, focal, dist = view_params(zoom, sw, sh, HUD_HEIGHT)
                        hx = pixel_to_hex_globe(
                            mx, my, state.world, globe_yaw, globe_pitch, gcx, gcy, focal, dist
                        )
                        if hx is not None:
                            if selected is not None:
                                order_move(hx)
                            info = hex_inspect(state, hx)
                            if info is None:
                                pinned_hex = None
                            elif pinned_hex == info["hex"]:
                                pinned_hex = None
                            else:
                                pinned_hex = info["hex"]
            elif event.type == pygame.MOUSEBUTTONUP:
                if event.button == drag_button:
                    dragging = False
                if event.button == tech_drag:
                    if tech_drag == 1 and not tech_press["moved"] and tech_press["pick"]:
                        side_click(tech_press["pick"])
                    tech_drag = 0
            elif event.type == pygame.MOUSEMOTION and tech_drag:
                tlay = renderer.side_hits.get("tech")
                if tlay and side_panel == "savoirs":
                    from src.kora.render import pan

                    mx, my = event.pos
                    ax, ay = tech_press["at"]
                    if tech_drag != 1 or tech_press["moved"] or abs(mx - ax) + abs(my - ay) > 4:
                        tech_press["moved"] = True
                        ui["tech_cam"] = pan(tlay["cam"], tlay["view"], tlay["world"], mx - last_mouse[0], my - last_mouse[1])
                        renderer.side_hits["tech"]["cam"] = ui["tech_cam"]
                        last_mouse = (mx, my)
                else:
                    tech_drag = 0
            elif event.type == pygame.MOUSEMOTION and dragging:
                mx, my = event.pos
                _cx, _cy, _focal, dist = view_params(zoom, sw, sh, HUD_HEIGHT)
                sens = orbit_sensitivity(dist)
                globe_yaw += (mx - last_mouse[0]) * sens
                globe_pitch = clamp_pitch(globe_pitch + (my - last_mouse[1]) * sens)
                last_mouse = (mx, my)
        if not menu_open and not state.clock.paused and not state.player_dead:
            # Un combat ne deplace plus la camera et n'arrete plus le temps :
            # toast + journal + epee ; un clic sur le toast ou la ligne y mene.
            acc = consume_ticks(state, acc, dt)
            selected = _refresh_selection(state, selected)
            if (
                state.tick_count > 0
                and state.tick_count % 8 == 0
                and state.tick_count != last_auto
            ):
                persist()
                last_auto = state.tick_count
        else:
            acc = 0.0
        if ui["event_open"] is not None and events.find(state, ui["event_open"]) is None:
            close_event()
        selected = _refresh_selection(state, selected)
        for t in toasts:
            t["age"] += dt
        toasts = [t for t in toasts if t["age"] < TOAST_LIFE]
        if state.log.seq > last_log_seq:
            fresh = [e for e in state.log.entries if e.seq > last_log_seq]
            for entry in fresh:
                toasts.append(
                    {
                        "text": entry.text,
                        "age": 0.0,
                        "seq": entry.seq,
                        "hex": entry.hex,
                        "combat": entry.kind is LogKind.COMBAT,
                    }
                )
            last_log_seq = state.log.seq
            toasts = toasts[-MAX_TOASTS:]
        mx, my = pygame.mouse.get_pos()
        hover_info = None
        pin_info = hex_inspect(state, pinned_hex) if pinned_hex is not None else None
        if ui["village_open"] is not None:
            vsite = state.sites.get(ui["village_open"])
            if vsite is None or vsite.kind != "village":
                ui["village_open"] = None
        blocked = (
            menu_open
            or ui["event_open"] is not None
            or ui["found"] is not None
            or (ui["village_open"] is not None and bool(renderer.village_hits) and _in_rect(renderer.village_hits["box"], mx, my))
            or (ui["trade_open"] and bool(renderer.trade_hits) and _in_rect(renderer.trade_hits["box"], mx, my))
            or my < HUD_HEIGHT
            or band_card_hit(renderer.band_hits, mx, my) is not None
        )
        if not blocked and side_hit(renderer.side_hits, mx, my) is None:
            gcx, gcy, focal, dist = view_params(zoom, sw, sh, HUD_HEIGHT)
            hx = pixel_to_hex_globe(
                mx, my, state.world, globe_yaw, globe_pitch, gcx, gcy, focal, dist
            )
            if hx is not None:
                hover_info = hex_inspect(state, hx)
        renderer.draw(
            state,
            camera_x,
            camera_y,
            zoom,
            selected,
            menu_open,
            globe_yaw,
            globe_pitch,
            side_panel,
            log_filter,
            log_newest,
            toasts,
            hover_info,
            pin_info,
            tech_pick,
            open_fight,
            ui,
        )
        pygame.display.flip()
    pygame.quit()
