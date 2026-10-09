"""L'ecran des guerres (wars.py, render_wars.py), le rapport de force avant
l'attaque (orders.attack_preview) et les vivres des troupes en campagne
(ai_war.short_of_food, villages.warn_supply)."""

import os

os.environ.setdefault("SDL_VIDEODRIVER", "dummy")

import pygame

from src.kora import ai_war, chiefdom, diplo, orders, villages, wars
from src.kora.types import Band, Order, OrderKind
from src.kora.world import offset_to_axial
from test_war_goals import _three


def _war():
    """1 (le joueur) soumet 2, tributaire de 3 ; une troupe de chaque cote."""
    st = _three()
    chiefdom.make_vassal(st, 3, 2, "force")
    diplo.declare_war(st, 1, 2, 2)
    mine = villages.raise_army(st, 1, villages.LEVY_SHARE["troupe"])
    theirs = villages.raise_army(st, 3, villages.LEVY_SHARE["troupe"])
    return st, mine, theirs


def test_a_war_is_a_front_against_a_whole_country():
    st, mine, theirs = _war()
    fronts = wars.fronts(st, 1)
    assert len(fronts) == 1
    f = fronts[0]
    assert f.key == 3 and set(f.enemies) == {2, 3}
    assert f.my_side == [1] and set(f.their_side) == {2, 3}
    assert f.my_goals == [2] and f.target == 2 and f.declared_by == 1
    diplo.on_fight(st, 1, 2, True, True)
    assert wars.fronts(st, 1)[0].score == diplo.WIN_SCORE
    sides = {a.id: side for a, side, _doing in wars.fronts(st, 1)[0].armies}
    assert sides[mine.id] == "nous"
    # Leur troupe : seulement si on la voit (le brouillard).
    from src.kora.vision import is_visible
    assert (theirs.id in sides) == is_visible(st, theirs.position, 1)


def test_other_wars_of_the_world_are_listed_once_per_pair_of_countries():
    st = _three()
    diplo.declare_war(st, 2, 3)
    assert wars.others(st, 1) == [(2, 3, st.tick_count)]
    assert wars.fronts(st, 1) == []


def test_the_wars_screen_draws_and_answers_clicks(monkeypatch, tmp_path):
    from src.kora import app
    from test_app_clicks import _center, _click, _key, _play

    st, mine, theirs = _war()
    st.story = True
    seen = {}

    def need(cond, what):
        assert cond, what

    steps = [
        lambda r: [],
        lambda r: _key(pygame.K_w),
        lambda r: need(r.wars_hits, "W ouvre l'écran des guerres") or seen.update(buttons=set(r.wars_hits["buttons"])) or _click(_center(r.wars_hits["buttons"]["wact:treve:3"])),
        lambda r: [],
        lambda r: seen.update(truce=not diplo.declared_war(st, 1, 3) or diplo.on_cooldown(st, 1, 3, "treve") > 0) or _key(pygame.K_w),
        lambda r: need(not r.wars_hits, "W le referme") or [],
    ]
    _play(monkeypatch, tmp_path, st, steps)
    assert {"wpick:3", f"wsee:{mine.id}", "wact:soumission:2", "wact:treve:3", "wact:fiche:3"} <= seen["buttons"]
    assert seen["truce"], "la trêve est proposée (acceptée ou en attente)"


def test_hovering_a_foreigner_tells_the_odds_before_the_attack():
    st, mine, theirs = _war()
    prey = st.bands[3]
    p = orders.attack_preview(st, mine.id, prey.id)
    assert p["title"].startswith("Attaquer les") and not p["blocked"]
    ratio, word = ai_war.odds_at(st, mine, prey)
    assert p["ratio"] == ratio and word in p["rows"][0][0]
    labels = " ".join(t for t, _k in p["rows"])
    assert "Vos combattants" in labels and "Les leurs" in labels and "Moral" in labels and "Trajet" in labels
    # En paix avec un peuple qui a la diplomatie : il faut declarer la guerre.
    st2 = _three()
    army = villages.raise_army(st2, 1, villages.LEVY_SHARE["troupe"])
    p2 = orders.attack_preview(st2, army.id, st2.bands[2].id)
    assert "déclarez-leur d'abord la guerre" in p2["blocked"]
    assert orders.attack_preview(st2, army.id, army.id) is None


def test_an_ai_troop_does_not_chase_beyond_its_food():
    st, mine, theirs = _war()
    st.tribes[1].is_player = False
    # Une proie qui s'enfuit loin : la troupe de 3 la poursuit...
    far = Band(90, 1, offset_to_axial(58, 15), 30, 300.0)
    st.bands[90] = far
    theirs.position = offset_to_axial(40, 15)
    theirs.order = Order(OrderKind.MARCH_TO_BAND, target_band_id=far.id)
    theirs.stock = theirs.population * 30.0
    assert not ai_war.short_of_food(st, theirs, far.position)
    ai_war.recheck_hunts(st)
    # ... tant que ses vivres tiennent l'aller et le retour.
    theirs.stock = theirs.population * 3.0
    assert ai_war.short_of_food(st, theirs, far.position)
    ai_war.recheck_hunts(st)
    assert theirs.id not in st.bands or theirs.homebound or theirs.order.kind is not OrderKind.MARCH_TO_BAND


def test_the_player_is_warned_when_a_troop_runs_out_of_food_far_from_home():
    st, mine, theirs = _war()
    mine.position = offset_to_axial(40, 15)
    mine.stock = mine.population * 1.0
    villages.warn_supply(st)
    assert any("n'a plus que" in e.text for e in st.log.entries)
    n = len(st.log.entries)
    villages.warn_supply(st)
    assert len(st.log.entries) == n, "une fois par SUPPLY_WARN_EVERY semaines"
