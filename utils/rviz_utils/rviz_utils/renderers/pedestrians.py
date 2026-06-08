"""Renderer for DisplayKind.PEDESTRIANS (visualization_msgs/MarkerArray)."""

from __future__ import annotations

from arena_viz import DisplayKind, StyleSpec
from task_generator_msgs.msg import AdapterDisplay, RobotDescriptor

from rviz_utils.renderers._registry import register


@register(DisplayKind.PEDESTRIANS)
def render_pedestrians(d: AdapterDisplay, robot: RobotDescriptor | None) -> dict[str, object] | None:
    style = StyleSpec.from_json(d.style_json)
    result: dict[str, object] = {
        "Class": "rviz_default_plugins/MarkerArray",
        "Name": d.name,
        "Enabled": style.enabled,
        "Topic": {
            "Value": d.topic,
            "Depth": 20,
            "History Policy": "Keep Last",
            "Reliability Policy": "Best Effort",
            "Durability Policy": "Volatile",
        },
        "Namespaces": {
            "pedestrian_meshes": True,
            "pedestrian_arrows": True,
            "pedestrian_labels": True,
        },
        "Value": True,
    }
    result.update(style.extra.get("rviz", {}))
    return result
