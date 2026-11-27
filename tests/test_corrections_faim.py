"""Les corrections de la faim et de l'economie (revue du 2026-11-27) :
la recolte avant les repas, le creux avant la recolte (villages.food_low),
l'etape des champs a la saison locale, la fenetre de fondation, les routes
qui clignotaient, le grain (tresor, vendeurs), le grenier qui deborde, le
peage a la couture du monde, les batiments lus dans leur table, les biens
sauves sans arrondi."""

from types import SimpleNamespace

from src.kora import batiments, decisions, diplo, goods, grain, money, persist, places, sim, villages
from src.kora.clock import Clock
from src.kora.gamestate import GameState
from src.kora.types import Season, Terrain, Tribe
from src.kora.world import make_filled_world, offset_to_axial
from test_goods import CENTER, _partners, _quiet_ai
from test_grain import _two
from test_ost_siege import _state, _village


# --- la semaine de la recolte : on recolte, puis on mange (G7) -------------------------


def test_la_semaine_de_la_recolte_on_recolte_avant_de_manger():
    st = _state()
    band, site = _village(st, 1, 1, pop=900, col=20, row=15)
    assert site.data.fields, "fonde en été : des champs semes (tard)"
    for _ in range(30):
        if villages.harvest_in(st, site) == 1:
            break
        band.stock = 10.0 * band.population
        sim.tick(st)
    assert villages.harvest_in(st, site) == 1
    # Le grenier est vide la veille de la moisson ; la cueillette ne nourrit
    # pas 900 personnes (avant la correction : 115 morts cette semaine-la).
    band.stock = 0.0
    pop = band.population
    sim.tick(st)
    assert st.world.hex_season(site.hex) is Season.AUTOMNE and not site.data.fields, "la récolte est faite"
    assert band.famine_tick < st.tick_count - 1, "personne ne meurt de faim la semaine de la récolte"
    assert band.population >= pop


# --- le creux avant la recolte (G8) ----------------------------------------------------


def _autumn_village(stock_weeks: float, memo: dict):
    """Un village juste apres sa recolte (l'automne), le grenier a
    stock_weeks semaines, une collecte par saison (part de ce qu'on mange)."""
    st = _state()
    band, site = _village(st, 1, 1, pop=200, col=20, row=15)
    st.clock.week = 30
    st.world.fill_season(Season.AUTOMNE)
    site.data.season = Season.AUTOMNE.value
    site.data.season_at = st.tick_count
    site.data.fields = []
    site.data.seed = villages.SEED * 8
    site.data.forage = {k: v * band.population for k, v in memo.items()}
    band.stock = stock_weeks * band.population
    st.tribes[1].is_player = False
    return st, band, site


# Un hiver vide que le printemps et l'ete rattrapent.
LEAN_WINTER = {"automne": 0.5, "hiver": 0.2, "printemps": 1.5, "ete": 2.0}


def test_le_creux_de_l_hiver_se_voit_meme_si_l_ete_le_rattrape():
    st, band, site = _autumn_village(10.0, LEAN_WINTER)
    left, end = villages.food_outlook(st, site, band)
    at, low = villages.food_low(st, site, band)
    # Le jour de la recolte, le grenier serait plein : la marge dit "sur".
    assert end > 0
    # Le creux, lui, est sous zero, en hiver ou a sa fin.
    assert low < 0 < at < left
    assert at >= 9, "apres l'automne"
    # Ceux qui decident le lisent : la disette en vue, l'alerte, le rationnement.
    assert grain.shortfall(st, band) > 0
    assert sim.band_hunger(st, band) == "disette"
    assert decisions._ration_ai(st, 1) == 1.0
    assert decisions.status(st, 1, "rationner")[0] == "possible", "rationner dès la récolte si elle ne suffira pas"
    assert villages.granary_growth(st, band) == villages.FOOD_LOW_GROWTH


def test_un_grenier_qui_tient_n_a_pas_de_creux_negatif():
    st, band, site = _autumn_village(30.0, LEAN_WINTER)
    at, low = villages.food_low(st, site, band)
    assert low > 0 and grain.shortfall(st, band) == 0
    assert decisions._ration_ai(st, 1) == 0.0
    # La veille de la recolte, le creux est maintenant : rien a manger avant.
    st2, band2, site2 = _autumn_village(3.0, {"automne": 0.0, "hiver": 0.0, "printemps": 0.0, "ete": 0.0})
    st2.clock.week = 27 + st2.world.season_lag(site2.hex, True) - 1
    assert villages.harvest_in(st2, site2) == 1
    assert villages.food_low(st2, site2, band2) == (0, 3.0)


