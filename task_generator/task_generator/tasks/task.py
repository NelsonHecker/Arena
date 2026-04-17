import asyncio
import typing
from collections.abc import Sequence

import rclpy
import rclpy.publisher
import std_msgs.msg as std_msgs
from arena_rclpy_mixins.ROSParamServer import ROSParamServer
from arena_rclpy_mixins.shared import DefaultParameter

from task_generator import NodeInterface
from task_generator.constants import Constants
from task_generator.manager.environment_manager import EnvironmentManager
from task_generator.manager.robot_manager import RobotsManager
from task_generator.manager.world_manager.world_manager_ros import WorldManager
from task_generator.shared import Pose
from task_generator.tasks.registry import _TaskRegistry
from task_generator.tasks.robots.composite import (
    TM_Composite,
    _scoped_ctx,
    get_extra_tm_loader,
)
from task_generator.tasks.robots.fleet_manager import FleetManager, TaskModeSpec
from task_generator.tasks.robots.request import TaskKind, TaskRequest

from . import TaskContext
from .obstacles import TM_Obstacles
from .robots import TM_Robots

# import training.srv as training_srvs


class Task(_TaskRegistry, NodeInterface):
    """Task class that comibnes task modes.
    """
    last_reset_time: int

    TOPIC_RESET_START = "reset_start"
    TOPIC_RESET_END = "reset_end"
    PARAM_RESETTING = "resetting"

    @classmethod
    def declare_parameters(cls, node: ROSParamServer):
        node.ROSParam[bool](cls.PARAM_RESETTING, True)

    __reset_start: rclpy.publisher.Publisher
    __reset_end: rclpy.publisher.Publisher
    __reset_mutex: bool

    PARAM_TM_ROBOTS = "tm_robots"
    PARAM_TM_OBSTACLES = "tm_obstacles"

    __param_tm_robots: Constants.TaskMode.TM_Robots
    __param_tm_obstacles: Constants.TaskMode.TM_Obstacles

    __tm_robots: TM_Robots
    __tm_obstacles: TM_Obstacles

    _force_reset: bool

    @classmethod
    async def create(
        cls,
        *,
        environment_manager: EnvironmentManager,
        robots_manager: RobotsManager,
        world_manager: WorldManager,
        modules: Sequence[Constants.TaskMode.TM_Module] = (),
        **kwargs,
    ):
        self = cls(
            environment_manager=environment_manager,
            robots_manager=robots_manager,
            world_manager=world_manager,
            modules=modules,
            **kwargs,
        )
        await self.robots_manager.set_up()
        return self

    _ctx: TaskContext

    @property
    def environment_manager(self) -> EnvironmentManager:
        return self._ctx.environment_manager

    @property
    def robots_manager(self) -> RobotsManager:
        return self._ctx.robots_manager

    @property
    def world_manager(self) -> WorldManager:
        return self._ctx.world_manager

    @property
    def robots(self):
        return self._ctx.robots

    def __init__(
        self,
        *args,
        environment_manager: EnvironmentManager,
        robots_manager: RobotsManager,
        world_manager: WorldManager,
        modules: Sequence[Constants.TaskMode.TM_Module] = (),
        **kwargs,
    ):
        super().__init__(*args, **kwargs)

        self._force_reset = False

        self._ctx = TaskContext(
            environment_manager=environment_manager,
            robots_manager=robots_manager,
            world_manager=world_manager,
        )

        self._train_mode = self.node.get_parameter_or("/train_mode", DefaultParameter(False)).value

        self.__reset_start = self.node.create_publisher(std_msgs.Empty, 'reset_start', 1)
        self.__reset_end = self.node.create_publisher(std_msgs.Empty, 'reset_end', 1)
        self.__reset_mutex = False

        self.last_reset_time = 0

        self.__param_tm_obstacles = None  # type: ignore
        self.__param_tm_robots = None  # type: ignore
        self._logger.info('initing modules')
        self.__modules = []
        for module in modules:
            loader, ns = self.registry_module[module]
            self.__modules.append(loader()(ctx=self._ctx, namespace=ns, task=self, node=self.node))

        if self._train_mode:
            self.set_tm_robots(Constants.TaskMode.TM_Robots(self.node.conf.TaskMode.TM_ROBOTS.value))
            self.set_tm_obstacles(Constants.TaskMode.TM_Obstacles(self.node.conf.TaskMode.TM_OBSTACLES.value))

    def set_tm_robots(self, tm_robots: Constants.TaskMode.TM_Robots):
        assert tm_robots in self.registry_robots, f"TaskMode '{tm_robots}' for robots is not registered!"
        loader, ns = self.registry_robots[tm_robots]
        self.__tm_robots = loader()(ctx=self._ctx, namespace=ns, node=self.node)
        self.__param_tm_robots = tm_robots

    def set_tm_robots_composite(
        self,
        specs: typing.Sequence[TaskModeSpec],
    ) -> None:
        """Bind a multi-TM composite task mode via FleetManager allocation."""
        if not specs:
            raise ValueError("task_modes list is empty")

        allocation = FleetManager.match(
            list(specs),
            self._ctx.robots.values(),
        )

        sub_modes: list[TM_Robots] = []
        for spec, robots in allocation.items():
            # Resolve the TM loader via the standard TaskMode enum;
            # fall back to the composite module's extra registry for TM_Null.
            loader = None
            ns = None
            try:
                enum_key = Constants.TaskMode.TM_Robots(spec.kind)
            except ValueError:
                enum_key = None
            if enum_key is not None and enum_key in self.registry_robots:
                loader, ns = self.registry_robots[enum_key]
            else:
                extra = get_extra_tm_loader(spec.kind)
                if extra is None:
                    raise KeyError(
                        f"task_mode kind {spec.kind!r} is not registered"
                    )
                loader = extra
                ns = _TaskRegistry._namespace(spec.kind)

            scoped = _scoped_ctx(self._ctx, (r.name for r in robots))
            sub_modes.append(
                loader()(ctx=scoped, namespace=ns, node=self.node)
            )

        self.__tm_robots = TM_Composite(
            ctx=self._ctx,
            namespace=_TaskRegistry._namespace("composite"),
            node=self.node,
            sub_modes=sub_modes,
        )
        # No single enum value applies; sentinel prevents the
        # new_tm_robots != __param_tm_robots comparison in _reset_task
        # from retriggering a rebind.
        self.__param_tm_robots = None  # type: ignore[assignment]

    def set_tm_obstacles(
            self, tm_obstacles: Constants.TaskMode.TM_Obstacles):
        assert tm_obstacles in self.registry_obstacles, f"TaskMode '{tm_obstacles}' for obstacles is not registered!"
        loader, ns = self.registry_obstacles[tm_obstacles]
        self.__tm_obstacles = loader()(ctx=self._ctx, namespace=ns, node=self.node)
        self.__param_tm_obstacles = tm_obstacles

    async def _reset_task(self, **kwargs):
        try:
            self.__reset_start.publish(std_msgs.Empty())

            await self.robots_manager.set_up()

            if not self._train_mode:
                if (
                    new_tm_robots := self.node.conf.TaskMode.TM_ROBOTS.value
                ) != self.__param_tm_robots:
                    self.set_tm_robots(new_tm_robots)

                if (
                    new_tm_obstacles := self.node.conf.TaskMode.TM_OBSTACLES.value
                ) != self.__param_tm_obstacles:
                    self.set_tm_obstacles(new_tm_obstacles)

            for module in self.__modules:
                module.before_reset()

            await self.__tm_robots.reset(**kwargs)
            obstacles, dynamic_obstacles = await self.__tm_obstacles.reset(**kwargs)

            async def respawn():
                await asyncio.gather(
                    self.environment_manager.spawn_dynamic_obstacles(dynamic_obstacles),
                    self.environment_manager.spawn_obstacles(obstacles),
                )

            await self.environment_manager.respawn(respawn)

            for module in self.__modules:
                module.after_reset()

            self.last_reset_time = self.node.sim_time.sec

        except Exception as e:
            self.node.get_logger().error(repr(e))
            raise

        finally:
            self.__reset_end.publish(std_msgs.Empty())

    async def reset(self, **kwargs):
        self._force_reset = False
        await self._reset_task(**kwargs)

    @property
    async def is_done(self) -> bool:
        return self._force_reset or await self.__tm_robots.done

    async def set_robot_position(self, pose: Pose):
        """Broadcast a teleport to all robots (back-compat shim for RViz / training UI)."""
        await self.__tm_robots.set_position(pose)

    async def set_robot_goal(self, pose: Pose):
        """Broadcast a goal to all robots (back-compat shim for RViz / training UI)."""
        await self.__tm_robots.set_goal(pose)

    async def submit_task(self, request: TaskRequest, robot_name: str) -> None:
        """Submit a typed task request to a specific robot; bypasses TM_Robots."""
        robot = self._ctx.robots[robot_name]
        await robot.submit_task(request)

    _TaskKindAlias = TaskKind  # keep TaskKind import live

    def force_reset(self):
        self._force_reset = True
