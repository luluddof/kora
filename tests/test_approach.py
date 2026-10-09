"""Les approches des dirigeants (approach.py) et les grandes chefferies
(savoirs du palier 6 : enceintes, festins, biens de prestige, chef des chefs,
otages et serments, araire, lait et laine)."""

from src.kora import approach, chiefdom, chiefs, diplo, learning, sites, tech, villages
from src.kora.clock import Clock
from src.kora.gamestate import GameState
from src.kora.types import Band, Terrain, Tribe
from src.kora.world import make_filled_world, offset_to_axial

NEO = set(tech.START_KNOWLEDGE) | {"huttes", "semis", "sedentarite", "chefferie", "maisons", "ancetres", "echanges", "palabres", "messagers", "greniers", "poterie"}


def _world():
    return make_filled_world(80, 40, Terrain.VALLEE, wrap_x=True)


def _state(strong=300, weak=40, known=()):
    """Deux peuples de l'IA voisins : 2 (un village, `strong` gens) et 3
    (`weak` gens, a 10 cases) ; et le joueur (1) au loin."""
    w = _world()
    tribes = {
        1: Tribe(1, "Kora", 30, True, knowledge=set(NEO), culture="joueur"),
        2: Tribe(2, "Akor", 30, False, knowledge=set(NEO) | set(known), culture="vallee"),
        3: Tribe(3, "Tavek", 30, False, knowledge=set(NEO), culture="vallee"),
    }
    bands = {
        1: Band(1, 1, offset_to_axial(70, 20), 40, 400.0),
        2: Band(2, 2, offset_to_axial(20, 20), strong, 3000.0),
        3: Band(3, 3, offset_to_axial(30, 20), weak, 400.0),
    }
    st = GameState(world=w, clock=Clock(), tribes=tribes, bands=bands, next_band_id=4)
    w.fill_season(st.clock.season())
    chiefs.ensure(st)
    for bid in (2, 3):
        sites.make_camp(st, bid)
        villages.found(st, bid)
    st.bands[2].stock = 3000.0
    st.bands[3].stock = 400.0
    diplo.make_contact(st, 2, 3, quiet=True)
    tech.invalidate()
    return st


def _traits(st, tid, *traits):
    chiefs.chief_of(st, tid).traits = tuple(traits)


def test_an_ambitious_strong_chief_next_to_the_weak_becomes_a_conqueror():
    st = _state()
    _traits(st, 2, "ambitieux")
    approach.monthly(st)
    assert approach.of(st, 2) == "conquerant"
    why = [w for w, _v in approach.reasons(st, 2)]
    assert "Ambitieux" in why and any("faibles" in w for w in why)
    # Ce qu'il change : il raide plus, offre moins sa protection.
    assert approach.factor(st, 2, "raid") > 1.0 and approach.factor(st, 2, "protect") < 1.0


def test_a_generous_chief_protects_and_a_weak_neighbour_grows_wary():
    st = _state()
    _traits(st, 2, "genereux")
    _traits(st, 3, "chasseur")
    approach.monthly(st)
    assert approach.of(st, 2) == "protecteur"
    assert approach.of(st, 3) == "mefiant"
    # Le mefiant se range plus volontiers sous une protection.
    v = diplo.evaluate(st, 2, 3, "proteger")
    assert ("Leur chef : méfiant", 15) in v.reasons


def test_hunger_turns_a_chief_desperate():
    st = _state()
    _traits(st, 3, "sage")
    st.bands[3].stock = 10.0
    approach.monthly(st)
    assert approach.of(st, 3) == "affame"
    assert chiefdom.ai_choice(st, 3, 2) == "piller"


def test_a_chief_keeps_his_way_unless_another_is_clearly_better():
    st = _state()
    _traits(st, 2, "ambitieux")
    approach.monthly(st)
    assert approach.of(st, 2) == "conquerant"
    # Un peu plus de raisons d'etre protecteur : pas assez pour changer.
    _traits(st, 2, "ambitieux", "fidele")
    st.tick_count += approach.MIN_WEEKS
    approach.monthly(st)
    assert approach.of(st, 2) == "conquerant"
    # Un nouveau chef choisit la sienne tout de suite.
    band = st.bands[st.tribes[2].chief_band]
    band.leader = chiefs.new_person(st, st.tribes[2])
    band.leader.traits = ("genereux", "rassembleur")
    st.tick_count += 1
    approach.monthly(st)
    assert approach.of(st, 2) == "protecteur"


