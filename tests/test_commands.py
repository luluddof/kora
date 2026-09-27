"""Le canal des ordres (commands.py) : chaque genre d'ordre fait ce que
faisait l'interface ; on ne commande que ce qui est a soi ; un ordre mal
forme ne casse rien."""

from src.kora import chiefs, commands, diplo, events, goods, sites, tech, villages  # noqa: F401
from src.kora.commands import NOT_YOURS, apply, make
from src.kora.sim import new_game
from src.kora.types import OrderKind, Terrain
from src.kora.world import make_filled_world, offset_to_axial


def _mp():
    world = make_filled_world(60, 30, Terrain.VALLEE, wrap_x=True)
    return new_game(world, setup={"name": "Aroha"}, others={2: {"name": "Tahu"}})


def _band(st, tid):
    return next(b for b in st.bands.values() if b.tribe_id == tid)


def test_every_kind_has_a_handler():
    assert set(commands._HANDLERS) == set(commands.KINDS)


def test_goto_and_march_only_for_own_bands():
    st = _mp()
    mine, theirs = _band(st, 1), _band(st, 2)
    goal = offset_to_axial(10, 10)
    assert apply(st, make(1, "goto", mine.id, goal.q, goal.r))["msg"] == ""
    assert mine.order.kind is OrderKind.GOTO and mine.order.target_hex == goal
    assert apply(st, make(1, "goto", theirs.id, goal.q, goal.r))["msg"] == NOT_YOURS
    assert theirs.order.kind is not OrderKind.GOTO
    assert apply(st, make(2, "march", theirs.id, mine.id))["msg"] == ""
    assert theirs.order.kind is OrderKind.MARCH_TO_BAND
    assert apply(st, make(2, "march", mine.id, theirs.id))["msg"] == NOT_YOURS


def test_band_actions_split_and_camp():
    st = _mp()
    band = _band(st, 1)
    band.population = 60
    tech.grant(st.tribes[1], "huttes")
    tech.invalidate()
    n = len(st.bands)
    res = apply(st, make(1, "band", band.id, "split"))
    assert res["msg"] == "" and res["sel"] != band.id and len(st.bands) == n + 1
    res = apply(st, make(1, "band", band.id, "camp"))
    assert res["msg"] == "" and sites.own_site_at(st, band) is not None
    assert apply(st, make(2, "band", band.id, "split"))["msg"] == NOT_YOURS
    assert apply(st, make(1, "band", band.id, "voler"))["msg"] == "?"


def test_found_a_village_and_run_it():
    st = _mp()
    band = _band(st, 1)
    for tid in tech.TECHS:
        tech.grant(st.tribes[1], tid)
    tech.invalidate()
    band.population, band.stock = 90, 3000.0
    sites.make_camp(st, band.id)
    res = apply(st, make(1, "found", band.id, sorted(villages.OATHS)[0]))
    assert res["site"] is not None and st.sites[res["site"]].kind == "village"
    site = st.sites[res["site"]]
    pick = next(b for b in villages.BUILD_ORDER if villages.building_status(st, site, b) == "possible")
    assert apply(st, make(1, "build", band.id, pick))["msg"] == ""
    assert villages.works(site)
    cid = next(c for c in goods.CRAFTS if not goods.add_block(st, site, c))
    assert apply(st, make(1, "teams", site.id, cid, 1))["msg"] == ""
    assert goods.teams_of(site, cid) == 1
    assert apply(st, make(2, "teams", site.id, cid, 1))["msg"] == NOT_YOURS
    assert apply(st, make(1, "teams", site.id, cid, -1))["msg"] == ""
    assert goods.teams_of(site, cid) == 0
    res = apply(st, make(1, "raise", band.id, "troupe", None))
    assert res["msg"] == "" and res["sel"] in st.bands and st.bands[res["sel"]].kind == "armee"
    assert apply(st, make(1, "dissolve", res["sel"]))["msg"] == ""


def test_learn_honor_heir():
    from src.kora.sim import tick

    st = _mp()
    # Un savoir devient disponible quand on l'a vu pratiquer : quelques semaines.
    for _ in range(104):
        ready = next((t for t in tech.TECHS if tech.status(st, 1, t) == "disponible"), None)
        if ready:
            break
        tick(st)
    assert ready
    apply(st, make(1, "learn", ready))
    assert st.tribes[1].learning == ready
    band = _band(st, 1)
    band.population = 60
    child = apply(st, make(1, "band", band.id, "split"))["sel"]
    st.bands[child].loyalty = 30.0
    st.tribes[1].prestige = 50
    assert apply(st, make(1, "honor", child))["msg"] == ""
    assert st.bands[child].loyalty > 30.0
    apply(st, make(1, "heir", child))
    assert st.tribes[1].heir == st.bands[child].leader.pid
    assert apply(st, make(2, "honor", child))["msg"] == NOT_YOURS


def test_diplo_and_event_answers_belong_to_their_player():
    st = _mp()
    diplo.make_contact(st, 1, 2)
    assert "decider" in apply(st, make(1, "diplo", 2, "treve"))["msg"]
    assert "recemment" in apply(st, make(1, "diplo", 2, "treve"))["msg"]
    card = next(c for c in events.pending(st, 2) if c.event_id == "offre_treve")
    assert apply(st, make(1, "event", card.uid, 0))["msg"] == NOT_YOURS
    apply(st, make(2, "event", card.uid, 0))
    assert diplo.has_pact(st, 1, 2, "treve")


def test_routes_are_found_by_their_key():
    st = _mp()
    diplo.make_contact(st, 1, 2)
    diplo.add_pact(st, 1, 2, "commerce")
    route = diplo.TradeRoute(1, 2, goods.GOODS[0], 1, 1, 0)
    st.diplo.routes.append(route)
    key = commands.route_key(route)
    assert commands._route(st, key) is route
    assert commands._route(st, [1, 2, "rien"]) is None
    assert "n'existe plus" in apply(st, make(1, "route_level", [2, 1, "rien"], 2))["msg"]


def test_malformed_orders_are_refused_quietly():
    st = _mp()
    assert apply(st, ["x"])["msg"] == "Ordre illisible"
    assert apply(st, [1, "pas-un-ordre"])["msg"] == "Ordre inconnu"
    assert apply(st, [3, "learn", "feu"])["msg"].startswith("Ce peuple")
    assert apply(st, [1, "goto", "a", "b"])["msg"] == "Ordre refuse"
    assert apply(st, [1, "goto"])["msg"] == "Ordre refuse"
    assert chiefs.obeys(st, _band(st, 1))
