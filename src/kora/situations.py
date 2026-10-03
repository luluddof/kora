"""Les SITUATIONS : crises et conjonctures (spec 2026-10-02-profondeur-
epoques-situations.txt), inspirees d'EU5 (situations, catastrophes) et de
Stellaris (crises).

  CRISE : un malheur qui frappe un peuple ou une region. Une jauge de
  resolution (0 a 100) que les peuples touches font monter (leur facon de
  vivre, leurs actions) ; des etapes qui s'aggravent. Resolue : tout revient
  comme avant (ses effets s'eteignent). Ratee : des pertes durables.
  CONJONCTURE : un moment du monde qui met des peuples en concurrence. Un
  score par peuple ; a la fin, le premier gagne un prix s'ils etaient au
  moins deux.

Une situation nait d'un CONTEXTE (saison, terrain, foule, voisins, savoirs),
la part de hasard (_rand : son propre hasard, tire de la semaine et de la
situation, le meme sur chaque machine, qui ne touche pas a celui du recit)
dit seulement quand. Elle a un lieu
(centre, rayon ; ou tout un peuple ; ou la moitie du monde), des etapes aux
effets chiffres (les memes leviers que les savoirs, tech.SITUATION_EFFECTS),
des actions (commands.py : "situation"), une duree.

Tout est dans state.situations (sauvegarde : persist) ; les effets actifs
d'un peuple sont dans Tribe.situation_effects ([id, jusqu'a], -1 : tant que
la situation dure). N'importe pas pygame.
"""

from __future__ import annotations

from dataclasses import dataclass, field

from src.kora import chiefs, population, tech
from src.kora.log import LogKind
from src.kora.types import Hex, Season, Terrain
from src.kora.gamestate import humans, is_human, note
from src.kora.world import axial_to_offset, enter_cost_for
from src.kora.bands import gain_prestige, set_goto

MONTH = 4
YEAR = 52
CRISE = "crise"
CONJONCTURE = "conjoncture"
# Une situation finie reste dans la liste (le journal, l'ecran) ce temps-la.
KEEP_ENDED = YEAR
ALL_TERRAINS = tuple(Terrain)


def _food(mult: float, terrains=ALL_TERRAINS) -> dict:
    return {t: mult for t in terrains}


@dataclass
class Situation:
    uid: int
    sid: str
    started: int
    until: int
    center: Hex | None = None
    radius: int = 0  # 0 : tout le peuple ; -1 : une moitie du monde (data["moitie"])
    stage: int = 0
    progress: float = 0.0
    # tid -> {"score": float, "joined": tick, "acted": {action: tick}, "pop0": int}
    participants: dict = field(default_factory=dict)
    data: dict = field(default_factory=dict)
    outcome: str = ""  # "" en cours, "resolue", "ratee", "gagnee", "finie"
    ended: int = -1
    winner: int = 0


@dataclass(frozen=True)
class Action:
    id: str
    label: str
    about: str
    prestige: int = 0
    vivres: int = 0
    cooldown: int = 3 * MONTH
    progress: float = 0.0
    score: float = 0.0


class Spec:
    """Une situation : son contexte, ses etapes, ses actions, sa fin."""

    id = ""
    name = ""
    kind = CRISE
    era = None  # 0 : age tribal, 1 : age des villages, None : les deux
    icon = "crise"
    about = ""
    goal = ""  # comment on en sort (crise) ou comment on gagne (conjoncture)
    fail = ""  # ce que coute une crise ratee
    stages: tuple = ()  # (nom, recit, effets)
    actions: tuple = ()
    months = 12
    cooldown = 4 * YEAR
    natural = 0.0  # jauge gagnee chaque mois sans rien faire (une crise s'use)

    # --- a definir -------------------------------------------------------------
    def candidates(self, state) -> list:
        """Les situations qui pourraient naitre : [(centre, rayon, peuples, data)]."""
        return []

    def chance(self, state) -> float:
        return 0.3

    def month(self, state, inst) -> None:
        """Le mois de la situation : jauge, score, effets directs."""

    def end(self, state, inst) -> None:
        """La fin (inst.outcome est connu)."""

    def risk(self, state, tid: int) -> str:
        """Une crise qui menace ce peuple : ce qui la fait venir et comment
        l'eviter ("" : rien). Les conjonctures ne previennent pas."""
        return ""

    # --- communs ---------------------------------------------------------------
    def effect_id(self, stage: int) -> str:
        return f"sit:{self.id}:{stage}"

    def stage_name(self, inst) -> str:
        return self.stages[min(inst.stage, len(self.stages) - 1)][0] if self.stages else ""

    def stage_text(self, inst) -> str:
        return self.stages[min(inst.stage, len(self.stages) - 1)][1] if self.stages else ""


# --- outils ---------------------------------------------------------------------


def _rand(state, *keys) -> float:
    """Le hasard des situations : tire de la semaine et de ces cles (une
    chaine -> SHA-512 : le meme sur chaque machine, quelle que soit la graine
    de hachage), sans toucher au hasard du recit (state.story_rng)."""
    import random

    return random.Random("kora-situation:" + str(state.tick_count) + ":" + ":".join(str(k) for k in keys)).random()


def _alive(state, tid: int) -> bool:
    return any(b.tribe_id == tid and b.population > 0 for b in state.bands.values())


def _bands(state, tid: int, village=None):
    out = [b for b in state.bands.values() if b.tribe_id == tid and b.population > 0 and b.kind != "armee"]
    if village is True:
        out = [b for b in out if b.village]
    elif village is False:
        out = [b for b in out if not b.village]
    return sorted(out, key=lambda b: b.id)


def _has_village(state, tid: int) -> bool:
    return any(s.kind == "village" and s.tribe_id == tid for s in state.sites.values())


def _era_of(state, tid: int) -> int:
    return 1 if _has_village(state, tid) else 0


def in_zone(state, inst, h) -> bool:
    if inst.radius == 0:
        return True
    if inst.radius < 0:
        _col, row = axial_to_offset(state.world.canonicalize(h) or h)
        north = row < state.world.height // 2
        return north == (inst.data.get("moitie") == "nord")
    return inst.center is not None and state.world.distance(h, inst.center) <= inst.radius


def zone_bands(state, inst, tid: int, village=None) -> list:
    return [b for b in _bands(state, tid, village) if in_zone(state, inst, b.position)]


def _note(state, tid: int, kind, text: str, where=None) -> None:
    if is_human(state, tid):
        note(state, kind, text, where, to=tid)


def _deaths(state, bands, share: float) -> int:
    lost = 0
    for b in bands:
        n = min(b.population - 1, max(1, round(b.population * share))) if b.population > 4 else 0
        b.population -= n
        lost += n
    return lost


def _pay_vivres(state, tid: int, amount: float, bands=None) -> bool:
    bands = bands if bands is not None else _bands(state, tid)
    have = sum(max(0.0, b.stock - b.population) for b in bands)
    if have < amount:
        return False
    left = amount
    for b in sorted(bands, key=lambda b: -b.stock):
        take = min(left, max(0.0, b.stock - b.population))
        b.stock -= take
        left -= take
        if left <= 0:
            break
    return True


def _season(state) -> Season:
    return state.clock.season()


def _mean_weeks(bands) -> float:
    pop = sum(b.population for b in bands)
    return sum(b.stock for b in bands) / max(1, pop)


# --- AGE TRIBAL -------------------------------------------------------------------


class Disette(Spec):
    id = "disette"
    goal = "Refaire des réserves : la jauge monte quand il y a plus de deux semaines de vivres, et vite à la belle saison."
    fail = "Ratée : encore des morts de faim, prestige -10."
    name = "La disette"
    kind = CRISE
    icon = "famine"
    about = "Les réserves sont vides avant le retour des beaux jours. Il faut tenir jusqu'au printemps."
    stages = (
        ("Les ventres creux", "On mange moins, on fait moins d'enfants ; les clans grondent.", {"growth": 0.6, "loyalty": -3}),
        ("La faim", "Les plus faibles meurent. Les clans regardent vers ceux qui ont encore de quoi.", {"growth": 0.3, "loyalty": -6}),
    )
    actions = (
        Action("rationner", "Rationner", "Chaque bouche reçoit moins : on tient plus longtemps, mais les clans le prennent mal.", progress=20, cooldown=3 * MONTH),
        Action("battue", "Grande battue", "Tous les chasseurs ensemble, pour remplir les caches.", prestige=10, progress=15, cooldown=4 * MONTH),
        Action("partager", "Partager entre clans", "Les vivres des mieux lotis vont aux affamés.", progress=10, cooldown=6 * MONTH),
    )
    months = 12
    cooldown = 6 * YEAR
    natural = 0.0

    def candidates(self, state):
        if _season(state) not in (Season.HIVER, Season.PRINTEMPS):
            return []
        out = []
        for tid in sorted(state.tribes):
            bands = _bands(state, tid, village=False)
            pop = sum(b.population for b in bands)
            if pop < 30:
                continue
            # Une vraie famine : la moitie du peuple a eu faim ces deux derniers
            # mois, et plus rien en reserve.
            hungry = sum(b.population for b in bands if state.tick_count - b.famine_tick <= 2 * MONTH)
            if hungry * 2 >= pop and _mean_weeks(bands) < 1.0:
                out.append((None, 0, [tid], {}))
        return out

    def chance(self, state):
        return 0.25

    def month(self, state, inst):
        tid = next(iter(inst.participants))
        bands = _bands(state, tid, village=False)
        weeks = _mean_weeks(bands)
        gain = max(-5.0, min(25.0, (weeks - 2.0) * 9.0))
        if _season(state) in (Season.ETE, Season.AUTOMNE):
            gain += 12.0
        inst.progress += gain
        months = (state.tick_count - inst.started) // MONTH
        if inst.stage == 0 and months >= 2 and inst.progress < 30:
            inst.stage = 1
            _note(state, tid, LogKind.SURVIE, "La disette s'aggrave : la faim tue.")
        if inst.stage >= 1:
            lost = _deaths(state, bands, 0.02)
            if lost:
                _note(state, tid, LogKind.SURVIE, f"La faim : {lost} morts ce mois-ci.")

    def act(self, state, inst, tid, action):
        if action == "rationner":
            for b in _bands(state, tid):
                b.loyalty = max(0.0, b.loyalty - 3.0)
        elif action == "battue":
            for b in _bands(state, tid, village=False):
                b.stock += b.population * 2.5
        elif action == "partager":
            bands = _bands(state, tid)
            total = sum(b.stock for b in bands)
            pop = sum(b.population for b in bands)
            for b in bands:
                b.stock = total * b.population / max(1, pop)

    def end(self, state, inst):
        tid = next(iter(inst.participants))
        if inst.outcome == "ratee":
            lost = _deaths(state, _bands(state, tid), 0.05)
            tribe = state.tribes.get(tid)
            if tribe is not None:
                tribe.prestige = max(0, tribe.prestige - 10)
            _note(state, tid, LogKind.SURVIE, f"La disette laisse des traces : {lost} morts de plus, prestige -10.")


