import asyncio
import math
import os
import typing

import ament_index_python
import arena_bringup.extensions.NodeLogLevelExtension as NodeLogLevelExtension
import geometry_msgs.msg
import launch.launch_description_sources
import launch_ros
import lifecycle_msgs.msg
import rclpy
import rclpy.client
import rclpy.logging
import rclpy.publisher
import rclpy.timer
import tf2_ros
from arena_rclpy_mixins.shared import Namespace
from arena_robots.Robot import RobotView
from nav2_msgs.srv import ClearCostmapAroundRobot, ClearEntireCostmap

import launch
import task_generator.utils.arena as Utils
from task_generator import NodeInterface
from task_generator.constants import Constants
from task_generator.manager.environment_manager import EnvironmentManager
from task_generator.shared import Orientation, Pose, Position, Robot

import rclpy.node


class RobotManager(NodeInterface):
    """
    The robot manager manages the goal and start
    position of a robot for all task modes.

    Args:
        namespace (Namespace): The namespace for the robot.
        environment_manager (EnvironmentManager): The environment manager.
        robot (Robot): The robot instance.
    """

    _namespace: Namespace
    _environment_manager: EnvironmentManager
    _start_pos: Pose
    _goal_pos: Pose
    _robot_radius: float
    _goal_tolerance_distance: float
    _goal_tolerance_angle: float
    _robot: Robot
    _move_base_pub: rclpy.publisher.Publisher
    _goal_pub: rclpy.publisher.Publisher
    _pub_goal_timer: rclpy.timer.Timer
    _clear_costmap_around_robot_srv: rclpy.client.Client
    _rate_setup: rclpy.timer.Rate
    _config: RobotView

    @property
    def robot(self) -> Robot:
        """Get the robot instance.

        Returns:
            Robot: The robot instance.
        """
        return self._robot

    @property
    def start_pos(self) -> Pose:
        """Get the start position.

        Returns:
            Pose: The start position.
        """
        return self._start_pos

    @property
    def goal_pos(self) -> Pose:
        """Get the goal position.

        Returns:
            Pose: The goal position.
        """
        return self._goal_pos

    @property
    def pose(self) -> typing.Optional[Pose]:
        """Current robot pose in the map frame, looked up via tf2.

        Returns None when the transform is not yet available (e.g. during
        reset/respawn windows).
        """
        base = self.frame(self._config.model_params.base_frame).raw()
        try:
            t = self.node.tf_buffer.lookup_transform(
                'map', base, rclpy.time.Time())
        except (tf2_ros.LookupException, tf2_ros.ConnectivityException,
                tf2_ros.ExtrapolationException):
            return None
        tr = t.transform.translation
        return Pose(
            Position(tr.x, tr.y),
            Orientation.from_msg(t.transform.rotation),
        )

    def __init__(
        self,
        *args,
        namespace: Namespace,
        environment_manager: EnvironmentManager,
        robot: Robot,
        **kwargs,
    ):
        super().__init__(*args, **kwargs)
        self._rate_setup = self.node.create_rate(.1)

        self._config = robot.model.resolve_sync()

        self._namespace = namespace
        self._environment_manager = environment_manager

        self._start_pos = Pose()
        self._goal_pos = Pose()
        self._robot_radius = 0.25

        self._goal_tolerance_distance = self.node.conf.Robot.GOAL_TOLERANCE_RADIUS.value
        self._goal_tolerance_angle = self.node.conf.Robot.GOAL_TOLERANCE_ANGLE.value
        self._safety_distance = self.node.conf.Robot.SPAWN_ROBOT_SAFE_DIST.value

        self._robot = robot
        self._robot.sim_path = self._environment_manager.realize(robot.name)
        self._robot.extra.setdefault('namespace', self.namespace)
        self._goal_timer = None

        self._publish_goal_task: typing.Optional[asyncio.Task] = None

    async def _odom_base_transform(self):
        """Launch a static transform publisher for odometry to base frame.
        """
        await self.node.do_launch(
            launch.LaunchDescription([
                launch_ros.actions.Node(
                    package="tf2_ros",
                    executable="static_transform_publisher",
                    name="odom_to_baseframe_publisher",
                    arguments=[
                        "0", "0", "0",
                        "0", "0", "0", "1",
                        self.frame(self._config.model_params.odom_frame).raw(),
                        self.frame(self._config.model_params.base_frame).raw(),
                    ],
                    parameters=[{'use_sim_time': True}],
                )
            ])
        )

    async def set_up_robot(self, node_names: set[str]):
        """Set up the robot by configuring its model and spawning it in the environment.
        """

        self._robot.pose.position.z += self._config.model_params.z_offset
        self._robot = (await self._environment_manager.spawn_robot((self._robot,)))[0]

        _gen_goal_topic = self.namespace("goal_pose")

        self._goal_pub = self.node.create_publisher(
            geometry_msgs.msg.PoseStamped,
            _gen_goal_topic,
            10,
        )

        await self._launch_robot(node_names)
        await self._odom_base_transform()

        self._robot_radius = self.node.rosparam[float].get(
            'robot_radius',
            self._robot_radius,
        )

    @property
    def radius(self) -> float:
        """Physical radius of the robot in metres."""
        return self._robot_radius

    @property
    def safe_distance(self) -> float:
        """Get the safe distance for the robot.

        Returns:
            float: The safe distance for the robot.
        """
        return self._robot_radius + self._safety_distance

    @property
    def model_name(self) -> str:
        """Get the model name of the robot.

        Returns:
            str: The model name of the robot.
        """
        return self._robot.model.name

    @property
    def name(self) -> str:
        """Get the name of the robot.

        Returns:
            str: The name of the robot.
        """
        return self._robot.name

    @property
    def frame(self) -> Namespace:
        """Get the tf2 frame of the robot.

        Returns:
            Namespace: The tf2 frame of the robot.
        """
        return self._robot.frame

    @property
    def namespace(self) -> Namespace:
        """Get the ROS2 namespace of the robot.

        Returns:
            Namespace: The ROS2 namespace of the robot.
        """
        if Utils.get_arena_type() == Constants.ArenaType.TRAINING:
            return Namespace(
                f"{self._namespace}{self._namespace}_{self.model_name}"
            )

        return self._namespace(self.name)

    @property
    async def is_done(self) -> bool:
        """Check if the robot has reached its goal.

        Done-detection uses TF + tolerance: compares the robot's current pose
        (via :pyattr:`pose`) to :pyattr:`_goal_pos` against the configured
        distance and (optional) angle tolerances. The pose accessor returns
        ``None`` during reset windows; in that case the robot is treated as
        not-done.

        Returns:
            bool: True if the goal is reached, False otherwise.
        """
        pose = self.pose
        if pose is None:
            return False

        dx = pose.position.x - self._goal_pos.position.x
        dy = pose.position.y - self._goal_pos.position.y
        if math.hypot(dx, dy) > self._goal_tolerance_distance:
            return False

        if self._goal_tolerance_angle > 0:
            dyaw = pose.orientation.to_yaw() - self._goal_pos.orientation.to_yaw()
            # wrap to [-pi, pi]
            dyaw = (dyaw + math.pi) % (2 * math.pi) - math.pi
            if abs(dyaw) > self._goal_tolerance_angle:
                return False

        return True

    async def move_robot_to_pos(self, pose: Pose):
        """Move the robot to the specified pose.

        Args:
            pose(Pose): The target pose for the robot.
        """
        pose.position.z += self._config.model_params.z_offset
        self.robot.pose = pose
        await self._environment_manager.move_robot((self.robot,))
        import time
        time.sleep(0.001)  # wait for the robot to move
        await self._clear_local_costmap(-1)

    async def _clear_local_costmap(self, reset_distance: float = -1) -> bool:
        """Clear the local costmap around the robot.

        Args:
            reset_distance(float, optional): The distance to reset the costmap. Defaults to - 1. If reset_distance is -1, the entire costmap will be cleared. If reset_distance is >= 0, only the costmap around the robot will be cleared.

        Returns:
            bool: True if the costmap was cleared successfully, False otherwise.
        """
        node_name = self.node.service_namespace(self.name, 'local_costmap/local_costmap')

        if reset_distance < 0:
            srv_name = os.path.abspath(node_name('../clear_entirely_local_costmap'))
            srv_type = ClearEntireCostmap
            req = ClearEntireCostmap.Request()
        else:
            srv_name = os.path.abspath(node_name('../clear_around_local_costmap'))
            srv_type = ClearCostmapAroundRobot
            req = ClearCostmapAroundRobot.Request()
            req.reset_distance = reset_distance

        state = await self.node.get_lifecycle_state_async(node_name)
        if state.id != lifecycle_msgs.msg.State.PRIMARY_STATE_ACTIVE:
            return False

        self._logger.info(f"Service name: {srv_name}")
        cli = self.node.create_client_wrapper(
            srv_type,
            srv_name,
        )
        await cli.ensure()

        result = await cli.call_timeout(req)
        if result is None:
            self._logger.error(
                f"service call failed for {srv_name}")
            return False
        self._logger.info(
            f"successfull service call for {srv_name}"
        )
        return True

    async def reset(
        self,
        start_pos: typing.Optional[Pose],
        goal_pos: typing.Optional[Pose],
    ) -> tuple[Pose, Pose]:
        """Reset the robot's position and / or goal.

        Args:
            start_pos(typing.Optional[Pose]): The new starting position of the robot.
            goal_pos(typing.Optional[Pose]): The new goal position of the robot.

        Returns:
            tuple[Pose, Pose]: The new starting and goal positions of the robot.
        """
        if start_pos is not None:
            self._start_pos = self._environment_manager.realize(start_pos)
            await self.move_robot_to_pos(start_pos)

            if self._robot.record_data_dir:
                self.node.rosparam[list[float]].set(
                    self.namespace.robot_ns.ParamNamespace()("start"),
                    [self.start_pos.position.x, self.start_pos.position.y, self.start_pos.orientation.to_yaw()]
                )
        if goal_pos is not None:
            self._goal_pos = self._environment_manager.realize(goal_pos)

            if self._publish_goal_task is not None:
                self._publish_goal_task.cancel()
            self._publish_goal_task = asyncio.create_task(self._publish_goal_loop())

            if self._robot.record_data_dir:
                self.node.rosparam[list[float]].set(
                    self.namespace.robot_ns.ParamNamespace()("goal"),
                    [self.goal_pos.position.x, self.goal_pos.position.y, self.goal_pos.orientation.to_yaw()]
                )
        return self._start_pos, self._goal_pos

    async def _publish_goal_loop(self):
        """Publish the goal to the robot.
        """
        # only way to circumvent amcl absolutely trolling us is to create this loop

        target = self._goal_pos
        with self.node.sim_time_rate(1.0, 60) as (done, rate):
            while not done.is_set():
                await rate.get()

                # Terminate when the goal has been superseded by a new reset.
                # is-done is evaluated elsewhere by TM_Robots via the is_done
                # property; the publish loop only keeps the current goal alive
                # against amcl jitter until the next reset swaps _goal_pos.
                if self._goal_pos is not target:
                    break

                goal = self._goal_pos
                self._logger.info(f"Publishing goal: x={goal.position.x}, y={goal.position.y}, orientation={goal.orientation.to_yaw()}")

                if self._goal_timer is not None:
                    self._goal_timer.cancel()
                    self._goal_timer.destroy()

                goal_msg = geometry_msgs.msg.PoseStamped()
                goal_msg.header.frame_id = "map"
                goal_msg.header.stamp = self.node.sim_time.to_msg()
                goal_msg.pose = goal.to_msg()
                self._goal_pub.publish(goal_msg)

                self._goal_start_time = self.node.sim_time

    async def _launch_robot(self, node_paths: set[str]):
        """Launch the robot external nodes.
        """
        self._logger.info(f"LAUNCH ROBOT {self.name}")

        if Utils.get_arena_type() != Constants.ArenaType.TRAINING:
            launch_description = launch.LaunchDescription()
            current_log_level = rclpy.logging.get_logger_effective_level(self.node.get_logger().name).name.lower()
            launch_description.add_action(NodeLogLevelExtension.SetGlobalLogLevelAction(current_log_level))  # type: ignore

            launch_arguments = {
                'robot': self.model_name,
                # 'simulator': self.node.conf.Arena.SIM.value.value,
                # 'name': self.name,
                'task_generator_node': os.path.join(self.node.get_namespace(), self.node.get_name()),
                'namespace': self.namespace,
                # 'use_namespace': 'True',
                'frame': self._robot.frame('').raw(),  # trailing slash
                'inter_planner': self._robot.inter_planner,
                'global_planner': self._robot.global_planner,
                'local_planner': self._robot.local_planner,
                # 'complexity': self.node.declare_parameter('complexity', 1).value,
                'train_mode': str(self.node.rosparam[bool].get('train_mode', False)).lower(),
                'agent_name': self._robot.agent,
                'use_sim_time': 'True',
                'amcl': 'true' if self.node.conf.Arena.SIM.value in (Constants.SimSimulator.GAZEBO,) else 'false',
            }

            if self._robot.record_data_dir:
                launch_arguments.update({
                    'record_data_dir': self._robot.record_data_dir,
                })

            launch_description.add_action(
                launch.actions.IncludeLaunchDescription(
                    launch.launch_description_sources.PythonLaunchDescriptionSource(
                        os.path.join(
                            ament_index_python.packages.get_package_share_directory('arena_simulation_setup'),
                            'launch/robot.launch.py'
                        )
                    ),
                    launch_arguments=launch_arguments.items(),
                )
            )
            await self.node.do_launch(launch_description)

            bt_node_path = str(self.namespace('bt_navigator'))
            self._logger.info(f'waiting for {bt_node_path}')
            while bt_node_path not in node_paths:
                await asyncio.sleep(0.01)

    async def update(self):
        """Live - update some kwargs of robot
        """
        # TODO implement record data dir

    async def destroy(self):
        """Destroy robot and remove from simulation and navigation stack.
        """
        if self._goal_timer is not None:
            self._goal_timer.cancel()
            self._goal_timer.destroy()
        await self._environment_manager.remove_robot((self.robot,))
        # TODO kill node in navigation stack
