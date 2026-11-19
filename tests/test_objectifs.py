"""Des interfaces qui se lisent (0.32.0) : ce qui attend le joueur
(objectifs.py : les alertes, le chemin du premier village), le sens des
effets (events.effect_tone, theme.tone_of), le journal qui regroupe ce qui
se repete (log.group_repeats), la fiche de l'unite qui evite le panneau
ouvert (layout.band_card_layout)."""

from src.kora import events, objectifs, theme
from src.kora.places import Site
from src.kora.layout import band_card_layout
from src.kora.log import LogEntry, LogKind, group_repeats, merged_text
from src.kora.sim import new_game
from src.kora.types import Terrain
from src.kora.world import make_filled_world


def _game(terrain=Terrain.VALLEE):
    return new_game(make_filled_world(40, 24, terrain, wrap_x=True))


def test_the_path_to_the_first_village_has_four_steps_and_says_what_is_missing():
    st = _game()
    goal = objectifs.chemin(st)
    assert goal is not None and len(goal["steps"]) == 4
    assert goal["current"] == 0, "au début, il faut d'abord savoir camper"
    assert not any(s["done"] for s in goal["steps"])
    # L'etape en cours dit ce qui manque, en mots (jamais une liste vide).
    assert goal["steps"][0]["lines"]


def test_knowing_how_to_camp_checks_the_first_step():
    st = _game()
    tribe = st.tribes[st.viewer]
    tribe.knowledge.add(objectifs.CAMP_TECH)
    st.tick_count += 1  # la memoire d'une semaine
    goal = objectifs.chemin(st)
    assert goal["steps"][0]["done"]
    assert goal["current"] == 1
    # Premieres semailles : ses conditions, avec les chiffres du peuple.
    text = " ".join(t for t, _ok in goal["steps"][1]["lines"])
    assert "sur" in text or "D'abord" in text


def test_no_path_once_the_people_has_a_village():
    st = _game()
    village = Site(id=999, kind="village", tribe_id=st.viewer, hex=st.bands[1].position)
    st.sites[village.id] = village
    st.tick_count += 1
    assert objectifs.chemin(st) is None


def test_a_starving_band_raises_a_red_alert_that_leads_to_it():
    st = _game()
    b = st.bands[1]
    assert not [a for a in objectifs.alertes(st) if a["key"] == f"faim:{b.id}"]
    b.famine_tick = st.tick_count
    st.tick_count += 1
    b.famine_tick = st.tick_count
    alerts = objectifs.alertes(st)
    mine = [a for a in alerts if a["key"] == f"faim:{b.id}"]
    assert mine and mine[0]["tone"] == "danger"
    assert mine[0]["action"] == f"tribe_see:{b.id}"


def test_alerts_put_the_gravest_first():
    st = _game(Terrain.DESERT)
    b = st.bands[1]
    b.stock = 2.0 * b.population  # disette (la collecte du desert ne suffit pas)
    st.tick_count += 1
    alerts = objectifs.alertes(st)
    tones = [a["tone"] for a in alerts]
    assert tones == sorted(tones, key=lambda t: objectifs.GRAVITY[t])
    assert any(a["tone"] == "alerte" for a in alerts)


def test_event_effects_have_a_meaning_not_a_colour():
    assert events.effect_tone(("stock", -1)) == "perte"
    assert events.effect_tone(("stock", 2)) == "gain"
    assert events.effect_tone(("pop", 4, 7)) == "gain"
    assert events.effect_tone(("pop", -3, -1)) == "perte"
    assert events.effect_tone(("pact", "tribut_paye")) == "perte"
    assert events.effect_tone(("pact", "alliance")) == "gain"
    assert events.effect_tone(("secede",)) == "perte"
    assert events.effect_tone(("reveal",)) == "gain"
    assert events.effect_tone(("stop",)) == "neutre"


def test_every_event_option_has_chips():
    st = _game()
    for ev in list(events.EVENTS.values())[:40]:
        inst = events._new_instance(st, ev, st.viewer, 1)
        for opt in ev.options:
            chips = events.summary_chips(st, inst, opt)
            assert chips, ev.id
            assert all(tone in theme.TONES for _t, tone in chips)


def test_tone_of_a_bare_text():
    assert theme.tone_of("+3 prestige") == "gain"
    assert theme.tone_of("-2 sem. de vivres") == "perte"
    assert theme.tone_of("Relation -10 avec les deux peuples") == "perte"
    assert theme.tone_of("Moins de morts de faim", "gain") == "gain"


def test_the_journal_merges_lines_that_only_differ_by_their_numbers():
    rows = [
        LogEntry(2, 14, LogKind.SURVIE, "Famine : 3 morts.", seq=10),
        LogEntry(2, 13, LogKind.SURVIE, "Famine : 1 morts.", seq=9),
        LogEntry(2, 12, LogKind.SURVIE, "Famine : 2 morts.", seq=8),
        LogEntry(2, 11, LogKind.POLITIQUE, "Un clan vous rejoint.", seq=7),
        LogEntry(2, 10, LogKind.SURVIE, "Famine : 1 morts.", seq=6),
    ]
    groups = group_repeats(rows)
    assert [g["count"] for g in groups] == [3, 1, 1], "seules les lignes qui se suivent se regroupent"
    assert groups[0]["text"] == "Famine : 6 morts."
    assert groups[0]["entry"].seq == 10 and groups[0]["first"].seq == 8
    assert merged_text(["À 1 et 2", "À 3 et 4"]) == "À 1 et 2", "deux nombres : on ne somme pas"


def test_the_band_card_steps_aside_for_an_open_panel():
    alone = band_card_layout(1600, 900, 4)
    panel = (846, 64, 680, 660)
    moved = band_card_layout(1600, 900, 4, avoid=panel)
    bx, by, bw, bh = moved["box"]
    assert bx + bw <= panel[0], "à gauche du panneau"
    assert (bx, by) != tuple(alone["box"][:2])
    # Plus de place du tout : la fiche attend que le panneau se ferme.
    hidden = band_card_layout(800, 600, 4, avoid=(60, 64, 700, 520))
    assert hidden.get("hidden") and hidden["buttons"] == {}
