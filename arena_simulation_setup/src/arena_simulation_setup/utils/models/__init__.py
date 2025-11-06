from __future__ import annotations

import abc
import enum
from collections.abc import Callable, Collection
from pathlib import Path
from typing import Optional, Type, overload
import typing

import attrs

from arena_simulation_setup.utils.cattrs import Parseable, Serializable, converter


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

    @classmethod
    def EMPTY(cls) -> Model:
        return Model(
            type=ModelType.UNKNOWN,
            name="__EMPTY",
            description="Empty Model",
            path=Path("/dev/null"),
        )


class ModelProvider(abc.ABC):
    @classmethod
    def provides(cls, model_type: ModelType) -> Type[ModelProvider]:
        return type(cls.__name__, (cls,), {'type': classmethod(lambda cls: model_type)})

    @classmethod
    def asdict(cls, model_dir: Path, model: str) -> dict[ModelType, Callable[[dict], Model]]:
        return {
            cls.type(): lambda loader_args: cls.load(model_dir, model, loader_args)
        }

    @classmethod
    @abc.abstractmethod
    def type(cls) -> ModelType:
        """
        return ModelType handled by this loader
        """

    @classmethod
    @abc.abstractmethod
    def load(cls, model_dir: Path, model: str, loader_args: dict | None) -> Model:
        raise FileNotFoundError(f"Model {model} not found in {model_dir}")

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


class ModelWrapper(Parseable, Serializable):

    _loaders: dict[ModelType, Callable[[dict], Model]]
    _name: str

    def __repr__(self) -> str:
        return f"ModelWrapper(name={self.name}, loaders={list(self._loaders.keys())})"

    @classmethod
    def parse(cls, value: typing.Any) -> ModelWrapper:
        if isinstance(value, str):
            return cls.EMPTY()
        if isinstance(value, cls):
            return value
        raise TypeError(f"Cannot parse ModelWrapper from {value!r}")

    def serialize(self) -> str:
        return self.name

    def __init__(
        self,
        name: str,
        loaders: dict[ModelType, Callable[[dict], Model]],
    ):
        """Create a new ModelWrapper

        Args:
            name (str): Name of the ModelWrapper (should match the underlying Models)
            loaders (dict[ModelType, Callable[[dict], Model]]): Functions to call to get the model for each ModelType.
        """
        self._name = name
        self._loaders = loaders

    def clone(self) -> ModelWrapper:
        """
        Clone (shallow copy) this ModelWrapper instance
        """
        clone = ModelWrapper(self.name, self._loaders)
        return clone

    def override(
        self,
        model_type: ModelType,
        override: Callable[[Model], Model],
        noload: bool = False,
        name: Optional[str] = None,
    ) -> ModelWrapper:
        """Create a new ModelWrapper with an overridden loader for a specific ModelType

        Args:
            model_type (ModelType): The ModelType to override.
            override (Callable[[Model], Model]): The function to call to get the overridden model.
            noload (bool, optional): If True, indicates that the original Model is not used by the override function and a dummy Model can be passed to it instead. Defaults to False.
            name (Optional[str], optional): If set, overrides name of ModelWrapper. Defaults to None.

        Returns:
            ModelWrapper: A new ModelWrapper with the overridden loader.
        """
        old_loader = self._loaders.get(model_type)
        if old_loader is None:
            def old_loader(): raise ValueError(f"No loader for model type {model_type}")

        def new_loader(loader_args: dict | None) -> Model:
            if noload:
                return override(Model.EMPTY())
            return override(old_loader(loader_args))

        self._loaders[model_type] = new_loader
        return self

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
            only = self._loaders.keys()
        if isinstance(only, ModelType):
            only = [only]

        if loader_args is None:
            loader_args = {}

        args: LoaderArgs = LoaderArgs(loader_args)  # make hashable

        for model_type in only:
            loader = self._loaders.get(model_type)
            if loader is not None:
                model = loader(args)
                if model is not None:
                    return model
        raise FileNotFoundError(f'Could not load model of type(s) {only} in ModelWrapper {self.name}')

    @property
    def name(self) -> str:
        """
        get name
        """
        return self._name

    @classmethod
    def Constant(cls, name: str, models: dict[ModelType, Model]) -> ModelWrapper:
        """
        Create new ModelWrapper from a dict of already existing models
        @name: name of model
        @models: dictionary of ModelType->Model mappings
        """

        return ModelWrapper(
            name,
            {model_type: (lambda _: model) for model_type, model in models.items()}
        )

    @classmethod
    def from_model(cls, model: Model) -> ModelWrapper:
        """
        Create new ModelWrapper containing a single existing Model
        @model: Model to wrap
        """
        return ModelWrapper.Constant(
            name=model.name,
            models={model.type: model}
        )

    @classmethod
    def EMPTY(cls) -> ModelWrapper:
        wrapper = ModelWrapper(
            "__EMPTY",
            {t: lambda _: Model.EMPTY() for t in ModelType}
        )
        return wrapper


converter.register_unstructure_hook(ModelWrapper, ModelWrapper.serialize)


class LoadersT(tuple[Type[ModelProvider], ...]):
    def __hash__(self) -> int:
        return hash(tuple(map(id, self)))


class LoaderArgs(dict):
    def __hash__(self) -> int:
        return hash(str(self))
