"""Les nombres et l'argent (0.7.0) : comptage, nombres additifs et base,
operations trouvees par les calculateurs ; valeurs d'echange, tresor,
budget (impot, solde, gages, commerce en argent), argent pese et mines,
droits de passage ; commandes, sauvegarde, ecrans."""

import os

os.environ.setdefault("SDL_VIDEODRIVER", "dummy")

from src.kora import battle, commands, goods, money, numbers, persist, resources, tech, villages
from src.kora.types import Band, Terrain, Tribe
from src.kora.world import make_filled_world, offset_to_axial
from test_goods import CENTER, _village

MONEY = ("comptage", "nombres", "valeurs")


def _learn(st, tid, *ids):
    st.tribes[tid].knowledge.update(ids)
    tech.invalidate()


# --- les savoirs -------------------------------------------------------------------


def test_the_numbers_techs_sit_where_the_author_wants_them():
    t = tech.TECHS
    # Deux savoirs de mathematiques maintenant : le comptage (age tribal),
    # les nombres additifs (neolithique) ; la numeration de position viendra.
    assert tech.era_of(t["comptage"]) == 0 and tech.era_of(t["nombres"]) == 1
    assert "comptage" in t["nombres"].prereqs
    # L'argent au neolithique : valeurs d'echange, puis argent pese.
    for tid in ("valeurs", "argent_pese", "peages"):
        assert tech.era_of(t[tid]) == 1
    assert "valeurs" in t["argent_pese"].prereqs and "valeurs" in t["peages"].prereqs
    assert all(tech.TECHS[p].tier < x.tier for x in t.values() for p in x.prereqs)


def test_counting_gives_addition_and_only_addition():
    st, site, band = _village(("comptage",))
    numbers.monthly(st)
    tribe = st.tribes[1]
    assert tribe.operations == ["add"]
    assert "op:add" in tribe.math_effects
    # Sans Nombres additifs : pas de base, pas de recherche.
    assert numbers.choose(st, 1, 10) == "Il faut connaître Nombres additifs"
    goods_teams = goods.add_block(st, site, "calculateurs")
    assert goods_teams.startswith("Il faut connaître")


def test_the_base_is_chosen_once_and_changing_it_is_a_heavy_reform():
    st, site, band = _village(("comptage", "nombres"))
    tribe = st.tribes[1]
    tribe.prestige = 100
    before = tech.bonuses(tribe).grain_rot
    assert numbers.choose(st, 1, 60).startswith("Vos nombres")
    numbers.monthly(st)
    assert tribe.base == 60 and "base:60" in tribe.math_effects
    assert tech.bonuses(tribe).grain_rot < before
    assert tech.bonuses(tribe).granary >= 4
    # Changer tout de suite : non (une reforme tous les 30 ans).
    assert "30 ans" in numbers.choose(st, 1, 10)
    st.tick_count += numbers.REFORM_EVERY
    prestige = tribe.prestige
    assert numbers.choose(st, 1, 10).startswith("Réforme")
    assert tribe.prestige == prestige - numbers.REFORM_PRESTIGE
    # Trois ans sans l'avantage de la nouvelle base.
    assert "base:10" not in tribe.math_effects
    st.tick_count += numbers.REFORM_WEEKS
    numbers.monthly(st)
    assert "base:10" in tribe.math_effects and "base:60" not in tribe.math_effects


def test_each_base_has_its_own_bonus():
    st, site, band = _village(("comptage", "nombres"))
    tribe = st.tribes[1]
    plain = tech.bonuses(tribe)
    seen = {}
    for base in numbers.BASE_ORDER:
        tribe.base = base
        numbers._sync(st, tribe)
        seen[base] = tech.bonuses(tribe)
    assert seen[10].learn > plain.learn
    assert seen[12].trade_price > plain.trade_price
    assert seen[20].stability > plain.stability
    assert seen[60].grain_rot < plain.grain_rot


def test_the_ai_picks_a_base_by_itself():
    st, site, band = _village(("comptage", "nombres"))
    st.tribes[1].is_player = False
    numbers.monthly(st)
    assert st.tribes[1].base in numbers.BASES


def test_mathematicians_find_the_operations_one_after_another():
    st, site, band = _village(("comptage", "nombres"), pop=200)
    tribe = st.tribes[1]
    assert not goods.add_block(st, site, "calculateurs")
    goods.set_teams(st, site, "calculateurs", 1)
    assert numbers.points(st, 1) > 0
    # Sans calculateurs, aucune operation ne vient.
    for _ in range(400):
        numbers.monthly(st)
        if numbers.knows(tribe, "frac"):
            break
    assert tribe.operations == ["add", "sub", "mul", "div", "frac"]
    b = tech.bonuses(tribe)
    assert b.field_yield > 1.0 and b.tax > 1.0
    page = numbers.page(st, 1)
    assert all(o["state"] == "connue" for o in page["ops"])


