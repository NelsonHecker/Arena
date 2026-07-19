"""Per-joint composition (slider > gaze > clip > gait) and gaze angle solving.

ROS-free, Qt-free: consumes and returns plain dicts of bare joint names to
radians so it is importable and testable without a sourced ROS install.
"""

from __future__ import annotations

import math
from collections.abc import Mapping, Sequence

GAZE_HEAD_HEIGHT_M = 1.6


def wrap_pi(angle: float) -> float:
    """Wrap an angle to (-pi, pi]."""
    return (angle + math.pi) % (2.0 * math.pi) - math.pi


def solve_gaze(
    origin_x: float,
    origin_y: float,
    origin_yaw: float,
    target_x: float,
    target_y: float,
    target_z: float = 0.0,
    head_height: float = GAZE_HEAD_HEIGHT_M,
) -> tuple[float, float]:
    """Solve (y_head, p_head) so the head points at a world-frame target.

    y_head is the head yaw relative to the ped's own body heading, p_head the
    head pitch (positive = looking down) from a head mounted at head_height.
    """
    dx = target_x - origin_x
    dy = target_y - origin_y
    y_head = wrap_pi(math.atan2(dy, dx) - origin_yaw)
    horizontal = math.hypot(dx, dy)
    if horizontal <= 1e-6:
        p_head = 0.0
    else:
        p_head = -math.atan2(target_z - head_height, horizontal)
    return y_head, p_head


def compose_joint(
    name: str,
    *,
    slider: float | None,
    gaze: Mapping[str, float],
    clip: Mapping[str, float],
    gait: float,
) -> float:
    """Resolve one joint: engaged slider wins, then gaze (head joints only), then clip, else gait fallback."""
    if slider is not None:
        return slider
    if name in gaze:
        return gaze[name]
    if name in clip:
        return clip[name]
    return gait


def compose(
    names: Sequence[str],
    *,
    slider: Mapping[str, float],
    gaze: Mapping[str, float],
    clip: Mapping[str, float],
    gait: Mapping[str, float],
) -> dict[str, float]:
    """Compose every joint for one ped: slider (engaged) > gaze > clip > gait fallback."""
    return {
        name: compose_joint(
            name,
            slider=slider.get(name),
            gaze=gaze,
            clip=clip,
            gait=gait.get(name, 0.0),
        )
        for name in names
    }
