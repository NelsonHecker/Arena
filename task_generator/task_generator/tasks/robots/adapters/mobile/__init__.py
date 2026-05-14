from __future__ import annotations

from typing import TYPE_CHECKING

from task_generator.tasks.robots.adapters import ADAPTERS, Adapter

if TYPE_CHECKING:
    from task_generator.manager.robot_manager.robot_manager import RobotManager
    from task_generator.tasks.robots.adapters import ResetContext


class MobileAdapter(Adapter):
    async def on_reset(self, robot: RobotManager, ctx: ResetContext) -> None:
        if ctx.start_pose is not None:
            await robot.move(ctx.start_pose)


@ADAPTERS["mobile"].register("nav2")
def _load_nav2() -> type[Adapter]:
    from .nav2 import Nav2Adapter

    return Nav2Adapter


@ADAPTERS["mobile"].register("external")
def _load_external() -> type[Adapter]:
    from .external import ExternalAdapter

    return ExternalAdapter


@ADAPTERS["mobile"].register("rosnav_rl")
def _load_rosnav_rl() -> type[Adapter]:
    from .rosnav_rl import RosnavRlAdapter

    return RosnavRlAdapter


@ADAPTERS["mobile"].register("none")
def _load_none() -> type[Adapter]:
    from .none import NoneAdapter

    return NoneAdapter


@ADAPTERS["mobile"].register("test-collision")
def _load_test_collision() -> type[Adapter]:
    from .test_collision import TestCollisionAdapter

    return TestCollisionAdapter
