from __future__ import annotations

import random

import pygame

from src.kora import (
    battle as _battle,
    chiefdom,
    chiefs,
    commands,
    diplo,
    events,
    goods,
    grain,
    influence,
    laws,
    layout,
    memory,
    money,
    net,
    orders,
    places,
    render_battle,
    render_menu,
    music,
    render_tech,
    render_treasury,
    screens,
    session,
    sites,
    situations,
    tech,
    villages,
)
from src.kora.globe import (
    FOCUS_ZOOM,
    clamp_pitch,
    hex_to_globe_screen,
    look_at_hex,
    orbit_sensitivity,
    pixel_to_hex_globe,
    view_params,
)
from src.kora.bands import is_army
from src.kora.types import Hex
from src.kora.log import FILTER_ALL, LogKind
from src.kora.persist import (
    default_save_path,
    latest_save,
    list_saves,
    new_save_path,
    trash_save,
    load_game,
    load_prefs,
    multi_save_path,
    peek_save,
    save_game,
    save_prefs,
)
from src.kora.render import Renderer
from src.kora.layout import (
    FILTER_BY_HIT,
    HUD_HEIGHT,
    MAX_ZOOM,
    TREE_ZOOM_STEP,
    band_card_hit,
    band_screen_positions,
    fight_mark_screen_pos,
    fight_panel_hit,
    hud_hit,
    map_mode_hit,
    menu_hit,
    min_zoom_for,
    pan,
    side_hit,
    toast_hit,
    zoom_at,
)
from src.kora.sim import _default_world, consume_ticks, fight_at, hex_inspect, new_game, player_home_hex
from src.kora.gamestate import human_dead, log_of
from src.kora.vision import is_explored, is_visible, vision_of
from src.kora.situations import SPECS
from src.kora.render_situations import banner_hit, window_hit
from src.kora.render_village import found_hit
from src.kora.render_panels import army_ready, commerce_ready, wars_ready


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


def _seen_village_at_pixel(state, x, y, zoom, globe_yaw, globe_pitch, sw, sh):
    """Le peuple d'un village etranger qu'on connait sous la souris : dans le
    brouillard, d'apres la memoire du joueur (memory.py) ; 0 sinon."""
    vis = vision_of(state, state.viewer)
    if vis is None:
        return 0
    gcx, gcy, focal, dist = view_params(zoom, sw, sh, HUD_HEIGHT)
    best, hit = 14.0, 0
    for _sid, (q, r, kind, tid, _w, _lord) in sorted(vis.sites.items()):
        if kind != "village" or tid == state.viewer:
            continue
        h = Hex(q, r)
        if h in vis.visible:
            continue
        pos = hex_to_globe_screen(h, state.world, globe_yaw, globe_pitch, gcx, gcy, focal, dist)
        if pos is None:
            continue
        d = ((pos[0] - x) ** 2 + (pos[1] - y) ** 2) ** 0.5
        if d < best:
            best, hit = d, tid
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


def _continue_boot(worlds, sw: int, sh: int, path=None):
    """Une partie sauvegardee (par defaut la plus recente qui se lit :
    persist.latest_save) ; None si elle ne se lit pas (elle reste ou elle
    est : le menu Charger la montre)."""
    path = path or latest_save()
    if path is None:
        return None
    loaded = load_game(path, worlds.fresh())
    if loaded is None:
        return None
    state, view = loaded
    return _start_view(state, _refresh_selection(state, view.get("selected")), sw, sh)


def _fresh_seed() -> int:
    """La graine d'une partie neuve (le hasard de la machine : l'interface
    seulement ; la partie, elle, la garde et la sauve)."""
    return random.SystemRandom().randrange(1, 2 ** 30)


def _new_boot(worlds, setup: dict | None, sw: int, sh: int):
    """Une partie neuve (menu de demarrage) : elle aura sa propre
    sauvegarde (persist.new_save_path) ; les autres restent."""
    # Chaque partie tire son monde (les savoirs tires, draws.py).
    setup = dict(setup or {})
    setup.setdefault("seed", _fresh_seed())
    state = new_game(worlds.fresh(), setup=setup)
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
        "people_scroll": 0,
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
        "country_open": False,
        "country_tab": "lois",
        "law_confirm": None,
        "levy": "troupe",
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
    # La musique (music.py) : une pour tout le programme, menu et parties.
    director = music.Director(load_prefs())
    while True:
        choice = title_screen(renderer, clock, worlds, message, director)
        message = ""
        sw, sh = renderer.screen.get_size()
        if choice[0] == "quit":
            break
        mp = None
        save_path = None
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
            if choice[0] in ("continue", "load"):
                save_path = latest_save() if choice[0] == "continue" else choice[1]
                boot = _continue_boot(worlds, sw, sh, save_path)
                if boot is None:
                    message = "Cette sauvegarde ne se lit pas (autre version du jeu ?)."
                    continue
            else:
                save_path = new_save_path()
                boot = _new_boot(worlds, choice[1], sw, sh)
        _settle_memory()
        outcome, message = play(renderer, clock, boot, mp, save_path, director)
        if outcome == "quit":
            break
    pygame.quit()


def _remember(setup: dict) -> None:
    """Le nom, la couleur, les bonus et la derniere adresse : proposes la
    prochaine fois (reglages.json, a cote des sauvegardes)."""
    prefs = load_prefs()
    for key in ("name", "color", "bonuses", "address"):
        if setup.get(key):
            prefs[key] = list(setup[key]) if key in ("color", "bonuses") else setup[key]
    save_prefs(prefs)


def _prefilled(setup: dict) -> dict:
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


class Settings:
    """La fenetre des Reglages (render_menu.draw_settings) : le volume de la
    musique (curseur, - et +), la couper, l'ecouter ; enregistres dans
    reglages.json a chaque changement. Commune au menu de demarrage et au
    menu de la partie."""

    def __init__(self, director) -> None:
        self.director = director
        self.open = False
        self.drag = False

    def show(self) -> None:
        self.open = True

    def close(self) -> None:
        self.open = False
        self.drag = False
        self.director.listening = False

    def _set(self, volume: float, on: bool | None = None) -> None:
        self.director.set_volume(volume, on)
        save_prefs(load_prefs() | self.director.prefs())

    def handle(self, renderer, event) -> bool:
        """Traite l'evenement si la fenetre est ouverte (True : il est pris)."""
        if not self.open:
            return False
        lay = getattr(renderer, "settings_hits", None) or {}
        if event.type == pygame.KEYDOWN and event.key == pygame.K_ESCAPE:
            self.close()
        elif event.type == pygame.MOUSEBUTTONDOWN and event.button == 1 and lay:
            hit = render_menu.settings_hit(lay, *event.pos)
            d = self.director
            if hit in ("close", "dehors"):
                self.close()
            elif hit == "minus":
                self._set(round(d.volume - render_menu.VOLUME_STEP, 2))
            elif hit == "plus":
                self._set(round(d.volume + render_menu.VOLUME_STEP, 2))
            elif hit == "toggle":
                self._set(d.volume, not d.on)
            elif hit == "listen" and d.on:
                d.listening = not d.listening
            elif hit == "track":
                self.drag = True
                self._set(render_menu.settings_value(lay, event.pos[0]))
        elif event.type == pygame.MOUSEMOTION and self.drag and lay:
            self.director.set_volume(render_menu.settings_value(lay, event.pos[0]))
        elif event.type == pygame.MOUSEBUTTONUP and event.button == 1 and self.drag:
            self.drag = False
            self._set(self.director.volume)
        return True

    def draw(self, renderer) -> None:
        if self.open:
            d = self.director
            render_menu.draw_settings(renderer, d.volume, d.on, d.listening)


