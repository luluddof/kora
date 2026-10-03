"""Les ecrans d'avant la partie (dans le style des autres fenetres : cadre
dore, cartes en degrade) :
  - le MENU DE DEMARRAGE, sur la planete qui tourne : Continuer (la partie
    sauvegardee, resumee), Nouvelle partie, Multijoueur, Quitter ;
  - la CREATION DE LA TRIBU : son nom (ecrit, ou tire au hasard), sa
    couleur, et START_BONUS_PICKS bonus de depart choisis dans le pool
    (tech.START_BONUSES), actifs START_BONUS_YEARS ans. En multijoueur, le
    meme ecran (mode "host" ou "join" : l'adresse de l'hote en plus) ;
  - le MULTIJOUEUR : son menu (heberger, rejoindre, reprendre), le SALON
    (les quatre places, prets, discussion) et, en partie, le bandeau des
    joueurs et la discussion (draw_mp_overlay).
Les *_layout et *_hit sont purs (tests) ; draw_* dessinent.
"""

from __future__ import annotations

import pygame

from src.kora import __version__, net, session, tech, theme
from src.kora.render_tech import (
    GOLD,
    GOLD_DEEP,
    GOLD_DIM,
    INK,
    NOTE,
    SOFT,
    _button,
    _fit,
    _fonts,
    _wrap,
    medallion,
)
from src.kora.theme import C, _gradient_card
from src.kora.render_village import _frame, _hover, _plain_button
from src.kora.gamestate import human_dead
from src.kora.peoples import CULTURES, make_name
from src.kora.globe_draw import Planet
from src.kora.layout import HUD_HEIGHT

# Couleurs proposees au joueur (le bleu et le vert sont ceux des grands peuples IA).
PALETTE = (
    (220, 70, 70),
    (230, 140, 50),
    (225, 190, 70),
    (190, 120, 70),
    (225, 110, 170),
    (160, 100, 210),
    (60, 190, 190),
    (225, 225, 215),
    (150, 95, 60),
    (170, 40, 60),
)
NAME_MAX = 20
# Recul de la camera sur la planete du menu, et son decalage vers la droite.
TITLE_ZOOM = 0.34
TITLE_SHIFT = 0.17
# L'icone de chaque bonus de depart (theme.ICON_FILES).
BONUS_ICONS = {
    "bonus:aurochs": "bison", "bonus:bois": "baies", "bonus:rivages": "peche", "bonus:froid": "froid",
    "bonus:prevoyants": "cache", "bonus:fertiles": "gens", "bonus:guerriers": "hache", "bonus:eclaireurs": "voir",
    "bonus:conteurs": "feu", "bonus:rassembleur": "chef", "bonus:diplomates": "peuples", "bonus:campeurs": "camp",
}
TITLE_ITEMS = (
    ("continuer", "Continuer"),
    ("nouvelle", "Nouvelle partie"),
    ("multijoueur", "Multijoueur"),
    ("quitter", "Quitter"),
)


def _big_font(r, size: int):
    """Les petites capitales de la charte (titres du menu)."""
    return theme.font_file("sc-bold", size)


# --- menu de demarrage -----------------------------------------------------------


def title_layout(width: int, height: int) -> dict:
    x = max(40, int(width * 0.07))
    top = max(160, int(height * 0.36))
    bw = 360
    buttons = {}
    y = top
    for key, _label in TITLE_ITEMS:
        h = 58 if key == "continuer" else 46
        buttons[key] = (x, y, bw, h)
        y += h + 12
    return {"buttons": buttons, "title": (x, max(40, int(height * 0.12))), "panel": (0, 0, x + bw + 60, height)}


def title_hit(lay: dict, mx: int, my: int, can_continue: bool = True):
    for key, rect in lay["buttons"].items():
        if _hover(rect, mx, my):
            if key == "continuer" and not can_continue:
                return None
            return key
    return None


