"""Evenements en chaines : bien formes, choisis, suivis (ou pas)."""

import random

from src.kora import chiefs, events, tech
from src.kora.clock import Clock
from src.kora.events import EVENTS, Follow
from src.kora.persist import load_game, save_game
from src.kora.sim import GameState, new_game
from src.kora.types import Band, Terrain, Tribe
from src.kora.world import make_filled_world, offset_to_axial

EFFECTS = set(events.EFFECT_TEXT) | {"trait", "chief_trait", "flag", "unflag"}
CONDS = {
    "chance", "knows", "not_knows", "flag", "no_flag", "prestige_ge", "prestige_lt", "week_between",
    "bands_ge", "can_split", "other_alive", "other_teaches", "has_rival", "chief_trait", "learning",
    "season", "terrain", "stock_lt", "stock_ge", "pop_ge", "pop_lt", "winter_long", "chief_band",
    "not_chief_band", "at_camp", "crowded", "leader_trait", "leader_not_trait", "loyalty_lt",
    "near_chief", "chief_stronger", "site_alive", "is_rival", "village", "not_village", "foreign_near",
    "crafts", "no_trade", "trade_partner",
}


def _state(player=True):
    world = make_filled_world(60, 30, Terrain.FORET, wrap_x=True)
    tribe = Tribe(1, "Kora", 30, player, knowledge=set(tech.START_KNOWLEDGE), culture="joueur")
    other = Tribe(2, "Tavek", 30, False, knowledge=set(tech.START_KNOWLEDGE) | {"epieu"}, culture="vallee")
    band = Band(1, 1, offset_to_axial(20, 15), 40, 120.0)
    them = Band(2, 2, offset_to_axial(40, 15), 40, 120.0)
    st = GameState(world=world, clock=Clock(), tribes={1: tribe, 2: other}, bands={1: band, 2: them}, story=True)
    world.fill_season(st.clock.season())
    chiefs.ensure(st)
    return st, band


def _all_follows(ev):
    for opt in ev.options:
        yield from opt.follow
        for o in opt.outcomes:
            yield from o.follow


def test_every_event_is_well_formed():
    assert len(EVENTS) >= 30
    for ev in EVENTS.values():
        assert ev.title and ev.text
        assert ev.options or ev.special, ev.id
        for c in ev.conds:
            assert c[0] in CONDS, (ev.id, c)
        for opt in ev.options:
            assert opt.label
            for e in opt.effects:
                assert e[0] in EFFECTS, (ev.id, e)
            for o in opt.outcomes:
                for e in o.effects:
                    assert e[0] in EFFECTS, (ev.id, e)
                for cond, _delta in o.mods:
                    assert cond[0] in CONDS, (ev.id, cond)
        for f in _all_follows(ev):
            assert f.event in EVENTS, (ev.id, f.event)
            assert 0 < f.prob <= 1


def test_follow_ups_are_reachable_and_pulses_have_a_weight():
    followed = {f.event for ev in EVENTS.values() for f in _all_follows(ev)}
    # Programmee par le code de la succession (un ambitieux ecarte).
    followed.add("succession_contestee")
    for ev in EVENTS.values():
        if ev.trigger == "follow":
            assert ev.id in followed, ev.id
        if ev.trigger == "pulse":
            assert ev.weight > 0, ev.id


def test_the_player_gets_a_card_and_chooses():
    st, band = _state()
    inst = events._new_instance(st, EVENTS["visiteurs"], 1, band.id)
    assert events.fire(st, inst)
    assert len(events.pending(st)) == 1
    opts = events.options_for(st, inst)
    assert opts[0]["summary"].startswith("+4 a 7 personnes")
    events.choose(st, inst.uid, 0)
    assert not events.pending(st)
    assert band.population > 40


def test_an_unanswered_card_is_decided_by_default_at_the_deadline():
    st, band = _state()
    inst = events._new_instance(st, EVENTS["visiteurs"], 1, band.id)
    events.fire(st, inst)
    st.tick_count = inst.deadline
    events.weekly(st)
    assert not events.pending(st)
    assert any("Decide d'office" in e.text for e in st.log.entries)


def test_the_ai_decides_at_once():
    st, _band = _state()
    them = st.bands[2]
    inst = events._new_instance(st, EVENTS["visiteurs"], 2, them.id)
    assert not events.fire(st, inst)
    assert not events.pending(st)


def test_a_follow_up_is_never_certain_and_is_checked_when_it_comes():
    st, band = _state()
    inst = events._new_instance(st, EVENTS["loups"], 1, band.id)
    hits = 0
    st.story_rng = random.Random(4)
    for _ in range(200):
        before = len(events._book(st).scheduled)
        events._schedule(st, Follow("louveteaux", 1.0, (1, 1)), inst) if st.story_rng.random() < 0.35 else None
        hits += len(events._book(st).scheduled) - before
    assert 40 < hits < 110
    # Une suite dont la condition ne tient plus n'arrive pas.
    st.tribes[1].flags["louveteaux"] = -1
    st.tick_count += 2
    events.weekly(st)
    assert not events.pending(st)


def test_the_wolves_can_give_dogs():
    st, band = _state()
    inst = events._new_instance(st, EVENTS["louveteaux"], 1, band.id)
    events.fire(st, inst)
    events.choose(st, inst.uid, 0)
    assert "louveteaux" in st.tribes[1].flags
    st.tribes[1].knowledge.add("epieu")
    assert tech.status(st, 1, "chiens") == "disponible"


def test_outcome_chances_follow_knowledge():
    st, band = _state()
    inst = events._new_instance(st, EVENTS["loups"], 1, band.id)
    plain = events.options_for(st, inst)[0]["summary"]
    st.tribes[1].knowledge.update(("epieu", "arc"))
    wise = events.options_for(st, inst)[0]["summary"]
    assert plain != wise
    assert int(wise.split(" %")[0]) > int(plain.split(" %")[0])


def test_succession_offers_the_candidates():
    st, band = _state()
    st.bands[3] = Band(3, 1, offset_to_axial(22, 15), 30, 90.0)
    chiefs.ensure(st)
    heart = chiefs.chief_band(st, 1)
    chiefs.leader_dies(st, heart, "de vieillesse")
    cards = events.pending(st)
    assert cards and cards[0].event_id == "succession"
    opts = events.options_for(st, cards[0])
    assert len(opts) >= 2
    events.choose(st, cards[0].uid, 1)
    assert chiefs.chief_band(st, 1).id == opts[1]["band"]


def test_pending_cards_are_saved(tmp_path):
    world = make_filled_world(40, 20, Terrain.FORET, wrap_x=True)
    st = new_game(world)
    inst = events._new_instance(st, EVENTS["visiteurs"], 1, 1)
    events.fire(st, inst)
    path = tmp_path / "kora.json"
    save_game(st, path, {})
    loaded, _ = load_game(path, world)
    assert [p.event_id for p in events.pending(loaded)] == ["visiteurs"]
    assert loaded.story