class MalQuiCourt(Spec):
    id = "mal"
    goal = "Le mal s'use seul, lentement ; isoler les malades, les rites et la fuite le font reculer plus vite."
    fail = "Ratée : le mal emporte encore des clans entiers."
    name = "Le mal qui court"
    kind = CRISE
    icon = "epidemie"
    about = "Une fièvre passe de bande en bande. Elle prend ceux qui vivent serrés, et voyage avec eux."
    stages = (
        ("Les premiers malades", "Des enfants toussent, des anciens ne se lèvent plus.", {"learn": 0.9}),
        ("L'épidémie", "Le mal est partout dans le pays. On n'ose plus se réunir.", {"learn": 0.8, "growth": 0.6}),
        ("Le reflux", "Ceux qui ont survécu ne tombent plus malades. Le mal recule.", {"growth": 0.8}),
    )
    actions = (
        Action("isoler", "Isoler les malades", "Les malades vivent à part ; les bandes ne se réunissent plus un temps.", progress=20, cooldown=3 * MONTH),
        Action("rites", "Rites de guérison", "Les anciens connaissent des plantes, des chants.", prestige=8, progress=15, cooldown=3 * MONTH),
        Action("fuir", "Fuir le mal", "Les bandes saines s'éloignent du lieu du mal.", progress=8, cooldown=4 * MONTH),
    )
    months = 12
    cooldown = 4 * YEAR
    natural = 4.0

    def candidates(self, state):
        if _season(state) not in (Season.ETE, Season.AUTOMNE):
            return []
        out = []
        bands = [b for b in state.bands.values() if b.population >= 90 and b.kind != "armee"]
        for b in sorted(bands, key=lambda b: b.id):
            near = [o for o in state.bands.values() if o.id != b.id and o.population > 0 and state.world.distance(o.position, b.position) <= 3]
            if near:
                tids = sorted({b.tribe_id} | {o.tribe_id for o in near})
                out.append((b.position, 8, tids, {}))
        return out[:1]

    def chance(self, state):
        return 0.12

    def month(self, state, inst):
        # Le mal s'etend aux bandes voisines (de tous les peuples).
        world = state.world
        sick = [b for t in inst.participants for b in zone_bands(state, inst, t)]
        if inst.radius < 16:
            for o in sorted(state.bands.values(), key=lambda b: b.id):
                if o.population <= 0 or o.kind == "armee" or o.tribe_id in inst.participants:
                    continue
                if any(world.distance(o.position, s.position) <= 4 for s in sick) and _rand(state, inst.uid, "mal", o.id) < 0.5:
                    join(state, inst, o.tribe_id)
                    inst.radius = min(16, inst.radius + 2)
        share = {0: 0.02, 1: 0.04, 2: 0.01}[min(inst.stage, 2)]
        for t in sorted(inst.participants):
            lost = _deaths(state, zone_bands(state, inst, t), share)
            if lost:
                _note(state, t, LogKind.SURVIE, f"Le mal qui court : {lost} morts.")
        months = (state.tick_count - inst.started) // MONTH
        if inst.stage == 0 and months >= 2:
            inst.stage = 1
        if inst.stage == 1 and inst.progress >= 55:
            inst.stage = 2

    def act(self, state, inst, tid, action):
        tribe = state.tribes.get(tid)
        if action == "isoler" and tribe is not None:
            tribe.flags["isoles"] = state.tick_count + 3 * MONTH
        elif action == "rites" and _rand(state, inst.uid, "rites", tid) < 0.5:
            inst.progress += 10
        elif action == "fuir":
            for b in zone_bands(state, inst, tid, village=False):
                spot = _away(state, b.position, inst.center, 8)
                if spot is not None:
                    set_goto(state, b.id, spot, max_nodes=300, max_cost=600)

    def end(self, state, inst):
        if inst.outcome == "ratee":
            for tid in sorted(inst.participants):
                lost = _deaths(state, _bands(state, tid), 0.04)
                _note(state, tid, LogKind.SURVIE, f"Le mal n'a pas été arrêté à temps : {lost} morts de plus.")


def _away(state, h, center, dist):
    """Une case praticable a `dist` cases, a l'oppose de `center`."""
    world = state.world
    best = None
    for c in world.hexes_in_radius(h, dist)[::3]:
        if enter_cost_for(world, c, False) is None:
            continue
        d = world.distance(c, center) if center is not None else 0
        if best is None or d > best[0]:
            best = (d, c)
    return best[1] if best else None


class GibierEpuise(Spec):
    id = "gibier"
    goal = "Quitter le pays épuisé : la jauge monte avec la part des bandes qui chassent ailleurs, et quand la terre se refait."
    fail = "Ratée : la chasse rapporte moins pendant 2 ans, prestige -5."
    name = "Le gibier s'épuise"
    kind = CRISE
    era = 0
    icon = "cerf"
    about = "On a trop chassé, trop cueilli au même endroit : le pays ne nourrit plus. Il faut laisser la terre se refaire."
    stages = (
        ("Le pays maigrit", "Les pièges restent vides, les baies se font rares.", {"food": _food(0.85)}),
        ("La terre est vide", "Plus rien autour des camps : il faut partir ou mourir.", {"food": _food(0.7)}),
    )
    actions = (
        Action("laisser", "Laisser la terre", "Les bandes partent chasser plus loin et ne reviennent qu'au printemps.", progress=15, cooldown=6 * MONTH),
        Action("rites", "Rites du gibier", "On demande pardon aux bêtes ; on promet de ne plus tuer les mères.", prestige=6, progress=12, cooldown=4 * MONTH),
    )
    months = 18
    cooldown = 5 * YEAR
    natural = 4.0

    def candidates(self, state):
        out = []
        for tid in sorted(state.tribes):
            if _has_village(state, tid):
                continue
            heart = chiefs.chief_band(state, tid)
            if heart is None or heart.village:
                continue
            hexes = state.world.hexes_in_radius(heart.position, 5)
            mean = sum(state.world.exhaustion(h) for h in hexes) / max(1, len(hexes))
            if mean < 0.78:
                out.append((heart.position, 9, [tid], {"mean": round(mean, 3)}))
        return out

    def chance(self, state):
        return 0.3

    def month(self, state, inst):
        tid = next(iter(inst.participants))
        bands = _bands(state, tid, village=False)
        inside = [b for b in bands if in_zone(state, inst, b.position)]
        out_share = 1.0 - len(inside) / max(1, len(bands))
        inst.progress += 25.0 * out_share
        hexes = state.world.hexes_in_radius(inst.center, 5)
        mean = sum(state.world.exhaustion(h) for h in hexes) / max(1, len(hexes))
        if mean > max(0.85, inst.data.get("mean", 0.7) + 0.1):
            # La terre s'est refaite.
            inst.progress += 15
        months = (state.tick_count - inst.started) // MONTH
        if inst.stage == 0 and months >= 3 and inst.progress < 35:
            inst.stage = 1
            _note(state, tid, LogKind.SURVIE, "La terre est vide : partez chasser ailleurs.", inst.center)

    def act(self, state, inst, tid, action):
        if action == "laisser":
            tribe = state.tribes.get(tid)
            if tribe is not None:
                tribe.prestige = max(0, tribe.prestige - 2)

    def end(self, state, inst):
        if inst.outcome == "ratee":
            for tid in sorted(inst.participants):
                tribe = state.tribes[tid]
                tribe.prestige = max(0, tribe.prestige - 5)
                grant_effect(tribe, "sit:gibier:maigre", state.tick_count + 2 * YEAR)
                _note(state, tid, LogKind.SURVIE, "Le pays est resté vide : la chasse rapporte moins (2 ans), prestige -5.")


