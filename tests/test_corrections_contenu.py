"""Les corrections du debut et du contenu (revue du 2026-11-27,
docs/superpowers/specs/2026-11-27-revue-bugs.txt) : les savoirs qu'un peuple
fixe ne pouvait jamais vivre (G9), les cartes de bande qui ne connaissaient
que quatre sols (G10), les conjonctures a un seul candidat (G11), les
decisions de l'age tribal, les cartes qui coupaient un village, le progres
qui contournait le sort, la soudure des decisions de l'IA, le pillage des
routes, la fete des morts, la relation des cartes, le sens des pastilles, le
prestige des situations, la memoire des regards."""

from src.kora import ai, chiefs, decisions, diplo, draws, events, learning, situations, tech, turning, villages
from src.kora.clock import Clock
from src.kora.events import EVENTS, Instance
from src.kora.gamestate import GameState
from src.kora.situations import SPECS
from src.kora.types import Band, Terrain, Tribe
from src.kora.world import MOVE_COST, make_filled_world, offset_to_axial
from test_decisions import _route_world
from test_grain import _two
from test_ost_siege import _village


# De quoi fonder un village (sans l'arc : les essais de G9 le demandent).
SETTLE = {"huttes", "semis", "sedentarite", "palissade", "palabres", "messagers"}


def _plain_state(tribes=(1, 2), width=60):
    world = make_filled_world(width, 30, Terrain.PLAINE, wrap_x=True)
    st = GameState(
        world=world,
        clock=Clock(),
        tribes={t: Tribe(t, f"P{t}", 30, t == 1, knowledge=set(tech.START_KNOWLEDGE) | SETTLE) for t in tribes},
        bands={},
        next_band_id=50,
    )
    st.clock.week = 20
    world.fill_season(st.clock.season())
    return st


# --- G9 : un peuple fixe n'est jamais prive d'un savoir de lieu -----------------


def test_a_settled_people_learns_from_a_neighbour_what_its_land_does_not_show():
    st = _plain_state()
    me, _site = _village(st, 1, 1, pop=200, col=10)
    _village(st, 2, 2, pop=200, col=30)
    st.tribes[1].knowledge.add("epieu")
    st.tribes[2].knowledge.update({"epieu", "arc"})
    tech.invalidate()
    # Pas une foret dans tout le pays : l'arc attendait pour toujours.
    assert learning.status(st, 1, "arc") == "attente"
    forest = next(c for c in tech.TECHS["arc"].conds if c.kind == "weeks")
    assert not learning._neighbors_know(st, 1, "arc")
    assert learning.cond_progress(st, st.tribes[1], forest, False)[0] == 0
    # Un voisin qui sait l'arc : il le lui apprend (le peuple ne bouge plus).
    diplo.of(st).neighbors = {1: [2], 2: [1]}
    assert learning._neighbors_know(st, 1, "arc") == [2]
    have, need, label = learning.cond_progress(st, st.tribes[1], forest, True)
    assert have >= need and "voisin" in label
    assert learning.status(st, 1, "arc") == "disponible"
    assert any("ce que votre pays ne montre pas" in text for text, _k in learning.detail_lines(st, 1, "arc"))
    # Un clan nomade encore sur les routes : il peut aller vivre en foret, le
    # voisin ne fait que diviser les semaines par deux.
    st.bands[9] = Band(9, 1, offset_to_axial(12, 20), 30, 60.0)
    assert not learning.settled(st, 1)
    assert learning.status(st, 1, "arc") == "attente"


def test_a_village_lives_on_its_whole_zone_not_only_its_fields():
    st = _plain_state(tribes=(1,))
    # Une foret a 4 lieux du village : hors de ses champs (3), dans sa zone.
    for row in range(30):
        st.world._terrains[row][24] = Terrain.FORET
    me, site = _village(st, 1, 1, pop=200, col=20, row=15)
    assert Terrain.FORET not in villages.land_profile(st.world, me.position)[0]
    assert Terrain.FORET in learning.range_profile(st.world, site)[0]
    learning.update_practice(st)
    assert st.tribes[1].practice.get("foret", 0) == 1


