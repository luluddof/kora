"""Metiers, biens du peuple, accords commerciaux ; savoirs des peuples fixes ;
croissance qui suit les vivres a venir ; onglet des villages."""

import os

from src.kora import chiefs, diplo, goods, sites, tech, villages
from src.kora.clock import Clock
from src.kora.sim import GameState, stock_max
from src.kora.types import Band, Terrain, Tribe
from src.kora.world import make_filled_world, offset_to_axial

CENTER = (30, 15)


def _world(res: dict | None = None, terrain=Terrain.VALLEE):
    world = make_filled_world(60, 30, terrain, wrap_x=True)
    n = world.width * world.height
    layers = {}
    for name, (value, radius) in (res or {}).items():
        layer = bytearray(n)
        center = offset_to_axial(*CENTER)
        for h in world.hexes_in_radius(center, radius):
            col, row = world._index(h)
            layer[row * world.width + col] = value
        layers[name] = bytes(layer)
    if layers:
        world.set_resources(layers)
    return world


def _village(known=(), res=None, pop=120, stock=3000.0, terrain=Terrain.VALLEE):
    world = _world(res, terrain)
    tribe = Tribe(1, "Kora", 30, True, knowledge=set(tech.START_KNOWLEDGE) | {"huttes", "semis"} | set(known), culture="joueur")
    st = GameState(world=world, clock=Clock(), tribes={1: tribe}, bands={1: Band(1, 1, offset_to_axial(*CENTER), pop, stock)}, next_band_id=2)
    world.fill_season(st.clock.season())
    chiefs.ensure(st)
    sites.make_camp(st, 1)
    site = villages.found(st, 1)
    st.bands[1].stock = stock
    return st, site, st.bands[1]


# --- savoirs ------------------------------------------------------------------------


def test_a_started_knowledge_is_finished_even_if_its_conditions_go():
    st, site, band = _village()
    tribe = st.tribes[1]
    # Chasse a l'epieu : 30 personnes et 6 semaines en plaine ou steppe.
    tribe.practice["plaine"] = 10
    assert tech.status(st, 1, "epieu") == "disponible"
    assert tech.choose(st, 1, "epieu")
    tribe.practice["plaine"] = 0
    assert tech.status(st, 1, "epieu") == "en_cours"
    for _ in range(200):
        tech.update_learning(st)
        if "epieu" in tribe.knowledge:
            break
    assert "epieu" in tribe.knowledge


def test_a_knowledge_once_begun_can_be_taken_up_again():
    st, site, band = _village()
    tribe = st.tribes[1]
    tribe.practice["plaine"] = 10
    tech.choose(st, 1, "epieu")
    tech.update_learning(st)
    tribe.learning = None
    tribe.practice["plaine"] = 0
    assert tribe.progress.get("epieu", 0) > 0
    assert tech.status(st, 1, "epieu") == "disponible"
    assert tech.choose(st, 1, "epieu")


def test_a_village_lives_off_all_its_lands():
    # Un village de vallee, de la foret dans ses terres : il la connait.
    st, site, band = _village(res={"argile": (200, 2)})
    world = st.world
    for h in world.hexes_in_radius(site.hex, villages.FIELD_RADIUS):
        if world.distance(h, site.hex) == villages.FIELD_RADIUS:
            col, row = world._index(h)
            world._terrains[row][col] = Terrain.FORET
    world._lands = {}
    tribe = st.tribes[1]
    tech.update_practice(st)
    assert tribe.practice.get("foret", 0) == 1
    assert tribe.practice.get("vallee", 0) == 1
    assert tribe.practice.get("res:argile", 0) == 1


def test_bands_the_people_had_still_count():
    st, site, band = _village()
    tribe = st.tribes[1]
    cond = tech.Cond("bands", 4)
    assert tech.cond_progress(st, tribe, cond)[0] == 1
    tribe.practice["bandes"] = 4
    have, need, label = tech.cond_progress(st, tribe, cond)
    assert have >= need and "eu" in label