class GrandHiver(Spec):
    id = "grand_hiver"
    goal = "Tenir : le ciel s'éclaircit après l'hiver sans fin. Les vallées, les abris et les réserves sauvent."
    fail = "Celui qui perd le moins de monde en sort grandi."
    name = "Le grand hiver"
    kind = CRISE
    icon = "froid"
    about = "Le ciel s'est voilé : une montagne a craché sa cendre très loin. L'hiver sera long, pour tous les peuples de cette moitié du monde."
    stages = (
        ("Le ciel voilé", "Le soleil est pâle ; l'automne est froid, les baies ne mûrissent pas.", {"food": _food(0.85)}),
        ("L'hiver sans fin", "La neige ne part plus. Seuls les abris, les réserves et les vallées sauvent.", {"food": _food(0.75), "winter_famine": 1.5}),
        ("Le ciel s'éclaircit", "Le soleil revient, la terre se réveille lentement.", {"food": _food(0.9)}),
    )
    actions = (
        Action("terrer", "Se terrer dans les vallées", "Les bandes descendent dans les vallées abritées, près des feux.", progress=15, cooldown=12 * MONTH),
        Action("fumer", "Fumer et sécher", "Tout ce qui se chasse est fumé et caché : on tiendra.", progress=10, cooldown=6 * MONTH),
    )
    months = 18
    cooldown = 25 * YEAR
    natural = 5.0

    def candidates(self, state):
        if state.clock.week not in range(34, 40) or state.clock.year < 4:
            return []
        half = "nord" if _rand(state, self.id, "moitie") < 0.5 else "sud"
        return [(None, -1, None, {"moitie": half})]

    def chance(self, state):
        return 1.0 / 30.0

    def start(self, state, inst):
        for tid in sorted(state.tribes):
            if any(in_zone(state, inst, b.position) for b in _bands(state, tid)):
                join(state, inst, tid)

    def month(self, state, inst):
        months = (state.tick_count - inst.started) // MONTH
        if inst.stage == 0 and _season(state) is Season.HIVER:
            inst.stage = 1
        if inst.stage == 1 and months >= 10:
            inst.stage = 2
        if inst.stage == 2:
            inst.progress += 15

    def act(self, state, inst, tid, action):
        until = state.tick_count + 6 * MONTH
        if action == "terrer":
            grant_effect(state.tribes[tid], "sit:grand_hiver:abri", until)
        elif action == "fumer":
            grant_effect(state.tribes[tid], "sit:grand_hiver:fume", until)

    def end(self, state, inst):
        # Ceux qui ont le mieux tenu : un peu de prestige (on raconte leur hiver).
        losses = {}
        for tid, p in inst.participants.items():
            now = sum(b.population for b in _bands(state, tid))
            losses[tid] = 1.0 - now / max(1, p.get("pop0", now))
        if len(losses) >= 2:
            best = min(sorted(losses), key=lambda t: losses[t])
            tribe = state.tribes.get(best)
            if tribe is not None:
                tribe.prestige = min(100, tribe.prestige + 5)
                for t in inst.participants:
                    _note(state, t, LogKind.DECOUVERTE, f"Le grand hiver est fini. Les {tribe.name} sont ceux qui l'ont le mieux traversé (prestige +5).")


PASSAGE_MEAT = 300.0


class GrandPassage(Spec):
    id = "passage"
    goal = "Avoir le plus de chasseurs dans le couloir des troupeaux, mois après mois : il avance, il faut le suivre."
    name = "Le grand passage"
    kind = CONJONCTURE
    era = 0
    icon = "bison"
    about = "Les grands troupeaux traversent la plaine. Qui chassera le plus avant qu'ils ne soient passés ?"
    stages = (("Le passage", "Le sol tremble sous les sabots ; les chasseurs de plusieurs peuples sont là.", {}),)
    actions = (
        Action("battue", "Battue au passage", "Rabattre les bêtes vers les pièges : beaucoup de viande, d'un coup.", prestige=5, score=0.3, cooldown=MONTH),
        Action("partager", "Partager la chasse", "Laisser les autres chasser aussi : ils s'en souviendront.", score=-0.1, cooldown=3 * MONTH),
    )
    months = 3
    cooldown = 3 * YEAR

    def candidates(self, state):
        if state.clock.week not in (10, 11, 12, 36, 37, 38):
            return []
        world = state.world
        for b in sorted(state.bands.values(), key=lambda b: b.id):
            if b.population <= 0 or world.terrain(b.position) not in (Terrain.STEPPE, Terrain.PLAINE):
                continue
            tids = sorted({o.tribe_id for o in state.bands.values() if o.population > 0 and not o.village and world.distance(o.position, b.position) <= 18})
            if len(tids) >= 2 and not any(_has_village(state, t) for t in tids[:1]):
                dirs = ((1, 0), (-1, 0), (0, 1), (0, -1), (1, -1), (-1, 1))
                dq, dr = dirs[int(_rand(state, self.id, "dir", b.id) * len(dirs)) % len(dirs)]
                return [(b.position, 6, tids, {"dq": dq, "dr": dr})]
        return []

    def chance(self, state):
        return 0.2

    def month(self, state, inst):
        from src.kora import diplo

        # Le passage avance.
        c = inst.center
        inst.center = Hex(c.q + 4 * inst.data.get("dq", 1), c.r + 4 * inst.data.get("dr", 0))
        inst.center = state.world.canonicalize(inst.center) or c
        present = []
        hunters = []
        for tid in sorted(inst.participants):
            bands = [b for b in zone_bands(state, inst, tid, village=False) if b.order.kind.value != "march_to_band"]
            inst.participants[tid]["score"] += sum(b.population for b in bands)
            hunters.extend(bands)
            if bands:
                present.append(tid)
        # Un troupeau ne nourrit qu'un nombre fini de chasseurs : la viande du
        # mois se partage entre les bandes qui chassent dans le couloir.
        total = sum(b.population for b in hunters)
        for b in hunters:
            b.stock += PASSAGE_MEAT * b.population / max(1, total)
        for i, a in enumerate(present):
            for b in present[i + 1:]:
                diplo.add_mod(state, a, b, "passage", -2)

    def act(self, state, inst, tid, action):
        from src.kora import diplo

        p = inst.participants[tid]
        if action == "battue":
            p["score"] = p["score"] * 1.3 + 20
        elif action == "partager":
            p["score"] *= 0.9
            for other in inst.participants:
                if other != tid:
                    diplo.add_mod(state, tid, other, "chasse_partagee", 8, actor=tid)

    def end(self, state, inst):
        win = inst.winner
        if not win:
            return
        tribe = state.tribes[win]
        tribe.prestige = min(100, tribe.prestige + 8)
        grant_effect(tribe, "sit:passage:prix", state.tick_count + 5 * YEAR)
        for t in inst.participants:
            _note(state, t, LogKind.DECOUVERTE, f"Le grand passage est fini : les {tribe.name} ont été les meilleurs chasseurs (Maîtres de la chasse, 5 ans).")


class Rassemblement(Spec):
    id = "rassemblement"
    goal = "Venir nombreux près des grands feux, offrir, raconter : le plus grand hôte l'emporte."
    name = "Le rassemblement des clans"
    kind = CONJONCTURE
    era = 0
    icon = "feu"
    about = "À la fin de l'été, les peuples voisins se retrouvent autour des grands feux : on échange, on se marie, on raconte."
    stages = (("Les grands feux", "Les bandes arrivent de partout ; chacun veut être celui qu'on écoute.", {}),)
    actions = (
        Action("presents", "Offrir des présents", "Viande séchée, peaux, colliers : celui qui donne le plus est le plus grand.", vivres=100, score=20, cooldown=MONTH),
        Action("recits", "Danses et récits", "Vos conteurs font revivre les ancêtres devant tous.", prestige=4, score=12, cooldown=MONTH),
    )
    months = 2
    cooldown = 3 * YEAR

    def candidates(self, state):
        from src.kora import diplo

        if state.clock.week not in range(30, 34):
            return []
        for tid in sorted(state.tribes):
            if not _alive(state, tid) or _has_village(state, tid):
                continue
            friends = [o for o in diplo.contacts_of(state, tid) if diplo.at_peace(state, tid, o) and _alive(state, o)]
            if len(friends) >= 2:
                bands = _bands(state, tid, village=False)
                if bands:
                    host = max(bands, key=lambda b: (b.population, -b.id))
                    near = [t for t in friends if any(state.world.distance(b.position, host.position) <= 25 for b in _bands(state, t))]
                    if len(near) >= 2:
                        return [(host.position, 10, sorted([tid] + near), {})]
        return []

    def chance(self, state):
        return 0.4

    def month(self, state, inst):
        for tid in sorted(inst.participants):
            inst.participants[tid]["score"] += sum(b.population for b in zone_bands(state, inst, tid)) / 10.0

    def end(self, state, inst):
        from src.kora import diplo

        win = inst.winner
        tids = sorted(inst.participants)
        for i, a in enumerate(tids):
            for b in tids[i + 1:]:
                diplo.add_mod(state, a, b, "rassemblement", 15 if win in (a, b) else 5)
        if not win:
            return
        tribe = state.tribes[win]
        grant_effect(tribe, "sit:rassemblement:prix", state.tick_count + 3 * YEAR)
        for t in tids:
            _note(state, t, LogKind.POLITIQUE, f"Fin du rassemblement : les {tribe.name} en ont été les hôtes (relations, mariages et savoirs qui passent mieux, 3 ans).")


# --- AGE DES VILLAGES ---------------------------------------------------------------


def _villages(state, tid=None):
    out = [s for s in state.sites.values() if s.kind == "village" and (tid is None or s.tribe_id == tid)]
    return sorted(out, key=lambda s: s.id)


def _village_band(state, site):
    from src.kora import villages

    return villages.band_of(state, site)