def test_le_rationnement_ecarte_le_creux():
    st, band, site = _autumn_village(10.0, LEAN_WINTER)
    _at, low = villages.food_low(st, site, band)
    assert decisions.take(st, 1, "rationner") is not None
    assert villages.food_low(st, site, band)[1] > low


# --- la prochaine etape des champs : la saison LOCALE (regle 4.1) ---------------------


def test_l_etape_des_champs_suit_la_saison_locale():
    world = make_filled_world(40, 160, Terrain.PLAINE, wrap_x=True)
    st = GameState(world=world, clock=Clock(), tribes={}, bands={}, next_band_id=1)
    world.fill_season(st.clock.season())
    rows = (0, 15, 30, 50, 70, 79, 80, 95, 130, 159)
    spots = {r: SimpleNamespace(hex=offset_to_axial(5, r)) for r in rows}
    said = {r: [] for r in rows}
    turns = {r: [] for r in rows}
    last = {r: world.hex_season(spots[r].hex) for r in rows}
    for step in range(3 * 52):
        st.clock.advance_week()
        sim.apply_season_spread(st)
        st.tick_count += 1
        for r in rows:
            now = world.hex_season(spots[r].hex)
            if now is not last[r]:
                turns[r].append((st.tick_count, now))
                last[r] = now
            if step >= 52:
                label, left = villages.next_step(st, spots[r])
                said[r].append((st.tick_count, label, left))
    wrong = []
    for r in rows:
        for tick, label, left in said[r]:
            want = Season.AUTOMNE if label.startswith("Récolte") else Season.PRINTEMPS
            nxt = next((t for t, s in turns[r] if t > tick and s is want), None)
            if nxt is not None and nxt - tick != left:
                wrong.append((r, tick, label, left, nxt - tick))
    assert not wrong, wrong[:5]


# --- la fenetre "Fonder un village" ----------------------------------------------------


def test_fonder_en_ete_promet_la_vraie_premiere_recolte():
    from src.kora import chiefs, sites
    from src.kora.types import Band

    for season, week in ((Season.PRINTEMPS, 5), (Season.ETE, 20)):
        st = _state()
        st.clock.week = week
        st.world.fill_season(season)
        b = Band(1, 1, offset_to_axial(20, 15), 200, 4000.0)
        st.bands[1] = b
        chiefs.ensure(st)
        sites.make_camp(st, 1)
        info = villages.found_preview(st, 1)
        site = villages.found(st, 1)
        real = villages.expected_harvest(st, site, b)
        assert abs(info["harvest"] - real) <= 0.15 * real, (season, info["harvest"], real)
        assert info["sow_now"] and info["late_sow"] is (season is Season.ETE)
        assert info["harvest_in"] == villages.harvest_in(st, site) and not info["next_year"]


def test_fonder_en_automne_dit_l_an_prochain():
    from src.kora import chiefs, sites
    from src.kora.types import Band

    st = _state()
    st.clock.week = 33
    st.world.fill_season(Season.AUTOMNE)
    b = Band(1, 1, offset_to_axial(20, 15), 200, 4000.0)
    st.bands[1] = b
    chiefs.ensure(st)
    sites.make_camp(st, 1)
    info = villages.found_preview(st, 1)
    assert not info["sow_now"] and info["next_year"]
    assert info["harvest_in"] > 40 and info["harvest"] > 0
    site = villages.found(st, 1)
    assert not site.data.fields and site.data.seed > 0, "rien n'est seme avant le printemps"
    assert villages.harvest_in(st, site) == info["harvest_in"]


# --- les routes qui clignotaient --------------------------------------------------------


def _three():
    """Le peuple 2 (IA) vend des poteries ; 1 et 3 en manquent."""
    from src.kora import chiefs, sites, tech
    from src.kora.types import Band

    st, site, band, osite, other = _partners()
    _quiet_ai(st)
    t3 = Tribe(3, "Teru", 30, False, knowledge=set(st.tribes[2].knowledge), culture="steppe")
    st.tribes[3] = t3
    b3 = Band(3, 3, offset_to_axial(CENTER[0] - 14, CENTER[1]), 120, 2000.0)
    st.bands[3] = b3
    st.next_band_id = 4
    chiefs.ensure(st)
    sites.make_camp(st, 3)
    villages.found(st, 3)
    tech.invalidate()
    for a, b in ((1, 2), (2, 3), (1, 3)):
        diplo.make_contact(st, a, b, quiet=True)
        diplo.add_pact(st, a, b, "commerce")
    for tid in (1, 3):
        st.tribes[tid].goods.pop("poteries", None)
    return st


