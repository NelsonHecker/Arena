"""Robot navigation-stack adapters."""

from __future__ import annotations

import enum
from abc import ABC, abstractmethod
from dataclasses import dataclass
from typing import TYPE_CHECKING, Any, Callable, ClassVar, Optional, Type

import attrs
from arena_robots.Sensor import SensorSpec, SensorType, SensorTypeOrStr

if TYPE_CHECKING:
    from arena_rclpy_mixins.shared import Namespace

    from task_generator.manager.robot_manager.robot_manager import RobotManager
    from task_generator.shared import Pose
    from task_generator.tasks.robots.request import TaskKind, TaskPhase


class ActuatorCap(enum.StrEnum):
    """Canonical actuator-capability vocabulary."""

    MOBILE = "mobile"
    DRONE = "drone"
    MANIPULATOR = "manipulator"


type Cap = ActuatorCap | str


@dataclass(frozen=True)
class AdapterCtx:
    """Immutable config-time snapshot handed to an adapter."""

    namespace: "Namespace"
    robot_name: str
    frame: str
    task_generator_node: str
    use_sim_time: bool
    base_frame: str
    odom_frame: str
    sensors: list["SensorSpec"]
    tf_buffer: Any
    node_handle: Any


class Adapter(ABC):
    """Abstract base class for robot navstack adapters."""

    kind: ClassVar[str]
    requires: ClassVar[frozenset[str]]
    accepts: ClassVar[frozenset]

    # True: adapter relies on RobotManager._publish_goal_loop to keep
    # republishing the goal_pose topic against AMCL jitter. False: adapter
    # owns goal transport (e.g. action client) and the republish loop must
    # not run — otherwise it races the adapter's dispatch.
    republishes_goal: ClassVar[bool] = True

    @abstractmethod
    def launch_description(self, ctx: AdapterCtx):
        """Build the launch description that brings up this adapter."""

    def on_episode_start(self) -> None:
        return None

    def on_episode_end(self) -> None:
        return None

    async def on_move(
        self,
        pose: "Pose",
        robot: "RobotManager",
    ) -> None:
        """Called after the robot has been teleported. Default no-op."""
        return None

    async def wait_until_ready(
        self,
        robot: "RobotManager",
        node_paths: set[str],
    ) -> None:
        """Block until the adapter's nodes are discoverable. Default no-op."""
        return None

    async def dispatch_phase(
        self,
        phase: "TaskPhase",
        robot: "RobotManager",
    ) -> None:
        raise NotImplementedError(
            f"{type(self).__name__} does not implement dispatch_phase; "
            f"accepts={sorted(getattr(self, 'accepts', frozenset()))}"
        )

    def is_phase_done(
        self,
        phase: "TaskPhase",
        robot: "RobotManager",
    ) -> Optional[bool]:
        """Tier-2 completion check; return None to defer to the phase default."""
        return None


_ADAPTERS: dict[str, Type[Adapter]] = {}


def register_adapter(cls: Type[Adapter]) -> Type[Adapter]:
    """Register an :class:`Adapter` subclass under its :attr:`kind`."""
    kind = getattr(cls, "kind", None)
    if not isinstance(kind, str) or not kind:
        raise TypeError(
            f"{cls.__name__} must declare a non-empty string 'kind' "
            "ClassVar before registration"
        )
    if kind in _ADAPTERS and _ADAPTERS[kind] is not cls:
        raise ValueError(
            f"adapter kind {kind!r} already registered to "
            f"{_ADAPTERS[kind].__name__}; cannot re-register to "
            f"{cls.__name__}"
        )
    _ADAPTERS[kind] = cls
    return cls


def get_adapter(kind: str) -> Type[Adapter]:
    """Look up an adapter class by its :attr:`kind` string."""
    try:
        return _ADAPTERS[kind]
    except KeyError:
        known = sorted(_ADAPTERS.keys())
        raise KeyError(
            f"no adapter registered for kind {kind!r}; known: {known}"
        ) from None


__all__ = [
    "ActuatorCap",
    "Cap",
    "SensorType",
    "SensorTypeOrStr",
    "SensorSpec",
    "AdapterCtx",
    "Adapter",
    "register_adapter",
    "get_adapter",
]
