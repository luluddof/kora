"""Plusieurs peuples joueurs dans une meme partie (multijoueur, phase B) :
chacun sa vue, son journal, ses cartes ; l'IA ne les mene pas ; ils se
proposent des pactes en cartes d'evenement ; la sauvegarde garde tout."""

import random

from src.kora import diplo, events, tech
from src.kora.persist import dumps_game, loads_game
from src.kora.sim import new_game, tick
from src.kora.bands import split_band
from src.kora.gamestate import PLAYER_TRIBE_ID, human_dead, humans, is_human, log_of, seen_of
from src.kora.types import Terrain
from src.kora.vision import is_explored, is_visible, vision_of
from src.kora.world import make_filled_world


def _world():
    return make_filled_world(60, 30, Terrain.PLAINE, wrap_x=True)


def _mp(**kw):
    others = {2: {"name": "Tahu", "color": (60, 190, 190), "bonuses": ["bonus:froid", "bonus:guerriers"]}, 4: {"name": "Mira"}}
    return new_game(_world(), setup={"name": "Aroha", "bonuses": ["bonus:conteurs", "bonus:fertiles"]}, others=others, **kw)


def test_seats_become_players_with_their_setup():
    st = _mp()
    assert humans(st) == [1, 2, 4]
    assert is_human(st, 2) and is_human(st, 4) and not is_human(st, 3)
    assert st.tribes[1].name == "Aroha"
    assert st.tribes[2].name == "Tahu" and st.tribes[2].color == (60, 190, 190)
    assert st.tribes[2].start_bonuses == ["bonus:froid", "bonus:guerriers"]
    assert st.tribes[4].name == "Mira" and st.tribes[4].start_bonuses == []
    # La steppe garde son savoir de pays, comme l'IA qui y serait nee.
    assert "troupeau" in st.tribes[2].knowledge
    plain = new_game(_world(), others={2: {}})
    assert abs(tech.bonuses(st.tribes[2]).combat - 1.2 * tech.bonuses(plain.tribes[2]).combat) < 1e-9


def test_each_player_has_its_own_vision():
    st = _mp()
    v1, v2 = vision_of(st, 1), vision_of(st, 2)
    assert v1 is not None and v2 is not None and v1 is not v2
    home2 = next(b.position for b in st.bands.values() if b.tribe_id == 2)
    assert is_visible(st, home2, 2)
    assert is_explored(st, home2, 2)
    # Les foyers sont loin : l'un ne voit pas chez l'autre.
    home1 = next(b.position for b in st.bands.values() if b.tribe_id == 1)
    if st.world.distance(home1, home2) > 20:
        assert not is_visible(st, home2, 1)
        assert not is_visible(st, home1, 2)


def test_messages_go_to_the_right_journal():
    st = _mp()
    band2 = next(b for b in st.bands.values() if b.tribe_id == 2)
    before1, before2 = len(st.log.entries), len(log_of(st, 2).entries)
    assert split_band(st, band2.id) is not None
    assert len(log_of(st, 2).entries) == before2 + 1
    assert "scinde" in log_of(st, 2).entries[-1].text
    assert len(st.log.entries) == before1


def test_ai_leaves_player_bands_alone():
    st = _mp()
    st.rng = random.Random(3)
    band4 = next(b for b in st.bands.values() if b.tribe_id == 4)
    start = band4.position
    for _ in range(8):
        tick(st)
        st.clock.paused = False
        assert st.last_error is None, st.last_error
    assert band4.position == start, "personne n'a donne d'ordre : la bande du joueur reste"


def test_multiplayer_game_runs_and_is_deterministic():
    runs = []
    for _ in range(2):
        st = _mp()
        st.rng = random.Random(9)
        for _ in range(52):
            tick(st)
            st.clock.paused = False
            assert st.last_error is None, st.last_error
        runs.append(dumps_game(st))
    assert runs[0] == runs[1]