# --- metiers ------------------------------------------------------------------------


def test_a_craft_needs_its_knowledge_its_resource_and_hands():
    st, site, band = _village(res={"argile": (230, 1)})
    assert "Poterie" in goods.add_block(st, site, "potiers")
    st.tribes[1].knowledge.add("poterie")
    assert goods.add_block(st, site, "potiers") == ""
    assert "sel" in goods.add_block(st, site, "sauniers") or "Salaison" in goods.add_block(st, site, "sauniers")
    # Une case d'argile et ses voisines : 7 gisements, 3 equipes au plus.
    assert goods.max_teams(st, site, "potiers") == goods.MAX_TEAMS
    assert goods.set_teams(st, site, "potiers", 3)
    assert not goods.set_teams(st, site, "potiers", 4)
    band.population = 60
    assert "bras" in goods.add_block(st, site, "potiers").lower() or goods.teams_of(site, "potiers") >= goods.MAX_TEAMS


def test_crafts_fill_the_people_reserve_and_villages_use_it():
    st, site, band = _village(known=("poterie",), res={"argile": (255, 2)})
    tribe = st.tribes[1]
    goods.set_teams(st, site, "potiers", 2)
    made = goods.output(st, site, "potiers")
    assert made == 2 * goods.OUTPUT * 1.5
    goods.update(st)
    use = band.population / 100.0 * goods.NEED
    assert abs(tribe.goods["poteries"] - (made - use)) < 1e-6
    assert goods.supplied(st, 1, "poteries")
    # Les pots gardent le grain et agrandissent le grenier.
    assert villages.rot_mult(st, site) < tech.bonuses(tribe).grain_rot
    cap = stock_max(band, st)
    tribe.goods.clear()
    assert stock_max(band, st) < cap
    # Sans equipes, la reserve s'use jusqu'au bout.
    tribe.goods["poteries"] = 1.0
    goods.set_teams(st, site, "potiers", 0)
    for _ in range(3):
        goods.update(st)
    assert not goods.supplied(st, 1, "poteries")


def test_salt_and_cloth_hold_the_village_together():
    st, site, band = _village(known=("salaison", "tissage", "chevres"))
    base = villages.stability(st, site, band)
    st.tribes[1].goods.update({"sel": 10.0, "etoffes": 10.0})
    assert villages.stability(st, site, band) == base + 9
    assert villages.winter_famine_mult(st, band) < 0.7


def test_herders_weave_without_wild_goats():
    st, site, band = _village(known=("tissage",))
    assert goods.craft_status(st, site, "tisserands") == "absent"
    st.tribes[1].knowledge.add("chevres")
    assert goods.craft_status(st, site, "tisserands") == "possible"


def test_craftsmen_are_not_in_the_fields():
    st, site, band = _village(known=("poterie",), res={"argile": (255, 2)}, pop=90)
    site.data["fields"] = [[30, 15], [31, 15], [29, 15], [30, 14], [31, 14]]
    full = villages.field_hands_mult(site, band)
    goods.set_teams(st, site, "potiers", 3)
    assert villages.field_hands_mult(site, band) < full
    assert goods.forage_mult(site, band) < 1.0


def test_fishers_feed_the_village():
    st, site, band = _village(known=("peche",), res={"poisson": (200, 2)})
    goods.set_teams(st, site, "pecheurs", 2)
    band.stock = 100.0
    goods.update(st)
    assert band.stock > 100.0
    st.tribes[1].knowledge.add("filets")
    assert goods.output(st, site, "pecheurs") > 2 * goods.CRAFTS["pecheurs"].food


def test_a_village_that_lost_people_keeps_the_teams_it_can():
    st, site, band = _village(known=("poterie",), res={"argile": (255, 2)})
    goods.set_teams(st, site, "potiers", 3)
    band.population = 35
    goods.update(st)
    assert goods.teams_of(site, "potiers") == 1


