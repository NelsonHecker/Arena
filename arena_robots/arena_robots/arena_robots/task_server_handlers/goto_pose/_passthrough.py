from __future__ import annotations

from typing import TYPE_CHECKING

from geometry_msgs.msg import PoseStamped

from arena_robots_msgs.action import GotoPose

if TYPE_CHECKING:
    from arena_robots.bringup.external import ExternalBringup
    from arena_robots.bringup.none import NoneBringup


class _PassthroughHandler:
    """Publishes the goal to a topic and immediately succeeds.

    Shared body of the ``none`` and ``external`` bringups — both treat the
    arena ``GotoPose`` action as a fire-and-forget goal-pose publish."""

    def __init__(self, bringup: "NoneBringup | ExternalBringup", *, tf_buffer, node) -> None:
        self._pub = node.create_publisher(PoseStamped, bringup.goal_topic, 1)

    async def execute(self, goal_handle) -> GotoPose.Result:
        arena_goal: GotoPose.Goal = goal_handle.request
        self._pub.publish(arena_goal.target)
        goal_handle.succeed()
        result = GotoPose.Result()
        result.status = GotoPose.Result.STATUS_SUCCEEDED
        result.final_pose = arena_goal.target
        return result


class GotoPoseHandlerNone(_PassthroughHandler):
    pass


class GotoPoseHandlerExternal(_PassthroughHandler):
    pass
