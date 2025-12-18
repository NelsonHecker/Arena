from __future__ import annotations

import abc
import itertools
import math
from pathlib import Path
import typing
from collections.abc import Iterable

import attrs
import yaml

from arena_simulation_setup.shared.entities import Obstacle
from arena_simulation_setup.tree import (
    DomainAssetIdentifier,
    DynamicPathResolver,
    DynamicPaths,
    NetResolver,
)
from arena_simulation_setup.tree.assets.Material import Material, MaterialIdentifier
from arena_simulation_setup.tree.assets.Object import ObjectIdentifier
from arena_simulation_setup.utils.cattrs import Parseable, converter
from arena_simulation_setup.utils.geometry import Orientation, Pose, Position

###
# Parsing wall description
###


class PositionalNumber(Parseable):
    def __init__(self, *, absolute: typing.Optional[float] = None, relative: typing.Optional[float] = None):
        if absolute is not None:
            self._absolute = absolute
            self._relative = None
        elif relative is not None:
            self._absolute = None
            self._relative = relative
        else:
            raise ValueError("Must specify either absolute or relative.")

    def absolute(self, low: float, high: float) -> float:
        if self._absolute is not None:
            if math.copysign(1, self._absolute) < 0:
                return high + self._absolute
            return self._absolute
        if self._relative is not None:
            return low + (high - low) * self._relative
        raise ValueError("Neither absolute nor relative is set.")

    def realize(self, start: Position, end: Position) -> Position:
        return start + self.absolute(0.0, (end - start).norm()) * (end - start).normalized()

    @classmethod
    def parse(cls, value: typing.Any) -> PositionalNumber:
        if isinstance(value, str) and value.endswith('%'):
            return cls(relative=float(value[:-1]) / 100.0)
        return cls(absolute=float(value))


@attrs.define(kw_only=True)
class SubWall(abc.ABC):
    x: float = attrs.field(converter=float, default=0.0)  # x axis shift [m]
    y: float = attrs.field(converter=float, default=0.0)  # y axis shift [m]
    z: float = attrs.field(converter=float, default=0.0)  # z axis shift [m]

    def _shift(self, start: Position, end: Position) -> tuple[Position, Position]:
        external_orientation = (end - start).to_orientation()
        offset = external_orientation * Position(self.x, self.y, self.z)
        return offset + start, offset + end

    @abc.abstractmethod
    def realize(self, start: Position, end: Position) -> WallRealization:
        pass


@attrs.define(kw_only=True)
class TilingAsset(SubWall):
    """
    Place repeating asset along the wall.
    """
    tile: list[SubWallT]
    every: float  # place every N meters
    width: float = attrs.field(converter=float, default=0.0)  # width of the tile [m]

    def realize(self, start: Position, end: Position) -> WallRealization:
        start, end = self._shift(start, end)

        r_walls, r_obstacles = itertools.chain(()), itertools.chain(())
        if (divisor := (end - start).norm()) > 1e-6:
            every = self.every / divisor
            width = self.width / divisor / 2.0
        else:
            every = 1.0
            width = 0.0

        offset = every + width
        while (offset + width) < 1:
            for asset in self.tile:
                walls, obstacles = asset.realize(start + (offset - width) * (end - start), start + (offset + width) * (end - start))
                r_walls = itertools.chain(r_walls, walls)
                r_obstacles = itertools.chain(r_obstacles, obstacles)
            offset += every
        return (r_walls, r_obstacles)


@attrs.define(kw_only=True)
class FillAsset(SubWall):
    """
    Place along slice of the wall.
    """
    fill: list[SubWallT]
    start: PositionalNumber = PositionalNumber.parse(0.0)  # start at N meters along the wall
    end: PositionalNumber = PositionalNumber.parse(-0.0)  # end at N meters along the wall

    def realize(self, start: Position, end: Position) -> WallRealization:
        start, end = self._shift(start, end)

        r_start = self.start.realize(start, end)
        r_end = self.end.realize(start, end)

        return tuple(
            itertools.chain.from_iterable(
                zip(*(e.realize(r_start, r_end) for e in self.fill))
            )
        )


@attrs.define(kw_only=True)
class PlaceObstacleAsset(SubWall):
    """
    Place a single obstacle.
    """
    model: ObjectIdentifier = attrs.field(converter=ObjectIdentifier.converter)  # model

    at: PositionalNumber = PositionalNumber.parse('50%')  # place at position along the wall
    orientation: Orientation = attrs.field(factory=Orientation.identity)  # interior orientation

    name: str = ""  # asset name, defaults to model name

    def realize(self, start: Position, end: Position) -> WallRealization:

        exterior_orientation = (end - start).to_orientation()
        start, end = self._shift(start, end)

        return (), (
            Obstacle(
                name=self.name or self.model.name,
                model=self.model,
                pose=Pose(
                    position=self.at.realize(start, end),
                    orientation=self.orientation * exterior_orientation,
                ),
            ),
        )


@attrs.define(kw_only=True)
class PlaceWallSegmentAsset(SubWall):
    """
    Place a single wall segment.
    """
    material: MaterialIdentifier = attrs.field(
        converter=MaterialIdentifier.converter,
        default=Material.default('wall'),
    )
    height: float = attrs.field(converter=float, default=2.0)
    width: float = attrs.field(converter=float, default=0.05)
    name: str = ""

    def realize(self, start: Position, end: Position) -> WallRealization:
        start, end = self._shift(start, end)

        return (
            WallSegment(
                start=start,
                end=end,
                height=self.height,
                width=self.width,
                material=self.material,
            ),
        ), ()


# Now that all SubWall classes are defined, create the proper type alias
SubWallT = TilingAsset | FillAsset | PlaceObstacleAsset | PlaceWallSegmentAsset


###
# Realization of a wall description
###


@attrs.define
class WallSegment:
    start: Position
    end: Position
    height: float
    width: float
    material: MaterialIdentifier = attrs.field(
        converter=MaterialIdentifier.converter,
        default=Material.default('wall'),
    )


WallRealization = tuple[Iterable[WallSegment], Iterable[Obstacle]]


@attrs.define
class WallDescription:
    main: list[SubWallT]

    def realize(self, start: Position, end: Position) -> WallRealization:
        r_walls, r_obstacles = itertools.chain(()), itertools.chain(())
        for subwall in self.main:
            walls, obstacles = subwall.realize(start, end)
            r_walls = itertools.chain(r_walls, walls)
            r_obstacles = itertools.chain(r_obstacles, obstacles)

        return (r_walls, r_obstacles)

    @classmethod
    def simple(cls, material: typing.Optional[MaterialIdentifier] = None) -> WallDescription:
        if material is None:
            return cls(main=[PlaceWallSegmentAsset()])
        return cls(
            main=[
                PlaceWallSegmentAsset(
                    material=material,
                )
            ]
        )


class WallIdentifier(DomainAssetIdentifier[WallDescription]):
    _asset_type = 'Wall'

    def load(self, path: Path, /, **kwargs) -> WallDescription:
        del kwargs  # unused
        with open(path / f'{path.name}.yaml') as f:
            return converter.structure(yaml.safe_load(f), WallDescription)


WallIdentifier.use(*DynamicPaths.as_resolvers(WallIdentifier))
WallIdentifier.use(*NetResolver.all(WallIdentifier))
