"""DisplayKind.INTERACTIVE_MARKERS renderer: rerun has no interactive markers, nothing is logged."""

from __future__ import annotations

from arena_viz import DisplayKind
from task_generator_msgs.msg import AdapterDisplay, RobotDescriptor

from rerun_utils.renderers._registry import RendererCtx, register


@register(DisplayKind.INTERACTIVE_MARKERS)
def render_interactive_markers(d: AdapterDisplay, robot: RobotDescriptor | None, ctx: RendererCtx) -> None:
    del d, robot, ctx
