#!/usr/bin/env python3
"""Single-window multi-environment RViz launcher.

Accepts N task_generator_node namespace paths as positional CLI arguments,
waits for every environment to finish initialising, then builds **one**
collapsible Group display per environment (Map, TF, Pedestrians, per-robot
sub-groups) and opens exactly **one** rviz2 window.

Usage (called by arena.launch.py):
    multi_env_rviz /task_generator_node
    multi_env_rviz /task_generator_node/env0 /task_generator_node/env1 ...
"""

import os
import subprocess
import sys
import tempfile
import time
import typing

import rcl_interfaces.msg
import rcl_interfaces.srv
import rclpy
import yaml
from ament_index_python.packages import get_package_share_directory
from rclpy.node import Node

from rviz_utils.utils import Utils

# ---------------------------------------------------------------------------
# Snap / libpthread environment fix
# ---------------------------------------------------------------------------
_SYSTEM_LIB_DIRS = ["/lib/x86_64-linux-gnu", "/usr/lib/x86_64-linux-gnu"]
_PTHREAD_CANDIDATES = [
    "/lib/x86_64-linux-gnu/libpthread.so.0",
    "/usr/lib/x86_64-linux-gnu/libpthread.so.0",
]


def _build_clean_env() -> dict:
    """Return a sanitised copy of the current environment suitable for launching
    rviz2 without snap-induced glibc PRIVATE symbol conflicts.

    Three-layer defence:
    1. Drop all SNAP* env vars and strip any /snap/ paths from path-list vars.
    2. Prepend system lib dirs to LD_LIBRARY_PATH so they win over any RPATH
       that might still point into /snap/core20/.
    3. LD_PRELOAD the stub libpthread so it is already resident in memory before
       any dlopen()'d GL/Qt plugin can load the snap version via its own RPATH.
    """
    def _strip_snap_paths(val: str) -> str:
        return ":".join(p for p in val.split(":") if "/snap/" not in p)

    env = {
        k: (_strip_snap_paths(v) if k in ("LD_LIBRARY_PATH", "PYTHONPATH") else v)
        for k, v in os.environ.items()
        if not k.startswith("SNAP")
    }

    existing = env.get("LD_LIBRARY_PATH", "")
    env["LD_LIBRARY_PATH"] = ":".join(
        _SYSTEM_LIB_DIRS + [p for p in existing.split(":") if p]
    )

    system_pthread = next((p for p in _PTHREAD_CANDIDATES if os.path.exists(p)), None)
    if system_pthread:
        existing_preload = env.get("LD_PRELOAD", "")
        env["LD_PRELOAD"] = f"{system_pthread}:{existing_preload}".rstrip(":")

    return env


# Per-environment accent colour palette (cycles for > 8 envs)
_ENV_PALETTE = [
    "66; 134; 244",   # blue
    "244; 110; 66",   # orange
    "66; 214; 126",   # green
    "214; 66; 164",   # pink
    "214; 194; 66",   # yellow
    "66; 214; 214",   # cyan
    "164; 66; 214",   # purple
    "214; 66; 66",    # red
]


