from task_generator.shared import Pose
from task_generator.tasks.robots import TM_Robots


class TM_Stationary(TM_Robots):
    """Stationary task mode: robot stays parked at start pose without goal dispatch."""

    async def reset(self, **kwargs: object) -> None:
        await super().reset(**kwargs)

        pos_x = self.node.get_parameter("stationary.pos_x").value if self.node.has_parameter("stationary.pos_x") else None
        pos_y = self.node.get_parameter("stationary.pos_y").value if self.node.has_parameter("stationary.pos_y") else None

        override_pose = None
        if pos_x is not None and pos_y is not None:
            from task_generator.shared import Orientation, Pose, Position
            override_pose = Pose(
                position=Position(x=pos_x, y=pos_y, z=0.0),
                orientation=Orientation(0.0, 0.0, 0.0, 1.0)
            )

        for robot in self._ctx.robots.values():
            if override_pose is not None:
                self._start_poses[robot.name] = override_pose
            else:
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
