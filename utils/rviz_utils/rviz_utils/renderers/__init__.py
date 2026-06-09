"""Renderer registry for rviz display kinds."""

from __future__ import annotations

from arena_viz import DisplayKind

from rviz_utils.renderers import (  # noqa: F401 -- import to trigger @register side-effects
    foot_contact,
    image,
    imu,
    laser_scan,
    map,
    marker_array,
    odom,
    path,
    pedestrians,
    planning_scene,
    points3d,
    polygon,
    pose,
    robot_model,
    tf,
    trajectory,
)
from rviz_utils.renderers._registry import REGISTRY, register

_missing = {k for k in DisplayKind if k not in REGISTRY}
assert not _missing, f"renderers missing for: {_missing}"

__all__ = ["REGISTRY", "register"]