def test_a_rolled_back_glance_is_looked_again():
    # Le regard part du POINT de l'unite, et la memoire garde ce que le peuple
    # avait deja vu : un retour en arriere qui le lui fait oublier fait
    # regarder de nouveau (avant : la memoire disait "deja vu", pour toujours).
    world = make_filled_world(20, 12, Terrain.PLAINE)
    for row in range(12):
        world._terrains[row][15] = Terrain.EAU
    band = Band(1, 1, offset_to_axial(13, 6), 40, 160.0)
    tribe = Tribe(1, "t", 20, True)
    st = GameState(world=world, clock=Clock(), tribes={1: tribe}, bands={1: band})
    learning.update_practice(st, count=False)
    assert tribe.shore_seen
    tribe.shore_seen = False
    learning.update_practice(st, count=False)
    assert tribe.shore_seen


# --- G10 : chaque sol ou l'on vit a ses cartes de bande -------------------------------


def test_every_livable_soil_is_named_by_a_band_card():
    named = set()
    for ev in EVENTS.values():
        if ev.trigger != "pulse" or ("village",) in ev.conds:
            continue
        for c in ev.conds:
            if c[0] == "terrain":
                named.update(c[1:])
    livable = {t.value for t in MOVE_COST}
    assert livable - named == set(), sorted(livable - named)


def test_a_band_in_the_jungle_meets_the_wolves():
    st = _plain_state(tribes=(1,))
    band = Band(1, 1, offset_to_axial(10, 10), 40, 4.0)
    st.bands[1] = band
    st.world._terrains[10][10] = Terrain.JUNGLE
    st.clock.week = 45
    st.world.fill_season(st.clock.season())
    inst = Instance(uid=1, event_id="loups", tribe_id=1, band_id=1)
    assert events.check(st, inst, ("terrain", *events.EVENTS["loups"].conds[2][1:]))


# --- G11 : une conjoncture prend le premier groupe qui n'est pas au repos --------------


def test_a_conjuncture_starts_with_the_first_group_not_at_rest(monkeypatch):
    st = _plain_state(tribes=(1, 2, 3, 4), width=120)
    st.story = True
    for tid, col in ((1, 5), (2, 9), (3, 60), (4, 64)):
        _village(st, tid, tid, pop=120, col=col)
        st.tribes[tid].knowledge.add("ancetres")
    st.clock.week = 18
    groups = SPECS["travaux"].candidates(st)
    assert [g[2] for g in groups] == [[1, 2], [1, 2], [3, 4], [3, 4]]
    # Le premier groupe a eu ses grands travaux il y a peu : il est au repos.
    st.situation_last["travaux:1"] = st.tick_count
    monkeypatch.setattr(situations, "_rand", lambda *a: 0.0)
    situations.monthly(st)
    born = [s for s in st.situations if s.sid == "travaux"]
    assert len(born) == 1 and sorted(born[0].participants) == [3, 4]


def test_the_sickness_and_the_gathering_keep_all_their_candidates():
    st = _plain_state(tribes=(1, 2, 3, 4))
    st.clock.week = 30
    for bid, (tid, col) in enumerate(((1, 5), (2, 6), (3, 40), (4, 41)), start=1):
        st.bands[bid] = Band(bid, tid, offset_to_axial(col, 10), 120, 400.0)
    st.world.fill_season(st.clock.season())
    sick = SPECS["mal"].candidates(st)
    assert len(sick) == 4, "un foyer par grosse bande, pas le premier seul"


# --- les decisions de l'age tribal ------------------------------------------------------


def _nomads():
    st = _plain_state(tribes=(1, 2))
    n = st.world.width * st.world.height
    st.world.set_resources({"aurochs": bytes([255]) * n})
    band = Band(1, 1, offset_to_axial(10, 10), 42, 120.0)
    st.bands[1] = band
    st.bands[2] = Band(2, 2, offset_to_axial(40, 10), 30, 60.0)
    chiefs.ensure(st)
    return st, band


def test_a_nomad_band_can_hunt_and_send_scouts():
    st, band = _nomads()
    assert st.tribes[1].chief_band == band.id
    assert decisions.block(st, 1, "grande_chasse") == ""
    before = band.stock
    assert decisions.take(st, 1, "grande_chasse") == "Les chasseurs reviennent."
    assert band.stock > before or band.stock >= decisions.stock_max(band, st) - 1e-6
    assert decisions.block(st, 1, "eclaireurs") == ""
    seen = len(st.vision[1].explored) if st.vision and 1 in st.vision else 0
    assert decisions.take(st, 1, "eclaireurs") == "Les éclaireurs sont revenus."
    if st.vision and 1 in st.vision:
        assert len(st.vision[1].explored) > seen
    # L'IA : la bande du chef chasse quand ses reserves baissent.
    st.bands[2].stock = 1.0 * st.bands[2].population
    assert decisions._hunt_ai(st, 2) > 0


