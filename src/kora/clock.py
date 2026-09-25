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
