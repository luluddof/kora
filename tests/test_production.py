"""Le savoir-faire des villages (production.py), la surproduction et
l'effondrement du commerce (situations.py), les crises que l'on voit venir."""

from src.kora import diplo, goods, persist, places, production, sites, situations, tech, villages
from src.kora.sim import new_game
from src.kora.gamestate import PLAYER_TRIBE_ID
from src.kora.situations import SPECS
from src.kora.types import Terrain
from src.kora.world import make_filled_world


def _world():
    return make_filled_world(60, 30, Terrain.VALLEE, wrap_x=True)


def _villages_state(tids=(1, 2)):
    st = new_game(_world())
    st.story = True
    for tid in tids:
        for t in (t for t in tech.TECHS if not tech.TECHS[t].drawn):
            tech.grant(st.tribes[tid], t)
        band = next(b for b in st.bands.values() if b.tribe_id == tid)
        band.population, band.stock = 130, 3000.0
        sites.make_camp(st, band.id)
        villages.found(st, band.id)
    tech.invalidate()
    return st


def _site(st, tid):
    return next(s for s in st.sites.values() if s.kind == "village" and s.tribe_id == tid)


def test_no_know_how_before_the_villages():
    st = new_game(_world())
    for _ in range(6):
        production.monthly(st)
    assert all(not t.efficiency for t in st.tribes.values())


def test_hungry_villages_learn_to_get_more_food_slowly():
    st = _villages_state()
    band = places.band_of(st, _site(st, 1))
    tribe = st.tribes[1]
    band.stock = 0.0
    before = villages.food_mult(st, band)
    for _ in range(12):
        band.stock = 0.0
        production.monthly(st)
    eff = production.of(st, 1, "collecte")
    assert 1.01 < eff < 1.05, eff
    assert villages.food_mult(st, band) > before
    # Avec des greniers pleins, rien ne bouge.
    band.stock = band.population * 60
    production.monthly(st)
    assert production.of(st, 1, "collecte") == eff
    assert tribe.efficiency["collecte"] <= production.EFF_MAX


def test_a_craft_in_short_supply_gains_know_how_and_produces_more():
    st = _villages_state()
    site = _site(st, 1)
    # Un gros village : une equipe ne suffit plus a ce qu'il use.
    places.band_of(st, site).population = 400
    goods.set_teams(st, site, "tisserands", 1)
    st.tribes[1].goods.pop("etoffes", None)
    out = goods.output(st, site, "tisserands")
    assert out > 0
    for _ in range(10):
        st.tribes[1].goods["etoffes"] = 0.0
        production.monthly(st)
    assert production.of(st, 1, "tisserands") > 1.02
    assert goods.output(st, site, "tisserands") > out


def test_a_glut_warns_then_becomes_a_crisis_that_can_be_solved():
    st = _villages_state()
    site = _site(st, 1)
    tribe = st.tribes[1]
    goods.set_teams(st, site, "tisserands", 3)
    tribe.efficiency["tisserands"] = 1.2
    for _ in range(production.GLUT_RISK):
        tribe.goods["etoffes"] = goods.CAP
        production.monthly(st)
    assert tribe.glut["etoffes"] >= production.GLUT_RISK
    situations._risks(st)
    risk = situations.risks_of(st, 1)
    assert any(sid == "surproduction" for sid, _t in risk), "on la voit venir"
    assert any("Risque : la surproduction" in e.text for e in st.log.entries)
    # Les conjonctures ne previennent jamais.
    assert all(SPECS[sid].kind == situations.CRISE for sid, _t in risk)
    tribe.glut["etoffes"] = production.GLUT_CRISIS
    cands = SPECS["surproduction"].candidates(st)
    center, radius, tids, data = next(c for c in cands if 1 in c[2])
    assert data == {"good": "etoffes"}
    calm = tech.bonuses(tribe).stability
    inst = situations._start(st, SPECS["surproduction"], center, radius, tids, data)
    situations._sync_effects(st)
    assert tech.bonuses(tribe).stability < calm
    assert goods.price(st, 1, "etoffes") < goods.value("etoffes") * goods.PRICE_LOW + 1e-6
    teams = goods.teams_of(site, "tisserands")
    assert teams >= 1
    assert situations.act(st, inst.uid, 1, "renvoyer").endswith("fait.")
    assert goods.teams_of(site, "tisserands") == teams - 1
    situations.act(st, inst.uid, 1, "offrandes")
    assert tribe.goods["etoffes"] < goods.CAP * 0.5
    for _ in range(4):
        st.tick_count += 4
        situations.monthly(st)
        if inst.outcome:
            break
    assert inst.outcome == "resolue"
    assert tech.bonuses(tribe).stability == calm, "tout redevient comme avant"
    assert production.of(st, 1, "tisserands") == 1.2, "le savoir-faire n'est pas perdu"


