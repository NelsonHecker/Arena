"""DisplayKind.PEDESTRIANS renderer: visualization_msgs/MarkerArray → rr.Boxes3D / rr.Points3D.

Consumes the converted-marker stream produced by pedestrian_marker_publisher.
"""

from __future__ import annotations

import rerun as rr
from arena_viz import DisplayKind, StyleSpec
from rclpy.qos import QoSProfile, ReliabilityPolicy
from task_generator_msgs.msg import AdapterDisplay, RobotDescriptor
from visualization_msgs.msg import Marker, MarkerArray

from rerun_utils.entity_paths import display_path
from rerun_utils.renderers._registry import RendererCtx, register


def _marker_color(m: Marker) -> tuple[int, int, int, int]:
    c = m.color
    return (int(c.r * 255), int(c.g * 255), int(c.b * 255), int(c.a * 255))


@register(DisplayKind.PEDESTRIANS)
def render_pedestrians(d: AdapterDisplay, robot: RobotDescriptor | None, ctx: RendererCtx) -> None:
    style = StyleSpec.from_json(d.style_json)
    if not style.enabled:
        return
    base = display_path(ctx.env_id, robot, d.name)

    def cb(msg: MarkerArray) -> None:
        cylinders: list[tuple[float, float, float]] = []
        cyl_sizes: list[tuple[float, float, float]] = []
        cyl_colors: list[tuple[int, int, int, int]] = []
        for m in msg.markers:
            if m.type in (Marker.CYLINDER, Marker.CUBE):
                cylinders.append((m.pose.position.x, m.pose.position.y, m.pose.position.z))
                cyl_sizes.append((m.scale.x, m.scale.y, m.scale.z))
                cyl_colors.append(_marker_color(m))
        if cylinders:
            rr.log(
                f"{base}/bodies",
                rr.Boxes3D(centers=cylinders, sizes=cyl_sizes, colors=cyl_colors),
            )

    qos = QoSProfile(depth=5, reliability=ReliabilityPolicy.BEST_EFFORT)
    ctx.node.create_subscription(MarkerArray, d.topic, cb, qos)
