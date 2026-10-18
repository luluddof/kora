"""Le conseil des peuples (render_peuples.py, 2026-10-18 : la maquette A
choisie par le joueur) : tout tient dans la fenetre a toutes les tailles,
la liste defile (molette, poignee glissee, rainure), les filtres trient, un
clic choisit un peuple - joue dans la vraie boucle."""

import copy

import pygame

from src.kora import diplo, render_peuples
from src.kora.layout import (
    PEOPLE_FILTERS,
    clamp_people_top,
    panel_box,
    people_rows,
    people_thumb,
    people_top_at,
    peoples_layout,
)
from test_app_clicks import _center, _click, _key, _play
from test_war_goals import _three


def _inside(inner, outer):
    x, y, w, h = inner
    X, Y, W, H = outer
    return X <= x and Y <= y and x + w <= X + W and y + h <= Y + H


def test_the_council_fits_every_window():
    for w, h in ((1280, 720), (1600, 900), (1920, 1080)):
        lay = peoples_layout(panel_box(w, h, "peuples", 66))
        box = lay["box"]
        assert box[0] + box[2] <= w - 66, "le rail des onglets reste libre"
        for rect in [lay["list"], lay["track"], lay["head"], lay["know"], *lay["cards"], *lay["cols"], *lay["filters"].values()]:
            assert _inside(rect, box), (w, h, rect)
        assert lay["visible"] >= 9
        assert min(c[3] for c in lay["cols"]) >= 240, "quatre familles d'actions lisibles"


def test_the_list_scrolls_and_its_thumb_follows():
    lay = peoples_layout(panel_box(1280, 720, "peuples", 66))
    n, v = 30, lay["visible"]
    assert len(people_rows(lay, n, 0)) == v
    assert clamp_people_top(lay, n, 99) == n - v and clamp_people_top(lay, n, -5) == 0
    assert people_thumb(lay, v, 0) is None, "tout tient : pas de barre"
    track = lay["track"]
    for top in (0, 7, n - v):
        thumb = people_thumb(lay, n, top)
        assert track[1] <= thumb[1] and thumb[1] + thumb[3] <= track[1] + track[3]
        assert people_top_at(lay, n, thumb[1]) == top, "la poignée tirée là où elle est ne bouge rien"
    assert people_top_at(lay, n, track[1] - 50) == 0 and people_top_at(lay, n, track[1] + 9999) == n - v


def _many():
    """Le peuple 1 et dix-sept peuples connus (plus que la liste n'en montre)."""
    st = _three()
    base_t, base_b = st.tribes[2], next(b for b in st.bands.values() if b.tribe_id == 2)
    for i in range(15):
        tid = 100 + i
        t = copy.deepcopy(base_t)
        t.id, t.name, t.is_player = tid, f"Peuple{i:02d}", False
        st.tribes[tid] = t
        b = copy.deepcopy(base_b)
        b.id, b.tribe_id, b.village = 5000 + i, tid, 0
        st.bands[b.id] = b
        diplo.make_contact(st, 1, tid, quiet=True)
        diplo.add_mod(st, 1, tid, "cadeau", 20 if i < 3 else -20 if i < 5 else 0, actor=1)
    return st


def test_filters_sort_the_peoples():
    st = _many()
    st.viewer = 1
    known = render_peuples.known_peoples(st)
    counts = {key: sum(1 for t in known if render_peuples.in_filter(st, t, key)) for key, _l in PEOPLE_FILTERS}
    assert counts["tous"] == len(known) == 17
    assert counts["cordiaux"] >= 3 and counts["hostiles"] >= 2 and counts["guerre"] == 0
    assert counts["cordiaux"] + counts["mefiants"] + counts["hostiles"] == counts["tous"]


def test_the_council_scrolls_filters_and_picks_in_the_real_loop(monkeypatch, tmp_path):
    st = _many()
    seen = {}

    def need(cond, what):
        assert cond, what

    def rows(r):
        return sorted((rect[1], int(k.split(":")[1])) for k, rect in r.side_hits["items"].items() if k.startswith("people:"))

    def wheel_over(r):
        lx, ly, lw, lh = r.people_list
        return [pygame.event.Event(pygame.MOUSEMOTION, pos=(lx + 20, ly + 20), rel=(0, 0), buttons=(0, 0, 0)),
                pygame.event.Event(pygame.MOUSEWHEEL, x=0, y=-1, flipped=False, precise_x=0.0, precise_y=-1.0)]

    def press_thumb(r):
        x, y, w, h = r.side_hits["items"]["pthumb"]
        seen["at"] = (x + w // 2, y + h // 2)
        return [pygame.event.Event(pygame.MOUSEBUTTONDOWN, pos=seen["at"], button=1)]

    def drag_down(r):
        at = (seen["at"][0], seen["at"][1] + 400)
        return [pygame.event.Event(pygame.MOUSEMOTION, pos=at, rel=(0, 400), buttons=(1, 0, 0))]

    def release(r):
        return [pygame.event.Event(pygame.MOUSEBUTTONUP, pos=(seen["at"][0], seen["at"][1] + 400), button=1)]

    steps = [
        lambda r: [],
        lambda r: _key(pygame.K_p),
        lambda r: need(r.side_hits.get("panel") == "peuples", "P ouvre le conseil") or seen.update(first=rows(r)[0][1]) or wheel_over(r),
        lambda r: need(rows(r)[0][1] != seen["first"], "la molette fait défiler la liste") or need("pthumb" in r.side_hits["items"], "la barre") or [],
        lambda r: press_thumb(r),
        lambda r: drag_down(r),
        lambda r: release(r),
        lambda r: seen.update(bottom=[t for _y, t in rows(r)]) or [],
        lambda r: _click(_center(r.side_hits["items"]["pfilter:hostiles"])),
        lambda r: need(len(rows(r)) == 2, ("deux hostiles", rows(r))) or _click(_center(r.side_hits["items"][f"people:{rows(r)[1][1]}"])),
        lambda r: seen.update(picked=rows(r)[1][1]) or need(any(k.startswith("diplo:") for k in r.side_hits["items"]), "les actions du peuple choisi") or [],
        lambda r: _click(_center(r.side_hits["items"]["pfilter:tous"])),
        lambda r: need(len(rows(r)) >= 9, "tous revient") or [],
    ]
    _play(monkeypatch, tmp_path, st, steps)
    known = render_peuples.known_peoples(st)
    assert seen["bottom"][-1] == known[-1], "la poignée tirée en bas montre le dernier peuple"
    assert seen["picked"] in known and render_peuples.in_filter(st, seen["picked"], "hostiles")