def test_a_failed_glut_costs_know_how_and_spreads_a_trade_collapse():
    st = _villages_state((1, 2, 3))
    diplo.make_contact(st, 1, 2)
    diplo.make_contact(st, 2, 3)
    diplo.add_pact(st, 1, 2, "commerce")
    diplo.add_pact(st, 2, 3, "commerce")
    tribe = st.tribes[1]
    tribe.efficiency["potiers"] = 1.3
    tribe.efficiency["sauniers"] = 1.2
    st.tribes[2].efficiency["tisserands"] = 1.2
    goods.set_teams(st, _site(st, 2), "tisserands", 1)
    inst = situations._start(st, SPECS["surproduction"], _site(st, 1).hex, 0, [1], {"good": "poteries"})
    inst.until = st.tick_count
    tribe.goods["poteries"] = goods.CAP
    situations.monthly(st)
    assert inst.outcome == "ratee"
    assert abs(production.of(st, 1, "potiers") - 1.15) < 1e-9
    crash = next(s for s in st.situations if s.sid == "effondrement" and not s.outcome)
    assert set(crash.participants) == {1, 2}
    route = diplo.TradeRoute(2, 3, "etoffes", 1, 2, 0)
    assert situations.route_mult(st, route) == 0.6
    # Le mal gagne les partenaires des partenaires (une profondeur de plus).
    for k in range(30):
        st.tick_count += 4
        SPECS["effondrement"].month(st, crash)
        if 3 in crash.participants:
            break
    assert 3 in crash.participants and crash.data["depth"]["3"] == 2
    assert production.of(st, 2, "tisserands") < 1.2, "les artisans perdent la main"
    # Fermer ses marches : on en sort, sans pouvoir gagner.
    situations.act(st, crash.uid, 3, "fermer")
    assert 3 not in crash.participants


def test_know_how_and_gluts_are_saved():
    st = _villages_state()
    st.tribes[1].efficiency = {"agriculture": 1.12, "potiers": 1.05}
    st.tribes[1].glut = {"sel": 4}
    loaded, _view = persist.loads_game(persist.dumps_game(st), _world())
    assert loaded.tribes[1].efficiency == {"agriculture": 1.12, "potiers": 1.05}
    assert loaded.tribes[1].glut == {"sel": 4}


def test_the_monument_rises_in_stages_and_only_the_winner_keeps_it():
    st = _villages_state((1, 2))
    s1, s2 = _site(st, 1), _site(st, 2)
    b1, b2 = places.band_of(st, s1), places.band_of(st, s2)
    assert villages.building_status(st, s1, "monument") == "verrouille"
    assert "grands travaux" in villages.build_block_site(st, s1, "monument")
    inst = situations._start(st, SPECS["travaux"], s1.hex, 40, [1, 2], {})
    assert villages.building_status(st, s1, "monument") == "possible"
    for band, site, stages in ((b1, s1, 3), (b2, s2, 1)):
        for k in range(stages):
            band.stock = 3000.0
            weeks = villages.build_weeks(site, "monument")
            assert villages.build(st, band.id, "monument")
            for _ in range(weeks):
                villages._advance_works(st, site, band)
            assert places.monument_stages(site) == k + 1
    assert villages.build_weeks(s1, "monument") > villages.BUILDINGS["monument"].weeks, "chaque etape est plus longue"
    assert "Grand monument · 3/" in villages.building_name(s1, "monument")
    SPECS["travaux"].month(st, inst)
    assert inst.participants[1]["score"] == 3 and inst.participants[2]["score"] == 1
    prestige = villages.winter_prestige(st, 1)
    inst.until = st.tick_count
    situations.monthly(st)
    assert inst.outcome == "gagnee" and inst.winner == 1
    assert places.monument_stages(s1) == 3 and places.has(s1, "monument")
    assert places.monument_stages(s2) == 0 and not places.has(s2, "monument"), "le monument du vaincu est abattu"
    assert tech.bonuses(st.tribes[1]).prestige_gain > 1.0
    from src.kora.bands import gain_prestige

    st.tribes[1].prestige = 10
    assert gain_prestige(st, st.tribes[1], 10) == 13
    assert villages.winter_prestige(st, 1) == prestige
    # Le vainqueur ne revit plus les grands travaux.
    st.clock.week = 18
    st.situation_last.clear()
    assert not any(1 in tids for _c, _r, tids, _d in SPECS["travaux"].candidates(st))


def test_the_ai_raises_its_monument_during_the_works():
    from src.kora import ai

    st = _villages_state((1, 2))
    s2 = _site(st, 2)
    band = places.band_of(st, s2)
    situations._start(st, SPECS["travaux"], s2.hex, 40, [1, 2], {})
    band.stock = band.population * 60.0
    st.clock.week = 20
    for k in range(3):
        if places.works(s2):
            break
        ai._village_ai(st, band, band.stock / band.population)
    job = places.works(s2)
    assert job and job[0] == "monument"


def test_crisis_risks_warn_the_player_in_the_journal_once():
    st = new_game(_world())
    st.story = True
    band = next(b for b in st.bands.values() if b.tribe_id == PLAYER_TRIBE_ID)
    band.population = 90
    other = next(b for b in st.bands.values() if b.tribe_id == 3)
    other.position = band.position
    situations._risks(st)
    assert any(sid == "mal" for sid, _t in situations.risks_of(st, PLAYER_TRIBE_ID))
    n = sum(1 for e in st.log.entries if e.text.startswith("Risque : le mal qui court"))
    situations._risks(st)
    assert sum(1 for e in st.log.entries if e.text.startswith("Risque : le mal qui court")) == n == 1
    # Une IA ne recoit rien.
    assert 3 not in st.situation_risks