class MultiEnvRvizGenerator(Node):
    """Generate and write an rviz config covering all environments, then
    launch a single rviz2 process."""

    def __init__(self, taskgen_nodes: typing.List[str]) -> None:
        Node.__init__(self, "multi_env_rviz_generator")

        self._nodes = taskgen_nodes
        self._env_data: typing.List[typing.Dict[str, typing.Any]] = []

        for taskgen_node in taskgen_nodes:
            srv_name = os.path.join(taskgen_node, "get_parameters")
            cli = self.create_client(rcl_interfaces.srv.GetParameters, srv_name)
            self.get_logger().info(f"Waiting for service: {srv_name}")
            while not cli.wait_for_service(timeout_sec=1.0):
                self.get_logger().info(f"  still waiting for {srv_name} …")

            self._wait_for_param(cli, "initialized", test_fn=lambda x: x.bool_value)
            robot_names = self._wait_for_param(cli, "robot_names").string_array_value

            self._env_data.append(
                {
                    "node": taskgen_node,
                    "robot_names": list(robot_names),
                }
            )
            self.get_logger().info(
                f"Env '{taskgen_node}' ready — robots: {list(robot_names)}"
            )

    # ------------------------------------------------------------------
    # Helpers
    # ------------------------------------------------------------------

    def _wait_for_param(
        self,
        client: rclpy.client.Client,
        param_name: str,
        test_fn: typing.Optional[typing.Callable[[typing.Any], bool]] = None,
        timeout: float = 1.0,
    ) -> rcl_interfaces.msg.ParameterValue:
        """Block until parameter exists and satisfies *test_fn* (if given)."""
        while True:
            self.get_logger().info(f"  waiting for param '{param_name}' …")
            for _ in range(5):
                req = rcl_interfaces.srv.GetParameters.Request(names=[param_name])
                future = client.call_async(req)
                rclpy.spin_until_future_complete(self, future, timeout_sec=timeout)
                result = future.result()
                if result and result.values:
                    val = result.values[0]
                    if (not test_fn) or test_fn(val):
                        return val
                time.sleep(timeout)

    @staticmethod
    def _read_default_file(first_taskgen_node: str) -> dict:
        pkg = get_package_share_directory("rviz_utils")
        path = os.path.join(pkg, "config", "rviz_default.rviz")
        with open(path) as fh:
            raw = fh.read().format(task_generator_node=first_taskgen_node)
        return yaml.safe_load(raw)

    @staticmethod
    def _tmp_config_file(cfg: dict) -> str:
        f = tempfile.NamedTemporaryFile("w", suffix=".rviz", delete=False)
        yaml.dump(cfg, f)
        f.close()
        return f.name

    # ------------------------------------------------------------------
    # Display builders
    # ------------------------------------------------------------------

    def _create_pedestrian_group(
        self, taskgen_node: str, all_topics: list
    ) -> dict:
        ped_group: dict = {
            "Class": "rviz_common/Group",
            "Name": "Pedestrians",
            "Enabled": True,
            "Displays": [],
        }
        for topic_name, topic_types in all_topics:
            if not topic_name.startswith(taskgen_node):
                continue
            if "visualization_msgs/msg/MarkerArray" in topic_types and (
                topic_name.endswith("/pedestrian_markers")
                or topic_name.endswith("/wall_markers")
            ):
                enabled = True
                ped_group["Displays"].append(
                    Utils.Displays.pedestrians(
                        topic_name,
                        name=os.path.basename(topic_name),
                        enabled=enabled,
                    )
                )
        return ped_group

    def _create_robot_group(
        self,
        taskgen_node: str,
        robot_name: str,
        env_color: str,
        all_topics: list,
    ) -> dict:
        robot_group: dict = {
            "Class": "rviz_common/Group",
            "Name": f"Robot: {robot_name}",
            "Enabled": True,
            "Displays": [],
        }
        ns = taskgen_node
        # Derive the TF prefix that rviz2 uses to locate robot link frames.
        # rviz2 constructs per-link frame IDs as:  tf_prefix + "/" + link_name
        # robot_state_publisher is launched with frame_prefix = "<label>_<robot>_"
        # so the actual TF frames are  env0_jackal_base_link  etc.
        # Gazebo DiffDrive bridge also publishes env0_jackal/base_link (slash) –
        # those match when tf_prefix = "env0_jackal".
        label = os.path.basename(ns.rstrip("/"))
        if label == "task_generator_node":
            tf_prefix = robot_name          # single-env: just "jackal"
        else:
            tf_prefix = f"{label}_{robot_name}"  # multi-env: "env0_jackal"

        robot_group["Displays"].extend(
            [
                # RobotModel disabled: RViz2 TF Prefix always uses "/" separator
                # (e.g. "jackal/base_link") but TF frames use underscore prefix
                # ("jackal_base_link") from frame_prefix="jackal_" in RSP.
                # There is no TF Prefix value that bridges this mismatch.
                {**Utils.Displays.robot_model(
                    topic=f"{ns}/{robot_name}/robot_description",
                    robot_name=tf_prefix,
                ), "Enabled": False},
                Utils.Displays.odom(f"{ns}/{robot_name}/odom", env_color),
                Utils.Displays.local_costmap(
                    f"{ns}/{robot_name}/local_costmap/costmap"
                ),
                Utils.Displays.global_costmap(
                    f"{ns}/{robot_name}/global_costmap/costmap"
                ),
                Utils.Displays.global_path(f"{ns}/{robot_name}/plan", env_color),
                Utils.Displays.local_path(f"{ns}/{robot_name}/local_plan"),
                Utils.Displays.robot_footprint(
                    f"{ns}/{robot_name}/local_costmap/published_footprint",
                    env_color,
                ),
            ]
        )

        # Robot task marker (obstacle visualization, etc.)
        robot_group["Displays"].append(
            Utils.Displays.marker_array(
                f"{ns}/{robot_name}/marker",
                name="Task Markers",
            )
        )

        sensor_map = {
            "sensor_msgs/msg/LaserScan": Utils.Displays.laser_scan,
            "sensor_msgs/msg/PointCloud2": Utils.Displays.pointcloud,
            "sensor_msgs/msg/PointCloud": Utils.Displays.pointcloud_legacy,
            "foot_contact_msgs/msg/FootContact": Utils.Displays.footcontact,
            "sensor_msgs/msg/Image": Utils.Displays.image,
        }
        # Sensors that accept a color argument
        colored_sensors = {
            "sensor_msgs/msg/LaserScan",
            "sensor_msgs/msg/PointCloud2",
            "sensor_msgs/msg/PointCloud",
            "foot_contact_msgs/msg/FootContact",
        }
        sensor_counts: typing.Dict[str, int] = {}
        robot_ns = f"{ns}/{robot_name}"

        for topic_name, topic_types in all_topics:
            if not topic_name.startswith(robot_ns):
                continue
            for t in topic_types:
                if t in sensor_map:
                    cnt = sensor_counts.get(t, 0)
                    sensor_counts[t] = cnt + 1
                    if t in colored_sensors:
                        sensor_color = Utils.get_sensor_color(t, cnt)
                        robot_group["Displays"].append(
                            sensor_map[t](topic_name, sensor_color)
                        )
                    else:
                        robot_group["Displays"].append(sensor_map[t](topic_name))
                    break  # use first matching type only

        return robot_group

    def _create_env_group(
        self, idx: int, env_info: dict, all_topics: list
    ) -> dict:
        taskgen_node: str = env_info["node"]
        robot_names: typing.List[str] = env_info["robot_names"]
        env_color = _ENV_PALETTE[idx % len(_ENV_PALETTE)]
        # Use basename as label: "task_generator_node", "env0", "env1", …
        label = os.path.basename(taskgen_node)

        env_group: dict = {
            "Class": "rviz_common/Group",
            "Name": f"Environment: {label}",
            "Enabled": True,
            "Displays": [],
        }

        # Map
        env_group["Displays"].append(
            {
                "Class": "rviz_default_plugins/Map",
                "Enabled": True,
                "Name": "Map",
                "Topic": {
                    "Value": os.path.join(taskgen_node, "map"),
                    "Depth": 20,
                    "History Policy": "Keep Last",
                    "Reliability Policy": "Reliable",
                    "Durability Policy": "Transient Local",
                },
                "Use Timestamp": False,
                "Alpha": 0.7,
            }
        )

        # TF (disabled by default to reduce clutter with many envs)
        env_group["Displays"].append(
            {
                "Class": "rviz_default_plugins/TF",
                "Enabled": False,
                "Name": "TF",
                "Frame Timeout": 15,
                "Marker Scale": 1.0,
                "Show Arrows": True,
                "Show Axes": True,
                "Show Names": False,
            }
        )

        # Goal
        env_group["Displays"].append(
            Utils.Displays.goal_pose(f"{taskgen_node}/goal")
        )

        # Pedestrians
        env_group["Displays"].append(
            self._create_pedestrian_group(taskgen_node, all_topics)
        )

        # Per-robot groups
        for robot_name in robot_names:
            env_group["Displays"].append(
                self._create_robot_group(taskgen_node, robot_name, env_color, all_topics)
            )

        return env_group

    # ------------------------------------------------------------------
    # Top-level entry
    # ------------------------------------------------------------------

    def create_config(self) -> str:
        cfg = self._read_default_file(self._nodes[0])
        all_topics = self.get_topic_names_and_types()

        displays = [
            self._create_env_group(idx, env_info, all_topics)
            for idx, env_info in enumerate(self._env_data)
        ]
        cfg["Visualization Manager"]["Displays"] = displays

        # Sensible overview camera
        cfg["Visualization Manager"]["Views"]["Current"] = {
            "Class": "rviz_default_plugins/Orbit",
            "Distance": 80.0,
            "Focal Point": {"X": 0.0, "Y": 0.0, "Z": 0.0},
            "Name": "Current View",
            "Near Clip Distance": 0.01,
            "Pitch": 1.0,
            "Target Frame": "<Fixed Frame>",
            "Value": True,
            "Yaw": 3.14,
        }

        path = self._tmp_config_file(cfg)
        self.get_logger().info(f"Config written to: {path}")
        return path


