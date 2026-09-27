"""Les ecrans d'avant la partie (dans le style des autres fenetres : cadre
dore, cartes en degrade) :
  - le MENU DE DEMARRAGE, sur la planete qui tourne : Continuer (la partie
    sauvegardee, resumee), Nouvelle partie, Multijoueur, Quitter ;
  - la CREATION DE LA TRIBU : son nom (ecrit, ou tire au hasard), sa
    couleur, et START_BONUS_PICKS bonus de depart choisis dans le pool
    (tech.START_BONUSES), actifs START_BONUS_YEARS ans.
Les *_layout et *_hit sont purs (tests) ; draw_* dessinent.
"""

from __future__ import annotations

import pygame

from src.kora import tech
from src.kora.render_tech import GOLD, GOLD_DEEP, GOLD_DIM, INK, NOTE, SOFT, _button, _fit, _gradient_card, _wrap, medallion
from src.kora.render_village import _frame, _hover, _plain_button

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
TITLE_ITEMS = (
    ("continuer", "Continuer"),
    ("nouvelle", "Nouvelle partie"),
    ("multijoueur", "Multijoueur"),
    ("quitter", "Quitter"),
)


def _big_font(r, size: int):
    key = f"menu_font_{size}"
    if not hasattr(r, key):
        setattr(r, key, pygame.font.SysFont("georgia", size, bold=True))
    return getattr(r, key)


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
    from src.kora import __version__

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
    screen.fill((6, 8, 14), (0, 0, shift, h))
    # Un voile a gauche, sous le menu.
    veil = pygame.Surface((w, h), pygame.SRCALPHA)
    for x in range(0, min(w, 760), 4):
        a = int(210 * max(0.0, 1.0 - x / 760.0) ** 1.2)
        pygame.draw.rect(veil, (6, 8, 12, a), (x, 0, 4, h))
    screen.blit(veil, (0, 0))
    lay = title_layout(w, h)
    r.title_hits = lay
    tx, ty = lay["title"]
    big = _big_font(r, 78)
    shadow = big.render("KORA", True, (20, 16, 10))
    screen.blit(shadow, (tx + 3, ty + 3))
    screen.blit(big.render("KORA", True, GOLD), (tx, ty))
    sub = _big_font(r, 20).render("Du feu aux premiers villages", True, (226, 214, 186))
    screen.blit(sub, (tx + 4, ty + big.get_height() + 2))
    pygame.draw.line(screen, GOLD_DEEP, (tx, ty + big.get_height() + 34), (tx + 360, ty + big.get_height() + 34))
    mx, my = pygame.mouse.get_pos()
    for key, label in TITLE_ITEMS:
        rect = lay["buttons"][key]
        on = key != "continuer" or save_info is not None
        hover = on and _hover(rect, mx, my)
        if key == "quitter":
            _plain_button(r, rect, label, hover, r.tech_head if hasattr(r, "tech_head") else r.font)
        elif key == "continuer":
            _button(screen, _big_font(r, 20), rect, "", on, hover)
            x, y, bw, bh = rect
            lab = _big_font(r, 20).render(label, True, (28, 20, 8) if hover else INK if on else (126, 128, 134))
            screen.blit(lab, (x + (bw - lab.get_width()) // 2, y + 7))
        else:
            _button(screen, _big_font(r, 20), rect, label, on, hover)
        if key == "continuer":
            if save_info is not None:
                info = f"{save_info['name']}  ·  an {save_info['year']}  ·  {save_info['population']} personnes"
                if save_info.get("villages"):
                    info += f"  ·  {save_info['villages']} village{'s' if save_info['villages'] > 1 else ''}"
                if save_info.get("dead"):
                    info += "  ·  peuple disparu"
            else:
                info = "Aucune partie sauvegardee"
            s = r.tiny.render(_fit(r.tiny, info, bw - 16), True, (40, 30, 14) if hover else NOTE)
            screen.blit(s, (x + (bw - s.get_width()) // 2, y + bh - 17))
    if message:
        m = r.small.render(message, True, (236, 170, 90))
        x, y, bw, bh = lay["buttons"]["quitter"]
        screen.blit(m, (x, y + bh + 16))
    ver = r.tiny.render(f"version {__version__}", True, (150, 150, 146))
    screen.blit(ver, (12, h - ver.get_height() - 8))


# --- creation de la tribu -----------------------------------------------------------


def setup_layout(width: int, height: int) -> dict:
    bw = min(1180, width - 40)
    bh = min(720, height - 30)
    bx = (width - bw) // 2
    by = (height - bh) // 2
    name = (bx + 30, by + 96, 320, 36)
    randomize = (name[0] + name[2] + 10, name[1] + 3, 120, 30)
    colors = []
    cx = randomize[0] + randomize[2] + 40
    for i in range(len(PALETTE)):
        colors.append((cx + i * 38, name[1] + 2, 30, 30))
    cols, rows = 4, 3
    top = by + 190
    gap = 12
    card_w = (bw - 60 - (cols - 1) * gap) // cols
    card_h = max(88, min(128, (by + bh - 90 - top - (rows - 1) * gap) // rows))
    cards = {}
    for i, bid in enumerate(tech.START_BONUSES):
        c, rr = i % cols, i // cols
        cards[bid] = (bx + 30 + c * (card_w + gap), top + rr * (card_h + gap), card_w, card_h)
    start = (bx + bw - 30 - 260, by + bh - 62, 260, 42)
    back = (start[0] - 16 - 160, start[1] + 4, 160, 34)
    return {"box": (bx, by, bw, bh), "name": name, "random": randomize, "colors": colors, "cards": cards, "start": start, "back": back}


def setup_hit(lay: dict, mx: int, my: int):
    for key in ("start", "back", "random", "name"):
        if _hover(lay[key], mx, my):
            return key
    for i, rect in enumerate(lay["colors"]):
        if _hover(rect, mx, my):
            return f"color:{i}"
    for bid, rect in lay["cards"].items():
        if _hover(rect, mx, my):
            return f"bonus:{bid}"
    return None


def draw_setup(r, setup: dict, t: float, save_info: dict | None, hint: str = "") -> None:
    """setup : {"name", "color", "bonuses" (liste), "typing" (bool)}."""
    from src.kora.render_tech import _fonts

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
    screen.blit(title_font.render("Votre peuple", True, GOLD), (bx + 30, by + 22))
    screen.blit(
        r.tiny.render("On vient de maitriser le feu. Nommez votre peuple, donnez-lui sa couleur et ses forces de depart.", True, NOTE),
        (bx + 32, by + 56),
    )
    # Le nom.
    screen.blit(r.tiny.render("NOM DU PEUPLE", True, GOLD_DIM), (lay["name"][0], lay["name"][1] - 17))
    nx, ny, nw, nh = lay["name"]
    typing = setup.get("typing", False)
    screen.blit(_gradient_card(nw, nh, (20, 22, 28), (14, 16, 20), 6), (nx, ny))
    pygame.draw.rect(screen, GOLD if typing else GOLD_DEEP, lay["name"], 2 if typing else 1, border_radius=6)
    text = setup.get("name", "")
    caret = "|" if typing and int(t * 2) % 2 == 0 else ""
    screen.blit(head_font.render(text + caret, True, INK), (nx + 10, ny + (nh - head_font.get_height()) // 2))
    _button(screen, r.small, lay["random"], "Au hasard", True, _hover(lay["random"], mx, my))
    # La couleur.
    screen.blit(r.tiny.render("COULEUR", True, GOLD_DIM), (lay["colors"][0][0], lay["name"][1] - 17))
    for i, rect in enumerate(lay["colors"]):
        color = PALETTE[i]
        chosen = tuple(setup.get("color", ())) == color
        cx, cy, cw, ch = rect
        pygame.draw.rect(screen, color, rect, border_radius=5)
        pygame.draw.rect(screen, (250, 244, 226) if chosen else (30, 30, 30), rect, 3 if chosen else 1, border_radius=5)
    # Les bonus.
    picks = list(setup.get("bonuses", []))
    head = f"BONUS DE DEPART  ·  choisissez-en {tech.START_BONUS_PICKS} ({len(picks)}/{tech.START_BONUS_PICKS})  ·  ils durent {tech.START_BONUS_YEARS} ans, puis s'eteignent"
    first = min(r_[1] for r_ in lay["cards"].values())
    screen.blit(r.tiny.render(head, True, GOLD), (bx + 30, first - 22))
    pygame.draw.line(screen, GOLD_DEEP, (bx + 30, first - 6), (bx + bw - 30, first - 6))
    for bid, rect in lay["cards"].items():
        bonus = tech.START_BONUSES[bid]
        chosen = bid in picks
        x, y, cw, ch = rect
        hover = _hover(rect, mx, my)
        top, bot = ((86, 70, 38), (54, 43, 24)) if chosen else (((46, 50, 58), (28, 30, 35)) if hover else ((36, 40, 48), (24, 26, 30)))
        screen.blit(_gradient_card(cw, ch, top, bot, 7), (x, y))
        pygame.draw.rect(screen, GOLD if chosen else (GOLD_DEEP if hover else (70, 72, 78)), rect, 2 if chosen else 1, border_radius=7)
        state = "connu" if chosen else "disponible"
        med = medallion(0, bonus.icon, state, 15)
        screen.blit(med, (x + 8, y + 8))
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
                    pygame.draw.polygon(screen, (184, 222, 168), [(x + 12, yy + 3), (x + 18, yy + 7), (x + 12, yy + 11)])
                screen.blit(r.tiny.render(part, True, (184, 222, 168)), (x + 24, yy))
                yy += 13
        if chosen:
            pygame.draw.circle(screen, GOLD, (x + cw - 14, y + 14), 8)
            pygame.draw.lines(screen, (40, 30, 14), False, [(x + cw - 18, y + 14), (x + cw - 15, y + 17), (x + cw - 10, y + 11)], 2)
    # En bas : resume, avertissement, boutons.
    sx, sy = bx + 30, lay["start"][1] + 4
    names = ", ".join(tech.START_BONUSES[b].name for b in picks) or "aucun bonus choisi"
    screen.blit(r.small.render(_fit(r.small, f"{text or '?'}  ·  {names}", lay["back"][0] - sx - 20), True, INK), (sx, sy))
    note = hint
    if not note and save_info is not None:
        note = f"Votre partie en cours ({save_info['name']}, an {save_info['year']}) sera mise de cote, pas effacee."
    if note:
        color = (236, 170, 90) if hint else NOTE
        screen.blit(r.tiny.render(_fit(r.tiny, note, lay["back"][0] - sx - 20), True, color), (sx, sy + 22))
    ready = bool(text.strip()) and len(picks) == tech.START_BONUS_PICKS
    _plain_button(r, lay["back"], "Retour", _hover(lay["back"], mx, my))
    _button(screen, head_font, lay["start"], "Commencer la partie", ready, ready and _hover(lay["start"], mx, my))


def random_name(rng, taken=()) -> str:
    from src.kora.peoples import CULTURES, make_name

    return make_name(rng, CULTURES["joueur"], taken)


def new_setup(rng) -> dict:
    return {"name": "Kora", "color": PALETTE[0], "bonuses": [], "typing": False}


def setup_click(setup: dict, hit: str, rng) -> str:
    """Un clic dans l'ecran de creation ; rend un message (vide si rien a dire)."""
    setup["typing"] = hit == "name"
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
            return f"Deja {tech.START_BONUS_PICKS} bonus : retirez-en un d'abord."
        else:
            picks.append(bid)
    return ""


def setup_key(setup: dict, event) -> None:
    """Frappe au clavier dans le nom du peuple."""
    if not setup.get("typing"):
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
        return "Donnez un nom a votre peuple."
    n = len(setup.get("bonuses", []))
    if n < tech.START_BONUS_PICKS:
        return f"Choisissez encore {tech.START_BONUS_PICKS - n} bonus de depart."
    return ""


def setup_for_game(setup: dict) -> dict:
    """Ce que sim.new_game(setup=...) recoit."""
    return {"name": setup["name"].strip(), "color": tuple(setup["color"]), "bonuses": list(setup["bonuses"])}


def setup_ready(setup: dict) -> bool:
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
    from src.kora.globe_draw import Planet

    planet = getattr(r, "_title_planet", None)
    if planet is None or planet.world is not world:
        planet = Planet(world)
        planet.fog[:] = 2
        planet.fog_gen += 1
        planet.zones_on = False
        r._title_planet = planet
        r._title_key = None
    return planet