def test_without_mathematicians_no_operation_is_found():
    st, site, band = _village(("comptage", "nombres"))
    for _ in range(60):
        numbers.monthly(st)
    assert st.tribes[1].operations == ["add"]


# --- l'argent ----------------------------------------------------------------------


def test_money_comes_with_exchange_values_and_the_tax_costs_stability():
    st, site, band = _village(("comptage",))
    assert not money.has_money(st, 1)
    assert money.set_budget(st, 1, "tax", 2).startswith("Il faut")
    _learn(st, 1, *MONEY)
    assert money.has_money(st, 1)
    calm = villages.stability(st, site)
    assert money.set_budget(st, 1, "tax", 3).startswith("Impôt")
    assert villages.stability(st, site) < calm
    labels = [l for l, _v in villages.stability_parts(st, site)]
    assert "Impôt lourd" in labels
    money.monthly(st)
    tribe = st.tribes[1]
    assert tribe.money > 0
    assert money.last_month(tribe)["impot"] > 0
    assert tribe.money_hist and tribe.money_hist[-1][4] == round(tribe.money, 2)


def test_silver_makes_the_tax_yield_more():
    st, site, band = _village(MONEY)
    money.set_budget(st, 1, "tax", 2)
    plain = money.tax_income(st, 1)
    _learn(st, 1, "argent_pese")
    assert money.tax_income(st, 1) > plain


def test_paid_soldiers_hold_better_and_unpaid_ones_worse():
    st, site, band = _village(MONEY)
    tribe = st.tribes[1]
    army = Band(5, 1, band.position, 30, 0.0, kind="armee")
    st.bands[5] = army
    st.next_band_id = 6
    base = villages.army_morale(st, army)
    money.set_budget(st, 1, "solde", True)
    tribe.money = 100.0
    money.monthly(st)
    assert money.budget(tribe)["etat_solde"] == "payee"
    assert villages.army_morale(st, army) == base + 5
    assert money.flee_mult(st, 1) < 1.0
    tribe.money = 0.0
    tribe.budget["tax"] = 0
    money.monthly(st)
    assert money.budget(tribe)["etat_solde"] == "impayee"
    assert villages.army_morale(st, army) == base - 5
    assert money.flee_mult(st, 1) > 1.0


def test_paid_craftsmen_work_better():
    st, site, band = _village(MONEY + ("poterie",), res={"argile": (220, 3)})
    goods.set_teams(st, site, "potiers", 1)
    plain = goods.output(st, site, "potiers")
    tribe = st.tribes[1]
    tribe.money = 100.0
    money.set_budget(st, 1, "gages", True)
    money.monthly(st)
    assert goods.output(st, site, "potiers") > plain
    assert money.last_month(tribe)["gages"] < 0


def test_silver_miners_need_silver_veins_and_fill_the_treasury():
    st, site, band = _village(MONEY + ("argent_pese",), pop=200)
    assert goods.craft_status(st, site, "mineurs") == "absent"
    assert "filon" in goods.add_block(st, site, "mineurs")
    st, site, band = _village(MONEY + ("argent_pese",), pop=200, res={"argent": (230, 3)})
    assert not goods.add_block(st, site, "mineurs")
    goods.set_teams(st, site, "mineurs", 1)
    tribe = st.tribes[1]
    before = tribe.money
    goods.update(st)
    assert tribe.money > before
    assert tribe.money_month.get("mines", 0) > 0
    # L'argent n'est pas un bien du marche.
    assert "argent" not in goods.GOODS and "" not in goods.GOODS


def test_the_silver_layer_lies_in_the_hills_only():
    salt = {"sel": bytes(40 * 20)}
    world = make_filled_world(40, 20, Terrain.COLLINE, wrap_x=True)
    world.set_resources(salt)
    assert any(v >= resources.PRESENT_BYTE for v in world.resources["argent"])
    flat = make_filled_world(40, 20, Terrain.PLAINE, wrap_x=True)
    flat.set_resources(salt)
    assert max(flat.resources["argent"]) == 0
    again = make_filled_world(40, 20, Terrain.COLLINE, wrap_x=True)
    again.set_resources(salt)
    assert again.resources["argent"] == world.resources["argent"]


def test_miners_walk_to_the_hills_nearby():
    world = make_filled_world(60, 30, Terrain.VALLEE, wrap_x=True)
    n = world.width * world.height
    layer = bytearray(n)
    far = offset_to_axial(CENTER[0] + 5, CENTER[1])
    col, row = world._index(far)
    layer[row * world.width + col] = 230
    world.set_resources({"argent": bytes(layer)})
    assert goods.riches(world, offset_to_axial(*CENTER))["argent"][0] == 1
    assert "argent" not in goods.riches(world, offset_to_axial(CENTER[0] + 15, CENTER[1]))


