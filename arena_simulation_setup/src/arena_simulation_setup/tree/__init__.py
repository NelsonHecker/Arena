from __future__ import annotations

import abc
import enum
import os
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

NETWORK_PROVIDERS: Sequence[str] = os.environ.get('ASSET_BUCKETS', 'default').split(',')
ANNOTATION_MARKER = 'annotation.yaml'


class AssetType(str, enum.Enum):
    """Represents the type of a simulation asset.
    """
    OBJECT = 'Object'  # 3D model
    MATERIAL = 'Material'  # Material
    PEDESTRIAN = 'Pedestrian'  # Pedestrian
    WALL = 'Wall'  # Wall Description


T = typing.TypeVar('T')


# RESOLVERS


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

    def _check_exists(self, identifier: Identifier, type_: AssetType) -> Optional[Path]:
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
            candidate = local_source / identifier.path(type_)
            if candidate.exists():
                return candidate
        return None

    def resolve(self, identifier: Identifier) -> Optional[Path]:
        """
        Resolve the given identifier.
        """
        if identifier not in self._cache:
            target = self._check_exists(identifier, self._asset_type)
            if target is not None:
                self._cache[identifier] = target
        return self._cache.get(identifier, None)

    def list_cached(self) -> Sequence[Identifier]:
        """
        List all cached assets.
        """
        return list(self._cache.keys())

    def list_local(self) -> Sequence[Identifier]:
        """
        List all local assets available. Builds the cache in the process.
        """
        found: list[Identifier] = []
        for local_source in self._dirs.values():
            for root, _, files in os.walk(local_source):
                if self._asset_type != Path(root).parts[0]:
                    continue
                for file in files:
                    if not file == ANNOTATION_MARKER:
                        continue
                    relpath = Path(root).relative_to(local_source)
                    identifier = Identifier(domain=relpath.parts[0], name=str(relpath.relative_to(relpath.parts[0])))
                    self._cache[identifier] = identifier.path(self._asset_type)
                    found.append(identifier)
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
        target_path = identifier.path(self._asset_type)
        try:
            if (subprocess.check_output([
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

    def resolve(self, identifier):
        """
        Resolve the given name.
        """
        local = super().resolve(identifier)
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


# PROVIDERS


class ProviderBase(Parseable, Serializable, Idempotent, abc.ABC, typing.Generic[T]):

    # Class Methods: Provider

    @classmethod
    def _listdir(cls, path: Path) -> Sequence[str]:
        if not path.exists():
            return ()
        return tuple(sorted(str(f.relative_to(path)) for f in path.iterdir() if not f.name.startswith('.')))

    # Instance Methods: Providee

    @abc.abstractmethod
    def __init__(self, identifier: typing.Any) -> None:
        ...

    @property
    @abc.abstractmethod
    def name(self) -> str:
        ...

    @property
    @abc.abstractmethod
    def path(self) -> Path:
        """Get the path to the asset.

        Returns:
            Path: The path to the asset.
        """

    @abc.abstractmethod
    def load(self, *args, **kwargs) -> T:
        """
        Load the asset.
        """


DynamicProviderT = typing.TypeVar('DynamicProviderT', bound='DynamicProvider')


class DynamicProvider(ProviderBase[T], typing.Generic[T]):
    """
    Dynamic provider base class
    """
    _resolver: typing.ClassVar[Resolver]

    @classmethod
    def parse(cls: typing.Type[DynamicProviderT], value: typing.Any) -> DynamicProviderT:
        if isinstance(value, cls):
            return value
        if not isinstance(value, str):
            raise TypeError(f'Expected value to be str, got {type(value)}')
        return cls(value)

    def serialize(self) -> typing.Any:
        return self.identifier

    @classmethod
    def bind(cls: typing.Type[DynamicProviderT], resolver: Resolver) -> typing.Type[DynamicProviderT]:
        return typing.cast(
            typing.Type[DynamicProviderT],
            type('Bound' + cls.__name__, (cls,), dict(_resolver=resolver))
        )

    @classmethod
    def list(cls) -> Sequence[Identifier]:
        return cls._resolver.list_local()

    @classmethod
    def resolve(cls, identifier: Identifier[T]):
        result = cls._resolver.resolve(identifier)
        if result is None:
            raise FileNotFoundError(f"Asset '{identifier}' not found in {cls._resolver}")
        return result

    # Instance Methods
    _identifier: Identifier

    @property
    def name(self) -> str:
        return self._identifier.name

    @property
    def identifier(self) -> Identifier:
        return self._identifier

    @property
    def path(self) -> Path:
        return self.resolve(self._identifier)

    def __init__(self, identifier: Identifier | str) -> None:
        if hasattr(self, '_identifier'):
            return
        if isinstance(identifier, str):
            identifier = Identifier.parse(identifier)
        if not isinstance(identifier, Identifier):
            raise TypeError(f'Expected identifier to be Identifier, got {type(identifier)}')
        self._identifier = identifier


StaticProviderT = typing.TypeVar('StaticProviderT', bound='StaticProvider')


class StaticProvider(ProviderBase[T], typing.Generic[T]):
    """Static provider base class.
    """

    _path: typing.ClassVar[Path]

    @classmethod
    def parse(cls: typing.Type[StaticProviderT], value: typing.Any) -> StaticProviderT:
        if isinstance(value, cls):
            return value
        if not isinstance(value, str):
            raise TypeError(f'Expected value to be str, got {type(value)}')
        return cls(value)

    def serialize(self) -> typing.Any:
        return self.name

    @classmethod
    def bind(cls: typing.Type[StaticProviderT], path: Path) -> typing.Type[StaticProviderT]:
        return typing.cast(
            typing.Type[StaticProviderT],
            type('Bound' + cls.__name__, (cls,), dict(_path=path))
        )

    @classmethod
    def list(cls) -> Sequence[str]:
        return cls._listdir(cls._path)

    @classmethod
    def base_dir(cls) -> Path:
        return cls._path

    @classmethod
    def resolve(cls, name: str) -> Path:
        return cls._path / name

    # Instance Methods
    _name: str

    @property
    def name(self) -> str:
        return self._name

    @property
    def path(self) -> Path:
        return self._path / self._name

    def __init__(self, identifier: str) -> None:
        if hasattr(self, '_name'):
            return
        if not isinstance(identifier, str):
            raise TypeError(f'Expected name to be str, got {type(identifier)}')
        self._name = identifier


# IDENTIFIERS

@attrs.define(eq=False, hash=False)
class Identifier(Parseable, Serializable, Idempotent, typing.Generic[T]):
    """Represents an identifier referencing an asset.
    """
    name: str
    domain: str = attrs.field(default=DOMAIN_DEFAULT)

    def path(self, type_: AssetType) -> Path:
        """Get the path representation of the identifier.

        Returns:
            Path: The path of the identifier relative to a repository.
        """
        return Path(self.domain) / type_.value / self.name

    def __hash__(self) -> int:
        return hash((self.domain, self.name))

    def __eq__(self, other: object) -> bool:
        if not isinstance(other, Identifier):
            return False
        return self.domain == other.domain and self.name == other.name

    @classmethod
    def parse(cls, value: str | Identifier) -> Identifier:
        """Parse path of the form [type:][domain:]name into an Identifier.

        Args:
            identifier (str): The identifier string to parse.
            default_target (AssetType): The default target type if not specified.
            default_domain (str): The default domain if not specified.

        Returns:
            Identifier: The parsed Identifier object.
        """
        if isinstance(value, Identifier):
            return value
        parts = list(reversed(value.split('/', 2)))

        name = parts[0]
        domain = parts[1] if len(parts) > 1 else None

        if domain:
            return cls(
                domain=domain,
                name=name,
            )
        return cls(
            name=name
        )

    def serialize(self) -> str:
        return f'{self.domain}:{self.name}'

    @classmethod
    def converter(cls, *args, **kwargs):
        return super().instance_or(cls.parse)(*args, **kwargs)

    # Class Methods
    _providers: typing.ClassVar[list[typing.Type[ProviderBase[T]]]] = []  # type: ignore

    @classmethod
    def provide(cls, *providers: typing.Type[ProviderBase[T]]):
        if '_providers' not in cls.__dict__:
            cls._providers = []
        cls._providers.extend(providers)

    def load(self) -> T:
        last_error: Optional[Exception] = None
        for provider_cls in self._providers:
            provider = provider_cls(self)
            try:
                return provider.load()
            except Exception as e:
                last_error = e
        raise RuntimeError(f'Failed to load asset {self}') from last_error

    @classmethod
    def inline(cls, data: T, name: str = '') -> InlineIdentifier[T]:
        """Create an InlineIdentifier containing the given data.

        Args:
            data (T): The asset data.
            name (str, optional): The name of the asset. Defaults to ''.

        Returns:
            InlineIdentifier[T]: The created InlineIdentifier.
        """
        return InlineIdentifier(data=data, name=name)


class InlineIdentifier(Identifier[T], typing.Generic[T]):
    """An identifier that directly contains the asset data.
    """
    _data: T

    def __init__(self, data: T, name: str = '') -> None:
        super().__init__(name=name, domain='')
        self._data = data

    def serialize(self) -> str:
        raise TypeError('InlineIdentifier cannot be serialized')

    def load(self) -> T:
        return self._data
