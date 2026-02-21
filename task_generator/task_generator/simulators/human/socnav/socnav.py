#!/usr/bin/env python3
"""
SocNav Human Simulator for Arena
Uses Pre recorded Trajectory Data
"""

import asyncio
from collections.abc import Collection
from typing import Sequence

from arena_people_msgs.msg import Pedestrians
from arena_rclpy_mixins.Time import Time
from arena_simulation_setup.tree.World import WorldIdentifier

# Arena imports
from task_generator.shared import DynamicObstacle
from task_generator.simulators.human.dummy import DummyHumanSimulator

from . import SocnavPedestrian
from .trajectory_loader import SocnavPlayer


class SocNavHumanSimulator(DummyHumanSimulator):
    """Minimal SocNav Human Simulator - Starting Point"""

    def __init__(
        self,
        *args,
        **kwargs,
    ):
        super().__init__(*args, **kwargs)
        self._playing: bool = False
        self._pedestrians: Pedestrians = Pedestrians()
        self._last_time = Time()
        self._player: SocnavPlayer | None = None
        self._update_loop_task = asyncio.create_task(self._update_loop())

    async def _update_loop(self):
        while True:
            try:
                if not self._player:
                    await asyncio.sleep(0.1)
                    continue
                await asyncio.sleep(1 / self._player._fps)
                if self._playing:
                    now = self.node.sim_time
                    dt = (now - self._last_time).to_seconds()
                    self._last_time = now

                    to_spawn: Collection[DynamicObstacle] = []
                    to_delete: Collection[DynamicObstacle] = []

                    for (step_spawn, step_delete) in self._player.step(dt):
                        to_spawn.extend(step_spawn)
                        to_delete.extend(step_delete)

                    if to_spawn:
                        self._logger.debug(f'spawning {[ped.name for ped in to_spawn]}')

                    await self._simulator.pedestrian_spawn(to_spawn)
                    await self._simulator.pedestrian_update(self._player.pedestrians)
                    await self._simulator.pedestrian_delete(to_delete)
                self._publish_peds(self._player.pedestrians)
            except Exception as e:
                import traceback
                self._logger.error(f'Exception in update loop: {e}')
                self._logger.error(traceback.format_exc())
                await asyncio.sleep(1)

    @property
    async def _csv_dataset(self) -> SocnavPlayer:
        world_path = await WorldIdentifier(self.node.conf.Arena.WORLD.value).resolve_path()
        dataset_name = self.node.rosparam[str].get('dataset', 'default')
        dataset_path = world_path / 'socnav' / f'{dataset_name}.csv'
        if not dataset_path.is_file():
            raise FileNotFoundError(f"Dataset file not found: {dataset_path}")
        return SocnavPlayer.from_csv(dataset_path)

    def _play(self, player: SocnavPlayer):
        self._last_time = self.node.sim_time
        self._player = player
        self._playing = True

    async def spawn_dynamic_obstacles(self, obstacles: Sequence[DynamicObstacle]):
        instanceable: list[SocnavPedestrian] = [obstacle for obstacle in obstacles if isinstance(obstacle, SocnavPedestrian)]

        # TODO define custom task modes based on humansim
        if instanceable:
            self._play(SocnavPlayer(instanceable))
        else:
            try:
                self._play(await self._csv_dataset)
                self._logger.warning('playing dataset')
            except Exception as e:
                self._logger.error(f'{e}')