def title_screen(renderer, clock, worlds, message: str = "", director=None):
    """Le menu de demarrage, la creation du peuple, les sauvegardes, le menu
    du multijoueur. Rend ("continue",), ("load", fichier), ("new", setup),
    ("host", setup), ("join", setup), ("resume_mp",) ou ("quit",)."""

    scene = render_menu.TitleScene(worlds.shown)
    saves = list_saves()
    latest = next((s for s in saves if s["info"] is not None), None)
    info = latest["info"] if latest is not None else None
    multi = peek_save(multi_save_path())
    load = {"scroll": 0, "confirm": None, "message": ""}
    rng = random.Random()
    setup = None
    page = "title"
    hint = ""
    t = 0.0
    director = director or music.Director(load_prefs())
    settings = Settings(director)
    while True:
        dt = clock.tick(60) / 1000.0
        t += dt
        director.update(None, dt)
        for event in pygame.event.get():
            if event.type == pygame.QUIT:
                return ("quit",)
            if event.type == pygame.VIDEORESIZE:
                renderer.screen = pygame.display.set_mode((event.w, event.h), pygame.RESIZABLE)
                continue
            if settings.handle(renderer, event):
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
            if page == "load":
                # Charger une partie : jouer, supprimer (un second clic), defiler.
                if event.type == pygame.KEYDOWN and event.key == pygame.K_ESCAPE:
                    page = "title"
                elif event.type == pygame.MOUSEWHEEL:
                    load["scroll"] = max(0, load["scroll"] - event.y)
                elif event.type == pygame.MOUSEBUTTONDOWN and event.button == 1:
                    hits = getattr(renderer, "load_hits", None)
                    hit = render_menu.load_hit(hits, *event.pos, saves) if hits else None
                    if hit == "retour":
                        page = "title"
                    elif hit and hit.startswith("jouer:"):
                        return ("load", saves[int(hit[6:])]["path"])
                    elif hit and hit.startswith("suppr:"):
                        i = int(hit[6:])
                        if load["confirm"] != i:
                            load["confirm"] = i
                        else:
                            load["confirm"] = None
                            gone = saves[i]["path"]
                            load["message"] = f"{gone.name} est à la corbeille." if trash_save(gone) else "Impossible de la supprimer."
                            saves = list_saves()
                            latest = next((s for s in saves if s["info"] is not None), None)
                            info = latest["info"] if latest is not None else None
                    else:
                        load["confirm"] = None
                continue
            if event.type == pygame.KEYDOWN:
                if event.key == pygame.K_ESCAPE:
                    return ("quit",)
                if event.key in (pygame.K_RETURN, pygame.K_KP_ENTER) and info is not None:
                    return ("continue",)
            elif event.type == pygame.MOUSEBUTTONDOWN and event.button == 1:
                hits = getattr(renderer, "title_hits", None)
                hit = render_menu.title_hit(hits, *event.pos, can_continue=info is not None, can_load=bool(saves)) if hits else None
                if hit == "continuer":
                    return ("continue",)
                if hit == "charger":
                    page = "load"
                    load = {"scroll": 0, "confirm": None, "message": ""}
                    continue
                if hit == "reglages":
                    settings.show()
                    continue
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
        elif page == "load":
            render_menu.draw_load(renderer, scene, saves, t, load["scroll"], load["confirm"], load["message"])
        else:
            render_menu.draw_title(renderer, scene, info, t, message, len(saves))
        if setup is not None:
            render_menu.draw_setup(renderer, setup, t, info if setup.get("mode", "solo") == "solo" else None, hint)
        settings.draw(renderer)
        pygame.display.flip()


def _multiplayer(renderer, clock, worlds, choice):
    """Heberger, rejoindre ou reprendre : jusqu'au lancement de la partie.
    Rend ("play", session, state), ("back", message) ou ("quit",)."""
    import threading

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


