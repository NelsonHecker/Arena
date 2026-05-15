"""Handlers for ``TaskKind.REACH_POSE``.

Declarations only: each ``HANDLERS.register`` call below stores a zero-arg
loader. The actual handler modules (and their msgs deps) are imported lazily
by ``HANDLERS.get`` when that bringup is selected at node startup.
"""

from __future__ import annotations

from arena_robots_msgs.action import ReachPose

from arena_robots.task_kinds import TaskKind
from arena_robots.task_server_handlers import HANDLERS, TaskHandler

ReachPoseHandler = TaskHandler[ReachPose.Goal, ReachPose.Feedback, ReachPose.Result]


@HANDLERS.register((TaskKind.REACH_POSE, "none"))
def _load_none() -> type[ReachPoseHandler]:
    from ._passthrough import ReachPoseHandlerNone

    return ReachPoseHandlerNone


@HANDLERS.register((TaskKind.REACH_POSE, "moveit"))
def _load_moveit() -> type[ReachPoseHandler]:
    from .moveit import ReachPoseHandlerMoveIt

    return ReachPoseHandlerMoveIt
