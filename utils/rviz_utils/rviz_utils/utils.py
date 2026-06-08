import numpy as np


class Utils:
    @classmethod
    def generate_random_color(cls) -> list[int]:
        return list(np.random.choice(range(0, 200), size=3))

    @classmethod
    def get_random_rviz_color(cls) -> str:
        r, g, b = cls.generate_random_color()
        return f"{r}; {g}; {b}"

    @classmethod
    def get_sensor_color(cls, sensor_type: str, index: int = 0) -> str:
        """Generate appropriate colors for different sensor types."""
        if sensor_type == "sensor_msgs/msg/Imu":
            return "204; 51; 204"
        elif "FootContact" in sensor_type:
            return "255; 140; 0"
        else:
            r = (index * 67) % 200 + 55
            g = (index * 101) % 200 + 55
            b = (index * 173) % 200 + 55
            return f"{r}; {g}; {b}"
