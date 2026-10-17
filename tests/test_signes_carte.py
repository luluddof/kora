"""Ce que disent les jetons sur la carte (2026-10-17, au-dela du signe de la
marche) : la FAIM de vos unites (sim.band_hunger : famine, disette) et le
lisere rouge des peuples EN GUERRE avec vous (guerre.hostiles : une guerre
declaree, ou un raid de moins d'un an sans paix depuis ; un motif n'en est
pas une)."""

from src.kora import chiefdom, diplo, guerre
from src.kora.sim import band_hunger, band_lines, band_summary, hex_inspect, hunger_text, inspect_lines, new_game
from src.kora.types import Terrain
from src.kora.world import make_filled_world
from test_war_goals import _three


def _band(terrain):
    st = new_game(make_filled_world(40, 24, terrain, wrap_x=True))
    return st, st.bands[1]


def test_a_band_that_eats_shows_nothing():
    st, b = _band(Terrain.VALLEE)
    b.stock = 2.0 * b.population
    assert band_hunger(st, b) == "", "la collecte suffit : pas de faim, même à réserve basse"


def test_dearth_when_the_forage_falls_short_and_the_store_runs_low():
    st, b = _band(Terrain.DESERT)
    assert band_hunger(st, b) == "", "quatre semaines de réserve : pas encore"
    b.stock = 2.0 * b.population
    assert band_hunger(st, b) == "disette"
    assert "La collecte ne suffit pas" in band_lines(band_summary(st, b.id))[-1]


def test_famine_this_week_or_the_last():
    st, b = _band(Terrain.VALLEE)
    b.famine_tick = st.tick_count
    assert band_hunger(st, b) == "famine"
    assert band_lines(band_summary(st, b.id))[-1] == hunger_text("famine", False)
    st.tick_count += 3
    assert band_hunger(st, b) != "famine"


def test_the_hover_says_it_too():
    st, b = _band(Terrain.VALLEE)
    b.famine_tick = st.tick_count
    lines = inspect_lines(hex_inspect(st, b.position))
    assert hunger_text("famine", False) in lines
    assert "Disette en vue" in hunger_text("disette", True)


def test_a_declared_war_is_hostile_both_ways():
    st = _three()
    assert guerre.hostiles(st, 1) == set()
    guerre.declare_war(st, 1, 2)
    assert 2 in guerre.hostiles(st, 1) and 1 in guerre.hostiles(st, 2)
    assert 3 not in guerre.hostiles(st, 1), "un tiers reste neutre"


def test_a_recent_raid_is_hostile_until_peace_or_a_year():
    st = _three()
    diplo.of(st).raids[(2, 3)] = (st.tick_count, True)
    assert 3 in guerre.hostiles(st, 2) and 2 in guerre.hostiles(st, 3)
    st.tick_count += guerre.WAR_WEEKS + 1
    assert not guerre.hostiles(st, 2), "un an après, plus rien"
    st.tick_count -= guerre.WAR_WEEKS + 1
    diplo.add_pact(st, 2, 3, "treve")
    assert not guerre.hostiles(st, 2), "la paix faite, plus de liseré"


def test_a_motive_is_not_a_war():
    st = _three()
    guerre.set_casus(st, 1, 2, 52, "La terre")
    assert guerre.at_war(st, 1, 2)
    assert not guerre.hostile(st, 1, 2)


def test_a_raid_on_your_tributary_makes_its_whole_country_hostile():
    st = _three()
    chiefdom.make_vassal(st, 1, 2, "force")
    diplo.of(st).raids[(3, 2)] = (st.tick_count, True)
    assert 3 in guerre.hostiles(st, 1), "votre tributaire raide : son pays est le vôtre"
    assert 2 not in guerre.hostiles(st, 1), "pas soi-même ni son pays"


def test_the_last_week_of_an_event_says_so():
    from src.kora.render_panels import deadline_text
    assert deadline_text(0, short=True) == "dernière semaine"
    assert deadline_text(-1) == "cette semaine"
    assert deadline_text(3, short=True) == "encore 3 sem."
    assert deadline_text(1) == "dans 1 semaine" and deadline_text(5) == "dans 5 semaines"
