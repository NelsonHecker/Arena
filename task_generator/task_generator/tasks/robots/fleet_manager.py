"""FleetManager — matches TaskModeSpec entries to RobotManager instances at reset."""

from __future__ import annotations

import typing
from typing import TYPE_CHECKING, Iterable

import attrs

from task_generator.tasks.robots.request import TaskKind

if TYPE_CHECKING:
    from task_generator.manager.robot_manager.robot_manager import RobotManager


@attrs.define
class TaskModeSpec:
    """A single entry in the episode-level task_modes list."""

    kind: str
    produces: TaskKind = TaskKind.GOTO_POSE
    assignments: list[str] = attrs.field(factory=list)
    config: dict = attrs.field(factory=dict)


class FleetManager:
    """Greedy allocator pairing TM specs to robot managers."""

    @staticmethod
    def match(
        task_modes: list[TaskModeSpec],
        robots: Iterable["RobotManager"],
    ) -> dict[TaskModeSpec, list["RobotManager"]]:
        """Allocate each RobotManager to exactly one TM spec."""
        robots_list: list["RobotManager"] = list(robots)
        by_name: dict[str, "RobotManager"] = {r.name: r for r in robots_list}

        allocation: dict[TaskModeSpec, list["RobotManager"]] = {
            spec: [] for spec in task_modes
        }
        used: set[str] = set()

        for spec in task_modes:
            for name in spec.assignments:
                if name not in by_name:
                    raise KeyError(
                        f"task_mode {spec.kind!r} pins robot {name!r} "
                        f"but no such robot exists; known: "
                        f"{sorted(by_name.keys())}"
                    )
                if name in used:
                    raise AssertionError(
                        f"robot {name!r} is pinned to multiple task_modes"
                    )
                robot = by_name[name]
                if spec.produces not in robot.accepts:
                    raise AssertionError(
                        f"task_mode {spec.kind!r} requires task kind "
                        f"{spec.produces!r} but robot "
                        f"{name!r} accepts only "
                        f"{sorted(k.name for k in robot.accepts)}"
                    )
                allocation[spec].append(robot)
                used.add(name)

        unpinned_specs = [spec for spec in task_modes if not spec.assignments]
        for robot in robots_list:
            if robot.name in used:
                continue
            for spec in unpinned_specs:
                if spec.produces in robot.accepts:
                    allocation[spec].append(robot)
                    used.add(robot.name)
                    break

        null_spec: typing.Optional[TaskModeSpec] = next(
            (spec for spec in task_modes if spec.kind == "null"),
            None,
        )
        if null_spec is not None:
            for robot in robots_list:
                if robot.name in used:
                    continue
                allocation[null_spec].append(robot)
                used.add(robot.name)

        return allocation


__all__ = ["TaskModeSpec", "FleetManager"]
