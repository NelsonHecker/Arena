import math

from arena_rclpy_mixins.Time import Time

from task_generator.shared import Orientation, Pose
from task_generator.tasks.robots.random import TM_Random


class TM_Explore(TM_Random):
    """
    This class represents a task manager for exploring robots.
    It inherits from the TM_Random class.
    """

    _timeouts: dict[str, Time]

    async def reset(self, **kwargs):
        await super().reset(**kwargs)
        self._timeouts = {}
        for name in self._ctx.robots.keys():
            self._reset_timeout(name)

    @property
    async def done(self) -> bool:
        """
        Checks if the exploration task is done for all robots.

        Returns:
            bool: True if the task is done for all robots, False otherwise.
        """
        for robot, manager in self._ctx.robots.items():
            if await manager.is_done:
                waypoint = self._ctx.world_manager.get_position_on_map(
                    safe_dist=manager.safe_distance, forbid=False
                )
                await self._set_goal(
                    robot,
                    Pose(
                        waypoint,
                        Orientation.from_yaw(self.node.conf.General.RNG.value.random() * 2 * math.pi)
                    )
                )

            elif (self.node.sim_time.sec - self._timeouts.get(robot, Time()).sec) >= self.node.conf.Robot.TIMEOUT.value:
                waypoint = self._ctx.world_manager.get_position_on_map(
                    safe_dist=manager.safe_distance, forbid=False
                )
                await self._set_position(
                    robot,
                    Pose(
                        waypoint,
                        Orientation.from_yaw(self.node.conf.General.RNG.value.random() * 2 * math.pi)
                    )
                )

        return False

    def _reset_timeout(self, robot: str):
        """
        Resets the timeout for a specific robot.

        Args:
            robot (str): The name of the robot.
        """
        self._timeouts[robot] = self.node.sim_time

    async def _set_position(self, name: str, pose: Pose):
        """
        Sets the position of a specific robot and resets the timeout.

        Args:
            name (str): The name of the robot.
            position (Pose): The new position of the robot.
        """
        self._reset_timeout(name)
        await self._ctx.robots[name].reset(pose, None)

    async def _set_goal(self, name: str, pose: Pose):
        """
        Sets the goal position of a specific robot and resets the timeout.

        Args:
            name (str): The name of the robot.
            position (Pose): The new goal position of the robot.
        """
        self._reset_timeout(name)
        await self._ctx.robots[name].reset(None, pose)

    def __init__(self, **kwargs):
        super().__init__(**kwargs)
