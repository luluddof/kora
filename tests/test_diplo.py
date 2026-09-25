"""Diplomatie : relations lisibles, pactes, propositions, diffusion."""

from src.kora import chiefs, diplo, tech
from src.kora.clock import Clock
from src.kora.persist import load_game, save_game
from src.kora.sim import GameState, new_game, resolve_raids, set_march_to_band, side_force
from src.kora.types import Band, Terrain, Tribe
from src.kora.world import make_filled_world, offset_to_axial


def _state(known=(), other_known=()):
    world = make_filled_world(80, 30, Terrain.PLAINE, wrap_x=True)
    me = Tribe(1, "Kora", 30, True, knowledge=set(tech.START_KNOWLEDGE) | set(known), culture="joueur")
    them = Tribe(2, "Tavek", 30, False, knowledge=set(tech.START_KNOWLEDGE) | set(other_known), culture="vallee")
    a = Band(1, 1, offset_to_axial(20, 15), 40, 200.0)
    b = Band(2, 2, offset_to_axial(30, 15), 40, 200.0)
    st = GameState(world=world, clock=Clock(), tribes={1: me, 2: them}, bands={1: a, 2: b}, next_band_id=3)
    world.fill_season(st.clock.season())
    chiefs.ensure(st)
    return st, a, b


def test_peoples_meet_when_their_bands_come_close():
    st, a, b = _state()
    assert not diplo.in_contact(st, 1, 2)
    diplo.update_contacts(st)
    assert diplo.in_contact(st, 1, 2)
    assert any("Premier contact" in e.text for e in st.log.entries)


def test_a_raid_sours_the_relation_and_says_why():
    st, a, b = _state()
    diplo.make_contact(st, 1, 2)
    diplo.on_fight(st, 1, 2, True, hunted=True)
    assert diplo.relation(st, 1, 2) <= -20
    mine = [label for label, _v in diplo.reasons(st, 1, 2)]
    theirs = [label for label, _v in diplo.reasons(st, 2, 1)]
    assert "Vous les avez attaques" in mine and "Ils vous ont attaques" in theirs
    for _ in range(40):
        diplo.monthly(st)
    assert diplo.relation(st, 1, 2) > -10


def test_a_truce_lets_bands_share_a_hex_but_an_attack_breaks_it():
    st, a, b = _state()
    diplo.make_contact(st, 1, 2)
    diplo.add_pact(st, 1, 2, "treve", diplo.TRUCE_WEEKS)
    b.position = a.position
    resolve_raids(st)
    assert a.population == 40 and b.population == 40
    set_march_to_band(st, 1, 2)
    prestige = st.tribes[1].prestige
    resolve_raids(st)
    assert not diplo.has_pact(st, 1, 2)
    assert st.tribes[1].prestige < prestige + 5
    assert any("trahis" in label for label, _v in diplo.reasons(st, 1, 2))


def test_the_panel_can_show_why_they_would_accept_before_asking():
    st, a, b = _state(known=("palabres",))
    diplo.make_contact(st, 1, 2)
    v = diplo.evaluate(st, 1, 2, "treve")
    assert v.reasons and ("Dons et palabres", 10) in v.reasons
    assert diplo.evaluate(st, 1, 2, "alliance").blocked.startswith("Il faut")
    assert diplo.evaluate(st, 1, 2, "union").blocked


def test_a_gift_is_carried_by_the_nearest_band_and_warms_the_relation():
    st, a, b = _state()
    diplo.make_contact(st, 1, 2)
    before = diplo.relation(st, 1, 2)
    # La bande qui porte garde toujours 2 semaines de vivres.
    assert diplo.gift_sizes(st, 1, 2) == [50]
    text = diplo.perform(st, 1, 2, "cadeau", 50)
    assert "acceptent" in text
    assert a.stock == 150.0 and b.stock > 200.0
    assert diplo.relation(st, 1, 2) > before


def test_allies_come_to_help():
    st, a, b = _state()
    b.position = offset_to_axial(21, 15)
    alone = side_force(st, a)
    diplo.make_contact(st, 1, 2)
    diplo.add_pact(st, 1, 2, "alliance")
    assert side_force(st, a) > alone * 1.5


def test_tribute_is_paid_every_season():
    st, a, b = _state()
    diplo.make_contact(st, 1, 2)
    diplo.add_pact(st, 1, 2, "tribut", diplo.TRIBUTE_WEEKS, payer=2)
    before = a.stock
    st.tick_count = diplo.TRIBUTE_EVERY + 1
    diplo.monthly(st)
    assert a.stock > before


def test_neighbours_teach_what_they_know():
    st, a, b = _state(other_known=("epieu",))
    diplo.make_contact(st, 1, 2)
    diplo.monthly(st)
    assert diplo.teachers(st, 1, "epieu") == [2]
    assert diplo.diffusion_bonus(st, 1, "epieu") > 0
    assert tech.learn_rate(st, 1, "epieu") > tech.learn_rate(st, 1)
    # Semaines vecues divisees par deux : 3 semaines de plaine suffisent.
    st.tribes[1].practice["plaine"] = 3
    assert tech.status(st, 1, "epieu") == "disponible"


def test_a_disloyal_clan_nearby_can_be_invited():
    import random

    from src.kora.vision import recompute_vision

    st, a, b = _state()
    st.tribes[1].prestige = 60
    # Le peuple 2 a un deuxieme clan, indocile, tout pres de chez vous.
    stray = Band(3, 2, offset_to_axial(22, 15), 30, 100.0)
    st.bands[3] = stray
    chiefs.ensure(st)
    stray.loyalty = 10.0
    diplo.make_contact(st, 1, 2)
    recompute_vision(st)
    assert diplo.invitable(st, 1, 2) == [stray]
    assert diplo.invite_chance(st, 1, stray) > 0.8
    st.story_rng = random.Random(1)
    text = diplo.invite(st, 1, 3)
    assert "rejoint" in text and stray.tribe_id == 1
    assert st.tribes[1].prestige == 60 - diplo.INVITE_COST
    assert any("pris" in label for label, _v in diplo.reasons(st, 2, 1))


def test_relations_and_pacts_are_saved(tmp_path):
    world = make_filled_world(40, 20, Terrain.PLAINE, wrap_x=True)
    st = new_game(world)
    diplo.make_contact(st, 1, 2)
    diplo.add_pact(st, 1, 2, "treve", 50)
    diplo.add_mod(st, 1, 2, "cadeau", 12, actor=1)
    path = tmp_path / "kora.json"
    save_game(st, path, {})
    loaded, _ = load_game(path, world)
    assert diplo.has_pact(loaded, 1, 2, "treve")
    assert round(diplo.relation(loaded, 1, 2)) == round(diplo.relation(st, 1, 2))