# --- echanges -----------------------------------------------------------------------


def _partners(known_b=("echanges",)):
    st, site, band = _village(known=("poterie", "echanges", "palabres"), res={"argile": (255, 2)})
    b = Tribe(2, "Akor", 30, False, knowledge=set(tech.START_KNOWLEDGE) | {"huttes", "semis"} | set(known_b), culture="steppe")
    st.tribes[2] = b
    other = Band(2, 2, offset_to_axial(CENTER[0] + 14, CENTER[1]), 100, 2000.0)
    st.bands[2] = other
    st.next_band_id = 3
    chiefs.ensure(st)
    sites.make_camp(st, 2)
    osite = villages.found(st, 2)
    other.stock = 2000.0
    diplo.make_contact(st, 1, 2, quiet=True)
    return st, site, band, osite, other


def test_a_trade_pact_needs_the_knowledge_and_villages():
    st, site, band, osite, other = _partners()
    st.tribes[1].knowledge.discard("echanges")
    assert "Echanges lointains" in diplo.evaluate(st, 1, 2, "commerce").blocked
    st.tribes[1].knowledge.add("echanges")
    v = diplo.evaluate(st, 1, 2, "commerce")
    assert not v.blocked and v.accepted
    msg = diplo.perform(st, 1, 2, "commerce")
    assert diplo.has_pact(st, 1, 2, "commerce") and diplo.at_peace(st, 1, 2)
    assert "Accord commercial" in diplo.status_line(st, 1, 2) and msg
    assert diplo.evaluate(st, 1, 2, "commerce").blocked


def _quiet_ai(st):
    """Le mois ou l'IA (peuple 2) ne touche pas a ses routes."""
    st.tick_count = 4


def test_the_player_opens_a_route_and_is_paid():
    st, site, band, osite, other = _partners()
    _quiet_ai(st)
    diplo.add_pact(st, 1, 2, "commerce")
    st.tribes[1].goods["poteries"] = 40.0
    route = goods.open_route(st, 1, 2, "poteries", sell=True, level=1)
    assert route is not None and route.by == 1 and goods.convoys_used(st, 1) == 1
    price = goods.route_price(st, route)
    before = band.stock, other.stock
    goods.monthly(st)
    got = st.tribes[2].goods.get("poteries", 0.0)
    assert 0 < got <= goods.LOAD and route.units == got
    assert abs((before[1] - other.stock) - got * price) < 0.2
    assert band.stock > before[0]
    assert goods.last_month(st, 1)["sold"] > 0 and "vendu" in goods.summary(st, 1, 2)


def test_a_route_needs_a_pact_convoys_and_distance(monkeypatch):
    st, site, band, osite, other = _partners()
    assert "accord commercial" in goods.open_block(st, 1, 2, "sel", True)
    diplo.add_pact(st, 1, 2, "commerce")
    assert goods.open_block(st, 1, 2, "sel", True) == ""
    # Un village : 1 + 1 convois.
    assert goods.convoys(st, 1) == 2
    goods.open_route(st, 1, 2, "sel", True, level=2)
    assert "convois" in goods.open_block(st, 1, 2, "etoffes", False)
    route = goods.find_route(st, 1, 2, "sel")
    assert "existe" in goods.open_block(st, 1, 2, "sel", True, 0) or goods.convoys_used(st, 1) == 2
    assert goods.set_level(st, 1, route, 1) and goods.open_block(st, 1, 2, "etoffes", False) == ""
    monkeypatch.setattr(goods, "TRADE_RANGE", 5)
    assert "Trop loin" in goods.open_block(st, 1, 2, "etoffes", False)


