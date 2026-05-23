import asyncio
import typing
import uuid

from arena_rclpy_mixins.ROSParamServer import ROSParamT

from task_generator.shared import Pose
from task_generator.shared import Robot as RobotEntity
from task_generator.tasks.mode import TaskMode
from task_generator.tasks.robots._placement import random_placement
from task_generator.tasks.robots.request import GoToPhase, TaskRequest

from . import demo, explore, guided, random, scenario


class TM_Robots(TaskMode):
    """
    Task mode for controlling one or multiple robots.

    Args:
        **kwargs: Additional keyword arguments.

    Attributes:
        _ctx (TaskContext): Shared task context.

    """

    _last_reset: int
    _start_poses: dict[str, Pose]
    _floor_id: ROSParamT[str]
    _floor_id_mode: ROSParamT[str]

    def __init__(self, **kwargs: object) -> None:
        super().__init__(**kwargs)
        self._floor_id = self.node.ROSParam[str](self.namespace('floor_id'), "")
        self._floor_id_mode = self.node.ROSParam[str](self.namespace('floor_id_mode'), "default")

    def _random_floor_id(self) -> str:
        floor_ids = [str(floor_id) for floor_id in self._ctx.world_manager.world.floor_ids if str(floor_id)]
        if not floor_ids:
            return ""
        return str(self.node.conf.General.RNG.value.choice(floor_ids))

    def _resolve_floor_id(self, floor_id: str | None = None) -> str:
        if floor_id:
            return floor_id
        mode = (self._floor_id_mode.value or "default").lower()
        if mode == "random":
            return self._random_floor_id()
        if mode == "explicit":
            return self._floor_id.value or ""
        return self._random_floor_id() or self._floor_id.value or ""

    @property
    def start_poses(self) -> dict[str, Pose]:
        return self._start_poses

    async def reset(self, **kwargs: object) -> None:
        self._last_reset = self.node.sim_time.sec
        self._start_poses = {}

    async def set_position(self, pose: Pose):
        """Teleport every robot to ``pose``."""
        for robot_manager in self._ctx.robots.values():
            await robot_manager.move(pose)

    async def set_goal(self, pose: Pose):
        """Dispatch a single-phase GOTO request targeting ``pose`` on every robot."""
        for robot_manager in self._ctx.robots.values():
            await robot_manager.submit_task(TaskRequest(phases=[GoToPhase(pose=pose)]))

    async def extend(
        self,
        model: str,
        name: str | None = None,
        pose: Pose | None = None,
        args: dict[str, str] | None = None,
    ) -> str:
        floor_id = self._resolve_floor_id(typing.cast(str, (args or {}).get("floor_id", "")))
        resolved_pose = pose if pose is not None else await random_placement(self._ctx, floor_id=floor_id)
        assigned_name = name or f"{model}_{uuid.uuid4().hex[:6]}"
        value: dict[str, object] = dict(args or {})
        value['model'] = model
        value['name'] = assigned_name
        value['pos'] = resolved_pose.to_2d()
        robot = RobotEntity.parse(value, node=self.node)
        self.node._robots_manager.add_pending(assigned_name, robot)
        return assigned_name

    @property
    async def done(self) -> bool:
        """
        Check if all robots have completed their tasks.

        Returns:
            bool: True if all robots are done, False otherwise.

        """
        if (self.node.sim_time.sec - self._last_reset) > self.node.conf.Robot.TIMEOUT.value:
            return True

        if not self._ctx.robots:
            return False
        if not all(await asyncio.gather(*(robot_manager.is_done for robot_manager in self._ctx.robots.values()))):
            return False
        return True


__all__ = ["TM_Robots", "demo", "explore", "guided", "random", "scenario"]
