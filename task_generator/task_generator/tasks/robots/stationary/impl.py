from task_generator.shared import Pose
from task_generator.tasks import TaskContext
from task_generator.tasks.robots import TM_Robots


class TM_Stationary(TM_Robots):
    """Stationary task mode: robot stays parked at start pose without goal dispatch."""

    async def reset(self, **kwargs: object) -> None:
        await super().reset(**kwargs)
        for robot in self._ctx.robots.values():
            self._start_poses[robot.name] = robot.start_pos

    @property
    async def done(self) -> bool:
        if (self.node.sim_time.sec - self._last_reset) > self.node.conf.Robot.TIMEOUT.value:
            return True
        return False

    async def set_position(self, pose: Pose):
        for robot in self._ctx.robots.values():
            await robot.move(pose)

    async def set_goal(self, pose: Pose):
        del pose
        return None
