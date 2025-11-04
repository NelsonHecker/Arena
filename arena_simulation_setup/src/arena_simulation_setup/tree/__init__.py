from __future__ import annotations

import abc
import enum
import os
import re
import subprocess
import typing
from collections.abc import Sequence
from pathlib import Path
from typing import Optional

import attrs

from arena_simulation_setup import (
    ARENA_ASSETS_DIR,
    DOMAIN_DEFAULT,
)
from arena_simulation_setup.utils.cattrs import Idempotent, Parseable, Serializable


ProviderT = typing.TypeVar('ProviderT', bound='ProviderBase')


class ProviderBase(Parseable, Serializable, abc.ABC):

    # mixins for cattrs
    @classmethod
    def parse(cls: typing.Type[ProviderT], value: typing.Any) -> ProviderT:
        if isinstance(value, cls):
            return value
        if not isinstance(value, str):
            raise TypeError(f'Expected value to be str, got {type(value)}')
        return cls(value)

    def serialize(self) -> typing.Any:
        return self.name

    # Class Methods: Provider
    @classmethod
    def _listdir(cls, path: Path) -> Sequence[str]:
        if not path.exists():
            return ()
        return tuple(sorted(str(f.relative_to(path)) for f in path.iterdir() if not f.name.startswith('.')))

    @classmethod
    @abc.abstractmethod
    def list(cls) -> Sequence[str]:
        """
        List all assets provided by the provider.
        """

    @classmethod
    @abc.abstractmethod
    def resolve(cls, name: str) -> Path:
        """
        Resolve the given asset name to an absolute path.
        """

    # Instance Methods: Providee
    _name: str

    @property
    def name(self) -> str:
        return self._name

    @property
    def path(self) -> Path:
        return self.resolve(self.name)

    def __init__(self, name: str) -> None:
        if hasattr(self, '_name'):
            return
        if not isinstance(name, str):
            raise TypeError(f'Expected name to be str, got {type(name)}')
        self._name = str(name)


class StaticProvider(ProviderBase, Idempotent):

    _path: typing.ClassVar[Path]

    @classmethod
    def bind(cls: typing.Type[ProviderT], path: Path) -> typing.Type[ProviderT]:
        return typing.cast(
            typing.Type[ProviderT],
            type('Bound' + cls.__name__, (cls,), dict(_path=path))
        )

    @classmethod
    def list(cls):
        return cls._listdir(cls._path)

    @classmethod
    def base_dir(cls) -> Path:
        return cls._path

    @classmethod
    def resolve(cls, name: str) -> Path:
        return cls._path / Path(name)


NETWORK_PROVIDERS: Sequence[str] = os.environ.get('ASSET_BUCKETS', 'default').split(',')
ANNOTATION_MARKER = 'annotation.yaml'


class AssetType(str, enum.Enum):
    """Represents the type of a simulation asset.
    """
    OBJECT = 'Object'  # 3D model
    MATERIAL = 'Material'  # Material
    PEDESTRIAN = 'Pedestrian'  # Pedestrian
    WALL = 'Wall'  # Wall Description


@attrs.define
class Identifier:
    """Represents an identifier referencing an asset.
    """
    type_: AssetType
    domain: str
    name: str

    @property
    def path(self) -> Path:
        """Get the path representation of the identifier.

        Returns:
            Path: The path of the identifier relative to a repository.
        """
        return Path(self.domain) / self.type_.value / self.name

    @property
    def canonical(self) -> str:
        """Get the canonical representation of the identifier for use in hashing.

        Returns:
            str: The canonical representation of the identifier.
        """
        return f'{self.type_.value}:{self.domain}:{self.name}'

    def __hash__(self) -> int:
        return hash(Path(self.domain) / self.name)

    @classmethod
    def parse(cls, identifier: str, *, default_target: AssetType, default_domain: str) -> Identifier:
        """Parse path of the form [type:][domain:]name into an Identifier.

        Args:
            identifier (str): The identifier string to parse.
            default_target (AssetType): The default target type if not specified.
            default_domain (str): The default domain if not specified.

        Returns:
            Identifier: The parsed Identifier object.
        """
        parts = list(reversed(identifier.split('/', 2)))

        name = parts[0]
        domain = parts[1] if len(parts) > 1 else default_domain
        type_ = AssetType(parts[2]) if len(parts) > 2 else default_target

        return cls(
            type_=type_,
            domain=domain,
            name=name,
        )


