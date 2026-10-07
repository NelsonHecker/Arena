from __future__ import annotations

import shutil
from pathlib import Path

import pytest
import yaml
from task_generator.utils.zone_corners import write_zone_corners

_WORLDS = Path(__file__).resolve().parents[3] / "arena_simulation_setup" / "worlds"


def _copy(tmp_path: Path, world: str, level: str) -> Path:
    target = tmp_path / "world.yaml"
    shutil.copy(_WORLDS / world / level / "world.yaml", target)
    return target


def _without_corners(data: dict) -> dict:
    return {**data, "zones": [{k: v for k, v in zone.items() if k != "corners"} for zone in data["zones"]]}


def test_flow_sequence_corner_edit_changes_only_that_coordinate(tmp_path: Path):
    path = _copy(tmp_path, "reception", "0")
    before = path.read_text()
    original = yaml.safe_load(before)
    corners = [tuple(c) for c in original["zones"][1]["corners"]]
    corners[2] = (31.5, 24.25)

    assert write_zone_corners(path, {"entrance": corners}) == 2

    after = path.read_text()
    changed = [(a, b) for a, b in zip(before.splitlines(), after.splitlines(), strict=True) if a != b]
    assert changed == [("      - [30.0, 23.0]", "      - [31.5, 24.25]")]
    edited = yaml.safe_load(after)
    assert edited["zones"][1]["corners"][2] == [31.5, 24.25]
    assert _without_corners(edited) == _without_corners(original)


def test_mapping_corner_edit_keeps_untouched_zones_and_z(tmp_path: Path):
    path = _copy(tmp_path, "three_storied_residential", "1")
    original = yaml.safe_load(path.read_text())
    first = original["zones"][0]
    corners = [(c["x"], c["y"]) for c in first["corners"]]
    corners[1] = (corners[1][0] + 0.5, corners[1][1])

    assert write_zone_corners(path, {first["name"]: corners}) == 1

    edited = yaml.safe_load(path.read_text())
    assert edited["zones"][0]["corners"][1] == {**first["corners"][1], "x": first["corners"][1]["x"] + 0.5}
    assert edited["zones"][0]["corners"][0] == first["corners"][0]
    assert edited["zones"][1:] == original["zones"][1:]


def test_unchanged_corners_leave_file_untouched(tmp_path: Path):
    path = _copy(tmp_path, "reception", "0")
    before = path.read_bytes()
    corners = {z["name"]: [tuple(c) for c in z["corners"]] for z in yaml.safe_load(before)["zones"]}

    assert write_zone_corners(path, corners) == 0
    assert path.read_bytes() == before


def test_unknown_zone_is_rejected(tmp_path: Path):
    path = _copy(tmp_path, "reception", "0")
    with pytest.raises(ValueError, match="no zone"):
        write_zone_corners(path, {"nowhere": [(0.0, 0.0)]})


def test_corner_count_mismatch_is_rejected(tmp_path: Path):
    path = _copy(tmp_path, "reception", "0")
    with pytest.raises(ValueError, match="corners"):
        write_zone_corners(path, {"entrance": [(0.0, 0.0)]})
