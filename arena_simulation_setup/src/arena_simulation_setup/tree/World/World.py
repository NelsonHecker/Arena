import io
import math
import os
import tarfile
import typing
from collections.abc import Iterator
from copy import deepcopy
from pathlib import Path

import attrs
import numpy as np
import yaml
from typing_extensions import Self

from arena_simulation_setup import ASS_DIR
from arena_simulation_setup.shared import (
    Door,
    DynamicObstacle,
    Elevator,
    Floor,
    Obstacle,
    Wall,
)
from arena_simulation_setup.tree import FallbackResolver, Identifier, PathView
from arena_simulation_setup.tree.assets.Material import (
    Material,
    MaterialIdentifier,
)
from arena_simulation_setup.utils.cattrs import ArenaConverter, converter
from arena_simulation_setup.utils.geometry import Orientation, Pose, Position, sample_point_in_polygon

from .Map import Map
from .Scenario import RegionAssignment, ScenarioView


@attrs.define
class WorldDescription:
    """
    Description of the 3D world
    """

    @attrs.define
    class Zone:
        """
        Description of a zone (e.g. room) within the 3D world
        """

        @attrs.define
        class WorldEntities:
            """
            Description of the entities within the 3D world
            """

            static: list[Obstacle] = attrs.field(factory=list)
            dynamic: list[DynamicObstacle] = attrs.field(factory=list)

        name: str
        description: str = ''
        material: MaterialIdentifier = attrs.field(
            converter=MaterialIdentifier.converter,
            default=Material.default('floor'),
        )
        corners: list[Position] = attrs.field(factory=list)
        walls: list[Wall] = attrs.field(factory=list)
        doors: list[Door] = attrs.field(factory=list)
        elevators: list[Elevator] = attrs.field(factory=list)
        entities: WorldEntities = attrs.field(factory=WorldEntities)

        @property
        def floor(self) -> Floor:
            x_min = min(corner.x for corner in self.corners)
            y_min = min(corner.y for corner in self.corners)
            x_max = max(corner.x for corner in self.corners)
            y_max = max(corner.y for corner in self.corners)
            pos = Position(x=(x_min + x_max) / 2, y=(y_min + y_max) / 2)
            x_length = x_max - x_min
            y_length = y_max - y_min
            return Floor(name=self.name, pos=pos, x_length=x_length, y_length=y_length, material=self.material)

    zones: list[Zone] = attrs.field(factory=list)

    @property
    def all_walls(self) -> typing.Iterable[Wall]:
        return (wall for zone in self.zones for wall in zone.walls)

    @property
    def all_doors(self) -> typing.Iterable[Door]:
        return (door for zone in self.zones for door in zone.doors)

    @property
    def all_elevators(self) -> typing.Iterable[Elevator]:
        return (elevator for zone in self.zones for elevator in zone.elevators)

    @property
    def all_elevator_names(self) -> typing.Iterable[str]:
        return (elevator.name for zone in self.zones for elevator in zone.elevators)

    @property
    def all_floors(self) -> typing.Iterable[Floor]:
        return (zone.floor for zone in self.zones)

    @property
    def all_static_entities(self) -> typing.Iterable[Obstacle]:
        return (entity for zone in self.zones for entity in zone.entities.static)

    @property
    def all_dynamic_entities(self) -> typing.Iterable[DynamicObstacle]:
        return (entity for zone in self.zones for entity in zone.entities.dynamic)

<<<<<<< HEAD
    def shift_all_positions(self, dx: float, dy: float):
        diff: Position = Position(dx, dy)
        for zone in self.zones:
            for idx, corner in enumerate(zone.corners):
                zone.corners[idx] = corner + diff
        for wall in self.all_walls:
            wall.start = wall.start + diff
            wall.end = wall.end + diff
        for door in self.all_doors:
            door.start = door.start + diff
            door.end = door.end + diff
        for elevator in self.all_elevators:
            elevator.position = elevator.position + diff
        for static_entity in self.all_static_entities:
            static_entity.pose.position = static_entity.pose.position + diff
        for dynamic_entity in self.all_dynamic_entities:
            dynamic_entity.pose.position = dynamic_entity.pose.position + diff
            for idx, wp in enumerate(dynamic_entity.waypoints):
                dynamic_entity.waypoints[idx] = wp + diff
