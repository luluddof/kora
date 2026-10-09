"""Le grain des disettes (grain.py) : un village affame achete du grain,
plus cher que le marche, a un partenaire qui en a de trop."""

from src.kora import commands, diplo, grain, money, tech
from src.kora.types import Season
from test_ost_siege import _state, _village

MONEY = {"valeurs", "comptage", "don"}


def _two(stock=60.0):
    st = _state()
    for tid in (1, 3):
        st.tribes[tid].knowledge.update(MONEY)
    tech.invalidate()
    buyer, bsite = _village(st, 1, 1, pop=200, col=10)
    seller, ssite = _village(st, 3, 3, pop=200, col=24)
    buyer.stock = stock
    seller.stock = 6000.0
    st.tribes[1].money = 50.0
    st.tribes[3].money = 0.0
    diplo.make_contact(st, 1, 3, quiet=True)
    diplo.add_pact(st, 1, 3, "commerce")
    return st, buyer, bsite, seller, ssite


def test_a_starving_village_buys_grain_dearer_than_the_market():
    st, buyer, bsite, seller, ssite = _two()
    assert grain.in_dearth(st, buyer)
    q = grain.quote(st, 1, bsite.id)
    assert q["why"] == "" and q["seller"] == 3
    assert 0 < q["per_sicle"] < money.VPS, "plus cher que le marche"
    before, sold = buyer.stock, seller.stock
    out = commands.apply(st, commands.make(1, "grain", bsite.id))
    assert out["msg"] == ""
    assert buyer.stock > before and seller.stock < sold
    assert abs((buyer.stock - before) - (sold - seller.stock)) < 1e-6
    assert abs(st.tribes[1].money - (50.0 - q["sicles"])) < 1e-6 and abs(st.tribes[3].money - q["sicles"]) < 1e-6
    assert st.tribes[1].money_month.get("grain", 0) < 0 < st.tribes[3].money_month.get("grain", 0)
    assert any(m.key == "grain" for m in diplo._d(st).mods.get(diplo.pair(1, 3), []))


def test_no_grain_without_dearth_partner_or_treasure():
    st, buyer, bsite, seller, ssite = _two(stock=4000.0)
    assert "Pas de disette" in grain.quote(st, 1, bsite.id)["why"]
    st, buyer, bsite, seller, ssite = _two()
    diplo.break_pact(st, 1, 3, "commerce")
    assert grain.quote(st, 1, bsite.id)["why"]
    st, buyer, bsite, seller, ssite = _two()
    st.tribes[1].money = 0.0
    assert "vide" in grain.quote(st, 1, bsite.id)["why"]
    st, buyer, bsite, seller, ssite = _two()
    diplo.declare_war(st, 1, 3)
    assert grain.quote(st, 1, bsite.id)["why"]


def test_the_more_you_take_and_in_winter_the_dearer():
    st, buyer, bsite, seller, ssite = _two()
    cheap = grain.quote(st, 1, bsite.id)["per_sicle"]
    seller.stock = 2000.0 + 10 * seller.population  # moins de grain de trop
    dear = grain.quote(st, 1, bsite.id)["per_sicle"]
    assert dear < cheap
    st.world.hex_season = lambda h: Season.HIVER
    assert grain.quote(st, 1, bsite.id)["per_sicle"] < dear


def test_the_ai_buys_grain_when_its_village_starves():
    st, buyer, bsite, seller, ssite = _two()
    st.tribes[1].is_player = False
    before = buyer.stock
    grain.ai_weekly(st)
    assert buyer.stock > before
