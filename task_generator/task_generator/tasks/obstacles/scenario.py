import os
import numpy as np
from datetime import datetime
import csv

import rclpy.time
from rclpy.time import Time
from tf2_ros import Buffer, TransformListener
from tf2_msgs.msg import TFMessage
from std_msgs.msg import Float32MultiArray, MultiArrayDimension
from hunav_msgs.srv import SetVelocityField, SetArenaWorldBounds
from arena_people_msgs.msg import Pedestrians, Pedestrian
from message_filters import Subscriber, ApproximateTimeSynchronizer
from rclpy.qos import (
    QoSProfile,
    QoSReliabilityPolicy,
    QoSDurabilityPolicy,
    QoSHistoryPolicy,
    ReliabilityPolicy,
)
from arena_rclpy_mixins.ROSParamServer import ROSParamT
from arena_simulation_setup.tree.World import WorldIdentifier
from arena_simulation_setup.tree.World.Scenario import Scenario

from task_generator.tasks import identifier_to_available
from task_generator.tasks.obstacles import Obstacles, TM_Obstacles
from task_generator.tasks.obstacles.prompt.velocity_field_marker import (
    VelocityFieldVisualizer,
)


class TM_Scenario(TM_Obstacles):
    _config: ROSParamT[Scenario]

    def send_velocity_msg(self, velocity_field: np.ndarray):
        n_groups, h, w, c = velocity_field.shape
        msg = Float32MultiArray()
        msg.data = velocity_field.astype(np.float32).flatten(order="C").tolist()
        msg.layout.dim = [
            MultiArrayDimension(label="G", size=n_groups, stride=n_groups * h * w * c),
            MultiArrayDimension(label="H", size=h, stride=h * w * c),
            MultiArrayDimension(label="W", size=w, stride=w * c),
            MultiArrayDimension(label="C", size=c, stride=c),
        ]

        req = SetVelocityField.Request()
        req.velocity_field = msg

        response: SetVelocityField.Response = self.velocity_field_client.call(req)

        return response

    def send_arena_world_bounds_msg(self):
        # TODO: Optimize
        # Get Arena World size
        x_min, y_min, x_max, y_max = np.inf, np.inf, -np.inf, -np.inf

        for zones in self._PROPS.world_manager.world.zones:
            x_min, y_min, x_max, y_max = (
                min(x_min, *(corner.x for corner in zones.corners)),
                min(y_min, *(corner.y for corner in zones.corners)),
                max(x_max, *(corner.x for corner in zones.corners)),
                max(y_max, *(corner.y for corner in zones.corners)),
            )
        arena_world_bounds = [x_min, y_min, x_max, y_max]

        msg = Float32MultiArray()
        msg.data = arena_world_bounds
        msg.layout.dim = [
            MultiArrayDimension(label="bounds", size=4, stride=4),
        ]

        req = SetArenaWorldBounds.Request()
        req.arena_world_bounds = msg

        response: SetArenaWorldBounds.Response = self.arena_world_bounds_client.call(
            req
        )

        return response, x_min, y_min, x_max, y_max

    def _parse_scenario(self, scenario: str) -> Scenario:
        velocity_field_path = os.path.join(
            WorldIdentifier(self.node._world_manager.world_name)
            .resolve_sync()
            .scenario(scenario)
            .resolve_sync()
            .path,
            "velocity_field.npy",
        )
        if os.path.isfile(velocity_field_path):
            arena_world_bounds_res, x_min, y_min, x_max, y_max = (
                self.send_arena_world_bounds_msg()
            )
            self._logger.info(
                f"Set Arena World bounds response: {arena_world_bounds_res.success}, {arena_world_bounds_res.message}"
            )
            self.velocity_field_visualizer.update_world_bounds(
                x_min, y_min, x_max, y_max
            )
            velocity_field = np.load(velocity_field_path)
            self.send_velocity_msg(velocity_field)

        return (
            WorldIdentifier(self.node._world_manager.world_name)
            .resolve_sync()
            .scenario(scenario)
            .resolve_sync()
            .load()
        )

    async def reset(self, **kwargs) -> Obstacles:
        self._logger.info(f"Last scenario: Robot data: {len(self.robot_pos)}")
        self.dump_trajectories(self.scenario_name_prefix)
        self.current_scenario_id = datetime.now().strftime("%H%M%S")
        self.all_samples = []
        self.robot_pos = []
        self.robot_last_pos = None
        self.time_step_count = 1
        return self._config.value.static, self._config.value.dynamic

    def __init__(self, **kwargs):
        TM_Obstacles.__init__(self, **kwargs)

        default_scenario: str | None = "default"
        if default_scenario not in (
            scenarios := list(
                identifier_to_available(
                    WorldIdentifier(self.node._world_manager.world_name)
                    .resolve_sync()
                    .scenario
                )
            )
        ):
            default_scenario = next(iter(scenarios), None)
        if default_scenario is None:
            raise ValueError(
                f"No scenarios found in world {self.node._world_manager.world_name}"
            )

        self._config = self.node.ROSParam[Scenario](
            self.namespace("file"),
            default_scenario,
            parse=self._parse_scenario,
        )

        self.velocity_field_client = self.node.create_client(
            SetVelocityField, "/task_generator_node/set_velocity_field"
        )
        while not self.velocity_field_client.wait_for_service(timeout_sec=1.0):
            self.node.get_logger().info(
                "Waiting for service /task_generator_node/set_velocity_field"
            )
        self.velocity_field_visualizer = VelocityFieldVisualizer(
            self.node,
            topic_name="/task_generator_node/velocity_field_marker",
        )
        self.arena_world_bounds_client = self.node.create_client(
            SetArenaWorldBounds, "/task_generator_node/set_arena_world_bounds"
        )
        while not self.arena_world_bounds_client.wait_for_service(timeout_sec=1.0):
            self.node.get_logger().info(
                "Waiting for service /task_generator_node/set_arena_world_bounds"
            )

        self.pedestrians_subscriber = self.node.create_subscription(
            Pedestrians,
            "/task_generator_node/arena_peds",
            self.pedestrians_callback,
            QoSProfile(
                reliability=QoSReliabilityPolicy.RELIABLE,
                durability=QoSDurabilityPolicy.VOLATILE,
                history=QoSHistoryPolicy.KEEP_LAST,
                depth=10,
            ),
        )

        self.dump_timer = self.node.create_timer(60, self._periodic_dump_callback)
        self.scenario_name_prefix = "scenario"
        self.current_scenario_id = datetime.now().strftime("%H%M%S")
        self.all_samples = []
        self.robot_pos = []
        self.robot_last_pos = None
        self.time_step_count = 1
        self.tf_buffer = Buffer()
        self.tf_listener = TransformListener(self.tf_buffer, self.node)

    def pedestrians_callback(self, ped_msg: Pedestrians):
        for ped in ped_msg.pedestrians:
            ped: Pedestrian
            if ped.name == "robot":
                self.robot_pos.append(
                    {
                        "frame": self.time_step_count,
                        "id": "robot",
                        "x": ped.pose.position.x,
                        "y": ped.pose.position.y,
                    }
                )
            else:
                ped_id = ped.id
                self.all_samples.append(
                    {
                        "frame": self.time_step_count,
                        "id": ped_id,
                        "x": ped.pose.position.x,
                        "y": ped.pose.position.y,
                    }
                )

        self.time_step_count += 1

    def _periodic_dump_callback(self):
        if len(self.all_samples) == 0:
            self._logger.warn("No trajectories to save")
            return

        if len(self.robot_pos) == 0:
            self._logger.warn("No robot data")
            return

        output_csv_path = os.path.join(
            "/home/linh/ductai_nguyen_ws/Arena_ws/",
            f"{self.current_scenario_id}.csv",
        )
        all_samples = self.all_samples
        all_samples.sort(key=lambda s: (s["frame"], s["id"]))
        row_frames = [s["frame"] for s in all_samples]
        row_ids = [s["id"] for s in all_samples]
        row_xs = [round(s["x"], 4) for s in all_samples]
        row_ys = [round(s["y"], 4) for s in all_samples]

        with open(output_csv_path, "w", newline="") as f:
            writer = csv.writer(f)
            writer.writerow(row_frames)
            writer.writerow(row_ids)
            writer.writerow(row_xs)
            writer.writerow(row_ys)

        self.robot_pos.sort(key=lambda s: (s["frame"], s["id"]))
        row_frames = [s["frame"] for s in self.robot_pos]
        row_ids = [s["id"] for s in self.robot_pos]
        row_xs = [round(s["x"], 4) for s in self.robot_pos]
        row_ys = [round(s["y"], 4) for s in self.robot_pos]

        with open(
            os.path.join(
                "/home/linh/ductai_nguyen_ws/Arena_ws",
                f"{self.current_scenario_id}_robot.csv",
            ),
            "w",
            newline="",
        ) as f:
            writer = csv.writer(f)
            writer.writerow(row_frames)
            writer.writerow(row_ids)
            writer.writerow(row_xs)
            writer.writerow(row_ys)

        print(f"Successfully converted trajectories to {output_csv_path}")
        print(f"Total frames: {max(row_frames)}, Total agents: {len(set(row_ids))}")

    def dump_trajectories(self, file_name_prefix: str):
        if len(self.all_samples) == 0:
            self._logger.warn("No trajectories to save")
            return

        if len(self.robot_pos) == 0:
            self._logger.warn("No robot data")
            return

        output_csv_path = os.path.join(
            "/home/linh/ductai_nguyen_ws/Arena_ws/",
            f"{file_name_prefix[: min(20, len(file_name_prefix))]}_{self.current_scenario_id}.csv",
        )
        all_samples = self.all_samples
        all_samples.sort(key=lambda s: (s["frame"], s["id"]))
        row_frames = [s["frame"] for s in all_samples]
        row_ids = [s["id"] for s in all_samples]
        row_xs = [round(s["x"], 4) for s in all_samples]
        row_ys = [round(s["y"], 4) for s in all_samples]

        with open(output_csv_path, "w", newline="") as f:
            writer = csv.writer(f)
            writer.writerow(row_frames)
            writer.writerow(row_ids)
            writer.writerow(row_xs)
            writer.writerow(row_ys)

        self.robot_pos.sort(key=lambda s: (s["frame"], s["id"]))
        row_frames = [s["frame"] for s in self.robot_pos]
        row_ids = [s["id"] for s in self.robot_pos]
        row_xs = [round(s["x"], 4) for s in self.robot_pos]
        row_ys = [round(s["y"], 4) for s in self.robot_pos]

        with open(
            os.path.join(
                "/home/linh/ductai_nguyen_ws/Arena_ws",
                f"{self.current_scenario_id}_robot.csv",
            ),
            "w",
            newline="",
        ) as f:
            writer = csv.writer(f)
            writer.writerow(row_frames)
            writer.writerow(row_ids)
            writer.writerow(row_xs)
            writer.writerow(row_ys)

        print(f"Successfully converted trajectories to {output_csv_path}")
        print(f"Total frames: {max(row_frames)}, Total agents: {len(set(row_ids))}")
