from __future__ import annotations

import random

import pytest
import shapely
from shapely import LineString, MultiLineString, Polygon

from arena_simulation_setup.utils.generative import (
    BaseConfiguration,
    WorldGeneratorType,
    WorldGenerator,
)
from arena_simulation_setup.utils.generative.empty import WorldGeneratorEmpty
from arena_simulation_setup.utils.generative.hallway import WorldGeneratorHallway
from arena_simulation_setup.utils.generative.utils import line_pairs, to_corners, to_walls


# ---------------------------------------------------------------------------
# WorldGeneratorType enum
# ---------------------------------------------------------------------------


def test_world_generator_type_empty_value():
    assert WorldGeneratorType.EMPTY.value == "empty"


def test_world_generator_type_hallway_value():
    assert WorldGeneratorType.HALLWAY.value == "hallway"


# ---------------------------------------------------------------------------
# BaseConfiguration defaults
# ---------------------------------------------------------------------------


def test_base_configuration_defaults():
    cfg = BaseConfiguration()
    assert cfg.width == pytest.approx(15.0)
    assert cfg.height == pytest.approx(15.0)
    assert cfg.resolution == pytest.approx(0.05)
    assert cfg.wall_gap == pytest.approx(0.05)


def test_base_configuration_custom_values():
    cfg = BaseConfiguration(width=20.0, height=30.0)
    assert cfg.width == pytest.approx(20.0)
    assert cfg.height == pytest.approx(30.0)


def test_base_configuration_custom_resolution():
    cfg = BaseConfiguration(resolution=0.1)
    assert cfg.resolution == pytest.approx(0.1)


# ---------------------------------------------------------------------------
# WorldGeneratorEmpty.compute
# ---------------------------------------------------------------------------


def test_world_generator_empty_compute_single_zone():
    gen = WorldGeneratorEmpty({"width": 10.0, "height": 8.0})
    wd = gen.compute()
    assert len(wd.zones) == 1


def test_world_generator_empty_compute_4_corners():
    gen = WorldGeneratorEmpty({"width": 10.0, "height": 8.0})
    wd = gen.compute()
    corners = wd.zones[0].corners
    # shapely Polygon.exterior.coords includes closing point = 5 for rectangle
    assert len(corners) >= 4


def test_world_generator_empty_compute_has_walls():
    gen = WorldGeneratorEmpty({"width": 10.0, "height": 8.0})
    wd = gen.compute()
    walls = wd.zones[0].walls
    assert len(walls) > 0


# ---------------------------------------------------------------------------
# WorldGeneratorHallway.Configuration
# ---------------------------------------------------------------------------


def test_hallway_config_defaults():
    cfg = WorldGeneratorHallway.Configuration()
    assert cfg.width == pytest.approx(80.0)
    assert cfg.height == pytest.approx(50.0)
    assert cfg.hallway_height == pytest.approx(5.0)


def test_hallway_config_hallway_top():
    cfg = WorldGeneratorHallway.Configuration()
    assert cfg.hallway_top == pytest.approx(cfg.height / 2 + cfg.hallway_height / 2)


def test_hallway_config_hallway_bottom():
    cfg = WorldGeneratorHallway.Configuration()
    assert cfg.hallway_bottom == pytest.approx(cfg.height / 2 - cfg.hallway_height / 2)


def test_hallway_config_hallway_top_custom():
    cfg = WorldGeneratorHallway.Configuration(height=100.0, hallway_height=10.0)
    assert cfg.hallway_top == pytest.approx(55.0)
    assert cfg.hallway_bottom == pytest.approx(45.0)


# ---------------------------------------------------------------------------
# WorldGeneratorHallway.compute (seeded random for determinism)
# ---------------------------------------------------------------------------


def test_hallway_compute_room_count_per_side():
    rng_state = random.getstate()
    random.seed(42)
    try:
        gen = WorldGeneratorHallway({
            "rooms_per_side": 3,
            "width": 40.0,
            "height": 30.0,
        })
        wd = gen.compute()
        # 2 sides, each with (1 hallway + rooms_per_side) zones
        assert len(wd.zones) == 2 * (1 + 3)
    finally:
        random.setstate(rng_state)


def test_hallway_compute_doors_per_room():
    random.seed(0)
    gen = WorldGeneratorHallway({
        "rooms_per_side": 2,
        "width": 40.0,
        "height": 30.0,
    })
    wd = gen.compute()
    door_zones = [z for z in wd.zones if z.doors]
    assert len(door_zones) > 0


# ---------------------------------------------------------------------------
# utils.line_pairs
# ---------------------------------------------------------------------------


def test_line_pairs_polygon_exterior():
    poly = Polygon([(0, 0), (1, 0), (1, 1), (0, 1)])
    pairs = list(line_pairs(poly))
    assert len(pairs) == 4  # 4 edges in square


def test_line_pairs_polygon_with_interior():
    outer = [(0, 0), (10, 0), (10, 10), (0, 10)]
    inner = [(3, 3), (7, 3), (7, 7), (3, 7)]
    poly = Polygon(outer, [inner])
    pairs = list(line_pairs(poly))
    # exterior: 4 + interior: 4 = 8
    assert len(pairs) == 8


def test_line_pairs_linestring():
    ls = LineString([(0, 0), (1, 0), (2, 0)])
    pairs = list(line_pairs(ls))
    assert len(pairs) == 2


def test_line_pairs_multilinestring():
    mls = MultiLineString([[(0, 0), (1, 0)], [(2, 0), (3, 0)]])
    pairs = list(line_pairs(mls))
    assert len(pairs) == 2


# ---------------------------------------------------------------------------
# utils.to_corners
# ---------------------------------------------------------------------------


def test_to_corners_square():
    poly = Polygon([(0, 0), (1, 0), (1, 1), (0, 1)])
    corners = to_corners(poly)
    # Polygon closes itself, so exterior.coords has 5 points
    assert len(corners) == 5


def test_to_corners_empty():
    poly = Polygon()
    corners = to_corners(poly)
    assert corners == []


# ---------------------------------------------------------------------------
# utils.to_walls
# ---------------------------------------------------------------------------


def test_to_walls_polygon():
    poly = Polygon([(0, 0), (2, 0), (2, 2), (0, 2)])
    walls = to_walls(poly)
    assert len(walls) == 4


def test_to_walls_linestring():
    ls = LineString([(0, 0), (1, 0), (2, 0)])
    walls = to_walls(ls)
    assert len(walls) == 2


def test_to_walls_multilinestring():
    mls = MultiLineString([[(0, 0), (1, 0)], [(2, 0), (4, 0)]])
    walls = to_walls(mls)
    assert len(walls) == 2
