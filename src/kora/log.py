from dataclasses import dataclass, field
from enum import Enum


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


def season_fr(season) -> str:
    from src.kora.types import Season

    names = {
        Season.PRINTEMPS: "Printemps",
        Season.ETE: "Ete",
        Season.AUTOMNE: "Automne",
        Season.HIVER: "Hiver",
    }
    return names.get(season, getattr(season, "value", str(season)))


def terrain_fr(terrain) -> str:
    from src.kora.types import Terrain

    names = {
        Terrain.PLAINE: "Plaine",
        Terrain.VALLEE: "Vallee",
        Terrain.STEPPE: "Steppe",
        Terrain.FORET: "Foret",
        Terrain.COLLINE: "Colline",
        Terrain.MONTAGNE: "Montagne",
        Terrain.SOMMET: "Sommet",
        Terrain.EAU: "Eau",
        Terrain.COTE: "Cote",
        Terrain.DESERT: "Desert",
    }
    return names.get(terrain, terrain.value)