=======
    def lookup_zone_polygon(self, name: str) -> list[Position] | None:
        """Look up a zone, door, or elevator by name and return its polygon vertices."""
        for zone in self.zones:
            if zone.name == name:
                return zone.corners
            for door in zone.doors:
                if door.name == name:
                    return _door_polygon(door.start, door.end)
            for elevator in zone.elevators:
                if elevator.name == name:
                    return elevator.cabin_corners()
        return None

    def zone_converter(
        self,
        rng: np.random.Generator,
        *,
        is_valid: typing.Callable[[Position], bool] | None = None,
    ) -> ArenaConverter:
        """Return a converter that resolves zone/door/elevator names to geometry.

        String values for Pose/Position fields are resolved by sampling a
        random point within the named zone polygon. RegionAssignment dicts
        with a ``ref`` key get their polygon resolved from the world.
        """
        lookup = self.lookup_zone_polygon

        base_pose_hook = converter.get_structure_hook(Pose)
        base_position_hook = converter.get_structure_hook(Position)
        base_region_hook = converter.get_structure_hook(RegionAssignment)

        def pose_hook(v: object, t: type) -> Pose:
            if isinstance(v, str):
                polygon = lookup(v)
                if polygon is None:
                    raise ValueError(f"zone ref '{v}' not found in world")
                pt = sample_point_in_polygon(polygon, rng, is_valid=is_valid)
                return Pose(position=pt, orientation=Orientation.identity())
            return base_pose_hook(v, t)

        def position_hook(v: object, t: type) -> Position:
            if isinstance(v, str):
                polygon = lookup(v)
                if polygon is None:
                    raise ValueError(f"zone ref '{v}' not found in world")
                return sample_point_in_polygon(polygon, rng, is_valid=is_valid)
            return base_position_hook(v, t)

        def region_hook(v: object, t: type) -> RegionAssignment:
            if isinstance(v, dict) and 'ref' in v:
                ref = v.pop('ref')
                polygon = lookup(ref)
                if polygon is None:
                    raise ValueError(f"region ref '{ref}' not found in world")
                v['polygon'] = polygon
            return base_region_hook(v, t)

        c = converter.copy()
        c.register_structure_hook(Pose, pose_hook)
        c.register_structure_hook(Position, position_hook)
        c.register_structure_hook(RegionAssignment, region_hook)
        return c
>>>>>>> feature/mechanism-shim

    def _rasterize_kwargs(
        self,
        *,
        default_asset_bbox: tuple[tuple[float, float], tuple[float, float]] | None = None,
        asset_color: str | None = None,
        asset_name_color: str | None = None,
    ) -> dict[str, typing.Any]:
        import shapely
        import shapely.affinity

        map_kwargs: dict[str, typing.Any] = {
            "rooms": shapely.MultiPolygon([shapely.Polygon(zone.corners) for zone in self.zones]),
            "doors": shapely.MultiPolygon([poly for door in self.all_doors for poly in _render_door_polygons(door)] + [poly for elevator in self.all_elevators for poly in _render_elevator_polygons(elevator)]),
            "walls": shapely.MultiLineString(list(self.all_walls)),
            "padding": 5,
        }

        if asset_color is not None:
            static_objects: list[tuple[str, shapely.Polygon]] = []
            for entity in self.all_static_entities:
                try:
                    bbox = entity.asdict(expand_extra=True).get('bbox')
                    if bbox is None:
                        if default_asset_bbox is None:
                            raise ValueError(f"Static entity '{entity.name}' does not have a bbox and no default_asset_bbox was provided.")
                        bbox = default_asset_bbox
                    (x_min, x_max), (y_min, y_max), *_ = bbox
                except Exception:
                    continue
                poly = shapely.box(x_min, y_min, x_max, y_max)
                poly = shapely.affinity.rotate(poly, entity.pose.orientation.to_yaw(), use_radians=True)
                poly = shapely.affinity.translate(poly, entity.pose.position.x, entity.pose.position.y)
                static_objects.append((entity.name, poly))

            map_kwargs["static_objects"] = static_objects
            map_kwargs["asset_color"] = asset_color
            map_kwargs["asset_name_color"] = asset_name_color

        return map_kwargs

    def render(
        self,
        resolution: float = 0.05,
        *,
        default_asset_bbox: tuple[tuple[float, float], tuple[float, float]] | None = None,
        asset_color: str | None = None,
        asset_name_color: str | None = None,
    ) -> tuple[bytes, tuple[float, float]]:
        """
        Render the world description to a PNG image.

        Args:
            resolution (float): The resolution of the rendered image in meters per pixel.
            default_asset_bbox (Optional[tuple[tuple[float, float], tuple[float, float]]]): Default bounding box ((xmin, xmax), (ymin, ymax)) to use for static entities if not specified individually.
            asset_color (Optional[str]): Color used to fill static objects in the map.
            asset_name_color (Optional[str]): Color used for static object names in the map.

        Returns:
            Tuple[bytes, tuple[float, float]]: PNG image bytes and the origin (x, y) of the map.

        Notes:
            - Static objects are drawn only if their dimensions can be determined from bbox, width/height, or default_asset_bbox.
            - If asset_color is None, static objects are not drawn.
        """
        return Map.generate_png(
            resolution=resolution,
            **self._rasterize_kwargs(
                default_asset_bbox=default_asset_bbox,
                asset_color=asset_color,
                asset_name_color=asset_name_color,
            ),
        )

    def render_grid(
        self,
        resolution: float = 0.05,
        *,
        default_asset_bbox: tuple[tuple[float, float], tuple[float, float]] | None = None,
        asset_color: str | None = None,
        asset_name_color: str | None = None,
    ) -> tuple[np.ndarray, tuple[float, float]]:
        """Like `render` but returns a uint8 numpy array (255=free, 0=occupied) + origin."""
        return Map.rasterize(
            resolution=resolution,
            **self._rasterize_kwargs(
                default_asset_bbox=default_asset_bbox,
                asset_color=asset_color,
                asset_name_color=asset_name_color,
            ),
        )

    def export(self, resolution: float = 0.05, extra_files: dict[str, bytes] | None = None, **kwargs: object) -> tarfile.TarFile:
        """
        Export the world description to world.yaml, map.png, map.yaml
        """

        if extra_files is None:
            extra_files = {}
        files: dict[str, bytes] = {**extra_files}

        files['world.yaml'] = typing.cast(bytes, yaml.safe_dump(converter.unstructure(self), encoding='utf-8', sort_keys=False))

        render_args: dict[str, typing.Any] = {"resolution": resolution}
        if "default_asset_bbox" in kwargs:
            render_args["default_asset_bbox"] = kwargs["default_asset_bbox"]
        if "asset_color" in kwargs:
            render_args["asset_color"] = kwargs["asset_color"]
        if "asset_name_color" in kwargs:
            render_args["asset_name_color"] = kwargs["asset_name_color"]

        files['map/map.png'], origin = self.render(**render_args)

        files['map/map.yaml'] = Map.generate_map_yaml(resolution=resolution, filename='map.png', origin=origin).encode('utf-8')

        with io.BytesIO() as tar_stream:
            with tarfile.open(mode='w', fileobj=tar_stream) as tarball:
                for filename, content in files.items():
                    info = tarfile.TarInfo(name=os.path.normpath(filename))
                    info.size = len(content)
                    tarball.addfile(tarinfo=info, fileobj=io.BytesIO(content))
            tar_stream.seek(0)
            return tarfile.open(fileobj=io.BytesIO(tar_stream.getvalue()))


