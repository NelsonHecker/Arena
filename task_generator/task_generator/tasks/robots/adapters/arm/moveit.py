"""MoveIt arm adapter — thin composer of MoveItArmBringup + ReachPoseClient."""

from __future__ import annotations

import asyncio
from typing import TYPE_CHECKING, ClassVar

from arena_robots.bringup.arm.moveit import MoveItArmBringup
from arena_robots.clients.reach_pose import ReachPoseClient
from arena_robots.task_kinds import TaskKind
from arena_robots_msgs.action import ReachPose

from task_generator.tasks.robots.adapters import Adapter, AdapterDisplayHint, AdapterMeta
from task_generator.tasks.robots.request import ReachPhase

if TYPE_CHECKING:
    from task_generator.manager.robot_manager.robot_manager import RobotManager
    from task_generator.tasks.robots.adapters import ResetContext
    from task_generator.tasks.robots.request import TaskPhase


@AdapterMeta.attach(
    accepts={TaskKind.REACH_POSE},
    bringup=MoveItArmBringup,
    client=ReachPoseClient,
    cap="arm",
    republishes_goal=False,
    displays=(
        AdapterDisplayHint(
            name="Planned Trajectory",
            topic="{ns}/move_group/display_planned_path",
            topic_type="moveit_msgs/DisplayTrajectory",
            rviz_class="moveit_rviz_plugin/Trajectory",
            config_json='{"Robot Description": "{robot}.robot_description"}',
        ),
        AdapterDisplayHint(
            name="Planning Scene",
            topic="{ns}/monitored_planning_scene",
            topic_type="moveit_msgs/PlanningScene",
            rviz_class="moveit_rviz_plugin/PlanningScene",
            config_json='{"Robot Description": "{robot}.robot_description", "Enabled": false}',
        ),
    ),
)
class MoveItArmAdapter(Adapter):
    kind: ClassVar[str] = "moveit"

    async def dispatch_phase(self, phase: TaskPhase, robot: RobotManager) -> None:
        assert isinstance(phase, ReachPhase), f"MoveItArmAdapter only accepts ReachPhase; got {type(phase).__name__} (kind={phase.kind!r})"
        goal = ReachPose.Goal()
        if phase.random:
            from task_generator.tasks.robots._reach_sampling import sample_reach_target

            arms = robot.robot_view.caps.arm
            if not arms:
                raise ValueError(f"random ReachPhase requested but robot {robot.name!r} has no arm cap")
            (arm,) = arms.values()
            rng = robot.node.conf.General.RNG.value
            goal.target = sample_reach_target(arm, robot.namespace, rng)
        elif phase.target is not None:
            goal.target = phase.target
        elif phase.named_target is not None:
            goal.named_target = phase.named_target
        goal.position_tolerance = float(phase.position_tolerance or 0.0)
        goal.orientation_tolerance = float(phase.orientation_tolerance or 0.0)
        goal.planning_time = float(phase.planning_time or 0.0)
        await self.client.send_goal(goal)

    async def reset_to(self, robot: RobotManager, ctx: ResetContext) -> None:
        # MoveIt cannot plan while sim is paused (no /joint_states → no current state).
        # The TM is responsible for emitting a stow phase if it wants the arm parked.
        del robot, ctx

    async def wait_until_ready(self, robot: RobotManager, node_paths: set[str]) -> None:
        mg = str(robot.namespace("move_group"))
        while mg not in node_paths:
            await asyncio.sleep(0.01)
        await super().wait_until_ready(robot, node_paths)
