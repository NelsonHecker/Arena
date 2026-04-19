"""arena_robots.clients — action client abstractions for all TaskKinds.

Two surfaces, one shared state machine:
- Awaitable: ``send_goal`` + ``await_result`` — suited for notebooks and
  remote tooling where the caller can simply await the full round-trip.
- Polling: ``is_done`` / ``status`` / ``feedback`` — suited for
  task_generator's tick-based loop that cannot block awaiting a future.

Both surfaces operate on the same in-flight goal; mixing them is safe.
"""

from __future__ import annotations

from abc import ABC, abstractmethod
from typing import TYPE_CHECKING, ClassVar

if TYPE_CHECKING:
    import rclpy.node
    import tf2_ros

    from arena_robots.Robot import RobotView

from arena_robots.task_kinds import TaskKind, PUBLIC_SUFFIX


class Client(ABC):
    task_kind: ClassVar[TaskKind]

    def __init__(
        self,
        robot: "RobotView",
        namespace: str,
        *,
        node: "rclpy.node.Node",
        tf_buffer: "tf2_ros.Buffer",
    ) -> None:
        self.robot = robot
        self.namespace = namespace
        self.node = node
        self.tf_buffer = tf_buffer

    @abstractmethod
    def action_endpoint(self) -> str:
        ...

    @abstractmethod
    async def wait_ready(self) -> None:
        ...

    @abstractmethod
    async def send_goal(self, goal) -> "object":
        """Send goal; return once accepted by the server (returns GoalHandle)."""
        ...

    @abstractmethod
    async def await_result(self) -> object:
        ...

    @abstractmethod
    def is_done(self) -> bool | None:
        ...

    def cancel(self) -> None:
        raise NotImplementedError

    @property
    def status(self) -> int | None:
        return None

    @property
    def feedback(self):
        return None


_CLIENTS: dict[TaskKind, type[Client]] = {}


def register_client(cls: type[Client]) -> type[Client]:
    _CLIENTS[cls.task_kind] = cls
    return cls


def get_client(task_kind: TaskKind) -> type[Client]:
    if task_kind not in _CLIENTS:
        raise KeyError(
            f"No client registered for task_kind {task_kind!r}; available: {list(_CLIENTS)}"
        )
    return _CLIENTS[task_kind]


from . import goto_pose  # noqa: F401
