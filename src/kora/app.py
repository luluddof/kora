from __future__ import annotations

import pygame

from src.kora import chiefs, commands, diplo, events, orders, screens, situations
from src.kora.globe import (
    FOCUS_ZOOM,
    clamp_pitch,
    look_at_hex,
    orbit_sensitivity,
    pixel_to_hex_globe,
    view_params,
)
from src.kora.log import FILTER_ALL, LogKind
from src.kora.persist import default_save_path, load_game, multi_save_path, save_game, set_aside_save
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
from src.kora.sim import _default_world, consume_ticks, fight_at, hex_inspect, new_game, player_home_hex
from src.kora.gamestate import human_dead, log_of, note


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
    return sorted(b.id for b in state.bands.values() if b.tribe_id == state.viewer)


def _first_player_band(state):
    ids = _player_band_ids(state)
    return ids[0] if ids else None


def _refresh_selection(state, selected):
    # None = rien de selectionne, voulu par le joueur : un clic sur la carte
    # montre alors la case sans deplacer personne. Une bande disparue
    # (reunie, detruite, partie) passe la selection a une autre bande.
    if selected is None or (selected in state.bands and state.bands[selected].tribe_id == state.viewer):
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


class _Worlds:
    """La carte : lue une fois au lancement (le menu la montre). Une partie
    la modifie (epuisement, influence) : la suivante en relit une propre."""

    def __init__(self) -> None:
        self.shown = _default_world()
        self._fresh = self.shown

    def fresh(self):
        world = self._fresh if self._fresh is not None else _default_world()
        self._fresh = None
        return world


def _start_view(state, selected, sw: int, sh: int):
    yaw, pitch, zoom = _tribe_start_view(state, selected)
    zmin = min_zoom_for(state.world, sw, sh)
    zoom = min(MAX_ZOOM, max(zmin, zoom))
    return state, selected, 0.0, 0.0, zoom, yaw, pitch


def _continue_boot(worlds, sw: int, sh: int):
    """La partie sauvegardee ; None si elle ne se lit pas (elle est alors
    mise de cote, jamais ecrasee)."""
    path = default_save_path()
    loaded = load_game(path, worlds.fresh())
    if loaded is None:
        set_aside_save(path)
        return None
    state, view = loaded
    return _start_view(state, _refresh_selection(state, view.get("selected")), sw, sh)


def _new_boot(worlds, setup: dict | None, sw: int, sh: int):
    """Une partie neuve (menu de demarrage) ; l'ancienne sauvegarde est
    mise de cote, pas effacee."""
    moved = set_aside_save(default_save_path())
    state = new_game(worlds.fresh(), setup=setup)
    if moved is not None:
        note(state, LogKind.DECOUVERTE, f"Ancienne partie mise de côté : {moved.name}")
    return _start_view(state, _first_player_band(state), sw, sh)


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
        # Situation (crise, conjoncture) dont la fenetre est ouverte (uid).
        "situation_open": None,
        "found": None,
        "found_oath": None,
        "village_open": None,
        "village_pick": None,
        "village_page": "village",
        "trade_open": False,
        "treasury_open": False,
        "trade_partner": None,
        "trade_good": None,
        "trade_sell": True,
        "trade_level": 1,
        "tech_cam": None,
        "tech_tab": "arbre",
        "base_confirm": None,
        "levy": "troupe",
        "levy_role": "melee",
        "leave_confirm": 0.0,
        # Multijoueur : cartes deja repondues (la reponse est en route).
        "answered": set(),
    }


