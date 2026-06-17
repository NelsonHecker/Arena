"""Renderer for DisplayKind.IMU (sensor_msgs/Imu)."""

from __future__ import annotations

import os

from arena_viz import DisplayKind, StyleSpec
from task_generator_msgs.msg import AdapterDisplay, RobotDescriptor

from rviz_utils.renderers._registry import register


@register(DisplayKind.IMU)
def render_imu(d: AdapterDisplay, robot: RobotDescriptor | None) -> dict[str, object] | None:
    style = StyleSpec.from_json(d.style_json)
    color = "204; 51; 204"
    if style.color is not None:
        r, g, b = style.color
        color = f"{r}; {g}; {b}"
    name = d.name if d.name else f"IMU: {os.path.basename(d.topic)}"
    result: dict[str, object] = {
        "Class": "rviz_default_plugins/Imu",
        "Name": name,
        "Enabled": style.enabled,
        "Topic": {
            "Value": d.topic,
            "Depth": 20,
            "History Policy": "Keep Last",
            "Reliability Policy": "Best Effort",
            "Durability Policy": "Volatile",
        },
        "Axes Length": 0.3,
        "Axes Radius": 0.03,
        "Color": color,
    }
    result.update(style.extra.get("rviz", {}))
    return result