class Rouille(Spec):
    id = "rouille"
    goal = "Brûler, changer de semences, prier : la rouille recule peu à peu d'elle-même."
    fail = "Ratée : des sols usés, qui s'épuisent plus vite (5 ans)."
    name = "La rouille des blés"
    kind = CRISE
    era = 1
    icon = "ble"
    about = "Les épis se couvrent de taches rousses. Le mal saute de champ en champ, de village en village."
    stages = (
        ("Les épis tachés", "Un champ sur deux est touché ; la récolte sera maigre.", {"field_yield": 0.5}),
        ("Les champs perdus", "Le mal a tout pris : il faudra des semences saines.", {"field_yield": 0.35}),
    )
    actions = (
        Action("bruler", "Brûler les champs malades", "On perd la récolte de l'année, mais le mal brûle avec.", progress=35, cooldown=12 * MONTH),
        Action("semences", "Changer de semences", "Acheter des graines saines aux voisins.", vivres=150, progress=25, cooldown=6 * MONTH),
        Action("prier", "Prier les ancêtres", "Des offrandes au bord des champs.", prestige=6, progress=10, cooldown=4 * MONTH),
    )
    months = 18
    cooldown = 3 * YEAR
    natural = 3.0

    def candidates(self, state):
        if not 14 <= state.clock.week <= 26:
            return []
        out = []
        for site in _villages(state):
            tribe = state.tribes.get(site.tribe_id)
            if tribe is None or "jachere" in tribe.knowledge:
                continue
            if len(site.data.get("fields", [])) >= 4:
                out.append((site.hex, 10, [site.tribe_id], {"site": site.id}))
        return out

    def chance(self, state):
        return 0.05

    def start(self, state, inst):
        for site in _villages(state):
            if in_zone(state, inst, site.hex):
                join(state, inst, site.tribe_id)

    def month(self, state, inst):
        if inst.radius < 22:
            for site in _villages(state):
                if site.tribe_id in inst.participants:
                    continue
                if state.world.distance(site.hex, inst.center) <= inst.radius + 6 and _rand(state, inst.uid, "rouille", site.id) < 0.35:
                    join(state, inst, site.tribe_id)
                    inst.radius += 3
        months = (state.tick_count - inst.started) // MONTH
        if inst.stage == 0 and months >= 3 and inst.progress < 30:
            inst.stage = 1

    def act(self, state, inst, tid, action):
        if action == "bruler":
            for b in zone_bands(state, inst, tid, village=True):
                b.stock *= 0.8

    def end(self, state, inst):
        if inst.outcome == "ratee":
            for tid in inst.participants:
                grant_effect(state.tribes[tid], "sit:rouille:sol", state.tick_count + 5 * YEAR)
                _note(state, tid, LogKind.SURVIE, "La rouille a usé les sols : ils s'épuiseront plus vite (5 ans).")


class MalDesBetes(Spec):
    id = "mal_betes"
    goal = "Fermer les routes, abattre les bêtes malades : le mal ne vit que s'il voyage."
    fail = "Ratée : des troupeaux décimés, les villages mangent moins (3 ans)."
    name = "Le mal des bêtes"
    kind = CRISE
    era = 1
    icon = "boeuf"
    about = "Le mal est venu des enclos : les bêtes toussent, puis les gens. Il voyage avec les porteurs, de village en village."
    stages = (
        ("Les enclos malades", "Les bêtes meurent ; les enfants qui les gardent aussi.", {"stability": -10, "village_food": 0.9}),
        ("La fièvre des villages", "Les morts se comptent chaque semaine ; on accuse les étrangers.", {"stability": -15, "village_food": 0.85, "village_growth": 0.6}),
    )
    actions = (
        Action("routes", "Fermer les routes", "Plus de porteurs, plus d'étrangers : le mal ne viendra plus d'ailleurs.", progress=30, cooldown=6 * MONTH),
        Action("abattre", "Abattre les bêtes malades", "On perd des bêtes, mais le mal n'a plus où vivre.", progress=25, cooldown=12 * MONTH),
        Action("rites", "Rites de purification", "On brûle des herbes, on chante autour des enclos.", prestige=6, progress=10, cooldown=4 * MONTH),
    )
    months = 15
    cooldown = 4 * YEAR
    natural = 3.0

    def candidates(self, state):
        from src.kora import villages

        out = []
        for site in _villages(state):
            band = _village_band(state, site)
            if band is not None and band.population >= 110 and villages.has(site, "enclos"):
                out.append((site.hex, 6, [site.tribe_id], {"site": site.id}))
        return out

    def chance(self, state):
        return 0.015

    def month(self, state, inst):
        from src.kora import goods

        # Le mal voyage avec les routes commerciales.
        for tid in sorted(inst.participants):
            for r in goods.routes_of(state, tid):
                other = r.importer if r.exporter == tid else r.exporter
                if other not in inst.participants and r.units > 0 and _rand(state, inst.uid, "betes", other) < 0.4:
                    join(state, inst, other)
                    _note(state, other, LogKind.SURVIE, "Le mal des bêtes arrive avec les porteurs.")
        for tid in sorted(inst.participants):
            lost = _deaths(state, _bands(state, tid, village=True), 0.02 if inst.stage == 0 else 0.035)
            if lost:
                _note(state, tid, LogKind.SURVIE, f"Le mal des bêtes : {lost} morts dans vos villages.")
        months = (state.tick_count - inst.started) // MONTH
        if inst.stage == 0 and months >= 3 and inst.progress < 35:
            inst.stage = 1

    def act(self, state, inst, tid, action):
        from src.kora import goods

        if action == "routes":
            for r in list(goods.routes_of(state, tid)):
                goods.close_route(state, tid, r)
        elif action == "abattre":
            grant_effect(state.tribes[tid], "sit:mal_betes:abattage", state.tick_count + YEAR)

    def end(self, state, inst):
        if inst.outcome == "ratee":
            for tid in inst.participants:
                grant_effect(state.tribes[tid], "sit:mal_betes:troupeaux", state.tick_count + 3 * YEAR)
                _note(state, tid, LogKind.SURVIE, "La moitié des bêtes est morte : les villages mangeront moins (3 ans).")


class Crue(Spec):
    id = "crue"
    goal = "Relever les digues, rebâtir plus haut : l'eau finit toujours par redescendre."
    fail = "Ratée : des champs envasés, la récolte baisse (2 ans)."
    name = "La crue"
    kind = CRISE
    era = 1
    icon = "inondation"
    about = "La rivière est sortie de son lit. Les champs sont sous l'eau, les greniers mouillés."
    stages = (("Les eaux hautes", "Les champs noyés, les maisons basses détruites.", {"field_yield": 0.6, "stability": -8}),)
    actions = (
        Action("digues", "Relever les digues", "Des talus de terre et de pieux le long de l'eau.", vivres=120, progress=30, cooldown=3 * MONTH),
        Action("hauteurs", "Rebâtir sur les hauteurs", "Les maisons montent sur la colline ; on garde les champs en bas.", prestige=5, progress=20, cooldown=6 * MONTH),
    )
    months = 8
    cooldown = 4 * YEAR
    natural = 6.0

    def candidates(self, state):
        if not 4 <= state.clock.week <= 12:
            return []
        out = []
        for site in _villages(state):
            if state.world.terrain(site.hex) in (Terrain.VALLEE, Terrain.COTE):
                out.append((site.hex, 4, [site.tribe_id], {"site": site.id}))
        return out

    def chance(self, state):
        return 0.04

    def start(self, state, inst):
        for site in _villages(state):
            if in_zone(state, inst, site.hex):
                join(state, inst, site.tribe_id)
                band = _village_band(state, site)
                if band is not None:
                    band.stock *= 0.7

    def end(self, state, inst):
        if inst.outcome == "ratee":
            for tid in inst.participants:
                grant_effect(state.tribes[tid], "sit:crue:boue", state.tick_count + 2 * YEAR)


class GrandsTravaux(Spec):
    id = "travaux"
    goal = "Élever le grand monument dans ses villages (écran du village, Bâtiments), étape après étape : le peuple qui a le plus d'étapes à la fin l'emporte."
    name = "Les grands travaux"
    kind = CONJONCTURE
    era = 1
    icon = "dolmen"
    about = "Les peuples voisins élèvent chacun un grand monument à leurs ancêtres. Le plus haut dira qui est le plus grand peuple : les monuments des autres seront abattus."
    stages = (("Les pierres se dressent", "On traîne des blocs sur des rondins ; chaque village veut son tertre.", {}),)
    actions = (
        Action("corvee", "Corvée des clans", "Tous les bras du peuple au chantier : chaque monument en cours avance d'un mois.", prestige=6, cooldown=4 * MONTH),
        Action("fete", "Fête des bâtisseurs", "Un festin au pied du monument : les voisins y viennent et vous regardent autrement.", vivres=150, cooldown=6 * MONTH),
    )
    months = 6 * 12
    cooldown = 15 * YEAR

    def candidates(self, state):
        if not 17 <= state.clock.week <= 20:
            return []
        peoples = sorted({
            s.tribe_id for s in _villages(state)
            if "ancetres" in state.tribes[s.tribe_id].knowledge and not state.tribes[s.tribe_id].flags.get("monument")
        })
        for tid in peoples:
            mine = _villages(state, tid)
            others = [t for t in peoples if t != tid and any(state.world.distance(a.hex, b.hex) <= 40 for a in mine for b in _villages(state, t))]
            if others:
                return [(mine[0].hex, 40, sorted([tid] + others), {})]
        return []

    def chance(self, state):
        return 0.25

    def month(self, state, inst):
        # Le score : les etapes du monument dans les villages du lieu, et
        # l'etape en cours (au prorata de ce qui est fait).
        from src.kora import villages

        for tid in sorted(inst.participants):
            score = 0.0
            for site in _villages(state, tid):
                if not in_zone(state, inst, site.hex):
                    continue
                score += villages.monument_stages(site)
                job = villages.works(site)
                if job and job[0] == "monument":
                    total = max(1, villages.build_weeks(site, "monument"))
                    score += 1.0 - job[1] / total
            inst.participants[tid]["score"] = round(score, 3)

    def act(self, state, inst, tid, action):
        from src.kora import diplo, villages

        if action == "corvee":
            for site in _villages(state, tid):
                job = villages.works(site)
                if job and job[0] == "monument":
                    site.data["build"] = [job[0], max(1, job[1] - MONTH)]
        elif action == "fete":
            for other in sorted(inst.participants):
                if other != tid:
                    diplo.add_mod(state, tid, other, "monument", 5, actor=tid)

    def end(self, state, inst):
        from src.kora import villages

        win = inst.winner
        if not win:
            for t in inst.participants:
                _note(state, t, LogKind.DECOUVERTE, "Les grands travaux sont finis, sans vainqueur : chacun garde ce qu'il a élevé.")
            return
        tribe = state.tribes[win]
        tribe.flags["monument"] = -1
        grant_effect(tribe, "sit:travaux:prix", state.tick_count + 30 * YEAR)
        for t in sorted(inst.participants):
            if t == win:
                continue
            gone = sum(1 for site in _villages(state, t) if villages.pull_down_monument(state, site))
            if gone:
                _note(state, t, LogKind.DECOUVERTE, f"Les grands travaux sont perdus : nos monuments sont abattus ({gone}).")
        for t in inst.participants:
            _note(state, t, LogKind.DECOUVERTE, f"Les grands travaux sont finis : le grand monument est celui des {tribe.name}. Il reste debout ; leur prestige grandit plus vite (30 ans).")


