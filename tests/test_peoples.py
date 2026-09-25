"""Peuples en donnees : cultures, noms, couleurs, petits peuples."""

import random

from src.kora import peoples
from src.kora.peoples import CULTURES, culture_of, color_of, make_name
from src.kora.sim import _default_world, can_split, new_game, split_band
from src.kora.types import Band, Terrain, Tribe
from src.kora.world import make_filled_world, offset_to_axial


def test_old_tribes_keep_their_culture_and_color():
    assert culture_of(Tribe(2, "Steppe", 20, False)).id == "steppe"
    assert culture_of(Tribe(4, "Cote", 20, False)).id == "cote"
    assert color_of(Tribe(1, "Joueur", 20, True)) == (220, 70, 70)
    assert culture_of(Tribe(9, "x", 20, False, culture="nord")).label == "peuple du grand froid"


def test_every_culture_knows_what_it_starts_with():
    from src.kora import tech

    for culture in CULTURES.values():
        for tid in culture.knowledge + culture.taste:
            assert tid in tech.TECHS, (culture.id, tid)


def test_names_are_unique_and_readable():
    rng = random.Random(3)
    taken = []
    for _ in range(40):
        name = make_name(rng, CULTURES["steppe"], taken)
        assert 3 <= len(name) <= 10 and name[0].isupper()
        assert name.lower() not in {t.lower() for t in taken}
        taken.append(name)


def test_new_game_names_the_peoples_and_adds_a_few_small_ones_far_apart():
    st = new_game(_default_world())
    assert st.tribes[1].name == "Kora"
    minors = [t for t in st.tribes.values() if t.minor]
    assert len(minors) == peoples.MINOR_START
    positions = [b.position for b in st.bands.values()]
    for i, a in enumerate(positions):
        for b in positions[i + 1:]:
            assert st.world.distance(a, b) >= 16
    for t in minors:
        band = next(b for b in st.bands.values() if b.tribe_id == t.id)
        assert band.population >= peoples.MINOR_POP[0]
        assert st.world.distance(band.position, st.bands[1].position) >= peoples.MINOR_SPACING
    colors = [color_of(t) for t in st.tribes.values()]
    assert len(set(colors)) == len(colors)


def test_small_maps_keep_four_peoples():
    st = new_game(make_filled_world(40, 24, Terrain.VALLEE, wrap_x=True))
    assert len(st.tribes) == 4


def test_a_small_people_keeps_at_most_four_bands():
    st = new_game(make_filled_world(60, 30, Terrain.VALLEE, wrap_x=True))
    st.tribes[9] = Tribe(9, "Petit", 10, False, culture="vallee", minor=True, knowledge={"feu", "outils"})
    st.bands[50] = Band(50, 9, offset_to_axial(30, 15), 400, 0.0)
    while can_split(st, max((b for b in st.bands.values() if b.tribe_id == 9), key=lambda b: b.population).id):
        split_band(st, max((b for b in st.bands.values() if b.tribe_id == 9), key=lambda b: b.population).id)
    assert sum(1 for b in st.bands.values() if b.tribe_id == 9) == 4


def test_culture_for_place_reads_biome_and_cold():
    world = make_filled_world(20, 40, Terrain.FORET)
    assert peoples.culture_for_place(world, offset_to_axial(5, 20)) == "foret"
    assert peoples.culture_for_place(world, offset_to_axial(5, 2)) == "nord"
