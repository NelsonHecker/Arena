"""Renderer for DisplayKind.PEDESTRIANS (visualization_msgs/MarkerArray)."""

from __future__ import annotations

from arena_viz import DisplayKind, StyleSpec
from task_generator_msgs.msg import AdapterDisplay, RobotDescriptor

from rviz_utils.renderers._registry import register


@register(DisplayKind.PEDESTRIANS)
def render_pedestrians(d: AdapterDisplay, robot: RobotDescriptor | None) -> dict[str, object] | None:
    style = StyleSpec.from_json(d.style_json)
    rviz_extra: dict[str, object] = style.extra.get("rviz", {})
    reliability = rviz_extra.get("Reliability Policy", "Best Effort")
    durability = rviz_extra.get("Durability Policy", "Volatile")
    namespaces = rviz_extra.get(
        "Namespaces",
        {
            "pedestrian_meshes": True,
            "pedestrian_orientation": True,
            "pedestrian_velocity": True,
            "pedestrian_labels": True,
        },
    )
    result: dict[str, object] = {
        "Class": "rviz_default_plugins/MarkerArray",
        "Name": d.name,
        "Enabled": style.enabled,
        "Topic": {
            "Value": d.topic,
            "Depth": 20,
            "History Policy": "Keep Last",
            "Reliability Policy": reliability,
            "Durability Policy": durability,
        },
        "Namespaces": namespaces,
        "Value": True,
    }
    for k, v in rviz_extra.items():
        if k not in ("Reliability Policy", "Durability Policy", "Namespaces"):
            result[k] = v
    return result
