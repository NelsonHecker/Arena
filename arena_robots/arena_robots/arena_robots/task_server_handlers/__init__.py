"""Registry of per-(TaskKind, bringup_kind) action-server handlers.

Handlers are registered via zero-arg loader functions so their modules — and
any non-core msgs deps (e.g. ``nav2_msgs``) — are imported only when that
particular ``(task_kind, bringup_kind)`` pair is actually requested.
"""

from __future__ import annotations

from collections.abc import Callable, KeysView
from typing import (
    TYPE_CHECKING,
    Protocol,
    TypeVar,
)

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


K = TypeVar("K")
V = TypeVar("V")


class HandlerRegistry[K, V]:
    def __init__(self) -> None:
        self._loaders: dict[K, Callable[[], V]] = {}
        self._cache: dict[K, V] = {}

    def register(self, key: K) -> Callable[[Callable[[], V]], Callable[[], V]]:
        def _dec(loader: Callable[[], V]) -> Callable[[], V]:
            if key in self._loaders:
                raise ValueError(f"registry key {key!r} already registered")
            self._loaders[key] = loader
            return loader

        return _dec

    def get(self, key: K) -> V:
        if key not in self._cache:
            try:
                loader = self._loaders[key]
            except KeyError:
                raise KeyError(f"no entry for {key!r}; known: {sorted(self._loaders)!r}") from None
            self._cache[key] = loader()
        return self._cache[key]

    def keys(self) -> KeysView[K]:
        return self._loaders.keys()


HANDLERS: HandlerRegistry[tuple[TaskKind, str], type[TaskHandler]] = HandlerRegistry()


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
