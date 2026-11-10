"""Les corrections du moteur (0.25.2) : le memo de la semaine partage entre
tech et learning, la trace d'une erreur de simulation, et des calculs
allegés qui rendent EXACTEMENT ce qu'ils rendaient (les peuples qui ont un
village, le rival du chef, la terre ou fonder)."""

from src.kora import ai, chiefs, events, goods, learning, persist, sim, sites, tech, villages
from src.kora.sim import new_game, tick
from src.kora.types import Terrain
from src.kora.world import make_filled_world


def _world():
    return make_filled_world(60, 30, Terrain.VALLEE, wrap_x=True)


def _villages_state(tids=(1, 2)):
    st = new_game(_world())
    for tid in tids:
        for t in (t for t in tech.TECHS if not tech.TECHS[t].drawn and tech.era_of(tech.TECHS[t]) < 2):
            tech.grant(st.tribes[tid], t)
        band = next(b for b in st.bands.values() if b.tribe_id == tid)
        band.population, band.stock = 130, 3000.0
        sites.make_camp(st, band.id)
        villages.found(st, band.id)
    tech.invalidate()
    return st


def test_the_week_memo_is_the_same_for_tech_and_learning(monkeypatch):
    """learning gardait une copie du memo prise a l'import (None pour
    toujours) : les lignees etaient recalculees a chaque question."""
    st = new_game(_world())
    calls = []
    real = learning._lineage_all
    monkeypatch.setattr(learning, "_lineage_all", lambda state: calls.append(1) or real(state))
    tech.begin_tick()
    try:
        assert learning.tick_memo() is tech._TICK_MEMO and tech._TICK_MEMO is not None
        first = learning._lineage_pop(st, 1)
        assert learning._lineage_pop(st, 1) == first and learning._lineage_pop(st, 2) >= 0
        assert len(calls) == 1, "une seule fois par memo"
        tech.invalidate()
        learning._lineage_pop(st, 1)
        assert len(calls) == 2, "refait apres invalidate"
    finally:
        tech.end_tick()
    assert learning.tick_memo() is None
    # Hors d'un pas : pas de memo, le calcul est toujours frais.
    learning._lineage_pop(st, 1)
    learning._lineage_pop(st, 1)
    assert len(calls) == 4


def test_a_simulation_error_keeps_its_trace(monkeypatch, tmp_path):
    st = new_game(_world())
    tick(st)

    def boom(state):
        raise RuntimeError("panne")

    monkeypatch.setattr(sim, "collect_food", boom)
    tick(st)
    assert st.clock.paused and "panne" in st.last_error and "RuntimeError" in st.last_error
    assert "kora_erreur.txt" in st.last_error
    assert "boom" in st.last_trace and "RuntimeError: panne" in st.last_trace
    # L'interface l'ecrit a cote des sauvegardes (partie.Play._frame).
    monkeypatch.setattr(persist, "default_save_path", lambda: tmp_path / "saves" / "kora.json")
    assert persist.write_error(st.last_trace)
    text = (tmp_path / "kora_erreur.txt").read_text(encoding="utf-8")
    assert text.startswith("Kora ") and "RuntimeError: panne" in text


def test_village_tribes_says_what_has_village_says():
    st = _villages_state((1, 2))
    settled = goods.village_tribes(st)
    assert settled == {1, 2}
    assert all((tid in settled) == goods.has_village(st, tid) for tid in st.tribes)
    # Un village sans habitants ne compte plus, pour l'un comme pour l'autre.
    band = next(b for b in st.bands.values() if b.tribe_id == 2 and b.village)
    del st.bands[band.id]
    assert goods.village_tribes(st) == {1} and not goods.has_village(st, 2)


def test_the_rival_of_the_chief_is_found_as_before():
    """Le plus petit id parmi les chefs de clan plus renommes que le chef
    (et pas fideles) : on ne trie plus que les bandes du peuple."""
    st = new_game(_world())
    chiefs.ensure(st)
    from src.kora.bands import split_band

    main = next(b for b in st.bands.values() if b.tribe_id == 1)
    main.population = 120
    kids = [split_band(st, main.id) for _ in range(2)]
    kids = [k for k in kids if k is not None]
    assert kids
    chief = chiefs.chief_of(st, 1)

    def old(state, tid):
        for b in sorted(state.bands.values(), key=lambda b: b.id):
            if b.tribe_id != tid or b.leader is None or chiefs.is_chief_band(state, b):
                continue
            if b.leader.renown >= chief.renown + 10 and "fidele" not in b.leader.traits:
                return b
        return None

    assert events._rival_band(st, 1) is old(st, 1)
    for k in kids:
        st.bands[k].leader.renown = chief.renown + 20
        st.bands[k].leader.traits = [t for t in st.bands[k].leader.traits if t != "fidele"]
    assert events._rival_band(st, 1) is old(st, 1) is st.bands[min(kids)]


def test_the_search_for_new_land_remembers_and_forgets(monkeypatch):
    st = _villages_state((1,))
    band = next(b for b in st.bands.values() if b.tribe_id == 2)
    tech.grant(st.tribes[2], "champs")
    tech.invalidate()
    calls = []
    real = ai._new_land
    monkeypatch.setattr(ai, "_new_land", lambda *a, **k: calls.append(1) or real(*a, **k))
    first = ai.find_new_land(st, band)
    n = len(calls)
    assert n >= 1
    # Du meme endroit, avec les memes villages : la meme terre, sans recherche.
    assert ai.find_new_land(st, band) == first and len(calls) == n
    # La reponse sans memo est la meme.
    st.world._lands.pop("new_land")
    assert ai.find_new_land(st, band) == first and len(calls) > n
    # Un village de plus : la recherche est refaite.
    n = len(calls)
    other = next(b for b in st.bands.values() if b.tribe_id == 2)
    for t in (t for t in tech.TECHS if not tech.TECHS[t].drawn and tech.era_of(tech.TECHS[t]) < 2):
        tech.grant(st.tribes[2], t)
    other.population, other.stock = 130, 3000.0
    sites.make_camp(st, other.id)
    villages.found(st, other.id)
    third = next((b for b in st.bands.values() if b.tribe_id == 3), None)
    if third is not None:
        ai.find_new_land(st, third)
        assert len(calls) > n
