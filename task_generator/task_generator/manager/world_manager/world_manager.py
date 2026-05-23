import itertools
import math
from collections.abc import Collection
from math import floor
import typing

import attrs

import arena_simulation_setup.tree.World as World
import numpy as np
import scipy.signal
import shapely
from arena_runtime._node import NodeInterface

from task_generator.shared import Position, PositionRadius, Wall

from .utils import WorldMap, WorldOccupancy, MultiLevelMap


def _disc_kernel(safe_dist_cells: float) -> np.ndarray:
    """L2 disc of radius safe_dist_cells, normalised so sum == 1."""
    r = max(1, int(math.ceil(safe_dist_cells)))
    yy, xx = np.ogrid[-r : r + 1, -r : r + 1]
    mask = (xx * xx + yy * yy) <= (safe_dist_cells * safe_dist_cells)
    kernel = mask.astype(np.float32)
    return kernel / kernel.sum()


def _occupancy_to_available(occupancy: np.ndarray, safe_dist_cells: float) -> np.ndarray:
    """Return (row, col) cells whose Euclidean safe_dist_cells neighbourhood is fully not-full. Off-map counts as full."""
    kernel = _disc_kernel(safe_dist_cells)
    free = WorldOccupancy.not_full(occupancy).astype(np.float32)
    spread = scipy.signal.convolve2d(free, kernel, mode="same", boundary="fill", fillvalue=0.0)
    available = np.isclose(spread, 1.0)
    return np.transpose(np.where(available))


def _sample_from_candidates(
    available: np.ndarray,
    n: int,
    safe_dist_cells: float,
    rng: np.random.Generator,
    *,
    max_depth: int = 10,
) -> np.ndarray:
    """Pick n cells from `available` (row, col) keeping safe_dist_cells separation between picks.

    Returns an (n, 2) int array. Raises RuntimeError if fewer than n cells fit.
    """
    if n <= 0:
        return np.zeros((0, 2), dtype=np.int64)

    if len(available) < n:
        raise RuntimeError(f"need {n} positions, only {len(available)} candidate cells available")

    accepted = np.zeros((n, 2), dtype=np.int64)
    accepted_n = 0

    for _ in range(max_depth):
        need = n - accepted_n
        if need <= 0:
            break
        if need > len(available):
            raise RuntimeError(f"need {need} more positions, only {len(available)} candidate cells available")
        for idx in rng.choice(len(available), need, replace=False):
            candidate = available[idx]
            if accepted_n and np.any(np.linalg.norm(accepted[:accepted_n] - candidate, axis=1) < safe_dist_cells):
                continue
            accepted[accepted_n] = candidate
            accepted_n += 1
            if accepted_n >= n:
                break

    if accepted_n < n:
        raise RuntimeError(f"failed to find {n} positions with safe_dist={safe_dist_cells} cells after {max_depth} retries")

    return accepted


def _sample_grid_positions(
    occupancy: np.ndarray,
    n: int,
    safe_dist_cells: float,
    rng: np.random.Generator,
    *,
    max_depth: int = 10,
) -> np.ndarray:
    """Pick n (row, col) cells with Euclidean safe_dist_cells clearance from non-empty cells and from each other."""
    available = _occupancy_to_available(occupancy, safe_dist_cells)
    return _sample_from_candidates(available, n, safe_dist_cells, rng, max_depth=max_depth)


