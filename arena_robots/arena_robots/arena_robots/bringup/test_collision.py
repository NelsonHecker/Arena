from __future__ import annotations

from launch import Action
from launch.actions import ExecuteProcess

from arena_robots.bringup import Bringup


class TestCollisionBringup(Bringup):
    kind = "test-collision"
    requires = frozenset({"mobile"})

    @property
    def goal_topic(self) -> str:
        return self.namespace("goal_pose")

    def _launch_actions(
        self,
        *,
        use_sim_time: bool = True,
        frame: str = "",
        linear_x: float = 1.0,
        rate_hz: float = 10.0,
        **_: object,
    ) -> list[Action]:
        cmd_vel_topic = str(self.namespace("cmd_vel"))
        twist = f"{{linear: {{x: {float(linear_x)}, y: 0.0, z: 0.0}}, angular: {{x: 0.0, y: 0.0, z: 0.0}}}}"
        return [
            ExecuteProcess(
                cmd=[
                    "ros2",
                    "topic",
                    "pub",
                    "-r",
                    str(float(rate_hz)),
                    cmd_vel_topic,
                    "geometry_msgs/msg/Twist",
                    twist,
                ],
                output="log",
            ),
        ]
