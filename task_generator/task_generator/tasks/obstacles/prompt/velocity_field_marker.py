from rclpy.node import Node
from rclpy.qos import QoSProfile, ReliabilityPolicy, HistoryPolicy, DurabilityPolicy

import numpy as np

from geometry_msgs.msg import Point
from visualization_msgs.msg import Marker, MarkerArray
from std_msgs.msg import ColorRGBA


class VelocityFieldVisualizer:
    def __init__(
        self,
        node: Node,
        map_min_x: float = 0.0,
        map_min_y: float = 0.0,
        map_max_x: float = 0.0,
        map_max_y: float = 0.0,
        topic_name: str = "/velocity_field_marker",
    ):
        self.node = node
        self._logger = node.get_logger()

        # Internal state for coordinate conversion
        self.map_min_x = map_min_x
        self.map_min_y = map_min_y
        self.map_max_x = map_max_x
        self.map_max_y = map_max_y

        # RViz Publisher
        qos_profile = QoSProfile(
            reliability=ReliabilityPolicy.RELIABLE,
            durability=DurabilityPolicy.TRANSIENT_LOCAL,  # This is the "magic" setting
            history=HistoryPolicy.KEEP_LAST,
            depth=1,
        )
        self.marker_pub = self.node.create_publisher(
            MarkerArray, topic_name, qos_profile
        )

    def update_world_bounds(self, x_min, y_min, x_max, y_max):
        """Update bounds used for coordinate mapping."""
        self.map_min_x = x_min
        self.map_min_y = y_min
        self.map_max_x = x_max
        self.map_max_y = y_max

    def publish_markers(self, field: np.ndarray):
        """
        Converts normalized grid to RViz Markers.
        field: np.ndarray of shape (H, W, 2)
        """
        marker_array = MarkerArray()
        h, w, _ = field.shape

        # Calculate cell sizes in world coordinates
        world_width = self.map_max_x - self.map_min_x
        world_height = self.map_max_y - self.map_min_y
        assert world_width * world_height > 0, (
            f"Invalid world size: {world_height}x{world_width}"
        )
        dx = world_width / w
        dy = world_height / h

        # Downsample for performance if grid is too dense
        step = 2 if h > 32 else 1

        id_counter = 0
        for i in range(0, h, step):
            for j in range(0, w, step):
                # Center of the cell in world coordinates
                # Note: Grid index i is usually Y, j is X
                world_x = self.map_min_x + (j + 0.5) * dx
                world_y = self.map_min_y + (i + 0.5) * dy

                vx = field[i, j, 0]
                vy = field[i, j, 1]

                # Skip near-zero vectors
                if np.hypot(vx, vy) < 0.05:
                    self._logger.warn("Velocity too small for visualization")
                    continue

                marker = Marker()
                marker.header.frame_id = "map"
                marker.header.stamp = self.node.get_clock().now().to_msg()
                marker.ns = "velocity_field"
                marker.id = id_counter
                marker.type = Marker.ARROW
                marker.action = Marker.ADD

                # Arrow Start (World position)
                start = Point(x=world_x, y=world_y, z=0.1)
                # Arrow End (Position + scaled velocity)
                end = Point(x=world_x + vx * dx, y=world_y + vy * dy, z=0.1)

                marker.points = [start, end]

                # Aesthetics
                marker.scale.x = 0.08  # Shaft diameter
                marker.scale.y = 0.15  # Head diameter
                marker.scale.z = 0.15  # Head length
                marker.color = ColorRGBA(r=1.0, g=0.5, b=0.0, a=1.0)  # Orange

                marker_array.markers.append(marker)
                id_counter += 1

        self._logger.info(
            f"Publishing {id_counter} markers for grid: {h}x{w}, world: {world_height}x{world_width}"
        )
        self.marker_pub.publish(marker_array)


if __name__ == "__main__":
    import rclpy
    from rclpy.executors import MultiThreadedExecutor

    rclpy.init()

    node = rclpy.create_node("velocity_field_marker_test_node")

    visualizer = VelocityFieldVisualizer(node)

    visualizer.update_world_bounds(0.0, 0.0, 30.0, 23.0)

    visualizer.publish_markers(np.random.uniform(-1, 1, size=(64, 64, 2)))

    executor = MultiThreadedExecutor()
    executor.add_node(node)

    try:
        executor.spin()
    except KeyboardInterrupt:
        pass
    finally:
        node.destroy_node()
        rclpy.shutdown()
