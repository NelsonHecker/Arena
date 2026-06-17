from __future__ import annotations

import contextlib
import contextvars
import typing

if typing.TYPE_CHECKING:
    from arena_simulation_setup.utils.geometry import PointResolver, Position

_active_resolver: contextvars.ContextVar[PointResolver | None] = contextvars.ContextVar(
    "_active_resolver",
    default=None,
)


def current_resolver() -> PointResolver | None:
    """Return the resolver for the world currently being parsed, or None."""
    return _active_resolver.get()


@contextlib.contextmanager
def activate_resolver(resolver: PointResolver | None) -> typing.Iterator[None]:
    """Bind *resolver* as the active world resolution context for the duration of the block."""
    token = _active_resolver.set(resolver)
    try:
        yield
    finally:
        _active_resolver.reset(token)


def resolve_zone_point(name: str) -> Position:
    """Resolve a zone/door/elevator name to a point using the active world context.

    Raises ValueError when no context is active.
    """
    resolver = _active_resolver.get()
    if resolver is None:
        raise ValueError(f"zone ref {name!r} cannot be resolved: no world resolution context active")
    return resolver.resolve(name)
