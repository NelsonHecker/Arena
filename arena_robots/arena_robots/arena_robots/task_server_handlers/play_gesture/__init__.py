"""Handlers for ``TaskKind.PLAY_GESTURE``.

Declarations only: each ``HANDLERS.register`` call below stores a zero-arg
loader. The actual handler modules (and their msgs deps) are imported lazily
by ``HANDLERS.get`` when that bringup is selected at node startup.
"""

from __future__ import annotations

from arena_robots_msgs.action import PlayGesture

from arena_robots.task_kinds import TaskKind
from arena_robots.task_server_handlers import HANDLERS, TaskHandler

PlayGestureHandler = TaskHandler[PlayGesture.Goal, PlayGesture.Feedback, PlayGesture.Result]


@HANDLERS.register((TaskKind.PLAY_GESTURE, "moveit"))
def _load_moveit() -> type[PlayGestureHandler]:
    from .moveit import PlayGestureHandlerMoveIt

    return PlayGestureHandlerMoveIt
