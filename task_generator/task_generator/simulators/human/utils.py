import enum
import typing
from typing import Optional

import attrs


class ObstacleLayer(int, enum.Enum):
    UNUSED = 0  # unused, could be garbage collected
    INUSE = 1  # in use, but can be unused
    WORLD = 2  # intrinsic part of world


ObstacleT = typing.TypeVar('ObstacleT')


@attrs.define()
class KnownObstacle(typing.Generic[ObstacleT]):
    obstacle: ObstacleT
    spawned: bool = False
    layer: ObstacleLayer = ObstacleLayer.UNUSED


class KnownObstacles(typing.Generic[ObstacleT]):
    """
    Helper interface to store known obstacles
    """

    # store obstacle descs and whether they have been spawned
    _known_obstacles: dict[str, KnownObstacle[ObstacleT]]

    def __init__(self):
        self._known_obstacles = dict()

    def forget(self, name: str):
        """
        Delete obstacle.
        @name: name of obstacle
        """
        if name in self._known_obstacles:
            del self._known_obstacles[name]

    def create_or_get(self, name: str, obstacle: ObstacleT, **kwargs) -> KnownObstacle[ObstacleT]:
        """
        Get an existing obstacle or create it if it doesn't exist. To overwrite an existing obstacle, first remove it using forget().
        @name: name of obstacle
        @kwargs: arguments passed to KnownObstacle constructor
        """
        if name not in self._known_obstacles:
            self._known_obstacles[name] = KnownObstacle[ObstacleT](obstacle=obstacle, **kwargs)

        return self._known_obstacles[name]

    def get(self, name: str) -> Optional[KnownObstacle[ObstacleT]]:
        """
        Get an existing obstacle or return None if it doesn't exist.
        @name: name of obstacle
        """
        return self._known_obstacles.get(name, None)

    def keys(self):
        """
        Get internal dict_keys.
        """
        return self._known_obstacles.keys()

    def values(self):
        """
        Get internal dict_values.
        """
        return self._known_obstacles.values()

    def items(self):
        """
        Get internal dict_items.
        """
        return self._known_obstacles.items()

    def clear(self):
        """
        Clear internal dict.
        """
        return self._known_obstacles.clear()

    def __contains__(self, item: str) -> bool:
        return item in self._known_obstacles
