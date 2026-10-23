"""L'age du bronze et les VOIES (2026-10-23) : un troisieme age dans l'arbre,
une fourche (la cite ou la steppe : deux grands tournants exclusifs PAR
PEUPLE), le marqueur d'age, les evenements de la fourche, l'IA."""

from src.kora import chiefs, diplo, draws, events, learning, tech, tree_graph, turning
from src.kora.clock import Clock
from src.kora.gamestate import GameState
from src.kora.tech import Cond
from src.kora.types import Band, Terrain, Tribe
from src.kora.world import make_filled_world, offset_to_axial

# Ce qu'il faut pour les deux tournants de la fourche.
FORK = {"troupeau", "chevres", "lait", "bovins", "maisons", "araire", "sedentarite", "champs"}


def _state(known=(), story=False):
    w = make_filled_world(80, 40, Terrain.STEPPE, wrap_x=True)
    base = set(tech.START_KNOWLEDGE) | {"rites", "palabres", "huttes", "epieu"} | set(known)
    tribes = {
        1: Tribe(1, "Kora", 30, True, knowledge=set(base), culture="joueur"),
        2: Tribe(2, "Akor", 30, False, knowledge=set(base), culture="vallee"),
    }
    bands = {
        1: Band(1, 1, offset_to_axial(20, 20), 90, 900.0),
        2: Band(2, 2, offset_to_axial(26, 20), 90, 900.0),
    }
    st = GameState(world=w, clock=Clock(), tribes=tribes, bands=bands, next_band_id=3, story=story)
    w.fill_season(st.clock.season())
    chiefs.ensure(st)
    draws.set_seed(st, 1)
    diplo.make_contact(st, 1, 2, quiet=True)
    tech.invalidate()
    return st


def test_the_bronze_age_is_a_third_age_of_the_tree():
    names = [name for name, _tiers, _b in tech.ERAS]
    assert names == ["Âge tribal", "Néolithique", "Âge du bronze"]
    assert 6.5 in tech.TURNING_TIERS and tech.ERAS[2][1] == (6.5, 7, 8, 9)
    bronze = [t for t in tech.TECHS.values() if t.tier in tech.ERAS[2][1]]
    assert len(bronze) >= 16 and all(tech.era_of(t) == 2 for t in bronze)
    # Plus cher que le neolithique.
    assert tech.TIER_COST[7] > tech.TIER_COST[6] and tech.TIER_COST[9] > tech.TIER_COST[8]
    # Deux voies, chacune entree par un grand tournant de la rangee 6,5 ;
    # chaque voie a ses savoirs, et il reste des savoirs communs.
    for v in tech.VOIES.values():
        entry = tech.TECHS[v.tournant]
        assert entry.turning and entry.tier == 6.5 and entry.voie == v.id
        assert sum(1 for t in bronze if t.voie == v.id and not t.turning) >= 5
    assert sum(1 for t in bronze if not t.voie) >= 4
    # Un savoir d'une voie descend de son tournant (jamais de l'autre voie).
    for t in bronze:
        if t.voie and not t.turning:
            chain = set()
            todo = list(t.prereqs)
            while todo:
                p = todo.pop()
                if p not in chain:
                    chain.add(p)
                    todo.extend(tech.TECHS[p].prereqs)
            assert tech.VOIES[t.voie].tournant in chain, t.id
            assert not any(tech.TECHS[p].voie and tech.TECHS[p].voie != t.voie for p in chain), t.id


def test_taking_a_voie_closes_the_other_for_the_whole_age():
    st = _state(known=FORK | {"steppe"})
    tribe = st.tribes[1]
    assert tech.voie_of(tribe) == "steppe"
    assert learning.status(st, 1, "cite") == "ferme"
    assert learning.status(st, 1, "canaux") == "ferme"
    assert learning.status(st, 1, "feutre") != "ferme"
    # Les savoirs communs restent ouverts.
    assert not tech.closed(tribe, tech.TECHS["fonte"]) and not tech.closed(tribe, tech.TECHS["roue"])
    # Le tournant ferme ne vient plus : ni naissance, ni voisins (l'autre
    # peuple, lui, a pris la cite).
    other = st.tribes[2]
    other.knowledge.discard("steppe")
    other.knowledge.add("cite")
    assert turning.sources(st, 1, "cite") == []
    turning.monthly(st)
    assert turning.presence(tribe, "cite") == 0.0
    # On ne peut pas l'etudier, et une etude commencee s'arrete.
    learning.choose(st, 1, "cite")
    assert tribe.learning != "cite"
    tribe.learning = "canaux"
    learning.update_learning(st)
    assert tribe.learning is None
    # Chez l'autre peuple, c'est l'inverse ; un peuple sans voie n'a rien de ferme.
    assert tech.voie_of(other) == "cite" and learning.status(st, 2, "steppe") == "ferme"
    other.knowledge.discard("cite")
    assert learning.status(st, 2, "steppe") != "ferme" and learning.status(st, 2, "cite") != "ferme"


def test_the_town_condition_counts_the_biggest_village():
    st = _state()
    assert learning.town_pop(st, 1) == 0
    st.bands[1].village = 7
    st.bands[1].population = 420
    have, need, label = learning.cond_progress(st, st.tribes[1], Cond("town", 400))
    assert (have, need) == (420, 400) and "400 habitants" in label
    assert any(c.kind == "town" for c in tech.TECHS["cite"].conds)