class RouteDuSel(Spec):
    id = "sel"
    goal = "Faire passer le plus de marchandises par ses routes de commerce, et envoyer des porteurs."
    name = "La route du sel"
    kind = CONJONCTURE
    era = 1
    icon = "sel"
    about = "Le sel, les haches polies, les étoffes voyagent d'un peuple à l'autre : un carrefour des échanges est en train de naître."
    stages = (("Les porteurs se croisent", "Qui sera le passage obligé des routes ?", {}),)
    actions = (
        Action("porteurs", "Envoyer des porteurs", "Plus de convois, plus loin, plus souvent.", prestige=4, score=15, cooldown=3 * MONTH),
    )
    months = 4 * 12
    cooldown = 10 * YEAR

    def candidates(self, state):
        from src.kora import diplo

        if not 29 <= state.clock.week <= 32:
            return []
        traders = sorted({t for t in state.tribes if _has_village(state, t)})
        for tid in traders:
            linked = [o for o in traders if o != tid and diplo.has_pact(state, tid, o, "commerce")]
            if len(linked) >= 2:
                return [(_villages(state, tid)[0].hex, 0, sorted([tid] + linked), {})]
        return []

    def chance(self, state):
        return 0.3

    def month(self, state, inst):
        from src.kora import goods

        for tid in sorted(inst.participants):
            inst.participants[tid]["score"] += sum(r.units for r in goods.routes_of(state, tid))

    def end(self, state, inst):
        from src.kora import diplo

        win = inst.winner
        if not win:
            return
        tribe = state.tribes[win]
        tribe.prestige = min(100, tribe.prestige + 12)
        grant_effect(tribe, "sit:sel:prix", state.tick_count + 5 * YEAR)
        for t in inst.participants:
            if t != win:
                diplo.add_mod(state, win, t, "carrefour", 10)
            _note(state, t, LogKind.POLITIQUE, f"La route du sel passe par les {tribe.name} : ils sont le carrefour des échanges (5 ans).")


class Chefferies(Spec):
    id = "chefferies"
    goal = "Avoir le plus de villages, de prestige et de victoires ; montrer sa force ou marier les fils des chefs."
    name = "L'essor des chefferies"
    kind = CONJONCTURE
    era = 1
    icon = "couronne"
    about = "Les villages se multiplient dans la vallée ; les terres manquent. Un peuple va s'imposer aux autres."
    stages = (("La vallée disputée", "Chaque chef veut être celui qu'on écoute, et à qui l'on paie.", {}),)
    actions = (
        Action("force", "Montrer sa force", "Des guerriers en armes aux limites des autres villages.", prestige=8, score=20, cooldown=6 * MONTH),
        Action("mariage", "Marier les fils des chefs", "Une alliance de familles : on vous respecte, sans la guerre.", prestige=5, score=10, cooldown=6 * MONTH),
    )
    months = 5 * 12
    cooldown = 12 * YEAR

    def candidates(self, state):
        if not 25 <= state.clock.week <= 28:
            return []
        peoples = sorted({s.tribe_id for s in _villages(state)})
        for tid in peoples:
            mine = _villages(state, tid)
            # Trois peuples a villages ou plus dans la meme vallee (30 cases).
            rivals = [t for t in peoples if t != tid and any(state.world.distance(a.hex, b.hex) <= 30 for a in mine for b in _villages(state, t))]
            if len(rivals) >= 2:
                return [(mine[0].hex, 30, sorted([tid] + rivals), {})]
        return []

    def chance(self, state):
        return 0.25

    def month(self, state, inst):
        for tid in sorted(inst.participants):
            p = inst.participants[tid]
            n = sum(1 for s in _villages(state, tid) if in_zone(state, inst, s.hex))
            wins = sum(1 for m in state.fights if m.winner_tribe == tid and m.tick >= state.tick_count - MONTH and in_zone(state, inst, m.hex))
            p["score"] += 2 * n + state.tribes[tid].prestige / 10.0 + 10 * wins

    def act(self, state, inst, tid, action):
        from src.kora import diplo

        others = [t for t in inst.participants if t != tid]
        if action == "force":
            for t in others:
                diplo.add_mod(state, tid, t, "intimidation", -5, actor=tid)
        elif action == "mariage" and others:
            rival = max(others, key=lambda t: (inst.participants[t]["score"], -t))
            diplo.add_mod(state, tid, rival, "mariage", 10)

    def end(self, state, inst):
        from src.kora import diplo

        win = inst.winner
        if not win:
            return
        tribe = state.tribes[win]
        tribe.prestige = min(100, tribe.prestige + 15)
        grant_effect(tribe, "sit:chefferies:prix", state.tick_count + 10 * YEAR)
        for t in inst.participants:
            if t != win:
                diplo.add_mod(state, win, t, "domination", 10)
            _note(state, t, LogKind.POLITIQUE, f"La vallée a trouvé son maître : les {tribe.name} sont la chefferie dominante (10 ans).")


class Surproduction(Spec):
    id = "surproduction"
    name = "La surproduction"
    kind = CRISE
    era = 1
    icon = "balance"
    about = "Les artisans font bien plus qu'on n'en use et qu'on n'en vend : les réserves débordent, plus personne n'en veut, les gens de métier ne savent plus de quoi vivre."
    goal = "Faire redescendre la réserve et la production du bien : moins d'artisans, des ventes, des offrandes. Quand la réserve passe sous les deux tiers, la jauge monte vite."
    fail = "Ratée : le métier perd son savoir-faire (-15 %) et l'effondrement du commerce gagne vos partenaires."
    stages = (
        ("Les réserves débordent", "Les jarres s'entassent, les porteurs n'en veulent plus ; on brade.", {"stability": -4}),
        ("Les artisans sans ouvrage", "Des familles entières n'ont plus rien à échanger ; elles grondent contre le chef.", {"stability": -8, "loyalty": -2}),
    )
    actions = (
        Action("renvoyer", "Renvoyer des artisans aux champs", "Une équipe de moins à ce métier dans chaque village.", progress=25, cooldown=4 * MONTH),
        Action("brader", "Brader aux voisins", "La moitié de la réserve part chez vos partenaires, presque pour rien : ils s'en souviendront.", progress=15, cooldown=3 * MONTH),
        Action("offrandes", "Offrir aux ancêtres", "On brûle et on enterre le surplus : la réserve fond, les anciens sont contents.", progress=10, cooldown=3 * MONTH),
    )
    months = 12
    cooldown = 4 * YEAR
    natural = 0.0

    def candidates(self, state):
        from src.kora import goods, production

        out = []
        for tid in sorted(state.tribes):
            tribe = state.tribes[tid]
            mine = _villages(state, tid)
            if not mine or not tribe.glut:
                continue
            for good in goods.GOODS:
                if tribe.glut.get(good, 0) >= production.GLUT_CRISIS:
                    out.append((mine[0].hex, 0, [tid], {"good": good}))
                    break
        return out

    def chance(self, state):
        return 0.35

    def risk(self, state, tid):
        from src.kora import goods, production

        tribe = state.tribes.get(tid)
        if tribe is None or not tribe.glut:
            return ""
        for good in goods.GOODS:
            if tribe.glut.get(good, 0) >= production.GLUT_RISK:
                return (f"{goods.GOOD_NAMES[good]} : la réserve déborde et l'on en fait bien plus qu'on n'en use ou vend. "
                        "Moins d'artisans, ou plus de routes de vente, avant que les prix ne s'effondrent.")
        return ""

    def _good(self, inst) -> str:
        return inst.data.get("good", "")

    def stage_name(self, inst):
        from src.kora import goods

        base = super().stage_name(inst)
        good = goods.GOOD_NAMES.get(self._good(inst), "")
        return f"{base} ({good.lower()})" if good else base

    def month(self, state, inst):
        from src.kora import goods, production

        tid = next(iter(inst.participants))
        good = self._good(inst)
        have = goods.stock(state, tid, good)
        made = goods.made(state, tid, good)
        use, _unmet = production.demand(state, tid, good)
        if have < goods.CAP * 0.66:
            inst.progress += 20
        elif made <= 1.2 * max(use, 0.05):
            inst.progress += 10
        months = (state.tick_count - inst.started) // MONTH
        if inst.stage == 0 and months >= 3 and inst.progress < 30:
            inst.stage = 1
            _note(state, tid, LogKind.POLITIQUE, "La surproduction s'aggrave : les artisans sont sans ouvrage.")

    def act(self, state, inst, tid, action):
        from src.kora import diplo, goods
        good = self._good(inst)
        cid = goods.GOOD_CRAFT.get(good)
        tribe = state.tribes[tid]
        if action == "renvoyer" and cid:
            for site in _villages(state, tid):
                n = goods.teams_of(site, cid)
                if n > 0:
                    goods.set_teams(state, site, cid, n - 1)
        elif action == "brader":
            have = tribe.goods.get(good, 0.0)
            give = have / 2.0
            friends = goods.partners(state, tid)
            if give > 0:
                tribe.goods[good] = have - give
                for other in friends:
                    o = state.tribes[other]
                    o.goods[good] = min(goods.CAP, o.goods.get(good, 0.0) + give / len(friends))
                    diplo.add_mod(state, tid, other, "brade", 3, actor=tid)
        elif action == "offrandes":
            have = tribe.goods.get(good, 0.0)
            if have > 0:
                tribe.goods[good] = have * 0.4
            gain_prestige(state, tribe, 1)

    def end(self, state, inst):
        from src.kora import goods, production

        tid = next(iter(inst.participants), None)
        if tid is None:
            return
        tribe = state.tribes[tid]
        good = self._good(inst)
        tribe.glut.pop(good, None)
        if inst.outcome != "ratee":
            return
        cid = goods.GOOD_CRAFT.get(good)
        if cid:
            production.adjust(tribe, production.craft_kind(cid), -0.15)
        _note(state, tid, LogKind.POLITIQUE, f"La surproduction n'a pas été enrayée : le métier perd son savoir-faire ({goods.GOOD_NAMES.get(good, good).lower()}).")
        friends = [t for t in goods.partners(state, tid) if not _busy(state, "effondrement", [t])]
        if friends and not _busy(state, "effondrement", [tid]):
            depth = {str(tid): 0}
            depth.update({str(t): 1 for t in friends})
            _start(state, SPECS["effondrement"], inst.center, 0, [tid] + friends, {"good": good, "origin": tid, "depth": depth})


