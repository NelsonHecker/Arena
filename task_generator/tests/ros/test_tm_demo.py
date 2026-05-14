from __future__ import annotations

import math

import pytest


@pytest.fixture(autouse=True)
def _ros_gate():
    try:
        import rclpy  # noqa: F401
    except ImportError:
        pytest.skip("ROS2 not available")


def _origin() -> object:
    from task_generator.shared import Position

    return Position(0.0, 0.0, 0.0)


def _at(x: float, y: float) -> object:
    from task_generator.shared import Position

    return Position(x, y, 0.0)


def test_vertices_count():
    from task_generator.tasks.robots.demo.impl import _Orientation, _vertices

    result = _vertices(_origin(), 4, 1.5, _Orientation.RADIAL_IN)
    assert len(result) == 4


def test_vertices_on_circle_at_origin():
    from task_generator.tasks.robots.demo.impl import _Orientation, _vertices

    radius = 1.5
    for pose in _vertices(_origin(), 4, radius, _Orientation.RADIAL_IN):
        dist = math.hypot(pose.position.x, pose.position.y)
        assert abs(dist - radius) < 1e-9


def test_vertices_on_circle_offset_center():
    from task_generator.tasks.robots.demo.impl import _Orientation, _vertices

    cx, cy, radius = 5.0, 3.0, 1.5
    for pose in _vertices(_at(cx, cy), 4, radius, _Orientation.RADIAL_IN):
        dist = math.hypot(pose.position.x - cx, pose.position.y - cy)
        assert abs(dist - radius) < 1e-9


def test_vertices_radial_in_faces_center():
    from task_generator.tasks.robots.demo.impl import _Orientation, _vertices

    cx, cy = 5.0, 3.0
    for pose in _vertices(_at(cx, cy), 4, 1.5, _Orientation.RADIAL_IN):
        x, y = pose.position.x, pose.position.y
        expected_yaw = math.atan2(cy - y, cx - x)
        actual_yaw = pose.orientation.to_yaw()
        diff = (actual_yaw - expected_yaw + math.pi) % (2 * math.pi) - math.pi
        assert abs(diff) < 1e-9


def test_vertices_radial_out_faces_away_from_center():
    from task_generator.tasks.robots.demo.impl import _Orientation, _vertices

    cx, cy = 5.0, 3.0
    for pose in _vertices(_at(cx, cy), 4, 1.5, _Orientation.RADIAL_OUT):
        x, y = pose.position.x, pose.position.y
        expected_yaw = math.atan2(y - cy, x - cx)
        actual_yaw = pose.orientation.to_yaw()
        diff = (actual_yaw - expected_yaw + math.pi) % (2 * math.pi) - math.pi
        assert abs(diff) < 1e-9


def test_vertices_tangent_points_to_next():
    from task_generator.tasks.robots.demo.impl import _Orientation, _vertices

    n = 3
    poses = _vertices(_at(2.0, 2.0), n, 2.0, _Orientation.TANGENT)
    for i, pose in enumerate(poses):
        nx = poses[(i + 1) % n].position.x
        ny = poses[(i + 1) % n].position.y
        expected_yaw = math.atan2(ny - pose.position.y, nx - pose.position.x)
        actual_yaw = pose.orientation.to_yaw()
        diff = (actual_yaw - expected_yaw + math.pi) % (2 * math.pi) - math.pi
        assert abs(diff) < 1e-9


def test_vertices_too_few_raises():
    from task_generator.tasks.robots.demo.impl import _Orientation, _vertices

    with pytest.raises(ValueError, match="VERTICES"):
        _vertices(_origin(), 2, 1.0, _Orientation.TANGENT)


def test_vertices_negative_radius_raises():
    from task_generator.tasks.robots.demo.impl import _Orientation, _vertices

    with pytest.raises(ValueError, match="RADIUS"):
        _vertices(_origin(), 4, -1.0, _Orientation.TANGENT)


def test_vertices_zero_radius_raises():
    from task_generator.tasks.robots.demo.impl import _Orientation, _vertices

    with pytest.raises(ValueError, match="RADIUS"):
        _vertices(_origin(), 4, 0.0, _Orientation.TANGENT)


def test_vertices_bad_orientation_raises():
    from task_generator.tasks.robots.demo.impl import _vertices

    with pytest.raises(ValueError, match="ORIENTATION"):
        _vertices(_origin(), 4, 1.0, "spiral")  # type: ignore[arg-type]


def test_pick_gesture_canonical_random_returns_none():
    from task_generator.tasks.robots.demo.impl import _pick_gesture

    assert _pick_gesture("<random>") is None


def test_pick_gesture_empty_returns_string():
    from task_generator.tasks.robots.demo.impl import _pick_gesture

    # "" is not the canonical sentinel after parse; _pick_gesture only checks "<random>"
    assert _pick_gesture("") == ""


def test_pick_gesture_named_returns_name():
    from task_generator.tasks.robots.demo.impl import _pick_gesture

    assert _pick_gesture("wave") == "wave"


def test_parse_gesture_empty_canonicalizes():
    from task_generator.tasks.robots.demo.impl import _parse_gesture

    assert _parse_gesture("") == "<random>"


def test_parse_gesture_random_canonicalizes():
    from task_generator.tasks.robots.demo.impl import _parse_gesture

    assert _parse_gesture("random") == "<random>"


def test_parse_gesture_canonical_random():
    from task_generator.tasks.robots.demo.impl import _parse_gesture

    assert _parse_gesture("<random>") == "<random>"


def test_parse_gesture_wave_returns_wave():
    from arena_simulation_setup import ASS_DIR

    gestures_dir = ASS_DIR / "configs" / "gestures"
    if not gestures_dir.exists():
        pytest.skip("gestures config dir not present in test environment")

    from task_generator.tasks.robots.demo.impl import _parse_gesture

    assert _parse_gesture("wave") == "wave"


def test_parse_gesture_unknown_raises():
    from arena_simulation_setup import ASS_DIR

    gestures_dir = ASS_DIR / "configs" / "gestures"
    if not gestures_dir.exists():
        pytest.skip("gestures config dir not present in test environment")

    from task_generator.tasks.robots.demo.impl import _parse_gesture

    with pytest.raises(ValueError, match="unknown gesture"):
        _parse_gesture("nonexistent_gesture_xyz")
