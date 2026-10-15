"""Les NOTES que lisent les IA disent vrai (tools/notes.py) : les dates, la
version, les fichiers et les noms du code qu'elles citent, leurs parties
tirees du code. Une note qui ment casse ce test, qui dit quoi faire."""

import datetime as dt
import pathlib
import sys

ROOT = pathlib.Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "tools"))
import notes  # noqa: E402

TODAY = dt.date(2026, 10, 16)


def test_the_notes_tell_the_truth():
    problems = notes.check()
    assert not problems, (
        "Les notes mentent :\n  "
        + "\n  ".join(problems)
        + "\n(les parties automatiques : python tools/notes.py write ; le reste : corriger la note)"
    )


def test_a_date_from_the_future_is_caught():
    assert notes.check_future("x", "Fait le 2026-10-18.", TODAY)
    assert not notes.check_future("x", "Fait le 2026-10-17.", TODAY)  # un jour de marge (fuseaux)
    assert not notes.check_future("x", "Fait le 2026-10-09.", TODAY)


def _vision(story: str, head: str = "2026-10-11", version: str = "0.20.2") -> str:
    return (
        f"KORA\nDerniere mise a jour : {head}.\n\n"
        "1. LE JEU\n--------\n\n"
        f"3. SES DEMANDES\n---------------\n{story}\n"
        "4. REGLES\n--------\n\n"
        f"5. OU EN EST LE JEU\n------------------\nVersion du jeu : {version}\n"
    )


def test_a_vision_entry_dated_after_its_release_is_caught():
    tags = {"0.12.0": dt.date(2026, 10, 9)}
    # La derive vue en octobre : un chantier du 9 date du 10.
    bad = notes.check_vision(_vision("2026-10-10 (0.12.0)\n  - la guerre declaree\n"), TODAY, tags, "0.20.2")
    assert any("0.12.0" in p for p in bad)
    good = notes.check_vision(_vision("2026-10-09 (0.12.0)\n  - la guerre declaree\n"), TODAY, tags, "0.20.2")
    assert good == []


def test_vision_days_go_forward_and_the_header_follows():
    out = notes.check_vision(_vision("2026-10-11\n  - a\n2026-10-09\n  - b\n", head="2026-10-11"), TODAY, {}, "0.20.2")
    assert any("l'ordre des jours" in p for p in out)
    out = notes.check_vision(_vision("2026-10-11\n  - a\n", head="2026-10-03"), TODAY, {}, "0.20.2")
    assert any("avant sa" in p for p in out)  # l'en-tete date d'avant la derniere entree


def test_the_vision_says_the_game_version():
    out = notes.check_vision(_vision("2026-10-11\n  - a\n", version="0.19.0"), TODAY, {}, "0.20.2")
    assert any("Version du jeu" in p for p in out)


def test_a_misdated_spec_is_caught(tmp_path):
    class FakeGit:
        ok = False
        tags = {"0.20.0": dt.date(2026, 10, 11)}

        def added_at(self, path):
            return None

    spec = notes.SPECS / "2026-10-18-nouvelles-planetes-design.txt"
    text = "Kora - Les planetes\n====\nDate : 2026-10-18. Statut : FAIT (version 0.20.0).\n"
    out = notes.check_spec(spec, text, TODAY, FakeGit())
    assert any("futur" in p for p in out)
    assert any("0.20.0" in p for p in out)
    text = "Kora - Les planetes\n====\nDate : 2026-10-09. Statut : FAIT.\n"
    spec = notes.SPECS / "2026-10-11-nouvelles-planetes-design.txt"
    assert any("Date : 2026-10-09" in p for p in notes.check_spec(spec, text, TODAY, FakeGit()))


def test_a_note_citing_a_vanished_name_is_caught():
    index = notes.CodeIndex()
    assert notes.check_refs("x", "Le temps : state.tick_count ; money.earn ; Tribe.situation_effects.", index) == []
    assert notes.check_refs("x", "Voir money.gagner_des_sicles.", index)
    assert notes.check_refs("x", "Voir Tribe.champ_qui_n_existe_pas.", index)
    assert notes.check_refs("x", "Le fichier src/kora/inexistant.py.", index)
    assert notes.check_refs("x", "Lire docs/code/carte-du-depot.txt et sim.py.", index) == []


def test_a_missing_spec_reference_is_caught():
    assert notes.check_spec_refs("x", "spec 2026-10-18-nouvelles-planetes-design.txt")
    assert not notes.check_spec_refs("x", "spec 2026-10-11-nouvelles-planetes-design.txt")


def test_the_automatic_parts_come_from_the_code():
    text = "<<< auto : gros-modules >>>\nfaux\n<<< fin auto >>>\n"
    assert notes.check_auto("x", text)
    assert notes.check_auto("x", notes.refresh(text)) == []
    assert "villages.py" in notes.refresh(text) or "lignes" in notes.refresh(text)


def test_status_gives_the_real_date_and_never_breaks():
    out = notes.status(short=True)
    assert str(dt.date.today()) in out
    assert notes.version() in out
