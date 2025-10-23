from __future__ import annotations

import os
import typing

import attrs

from arena_simulation_setup.tree import AssetType, DynamicProvider, NetResolver, Resolvers
from arena_simulation_setup.utils.cattrs import Serializable


@attrs.define
class Material:
    path: str
    name: str

    DEFAULT: typing.ClassVar[str] = "Marble"

    def asdict(self) -> dict:
        return attrs.asdict(self)


class MaterialProvider(DynamicProvider, Serializable):
    _path: typing.ClassVar[str]

    @classmethod
    def DEFAULT(cls) -> MaterialProvider:
        return cls(Material.DEFAULT)

    def load(self, *, default: Material | None = None) -> Material:
        resolved = self._resolver.resolve(self.name)
        if resolved is None:
            if default is not None:
                return default
            raise FileNotFoundError(f'Material {self.name} not found')
        return Material(
            name=self.name,
            path=os.path.join(resolved, f'{self.name}.mdl'),
        )

    def serialize(self) -> str:
        return self.name


MaterialResolver = NetResolver(AssetType.MATERIAL)
Resolvers.register(MaterialResolver)

MaterialLoader = MaterialProvider.bind(MaterialResolver)
