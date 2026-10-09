"""La recherche refaite : les grands tournants (turning.py, a la maniere des
institutions d'Europa Universalis V) et les savoirs tires (draws.py, a la
maniere de Terra Invicta)."""

from src.kora import draws, events, learning, look, persist, tech, turning
from src.kora.clock import Clock
from src.kora.gamestate import GameState
from src.kora.types import Band, Terrain, Tribe
from src.kora.world import make_filled_world, offset_to_axial
from src.kora import chiefs, diplo


def _state(seed=1, known=()):
    w = make_filled_world(80, 40, Terrain.VALLEE, wrap_x=True)
    base = set(tech.START_KNOWLEDGE) | {"rites", "palabres", "huttes", "epieu"} | set(known)
    tribes = {
        1: Tribe(1, "Kora", 30, True, knowledge=set(base), culture="joueur"),
        2: Tribe(2, "Akor", 30, False, knowledge=set(base), culture="vallee"),
        3: Tribe(3, "Tavek", 30, False, knowledge=set(base), culture="vallee"),
    }
    bands = {
        1: Band(1, 1, offset_to_axial(20, 20), 90, 900.0),
        2: Band(2, 2, offset_to_axial(26, 20), 90, 900.0),
        3: Band(3, 3, offset_to_axial(70, 20), 90, 900.0),
    }
    st = GameState(world=w, clock=Clock(), tribes=tribes, bands=bands, next_band_id=4)
    w.fill_season(st.clock.season())
    chiefs.ensure(st)
    draws.set_seed(st, seed)
    diplo.make_contact(st, 1, 2, quiet=True)
    tech.invalidate()
    return st


# --- les tirages ---------------------------------------------------------------------


def test_the_world_draw_is_fixed_by_the_seed_and_exclusive_groups_keep_one():
    a, b = _state(1), _state(1)
    assert draws.world_draw(a) == draws.world_draw(b)
    worlds = {tuple(sorted(draws.world_draw(_state(s)).items())) for s in range(1, 40)}
    assert len(worlds) > 5, "chaque partie tire son monde"
    for s in range(1, 60):
        drawn = draws.world_draw(_state(s))
        for group, (_name, none_chance) in tech.GROUPS.items():
            members = [t.id for t in tech.TECHS.values() if t.group == group]
            born = [m for m in members if drawn[m]]
            assert len(born) <= 1, (s, group, born)
            if none_chance == 0.0:
                assert len(born) == 1, (s, group)


def test_each_people_rolls_its_own_chance():
    st = _state(3)
    hits = 0
    for tid in range(1, 401):
        hits += draws.comes_to(st, tid, "peintures")
    assert 0.4 < hits / 400 < 0.6, hits
    # Le meme peuple, la meme graine : le meme sort (recharger ne change rien).
    assert draws.comes_to(st, 7, "peintures") == draws.comes_to(_state(3), 7, "peintures")


def _seed_where(pred):
    for s in range(1, 500):
        st = _state(s, known=("clan",))
        if pred(st):
            return st
    raise AssertionError("aucune graine")


def test_a_drawn_knowledge_that_does_not_come_is_absent_once_its_prerequisites_are_known():
    st = _seed_where(lambda st: not draws.comes_to(st, 1, "peintures"))
    tribe = st.tribes[1]
    tribe.knowledge.discard("clan")
    # Avant le tirage : verrouille, avec sa chance.
    assert learning.status(st, 1, "peintures") == "verrouille"
    assert "50 %" in draws.chance_text(st, 1, "peintures")
    tribe.knowledge.add("clan")
    assert learning.status(st, 1, "peintures") == "absent"
    assert "pas venu" in draws.why_absent(st, 1, "peintures")
    assert not learning.choose(st, 1, "peintures")
    # Le joueur l'apprend une fois, au journal.
    draws.monthly(st)
    draws.monthly(st)
    assert sum("Peintures des cavernes" in e.text for e in st.log.entries) == 1
    assert "peintures" in tribe.revealed


def test_a_world_without_the_knowledge_never_sees_it():
    st = _seed_where(lambda st: not draws.in_world(st, "propulseur"))
    assert learning.status(st, 1, "propulseur") == "absent"
    assert "pas né dans ce monde" in draws.why_absent(st, 1, "propulseur")
    st2 = _seed_where(lambda st: draws.in_world(st, "chamanes"))
    assert learning.status(st2, 1, "deesse") == "absent"
    assert "La Grande Mère" in draws.why_absent(st2, 1, "deesse") or "Chamanes" in draws.why_absent(st2, 1, "deesse")


def test_a_drawn_knowledge_is_never_a_dead_end():
    for t in tech.TECHS.values():
        for p in t.prereqs:
            assert t.drawn or not tech.TECHS[p].drawn, (t.id, p)
        assert not (t.turning and t.drawn)


# --- les grands tournants ------------------------------------------------------------