def test_pending_cards_are_per_player():
    st = _mp()
    band2 = next(b for b in st.bands.values() if b.tribe_id == 2)
    assert events.hook(st, "offre_treve", tribe_id=2, band_id=band2.id, other=3)
    assert [p.tribe_id for p in events.pending(st, 2)] == [2]
    assert events.pending(st, 1) == [] and events.pending(st) == []


def test_a_player_decides_the_offer_of_another_player():
    st = _mp()
    diplo.make_contact(st, 1, 2)
    msg = diplo.perform(st, 1, 2, "treve")
    assert "décider" in msg, msg
    cards = [c for c in events.pending(st, 2) if c.event_id == "offre_treve"]
    assert len(cards) == 1 and cards[0].other == 1
    assert not diplo.at_peace(st, 1, 2)
    events.choose(st, cards[0].uid, 0)
    assert diplo.has_pact(st, 1, 2, "treve")
    assert any("ont répondu" in e.text for e in st.log.entries)
    assert diplo.on_cooldown(st, 1, 2, "treve")


def test_gifts_and_broken_pacts_are_told_to_the_other_player():
    st = _mp()
    diplo.make_contact(st, 1, 2)
    b1 = next(b for b in st.bands.values() if b.tribe_id == 1)
    b2 = next(b for b in st.bands.values() if b.tribe_id == 2)
    b1.position = b2.position
    b1.stock = 400.0
    diplo.perform(st, 1, 2, "cadeau", 50)
    assert any("vous offrent 50 vivres" in e.text for e in log_of(st, 2).entries)
    diplo.add_pact(st, 1, 2, "treve", 50)
    diplo.perform(st, 1, 2, "rompre")
    assert any("rompent leur pacte" in e.text for e in log_of(st, 2).entries)


def test_first_contact_between_two_players_is_told_to_both():
    st = _mp()
    diplo.make_contact(st, 2, 4)
    assert any("Premier contact" in e.text for e in log_of(st, 2).entries)
    assert any("Premier contact" in e.text for e in log_of(st, 4).entries)
    assert not any("Premier contact avec les Mira" in e.text for e in st.log.entries)


def test_each_player_spots_peoples_for_itself():
    st = _mp()
    for _ in range(4):
        tick(st)
        st.clock.paused = False
    assert seen_of(st, 2) is not seen_of(st, 1)


def test_save_keeps_every_player(tmp_path):
    st = _mp()
    band2 = next(b for b in st.bands.values() if b.tribe_id == 2)
    split_band(st, band2.id)
    for _ in range(3):
        tick(st)
        st.clock.paused = False
    text = dumps_game(st)
    loaded, _view = loads_game(text, _world())
    assert humans(loaded) == [1, 2, 4]
    assert [e.text for e in log_of(loaded, 2).entries] == [e.text for e in log_of(st, 2).entries]
    assert vision_of(loaded, 2).explored == vision_of(st, 2).explored
    assert seen_of(loaded, 4) == seen_of(st, 4)
    assert loaded.tribes[2].start_bonuses == ["bonus:froid", "bonus:guerriers"]
    # La copie rechargee est la meme partie (les ensembles mis dans l'ordre).
    def norm(t):
        import json

        data = json.loads(t)
        data["explored"] = sorted(data["explored"])
        for _tid, pov in data["povs"]:
            pov["explored"] = sorted(pov["explored"])
        return data

    assert norm(dumps_game(loaded)) == norm(text)


def test_dead_player_is_seen_as_such():
    st = _mp()
    for b in list(st.bands.values()):
        if b.tribe_id == 4:
            b.population = 0
    tick(st)
    assert human_dead(st, 4)
    assert not human_dead(st, 2)
    assert not st.player_dead


def test_viewer_changes_only_the_screen():
    st = _mp()
    from src.kora.sim import hex_inspect

    home2 = next(b.position for b in st.bands.values() if b.tribe_id == 2)
    st.viewer = 2
    info = hex_inspect(st, home2)
    assert info is not None and info["band"]["ally"]
    st.viewer = PLAYER_TRIBE_ID
    if hex_inspect(st, home2) is not None:
        assert not hex_inspect(st, home2)["band"] or not hex_inspect(st, home2)["band"]["ally"]
