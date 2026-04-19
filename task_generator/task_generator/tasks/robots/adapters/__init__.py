"""Robot navigation-stack adapters."""

from __future__ import annotations

import enum
from abc import ABC, abstractmethod
from dataclasses import dataclass
from typing import TYPE_CHECKING, Any, ClassVar, Optional, Type

import attrs
from arena_robots.Sensor import SensorSpec, SensorType, SensorTypeOrStr
from launch.actions import GroupAction

if TYPE_CHECKING:
    from arena_rclpy_mixins.shared import Namespace

    from arena_robots.bringup import Bringup
    from arena_robots.clients import Client
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
    accepts: ClassVar[frozenset]
    bringup_cls: ClassVar[Type["Bringup"]]
    client_cls: ClassVar[Type["Client"]]

    republishes_goal: ClassVar[bool] = True

    def __init__(self, robot_manager: "RobotManager", **bringup_kwargs):
        self.rm = robot_manager
        self._bringup_kwargs = bringup_kwargs
        self.bringup = self.bringup_cls(
            robot_manager.robot_view,
            str(robot_manager.namespace),
        )
        self.client = self.client_cls(
            robot_manager.robot_view,
            str(robot_manager.namespace),
            node=robot_manager.node,
            tf_buffer=robot_manager.tf_buffer,
        )

    @property
    def requires(self) -> frozenset[str]:
        return self.bringup.requires

    def launch_description(self, ctx: AdapterCtx):
        return GroupAction([
            *self.bringup._launch_actions(
                use_sim_time=ctx.use_sim_time,
                frame=ctx.frame,
                task_generator_node=ctx.task_generator_node,
                **self._bringup_kwargs,
            ),
            self.bringup._task_server_node(use_sim_time=ctx.use_sim_time),
        ])

    async def wait_until_ready(
        self,
        robot: "RobotManager",
        node_paths: set[str],
    ) -> None:
        await self.client.wait_ready()

    @abstractmethod
    async def dispatch_phase(
        self,
        phase: "TaskPhase",
        robot: "RobotManager",
    ) -> None: ...

    def is_phase_done(
        self,
        phase: "TaskPhase",
        robot: "RobotManager",
    ) -> Optional[bool]:
        done = self.client.is_done()
        if done is None or not done:
            return done
        return self.client.status == 0

    def on_episode_start(self) -> None:
        return None

    def on_episode_end(self) -> None:
        self.client.cancel()

    async def on_move(
        self,
        pose: "Pose",
        robot: "RobotManager",
    ) -> None:
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