def main() -> None:
    rclpy.init()

    cli_args = rclpy.utilities.remove_ros_args(sys.argv)
    # Positional args after the script name are the task_generator namespaces
    taskgen_nodes: typing.List[str] = (
        cli_args[1:] if len(cli_args) > 1 else ["/task_generator_node"]
    )

    gen = MultiEnvRvizGenerator(taskgen_nodes)
    exit_code = 0
    try:
        config_path = gen.create_config()
        gen.get_logger().info(f"Starting rviz2 with {len(taskgen_nodes)} environment(s)")

        clean_env = _build_clean_env()
        gen.get_logger().info(
            f"LD_PRELOAD: {clean_env.get('LD_PRELOAD', '(none)')}"
        )

        proc = subprocess.Popen(
            [
                "rviz2",
                "-d",
                config_path,
                "--ros-args",
                "-p",
                "use_sim_time:=true",
            ],
            env=clean_env,
        )
        proc.wait()
        exit_code = proc.returncode if proc.returncode is not None else 0
    except KeyboardInterrupt:
        pass
    except Exception as exc:
        gen.get_logger().error(f"Error: {exc}")
        exit_code = 1
    finally:
        gen.destroy_node()
        rclpy.shutdown()

    sys.exit(exit_code)


if __name__ == "__main__":
    main()
