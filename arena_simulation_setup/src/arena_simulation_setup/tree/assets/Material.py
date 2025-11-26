from __future__ import annotations

import os
import typing

import attrs

from arena_simulation_setup.tree import (
    AssetType,
    DynamicProvider,
    Identifier,
    NetResolver,
    Resolvers,
)


@attrs.define
class Material:
    path: str
    name: str

    __DEFAULT: typing.ClassVar[str] = "Marble"
    __DEFAULTS: typing.ClassVar[dict[str, str]] = {
        'wall': 'Marble',
        'floor': 'Porcelain_Tile_4',
        'door': 'Aluminum_Anodized',
    }

    @classmethod
    def default(cls, context: typing.Literal['floor', 'wall', 'door'] | str = '') -> str:
        return cls.__DEFAULTS.get(context, cls.__DEFAULT)

    def asdict(self) -> dict:
        return attrs.asdict(self)


class MaterialProvider(DynamicProvider[Material]):
    _path: typing.ClassVar[str]

    def load(self, *args, default: Material | None = None, **kwargs) -> Material:
        resolved = self._resolver.resolve(self.identifier)
        if resolved is None:
            if default is not None:
                return default
            raise FileNotFoundError(f'Material {self.identifier} not found')
        return Material(
            name=self.name,
            path=os.path.join(resolved, f'{self.name}.mdl'),
        )


MaterialResolver = NetResolver(AssetType.MATERIAL)
Resolvers.register(MaterialResolver)

MaterialLoader = MaterialProvider.bind(MaterialResolver)


@attrs.define(eq=False, hash=False)
class MaterialIdentifier(Identifier[Material]):
    """Represents an identifier referencing a material asset.
    """


MaterialIdentifier.provide(MaterialLoader)
