import typing
from collections.abc import Iterable

from arena_rclpy_mixins.shared import Namespace
from arena_simulation_setup.tree import Identifier

from task_generator.constants import Constants
from task_generator.tasks.mode import Namespaced

if typing.TYPE_CHECKING:
    from task_generator.tasks.modules import TM_Module
    from task_generator.tasks.obstacles import TM_Obstacles
    from task_generator.tasks.robots import TM_Robots


def identifier_to_available(identifier: type[Identifier], **kwargs: object) -> Iterable[str]:
    yield from (identifier.shortname for identifier in identifier.listall(**kwargs))


_ObstacleLoader = typing.Callable[[], "type[TM_Obstacles]"]
_RobotsLoader = typing.Callable[[], "type[TM_Robots]"]
_ModuleLoader = typing.Callable[[], "type[TM_Module]"]


class _TaskRegistry(Namespaced):
    registry_obstacles: dict[Constants.TaskMode.TM_Obstacles, tuple[_ObstacleLoader, Namespace]] = {}
    registry_robots: dict[Constants.TaskMode.TM_Robots, tuple[_RobotsLoader, Namespace]] = {}
    registry_module: dict[Constants.TaskMode.TM_Module, tuple[_ModuleLoader, Namespace]] = {}

    _namespace: Namespace = Namespaced._namespace('task')

    @classmethod
    def register_obstacles(cls, name: Constants.TaskMode.TM_Obstacles) -> typing.Callable[[_ObstacleLoader], _ObstacleLoader]:
        def inner_wrapper(loader: _ObstacleLoader) -> _ObstacleLoader:
            assert name not in cls.registry_obstacles, f"TaskMode '{name}' for obstacles already exists!"
            cls.registry_obstacles[name] = (loader, cls._namespace(name.value))
            return loader

        return inner_wrapper

    @classmethod
    def register_robots(cls, name: Constants.TaskMode.TM_Robots) -> typing.Callable[[_RobotsLoader], _RobotsLoader]:
        def inner_wrapper(loader: _RobotsLoader) -> _RobotsLoader:
            assert name not in cls.registry_robots, f"TaskMode '{name}' for robots already exists!"
            cls.registry_robots[name] = (loader, cls._namespace(name.value))
            return loader

        return inner_wrapper

    @classmethod
    def register_module(cls, name: Constants.TaskMode.TM_Module) -> typing.Callable[[_ModuleLoader], _ModuleLoader]:
        def inner_wrapper(loader: _ModuleLoader) -> _ModuleLoader:
            assert name not in cls.registry_module, f"TaskMode '{name}' for module already exists!"
            cls.registry_module[name] = (loader, cls._namespace(name.value))
            return loader

        return inner_wrapper


def declare_modules():
    @_TaskRegistry.register_module(Constants.TaskMode.TM_Module.BENCHMARK)
    def _benchmark() -> type:
        from .modules.benchmark import Mod_Benchmark

        return Mod_Benchmark

    @_TaskRegistry.register_module(Constants.TaskMode.TM_Module.CLEAR_FORBIDDEN_ZONES)
    def _clear_forbidden_zones() -> type:
        from .modules.clear_forbidden_zones import Mod_ClearForbiddenZones

        return Mod_ClearForbiddenZones

    @_TaskRegistry.register_module(Constants.TaskMode.TM_Module.RVIZ_UI)
    def _rviz_ui() -> type:
        from .modules.rviz_ui import Mod_OverrideRobot

        return Mod_OverrideRobot

    @_TaskRegistry.register_module(Constants.TaskMode.TM_Module.STAGED)
    def _staged() -> type:
        from .modules.staged import Mod_Staged

        return Mod_Staged


def declare_obstacles():
    @_TaskRegistry.register_obstacles(Constants.TaskMode.TM_Obstacles.PARAMETRIZED)
    def _parametrized() -> type:
        from .obstacles.parametrized import TM_Parametrized

        return TM_Parametrized

    @_TaskRegistry.register_obstacles(Constants.TaskMode.TM_Obstacles.RANDOM)
    def _random() -> type:
        from .obstacles.random import TM_Random

        return TM_Random

    @_TaskRegistry.register_obstacles(Constants.TaskMode.TM_Obstacles.SCENARIO)
    def _scenario() -> type:
        from .obstacles.scenario import TM_Scenario

        return TM_Scenario

    @_TaskRegistry.register_obstacles(Constants.TaskMode.TM_Obstacles.ENVIRONMENT)
    def _environment() -> type:
        from .obstacles.environment import TM_Environment

        return TM_Environment

    # PROMPT is registered per-simulator via BaseHumanSimulator._register_task_modes
    # (see hunav.py / arena_humansim.py); each provides its own TM_Prompt subclass.


def declare_robots():
    @_TaskRegistry.register_robots(Constants.TaskMode.TM_Robots.EXPLORE)
    def _explore() -> type:
        from .robots.explore import TM_Explore

        return TM_Explore

    @_TaskRegistry.register_robots(Constants.TaskMode.TM_Robots.GUIDED)
    def _guided() -> type:
        from .robots.guided import TM_Guided

        return TM_Guided

    @_TaskRegistry.register_robots(Constants.TaskMode.TM_Robots.RANDOM)
    def _random() -> type:
        from .robots.random import TM_Random

        return TM_Random

    @_TaskRegistry.register_robots(Constants.TaskMode.TM_Robots.SCENARIO)
    def _scenario() -> type:
        from .robots.scenario import TM_Scenario

        return TM_Scenario


declare_modules()
declare_obstacles()
declare_robots()
