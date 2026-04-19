import asyncio
import typing
from collections.abc import Callable, Collection, Sequence
from typing import Any

from arena_simulation_setup.tree.World import WorldDescription

from task_generator import NodeInterface
from task_generator.manager.realizer import Realizer
from task_generator.shared import (
    DynamicObstacle,
    Obstacle,
    Robot,
)
from task_generator.simulators.human import BaseHumanSimulator
from task_generator.simulators.human.utils import ObstacleLayer
from task_generator.simulators.sim import BaseSim


class EnvironmentManager(NodeInterface):
    _human_simulator: BaseHumanSimulator
    _simulator: BaseSim
    _realizer: Realizer

    def __init__(
        self,
        *args: object,
        simulator: BaseSim,
        human_simulator: BaseHumanSimulator,
        realizer: Realizer,
        **kwargs: object,
    ):
        super().__init__(*args, **kwargs)

        self._simulator = simulator
        self._human_simulator = human_simulator
        self._realizer = realizer

    def realize(self, target: object) -> object:
        return self._realizer.realize(target)

    async def spawn_world_obstacles(self, world: WorldDescription):
        """
        Loads given obstacles into the simulator,
        the map file is retrieved from launch parameter "world"
        """

        futures: list[typing.Awaitable] = []

        walls = tuple(world.all_walls)
        doors = tuple(world.all_doors)
        floors = tuple(world.all_floors)
        elevators = tuple(world.all_elevators)
        if floors:
            futures.append(self._simulator.spawn_floors(tuple(map(self.realize, floors))))

        if walls or doors:
            futures.append(
                self._human_simulator.spawn_world(
                    tuple(map(self.realize, walls)),
                    tuple(map(self.realize, doors)),
                )
            )

        futures.append(
            self._human_simulator.spawn_obstacles(
                tuple(map(self.realize, world.all_static_entities)),
                layer=ObstacleLayer.WORLD,
            )
        )
        if elevators:
            self._logger.debug(f"Realized elevators for world: {[e.name for e in elevators]}")
            futures.append(self._simulator.spawn_elevators(tuple(map(self.realize, elevators))))

        await asyncio.gather(*futures)

    async def spawn_dynamic_obstacles(self, setups: Collection[DynamicObstacle]):
        """
        Loads given dynamic obstacles into the simulator.
        """

        await self._human_simulator.spawn_dynamic_obstacles(tuple(map(self.realize, setups)))

    async def spawn_obstacles(self, setups: Collection[Obstacle]):
        """
        Loads given obstacles into the simulator.
        """

        await self._human_simulator.spawn_obstacles(tuple(map(self.realize, setups)))

    async def spawn_robot(self, robots: Sequence[Robot]) -> Sequence[Robot]:
        """
        Loads given robot into the simulator
        """
        await self._human_simulator.spawn_robot(robots=tuple(map(self.realize, robots)))
        return robots

    async def move_robot(self, robots: Sequence[Robot]) -> Sequence[bool]:
        """
        Moves given robot
        """
        return await self._human_simulator.move_robot(tuple(map(self.realize, robots)))

    async def remove_robot(self, robots: Sequence[Robot]) -> Sequence[bool]:
        """
        Deletes given robot
        """
        return await self._human_simulator.remove_robot(tuple(map(self.realize, robots)))

    async def respawn(self, callback: Callable[[], typing.Awaitable[Any]]):
        """
        Unuse obstacles, (re-)use them in callback, finally remove unused obstacles
        @callback: Function to call between unuse and remove
        """
        await self._human_simulator.unuse_obstacles()
        await callback()
        await self._human_simulator.remove_obstacles(purge=ObstacleLayer.UNUSED)

    async def reset(self, purge: ObstacleLayer = ObstacleLayer.INUSE):
        """
        Unuse and remove all obstacles
        """
        await self._human_simulator.remove_obstacles(purge=purge)

    async def step(self, n: int = 1) -> bool:
        return await self._simulator.step(n)

    async def before_reset_task(self) -> bool:
        return await self._simulator.before_reset_task()

    async def after_reset_task(self) -> bool:
        return await self._simulator.after_reset_task()