def _two_peoples(known=MONEY):
    st, site, band = _village(known, pop=200)
    other = Tribe(2, "Voisins", 120, False, knowledge=set(st.tribes[1].knowledge), culture="")
    st.tribes[2] = other
    st.bands[7] = Band(7, 2, offset_to_axial(CENTER[0] + 6, CENTER[1]), 150, 3000.0)
    st.next_band_id = 8
    tech.invalidate()
    return st


def test_routes_can_be_paid_in_silver():
    st = _two_peoples()
    money.set_budget(st, 1, "commerce", True)
    assert money.pays_in_money(st, 1, 2)
    st.tribes[1].money = 10.0
    paid = money.pay_route(st, 1, 2, 100.0)
    assert paid == 100.0
    assert st.tribes[1].money == 5.0 and st.tribes[2].money == 5.0
    assert money.last_month(st.tribes[2]) == {} and st.tribes[2].money_month["ventes"] == 5.0
    # Plus d'argent : le reste en vivres.
    assert money.pay_route(st, 1, 2, 500.0) == 100.0
    # Un peuple sans l'argent ne le prend pas.
    st.tribes[2].knowledge.discard("valeurs")
    tech.invalidate()
    assert not money.pays_in_money(st, 1, 2)


def test_tolls_are_paid_to_whoever_holds_the_way(monkeypatch):
    st = _two_peoples()
    third = Tribe(3, "Passeurs", 200, False, knowledge=set(st.tribes[1].knowledge) | {"peages"}, culture="")
    st.tribes[3] = third
    tech.invalidate()

    class R:
        exporter, importer, good, paid = 1, 2, "sel", 200.0

    monkeypatch.setattr(goods, "all_routes", lambda s: [R])
    monkeypatch.setattr(money, "toll_owner", lambda s, r: 3)
    st.tribes[1].money = 10.0
    money.collect_tolls(st)
    # Un demi-sicle par convoi et 10 % de la charge.
    assert third.money == 200.0 * money.TOLL / money.VPS + money.TOLL_FLAT
    assert st.tribes[1].money_month["peages"] < 0
    # Sans argent, le passage se paie en vivres.
    st.tribes[1].money = 0.0
    food = st.bands[1].stock
    money.collect_tolls(st)
    assert st.bands[1].stock < food


def test_the_ai_keeps_a_budget_and_does_not_hoard():
    st = _two_peoples()
    st.tribes[2].money = 50.0
    money.monthly(st)
    b = money.budget(st.tribes[2])
    assert b["commerce"] is True and b["tax"] in money.TAX
    # Un tresor plein : plus d'impot, des presents aux familles.
    st.tribes[2].families = [{"id": 1, "name": "x", "trait": "", "charge": "", "favour": 40.0, "village": 0}]
    st.tribes[2].money = 50 * money.reserve(st, 2)
    money.monthly(st)
    b = money.budget(st.tribes[2])
    assert b["tax"] == 0 and b["dons"] is True and b["etat_dons"] == "payee"
    assert st.tribes[2].families[0]["favour"] > 40.0


def test_gifts_to_the_families_cost_a_share_of_the_treasury():
    st, site, band = _village(MONEY)
    tribe = st.tribes[1]
    tribe.families = [{"id": i, "name": "f", "trait": "", "charge": "", "favour": 30.0, "village": site.id} for i in range(2)]
    tribe.money = 200.0
    calm = villages.stability(st, site)
    money.set_budget(st, 1, "dons", True)
    money.monthly(st)
    assert money.last_month(tribe)["dons"] == -200.0 * money.DON_SHARE
    assert all(f["favour"] == 30.0 + money.DON_FAVOUR for f in tribe.families)
    assert villages.stability(st, site) == calm + money.DON_STABILITY
    # Pas de quoi : rien n'est donne, rien n'est promis.
    tribe.money = 0.5
    money.monthly(st)
    assert money.budget(tribe)["etat_dons"] == ""


def test_vassals_pay_part_of_their_treasury(monkeypatch):
    from src.kora import chiefdom

    st = _two_peoples()
    st.tribes[2].money = 100.0
    monkeypatch.setattr(chiefdom, "vassals_of", lambda s, tid: [2] if tid == 1 else [])
    money.monthly(st)
    assert st.tribes[1].money_month == {} and money.last_month(st.tribes[1]).get("tribut") == 10.0


# --- commandes, sauvegarde, ecrans ---------------------------------------------------