def test_a_tributary_is_submissive_or_restive():
    st = _state()
    chiefdom.make_vassal(st, 2, 3, "force")
    approach.monthly(st)
    assert approach.of(st, 3) in ("soumis", "retif")
    expected = "retif" if chiefdom.unrest(st, 3, 2) >= approach.RETIF_UNREST else "soumis"
    assert approach.of(st, 3) == expected


def test_players_have_no_approach_and_hear_of_their_neighbours():
    st = _state()
    st.bands[1].position = offset_to_axial(40, 20)
    diplo.make_contact(st, 1, 2, quiet=True)
    _traits(st, 2, "ambitieux")
    approach.monthly(st)
    assert approach.of(st, 1) == ""
    # Un vrai changement d'approche : le joueur voisin l'apprend.
    _traits(st, 2, "genereux", "rassembleur", "fidele")
    st.tribes[2].prestige = 10
    st.tick_count += approach.MIN_WEEKS
    approach.monthly(st)
    assert approach.of(st, 2) == "protecteur"
    assert any("Akor" in e.text and "protecteur" in e.text for e in st.log.entries)


def test_a_conqueror_chief_worries_everyone():
    st = _state()
    _traits(st, 2, "ambitieux")
    approach.monthly(st)
    assert ("Chef conquérant", -4.0) in diplo.reasons(st, 3, 2)


# --- les grandes chefferies ------------------------------------------------------------


def test_the_great_chiefdom_techs_sit_in_the_neolithic():
    for tid in ("enceintes", "araire", "festins", "lait", "grand_chef", "otages", "biens_prestige"):
        t = tech.TECHS[tid]
        assert t.tier >= 5 and tech.era_of(t) == 1, tid
        assert tech.effect_lines(t), tid
    assert 6 in tech.ERAS[1][1] and tech.TIER_NAMES[6] == "Grandes chefferies"
    cells = [(t.branch, t.tier, t.slot) for t in tech.TECHS.values() if tech.era_of(t) == 1]
    assert len(cells) == len(set(cells))


def test_walls_defend_the_village():
    st = _state(known=("enceintes",))
    labels = [l for l, _m in villages.defense_parts(st, st.bands[2])]
    assert "Enceintes et fossés" in labels


def test_the_chief_of_chiefs_holds_more_tributaries_with_less_force():
    st = _state()
    before_cap, before_ratio = chiefdom.vassal_cap(st, 2), chiefdom.protect_ratio(st, 2)
    st.tribes[2].knowledge.add("grand_chef")
    tech.invalidate()
    assert chiefdom.vassal_cap(st, 2) == before_cap + 2
    assert chiefdom.protect_ratio(st, 2) < before_ratio


def test_hostages_calm_the_tributaries():
    st = _state(strong=120, weak=110)
    chiefdom.make_vassal(st, 2, 3, "force")
    calm = chiefdom.unrest(st, 3, 2)
    assert calm > 0
    st.tribes[2].knowledge.add("otages")
    tech.invalidate()
    assert chiefdom.unrest(st, 3, 2) < calm
    # "Avoir un tributaire" : la condition de ces savoirs.
    have, need, label = learning.cond_progress(st, st.tribes[2], tech.Cond("vassals", 1))
    assert (have, need) == (1, 1) and "tributaire" in label


def test_prestige_feasts_honour_the_neighbours():
    st = _state(known=("festins",))
    tribe = st.tribes[2]
    full = chiefdom.feast_cost(st, 2)
    tribe.knowledge.discard("festins")
    tech.invalidate()
    assert chiefdom.feast_cost(st, 2) > full
    tribe.knowledge.add("festins")
    tech.invalidate()
    tribe.granary = 10 * full
    assert chiefdom.feast(st, 2) == "La fête est donnée."
    assert any(m.key == "festin" for m in st.diplo.mods.get(diplo.pair(2, 3), []))
    assert chiefdom.feasted(st, 2, 3)
    assert ("Ils ont mangé à votre table", 10) in diplo.evaluate(st, 2, 3, "proteger").reasons


def test_prestige_goods_oblige_those_who_receive_them():
    st = _state(known=("biens_prestige",))
    st.bands[3].position = offset_to_axial(24, 20)
    out = diplo.perform(st, 2, 3, "cadeau", 100.0)
    assert "acceptent" in out
    assert diplo._obliged(st, 2, 3)
    assert ("Vos dons les obligent", 12) in diplo.evaluate(st, 2, 3, "proteger").reasons
    assert ("Vos dons les obligent", 8) in diplo.evaluate(st, 2, 3, "tribut").reasons