def _loading(renderer, text: str) -> None:
    screen = renderer.screen
    screen.fill((6, 8, 14))
    surf = renderer.font.render(text, True, (214, 180, 104))
    w, h = screen.get_size()
    screen.blit(surf, ((w - surf.get_width()) // 2, (h - surf.get_height()) // 2))
    pygame.display.flip()


def run() -> None:
    pygame.init()
    pygame.display.set_caption("Kora")
    screen = pygame.display.set_mode((1280, 720), pygame.RESIZABLE)
    clock = pygame.time.Clock()
    renderer = Renderer(screen)
    _loading(renderer, "Kora : la carte du monde se prépare...")
    worlds = _Worlds()
    message = ""
    while True:
        choice = title_screen(renderer, clock, worlds, message)
        message = ""
        sw, sh = renderer.screen.get_size()
        if choice[0] == "quit":
            break
        mp = None
        if choice[0] in ("host", "join", "resume_mp"):
            out = _multiplayer(renderer, clock, worlds, choice)
            if out[0] == "quit":
                break
            if out[0] == "back":
                message = out[1]
                continue
            mp, state = out[1], out[2]
            boot = _start_view(state, _first_player_band(state), sw, sh)
        else:
            _loading(renderer, "La partie se prépare...")
            if choice[0] == "continue":
                boot = _continue_boot(worlds, sw, sh)
                if boot is None:
                    message = "La sauvegarde ne se lit pas (autre version ?) : elle est mise de côté."
                    continue
            else:
                boot = _new_boot(worlds, choice[1], sw, sh)
        _settle_memory()
        outcome, message = play(renderer, clock, boot, mp)
        if outcome == "quit":
            break
    pygame.quit()


def _remember(setup: dict) -> None:
    """Le nom, la couleur, les bonus et la derniere adresse : proposes la
    prochaine fois (reglages.json, a cote des sauvegardes)."""
    from src.kora.persist import load_prefs, save_prefs

    prefs = load_prefs()
    for key in ("name", "color", "bonuses", "address"):
        if setup.get(key):
            prefs[key] = list(setup[key]) if key in ("color", "bonuses") else setup[key]
    save_prefs(prefs)


def _prefilled(setup: dict) -> dict:
    from src.kora import render_menu, tech
    from src.kora.persist import load_prefs

    prefs = load_prefs()
    if isinstance(prefs.get("name"), str) and prefs["name"].strip():
        setup["name"] = prefs["name"][: render_menu.NAME_MAX]
    color = prefs.get("color")
    if isinstance(color, list) and tuple(color) in render_menu.PALETTE:
        setup["color"] = tuple(color)
    bonuses = [b for b in prefs.get("bonuses", []) if b in tech.START_BONUSES][: tech.START_BONUS_PICKS]
    if bonuses:
        setup["bonuses"] = bonuses
    if isinstance(prefs.get("address"), str):
        setup["address"] = prefs["address"][: render_menu.ADDRESS_MAX]
    return setup


def title_screen(renderer, clock, worlds, message: str = ""):
    """Le menu de demarrage, la creation du peuple, le menu du multijoueur.
    Rend ("continue",), ("new", setup), ("host", setup), ("join", setup),
    ("resume_mp",) ou ("quit",)."""
    import random

    from src.kora import render_menu
    from src.kora.persist import multi_save_path, peek_save

    scene = render_menu.TitleScene(worlds.shown)
    info = peek_save(default_save_path())
    multi = peek_save(multi_save_path())
    rng = random.Random()
    setup = None
    page = "title"
    hint = ""
    t = 0.0
    while True:
        t += clock.tick(60) / 1000.0
        for event in pygame.event.get():
            if event.type == pygame.QUIT:
                return ("quit",)
            if event.type == pygame.VIDEORESIZE:
                renderer.screen = pygame.display.set_mode((event.w, event.h), pygame.RESIZABLE)
                continue
            if setup is not None:
                mode = setup.get("mode", "solo")
                if event.type == pygame.KEYDOWN:
                    if event.key == pygame.K_ESCAPE:
                        if setup.get("typing"):
                            setup["typing"] = False
                        else:
                            setup = None
                    elif setup.get("typing"):
                        render_menu.setup_key(setup, event)
                    elif event.key in (pygame.K_RETURN, pygame.K_KP_ENTER) and render_menu.setup_ready(setup):
                        _remember(setup)
                        return (mode if mode != "solo" else "new", render_menu.setup_for_game(setup) | {"address": setup.get("address", "")})
                elif event.type == pygame.MOUSEBUTTONDOWN and event.button == 1:
                    hits = getattr(renderer, "setup_hits", None)
                    hit = render_menu.setup_hit(hits, *event.pos, mode=mode) if hits else None
                    if hit is None:
                        setup["typing"] = False
                    elif hit == "back":
                        setup = None
                    elif hit == "start":
                        if render_menu.setup_ready(setup):
                            _remember(setup)
                            return (mode if mode != "solo" else "new", render_menu.setup_for_game(setup) | {"address": setup.get("address", "")})
                        hint = render_menu.setup_missing(setup)
                    else:
                        hint = render_menu.setup_click(setup, hit, rng)
                continue
            if page == "mp":
                if event.type == pygame.KEYDOWN and event.key == pygame.K_ESCAPE:
                    page = "title"
                elif event.type == pygame.MOUSEBUTTONDOWN and event.button == 1:
                    hits = getattr(renderer, "mp_menu_hits", None)
                    hit = render_menu.mp_menu_hit(hits, *event.pos, can_resume=multi is not None) if hits else None
                    if hit == "retour":
                        page = "title"
                    elif hit in ("heberger", "rejoindre"):
                        setup = _prefilled(render_menu.new_setup(rng))
                        setup["mode"] = "host" if hit == "heberger" else "join"
                        if setup["mode"] == "join" and not setup.get("address"):
                            setup["typing"] = "address"
                        hint = ""
                    elif hit == "reprendre":
                        return ("resume_mp",)
                continue
            if event.type == pygame.KEYDOWN:
                if event.key == pygame.K_ESCAPE:
                    return ("quit",)
                if event.key in (pygame.K_RETURN, pygame.K_KP_ENTER) and info is not None:
                    return ("continue",)
            elif event.type == pygame.MOUSEBUTTONDOWN and event.button == 1:
                hits = getattr(renderer, "title_hits", None)
                hit = render_menu.title_hit(hits, *event.pos, can_continue=info is not None) if hits else None
                if hit == "continuer":
                    return ("continue",)
                if hit == "nouvelle":
                    setup = _prefilled(render_menu.new_setup(rng))
                    hint = ""
                elif hit == "multijoueur":
                    page = "mp"
                    message = ""
                elif hit == "quitter":
                    return ("quit",)
        if page == "mp":
            render_menu.draw_mp_menu(renderer, scene, multi, t, message)
        else:
            render_menu.draw_title(renderer, scene, info, t, message)
        if setup is not None:
            render_menu.draw_setup(renderer, setup, t, info if setup.get("mode", "solo") == "solo" else None, hint)
        pygame.display.flip()


def _multiplayer(renderer, clock, worlds, choice):
    """Heberger, rejoindre ou reprendre : jusqu'au lancement de la partie.
    Rend ("play", session, state), ("back", message) ou ("quit",)."""
    import threading

    from src.kora import net, render_menu, session
    from src.kora.persist import load_game, multi_save_path

    scene = render_menu.TitleScene(worlds.shown)
    mp = None
    connecting = None
    status = ""
    try:
        if choice[0] == "host":
            mp = session.HostSession(choice[1], port=net.PORT)
        elif choice[0] == "resume_mp":
            _loading(renderer, "La partie à plusieurs se prépare...")
            loaded = load_game(multi_save_path(), worlds.fresh())
            if loaded is None:
                return ("back", "La partie à plusieurs ne se lit pas (autre version ?).")
            saved, _view = loaded
            me = saved.tribes[1]
            mp = session.HostSession({"name": me.name, "color": me.color, "bonuses": me.start_bonuses}, port=net.PORT, resume=saved)
        else:
            host, port = net.parse_address(choice[1].get("address", ""))
            status = f"Connexion à {host}..."
            box: dict = {}

            def work():
                try:
                    box["conn"] = net.connect(host, port)
                except OSError as exc:
                    box["err"] = str(exc)

            connecting = (threading.Thread(target=work, daemon=True), box, choice[1])
            connecting[0].start()
    except OSError as exc:
        return ("back", f"Impossible d'ouvrir le salon (port {net.PORT} déjà pris ?) : {exc}")
    chat_text = None
    hint = ""
    t = 0.0
    while True:
        t += clock.tick(60) / 1000.0
        if connecting is not None:
            _thread, box, setup = connecting
            if "err" in box:
                return ("back", f"Pas de réponse de l'hôte ({box['err']}). Vérifiez l'adresse, et que son salon est ouvert.")
            if "conn" in box:
                mp = session.ClientSession(box["conn"], setup)
                connecting = None
                status = ""
        if mp is not None:
            if mp.role == "host":
                mp.pump_lobby()
            else:
                mp.pump_lobby()
                if mp.ended:
                    mp.close()
                    return ("back", mp.ended)
                if mp.snap is not None:
                    _loading(renderer, "La partie arrive de l'hôte...")
                    state = mp.begin(worlds.fresh())
                    if state is None:
                        mp.close()
                        return ("back", mp.ended)
                    return ("play", mp, state)
        for event in pygame.event.get():
            if event.type == pygame.QUIT:
                if mp is not None:
                    mp.close()
                return ("quit",)
            if event.type == pygame.VIDEORESIZE:
                renderer.screen = pygame.display.set_mode((event.w, event.h), pygame.RESIZABLE)
                continue
            if mp is None:
                if event.type == pygame.KEYDOWN and event.key == pygame.K_ESCAPE:
                    return ("back", "")
                continue
            if event.type == pygame.KEYDOWN:
                if chat_text is not None:
                    if event.key in (pygame.K_RETURN, pygame.K_KP_ENTER):
                        mp.say(chat_text)
                        chat_text = None
                    elif event.key == pygame.K_ESCAPE:
                        chat_text = None
                    elif event.key == pygame.K_BACKSPACE:
                        chat_text = chat_text[:-1]
                    elif event.unicode and event.unicode.isprintable() and len(chat_text) < 160:
                        chat_text += event.unicode
                elif event.key in (pygame.K_RETURN, pygame.K_KP_ENTER):
                    chat_text = ""
                elif event.key == pygame.K_ESCAPE:
                    mp.close()
                    return ("back", "")
            elif event.type == pygame.MOUSEBUTTONDOWN and event.button == 1:
                hits = getattr(renderer, "lobby_hits", None)
                hit = render_menu.lobby_hit(hits, *event.pos, mp.role) if hits else None
                if hit == "chat_input":
                    chat_text = "" if chat_text is None else chat_text
                elif hit == "back":
                    mp.close()
                    return ("back", "")
                elif hit == "ready" and mp.role == "client":
                    mine = mp.seats.get(mp.me)
                    mp.set_ready(not (mine and mine.ready))
                elif hit == "go" and mp.role == "host":
                    why = mp.can_start()
                    if why:
                        hint = why
                    else:
                        _loading(renderer, "La partie se prépare...")
                        world = mp.resume.world if mp.resume is not None else worlds.fresh()
                        state = mp.start(world)
                        return ("play", mp, state)
                elif isinstance(hit, str) and hit.startswith("seat:") and mp.role == "client":
                    tid = int(hit.split(":")[1])
                    if tid not in mp.seats and not mp.resume:
                        mp.want_slot(tid)
        if mp is None:
            render_menu.draw_title(renderer, scene, None, t, status)
        else:
            render_menu.draw_title(renderer, scene, None, t, "")
            render_menu.draw_lobby(renderer, mp, t, chat_text, hint, status)
        pygame.display.flip()


def play(renderer, clock, boot, mp=None) -> tuple[str, str]:
    """Une partie, jusqu'au retour au menu ("menu", message) ou au depart
    ("quit", ""). mp : la session multijoueur (session.py), sinon solo."""
    screen = renderer.screen
    state, selected, camera_x, camera_y, zoom, globe_yaw, globe_pitch = boot
    renderer.map_mode = "zones"
    renderer._layer_key = None
    dragging = False
    drag_button = 0
    last_mouse = (0, 0)
    # La toile des savoirs se deplace a la souris (render.tech_panel_layout) :
    # on glisse depuis n'importe ou ; sans bouger, un clic choisit le savoir.
    tech_drag = 0
    tech_press = {"at": (0, 0), "moved": False, "pick": None}
    acc = 0.0
    # En multijoueur, seul l'hote sauvegarde (a part : la partie solo reste).
    save_path = multi_save_path() if mp is not None else default_save_path()
    last_auto = -1
    # Multijoueur : le message qu'on ecrit (Entree), None sinon.
    chat_text = None
    menu_open = False
    side_panel = None
    tech_pick = None
    log_filter = FILTER_ALL
    log_newest = True
    pinned_hex = None
    open_fight = None
    toasts: list[dict] = []
    last_log_seq = log_of(state, state.viewer).seq
    ui: dict = _fresh_ui()
    resume_after_event = False
    resume_after_found = False
    resume_after_situation = False
    confirm = {"band": None, "until": 0.0}
    now = 0.0

    def persist() -> None:
        if mp is not None and mp.role != "host":
            return
        save_game(
            state,
            save_path,
            _view(camera_x, camera_y, zoom, selected, globe_yaw, globe_pitch),
        )

    def leave() -> None:
        persist()
        if mp is not None:
            mp.close()

    def say(res) -> None:
        if res.get("msg"):
            toast(res["msg"])

    def issue(cmd, then=None) -> None:
        """Un ordre du joueur (commands.py) : tout de suite en solo ; par
        l'hote en multijoueur. then recoit la reponse quand il s'applique."""
        then = then or say
        if mp is None:
            then(commands.apply(state, cmd))
        else:
            mp.issue(cmd, then)

    def me() -> int:
        return state.viewer

    def toggle_pause() -> None:
        if mp is None:
            state.clock.toggle_pause()
        else:
            mp.toggle_pause()

    def set_speed(n: int) -> None:
        if mp is None:
            state.clock.set_speed(n)
        else:
            mp.set_speed(n)

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
        def done(res):
            nonlocal selected
            if res["msg"]:
                toast(res["msg"])
            elif band_id is None and res["sel"] is not None:
                selected = res["sel"]

        issue(commands.make(me(), "band", target, action), done)

    def open_found(band_id) -> None:
        """Fonder un village : un choix qui arrete le temps (en solo)."""
        nonlocal resume_after_found, side_panel
        if ui["found"] is None and mp is None:
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
        screens.open(ui, "village", site_id)
        ui["village_pick"] = None
        ui["leave_confirm"] = 0.0
        side_panel = None

    def open_screen(name: str, toggle: bool = False) -> None:
        """Un grand ecran (screens.py) : les autres et les panneaux se ferment."""
        nonlocal side_panel
        if toggle:
            screens.toggle(ui, name)
        else:
            screens.open(ui, name)
        side_panel = None

    def treasury_click(choice) -> None:
        """Clic dans l'ecran du tresor : le budget passe par commands.py."""
        from src.kora import money

        if choice == "mclose":
            screens.close_all(ui)
            return
        if choice.startswith("mtax:"):
            issue(commands.make(me(), "budget", "tax", int(choice.split(":")[1])))
            return
        if choice.startswith("mtoggle:"):
            key = choice.split(":")[1]
            tribe = state.tribes.get(me())
            if tribe is not None:
                issue(commands.make(me(), "budget", key, not money.budget(tribe)[key]))

    def trade_click(choice) -> None:
        """Clic dans l'ecran du commerce."""
        from src.kora import goods

        if choice == "tclose":
            screens.close_all(ui)
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
            why = goods.open_block(state, state.viewer, partner, good, ui["trade_sell"], ui["trade_level"])
            if why:
                toast(why)
                return
            issue(commands.make(me(), "route_open", partner, good, ui["trade_sell"], ui["trade_level"]))
            return
        if choice.startswith(("rlevel:", "rclose:")):
            parts = choice.split(":")
            idx = int(parts[1])
            if idx >= len(renderer.trade_routes):
                return
            route = renderer.trade_routes[idx]
            if choice.startswith("rclose:"):
                issue(commands.make(me(), "route_close", commands.route_key(route)))
                return
            level = int(parts[2])
            why = goods.level_block(state, state.viewer, route, level)
            if why:
                toast(why)
            else:
                issue(commands.make(me(), "route_level", commands.route_key(route), level))
            return
        if choice.startswith("tpropose:"):
            tid = int(choice.split(":")[1])
            if diplo.on_cooldown(state, state.viewer, tid, "commerce"):
                toast("Vous avez déjà proposé cela récemment.")
            else:
                issue(commands.make(me(), "diplo", tid, "commerce"))
            return

    def village_click(choice) -> None:
        """Clic dans l'ecran du village."""
        nonlocal selected, globe_yaw, globe_pitch
        from src.kora import villages

        site = state.sites.get(ui["village_open"])
        home = villages.band_of(state, site) if site is not None and site.kind == "village" else None
        if home is None or choice == "vclose":
            screens.close_all(ui)
            return
        if choice == "vleave":
            if now > ui["leave_confirm"]:
                ui["leave_confirm"] = now + CONFIRM_SECONDS
                toast("Abandonner le village ? Cliquez encore pour confirmer (champs et bâtiments perdus).", True)
                return
            ui["leave_confirm"] = 0.0

            def left(res):
                if res["msg"]:
                    toast(res["msg"])
                else:
                    ui["village_open"] = None

            issue(commands.make(me(), "band", home.id, "leave"), left)
            return
        if choice.startswith("vb:"):
            ui["village_pick"] = choice[3:]
            return
        if choice.startswith("vpage:"):
            ui["village_page"] = choice[6:]
            return
        if choice.startswith("crate:"):
            issue(commands.make(me(), "levy_rate", int(choice[6:])))
            return
        if choice == "cfeast":
            issue(commands.make(me(), "feast"))
            return
        if choice.startswith("ccharge:"):
            _k, idx, charge = choice.split(":", 2)
            fams = state.tribes[home.tribe_id].families or []
            if int(idx) < len(fams):
                issue(commands.make(me(), "charge", fams[int(idx)]["id"], charge))
            return
        if choice == "vtrade":
            screens.open(ui, "commerce")
            return
        if choice.startswith(("vteam+:", "vteam-:")):
            from src.kora import goods

            cid = choice.split(":")[1]
            if not chiefs.obeys(state, home):
                toast(orders.INDOCILE)
                return
            if choice.startswith("vteam+:"):
                why = goods.add_block(state, site, cid)
                if why:
                    toast(why)
                else:
                    issue(commands.make(me(), "teams", site.id, cid, 1))
            elif goods.teams_of(site, cid) > 0:
                issue(commands.make(me(), "teams", site.id, cid, -1))
            return
        if choice == "vsplit":
            place = villages.name(site)

            def split_done(res, home_id=home.id):
                nonlocal selected
                new_sel = res["sel"]
                if res["msg"]:
                    toast(res["msg"])
                elif new_sel is not None and new_sel != home_id and new_sel in state.bands:
                    selected = new_sel
                    ui["village_open"] = None
                    toast(f"Une bande part de {place} : {state.bands[new_sel].population} personnes.")

            issue(commands.make(me(), "band", home.id, "split"), split_done)
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
                issue(commands.make(me(), "build", home.id, pick))
            return
        if choice.startswith("levy:"):
            ui["levy"] = choice[5:]
            return
        if choice.startswith("ltype:"):
            from src.kora import units

            role = choice[6:]
            if units.best(state.tribes[home.tribe_id], role) is None:
                toast("Aucune unité de ce rôle pour l'instant (voir les savoirs).")
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
                issue(commands.make(me(), "raise", home.id, ui["levy"], type_id))
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
                    issue(commands.make(me(), "reequip", bid))
            else:
                why = villages.dissolve_block(state, bid)
                if why:
                    toast(why)
                else:
                    issue(commands.make(me(), "dissolve", bid))
            return

    def army_click(choice) -> None:
        """Clic dans le panneau Armee."""
        nonlocal selected, globe_yaw, globe_pitch, side_panel
        from src.kora import units, villages

        kind, _sep, rest = choice.partition(":")
        if kind == "arole":
            sid, role = rest.split(":")
            if units.best(state.tribes[state.viewer], role) is None:
                toast("Aucune unité de ce rôle pour l'instant (voir les savoirs).")
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
            unit = units.best(state.tribes[state.viewer], role) or units.best(state.tribes[state.viewer], "melee")
            share = villages.LEVY_SHARE.get(key, villages.LEVY_SHARE["troupe"])
            why = villages.army_block(state, home.id, share, unit.id) or ("" if chiefs.obeys(state, home) else orders.INDOCILE)
            if why:
                toast(why)
            else:
                issue(commands.make(me(), "raise", home.id, key, unit.id))
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
            issue(commands.make(me(), "dissolve", bid))

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
            oath = ui["found_oath"]
            close_found()

            def founded(res):
                say(res)
                if res["site"] is not None and res["site"] in state.sites:
                    open_village(res["site"])

            issue(commands.make(me(), "found", bid, oath), founded)

    def open_event(uid) -> None:
        nonlocal resume_after_event
        if events.find(state, uid) is None:
            return
        if ui["event_open"] is None and mp is None:
            # Lire un evenement met en pause (en solo) ; on reprend en le fermant.
            resume_after_event = not state.clock.paused
            state.clock.paused = True
        ui["event_open"] = uid

    def close_event() -> None:
        nonlocal resume_after_event
        ui["event_open"] = None
        if resume_after_event and not events.pending(state, state.viewer):
            state.clock.paused = False
        elif resume_after_event:
            state.clock.paused = False
        resume_after_event = False

    def open_situation(uid) -> None:
        nonlocal resume_after_situation
        if situations.find(state, uid) is None:
            return
        if ui["situation_open"] is None and mp is None:
            # Lire une crise met en pause (en solo) ; on reprend en fermant.
            resume_after_situation = not state.clock.paused
            state.clock.paused = True
        ui["situation_open"] = uid

    def close_situation() -> None:
        nonlocal resume_after_situation
        ui["situation_open"] = None
        if resume_after_situation:
            state.clock.paused = False
        resume_after_situation = False

    def situation_click(hit) -> None:
        from src.kora.situations import SPECS

        inst = situations.find(state, ui["situation_open"])
        if inst is None or hit is None:
            close_situation()
            return
        if hit == "close":
            close_situation()
        elif hit == "place" and inst.center is not None:
            close_situation()
            show_place(inst.center)
        elif isinstance(hit, tuple) and hit[0] == "action":
            actions = SPECS[inst.sid].actions
            if hit[1] < len(actions):
                issue(commands.make(me(), "situation", inst.uid, actions[hit[1]].id))

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
        issue(commands.make(me(), "goto", selected, hx.q, hx.r))
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
        if target.tribe_id != state.viewer and diplo.at_peace(state, state.viewer, target.tribe_id):
            name = state.tribes[target.tribe_id].name
            if confirm["band"] != target.id or now > confirm["until"]:
                confirm["band"] = target.id
                confirm["until"] = now + CONFIRM_SECONDS
                toast(f"Pacte avec les {name} : cliquez encore pour attaquer (trahison, prestige -10).", True)
                return
            confirm["band"] = None
        issue(commands.make(me(), "march", selected, target.id))

    def side_click(choice) -> bool:
        """Clic dans un panneau lateral ; True si traite."""
        nonlocal side_panel, tech_pick, log_filter, log_newest, selected, globe_yaw, globe_pitch, tech_drag, last_mouse
        if not isinstance(choice, str):
            return False
        if choice in ("tview", "tzoom_in", "tzoom_out", "tcenter"):
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
            elif choice == "tcenter":
                ui["tech_cam"] = render_tech.focus_cam(state, *screen.get_size())
            else:
                factor = TREE_ZOOM_STEP if choice == "tzoom_in" else 1.0 / TREE_ZOOM_STEP
                ui["tech_cam"] = zoom_at(cam, view, world, view[0] + view[2] / 2, view[1] + view[3] / 2, factor)
            return True
        if choice.startswith("log_"):
            seq = int(choice[4:])
            entry = next((e for e in log_of(state, state.viewer).entries if e.seq == seq), None)
            if entry is not None:
                show_place(entry.hex)
            return True
        if choice.startswith("tab_"):
            key = choice[4:]
            if key in screens.BY_NAME:
                # Commerce, Tresor : des onglets qui ouvrent un grand ecran.
                open_screen(key, toggle=True)
                return True
            side_panel = None if side_panel == key else key
            screens.close_all(ui)
            return True
        if choice == "trade_with":
            open_screen("commerce")
            ui["trade_partner"] = ui.get("people_pick")
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
        if choice.startswith("ttab:"):
            ui["tech_tab"] = choice[5:]
            ui["base_confirm"] = None
            return True
        if choice.startswith("nbase:"):
            # Deux clics : la base est presque definitive.
            base = int(choice[6:])
            if ui.get("base_confirm") == base:
                ui["base_confirm"] = None
                issue(commands.make(me(), "base", base))
            else:
                ui["base_confirm"] = base
            return True
        if choice.startswith("era:"):
            ui["era"] = int(choice[4:])
            tech_pick = None
            return True
        if choice == "learn":
            if tech_pick is not None:
                issue(commands.make(me(), "learn", tech_pick))
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
                issue(commands.make(me(), "honor", bid))
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
                issue(commands.make(me(), "promote", int(bid), int(pid)))
            return True
        if choice.startswith("tribe_heir:"):
            bid = int(choice.split(":")[1])
            issue(commands.make(me(), "heir", bid))
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
                issue(commands.make(me(), "diplo", tid, "cadeau", float(choice.split(":")[1])))
            return True
        if choice.startswith("invite:"):
            issue(commands.make(me(), "invite", int(choice.split(":")[1])))
            return True
        if choice.startswith("diplo:"):
            tid = ui.get("people_pick")
            action = choice.split(":")[1]
            if tid is not None:
                if diplo.on_cooldown(state, state.viewer, tid, action) and action not in ("rompre",):
                    toast("Vous avez déjà proposé cela récemment.")
                else:
                    issue(commands.make(me(), "diplo", tid, action))
            return True
        return choice == "panel"

    # Les clics de chaque grand ecran (screens.SCREENS).
    screen_clicks = {"village": village_click, "commerce": trade_click, "tresor": treasury_click}
    assert set(screen_clicks) == set(screens.BY_NAME)

    while True:
        dt = clock.tick(60) / 1000.0
        now += dt
        sw, sh = screen.get_size()
        for event in pygame.event.get():
            if event.type == pygame.QUIT:
                leave()
                return "quit", ""
            elif event.type == pygame.KEYDOWN and chat_text is not None:
                # La discussion (multijoueur) : Entree envoie, Echap renonce.
                if event.key in (pygame.K_RETURN, pygame.K_KP_ENTER):
                    if chat_text.strip():
                        mp.say(chat_text)
                    chat_text = None
                elif event.key == pygame.K_ESCAPE:
                    chat_text = None
                elif event.key == pygame.K_BACKSPACE:
                    chat_text = chat_text[:-1]
                elif event.unicode and event.unicode.isprintable() and len(chat_text) < 160:
                    chat_text += event.unicode
                continue
            elif event.type == pygame.KEYDOWN and mp is not None and event.key in (pygame.K_RETURN, pygame.K_KP_ENTER) and not menu_open:
                chat_text = ""
                continue
            elif event.type == pygame.KEYDOWN:
                if event.key == pygame.K_ESCAPE:
                    if ui["event_open"] is not None:
                        close_event()
                    elif ui["situation_open"] is not None:
                        close_situation()
                    elif ui["found"] is not None:
                        close_found()
                    elif screens.opened(ui) is not None:
                        screens.close_all(ui)
                    elif open_fight is not None:
                        open_fight = None
                    elif side_panel:
                        side_panel = None
                    elif pinned_hex is not None:
                        pinned_hex = None
                    else:
                        menu_open = not menu_open
                elif menu_open or ui["event_open"] is not None or ui["found"] is not None or ui["situation_open"] is not None:
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
                    toggle_pause()
                elif event.key == pygame.K_F5:
                    if mp is not None and mp.role != "host":
                        toast("C'est l'hôte qui sauvegarde la partie.")
                    else:
                        persist()
                        toast("Partie sauvegardée.")
                elif event.key in ACTION_KEYS:
                    band_action(ACTION_KEYS[event.key])
                elif event.key in PANEL_KEYS:
                    key = PANEL_KEYS[event.key]
                    from src.kora.render_panels import army_ready

                    if key == "armee" and not army_ready(state):
                        toast("L'armée vient avec le premier village.")
                        continue
                    side_panel = None if side_panel == key else key
                    screens.close_all(ui)
                elif event.key == pygame.K_m:
                    from src.kora.render_panels import commerce_ready

                    if not commerce_ready(state):
                        toast("Le commerce vient avec le premier village.")
                        continue
                    open_screen("commerce", toggle=True)
                elif event.key == pygame.K_g:
                    from src.kora import money

                    if not money.has_money(state, state.viewer):
                        toast("Le trésor vient avec Valeurs d'échange.")
                        continue
                    open_screen("tresor", toggle=True)
                elif event.key == pygame.K_z:
                    renderer.map_mode = "relief" if renderer.map_mode == "zones" else "zones"
                elif event.key == pygame.K_r:
                    renderer.map_mode = "relief" if renderer.map_mode == "ressources" else "ressources"
                elif event.key == pygame.K_x:
                    renderer.map_mode = "relief" if renderer.map_mode == "commerce" else "commerce"
                elif event.key == pygame.K_e:
                    waiting = [p for p in events.pending(state, state.viewer) if p.uid not in ui["answered"]]
                    if waiting:
                        open_event(waiting[0].uid)
                elif event.key in (
                    pygame.K_1,
                    pygame.K_2,
                    pygame.K_3,
                    pygame.K_4,
                    pygame.K_5,
                ):
                    set_speed(event.key - pygame.K_0)
            elif event.type == pygame.VIDEORESIZE:
                screen = pygame.display.set_mode((event.w, event.h), pygame.RESIZABLE)
                renderer.screen = screen
            elif menu_open:
                if event.type == pygame.MOUSEBUTTONDOWN and event.button == 1:
                    choice = menu_hit(renderer.menu_hits, event.pos[0], event.pos[1])
                    if choice == "reprendre":
                        menu_open = False
                    elif choice == "sauvegarder":
                        if mp is not None and mp.role != "host":
                            toast("C'est l'hôte qui sauvegarde la partie.")
                        else:
                            persist()
                            toast("Partie sauvegardée.")
                    elif choice == "principal":
                        leave()
                        return "menu", ""
                    elif choice == "quitter":
                        leave()
                        return "quit", ""
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
                            uid = ui["event_open"]

                            def chosen(res, uid=uid):
                                if events.find(state, uid) is None:
                                    if ui["event_open"] == uid:
                                        close_event()
                                else:
                                    ui["answered"].discard(uid)
                                    say(res)

                            if mp is not None:
                                # La reponse part chez l'hote : la carte se ferme deja.
                                ui["answered"].add(uid)
                                close_event()
                            issue(commands.make(me(), "event", uid, i), chosen)
                            break
            elif ui["situation_open"] is not None:
                if event.type == pygame.MOUSEBUTTONDOWN and event.button == 1:
                    from src.kora.render_situations import window_hit

                    hit = window_hit(renderer.situation_window, event.pos[0], event.pos[1])
                    if hit != "box":
                        situation_click(hit)
            elif ui["found"] is not None:
                if event.type == pygame.MOUSEBUTTONDOWN and event.button == 1:
                    from src.kora.render_village import found_hit

                    found_click(found_hit(renderer.found_hits, event.pos[0], event.pos[1]))
            elif event.type == pygame.MOUSEWHEEL:
                tlay = renderer.side_hits.get("tech") if side_panel == "savoirs" else None
                wx_, wy_ = pygame.mouse.get_pos()
                if tlay and tlay.get("numbers") is None and _in_rect(tlay["view"], wx_, wy_):
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
                    if side_hit(renderer.side_hits, mx, my) is None and not screens.under_mouse(renderer, ui, mx, my):
                        dragging = True
                        drag_button = event.button
                        last_mouse = event.pos
                elif event.button == 1:
                    mx, my = event.pos
                    ui_hit = hud_hit(renderer.hud_hits, mx, my)
                    if ui_hit == "pause":
                        toggle_pause()
                        continue
                    if isinstance(ui_hit, tuple) and ui_hit[0] == "speed":
                        set_speed(ui_hit[1])
                        continue
                    if ui_hit == "bar":
                        continue
                    scr, schoice = screens.hit(renderer, ui, mx, my)
                    if scr is not None:
                        # Le grand ecran ouvert (screens.py) prend le clic ;
                        # un clic hors de lui (et des onglets) le ferme.
                        if schoice is not None:
                            if schoice != "panel":
                                screen_clicks[scr.name](schoice)
                            continue
                        if side_hit(renderer.side_hits, mx, my) is None:
                            screens.close_all(ui)
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
                    from src.kora import render_battle

                    bhit = render_battle.hit(renderer.battle_hits, mx, my)
                    if bhit is not None:
                        from src.kora import battle as _battle

                        bt = next((x for x in _battle.battles(state) if x.uid == renderer.battle_hits.get("uid")), None)
                        if bt is not None and bhit == "retreat":
                            mine_band = next((b for b in bt.attackers + bt.defenders if b in state.bands and state.bands[b].tribe_id == me()), None)
                            if mine_band is not None:
                                issue(commands.make(me(), "battle_retreat", mine_band))
                        elif bt is not None and bhit == "see":
                            show_place(bt.hex)
                        continue
                    from src.kora.render_situations import banner_hit

                    sit_uid = banner_hit(renderer.situation_hits, mx, my)
                    if sit_uid is not None:
                        open_situation(sit_uid)
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
                    if hit is not None and hit.tribe_id == state.viewer and hit.village and not shift:
                        # Un clic sur un de vos villages ouvre son ecran.
                        selected = hit.id
                        open_village(hit.village)
                        continue
                    if hit is not None and hit.tribe_id == state.viewer:
                        if shift and selected not in (None, hit.id):
                            # Rejoindre : les deux bandes se reunissent.
                            band = state.bands.get(selected)
                            if band is not None and chiefs.obeys(state, band):
                                issue(commands.make(me(), "march", selected, hit.id))
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
        if mp is not None:
            # Le temps est a l'hote : il annonce les semaines, chacun les calcule.
            mp.pump(dt)
            if mp.state is not state:
                # Partie recopiee depuis l'hote (un ecart, un retour).
                state = mp.state
                last_log_seq = log_of(state, state.viewer).seq
                renderer._layer_key = None
                if selected not in state.bands:
                    selected = None
            for then, res in mp.take_results():
                (then or say)(res)
            for text in mp.take_notes():
                toast(text)
            ui["answered"] = {u for u in ui["answered"] if events.find(state, u) is not None}
            if mp.ended:
                leave()
                return "menu", mp.ended
            if mp.role == "host" and state.tick_count > 0 and state.tick_count % 8 == 0 and state.tick_count != last_auto:
                persist()
                last_auto = state.tick_count
        elif not menu_open and not state.clock.paused and not human_dead(state, state.viewer):
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
        if log_of(state, state.viewer).seq > last_log_seq:
            fresh = [e for e in log_of(state, state.viewer).entries if e.seq > last_log_seq]
            for entry in fresh:
                toasts.append(
                    {
                        "text": entry.text,
                        "age": 0.0,
                        "seq": entry.seq,
                        "hex": entry.hex,
                        "combat": entry.kind is LogKind.COMBAT,
                        "kind": entry.kind.value,
                    }
                )
            last_log_seq = log_of(state, state.viewer).seq
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
            or ui["situation_open"] is not None
            or screens.under_mouse(renderer, ui, mx, my)
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
        if ui["situation_open"] is not None and situations.find(state, ui["situation_open"]) is None:
            close_situation()
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
        if mp is not None:
            from src.kora import render_menu

            render_menu.draw_mp_overlay(renderer, mp, state, chat_text)
        pygame.display.flip()
