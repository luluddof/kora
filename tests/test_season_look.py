from src.kora.look import BIOME_COLORS, season_color
from src.kora.types import Season, Terrain


def test_winter_land_is_whiter_than_base():
    base = BIOME_COLORS[Terrain.PLAINE]
    winter = season_color(Terrain.PLAINE, Season.HIVER)
    assert sum(winter) > sum(base)


def test_summer_steppe_is_yellower_than_spring():
    spring = season_color(Terrain.STEPPE, Season.PRINTEMPS)
    summer = season_color(Terrain.STEPPE, Season.ETE)
    assert summer[0] >= spring[0]
    assert summer[2] <= spring[2]


def test_autumn_forest_is_redder_than_summer():
    summer = season_color(Terrain.FORET, Season.ETE)
    autumn = season_color(Terrain.FORET, Season.AUTOMNE)
    assert autumn[0] > summer[0]


def test_water_stays_bluer_than_land_in_winter():
    land = season_color(Terrain.PLAINE, Season.HIVER)
    water = season_color(Terrain.EAU, Season.HIVER)
    assert water[2] - water[0] > land[2] - land[0]
