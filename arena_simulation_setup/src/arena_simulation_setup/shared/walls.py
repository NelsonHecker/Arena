from __future__ import annotations

import attrs

from arena_simulation_setup.tree.assets.Material import Material, MaterialIdentifier
from arena_simulation_setup.tree.Wall import WallDescription, WallIdentifier, WallRealization
from arena_simulation_setup.utils.cattrs import Serializable
from arena_simulation_setup.utils.geometry import Position


@attrs.define
class Wall(Serializable):
    start: Position = attrs.field(converter=Position.converter)
    end: Position = attrs.field(converter=Position.converter)
    kind: str = ''
    material: MaterialIdentifier | None = None

    async def assets(self) -> WallRealization:
        """
        Get sub-assets that make up the wall.
        """
        try:
            if self.kind:
                _description = await WallIdentifier(self.kind).resolve()
            else:
                _description = WallDescription.simple(material=self.material if self.material else None)
            return _description.realize(self.start, self.end)
        except Exception as e:
            import logging
            import traceback

            logging.error(f"Failed to load wall assets for wall from {self.start} to {self.end} of kind '{self.kind}' and material '{self.material}': {e}\n{traceback.format_exc()}")

            return WallDescription.simple(material=Material.default('wall')).realize(self.start, self.end)

    def __iter__(self):
        yield self.start
        yield self.end

    def serialize(self) -> dict:
        ser = attrs.asdict(self)
        if self.kind or not self.material:
            ser.pop('material', None)
        if not self.kind:
            ser.pop('kind', None)
        return ser
