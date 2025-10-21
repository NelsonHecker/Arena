from __future__ import annotations

import os
import typing

import attrs

from arena_simulation_setup import ProviderBase, ass_sources
from arena_simulation_setup.utils.cattrs import Serializable


@attrs.define
class Material:
    path: str  # TODO rename to path
    name: str

    DEFAULT: typing.ClassVar[str] = "PCB_Copper"

    def asdict(self) -> dict:
        return attrs.asdict(self)


class MaterialProvider(ProviderBase, Serializable):
    _path: typing.ClassVar[str]

    @classmethod
    def DEFAULT(cls) -> MaterialProvider:
        return cls(Material.DEFAULT)

    def load(self, *, default: Material | None = None) -> Material:
        resolved = self.resolve(self.name, fn=os.path.isdir)
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


MaterialLoader = MaterialProvider.bind(ass_sources('entities', 'materials'))