class Play:
    """Une partie, jusqu'au retour au menu ("menu", message) ou au depart
    ("quit", ""). mp : la session multijoueur (session.py), sinon solo.

    L'etat de la partie a l'ecran (camera, selection, panneaux, fenetres)
    est dans self ; une methode par chose a faire (les clics de chaque
    ecran, les ordres) ; run() : la boucle, _on_event : un evenement,
    _frame : une image."""

    def __init__(self, renderer, clock, boot, mp=None, save_path=None, director=None) -> None:
        self.renderer, self.clock, self.boot, self.mp = renderer, clock, boot, mp
        # La musique de guerre (music.py) et la fenetre des reglages.
        self.director = director or music.Director(load_prefs())
        self.settings = Settings(self.director)
        self.screen = self.renderer.screen
        self.state, self.selected, self.camera_x, self.camera_y, self.zoom, self.globe_yaw, self.globe_pitch = self.boot
        self.renderer.map_mode = "zones"
        self.renderer._layer_key = None
        self.dragging = False
        self.drag_button = 0
        self.last_mouse = (0, 0)
        # La toile des savoirs se deplace a la souris (layout.tech_panel_layout) :
        # on glisse depuis n'importe ou ; sans bouger, un clic choisit le savoir.
        self.tech_drag = 0
        self.tech_press = {"at": (0, 0), "moved": False, "pick": None}
        # Le curseur du budget qu'on glisse (render_treasury), le dernier ordre.
        self.slider_drag = None
        self.slider_sent = None
        # Le clic droit : glisser fait tourner la planete ; un clic sans
        # bouger sur une bande etrangere, avec une de vos bandes choisie,
        # l'attaque (au relachement).
        self.right_press = None
        # Le rapport de force au survol d'un etranger (orders.attack_preview).
        self.preview_cache: dict = {}
        self.acc = 0.0
        # En multijoueur, seul l'hote sauvegarde (a part : la partie solo reste).
        self.save_path = multi_save_path() if self.mp is not None else (save_path or default_save_path())
        self.last_auto = -1
        # Multijoueur : le message qu'on ecrit (Entree), None sinon.
        self.chat_text = None
        self.menu_open = False
        self.side_panel = None
        self.tech_pick = None
        self.log_filter = FILTER_ALL
        self.log_newest = True
        self.pinned_hex = None
        self.open_fight = None
        self.toasts: list[dict] = []
        self.last_log_seq = log_of(self.state, self.state.viewer).seq
        self.ui: dict = _fresh_ui()
        self.resume_after_event = False
        self.resume_after_found = False
        self.resume_after_situation = False
        self.confirm = {"band": None, "until": 0.0}
        self.now = 0.0

        # Les clics de chaque grand ecran (screens.SCREENS).
        self.screen_clicks = {
            "village": self.village_click, "commerce": self.trade_click, "tresor": self.treasury_click, "pays": self.country_click,
            "guerres": self.wars_click,
        }
        assert set(self.screen_clicks) == set(screens.BY_NAME)


    def persist(self) -> None:
        if self.mp is not None and self.mp.role != "host":
            return
        save_game(
            self.state,
            self.save_path,
            _view(self.camera_x, self.camera_y, self.zoom, self.selected, self.globe_yaw, self.globe_pitch),
        )

    def leave(self) -> None:
        self.persist()
        self.settings.close()
        self.director.stop(1.5)
        if self.mp is not None:
            self.mp.close()

    def say(self, res) -> None:
        if res.get("msg"):
            self.toast(res["msg"])

    def issue(self, cmd, then=None) -> None:
        """Un ordre du joueur (commands.py) : tout de suite en solo ; par
        l'hote en multijoueur. then recoit la reponse quand il s'applique."""
        then = then or self.say
        if self.mp is None:
            then(commands.apply(self.state, cmd))
        else:
            self.mp.issue(cmd, then)

    def me(self) -> int:
        return self.state.viewer

    def toggle_pause(self) -> None:
        if self.mp is None:
            self.state.clock.toggle_pause()
        else:
            self.mp.toggle_pause()

    def set_speed(self, n: int) -> None:
        if self.mp is None:
            self.state.clock.set_speed(n)
        else:
            self.mp.set_speed(n)

    def toast(self, text: str, combat: bool = False) -> None:
        self.toasts.append({"text": text, "age": 0.0, "seq": -1, "hex": None, "combat": combat})
        self.toasts = self.toasts[-MAX_TOASTS:]

    def show_place(self, where) -> None:
        if where is None:
            return
        self.globe_yaw, self.globe_pitch = _look_hex(self.state, where)
        mark = fight_at(self.state, where)
        if mark is not None:
            self.open_fight = mark
        else:
            self.pinned_hex = where if hex_inspect(self.state, where) is not None else None

    def band_action(self, action: str, band_id=None) -> None:
        target = self.selected if band_id is None else band_id
        if action == "next":
            self.selected = _next_player_band(self.state, self.selected)
            if self.selected is not None:
                self.globe_yaw, self.globe_pitch = _look_hex(self.state, self.state.bands[self.selected].position)
            return
        if target is None or target not in self.state.bands:
            return
        band = self.state.bands[target]
        if action == "village":
            why = orders.band_actions(self.state, target).get("village", "?")
            if why:
                self.toast(why)
            elif band.village:
                self.open_village(band.village)
            else:
                self.open_found(target)
            return
        def done(res):
            if res["msg"]:
                self.toast(res["msg"])
            elif band_id is None and res["sel"] is not None:
                self.selected = res["sel"]

        self.issue(commands.make(self.me(), "band", target, action), done)

    def open_found(self, band_id) -> None:
        """Fonder un village : un choix qui arrete le temps (en solo)."""
        if self.ui["found"] is None and self.mp is None:
            self.resume_after_found = not self.state.clock.paused
            self.state.clock.paused = True
        self.ui["found"] = band_id
        self.ui["found_oath"] = None
        self.side_panel = None

    def close_found(self) -> None:
        self.ui["found"] = None
        self.ui["found_oath"] = None
        if self.resume_after_found:
            self.state.clock.paused = False
        self.resume_after_found = False

    def open_village(self, site_id) -> None:
        screens.open(self.ui, "village", site_id)
        self.ui["village_pick"] = None
        self.side_panel = None

    def open_screen(self, name: str, toggle: bool = False) -> None:
        """Un grand ecran (screens.py) : les autres et les panneaux se ferment."""
        if toggle:
            screens.toggle(self.ui, name)
        else:
            screens.open(self.ui, name)
        self.side_panel = None

    def treasury_click(self, choice) -> None:
        """Clic dans l'ecran du tresor : le budget passe par commands.py."""
        if choice == "mclose":
            screens.close_all(self.ui)
            return
        tribe = self.state.tribes.get(self.me())
        if tribe is None or ":" not in choice:
            return
        kind, key = choice.split(":", 1)
        bud = money.budget(tribe)
        if kind in ("mminus", "mplus"):
            self.set_slider(key, render_treasury.slider_step(bud, key, -1 if kind == "mminus" else 1))
        elif kind == "mslide":
            # Un clic sur la piste pose le curseur ; on peut ensuite le glisser.
            self.slider_drag = key
            self.set_slider(key, render_treasury.slider_value(self.renderer.treasury_hits, key, pygame.mouse.get_pos()[0]))

    def country_click(self, choice) -> None:
        """Clic dans l'ecran du pays : une loi passe par commands.py ; une
        reforme des nombres demande un second clic."""
        if choice == "lclose":
            screens.close_all(self.ui)
            return
        if choice.startswith("ltab:"):
            self.ui["country_tab"] = choice[5:]
            return
        if choice.startswith("law:"):
            _k, law_id, option = choice.split(":", 2)
            if law_id == "base" and self.ui.get("law_confirm") != (law_id, option):
                self.ui["law_confirm"] = (law_id, option)
                return
            self.ui["law_confirm"] = None
            self.issue(commands.make(self.me(), "law", law_id, option))

    def wars_click(self, choice) -> None:
        """Clic dans l'ecran des guerres : choisir une guerre, voir une
        troupe, un village ou un combat ; exiger la soumission, proposer la
        treve (commands.py, "diplo") ; leur fiche (Peuples)."""
        if choice == "wclose":
            screens.close_all(self.ui)
            return
        kind, _sep, rest = choice.partition(":")
        if kind == "wpick":
            self.ui["war_pick"] = int(rest)
        elif kind == "wsee":
            band = self.state.bands.get(int(rest))
            if band is not None:
                screens.close_all(self.ui)
                if band.tribe_id == self.state.viewer:
                    self.selected = band.id
                self.globe_yaw, self.globe_pitch = _look_hex(self.state, band.position)
        elif kind == "wsite":
            site = self.state.sites.get(int(rest))
            if site is not None:
                screens.close_all(self.ui)
                self.show_place(site.hex)
        elif kind == "whex":
            q, r = rest.split(":")
            screens.close_all(self.ui)
            self.show_place(Hex(int(q), int(r)))
        elif kind == "wact":
            action, tid = rest.split(":")
            tid = int(tid)
            if action == "fiche":
                screens.close_all(self.ui)
                self.open_diplomacy(tid)
                return
            verdict = diplo.evaluate(self.state, self.state.viewer, tid, action)
            if verdict.blocked:
                self.toast(verdict.blocked)
            elif diplo.on_cooldown(self.state, self.state.viewer, tid, action):
                self.toast("Vous avez déjà proposé cela récemment.")
            else:
                self.issue(commands.make(self.me(), "diplo", tid, action))

    def set_slider(self, key: str, value) -> None:
        """Un curseur du budget : l'ordre ne part que si la valeur change."""
        tribe = self.state.tribes.get(self.me())
        if tribe is not None and money.budget(tribe)[key] != value and self.slider_sent != (key, value):
            self.slider_sent = (key, value)
            self.issue(commands.make(self.me(), "budget", key, value))

    def trade_click(self, choice) -> None:
        """Clic dans l'ecran du commerce."""
        if choice == "tclose":
            screens.close_all(self.ui)
            return
        if choice.startswith("tpartner:"):
            self.ui["trade_partner"] = int(choice.split(":")[1])
            return
        if choice.startswith("tgood:"):
            self.ui["trade_good"] = choice.split(":")[1]
            return
        if choice.startswith("tdir:"):
            self.ui["trade_sell"] = choice.endswith("sell")
            return
        if choice.startswith("tlevel:"):
            self.ui["trade_level"] = int(choice.split(":")[1])
            return
        if choice == "topen":
            partner = self.ui["trade_partner"]
            good = self.ui["trade_good"] or goods.GOODS[0]
            if partner is None:
                self.toast("Choisissez un partenaire (il faut un accord commercial).")
                return
            why = goods.open_block(self.state, self.state.viewer, partner, good, self.ui["trade_sell"], self.ui["trade_level"])
            if why:
                self.toast(why)
                return
            self.issue(commands.make(self.me(), "route_open", partner, good, self.ui["trade_sell"], self.ui["trade_level"]))
            return
        if choice.startswith(("rlevel:", "rclose:")):
            parts = choice.split(":")
            idx = int(parts[1])
            if idx >= len(self.renderer.trade_routes):
                return
            route = self.renderer.trade_routes[idx]
            if choice.startswith("rclose:"):
                self.issue(commands.make(self.me(), "route_close", commands.route_key(route)))
                return
            level = int(parts[2])
            why = goods.level_block(self.state, self.state.viewer, route, level)
            if why:
                self.toast(why)
            else:
                self.issue(commands.make(self.me(), "route_level", commands.route_key(route), level))
            return
        if choice.startswith("tpropose:"):
            tid = int(choice.split(":")[1])
            if diplo.on_cooldown(self.state, self.state.viewer, tid, "commerce"):
                self.toast("Vous avez déjà proposé cela récemment.")
            else:
                self.issue(commands.make(self.me(), "diplo", tid, "commerce"))
            return

    def village_click(self, choice) -> None:
        """Clic dans l'ecran du village."""
        site = self.state.sites.get(self.ui["village_open"])
        home = places.band_of(self.state, site) if site is not None and site.kind == "village" else None
        if home is None or choice == "vclose":
            screens.close_all(self.ui)
            return
        if choice.startswith("vb:"):
            self.ui["village_pick"] = choice[3:]
            return
        if choice == "vgrain":
            why = grain.quote(self.state, home.tribe_id, site.id)["why"]
            if why:
                self.toast(why)
            else:
                self.issue(commands.make(self.me(), "grain", site.id))
            return
        if choice.startswith("vpage:"):
            self.ui["village_page"] = choice[6:]
            return
        if choice.startswith("crate:"):
            self.issue(commands.make(self.me(), "levy_rate", int(choice[6:])))
            return
        if choice == "cfeast":
            self.issue(commands.make(self.me(), "feast"))
            return
        if choice.startswith("ccharge:"):
            _k, idx, charge = choice.split(":", 2)
            fams = self.state.tribes[home.tribe_id].families or []
            if int(idx) < len(fams):
                self.issue(commands.make(self.me(), "charge", fams[int(idx)]["id"], charge))
            return
        if choice == "vtrade":
            screens.open(self.ui, "commerce")
            return
        if choice.startswith(("vteam+:", "vteam-:")):
            cid = choice.split(":")[1]
            if not chiefs.obeys(self.state, home):
                self.toast(orders.INDOCILE)
                return
            if choice.startswith("vteam+:"):
                why = goods.add_block(self.state, site, cid)
                if why:
                    self.toast(why)
                else:
                    self.issue(commands.make(self.me(), "teams", site.id, cid, 1))
            elif goods.teams_of(site, cid) > 0:
                self.issue(commands.make(self.me(), "teams", site.id, cid, -1))
            return
        if choice == "vbuild":
            pick = self.ui["village_pick"] or next(
                (b for b in villages.BUILD_ORDER if villages.building_status(self.state, site, b) == "possible"), None
            )
            if pick is None:
                return
            why = villages.build_block(self.state, home.id, pick) or ("" if chiefs.obeys(self.state, home) else orders.INDOCILE)
            if why:
                self.toast(why)
            else:
                self.issue(commands.make(self.me(), "build", home.id, pick))
            return
        if choice.startswith("levy:"):
            self.ui["levy"] = choice[5:]
            return
        if choice == "vraise":
            share = villages.LEVY_SHARE.get(self.ui["levy"], villages.LEVY_SHARE["troupe"])
            why = villages.army_block(self.state, home.id, share) or ("" if chiefs.obeys(self.state, home) else orders.INDOCILE)
            if why:
                self.toast(why)
            else:
                self.issue(commands.make(self.me(), "raise", home.id, self.ui["levy"], None))
            return
        if choice.startswith(("vsee:", "vrecall:", "vreequip:")):
            bid = int(choice.split(":")[1])
            army = self.state.bands.get(bid)
            if army is None:
                return
            if choice.startswith("vsee:"):
                self.selected = bid
                self.ui["village_open"] = None
                self.globe_yaw, self.globe_pitch = _look_hex(self.state, army.position)
            elif choice.startswith("vreequip:"):
                why = villages.reequip_block(self.state, bid)
                if why:
                    self.toast(why)
                else:
                    self.issue(commands.make(self.me(), "reequip", bid))
            else:
                why = villages.dissolve_block(self.state, bid)
                if why:
                    self.toast(why)
                else:
                    self.issue(commands.make(self.me(), "dissolve", bid))
            return

    def army_click(self, choice) -> None:
        """Clic dans le panneau Armee."""
        kind, _sep, rest = choice.partition(":")
        if kind == "asize":
            sid, key = rest.split(":")
            self.ui.setdefault("army_size", {})[int(sid)] = key
            return
        if kind in ("araise", "avillage"):
            site = self.state.sites.get(int(rest))
            home = places.band_of(self.state, site) if site is not None and site.kind == "village" else None
            if home is None:
                return
            if kind == "avillage":
                self.side_panel = None
                self.open_village(site.id)
                return
            key = self.ui.get("army_size", {}).get(site.id, "troupe")
            share = villages.LEVY_SHARE.get(key, villages.LEVY_SHARE["troupe"])
            why = villages.army_block(self.state, home.id, share) or ("" if chiefs.obeys(self.state, home) else orders.INDOCILE)
            if why:
                self.toast(why)
            else:
                self.issue(commands.make(self.me(), "raise", home.id, key, None))
            return
        bid = int(rest)
        army = self.state.bands.get(bid)
        if army is None:
            return
        if kind == "asee":
            self.selected = bid
            self.globe_yaw, self.globe_pitch = _look_hex(self.state, army.position)
            return
        why = villages.dissolve_block(self.state, bid)
        if why:
            self.toast(why)
        else:
            self.issue(commands.make(self.me(), "dissolve", bid))

    def found_click(self, choice) -> None:
        if choice is None:
            return
        if choice == "found_cancel":
            self.close_found()
            return
        if choice.startswith("oath:"):
            self.ui["found_oath"] = choice[5:]
            return
        if choice == "found_ok":
            bid = self.ui["found"]
            if self.ui["found_oath"] not in villages.OATHS:
                self.toast("Choisissez d'abord le serment du village.")
                return
            why = villages.found_block(self.state, bid) if bid in self.state.bands else "Pas de bande"
            if why:
                self.toast(why)
                self.close_found()
                return
            oath = self.ui["found_oath"]
            self.close_found()

            def founded(res):
                self.say(res)
                if res["site"] is not None and res["site"] in self.state.sites:
                    self.open_village(res["site"])

            self.issue(commands.make(self.me(), "found", bid, oath), founded)

    def open_event(self, uid) -> None:
        if events.find(self.state, uid) is None:
            return
        if self.ui["event_open"] is None and self.mp is None:
            # Lire un evenement met en pause (en solo) ; on reprend en le fermant.
            self.resume_after_event = not self.state.clock.paused
            self.state.clock.paused = True
        self.ui["event_open"] = uid

    def close_event(self) -> None:
        self.ui["event_open"] = None
        if self.resume_after_event and not events.pending(self.state, self.state.viewer):
            self.state.clock.paused = False
        elif self.resume_after_event:
            self.state.clock.paused = False
        self.resume_after_event = False

    def open_situation(self, uid) -> None:
        if situations.find(self.state, uid) is None:
            return
        if self.ui["situation_open"] is None and self.mp is None:
            # Lire une crise met en pause (en solo) ; on reprend en fermant.
            self.resume_after_situation = not self.state.clock.paused
            self.state.clock.paused = True
        self.ui["situation_open"] = uid

    def close_situation(self) -> None:
        self.ui["situation_open"] = None
        if self.resume_after_situation:
            self.state.clock.paused = False
        self.resume_after_situation = False

    def situation_click(self, hit) -> None:
        inst = situations.find(self.state, self.ui["situation_open"])
        if inst is None or hit is None:
            self.close_situation()
            return
        if hit == "close":
            self.close_situation()
        elif hit == "place" and inst.center is not None:
            self.close_situation()
            self.show_place(inst.center)
        elif isinstance(hit, tuple) and hit[0] == "action":
            actions = SPECS[inst.sid].actions
            if hit[1] < len(actions):
                self.issue(commands.make(self.me(), "situation", inst.uid, actions[hit[1]].id))

    def order_move(self, hx) -> bool:
        band = self.state.bands.get(self.selected) if self.selected is not None else None
        if band is None:
            return False
        if not chiefs.obeys(self.state, band):
            self.toast(orders.INDOCILE + " : rapprochez le chef ou honorez le clan.")
            return False
        if band.village:
            self.toast("Un village ne bouge pas : formez une bande [S] pour partir.")
            return False
        if band.homebound:
            self.toast(orders.HOMEBOUND + ".")
            return False
        self.issue(commands.make(self.me(), "goto", self.selected, hx.q, hx.r))
        return True

    def _attack_preview(self, foe_id: int):
        """Le rapport de force sous la souris : recalcule quand la bande, la
        proie ou la semaine changent (il cherche un chemin)."""
        band, prey = self.state.bands.get(self.selected), self.state.bands.get(foe_id)
        if band is None or prey is None:
            return None
        key = (band.id, prey.id, band.position, prey.position, band.population, prey.population, self.state.step)
        if self.preview_cache.get("key") != key:
            self.preview_cache = {"key": key, "value": orders.attack_preview(self.state, band.id, prey.id)}
        return self.preview_cache["value"]

    def _foe_under(self, mx: int, my: int):
        """La bande etrangere sous la souris, si une de vos bandes est
        choisie (le clic droit l'attaquera) ; None sinon."""
        mine = self.state.bands.get(self.selected) if self.selected is not None else None
        if mine is None or mine.tribe_id != self.state.viewer:
            return None
        hit = _band_at_pixel(self.state, mx, my, self.zoom, self.globe_yaw, self.globe_pitch, self.sw, self.sh)
        return hit.id if hit is not None and hit.tribe_id != self.state.viewer else None

    def _country_at(self, h) -> int:
        """Le peuple etranger dont on voit le village sur la case, ou dans la
        zone duquel elle est (0 : aucun, ou un peuple qu'on ne connait pas)."""
        me = self.state.viewer
        h = self.state.world.canonicalize(h) or h
        if not is_explored(self.state, h, me):
            return 0
        if is_visible(self.state, h, me):
            site = sites.site_on_hex(self.state, h)
            tid = site.tribe_id if site is not None and site.tribe_id != me else influence.foreign_zone(self.state.world, h, me)
        else:
            # Le brouillard : ce dont on se souvient (memory.py).
            seen = memory.site_at(self.state, h, me)
            zone = vision_of(self.state, me).zones.get(self.state.world._index(h))
            tid = seen[1][3] if seen is not None else (zone[0] if zone else 0)
            tid = 0 if tid == me else tid
        return tid if tid and tid in diplo.contacts_of(self.state, me) else 0

    def open_diplomacy(self, tid: int) -> None:
        """L'ecran Peuples sur ce peuple ; un tributaire n'a pas de diplomatie
        a lui : c'est son grand suzerain qui parle pour lui."""
        me = self.state.viewer
        if tid == me or tid not in self.state.tribes:
            return
        lord = chiefdom.top_lord(self.state, tid)
        if lord != tid and lord != me and lord in diplo.contacts_of(self.state, me):
            self.toast(f"Les {self.state.tribes[tid].name} sont tributaires des {self.state.tribes[lord].name} : c'est à eux de parler.")
            tid = lord
        elif tid not in diplo.contacts_of(self.state, me):
            return
        screens.close_all(self.ui)
        self.side_panel = "peuples"
        self.ui["people_pick"] = tid

    def order_raid(self, target) -> None:
        band = self.state.bands.get(self.selected) if self.selected is not None else None
        if band is None:
            return
        if not chiefs.obeys(self.state, band):
            self.toast(orders.INDOCILE + ".")
            return
        if band.village:
            self.toast("Un village ne bouge pas : formez une bande [S] pour aller raider.")
            return
        if band.homebound:
            self.toast(orders.HOMEBOUND + ".")
            return
        if target.tribe_id != self.state.viewer and diplo.at_peace(self.state, self.state.viewer, target.tribe_id):
            name = self.state.tribes[target.tribe_id].name
            if self.confirm["band"] != target.id or self.now > self.confirm["until"]:
                self.confirm["band"] = target.id
                self.confirm["until"] = self.now + CONFIRM_SECONDS
                self.toast(f"Pacte avec les {name} : clic droit encore pour attaquer (trahison, prestige -10).", True)
                return
            self.confirm["band"] = None
        self.issue(commands.make(self.me(), "march", self.selected, target.id))

    def side_click(self, choice) -> bool:
        """Clic dans un panneau lateral ; True si traite."""
        if not isinstance(choice, str):
            return False
        if choice in ("tview", "tzoom_in", "tzoom_out", "tcenter"):
            lay = self.renderer.side_hits.get("tech")
            if not lay:
                return True
            mx, my = pygame.mouse.get_pos()
            view, world, cam = lay["view"], lay["world"], lay["cam"]
            if choice == "tview":
                # Glisser la toile (le clic gauche sur un savoir le choisit).
                self.tech_drag = 1
                self.last_mouse = (mx, my)
            elif choice == "tcenter":
                self.ui["tech_cam"] = render_tech.focus_cam(self.state, *self.screen.get_size())
            else:
                factor = TREE_ZOOM_STEP if choice == "tzoom_in" else 1.0 / TREE_ZOOM_STEP
                self.ui["tech_cam"] = zoom_at(cam, view, world, view[0] + view[2] / 2, view[1] + view[3] / 2, factor)
            return True
        if choice.startswith("log_"):
            seq = int(choice[4:])
            entry = next((e for e in log_of(self.state, self.state.viewer).entries if e.seq == seq), None)
            if entry is not None:
                self.show_place(entry.hex)
            return True
        if choice.startswith("tab_"):
            key = choice[4:]
            if key in screens.BY_NAME:
                # Commerce, Tresor : des onglets qui ouvrent un grand ecran.
                self.open_screen(key, toggle=True)
                return True
            self.side_panel = None if self.side_panel == key else key
            screens.close_all(self.ui)
            return True
        if choice == "trade_with":
            self.open_screen("commerce")
            self.ui["trade_partner"] = self.ui.get("people_pick")
            return True
        if choice.startswith(("vil_open:", "vil_see:", "vil_row:")):
            sid = int(choice.split(":")[1])
            site = self.state.sites.get(sid)
            if site is not None and site.kind == "village":
                if choice.startswith("vil_see:"):
                    self.show_place(site.hex)
                else:
                    self.open_village(sid)
            return True
        if choice.startswith("tech:"):
            self.tech_pick = choice[5:]
            return True
        if choice.startswith("ttab:"):
            self.ui["tech_tab"] = choice[5:]
            self.ui["base_confirm"] = None
            return True
        if choice == "nlaws":
            # La base des nombres est une loi : l'ecran du pays.
            self.open_screen("pays")
            return True
        if choice.startswith("era:"):
            self.ui["era"] = int(choice[4:])
            self.tech_pick = None
            return True
        if choice == "learn":
            if self.tech_pick is not None:
                self.issue(commands.make(self.me(), "learn", self.tech_pick))
            return True
        if choice in FILTER_BY_HIT:
            self.log_filter = FILTER_BY_HIT[choice]
            return True
        if choice == "sort_recent":
            self.log_newest = True
            return True
        if choice == "sort_ancien":
            self.log_newest = False
            return True
        if choice.startswith("tribe_row:"):
            bid = int(choice.split(":")[1])
            self.ui["tribe_pick"] = bid
            return True
        if choice.startswith("tribe_see:"):
            bid = int(choice.split(":")[1])
            if bid in self.state.bands:
                self.selected = bid
                self.ui["tribe_pick"] = bid
                self.globe_yaw, self.globe_pitch = _look_hex(self.state, self.state.bands[bid].position)
            return True
        if choice.startswith("tribe_honor:"):
            bid = int(choice.split(":")[1])
            why = chiefs.can_honor(self.state, bid)
            if why:
                self.toast(why)
            else:
                self.issue(commands.make(self.me(), "honor", bid))
            return True
        if choice.startswith(("arole:", "asize:", "araise:", "avillage:", "asee:", "adissolve:")):
            self.army_click(choice)
            return True
        if choice.startswith("promote:"):
            _k, bid, pid = choice.split(":")
            why = chiefs.can_promote(self.state, int(bid), int(pid))
            if why:
                self.toast(why)
            else:
                self.issue(commands.make(self.me(), "promote", int(bid), int(pid)))
            return True
        if choice.startswith("tribe_heir:"):
            bid = int(choice.split(":")[1])
            self.issue(commands.make(self.me(), "heir", bid))
            return True
        if choice.startswith("people:"):
            self.ui["people_pick"] = int(choice.split(":")[1])
            return True
        if choice == "people_see":
            tid = self.ui.get("people_pick")
            home = self.state.bands[self.selected].position if self.selected in self.state.bands else player_home_hex(self.state)
            band = _nearest_band_of(self.state, tid, home) if tid is not None else None
            if band is not None:
                self.globe_yaw, self.globe_pitch = _look_hex(self.state, band.position)
            return True
        if choice.startswith("gift:"):
            tid = self.ui.get("people_pick")
            if tid is not None:
                self.issue(commands.make(self.me(), "diplo", tid, "cadeau", float(choice.split(":")[1])))
            return True
        if choice.startswith("present:"):
            tid = self.ui.get("people_pick")
            if tid is not None:
                self.issue(commands.make(self.me(), "diplo", tid, "present", float(choice.split(":")[1])))
            return True
        if choice.startswith("invite:"):
            self.issue(commands.make(self.me(), "invite", int(choice.split(":")[1])))
            return True
        if choice.startswith("diplo:"):
            tid = self.ui.get("people_pick")
            action = choice.split(":")[1]
            if tid is not None:
                if diplo.on_cooldown(self.state, self.state.viewer, tid, action) and action not in ("rompre",):
                    self.toast("Vous avez déjà proposé cela récemment.")
                else:
                    self.issue(commands.make(self.me(), "diplo", tid, action))
            return True
        return choice == "panel"

    def run(self) -> tuple[str, str]:
        while True:
            dt = self.clock.tick(60) / 1000.0
            self.now += dt
            self.sw, self.sh = self.screen.get_size()
            for event in pygame.event.get():
                out = self._on_event(event)
                if out is not None:
                    return out
            # La musique de guerre : elle monte quand la guerre vous touche.
            self.director.update(self.state, dt)
            out = self._frame(dt)
            if out is not None:
                return out

    def _on_event(self, event):
        """Un evenement (touche, souris, fenetre) ; rend ("menu"|"quit", message)
        pour quitter la partie, sinon None."""
        if event.type == pygame.QUIT:
            self.leave()
            return "quit", ""
        elif self.settings.handle(self.renderer, event):
            return None
        elif event.type == pygame.KEYDOWN and self.chat_text is not None:
            # La discussion (multijoueur) : Entree envoie, Echap renonce.
            if event.key in (pygame.K_RETURN, pygame.K_KP_ENTER):
                if self.chat_text.strip():
                    self.mp.say(self.chat_text)
                self.chat_text = None
            elif event.key == pygame.K_ESCAPE:
                self.chat_text = None
            elif event.key == pygame.K_BACKSPACE:
                self.chat_text = self.chat_text[:-1]
            elif event.unicode and event.unicode.isprintable() and len(self.chat_text) < 160:
                self.chat_text += event.unicode
            return None
        elif event.type == pygame.KEYDOWN and self.mp is not None and event.key in (pygame.K_RETURN, pygame.K_KP_ENTER) and not self.menu_open:
            self.chat_text = ""
            return None
        elif event.type == pygame.KEYDOWN:
            return self._on_key(event)
        elif event.type == pygame.VIDEORESIZE:
            self.screen = pygame.display.set_mode((event.w, event.h), pygame.RESIZABLE)
            self.renderer.screen = self.screen
        elif self.menu_open:
            if event.type == pygame.MOUSEBUTTONDOWN and event.button == 1:
                choice = menu_hit(self.renderer.menu_hits, event.pos[0], event.pos[1])
                if choice == "reprendre":
                    self.menu_open = False
                elif choice == "sauvegarder":
                    if self.mp is not None and self.mp.role != "host":
                        self.toast("C'est l'hôte qui sauvegarde la partie.")
                    else:
                        self.persist()
                        self.toast("Partie sauvegardée.")
                elif choice == "copie":
                    if self.mp is not None:
                        self.toast("À plusieurs, c'est l'hôte qui garde la partie : pas de copie.")
                    else:
                        # Une copie a cote (Charger une partie) ; on continue
                        # de jouer dans la sauvegarde de cette partie.
                        self.persist()
                        copy = new_save_path()
                        save_game(self.state, copy, _view(self.camera_x, self.camera_y, self.zoom, self.selected, self.globe_yaw, self.globe_pitch))
                        self.toast(f"Copie enregistrée (an {self.state.clock.year}) : menu principal, Charger une partie.")
                elif choice == "reglages":
                    self.settings.show()
                elif choice == "principal":
                    self.leave()
                    return "menu", ""
                elif choice == "quitter":
                    self.leave()
                    return "quit", ""
        elif self.ui["event_open"] is not None:
            if event.type == pygame.MOUSEBUTTONDOWN and event.button == 1:
                lay = self.renderer.event_hits.get("modal") if isinstance(self.renderer.event_hits, dict) else None
                if lay is None:
                    self.close_event()
                    return None
                mx, my = event.pos
                cx, cy, cw, ch = lay["close"]
                if cx <= mx <= cx + cw and cy <= my <= cy + ch:
                    self.close_event()
                    return None
                for i, (ox, oy, ow, oh) in lay["options"].items():
                    if ox <= mx <= ox + ow and oy <= my <= oy + oh:
                        uid = self.ui["event_open"]

                        def chosen(res, uid=uid):
                            if events.find(self.state, uid) is None:
                                if self.ui["event_open"] == uid:
                                    self.close_event()
                            else:
                                self.ui["answered"].discard(uid)
                                self.say(res)

                        if self.mp is not None:
                            # La reponse part chez l'hote : la carte se ferme deja.
                            self.ui["answered"].add(uid)
                            self.close_event()
                        self.issue(commands.make(self.me(), "event", uid, i), chosen)
                        break
        elif self.ui["situation_open"] is not None:
            if event.type == pygame.MOUSEBUTTONDOWN and event.button == 1:
                hit = window_hit(self.renderer.situation_window, event.pos[0], event.pos[1])
                if hit != "box":
                    self.situation_click(hit)
        elif self.ui["found"] is not None:
            if event.type == pygame.MOUSEBUTTONDOWN and event.button == 1:
                self.found_click(found_hit(self.renderer.found_hits, event.pos[0], event.pos[1]))
        elif event.type == pygame.MOUSEWHEEL:
            tlay = self.renderer.side_hits.get("tech") if self.side_panel == "savoirs" else None
            wx_, wy_ = pygame.mouse.get_pos()
            if tlay and tlay.get("numbers") is None and _in_rect(tlay["view"], wx_, wy_):
                # La molette zoome l'arbre des savoirs, autour du curseur.
                factor = TREE_ZOOM_STEP if event.y > 0 else 1.0 / TREE_ZOOM_STEP
                self.ui["tech_cam"] = zoom_at(tlay["cam"], tlay["view"], tlay["world"], wx_, wy_, factor)
                return None
            plist = getattr(self.renderer, "people_list", None)
            if self.side_panel == "peuples" and plist and _in_rect(plist, wx_, wy_):
                # La molette fait defiler la liste des peuples.
                self.ui["people_scroll"] = max(0, int(self.ui.get("people_scroll", 0)) - (1 if event.y > 0 else -1))
                return None
            zmin = min_zoom_for(self.state.world, self.sw, self.sh)
            self.zoom = min(MAX_ZOOM, max(zmin, self.zoom * (1.1 if event.y > 0 else 0.9)))
        elif event.type == pygame.MOUSEBUTTONDOWN:
            return self._on_click(event)
        elif event.type == pygame.MOUSEBUTTONUP:
            if event.button == 1:
                self.slider_drag = None
                self.slider_sent = None
            if event.button == 3 and self.right_press is not None:
                press, self.right_press = self.right_press, None
                ax, ay = press["at"]
                moved = abs(event.pos[0] - ax) + abs(event.pos[1] - ay)
                target = self.state.bands.get(press["target"]) if press["target"] else None
                if target is not None and moved <= 6 and target.population > 0:
                    self.order_raid(target)
            if event.button == self.drag_button:
                self.dragging = False
            if event.button == self.tech_drag:
                if self.tech_drag == 1 and not self.tech_press["moved"] and self.tech_press["pick"]:
                    self.side_click(self.tech_press["pick"])
                self.tech_drag = 0
        elif event.type == pygame.MOUSEMOTION and self.slider_drag:
            if self.renderer.treasury_hits:
                self.set_slider(self.slider_drag, render_treasury.slider_value(self.renderer.treasury_hits, self.slider_drag, event.pos[0]))
            else:
                self.slider_drag = None
        elif event.type == pygame.MOUSEMOTION and self.tech_drag:
            tlay = self.renderer.side_hits.get("tech")
            if tlay and self.side_panel == "savoirs":
                mx, my = event.pos
                ax, ay = self.tech_press["at"]
                if self.tech_drag != 1 or self.tech_press["moved"] or abs(mx - ax) + abs(my - ay) > 4:
                    self.tech_press["moved"] = True
                    self.ui["tech_cam"] = pan(tlay["cam"], tlay["view"], tlay["world"], mx - self.last_mouse[0], my - self.last_mouse[1])
                    self.renderer.side_hits["tech"]["cam"] = self.ui["tech_cam"]
                    self.last_mouse = (mx, my)
            else:
                self.tech_drag = 0
        elif event.type == pygame.MOUSEMOTION and self.dragging:
            mx, my = event.pos
            _cx, _cy, _focal, dist = view_params(self.zoom, self.sw, self.sh, HUD_HEIGHT)
            sens = orbit_sensitivity(dist)
            self.globe_yaw += (mx - self.last_mouse[0]) * sens
            self.globe_pitch = clamp_pitch(self.globe_pitch + (my - self.last_mouse[1]) * sens)
            self.last_mouse = (mx, my)

    def _on_key(self, event):
        """Une touche (hors discussion) : Echap, panneaux, temps, modes de carte."""
        if event.key == pygame.K_ESCAPE:
            if self.ui["event_open"] is not None:
                self.close_event()
            elif self.ui["situation_open"] is not None:
                self.close_situation()
            elif self.ui["found"] is not None:
                self.close_found()
            elif screens.opened(self.ui) is not None:
                screens.close_all(self.ui)
            elif self.open_fight is not None:
                self.open_fight = None
            elif self.side_panel:
                self.side_panel = None
            elif self.pinned_hex is not None:
                self.pinned_hex = None
            else:
                self.menu_open = not self.menu_open
        elif self.menu_open or self.ui["event_open"] is not None or self.ui["found"] is not None or self.ui["situation_open"] is not None:
            pass
        elif self.side_panel == "savoirs" and event.key in (
            pygame.K_LEFT, pygame.K_RIGHT, pygame.K_UP, pygame.K_DOWN,
            pygame.K_PLUS, pygame.K_KP_PLUS, pygame.K_EQUALS, pygame.K_MINUS, pygame.K_KP_MINUS,
        ):
            # Fleches : se deplacer dans l'arbre ; + et - : zoomer.
            tlay = self.renderer.side_hits.get("tech")
            if tlay:
                view = tlay["view"]
                step = {pygame.K_LEFT: (120, 0), pygame.K_RIGHT: (-120, 0), pygame.K_UP: (0, 90), pygame.K_DOWN: (0, -90)}.get(event.key)
                if step is not None:
                    self.ui["tech_cam"] = pan(tlay["cam"], view, tlay["world"], *step)
                else:
                    zin = event.key in (pygame.K_PLUS, pygame.K_KP_PLUS, pygame.K_EQUALS)
                    self.ui["tech_cam"] = zoom_at(tlay["cam"], view, tlay["world"], view[0] + view[2] / 2, view[1] + view[3] / 2, TREE_ZOOM_STEP if zin else 1.0 / TREE_ZOOM_STEP)
        elif event.key == pygame.K_SPACE:
            self.toggle_pause()
        elif event.key == pygame.K_F5:
            if self.mp is not None and self.mp.role != "host":
                self.toast("C'est l'hôte qui sauvegarde la partie.")
            else:
                self.persist()
                self.toast("Partie sauvegardée.")
        elif event.key in ACTION_KEYS:
            self.band_action(ACTION_KEYS[event.key])
        elif event.key in PANEL_KEYS:
            key = PANEL_KEYS[event.key]
            if key == "armee" and not army_ready(self.state):
                self.toast("L'armée vient avec le premier village.")
                return None
            self.side_panel = None if self.side_panel == key else key
            screens.close_all(self.ui)
        elif event.key == pygame.K_m:
            if not commerce_ready(self.state):
                self.toast("Le commerce vient avec le premier village.")
                return None
            self.open_screen("commerce", toggle=True)
        elif event.key == pygame.K_g:
            if not money.has_money(self.state, self.state.viewer):
                self.toast("Le trésor vient avec Valeurs d'échange.")
                return None
            self.open_screen("tresor", toggle=True)
        elif event.key == pygame.K_z:
            self.renderer.map_mode = "relief" if self.renderer.map_mode == "zones" else "zones"
        elif event.key == pygame.K_w:
            if not wars_ready(self.state):
                self.toast("Les guerres se déclarent avec Dons et palabres (la diplomatie).")
                return None
            self.open_screen("guerres", toggle=True)
        elif event.key == pygame.K_n:
            if not laws.available(self.state, self.state.viewer):
                self.toast("Les lois viennent avec Valeurs d'échange ou Nombres additifs.")
                return None
            self.open_screen("pays", toggle=True)
        elif event.key == pygame.K_i:
            self.renderer.map_mode = "relief" if self.renderer.map_mode == "tournants" else "tournants"
        elif event.key == pygame.K_u:
            self.renderer.map_mode = "relief" if self.renderer.map_mode == "suzerains" else "suzerains"
        elif event.key == pygame.K_r:
            self.renderer.map_mode = "relief" if self.renderer.map_mode == "ressources" else "ressources"
        elif event.key == pygame.K_x:
            self.renderer.map_mode = "relief" if self.renderer.map_mode == "commerce" else "commerce"
        elif event.key == pygame.K_e:
            waiting = [p for p in events.pending(self.state, self.state.viewer) if p.uid not in self.ui["answered"]]
            if waiting:
                self.open_event(waiting[0].uid)
        elif event.key in (
            pygame.K_1,
            pygame.K_2,
            pygame.K_3,
            pygame.K_4,
            pygame.K_5,
        ):
            self.set_speed(event.key - pygame.K_0)

    def _on_click(self, event):
        """Un bouton de souris : glisser la carte (droit), viser un ecran, une bande, une case (gauche)."""
        self.selected = _refresh_selection(self.state, self.selected)
        tlay = self.renderer.side_hits.get("tech") if self.side_panel == "savoirs" else None
        if event.button in (2, 3) and tlay and _in_rect(tlay["view"], *event.pos):
            self.tech_drag = event.button
            self.last_mouse = event.pos
            return None
        if event.button in (2, 3):
            mx, my = event.pos
            if side_hit(self.renderer.side_hits, mx, my) is None and not screens.under_mouse(self.renderer, self.ui, mx, my):
                self.dragging = True
                self.drag_button = event.button
                self.last_mouse = event.pos
                if event.button == 3:
                    self.right_press = {"at": event.pos, "target": self._foe_under(mx, my)}
        elif event.button == 1:
            mx, my = event.pos
            ui_hit = hud_hit(self.renderer.hud_hits, mx, my)
            if ui_hit == "pause":
                self.toggle_pause()
                return None
            if isinstance(ui_hit, tuple) and ui_hit[0] == "speed":
                self.set_speed(ui_hit[1])
                return None
            # Les medaillons des crises et conjonctures sont DANS la barre du
            # haut : leur clic passe avant celui de la barre.
            sit_uid = banner_hit(self.renderer.situation_hits, mx, my)
            if sit_uid is not None:
                self.open_situation(sit_uid)
                return None
            if ui_hit == "bar":
                return None
            scr, schoice = screens.hit(self.renderer, self.ui, mx, my)
            if scr is not None:
                # Le grand ecran ouvert (screens.py) prend le clic ;
                # un clic hors de lui (et des onglets) le ferme.
                if schoice is not None:
                    if schoice != "panel":
                        self.screen_clicks[scr.name](schoice)
                    return None
                if side_hit(self.renderer.side_hits, mx, my) is None:
                    screens.close_all(self.ui)
                    return None
            choice = side_hit(self.renderer.side_hits, mx, my)
            if self.side_panel == "savoirs" and isinstance(choice, str) and (choice.startswith("tech:") or choice == "tview"):
                self.tech_drag = 1
                self.last_mouse = (mx, my)
                self.tech_press.update({"at": (mx, my), "moved": False, "pick": choice if choice.startswith("tech:") else None})
                return None
            if choice is not None:
                self.side_click(choice)
                return None
            # La carte des grands tournants : une ligne de sa legende le choisit.
            pick = next((tid for tid, rect in self.renderer.turning_hits.items() if _in_rect(rect, mx, my)), None)
            if pick is not None:
                self.renderer.turning_pick = pick
                return None
            mode = map_mode_hit(self.renderer.mode_hits, mx, my)
            if mode == "menu":
                self.renderer.mode_menu_open = not self.renderer.mode_menu_open
                return None
            if mode is not None:
                self.renderer.map_mode = mode
                self.renderer.mode_menu_open = False
                return None
            if self.renderer.mode_menu_open:
                # Un clic ailleurs referme la liste des modes.
                self.renderer.mode_menu_open = False
                return None
            card_uid = next(
                (uid for uid, rect in self.renderer.event_hits.items() if isinstance(uid, int)
                 and rect[0] <= mx <= rect[0] + rect[2] and rect[1] <= my <= rect[1] + rect[3]),
                None,
            ) if isinstance(self.renderer.event_hits, dict) else None
            if card_uid is not None:
                self.open_event(card_uid)
                return None
            bhit = render_battle.hit(self.renderer.battle_hits, mx, my)
            if bhit is not None:
                bt = next((x for x in _battle.battles(self.state) if x.uid == self.renderer.battle_hits.get("uid")), None)
                if bt is not None and bhit == "retreat":
                    mine_band = next((b for b in bt.attackers + bt.defenders if b in self.state.bands and self.state.bands[b].tribe_id == self.me()), None)
                    if mine_band is not None:
                        self.issue(commands.make(self.me(), "battle_retreat", mine_band))
                elif bt is not None and bhit == "see":
                    self.show_place(bt.hex)
                return None
            if self.open_fight is None:
                hit_toast = toast_hit(self.renderer.toast_hits, mx, my)
                if hit_toast is not None:
                    self.show_place(hit_toast.get("hex"))
                    return None
            card = band_card_hit(self.renderer.band_hits, mx, my)
            if card in orders.ACTIONS:
                self.band_action(card)
                return None
            if card == "card":
                return None
            if self.open_fight is not None:
                fhit = fight_panel_hit(self.renderer.fight_hits, mx, my)
                if fhit == "close" or fhit == "panel":
                    if fhit == "close":
                        self.open_fight = None
                    return None
            sword = _fight_at_pixel(self.state, mx, my, self.zoom, self.globe_yaw, self.globe_pitch, self.sw, self.sh)
            if sword is not None:
                self.open_fight = sword
                return None
            if self.open_fight is not None:
                self.open_fight = None
                return None
            hit = _band_at_pixel(self.state, mx, my, self.zoom, self.globe_yaw, self.globe_pitch, self.sw, self.sh)
            shift = pygame.key.get_mods() & pygame.KMOD_SHIFT
            if hit is not None and hit.tribe_id == self.state.viewer and hit.village and not shift:
                # Un clic sur un de vos villages ouvre son ecran.
                self.selected = hit.id
                self.open_village(hit.village)
                return None
            if hit is not None and hit.tribe_id == self.state.viewer:
                if shift and self.selected not in (None, hit.id):
                    # Rejoindre : les deux bandes se reunissent.
                    band = self.state.bands.get(self.selected)
                    if band is not None and chiefs.obeys(self.state, band):
                        self.issue(commands.make(self.me(), "march", self.selected, hit.id))
                    else:
                        self.toast(orders.INDOCILE + ".")
                elif self.selected == hit.id:
                    self.selected = None
                else:
                    self.selected = hit.id
            elif hit is not None:
                # Un clic gauche sur un autre peuple : sa diplomatie (on
                # l'attaque au clic droit).
                self.open_diplomacy(hit.tribe_id)
            elif (
                seen := _seen_village_at_pixel(self.state, mx, my, self.zoom, self.globe_yaw, self.globe_pitch, self.sw, self.sh)
            ) and seen in diplo.contacts_of(self.state, self.state.viewer):
                # Une ville connue, meme dans le brouillard : sa diplomatie.
                self.open_diplomacy(seen)
            else:
                gcx, gcy, focal, dist = view_params(self.zoom, self.sw, self.sh, HUD_HEIGHT)
                hx = pixel_to_hex_globe(
                    mx, my, self.state.world, self.globe_yaw, self.globe_pitch, gcx, gcy, focal, dist
                )
                if hx is not None:
                    if self.selected is not None:
                        self.order_move(hx)
                    else:
                        other = self._country_at(hx)
                        if other:
                            self.open_diplomacy(other)
                            return None
                    info = hex_inspect(self.state, hx)
                    if info is None:
                        self.pinned_hex = None
                    elif self.pinned_hex == info["hex"]:
                        self.pinned_hex = None
                    else:
                        self.pinned_hex = info["hex"]

    def _frame(self, dt: float):
        """Une image : le temps (solo) ou l'hote (multijoueur), les nouvelles,
        ce que survole la souris, le dessin ; rend ("menu", message) pour
        quitter la partie, sinon None."""
        if self.mp is not None:
            # Le temps est a l'hote : il annonce les semaines, chacun les calcule.
            self.mp.pump(dt)
            if self.mp.state is not self.state:
                # Partie recopiee depuis l'hote (un ecart, un retour).
                self.state = self.mp.state
                self.last_log_seq = log_of(self.state, self.state.viewer).seq
                self.renderer._layer_key = None
                if self.selected not in self.state.bands:
                    self.selected = None
            for then, res in self.mp.take_results():
                (then or self.say)(res)
            for text in self.mp.take_notes():
                self.toast(text)
            self.ui["answered"] = {u for u in self.ui["answered"] if events.find(self.state, u) is not None}
            if self.mp.ended:
                self.leave()
                return "menu", self.mp.ended
            if self.mp.role == "host" and self.state.tick_count > 0 and self.state.tick_count % 8 == 0 and self.state.tick_count != self.last_auto:
                self.persist()
                self.last_auto = self.state.tick_count
        elif not self.menu_open and not self.state.clock.paused and not human_dead(self.state, self.state.viewer):
            # Un combat ne deplace plus la camera et n'arrete plus le temps :
            # toast + journal + epee ; un clic sur le toast ou la ligne y mene.
            self.acc = consume_ticks(self.state, self.acc, dt)
            self.selected = _refresh_selection(self.state, self.selected)
            if (
                self.state.tick_count > 0
                and self.state.tick_count % 8 == 0
                and self.state.tick_count != self.last_auto
            ):
                self.persist()
                self.last_auto = self.state.tick_count
        else:
            self.acc = 0.0
        if self.ui["event_open"] is not None and events.find(self.state, self.ui["event_open"]) is None:
            self.close_event()
        self.selected = _refresh_selection(self.state, self.selected)
        for t in self.toasts:
            t["age"] += dt
        self.toasts = [t for t in self.toasts if t["age"] < TOAST_LIFE]
        if log_of(self.state, self.state.viewer).seq > self.last_log_seq:
            fresh = [e for e in log_of(self.state, self.state.viewer).entries if e.seq > self.last_log_seq]
            for entry in fresh:
                self.toasts.append(
                    {
                        "text": entry.text,
                        "age": 0.0,
                        "seq": entry.seq,
                        "hex": entry.hex,
                        "combat": entry.kind is LogKind.COMBAT,
                        "kind": entry.kind.value,
                    }
                )
            self.last_log_seq = log_of(self.state, self.state.viewer).seq
            self.toasts = self.toasts[-MAX_TOASTS:]
        mx, my = pygame.mouse.get_pos()
        hover_info = None
        pin_info = hex_inspect(self.state, self.pinned_hex) if self.pinned_hex is not None else None
        if self.ui["village_open"] is not None:
            vsite = self.state.sites.get(self.ui["village_open"])
            if vsite is None or vsite.kind != "village":
                self.ui["village_open"] = None
        blocked = (
            self.menu_open
            or self.ui["event_open"] is not None
            or self.ui["found"] is not None
            or self.ui["situation_open"] is not None
            or screens.under_mouse(self.renderer, self.ui, mx, my)
            or my < HUD_HEIGHT
            or band_card_hit(self.renderer.band_hits, mx, my) is not None
        )
        if not blocked and side_hit(self.renderer.side_hits, mx, my) is None:
            gcx, gcy, focal, dist = view_params(self.zoom, self.sw, self.sh, HUD_HEIGHT)
            hx = pixel_to_hex_globe(
                mx, my, self.state.world, self.globe_yaw, self.globe_pitch, gcx, gcy, focal, dist
            )
            if hx is not None:
                hover_info = hex_inspect(self.state, hx)
        # Une de vos bandes choisie, la souris sur un etranger : ce que
        # donnerait l'attaque (orders.attack_preview), a la place de la case.
        self.ui["attack_preview"] = None
        foe = self._foe_under(mx, my) if not blocked and side_hit(self.renderer.side_hits, mx, my) is None else None
        if foe is not None:
            self.ui["attack_preview"] = self._attack_preview(foe)
            if self.ui["attack_preview"] is not None:
                hover_info = None
        if self.ui["situation_open"] is not None and situations.find(self.state, self.ui["situation_open"]) is None:
            self.close_situation()
        self.renderer.draw(
            self.state,
            self.camera_x,
            self.camera_y,
            self.zoom,
            self.selected,
            self.menu_open,
            self.globe_yaw,
            self.globe_pitch,
            self.side_panel,
            self.log_filter,
            self.log_newest,
            self.toasts,
            hover_info,
            pin_info,
            self.tech_pick,
            self.open_fight,
            self.ui,
        )
        if self.mp is not None:
            render_menu.draw_mp_overlay(self.renderer, self.mp, self.state, self.chat_text)
        self.settings.draw(self.renderer)
        pygame.display.flip()


def play(renderer, clock, boot, mp=None, save_path=None, director=None) -> tuple[str, str]:
    """Une partie, jusqu'au retour au menu ("menu", message) ou au depart
    ("quit", ""). mp : la session multijoueur (session.py), sinon solo ;
    save_path : sa sauvegarde (par defaut kora.json) ; director : la musique."""
    return Play(renderer, clock, boot, mp, save_path, director).run()
