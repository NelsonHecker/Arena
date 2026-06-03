"""Renderer registry for rerun display kinds."""

from __future__ import annotations

from arena_viz import DisplayKind

from rerun_utils.renderers import (  # noqa: F401 -- import to trigger @register side-effects
    foot_contact,
    image,
    imu,
    laser_scan,
    map,
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
from rerun_utils.renderers._registry import REGISTRY, RendererCtx, register

_missing = {k for k in DisplayKind if k not in REGISTRY}
assert not _missing, f"rerun renderers missing for: {_missing}"

__all__ = ["REGISTRY", "RendererCtx", "register"]
