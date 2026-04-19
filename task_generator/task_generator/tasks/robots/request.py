"""Typed task requests submitted to robots."""

from __future__ import annotations

import math
from abc import ABC, abstractmethod
from collections.abc import Callable
from typing import TYPE_CHECKING, ClassVar

import attrs
from arena_robots.task_kinds import TaskKind

from task_generator.shared import Pose

if TYPE_CHECKING:
    from task_generator.manager.robot_manager.robot_manager import RobotManager


class TaskPhase(ABC):
    """One typed step within a :class:`TaskRequest`."""

    kind: ClassVar[TaskKind]

    @abstractmethod
    def is_satisfied(self, robot_manager: RobotManager) -> bool:
        """Tier-3 default completion check; must not raise when pose is unavailable."""


@attrs.define
class GoToPhase(TaskPhase):
    """Navigate-to-pose phase with optional per-phase tolerance overrides."""

    kind: ClassVar[TaskKind] = TaskKind.GOTO_POSE

    pose: Pose
    tolerance_radius: float | None = None
    tolerance_angle: float | None = None

    def is_satisfied(self, robot_manager: RobotManager) -> bool:
        pose = robot_manager.pose
        if pose is None:
            return False

        tol_dist = (
            self.tolerance_radius if self.tolerance_radius is not None else robot_manager._goal_tolerance_distance  # noqa: SLF001
        )
        tol_ang = (
            self.tolerance_angle if self.tolerance_angle is not None else robot_manager._goal_tolerance_angle  # noqa: SLF001
        )

        dx = pose.position.x - self.pose.position.x
        dy = pose.position.y - self.pose.position.y
        if math.hypot(dx, dy) > tol_dist:
            return False

        if tol_ang > 0:
            dyaw = pose.orientation.to_yaw() - self.pose.orientation.to_yaw()
            dyaw = (dyaw + math.pi) % (2 * math.pi) - math.pi
            if abs(dyaw) > tol_ang:
                return False

        return True


DonePredicate = Callable[
    ["RobotManager", TaskPhase],
    bool | None,
]


@attrs.define
class TaskRequest:
    """Typed sequence of phases submitted to a robot."""

    phases: list[TaskPhase]
    done_predicate: DonePredicate | None = None

    @property
    def kind(self) -> TaskKind | None:
        """Single homogeneous kind of all phases, or None if mixed/empty."""
        if not self.phases:
            return None
        first = self.phases[0].kind
        for phase in self.phases[1:]:
            if phase.kind is not first:
                return None
        return first


__all__ = [
    "TaskKind",
    "TaskPhase",
    "GoToPhase",
    "TaskRequest",
    "DonePredicate",
]
