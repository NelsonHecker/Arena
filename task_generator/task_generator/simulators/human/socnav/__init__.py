
import attrs
from arena_simulation_setup.shared import DynamicObstacle


@attrs.define
class SocnavPedestrian(DynamicObstacle):
    spawn_at: int = 0  # frame to spawn at

    @property
    def last_frame(self) -> int:
        return self.spawn_at + len(self.waypoints)
