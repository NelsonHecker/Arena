import asyncio

from collections.abc import Sequence

import rosgraph_msgs.msg

from task_generator.shared import Entity, Wall
from task_generator.simulators.sim import BaseSim
import typing

T = typing.TypeVar('T')


class DummySimulator(BaseSim):
    """
    Does nothing.
    """

    _clock_task: asyncio.Task

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self._clock_publisher = self.node.create_publisher(
            rosgraph_msgs.msg.Clock, '/clock', 10
        )
        self._clock_task = asyncio.create_task(self._publish_clock_loop())

    async def _publish_clock_loop(self):
        """Publish simulated clock at ~100Hz using wall time."""
        start = self.node.wall_time
        try:
            while True:
                elapsed = self.node.wall_time - start
                self._clock_publisher.publish(elapsed.to_rosgraph_msg())
                await asyncio.sleep(0.01)
        except asyncio.CancelledError:
            pass

    async def before_reset_task(self):
        self._logger.debug("pausing")
        return True

    async def after_reset_task(self):
        self._logger.debug("unpausing")
        return True

    # fake spawn
    @staticmethod
    async def _wrap_future(v: T) -> T:
        return v

    async def __spawn_entity(self, entities: Sequence[Entity]) -> Sequence[bool]:
        self._logger.debug(f"spawning {len(entities)} entities")

        await asyncio.gather(*(
            self.safe_resolve(e.model)
            for e
            in entities)
        )
        return tuple(True for _ in entities)

    async def obstacle_spawn(self, obstacles):
        return await self.__spawn_entity(obstacles)

    async def pedestrian_spawn(self, pedestrians):
        return await self.__spawn_entity(pedestrians)

    async def robot_spawn(self, robots):
        return await self.__spawn_entity(robots)

    # fake move
    def __move_entity(self, entities: Sequence[Entity]) -> Sequence[bool]:
        self._logger.debug(f"moving {len(entities)} entities")
        return tuple(True for _ in entities)

    async def obstacle_move(self, obstacles):
        return self.__move_entity(obstacles)

    async def pedestrian_move(self, pedestrians):
        return self.__move_entity(pedestrians)

    async def robot_move(self, robots):
        return self.__move_entity(robots)

    # fake delete
    def __delete_entity(self, entities: Sequence[Entity]) -> Sequence[bool]:
        self._logger.debug(f"deleting {len(entities)} entities")
        return tuple(True for _ in entities)

    async def obstacle_delete(self, obstacles):
        return self.__delete_entity(obstacles)

    async def pedestrian_delete(self, pedestrians):
        return self.__delete_entity(pedestrians)

    async def robot_delete(self, robots):
        return self.__delete_entity(robots)

    # assorted
    async def pedestrian_update(self, pedestrians):
        self._logger.debug(f'updating {len(pedestrians.pedestrians)} pedestrians')
        return tuple(True for _ in pedestrians.pedestrians)

    # world interface
    async def spawn_walls(self, walls):
        self._logger.debug(f'spawning {len(walls)} walls')

        async def resolve(wall: Wall):
            walls, obs = await wall.assets()
            await asyncio.gather(
                self.__spawn_entity(tuple(obs)),
                *(self.safe_resolve(wall.material) for wall in walls),
            )

        await asyncio.gather(*map(resolve, walls))
        return True

    async def spawn_floors(self, floors):
        self._logger.debug(f'spawning {len(floors)} floors')
        await asyncio.gather(*(self.safe_resolve(floor.material) for floor in floors))
        return True

    async def spawn_doors(self, doors):
        self._logger.debug(f'spawning {len(doors)} doors')
        await asyncio.gather(*(self.safe_resolve(door.material) for door in doors))
        return True

    async def spawn_elevators(self, elevators) -> bool:
        self._logger.debug(f'spawning {len(elevators)} elevators')
        await asyncio.gather(*(self.safe_resolve(elevator.material) for elevator in elevators))
        return True

    async def remove_world(self):
        self._logger.debug('removing all walls and doors')
        return True
