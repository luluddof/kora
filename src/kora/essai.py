"""L'essai du multijoueur sans fenetre : un hote et un ami joues par des
robots qui ne passent que par des ordres (commands.py), sur la vraie carte.
Chacun ecrit ses empreintes (session.sync_digest) dans un fichier JSON.

Deux usages :
  - tools/essai_reseau.py lance deux processus Python ;
  - l'exe lui-meme : KORA_ESSAI=hote|ami, KORA_ESSAI_PORT, KORA_ESSAI_ANS,
    KORA_ESSAI_SORTIE (le fichier resultat). Invisible pour les joueurs :
    sans ces variables, Kora.exe lance le jeu.
N'importe pas pygame.
"""

from __future__ import annotations

import json
import os
import random
import time
from pathlib import Path
from src.kora.commands import make
from src.kora.sim import _default_world
from src.kora import chiefs, money, orders, situations, tech, villages


def robot(state, issue, me: int, rng: random.Random) -> None:
    """Un joueur presse : des ordres a ses bandes, par le canal des ordres.
    Ne touche JAMAIS la partie directement (sinon les machines divergent)."""
    mine = sorted((b for b in state.bands.values() if b.tribe_id == me and b.population > 0), key=lambda b: b.id)
    if not mine:
        return
    tribe = state.tribes[me]
    if not tribe.learning:
        ready = sorted((tid for tid in tech.TECHS if tech.status(state, me, tid) == "disponible"), key=lambda t: (tech.TECHS[t].cost, t))
        if ready:
            issue(make(me, "learn", ready[0]))
    # Les nombres et l'argent : une base, un budget (ordres "base", "budget").
    b = tech.bonuses(tribe)
    if b.numbers and not tribe.base:
        issue(make(me, "base", (10, 12, 20, 60)[me % 4]))
    if b.money and rng.random() < 0.1:
        issue(make(me, "budget", "tax", rng.randrange(4)))
        issue(make(me, "budget", rng.choice(money.TOGGLE_KEYS), rng.random() < 0.5))
    # Les situations : une action permise, de temps en temps (ordre "situation").
    for inst in situations.of_tribe(state, me):
        if rng.random() < 0.25:
            ok = [a.id for a in situations.SPECS[inst.sid].actions if not situations.action_block(state, inst, me, a.id)]
            if ok:
                issue(make(me, "situation", inst.uid, rng.choice(ok)))
    band = rng.choice(mine)
    if band.village:
        site = villages.site_of(state, band)
        if site is not None and rng.random() < 0.3:
            pick = next((b for b in villages.BUILD_ORDER if villages.building_status(state, site, b) == "possible"), None)
            if pick:
                issue(make(me, "build", band.id, pick))
        return
    if not chiefs.obeys(state, band):
        issue(make(me, "honor", band.id))
        return
    acts = orders.band_actions(state, band.id)
    roll = rng.random()
    if roll < 0.08 and acts.get("split") == "":
        issue(make(me, "band", band.id, "split"))
    elif roll < 0.14 and acts.get("camp") == "":
        issue(make(me, "band", band.id, "camp"))
    elif roll < 0.2 and acts.get("village") == "" and villages.found_block(state, band.id) == "":
        issue(make(me, "found", band.id, sorted(villages.OATHS)[0]))
    elif roll < 0.25 and acts.get("merge") == "":
        issue(make(me, "band", band.id, "merge"))
    else:
        spots = [h for h in state.world.hexes_in_radius(band.position, 5) if h != band.position]
        if spots:
            h = rng.choice(spots)
            issue(make(me, "goto", band.id, h.q, h.r))