# --- les cartes qui coupaient un village en deux -------------------------------------------


def test_the_young_leave_only_a_nomad_band():
    assert ("not_village",) in EVENTS["jeunes_partent"].conds
    st = _plain_state(tribes=(1,))
    me, _site = _village(st, 1, 1, pop=120, col=20)
    inst = Instance(uid=1, event_id="jeunes_partent", tribe_id=1, band_id=me.id)
    assert not events.check(st, inst, ("not_village",))


def test_the_village_fever_sends_a_tenth_away_and_they_come_back():
    st = _plain_state(tribes=(1,))
    st.story = True
    me, _site = _village(st, 1, 1, pop=100, col=20)
    n0 = len(st.bands)
    inst = Instance(uid=1, event_id="fievre_village", tribe_id=1, band_id=me.id)
    opt = EVENTS["fievre_village"].options[2]
    chips = events.summary_chips(st, inst, opt)
    assert chips[0][0].startswith("10 personnes partent camper")
    events.resolve(st, inst, 2)
    assert len(st.bands) == n0, "pas de bande nouvelle"
    assert me.population == 88, me.population
    due = [s for s in events._book(st).scheduled if s[1] == "fievre_retour"]
    assert due and due[0][2]["data"]["campeurs"] == 10
    back = Instance(uid=2, event_id="fievre_retour", tribe_id=1, band_id=me.id, data=dict(due[0][2]["data"]))
    assert events.summary_chips(st, back, EVENTS["fievre_retour"].options[0])[0] == ("+10 personnes de retour au village", "gain")
    events.resolve(st, back, 0)
    assert me.population == 98


# --- le progres ne contourne ni le sort ni l'arrivee d'un grand tournant ---------------------


def test_points_do_not_bypass_the_draw_or_a_turning(monkeypatch):
    st = _plain_state()
    tribe = st.tribes[1]
    tribe.knowledge.add("epieu")
    tech.invalidate()
    # Un grand tournant pas arrive : un point ne le rend pas disponible.
    assert turning.presence(tribe, "domestication") < 100
    tribe.progress["domestication"] = 1.0
    assert learning.status(st, 1, "domestication") == "attente"
    assert not learning.choose(st, 1, "domestication")
    # Un savoir que le sort a ecarte : un point n'y fait rien.
    monkeypatch.setattr(draws, "absent", lambda s, t, tid: tid == "propulseur")
    tribe.progress["propulseur"] = 1.0
    assert learning.status(st, 1, "propulseur") == "absent"
    # Une carte "un de leurs savoirs avance" ne vise ni l'un ni l'autre.
    other = st.tribes[2]
    other.knowledge.update({"epieu", "domestication", "propulseur", "cueillette"})
    tribe.progress.clear()
    st.bands[1] = Band(1, 1, offset_to_axial(10, 10), 40, 120.0)
    for uid in range(6):
        inst = Instance(uid=uid, event_id="etrangers_cadeaux", tribe_id=1, band_id=1, other=2)
        events.apply(st, inst, ("tech_progress", 0.25))
    assert set(tribe.progress) == {"cueillette"}


# --- la soudure des decisions de l'IA --------------------------------------------------


def test_the_ai_gives_no_dowry_in_the_lean_weeks():
    st, buyer, bsite, seller, ssite = _two(stock=4000.0)
    ai_tribe = st.tribes[3]
    ai_tribe.knowledge.add("mariages")
    diplo.add_mod(st, 3, 1, "cadeau", 30.0, actor=3)
    st.tick_count = 12  # le mois ou il y pense : (12 // 4 + 3) % 6 == 0
    seller.stock = 6000.0
    assert decisions._marriage_ai(st, 3) > 0
    # Le grenier ne tiendra pas jusqu'a la recolte : pas de dot.
    seller.stock = 50.0
    decisions.forget()
    assert decisions._marriage_ai(st, 3) == 0.0


def test_the_ai_council_waits_for_the_clans_food():
    st, band = _nomads()
    st.tribes[2].chief_band = 2
    st.bands[3] = Band(3, 2, offset_to_axial(42, 10), 30, 300.0, loyalty=30.0)
    st.bands[2].stock = 300.0
    assert decisions._council_ai(st, 2) == 1.0
    st.bands[3].stock = 30.0  # un clan a une semaine de vivres
    assert decisions._council_ai(st, 2) == 0.0


