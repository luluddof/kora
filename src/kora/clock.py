"""L'HORLOGE de la partie : l'annee, la semaine (1 a 52), la pause et la
vitesse (1 a 5 : 2, 4, 6, 8 ou 10 semaines par seconde, ticks_per_second).

La saison CALENDAIRE est une tranche de 13 semaines (Clock.season) ; la
saison LOCALE d'une case, qui avance sur la carte, est dans world.py
(World.hex_season). L'hiver commence a la semaine 40 (weeks_until_winter).
Une semaine de jeu = un tick (sim.tick) ; en bataille d'un joueur, un pas
dure un jour (state.step : voir gamestate.py). N'importe pas pygame.
"""

from src.kora.types import Season


class Clock:
    def __init__(self) -> None:
        self.year = 1
        self.week = 1
        self.paused = True
        self.speed = 1
        self._finished_winter = False

    def season(self) -> Season:
        if self.week <= 13:
            return Season.PRINTEMPS
        if self.week <= 26:
            return Season.ETE
        if self.week <= 39:
            return Season.AUTOMNE
        return Season.HIVER

    def advance_week(self) -> None:
        self._finished_winter = False
        if self.week == 52:
            self.week = 1
            self.year += 1
            self._finished_winter = True
        else:
            self.week += 1

    def just_finished_winter(self) -> bool:
        return self._finished_winter

    def ticks_per_second(self) -> int:
        if self.paused:
            return 0
        return {1: 2, 2: 4, 3: 6, 4: 8, 5: 10}[self.speed]

    def set_speed(self, value: int) -> None:
        if value in (1, 2, 3, 4, 5):
            self.speed = value
            self.paused = False

    def toggle_pause(self) -> None:
        self.paused = not self.paused

    def weeks_until_winter(self) -> int:
        if self.week >= 40:
            return 0
        return 40 - self.week
