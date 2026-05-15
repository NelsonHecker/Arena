from __future__ import annotations

import pytest
import yaml

from arena_simulation_setup.tree.Gesture import GestureIdentifier, GestureKeyframe, GestureSpec


# ---------------------------------------------------------------------------
# GestureSpec.parse
# ---------------------------------------------------------------------------


def test_gesture_spec_parse_wave():
    data = {
        "interp": "linear",
        "keyframes": [
            {"pose": "ready", "t": 0.0},
            {"pose": "wave_up", "t": 0.6},
            {"pose": "wave_l", "t": 1.2},
            {"pose": "wave_r", "t": 1.6},
            {"pose": "wave_l", "t": 2.0},
            {"pose": "wave_r", "t": 2.4},
            {"pose": "ready", "t": 3.0},
        ],
    }
    spec = GestureSpec.parse(data)
    assert spec.interp == "linear"
    assert len(spec.keyframes) == 7
    assert spec.keyframes[0].pose == "ready"
    assert spec.keyframes[0].t == pytest.approx(0.0)
    assert spec.keyframes[1].pose == "wave_up"
    assert spec.keyframes[1].t == pytest.approx(0.6)
    assert spec.keyframes[-1].pose == "ready"
    assert spec.keyframes[-1].t == pytest.approx(3.0)


def test_gesture_spec_default_interp():
    data = {
        "keyframes": [
            {"pose": "ready", "t": 0.0},
            {"pose": "nod_dn", "t": 0.4},
        ],
    }
    spec = GestureSpec.parse(data)
    assert spec.interp == "linear"


def test_gesture_spec_invalid_interp_raises():
    data = {
        "interp": "cubic",
        "keyframes": [
            {"pose": "ready", "t": 0.0},
        ],
    }
    with pytest.raises((ValueError, Exception)):
        GestureSpec.parse(data)


# ---------------------------------------------------------------------------
# GestureSpec.required_poses
# ---------------------------------------------------------------------------


def test_required_poses_wave():
    data = {
        "interp": "linear",
        "keyframes": [
            {"pose": "ready", "t": 0.0},
            {"pose": "wave_up", "t": 0.6},
            {"pose": "wave_l", "t": 1.2},
            {"pose": "wave_r", "t": 1.6},
            {"pose": "wave_l", "t": 2.0},
            {"pose": "wave_r", "t": 2.4},
            {"pose": "ready", "t": 3.0},
        ],
    }
    spec = GestureSpec.parse(data)
    assert spec.required_poses() == frozenset({"ready", "wave_up", "wave_l", "wave_r"})


def test_required_poses_deduplicates():
    data = {
        "interp": "linear",
        "keyframes": [
            {"pose": "a", "t": 0.0},
            {"pose": "a", "t": 1.0},
            {"pose": "b", "t": 2.0},
        ],
    }
    spec = GestureSpec.parse(data)
    assert spec.required_poses() == frozenset({"a", "b"})


# ---------------------------------------------------------------------------
# GestureIdentifier.load from file
# ---------------------------------------------------------------------------


def test_gesture_identifier_load_wave_yaml(tmp_path):
    wave_data = {
        "interp": "linear",
        "keyframes": [
            {"pose": "ready", "t": 0.0},
            {"pose": "wave_up", "t": 0.6},
            {"pose": "wave_l", "t": 1.2},
            {"pose": "wave_r", "t": 1.6},
            {"pose": "wave_l", "t": 2.0},
            {"pose": "wave_r", "t": 2.4},
            {"pose": "ready", "t": 3.0},
        ],
    }
    p = tmp_path / "wave.yaml"
    p.write_text(yaml.dump(wave_data))

    ident = GestureIdentifier("wave")
    spec = ident.load(p)
    assert isinstance(spec, GestureSpec)
    assert len(spec.keyframes) == 7
    assert isinstance(spec.keyframes[0], GestureKeyframe)
    assert spec.required_poses() == frozenset({"ready", "wave_up", "wave_l", "wave_r"})


def test_gesture_identifier_load_invalid_interp_raises(tmp_path):
    bad_data = {
        "interp": "cubic",
        "keyframes": [{"pose": "ready", "t": 0.0}],
    }
    p = tmp_path / "bad.yaml"
    p.write_text(yaml.dump(bad_data))

    ident = GestureIdentifier("bad")
    with pytest.raises((ValueError, Exception)):
        ident.load(p)