def test_barter_only_the_balance_is_paid():
    st, site, band, osite, other = _partners(known_b=("echanges", "tissage", "chevres"))
    _quiet_ai(st)
    diplo.add_pact(st, 1, 2, "commerce")
    st.tribes[1].goods["poteries"] = 40.0
    st.tribes[2].goods["etoffes"] = 40.0
    # L'acheteur n'a presque rien au grenier : sans troc, il ne paierait pas.
    other.stock = goods.PAY_KEEP_WEEKS * other.population
    goods.open_route(st, 1, 2, "poteries", sell=True)
    goods.open_route(st, 1, 2, "etoffes", sell=False)
    goods.monthly(st)
    sold = goods.find_route(st, 1, 2, "poteries")
    bought = goods.find_route(st, 2, 1, "etoffes")
    assert sold.units > 0 and bought.units > 0
    assert st.tribes[2].goods["poteries"] == sold.units


def test_prices_follow_scarcity():
    st, site, band = _village(known=("poterie",))
    base = goods.value("sel")
    assert goods.price(st, 1, "sel") == round(base * goods.PRICE_HIGH, 2)
    st.tribes[1].goods["sel"] = 3 * goods.reserve(st, 1)
    assert goods.price(st, 1, "sel") == round(base * goods.PRICE_LOW, 2)
    assert goods.price_word(st, 1, "sel") == "bon marche"


def test_ai_trades_with_the_player_who_may_close():
    st, site, band, osite, other = _partners()
    diplo.add_pact(st, 1, 2, "commerce")
    st.tribes[2].knowledge.add("poterie")
    st.tribes[2].goods["poteries"] = 60.0
    goods.ai_routes(st, 2)
    route = goods.find_route(st, 2, 1, "poteries")
    assert route is not None and route.by == 2
    assert any("ouvrent une route" in e.text for e in st.log.entries)
    assert goods.close_route(st, 1, route)
    assert goods.find_route(st, 2, 1, "poteries") is None
    assert any(m.key == "route_fermee" for m in st.diplo.mods[diplo.pair(1, 2)])


def test_routes_die_with_the_pact():
    st, site, band, osite, other = _partners()
    diplo.add_pact(st, 1, 2, "commerce")
    st.tribes[1].goods["poteries"] = 40.0
    goods.open_route(st, 1, 2, "poteries", sell=True)
    diplo.break_pact(st, 1, 2)
    goods.monthly(st)
    assert not goods.all_routes(st)


def test_a_trade_place_and_workshops():
    st, site, band = _village(known=("poterie", "echanges"), res={"argile": (255, 2)})
    before = goods.convoys(st, 1)
    goods.set_teams(st, site, "potiers", 1)
    made = goods.output(st, site, "potiers")
    site.data["buildings"] = ["place", "atelier"]
    assert goods.convoys(st, 1) == before + goods.CONVOYS_PLACE
    assert abs(goods.output(st, site, "potiers") - made * goods.WORKSHOP) < 1e-9


def test_traders_teach_and_reveal_the_way():
    from src.kora.vision import PlayerVision

    st, site, band, osite, other = _partners()
    _quiet_ai(st)
    st.vision = PlayerVision()
    diplo.add_pact(st, 1, 2, "commerce")
    st.tribes[1].goods["poteries"] = 40.0
    goods.open_route(st, 1, 2, "poteries", sell=True)
    goods.monthly(st)
    assert osite.hex in st.vision.explored
    diplo._update_neighbors_now(st)
    assert 2 in st.diplo.neighbors.get(1, [])


def test_routes_survive_a_save(tmp_path):
    from src.kora import persist

    st, site, band, osite, other = _partners()
    _quiet_ai(st)
    diplo.add_pact(st, 1, 2, "commerce")
    st.tribes[1].goods["poteries"] = 40.0
    goods.open_route(st, 1, 2, "poteries", sell=True, level=2)
    goods.monthly(st)
    path = tmp_path / "s.json"
    persist.save_game(st, path)
    loaded, _view = persist.load_game(path, st.world)
    r = goods.find_route(loaded, 1, 2, "poteries")
    assert r is not None and r.level == 2 and r.units == goods.find_route(st, 1, 2, "poteries").units
    assert loaded.tribes[1].trade["hist"] == st.tribes[1].trade["hist"]


