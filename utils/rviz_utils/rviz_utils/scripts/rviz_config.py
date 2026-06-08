#! /usr/bin/env python3

import asyncio
import os
import signal
import sys
import tempfile
import typing

import arena_bringup.extensions.NodeLogLevelExtension as NodeLogLevelExtension
import launch
import launch_ros.actions
import rcl_interfaces.msg
import rcl_interfaces.srv
import rclpy
import yaml
from ament_index_python.packages import get_package_share_directory
from arena_rclpy_mixins import ArenaMixinNode
from arena_rclpy_mixins.shared import FrameNamespace
from arena_robots.moveit_factory import build_moveit_params
from arena_robots.Robot import RobotIdentifier
from task_generator_msgs.msg import AdapterVizManifest, RobotDescriptor, RobotFleet
from arena_viz import DisplayKind

from rviz_utils.renderers import REGISTRY


class ConfigFileGenerator(ArenaMixinNode):
    topics: list[tuple[str, list[str]]]
    robots: list[RobotDescriptor]
    viz_manifest: AdapterVizManifest
    _frame_prefix: str
    _env_id: int

    def __init__(self, TASKGEN_NODE: str = '/task_generator_node'):
        super().__init__('rviz_config_generator')

        self._TASKGEN_NODE = TASKGEN_NODE
        self.declare_parameter('view', 'map')
        self.declare_parameter('robot', 0)

    async def _await_param(
        self,
        client: rclpy.client.Client,
        param_name: str,
        test_fn: typing.Callable[[typing.Any], bool] | None = None,
        interval: float = 1.0,
    ) -> rcl_interfaces.msg.ParameterValue:
        """Block until parameter passes test function."""
        while True:
            self.get_logger().info(f'waiting for {param_name} to be set')
            req = rcl_interfaces.srv.GetParameters.Request(names=[param_name])
            params = await self.await_ros(client.call_async(req))
            if params and params.values:
                value = params.values[0]
                if (not test_fn) or test_fn(value):
                    self.get_logger().info(f'param {param_name} is set')
                    return value
            await asyncio.sleep(interval)

    async def _await_first_fleet(self) -> RobotFleet:
        loop = asyncio.get_running_loop()
        future: asyncio.Future[RobotFleet] = loop.create_future()
        topic = os.path.join(self._TASKGEN_NODE, 'state', 'robots')
        sub = self.create_subscription(
            RobotFleet,
            topic,
            lambda msg: loop.call_soon_threadsafe(future.set_result, msg) if not future.done() else None,
            qos_profile=rclpy.qos.QoSProfile(
                depth=1,
                durability=rclpy.qos.DurabilityPolicy.TRANSIENT_LOCAL,
            ),
        )
        try:
            self.get_logger().info(f'waiting for first {topic} message')
            return await future
        finally:
            self.destroy_subscription(sub)

    async def _await_viz_manifest(self) -> AdapterVizManifest:
        loop = asyncio.get_running_loop()
        future: asyncio.Future[AdapterVizManifest] = loop.create_future()
        topic = os.path.join(self._TASKGEN_NODE, 'state', 'viz_manifest')
        sub = self.create_subscription(
            AdapterVizManifest,
            topic,
            lambda msg: loop.call_soon_threadsafe(future.set_result, msg) if not future.done() else None,
            qos_profile=rclpy.qos.QoSProfile(
                depth=1,
                durability=rclpy.qos.DurabilityPolicy.TRANSIENT_LOCAL,
            ),
        )
        try:
            self.get_logger().info(f'waiting for first {topic} message')
            return await future
        finally:
            self.destroy_subscription(sub)

    async def setup(self) -> None:
        TASKGEN_PARAM_SRV = os.path.join(self._TASKGEN_NODE, 'get_parameters')
        PARAM_INITIALIZED = 'initialized'

        get_parameters_cli = self.create_client(rcl_interfaces.srv.GetParameters, TASKGEN_PARAM_SRV)
        self.get_logger().info(f'waiting for service {TASKGEN_PARAM_SRV} to become available')
        await self.wait_for_service_async(get_parameters_cli)
        self.get_logger().info(f'service {TASKGEN_PARAM_SRV} is available')

        await self._await_param(get_parameters_cli, PARAM_INITIALIZED, lambda x: x.bool_value)
        self._frame_prefix = (await self._await_param(get_parameters_cli, 'prefix')).string_value
        self._env_id = (await self._await_param(get_parameters_cli, 'env_id')).integer_value
        self.robots = list((await self._await_first_fleet()).robots)
        self.viz_manifest = await self._await_viz_manifest()

        config_file = self.create_config()

        rviz_parameters: list[dict[str, object]] = [{"use_sim_time": True}]
        arm_params = self._collect_moveit_params()
        if arm_params:
            rviz_parameters.append(arm_params)

        launch_task = await self._launch_manager.launch_description(
            launch.LaunchDescription(
                [
                    NodeLogLevelExtension.SetGlobalLogLevelAction(rclpy.logging.get_logger_effective_level(self.get_logger().name).name.lower()),
                    launch_ros.actions.Node(
                        package="rviz2",
                        executable="rviz2",
                        name="rviz2",
                        arguments=['-d', config_file],
                        parameters=rviz_parameters,
                        output="screen",
                        additional_env={"LIBGL_ALWAYS_SOFTWARE": "1"},
                    ),
                ]
            )
        )
        await launch_task
        self.get_logger().info('rviz2 exited, shutting down supervisor')
        os.kill(os.getpid(), signal.SIGINT)

    def _collect_moveit_params(self) -> dict[str, object]:
        """Mirror each arm robot's MoveIt config into rviz2 under a robot-named
        prefix. Per-display ``Robot Description`` properties point at
        ``<robot>.robot_description`` so every arm robot gets its own
        Trajectory/PlanningScene display."""
        combined: dict[str, object] = {}
        arm_names: list[str] = []
        for robot in self.robots:
            tf_prefix = FrameNamespace(robot.frame).raw()
            tf_prefix = tf_prefix + "/" if tf_prefix else ""
            params = build_moveit_params(robot.model, tf_prefix=tf_prefix)
            if params is None:
                continue
            arm_names.append(robot.name)
            for key, value in params.items():
                combined[f"{robot.name}.{key}"] = value
        if arm_names:
            self.get_logger().info(f"injecting MoveIt params into rviz2 for: {arm_names}")
        return combined

    def create_config(self) -> str:
        skeleton = self._read_default_file()
        self.topics = self.get_topic_names_and_types()
        published_topics = {t for t, _ in self.topics}
        displays: list[dict[str, object]] = []

        for d in self.viz_manifest.env_displays:
            try:
                renderer = REGISTRY[DisplayKind(d.kind)]
            except KeyError:
                self.get_logger().warning(f"no rviz renderer for kind {d.kind!r}, skipping {d.name!r}")
                continue
            if d.topic_must_exist and d.topic not in published_topics:
                continue
            rendered = renderer(d, None)
            if rendered is not None:
                displays.append(rendered)

        robots_by_ns = {robot.ns: robot for robot in self.robots}
        entries_by_ns: dict[str, list] = {}
        for entry in self.viz_manifest.entries:
            entries_by_ns.setdefault(entry.robot_ns, []).append(entry)

        for robot_ns, robot_entries in entries_by_ns.items():
            robot = robots_by_ns.get(robot_ns)
            if robot is None:
                self.get_logger().warning(f"manifest entry for unknown robot ns {robot_ns!r}, skipping")
                continue
            group: dict[str, object] = {
                "Class": "rviz_common/Group",
                "Name": f"Robot: {robot.name}",
                "Enabled": True,
                "Displays": [],
            }
            for entry in robot_entries:
                for d in entry.displays:
                    try:
                        renderer = REGISTRY[DisplayKind(d.kind)]
                    except KeyError:
                        self.get_logger().warning(f"no rviz renderer for kind {d.kind!r}, skipping {d.name!r}")
                        continue
                    if d.topic_must_exist and d.topic not in published_topics:
                        continue
                    rendered = renderer(d, robot)
                    if rendered is not None:
                        group["Displays"].append(rendered)
            displays.append(group)

        skeleton["Visualization Manager"]["Displays"] = displays
        skeleton["Visualization Manager"]["Views"]["Current"] = self._build_view()
        file_path = self._tmp_config_file(skeleton, prefix=f"env{self._env_id}_")
        self.get_logger().info(f'created config file at {file_path}')
        return file_path

    def _target_robot_frame(self) -> str | None:
        if not self.robots:
            self.get_logger().warning('view requested a robot target frame, but fleet is empty, falling back to map view')
            return None
        idx = self.get_parameter('robot').value
        try:
            robot = self.robots[idx]
        except IndexError:
            self.get_logger().warning(f'robot index {idx} out of range (fleet size {len(self.robots)}), ignoring')
            return None
        base_frame = RobotIdentifier(robot.model).resolve_sync().model_params.base_frame
        prefix = FrameNamespace(robot.frame).raw()
        return f'{prefix}/{base_frame}' if prefix else base_frame

    def _build_view(self) -> dict[str, object]:
        view = str(self.get_parameter('view').value)

        if view in ('robot', 'robot3p'):
            target = self._target_robot_frame()
            if target is None:
                view = 'map'

        if view == 'robot':
            return {
                'Class': 'rviz_default_plugins/Orbit',
                'Distance': 8.0,
                'Focal Point': {'X': 0.0, 'Y': 0.0, 'Z': 0.0},
                'Name': 'Current View',
                'Near Clip Distance': 0.01,
                'Pitch': 0.9,
                'Target Frame': target,
                'Value': True,
                'Yaw': 3.14,
            }

        if view == 'robot3p':
            return {
                'Class': 'rviz_default_plugins/ThirdPersonFollower',
                'Distance': 8.0,
                'Focal Point': {'X': 0.0, 'Y': 0.0, 'Z': 0.0},
                'Name': 'Current View',
                'Near Clip Distance': 0.01,
                'Pitch': 0.5,
                'Target Frame': target,
                'Value': True,
                'Yaw': 3.14,
            }

        python_yaw: float = 3.8
        try:
            python_yaw = sum(2 * (i % 2 - 0.5) * float(d) / 10**i for i, d in enumerate(sys.version.split(' ', 1)[0].split('.')))  # i am going insane
        except BaseException:
            pass
        return {
            'Class': 'rviz_default_plugins/Orbit',
            'Distance': 50.0,
            'Focal Point': {'X': 15.0, 'Y': 10.0, 'Z': 0.0},
            'Name': 'Current View',
            'Near Clip Distance': 0.01,
            'Pitch': 0.9,
            'Target Frame': '<Fixed Frame>',
            'Value': True,
            'Yaw': python_yaw,
        }

    def _read_default_file(self) -> dict[str, object]:
        package_path = get_package_share_directory("rviz_utils")
        file_path = os.path.join(package_path, "config", "rviz_default.rviz")

        fixed_frame = FrameNamespace(self._frame_prefix).tf('map')

        with open(file_path) as file:
            content = file.read()
            # i'm lazy, bite me
            content = content.format(
                task_generator_node=self._TASKGEN_NODE,
                fixed_frame=fixed_frame,
            )
            return yaml.safe_load(content)

    @classmethod
    def _tmp_config_file(cls, config_file: dict[str, object], prefix: str = "") -> str:
        f = tempfile.NamedTemporaryFile('w', delete=False, prefix=prefix)
        yaml.dump(config_file, f)
        f.close()
        return f.name


def main():
    cli_args = rclpy.utilities.remove_ros_args(sys.argv)
    ConfigFileGenerator.run_main(*cli_args[1:])


if __name__ == "__main__":
    main()
