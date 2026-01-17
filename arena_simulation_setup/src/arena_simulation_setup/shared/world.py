from __future__ import annotations

import typing

import attrs
import numpy as np

from arena_simulation_setup.utils.geometry import Position
from arena_simulation_setup.tree.assets.Material import MaterialIdentifier, Material

from .entities import Named


@attrs.define
class Elevator(Named):
    position: Position = attrs.field(converter=Position.converter)
    size: list[float] = attrs.field(factory=lambda: [2.0, 2.0, 0.2])
    height_min: float = 0.0
    height_max: float = 3.0
    material: MaterialIdentifier = attrs.field(
        converter=MaterialIdentifier.converter,
        default=Material.default('elevator')
    )
    destination: str = attrs.field(default="")


@attrs.define
class Door(Named):
    start: Position = attrs.field(converter=Position.converter)
    end: Position = attrs.field(converter=Position.converter)
    kind: typing.Literal['sliding'] = 'sliding'
    width: float = 0.1
    height: float = attrs.field(default=2.0)
    material: MaterialIdentifier = attrs.field(
        converter=MaterialIdentifier.converter,
        default=Material.default('door')
    )

    @property
    def corners(self) -> list[Position]:
        direction = np.array(list(self.end)) - np.array(list(self.start))
        direction = direction / np.linalg.norm(direction)
        perp = np.array([-direction[1], direction[0], 0])
        projected_half_width = Position(*(self.width / 2 * perp))
        return [
            self.start + projected_half_width,
            self.start - projected_half_width,
            self.end - projected_half_width,
            self.end + projected_half_width,
        ]


@attrs.define
class Floor(Named):
    pos: Position = attrs.field(converter=Position.converter)
    x_length: float = attrs.field(converter=float, default=20.)
    y_length: float = attrs.field(converter=float, default=20.)
    material: MaterialIdentifier = attrs.field(
        converter=MaterialIdentifier.converter,
        default=Material.default('floor')
    )