def test_a_partner_who_cannot_pay_takes_less():
    st, site, band, osite, other = _partners()
    diplo.add_pact(st, 1, 2, "commerce")
    st.tribes[1].goods["poteries"] = 40.0
    other.stock = goods.PAY_KEEP_WEEKS * other.population + 6.0
    goods.monthly(st)
    got = st.tribes[2].goods.get("poteries", 0.0)
    assert got * goods.CRAFTS["potiers"].value <= 6.0 + 1e-6


def test_far_villages_do_not_trade(monkeypatch):
    st, site, band, osite, other = _partners()
    monkeypatch.setattr(goods, "TRADE_RANGE", 10)
    assert goods.trade_distance(st, 1, 2) > goods.TRADE_RANGE
    assert "Trop loin" in diplo.evaluate(st, 1, 2, "commerce").blocked
    diplo.add_pact(st, 1, 2, "commerce")
    st.tribes[1].goods["poteries"] = 40.0
    goods.monthly(st)
    assert "poteries" not in st.tribes[2].goods
    # Les Routes du sel et du silex doublent la portee.
    st.tribes[2].knowledge.add("routes")
    assert goods.trade_range(st, 1, 2) == 20


def test_ai_villages_put_hands_to_work():
    st, site, band = _village(known=("poterie", "peche"), res={"argile": (255, 2), "poisson": (255, 2)})
    goods.ai_crafts(st, site, band, 20.0)
    assert goods.teams_of(site, "potiers") == 1
    # Grenier plein : pas de pecheurs ; grenier bas : on peche.
    assert goods.teams_of(site, "pecheurs") == 0
    goods.ai_crafts(st, site, band, 4.0)
    assert goods.teams_of(site, "pecheurs") >= 1


# --- croissance, onglet, sauvegarde -------------------------------------------------


def test_a_village_has_children_only_if_food_will_last():
    st, site, band = _village()
    band.stock = 40.0 * band.population
    assert villages.granary_growth(st, band) == 1.0
    band.stock = 0.0
    site.data["forage"] = {s: band.population * 0.5 for s in ("hiver", "printemps", "ete", "automne")}
    assert villages.granary_growth(st, band) == villages.FOOD_LOW_GROWTH


def test_the_tab_is_named_after_the_villages():
    from src.kora import render_panels

    st, site, band = _village()
    assert render_panels.tribe_tab_label(st) == "Village"
    st.bands[5] = Band(5, 1, offset_to_axial(10, 10), 30, 100.0)
    assert render_panels.tribe_tab_label(st) == "Tribu"


def test_goods_and_trade_survive_a_save(tmp_path):
    from src.kora import persist

    st, site, band, osite, other = _partners()
    diplo.add_pact(st, 1, 2, "commerce")
    st.tribes[1].goods["poteries"] = 40.0
    goods.set_teams(st, site, "potiers", 2)
    goods.monthly(st)
    path = tmp_path / "s.json"
    persist.save_game(st, path)
    loaded, _view = persist.load_game(path, st.world)
    assert loaded.tribes[1].goods == {k: round(v, 3) for k, v in st.tribes[1].goods.items()}
    assert loaded.tribes[1].trade.get("hist") == st.tribes[1].trade.get("hist")
    assert goods.teams_of(loaded.sites[site.id], "potiers") == 2
    assert diplo.has_pact(loaded, 1, 2, "commerce")


def test_the_crafts_page_fits_and_answers_clicks():
    from src.kora.render_village import village_hit, village_layout

    for w, h in ((1024, 640), (1280, 720), (1920, 1080)):
        lay = village_layout(w, h, 0, "metiers")
        bx, by, bw, bh = lay["box"]
        for cid, rects in lay["crafts"].items():
            x, y, cw, ch = rects["card"]
            assert y + ch <= by + bh
            assert village_hit(lay, rects["plus"][0] + 3, rects["plus"][1] + 3) == f"vteam+:{cid}"
            assert village_hit(lay, rects["minus"][0] + 3, rects["minus"][1] + 3) == f"vteam-:{cid}"
        page = lay["pages"]["village"]
        assert village_hit(lay, page[0] + 3, page[1] + 3) == "vpage:village"


