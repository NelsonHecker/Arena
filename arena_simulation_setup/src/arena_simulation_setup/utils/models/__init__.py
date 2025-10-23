from __future__ import annotations

import abc
import enum
import functools
import sys
from collections.abc import Callable, Collection, Set
from pathlib import Path
from typing import Optional, Type, overload

import attrs

from arena_simulation_setup.tree import ProviderProtocol
from arena_simulation_setup.utils.cattrs import Serializable, converter

# TODO deprecate this in favor of Model.EMPTY


def _EMPTY_LOADER(*_, **__) -> Model:

    return Model(
        type=ModelType.UNKNOWN, name="", description="", path=Path('/dev/null')
    )


EMPTY_LOADER = _EMPTY_LOADER


class ModelType(enum.Enum):
    UNKNOWN = ""
    URDF = "urdf"
    SDF = "sdf"
    YAML = "yaml"
    USD = "usd"


@attrs.frozen()
class Model:
    type: ModelType
    name: str
    description: str
    path: Path

    @property
    def mapper(self) -> Callable[[Model], Model]:
        """
        Returns a (Model)->Model mapper that simply returns this model
        """
        return lambda m: self

    def replace(self, **kwargs) -> Model:
        """
        Wrapper for attrs.evolve
        **kwargs: properties to replace
        """
        return attrs.evolve(self, **kwargs)


class ModelProvider(abc.ABC):
    @classmethod
    def provides(cls, model_type: ModelType) -> Type[ModelProvider]:
        return type(cls.__name__, (cls,), {'type': classmethod(lambda cls: model_type)})

    @classmethod
    @abc.abstractmethod
    def type(cls) -> ModelType:
        """
        return ModelType handled by this loader
        """

    @classmethod
    @abc.abstractmethod
    def load(cls, model_dir: Path, model: str, loader_args: dict | None) -> Model | None:
        return None

    @classmethod
    @abc.abstractmethod
    def convertable(cls) -> Collection[ModelType]:
        """
        return collection of model types convertable
        """
        return ()

    @classmethod
    @abc.abstractmethod
    def convert(cls, model_dir: Path, model: Model, loader_args: dict | None) -> Model | None:
        return None


class ModelWrapper(Serializable):

    _get: Callable[[Collection[ModelType], dict], Model]
    _name: str
    _override: dict[ModelType, tuple[bool, Callable[..., Model]]]
    _loader: object

    def loader_matches(self, loader: object) -> bool:
        return self._loader is loader

    def __repr__(self) -> str:
        return f"ModelWrapper(name={self.name}, loader={self._loader})"

    def serialize(self) -> str:
        return self.name

    def __init__(
        self,
        name: str,
        callback: Callable[[Collection[ModelType], dict], Model] | None = None,
        loader: ModelProvider | None = None,
    ):
        """
        Create new ModelWrapper
        @name: Name of the ModelWrapper (should match the underlying Models)
        """
        self._loader = loader
        if self._loader is None:
            self._loader = object()
        if callback is None:
            callback = EMPTY_LOADER
        self._name = name
        self._get = callback
        self._override = {}

    def clone(self) -> ModelWrapper:
        """
        Clone (shallow copy) this ModelWrapper instance
        """
        clone = ModelWrapper(self.name, self._get, loader=self._loader)
        clone._override = self._override
        return clone

    def override(
        self,
        model_type: ModelType,
        override: Callable[[Model], Model],
        noload: bool = False,
        name: Optional[str] = None,
    ) -> ModelWrapper:
        """
        Create new ModelWrapper with an overridden ModelType callback
        @model_type: Which ModelType to override
        @override: Mapping function (Model)->Model which replaces the loaded model with a new one
        @noload: (default: False) If True, indicates that the original Model is not used by the override function and a dummy Model can be passed to it instead
        @name: (optional) If set, overrides name of ModelWrapper
        """
        clone = self.clone()
        clone._loader = object()
        clone._override = {**self._override, model_type: (noload, override)}

        if name is not None:
            clone._name = name

        return clone

    @overload
    def get(
        self,
        only: ModelType,
        *,
        loader_args: dict | None = None,
        **kwargs
    ) -> Model:
        """
            load specific model
            @only: single accepted ModelType
        """

    @overload
    def get(
        self,
        only: Collection[ModelType],
        *,
        loader_args: dict | None = None,
        **kwargs
    ) -> Model:
        """
            load specific model from collection
            @only: collection of acceptable ModelTypes
        """

    @overload
    def get(
        self,
        *,
        loader_args: dict | None = None,
        **kwargs
    ) -> Model:
        """
            load any available model
        """

    def get(
        self,
        only: ModelType | Collection[ModelType] | None = None,
        *,
        loader_args: dict | None = None,
        **kwargs,
    ) -> Model:
        if only is None:
            only = self._override.keys()

        if loader_args is None:
            loader_args = {}

        args: LoaderArgs = LoaderArgs(loader_args)  # make hashable

        if isinstance(only, ModelType):
            return self.get([only])

        for model_type in only:
            if model_type in self._override:
                noload, mapper = self._override[model_type]

                if noload:
                    return mapper(EMPTY_LOADER())

                return mapper(self._get([model_type], args), **kwargs)

        return self._get(only, args)

    @property
    def name(self) -> str:
        """
        get name
        """
        return self._name

    @staticmethod
    def Constant(name: str, models: dict[ModelType, Model]) -> ModelWrapper:
        """
        Create new ModelWrapper from a dict of already existing models
        @name: name of model
        @models: dictionary of ModelType->Model mappings
        """

        def get(only: Collection[ModelType], loader_args: dict | None) -> Model:
            if not len(only):
                only = list(models.keys())

            for model_type in only:
                if model_type in models:
                    return models[model_type]
            raise LookupError(
                f"no matching model found for {name} (available: {list(models.keys())}, requested: {list(only)})"
            )

        return ModelWrapper(name, get)

    @staticmethod
    def from_model(model: Model) -> ModelWrapper:
        """
        Create new ModelWrapper containing a single existing Model
        @model: Model to wrap
        """
        return ModelWrapper.Constant(
            name=model.name,
            models={model.type: model}
        )

    @staticmethod
    def EMPTY() -> ModelWrapper:
        wrapper = ModelWrapper("__EMPTY", EMPTY_LOADER)
        return wrapper


