import io
import itertools
import os

import attrs
import PIL.Image
import PIL.ImageDraw
import shapely
import shapely.affinity
import yaml

import arena_simulation_setup.worlds.world
from arena_simulation_setup.shared import Position, Wall
from arena_simulation_setup.utils.cattrs import converter

Point = tuple[float, float]
Line = tuple[Point, Point]
Polygon = list[Point]


@attrs.define
class GeneratedWorld:
    rooms: list[Polygon]  # m
    doors: list[Polygon]  # m
    width: float  # m
    height: float  # m
    resolution: float  # m/px

    padding: int = 50  # px

    _world_description: arena_simulation_setup.worlds.world.WorldDescription | None = attrs.field(
        default=None, init=False
    )

    @property
    def world_padding(self) -> float:
        return self.padding * self.resolution

    def global_tf(self, geom):
        padding_world = self.world_padding
        geom = shapely.affinity.translate(geom, padding_world, padding_world)
        geom = shapely.set_precision(geom, 0.01)
        geom = shapely.make_valid(geom)
        geom = shapely.remove_repeated_points(geom)
        return geom

    def to_world(self) -> arena_simulation_setup.worlds.world.WorldDescription:

        all_walls: list[shapely.LineString] = []
        doors = shapely.MultiPolygon([shapely.Polygon(door) for door in self.doors])

        def poly_to_walls(poly: shapely.Polygon) -> list[Wall]:
            nonlocal all_walls
            reduced_walls = self.global_tf(self.remove_doors(poly.exterior, doors))
            all_walls += reduced_walls.geoms
            return [
                Wall(
                    start=Position(x=wall.coords[0][0], y=wall.coords[0][1]),
                    end=Position(x=wall.coords[-1][0], y=wall.coords[-1][1])
                )
                for wall in reduced_walls.geoms
                # if shapely.Point(wall.coords[0]).distance(shapely.Point(wall.coords[-1])) > 0.01  # safeguard against zero-length walls
            ]

        def create_zone(room: shapely.Polygon, i: int) -> arena_simulation_setup.worlds.world.WorldDescription.Zone:
            return arena_simulation_setup.worlds.world.WorldDescription.Zone(
                name=f'zone_{i}',
                corners=[Position(x=pt[0], y=pt[1]) for pt in self.global_tf(room).exterior.coords[:-1]],
                walls=poly_to_walls(room),
                entities=arena_simulation_setup.worlds.world.WorldDescription.Zone.WorldEntities(),
            )
        zones = [
            create_zone(shapely.Polygon(room), i)
            for i, room in enumerate(self.rooms)
        ]

        inner_width = self.width + 2 * self.world_padding
        inner_height = self.height + 2 * self.world_padding

        world_corners = [
            (-self.world_padding, -self.world_padding),
            (inner_width + self.world_padding, -self.world_padding),
            (inner_width + self.world_padding, inner_height + self.world_padding),
            (-self.world_padding, inner_height + self.world_padding),
        ]

        extra_walls = self.connective_walls(
            shapely.MultiLineString(all_walls),
        )

        zones.append(
            arena_simulation_setup.worlds.world.WorldDescription.Zone(
                name='extra_walls',
                corners=[
                    Position(x=pt[0], y=pt[1]) for pt in world_corners
                ],
                walls=poly_to_walls(shapely.Polygon(world_corners)) + [
                    Wall(start=Position(x=start[0], y=start[1]), end=Position(x=end[0], y=end[1]))
                    for start, end in extra_walls.geoms
                ],
                entities=arena_simulation_setup.worlds.world.WorldDescription.Zone.WorldEntities(),
            )
        )

        return arena_simulation_setup.worlds.world.WorldDescription(zones=zones)

    def remove_doors(self, walls: shapely.MultiLineString, doors: shapely.MultiPolygon) -> shapely.MultiLineString:
        """
        Removes doors from the walls.
        """
        doors = shapely.make_valid(shapely.MultiPolygon([shapely.Polygon(door) for door in self.doors]), method='structure')

        result_walls: list[shapely.LineString] = []

        reduced = shapely.make_valid(walls.difference(doors), method='structure')

        if not reduced.is_empty and isinstance(reduced, shapely.LineString):
            reduced = shapely.MultiLineString([reduced])

        if isinstance(reduced, shapely.MultiLineString):
            for geom in reduced.geoms:
                pts = list(geom.coords)
                for i in range(1, len(pts)):
                    start = pts[i - 1]
                    end = pts[i]
                    result_walls.append(
                        shapely.LineString(
                            (
                                (start[0], start[1]),
                                (end[0], end[1])
                            )
                        )
                    )

        return shapely.MultiLineString(result_walls)

    def connective_walls(self, walls: shapely.MultiLineString, connect: tuple[float, float] | None = None) -> shapely.MultiLineString:
        result_walls: list[shapely.LineString] = []

        if connect is not None:
            all_pts = [pt for wall in walls for pt in wall]
            for pt_a, pt_b in itertools.combinations(all_pts, 2):
                dist = pt_a.distance(pt_b)
                if dist > connect[0] and dist < connect[1]:
                    start = pt_a.coords[0]
                    end = pt_b.coords[0]
                    result_walls.append(
                        shapely.LineString(
                            (
                                (start[0], start[1]),
                                (end[0], end[1])
                            )
                        )
                    )

        return shapely.MultiLineString(result_walls)

    def to_map_yaml(self) -> str:
        res = yaml.safe_dump({
            'free_thresh': 0.196,
            'image': 'map.png',
            'negate': 0,
            'occupied_thresh': 0.65,
            'origin': [0, 0, 0],
            'resolution': self.resolution,
        })
        assert isinstance(res, str), "YAML dump should return a string"
        return res

    def to_map_png(self) -> bytes:
        img = PIL.Image.new(
            'RGB',
            (
                int(self.width / self.resolution) + 2 * self.padding,
                int(self.height / self.resolution) + 2 * self.padding),
            color='black'
        )

        scaling_factor = 1 / self.resolution

        def tf(shape):
            shape = shapely.affinity.scale(shape, scaling_factor, -scaling_factor, origin=(0, 0))
            shape = shapely.affinity.translate(shape, 0, self.height * scaling_factor)
            shape = shapely.affinity.translate(shape, self.padding, self.padding)
            return shape

        draw = PIL.ImageDraw.Draw(img)
        for room in self.rooms:
            poly = tf(shapely.Polygon(room))
            draw.polygon(list(poly.exterior.coords), fill='white', outline='black')
        for door in self.doors:
            poly = tf(shapely.Polygon(door))
            draw.polygon(list(poly.exterior.coords), fill='white')

        img_bytes = io.BytesIO()
        img.save(img_bytes, format='PNG')
        img_bytes.seek(0)
        return img_bytes.getvalue()

    @property
    def world_description(self) -> arena_simulation_setup.worlds.world.WorldDescription:
        if self._world_description is None:
            self._world_description = self.to_world()
        return self._world_description

    @world_description.setter
    def world_description(self, value: arena_simulation_setup.worlds.world.WorldDescription):
        self._world_description = value

    def save_to(self, world_name: str):
        world = arena_simulation_setup.worlds.world.World(world_name)

        os.makedirs(world.path, exist_ok=True)
        with open(world.world_path, 'w') as f:
            world_description = self.world_description
            yaml.safe_dump(converter.unstructure(world_description), f, sort_keys=False)

        os.makedirs(world.map.path, exist_ok=True)
        with open(world.map.map_yaml, 'w') as f:
            f.write(self.to_map_yaml())
        with open(world.map.map_png, 'wb') as f:
            f.write(self.to_map_png())

        scenario = world.scenario('default')
        os.makedirs(scenario.path, exist_ok=True)
        with open(scenario.scenario_path, 'w') as f:
            f.write('{}')
