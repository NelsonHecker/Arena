#!/usr/bin/env python3
"""
Simple SocNav Trajectory Loader - Minimal CSV reader
"""
from __future__ import annotations

import csv
import itertools
import logging
import typing
from collections.abc import Collection
from functools import cached_property
from pathlib import Path

from arena_people_msgs.msg import Pedestrian, Pedestrians
from arena_simulation_setup.shared import DynamicObstacle, Pose, Position
from arena_simulation_setup.utils.geometry import Vector3
from typing_extensions import Self

from . import SocnavPedestrian


class SocnavPlayer:
    def __init__(
        self,
        data: Collection[SocnavPedestrian],
        *,
        time: float = 0,
        prespawn: bool = False,
        despawn: bool = True,
        fps: float = 25,
    ):
        self._fps = fps
        self._data = data
        self._time = time
        self._frame = self._time_to_frame(self._time)
        self._id_iter = itertools.count()
        self._logger = logging.getLogger('SocnavPlayer')

        self._pedestrians: dict[str, Pedestrian] = {}
        if prespawn:
            for ped in self._data:
                ped_msg = Pedestrian()
                ped_msg.pose = ped.pose
                self._pedestrians[ped.name] = ped_msg

        self._despawn = despawn

    def _time_to_frame(self, time: float) -> int:
        return int(time * self._fps)

    @cached_property
    def max_frame(self) -> int:
        return max(ped.last_frame for ped in self._data)

    @property
    def time(self) -> float:
        return self._time

    @time.setter
    def time(self, value: float) -> None:
        self._time = value
        self._frame = self._time_to_frame(self._time)

    @property
    def pedestrians(self) -> Pedestrians:
        return Pedestrians(pedestrians=list(self._pedestrians.values()))

    def get_frame(self, frame: int) -> dict[str, Position]:
        peds: dict[str, Position] = {}
        for ped in self._data:
            if ped.spawn_at <= frame <= ped.last_frame - 1:
                peds[ped.name] = ped.waypoints[frame - ped.spawn_at]
        return peds

    def step(self, dt: float) -> typing.Generator[tuple[Collection[DynamicObstacle], Collection[DynamicObstacle]], None, int | None]:
        self._time += dt
        new_frame = self._time_to_frame(self._time)
        if new_frame <= self._frame:
            return

        for frame in range(self._frame + 1, new_frame + 1):
            to_spawn: list[DynamicObstacle] = []
            to_delete: list[DynamicObstacle] = []
            if frame > self.max_frame:
                break
            not_updated = set(self._pedestrians.keys())
            for ped_id, ped_data in self.get_frame(frame).items():
                not_updated.discard(ped_id)
                if ped_id in self._pedestrians:
                    # update existing
                    ped = self._pedestrians[ped_id]
                    dx = Vector3(
                        x=ped_data.x - ped.pose.position.x,
                        y=ped_data.y - ped.pose.position.y,
                    )
                    ped.pose.position.x = ped_data.x
                    ped.pose.position.y = ped_data.y
                    ped.pose.orientation = dx.to_orientation().to_msg()
                    ped.twist.linear.x = dx.x * self._fps
                    ped.twist.linear.y = dx.y * self._fps
                else:
                    # create new
                    ped_msg = Pedestrian()
                    ped_msg.id = next(self._id_iter)
                    ped_msg.name = ped_id
                    ped_msg.pose.position.x = ped_data.x
                    ped_msg.pose.position.y = ped_data.y
                    self._pedestrians[ped_id] = ped_msg
                    self._logger.debug(f'WOW NEVER SEEN {ped_id} B4')
                    to_spawn.append(next(obs for obs in self._data if obs.name == ped_id))
            for ped_id in not_updated:
                if self._despawn:
                    del self._pedestrians[ped_id]
                    to_delete.append(next(obs for obs in self._data if obs.name == ped_id))
            yield to_spawn, to_delete
        else:
            self._frame = new_frame
            self._logger.debug(f'new frame is {self._frame}/{self.max_frame}')
            return self._frame

        # frame range exceeded
        return None

    @classmethod
    def from_csv(cls, path: Path) -> Self:
        """Load CSV file and parse to simple format"""

        if not path.is_file():
            raise FileNotFoundError(path)

        # Load and transpose CSV (like SocNavBench does)
        with open(path, 'r') as f:
            reader = zip(*csv.reader(f))  # read transposed

        # Parse: frame, ped_id, y, x (SocNavBench format)
        min_frame = float('inf')
        pedestrians: dict[str, SocnavPedestrian] = {}

        for row in reader:
            frame = int(row[0])
            if frame < min_frame:
                min_frame = frame
            ped_id = row[1]
            x = float(row[2])
            y = float(row[3])

            if ped_id not in pedestrians:
                pedestrians[ped_id] = SocnavPedestrian(
                    name=f'Ped{ped_id}',
                    model='gazebo_actor',
                    pose=Pose(position=Position(x=x, y=y, z=0)),
                    spawn_at=frame,
                )
            pedestrians[ped_id].waypoints.append(Position(x=x, y=y, z=0))

        for ped in pedestrians.values():
            ped.spawn_at -= int(min_frame)

        return cls(pedestrians.values())