def test_the_crafts_page_draws():
    os.environ.setdefault("SDL_VIDEODRIVER", "dummy")
    import pygame

    from src.kora import render_village
    from src.kora.render import Renderer

    st, site, band, osite, other = _partners()
    diplo.add_pact(st, 1, 2, "commerce")
    st.tribes[1].goods["poteries"] = 40.0
    goods.set_teams(st, site, "potiers", 1)
    goods.monthly(st)
    pygame.init()
    try:
        r = Renderer(pygame.display.set_mode((1280, 720)))
        render_village.draw_village(r, st, {"village_open": site.id, "village_page": "metiers"})
        assert r.village_hits["page"] == "metiers"
        r.draw_side(st, "tribu", ui={})
        r.draw_side(st, "peuples", ui={"people_pick": 2})
        assert "diplo:commerce" in r.side_hits["items"]
    finally:
        pygame.quit()


def test_peddlers_sell_salt_to_a_village_without_trade():
    from src.kora import events

    st, site, band = _village()
    inst = events.Instance(1, "colporteurs", 1, band_id=1)
    assert all(events.check(st, inst, c) for c in events.EVENTS["colporteurs"].conds)
    before = band.stock
    for eff in events.EVENTS["colporteurs"].options[0].effects:
        events.apply(st, inst, eff)
    assert st.tribes[1].goods["sel"] == 8 and band.stock < before


def test_a_fine_vein_fills_the_reserve_of_what_the_village_makes():
    from src.kora import events

    st, site, band = _village(known=("poterie",), res={"argile": (255, 2)})
    inst = events.Instance(1, "belle_veine", 1, band_id=1)
    assert not events.check(st, inst, ("crafts",))
    goods.set_teams(st, site, "potiers", 1)
    assert events.check(st, inst, ("crafts",))
    events.apply(st, inst, ("craft_bonus", 10))
    assert st.tribes[1].goods["poteries"] == 10


def test_peoples_born_of_yours_count_for_knowledge():
    st, site, band = _village(pop=100)
    tribe = st.tribes[1]
    cond = tech.Cond("pop", 180)
    assert tech.cond_progress(st, tribe, cond)[0] == 100
    kin = Tribe(3, "Luel", 20, False, knowledge=set(tech.START_KNOWLEDGE), culture="souche", origin=1)
    st.tribes[3] = kin
    st.bands[9] = Band(9, 3, offset_to_axial(5, 5), 90, 100.0)
    have, need, label = tech.cond_progress(st, tribe, cond)
    assert have == 190 and have >= need and "nes du votre" in label


def test_imported_salt_teaches_what_salt_is():
    st, site, band = _village()
    tribe = st.tribes[1]
    st.world.set_resources({"sel": bytes(st.world.width * st.world.height)})
    tech.update_practice(st)
    assert tribe.practice.get("res:sel", 0) == 0
    tribe.goods["sel"] = 5.0
    tech.update_practice(st)
    assert tribe.practice.get("res:sel", 0) == 1


