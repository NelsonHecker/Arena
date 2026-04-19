from collections.abc import Sequence

from task_generator.shared import Door, DynamicObstacle, Obstacle, Robot, Wall
from task_generator.simulators.human import BaseHumanSimulator


class DummyHumanSimulator(BaseHumanSimulator):
    async def _spawn_obstacles_impl(
        self,
        obstacles: Sequence[Obstacle],
    ) -> Sequence[Obstacle | None]:
        return obstacles

    async def _spawn_dynamic_obstacles_impl(
        self,
        obstacles: Sequence[DynamicObstacle],
    ) -> Sequence[DynamicObstacle | None]:
        return obstacles

    async def _remove_obstacles_impl(
        self,
    ) -> bool:
        return True

    async def _spawn_walls_impl(
        self,
        walls: Sequence[Wall],
    ) -> bool:
        return True

    async def _spawn_doors_impl(
        self,
        doors: Sequence[Door],
    ) -> bool:
        return True

    async def _spawn_robot_impl(
        self,
        robots: Sequence[Robot],
    ) -> Sequence[bool]:
        return (True,) * len(robots)

    async def _remove_robot_impl(
        self,
        robots: Sequence[Robot],
    ) -> Sequence[bool]:
        return (True,) * len(robots)

    async def _move_robot_impl(
        self,
        robots: Sequence[Robot],
    ) -> Sequence[bool]:
        return (True,) * len(robots)
