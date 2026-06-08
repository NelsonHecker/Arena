"""Internal REGISTRY dict and register decorator. Imported by renderer modules."""

from __future__ import annotations

from typing import Callable

from arena_viz import DisplayKind
from task_generator_msgs.msg import AdapterDisplay, RobotDescriptor

RendererFn = Callable[[AdapterDisplay, "RobotDescriptor | None"], "dict[str, object] | None"]

REGISTRY: dict[DisplayKind, RendererFn] = {}


def register(kind: DisplayKind) -> Callable[[RendererFn], RendererFn]:
    """Decorator that registers a renderer for a DisplayKind."""

    def decorator(fn: RendererFn) -> RendererFn:
        REGISTRY[kind] = fn
        return fn

    return decorator
