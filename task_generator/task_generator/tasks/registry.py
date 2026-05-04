import typing
from collections.abc import Iterable

from arena_rclpy_mixins.shared import Namespace
from arena_simulation_setup.tree import Identifier

from task_generator.constants import Constants
from task_generator.tasks.mode import Namespaced

if typing.TYPE_CHECKING:
    from arena_rclpy_mixins.ROSParamServer import ROSParamServer

    from task_generator.tasks.modules import TM_Module
    from task_generator.tasks.obstacles import TM_Obstacles
    from task_generator.tasks.robots import TM_Robots


def identifier_to_available(identifier: type[Identifier], **kwargs: object) -> Iterable[str]:
    yield from (identifier.shortname for identifier in identifier.listall(**kwargs))


_ObstacleLoader = typing.Callable[[], "type[TM_Obstacles]"]
_RobotsLoader = typing.Callable[[], "type[TM_Robots]"]
_ModuleLoader = typing.Callable[[], "type[TM_Module]"]
_SchemaFn = typing.Callable[["ROSParamServer", Namespace], None]


class _TaskRegistry(Namespaced):
    registry_obstacles: dict[Constants.TaskMode.TM_Obstacles, tuple[_ObstacleLoader, Namespace, _SchemaFn | None]] = {}
    registry_robots: dict[Constants.TaskMode.TM_Robots, tuple[_RobotsLoader, Namespace, _SchemaFn | None]] = {}
    registry_module: dict[Constants.TaskMode.TM_Module, tuple[_ModuleLoader, Namespace, _SchemaFn | None]] = {}

    _namespace: Namespace = Namespaced._namespace('task')

    @classmethod
    def register_obstacles(
        cls,
        name: Constants.TaskMode.TM_Obstacles,
        schema: _SchemaFn | None = None,
    ) -> typing.Callable[[_ObstacleLoader], _ObstacleLoader]:
        def inner_wrapper(loader: _ObstacleLoader) -> _ObstacleLoader:
            assert name not in cls.registry_obstacles, f"TaskMode '{name}' for obstacles already exists!"
            cls.registry_obstacles[name] = (loader, cls._namespace(name.value), schema)
            return loader

        return inner_wrapper

    @classmethod
    def register_robots(
        cls,
        name: Constants.TaskMode.TM_Robots,
        schema: _SchemaFn | None = None,
    ) -> typing.Callable[[_RobotsLoader], _RobotsLoader]:
        def inner_wrapper(loader: _RobotsLoader) -> _RobotsLoader:
            assert name not in cls.registry_robots, f"TaskMode '{name}' for robots already exists!"
            cls.registry_robots[name] = (loader, cls._namespace(name.value), schema)
            return loader

        return inner_wrapper

    @classmethod
    def register_module(
        cls,
        name: Constants.TaskMode.TM_Module,
        schema: _SchemaFn | None = None,
    ) -> typing.Callable[[_ModuleLoader], _ModuleLoader]:
        def inner_wrapper(loader: _ModuleLoader) -> _ModuleLoader:
            assert name not in cls.registry_module, f"TaskMode '{name}' for module already exists!"
            cls.registry_module[name] = (loader, cls._namespace(name.value), schema)
            return loader

        return inner_wrapper

    @classmethod
    def walk_schemas(cls, node: "ROSParamServer") -> None:
        for _key, (_loader, ns, schema) in cls.registry_module.items():
            if schema is not None:
                schema(node, ns)
        for _key, (_loader, ns, schema) in cls.registry_obstacles.items():
            if schema is not None:
                schema(node, ns)
        for _key, (_loader, ns, schema) in cls.registry_robots.items():
            if schema is not None:
                schema(node, ns)


# Mode registrations live in each mode's own __init__.py (e.g.
# `tasks/obstacles/random/__init__.py` calls `_TaskRegistry.register_obstacles(...)`).
# PROMPT is registered per-simulator via BaseHumanSimulator._register_task_modes;
# each simulator provides its own TM_Prompt subclass.
