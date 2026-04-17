"""Nav2 adapter — wraps the generic ``nav2.launch.py`` in arena_robots."""

from __future__ import annotations

import asyncio
import os
from typing import TYPE_CHECKING, ClassVar, Optional

import lifecycle_msgs.msg
import launch
import launch.actions
import launch.launch_description_sources
import launch.substitutions
from action_msgs.msg import GoalStatus
from launch_ros.substitutions import FindPackageShare
from nav2_msgs.action import NavigateToPose
from nav2_msgs.srv import ClearCostmapAroundRobot, ClearEntireCostmap
from rclpy.action import ActionClient

from task_generator.tasks.robots.adapters import (
    Adapter,
    AdapterCtx,
    register_adapter,
)
from task_generator.tasks.robots.request import GoToPhase, TaskKind, TaskPhase

if TYPE_CHECKING:
    from rclpy.action.client import ClientGoalHandle

    from task_generator.manager.robot_manager.robot_manager import RobotManager
    from task_generator.shared import Pose




@register_adapter
class Nav2Adapter(Adapter):
    """Adapter wrapping the nav2 stack; uses NavigateToPose for dispatch+verdict."""

    kind = "nav2"
    requires = frozenset({"mobile"})
    accepts = frozenset({TaskKind.GOTO_POSE})
    # Goal transport is owned by the NavigateToPose action client below;
    # the RobotManager goal-republish loop must not race it.
    republishes_goal: ClassVar[bool] = False

    def __init__(
        self,
        *,
        global_planner: str,
        local_planner: str,
        inter_planner: str,
        train_mode: bool = False,
    ) -> None:
        self.global_planner = str(global_planner)
        self.local_planner = str(local_planner)
        self.inter_planner = str(inter_planner)
        self.train_mode = bool(train_mode)
        self._action_client: Optional[ActionClient] = None
        self._goal_handle: Optional["ClientGoalHandle"] = None
        self._terminal_status: Optional[int] = None
        self._dispatch_lock: asyncio.Lock = asyncio.Lock()
        self._resubmit_task: Optional[asyncio.Task] = None

    def launch_description(self, ctx: AdapterCtx):
        return launch.actions.IncludeLaunchDescription(
            launch.launch_description_sources.PythonLaunchDescriptionSource(
                launch.substitutions.PathJoinSubstitution([
                    FindPackageShare("arena_robots"),
                    "launch",
                    "adapters",
                    "nav2.launch.py",
                ])
            ),
            launch_arguments=[
                ("robot", ctx.robot_name),
                ("namespace", str(ctx.namespace)),
                ("frame", ctx.frame),
                ("use_sim_time", "true" if ctx.use_sim_time else "false"),
                ("task_generator_node", ctx.task_generator_node),
                ("global_planner", self.global_planner),
                ("local_planner", self.local_planner),
                ("inter_planner", self.inter_planner),
                ("train_mode", "true" if self.train_mode else "false"),
            ],
        )

    async def dispatch_phase(
        self,
        phase: TaskPhase,
        robot: "RobotManager",
    ) -> None:
        assert isinstance(phase, GoToPhase), (
            f"Nav2Adapter only accepts GOTO_POSE phases; got "
            f"{type(phase).__name__} (kind={phase.kind!r})"
        )
        # Serializes external dispatches against async resubmits spawned
        # from is_phase_done on ABORTED.
        async with self._dispatch_lock:
            await self._do_dispatch(phase, robot)

    async def _do_dispatch(
        self,
        phase: "GoToPhase",
        robot: "RobotManager",
    ) -> None:
        # pylint: disable=protected-access
        robot._goal_pos = phase.pose

        if self._action_client is None:
            self._action_client = ActionClient(
                robot.node,
                NavigateToPose,
                str(robot.namespace("navigate_to_pose")),
            )

        # bt_navigator is a lifecycle node — its action server is
        # discoverable before ACTIVATE finishes, and goals sent in that
        # window are rejected. Wait for ACTIVE before dispatching.
        await robot.node.wait_for_lifecycle_state_async(
            str(robot.namespace('bt_navigator')),
            lifecycle_msgs.msg.State.PRIMARY_STATE_ACTIVE,
        )

        while not self._action_client.server_is_ready():
            await asyncio.sleep(0.1)

        # Cancel any in-flight goal and wait for its result to settle;
        # otherwise the server may still be running the previous goal when
        # we submit a new one and reject it.
        if self._goal_handle is not None and self._terminal_status is None:
            try:
                await robot.node.await_ros(
                    self._goal_handle.cancel_goal_async()
                )
            except Exception:
                pass
            try:
                await robot.node.await_ros(
                    self._goal_handle.get_result_async()
                )
            except Exception:
                pass

        self._goal_handle = None
        self._terminal_status = None

        goal_msg = NavigateToPose.Goal()
        goal_msg.pose.header.frame_id = "map"
        goal_msg.pose.header.stamp = robot.node.sim_time.to_msg()
        goal_msg.pose.pose = phase.pose.to_msg()

        # Retry on rejection — transient causes include lingering state
        # from the previous goal's cancellation or the nav stack finishing
        # warmup even after lifecycle hit ACTIVE.
        handle = None
        for _ in range(30):
            handle = await robot.node.await_ros(
                self._action_client.send_goal_async(goal_msg)
            )
            if handle.accepted:
                break
            await asyncio.sleep(0.5)
        assert handle is not None and handle.accepted, (
            f"Nav2Adapter: NavigateToPose goal rejected by server for "
            f"robot {robot.name!r} after 30 attempts"
        )

        self._goal_handle = handle

        # Bind the callback to this specific handle so a late-arriving
        # result from a previous goal can't overwrite fresh state.
        def on_result(future, h=handle):
            if self._goal_handle is not h:
                return
            try:
                self._terminal_status = future.result().status
            except Exception:
                self._terminal_status = GoalStatus.STATUS_ABORTED

        handle.get_result_async().add_done_callback(on_result)

    def is_phase_done(
        self,
        phase: TaskPhase,
        robot: "RobotManager",
    ) -> Optional[bool]:
        if self._goal_handle is None:
            # Pre-dispatch race window; let Tier-3 run as a safety net.
            return None
        if self._terminal_status is None:
            return False
        if self._terminal_status == GoalStatus.STATUS_SUCCEEDED:
            return True
        if self._terminal_status == GoalStatus.STATUS_CANCELED:
            # We cancelled (e.g. to dispatch a new goal); the new dispatch
            # is in flight or done. Wait for it rather than declaring the
            # phase over.
            return False
        # STATUS_ABORTED (or unknown): bt_navigator gave up — typically
        # because a teleport or external disturbance invalidated the plan.
        # Resubmit to mirror the old republish-loop semantics where nav2
        # kept getting the goal until it succeeded. TIMEOUT is the backstop
        # for genuinely unreachable goals.
        if self._resubmit_task is None or self._resubmit_task.done():
            self._resubmit_task = asyncio.create_task(
                self.dispatch_phase(phase, robot)
            )
        return False

    def on_episode_end(self) -> None:
        if self._resubmit_task is not None and not self._resubmit_task.done():
            self._resubmit_task.cancel()
        self._resubmit_task = None
        if self._goal_handle is not None and self._terminal_status is None:
            try:
                self._goal_handle.cancel_goal_async()
            except Exception:
                pass
        self._goal_handle = None
        self._terminal_status = None

    async def on_move(
        self,
        pose: "Pose",
        robot: "RobotManager",
    ) -> None:
        await self._clear_local_costmap(robot)

    async def wait_until_ready(
        self,
        robot: "RobotManager",
        node_paths: set[str],
    ) -> None:
        bt_node_path = str(robot.namespace("bt_navigator"))
        robot.node.get_logger().info(f"waiting for {bt_node_path}")
        while bt_node_path not in node_paths:
            await asyncio.sleep(0.01)
        await robot.node.wait_for_lifecycle_state_async(
            bt_node_path,
            lifecycle_msgs.msg.State.PRIMARY_STATE_ACTIVE,
        )

    async def _clear_local_costmap(
        self,
        robot: "RobotManager",
        reset_distance: float = -1.0,
    ) -> bool:
        """Clear the local costmap; reset_distance < 0 clears entirely, else around the robot."""
        node_name = robot.node.service_namespace(
            robot.name, "local_costmap/local_costmap"
        )

        if reset_distance < 0:
            srv_name = os.path.abspath(node_name("../clear_entirely_local_costmap"))
            srv_type = ClearEntireCostmap
            req = ClearEntireCostmap.Request()
        else:
            srv_name = os.path.abspath(node_name("../clear_around_local_costmap"))
            srv_type = ClearCostmapAroundRobot
            req = ClearCostmapAroundRobot.Request()
            req.reset_distance = reset_distance

        state = await robot.node.get_lifecycle_state_async(node_name)
        if state.id != lifecycle_msgs.msg.State.PRIMARY_STATE_ACTIVE:
            return False

        cli = robot.node.create_client_wrapper(srv_type, srv_name)
        await cli.ensure()

        result = await cli.call_timeout(req)
        if result is None:
            robot.node.get_logger().error(
                f"service call failed for {srv_name}"
            )
            return False
        return True
