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


def test_a_turning_point_is_discovered_by_the_first_to_finish_its_research():
    st = _state()
    tribe = st.tribes[1]
    tribe.practice["hivers"] = 5
    st.bands[1].population = 50
    st.bands[4] = Band(4, 1, offset_to_axial(21, 20), 30, 300.0)
    st.next_band_id = 5
    assert turning.own_conditions(st, tribe, tech.TECHS["clan"])
    # Il ne s'adopte pas avant d'etre arrive.
    assert learning.status(st, 1, "clan") == "attente"
    assert learning.status(st, 1, "conte") == "verrouille"
    for _ in range(9):
        turning.monthly(st)
    assert turning.presence(tribe, "clan") == 100.0
    # Arrive : pas encore decouvert ; le journal dit qu'on peut etre le premier.
    assert turning.birthplace(st, "clan") is None
    assert any("berceau" in e.text for e in st.log.entries)
    assert learning.status(st, 1, "clan") == "disponible"
    # Personne ne l'a adopte : il ne se repand pas encore.
    turning.monthly(st)
    assert turning.presence(st.tribes[2], "clan") == 0
    # La recherche terminee : decouvert, le berceau et son bonus.
    prestige = tribe.prestige
    loyalty = tech.bonuses(tribe).loyalty
    learning.choose(st, 1, "clan")
    tribe.progress["clan"] = tech.TECHS["clan"].cost
    learning.update_learning(st)
    assert "clan" in tribe.knowledge
    assert turning.birthplace(st, "clan") == (1, st.clock.year)
    assert tribe.prestige >= prestige + turning.BIRTH_PRESTIGE
    assert tribe.cradles == ["clan"] and tech.bonuses(tribe).loyalty > loyalty + 5 - 1
    assert any("premiers au monde" in e.text for e in st.log.entries)
    # Maintenant il se repand chez le voisin en contact (2), pas chez l'inconnu (3).
    turning.monthly(st)
    assert turning.presence(st.tribes[2], "clan") > 0
    assert turning.presence(st.tribes[3], "clan") == 0
    assert any(who == 1 for _l, _v, who in turning.sources(st, 2, "clan"))
    # Le second a l'adopter n'est pas le berceau.
    other = st.tribes[2]
    tech.grant(other, "clan")
    turning.on_adopted(st, other, "clan")
    assert turning.birthplace(st, "clan")[0] == 1 and other.cradles == []
    assert learning.status(st, 1, "conte") in ("attente", "disponible")


def test_a_save_of_0_10_loses_cradles_that_never_adopted():
    st = _state()
    st.tribes[2].knowledge.add("don")
    st.research.update({"turnings": 1, "births": {"clan": [1, 4], "don": [2, 7]}})
    turning.migrate(st)
    assert "clan" not in st.research["births"], "le peuple 1 n'avait pas adopte le clan"
    assert st.research["births"]["don"] == [2, 7] and st.tribes[2].cradles == ["don"]


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
    # A chaque chargement, l'arbre reste coherent : qui sait un savoir du pan
    # d'un tournant a ce tournant (l'arbre a pu changer entre deux versions).
    tribe.knowledge.discard("clan")
    turning.migrate(st)
    assert "clan" in tribe.knowledge
    tribe.knowledge -= {"clan", "conte"}
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


