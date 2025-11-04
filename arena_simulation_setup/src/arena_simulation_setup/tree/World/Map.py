import io
import os
import typing
from pathlib import Path

import PIL.Image
import PIL.ImageDraw
import shapely
import shapely.affinity
import yaml


class Map:
    def __init__(self, path: Path):
        self._path = path

    @property
    def path(self) -> Path:
        return self._path

    @property
    def map_yaml(self) -> Path:
        return self.path / 'map.yaml'

    @property
    def map_png(self) -> Path:
        return self.path / 'map.png'

    @classmethod
    def generate_png(
        cls,
        rooms: shapely.MultiPolygon,
        walls: shapely.MultiLineString,
        resolution: float = 0.01,
        padding: int = 5,
    ) -> tuple[bytes, tuple[float, float]]:
        """
        Generate a PNG image of the map with the given elements.
        """
        min_x, min_y, max_x, max_y = map(lambda x: x + padding * resolution, rooms.bounds)

        width = max_x - min_x
        height = max_y - min_y

        img = PIL.Image.new(
            'RGB',
            (
                int(width / resolution) + 2 * padding,
                int(height / resolution) + 2 * padding,
            ),
            color='black'
        )

        scaling_factor = 1 / resolution

        def tf(shape):
            shape = shapely.affinity.translate(shape, -min_x, -min_y)
            shape = shapely.affinity.scale(shape, scaling_factor, -scaling_factor, origin=(0, 0))  # type: ignore
            shape = shapely.affinity.translate(shape, 0, height * scaling_factor)
            shape = shapely.set_precision(shape, 0.01)
            shape = shapely.make_valid(shape)
            shape = shapely.remove_repeated_points(shape)
            return shape

        def as_int(coords):
            return [(int(x), int(y)) for (x, y, *_) in coords]

        draw = PIL.ImageDraw.Draw(img)
        for room in rooms.geoms:
            poly = tf(shapely.Polygon(room))
            draw.polygon(as_int(poly.exterior.coords), fill='white')

        for wall in walls.geoms:
            line = tf(shapely.LineString(wall))
            draw.line(as_int(line.coords), fill='black', width=1)

        img_bytes = io.BytesIO()
        img.save(img_bytes, format='PNG')
        img_bytes.seek(0)
        return img_bytes.getvalue(), (min_x * resolution, min_y * resolution)

    @classmethod
    def generate_map_yaml(cls, resolution: float, filename: str, origin: tuple[float, float]) -> str:
        return typing.cast(
            str,
            yaml.safe_dump({
                'free_thresh': 0.1,
                'image': filename,
                'negate': 0,
                'occupied_thresh': 0.9,
                'origin': [*origin, 0],
                'resolution': resolution,
            })
        )