def draw_title(r, scene, save_info: dict | None, t: float, message: str = "") -> None:
    """Le menu de demarrage. `scene` : un objet avec .world (la planete),
    dessinee sans brouillard et qui tourne lentement."""
    screen = r.screen
    w, h = screen.get_size()
    yaw = 0.8 + t * 0.03
    # La planete du menu a son propre calque, tout eclaire : celui de la
    # partie (et son brouillard) n'est pas touche.
    mode, planet = r.map_mode, r._planet
    r.map_mode = "relief"
    r._planet = title_planet(r, scene.world)
    r._layer_key = getattr(r, "_title_key", None)
    r._draw_sphere(scene, yaw, 0.35, TITLE_ZOOM)
    r._title_key = r._layer_key
    r.map_mode, r._planet = mode, planet
    r._layer_key = None
    shift = int(w * TITLE_SHIFT)
    screen.scroll(shift, 0)
    screen.fill(C.nuit, (0, 0, shift, h))
    # La nuit a gauche, sous le menu ; une chaleur de feu en bas.
    key = ("title_veil", w, h)
    veil = theme._PANELS.get(key)
    if veil is None:
        veil = pygame.Surface((w, h), pygame.SRCALPHA)
        for x in range(0, min(w, 780), 4):
            a = int(225 * max(0.0, 1.0 - x / 780.0) ** 1.1)
            pygame.draw.rect(veil, (*C.nuit, a), (x, 0, 4, h))
        for y in range(h - 260, h, 4):
            a = int(60 * (y - (h - 260)) / 260)
            pygame.draw.rect(veil, (*C.ocre_sombre, a), (0, y, min(w, 700), 4))
        theme._PANELS[key] = veil
    screen.blit(veil, (0, 0))
    lay = title_layout(w, h)
    r.title_hits = lay
    tx, ty = lay["title"]
    lh = _logo(screen, tx, ty - 8, t)
    theme.text(screen, "Du feu aux premiers villages", "recit", C.lin, (tx + 6, ty + lh - 6))
    theme.stroke(screen, tx + 2, ty + lh + 26, 340, C.ocre, 3)
    mx, my = pygame.mouse.get_pos()
    for key_, label in TITLE_ITEMS:
        rect = lay["buttons"][key_]
        on = key_ != "continuer" or save_info is not None
        hover = on and _hover(rect, mx, my)
        x, y, bw, bh = rect
        if key_ == "continuer":
            theme.button(screen, rect, "", "principal", on, hover)
            lab = theme.font_file("sc-bold", 22)
            img = lab.render(label, True, C.nuit if on else C.cendre)
            screen.blit(img, (x + (bw - img.get_width()) // 2, y + 6))
            if save_info is not None:
                info = f"{save_info['name']}  ·  an {save_info['year']}  ·  {save_info['population']} personnes"
                if save_info.get("villages"):
                    info += f"  ·  {save_info['villages']} village{'s' if save_info['villages'] > 1 else ''}"
                if save_info.get("dead"):
                    info += "  ·  peuple disparu"
            else:
                info = "Aucune partie sauvegardée"
            theme.text(screen, theme.fit(theme.font("mini_gras"), info, bw - 20), "mini_gras", (58, 26, 10) if on else C.cendre, (x + (bw - theme.font("mini_gras").size(theme.fit(theme.font("mini_gras"), info, bw - 20))[0]) // 2, y + bh - 21))
        elif key_ == "quitter":
            theme.button(screen, rect, label, "discret", True, hover, role="h3")
        else:
            theme.button(screen, rect, label, "second", on, hover, role="h3")
    if message:
        x, y, bw, bh = lay["buttons"]["quitter"]
        theme.text(screen, message, "petit_gras", C.alerte, (x, y + bh + 16), 560)
    theme.text(screen, f"version {__version__}", "mini", C.cendre, (14, h - 24))
    theme.text(screen, "Icônes : game-icons.net (CC BY 3.0) · Polices : Alegreya (OFL)", "mini", (92, 80, 68), (w - 420, h - 24))


# --- creation de la tribu -----------------------------------------------------------


def setup_layout(width: int, height: int) -> dict:
    bw = min(1180, width - 40)
    bh = min(720, height - 30)
    bx = (width - bw) // 2
    by = (height - bh) // 2
    name = (bx + 30, by + 112, 320, 36)
    randomize = (name[0] + name[2] + 10, name[1] + 3, 120, 30)
    colors = []
    cx = randomize[0] + randomize[2] + 40
    for i in range(len(PALETTE)):
        colors.append((cx + i * 38, name[1] + 2, 30, 30))
    cols, rows = 4, 3
    top = by + 204
    gap = 12
    card_w = (bw - 60 - (cols - 1) * gap) // cols
    card_h = max(88, min(128, (by + bh - 90 - top - (rows - 1) * gap) // rows))
    cards = {}
    for i, bid in enumerate(tech.START_BONUSES):
        c, rr = i % cols, i // cols
        cards[bid] = (bx + 30 + c * (card_w + gap), top + rr * (card_h + gap), card_w, card_h)
    start = (bx + bw - 30 - 260, by + bh - 62, 260, 42)
    back = (start[0] - 16 - 160, start[1] + 4, 160, 34)
    # Rejoindre une partie : l'adresse de l'hote, en bas a gauche.
    address = (bx + 30, start[1] + 6, min(330, back[0] - bx - 60), 32)
    return {"box": (bx, by, bw, bh), "name": name, "random": randomize, "colors": colors, "cards": cards, "start": start, "back": back, "address": address}


def setup_hit(lay: dict, mx: int, my: int, mode: str = "solo"):
    for key in ("start", "back", "random", "name"):
        if _hover(lay[key], mx, my):
            return key
    if mode == "join" and _hover(lay["address"], mx, my):
        return "address"
    for i, rect in enumerate(lay["colors"]):
        if _hover(rect, mx, my):
            return f"color:{i}"
    for bid, rect in lay["cards"].items():
        if _hover(rect, mx, my):
            return f"bonus:{bid}"
    return None


START_LABEL = {"solo": "Commencer la partie", "host": "Ouvrir le salon", "join": "Rejoindre"}


def draw_setup(r, setup: dict, t: float, save_info: dict | None, hint: str = "") -> None:
    """setup : {"name", "color", "bonuses" (liste), "typing" (False, True :
    le nom, "address" : l'adresse), "mode" (solo, host, join), "address"}."""
    title_font, head_font, _era, _num = _fonts(r)
    screen = r.screen
    w, h = screen.get_size()
    lay = setup_layout(w, h)
    r.setup_hits = lay
    mx, my = pygame.mouse.get_pos()
    veil = pygame.Surface((w, h), pygame.SRCALPHA)
    veil.fill((6, 8, 12, 170))
    screen.blit(veil, (0, 0))
    _frame(r, lay["box"])
    bx, by, bw, bh = lay["box"]
    theme.title(screen, "Votre peuple", bx + 30, by + 18, "titre")
    theme.text(screen, "On vient de maîtriser le feu. Nommez votre peuple, donnez-lui sa couleur et ses forces de départ.", "recit_petit", C.lin, (bx + 32, by + 62))
    # Le nom.
    theme.text(screen, "Nom du peuple", "etiquette", C.ocre_jaune, (lay["name"][0], lay["name"][1] - 20))
    nx, ny, nw, nh = lay["name"]
    mode = setup.get("mode", "solo")
    typing = setup.get("typing") is True
    screen.blit(_gradient_card(nw, nh, (29, 22, 17), (20, 16, 12), 6), (nx, ny))
    pygame.draw.rect(screen, GOLD if typing else GOLD_DEEP, lay["name"], 2 if typing else 1, border_radius=6)
    text = setup.get("name", "")
    caret = "|" if typing and int(t * 2) % 2 == 0 else ""
    screen.blit(head_font.render(text + caret, True, INK), (nx + 10, ny + (nh - head_font.get_height()) // 2))
    _button(screen, r.small, lay["random"], "Au hasard", True, _hover(lay["random"], mx, my))
    # La couleur.
    theme.text(screen, "Couleur", "etiquette", C.ocre_jaune, (lay["colors"][0][0], lay["name"][1] - 20))
    for i, rect in enumerate(lay["colors"]):
        color = PALETTE[i]
        chosen = tuple(setup.get("color", ())) == color
        cx, cy, cw, ch = rect
        pygame.draw.rect(screen, color, rect, border_radius=5)
        pygame.draw.rect(screen, (239, 228, 204) if chosen else (38, 29, 22), rect, 3 if chosen else 1, border_radius=5)
    # Les bonus.
    picks = list(setup.get("bonuses", []))
    head = f"BONUS DE DÉPART  ·  choisissez-en {tech.START_BONUS_PICKS} ({len(picks)}/{tech.START_BONUS_PICKS})  ·  ils durent {tech.START_BONUS_YEARS} ans, puis s'éteignent"
    first = min(r_[1] for r_ in lay["cards"].values())
    screen.blit(r.tiny.render(head, True, GOLD), (bx + 30, first - 22))
    pygame.draw.line(screen, GOLD_DEEP, (bx + 30, first - 6), (bx + bw - 30, first - 6))
    for bid, rect in lay["cards"].items():
        bonus = tech.START_BONUSES[bid]
        chosen = bid in picks
        x, y, cw, ch = rect
        hover = _hover(rect, mx, my)
        top, bot = ((86, 70, 38), (54, 43, 24)) if chosen else (((67, 50, 36), (39, 30, 23)) if hover else ((52, 40, 30), (34, 25, 20)))
        screen.blit(_gradient_card(cw, ch, top, bot, 7), (x, y))
        pygame.draw.rect(screen, GOLD if chosen else (GOLD_DEEP if hover else (95, 72, 51)), rect, 2 if chosen else 1, border_radius=7)
        med = theme.medallion(BONUS_ICONS.get(bid, "feu"), 16, "connu" if chosen else "normal")
        screen.blit(med, (x + 6, y + 6))
        screen.blit(r.small.render(_fit(r.small, bonus.name, cw - 52), True, INK), (x + 46, y + 9))
        yy = y + 30
        for part in _wrap(r.tiny, bonus.about, cw - 54)[:2]:
            screen.blit(r.tiny.render(part, True, SOFT), (x + 46, yy))
            yy += 13
        yy += 3
        for line in tech.start_bonus_lines(bonus):
            for k, part in enumerate(_wrap(r.tiny, line, cw - 30)[:3]):
                if yy + 13 > y + ch - 4:
                    break
                if k == 0:
                    pygame.draw.polygon(screen, (178, 205, 140), [(x + 12, yy + 3), (x + 18, yy + 7), (x + 12, yy + 11)])
                screen.blit(r.tiny.render(part, True, (178, 205, 140)), (x + 24, yy))
                yy += 13
        if chosen:
            pygame.draw.circle(screen, GOLD, (x + cw - 14, y + 14), 8)
            pygame.draw.lines(screen, (40, 30, 14), False, [(x + cw - 18, y + 14), (x + cw - 15, y + 17), (x + cw - 10, y + 11)], 2)
    # En bas : resume (ou l'adresse de l'hote), avertissement, boutons.
    sx, sy = bx + 30, lay["start"][1] + 4
    if mode == "join":
        ax, ay, aw, ah = lay["address"]
        on = setup.get("typing") == "address"
        screen.blit(r.tiny.render("ADRESSE DE L'HÔTE (il la voit dans son salon)", True, GOLD_DIM), (ax, ay - 16))
        screen.blit(_gradient_card(aw, ah, (29, 22, 17), (20, 16, 12), 6), (ax, ay))
        pygame.draw.rect(screen, GOLD if on else GOLD_DEEP, lay["address"], 2 if on else 1, border_radius=6)
        addr = setup.get("address", "")
        shown = addr + ("|" if on and int(t * 2) % 2 == 0 else "")
        if not addr and not on:
            screen.blit(r.small.render("ex. 192.168.1.20", True, (130, 113, 96)), (ax + 10, ay + 8))
        else:
            screen.blit(r.small.render(_fit(r.small, shown, aw - 16), True, INK), (ax + 10, ay + 8))
        if hint:
            screen.blit(r.tiny.render(_fit(r.tiny, hint, lay["back"][0] - ax - aw - 30), True, (236, 170, 90)), (ax + aw + 14, ay + 9))
    else:
        names = ", ".join(tech.START_BONUSES[b].name for b in picks) or "aucun bonus choisi"
        screen.blit(r.small.render(_fit(r.small, f"{text or '?'}  ·  {names}", lay["back"][0] - sx - 20), True, INK), (sx, sy))
        note = hint
        if not note and mode == "host":
            note = "Vos amis choisiront leur peuple de leur côté, dans le salon."
        elif not note and save_info is not None:
            note = f"Votre partie en cours ({save_info['name']}, an {save_info['year']}) sera mise de côté, pas effacée."
        if note:
            color = (236, 170, 90) if hint else NOTE
            screen.blit(r.tiny.render(_fit(r.tiny, note, lay["back"][0] - sx - 20), True, color), (sx, sy + 22))
    ready = setup_ready(setup)
    _plain_button(r, lay["back"], "Retour", _hover(lay["back"], mx, my))
    _button(screen, head_font, lay["start"], START_LABEL.get(mode, "Commencer la partie"), ready, ready and _hover(lay["start"], mx, my))


def random_name(rng, taken=()) -> str:
    return make_name(rng, CULTURES["joueur"], taken)


def new_setup(rng) -> dict:
    return {"name": "Kora", "color": PALETTE[0], "bonuses": [], "typing": False}


def setup_click(setup: dict, hit: str, rng) -> str:
    """Un clic dans l'ecran de creation ; rend un message (vide si rien a dire)."""
    setup["typing"] = True if hit == "name" else ("address" if hit == "address" else False)
    if hit == "random":
        setup["name"] = random_name(rng)
    elif hit.startswith("color:"):
        setup["color"] = PALETTE[int(hit.split(":")[1])]
    elif hit.startswith("bonus:"):
        bid = hit[len("bonus:"):]
        picks = setup.setdefault("bonuses", [])
        if bid in picks:
            picks.remove(bid)
        elif len(picks) >= tech.START_BONUS_PICKS:
            return f"Déjà {tech.START_BONUS_PICKS} bonus : retirez-en un d'abord."
        else:
            picks.append(bid)
    return ""


ADDRESS_MAX = 64


def setup_key(setup: dict, event) -> None:
    """Frappe au clavier dans le nom du peuple (ou l'adresse de l'hote)."""
    if not setup.get("typing"):
        return
    if setup.get("typing") == "address":
        addr = setup.get("address", "")
        if event.key == pygame.K_BACKSPACE:
            setup["address"] = addr[:-1]
        elif event.key in (pygame.K_RETURN, pygame.K_KP_ENTER, pygame.K_TAB):
            setup["typing"] = False
        else:
            ch = getattr(event, "unicode", "")
            if ch and (ch.isalnum() or ch in ".:-_[]") and len(addr) < ADDRESS_MAX:
                setup["address"] = addr + ch
        return
    name = setup.get("name", "")
    if event.key == pygame.K_BACKSPACE:
        setup["name"] = name[:-1]
    elif event.key in (pygame.K_RETURN, pygame.K_KP_ENTER, pygame.K_TAB):
        setup["typing"] = False
    else:
        ch = getattr(event, "unicode", "")
        if ch and (ch.isalpha() or ch in " -'") and len(name) < NAME_MAX:
            setup["name"] = (name + ch)[:NAME_MAX]


def setup_missing(setup: dict) -> str:
    if not setup.get("name", "").strip():
        return "Donnez un nom à votre peuple."
    if setup.get("mode") == "join" and not setup.get("address", "").strip():
        return "Écrivez l'adresse de l'hôte."
    n = len(setup.get("bonuses", []))
    if n < tech.START_BONUS_PICKS:
        return f"Choisissez encore {tech.START_BONUS_PICKS - n} bonus de départ."
    return ""


def setup_for_game(setup: dict) -> dict:
    """Ce que sim.new_game(setup=...) recoit."""
    return {"name": setup["name"].strip(), "color": tuple(setup["color"]), "bonuses": list(setup["bonuses"])}


def setup_ready(setup: dict) -> bool:
    if setup.get("mode") == "join" and not setup.get("address", "").strip():
        return False
    return bool(setup.get("name", "").strip()) and len(setup.get("bonuses", [])) == tech.START_BONUS_PICKS


class TitleScene:
    """Ce que _draw_sphere lit pour peindre la planete du menu : le monde,
    sans brouillard (aucune vue de joueur)."""

    def __init__(self, world):
        self.world = world
        self.vision = None
        self.sites = {}
        self.bands = {}
        self.tribes = {}


def title_planet(r, world):
    """La planete du menu, toute eclairee (pas de brouillard), gardee a part."""
    planet = getattr(r, "_title_planet", None)
    if planet is None or planet.world is not world:
        planet = Planet(world)
        planet.fog[:] = 2
        planet.fog_gen += 1
        planet.zones_on = False
        r._title_planet = planet
        r._title_key = None
    return planet


# --- le multijoueur : son menu -------------------------------------------------------------------

MP_ITEMS = (
    ("heberger", "Héberger une partie", "Vos amis vous rejoignent ; vous tenez le temps."),
    ("rejoindre", "Rejoindre une partie", "L'adresse de l'hôte suffit."),
    ("reprendre", "Reprendre la partie à plusieurs", "La dernière partie que vous avez hébergée."),
    ("retour", "Retour", ""),
)


def mp_menu_layout(width: int, height: int) -> dict:
    lay = title_layout(width, height)
    x, top = lay["buttons"]["continuer"][0], lay["buttons"]["continuer"][1]
    buttons = {}
    y = top
    for key, _label, _about in MP_ITEMS:
        h = 40 if key == "retour" else 58
        buttons[key] = (x, y, 380, h)
        y += h + 12
    return {"buttons": buttons, "title": lay["title"], "help": (x, y + 6)}


def mp_menu_hit(lay: dict, mx: int, my: int, can_resume: bool = True):
    for key, rect in lay["buttons"].items():
        if _hover(rect, mx, my):
            if key == "reprendre" and not can_resume:
                return None
            return key
    return None


MP_HELP = (
    "Même maison (même box) : l'hôte donne l'adresse affichée dans son salon.",
    "Par Internet : un réseau privé commun (Radmin VPN, ZeroTier, Tailscale),",
    "ou l'hôte ouvre le port 45170 (TCP) de sa box vers son PC.",
    "Tout le monde doit avoir la même version de Kora.",
)


def draw_mp_menu(r, scene, resume_info: dict | None, t: float, message: str = "") -> None:
    draw_title(r, scene, None, t, "")
    screen = r.screen
    w, h = screen.get_size()
    lay = mp_menu_layout(w, h)
    r.mp_menu_hits = lay
    # Le menu du titre s'efface derriere celui du multijoueur.
    veil = pygame.Surface((440, h), pygame.SRCALPHA)
    veil.fill((6, 8, 12, 245))
    x0 = lay["buttons"]["heberger"][0] - 10
    screen.blit(veil, (x0, lay["buttons"]["heberger"][1] - 60))
    screen.blit(_big_font(r, 26).render("Partie à plusieurs", True, GOLD), (x0 + 10, lay["buttons"]["heberger"][1] - 48))
    mx, my = pygame.mouse.get_pos()
    for key, label, about in MP_ITEMS:
        rect = lay["buttons"][key]
        on = key != "reprendre" or resume_info is not None
        hover = on and _hover(rect, mx, my)
        if key == "retour":
            _plain_button(r, rect, label, hover)
            continue
        x, y, bw, bh = rect
        _button(screen, _big_font(r, 19), rect, "", on, hover)
        lab = _big_font(r, 19).render(label, True, (28, 20, 8) if hover else INK if on else (143, 130, 114))
        screen.blit(lab, (x + (bw - lab.get_width()) // 2, y + 7))
        sub = about
        if key == "reprendre":
            sub = f"{resume_info['name']}  ·  an {resume_info['year']}" if resume_info else "Aucune partie à plusieurs sauvegardée"
        s_ = r.tiny.render(_fit(r.tiny, sub, bw - 16), True, (40, 30, 14) if hover else NOTE)
        screen.blit(s_, (x + (bw - s_.get_width()) // 2, y + bh - 17))
    hx, hy = lay["help"]
    for i, line in enumerate(MP_HELP):
        screen.blit(r.tiny.render(line, True, SOFT if i else (200, 196, 180)), (hx, hy + i * 15))
    if message:
        screen.blit(r.small.render(_fit(r.small, message, 520), True, (236, 170, 90)), (hx, hy + len(MP_HELP) * 15 + 10))


# --- le salon ------------------------------------------------------------------------------------


def lobby_layout(width: int, height: int) -> dict:
    bw = min(1100, width - 40)
    bh = min(680, height - 30)
    bx = (width - bw) // 2
    by = (height - bh) // 2
    gap = 12
    seat_w = (bw - 60 - 3 * gap) // 4
    seats = {tid: (bx + 30 + i * (seat_w + gap), by + 118, seat_w, 220) for i, tid in enumerate((1, 2, 3, 4))}
    chat = (bx + 30, by + 118 + 220 + 24, bw - 60, bh - 118 - 220 - 24 - 80)
    chat_input = (chat[0], chat[1] + chat[3] - 30, chat[2], 30)
    go = (bx + bw - 30 - 260, by + bh - 62, 260, 42)
    back = (go[0] - 16 - 180, go[1] + 4, 180, 34)
    ready = (back[0] - 16 - 200, go[1] + 4, 200, 34)
    return {"box": (bx, by, bw, bh), "seats": seats, "chat": chat, "chat_input": chat_input, "go": go, "back": back, "ready": ready}


def lobby_hit(lay: dict, mx: int, my: int, role: str):
    for key in ("go", "back", "ready", "chat_input"):
        if key == "go" and role != "host":
            continue
        if key == "ready" and role == "host":
            continue
        if _hover(lay[key], mx, my):
            return key
    for tid, rect in lay["seats"].items():
        if _hover(rect, mx, my):
            return f"seat:{tid}"
    return None


def _addresses(mp) -> tuple[str, str]:
    """L'adresse a donner (celle du reseau principal) et les autres."""
    ips = net.local_addresses()
    port = getattr(mp, "port", net.PORT)
    suffix = "" if port == net.PORT else f":{port}"
    return ips[0] + suffix, ", ".join(ip + suffix for ip in ips[1:4])


def draw_lobby(r, mp, t: float, chat_text, hint: str = "", status: str = "") -> None:
    """Le salon : les quatre places (vallee, steppe, foret, cote), qui est
    pret, la discussion. mp : session.HostSession ou ClientSession."""
    title_font, head_font, _era, _num = _fonts(r)
    screen = r.screen
    w, h = screen.get_size()
    lay = lobby_layout(w, h)
    r.lobby_hits = lay
    mx, my = pygame.mouse.get_pos()
    veil = pygame.Surface((w, h), pygame.SRCALPHA)
    veil.fill((6, 8, 12, 175))
    screen.blit(veil, (0, 0))
    _frame(r, lay["box"])
    bx, by, bw, bh = lay["box"]
    host = mp.role == "host"
    resume = bool(getattr(mp, "resume", None))
    title = "Le salon" + ("  ·  reprise de la partie" if resume else "")
    screen.blit(title_font.render(title, True, GOLD), (bx + 30, by + 22))
    if host:
        main, others = _addresses(mp)
        line1 = f"Donnez à vos amis cette adresse : {main}" + (f"   (autres cartes réseau de ce PC : {others})" if others else "")
        line2 = "Par Internet : un réseau privé commun (Radmin VPN, ZeroTier, Tailscale : son adresse à lui) ou le port 45170 ouvert sur votre box."
    else:
        line1 = status or "Vous êtes dans le salon. L'hôte lancera la partie quand tout le monde sera prêt."
        line2 = "Cliquez sur une place libre pour changer de pays de départ." if not resume else "Vous retrouvez votre peuple ; l'hôte lance quand tout le monde est la."
    screen.blit(r.small.render(_fit(r.small, line1, bw - 60), True, INK), (bx + 32, by + 58))
    screen.blit(r.tiny.render(_fit(r.tiny, line2, bw - 60), True, NOTE), (bx + 32, by + 80))
    me = mp.me
    for tid, rect in lay["seats"].items():
        seat = mp.seats.get(tid)
        x, y, cw, ch = rect
        mine = tid == me
        free = seat is None
        hover = _hover(rect, mx, my) and free and not host and not resume
        top, bot = ((62, 54, 34), (40, 34, 22)) if mine else (((67, 50, 36), (39, 30, 23)) if hover else ((47, 36, 28), (31, 23, 18)))
        screen.blit(_gradient_card(cw, ch, top, bot, 8), (x, y))
        pygame.draw.rect(screen, GOLD if mine else (GOLD_DEEP if hover else (95, 72, 51)), rect, 2 if mine else 1, border_radius=8)
        screen.blit(head_font.render(session.SLOTS[tid], True, GOLD if mine else INK), (x + 12, y + 10))
        yy = y + 36
        for part in _wrap(r.tiny, session.SLOT_NOTE[tid], cw - 24)[:2]:
            screen.blit(r.tiny.render(part, True, NOTE), (x + 12, yy))
            yy += 13
        yy += 8
        pygame.draw.line(screen, (70, 64, 50), (x + 12, yy), (x + cw - 12, yy))
        yy += 10
        if free:
            screen.blit(r.small.render("Place libre", True, SOFT), (x + 12, yy))
            yy += 20
            note = "Un peuple de l'IA y vivra." if host or resume else "Cliquez pour la prendre."
            screen.blit(r.tiny.render(note, True, NOTE), (x + 12, yy))
            continue
        pygame.draw.circle(screen, tuple(seat.color), (x + 20, yy + 9), 7)
        pygame.draw.circle(screen, (20, 20, 20), (x + 20, yy + 9), 7, 1)
        label = seat.name + ("  (vous)" if mine else "")
        screen.blit(r.small.render(_fit(r.small, label, cw - 44), True, INK), (x + 34, yy + 1))
        yy += 24
        role = "L'hôte" if seat.host else ("Absent" if not seat.present else ("Prêt" if seat.ready else "Se prépare..."))
        tint = GOLD if seat.host else ((167, 152, 130) if not seat.present else ((157, 191, 110) if seat.ready else (236, 170, 90)))
        screen.blit(r.tiny.render(role, True, tint), (x + 12, yy))
        yy += 18
        for bid in seat.bonuses:
            bonus = tech.START_BONUSES.get(bid)
            if bonus is None:
                continue
            screen.blit(r.tiny.render(_fit(r.tiny, "+ " + bonus.name, cw - 24), True, (178, 205, 140)), (x + 12, yy))
            yy += 15
    # La discussion.
    cx, cy, cw, chh = lay["chat"]
    screen.blit(r.tiny.render("DISCUSSION  ·  Entrée pour écrire", True, GOLD_DIM), (cx, cy - 16))
    screen.blit(_gradient_card(cw, chh, (27, 20, 16), (20, 16, 12), 6), (cx, cy))
    pygame.draw.rect(screen, (80, 60, 42), lay["chat"], 1, border_radius=6)
    rows = max(1, (chh - 40) // 16)
    for i, msg in enumerate(mp.chat[-rows:]):
        who = r.tiny.render(msg["from"] + " :", True, GOLD)
        screen.blit(who, (cx + 10, cy + 8 + i * 16))
        screen.blit(r.tiny.render(_fit(r.tiny, msg["text"], cw - who.get_width() - 30), True, INK), (cx + 16 + who.get_width(), cy + 8 + i * 16))
    ix, iy, iw, ih = lay["chat_input"]
    on = chat_text is not None
    pygame.draw.rect(screen, (37, 28, 22), lay["chat_input"], border_radius=5)
    pygame.draw.rect(screen, GOLD if on else (95, 72, 51), lay["chat_input"], 1, border_radius=5)
    shown = (chat_text + ("|" if int(t * 2) % 2 == 0 else "")) if on else "Écrire un message..."
    screen.blit(r.small.render(_fit(r.small, shown, iw - 16), True, INK if on else (130, 113, 96)), (ix + 8, iy + 7))
    # En bas.
    if hint:
        screen.blit(r.tiny.render(_fit(r.tiny, hint, lay["ready"][0] - bx - 60), True, (236, 170, 90)), (bx + 30, lay["go"][1] + 14))
    _plain_button(r, lay["back"], "Quitter le salon" if not host else "Fermer le salon", _hover(lay["back"], mx, my))
    if host:
        why = mp.can_start()
        _button(screen, head_font, lay["go"], "Lancer la partie", not why, not why and _hover(lay["go"], mx, my))
        if why and not hint:
            screen.blit(r.tiny.render(_fit(r.tiny, why, lay["back"][0] - bx - 60), True, NOTE), (bx + 30, lay["go"][1] + 14))
    else:
        mine = mp.seats.get(me) if me is not None else None
        ready = bool(mine and mine.ready)
        _button(screen, r.small, lay["ready"], "Pas prêt" if ready else "Je suis prêt", True, _hover(lay["ready"], mx, my))


# --- en partie : le bandeau des joueurs, la discussion -------------------------------------------------

CHAT_SHOWN = 24.0


def draw_mp_overlay(r, mp, state, chat_text) -> None:
    import time as _time

    screen = r.screen
    w, h = screen.get_size()
    chips = []
    for tid, seat in sorted(mp.seats.items()):
        tribe = state.tribes.get(tid)
        name = tribe.name if tribe is not None else seat.name
        note = ""
        if not seat.present:
            note = " (absent)"
        elif human_dead(state, tid):
            note = " (disparu)"
        chips.append((tuple(tribe.color) if tribe is not None else tuple(seat.color), name + (" (vous)" if tid == state.viewer else "") + note, seat.present))
    wait = getattr(mp, "waiting_for", "")
    parts = [r.tiny.size(text)[0] + 22 for _c, text, _p in chips]
    total = sum(parts) + 16 + (r.tiny.size(f"on attend : {wait}")[0] + 20 if wait else 0)
    x = (w - total) // 2
    y = HUD_HEIGHT + 4
    pygame.draw.rect(screen, (20, 16, 12), (x, y, total, 20), border_radius=6)
    pygame.draw.rect(screen, (70, 64, 50), (x, y, total, 20), 1, border_radius=6)
    x += 8
    for (color, text, present), pw in zip(chips, parts):
        pygame.draw.circle(screen, color if present else (112, 89, 68), (x + 6, y + 10), 5)
        screen.blit(r.tiny.render(text, True, INK if present else (143, 130, 115)), (x + 15, y + 3))
        x += pw
    if wait:
        screen.blit(r.tiny.render(f"on attend : {wait}", True, (236, 170, 90)), (x + 4, y + 3))
    # La discussion, en bas a gauche.
    now = _time.time()
    lines = [m for m in mp.chat if chat_text is not None or now - m["at"] < CHAT_SHOWN][-6:]
    bx, bw = 12, min(460, w // 2)
    by = h - 36 - len(lines) * 16
    for i, msg in enumerate(lines):
        who = r.tiny.render(msg["from"] + " :", True, GOLD)
        tx = bx + 8 + who.get_width() + 6
        text = r.tiny.render(_fit(r.tiny, msg["text"], bw - tx), True, INK)
        back = pygame.Surface((who.get_width() + text.get_width() + 22, 16), pygame.SRCALPHA)
        back.fill((10, 12, 16, 170))
        screen.blit(back, (bx, by + i * 16))
        screen.blit(who, (bx + 6, by + i * 16 + 1))
        screen.blit(text, (tx, by + i * 16 + 1))
    if chat_text is not None:
        rect = (bx, h - 32, bw, 24)
        pygame.draw.rect(screen, (29, 22, 17), rect, border_radius=5)
        pygame.draw.rect(screen, GOLD, rect, 1, border_radius=5)
        caret = "|" if int(now * 2) % 2 == 0 else ""
        screen.blit(r.small.render(_fit(r.small, "> " + chat_text + caret, bw - 16), True, INK), (bx + 8, h - 28))
        hint = r.tiny.render("Entrée : envoyer  ·  Échap : annuler", True, NOTE)
        screen.blit(hint, (bx + 2, by - 16))
    elif not lines:
        hint = r.tiny.render("Entrée : écrire aux autres joueurs", True, (138, 123, 108))
        screen.blit(hint, (bx, h - 20))


def _logo(screen, x: int, y: int, t: float) -> int:
    """Le logo : KORA grave dans l'ocre, une lueur de feu qui respire."""
    f = theme.font("logo")
    img = f.render("KORA", True, C.ocre)
    glow = pygame.Surface((img.get_width() + 80, img.get_height() + 60), pygame.SRCALPHA)
    k = 0.6 + 0.4 * theme.pulse(t, 3.0)
    for i in range(10, 0, -1):
        pygame.draw.ellipse(glow, (*C.braise, int(7 * k * (11 - i))), (40 - i * 4, 30 - i * 3, img.get_width() + i * 8, img.get_height() + i * 6))
    screen.blit(glow, (x - 40, y - 30))
    screen.blit(f.render("KORA", True, C.nuit), (x + 3, y + 4))
    screen.blit(img, (x, y))
    # Le haut des lettres, eclaire par le feu.
    hi = f.render("KORA", True, C.braise)
    top = pygame.Surface(hi.get_size(), pygame.SRCALPHA)
    top.blit(hi, (0, 0))
    mask = pygame.Surface(hi.get_size(), pygame.SRCALPHA)
    for yy in range(hi.get_height()):
        a = int(160 * max(0.0, 1.0 - yy / (hi.get_height() * 0.55)))
        pygame.draw.line(mask, (255, 255, 255, a), (0, yy), (hi.get_width(), yy))
    top.blit(mask, (0, 0), special_flags=pygame.BLEND_RGBA_MULT)
    screen.blit(top, (x, y))
    return img.get_height()
