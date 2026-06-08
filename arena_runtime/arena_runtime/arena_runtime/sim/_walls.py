from __future__ import annotations

from collections.abc import Collection

from arena_simulation_setup.shared import Obstacle, Wall
from arena_simulation_setup.tree.Wall import WallSegment
from arena_simulation_setup.utils.models import Model, ModelType


async def realize_renderable(
    wall: Wall,
    asset_types: Collection[ModelType],
) -> tuple[list[WallSegment], list[tuple[Obstacle, Model]]]:
    """Realize a wall into segments plus the obstacles whose model resolves to one of asset_types.

    Each simulator passes the formats it can render (USD for Isaac, SDF for Gazebo), so the
    realize-and-skip path is identical and only the accepted asset format differs. Obstacles
    with no acceptable model format are dropped (the loader decides).
    """
    segments, obstacles = await wall.assets()
    resolved: list[tuple[Obstacle, Model]] = []
    for obstacle in obstacles:
        try:
            model = await (await obstacle.model.resolve()).model.get(asset_types)
        except FileNotFoundError:
            continue
        if model.type is ModelType.UNKNOWN:
            continue
        resolved.append((obstacle, model))
    return list(segments), resolved
