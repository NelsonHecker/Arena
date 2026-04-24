"""Robot navigation-stack adapters."""

from __future__ import annotations

import enum
from abc import ABC, abstractmethod
from dataclasses import dataclass
from typing import TYPE_CHECKING, Any, ClassVar

from arena_robots.Sensor import SensorSpec, SensorType, SensorTypeOrStr
from launch.actions import GroupAction

if TYPE_CHECKING:
    from arena_rclpy_mixins.shared import Namespace
    from arena_robots.bringup import Bringup
    from arena_robots.clients import Client

    from task_generator.manager.robot_manager.robot_manager import RobotManager
    from task_generator.shared import Pose
    from task_generator.tasks.robots.request import TaskPhase


class ActuatorCap(enum.StrEnum):
    """Canonical actuator-capability vocabulary."""

    MOBILE = "mobile"
    DRONE = "drone"
    MANIPULATOR = "manipulator"


type Cap = ActuatorCap | str


@dataclass(frozen=True)
class AdapterCtx:
    """Immutable config-time snapshot handed to an adapter."""

    namespace: Namespace
    robot_name: str
    frame: str
    task_generator_node: str
    use_sim_time: bool
    base_frame: str
    odom_frame: str
    sensors: list[SensorSpec]
    tf_buffer: Any
    node_handle: Any


class Adapter(ABC):
    """Abstract base class for robot navstack adapters."""

    kind: ClassVar[str]
    accepts: ClassVar[frozenset]
    bringup_cls: ClassVar[type[Bringup]]
    client_cls: ClassVar[type[Client]]

    republishes_goal: ClassVar[bool] = True

    def __init__(self, robot_manager: RobotManager, **bringup_kwargs: object) -> None:
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

    def launch_description(self, ctx: AdapterCtx) -> GroupAction:
        return GroupAction(
            [
                *self.bringup._launch_actions(
                    use_sim_time=ctx.use_sim_time,
                    frame=ctx.frame,
                    task_generator_node=ctx.task_generator_node,
                    **self._bringup_kwargs,
                ),
                self.bringup._task_server_node(use_sim_time=ctx.use_sim_time),
            ]
        )

    async def wait_until_ready(
        self,
        robot: RobotManager,
        node_paths: set[str],
    ) -> None:
        await self.client.wait_ready()

    @abstractmethod
    async def dispatch_phase(
        self,
        phase: TaskPhase,
        robot: RobotManager,
    ) -> None: ...

    def is_phase_done(
        self,
        phase: TaskPhase,
        robot: RobotManager,
    ) -> bool | None:
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
        pose: Pose,
        robot: RobotManager,
    ) -> None:
        return None


from arena_rclpy_mixins.registry import ClassRegistry

ADAPTERS: ClassRegistry[str, type[Adapter]] = ClassRegistry()


@ADAPTERS.register("nav2")
def _load_nav2() -> type[Adapter]:
    from .nav2 import Nav2Adapter

    return Nav2Adapter


@ADAPTERS.register("test-collision")
def _load_test_collision() -> type[Adapter]:
    from .test_collision import TestCollisionAdapter

    return TestCollisionAdapter


@ADAPTERS.register("none")
def _load_none() -> type[Adapter]:
    from .none import NoneAdapter

    return NoneAdapter


@ADAPTERS.register("external")
def _load_external() -> type[Adapter]:
    from .external import ExternalAdapter

    return ExternalAdapter


__all__ = [
    "ActuatorCap",
    "Cap",
    "SensorType",
    "SensorTypeOrStr",
    "SensorSpec",
    "AdapterCtx",
    "Adapter",
    "ADAPTERS",
]