def test_the_ai_takes_the_voie_that_fits_its_way_of_life():
    st = _state(known=FORK)
    tribe = st.tribes[2]
    tribe.practice["steppe"] = 200
    tribe.practice["res:chevaux"] = 100
    assert learning.preferred_voie(st, tribe) == "steppe"
    tribe.practice.clear()
    st.bands[2].village = 9
    st.bands[2].population = 900
    assert learning.preferred_voie(st, tribe) == "cite"
    # Les deux tournants arrives : l'IA n'en etudie qu'un, le sien.
    for v in tech.VOIES.values():
        tribe.tournants[v.tournant] = 100.0
    assert learning.status(st, 2, "cite") == "disponible" and learning.status(st, 2, "steppe") == "disponible"
    tribe.learning = None
    learning.auto_choose(st, 2)
    assert tribe.learning == "cite"
    # Seule l'autre voie est arrivee : il attend la sienne, tant qu'il a
    # autre chose a apprendre.
    tribe.learning = None
    tribe.tournants["cite"] = 50.0
    tribe.practice["hivers"] = 1
    assert learning.status(st, 2, "fumage") == "disponible"
    learning.auto_choose(st, 2)
    assert tribe.learning == "fumage"
    # Plus rien d'autre : faute de mieux, il prend la voie arrivee.
    tribe.knowledge.add("fumage")
    tribe.learning = None
    assert learning.available(st, 2) == ["steppe"]
    learning.auto_choose(st, 2)
    assert tribe.learning == "steppe"


def test_the_age_marker_of_a_people_and_of_the_world():
    st = _state()
    assert tech.age_of(st.tribes[1]) == 0
    st.tribes[1].knowledge |= FORK
    assert tech.age_of(st.tribes[1]) == 1
    st.tribes[1].knowledge.add("steppe")
    assert tech.age_of(st.tribes[1]) == 2
    ages, voies = learning.world_ages(st)
    assert ages == [1, 0, 1] and voies == {"cite": 0, "steppe": 1}
    lines = [text for text, _kind in learning.age_lines(st, 1)]
    assert lines[0] == "Votre peuple : Âge du bronze, la voie des steppes"
    assert any("dont la voie des steppes : 1" in t for t in lines)


def test_the_fork_card_comes_once_and_hastens_the_chosen_voie():
    st = _state(known=FORK, story=True)
    tribe = st.tribes[1]
    turning.monthly(st)
    cards = [p for p in events._book(st).pending if p.event_id == "fourche" and p.tribe_id == 1]
    assert len(cards) == 1
    before = turning.presence(tribe, "steppe")
    events.choose(st, cards[0].uid, 1)
    assert turning.presence(tribe, "steppe") >= before + 25.0
    turning.monthly(st)
    assert not [p for p in events._book(st).pending if p.event_id == "fourche"]
    # L'IA n'a pas la carte (elle choisit sa voie a l'adoption).
    assert all(p.tribe_id == 1 for p in events._book(st).pending)


def test_entering_a_voie_has_its_own_event():
    st = _state(known=FORK | {"cite"}, story=True)
    turning.on_adopted(st, st.tribes[1], "cite")
    ids = [p.event_id for p in events._book(st).pending if p.tribe_id == 1]
    assert "voie_cite" in ids and "voie_steppe" not in ids


def test_the_tree_shows_the_fork_side_by_side():
    g = tree_graph.build()
    layer = g["order"][g["layers"].index(6.5)]
    forks = [n for n in layer if not isinstance(n, tuple) and tech.TECHS[n].voie]
    assert sorted(forks) == ["cite", "steppe"]
    i, j = sorted(layer.index(f) for f in forks)
    assert j == i + 1
    gap = abs(g["x"][forks[0]] - g["x"][forks[1]]) - tree_graph.TURN_W
    assert gap >= tree_graph.FORK_GAP - 1


def test_the_tree_and_the_age_marker_draw_with_a_voie_taken():
    import os

    os.environ.setdefault("SDL_VIDEODRIVER", "dummy")
    import pygame

    from src.kora import render_tech
    from src.kora.layout import hud_hit
    from src.kora.render import Renderer
    from src.kora.sim import _default_world, new_game

    st = new_game(_default_world(), minor_peoples=0)
    st.tribes[st.viewer].knowledge |= FORK | {"steppe"}
    tech.invalidate()
    pygame.init()
    try:
        r = Renderer(pygame.display.set_mode((1280, 720)))
        for pick in ("cite", "steppe", "feutre"):
            r.draw(st, 0, 0, 1.0, None, side_panel="savoirs", ui={"tech_cam": None}, tech_pick=pick)
        assert render_tech.STATE_LABEL["ferme"] and render_tech.MEDAL_STATE["ferme"] == "eteint"
        # Le marqueur d'age, a cote de la saison : son clic ouvre l'arbre.
        x, y, w, h = r.hud_hits["age"]
        assert hud_hit(r.hud_hits, x + w // 2, y + h // 2) == "age"
    finally:
        pygame.quit()
