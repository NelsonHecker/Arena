"""No-op navstack adapter (navigator: none)."""

from __future__ import annotations

from typing import TYPE_CHECKING, Optional

import geometry_msgs.msg
import launch
import launch.actions
import launch.launch_description_sources
import launch.substitutions
from launch_ros.substitutions import FindPackageShare

from task_generator.tasks.robots.adapters import (
    Adapter,
    AdapterCtx,
    register_adapter,
)
from task_generator.tasks.robots.request import GoToPhase, TaskKind, TaskPhase

if TYPE_CHECKING:
    from task_generator.manager.robot_manager.robot_manager import RobotManager


@register_adapter
class NoneAdapter(Adapter):
    """Adapter that launches no navstack but still publishes goal_pose."""

    kind = "none"
    requires = frozenset({"mobile"})
    accepts = frozenset({TaskKind.GOTO_POSE})

    def launch_description(self, ctx: AdapterCtx):
        return launch.actions.IncludeLaunchDescription(
            launch.launch_description_sources.PythonLaunchDescriptionSource(
                launch.substitutions.PathJoinSubstitution([
                    FindPackageShare("arena_robots"),
                    "launch",
                    "adapters",
                    "none.launch.py",
                ])
            ),
        )

    async def dispatch_phase(
        self,
        phase: TaskPhase,
        robot: "RobotManager",
    ) -> None:
        assert isinstance(phase, GoToPhase), (
            f"NoneAdapter only accepts GOTO_POSE phases; got "
            f"{type(phase).__name__} (kind={phase.kind!r})"
        )
        # pylint: disable=protected-access
        robot._goal_pos = phase.pose

        goal_msg = geometry_msgs.msg.PoseStamped()
        goal_msg.header.frame_id = "map"
        goal_msg.header.stamp = robot.node.sim_time.to_msg()
        goal_msg.pose = phase.pose.to_msg()
        robot._goal_pub.publish(goal_msg)

    def is_phase_done(
        self,
        phase: TaskPhase,
        robot: "RobotManager",
    ) -> Optional[bool]:
        return None
