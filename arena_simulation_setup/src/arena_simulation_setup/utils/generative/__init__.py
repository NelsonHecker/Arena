import abc
import enum
import random
import typing

import pydantic

from arena_simulation_setup.tree.World import LevelDescription


class WorldGeneratorType(enum.Enum):
    """
    Enum for world generator types.
    """

    EMPTY = "empty"
    HALLWAY = "hallway"


class BaseConfiguration(pydantic.BaseModel):
    width: float = 15.0  # m
    height: float = 15.0  # m
    resolution: float = 0.05  # m / px
    wall_gap: float = 0.05  # gap between adjacent walls


class WorldGeneratorImpl(abc.ABC):
    """
    Abstract base class for world generators.
    """

    config: BaseConfiguration
    rng: random.Random

    def __init__(self, configuration: dict, rng: random.Random) -> None:
        super().__init__()
        self.rng = rng
        self.configure(configuration)

    @abc.abstractmethod
    def configure(self, configuration: dict): ...

    @abc.abstractmethod
    def compute(self) -> LevelDescription: ...


class WorldGenerator:
    __registry: typing.ClassVar[dict[WorldGeneratorType, typing.Callable[[], type[WorldGeneratorImpl]]]] = {}
    _active: WorldGeneratorImpl

    @classmethod
    def register(cls, name: WorldGeneratorType) -> typing.Callable[[typing.Callable[[], type[WorldGeneratorImpl]]], typing.Callable[[], type[WorldGeneratorImpl]]]:
        def wrap(impl: typing.Callable[[], type[WorldGeneratorImpl]]) -> typing.Callable[[], type[WorldGeneratorImpl]]:
            cls.__registry[name] = impl
            return impl

        return wrap

    @classmethod
    def available(cls) -> list[WorldGeneratorType]:
        return list(cls.__registry.keys())

    @classmethod
    def config_model(cls, generator: WorldGeneratorType) -> type[BaseConfiguration]:
        if generator not in cls.__registry:
            raise ValueError(f"Generator {generator} has no implementation")
        return cls.__registry[generator]().Configuration

    def compute(self) -> LevelDescription:
        return self._active.compute()

    def update_generator(self, generator: WorldGeneratorType, configuration: dict, seed: int = -1):
        if generator not in self.__registry:
            raise ValueError(f"Generator {generator} has no implementation")
        rng = random.Random(seed if seed >= 0 else None)  # negative seed = nondeterministic
        self._active: WorldGeneratorImpl = self.__registry[generator]()(configuration, rng)

    def __init__(self, generator: WorldGeneratorType, configuration: dict, seed: int = -1):
        self.update_generator(generator, configuration, seed)


@WorldGenerator.register(WorldGeneratorType.EMPTY)
def lazy_Empty() -> type[WorldGeneratorImpl]:
    from .empty import WorldGeneratorEmpty

    return WorldGeneratorEmpty


@WorldGenerator.register(WorldGeneratorType.HALLWAY)
def lazy_Hallway() -> type[WorldGeneratorImpl]:
    from .hallway import WorldGeneratorHallway

    return WorldGeneratorHallway
