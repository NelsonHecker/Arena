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

    def __init__(self, config: "Realizer._Configuration"):
        self._config = config

    def set_origin(self, x: float, y: float) -> None:
        self._config = attrs.evolve(self._config, x=x, y=y)

    @typing.overload
    def realize(self) -> str: ...

    @typing.overload
    def realize(self, target: str) -> str: ...

    @typing.overload
    def realize(self, target: Position) -> Position: ...

    def _prefix(self, *s: str) -> str:
        return str(FrameNamespace(self._config.prefix)(*s))

    def prefix(self, *s: str) -> str:
        """Public: return the env-prefixed identifier for ``s`` (no pose realization)."""
        return self._prefix(*s)

    def _realize_position(self, position: Position) -> Position:
        return Position(
            x=position.x + self._config.x,
            y=position.y + self._config.y,
            z=position.z,
        )

    def _realize_position_inv(self, position: Position) -> Position:
        return Position(
            x=position.x - self._config.x,
            y=position.y - self._config.y,
            z=position.z,
        )

    def _realize_orientation(self, orientation: Orientation) -> Orientation:
        return Orientation(*orientation)

    def _realize_pose(self, pose: Pose) -> Pose:
        return Pose(self._realize_position(pose.position), self._realize_orientation(pose.orientation))

    def ezilear(self, target: Pose) -> Pose:
        """Inverse of realize: shift a map-frame pose back into abstract space."""
        return Pose(self._realize_position_inv(target.position), self._realize_orientation(target.orientation))

    @typing.overload
    def realize(self, target: EntityPropsT) -> EntityPropsT: ...

    @typing.overload
    def realize(self, target: Pose) -> Pose: ...

    def _realize_entity(self, entity: EntityPropsT) -> EntityPropsT:
        return attrs.evolve(
            entity,
            pose=self._realize_pose(entity.pose),
        )

    def _realize_dynamic_obstacle(self, obstacle: DynamicObstacle) -> DynamicObstacle:
        return attrs.evolve(
            obstacle,
            pose=self._realize_pose(obstacle.pose),
            waypoints=[self._realize_position(w) for w in obstacle.waypoints],
        )

    @typing.overload
    def realize(self, target: Wall) -> Wall: ...

    def _realize_wall(self, wall: Wall) -> Wall:
        return attrs.evolve(
            wall,
            start=self._realize_position(wall.start),
            end=self._realize_position(wall.end),
        )

    @typing.overload
    def realize(self, target: Floor) -> Floor: ...

    def _realize_floor(self, floor: Floor) -> Floor:
        return attrs.evolve(
            floor,
            name=self._prefix(floor.name),
            pos=self._realize_position(floor.pos),
        )

    @typing.overload
    def realize(self, target: Door) -> Door: ...

    def _realize_door(self, door: Door) -> Door:
        return attrs.evolve(
            door,
            name=self._prefix(door.name),
            start=self._realize_position(door.start),
            end=self._realize_position(door.end),
        )

    @typing.overload
    def realize(self, target: Elevator) -> Elevator: ...

    def _realize_elevator(self, elevator: Elevator) -> Elevator:
        return attrs.evolve(
            elevator,
            name=self._prefix(elevator.name),
            position=self._realize_position(elevator.position),
            destination=self._prefix(elevator.destination) if elevator.destination else elevator.destination,
        )

    def realize(
        self,
        target: object = None,
    ) -> object:
        if target is None:
            return self._prefix()

        if isinstance(target, str):
            return self._prefix(target)

        if isinstance(target, Position):
            return self._realize_position(target)

        if isinstance(target, Pose):
            return self._realize_pose(target)

        if isinstance(target, Wall):
            return self._realize_wall(target)

        res = None

        if isinstance(target, DynamicObstacle):
            res = self._realize_dynamic_obstacle(target)

        elif isinstance(target, Entity):
            res = self._realize_entity(target)

        elif isinstance(target, Door):
            res = self._realize_door(target)

        elif isinstance(target, Floor):
            res = self._realize_floor(target)

        elif isinstance(target, Elevator):
            res = self._realize_elevator(target)

        if res is None:
            raise TypeError(f'realization not implemented for type {type(target)}')

        res.sim_path = self._prefix(res.name)
        return res
