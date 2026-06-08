"""DisplayKind.TF renderer: no-op. The TF tree is mirrored by tf_mirror.TFMirror unconditionally."""

from __future__ import annotations

from arena_viz import DisplayKind
from task_generator_msgs.msg import AdapterDisplay, RobotDescriptor

from rerun_utils.renderers._registry import RendererCtx, register


@register(DisplayKind.TF)
def render_tf(d: AdapterDisplay, robot: RobotDescriptor | None, ctx: RendererCtx) -> None:
    del d, robot, ctx
