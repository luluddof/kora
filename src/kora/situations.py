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

from src.kora import tech
from src.kora.log import LogKind
from src.kora.types import Hex, Season, Terrain

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
        from src.kora.world import axial_to_offset

        _col, row = axial_to_offset(state.world.canonicalize(h) or h)
        north = row < state.world.height // 2
        return north == (inst.data.get("moitie") == "nord")
    return inst.center is not None and state.world.distance(h, inst.center) <= inst.radius


def zone_bands(state, inst, tid: int, village=None) -> list:
    return [b for b in _bands(state, tid, village) if in_zone(state, inst, b.position)]


def _note(state, tid: int, kind, text: str, where=None) -> None:
    from src.kora.sim import is_human, note

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
            from src.kora.sim import set_goto

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
    from src.kora.world import enter_cost_for

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
        from src.kora import chiefs

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
    goal = "Chaque mois, chaque village ajoute au monument (bien plus s'il a déjà une pierre levée ou un autel) ; dresser des pierres en plus."
    name = "Les grands travaux"
    kind = CONJONCTURE
    era = 1
    icon = "dolmen"
    about = "Les peuples voisins dressent des pierres pour leurs ancêtres. Le plus grand monument dira qui est le plus grand peuple."
    stages = (("Les pierres se dressent", "On traîne des blocs sur des rondins ; chaque village veut sa pierre.", {}),)
    actions = (
        Action("pierre", "Dresser une pierre", "Cent bras, des cordes, des rondins : une pierre de plus au monument.", vivres=200, score=10, cooldown=3 * MONTH),
    )
    months = 6 * 12
    cooldown = 15 * YEAR

    def candidates(self, state):
        if not 17 <= state.clock.week <= 20:
            return []
        peoples = sorted({s.tribe_id for s in _villages(state) if "ancetres" in state.tribes[s.tribe_id].knowledge})
        for tid in peoples:
            mine = _villages(state, tid)
            others = [t for t in peoples if t != tid and any(state.world.distance(a.hex, b.hex) <= 40 for a in mine for b in _villages(state, t))]
            if others:
                return [(mine[0].hex, 40, sorted([tid] + others), {})]
        return []

    def chance(self, state):
        return 0.25

    def month(self, state, inst):
        from src.kora import villages

        for tid in sorted(inst.participants):
            for site in _villages(state, tid):
                if in_zone(state, inst, site.hex):
                    inst.participants[tid]["score"] += 1 + (3 if villages.has(site, "pierre") or villages.has(site, "autel") else 0)

    def end(self, state, inst):
        win = inst.winner
        if not win:
            return
        tribe = state.tribes[win]
        tribe.prestige = min(100, tribe.prestige + 20)
        grant_effect(tribe, "sit:travaux:prix", state.tick_count + 10 * YEAR)
        best = inst.participants[win]["score"]
        for t, p in inst.participants.items():
            if t != win and p["score"] >= best * 0.5:
                state.tribes[t].prestige = min(100, state.tribes[t].prestige + 5)
            _note(state, t, LogKind.DECOUVERTE, f"Les grands travaux sont finis : le grand monument est celui des {tribe.name} (prestige, stabilité, 10 ans).")


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


SPECS: dict[str, Spec] = {s.id: s for s in (Disette(), MalQuiCourt(), GibierEpuise(), GrandHiver(), GrandPassage(), Rassemblement(), Rouille(), MalDesBetes(), Crue(), GrandsTravaux(), RouteDuSel(), Chefferies())}

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
    "sit:travaux:prix": ("Le grand monument", {"stability": 10, "diplo": 10}),
    "sit:sel:prix": ("Carrefour des échanges", {"diplo": 8, "gifts": 1.3}),
    "sit:chefferies:prix": ("Chefferie dominante", {"diplo": 15, "loyalty": 5}),
}


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
