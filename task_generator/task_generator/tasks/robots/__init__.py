import asyncio

from task_generator.shared import Pose
from task_generator.tasks import TaskMode
from task_generator.tasks.robots.request import GoToPhase, TaskRequest


class TM_Robots(TaskMode):
    """
    Task mode for controlling one or multiple robots.

    Args:
        **kwargs: Additional keyword arguments.

    Attributes:
        _ctx (TaskContext): Shared task context.

    """

    _last_reset: int

    async def reset(self, **kwargs):
        self._last_reset = self.node.sim_time.sec

    async def set_position(self, pose: Pose):
        """Teleport every robot to ``pose``."""
        for robot_manager in self._ctx.robots.values():
            await robot_manager.move(pose)

    async def set_goal(self, pose: Pose):
        """Dispatch a single-phase GOTO request targeting ``pose`` on every robot."""
        for robot_manager in self._ctx.robots.values():
            realized = robot_manager._environment_manager.realize(pose)  # noqa: SLF001
            await robot_manager.submit_task(
                TaskRequest(phases=[GoToPhase(pose=realized)])
            )

    @property
    async def done(self) -> bool:
        """
        Check if all robots have completed their tasks.

        Returns:
            bool: True if all robots are done, False otherwise.

        """
        if (self.node.sim_time.sec - self._last_reset) \
                > self.node.conf.Robot.TIMEOUT.value:
            return True

        if not self._ctx.robots:
            return False
        if not all(await asyncio.gather(*(robot_manager.is_done for robot_manager in self._ctx.robots.values()))):
            return False
        return True
