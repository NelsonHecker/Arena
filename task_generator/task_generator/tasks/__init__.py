import typing
from collections.abc import Iterable

import rosgraph_msgs.msg as rosgraph_msgs
from arena_rclpy_mixins.shared import Namespace
from arena_simulation_setup.tree import Identifier

from task_generator import NodeInterface
from task_generator.constants import Constants
from task_generator.manager.environment_manager import EnvironmentManager
from task_generator.manager.robot_manager import RobotManager
from task_generator.manager.robot_manager.robots_manager_ros import RobotsManager
from task_generator.manager.world_manager.world_manager_ros import WorldManager


def identifier_to_available(
    identifier: typing.Type[Identifier], **kwargs
) -> Iterable[str]:
    yield from (identifier.shortname for identifier in identifier.listall(**kwargs))


class Props_Manager:
    environment_manager: EnvironmentManager
    robots_manager: RobotsManager
    world_manager: WorldManager

    @property
    def robots(self) -> dict[str, RobotManager]:
        return self.robots_manager.managers


class Props_(Props_Manager):
    clock: rosgraph_msgs.Clock

    def _clock_callback(self, clock: rosgraph_msgs.Clock):
        self.clock = clock


class Namespaced:
    _namespace: typing.ClassVar[Namespace] = Namespace("").ParamNamespace()

    @classmethod
    def namespace(cls, *path: str) -> Namespace:
        return cls._namespace(*path)


class TaskMode(NodeInterface, Namespaced):
    _PROPS: Props_

    def __init__(self, *args, props: Props_, **kwargs):
        super().__init__(*args, **kwargs)
        self._PROPS = props


from .task import _TaskRegistry  # noqa


def declare_modules():
    @_TaskRegistry.register_module(Constants.TaskMode.TM_Module.BENCHMARK)
    def _benchmark():
        from .modules.benchmark import Mod_Benchmark

        return Mod_Benchmark

    @_TaskRegistry.register_module(Constants.TaskMode.TM_Module.CLEAR_FORBIDDEN_ZONES)
    def _clear_forbidden_zones():
        from .modules.clear_forbidden_zones import Mod_ClearForbiddenZones

        return Mod_ClearForbiddenZones

    @_TaskRegistry.register_module(Constants.TaskMode.TM_Module.RVIZ_UI)
    def _rviz_ui():
        from .modules.rviz_ui import Mod_OverrideRobot

        return Mod_OverrideRobot

    @_TaskRegistry.register_module(Constants.TaskMode.TM_Module.STAGED)
    def _staged():
        from .modules.staged import Mod_Staged

        return Mod_Staged


def declare_obstacles():
    @_TaskRegistry.register_obstacles(Constants.TaskMode.TM_Obstacles.PARAMETRIZED)
    def _parametrized():
        from .obstacles.parametrized import TM_Parametrized

        return TM_Parametrized

    @_TaskRegistry.register_obstacles(Constants.TaskMode.TM_Obstacles.RANDOM)
    def _random():
        from .obstacles.random import TM_Random

        return TM_Random

    @_TaskRegistry.register_obstacles(Constants.TaskMode.TM_Obstacles.SCENARIO)
    def _scenario():
        from .obstacles.scenario import TM_Scenario

        return TM_Scenario

    @_TaskRegistry.register_obstacles(Constants.TaskMode.TM_Obstacles.ENVIRONMENT)
    def _environment():
        from .obstacles.environment import TM_Environment

        return TM_Environment


def declare_robots():
    @_TaskRegistry.register_robots(Constants.TaskMode.TM_Robots.EXPLORE)
    def _explore():
        from .robots.explore import TM_Explore

        return TM_Explore

    @_TaskRegistry.register_robots(Constants.TaskMode.TM_Robots.GUIDED)
    def _guided():
        from .robots.guided import TM_Guided

        return TM_Guided

    @_TaskRegistry.register_robots(Constants.TaskMode.TM_Robots.RANDOM)
    def _random():
        from .robots.random import TM_Random

        return TM_Random

    @_TaskRegistry.register_robots(Constants.TaskMode.TM_Robots.SCENARIO)
    def _scenario():
        from .robots.scenario import TM_Scenario

        return TM_Scenario


declare_modules()
declare_obstacles()
declare_robots()
