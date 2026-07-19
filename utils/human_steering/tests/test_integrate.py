from __future__ import annotations

import math

from human_steering.integrate import (
    ARRIVAL_M,
    DEADMAN_S,
    advance_waypoints,
    deadman_expired,
    teleop_step,
    waypoint_step,
)


def test_waypoint_step_moves_toward_target() -> None:
    x, y, yaw, arrived = waypoint_step(0.0, 0.0, 0.0, 10.0, 0.0, speed=1.0, dt=1.0)
    assert x == 1.0
    assert y == 0.0
    assert yaw == 0.0
    assert not arrived


def test_waypoint_step_heading_atan2() -> None:
    _x, _y, yaw, _arrived = waypoint_step(0.0, 0.0, 0.0, 0.0, 5.0, speed=1.0, dt=0.1)
    assert math.isclose(yaw, math.pi / 2.0, abs_tol=1e-9)


def test_waypoint_step_arrival_within_radius() -> None:
    x, y, _yaw, arrived = waypoint_step(0.0, 0.0, 0.0, 0.1, 0.0, speed=1.0, dt=1.0, arrival_m=ARRIVAL_M)
    assert arrived
    assert x == 0.1
    assert y == 0.0


def test_waypoint_step_does_not_overshoot_target() -> None:
    # speed*dt (10.0) far exceeds the remaining distance (2.0), the step must
    # clamp exactly onto the target instead of overshooting past it. Arrival
    # itself is flagged on the following call, once distance-to-target is
    # re-checked from the landed position.
    x, y, _yaw, arrived = waypoint_step(0.0, 0.0, 0.0, 2.0, 0.0, speed=10.0, dt=1.0)
    assert not arrived
    assert x == 2.0
    assert y == 0.0
    _x2, _y2, _yaw2, arrived2 = waypoint_step(x, y, 0.0, 2.0, 0.0, speed=10.0, dt=1.0)
    assert arrived2


def test_waypoint_step_dt_zero_freezes() -> None:
    x, y, yaw, arrived = waypoint_step(1.0, 2.0, 0.5, 10.0, 10.0, speed=1.0, dt=0.0)
    assert (x, y, yaw) == (1.0, 2.0, 0.5)
    assert not arrived


def test_advance_waypoints_advances_cursor_without_loop() -> None:
    waypoints = [(0.1, 0.0), (5.0, 5.0)]
    _x, _y, _yaw, cursor = advance_waypoints(0.0, 0.0, 0.0, waypoints, cursor=0, speed=1.0, dt=1.0, loop=False)
    assert cursor == 1
    assert waypoints == [(0.1, 0.0), (5.0, 5.0)]  # the route itself is never mutated


def test_advance_waypoints_non_loop_holds_at_route_end() -> None:
    waypoints = [(0.1, 0.0)]
    _x, _y, _yaw, cursor = advance_waypoints(0.0, 0.0, 0.0, waypoints, cursor=0, speed=1.0, dt=1.0, loop=False)
    assert cursor == 1
    x, y, yaw, cursor2 = advance_waypoints(0.1, 0.0, 0.0, waypoints, cursor=cursor, speed=1.0, dt=1.0, loop=False)
    assert (x, y, yaw) == (0.1, 0.0, 0.0)
    assert cursor2 == 1


def test_advance_waypoints_loop_wraps_cursor_to_front() -> None:
    waypoints = [(0.1, 0.0), (5.0, 5.0)]
    _x, _y, _yaw, cursor = advance_waypoints(0.0, 0.0, 0.0, waypoints, cursor=0, speed=1.0, dt=1.0, loop=True)
    assert cursor == 1
    _x, _y, _yaw, cursor = advance_waypoints(5.0, 5.0, 0.0, waypoints, cursor=cursor, speed=1.0, dt=1.0, loop=True)
    assert cursor == 0
    assert waypoints == [(0.1, 0.0), (5.0, 5.0)]  # input list is not mutated


def test_advance_waypoints_empty_list_is_noop() -> None:
    waypoints: list[tuple[float, float]] = []
    x, y, yaw, cursor = advance_waypoints(3.0, 4.0, 0.2, waypoints, cursor=0, speed=1.0, dt=1.0, loop=False)
    assert (x, y, yaw) == (3.0, 4.0, 0.2)
    assert cursor == 0


def test_advance_waypoints_cursor_past_end_is_noop() -> None:
    waypoints = [(0.1, 0.0)]
    x, y, yaw, cursor = advance_waypoints(3.0, 4.0, 0.2, waypoints, cursor=1, speed=1.0, dt=1.0, loop=False)
    assert (x, y, yaw) == (3.0, 4.0, 0.2)
    assert cursor == 1


def test_teleop_step_forward_and_turn() -> None:
    x, y, yaw = teleop_step(0.0, 0.0, 0.0, vx=1.0, vy=0.0, wz=0.5, dt=1.0)
    assert x == 1.0
    assert y == 0.0
    assert yaw == 0.5


def test_teleop_step_body_frame_strafe_respects_heading() -> None:
    # facing +y (yaw=pi/2): a body-frame +vy (left/strafe) step moves in world -x.
    x, y, _yaw = teleop_step(0.0, 0.0, math.pi / 2.0, vx=0.0, vy=1.0, wz=0.0, dt=1.0)
    assert math.isclose(x, -1.0, abs_tol=1e-9)
    assert math.isclose(y, 0.0, abs_tol=1e-9)


def test_teleop_step_dt_zero_freezes() -> None:
    x, y, yaw = teleop_step(1.0, 2.0, 0.3, vx=5.0, vy=5.0, wz=5.0, dt=0.0)
    assert (x, y, yaw) == (1.0, 2.0, 0.3)


def test_deadman_not_expired_within_window() -> None:
    assert not deadman_expired(last_cmd_wall=0.0, now_wall=DEADMAN_S - 0.01)


def test_deadman_expired_past_window() -> None:
    assert deadman_expired(last_cmd_wall=0.0, now_wall=DEADMAN_S + 0.01)


def test_deadman_boundary_is_exclusive() -> None:
    assert not deadman_expired(last_cmd_wall=0.0, now_wall=DEADMAN_S)
