"""LA PARTIE A L'ECRAN, COTE CARTE : la souris sur la planete, le clavier,
les ordres aux bandes (MapInput, une des bases de partie.Play).

Un clic gauche choisit une de vos bandes, ou la fait marcher (order_move),
ou ouvre la diplomatie d'un etranger (et de son suzerain : _country_at) ;
un clic droit sur un etranger l'ATTAQUE avec la bande choisie (order_raid ;
deux clics si l'on est en paix : CONFIRM_SECONDS) ; au survol, le rapport
de force (_attack_preview). Le clavier : _on_key (PANEL_KEYS ouvrent les
onglets, ACTION_KEYS donnent les ordres d'une bande : band_action).
Les outils de selection, purs et partages : band_at_pixel,
seen_village_at_pixel, fight_at_pixel, look_hex (la camera), player_band_ids,
first_player_band, refresh_selection, next_player_band, nearest_band_of,
in_rect. Tout ordre au jeu passe par Play.issue (commands.py).
"""

from __future__ import annotations

import pygame

from src.kora import (
    battle as _battle,
    chiefs,
    commands,
    diplo,
    events,
    guerre,
    influence,
    laws,
    memory,
    money,
    orders,
    render_battle,
    render_tutoriel,
    render_wars,
    screens,
    sites,
    tutoriel,
)
from src.kora.globe import hex_to_globe_screen, look_at_hex, pixel_to_hex_globe, view_params
from src.kora.layout import (
    band_card_hit,
    band_screen_positions,
    fight_mark_screen_pos,
    fight_panel_hit,
    HUD_HEIGHT,
    hud_hit,
    map_mode_hit,
    pan,
    side_hit,
    toast_hit,
    TREE_ZOOM_STEP,
    zoom_at,
)
from src.kora.render_panels import army_ready, commerce_ready, wars_ready
from src.kora.render_situations import banner_hit
from src.kora.sim import hex_inspect
from src.kora.types import Hex
from src.kora.vision import is_explored, is_visible, vision_of


