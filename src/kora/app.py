"""L'APPLICATION : la fenetre, le menu de demarrage, le salon du
multijoueur, puis la partie a l'ecran (la classe Play).

run : le menu (title_screen : Continuer, Nouvelle partie, Charger,
Multijoueur, Reglages) -> _multiplayer (le salon) -> Play -> le menu. Play
garde l'etat de l'ecran (camera, selection, panneaux, fenetres, nouvelles)
et a une methode par chose a faire : Play.issue (TOUT ordre au jeu passe
par la : commands.py), Play.band_action, open_village, village_click,
trade_click, treasury_click, wars_click, side_click... ; Play.run la boucle
(60 images par seconde), _on_event, _on_key (le clavier), _on_click (la
souris), _frame (le temps ou l'hote, les nouvelles, le survol, le dessin).
Sauvegarde automatique toutes les 8 semaines (Play.save_path : la partie a
SA sauvegarde ; en reseau, l'hote seul). En reseau : mp.pump (le temps de
l'hote), les ordres, la partie recopiee si elle s'ecarte. gc.freeze apres
chargement (_settle_memory) : plus de saccade du ramasse-miettes.
"""

from __future__ import annotations

import random

import pygame

from src.kora import music, net, partie, partie_carte, planets, render_menu, session, tech
from src.kora.globe import look_at_hex
from src.kora.layout import focus_zoom_for, max_zoom_for, min_zoom_for
from src.kora.persist import (
    latest_save,
    list_saves,
    load_game,
    load_prefs,
    multi_save_path,
    new_save_path,
    peek_save,
    save_prefs,
    trash_save,
)
from src.kora.render import Renderer
from src.kora.sim import _default_world, new_game, player_home_hex


def _look_band(state, selected):
    if selected is not None and selected in state.bands:
        return partie_carte.look_hex(state, state.bands[selected].position)
    home = player_home_hex(state)
    if home is None:
        return 0.0, 0.0
    return partie_carte.look_hex(state, home)


def _tribe_start_view(state, selected):
    return (*_look_band(state, selected), focus_zoom_for(state.world))


class _Worlds:
    """Les planetes (planets.py) : celle du menu, lue au lancement. Une
    partie modifie la sienne (epuisement, influence) : la suivante en relit
    une propre. fresh(pid) : une planete donnee (une partie neuve, une
    sauvegarde ; None : celle par defaut)."""

    def __init__(self) -> None:
        self.shown = _default_world()
        self._fresh = self.shown
        self._previews: dict = {}

    def fresh(self, pid: str | None = None):
        if pid is None or pid == getattr(self._fresh, "planet", None):
            world = self._fresh if self._fresh is not None else _default_world(pid)
            self._fresh = None
            return world
        return _default_world(pid)

    def preview(self, pid: str):
        """La planete montree au menu (sans la toucher ; gardee en memoire)."""
        if pid in (None, planets.RANDOM):
            return self.shown
        if pid == getattr(self.shown, "planet", None):
            return self.shown
        if pid not in self._previews:
            self._previews[pid] = _default_world(pid)
        return self._previews[pid]


def _start_view(state, selected, sw: int, sh: int):
    yaw, pitch, zoom = _tribe_start_view(state, selected)
    zmin = min_zoom_for(state.world, sw, sh)
    zoom = min(max_zoom_for(state.world), max(zmin, zoom))
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
    return _start_view(state, partie_carte.refresh_selection(state, view.get("selected")), sw, sh)


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
    # La planete choisie au menu, ou une au hasard (planets.py).
    pid = planets.choose(setup.get("planet"), random.Random(setup["seed"]))
    state = new_game(worlds.fresh(pid), setup=setup)
    return _start_view(state, partie_carte.first_player_band(state), sw, sh)


def _settle_memory() -> None:
    """Le monde fait ~3 millions d'objets Python : un passage complet du
    ramasse-miettes coutait jusqu'a 0,5 s (une saccade). On les met a part
    une fois charges (gc.freeze) ; rien ne change au jeu."""
    import gc

    gc.unfreeze()
    gc.collect()
    gc.freeze()


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
            boot = _start_view(state, partie_carte.first_player_band(state), sw, sh)
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
        outcome, message = play(renderer, clock, boot, mp, save_path, director, tuto=choice[0] == "tuto")
        if outcome == "quit":
            break
    pygame.quit()


def _remember(setup: dict) -> None:
    """Le nom, la couleur, les bonus et la derniere adresse : proposes la
    prochaine fois (reglages.json, a cote des sauvegardes)."""
    prefs = load_prefs()
    for key in ("name", "color", "bonuses", "address", "planet"):
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
    if prefs.get("planet") in planets.ids() + [planets.RANDOM, planets.LEGACY]:
        setup["planet"] = prefs["planet"]
    return setup


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
    settings = partie.Settings(director)
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
                        if hit in ("planet_prev", "planet_next"):
                            # Le globe du menu montre la planete choisie.
                            scene.world = worlds.preview(setup.get("planet"))
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
                        scene.world = worlds.preview(setup.get("planet"))
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
                if hit == "tutoriel":
                    return ("tuto", render_menu.tuto_setup(rng))
                if hit == "nouvelle":
                    setup = _prefilled(render_menu.new_setup(rng))
                    scene.world = worlds.preview(setup.get("planet"))
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
            saved, view_dict = loaded
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
                        pid = planets.choose(mp.setup.get("planet"), random.SystemRandom())
                        world = mp.resume.world if mp.resume is not None else worlds.fresh(pid)
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


def play(renderer, clock, boot, mp=None, save_path=None, director=None, tuto: bool = False) -> tuple[str, str]:
    """Une partie, jusqu'au retour au menu ("menu", message) ou au depart
    ("quit", ""). mp : la session multijoueur (session.py), sinon solo ;
    save_path : sa sauvegarde (par defaut kora.json) ; director : la musique."""
    return partie.Play(renderer, clock, boot, mp, save_path, director, tuto=tuto).run()