def test_une_route_garde_la_meme_reserve_qui_que_soit_son_ouvreur():
    st = _three()
    st.tribes[2].goods["poteries"] = goods.reserve(st, 2) + 1.5
    sold = goods.open_route(st, 2, 1, "poteries", sell=True)
    bought = goods.open_route(st, 3, 2, "poteries", sell=False)
    assert goods._flow(st, sold) == goods._flow(st, bought)
    assert 0 < goods._flow(st, sold)[0] <= 1.5 + 1e-9


def test_l_ia_n_ouvre_pas_plus_de_routes_que_son_surplus_net():
    st = _three()
    st.tribes[2].goods["poteries"] = goods.reserve(st, 2) + 3.0
    goods.ai_routes(st, 2)
    out = [r for r in goods.all_routes(st) if r.exporter == 2 and r.good == "poteries"]
    assert len(out) == 1, "3 charges de trop : une route (2 par convoi), pas deux"
    # L'acheteur ne rouvre pas une route de plus chez un vendeur deja promis.
    goods.ai_routes(st, 3)
    assert len([r for r in goods.all_routes(st) if r.exporter == 2 and r.good == "poteries"]) == 1


def test_une_route_fermee_ne_se_rouvre_pas_quelques_mois_apres():
    st = _three()
    st.tribes[2].goods["poteries"] = goods.reserve(st, 2) + 3.0
    goods.ai_routes(st, 2)
    route = next(r for r in goods.all_routes(st) if r.exporter == 2)
    buyer = route.importer
    route.idle = goods.IDLE_CLOSE
    goods.ai_routes(st, 2)
    assert route not in goods.all_routes(st)
    st.tribes[2].goods["poteries"] = goods.reserve(st, 2) + 3.0
    for tid in (2, 3):
        goods.ai_routes(st, tid)
    assert goods.find_route(st, 2, buyer, "poteries") is None, "ni le vendeur, ni l'acheteur ne la rouvrent"
    # Le souvenir passe la sauvegarde, puis s'oublie.
    loaded, _view = persist.loads_game(persist.dumps_game(st), st.world)
    assert loaded.tribes[2].trade["shut"] == st.tribes[2].trade["shut"]
    goods.all_routes(st).clear()
    st.tick_count += goods.REOPEN_WEEKS
    goods.ai_routes(st, 2)
    assert goods.find_route(st, 2, buyer, "poteries") is not None


# --- le grain ---------------------------------------------------------------------------


def test_un_achat_limite_par_le_tresor_ne_le_met_pas_sous_zero():
    st, buyer, bsite, seller, ssite = _two()
    for m in (3.0061, 7.12349, 0.99999, 12.345678):
        st.tribes[1].money = m
        buyer.stock = 60.0
        q = grain.quote(st, 1, bsite.id)
        if q["why"]:
            continue
        assert q["sicles"] <= m
        assert grain.buy(st, 1, bsite.id) == ""
        assert st.tribes[1].money >= 0.0, m


def test_on_n_achete_pas_le_grain_d_un_village_qui_voit_venir_la_disette():
    st, buyer, bsite, seller, ssite = _two()
    st.tribes[3].is_player = False
    # Un second village du vendeur (une vieille partie, un pays), le mieux
    # pourvu : grain.buy le videait le premier.
    lean, lsite = _village(st, 2, 2, pop=200, col=40)
    lean.tribe_id = lsite.tribe_id = 3
    # Juste apres la recolte : ce village-la a beaucoup en grenier, mais
    # rien ne se cueille jusqu'a la prochaine : son creux est negatif.
    st.clock.week = 30
    st.world.fill_season(Season.AUTOMNE)
    for s in (bsite, ssite, lsite):
        s.data.season, s.data.season_at = Season.AUTOMNE.value, st.tick_count
        s.data.fields = []
    ssite.data.forage = {k: 2.0 * seller.population for k in ("printemps", "ete", "automne", "hiver")}
    lsite.data.forage = {k: 0.0 for k in ("printemps", "ete", "automne", "hiver")}
    seller.stock = 15.0 * seller.population
    lean.stock = 30.0 * lean.population
    assert grain.shortfall(st, lean) > 0 and grain.shortfall(st, seller) == 0
    assert grain.spare(st, 3) == seller.stock - grain.KEEP_WEEKS * seller.population
    before = lean.stock, seller.stock
    assert grain.buy(st, 1, bsite.id) == ""
    assert lean.stock == before[0], "le village qui voit venir la disette ne vend rien"
    assert seller.stock < before[1]


