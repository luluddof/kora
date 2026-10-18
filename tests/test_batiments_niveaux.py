"""Les batiments a plusieurs niveaux (2026-10-18, la refonte demandee par le
joueur) : batir plusieurs fois le meme batiment ; des batiments peu couteux
(huttes, fosses) et des couteux (maison longue, palissade doublee, maison
du conseil) ; le terrain du village ; les logements et l'entassement ; la
file des chantiers ; demolir ; les vieilles parties ; l'IA ; les ordres ;
l'ecran, clique dans la vraie boucle."""

import random

import pygame

from src.kora import ai, batiments, commands, persist, places, villages
from src.kora.places import _village_data
from test_app_clicks import _center, _click, _key, _play
from test_goods import _village

ALL = ("palissade", "enceintes", "greniers", "maisons", "chevres", "guetteurs", "rites", "ancetres", "megalithes", "chefferie", "poterie", "echanges")


def _finish(st, site):
    """Laisser passer les semaines jusqu'a la fin des chantiers."""
    band = places.band_of(st, site)
    for _ in range(400):
        if not places.works(site) and not site.data.queue:
            break
        batiments.advance_works(st, site, band)


def test_a_building_rises_level_after_level_and_does_more():
    st, site, band = _village(ALL, pop=300, stock=1e6)
    weeks = []
    for n in (1, 2, 3):
        assert batiments.build(st, band.id, "grenier")
        _finish(st, site)
        assert places.level(site, "grenier") == n
        weeks.append(villages.store_weeks(st, band))
    assert weeks[0] < weeks[1] < weeks[2], "chaque niveau garde plus de grain"
    assert batiments.building_status(st, site, "grenier") == "haut"
    assert "au plus haut" in batiments.build_block(st, band.id, "grenier")
    assert batiments.building_name(site, "palissade") == "Palissade"
    site.data.buildings["palissade"] = 2
    assert batiments.building_name(site, "palissade") == "Double palissade"
    assert villages.defense_mult(st, band) > batiments.PALISADE_DEFENSE


def test_level_one_does_what_the_old_buildings_did():
    st, site, band = _village(ALL, pop=150)
    site.data.buildings = {"grenier": 1, "enclos": 1, "puits": 1, "palissade": 1, "tour": 1, "maison_longue": 1}
    assert batiments.value(site, "grenier", "reserve") == 8 and batiments.value(site, "grenier", "gate", 1.0) == 0.6
    assert batiments.value(site, "palissade", "defense", 1.0) == 1.6 and batiments.value(site, "tour", "defense", 1.0) == 1.15
    assert batiments.value(site, "maison_longue", "croissance", 1.0) == 1.2 and batiments.value(site, "puits", "fievres", 1.0) == 0.6


def test_cheap_and_costly_buildings_and_the_price_of_a_level():
    st, site, band = _village(ALL, pop=200, stock=1e6)
    tiers = {b.tier for b in batiments.BUILDINGS.values()}
    assert tiers == {"peu", "moyen", "cher"}
    assert batiments.build_cost(st, site, "huttes") < batiments.build_cost(st, site, "maisons") < batiments.build_cost(st, site, "maison_longue")
    assert batiments.build_cost(st, site, "conseil") > batiments.build_cost(st, site, "maison_longue")
    # Un niveau de plus coute plus cher ; les huttes, presque pas.
    assert batiments.build_cost(st, site, "palissade", 2) > 1.4 * batiments.build_cost(st, site, "palissade", 1)
    assert batiments.build_cost(st, site, "huttes", 6) < 1.4 * batiments.build_cost(st, site, "huttes", 1)
    assert batiments.build_weeks(site, "palissade", 3) > batiments.build_weeks(site, "palissade", 1)
    # Un niveau peut demander un savoir de plus (la palissade et son fosse).
    assert batiments.needs_for("palissade", 3) == "enceintes" and batiments.needs_for("palissade", 2) == "palissade"


def test_the_village_ground_fills_and_grows_with_its_people():
    st, site, band = _village(ALL, pop=60, stock=1e6)
    room = batiments.space(st, site)
    assert room == batiments.BASE_SPACE + 60 // batiments.SPACE_POP
    site.data.buildings = {"fosses": room}
    assert batiments.used_space(site) == room
    assert "terrain" in batiments.build_block(st, band.id, "puits")
    assert batiments.build_block(st, band.id, "palissade") == "", "la palissade est autour : elle ne prend pas de terrain"
    band.population = 60 + batiments.SPACE_POP
    assert batiments.build_block(st, band.id, "puits") == ""
    band.population = 10
    assert batiments.space(st, site) >= batiments.used_space(site), "on ne perd pas ce qui est bâti"


def test_houses_lodge_people_and_crowding_costs():
    st, site, band = _village(ALL, pop=100, stock=1e6)
    site.data.buildings.pop("huttes", None)
    assert batiments.housing(site) == batiments.BASE_HOUSING
    site.data.buildings["huttes"] = 2
    assert batiments.housing(site) == batiments.BASE_HOUSING + 40
    band.population = batiments.housing(site)
    calm = villages.stability(st, site, band)
    grow = villages.growth_mult(st, band)
    band.population += 30
    assert batiments.crowding(st, site, band) == 30
    assert villages.stability(st, site, band) < calm
    assert villages.growth_mult(st, band) < grow * 0.7, "entasses, ils font moins d'enfants"
    assert any("sans toit" in label for label, _v in villages.stability_parts(st, site, band))
    # On n'abat pas le toit de ceux qui y vivent.
    assert "toit" in batiments.demolish_block(st, site, "huttes")