EFFONDREMENT_DEPTH = 2


class Effondrement(Spec):
    id = "effondrement"
    name = "L'effondrement du commerce"
    kind = CONJONCTURE
    era = 1
    icon = "commerce"
    about = "Un peuple a trop produit : plus personne n'achète, les prix s'effondrent sur les routes et le mal gagne, de partenaire en partenaire. Qui saura le mieux tenir ?"
    goal = "Tenir : chaque mois, chaque bien encore pourvu et chaque route qui porte comptent. Le peuple qui a le mieux tenu devient le marché refuge. En attendant, les routes portent à bas prix et les artisans perdent la main."
    stages = (("Les marchés s'effondrent", "Les porteurs reviennent chargés ; les artisans perdent la main.", {}),)
    actions = (
        Action("soutenir", "Soutenir les partenaires", "Des vivres aux villages de vos partenaires qui ne vendent plus : ils ne l'oublieront pas.", vivres=150, score=15, cooldown=3 * MONTH),
        Action("fermer", "Fermer ses marchés", "Toutes vos routes fermées : le mal ne vous touche plus, mais vous ne pouvez plus l'emporter.", score=-1.0, cooldown=12 * MONTH),
    )
    months = 12
    cooldown = 6 * YEAR

    def candidates(self, state):
        # Seulement d'une surproduction ratee (Surproduction.end).
        return []

    def month(self, state, inst):
        from src.kora import goods, production

        depth = inst.data.setdefault("depth", {})
        # Le mal gagne les partenaires des partenaires, jusqu'a EFFONDREMENT_DEPTH.
        for tid in sorted(inst.participants):
            d = int(depth.get(str(tid), 0))
            if d >= EFFONDREMENT_DEPTH:
                continue
            for other in goods.partners(state, tid):
                if other in inst.participants or str(other) in depth:
                    continue
                if _rand(state, inst.uid, "cascade", tid, other) < 0.4:
                    depth[str(other)] = d + 1
                    join(state, inst, other)
        for tid in sorted(inst.participants):
            tribe = state.tribes.get(tid)
            if tribe is None:
                continue
            for kind in production.active_kinds(state, tid):
                if kind not in ("collecte", "agriculture", "peche"):
                    production.adjust(tribe, kind, -0.006)
            supplied = sum(1 for g in goods.GOODS if goods.supplied(state, tid, g))
            running = sum(1 for r in goods.routes_of(state, tid) if r.units > 0)
            inst.participants[tid]["score"] += 2 * supplied + 3 * running

    def act(self, state, inst, tid, action):
        from src.kora import diplo, goods

        if action == "soutenir":
            for other in sorted(inst.participants):
                if other != tid:
                    diplo.add_mod(state, tid, other, "soutien", 5, actor=tid)
        elif action == "fermer":
            for r in list(goods.routes_of(state, tid)):
                goods.close_route(state, tid, r)
            inst.participants.pop(tid, None)
            _note(state, tid, LogKind.POLITIQUE, "Vos marchés sont fermés : l'effondrement du commerce ne vous touche plus.")

    def end(self, state, inst):
        win = inst.winner
        if win:
            tribe = state.tribes[win]
            grant_effect(tribe, "sit:effondrement:prix", state.tick_count + 5 * YEAR)
        for t in inst.participants:
            text = "Les marchés reprennent." + (f" Les {state.tribes[win].name} sont devenus le marché refuge (prix de vente +15 %, 5 ans)." if win else "")
            _note(state, t, LogKind.POLITIQUE, text)


class Revolte(Spec):
    id = "revolte"
    name = "La révolte des cultivateurs"
    kind = CRISE
    era = 1
    icon = "faucille"
    about = "Le chef prend trop : les cultivateurs cachent le grain, les familles murmurent, on parle de partir."
    goal = "Rendre au peuple ce qu'on lui prend : baisser le prélèvement, distribuer le grenier du chef, ou mater la révolte par la force. La jauge monte quand le prélèvement est léger et les villages calmes."
    fail = "Ratée : le chef est renversé (un nouveau chef, le prélèvement aboli, prestige -15)."
    stages = (
        ("Le grain caché", "On cache des jarres sous les maisons ; la part du chef arrive moins pleine.", {"stability": -8, "field_yield": 0.9}),
        ("La révolte ouverte", "Des villages refusent de payer ; les familles se rangent d'un côté ou de l'autre.", {"stability": -15, "field_yield": 0.8}),
    )
    actions = (
        Action("baisser", "Baisser le prélèvement", "Le chef ne prend plus que 10 % au plus : la colère retombe.", progress=40, cooldown=6 * MONTH),
        Action("distribuer", "Distribuer le grenier", "La moitié du grenier du chef revient aux villages.", progress=35, cooldown=6 * MONTH),
        Action("mater", "Mater la révolte", "Les guerriers du chef font des exemples : la peur tient le peuple, pour un temps.", prestige=10, progress=30, cooldown=6 * MONTH),
    )
    months = 10
    cooldown = 5 * YEAR

    def _calm(self, state, tid) -> float:
        from src.kora import villages

        sites = _villages(state, tid)
        vals = [villages.stability(state, s) for s in sites if _village_band(state, s) is not None]
        return sum(vals) / len(vals) if vals else 50.0

    def candidates(self, state):
        out = []
        for tid in sorted(state.tribes):
            tribe = state.tribes[tid]
            mine = _villages(state, tid)
            if not mine or getattr(tribe, "levy_rate", 0) < 20:
                continue
            angry = any(f.get("favour", 50) < 25 for f in tribe.families or [])
            if self._calm(state, tid) < 45 or angry:
                out.append((mine[0].hex, 0, [tid], {}))
        return out

    def chance(self, state):
        return 0.25

    def risk(self, state, tid):
        tribe = state.tribes.get(tid)
        if tribe is None or getattr(tribe, "levy_rate", 0) < 20 or not _villages(state, tid):
            return ""
        if self._calm(state, tid) < 55 or any(f.get("favour", 50) < 30 for f in tribe.families or []):
            return "Le prélèvement du chef pèse et les villages grondent. Baissez-le, donnez une fête, ou contentez les familles."
        return ""

    def month(self, state, inst):
        tid = next(iter(inst.participants))
        tribe = state.tribes[tid]
        if tribe.levy_rate <= 10:
            inst.progress += 25
        if self._calm(state, tid) >= 50:
            inst.progress += 10
        months = (state.tick_count - inst.started) // MONTH
        if inst.stage == 0 and months >= 3 and inst.progress < 30:
            inst.stage = 1
            _note(state, tid, LogKind.POLITIQUE, "La révolte éclate : des villages refusent de payer le chef.")

    def act(self, state, inst, tid, action):
        tribe = state.tribes[tid]
        if action == "baisser":
            tribe.levy_rate = min(tribe.levy_rate, 10)
        elif action == "distribuer":
            bands = [_village_band(state, s) for s in _villages(state, tid)]
            bands = [b for b in bands if b is not None]
            give = tribe.granary / 2.0
            pop = sum(b.population for b in bands) or 1
            for b in bands:
                b.stock += give * b.population / pop
            tribe.granary -= give
        elif action == "mater":
            for s in _villages(state, tid):
                b = _village_band(state, s)
                if b is not None:
                    population.kill(b, max(1, round(b.population * 0.02)))
            for fam in tribe.families or []:
                fam["favour"] = max(0.0, fam["favour"] - 10.0)

    def end(self, state, inst):
        if inst.outcome != "ratee":
            return
        from src.kora import chiefdom

        tid = next(iter(inst.participants), None)
        if tid is None:
            return
        # Un peuple n'a qu'un village en cet age : le chef est renverse
        # (une vieille partie a plusieurs villages : le plus grand s'en va).
        if not chiefdom.village_secedes(state, tid):
            chiefdom.overthrow(state, tid)


