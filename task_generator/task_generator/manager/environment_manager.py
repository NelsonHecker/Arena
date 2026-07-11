import asyncio
import typing
from collections.abc import Callable, Collection, Sequence
from typing import Any

import shapely
import shapely.affinity
from arena_runtime._node import NodeInterface
from arena_runtime.sim import BaseSim
from arena_simulation_setup.shared import Ceiling
from arena_simulation_setup.tree.World import LevelDescription, WorldDescription

from task_generator.manager.realizer import Realizer
from task_generator.shared import (
    DynamicObstacle,
    Obstacle,
    Pose,
    Region,
    Robot,
    Wall,
)
from task_generator.simulators.human import BaseHumanSimulator
from task_generator.simulators.human.utils import ObstacleLayer
from task_generator.utils.flags import ObstaclesOptim, obstacles_optim_level


class EnvironmentManager(NodeInterface):
    _human_simulator: BaseHumanSimulator
    _simulator: BaseSim
    _realizer: Realizer

    _walls_geometry: shapely.MultiLineString
    _static_polygons: dict[str, shapely.Polygon]

    def __init__(
        self,
        *args: object,
        simulator: BaseSim,
        human_simulator: BaseHumanSimulator,
        realizer: Realizer,
        **kwargs: object,
    ):
        super().__init__(*args, **kwargs)

        self._simulator = simulator
        self._human_simulator = human_simulator
        self._realizer = realizer

        self._walls_geometry = shapely.MultiLineString()
        self._static_polygons = {}

    @property
    def _skip_obstacles(self) -> bool:
        """optim.obstacles=none: silently skip all static obstacle spawns."""
        return obstacles_optim_level(self.node) >= ObstaclesOptim.NONE

    def realize(self, target: object) -> object:
        return self._realizer.realize(target)

    def ezilear(self, target: Pose) -> Pose:
        return self._realizer.ezilear(target)

    @property
    def walls_geometry(self) -> shapely.MultiLineString:
        """Map-frame line geometry of all world walls and doors."""
        return self._walls_geometry

    @property
    def static_polygons(self) -> dict[str, shapely.Polygon]:
        """Map-frame footprint polygons of every static obstacle currently spawned,
        keyed by obstacle name. Includes both WORLD-layer entities and INUSE
        episode-spawned obstacles. Pedestrians are not included — consumers should
        read those from the `arena_peds` topic."""
        return self._static_polygons

    async def _resolve_polygon(self, obstacle: Obstacle) -> shapely.Polygon | None:
        try:
            view = await obstacle.model.resolve()
        except FileNotFoundError:
            return None
        bounds = view.bounds
        if bounds is None:
            return None
        poly = shapely.Polygon(bounds)
        poly = shapely.affinity.rotate(poly, obstacle.pose.orientation.to_yaw(), origin=(0, 0), use_radians=True)
        return shapely.affinity.translate(poly, xoff=obstacle.pose.position.x, yoff=obstacle.pose.position.y)

    async def _cache_polygons(self, obstacles: Sequence[Obstacle]) -> None:
        polys = await asyncio.gather(*(self._resolve_polygon(o) for o in obstacles))
        for obstacle, poly in zip(obstacles, polys, strict=True):
            if poly is not None:
                self._static_polygons[obstacle.name] = poly

    def _sync_static_polygons(self) -> None:
        """Drop polygons whose obstacle is no longer registered in the human simulator."""
        alive = set(self._human_simulator._known_obstacles.keys())
        self._static_polygons = {n: p for n, p in self._static_polygons.items() if n in alive}

    async def spawn_world_obstacles(
        self,
        world: WorldDescription | LevelDescription,
        level_id: str = "",
        detected_walls: dict[str, Sequence[Wall]] | None = None,
    ):
        """
        Loads given obstacles into the simulator,
        the map file is retrieved from launch parameter "world"

        Args:
            detected_walls: per-level occupancy-derived walls fed to the human-sim as collision geometry (populated only under debug.map_source:=disk).
        """
        await self._spawn_world_obstacles(world, level_id, detected_walls)

    async def _spawn_world_obstacles(
        self,
        world: WorldDescription | LevelDescription,
        level_id: str = "",
        detected_walls: dict[str, Sequence[Wall]] | None = None,
    ) -> None:

        def _match_level_id(fid: str | None) -> bool:
            target_id = level_id
            if target_id == "":
                return True
            else:
                if fid is not None:
                    return target_id == fid
                else:
                    return False

        _world = WorldDescription.from_levels(world) if isinstance(world, LevelDescription) else world
        walls_list: list[Wall] = []
        collision_walls: list[Wall] = []
        for fid, level in _world.levels.items():
            if not _match_level_id(fid):
                continue
            walls_list.extend(self._realizer.realize(w, fid) for w in level.all_walls)
            if detected_walls and detected_walls.get(fid):
                collision_walls.extend(self._realizer.realize(w, fid) for w in detected_walls[fid])
        walls = tuple(walls_list)
        doors = tuple(self._realizer.realize(d, fid) for fid, level in _world.levels.items() if _match_level_id(fid) for d in level.all_doors)
        floors = tuple(self._realizer.realize(f, fid) for fid, level in _world.levels.items() if _match_level_id(fid) for f in level.all_floors)
        ceilings: list[Ceiling] = []
        for fid, level in _world.levels.items():
            if not _match_level_id(fid):
                continue
            for ceiling in await level.all_ceilings():
                ceilings.append(self._realizer.realize(ceiling, fid))
        elevators = tuple(self._realizer.realize(e, fid) for fid, level in _world.levels.items() if _match_level_id(fid) for e in level.all_elevators)
        statics = tuple(self._realizer.realize(s, fid) for fid, level in _world.levels.items() if _match_level_id(fid) for s in level.all_static_entities)
        if self._skip_obstacles:
            statics = ()

        line_strings: list[shapely.LineString] = []
        for w in walls:
            line_strings.append(shapely.LineString([(w.start.x, w.start.y), (w.end.x, w.end.y)]))
        for d in doors:
            line_strings.append(shapely.LineString([(d.start.x, d.start.y), (d.end.x, d.end.y)]))
        if line_strings:
            floor_walls = shapely.MultiLineString(line_strings)
            if self._walls_geometry.is_empty:
                self._walls_geometry = floor_walls
            else:
                self._walls_geometry = shapely.MultiLineString(
                    [
                        *self._walls_geometry.geoms,
                        *floor_walls.geoms,
                    ]
                )

        await self._cache_polygons(statics)

        futures: list[typing.Awaitable] = []
        if floors:
            futures.append(self._simulator.spawn_floors(floors))
        if ceilings:
            futures.append(self._simulator.spawn_ceilings(ceilings))
        if walls or doors or collision_walls:
            futures.append(self._human_simulator.spawn_world(walls, doors, collision_walls=tuple(collision_walls)))
        futures.append(self._human_simulator.spawn_obstacles(statics, layer=ObstacleLayer.WORLD))
        if elevators:
            futures.append(self._simulator.spawn_elevators(elevators))

        await asyncio.gather(*futures)

    async def spawn_dynamic_obstacles(self, setups: Collection[DynamicObstacle]):
        """
        Loads given dynamic obstacles into the simulator.
        """
        realized = tuple(self._realizer.realize(obstacle, obstacle.level_id or "") for obstacle in setups)
        await self._human_simulator.spawn_dynamic_obstacles(realized)

    async def spawn_obstacles(self, setups: Collection[Obstacle]):
        """
        Loads given obstacles into the simulator.
        """
        if self._skip_obstacles:
            return
        realized = tuple(self._realizer.realize(obstacle, obstacle.level_id or "") for obstacle in setups)
        await self._cache_polygons(realized)
        await self._human_simulator.spawn_obstacles(realized)

    async def spawn_robot(self, robots: Sequence[Robot]) -> Sequence[Robot]:
        """
        Loads given robot into the simulator
        """
        await self._human_simulator.spawn_robot(robots=tuple(map(self.realize, robots)))
        return robots

    async def move_robot(self, robots: Sequence[Robot]) -> Sequence[bool]:
        """
        Moves given robot
        """
        return await self._human_simulator.move_robot(tuple(map(self.realize, robots)))

    async def remove_robot(self, robots: Sequence[Robot]) -> Sequence[bool]:
        """
        Deletes given robot
        """
        return await self._human_simulator.remove_robot(tuple(map(self.realize, robots)))

    async def respawn(self, callback: Callable[[], typing.Awaitable[Any]]):
        """
        Unuse obstacles, (re-)use them in callback, finally remove unused obstacles
        @callback: Function to call between unuse and remove
        """
        await self._human_simulator.unuse_obstacles()
        await callback()
        await self._human_simulator.remove_obstacles(purge=ObstacleLayer.UNUSED)
        self._sync_static_polygons()

    async def respawn_world(self, world: WorldDescription, detected_walls: dict[str, Sequence[Wall]] | None = None):
        """
        Replace world obstacles atomically: old items are only cleaned
        up after new ones have been spawned successfully.
        """
        old_walls, old_doors = self._human_simulator.unuse_world()
        await self._simulator.remove_world()
        await self.spawn_world_obstacles(world, detected_walls=detected_walls)
        self._human_simulator.remove_stale_world(old_walls, old_doors)
        await self._human_simulator.remove_obstacles(purge=ObstacleLayer.UNUSED)

    async def setup_regions(self, regions: Sequence[Region]) -> bool:
        """
        Configure regions (sources/sinks) on the human simulator.
        """
        return await self._human_simulator.setup_regions(regions)

    async def remove_all_regions(self) -> bool:
        """
        Remove all tracked regions from the human simulator.
        """
        return await self._human_simulator.remove_all_regions()

    async def reset(self, purge: ObstacleLayer = ObstacleLayer.INUSE):
        """
        Unuse and remove all obstacles
        """
        await self._human_simulator.remove_obstacles(purge=purge)
        self._sync_static_polygons()
        if purge >= ObstacleLayer.WORLD:
            self._walls_geometry = shapely.MultiLineString()

    async def step(self, n: int = 1) -> bool:
        return await self._simulator.step(n)

    async def before_reset_episode(self) -> bool:
        await self._human_simulator.pause()
        return await self._simulator.before_reset_episode()

    async def after_reset_episode(self) -> bool:
        try:
            return await self._simulator.after_reset_episode()
        finally:
            await self._human_simulator.unpause()