def test_the_queue_waits_pays_late_and_can_be_emptied():
    st, site, band = _village(ALL, pop=120, stock=1e6)
    assert batiments.build(st, band.id, "huttes")
    stock = band.stock
    for bid in ("huttes", "fosses", "foyer", "puits"):
        assert batiments.build(st, band.id, bid)
    assert band.stock == stock, "la file ne paie rien d'avance"
    assert len(site.data.queue) == batiments.QUEUE_MAX
    assert "pleine" in batiments.build_block(st, band.id, "sechoir")
    assert batiments.unqueue(st, site, 3) and site.data.queue == ["huttes", "fosses", "foyer"]
    # Sans vivres, le suivant attend (et dit pourquoi), puis repart.
    _finish_one = places.works(site)[1]
    band.stock = 0.0
    for _ in range(_finish_one):
        batiments.advance_works(st, site, band)
    assert not places.works(site) and "vivres" in batiments.queue_block(st, site, 0)
    band.stock = 1e6
    batiments.advance_works(st, site, band)
    assert places.works(site)[0] == "huttes" and band.stock < 1e6


def test_demolish_gives_the_ground_back():
    st, site, band = _village(ALL, pop=120, stock=1e6)
    site.data.buildings["foyer"] = 2
    used = batiments.used_space(site)
    assert batiments.demolish(st, site, "foyer")
    assert places.level(site, "foyer") == 1 and batiments.used_space(site) == used - 1
    assert batiments.demolish(st, site, "foyer") and not places.has(site, "foyer")
    assert batiments.demolish_block(st, site, "foyer") and batiments.demolish_block(st, site, "monument")


def test_a_new_village_has_a_roof_for_everyone():
    st, site, band = _village(pop=180)
    assert batiments.housing(site) >= 180
    assert places.level(site, "huttes") >= 1


def test_old_saves_keep_their_buildings_and_house_their_people():
    data = _village_data({"band": 1, "buildings": ["grenier", "puits", "monument"], "monument": 2})
    assert data.buildings == {"grenier": 1, "puits": 1} and data.monument == 2
    assert persist._older("0.23.0", "0.24.0") and not persist._older("0.24.0", "0.24.0") and persist._older("", "0.24.0")
    st, site, band = _village(pop=260)
    site.data.buildings = {"grenier": 1}
    assert batiments.crowding(st, site, band) > 0
    assert batiments.house_old_villages(st) > 0
    assert batiments.crowding(st, site, band) == 0


def test_the_ai_houses_its_people_first():
    st, site, band = _village(ALL, pop=150)
    band.population = int(batiments.housing(site) * 0.95)
    assert batiments.ai_choice(st, site, band)[:2] == ["maisons", "huttes"]
    band.population = 50
    assert batiments.ai_choice(st, site, band)[0] == "palissade", "sinon l'ordre d'avant"


def test_pillage_takes_one_level():
    st, site, band = _village(ALL, pop=150)
    site.data.buildings = {"grenier": 2}

    class Always(random.Random):
        def random(self):
            return 0.0
    assert villages.pillaged(st, band, Always()) == "Grenier surélevé"
    assert places.level(site, "grenier") == 1


def test_the_orders_build_unqueue_and_demolish():
    st, site, band = _village(ALL, pop=150, stock=1e6)
    assert commands.apply(st, commands.make(1, "build", band.id, "huttes"))["msg"] == ""
    commands.apply(st, commands.make(1, "build", band.id, "fosses"))
    assert site.data.queue == ["fosses"]
    commands.apply(st, commands.make(1, "unqueue", band.id, 0))
    assert site.data.queue == []
    site.data.buildings["foyer"] = 1
    assert "abattu" in commands.apply(st, commands.make(1, "demolish", band.id, "foyer"))["msg"]
    assert commands.apply(st, commands.make(2, "demolish", band.id, "grenier"))["msg"], "pas le village d'un autre"


def test_an_ai_village_builds_levels_in_a_long_run():
    st, site, band = _village(ALL, pop=150, stock=1e6)
    st.tribes[1].is_player = False
    for _ in range(300):
        ai._village_ai(st, band, band.stock / max(1, band.population))
        _finish(st, site)
        band.stock = 1e6
    assert sum(site.data.buildings.values()) >= 10


def test_the_page_answers_clicks_in_the_real_loop(monkeypatch, tmp_path):
    st, site, band = _village(ALL, pop=150, stock=1e5)
    st.selected_band = band.id
    seen = {}

    def need(cond, what):
        assert cond, what

    def bp(r):
        return r.village_hits["bpage"]

    steps = [
        lambda r: [],
        lambda r: _key(pygame.K_v),
        lambda r: need(r.village_hits, "V ouvre le village") or _click(_center(r.village_hits["pages"]["batiments"])),
        lambda r: need(r.village_hits.get("page") == "batiments", "l'onglet Les bâtiments") or _click(_center(bp(r)["cards"]["huttes"]["plus"])),
        lambda r: need(places.works(site) and places.works(site)[0] == "huttes", "+ lance le chantier") or _click(_center(bp(r)["cards"]["fosses"]["plus"])),
        lambda r: need(site.data.queue == ["fosses"], "le suivant en file") or _click(_center(bp(r)["unq"][0])),
        lambda r: need(site.data.queue == [], "la croix le retire") or seen.update(n=places.level(site, "huttes")) or _click(_center(bp(r)["cards"]["huttes"]["minus"])),
        lambda r: need(places.level(site, "huttes") == seen["n"], "un clic ne suffit pas à abattre") or _click(_center(bp(r)["cards"]["huttes"]["minus"])),
        lambda r: [],
    ]
    _play(monkeypatch, tmp_path, st, steps)
    assert places.level(site, "huttes") in (seen["n"] - 1, seen["n"]), "deux clics abattent (si personne n'y perd son toit)"
