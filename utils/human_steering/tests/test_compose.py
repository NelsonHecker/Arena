from __future__ import annotations

import math

from human_steering.compose import compose, compose_joint, solve_gaze, wrap_pi


def test_precedence_slider_wins() -> None:
    value = compose_joint("waist", slider=0.5, gaze={"waist": 0.1}, clip={"waist": 0.2}, gait=0.3)
    assert value == 0.5


def test_precedence_gaze_over_clip_and_gait() -> None:
    value = compose_joint("y_head", slider=None, gaze={"y_head": 0.1}, clip={"y_head": 0.2}, gait=0.3)
    assert value == 0.1


def test_precedence_clip_over_gait() -> None:
    value = compose_joint("l_elbow", slider=None, gaze={}, clip={"l_elbow": 0.2}, gait=0.3)
    assert value == 0.2


def test_precedence_gait_fallback() -> None:
    value = compose_joint("r_knee", slider=None, gaze={}, clip={}, gait=0.3)
    assert value == 0.3


def test_gaze_only_affects_its_own_joint_names() -> None:
    # gaze dict never contains "l_elbow", so it must not shadow the clip value.
    value = compose_joint("l_elbow", slider=None, gaze={"y_head": 0.1}, clip={"l_elbow": 0.2}, gait=0.0)
    assert value == 0.2


def test_compose_resolves_every_joint_independently() -> None:
    names = ["waist", "y_head", "l_elbow", "r_knee"]
    result = compose(
        names,
        slider={"waist": 1.0},
        gaze={"y_head": 2.0},
        clip={"l_elbow": 3.0},
        gait={"waist": 9.0, "y_head": 9.0, "l_elbow": 9.0, "r_knee": 9.0},
    )
    assert result == {"waist": 1.0, "y_head": 2.0, "l_elbow": 3.0, "r_knee": 9.0}


def test_wrap_pi_stays_in_range() -> None:
    assert math.isclose(wrap_pi(3.0 * math.pi), -math.pi, abs_tol=1e-9) or math.isclose(wrap_pi(3.0 * math.pi), math.pi, abs_tol=1e-9)
    assert -math.pi <= wrap_pi(10.0) <= math.pi


def test_solve_gaze_target_ahead_gives_zero_yaw() -> None:
    y_head, _p_head = solve_gaze(0.0, 0.0, 0.0, target_x=5.0, target_y=0.0)
    assert math.isclose(y_head, 0.0, abs_tol=1e-9)


def test_solve_gaze_target_to_the_left() -> None:
    y_head, _p_head = solve_gaze(0.0, 0.0, 0.0, target_x=0.0, target_y=5.0)
    assert math.isclose(y_head, math.pi / 2.0, abs_tol=1e-9)


def test_solve_gaze_relative_to_body_heading() -> None:
    # facing +y already (yaw=pi/2), a target further along +y is straight ahead -> yaw 0.
    y_head, _p_head = solve_gaze(0.0, 0.0, math.pi / 2.0, target_x=0.0, target_y=5.0)
    assert math.isclose(y_head, 0.0, abs_tol=1e-9)


def test_solve_gaze_pitch_looks_down_at_close_low_target() -> None:
    _y_head, p_head = solve_gaze(0.0, 0.0, 0.0, target_x=1.0, target_y=0.0, target_z=0.0, head_height=1.6)
    assert p_head > 0.0  # positive pitch = looking down, per the module contract


def test_solve_gaze_degenerate_same_point_returns_zero_pitch() -> None:
    _y_head, p_head = solve_gaze(1.0, 1.0, 0.0, target_x=1.0, target_y=1.0, target_z=1.6, head_height=1.6)
    assert p_head == 0.0
