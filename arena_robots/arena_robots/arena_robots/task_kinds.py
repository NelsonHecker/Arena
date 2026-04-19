"""Single source of truth for task kinds and their public endpoint names."""

import enum

from arena_rclpy_mixins.shared import Namespace


class TaskKind(enum.Enum):
    GOTO_POSE = "goto_pose"


PUBLIC_SUFFIX: dict[TaskKind, str] = {
    TaskKind.GOTO_POSE: "goto_pose",
}


def action_type(tk: TaskKind) -> type:
    if tk is TaskKind.GOTO_POSE:
        from arena_robots_msgs.action import GotoPose
        return GotoPose
    raise KeyError(tk)


def endpoint(namespace: str, tk: TaskKind) -> str:
    return Namespace(namespace)(PUBLIC_SUFFIX[tk])
