"""Les GRANDS ECRANS de l'interface : le village, le commerce, le tresor.

Un seul est ouvert a la fois. Chacun est decrit ICI (une ligne de SCREENS) :
  name      son nom (app.py y branche sa fonction de clic)
  key       la cle de ui qui dit s'il est ouvert (une valeur vraie : le lieu
            du village, True pour les autres)
  hits      l'attribut du renderer qui garde sa mise en page (avec "box")
  draw      'module.fonction' (renderer, state, ui) qui le dessine
  hit       (renderer, mx, my) -> ce que vise la souris ("panel" : le fond)
Ouvrir, fermer, savoir si la souris est dessus, dessiner : ici aussi.
app.py n'a plus qu'a appeler open / toggle / close_all et a router les clics
(un ecran nouveau : sa ligne ici, sa fonction de clic dans app.play).
Interface seulement : la partie ne change que par commands.py.
"""

from __future__ import annotations

import importlib
from dataclasses import dataclass


@dataclass(frozen=True)
class Screen:
    name: str
    key: str
    hits: str
    draw: str
    hit: object


def _village_hit(r, mx, my):
    from src.kora.render_village import village_hit

    return village_hit(r.village_hits, mx, my, r.village_armies)


def _trade_hit(r, mx, my):
    from src.kora.render_trade import trade_hit

    return trade_hit(r.trade_hits, mx, my, r.trade_partners, len(r.trade_routes), r.trade_candidates)


def _treasury_hit(r, mx, my):
    from src.kora.render_treasury import treasury_hit

    return treasury_hit(r.treasury_hits, mx, my)


SCREENS = (
    Screen("village", "village_open", "village_hits", "render_village.draw_village", _village_hit),
    Screen("commerce", "trade_open", "trade_hits", "render_trade.draw_trade", _trade_hit),
    Screen("tresor", "treasury_open", "treasury_hits", "render_treasury.draw_treasury", _treasury_hit),
)
BY_NAME = {s.name: s for s in SCREENS}
# Ferme : None pour le village (un lieu), False pour les autres.
_SHUT = {"village_open": None}


def is_open(ui, screen: Screen) -> bool:
    v = ui.get(screen.key)
    return v is not None and v is not False


def opened(ui):
    """Le grand ecran ouvert, ou None."""
    return next((s for s in SCREENS if is_open(ui, s)), None)


def close_all(ui) -> None:
    for s in SCREENS:
        ui[s.key] = _SHUT.get(s.key, False)


def open(ui, name: str, value=True) -> None:
    """Ouvre `name` (value : le lieu du village) ; les autres se ferment."""
    close_all(ui)
    ui[BY_NAME[name].key] = value


def toggle(ui, name: str) -> None:
    if is_open(ui, BY_NAME[name]):
        close_all(ui)
    else:
        open(ui, name)


def under_mouse(renderer, ui, mx: int, my: int) -> bool:
    """La souris est-elle sur le grand ecran ouvert ?"""
    s = opened(ui)
    if s is None:
        return False
    lay = getattr(renderer, s.hits, None)
    if not lay:
        return False
    x, y, w, h = lay["box"]
    return x <= mx <= x + w and y <= my <= y + h


def hit(renderer, ui, mx: int, my: int):
    """(ecran, ce que vise la souris) ; (None, None) s'il n'y en a pas."""
    s = opened(ui)
    if s is None or not getattr(renderer, s.hits, None):
        return None, None
    return s, s.hit(renderer, mx, my)


def draw(renderer, state, ui) -> None:
    """Dessine le grand ecran ouvert ; les autres oublient leur mise en page."""
    for s in SCREENS:
        if is_open(ui, s):
            mod, fn = s.draw.rsplit(".", 1)
            getattr(importlib.import_module(f"src.kora.{mod}"), fn)(renderer, state, ui)
        else:
            setattr(renderer, s.hits, {})
