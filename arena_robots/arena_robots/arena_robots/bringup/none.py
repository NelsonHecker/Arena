from __future__ import annotations

from launch import Action
from launch.actions import IncludeLaunchDescription
from launch.launch_description_sources import PythonLaunchDescriptionSource
from launch.substitutions import PathJoinSubstitution
from launch_ros.substitutions import FindPackageShare

from arena_robots.bringup import Bringup


class NoneBringup(Bringup):
    kind = "none"
    requires = frozenset({"mobile"})

    @property
    def goal_topic(self) -> str:
        return self.namespace("goal_pose")

    def _launch_actions(
        self,
        *,
        use_sim_time: bool = True,
        frame: str = "",
        **_: object,
    ) -> list[Action]:
        launch_file = PathJoinSubstitution(
            [
                FindPackageShare("arena_robots"),
                "launch",
                "adapters",
                "none.launch.py",
            ]
        )
        return [
            IncludeLaunchDescription(
                PythonLaunchDescriptionSource(launch_file),
            )
        ]
