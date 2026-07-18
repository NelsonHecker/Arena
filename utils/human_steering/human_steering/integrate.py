"""Pure kinematic integration: waypoint following and teleop dead-reckoning.

ROS-free, Qt-free. Every step function takes dt explicitly and freezes (no-op)
when dt <= 0, matching the driver's own cadence: it derives dt from the node's
sim-time clock, so a paused sim yields dt == 0 and motion holds in place.
"""

from __future__ import annotations

import math

ARRIVAL_M = 0.2
DEADMAN_S = 0.5


def waypoint_step(
    x: float,
    y: float,
    yaw: float,
    target_x: float,
    target_y: float,
    speed: float,
    dt: float,
    arrival_m: float = ARRIVAL_M,
) -> tuple[float, float, float, bool]:
    """Advance one step toward (target_x, target_y). Returns (x, y, yaw, arrived)."""
    if dt <= 0.0:
        return x, y, yaw, False
    dx = target_x - x
    dy = target_y - y
    dist = math.hypot(dx, dy)
    if dist <= arrival_m:
        return target_x, target_y, yaw, True
    heading = math.atan2(dy, dx)
    step = min(speed * dt, dist)
    return x + math.cos(heading) * step, y + math.sin(heading) * step, heading, False


def advance_waypoints(
    x: float,
    y: float,
    yaw: float,
    waypoints: list[tuple[float, float]],
    cursor: int,
    speed: float,
    dt: float,
    loop: bool,
    arrival_m: float = ARRIVAL_M,
) -> tuple[float, float, float, int]:
    """Advance one step toward waypoints[cursor], returns (x, y, yaw, next_cursor), advancing the cursor on arrival, wrapping if loop else holding at len(waypoints)."""
    if not waypoints or cursor >= len(waypoints):
        return x, y, yaw, cursor
    target_x, target_y = waypoints[cursor]
    nx, ny, nyaw, arrived = waypoint_step(x, y, yaw, target_x, target_y, speed, dt, arrival_m)
    if arrived:
        cursor += 1
        if loop:
            cursor %= len(waypoints)
    return nx, ny, nyaw, cursor


def teleop_step(
    x: float,
    y: float,
    yaw: float,
    vx: float,
    vy: float,
    wz: float,
    dt: float,
) -> tuple[float, float, float]:
    """Integrate one body-frame twist (vx forward, vy strafe, wz turn) step."""
    if dt <= 0.0:
        return x, y, yaw
    cos_yaw, sin_yaw = math.cos(yaw), math.sin(yaw)
    dx = (vx * cos_yaw - vy * sin_yaw) * dt
    dy = (vx * sin_yaw + vy * cos_yaw) * dt
    return x + dx, y + dy, yaw + wz * dt


def deadman_expired(last_cmd_wall: float, now_wall: float, deadman_s: float = DEADMAN_S) -> bool:
    """True once now_wall is more than deadman_s past the last received command."""
    return (now_wall - last_cmd_wall) > deadman_s
