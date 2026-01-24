from rclpy.node import Node

import numpy as np

from geometry_msgs.msg import Point
from visualization_msgs.msg import Marker, MarkerArray
from std_msgs.msg import ColorRGBA

from hunav_msgs.srv import SetVelocityField


class VelocityFieldVisualizer:
    def __init__(
        self,
        node: Node,
        map_min_x: float = 0.0,
        map_min_y: float = 0.0,
        map_max_x: float = 0.0,
        map_max_y: float = 0.0,
        topic_name: str = "/velocity_field_maker",
        service_name: str = "/set_velocity_field",
    ):
        self.node = node
        self._logger = node.get_logger()

        # Internal state for coordinate conversion
        self.map_min_x = map_min_x
        self.map_min_y = map_min_y
        self.map_max_x = map_max_x
        self.map_max_y = map_max_y

        # RViz Publisher
        self.marker_pub = self.node.create_publisher(MarkerArray, topic_name, 10)

        # Initialize the Service to listen for velocity field updates
        self.srv = self.node.create_service(
            SetVelocityField, service_name, self._handle_set_velocity_field
        )

        self._logger.info(f"Velocity Visualizer initialized on {service_name}")

    def update_world_bounds(self, x_min, y_min, x_max, y_max):
        """Update bounds used for coordinate mapping."""
        self.map_min_x = x_min
        self.map_min_y = y_min
        self.map_max_x = x_max
        self.map_max_y = y_max

    def _handle_set_velocity_field(
        self, request: SetVelocityField.Request, response: SetVelocityField.Response
    ):
        """Callback when the generation pipeline sends a new velocity field."""
        try:
            # Extract dimensions from MultiArrayLayout
            # Layout: [groups, H, W, C]
            dims = {d.label: d.size for d in request.velocity_field.layout.dim}
            g, h, w, c = dims["G"], dims["H"], dims["W"], dims["C"]

            # Reshape data
            raw_data = np.array(request.velocity_field.data)
            # We take the first group [0] for visualization
            field = raw_data.reshape(g, h, w, c)[0]

            self.publish_markers(field)

            response.success = True
            response.message = "Markers published to RViz"
        except Exception as e:
            response.success = False
            response.message = f"Visualization failed: {str(e)}"
            self._logger.error(response.message)

        return response

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
        self._logger.info(
            f"Publishing marbers for grid: {h}x{w}, world: {world_height}x{world_width}"
        )

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
                    self._logger.warn("Velocity too small")
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
                marker.scale.x = 0.05  # Shaft diameter
                marker.scale.y = 0.1  # Head diameter
                marker.scale.z = 0.1  # Head length
                marker.color = ColorRGBA(r=0.0, g=1.0, b=1.0, a=0.8)  # Cyan

                marker_array.markers.append(marker)
                id_counter += 1

        # Clear previous markers if the new set is smaller
        self.marker_pub.publish(marker_array)
