from __future__ import annotations

import typing

import attrs

from arena_simulation_setup.tree.assets.Material import MaterialLoader
from arena_simulation_setup.tree.Wall import WallDescription, WallRealization
from arena_simulation_setup.tree.Wall import loader as WallLoader
from arena_simulation_setup.utils.geometry import Position


@attrs.define
class Wall:
    start: Position = attrs.field(converter=Position.converter)
    end: Position = attrs.field(converter=Position.converter)
    kind: str = ''
    material: str = ''

    def assets(self) -> WallRealization:
        """
        Get sub-assets that make up the wall.
        """
        if self.kind:
            _description = WallLoader(self.kind).load()
        else:
            _description = WallDescription.simple(material=MaterialLoader(self.material) if self.material else None)
        return _description.realize(self.start, self.end)

    def __iter__(self):
        yield self.start
        yield self.end