@attrs.define
class ElevatorDescriptor:
    """
    Elevator descriptor in multi-level context.
    Stores destination mapping by floor id.
    """

    name: str = attrs.field(default='')
    destinations_dict: dict[str, str] = attrs.field(factory=dict)

    @classmethod
    def from_elevator(cls, elevator: Elevator) -> 'ElevatorDescriptor':
        return cls(name=elevator.name)

    @property
    def all_destinations(self) -> typing.Iterable[typing.Tuple[str, str]]:
        return ((floor_id, elevator_name) for floor_id, elevator_name in self.destinations_dict.items())

    def add_destination(self, destination: str, floor_id: str):
        if floor_id in self.destinations_dict:
            raise RuntimeError(
                f"Error occured while adding a new destination to elevator {self.name}: "
                f"floor {floor_id} of destination is already occupied"
            )
        self.destinations_dict[floor_id] = destination

    def change_destination(self, new_destination: str, floor_id: str):
        self.destinations_dict[floor_id] = new_destination

    def _map_floor_ids(self, ids_map: dict[str, str]) -> 'ElevatorDescriptor':
        remapped = ElevatorDescriptor(name=self.name)
        for old_floor_id, elevator_name in self.destinations_dict.items():
            if old_floor_id not in ids_map:
                raise RuntimeError(
                    f"when applying floor id changes, could not find floor id {old_floor_id} "
                    f"in the set of keys of floor id mapping"
                )
            remapped.add_destination(elevator_name, ids_map[old_floor_id])
        return remapped

    def map_floor_ids(self, ids_map: dict[str, str]):
        self.destinations_dict = self._map_floor_ids(ids_map).destinations_dict


# Backward-compatible alias used by existing downstream code.
LevelElevator = ElevatorDescriptor


@attrs.define
class Level(WorldDescription):
    levelElevators: list[ElevatorDescriptor] = attrs.field(factory=list)

    @classmethod
    def from_world_description(cls, world_description: WorldDescription) -> 'Level':
        return cls(zones=world_description.zones)

    # Backward-compatible alias used by existing downstream code.
    @classmethod
    def from_worldDescription(cls, _worldDescription: WorldDescription) -> 'Level':
        return cls.from_world_description(_worldDescription)

    def map_floor_ids(self, ids_map: dict[str, str]):
        for level_elevator in self.levelElevators:
            level_elevator.map_floor_ids(ids_map)

    def all_elevator_names(self) -> typing.Iterable[str]:
        return (elevator.name for elevator in self.all_elevators)


@attrs.define
class Shaft:
    id: str
    position: typing.Optional[Position] = None
    elevators: dict[str, str] = attrs.field(factory=dict)

    def add_elevator(self, floor_id: str, elevator_name: str):
        if floor_id in self.elevators:
            raise RuntimeError(f"shaft {self.id} already has an elevator mapped for floor {floor_id}")
        self.elevators[floor_id] = elevator_name


