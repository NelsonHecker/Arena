from __future__ import annotations

import math
import os

import pytest
from human_steering.clips import (
    Clip,
    blend,
    load_wire_json_file,
    parse_wire_json,
    poses_root,
    sample,
    sample_root_z,
    sample_track,
    slug,
)


def _clip(**overrides: object) -> Clip:
    base = {
        "name": "wave",
        "duration": 1.0,
        "cyclic": True,
        "rate_hz": 4.0,
        "tracks": {"waist": (0.0, 1.0, 0.0, -1.0)},
        "root_z": None,
    }
    base.update(overrides)
    return Clip(**base)  # type: ignore[arg-type]


def test_sample_track_exact_keyframe() -> None:
    value = sample_track((0.0, 1.0, 0.0, -1.0), rate_hz=4.0, duration=1.0, cyclic=True, t=0.25)
    assert math.isclose(value, 1.0, abs_tol=1e-9)


def test_sample_track_interpolates_between_keyframes() -> None:
    # halfway between index 0 (0.0) and index 1 (1.0) at t=0.125 (pos=0.5).
    value = sample_track((0.0, 1.0, 0.0, -1.0), rate_hz=4.0, duration=1.0, cyclic=True, t=0.125)
    assert 0.0 < value < 1.0
    # cosine interpolation at the midpoint of two keyframes lands exactly halfway.
    assert math.isclose(value, 0.5, abs_tol=1e-9)


def test_sample_track_loop_wrap() -> None:
    # t=1.0 on a 1.0s cyclic track wraps back to t=0.0.
    at_zero = sample_track((0.0, 1.0, 0.0, -1.0), rate_hz=4.0, duration=1.0, cyclic=True, t=0.0)
    at_wrap = sample_track((0.0, 1.0, 0.0, -1.0), rate_hz=4.0, duration=1.0, cyclic=True, t=1.0)
    assert math.isclose(at_zero, at_wrap, abs_tol=1e-9)


def test_sample_track_non_cyclic_clamps_and_holds_last_frame() -> None:
    value = sample_track((0.0, 1.0, 0.0, -1.0), rate_hz=4.0, duration=1.0, cyclic=False, t=10.0)
    assert value == -1.0


def test_sample_track_single_frame_is_constant() -> None:
    assert sample_track((0.7,), rate_hz=4.0, duration=0.0, cyclic=False, t=100.0) == 0.7


def test_sample_track_empty_is_zero() -> None:
    assert sample_track((), rate_hz=4.0, duration=1.0, cyclic=True, t=0.5) == 0.0


def test_sample_all_tracks_of_a_clip() -> None:
    clip = _clip()
    result = sample(clip, 0.25)
    assert result == {"waist": pytest.approx(1.0)}


def test_sample_root_z_present() -> None:
    clip = _clip(root_z=(0.0, 0.1, 0.0, -0.1))
    assert sample_root_z(clip, 0.25) == pytest.approx(0.1)


def test_sample_root_z_absent_is_none() -> None:
    clip = _clip(root_z=None)
    assert sample_root_z(clip, 0.25) is None


def test_blend_at_zero_elapsed_is_prev() -> None:
    result = blend({"waist": 0.0}, {"waist": 1.0}, elapsed_s=0.0, blend_s=0.3)
    assert math.isclose(result["waist"], 0.0, abs_tol=1e-9)


def test_blend_past_window_is_next() -> None:
    result = blend({"waist": 0.0}, {"waist": 1.0}, elapsed_s=0.3, blend_s=0.3)
    assert result == {"waist": 1.0}


def test_blend_midway_is_between() -> None:
    result = blend({"waist": 0.0}, {"waist": 1.0}, elapsed_s=0.15, blend_s=0.3)
    assert 0.0 < result["waist"] < 1.0


def test_blend_zero_window_is_immediate() -> None:
    result = blend({"waist": 0.0}, {"waist": 1.0}, elapsed_s=0.0, blend_s=0.0)
    assert result == {"waist": 1.0}


def test_blend_key_only_in_prev_holds_its_value() -> None:
    result = blend({"waist": 0.5}, {}, elapsed_s=0.0, blend_s=0.3)
    assert result == {"waist": 0.5}


def test_parse_wire_json_schema() -> None:
    doc = {
        "version": 1,
        "rate_hz": 30,
        "clips": {
            "wave": {
                "duration": 1.0,
                "cyclic": True,
                "tracks": {"r_elbow": [0.0, 1.0]},
                "root_z": [0.0, 0.01],
            },
        },
    }
    clips = parse_wire_json(doc)
    assert set(clips) == {"wave"}
    clip = clips["wave"]
    assert clip.duration == 1.0
    assert clip.cyclic is True
    assert clip.rate_hz == 30.0
    assert clip.tracks == {"r_elbow": (0.0, 1.0)}
    assert clip.root_z == (0.0, 0.01)


def test_parse_wire_json_missing_root_z_is_none() -> None:
    doc = {"version": 1, "rate_hz": 30, "clips": {"idle": {"duration": 0.0, "cyclic": False, "tracks": {}}}}
    clips = parse_wire_json(doc)
    assert clips["idle"].root_z is None


def test_load_wire_json_file_missing_is_empty(tmp_path: object) -> None:
    assert load_wire_json_file(tmp_path / "nope.json") == {}  # type: ignore[operator]


def test_slug_collapses_non_alphanumerics() -> None:
    assert slug("agent 07 (npc)") == "agent_07_npc"
    assert slug("agent 07") == "agent_07"
    assert slug("a--b__c") == "a_b_c"
    assert slug("...") == "_"


def test_poses_root_uses_arena_data_dir(tmp_path: object) -> None:
    previous = os.environ.get("ARENA_DATA_DIR")
    os.environ["ARENA_DATA_DIR"] = str(tmp_path)
    try:
        assert poses_root() == tmp_path / "peds" / "poses"  # type: ignore[operator]
    finally:
        if previous is None:
            os.environ.pop("ARENA_DATA_DIR", None)
        else:
            os.environ["ARENA_DATA_DIR"] = previous
