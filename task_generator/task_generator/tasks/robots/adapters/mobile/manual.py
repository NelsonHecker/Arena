"""Manual teleop adapter (mobile: manual).

Drives the robot via rqt_robot_steering publishing Twist on the robot's
`cmd_vel`. Task dispatch is a no-op and is_phase_done returns None so the
phase only ends when its own predicate fires; otherwise the user-driven
robot would be teleported back to spawn on every poll.
"""

from __future__ import annotations

from typing import TYPE_CHECKING, ClassVar

from arena_robots.bringup.mobile.manual import ManualBringup
from arena_robots.clients.goto_pose import GotoPoseClient
from arena_robots.task_kinds import TaskKind

from task_generator.tasks.robots.adapters import AdapterMeta
from task_generator.tasks.robots.adapters.mobile import MobileAdapter

if TYPE_CHECKING:
    from task_generator.manager.robot_manager.robot_manager import RobotManager
    from task_generator.tasks.robots.request import TaskPhase


@AdapterMeta.attach(
    accepts={TaskKind.GOTO_POSE},
    bringup=ManualBringup,
    client=GotoPoseClient,
    cap="mobile",
)
class ManualAdapter(MobileAdapter):
    kind: ClassVar[str] = "manual"

    def is_phase_done(self, phase: TaskPhase, robot: RobotManager) -> bool | None:
        return None

    async def dispatch_phase(self, phase: TaskPhase, robot: RobotManager) -> None:
        return None
