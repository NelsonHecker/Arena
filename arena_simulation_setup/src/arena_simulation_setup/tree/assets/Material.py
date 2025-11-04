from __future__ import annotations

import os
import typing

import attrs

from arena_simulation_setup.tree import AssetType, DynamicProvider, NetResolver, Resolvers


@attrs.define
class Material:
    path: str
    name: str

    DEFAULT: typing.ClassVar[str] = "Marble"
    DEFAULTS: typing.ClassVar[dict[str, str]] = {
        'wall': 'Marble',
        'floor': 'Wood_Oak',
    }

    def asdict(self) -> dict:
        return attrs.asdict(self)


class MaterialProvider(DynamicProvider):
    _path: typing.ClassVar[str]

    @classmethod
    def DEFAULT(cls, context: typing.Literal['floor', 'wall'] | str = '') -> MaterialProvider:
        return cls(Material.DEFAULTS.get(context, Material.DEFAULT))

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


MaterialResolver = NetResolver(AssetType.MATERIAL)
Resolvers.register(MaterialResolver)

MaterialLoader = MaterialProvider.bind(MaterialResolver)
