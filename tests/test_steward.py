"""L'intendant des villages IA (G7) : les champs d'abord, les metiers rendent
leurs bras quand la disette est en vue, pas de chantier ni de troupe sans
marge, et le grain achete d'avance, moins cher (pour le joueur aussi)."""

from src.kora import ai, goods, grain, money, villages
from test_grain import _two


def _short(st, band, site):
    """Une disette en vue : peu de vivres, une recolte encore loin."""
    band.stock = band.population * 4.0
    site.data.forage = {s: band.population * 0.3 for s in ("printemps", "ete", "automne", "hiver")}
    assert grain.shortfall(st, band) > 0 and not grain.in_dearth(st, band)


def test_the_fields_keep_their_hands_before_any_craft():
    st, buyer, bsite, seller, ssite = _two()
    buyer.stock = buyer.population * 30.0
    bsite.data.forage = {s: buyer.population * 2.0 for s in ("printemps", "ete", "automne", "hiver")}
    bsite.data.fields = [[0, 0]] * 8
    for _ in range(12):
        goods.ai_crafts(st, bsite, buyer, 30.0)
    assert villages.field_hands_mult(bsite, buyer, st) >= 1.0, "un métier ne prend jamais les bras des champs"


def test_a_shortage_in_sight_sends_craftsmen_back_to_the_fields():
    st, buyer, bsite, seller, ssite = _two()
    st.tribes[1].knowledge.update(("poterie", "salaison"))
    bsite.data.teams = {"potiers": 1, "sauniers": 1}
    _short(st, buyer, bsite)
    goods.ai_crafts(st, bsite, buyer, 6.0)
    assert goods.total_teams(bsite) == 1, "un métier qui ne nourrit pas rend une équipe"
    goods.ai_crafts(st, bsite, buyer, 6.0)
    assert goods.total_teams(bsite) == 0


def test_no_building_site_or_raid_levy_without_a_food_margin():
    st, buyer, bsite, seller, ssite = _two()
    st.tribes[1].is_player = False
    _short(st, buyer, bsite)
    st.clock.week = 20
    built = []
    real = villages.build
    villages.build = lambda *a, **k: built.append(a) or real(*a, **k)
    try:
        ai._village_ai(st, buyer, 6.0)
    finally:
        villages.build = real
    assert not built, "pas de chantier quand le grenier ne tiendra pas"


def test_grain_is_bought_ahead_and_cheaper_when_a_shortage_is_in_sight():
    st, buyer, bsite, seller, ssite = _two()
    _short(st, buyer, bsite)
    q = grain.quote(st, 1, bsite.id)
    assert q["why"] == "" and q["planned"], q
    lines = " ".join(grain.tip_lines(st, 1, bsite.id))
    assert "Disette en vue" in lines and "moins cher" in lines
    # En pleine disette, le meme grain coute plus cher.
    ahead = q["per_sicle"]
    buyer.stock = buyer.population * 1.0
    dear = grain.quote(st, 1, bsite.id)
    assert not dear.get("planned") and dear["per_sicle"] < ahead
    # L'IA achete d'avance, une fois par PLAN_EVERY semaines.
    st2, b2, s2, sel2, ss2 = _two()
    st2.tribes[1].is_player = False
    _short(st2, b2, s2)
    before = b2.stock
    for _ in range(grain.PLAN_EVERY):
        grain.ai_weekly(st2)
        st2.tick_count += 1
    assert b2.stock > before and grain.shortfall(st2, b2) == 0
    assert money.has_money(st2, 3) and st2.tribes[3].money > 0
