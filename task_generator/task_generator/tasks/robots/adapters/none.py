"""No-op navstack adapter (navigator: none)."""

from __future__ import annotations

from typing import TYPE_CHECKING

from arena_robots.bringup.none import NoneBringup
from arena_robots.clients.goto_pose import GotoPoseClient
from arena_robots.task_kinds import TaskKind
from arena_robots_msgs.action import GotoPose

from task_generator.tasks.robots.adapters import Adapter
from task_generator.tasks.robots.request import GoToPhase, TaskPhase

if TYPE_CHECKING:
    import geometry_msgs.msg

    from task_generator.manager.robot_manager.robot_manager import RobotManager


class NoneAdapter(Adapter):
    kind = "none"
    accepts = frozenset({TaskKind.GOTO_POSE})
    bringup_cls = NoneBringup
    client_cls = GotoPoseClient
    republishes_goal = True

    def is_phase_done(self, phase: TaskPhase, robot: RobotManager) -> bool | None:
        return None

    async def dispatch_phase(
        self,
        phase: TaskPhase,
        robot: RobotManager,
    ) -> None:
        assert isinstance(phase, GoToPhase), f"NoneAdapter only accepts GOTO_POSE phases; got {type(phase).__name__} (kind={phase.kind!r})"
        robot._goal_pos = phase.pose  # pylint: disable=protected-access
        goal = GotoPose.Goal()
        goal.target = self._phase_to_pose_stamped(phase, robot)
        goal.pose_tolerance = float(phase.tolerance_radius or 0.0)
        goal.yaw_tolerance = float(phase.tolerance_angle or 0.0)
        await self.client.send_goal(goal)

    def _phase_to_pose_stamped(
        self,
        phase: GoToPhase,
        robot: RobotManager,
    ) -> geometry_msgs.msg.PoseStamped:
        import geometry_msgs.msg

        msg = geometry_msgs.msg.PoseStamped()
        msg.header.frame_id = "map"
        msg.header.stamp = robot.node.sim_time.to_msg()
        msg.pose = phase.pose.to_msg()
        return msg
