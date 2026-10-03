"""La memoire du brouillard (memory.py) : ce qu'on a vu la derniere fois."""

from src.kora import influence, memory, persist
from src.kora.vision import recompute_vision, vision_of
from src.kora.world import offset_to_axial
from test_approach import _state


def _seen():
    st = _state()
    st.bands[1].position = offset_to_axial(26, 20)
    for _ in range(6):
        influence.update(st)
    recompute_vision(st)
    memory.update(st)
    return st


def test_a_village_once_seen_stays_on_the_map_as_it_was():
    st = _seen()
    vis = vision_of(st, 1)
    v3 = next(s for s in st.sites.values() if s.tribe_id == 3 and s.kind == "village")
    assert v3.id in vis.sites and vis.sites[v3.id][3] == 3
    zones = dict(vis.zones)
    assert zones
    # On s'en va : le village change de mains loin des yeux ; la memoire garde l'ancien.
    st.bands[1].position = offset_to_axial(70, 20)
    recompute_vision(st)
    v3.tribe_id = 2
    memory.update(st)
    assert vis.sites[v3.id][3] == 3 and v3.hex not in vis.visible
    # On revient : elle se met a jour.
    st.bands[1].position = offset_to_axial(26, 20)
    recompute_vision(st)
    memory.update(st)
    assert vis.sites[v3.id][3] == 2


def test_a_village_gone_under_your_eyes_leaves_the_memory():
    st = _seen()
    vis = vision_of(st, 1)
    v3 = next(s for s in st.sites.values() if s.tribe_id == 3 and s.kind == "village")
    del st.sites[v3.id]
    memory.update(st)
    assert v3.id not in vis.sites


def test_the_memory_survives_a_save_and_old_saves_get_one():
    st = _seen()
    vis = vision_of(st, 1)
    back, _view = persist.loads_game(persist.dumps_game(st), st.world)
    assert vision_of(back, 1).sites == vis.sites and vision_of(back, 1).zones == vis.zones
    data = persist.game_to_json(st)
    data.pop("memory")
    old, _view = persist.game_from_json(data, st.world)
    assert vision_of(old, 1).sites
