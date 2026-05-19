"""Handlers for ``TaskKind.GOTO_POSE``.

Declarations only: each ``HANDLERS.register`` call below stores a zero-arg
loader. The actual handler modules (and their msgs deps) are imported lazily
by ``HANDLERS.get`` when that bringup is selected at node startup.
"""

from __future__ import annotations

from arena_robots_msgs.action import GotoPose

from arena_robots.task_kinds import TaskKind
from arena_robots.task_server_handlers import HANDLERS, TaskHandler

GotoPoseHandler = TaskHandler[GotoPose.Goal, GotoPose.Feedback, GotoPose.Result]


@HANDLERS.register((TaskKind.GOTO_POSE, "nav2"))
def _load_nav2() -> type[GotoPoseHandler]:
    from .nav2 import GotoPoseHandlerNav2

    return GotoPoseHandlerNav2


@HANDLERS.register((TaskKind.GOTO_POSE, "test-collision"))
def _load_test_collision() -> type[GotoPoseHandler]:
    from ._passthrough import GotoPoseHandlerNone

    return GotoPoseHandlerNone


@HANDLERS.register((TaskKind.GOTO_POSE, "none"))
def _load_none() -> type[GotoPoseHandler]:
    from ._passthrough import GotoPoseHandlerNone

    return GotoPoseHandlerNone


@HANDLERS.register((TaskKind.GOTO_POSE, "external"))
def _load_external() -> type[GotoPoseHandler]:
    from ._passthrough import GotoPoseHandlerExternal

    return GotoPoseHandlerExternal


@HANDLERS.register((TaskKind.GOTO_POSE, "manual"))
def _load_manual() -> type[GotoPoseHandler]:
    from ._passthrough import GotoPoseHandlerNone

    return GotoPoseHandlerNone


@HANDLERS.register((TaskKind.GOTO_POSE, "rosnav_rl"))
def _load_rosnav_rl() -> type[GotoPoseHandler]:
    from ._passthrough import GotoPoseHandlerRosnavRl

    return GotoPoseHandlerRosnavRl