def test_base_and_budget_go_through_commands():
    st, site, band = _village(MONEY)
    out = commands.apply(st, commands.make(1, "base", 12))
    assert st.tribes[1].base == 12 and "douze" in out["msg"]
    commands.apply(st, commands.make(1, "budget", "tax", 1))
    commands.apply(st, commands.make(1, "budget", "gages", True))
    b = money.budget(st.tribes[1])
    assert b["tax"] == 1 and b["gages"] is True


def test_numbers_and_treasury_survive_a_save():
    st, site, band = _village(MONEY + ("argent_pese",))
    numbers.monthly(st)
    numbers.choose(st, 1, 20)
    tribe = st.tribes[1]
    tribe.operations = ["add", "sub"]
    tribe.math_progress = 7.5
    tribe.money = 12.25
    money.set_budget(st, 1, "tax", 2)
    money.set_budget(st, 1, "solde", True)
    money.monthly(st)
    back, _view = persist.loads_game(persist.dumps_game(st), st.world)
    t2 = back.tribes[1]
    for name in ("base", "base_changed", "operations", "math_progress", "math_effects", "money", "budget", "money_hist"):
        assert getattr(t2, name) == getattr(tribe, name), name


def test_the_numbers_page_and_the_treasury_lay_out_cleanly():
    from src.kora import render_numbers, render_treasury
    from src.kora.layout import side_hit, side_layout

    for w, h in ((1024, 640), (1280, 720), (1920, 1080)):
        lay = side_layout(w, h, panel="savoirs", tech_tab="nombres")
        page = lay["tech"]["numbers"]
        bx, by, bw, bh = lay["tech"]["box"]
        for base, rects in page["bases"].items():
            x, y, cw, ch = rects["card"]
            assert by <= y and y + ch <= by + bh
            assert side_hit(lay, rects["btn"][0] + 5, rects["btn"][1] + 5) == f"nbase:{base}"
        for rect in list(page["ops"].values()) + [page["later"], page["calc"]]:
            assert rect[1] + rect[3] <= by + bh
        assert side_hit(lay, *lay["tech"]["tabs"]["arbre"][:2]) == "ttab:arbre"
        tree = side_layout(w, h, panel="savoirs")
        assert any(k.startswith("tech:") for k in tree["items"]) and not any(k.startswith("nbase:") for k in tree["items"])
        tl = render_treasury.treasury_layout(w, h)
        bx, by, bw, bh = tl["box"]
        for lvl, rect in tl["taxes"].items():
            assert render_treasury.treasury_hit(tl, rect[0] + 3, rect[1] + 3) == f"mtax:{lvl}"
        for key, rects in tl["toggles"].items():
            assert render_treasury.treasury_hit(tl, rects["btn"][0] + 3, rects["btn"][1] + 3) == f"mtoggle:{key}"
            assert rects["row"][1] + rects["row"][3] <= by + bh
    assert "tresor" in side_layout(1280, 720, treasury=True)["tabs"]
    assert "tresor" not in side_layout(1280, 720)["tabs"]


def test_the_money_and_numbers_modules_stay_pure():
    import ast
    import pathlib

    for name in ("numbers", "money"):
        tree = ast.parse(pathlib.Path(f"src/kora/{name}.py").read_text(encoding="utf-8"))
        mods = {n.module for n in ast.walk(tree) if isinstance(n, ast.ImportFrom)} | {a.name for n in ast.walk(tree) if isinstance(n, ast.Import) for a in n.names}
        assert not any(m and m.startswith("pygame") for m in mods), name


def test_money_events_speak_through_the_systems_vocabulary():
    from src.kora import events

    st, site, band = _village(MONEY + ("argent_pese",), pop=200, res={"argent": (230, 3)})
    tribe = st.tribes[1]
    tribe.money = 20.0
    inst = events._new_instance(st, events.EVENTS["pierre_blanche"], 1, band.id)
    assert events.conds_ok(st, inst, (("has_money",), ("money_ge", 10), ("veins", "mineurs")))
    assert not events.check(st, inst, ("money_ge", 50))
    assert not events.check(st, inst, ("craft_teams", "mineurs"))
    events.apply(st, inst, ("craft_team", "mineurs"))
    assert events.check(st, inst, ("craft_teams", "mineurs"))
    events.apply(st, inst, ("money", 4))
    events.apply(st, inst, ("money_pct", -0.5))
    events.apply(st, inst, ("math_points", 8))
    assert tribe.money == 12.0 and tribe.math_progress == 8.0
    assert tribe.money_month["evenements"] == 4 - 12.0
    assert events.effect_text(("money", 4)) == "+4 sicles au trésor"
    assert "mineurs" in events.effect_text(("craft_team", "mineurs"))
