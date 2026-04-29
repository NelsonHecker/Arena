import asyncio
import uuid

from arena_robots.Robot import RobotIdentifier

from task_generator.shared import Pose
from task_generator.shared import Robot as RobotEntity
from task_generator.tasks.mode import TaskMode
from task_generator.tasks.robots._placement import random_placement
from task_generator.tasks.robots.request import GoToPhase, TaskRequest

from . import explore, guided, random, scenario


class TM_Robots(TaskMode):
    """
    Task mode for controlling one or multiple robots.

    Args:
        **kwargs: Additional keyword arguments.

    Attributes:
        _ctx (TaskContext): Shared task context.

    """

    _last_reset: int

    async def reset(self, **kwargs: object) -> None:
        self._last_reset = self.node.sim_time.sec

    async def set_position(self, pose: Pose):
        """Teleport every robot to ``pose``."""
        for robot_manager in self._ctx.robots.values():
            await robot_manager.move(pose)

    async def set_goal(self, pose: Pose):
        """Dispatch a single-phase GOTO request targeting ``pose`` on every robot."""
        for robot_manager in self._ctx.robots.values():
            await robot_manager.submit_task(TaskRequest(phases=[GoToPhase(pose=pose)]))

    async def extend(self, model: str, name: str | None = None, pose: Pose | None = None) -> str:
        resolved_pose = pose if pose is not None else await random_placement(self._ctx)
        assigned_name = name or f"{model}_{uuid.uuid4().hex[:6]}"
        await self._ctx.environment_manager.spawn_robot(
            [
                RobotEntity(
                    name=assigned_name,
                    model=RobotIdentifier(model),
                    pose=resolved_pose,
                    inter_planner="",
                    local_planner="",
                    global_planner="",
                    agent="",
                )
            ]
        )
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


__all__ = ["TM_Robots", "explore", "guided", "random", "scenario"]
