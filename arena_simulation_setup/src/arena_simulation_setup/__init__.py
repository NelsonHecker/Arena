from __future__ import annotations

import enum
import itertools
import os
import typing
from collections.abc import Iterator, Sequence

from arena_simulation_setup.utils.cattrs import Idempotent

ass_dir: str
ab_dir: str

try:
    import ament_index_python.packages
    ass_dir = ament_index_python.packages.get_package_share_directory('arena_simulation_setup')
    ab_dir = ament_index_python.packages.get_package_share_directory('arena_bringup')
except ImportError:
    ass_dir = os.environ.get('ass_dir', '')
    ab_dir = os.environ.get('ab_dir', '')

T = typing.TypeVar('T', bound='ProviderBase')


class ProviderBase(Idempotent):

    # Class Methods: Provider
    _sources: typing.ClassVar[Sources]

    @classmethod
    def bind(cls: typing.Type[T], path: Sources) -> typing.Type[T]:
        return typing.cast(
            typing.Type[T],
            type('Bound' + cls.__name__, (cls,), dict(_sources=path))
        )

    @classmethod
    def _listdir(cls, path: str) -> Sequence[str]:
        if not os.path.exists(path):
            return ()
        return tuple(sorted(f for f in os.listdir(path) if not f.startswith('.')))

    @classmethod
    def list(cls) -> Sequence[str]:
        return tuple(sorted(set(itertools.chain(*map(cls._listdir, cls._sources)))))

    @classmethod
    def base_dir(cls) -> Sources:
        # TODO rename
        return cls._sources

    @classmethod
    def resolve(cls, *path: str, fn: typing.Callable[[str], bool] | None = None) -> str | None:
        if fn is None:
            fn = os.path.exists
        return next(
            filter(
                fn,
                (os.path.join(x, *path) for x in cls._sources)
            ),
            None
        )

    # Instance Methods: Provider

    def __init__(self, name: str) -> None:
        if hasattr(self, '_name'):
            return
        if not isinstance(name, str):
            raise TypeError(f'Expected name to be str, got {type(name)}')
        self._name = name

    @property
    def name(self) -> str:
        return self._name

    @property
    def path(self) -> str:
        resolved = self.resolve(self.name)
        if resolved is None:
            raise FileNotFoundError(f"Could not find {self.name} in {self._sources}")
        return resolved


class SourcesContainer(dict):
    """
    Container for source directories
    """
    class Keys(enum.Enum):
        GLOBAL = 'global_dir'
        WORLD = 'world_dir'

    def override(self, **overrides: str) -> SourcesContainer:
        class OverridenSourcesContainer(SourcesContainer):
            def __getitem__(inner_self, key: str) -> str:
                if key in overrides:
                    return overrides[key]
                return self.__getitem__(key)
        return OverridenSourcesContainer(self)

    def __iter__(self) -> Iterator[str]:
        return filter(None, (self.get(SourcesContainer.Keys.WORLD), self.get(SourcesContainer.Keys.GLOBAL)))


class Sources:
    """
    Dynamic source directories
    """

    def __iter__(self) -> Iterator[str]:
        for x in self.__sources:
            yield os.path.join(x, self.__suffix)

    def __repr__(self) -> str:
        return f"Sources({list(self)})"

    def __hash__(self) -> int:
        return hash((self.__suffix, *self.__sources))

    def __init__(self, sources: SourcesContainer, suffix: str = '') -> None:
        self.__sources: SourcesContainer = sources
        self.__suffix: str = suffix

    def override(self, **overrides: str) -> Sources:
        return Sources(self.__sources.override(**overrides), self.__suffix)

    def __call__(self, *suffix: str) -> Sources:
        return Sources(self.__sources, os.path.join(self.__suffix, *suffix))

    @property
    def global_dir(self) -> str:
        return os.path.join(self.__sources.get(SourcesContainer.Keys.GLOBAL), self.__suffix)

    @property
    def world_dir(self) -> str | None:
        world_dir = self.__sources.get(SourcesContainer.Keys.WORLD)
        if world_dir is None:
            return None
        return os.path.join(world_dir, self.__suffix)

    # tmp

    @property
    def sources(self) -> SourcesContainer:
        return self.__sources


_ass_sources_container = SourcesContainer({SourcesContainer.Keys.GLOBAL: ass_dir})


def set_world_dir(world_dir: str | None) -> None:
    """
    Set the world directory dynamic source resolution.
    """
    _ass_sources_container[SourcesContainer.Keys.WORLD] = world_dir


ass_sources = Sources(_ass_sources_container)
