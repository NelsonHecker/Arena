from __future__ import annotations

import attrs

from arena_simulation_setup.entities.walls import WallRealization, WallDescription
from arena_simulation_setup.entities.walls import loader as WallLoader
from arena_simulation_setup.utils.geometry import Position


@attrs.define
class Wall:
    start: Position = attrs.field(converter=Position.converter)
    end: Position = attrs.field(converter=Position.converter)
    kind: str = ''
    material: str = ''

    _description: WallDescription = attrs.field(init=False)

    def __attrs_post_init__(self):
        if self.kind:
            self._description = WallLoader(self.kind).load()
        else:
            self._description = WallDescription.simple(material=self.material or None)
        _ = self.assets  # trigger the cached property

    def assets(self) -> WallRealization:
        """
        Get sub-assets that make up the wall.
        """
        return self._description.realize(self.start, self.end)

    def __iter__(self):
        yield self.start
        yield self.end