def test_the_tree_is_laid_out_as_a_graph_and_links_never_cross_a_card():
    from src.kora import tree_graph
    from src.kora.layout import tech_world

    world = tech_world()
    nodes, links = world["nodes"], world["links"]
    assert set(links) == {(p, t.id) for t in tech.TECHS.values() for p in t.prereqs}
    for (pid, tid), pts in links.items():
        # Du bas du prerequis au haut du savoir, toujours en descendant.
        assert pts[0][1] == nodes[pid][1] + nodes[pid][3] and pts[-1][1] == nodes[tid][1]
        assert all(b[1] >= a[1] - 1e-6 for a, b in zip(pts, pts[1:])), (pid, tid)
        for px, py in pts:
            for other, (nx, ny, nw, nh) in nodes.items():
                if other in (pid, tid):
                    continue
                assert not (nx + 1 < px < nx + nw - 1 and ny + 1 < py < ny + nh - 1), (pid, tid, other)
    # Moins de croisements que l'ordre des branches de depart.
    g = tree_graph.build()
    down = {}
    for chain in g["edges"].values():
        for a, b in zip(chain, chain[1:]):
            down.setdefault(a, []).append(b)
    start = [[] for _ in g["order"]]
    for k, layer in enumerate(g["order"]):
        start[k] = sorted(layer, key=lambda n: (tech.TECHS[n].branch, tech.TECHS[n].slot) if n in tech.TECHS else (99, 0))
    assert tree_graph.crossings(g["order"], down) < tree_graph.crossings(start, down)


def test_each_new_game_draws_its_own_luck():
    """D'une partie a l'autre, le hasard des savoirs change (graine tiree par
    la machine a chaque partie neuve : app._fresh_seed, session) ; une
    partie, elle, garde la sienne."""
    from src.kora import app, draws, tech
    from src.kora.sim import _default_world, new_game

    drawn = sorted(t.id for t in tech.TECHS.values() if t.chance < 1.0)
    seen = set()
    for _ in range(5):
        st = new_game(_default_world(), setup={"seed": app._fresh_seed()})
        seen.add((tuple(sorted(draws.world_draw(st).items())), tuple(draws.comes_to(st, 1, t) for t in drawn)))
    assert len(seen) >= 4, "cinq parties neuves : des tirages différents"


def test_a_resource_received_by_trade_counts_for_the_knowledge():
    """Un peuple sans silex chez lui, qui recoit des haches polies par
    l'echange : chaque semaine ou il en a compte comme une semaine pres du
    silex (la condition des Haches polies se remplit) ; la condition le dit."""
    world = make_filled_world(40, 20, Terrain.PLAINE, wrap_x=True)
    world.resources = {"silex": None}
    world.resources_near = lambda h: set()
    tribe = Tribe(1, "Kora", 30, True, knowledge=set(tech.START_KNOWLEDGE))
    st = GameState(world=world, clock=Clock(), tribes={1: tribe}, bands={1: Band(1, 1, offset_to_axial(5, 5), 60, 100.0)}, next_band_id=2)
    cond = next(c for c in tech.TECHS["haches"].conds if c.kind == "res")
    for _ in range(5):
        learning.update_practice(st)
    assert learning.cond_progress(st, tribe, cond)[0] == 0
    tribe.goods = {"haches": 3.0}
    for _ in range(cond.need):
        learning.update_practice(st)
    have, need, label = learning.cond_progress(st, tribe, cond)
    assert have >= need and "par l'échange" in label and "haches polies" in label


def test_the_tree_hides_what_an_exclusive_group_ruled_out():
    """Un groupe exclusif dont un savoir est ne : les autres (et ce qui en
    depend) ne sont plus dans l'arbre ; un groupe ou rien n'est ne reste
    visible."""
    from src.kora import layout
    from src.kora.sim import _default_world, new_game

    st = new_game(_default_world(), setup={"seed": 12345})
    drawn = draws.world_draw(st)
    gone = draws.hidden(st)
    for group in tech.GROUPS:
        members = [t.id for t in tech.TECHS.values() if t.group == group]
        born = [m for m in members if drawn.get(m)]
        if born:
            assert set(members) - set(born) <= gone and not set(born) & gone
        else:
            assert not set(members) & gone
    layout.set_tree_hidden(gone)
    nodes = layout.tech_world()["nodes"]
    assert not gone & set(nodes) and set(tech.TECHS) - gone <= set(nodes)
    assert all(a not in gone and b not in gone for a, b in layout.tech_world()["links"])
    layout.set_tree_hidden(frozenset())
    assert set(tech.TECHS) <= set(layout.tech_world()["nodes"])
