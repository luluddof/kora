"""LA PARTIE A L'ECRAN : la classe Play (une partie qu'on joue, seul ou a
plusieurs) et la fenetre des reglages.

Play garde l'etat de l'ecran (camera, selection, panneaux, fenetres,
nouvelles) et a une methode par chose a faire. Ses methodes vivent en trois
endroits, selon ce qu'elles touchent :
  partie.py         le coeur : Play.issue (TOUT ordre au jeu passe par la :
                    commands.py ; en reseau il part a l'hote), persist (la
                    sauvegarde : Play.save_path, toutes les 8 semaines ; en
                    reseau, l'hote seul), toast, show_place, la boucle
                    (Play.run, 60 images par seconde), _on_event (un
                    evenement), _frame (une image : le temps ou l'hote, les
                    nouvelles, le survol, le dessin) ;
  partie_carte.py   la carte, la souris, le clavier (MapInput) ;
  partie_ecrans.py  les grands ecrans et les panneaux (ScreenClicks).
Une touche ou un clic nouveau = une methode de Play, dans celui des trois
qui lui ressemble. Settings : les reglages (volume de la musique), communs
au menu de demarrage et a la partie (reglages.json).
"""

from __future__ import annotations

import pygame

from src.kora import (
    commands,
    events,
    music,
    partie_carte,
    partie_ecrans,
    render_menu,
    render_treasury,
    screens,
    situations,
)
from src.kora.gamestate import human_dead, log_of
from src.kora.globe import clamp_pitch, orbit_sensitivity, pixel_to_hex_globe, view_params
from src.kora.layout import (
    band_card_hit,
    HUD_HEIGHT,
    max_zoom_for,
    menu_hit,
    min_zoom_for,
    pan,
    side_hit,
    TREE_ZOOM_STEP,
    zoom_at,
)
from src.kora.log import FILTER_ALL, LogKind
from src.kora.persist import (
    default_save_path,
    load_prefs,
    multi_save_path,
    new_save_path,
    save_game,
    save_prefs,
)
from src.kora.render_situations import window_hit
from src.kora.render_village import found_hit
from src.kora.sim import consume_ticks, fight_at, hex_inspect


TOAST_LIFE = 4.0
MAX_TOASTS = 4


def view_dict(camera_x, camera_y, zoom, selected, globe_yaw=0.0, globe_pitch=0.0):
    return {
        "camera_x": camera_x,
        "camera_y": camera_y,
        "zoom": zoom,
        "selected": selected,
        "globe_yaw": globe_yaw,
        "globe_pitch": globe_pitch,
    }


def fresh_ui() -> dict:
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


class Play(partie_carte.MapInput, partie_ecrans.ScreenClicks):
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
        self.ui: dict = fresh_ui()
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
            view_dict(self.camera_x, self.camera_y, self.zoom, self.selected, self.globe_yaw, self.globe_pitch),
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
        self.globe_yaw, self.globe_pitch = partie_carte.look_hex(self.state, where)
        mark = fight_at(self.state, where)
        if mark is not None:
            self.open_fight = mark
        else:
            self.pinned_hex = where if hex_inspect(self.state, where) is not None else None

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
                        save_game(self.state, copy, view_dict(self.camera_x, self.camera_y, self.zoom, self.selected, self.globe_yaw, self.globe_pitch))
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
            if tlay and tlay.get("numbers") is None and partie_carte.in_rect(tlay["view"], wx_, wy_):
                # La molette zoome l'arbre des savoirs, autour du curseur.
                factor = TREE_ZOOM_STEP if event.y > 0 else 1.0 / TREE_ZOOM_STEP
                self.ui["tech_cam"] = zoom_at(tlay["cam"], tlay["view"], tlay["world"], wx_, wy_, factor)
                return None
            plist = getattr(self.renderer, "people_list", None)
            if self.side_panel == "peuples" and plist and partie_carte.in_rect(plist, wx_, wy_):
                # La molette fait defiler la liste des peuples.
                self.ui["people_scroll"] = max(0, int(self.ui.get("people_scroll", 0)) - (1 if event.y > 0 else -1))
                return None
            zmin = min_zoom_for(self.state.world, self.sw, self.sh)
            self.zoom = min(max_zoom_for(self.state.world), max(zmin, self.zoom * (1.1 if event.y > 0 else 0.9)))
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
            self.selected = partie_carte.refresh_selection(self.state, self.selected)
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
        self.selected = partie_carte.refresh_selection(self.state, self.selected)
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
