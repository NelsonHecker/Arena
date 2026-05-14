import math
import typing

from task_generator.shared import Orientation, Pose, PositionRadius
from task_generator.tasks.robots import TM_Robots
from task_generator.tasks.robots.request import GoToPhase, TaskRequest


class TM_Random(TM_Robots):
    """Random-goal task mode."""

    async def reset(self, **kwargs: object) -> None:
        await super().reset(**kwargs)

        floor_id = self._resolve_floor_id(typing.cast(str, kwargs.get("floor_id", "")))

        ROBOT_POSITIONS: list[tuple[Pose, Pose]] = kwargs.get("ROBOT_POSITIONS", [])
        biggest_robot = max((robot.safe_distance for robot in self._ctx.robots.values()), default=0)

        for robot_start, robot_goal in ROBOT_POSITIONS:
            self._ctx.world_manager.forbid(
                [
                    PositionRadius(robot_start.position.x, robot_start.position.y, biggest_robot),
                    PositionRadius(robot_goal.position.x, robot_goal.position.y, biggest_robot),
                ],
                floor_id=floor_id,
            )

        if len(ROBOT_POSITIONS) < len(self._ctx.robots):
            to_generate = 2 * (len(self._ctx.robots) - len(ROBOT_POSITIONS))

            orientations = 2 * math.pi * self.node.conf.General.RNG.value.random(to_generate)
            positions = self._ctx.world_manager.get_positions_on_map(n=to_generate, safe_dist=biggest_robot, floor_id=floor_id)

            generated_positions = [Pose(position, Orientation.from_yaw(orientation)) for (orientation, position) in zip(orientations, positions, strict=False)]

            ROBOT_POSITIONS += list(zip(generated_positions[::2], generated_positions[1::2], strict=False))

        for robot, pos in zip(self._ctx.robots.values(), ROBOT_POSITIONS, strict=False):
            await robot.move(pos[0])
            await robot.submit_task(TaskRequest(phases=[GoToPhase(pose=pos[1])]))
