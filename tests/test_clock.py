from src.kora.clock import Clock
from src.kora.types import Season


def test_seasons_ranges():
    c = Clock()
    c.week = 1
    assert c.season() is Season.PRINTEMPS
    c.week = 14
    assert c.season() is Season.ETE
    c.week = 27
    assert c.season() is Season.AUTOMNE
    c.week = 40
    assert c.season() is Season.HIVER
    c.week = 52
    assert c.season() is Season.HIVER


def test_year_wrap_and_winter_flag():
    c = Clock()
    c.year = 1
    c.week = 52
    assert c.just_finished_winter() is False
    c.advance_week()
    assert c.year == 2
    assert c.week == 1
    assert c.just_finished_winter() is True
    c.advance_week()
    assert c.just_finished_winter() is False


def test_ticks_per_second_and_pause():
    c = Clock()
    c.paused = True
    assert c.ticks_per_second() == 0
    c.paused = False
    c.set_speed(1)
    assert c.ticks_per_second() == 2
    c.set_speed(2)
    assert c.ticks_per_second() == 4
    c.set_speed(5)
    assert c.ticks_per_second() == 10
    c.set_speed(3)
    assert c.speed == 3
    assert c.paused is False
    assert c.ticks_per_second() == 6
    c.set_speed(4)
    assert c.speed == 4
    assert c.ticks_per_second() == 8
