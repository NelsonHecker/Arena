from __future__ import annotations

import shutil
from pathlib import Path

import pytest

try:
    import arena_simulation_setup.tree.World as World
    import attrs
    import yaml
    from task_generator.utils.zone_corners import write_zone_corners
except ImportError:
    pytestmark = pytest.mark.skip(reason="ROS2 not available")

_WORLDS = Path(__file__).resolve().parents[3] / "arena_simulation_setup" / "worlds"


def _load(path: Path) -> World.WorldDescription:
    return World.MultiLevelWorldView(path).load()


@pytest.fixture
def reception(tmp_path: Path) -> Path:
    shutil.copytree(_WORLDS / "reception", tmp_path / "reception", ignore=shutil.ignore_patterns("scenarios"))
    return tmp_path / "reception"


def test_corner_edit_changes_zone_lookup_after_compaction(reception: Path):
    world = _load(reception)
    zone = next(z for z in world.levels["0"].zones if z.name == "entrance")
    zone.corners[2] = attrs.evolve(zone.corners[2], x=31.5)

    polygon = world.compact_world({"0": (0.0, 0.0)}).lookup_zone_polygon("entrance")

    assert polygon is not None
    assert polygon[2].x == 31.5


def test_saved_corner_edit_survives_reload_and_leaves_other_values(reception: Path):
    world_yaml = reception / "0" / "world.yaml"
    before = yaml.safe_load(world_yaml.read_text())
    world = _load(reception)
    zone = next(z for z in world.levels["0"].zones if z.name == "entrance")
    zone.corners[2] = attrs.evolve(zone.corners[2], x=31.5, y=24.25)

    corners = {z.name: [(c.x, c.y) for c in z.corners] for z in world.levels["0"].zones}
    write_zone_corners(world_yaml, corners)

    after = yaml.safe_load(world_yaml.read_text())
    assert after["zones"][1]["corners"][2] == [31.5, 24.25]
    after["zones"][1]["corners"][2] = before["zones"][1]["corners"][2]
    assert after == before
    reloaded = next(z for z in _load(reception).levels["0"].zones if z.name == "entrance")
    assert (reloaded.corners[2].x, reloaded.corners[2].y) == (31.5, 24.25)
