from __future__ import annotations

from abc import ABC, abstractmethod
from typing import TYPE_CHECKING, ClassVar

if TYPE_CHECKING:
    from arena_robots.Robot import RobotView

from arena_rclpy_mixins.shared import Namespace
from launch import Action, LaunchDescription
from launch_ros.actions import Node


class AdapterCapMismatch(RuntimeError):
    pass


class Bringup(ABC):
    kind: ClassVar[str]
    requires: ClassVar[frozenset[str]]

    def __init__(self, robot: RobotView, namespace: str) -> None:
        self.robot = robot
        self.namespace = Namespace(namespace)

    @abstractmethod
    def _launch_actions(
        self,
        *,
        use_sim_time: bool = True,
        frame: str = "",
        **launch_args: object,
    ) -> list[Action]: ...

    def _task_server_node(self, *, use_sim_time: bool = True) -> Node:
        return Node(
            package="arena_robots",
            executable="task_server",
            namespace=self.namespace,
            parameters=[
                {
                    "robot_name": self.robot.name,
                    "bringup_kind": self.kind,
                    "use_sim_time": use_sim_time,
                }
            ],
        )

    def launch_description(
        self,
        *,
        use_sim_time: bool = True,
        frame: str = "",
        **launch_args: object,
    ) -> LaunchDescription:
        return LaunchDescription(
            [
                *self._launch_actions(use_sim_time=use_sim_time, frame=frame, **launch_args),
                self._task_server_node(use_sim_time=use_sim_time),
            ]
        )

    @property
    def accepts_task_kinds(self) -> frozenset:
        from arena_robots.task_server_handlers import HANDLERS

        return frozenset(tk for (tk, k) in HANDLERS.keys() if k == self.kind)


def check_caps(bringup: Bringup) -> None:
    available = bringup.robot.caps.available
    missing = bringup.requires - available
    if missing:
        raise AdapterCapMismatch(f"Bringup {bringup.kind!r} requires caps {sorted(missing)} but robot {bringup.robot.name!r} only advertises {sorted(available)}")


from arena_rclpy_mixins.registry import ClassRegistry

BRINGUPS: ClassRegistry[str, type[Bringup]] = ClassRegistry()


@BRINGUPS.register("nav2")
def _load_nav2() -> type[Bringup]:
    from .nav2 import Nav2Bringup

    return Nav2Bringup


@BRINGUPS.register("test-collision")
def _load_test_collision() -> type[Bringup]:
    from .test_collision import TestCollisionBringup

    return TestCollisionBringup


@BRINGUPS.register("none")
def _load_none() -> type[Bringup]:
    from .none import NoneBringup

    return NoneBringup


@BRINGUPS.register("external")
def _load_external() -> type[Bringup]:
    from .external import ExternalBringup

    return ExternalBringup