def test_the_feast_of_the_dead_counts_the_cult_it_needs(monkeypatch):
    assert decisions.DEAD_AI_STABILITY == 75 + tech.TECHS["ancetres"].effects["stability"]
    st, buyer, bsite, seller, ssite = _two(stock=4000.0)
    seller.stock = 6000.0
    st.tribes[3].knowledge.add("ancetres")
    # Un village a 70 (le culte compte deja pour 10) : la fete est voulue.
    monkeypatch.setattr(villages, "stability", lambda *a, **k: 70.0)
    assert decisions._dead_ai(st, 3) == 1.0
    monkeypatch.setattr(villages, "stability", lambda *a, **k: 95.0)
    assert decisions._dead_ai(st, 3) == 0.0


# --- le pillage des routes de l'IA -----------------------------------------------------------


def test_a_route_raider_stays_on_its_post_and_the_decision_rests():
    st, me, route = _route_world()
    key = decisions._route_key(route)
    assert decisions.DECISIONS["piller_routes"].repose_years == 1
    decisions.take(st, 1, "piller_routes", key)
    army = next(b for b in st.bands.values() if b.tribe_id == 1 and b.kind == "armee")
    army.position = offset_to_axial(20, 15)
    army.path = []
    ai._army_ai(st, army, 6.0)
    assert army.id in st.bands and army.raid_route == key
    assert not army.path and not army.homebound
    assert decisions.status(st, 1, "piller_routes", key)[0] == "repos"


# --- la relation des cartes, le sens des pastilles ---------------------------------------------


def test_card_relations_add_up_with_a_bound():
    st = _plain_state()
    st.bands[1] = Band(1, 1, offset_to_axial(10, 10), 40, 120.0)
    diplo.make_contact(st, 1, 2, quiet=True)
    r0 = diplo.relation(st, 1, 2)
    events.apply(st, Instance(uid=1, event_id="etrangers", tribe_id=1, band_id=1, other=2), ("relation", 15))
    events.apply(st, Instance(uid=2, event_id="etrangers_cadeaux", tribe_id=1, band_id=1, other=2), ("relation", 12))
    assert diplo.relation(st, 1, 2) - r0 == 27
    for uid in range(3, 8):
        events.apply(st, Instance(uid=uid, event_id="etrangers_approchent", tribe_id=1, band_id=1, other=2), ("relation", 10))
    assert diplo.relation(st, 1, 2) - r0 == events.RELATION_BOUNDS[1]
    # Le present des nomades : sa propre raison, "Vos cadeaux".
    events.apply(st, Instance(uid=9, event_id="nomades", tribe_id=1, band_id=1, other=2), ("relation", 12))
    assert any(m.key == "cadeau" for m in diplo.of(st).mods[diplo.pair(1, 2)])


def test_the_chips_tell_gains_and_losses_right():
    tone = events.effect_tone
    assert tone(("war_tribute",)) == "perte"
    assert tone(("provoke",)) == "perte"
    assert tone(("craft_team", "mineurs")) == "gain"
    assert tone(("tournant", 20)) == "gain"
    assert tone(("voie", "cite", 25)) == "gain"
    for flag in (("flag", "sur_gardes", 8), ("flag", "louveteaux")):
        assert events.effect_text(flag) and tone(flag) == "gain"
    st = _plain_state()
    st.bands[1] = Band(1, 1, offset_to_axial(10, 10), 40, 120.0)
    inst = Instance(uid=1, event_id="nomades", tribe_id=1, band_id=1, other=2)
    guard = EVENTS["nomades"].options[1]
    assert events.summary_chips(st, inst, guard) != [("Rien de plus", "neutre")]


# --- le prestige des situations passe par ses bonus ----------------------------------------------


def test_a_situation_prize_counts_the_prestige_bonus():
    from test_situations import _start, _state as _sit_state

    st = _sit_state()
    tribe = st.tribes[1]
    situations.grant_effect(tribe, "sit:travaux:prix", st.tick_count + 1000)
    mult = tech.bonuses(tribe).prestige_gain
    assert mult > 1.0
    tribe.prestige = 20
    inst = _start(st, "passage", next(b.position for b in st.bands.values() if b.tribe_id == 1), 6, [1, 2], {"dq": 1, "dr": 0})
    inst.participants[1]["score"] = 300.0
    inst.participants[2]["score"] = 100.0
    inst.until = st.tick_count
    situations.monthly(st)
    assert inst.winner == 1
    assert tribe.prestige == 20 + max(1, round(8 * mult))
