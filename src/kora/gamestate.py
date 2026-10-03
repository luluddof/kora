"""L'ETAT DE LA PARTIE (GameState) et ses joueurs.

Tout ce qui est la partie a un instant : le monde, le temps, les peuples,
les bandes, les lieux, la diplomatie, les evenements, les situations... (les
regles qui la font avancer sont ailleurs : sim.py et chaque systeme). Et les
peuples joueurs : qui est humain, son journal, ce qu'il a vu.
Le module le plus bas apres types.py : tout le monde peut l'importer en tete.
N'importe pas pygame.
"""

from __future__ import annotations

import random
from dataclasses import dataclass, field

from src.kora.clock import Clock
from src.kora.log import GameLog, LogKind
from src.kora.types import Band, Diplomacy, Hex, Tribe
from src.kora.world import World

PLAYER_TRIBE_ID = 1
AI_STEPPE_ID = 2
AI_FOREST_ID = 3
AI_COAST_ID = 4


@dataclass
class GameState:
    world: World
    clock: Clock
    tribes: dict[int, Tribe]
    bands: dict[int, Band]
    tick_count: int = 0
    rng: random.Random = field(default_factory=lambda: random.Random(1))
    last_error: str | None = None
    player_dead: bool = False
    last_pressure: dict[Hex, float] = field(default_factory=dict)
    vision: object | None = None
    log: GameLog = field(default_factory=GameLog)
    seen_enemy_tribes: set[int] = field(default_factory=set)
    fights: list = field(default_factory=list)
    next_band_id: int = 0
    # Positions deja examinees pour "rivage / steppe en vue" (la carte ne
    # change pas) : cache, pas sauvegarde.
    scan_memo: set = field(default_factory=set)
    # Hasard du recit (noms, evenements, chefs), separe de celui de l'IA :
    # ajouter une histoire ne change pas les choix de marche des bandes.
    story_rng: random.Random = field(default_factory=lambda: random.Random(7))
    next_tribe_id: int = 0
    # Zone d'influence : presences de la semaine (influence.py), cases
    # partagees entre deux peuples (recalcule chaque mois).
    presence: dict = field(default_factory=dict)
    overlap: dict = field(default_factory=dict)
    # Caches, campements, villages (sites.py).
    sites: dict = field(default_factory=dict)
    next_site_id: int = 1
    # Relations et pactes entre peuples (diplo.py).
    diplo: Diplomacy = field(default_factory=Diplomacy)
    next_person_id: int = 1
    # Evenements en attente du joueur, suites prevues (events.py). story :
    # les evenements tournent (vraie partie) ; les etats montes a la main
    # par les tests n'en ont pas.
    events: object | None = None
    story: bool = False
    # Caches de l'IA, le temps de decide_ai (ni sauvegardes ni copies) :
    # bandes rangees par carreaux de la carte, forces deja calculees.
    band_grid: object | None = None
    force_memo: object | None = None
    # Relations deja calculees, le temps d'une phase ou elles ne changent pas
    # (diplo.frozen_relations) : ni sauvegardees ni copiees.
    rel_memo: object | None = None
    # Multijoueur : ce que voit et lit chaque autre peuple joueur (Pov) ; le
    # joueur solo (PLAYER_TRIBE_ID) garde log, vision et seen_enemy_tribes.
    povs: dict = field(default_factory=dict)
    # Le joueur de CET ecran : l'interface seulement, la simulation ne le lit
    # jamais (sinon deux machines calculeraient deux parties differentes).
    viewer: int = PLAYER_TRIBE_ID
    # Crises et conjonctures (situations.py), leur numero, leurs dernieres
    # fins ("sid:peuple" -> semaine) pour ne pas les repeter trop vite.
    situations: list = field(default_factory=list)
    next_situation_uid: int = 1
    situation_last: dict = field(default_factory=dict)
    # Les crises qui menacent chaque joueur (situations._risks, chaque mois ;
    # calcule, pas sauvegarde).
    situation_risks: dict = field(default_factory=dict)
    # Les batailles en cours (battle.py), le jour de la semaine (le temps
    # passe en jours pendant une bataille d'un joueur) et le nombre de pas.
    battles: list = field(default_factory=list)
    next_battle_uid: int = 1
    day: int = 0
    step: int = 0


@dataclass
class Pov:
    """Ce qui est a un joueur : son journal, sa vue, les peuples apercus."""

    log: GameLog = field(default_factory=GameLog)
    vision: object | None = None
    seen: set = field(default_factory=set)


# --- les peuples joueurs -------------------------------------------------------------
# Un peuple is_player est mene par un humain : en solo, PLAYER_TRIBE_ID seul ;
# en multijoueur, un par joueur. Les messages vont au journal du peuple
# concerne (note(..., to=tid)) ; ce que tous peuvent voir va a chacun de ceux
# qui le voient (note_seen).


def humans(state: GameState) -> list[int]:
    """Les peuples menes par un joueur (le joueur solo compte toujours)."""
    out = [tid for tid, t in state.tribes.items() if t.is_player and tid != PLAYER_TRIBE_ID]
    out.sort()
    return [PLAYER_TRIBE_ID] + out


def is_human(state: GameState, tid: int) -> bool:
    if tid == PLAYER_TRIBE_ID:
        return True
    tribe = state.tribes.get(tid)
    return bool(tribe is not None and tribe.is_player)


def pov_of(state: GameState, tid: int) -> Pov:
    pov = state.povs.get(tid)
    if pov is None:
        pov = state.povs[tid] = Pov()
    return pov


def log_of(state: GameState, tid: int) -> GameLog:
    """Le journal d'un peuple joueur."""
    if tid == PLAYER_TRIBE_ID:
        return state.log
    return pov_of(state, tid).log


def seen_of(state: GameState, tid: int) -> set:
    """Les peuples qu'un joueur a deja apercus."""
    if tid == PLAYER_TRIBE_ID:
        return state.seen_enemy_tribes
    return pov_of(state, tid).seen


def human_dead(state: GameState, tid: int) -> bool:
    """Le peuple de ce joueur n'a plus personne."""
    if tid == PLAYER_TRIBE_ID:
        return state.player_dead
    return not any(b.tribe_id == tid and b.population > 0 for b in state.bands.values())


def note(state: GameState, kind: LogKind, text: str, where: Hex | None = None, to: int = PLAYER_TRIBE_ID) -> None:
    log_of(state, to).add(kind, text, state.clock.year, state.clock.week, where=where)


def note_all(state: GameState, kind: LogKind, text: str, where: Hex | None = None) -> None:
    """A tous les joueurs (les saisons...)."""
    for tid in humans(state):
        note(state, kind, text, where, to=tid)
