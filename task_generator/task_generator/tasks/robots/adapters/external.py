"""External-planner adapter — hand-off to third-party navigation stacks."""

from __future__ import annotations

from typing import TYPE_CHECKING, Any, Optional

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


_DEFAULT_GOAL_TOPIC = "goal_pose"
_DEFAULT_CMD_VEL_TOPIC = "cmd_vel"
_DEFAULT_LAUNCH_FILE = "none.launch.py"
_DEFAULT_REQUIRES: frozenset[str] = frozenset({"mobile"})


@register_adapter
class ExternalAdapter(Adapter):
    """Adapter for third-party planners that run outside Arena; topics configurable per robot."""

    kind = "external"
    accepts = frozenset({TaskKind.GOTO_POSE})
    requires: frozenset[str] = _DEFAULT_REQUIRES

    def __init__(
        self,
        *,
        goal_topic: str = _DEFAULT_GOAL_TOPIC,
        cmd_vel_topic: str = _DEFAULT_CMD_VEL_TOPIC,
        launch_file: str = _DEFAULT_LAUNCH_FILE,
        requires: frozenset[str] = _DEFAULT_REQUIRES,
        extra: Optional[dict[str, Any]] = None,
    ) -> None:
        self.goal_topic = str(goal_topic)
        self.cmd_vel_topic = str(cmd_vel_topic)
        self.launch_file = str(launch_file)
        # Coerce to frozenset[str] so the bind-time subset check in
        # RobotManager matches on equality semantics.
        self.requires = frozenset(str(c) for c in requires)
        self.extra: dict[str, Any] = dict(extra) if extra else {}

    def launch_description(self, ctx: AdapterCtx):
        return launch.actions.IncludeLaunchDescription(
            launch.launch_description_sources.PythonLaunchDescriptionSource(
                launch.substitutions.PathJoinSubstitution([
                    FindPackageShare("arena_robots"),
                    "launch",
                    "adapters",
                    self.launch_file,
                ])
            ),
            launch_arguments=[
                ("goal_topic", self.goal_topic),
                ("cmd_vel_topic", self.cmd_vel_topic),
            ],
        )

    async def dispatch_phase(
        self,
        phase: TaskPhase,
        robot: "RobotManager",
    ) -> None:
        assert isinstance(phase, GoToPhase), (
            f"ExternalAdapter only accepts GOTO_POSE phases; got "
            f"{type(phase).__name__} (kind={phase.kind!r})"
        )
        # pylint: disable=protected-access
        robot._goal_pos = phase.pose

        publisher = self._goal_publisher(robot)

        goal_msg = geometry_msgs.msg.PoseStamped()
        goal_msg.header.frame_id = "map"
        goal_msg.header.stamp = robot.node.sim_time.to_msg()
        goal_msg.pose = phase.pose.to_msg()
        publisher.publish(goal_msg)

    def is_phase_done(
        self,
        phase: TaskPhase,
        robot: "RobotManager",
    ) -> Optional[bool]:
        return None

    def _goal_publisher(self, robot: "RobotManager"):
        # Reuse robot._goal_pub for the default topic; only create a new
        # publisher when the YAML points at a non-default topic.
        if self.goal_topic == _DEFAULT_GOAL_TOPIC:
            # pylint: disable=protected-access
            return robot._goal_pub

        cache_attr = "_external_goal_pub"
        cached = getattr(self, cache_attr, None)
        if cached is not None:
            return cached

        topic = robot.namespace(self.goal_topic)
        pub = robot.node.create_publisher(
            geometry_msgs.msg.PoseStamped,
            topic,
            10,
        )
        setattr(self, cache_attr, pub)
        return pub


__all__ = ["ExternalAdapter"]
