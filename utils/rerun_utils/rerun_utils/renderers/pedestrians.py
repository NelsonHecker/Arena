"""DisplayKind.PEDESTRIANS renderer: visualization_msgs/MarkerArray → rerun.

Consumes the converted-marker stream produced by pedestrian_marker_publisher.
"""

from __future__ import annotations

from arena_viz import DisplayKind, StyleSpec
from task_generator_msgs.msg import AdapterDisplay, RobotDescriptor

from rerun_utils.entity_paths import display_path
from rerun_utils.renderers._registry import RendererCtx, register
from rerun_utils.renderers.marker_array import subscribe_marker_array


@register(DisplayKind.PEDESTRIANS)
def render_pedestrians(d: AdapterDisplay, robot: RobotDescriptor | None, ctx: RendererCtx) -> None:
    style = StyleSpec.from_json(d.style_json)
    if not style.enabled:
        return
    subscribe_marker_array(ctx, d, display_path(ctx.env_id, robot, d.name))
