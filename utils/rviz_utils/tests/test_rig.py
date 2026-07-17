from __future__ import annotations

import math

import numpy as np
import pytest

from rviz_utils.hri.rig import semantic_to_rig


def _Rx(a: float) -> np.ndarray:
    c, s = math.cos(a), math.sin(a)
    return np.array([[1.0, 0.0, 0.0], [0.0, c, -s], [0.0, s, c]])


def _Ry(a: float) -> np.ndarray:
    c, s = math.cos(a), math.sin(a)
    return np.array([[c, 0.0, s], [0.0, 1.0, 0.0], [-s, 0.0, c]])


def _Rz(a: float) -> np.ndarray:
    c, s = math.cos(a), math.sin(a)
    return np.array([[c, -s, 0.0], [s, c, 0.0], [0.0, 0.0, 1.0]])


_SHOULDER_NAMES = (
    "l_y_shoulder",
    "l_p_shoulder",
    "l_r_shoulder",
    "r_y_shoulder",
    "r_p_shoulder",
    "r_r_shoulder",
)


def _translate_shoulders(f: float) -> dict[str, float]:
    """Feed semantic shoulder values (p=f, reserved y/r=0) through the adapter."""
    positions = [0.0, f, 0.0, 0.0, f, 0.0]
    out = semantic_to_rig(_SHOULDER_NAMES, positions)
    return dict(zip(_SHOULDER_NAMES, out, strict=True))


_FLEX_VALUES = [0.0, 0.3, 1.2, -0.4, -1.0, math.pi / 3]


@pytest.mark.parametrize("f", _FLEX_VALUES)
def test_left_chain_matches_forward_flexion(f: float) -> None:
    s = _translate_shoulders(f)
    y, p, r = s["l_y_shoulder"], s["l_p_shoulder"], s["l_r_shoulder"]
    chain = _Rz(-y) @ _Rx(p) @ _Rz(r)
    assert np.allclose(chain, _Ry(-f), atol=1e-9)


@pytest.mark.parametrize("f", _FLEX_VALUES)
def test_right_chain_matches_forward_flexion(f: float) -> None:
    s = _translate_shoulders(f)
    y, p, r = s["r_y_shoulder"], s["r_p_shoulder"], s["r_r_shoulder"]
    chain = _Rz(y) @ _Rx(-p) @ _Rz(-r)
    assert np.allclose(chain, _Ry(-f), atol=1e-9)


def test_constant_shoulder_joints_are_half_pi() -> None:
    s = _translate_shoulders(0.9)
    for name in ("l_y_shoulder", "l_r_shoulder", "r_y_shoulder", "r_r_shoulder"):
        assert math.isclose(s[name], math.pi / 2, abs_tol=1e-12)


@pytest.mark.parametrize("f", _FLEX_VALUES)
def test_p_shoulder_passthrough(f: float) -> None:
    s = _translate_shoulders(f)
    assert math.isclose(s["l_p_shoulder"], f, abs_tol=1e-12)
    assert math.isclose(s["r_p_shoulder"], f, abs_tol=1e-12)


def test_non_shoulder_joints_passthrough() -> None:
    names = ["l_r_hip", "l_elbow", "waist", "r_knee", "p_head"]
    positions = [0.45, 0.8, 0.03, -0.9, 0.1]
    out = semantic_to_rig(names, positions)
    assert out == positions


def test_mixed_sequence_preserves_order_and_length() -> None:
    names = ["waist", "l_y_shoulder", "l_p_shoulder", "l_elbow", "r_p_shoulder"]
    positions = [0.02, 0.0, 0.5, 0.7, 0.5]
    out = semantic_to_rig(names, positions)
    assert len(out) == len(names)
    assert out[0] == 0.02
    assert math.isclose(out[1], math.pi / 2, abs_tol=1e-12)
    assert out[2] == 0.5
    assert out[3] == 0.7
    assert out[4] == 0.5