def test_the_commerce_screen_fits_answers_and_draws():
    os.environ.setdefault("SDL_VIDEODRIVER", "dummy")
    import pygame

    from src.kora import render_trade
    from src.kora.render import Renderer, side_layout

    for w, h in ((1024, 640), (1280, 720), (1920, 1080)):
        lay = render_trade.trade_layout(w, h, 3, 2, 2)
        bx, by, bw, bh = lay["box"]
        assert bx + bw <= w - 32 and by + bh <= h
        assert render_trade.trade_hit(lay, lay["open"][0] + 3, lay["open"][1] + 3) == "topen"
        lv = lay["routes"][1]["levels"][2]
        assert render_trade.trade_hit(lay, lv[0] + 3, lv[1] + 3, n_routes=3) == "rlevel:1:3"
        chip = lay["goods_chips"]["sel"]
        assert render_trade.trade_hit(lay, chip[0] + 3, chip[1] + 3) == "tgood:sel"
        p = lay["partners"][1]
        assert render_trade.trade_hit(lay, p[0] + 3, p[1] + 3, partners=[7, 9]) == "tpartner:9"
    assert "commerce" in side_layout(1280, 720, army=True, commerce=True)["tabs"]
    st, site, band, osite, other = _partners()
    diplo.add_pact(st, 1, 2, "commerce")
    st.tribes[1].goods["poteries"] = 40.0
    goods.open_route(st, 1, 2, "poteries", sell=True)
    goods.monthly(st)
    pygame.init()
    try:
        r = Renderer(pygame.display.set_mode((1280, 720)))
        render_trade.draw_trade(r, st, {"trade_open": True, "trade_good": "sel"})
        assert r.trade_partners == [2] and len(r.trade_routes) >= 1
        r.draw(st, 0, 0, 3.0, None, ui={"trade_open": True})
    finally:
        pygame.quit()


def test_a_village_that_ate_its_seed_sows_again():
    st, site, band = _village(res={"cereales": (200, 3)})
    # Plus de semences : on seme le grain du grenier (4 semaines gardees).
    site.data["seed"] = 0.0
    band.stock = 20.0 * band.population
    villages.sow(st, site, band)
    assert site.data["fields"] and site.data["sown_ratio"] > 0.9
    assert band.stock >= villages.SOW_KEEP_WEEKS * band.population
    # Plus rien au grenier : les graines sauvages donnent au moins un champ.
    site.data["seed"] = 0.0
    band.stock = 0.0
    villages.sow(st, site, band)
    assert site.data["fields"] and site.data["sown_ratio"] > 0
    assert band.stock == 0.0


def test_trade_events_name_the_partner_and_cost_goods():
    from src.kora import events

    st, site, band, osite, other = _partners()
    _quiet_ai(st)
    diplo.add_pact(st, 1, 2, "commerce")
    st.tribes[1].goods["poteries"] = 40.0
    goods.open_route(st, 1, 2, "poteries", sell=True)
    inst = events.Instance(1, "porteurs_perdus", 1, band_id=1)
    assert not events.check(st, inst, ("trade_partner",))
    goods.monthly(st)
    assert events.check(st, inst, ("trade_partner",)) and inst.other == 2
    before = st.tribes[1].goods["poteries"]
    events.apply(st, inst, ("lose_goods", 6))
    assert st.tribes[1].goods["poteries"] == before - 6


def test_routes_show_only_in_the_commerce_map_mode(monkeypatch):
    os.environ.setdefault("SDL_VIDEODRIVER", "dummy")
    import pygame

    from src.kora.render import MAP_MODES, Renderer

    assert "commerce" in dict(MAP_MODES)
    st, site, band, osite, other = _partners()
    diplo.add_pact(st, 1, 2, "commerce")
    st.tribes[1].goods["poteries"] = 40.0
    goods.open_route(st, 1, 2, "poteries", sell=True)
    goods.monthly(st)
    pygame.init()
    try:
        r = Renderer(pygame.display.set_mode((1280, 720)))
        calls = []
        real = r.draw_trade_routes
        monkeypatch.setattr(r, "draw_trade_routes", lambda *a, **k: (calls.append(1), real(*a, **k)))
        r.map_mode = "zones"
        r.draw(st, 0, 0, 2.0, None, ui={})
        assert not calls
        r.map_mode = "commerce"
        r.draw(st, 0, 0, 2.0, None, ui={})
        assert calls
    finally:
        pygame.quit()
