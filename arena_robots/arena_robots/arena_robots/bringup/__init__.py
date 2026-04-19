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

    def __init__(self, robot: "RobotView", namespace: str) -> None:
        self.robot = robot
        self.namespace = Namespace(namespace)

    @abstractmethod
    def _launch_actions(
        self,
        *,
        use_sim_time: bool = True,
        frame: str = "",
        **launch_args,
    ) -> list[Action]:
        ...

    def _task_server_node(self, *, use_sim_time: bool = True) -> Node:
        return Node(
            package="arena_robots",
            executable="task_server",
            namespace=self.namespace,
            parameters=[{
                "robot_name": self.robot.name,
                "bringup_kind": self.kind,
                "use_sim_time": use_sim_time,
            }],
        )

    def launch_description(
        self,
        *,
        use_sim_time: bool = True,
        frame: str = "",
        **launch_args,
    ) -> LaunchDescription:
        return LaunchDescription([
            *self._launch_actions(use_sim_time=use_sim_time, frame=frame, **launch_args),
            self._task_server_node(use_sim_time=use_sim_time),
        ])

    @property
    def accepts_task_kinds(self) -> "frozenset":
        from arena_robots.task_server_handlers import HANDLERS
        return frozenset(tk for (tk, k) in HANDLERS.keys() if k == self.kind)


_BRINGUPS: dict[str, type[Bringup]] = {}


def register_bringup(cls: type[Bringup]) -> type[Bringup]:
    _BRINGUPS[cls.kind] = cls
    return cls


def get_bringup(kind: str) -> type[Bringup]:
    if kind not in _BRINGUPS:
        raise KeyError(f"No bringup registered for kind {kind!r}; available: {sorted(_BRINGUPS)}")
    return _BRINGUPS[kind]


def check_caps(bringup: Bringup) -> None:
    available = bringup.robot.caps.available
    missing = bringup.requires - available
    if missing:
        raise AdapterCapMismatch(
            f"Bringup {bringup.kind!r} requires caps {sorted(missing)} "
            f"but robot {bringup.robot.name!r} only advertises {sorted(available)}"
        )


from . import nav2, none, external  # noqa: F401