converter.register_unstructure_hook(ModelWrapper, ModelWrapper.serialize)


class LoadersT(tuple[Type[ModelProvider], ...]):
    def __hash__(self) -> int:
        return hash(tuple(map(id, self)))


class LoaderArgs(dict):
    def __hash__(self) -> int:
        return hash(str(self))


class ModelLoader:

    def __init__(self, provider: Type[ProviderProtocol], loaders: Collection[Type[ModelProvider]]) -> None:
        self.__provider: Type[ProviderProtocol] = provider
        self.__loaders: LoadersT = LoadersT(loaders)

    @functools.cache
    @staticmethod
    def _match_loaders(loaders: LoadersT, model_type: ModelType) -> LoadersT:
        return LoadersT(loader for loader in loaders if model_type == loader.type())

    @property
    def models(self) -> Set[str]:
        return set(self.__provider.list())

    def bind(self, model: str) -> ModelWrapper:
        return ModelWrapper(
            name=model,
            callback=functools.partial(self._load_safe, model),
            loader=self,
        )

    @functools.lru_cache(maxsize=128)
    @staticmethod
    def _load_cached(loaders: LoadersT, provider: Type[ProviderProtocol], model: str, model_type: ModelType, loader_args: LoaderArgs | None) -> Model | None:
        for loader in ModelLoader._match_loaders(loaders, model_type):
            model_dir = provider(model).resolve(model)
            if (hit := loader.load(model_dir, model, loader_args)) is not None:
                return hit
        return None

    @functools.lru_cache(maxsize=128)
    @staticmethod
    def _convert_cached(loaders: LoadersT, provider: Type[ProviderProtocol], model: str, model_type: ModelType, loader_args: LoaderArgs | None) -> Model | None:
        for loader in ModelLoader._match_loaders(loaders, model_type):
            for convertable in loader.convertable():
                model_dir = provider(model).resolve(model)
                if (base := ModelLoader._load_cached(loaders, provider, model, convertable, loader_args)) is not None:
                    if (hit := loader.convert(model_dir, base, loader_args)) is not None:
                        return hit
        return None

    def _load(self, model: str, only: Collection[ModelType], loader_args: dict | None) -> Model | None:
        if not only:
            only = [loader.type() for loader in self.__loaders]
        if loader_args:
            loader_args = LoaderArgs(loader_args)  # hashable

        for model_type in only:  # try to load
            if (hit := ModelLoader._load_cached(self.__loaders, self.__provider, model, model_type, loader_args)) is not None:
                return hit

        for model_type in only:  # try to convert
            if (hit := ModelLoader._convert_cached(self.__loaders, self.__provider, model, model_type, loader_args)) is not None:
                return hit

        return None

    def _load_safe(self, model: str, only: Collection[ModelType], loader_args: dict | None) -> Model:
        loaded = self._load(model, only, loader_args)
        if loaded is not None:
            return loaded

        print(f"no model {model} among {only} found in {self.__provider(model).path} and could not be converted", file=sys.stderr)
        return Model(
            type=ModelType.UNKNOWN,
            name=model,
            description="",
            path=Path("/dev/null"),
        )