class RevolteTributaires(Spec):
    id = "tributaires"
    name = "Les tributaires grondent"
    kind = CRISE
    era = 1
    icon = "balance"
    about = "Un peuple qui vous paie le tribut se sent assez fort, ou assez maltraité, pour rejeter votre joug."
    goal = "Le tenir : montrer vos guerriers près de ses villages, lui faire des présents, ou le menacer. Un tributaire tenu ne gronde plus."
    fail = "Ratée : il se révolte et ne paie plus ; il faudra le soumettre à nouveau."
    stages = (("Le tribut arrive en retard", "Les porteurs viennent les mains moins pleines ; les anciens du tributaire parlent haut.", {"diplo": -5}),)
    actions = (
        Action("presents", "Faire des présents", "Des vivres au chef tributaire : il se souvient de ce que vous valez.", vivres=150, progress=30, cooldown=4 * MONTH),
        Action("menacer", "Menacer", "Vos envoyés rappellent ce qu'il en coûte de vous trahir.", prestige=6, progress=25, cooldown=4 * MONTH),
    )
    months = 8
    cooldown = 3 * YEAR
    natural = 5.0

    def candidates(self, state):
        from src.kora import chiefdom

        out = []
        for lord in sorted(state.tribes):
            for vassal in chiefdom.vassals_of(state, lord):
                if vassal in state.tribes and not state.tribes[vassal].is_player and chiefdom.unrest(state, vassal, lord) >= chiefdom.REVOLT_UNREST:
                    mine = _villages(state, vassal)
                    out.append((mine[0].hex if mine else None, 0, [lord], {"vassal": vassal}))
        return out

    def chance(self, state):
        return 0.3

    def risk(self, state, tid):
        from src.kora import chiefdom

        for vassal in chiefdom.vassals_of(state, tid):
            if vassal in state.tribes and not state.tribes[vassal].is_player and chiefdom.unrest(state, vassal, tid) >= 25:
                return f"Les {state.tribes[vassal].name}, vos tributaires, se sentent assez forts pour se révolter. Approchez une troupe de leurs villages, ou faites-leur des présents."
        return ""

    def stage_name(self, inst):
        return super().stage_name(inst)

    def month(self, state, inst):
        from src.kora import chiefdom

        lord = next(iter(inst.participants))
        vassal = inst.data.get("vassal", 0)
        if vassal not in state.tribes or chiefdom.overlord_of(state, vassal) != lord:
            inst.progress = 100.0
            return
        if chiefdom.unrest(state, vassal, lord) < chiefdom.REVOLT_UNREST:
            inst.progress += 15

    def act(self, state, inst, tid, action):
        from src.kora import diplo

        vassal = inst.data.get("vassal", 0)
        if vassal not in state.tribes:
            return
        if action == "presents":
            diplo.add_mod(state, tid, vassal, "cadeau", 10, actor=tid)
        elif action == "menacer":
            diplo.add_mod(state, tid, vassal, "intimidation", -3, actor=tid)

    def end(self, state, inst):
        if inst.outcome != "ratee":
            return
        from src.kora import chiefdom

        lord = next(iter(inst.participants), None)
        vassal = inst.data.get("vassal", 0)
        if lord is not None and vassal in state.tribes and chiefdom.overlord_of(state, vassal) == lord:
            chiefdom._revolt(state, vassal, lord)


def price_mult(state, tid: int, good: str) -> float:
    """Les prix que font les situations : un bien en surproduction ne vaut
    presque plus rien chez son peuple."""
    for inst in getattr(state, "situations", ()):
        if not inst.outcome and inst.sid == "surproduction" and tid in inst.participants and inst.data.get("good") == good:
            return 0.6
    return 1.0


def route_mult(state, route) -> float:
    """Les routes d'un peuple pris dans l'effondrement du commerce portent a
    bas prix."""
    for inst in getattr(state, "situations", ()):
        if not inst.outcome and inst.sid == "effondrement" and (route.exporter in inst.participants or route.importer in inst.participants):
            return 0.6
    return 1.0


# --- les risques : une crise que l'on voit venir -------------------------------------------


def _risk_disette(self, state, tid):
    bands = _bands(state, tid, village=False)
    pop = sum(b.population for b in bands)
    if pop < 30:
        return ""
    hungry = sum(b.population for b in bands if state.tick_count - b.famine_tick <= 2 * MONTH)
    lean = _season(state) in (Season.AUTOMNE, Season.HIVER) and _mean_weeks(bands) < 2.0
    if hungry * 4 >= pop or lean:
        return "Les réserves sont trop maigres pour la saison. Chassez, faites des caches, descendez vers les vallées."
    return ""


def _risk_mal(self, state, tid):
    for b in _bands(state, tid):
        if b.population < 75:
            continue
        if any(o.id != b.id and o.population > 0 and state.world.distance(o.position, b.position) <= 3 for o in state.bands.values()):
            return "Des bandes nombreuses vivent serrées : une fièvre pourrait courir, surtout l'été. Scindez les grosses bandes, écartez-les."
    return ""


def _risk_gibier(self, state, tid):
    if _has_village(state, tid):
        return ""
    heart = chiefs.chief_band(state, tid)
    if heart is None or heart.village:
        return ""
    hexes = state.world.hexes_in_radius(heart.position, 5)
    mean = sum(state.world.exhaustion(h) for h in hexes) / max(1, len(hexes))
    if mean < 0.86:
        return "Le pays du chef s'épuise (gibier, baies). Partez chasser ailleurs avant qu'il ne soit vide."
    return ""


def _risk_rouille(self, state, tid):
    if not 10 <= state.clock.week <= 26 or "jachere" in state.tribes[tid].knowledge:
        return ""
    if any(len(s.data.get("fields", [])) >= 3 for s in _villages(state, tid)):
        return "Beaucoup de champs sans jachère : la rouille des blés guette (le savoir Jachère l'éloigne)."
    return ""


def _risk_mal_betes(self, state, tid):
    from src.kora import villages

    for site in _villages(state, tid):
        band = _village_band(state, site)
        if band is not None and band.population >= 100 and villages.has(site, "enclos"):
            return "Un gros village vit serré avec ses bêtes : le mal des bêtes peut naître et voyager par vos routes."
    return ""


def _risk_crue(self, state, tid):
    if not 1 <= state.clock.week <= 12:
        return ""
    if any(state.world.terrain(s.hex) in (Terrain.VALLEE, Terrain.COTE) for s in _villages(state, tid)):
        return "Au printemps, l'eau peut sortir de son lit près de vos villages : gardez des vivres pour relever les digues."
    return ""


Disette.risk = _risk_disette
MalQuiCourt.risk = _risk_mal
GibierEpuise.risk = _risk_gibier
Rouille.risk = _risk_rouille
MalDesBetes.risk = _risk_mal_betes
Crue.risk = _risk_crue


SPECS: dict[str, Spec] = {s.id: s for s in (Disette(), MalQuiCourt(), GibierEpuise(), GrandHiver(), GrandPassage(), Rassemblement(), Rouille(), MalDesBetes(), Crue(), GrandsTravaux(), RouteDuSel(), Chefferies(), Surproduction(), Effondrement(), Revolte(), RevolteTributaires())}

# Les effets qui ne sont pas des etapes : actions et prix (tech.SITUATION_EFFECTS).
EXTRA_EFFECTS = {
    "sit:grand_hiver:abri": ("Réfugiés dans les vallées", {"winter_famine": 0.75}),
    "sit:grand_hiver:fume": ("Viande fumée", {"stock_weeks": 4}),
    "sit:gibier:maigre": ("Un pays maigre", {"food": _food(0.92)}),
    "sit:passage:prix": ("Maîtres de la chasse", {"food": _food(1.10, (Terrain.PLAINE, Terrain.STEPPE))}),
    "sit:rassemblement:prix": ("Hôtes du rassemblement", {"diplo": 10, "diffusion": 0.2}),
    "sit:rouille:sol": ("Sols usés par la rouille", {"soil_loss": 1.3}),
    "sit:mal_betes:abattage": ("Bêtes abattues", {"village_food": 0.85}),
    "sit:mal_betes:troupeaux": ("Troupeaux décimés", {"village_food": 0.8}),
    "sit:crue:boue": ("Champs envasés", {"field_yield": 0.85}),
    "sit:travaux:prix": ("Le grand monument", {"prestige_gain": 1.3, "stability": 5}),
    "sit:effondrement:prix": ("Marché refuge", {"trade_price": 1.15, "diplo": 5}),
    "sit:sel:prix": ("Carrefour des échanges", {"diplo": 8, "gifts": 1.3}),
    "sit:chefferies:prix": ("Chefferie dominante", {"diplo": 15, "loyalty": 5}),
}


def effect_ids(tribe) -> list:
    """Les effets en cours, lus par tech.bonuses (systems.EFFECT_FIELDS)."""
    return [e[0] for e in (getattr(tribe, "situation_effects", None) or [])]


def effect_specs() -> dict:
    """id -> (nom, effets) : les etapes de chaque situation, et les autres."""
    out = dict(EXTRA_EFFECTS)
    for spec in SPECS.values():
        for i, (name, _text, eff) in enumerate(spec.stages):
            if eff:
                out[spec.effect_id(i)] = (f"{spec.name} : {name.lower()}", eff)
    return out


# --- le cycle -----------------------------------------------------------------------------


def active(state) -> list:
    return [s for s in getattr(state, "situations", []) if not s.outcome]


def of_tribe(state, tid: int, ended: bool = False) -> list:
    out = [s for s in getattr(state, "situations", []) if tid in s.participants and (ended or not s.outcome)]
    return sorted(out, key=lambda s: (bool(s.outcome), s.started, s.uid))


def find(state, uid: int):
    return next((s for s in getattr(state, "situations", []) if s.uid == uid), None)


def grant_effect(tribe, effect_id: str, until: int) -> None:
    """Un effet de situation (une action, un prix) jusqu'a la semaine until."""
    effects = [e for e in tribe.situation_effects if e[0] != effect_id]
    effects.append([effect_id, int(until)])
    tribe.situation_effects = effects
    tech.invalidate()


def join(state, inst, tid: int) -> None:
    if tid in inst.participants or tid not in state.tribes:
        return
    inst.participants[tid] = {"score": 0.0, "joined": state.tick_count, "acted": {}, "pop0": sum(b.population for b in _bands(state, tid))}
    spec = SPECS[inst.sid]
    if inst.outcome == "":
        what = "Une crise commence" if spec.kind == CRISE else "Une conjoncture commence"
        _note(state, tid, LogKind.DECOUVERTE, f"{what} : {spec.name}. {spec.about}", inst.center)


def _busy(state, sid: str, tids) -> bool:
    """Ce peuple vit deja cette situation, ou l'a vecue il y a peu."""
    spec = SPECS[sid]
    for s in getattr(state, "situations", []):
        if s.sid != sid:
            continue
        if not s.outcome and (tids is None or any(t in s.participants for t in tids)):
            return True
    last = getattr(state, "situation_last", {})
    for t in (tids or [0]):
        if state.tick_count - last.get(f"{sid}:{t}", -10 ** 6) < spec.cooldown:
            return True
    return False


def _start(state, spec, center, radius, tids, data) -> Situation:
    uid = state.next_situation_uid
    state.next_situation_uid += 1
    inst = Situation(uid, spec.id, state.tick_count, state.tick_count + spec.months * MONTH, center, radius, data=dict(data))
    state.situations.append(inst)
    for t in tids or []:
        join(state, inst, t)
    starter = getattr(spec, "start", None)
    if starter is not None:
        starter(state, inst)
    return inst