# --- la recolte qui deborde du grenier ---------------------------------------------------


def test_une_recolte_qui_deborde_le_dit():
    from src.kora.bands import stock_max

    st = _state()
    band, site = _village(st, 1, 1, pop=200, col=20, row=15)
    band.stock = stock_max(band, st)
    site.data.seed = villages.SEED * 12
    crop = villages.harvest(st, site, band)
    assert crop > 0
    assert any("n'y ont pas tenu" in e.text for e in st.log.entries)


# --- le peage a la couture du monde -------------------------------------------------------


def test_le_peage_d_une_route_qui_passe_la_couture():
    from src.kora import chiefs, sites, tech
    from src.kora.types import Band

    world = make_filled_world(60, 30, Terrain.PLAINE, wrap_x=True)
    known = set(tech.START_KNOWLEDGE) | {"huttes", "semis", "sedentarite", "echanges"}
    tribes = {
        1: Tribe(1, "Kora", 30, True, knowledge=set(known), culture="joueur"),
        2: Tribe(2, "Akor", 30, False, knowledge=set(known), culture="steppe"),
        3: Tribe(3, "Passeurs", 30, False, knowledge=set(known) | {"peages"}, culture="steppe"),
    }
    st = GameState(world=world, clock=Clock(), tribes=tribes, bands={}, next_band_id=3)
    world.fill_season(st.clock.season())
    for bid, col in ((1, 55), (2, 5)):
        st.bands[bid] = Band(bid, bid, offset_to_axial(col, 15), 100, 2000.0)
        chiefs.ensure(st)
        sites.make_camp(st, bid)
        villages.found(st, bid)
    tech.invalidate()
    assert tech.bonuses(tribes[3]).tolls
    # Les Passeurs tiennent le pays de la couture (colonnes 58 a 2), entre
    # les deux villages ; le milieu "a plat" serait la colonne 30.
    world._influence = {}
    for col in (58, 59, 0, 1, 2):
        for row in range(13, 18):
            world._influence[(col, row)] = {3: 1.0}

    route = SimpleNamespace(exporter=1, importer=2, good="sel")
    assert money.toll_owner(st, route) == 3


# --- les batiments : la table qu'affiche l'ecran est celle que le jeu compte -------------


def test_les_effets_des_batiments_se_lisent_dans_leur_table(monkeypatch):
    st, site, band, osite, other = _partners()
    site.data.buildings["place"] = 1
    before = goods.convoys(st, 1)
    monkeypatch.setitem(batiments.VALUES, "place", {"convois": (5,), "prix": (1.3,)})
    assert goods.convoys(st, 1) == before - 2 + 5
    route = SimpleNamespace(exporter=1, importer=2, good="poteries")
    monkeypatch.setattr(goods, "price", lambda s, t, g: 10.0)
    monkeypatch.setattr(goods.situations, "route_mult", lambda s, r: 1.0)
    monkeypatch.setattr(goods.chiefdom, "trade_mult", lambda s, t: 1.0)
    assert goods.route_price(st, route) == 13.0
    # La Pierre dressee : l'influence vient de la meme table.
    assert batiments.VALUES["pierre"]["influence"] is places.STONE_INFLUENCE
    site.data.buildings["pierre"] = 1
    assert places.influence_radius(site, 4) == 4 + batiments.value(site, "pierre", "influence")


# --- les biens se sauvent sans arrondi -------------------------------------------------------


def test_les_biens_relus_sont_ceux_de_la_partie():
    st, site, band, osite, other = _partners()
    st.tribes[1].goods = {"poteries": 12.3456789123, "sel": 0.0004321}
    loaded, _view = persist.loads_game(persist.dumps_game(st), st.world)
    assert loaded.tribes[1].goods == st.tribes[1].goods