def test_a_turning_point_is_born_where_its_conditions_are_met_then_spreads():
    st = _state()
    tribe = st.tribes[1]
    tribe.practice["hivers"] = 5
    st.bands[1].population = 50
    st.bands[4] = Band(4, 1, offset_to_axial(21, 20), 30, 300.0)
    st.next_band_id = 5
    assert turning.own_conditions(st, tribe, tech.TECHS["clan"])
    # Le clan ne se voit pas avant d'etre arrive : on ne l'adopte pas.
    assert learning.status(st, 1, "clan") == "attente"
    assert learning.status(st, 1, "conte") == "verrouille"
    prestige = tribe.prestige
    for _ in range(9):
        turning.monthly(st)
    assert turning.presence(tribe, "clan") == 100.0
    assert turning.birthplace(st, "clan") == (1, st.clock.year)
    assert tribe.prestige > prestige
    assert any("naît chez vous" in e.text for e in st.log.entries)
    assert learning.status(st, 1, "clan") == "disponible"
    # Il se repand chez le voisin en contact (2), pas chez l'inconnu (3).
    turning.monthly(st)
    assert turning.presence(st.tribes[2], "clan") > 0
    assert turning.presence(st.tribes[3], "clan") == 0
    rows = turning.sources(st, 2, "clan")
    assert any(who == 1 for _l, _v, who in rows)
    # Adopte : il ouvre son pan.
    tech.grant(tribe, "clan")
    assert learning.status(st, 1, "conte") in ("attente", "disponible")


def test_the_ai_adopts_a_turning_point_first():
    st = _state()
    st.tribes[2].tournants["clan"] = 100.0
    st.tribes[2].learning = None
    assert learning.auto_choose(st, 2) == "clan"


def test_travellers_bring_a_turning_point_closer():
    st = _state()
    st.story = True
    st.research["births"] = {"clan": [2, 0]}
    st.tribes[2].knowledge.add("clan")
    st.tribes[1].tournants["clan"] = 20.0
    turning.monthly(st)
    inst = next(p for p in events.pending(st, 1) if p.event_id == "tournant_voyageurs")
    assert inst.data["tournant_id"] == "clan"
    before = turning.presence(st.tribes[1], "clan")
    events.choose(st, inst.uid, 0)
    assert turning.presence(st.tribes[1], "clan") >= before + 20


def test_an_old_save_gets_the_turning_points_of_what_it_knows():
    st = _state(known=("semis", "palissade", "conte"))
    st.research = {}
    turning.migrate(st)
    tribe = st.tribes[1]
    assert {"sedentarite", "clan"} <= tribe.knowledge
    assert turning.birthplace(st, "sedentarite") == (0, 0)
    assert "avant" in turning.born_text(st, 1, "sedentarite")
    # Une fois seulement.
    tribe.knowledge.discard("clan")
    turning.migrate(st)
    assert "clan" not in tribe.knowledge


def test_research_survives_a_save():
    st = _state()
    st.research["births"] = {"clan": [1, 4]}
    st.tribes[1].tournants["don"] = 37.5
    st.tribes[1].revealed.add("peintures")
    back, _view = persist.loads_game(persist.dumps_game(st), st.world)
    assert back.research["seed"] == 1 and back.research["births"] == {"clan": [1, 4]}
    assert back.tribes[1].tournants == {"don": 37.5} and back.tribes[1].revealed == {"peintures"}
    # Une sauvegarde sans graine en recoit une, toujours la meme.
    data = persist.game_to_json(st)
    data.pop("research")
    a, _v = persist.game_from_json(data, st.world)
    b, _v = persist.game_from_json(persist.game_to_json(st) | {"research": {}}, st.world)
    assert a.research["seed"] == b.research["seed"] == draws.seed_from(st)


def test_the_turning_map_colours_peoples_by_presence():
    st = _state()
    st.research["births"] = {"clan": [2, 3]}
    st.tribes[1].tournants["clan"] = 50.0
    assert look.turning_color(st, 2, "clan") == look.TURN_CRADLE
    assert look.turning_color(st, 3, "clan") == look.TURN_UNKNOWN
    half = look.turning_color(st, 1, "clan")
    assert half not in (look.TURN_NONE, look.TURN_HERE)
    st.tribes[1].knowledge.add("clan")
    assert look.turning_color(st, 1, "clan") == look.TURN_ADOPTED


def test_the_tree_lays_turning_points_in_their_rows_without_overlap():
    from src.kora.layout import tech_world

    world = tech_world()
    rects = list(world["nodes"].items())
    for i, (a, ra) in enumerate(rects):
        for b, rb in rects[i + 1:]:
            assert not (ra[0] < rb[0] + rb[2] and rb[0] < ra[0] + ra[2] and ra[1] < rb[1] + rb[3] and rb[1] < ra[1] + ra[3]), (a, b)
    for t in tech.turnings():
        assert world["nodes"][t.id][2] > world["nodes"]["feu"][2], "un tournant est une large carte"


def test_the_links_run_in_the_corridors_and_never_cross_a_card():
    from src.kora.layout import chain_of, tech_world

    world = tech_world()
    nodes, links = world["nodes"], world["links"]
    assert set(links) == {(p, t.id) for t in tech.TECHS.values() for p in t.prereqs}
    for (pid, tid), pts in links.items():
        # Du bas du prerequis au haut du savoir, a angles droits.
        assert pts[0][1] == nodes[pid][1] + nodes[pid][3] and pts[-1][1] == nodes[tid][1]
        for (x0, y0), (x1, y1) in zip(pts, pts[1:]):
            assert x0 == x1 or y0 == y1, (pid, tid)
            for other, (nx, ny, nw, nh) in nodes.items():
                if other in (pid, tid):
                    continue
                crosses = (
                    x0 == x1 and nx < x0 < nx + nw and min(y0, y1) < ny + nh and max(y0, y1) > ny
                ) or (y0 == y1 and ny < y0 < ny + nh and min(x0, x1) < nx + nw and max(x0, x1) > nx)
                assert not crosses, (pid, tid, other)
    up, down = chain_of("chefferie")
    assert {"conte", "clan", "rites", "palabres", "feu"} <= up
    assert {"terre_ancetres", "ancetres", "grand_chef"} <= down
