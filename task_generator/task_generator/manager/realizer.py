import typing

import attrs
from arena_simulation_setup.shared import Elevator

from task_generator.shared import (
    Door,
    DynamicObstacle,
    Entity,
    Floor,
    FrameNamespace,
    Orientation,
    Pose,
    Position,
    Wall,
)

EntityPropsT = typing.TypeVar('EntityPropsT', bound=Entity)


class Realizer:
    @attrs.frozen()
    class _Configuration:
        x: float = 0.0
        y: float = 0.0
        prefix: str = ''

    _config: _Configuration
    _level_origins: dict[str, tuple[float, float]]

    @typing.overload
    def __init__(self, config: "Realizer._Configuration", level_origins: None = None): ...
    @typing.overload
    def __init__(self, config: None = None, level_origins: dict[str, tuple[float, float]] = ...): ...
    @typing.overload
    def __init__(self, config: None = None, level_origins: None = None): ...

    def __init__(self, config: "Realizer._Configuration | None" = None, level_origins: dict[str, tuple[float, float]] | None = None):
        self._config = config if config is not None else Realizer._Configuration()
        self._level_origins = level_origins if level_origins is not None else {}

    def set_origin(self, x: float, y: float, floor_id: str = "") -> None:
        if floor_id == "":
            self._config = attrs.evolve(self._config, x=x, y=y)
        else:
            if floor_id not in self._level_origins:
                raise KeyError(f"floor_id {floor_id} is not registered on realizer")
            self._level_origins[floor_id] = (x, y)

    def register_floor(self, floor_id: str, x: float = 0.0, y: float = 0.0):
        if floor_id in self._level_origins.keys():
            raise RuntimeError(f"tried to register floor {floor_id} that is already registered on the realizer")
        self._level_origins[floor_id] = (x, y)

    def deregister_floor(self, floor_id: str):
        if floor_id in self._level_origins.keys():
            raise RuntimeWarning(f"Attempted to de-register floor {floor_id} that is not registered on the Realizer.")
        
    def get_config(self) -> "Realizer._Configuration":
        return self._config

    def get_level_origin(self, floor_id: str = "") -> tuple[float, float]:
        if floor_id == "":
            return (0.0, 0.0)
        if floor_id not in self._level_origins:
            raise KeyError(f"floor_id {floor_id} is not registered on realizer")
        return self._level_origins[floor_id]

    @typing.overload
    def realize(self) -> str: ...

    @typing.overload
    def realize(self, target: str) -> str: ...

    @typing.overload
    def realize(self, target: Position, floor_id: str = "") -> Position: ...

    def _prefix(self, *s: str) -> str:
        return str(FrameNamespace(self._config.prefix)(*s))

    def _realize_position(self, position: Position, floor_id: str = "") -> Position:
        level_x, level_y = self.get_level_origin(floor_id)
        return Position(
            x=position.x + self._config.x + level_x,
            y=position.y + self._config.y + level_y,
            z=position.z,
        )

    def _realize_position_inv(self, position: Position, floor_id: str = "") -> Position:
        level_x, level_y = self.get_level_origin(floor_id)
        return Position(
            x=position.x - self._config.x - level_x,
            y=position.y - self._config.y - level_y,
            z=position.z,
        )

    def _realize_orientation(self, orientation: Orientation, floor_id: str = "") -> Orientation:
        return Orientation(*orientation)

    def _realize_pose(self, pose: Pose, floor_id: str = "") -> Pose:
        return Pose(self._realize_position(pose.position, floor_id), self._realize_orientation(pose.orientation, floor_id))

    def ezilear(self, target: Pose, floor_id: str = "") -> Pose:
        """Inverse of realize: shift a map-frame pose back into abstract space."""
        return Pose(self._realize_position_inv(target.position, floor_id), self._realize_orientation(target.orientation, floor_id))

    @typing.overload
    def realize(self, target: EntityPropsT, floor_id: str = "") -> EntityPropsT: ...

    @typing.overload
    def realize(self, target: Pose, floor_id: str = "") -> Pose: ...

    def _realize_entity(self, entity: EntityPropsT, floor_id: str = "") -> EntityPropsT:
        return attrs.evolve(
            entity,
            pose=self._realize_pose(entity.pose, floor_id),
        )

    def _realize_dynamic_obstacle(self, obstacle: DynamicObstacle, floor_id: str = "") -> DynamicObstacle:
        return attrs.evolve(
            obstacle,
            pose=self._realize_pose(obstacle.pose, floor_id),
            waypoints=[self._realize_position(w.position, w.floor_id if w.floor_id is not None else "") for w in obstacle.waypoints],
        )

    @typing.overload
    def realize(self, target: Wall, floor_id: str = "") -> Wall: ...

    def _realize_wall(self, wall: Wall, floor_id: str = "") -> Wall:
        return attrs.evolve(
            wall,
            start=self._realize_position(wall.start, floor_id),
            end=self._realize_position(wall.end, floor_id),
        )

    @typing.overload
    def realize(self, target: Floor, floor_id: str = "") -> Floor: ...

    def _realize_floor(self, floor: Floor, floor_id: str = "") -> Floor:
        return attrs.evolve(
            floor,
            name=self._prefix(floor.name, floor_id),
            pos=self._realize_position(floor.pos, floor_id),
        )

    @typing.overload
    def realize(self, target: Door, floor_id: str = "") -> Door: ...

    def _realize_door(self, door: Door, floor_id: str = "") -> Door:
        return attrs.evolve(
            door,
            name=self._prefix(door.name, floor_id),
            start=self._realize_position(door.start, floor_id),
            end=self._realize_position(door.end, floor_id),
        )

    @typing.overload
    def realize(self, target: Elevator, floor_id: str = "") -> Elevator: ...

    def _realize_elevator(self, elevator: Elevator, floor_id: str = "") -> Elevator:
        return attrs.evolve(
            elevator,
            name=self._prefix(elevator.name, floor_id),
            position=self._realize_position(elevator.position, floor_id),
            destination=self._prefix(elevator.destination) if elevator.destination else elevator.destination,
        )

    def realize(
        self,
        target: object = None,
        floor_id: str = ""
    ) -> object:
        if target is None:
            return self._prefix(floor_id)

        if isinstance(target, str):
            return self._prefix(target)

        if isinstance(target, Position):
            return self._realize_position(target, floor_id)

        if isinstance(target, Pose):
            return self._realize_pose(target, floor_id)

        if isinstance(target, Wall):
            return self._realize_wall(target, floor_id)

        res = None

        if isinstance(target, DynamicObstacle):
            res = self._realize_dynamic_obstacle(target, floor_id)

        elif isinstance(target, Entity):
            res = self._realize_entity(target, floor_id)

        elif isinstance(target, Door):
            res = self._realize_door(target, floor_id)

        elif isinstance(target, Floor):
            res = self._realize_floor(target, floor_id)

        elif isinstance(target, Elevator):
            res = self._realize_elevator(target, floor_id)

        if res is None:
            raise TypeError(f'realization not implemented for type {type(target)}')

        res.sim_path = self._prefix(res.name, floor_id)
        return res
