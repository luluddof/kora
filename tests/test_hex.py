from src.kora.types import Hex
from src.kora.world import (
    axial_to_offset,
    hex_distance,
    hex_neighbors,
    offset_to_axial,
)


def test_offset_roundtrip():
    for col in range(0, 10):
        for row in range(0, 10):
            h = offset_to_axial(col, row)
            c2, r2 = axial_to_offset(h)
            assert (c2, r2) == (col, row)


def test_distance_zero():
    h = Hex(3, 4)
    assert hex_distance(h, h) == 0


def test_distance_neighbors_is_one():
    h = Hex(0, 0)
    for n in hex_neighbors(h):
        assert hex_distance(h, n) == 1


def test_twelve_east_distance():
    a = Hex(0, 0)
    b = Hex(12, 0)
    assert hex_distance(a, b) == 12
