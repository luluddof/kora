from src.kora.clock import Clock
from src.kora.sim import GameState, hex_inspect, inspect_lines
from src.kora.types import Band, Season, Terrain, Tribe
from src.kora.vision import recompute_vision
from src.kora.world import make_filled_world, offset_to_axial


def _state():
    world = make_filled_world(80, 40, Terrain.PLAINE, wrap_x=True)
    pos = offset_to_axial(8, 8)
    far = offset_to_axial(50, 30)
    band = Band(id=1, tribe_id=1, position=pos, population=40, stock=160)
    st = GameState(
        world=world,
        clock=Clock(),
        tribes={1: Tribe(1, "Joueur", 20, True)},
        bands={1: band},
    )
    world.fill_season(st.clock.season())
    recompute_vision(st)
    return st, pos, far


def test_inspect_unexplored_is_none():
    st, _pos, far = _state()
    assert far not in st.vision.explored
    assert hex_inspect(st, far) is None


def test_inspect_explored_out_of_sight_has_biome_not_food():
    st, _pos, far = _state()
    st.vision.explored.add(far)
    st.vision.visible.discard(far)
    info = hex_inspect(st, far)
    assert info is not None
    assert info["terrain_fr"] == "Plaine"
    assert info["season_fr"] == "Printemps"
    assert info["visible"] is False
    assert info["food"] is None
    assert info["band"] is None


def test_inspect_visible_has_food_and_band():
    st, pos, _far = _state()
    info = hex_inspect(st, pos)
    assert info is not None
    assert info["visible"] is True
    assert info["food"] is not None
    assert info["food"] > 0
    assert info["band"]["ally"] is True
    assert info["band"]["population"] == 40


def _steppe_state(troupeau: bool, season: Season = Season.PRINTEMPS):
    world = make_filled_world(80, 40, Terrain.STEPPE, wrap_x=True)
    pos = offset_to_axial(8, 8)
    far = offset_to_axial(50, 30)
    band = Band(id=1, tribe_id=1, position=pos, population=40, stock=160)
    st = GameState(
        world=world,
        clock=Clock(),
        tribes={1: Tribe(1, "Joueur", 20, True, troupeau=troupeau)},
        bands={1: band},
    )
    world.fill_season(season)
    recompute_vision(st)
    return st, pos, far


def _no_plain_compare(lines: list[str]) -> None:
    assert not any(line.startswith("Hiver") for line in lines)
    assert not any("plaine" in line.lower() for line in lines)


def test_inspect_steppe_herd_does_not_compare_to_plain():
    st, pos, _far = _steppe_state(troupeau=True, season=Season.PRINTEMPS)
    info = hex_inspect(st, pos)
    assert info is not None
    _no_plain_compare(inspect_lines(info))


def test_inspect_steppe_herd_raises_shown_food_year_round():
    winter_herd, pos, _far = _steppe_state(troupeau=True, season=Season.HIVER)
    winter_base, _pos, _ = _steppe_state(troupeau=False, season=Season.HIVER)
    info_h = hex_inspect(winter_herd, pos)
    info_b = hex_inspect(winter_base, pos)
    assert info_h is not None and info_b is not None
    assert info_h["food"] > info_b["food"]
    _no_plain_compare(inspect_lines(info_h))
    autumn_herd, apos, _ = _steppe_state(troupeau=True, season=Season.AUTOMNE)
    autumn_base, _apos, _ = _steppe_state(troupeau=False, season=Season.AUTOMNE)
    info_ah = hex_inspect(autumn_herd, apos)
    info_ab = hex_inspect(autumn_base, apos)
    assert info_ah is not None and info_ab is not None
    assert info_ah["food"] > info_ab["food"]
    spring_herd, spos, _ = _steppe_state(troupeau=True, season=Season.PRINTEMPS)
    spring_base, _spos, _ = _steppe_state(troupeau=False, season=Season.PRINTEMPS)
    info_sh = hex_inspect(spring_herd, spos)
    info_sb = hex_inspect(spring_base, spos)
    assert info_sh is not None and info_sb is not None
    assert info_sh["food"] > info_sb["food"]
