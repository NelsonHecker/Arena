from __future__ import annotations

import logging
import os
from pathlib import Path
import shutil
import tempfile
import typing

import attrs

from arena_simulation_setup.tree import (
    AssetType,
    DynamicProvider,
    Identifier,
    NetResolver,
    Resolvers,
)

from arena_simulation_setup.utils.material import ImgUtil, MdlUtil


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

    @classmethod
    def _apply_tint(cls, basepath: Path, material: Material, tint: str) -> Material:

        tmpdir = tempfile.mkdtemp(prefix='material_')
        shutil.copytree(basepath, tmpdir, dirs_exist_ok=True)
        path = Path(tmpdir) / Path(material.path).relative_to(basepath)
        basepath = Path(tmpdir)

        for texture_path in MdlUtil(path).diffuse_texture_paths:
            try:
                if texture_path.exists() and texture_path.is_relative_to(basepath):
                    tinted_img = ImgUtil.tint(texture_path, tint)
                    tinted_img.save(texture_path)
            except Exception as e:
                import traceback
                logging.error(f'Failed to tint texture {texture_path}: {e}\n{traceback.format_exc()}')

        return attrs.evolve(
            material,
            path=str(path.resolve()),
        )

    def load(self, *args, default: Material | None = None, **kwargs) -> Material:
        resolved = self._resolver.resolve(self.identifier)
        if resolved is None:
            if default is not None:
                return default
            raise FileNotFoundError(f'Material {self.identifier} not found')

        mat = Material(
            name=self.name,
            path=os.path.join(resolved, f'{self.name}.mdl'),
        )

        if (tint := self.identifier.modifiers.get('tint')) is not None:
            mat = self._apply_tint(resolved, mat, tint)

        return mat


MaterialResolver = NetResolver(AssetType.MATERIAL)
Resolvers.register(MaterialResolver)

MaterialLoader = MaterialProvider.bind(MaterialResolver)


@attrs.define(eq=False, hash=False)
class MaterialIdentifier(Identifier[Material]):
    """Represents an identifier referencing a material asset.
    """


MaterialIdentifier.provide(MaterialLoader)