class WorldManager(NodeInterface):
    """
    The map manager manages the static map
    and is used to get new goal, robot and
    obstacle positions.
    """

    _world: World.MultiLevelWorld
    _map: WorldMap # main map used that has all of the floors
    _multi_map: MultiLevelMap | None # this is just a utility reference maps for level-specific get position operations. The actual occupancy is managed by _map
    _classic_forbidden_zones: list[PositionRadius]
    _default_floor_id: str

    def __init__(self, *args: object, **kwargs: object) -> None:
        super().__init__(*args, **kwargs)
        self._detected_walls = None
        self._classic_forbidden_zones = []
        self._multi_map = None
        self._default_floor_id = ""

    @property
    def world(self) -> World.MultiLevelWorld:
        return self._world

    def world_description(self) -> World.WorldDescription | None:
        return self._world.as_world_description()

    def world_default_level(self) -> World.WorldDescription:
        single = self._world.as_world_description()
        if single is not None:
            return single
        level = self._world.get_level(self._default_floor_id)
        if level is None:
            level = next(iter(self._world.all_levels))
        return level

    @property
    def map(self) -> WorldMap:
        return self._map

    @property
    def level_maps(self) -> MultiLevelMap:
        return self._multi_map if self._multi_map is not None else MultiLevelMap.from_single(self._map)

    def map_for_floor(self, floor_id: str = "") -> WorldMap:
        if self._multi_map is None:
            return self._map
        return self._multi_map.get_map(floor_id) or self._map

    @property
    def _shape(self) -> tuple[int, int]:
        return self._map.shape[0], self._map.shape[1]

    @property
    def origin(self) -> Position:
        return self._map.origin

    @property
    def resolution(self) -> float:
        return self._map.resolution

    _detected_walls: Collection[Wall] | None = None

    @property
    def detected_walls(self) -> Collection[Wall]:
        if self._detected_walls is None:
            self._detected_walls = self._map.detect_walls()
        return self._detected_walls

    def update_world(
        self,
        world_map: WorldMap,
        world_description: World.MultiLevelWorld,
        multi_level_map: MultiLevelMap | None = None,
    ):
        self._detected_walls = None
        self._map = world_map
        self._multi_map = multi_level_map
        self._default_floor_id = next(iter(world_description.floor_ids), "")

        counter = itertools.count(0)
        for entity in itertools.chain(world_description.all_static_entities, world_description.all_dynamic_entities):
            if not entity.name:
                entity.name = f'{next(counter)}_{entity.model.name}'
            entity.name = f'world_{entity.name}'

        self._world = world_description

        for obstacle in self.world.all_static_entities:
            level_id = obstacle.floor_id
            level_origin = self.map.level_origins[level_id] if level_id is not None else (0,0)
            self.map.occupancy.obstacle_occupy(
                *self.map.tf_posr2rect(
                    PositionRadius(
                        x=obstacle.pose.position.x + level_origin[0],
                        y=obstacle.pose.position.y + level_origin[1],
                        radius=1,  # TODO actual radius
                    )
                )
            )
            map = self.level_maps.get_map(level_id)
            if map is not None:
                map.occupancy.obstacle_occupy(
                    *map.tf_posr2rect(
                        PositionRadius(
                            x=obstacle.pose.position.x,
                            y=obstacle.pose.position.y,
                            radius=1,  # TODO actual radius
                        )
                    )
                )

    def forbid(self, forbidden_zones: list[PositionRadius], floor_id: str = ""):
        world_map = self.map_for_floor(floor_id)
        for zone in forbidden_zones:
            world_map.occupancy.forbidden_occupy(*world_map.tf_posr2rect(zone))

    def forbid_clear(self, floor_id: str = ""):
        world_map = self.map_for_floor(floor_id)
        world_map.occupancy.forbidden_clear()

    def get_positions_on_map(
        self,
        n: int,
        safe_dist: float,
        forbidden_zones: list[PositionRadius] | None = None,
        forbid: bool = True,
        polygon: shapely.Polygon | None = None,
        level_id: str = ""
    ) -> list[Position]:
        """Sample n map positions with Euclidean safe_dist (metres) clearance from obstacles and from each other.

        If `polygon` is given, candidate cells ar
        If level_id is specified, return the local coordinate of the spawn position specific to that floor.
        If not, return the position in the global (all-floor) context.e restricted to those whose world coords lie inside it.

        Raises RuntimeError if fewer than n positions fit.
        """

        if forbidden_zones is None:
            forbidden_zones = []

        level_polygons: list[shapely.Polygon] | None = None

        # For level-specific queries, default to sampling inside that level's zones
        # (map rasters include padding around geometry, which is otherwise spawnable).
        if polygon is None and level_id:
            level = self._world.get_level(level_id)
            if level is not None:
                level_polygons = [
                    shapely.Polygon([(corner.x, corner.y) for corner in zone.corners])
                    for zone in level.zones
                    if len(zone.corners) >= 3
                ]
                if not level_polygons:
                    level_polygons = None

        select_from_whole_map  = level_id == ""
        map = self.map if select_from_whole_map  or self._multi_map is None else self._multi_map.select_map(level_id)
        origin = (0.0, 0.0) if select_from_whole_map else self.map.get_origin(level_id)
        origin_cell = (origin[1] / self.resolution, origin[0] / self.resolution) # row, col order
        fork = map.occupancy.fork()
        for zone in forbidden_zones:
            fork.occupy(*map.tf_posr2rect(zone))

        safe_dist_cells = safe_dist / self.resolution
        rng = self.node.conf.General.RNG.value
        available = _occupancy_to_available(fork.grid, safe_dist_cells)

        if len(available) and (polygon is not None or level_polygons is not None):
            world_xy = np.array(
                [(p.x, p.y) for p in (map.tf_grid2pos((int(r), int(c))) for r, c in available)],
            )
            if polygon is not None:
                available = available[shapely.contains_xy(polygon, world_xy[:, 0], world_xy[:, 1])]
            elif level_polygons is not None:
                mask = np.zeros(len(available), dtype=bool)
                for level_polygon in level_polygons:
                    mask |= shapely.contains_xy(level_polygon, world_xy[:, 0], world_xy[:, 1])
                available = available[mask]

        cells = _sample_from_candidates(available, n, safe_dist_cells, rng)

        if forbid:
            if select_from_whole_map:
                halo = int(math.ceil(safe_dist_cells))
                for row, col in cells:
                    fork.occupy((int(col) - halo, int(row) - halo), (int(col) + halo, int(row) + halo))
                fork.commit()

        # if selecting from a specific floor, reflect that occupancy to the main map
            else:
                whole_map_fork = self.map.occupancy.fork()
                halo = int(math.ceil(safe_dist_cells))
                for row, col in cells:
                    whole_map_fork.occupy((int(col + origin_cell[1]) - halo, int(row + origin_cell[0]) - halo), (int(col + origin_cell[1]) + halo, int(row + origin_cell[0]) + halo))
                whole_map_fork.commit()

        return [map.tf_grid2pos((int(row), int(col))) for row, col in cells]

    def get_position_on_map(self, safe_dist: float, forbidden_zones: list[PositionRadius] | None = None, forbid: bool = True, level_id: str = "") -> Position:
        return self.get_positions_on_map(n=1, safe_dist=safe_dist, forbidden_zones=forbidden_zones, forbid=forbid, level_id=level_id)[0]

    id_gen = itertools.count()
