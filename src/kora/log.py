"""LE JOURNAL du joueur : des lignes datees (annee, semaine), d'un genre
(LogKind : combat, survie, saison, decouverte, politique - "Peuples" a
l'ecran), avec la case ou elles se passent (un clic y emmene la camera).

GameLog garde les LOG_CAP dernieres lignes ; filtered les trie pour les
filtres de l'onglet Journal. season_fr / terrain_fr : les noms francais des
saisons et des sols dans les textes. Un message du jeu passe par
gamestate.note (jamais GameLog.add directement : un joueur, un journal).
N'importe pas pygame.
"""

import re
from dataclasses import dataclass, field
from enum import Enum
from src.kora.types import Season, Terrain


class LogKind(Enum):
    COMBAT = "combat"
    SURVIE = "survie"
    SAISON = "saison"
    DECOUVERTE = "decouverte"
    POLITIQUE = "politique"


LOG_CAP = 120

FILTER_ALL = "tous"
FILTERS = (
    FILTER_ALL,
    LogKind.COMBAT.value,
    LogKind.SURVIE.value,
    LogKind.SAISON.value,
    LogKind.DECOUVERTE.value,
    LogKind.POLITIQUE.value,
)


@dataclass
class LogEntry:
    year: int
    week: int
    kind: LogKind
    text: str
    seq: int = 0
    hex: object = None


@dataclass
class GameLog:
    entries: list[LogEntry] = field(default_factory=list)
    seq: int = 0

    def add(
        self, kind: LogKind, text: str, year: int, week: int, where=None
    ) -> LogEntry:
        self.seq += 1
        entry = LogEntry(
            year=year, week=week, kind=kind, text=text, seq=self.seq, hex=where
        )
        self.entries.append(entry)
        if len(self.entries) > LOG_CAP:
            self.entries = self.entries[-LOG_CAP:]
        return entry

    def filtered(self, filt: str, newest_first: bool = True) -> list[LogEntry]:
        if filt == FILTER_ALL:
            rows = list(self.entries)
        else:
            rows = [e for e in self.entries if e.kind.value == filt]
        rows.sort(key=lambda e: e.seq, reverse=newest_first)
        return rows


# --- les repetitions (2026-11-19) --------------------------------------------------------
# Ses parties neuves : 18 lignes du journal sur 32 disaient "Famine : 1
# morts", une par semaine. A l'ecran (le journal, les nouvelles), les
# lignes qui se suivent et ne different que par leurs nombres n'en font
# qu'une : "Famine : 12 morts", de telle semaine a telle autre, 9 fois.
_DIGITS = re.compile(r"\d+")


def repeat_key(entry) -> tuple:
    """Ce qui fait que deux lignes se repetent : le genre, le lieu de
    l'histoire, le texte sans ses nombres."""
    return (getattr(entry.kind, "value", entry.kind), _DIGITS.sub("#", entry.text))


def merged_text(texts: list[str]) -> str:
    """Le texte d'un groupe : s'il porte UN nombre, la somme ; sinon le
    premier de la liste."""
    first = texts[0]
    nums = [_DIGITS.findall(t) for t in texts]
    if all(len(n) == 1 for n in nums):
        total = sum(int(n[0]) for n in nums)
        return _DIGITS.sub(str(total), first, count=1)
    return first


def group_repeats(rows: list) -> list[dict]:
    """[{entry (la plus recente), first (la plus ancienne), count, text}],
    dans l'ordre des lignes : les lignes CONSECUTIVES qui se repetent
    (repeat_key) n'en font qu'une."""
    out: list[dict] = []
    for e in rows:
        if out and repeat_key(out[-1]["entry"]) == repeat_key(e):
            g = out[-1]
            g["texts"].append(e.text)
            g["count"] += 1
            if e.seq < g["first"].seq:
                g["first"] = e
            if e.seq > g["entry"].seq:
                g["entry"] = e
            continue
        out.append({"entry": e, "first": e, "count": 1, "texts": [e.text]})
    for g in out:
        g["text"] = merged_text(g["texts"]) if g["count"] > 1 else g["entry"].text
        del g["texts"]
    return out


def season_fr(season) -> str:
    names = {
        Season.PRINTEMPS: "Printemps",
        Season.ETE: "Été",
        Season.AUTOMNE: "Automne",
        Season.HIVER: "Hiver",
    }
    return names.get(season, getattr(season, "value", str(season)))


def terrain_fr(terrain) -> str:
    names = {
        Terrain.PLAINE: "Plaine",
        Terrain.VALLEE: "Vallée",
        Terrain.STEPPE: "Steppe",
        Terrain.FORET: "Forêt",
        Terrain.COLLINE: "Colline",
        Terrain.MONTAGNE: "Montagne",
        Terrain.SOMMET: "Sommet",
        Terrain.EAU: "Eau",
        Terrain.COTE: "Côte",
        Terrain.DESERT: "Désert",
        Terrain.TOUNDRA: "Toundra",
        Terrain.GLACE: "Glace",
        Terrain.MARAIS: "Marais",
        Terrain.JUNGLE: "Jungle",
        Terrain.SAVANE: "Savane",
    }
    return names.get(terrain, terrain.value)
