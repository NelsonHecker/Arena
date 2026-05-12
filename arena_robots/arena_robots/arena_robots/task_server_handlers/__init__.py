"""Registry of per-(TaskKind, bringup_kind) action-server handlers.

Handlers are registered via zero-arg loader functions so their modules — and
any non-core msgs deps (e.g. ``nav2_msgs``) — are imported only when that
particular ``(task_kind, bringup_kind)`` pair is actually requested.
"""

from __future__ import annotations

from typing import (
    TYPE_CHECKING,
    Protocol,
    TypeVar,
)

from arena_rclpy_mixins.registry import ClassRegistry
from rclpy.action.server import ServerGoalHandle
from rclpy.clock import Clock
from rclpy.task import Future

from arena_robots.task_kinds import TaskKind

if TYPE_CHECKING:
    from arena_robots.bringup import Bringup


GoalT = TypeVar("GoalT")
FeedbackT = TypeVar("FeedbackT")
ResultT = TypeVar("ResultT")


class TaskHandler(Protocol[GoalT, FeedbackT, ResultT]):
    def __init__(self, bringup: Bringup, *, tf_buffer: object, node: object) -> None: ...

    async def execute(self, goal_handle: ServerGoalHandle) -> ResultT: ...


HANDLERS: ClassRegistry[tuple[TaskKind, str], type[TaskHandler]] = ClassRegistry()


async def _executor_sleep(node: object, seconds: float, *, wall: bool = False) -> None:
    """Timer-backed sleep that yields to rclpy's executor. Works inside action
    server callbacks (which run under rclpy.spin, not asyncio).

    ``wall=True`` uses a wall-clock timer so the sleep still ticks while sim
    time is paused — use it for readiness/discovery polling, not for retry
    rate-limiting where sim-time semantics are preferred.
    """
    fut: Future = Future()

    def _fire():
        if not fut.done():
            fut.set_result(None)

    timer = node.create_timer(seconds, _fire, clock=Clock() if wall else None)
    try:
        await fut
    finally:
        node.destroy_timer(timer)


from . import goto_pose  # noqa: E402,F401
