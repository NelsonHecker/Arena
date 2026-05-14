"""Interface definitions for simulator interactions with obstacles, pedestrians, robots, and lifecycle."""

import abc
from collections.abc import Sequence

from arena_people_msgs.msg import Pedestrians
from task_generator.shared import (
    Door,
    DynamicObstacle,
    Elevator,
    Floor,
    Obstacle,
    Robot,
    Wall,
)


class SimLifecycle(abc.ABC):
    """Process-singleton hooks for sim-wide pause/unpause and namespace cleanup."""

    @abc.abstractmethod
    async def pause(self) -> bool: ...

    @abc.abstractmethod
    async def unpause(self) -> bool: ...

    @abc.abstractmethod
    async def cleanup_namespace(self, prefix: str) -> int:
        """Delete all entities under the given namespace prefix. Returns count removed."""
        ...

    def env_prefix(self, env_id: int) -> str:
        """Cleanup-namespace prefix for env_id. Default: slash-nested (USD-style)."""
        return f"env_{env_id}/"

    @abc.abstractmethod
    async def ensure_ready(self) -> None:
        """Block until the underlying sim's services are reachable."""
        ...


class ObstacleITF(abc.ABC):
    """Abstract base class for obstacle management in simulators."""

    @abc.abstractmethod
    async def obstacle_spawn(self, obstacles: Sequence[Obstacle]) -> Sequence[bool]:
        """Spawn obstacles."""
        raise NotImplementedError()

    @abc.abstractmethod
    async def obstacle_move(self, obstacles: Sequence[Obstacle]) -> Sequence[bool]:
        """Move obstacles."""
        raise NotImplementedError()

    @abc.abstractmethod
    async def obstacle_delete(self, obstacles: Sequence[Obstacle]) -> Sequence[bool]:
        """Delete obstacles."""
        raise NotImplementedError()


class PedestrianITF(abc.ABC):
    """Abstract base class for pedestrian management in simulators."""

    @abc.abstractmethod
    async def pedestrian_spawn(self, pedestrians: Sequence[DynamicObstacle]) -> Sequence[bool]:
        """Spawn pedestrians."""
        raise NotImplementedError()

    @abc.abstractmethod
    async def pedestrian_move(self, pedestrians: Sequence[DynamicObstacle]) -> Sequence[bool]:
        """Teleport pedestrians."""
        raise NotImplementedError()

    @abc.abstractmethod
    async def pedestrian_delete(self, pedestrians: Sequence[DynamicObstacle]) -> Sequence[bool]:
        """Delete pedestrians."""
        raise NotImplementedError()

    @abc.abstractmethod
    async def pedestrian_update(self, pedestrians: Pedestrians) -> Sequence[bool]:
        """Navigate pedestrians to position with velocity."""
        raise NotImplementedError()


class RobotITF(abc.ABC):
    """Abstract base class for robot management in simulators."""

    @abc.abstractmethod
    async def robot_spawn(self, robots: Sequence[Robot]) -> Sequence[bool]:
        """Spawn robots."""
        raise NotImplementedError()

    @abc.abstractmethod
    async def robot_move(self, robots: Sequence[Robot]) -> Sequence[bool]:
        """Move robots."""
        raise NotImplementedError()

    @abc.abstractmethod
    async def robot_delete(self, robots: Sequence[Robot]) -> Sequence[bool]:
        """Delete robots."""
        raise NotImplementedError()


class WorldITF(abc.ABC):
    @abc.abstractmethod
    async def spawn_walls(self, walls: Sequence[Wall], clear_existing: bool = True) -> bool:
        """
        Add a list of walls to the simulator.
        """
        raise NotImplementedError()

    @abc.abstractmethod
    async def spawn_floors(self, floors: Sequence[Floor]) -> bool:
        """
        Add a list of floors to the simulator.
        """
        raise NotImplementedError()

    @abc.abstractmethod
    async def spawn_doors(self, doors: Sequence[Door]) -> bool:
        """
        Add a list of doors to the simulator.
        """
        raise NotImplementedError()

    @abc.abstractmethod
    async def spawn_elevators(self, elevators: Sequence[Elevator]) -> bool:
        """
        Add a list of elevators to the simulator.
        """
        raise NotImplementedError()

    async def remove_world(self) -> bool:
        """
        Remove every spawned world element.
        """
        raise NotImplementedError()
