import io
import os
import tarfile
import typing

import attrs
import yaml

from arena_simulation_setup import ProviderBase, SourcesContainer, ass_sources
from arena_simulation_setup.entities.materials import (
    MaterialLoader,
    MaterialProvider,
)
from arena_simulation_setup.shared import (
    Door,
    DynamicObstacle,
    Elevator,
    Floor,
    Obstacle,
    Wall,
)
from arena_simulation_setup.utils.cattrs import converter
from arena_simulation_setup.utils.geometry import Position

from .map import Map
from .scenario import ScenarioProvider


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
        corners: list[Position] = attrs.field(factory=list)
        walls: list[Wall] = attrs.field(factory=list)
        doors: list[Door] = attrs.field(factory=list)
        elevators: list[Elevator] = attrs.field(factory=list)
        material: MaterialProvider = attrs.field(converter=MaterialLoader.converter, factory=MaterialLoader.DEFAULT)
        entities: WorldEntities = attrs.field(factory=WorldEntities)
        description: str = ''

        @property
        def floor(self) -> Floor:
            x_min = min(corner.x for corner in self.corners)
            y_min = min(corner.y for corner in self.corners)
            x_max = max(corner.x for corner in self.corners)
            y_max = max(corner.y for corner in self.corners)
            pos = Position(x=(x_min + x_max) / 2, y=(y_min + y_max) / 2)
            x_length = x_max - x_min
            y_length = y_max - y_min
            return Floor(pos=pos, x_length=x_length, y_length=y_length, material=self.material)

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
    def all_floors(self) -> typing.Iterable[Floor]:
        return (zone.floor for zone in self.zones)

    @property
    def all_static_entities(self) -> typing.Iterable[Obstacle]:
        return (entity for zone in self.zones for entity in zone.entities.static)

    @property
    def all_dynamic_entities(self) -> typing.Iterable[Obstacle]:
        return (entity for zone in self.zones for entity in zone.entities.dynamic)

    def export(
        self,
        resolution: float = 0.05,
        extra_files: dict[str, bytes] | None = None,
    ) -> tarfile.TarFile:
        """
        Export the world description to world.yaml, map.png, map.yaml
        """
        import shapely

        if extra_files is None:
            extra_files = {}
        files: dict[str, bytes] = {**extra_files}

        files['world.yaml'] = typing.cast(bytes, yaml.safe_dump(converter.unstructure(self), encoding='utf-8'))

        files['map/map.png'], origin = Map.generate_png(
            rooms=shapely.MultiPolygon([shapely.Polygon(zone.corners) for zone in self.zones]),
            walls=shapely.MultiLineString(list(self.all_walls)),
            resolution=resolution,
            padding=5,
        )

        files['map/map.yaml'] = Map.generate_map_yaml(resolution=resolution, filename='map.png', origin=origin).encode('utf-8')

        with io.BytesIO() as tar_stream:
            with tarfile.open(mode='w', fileobj=tar_stream) as tarball:
                for filename, content in files.items():
                    info = tarfile.TarInfo(name=os.path.normpath(filename))
                    info.size = len(content)
                    tarball.addfile(tarinfo=info, fileobj=io.BytesIO(content))
            tar_stream.seek(0)
            return tarfile.open(fileobj=io.BytesIO(tar_stream.getvalue()))

        return tarball


class WorldProvider(ProviderBase):

    @classmethod
    def list(cls):
        return ('.generated', *super().list())

    @classmethod
    def resolve(cls, path: str) -> str:
        return os.path.join(cls._sources.global_dir, path)

    @property
    def scenario(self):
        return ScenarioProvider.bind(ass_sources.override(**{SourcesContainer.Keys.WORLD.value: self.path})('scenarios'))

    @property
    def map(self):
        return Map(os.path.join(self.path, 'map'))

    @property
    def world_path(self) -> str:
        return os.path.join(self.path, 'world.yaml')

    def load(self) -> WorldDescription:
        with open(self.world_path) as f:
            return converter.structure(
                yaml.safe_load(f),
                WorldDescription
            )

    def save(self, world: WorldDescription, **kwargs) -> str:
        os.makedirs(self.path, exist_ok=True)
        tarball = world.export(**kwargs)
        tarball.extractall(self.path, filter='data')
        return self.path


World = WorldProvider.bind(ass_sources('worlds'))
