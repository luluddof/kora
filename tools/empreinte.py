"""Empreinte exacte d'une partie : prouve qu'un refactoring ne change pas le jeu.

Avant de toucher au code :
    .venv/Scripts/python.exe tools/empreinte.py record empreinte.json
Apres :
    .venv/Scripts/python.exe tools/empreinte.py check empreinte.json
Deux parties (robot de tests/test_balance.py 8 ans, joueur immobile 6 ans)
sont rejouees ; l'etat complet est compare semaine par semaine. Une
difference = le jeu a change (voulu ou non). Recuire la carte change aussi
l'empreinte : l'enregistrer de nouveau apres.
"""
import hashlib
import json
import random
import sys
import time

from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "tests"))

from src.kora.sim import _default_world, new_game, tick  # noqa: E402
from test_balance import _robot  # noqa: E402


def digest(st) -> str:
    parts = [str(st.tick_count), str(st.clock.week), str(st.clock.year)]
    for bid in sorted(st.bands):
        b = st.bands[bid]
        parts.append(
            f"{bid}|{b.tribe_id}|{b.position.q},{b.position.r}|{b.population}|{b.stock!r}"
            f"|{b.order.kind.value}|{b.order.target_band_id}|{b.order.target_hex}"
            f"|{[(h.q, h.r) for h in b.path]}|{b.growth_acc!r}|{b.retreating}|{b.shield_until}"
        )
    for tid in sorted(st.tribes):
        t = st.tribes[tid]
        parts.append(
            f"T{tid}|{t.prestige}|{t.cabotage}|{t.troupeau}|{t.coast_weeks}|{t.steppe_weeks}"
            f"|{t.shore_seen}|{t.steppe_seen}|{t.famine_during_winter}"
        )
    parts.append(str([(e.seq, e.text) for e in st.log.entries]))
    parts.append(str([(m.hex.q, m.hex.r, m.tick, m.loot) for m in st.fights]))
    parts.append(str(len(st.vision.explored)))
    parts.append(str(sorted(st.world._recovering)))
    # Tribus vivantes : chefs, attachement, savoirs, lieux, relations,
    # evenements (chantier du 24 sept.).
    for bid in sorted(st.bands):
        b = st.bands[bid]
        lead = b.leader
        parts.append(
            f"L{bid}|{lead.name if lead else ''}|{lead.traits if lead else ''}|{lead.renown if lead else ''}"
            f"|{b.loyalty!r}|{b.village}|{b.honored}|{b.kind}|{b.home}|{b.raised}"
            f"|{b.units}|{b.homebound}|{[p.pid for p in b.notables]}|{b.welded_until}|{b.autonomy!r}"
        )
    # Batailles (battle.py) : issue et passes d'armes.
    parts.append(str([(m.report or {}).get("headline", "") + str((m.report or {}).get("rounds", "")) for m in st.fights]))
    for tid in sorted(st.tribes):
        t = st.tribes[tid]
        parts.append(
            f"K{tid}|{sorted(t.knowledge)}|{t.learning}|{sorted(t.progress.items())}"
            f"|{sorted(t.flags.items())}|{t.chief_band}|{t.heir}|{t.name}|{t.settled_at}|{t.civ}"
            f"|{sorted(t.goods.items())}|{sorted(t.trade.items(), key=str)}|{sorted(t.practice.items())}"
        )
    for sid in sorted(st.sites):
        site = st.sites[sid]
        parts.append(f"S{sid}|{site.kind}|{site.tribe_id}|{site.hex}|{site.store!r}|{sorted(site.data.items(), key=str)}")
    parts.append(str(sorted(st.diplo.contacts)))
    parts.append(str(sorted((k, [(m.key, m.value) for m in v]) for k, v in st.diplo.mods.items())))
    parts.append(str(sorted((k, [(p.kind, p.until) for p in v]) for k, v in st.diplo.pacts.items())))
    book = st.events
    if book is not None:
        parts.append(str([(p.event_id, p.band_id, p.deadline) for p in book.pending]))
        parts.append(str(sorted(map(str, book.scheduled))))
    parts.append(str(len(st.world._influence)))
    return hashlib.sha1("\n".join(parts).encode()).hexdigest()


def play(robot: bool, years: int, seed: int) -> list[str]:
    st = new_game(_default_world())
    st.rng = random.Random(seed)
    out = [digest(st)]
    for _ in range(52 * years):
        if robot:
            _robot(st)
        tick(st)
        st.clock.paused = False
        assert st.last_error is None, st.last_error
        out.append(digest(st))
    return out


def run() -> dict:
    t = time.time()
    data = {"robot": play(True, 8, 1), "idle": play(False, 6, 2)}
    data["seconds"] = round(time.time() - t, 1)
    return data


if __name__ == "__main__":
    mode, path = sys.argv[1], sys.argv[2]
    data = run()
    if mode == "record":
        json.dump(data, open(path, "w"))
        print("recorded", len(data["robot"]), len(data["idle"]), "ticks in", data["seconds"], "s")
    else:
        ref = json.load(open(path))
        for key in ("robot", "idle"):
            bad = next((i for i, (a, b) in enumerate(zip(ref[key], data[key])) if a != b), None)
            if bad is None and len(ref[key]) == len(data[key]):
                print(key, "IDENTIQUE sur", len(data[key]), "ticks")
            else:
                print(key, "DIFFERENT a partir du tick", bad)
        print("temps", data["seconds"], "s (reference", ref["seconds"], "s)")
