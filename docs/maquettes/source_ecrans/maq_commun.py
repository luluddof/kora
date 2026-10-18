"""Socle des maquettes : sa partie (copie), la carte du jeu dessous, voilee,
et quelques petites briques de dessin dans la charte (theme.py)."""
import json
import os
import sys

os.environ["SDL_VIDEODRIVER"] = "dummy"
os.environ["SDL_AUDIODRIVER"] = "dummy"
ROOT = sys.argv[1]
sys.path.insert(0, ROOT)
from pathlib import Path  # noqa: E402

import pygame  # noqa: E402

from src.kora import app, partie, persist, planets, theme  # noqa: E402
from src.kora.render import Renderer  # noqa: E402
from src.kora.theme import C  # noqa: E402

W, H = 1600, 900


def load(save, outdir):
    pygame.init()
    r = Renderer(pygame.display.set_mode((W, H)))
    path = Path(save)
    st, view = persist.load_game(path, planets.load(json.loads(path.read_text(encoding="utf-8")).get("planet", "aurane")))
    boot = app._start_view(st, view.get("selected"), W, H)
    play = partie.Play(r, pygame.time.Clock(), boot, save_path=os.path.join(outdir, "x.json"))
    play.sw, play.sh = W, H
    pygame.event.get = lambda *a, **k: []
    pygame.mouse.get_pos = lambda: (3, 3)
    return st, play, r


def backdrop(play, r, side=None):
    """Une image du jeu (carte, bandeau, rail), le panneau `side` ouvert ou non."""
    play.side_panel = side
    for _ in range(2):
        play._frame(1 / 60)
    return r.screen


def veil(surf, alpha=150):
    theme.veil(surf, alpha)


def tag(surf, text, x=24, y=H - 30):
    """L'etiquette de la maquette (en bas a gauche)."""
    f = theme.font("mini_gras")
    w = f.size(text)[0] + 20
    theme.panel(surf, (x, y, w, 24), "infobulle")
    surf.blit(f.render(text, True, C.braise), (x + 10, y + 3))


def pill(surf, x, y, text, color, role="mini_gras", fill_alpha=0.22, right=False):
    """Une pastille de verdict (chamfer), alignee a droite si right."""
    f = theme.font(role)
    w = f.size(text)[0] + 14
    h = f.get_height() + 4
    if right:
        x -= w
    poly = theme.chamfer((x, y, w, h), 3)
    pygame.draw.polygon(surf, theme._mix(C.charbon, color, fill_alpha), poly)
    pygame.draw.polygon(surf, color, poly, 1)
    surf.blit(f.render(text, True, theme._mix(color, C.os, 0.35)), (x + 7, y + 2))
    return w


def lock(surf, x, y, color=C.cendre):
    pygame.draw.rect(surf, color, (x - 4, y - 1, 9, 7), border_radius=1)
    pygame.draw.arc(surf, color, (x - 3, y - 6, 7, 9), 0, 3.15, 2)


def check(surf, x, y, color=C.ocre_jaune):
    pygame.draw.lines(surf, color, False, [(x - 5, y), (x - 1, y + 4), (x + 6, y - 4)], 2)


def dots(surf, a, b, color=C.ocre, gap=6):
    theme.dotted(surf, a, b, color, gap)


def section(surf, x, y, w, label, color=C.ocre_jaune):
    """Une etiquette en petites capitales et ses pointilles."""
    f = theme.font("etiquette")
    surf.blit(f.render(label, True, color), (x, y))
    lw = f.size(label)[0]
    theme.dotted(surf, (x + lw + 8, y + 9), (x + w, y + 9), C.ocre_sombre, 6)
    return y + 22


def signed(v):
    return f"{v:+.0f}" if v else "0"


def rel_color(v):
    if v >= 30:
        return C.bon
    if v >= 10:
        return theme._mix(C.bon, C.lin, 0.4)
    if v > -10:
        return C.lin
    if v > -30:
        return C.alerte
    return C.mauvais


def meter(surf, x, y, w, rel, h=8):
    """La relation de -100 a +100 : rainure en trois teintes, curseur os."""
    for i in range(w):
        v = -100 + 200 * i / max(1, w - 1)
        c = rel_color(v)
        pygame.draw.line(surf, theme._mix(C.nuit, c, 0.55), (x + i, y), (x + i, y + h))
    pygame.draw.rect(surf, C.bois, (x - 1, y - 1, w + 2, h + 2), 1)
    mid = x + w // 2
    pygame.draw.line(surf, C.cendre, (mid, y - 3), (mid, y + h + 2))
    px = x + int(w * (rel + 100) / 200)
    pygame.draw.polygon(surf, C.os, [(px, y + h // 2 - 1), (px - 5, y - 7), (px + 5, y - 7)])
    pygame.draw.polygon(surf, C.nuit, [(px, y + h // 2 - 1), (px - 5, y - 7), (px + 5, y - 7)], 1)


def save(surf, path):
    pygame.image.save(surf, path)
    print("maquette :", path)


def token(surf, name, color, cx, cy, radius, chosen=False):
    """Le jeton d'un peuple : un disque a la couleur de son pays, son
    initiale en petites capitales (les tetes de totem, petites, faisaient
    des cranes)."""
    cx, cy = int(cx), int(cy)
    if chosen:
        theme.glow(surf, (cx - radius - 10, cy - radius - 10, 2 * radius + 20, 2 * radius + 20), C.braise, 0.9)
    pygame.draw.circle(surf, (0, 0, 0), (cx, cy + 2), radius + 1)
    pygame.draw.circle(surf, theme._mix(C.nuit, color, 0.5), (cx, cy), radius)
    pygame.draw.circle(surf, theme._mix(C.nuit, color, 0.62), (cx, cy - radius // 5), int(radius * 0.7))
    pygame.draw.circle(surf, theme._mix(C.nuit, color, 0.5), (cx, cy + radius // 6), int(radius * 0.68))
    pygame.draw.circle(surf, C.braise if chosen else color, (cx, cy), radius, 3 if chosen else 2)
    pygame.draw.circle(surf, C.nuit, (cx, cy), radius - 3, 1)
    f = theme.font_file("sc-bold", max(12, int(radius * 1.15)))
    letter = name[:1].upper()
    img = f.render(letter, True, C.os)
    sh = f.render(letter, True, C.nuit)
    surf.blit(sh, (cx - img.get_width() // 2 + 1, cy - img.get_height() // 2 + 1))
    surf.blit(img, (cx - img.get_width() // 2, cy - img.get_height() // 2))