def host_run(port: int, years: int) -> dict:
    from src.kora import session
    host = session.HostSession({"name": "Aroha", "color": (220, 70, 70), "bonuses": ["bonus:conteurs", "bonus:froid"]}, port=port)
    end = time.time() + 90
    while time.time() < end and host.can_start():
        host.pump_lobby()
        time.sleep(0.01)
    state = host.start(_default_world())
    host.set_speed(5)
    rng = random.Random(1)
    target = state.tick_count + 52 * years
    digests = {}
    frame = 0
    t0 = time.time()
    while host.state.tick_count < target and time.time() - t0 < 1200:
        host.pump(0.05)
        frame += 1
        if frame % 3 == 0:
            robot(host.state, host.issue, 1, rng)
        n = host.state.step
        if n % session.DIGEST_EVERY == 0 and n not in digests:
            digests[n] = session.sync_digest(host.state)
        time.sleep(0.005)
    host.toggle_pause()
    stop = time.time() + 5
    while time.time() < stop:
        host.pump(0.05)
        time.sleep(0.01)
    st = host.state
    digests[st.step] = session.sync_digest(st)
    out = {
        "role": "hote",
        "tick": st.step,
        "digests": digests,
        "resyncs": host.resyncs,
        "seconds": round(time.time() - t0, 1),
        "bands": sum(1 for b in st.bands.values() if b.tribe_id in (1, 2)),
        "villages": sum(1 for s in st.sites.values() if s.kind == "village" and s.tribe_id in (1, 2)),
        # Situations nees, et actions des deux joueurs dans les leurs.
        "situations": st.next_situation_uid - 1,
        "acts": sum(len(p["acted"]) for inst in st.situations for t, p in inst.participants.items() if t in (1, 2)),
    }
    host.close()
    return out


def client_run(port: int, years: int) -> dict:
    from src.kora import net, session
    conn = None
    for _ in range(300):
        try:
            conn = net.connect("127.0.0.1", port)
            break
        except OSError:
            time.sleep(0.1)
    client = session.ClientSession(conn, {"name": "Tahu", "color": (60, 190, 190), "bonuses": ["bonus:guerriers", "bonus:fertiles"]})
    while client.me is None and not client.ended:
        client.pump_lobby()
        time.sleep(0.01)
    client.set_ready(True)
    while client.snap is None and not client.ended:
        client.pump_lobby()
        time.sleep(0.01)
    client.begin(_default_world())
    rng = random.Random(2)
    digests = {}
    frame = 0
    t0 = time.time()
    while not client.ended and time.time() - t0 < 1200:
        client.pump(0.05)
        frame += 1
        if frame % 3 == 0 and not client.state.clock.paused:
            robot(client.state, client.issue, 2, rng)
        n = client.state.step
        if n % session.DIGEST_EVERY == 0 and n not in digests:
            digests[n] = session.sync_digest(client.state)
        time.sleep(0.005)
    digests[client.state.step] = session.sync_digest(client.state)
    return {"role": "ami", "tick": client.state.step, "digests": digests, "resyncs": client.resyncs}


def compare(host: dict, friend: dict) -> tuple[bool, str]:
    common = sorted(set(host["digests"]) & set(friend["digests"]), key=int)
    bad = [n for n in common if host["digests"][n] != friend["digests"][n]]
    lines = [
        f"hôte : semaine {host['tick']} en {host['seconds']} s, {host['bands']} bandes et {host['villages']} villages aux deux joueurs",
        f"ami  : semaine {friend['tick']}",
        f"situations nées : {host.get('situations', 0)} ; actions des joueurs encore visibles : {host.get('acts', 0)}",
        f"empreintes comparées : {len(common)} ; différentes : {len(bad)} ; resynchronisations : hôte {host['resyncs']}, ami {friend['resyncs']}",
    ]
    ok = not bad and host["resyncs"] == 0 and friend["resyncs"] == 0 and host["tick"] == friend["tick"]
    lines.append("IDENTIQUES" if ok else "DIFFÉRENTES")
    return ok, "\n".join(lines)


def from_env() -> bool:
    """Kora.exe lance avec KORA_ESSAI : l'essai au lieu du jeu. Rend True
    si un essai a tourne."""
    role = os.environ.get("KORA_ESSAI", "")
    if role not in ("hote", "ami"):
        return False
    port = int(os.environ.get("KORA_ESSAI_PORT", "45170"))
    years = int(os.environ.get("KORA_ESSAI_ANS", "2"))
    out = host_run(port, years) if role == "hote" else client_run(port, years)
    target = os.environ.get("KORA_ESSAI_SORTIE", "")
    if target:
        Path(target).write_text(json.dumps(out), encoding="utf-8")
    return True
