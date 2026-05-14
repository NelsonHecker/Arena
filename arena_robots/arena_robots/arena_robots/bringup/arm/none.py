from __future__ import annotations

from launch import Action

from arena_robots.bringup import Bringup, BringupMeta


@BringupMeta.attach(requires={"arm"}, cap="arm")
class NoneArmBringup(Bringup):
    kind = "none"

    @property
    def goal_topic(self) -> str:
        return self.namespace("reach_pose_goal")

    def _launch_actions(
        self,
        *,
        use_sim_time: bool = True,
        frame: str = "",
        **_: object,
    ) -> list[Action]:
        return []