def monthly(state) -> None:
    """Chaque mois : de nouvelles situations naissent de leur contexte, celles
    en cours avancent (jauge, score, etapes, effets), certaines finissent ;
    l'IA agit dans les siennes."""
    if not getattr(state, "story", False):
        return
    for sid in sorted(SPECS):
        spec = SPECS[sid]
        for center, radius, tids, data in spec.candidates(state):
            if _busy(state, sid, tids):
                continue
            if _rand(state, sid, "debut") < spec.chance(state):
                _start(state, spec, center, radius, tids, data)
                break
    for inst in sorted(active(state), key=lambda s: s.uid):
        spec = SPECS[inst.sid]
        for tid in [t for t in inst.participants if not _alive(state, t)]:
            del inst.participants[tid]
        if not inst.participants:
            _finish(state, inst, "finie")
            continue
        spec.month(state, inst)
        if spec.kind == CRISE:
            inst.progress += spec.natural
        inst.progress = max(0.0, min(100.0, inst.progress))
        _ai(state, inst)
        if not inst.participants:
            _finish(state, inst, "finie")
        elif spec.kind == CRISE and inst.progress >= 100.0:
            _finish(state, inst, "resolue")
        elif state.tick_count >= inst.until:
            _finish(state, inst, "ratee" if spec.kind == CRISE else "finie")
    _sync_effects(state)
    _prune(state)
    _risks(state)


def _risks(state) -> None:
    """Les crises qui menacent chaque joueur (Spec.risk) : au bandeau
    (state.situation_risks), et une fois au journal (pas plus d'une fois
    tous les deux ans pour la meme). Les conjonctures ne previennent pas."""
    out = {}
    last = state.situation_last
    for tid in humans(state):
        if tid not in state.tribes or not _alive(state, tid):
            continue
        living = {s.sid for s in of_tribe(state, tid)}
        found = []
        for sid in sorted(SPECS):
            spec = SPECS[sid]
            if spec.kind != CRISE or sid in living:
                continue
            text = spec.risk(state, tid)
            if not text:
                continue
            found.append([sid, text])
            key = f"risque:{sid}:{tid}"
            if state.tick_count - last.get(key, -10 ** 6) >= 2 * YEAR:
                last[key] = state.tick_count
                _note(state, tid, LogKind.SURVIE, f"Risque : {spec.name.lower()}. {text}")
        if found:
            out[tid] = found
    state.situation_risks = out


def risks_of(state, tid: int) -> list:
    """[[sid, texte]] : les crises qui menacent ce peuple (calcule chaque mois)."""
    return list(getattr(state, "situation_risks", {}).get(tid, []))


def _finish(state, inst, outcome: str) -> None:
    spec = SPECS[inst.sid]
    inst.outcome = outcome
    inst.ended = state.tick_count
    if spec.kind == CONJONCTURE:
        ranked = sorted(inst.participants.items(), key=lambda kv: (-kv[1]["score"], kv[0]))
        scored = [t for t, p in ranked if p["score"] > 0]
        if len(inst.participants) >= 2 and scored:
            inst.winner = scored[0]
            inst.outcome = "gagnee"
    last = state.situation_last
    for t in inst.participants:
        last[f"{inst.sid}:{t}"] = state.tick_count
    last[f"{inst.sid}:0"] = state.tick_count
    spec.end(state, inst)
    if spec.kind == CRISE:
        text = {"resolue": f"La crise est surmontée : {spec.name.lower()} est derrière vous. Tout redevient comme avant.", "ratee": f"{spec.name} : la crise n'a pas été surmontée à temps."}.get(outcome, f"{spec.name} : c'est fini.")
        for t in inst.participants:
            _note(state, t, LogKind.DECOUVERTE, text, inst.center)


def _sync_effects(state) -> None:
    """Les effets des etapes en cours sur leurs peuples ; les effets dates
    (actions, prix) jusqu'a leur echeance."""
    stage_of: dict[int, set] = {}
    for inst in active(state):
        spec = SPECS[inst.sid]
        if not spec.stages:
            continue
        eff = spec.stages[min(inst.stage, len(spec.stages) - 1)][2]
        if not eff:
            continue
        for tid in inst.participants:
            # Une situation a lieu : seuls les peuples qui y sont la vivent.
            if inst.radius > 0 and not any(in_zone(state, inst, b.position) for b in _bands(state, tid)):
                continue
            stage_of.setdefault(tid, set()).add(spec.effect_id(min(inst.stage, len(spec.stages) - 1)))
    changed = False
    for tid in sorted(state.tribes):
        tribe = state.tribes[tid]
        old = [list(e) for e in tribe.situation_effects]
        dated = [e for e in old if e[1] >= 0 and e[1] > state.tick_count]
        live = [[e, -1] for e in sorted(stage_of.get(tid, ()))]
        new = dated + live
        if new != old:
            tribe.situation_effects = new
            changed = True
    if changed:
        tech.invalidate()


def _prune(state) -> None:
    state.situations = [s for s in state.situations if not s.outcome or state.tick_count - s.ended < KEEP_ENDED]


# --- les actions ------------------------------------------------------------------------------


def action_block(state, inst, tid: int, action_id: str) -> str:
    """Pourquoi ce peuple ne peut pas faire cette action ("" : il peut)."""
    if inst is None or inst.outcome:
        return "Cette situation est finie"
    if tid not in inst.participants:
        return "Votre peuple n'y est pas"
    spec = SPECS[inst.sid]
    action = next((a for a in spec.actions if a.id == action_id), None)
    if action is None:
        return "?"
    last = inst.participants[tid]["acted"].get(action_id, -10 ** 6)
    wait = action.cooldown - (state.tick_count - last)
    if wait > 0:
        return f"Encore {wait} semaine{'s' if wait > 1 else ''} avant de recommencer"
    tribe = state.tribes[tid]
    if action.prestige and tribe.prestige < action.prestige:
        return f"Il faut {action.prestige} de prestige"
    if action.vivres:
        have = sum(max(0.0, b.stock - b.population) for b in _bands(state, tid))
        if have < action.vivres:
            return f"Il faut {action.vivres} vivres en réserve"
    return ""


def act(state, uid: int, tid: int, action_id: str) -> str:
    """Faire une action ; rend le texte du resultat (ou pourquoi pas)."""
    inst = find(state, uid)
    why = action_block(state, inst, tid, action_id)
    if why:
        return why
    spec = SPECS[inst.sid]
    action = next(a for a in spec.actions if a.id == action_id)
    tribe = state.tribes[tid]
    tribe.prestige -= action.prestige
    if action.vivres:
        _pay_vivres(state, tid, action.vivres)
    inst.participants[tid]["acted"][action_id] = state.tick_count
    inst.progress = max(0.0, min(100.0, inst.progress + action.progress))
    p = inst.participants[tid]
    if action.score:
        p["score"] = max(0.0, p["score"] + (action.score if action.score >= 1 else p["score"] * action.score))
    hook = getattr(spec, "act", None)
    if hook is not None:
        hook(state, inst, tid, action_id)
    if spec.kind == CRISE and inst.progress >= 100.0:
        _finish(state, inst, "resolue")
        _sync_effects(state)
    return f"{action.label} : fait."


def _ai(state, inst) -> None:
    """L'IA prend ses actions : la premiere qu'elle peut, souvent."""
    spec = SPECS[inst.sid]
    for tid in sorted(inst.participants):
        tribe = state.tribes.get(tid)
        if tribe is None or tribe.is_player:
            continue
        if _rand(state, inst.uid, "ia", tid) >= 0.35:
            continue
        for action in spec.actions:
            if action.score < 0:
                continue
            if not action_block(state, inst, tid, action.id):
                act(state, inst.uid, tid, action.id)
                break


# --- pour l'ecran -------------------------------------------------------------------------------


def ranking(inst) -> list:
    return sorted(inst.participants.items(), key=lambda kv: (-kv[1]["score"], kv[0]))


def months_left(state, inst) -> int:
    return max(0, -(-(inst.until - state.tick_count) // MONTH))


def effect_lines(inst) -> list:
    spec = SPECS[inst.sid]
    if not spec.stages:
        return []
    eff = spec.stages[min(inst.stage, len(spec.stages) - 1)][2]

    class _Shim:
        id = spec.effect_id(inst.stage)
        effects = eff

    return tech.effect_lines(_Shim) if eff else []


# --- sauvegarde ---------------------------------------------------------------------------------


def to_json(inst) -> dict:
    return {
        "uid": inst.uid,
        "sid": inst.sid,
        "started": inst.started,
        "until": inst.until,
        "center": None if inst.center is None else [inst.center.q, inst.center.r],
        "radius": inst.radius,
        "stage": inst.stage,
        "progress": inst.progress,
        "participants": [[tid, p] for tid, p in sorted(inst.participants.items())],
        "data": inst.data,
        "outcome": inst.outcome,
        "ended": inst.ended,
        "winner": inst.winner,
    }


def from_json(d: dict):
    if d.get("sid") not in SPECS:
        return None
    parts = {}
    for tid, p in d.get("participants", []):
        parts[int(tid)] = {
            "score": float(p.get("score", 0.0)),
            "joined": int(p.get("joined", 0)),
            "acted": {str(k): int(v) for k, v in p.get("acted", {}).items()},
            "pop0": int(p.get("pop0", 0)),
        }
    c = d.get("center")
    return Situation(
        int(d["uid"]), str(d["sid"]), int(d["started"]), int(d["until"]),
        None if c is None else Hex(int(c[0]), int(c[1])), int(d.get("radius", 0)), int(d.get("stage", 0)),
        float(d.get("progress", 0.0)), parts, dict(d.get("data", {})), str(d.get("outcome", "")), int(d.get("ended", -1)), int(d.get("winner", 0)),
    )


def copy_all(situations) -> list:
    import copy

    return copy.deepcopy(situations)