@attrs.define
class MultiLevelWorld:
    levels: dict[str, Level] = attrs.field(factory=dict) # level (floor) by its floor id
    shafts: dict[str, Shaft] = attrs.field(factory=dict) # shaft by its shaft id

    @property
    def floor_ids(self) -> typing.Iterable[str]:
        return self.levels.keys()

    @property
    def all_elevator_names(self) -> typing.Iterable[str]:
        return (
            elevator.name
            for level in self.levels.values()
            for elevator in level.all_elevators
        )

    @property
    def all_levels(self) -> typing.Iterable[Level]:
        return (
            level
            for level in self.levels.values()
        )

    @property
    def all_static_entities(self) -> typing.Iterable[Obstacle]:
        return (
            obstacle
            for level in self.all_levels
            for obstacle in level.all_static_entities
        )
    
    @property
    def all_dynamic_entities(self) -> typing.Iterable[DynamicObstacle]:
        return (
            d_obstacle
            for level in self.all_levels
            for d_obstacle in level.all_dynamic_entities
        )

    def get_level(self, floor_id: str) -> Level | None:
        return self.levels.get(floor_id, None)

    def as_world_description(self) -> WorldDescription | None:
        """Return a single-floor WorldDescription if this world has exactly one level."""
        if len(self.levels) != 1:
            return None
        return next(iter(self.levels.values()))

    def validate(self):
        elevator_floors: dict[str, str] = {}
        for floor_id, level in self.levels.items():
            for elevator in level.all_elevators:
                if elevator.name in elevator_floors:
                    raise RuntimeError(
                        f"elevator '{elevator.name}' appears in multiple floors: "
                        f"{elevator_floors[elevator.name]} and {floor_id}"
                    )
                elevator_floors[elevator.name] = floor_id

        for floor_id, level in self.levels.items():
            for level_elevator in level.levelElevators:
                if level_elevator.name not in elevator_floors:
                    raise RuntimeError(
                        f"level elevator '{level_elevator.name}' in floor '{floor_id}' "
                        f"has no matching elevator entity in levels"
                    )
                for destination_floor_id, destination_name in level_elevator.all_destinations:
                    if destination_floor_id not in self.levels:
                        raise RuntimeError(
                            f"destination floor '{destination_floor_id}' referenced by "
                            f"level elevator '{level_elevator.name}' does not exist"
                        )
                    if destination_name not in elevator_floors:
                        raise RuntimeError(
                            f"destination elevator '{destination_name}' referenced by "
                            f"level elevator '{level_elevator.name}' does not exist"
                        )
                    if elevator_floors[destination_name] != destination_floor_id:
                        raise RuntimeError(
                            f"destination mapping mismatch for '{destination_name}': "
                            f"declared floor '{destination_floor_id}', actual floor "
                            f"'{elevator_floors[destination_name]}'"
                        )

        for shaft in self.shafts.values():
            for floor_id, elevator_name in shaft.elevators.items():
                if floor_id not in self.levels:
                    raise RuntimeError(
                        f"shaft '{shaft.id}' references missing floor '{floor_id}'"
                    )
                if elevator_name not in elevator_floors:
                    raise RuntimeError(
                        f"shaft '{shaft.id}' references missing elevator '{elevator_name}'"
                    )
                if elevator_floors[elevator_name] != floor_id:
                    raise RuntimeError(
                        f"shaft '{shaft.id}' mapping mismatch: elevator '{elevator_name}' "
                        f"belongs to floor '{elevator_floors[elevator_name]}', not '{floor_id}'"
                    )

    @staticmethod
    def _parse_destinations(destination: str) -> list[str]:
        raw = str(destination or '')
        return [part.strip() for part in raw.split(',') if part.strip()]

    @classmethod
    def _all_destinations_for_elevator(cls, elevator: Elevator) -> typing.Iterable[str]:
        return (destination for destination in cls._parse_destinations(elevator.destination))

    @classmethod
    def from_list(cls, _worlds: typing.Iterable[WorldDescription]) -> 'MultiLevelWorld':
        worlds = list(_worlds)
        if not cls.unique_elevator_ids(worlds):
            raise RuntimeError(
                'from_list constructor of MultiLevelWorld expects elevator names to be unique '
                'across all provided WorldDescription instances'
            )

        levels: dict[str, Level] = {}
        for idx, world in enumerate(worlds):
            level = Level.from_world_description(world)
            level_elevators: list[ElevatorDescriptor] = []
            for elevator in world.all_elevators:
                level_elevator = ElevatorDescriptor.from_elevator(elevator)
                for destination in cls._all_destinations_for_elevator(elevator):
                    floor_id = cls._get_floor_id_for_elevator_in_worlds(destination, worlds)
                    if floor_id == '':
                        raise RuntimeError(
                            '_get_floor_id_for_elevator_in_worlds returned an empty string. '
                            'Check elevator destination mapping logic.'
                        )
                    level_elevator.add_destination(destination, floor_id)
                level_elevators.append(level_elevator)

            level.levelElevators = level_elevators
            levels[f'{idx}'] = level

        return cls(levels=levels)

    @classmethod
    def from_world_description(cls, world_description: WorldDescription) -> 'MultiLevelWorld':
        """Construct a MultiLevelWorld from a single-floor WorldDescription.

        The provided WorldDescription is treated as floor '0'.
        """
        return cls.from_list([world_description])

    @classmethod
    def from_yaml_files(cls, yaml_files: typing.Iterable[Path | str]) -> 'MultiLevelWorld':
        """Construct a MultiLevelWorld from a sequence of WorldDescription YAML files.
        WorldDescription files are treated as individual floors, in the order they are given.
        """
        worlds: list[WorldDescription] = []
        for yaml_file in yaml_files:
            with open(Path(yaml_file), encoding='utf-8') as f:
                data = yaml.safe_load(f)
                worlds.append(converter.structure(data, WorldDescription))

        return cls.from_list(worlds)

    @classmethod
    def unique_elevator_ids(cls, _worlds: typing.Iterable[WorldDescription]) -> bool:
        del cls
        seen = set()
        for world in _worlds:
            for elevator in world.all_elevators:
                if elevator.name in seen:
                    return False
                seen.add(elevator.name)
        return True

    @classmethod
    def _get_floor_id_for_elevator_in_worlds(
        cls,
        elevator_name: str,
        _worlds: typing.Iterable[WorldDescription],
    ) -> str:
        del cls
        for idx, world in enumerate(_worlds):
            if any(elevator.name == elevator_name for elevator in world.all_elevators):
                return f'{idx}'
        return ''

    def _get_floor_id_for_elevator_in_levels(self, elevator_name: str) -> str:
        for floor_id, level in self.levels.items():
            if any(elevator.name == elevator_name for elevator in level.all_elevators):
                return floor_id
        return ''

    # @classmethod
    # def all_elevators(cls, _worlds: typing.Iterable[WorldDescription]) -> typing.Iterable[Elevator]:
    #     del cls
    #     return (
    #         elevator
    #         for world in _worlds
    #         for zone in world.zones
    #         for elevator in zone.elevators
    #     )

    def map_floor_ids(self, ids_map: dict[str, str]):
        new_levels: dict[str, Level] = {}
        for floor_id, level in self.levels.items():
            level.map_floor_ids(ids_map=ids_map)

            if floor_id not in ids_map:
                raise RuntimeError(f'when remapping floor ids, could not find floor id {floor_id} in mapping')

            new_floor_id = ids_map[floor_id]
            if new_floor_id in new_levels:
                raise RuntimeError(f'duplicate remapped floor id {new_floor_id}; mapping must be one-to-one')
            new_levels[new_floor_id] = level
        self.levels = new_levels

        for shaft in self.shafts.values():
            remapped: dict[str, str] = {}
            for old_floor_id, elevator_name in shaft.elevators.items():
                if old_floor_id not in ids_map:
                    raise RuntimeError(
                        f'when remapping floor ids, could not find shaft floor id {old_floor_id} in mapping'
                    )
                new_floor_id = ids_map[old_floor_id]
                if new_floor_id in remapped:
                    raise RuntimeError(
                        f'duplicate remapped shaft floor id {new_floor_id}; mapping must be one-to-one'
                    )
                remapped[new_floor_id] = elevator_name
            shaft.elevators = remapped

    def rectify_ids(self):
        """rename floor ids so that they are numbered in the order that they appear
        """
        ids_map = {floor_id: f'{idx}' for idx, floor_id in enumerate(self.levels.keys())}
        self.map_floor_ids(ids_map=ids_map)

    def add_floor(self, new_floor: WorldDescription, floor_id: str):
        new_level = Level.from_world_description(new_floor)
        for elevator in new_level.all_elevators:
            level_elevator = ElevatorDescriptor.from_elevator(elevator)
            for destination in self._all_destinations_for_elevator(elevator):
                destination_floor_id = self._get_floor_id_for_elevator_in_levels(destination)
                if destination_floor_id == '':
                    raise RuntimeError(f'could not find destination elevator {destination} in existing levels')
                level_elevator.add_destination(destination, destination_floor_id)

            new_level.levelElevators.append(level_elevator)

        if floor_id in self.levels:
            raise RuntimeError('Tried to add a floor with an id that is already assigned to another floor')
        self.levels[str(floor_id)] = new_level

    def regular_floor_ids(self) -> bool:
        floor_count = len(self.levels)
        unseen_regular_floor_ids = set(map(lambda n: f'{n}', range(0, floor_count)))
        for floor_id in self.levels:
            unseen_regular_floor_ids.discard(floor_id)
        return len(unseen_regular_floor_ids) == 0

    def stack_floor(self, new_floor: WorldDescription):
        if self.regular_floor_ids():
            floor_count = len(self.levels)
            self.add_floor(new_floor, f'{floor_count}')
            return
        raise RuntimeError('stack_floor method expects floor ids to be 0, 1, ... , floor_count-1')

    def normalize_level_origins_in_place(self):
        """modify the coordinates so that the bottom-left corners of the bounding rectangles for levels are placed on origin (0,0)
        warning: Shaft positions need to be recomputed as this operation possibly applies different shift to different levels
        """
        for level in self.levels.values():
            x_min = min(corner.x for zone in level.zones for corner in zone.corners)
            y_min = min(corner.y for zone in level.zones for corner in zone.corners)
            dx, dy = -x_min, -y_min
            level.shift_all_positions(dx, dy)

    def normalize_level_origins(self) -> 'MultiLevelWorld':
        """return the copy of the world where the bottom-left corners of the bounding rectangles for levels are placed on origin (0,0)
        warning: Shaft positions need to be recomputed as this operation possibly applies different shift to different levels
        """

        out = deepcopy(self)
        out.normalize_level_origins_in_place()
        return out


    def floor_bbox(self) -> list[tuple[float, float]]:
        bboxes: list[tuple[float, float]] = []
        for level in self.levels.values():
            corners = [corner for zone in level.zones for corner in zone.corners]
            if not corners:
                bboxes.append((0.0, 0.0))
                continue

            x_min = min(corner.x for corner in corners)
            y_min = min(corner.y for corner in corners)
            x_max = max(corner.x for corner in corners)
            y_max = max(corner.y for corner in corners)
            bboxes.append((x_max - x_min, y_max - y_min))
        return bboxes

    def max_floor_bbox_dim(self) -> tuple[float, float]:
        bboxes = self.floor_bbox()
        if not bboxes:
            return (0.0, 0.0)
        return (
            max(width for width, _ in bboxes),
            max(height for _, height in bboxes),
        )

    def _render_whole_with_origins(
        self,
        resolution: float = 0.05,
        preferred_pixel_width: int = 500,
        margin_width_in_meter: float = 5,
        margin_height_in_meter: float = 5,
        *,
        default_asset_bbox: tuple[tuple[float, float], tuple[float, float]] | None = None,
        asset_color: str | None = None,
        asset_name_color: str | None = None,
    ) -> tuple[bytes, dict[str, tuple[float, float]]]:
        """Render all floors into a single PNG and return per-floor offsets.

        The returned offsets map each floor_id to the (x, y) shift applied
        when flattening into the shared map frame.
        """

        if not self.levels:
            raise RuntimeError('Cannot render an empty MultiLevelWorld')

        def _regularize_world_origin_then_apply_shift(world: WorldDescription, dx: float, dy: float) -> tuple[WorldDescription, tuple[float, float]]:
            shifted_world = deepcopy(world)

            corners = [corner for zone in shifted_world.zones for corner in zone.corners]
            if corners:
                x_min = min(corner.x for corner in corners)
                y_min = min(corner.y for corner in corners)
            else:
                x_min = 0.0
                y_min = 0.0

            offset_x = dx - x_min
            offset_y = dy - y_min

            shifted_world.shift_all_positions(offset_x, offset_y)

            return shifted_world, (offset_x, offset_y)

        max_bbox_width, max_bbox_height = self.max_floor_bbox_dim()

        # determine how many floors should be placed in one row
        max_pixel_width_per_floor = max((max_bbox_width + margin_width_in_meter) / resolution, 1)
        max_floor_counts_per_row = max(1, int(preferred_pixel_width // max_pixel_width_per_floor))

        floor_counts_per_row = 0
        row_count = 0
        flattened_world = WorldDescription()
        floor_origins: dict[str, tuple[float, float]] = {}
        for floor_id, floor in self.levels.items():
            shifted_floor, offset = _regularize_world_origin_then_apply_shift(
                floor,
                floor_counts_per_row * (max_bbox_width + margin_width_in_meter),
                -1 * row_count * (max_bbox_height + margin_height_in_meter)
            )

            flattened_world.zones.extend(shifted_floor.zones)
            floor_origins[floor_id] = offset

            floor_counts_per_row += 1
            if floor_counts_per_row >= max_floor_counts_per_row:
                row_count += 1
                floor_counts_per_row = 0

        png = flattened_world.render(
            resolution,
            default_asset_bbox=default_asset_bbox,
            asset_color=asset_color,
            asset_name_color=asset_name_color,
        )[0]
        return png, floor_origins

    def render_whole(
            self,
            resolution: float = 0.05,
            preferred_pixel_width: int = 500,
            margin_width_in_meter: float = 5,
            margin_height_in_meter: float = 5,
            *,
            default_asset_bbox: tuple[tuple[float, float], tuple[float, float]] | None = None,
            asset_color: str | None = None,
            asset_name_color: str | None = None,
    ) -> bytes:
        """Render all of the floors at once to a PNG image.

        In the rendered image, floor coordinates are shifted to lay out
        left-to-right, top-to-bottom.
        """
        png, _ = self._render_whole_with_origins(
            resolution=resolution,
            preferred_pixel_width=preferred_pixel_width,
            margin_width_in_meter=margin_width_in_meter,
            margin_height_in_meter=margin_height_in_meter,
            default_asset_bbox=default_asset_bbox,
            asset_color=asset_color,
            asset_name_color=asset_name_color,
        )
        return png

    def render_individually(
        self,
        resolution: float = 0.05,
        *,
        default_asset_bbox: tuple[tuple[float, float], tuple[float, float]] | None = None,
        asset_color: str | None = None,
        asset_name_color: str | None = None,
    ) -> typing.Iterable[typing.Tuple[str,typing.Tuple[bytes, tuple[float, float]]]]:

        return ((floor_id, floor.render(resolution, default_asset_bbox=default_asset_bbox, asset_color=asset_color, asset_name_color=asset_name_color)) for floor_id, floor in self.levels.items())

    def export(self, resolution: float = 0.05, extra_files: dict[str, bytes] | None = None, **kwargs: object) -> tarfile.TarFile:
        if extra_files is None:
            extra_files = {}
        files: dict[str, bytes] = {**extra_files}

        files['world.yaml'] = typing.cast(bytes, yaml.safe_dump(converter.unstructure(self), encoding='utf-8', sort_keys=False))

        render_args: dict[str, typing.Any] = {"resolution": resolution}
        if "default_asset_bbox" in kwargs:
            render_args["default_asset_bbox"] = kwargs["default_asset_bbox"]
        if "asset_color" in kwargs:
            render_args["asset_color"] = kwargs["asset_color"]
        if "asset_name_color" in kwargs:
            render_args["asset_name_color"] = kwargs["asset_name_color"]

        whole_png, floor_origins = self._render_whole_with_origins(**render_args)
        files['map/map.png'] = whole_png
        whole_origin = (0, 0)
        map_yaml = yaml.safe_load(Map.generate_map_yaml(
            resolution=resolution,
            filename='map.png',
            origin=whole_origin,
        ))
        map_yaml['origins'] = {floor_id: [x, y] for floor_id, (x, y) in floor_origins.items()}
        files['map/map.yaml'] = yaml.safe_dump(map_yaml, sort_keys=False).encode('utf-8')

        files['map/map.yaml'] = yaml.safe_dump(map_yaml).encode('utf-8')
        for floor_id, (png, origin) in self.render_individually(**render_args):
            files[f'map/floors/{floor_id}.png'] = png
            files[f'map/floors/{floor_id}.yaml'] = Map.generate_map_yaml(
                resolution=resolution,
                filename=f'{floor_id}.png',
                origin=origin,
            ).encode('utf-8')

        with io.BytesIO() as tar_stream:
            with tarfile.open(mode='w', fileobj=tar_stream) as tarball:
                for filename, content in files.items():
                    info = tarfile.TarInfo(name=os.path.normpath(filename))
                    info.size = len(content)
                    tarball.addfile(tarinfo=info, fileobj=io.BytesIO(content))
            tar_stream.seek(0)
            return tarfile.open(fileobj=io.BytesIO(tar_stream.getvalue()))
# -- Zone geometry helpers ---------------------------------------------------


def _door_polygon(start: Position, end: Position) -> list[Position]:
    dx = end.x - start.x
    dy = end.y - start.y
    length = math.sqrt(dx * dx + dy * dy)
    if length > 0:
        nx, ny = -dy / length, dx / length
    else:
        nx, ny = 0.0, 1.0
    t = 0.3  # half-thickness
    return [
        Position(start.x - nx * t, start.y - ny * t),
        Position(end.x - nx * t, end.y - ny * t),
        Position(end.x + nx * t, end.y + ny * t),
        Position(start.x + nx * t, start.y + ny * t),
    ]


_ELEVATOR_DOORWAY_DEPTH = 0.3


def _door_axis(door_side: str) -> tuple[tuple[float, float], tuple[float, float]]:
    return {
        '+x': ((1.0, 0.0), (0.0, 1.0)),
        '-x': ((-1.0, 0.0), (0.0, 1.0)),
        '+y': ((0.0, 1.0), (1.0, 0.0)),
        '-y': ((0.0, -1.0), (1.0, 0.0)),
    }[door_side]


def _elevator_doorway_corners(elevator: Elevator) -> list[Position]:
    outward, tangent = _door_axis(elevator.door_side)
    hx, hy = elevator.size[0] / 2.0, elevator.size[1] / 2.0
    out_extent = hx if outward[0] != 0 else hy
    tan_extent = hy if outward[0] != 0 else hx
    inner_cx = elevator.position.x + outward[0] * out_extent
    inner_cy = elevator.position.y + outward[1] * out_extent
    outer_cx = inner_cx + outward[0] * _ELEVATOR_DOORWAY_DEPTH
    outer_cy = inner_cy + outward[1] * _ELEVATOR_DOORWAY_DEPTH
    return [
        Position(inner_cx - tangent[0] * tan_extent, inner_cy - tangent[1] * tan_extent),
        Position(outer_cx - tangent[0] * tan_extent, outer_cy - tangent[1] * tan_extent),
        Position(outer_cx + tangent[0] * tan_extent, outer_cy + tangent[1] * tan_extent),
        Position(inner_cx + tangent[0] * tan_extent, inner_cy + tangent[1] * tan_extent),
    ]


def _render_door_polygons(door: Door) -> list:
    import shapely

    return [shapely.Polygon(door.corners)]


def _render_elevator_polygons(elevator: Elevator) -> list:
    import shapely

    return [shapely.Polygon(elevator.cabin_corners()), shapely.Polygon(_elevator_doorway_corners(elevator))]


class World(PathView):
    @property
    def scenario(self) -> type[Identifier[ScenarioView]]:
        class ScenarioIdentifier(Identifier[ScenarioView]):
            @classmethod
            def listall(cls, **kwargs: object) -> Iterator[Self]:
                scenarios_dir = self.path / 'scenarios'
                if not scenarios_dir.is_dir():
                    yield from ()
                    return
                yield from (cls(entry.name) for entry in os.scandir(scenarios_dir) if entry.is_dir())

            def load(self, path: Path, /, **kwargs: object) -> ScenarioView:
                del kwargs
                return ScenarioView(path)

        ScenarioIdentifier.use(FallbackResolver(ScenarioIdentifier, self.path / 'scenarios'))
        return ScenarioIdentifier

    @property
    def map(self) -> Map:
        return Map(self.path / 'map')

    @property
    def world_path(self) -> Path:
        return self.path / 'world.yaml'

    def load(self) -> WorldDescription:
        with open(self.world_path) as f:
            return converter.structure(yaml.safe_load(f), WorldDescription)

    def save(self, world: WorldDescription, map_only: bool = False, **kwargs: object) -> Path:
        os.makedirs(self.path, exist_ok=True)
        tarball = world.export(**kwargs)

        _filter: typing.Callable[[tarfile.TarInfo, str], tarfile.TarInfo | None] = tarfile.fully_trusted_filter
        if map_only:

            def map_only_filter(member: tarfile.TarInfo, destpath: str) -> tarfile.TarInfo | None:
                if not member.name.startswith('map/'):
                    return None
                return tarfile.fully_trusted_filter(member, destpath)

            _filter = map_only_filter

        tarball.extractall(self.path, filter=_filter)
        return self.path


class MultiLevelWorldView(PathView):

    @property
    def scenario(self) -> type[Identifier[ScenarioView]]:
        class ScenarioIdentifier(Identifier[ScenarioView]):
            @classmethod
            def listall(cls, **kwargs: object) -> Iterator[Self]:
                scenarios_dir = self.path / 'scenarios'
                if not scenarios_dir.is_dir():
                    yield from ()
                    return
                yield from (cls(entry.name) for entry in os.scandir(scenarios_dir) if entry.is_dir())

            def load(self, path: Path, /, **kwargs: object) -> ScenarioView:
                del kwargs
                return ScenarioView(path)

        ScenarioIdentifier.use(FallbackResolver(ScenarioIdentifier, self.path / 'scenarios'))
        return ScenarioIdentifier

    @property
    def map(self) -> Map:
        return Map(self.path / 'map')

    @property
    def world_path(self) -> Path:
        return self.path / 'world.yaml'

    def load(self, validate: bool = True) -> MultiLevelWorld:

        if self.world_path.exists():
            with open(self.world_path, encoding='utf-8') as f:
                data = yaml.safe_load(f)

            # Keep supporting the classic single-file format.
            if isinstance(data, dict) and 'zones' in data and 'levels' not in data:
                world_desc = converter.structure(data, WorldDescription)
                multi_level_world = MultiLevelWorld.from_list([world_desc])
            else:
                multi_level_world = converter.structure(data, MultiLevelWorld)
        
        else:
            yaml_files = sorted(
                path
                for path in self.path.iterdir()
                if path.is_file()
                and path.suffix in {'.yaml', '.yml'}
                and 'world' in path.name.lower()
            )
            if not yaml_files:
                raise FileNotFoundError(
                    f'could not find world.yaml or any world-related yaml files in {self.path}'
                )
            multi_level_world = MultiLevelWorld.from_yaml_files(yaml_files)

        if validate:
            multi_level_world.validate()
        return multi_level_world

    def save(self, multi_level_world: MultiLevelWorld, map_only: bool = False, validate: bool = True, **kwargs: object) -> Path:
        if validate:
            multi_level_world.validate()

        os.makedirs(self.path, exist_ok=True)
        tarball = multi_level_world.export(**kwargs)

        if not hasattr(tarfile, 'data_filter'):
            tarball.extractall(self.path)
            return self.path

        _filter = tarfile.data_filter
        if map_only:

            def map_only_filter(member: tarfile.TarInfo, destpath: str) -> tarfile.TarInfo | None:
                if not tarfile.data_filter(member, destpath):
                    return None
                if not member.name.startswith('map/'):
                    return None
                return member

            _filter = map_only_filter

        tarball.extractall(self.path, filter=_filter)
        return self.path


class WorldIdentifier(Identifier[World]):
    @classmethod
    def listall(cls, **kwargs: object) -> Iterator[Self]:
        yield from (WorldIdentifier(name) for name in os.listdir(ASS_DIR / 'worlds') if name.lower() != 'readme.md')

    def load(self, path: Path, /, **kwargs: object) -> World:
        del kwargs
        return World(path)


WorldIdentifier.use(FallbackResolver(WorldIdentifier, ASS_DIR / 'worlds'))


class MultiLevelWorldIdentifier(Identifier[MultiLevelWorldView]):
    @classmethod
    def listall(cls, **kwargs: object):
        del kwargs
        yield from (MultiLevelWorldIdentifier(name) for name in os.listdir(ASS_DIR / 'worlds'))

    def load(self, path: Path, /, **kwargs: object) -> MultiLevelWorldView:
        del kwargs
        return MultiLevelWorldView(path)


MultiLevelWorldIdentifier.use(FallbackResolver(MultiLevelWorldIdentifier, ASS_DIR / 'worlds'))