class Resolver:
    """
    Resolve asset paths from disk.
    """

    def __init__(self, asset_type: AssetType, dirs: Optional[dict[str, Path]] = None):
        self._cache: dict[Identifier, Path] = {}
        self._asset_type: AssetType = asset_type
        self._dirs: dict[str, Path] = dirs or {}

    def invalidate(self):
        """
        Invalidate the cache.
        """
        self._cache.clear()

    def update_dir(self, extra: str, path: Optional[Path]):
        """
        Update or remove extra disk source.
        Arguments:
            extra: The name of the extra disk source.
            path: The path to the extra disk source. If None, the extra disk source is removed.
        """
        if extra in self._dirs:
            self.invalidate()
        if path:
            self._dirs[extra] = path
        else:
            self._dirs.pop(extra, None)

    def _check_exists(self, identifier: Identifier) -> Optional[Path]:
        """Check if the asset exists in local sources.

        Args:
            identifier (Identifier): The identifier of the asset.

        Returns:
            Optional[Path]: The path to the asset if it exists, otherwise None.
        """
        arena_dir = self._dirs.get(Resolvers.ARENA_DIR)
        if arena_dir is None:
            globbed_arenadir = []
        else:
            globbed_arenadir = arena_dir.glob('*')
        for local_source in (*globbed_arenadir, *self._dirs.values()):
            candidate = local_source / identifier.path
            if candidate.exists():
                return candidate
        return None

    def resolve(self, name: str) -> Optional[Path]:
        """
        Resolve the given name.
        """
        identifier = Identifier.parse(name, default_target=self._asset_type, default_domain=DOMAIN_DEFAULT)
        if name not in self._cache:
            target = self._check_exists(identifier)
            if target is not None:
                self._cache[identifier] = target
        return self._cache.get(identifier, None)

    def list_cached(self) -> Sequence[str]:
        """
        List all cached assets.
        """
        return [str(key.path) for key in self._cache]

    def list_local(self) -> Sequence[str]:
        """
        List all local assets available. Builds the cache in the process.
        """
        found: list[str] = []
        for local_source in self._dirs.values():
            for root, _, files in os.walk(local_source):
                if self._asset_type != Path(root).parts[0]:
                    continue
                for file in files:
                    if not file == ANNOTATION_MARKER:
                        continue
                    relpath = Path(root).relative_to(local_source)
                    identifier = Identifier(type_=self._asset_type, domain=relpath.parts[0], name=str(relpath.relative_to(relpath.parts[0])))
                    self._cache[identifier] = identifier.path
                    found.append(identifier.canonical)
                    _.clear()

        return found

    def __repr__(self) -> str:
        sources = map(lambda v: os.path.join(v, '*', self._asset_type), self._dirs.values())
        return f"{self.__class__.__name__}({', '.join(sources)})"


class NetResolver(Resolver):
    """
    Resolve asset paths from both disk and network.
    """

    def _network_fetch(self, provider: str, identifier: Identifier) -> Optional[Path]:
        target_path = identifier.path
        try:
            if (subprocess.check_output(sp := [
                'ros2',
                'run',
                'arena_models',
                'arena_models',
                '-s',
                'net',
                provider,
                'exists',
                str(target_path),
            ]).strip().decode()) == '1':
                disk_path = ARENA_ASSETS_DIR / provider
                subprocess.check_output([
                    'ros2',
                    'run',
                    'arena_models',
                    'arena_models',
                    '-s',
                    'net',
                    provider,
                    'fetch',
                    str(target_path),
                    '-o',
                    str(disk_path),
                ])
                return disk_path / target_path

        except subprocess.CalledProcessError:
            return None

    def _check_exists_network(self, identifier: Identifier) -> Optional[Path]:
        for provider in NETWORK_PROVIDERS:
            if (target := self._network_fetch(provider, identifier)) is not None:
                return target
        return None

    def resolve(self, name):
        """
        Resolve the given name.
        """
        local = super().resolve(name)
        identifier = Identifier.parse(name, default_target=self._asset_type, default_domain=DOMAIN_DEFAULT)
        if local is None:
            net_result = self._check_exists_network(identifier)
            if net_result is not None:
                self._cache[identifier] = net_result
        return self._cache.get(identifier, None)

    def __repr__(self) -> str:
        sources = (*map(lambda v: os.path.join(v, self._asset_type), self._dirs.values()), *NETWORK_PROVIDERS)
        return f"{self.__class__.__name__}({', '.join(sources)})"


class _Resolvers:
    ARENA_DIR: str = 'arena'
    WORLD_DIR: str = 'world'

    def __init__(self) -> None:
        self._resolvers: list[Resolver] = []
        self._world_dir: Optional[Path] = None
        self._arena_dir: Path = ARENA_ASSETS_DIR

    def register(self, resolver: Resolver) -> None:
        self._resolvers.append(resolver)
        resolver.update_dir(self.ARENA_DIR, self._arena_dir)
        resolver.update_dir(self.WORLD_DIR, self._world_dir)

    def set_world_dir(self, world_dir: Path | None) -> None:
        """
        Set the world directory dynamic source resolution.
        """
        if world_dir is not None:
            world_dir = world_dir / 'assets'
        for resolver in self._resolvers:
            resolver.update_dir(self.WORLD_DIR, world_dir)


Resolvers = _Resolvers()


class DynamicProvider(ProviderBase, Idempotent):
    """
    Dynamic provider base class
    """
    _resolver: typing.ClassVar[Resolver]

    @classmethod
    def bind(cls: typing.Type[ProviderT], resolver: Resolver) -> typing.Type[ProviderT]:
        return typing.cast(
            typing.Type[ProviderT],
            type('Bound' + cls.__name__, (cls,), dict(_resolver=resolver))
        )

    @classmethod
    def list(cls):
        return cls._resolver.list_local()

    @classmethod
    def resolve(cls, name: str):
        result = cls._resolver.resolve(name)
        if result is None:
            raise FileNotFoundError(f"Asset '{name}' not found in {cls._resolver}")
        return result
