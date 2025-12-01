from __future__ import annotations

import logging
import os
import shutil
import tempfile
import traceback
import typing
from pathlib import Path

import attrs

from arena_simulation_setup.tree import (
    DynamicPaths,
    ModifiersDomainAssetIdentifier,
    NetResolver,
)
from arena_simulation_setup.utils.material import ImgUtil, MdlUtil


@attrs.define(eq=False, hash=False)
class MaterialIdentifier(ModifiersDomainAssetIdentifier["Material"]):
    """Represents an identifier referencing a material asset.
    """
    _asset_type = 'Material'

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
                logging.error(f'Failed to tint texture {texture_path}: {e}\n{traceback.format_exc()}')

        return attrs.evolve(
            material,
            path=str(path.resolve()),
        )

    def load(self, path: Path, /, **kwargs) -> Material:
        del kwargs  # unused
        mat = Material(
            name=self.name,
            path=os.path.join(path, f'{self.name}.mdl'),
        )

        if (tint := self.modifiers.get('tint')) is not None:
            mat = self._apply_tint(path, mat, tint)
        return mat


MaterialIdentifier.use(*DynamicPaths.as_resolvers(MaterialIdentifier))
MaterialIdentifier.use(*NetResolver.all(MaterialIdentifier))


@attrs.define
class Material:
    path: str
    name: str

    __DEFAULT: typing.ClassVar[MaterialIdentifier] = MaterialIdentifier("Marble")
    __DEFAULTS: typing.ClassVar[dict[str, MaterialIdentifier]] = {
        'wall': MaterialIdentifier('Marble'),
        'floor': MaterialIdentifier('Porcelain_Tile_4'),
        'door': MaterialIdentifier('Aluminum_Anodized'),
    }

    @classmethod
    def default(cls, context: typing.Literal['floor', 'wall', 'door'] | str = '') -> MaterialIdentifier:
        return cls.__DEFAULTS.get(context, cls.__DEFAULT)

    def asdict(self) -> dict:
        return attrs.asdict(self)
