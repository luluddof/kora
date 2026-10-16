"""LA PARTIE A L'ECRAN, COTE ECRANS : les grands ecrans, les fenetres et
les panneaux lateraux (ScreenClicks, une des bases de partie.Play).

Un grand ecran (screens.SCREENS : le village, le commerce, le tresor, le
pays, l'armee et les guerres) a ici sa methode de clic (village_click,
trade_click, treasury_click, country_click, wars_click et army_click) ; ses
mises en page et ses dessins sont dans render_<x>.py. Aussi : la fenetre de
fondation (open_found, found_click), les cartes d'evenements (open_event),
les situations (open_situation, situation_click), la diplomatie d'un peuple
(open_diplomacy), les onglets lateraux (side_click : savoirs, tribu,
peuples, journal). Tout ordre au jeu passe par Play.issue (commands.py) ;
ouvrir et fermer, par screens.py.
"""

from __future__ import annotations

import pygame

from src.kora import (
    batiments,
    chiefdom,
    chiefs,
    commands,
    diplo,
    events,
    goods,
    grain,
    money,
    orders,
    partie_carte,
    places,
    render_tech,
    render_treasury,
    render_wars,
    screens,
    situations,
    troupes,
    tutoriel,
    villages,
    wars,
)
from src.kora.gamestate import log_of
from src.kora.layout import FILTER_BY_HIT, TREE_ZOOM_STEP, zoom_at
from src.kora.sim import player_home_hex
from src.kora.situations import SPECS
from src.kora.types import Hex


class ScreenClicks:
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

    def open_war_room(self, pick) -> None:
        """L'ecran de l'armee et des guerres : A (pick = l'armee) ou W (pick
        None : la premiere guerre, sinon l'armee). La meme touche le ferme."""
        if pick is None:
            fronts = [f.key for f in wars.fronts(self.state, self.state.viewer)]
            pick = self.ui.get("war_pick") if self.ui.get("war_pick") in fronts else (fronts[0] if fronts else render_wars.ARMY)
        if self.ui.get("wars_open") and (self.ui.get("war_pick") == pick or (pick != render_wars.ARMY and self.ui.get("war_pick") != render_wars.ARMY)):
            screens.close_all(self.ui)
            return
        self.ui["war_pick"] = pick
        self.open_screen("guerres")

    def wars_click(self, choice) -> None:
        """Clic dans l'ecran de l'armee et des guerres : l'armee (lever,
        voir, dissoudre : army_click) ; choisir une guerre, voir une troupe,
        un village ou un combat ; exiger la soumission, proposer la treve
        (commands.py, "diplo") ; leur fiche (Peuples)."""
        if choice == "wclose":
            screens.close_all(self.ui)
            return
        if choice == "wlevy":
            self.ui["war_pick"] = render_wars.ARMY
            return
        if choice.startswith(("asize:", "araise:", "avillage:", "asee:", "adissolve:")):
            if choice.startswith("asee:"):
                screens.close_all(self.ui)
            self.army_click(choice)
            return
        kind, _sep, rest = choice.partition(":")
        if kind == "wpick":
            self.ui["war_pick"] = rest if rest == render_wars.ARMY else int(rest)
        elif kind == "wsee":
            band = self.state.bands.get(int(rest))
            if band is not None:
                screens.close_all(self.ui)
                if band.tribe_id == self.state.viewer:
                    self.selected = band.id
                self.globe_yaw, self.globe_pitch = partie_carte.look_hex(self.state, band.position)
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
                (b for b in batiments.BUILD_ORDER if batiments.building_status(self.state, site, b) == "possible"), None
            )
            if pick is None:
                return
            why = batiments.build_block(self.state, home.id, pick) or ("" if chiefs.obeys(self.state, home) else orders.INDOCILE)
            if why:
                self.toast(why)
            else:
                self.issue(commands.make(self.me(), "build", home.id, pick))
            return
        if choice.startswith("levy:"):
            self.ui["levy"] = choice[5:]
            return
        if choice == "vraise":
            share = troupes.LEVY_SHARE.get(self.ui["levy"], troupes.LEVY_SHARE["troupe"])
            why = troupes.army_block(self.state, home.id, share) or ("" if chiefs.obeys(self.state, home) else orders.INDOCILE)
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
                self.globe_yaw, self.globe_pitch = partie_carte.look_hex(self.state, army.position)
            elif choice.startswith("vreequip:"):
                why = troupes.reequip_block(self.state, bid)
                if why:
                    self.toast(why)
                else:
                    self.issue(commands.make(self.me(), "reequip", bid))
            else:
                why = troupes.dissolve_block(self.state, bid)
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
            share = troupes.LEVY_SHARE.get(key, troupes.LEVY_SHARE["troupe"])
            why = troupes.army_block(self.state, home.id, share) or ("" if chiefs.obeys(self.state, home) else orders.INDOCILE)
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
            self.globe_yaw, self.globe_pitch = partie_carte.look_hex(self.state, army.position)
            return
        why = troupes.dissolve_block(self.state, bid)
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
                self.globe_yaw, self.globe_pitch = partie_carte.look_hex(self.state, self.state.bands[bid].position)
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
            band = partie_carte.nearest_band_of(self.state, tid, home) if tid is not None else None
            if band is not None:
                self.globe_yaw, self.globe_pitch = partie_carte.look_hex(self.state, band.position)
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

    def tuto_click(self, choice) -> None:
        """Un clic dans la fiche du tutoriel (render_tutoriel.tuto_hit)."""
        if choice == "close":
            tutoriel.guide_close(self)
        elif choice == "next":
            tutoriel.go(self, 1)
        elif choice == "prev":
            tutoriel.go(self, -1)