# Deux clics sur la meme bande d'un peuple ami en moins de ce temps : on
# confirme le raid (et la trahison du pacte).
CONFIRM_SECONDS = 3.0
PANEL_KEYS = {
    pygame.K_t: "savoirs",
    pygame.K_b: "tribu",
    pygame.K_p: "peuples",
    pygame.K_j: "journal",
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


def look_hex(state, h):
    return look_at_hex(h, state.world.width, state.world.height)


def band_at_pixel(state, x, y, zoom, globe_yaw, globe_pitch, sw, sh):
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


def seen_village_at_pixel(state, x, y, zoom, globe_yaw, globe_pitch, sw, sh):
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


def fight_at_pixel(state, x, y, zoom, globe_yaw, globe_pitch, sw, sh):
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


def player_band_ids(state) -> list[int]:
    return sorted(b.id for b in state.bands.values() if b.tribe_id == state.viewer)


def first_player_band(state):
    ids = player_band_ids(state)
    return ids[0] if ids else None


def refresh_selection(state, selected):
    # None = rien de selectionne, voulu par le joueur : un clic sur la carte
    # montre alors la case sans deplacer personne. Une bande disparue
    # (reunie, detruite, partie) passe la selection a une autre bande.
    if selected is None or (selected in state.bands and state.bands[selected].tribe_id == state.viewer):
        return selected
    return first_player_band(state)


def next_player_band(state, selected):
    # Les villages se gerent dans leur ecran : Tab passe d'une bande a l'autre.
    ids = [i for i in player_band_ids(state) if not state.bands[i].village] or player_band_ids(state)
    if not ids:
        return None
    if selected not in ids:
        return ids[0]
    return ids[(ids.index(selected) + 1) % len(ids)]


def nearest_band_of(state, tid: int, near):
    bands = [b for b in state.bands.values() if b.tribe_id == tid and b.population > 0]
    if not bands:
        return None
    if near is None:
        return min(bands, key=lambda b: b.id)
    return min(bands, key=lambda b: (state.world.distance(b.position, near), b.id))


def in_rect(rect, mx, my) -> bool:
    x, y, w, h = rect
    return x <= mx <= x + w and y <= my <= y + h


class MapInput:
    def band_action(self, action: str, band_id=None) -> None:
        target = self.selected if band_id is None else band_id
        if action == "next":
            self.selected = next_player_band(self.state, self.selected)
            if self.selected is not None:
                self.globe_yaw, self.globe_pitch = look_hex(self.state, self.state.bands[self.selected].position)
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
        hit = band_at_pixel(self.state, mx, my, self.zoom, self.globe_yaw, self.globe_pitch, self.sw, self.sh)
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
        if target.tribe_id != self.state.viewer and guerre.at_peace(self.state, self.state.viewer, target.tribe_id):
            name = self.state.tribes[target.tribe_id].name
            if self.confirm["band"] != target.id or self.now > self.confirm["until"]:
                self.confirm["band"] = target.id
                self.confirm["until"] = self.now + CONFIRM_SECONDS
                self.toast(f"Pacte avec les {name} : clic droit encore pour attaquer (trahison, prestige -10).", True)
                return
            self.confirm["band"] = None
        self.issue(commands.make(self.me(), "march", self.selected, target.id))

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
        elif event.key == pygame.K_F1:
            # le tutoriel : l'ouvrir (la ou on l'avait laisse) ou le fermer
            tutoriel.guide_toggle(self)
        elif event.key == pygame.K_F3:
            # la fiche du moteur : l'image, la semaine, la vitesse tenue
            self.show_engine = not self.show_engine
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
        elif event.key == pygame.K_a:
            if not army_ready(self.state) and not wars_ready(self.state):
                self.toast("L'armée vient avec le premier village.")
                return None
            self.open_war_room(render_wars.ARMY)
        elif event.key == pygame.K_w:
            if not wars_ready(self.state) and not army_ready(self.state):
                self.toast("Les guerres se déclarent avec Messagers et serments (la diplomatie vient avec les villages).")
                return None
            self.open_war_room(None)
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
        self.selected = refresh_selection(self.state, self.selected)
        tlay = self.renderer.side_hits.get("tech") if self.side_panel == "savoirs" else None
        if event.button in (2, 3) and tlay and in_rect(tlay["view"], *event.pos):
            self.tech_drag = event.button
            self.last_mouse = event.pos
            return None
        if event.button in (2, 3):
            mx, my = event.pos
            on_card = render_tutoriel.tuto_hit(self.renderer.tuto_hits, mx, my) is not None
            if side_hit(self.renderer.side_hits, mx, my) is None and not screens.under_mouse(self.renderer, self.ui, mx, my) and not on_card:
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
            # Le tutoriel : sa fiche (par-dessus les ecrans), son bouton Tuto.
            th = render_tutoriel.tuto_hit(self.renderer.tuto_hits, mx, my) if tutoriel.is_open(self.ui) else None
            if th is not None:
                self.tuto_click(th)
                return None
            if self.renderer.tuto_button is not None and in_rect(self.renderer.tuto_button, mx, my):
                tutoriel.guide_toggle(self)
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
            pick = next((tid for tid, rect in self.renderer.turning_hits.items() if in_rect(rect, mx, my)), None)
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
            sword = fight_at_pixel(self.state, mx, my, self.zoom, self.globe_yaw, self.globe_pitch, self.sw, self.sh)
            if sword is not None:
                self.open_fight = sword
                return None
            if self.open_fight is not None:
                self.open_fight = None
                return None
            hit = band_at_pixel(self.state, mx, my, self.zoom, self.globe_yaw, self.globe_pitch, self.sw, self.sh)
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
                seen := seen_village_at_pixel(self.state, mx, my, self.zoom, self.globe_yaw, self.globe_pitch, self.sw, self.sh)
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
