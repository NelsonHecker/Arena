from __future__ import annotations

import warnings
from pathlib import Path


import attrs
import cattrs
from typing import Union
from typing_extensions import Self

from arena_simulation_setup.tree.assets.Object import ObjectIdentifier
from arena_simulation_setup.tree.assets.Pedestrian import PedestrianIdentifier
from arena_simulation_setup.utils.cattrs import (
    Parseable,
    Serializable,
    converter,
)
from arena_simulation_setup.utils.geometry import Pose, Position, Scale


@attrs.define(auto_attribs=True, kw_only=True)
class Waypoint:
    position: Position
    floor_id: str | None = None

    @staticmethod
    def from_any(obj: Union[Position, dict, 'Waypoint']) -> 'Waypoint':
        if isinstance(obj, Waypoint):
            return obj
        if isinstance(obj, Position):
            return Waypoint(position=obj)
        if isinstance(obj, dict):
            # Accept {"position": ..., "floor_id": ...} or just a Position dict
            if 'position' in obj:
                pos = obj['position']
                if not isinstance(pos, Position):
                    pos = Position.converter(pos)
                return Waypoint(position=pos, floor_id=obj.get('floor_id'))
            else:
                # Assume it's a Position dict
                return Waypoint(position=Position.converter(obj))
        raise TypeError(f"Cannot convert {obj!r} to Waypoint")
    
    def __add__(self, other):
        if isinstance(other, Position):
            return Waypoint(position=self.position + other, floor_id=self.floor_id)
        raise NotImplemented


@attrs.define(kw_only=True)
class Named(Parseable, Serializable):
    name: str
    extra: dict = attrs.field(factory=dict)

    @property
    def sim_path(self) -> str:
        return self.extra.get('sim_path', self.name)

    @sim_path.setter
    def sim_path(self, value: str) -> None:
        self.extra['sim_path'] = str(value)

    @classmethod
    def parse(cls, value: dict) -> Self:
        if 'pos' in value:
            value['pose'] = value['pos']
            del value['pos']
        value['extra'] = {**value}
        return converter.structure_attrs_fromdict(value, cls)

    def serialize(self) -> dict:
        result = cattrs.gen.make_dict_unstructure_fn(type(self), converter, _cattrs_omit_if_default=True)(self)
        for k in attrs.fields(type(self)):
            result.get('extra', {}).pop(k.name, None)
        if not result.get('extra', {}):
            result.pop('extra', None)
        return result


@attrs.define(kw_only=True)
class Entity(Named, Parseable, Serializable):
    pose: Pose = attrs.field(converter=Pose.converter)
    model: ObjectIdentifier = attrs.field(converter=ObjectIdentifier.converter)

    included_from: Path | None = attrs.field(default=None, repr=False)

    def asdict(self, expand_extra: bool = True) -> dict:
        if expand_extra:
            return {
                **self.extra,
                **attrs.asdict(self, filter=lambda a, v: a.name != 'extra'),
            }
        return attrs.asdict(self)


@attrs.define
class Obstacle(Entity):
    scale: Scale | None = None
    floor_id: str | None = None


def _waypoints_validator(instance, attribute, value):
    if not isinstance(value, list):
        raise TypeError("waypoints must be a list")
    for i, wp in enumerate(value):
        try:
            Waypoint.from_any(wp)
        except Exception as e:
            raise TypeError(f"Invalid waypoint at index {i}: {e}")

def _waypoints_converter(value):
    if not isinstance(value, list):
        raise TypeError("waypoints must be a list")
    return [Waypoint.from_any(wp) for wp in value]


@attrs.define
class DynamicObstacle(Entity):
    model: PedestrianIdentifier = attrs.field(converter=PedestrianIdentifier.converter)
    waypoints: list[Waypoint] = attrs.field(factory=list, validator=_waypoints_validator, converter=_waypoints_converter)
    velocity: float = attrs.field(converter=float, default=1.0)  # m/s


@attrs.define
class CustomDynamicObstacle(DynamicObstacle):
    """
    DynamicObstacles but with properties can be define in runtime
    """

    def __getattr__(self, name: str) -> object:
        """
        Allow access to dynamic attributes "attr_name" via self.attr_name
        """
        if name in self.extra:
            return self.extra[name]
        raise AttributeError(f"{name} not found")

    @classmethod
    def parse(cls, value: object) -> Self:
        known_fields = set(f.name for f in attrs.fields(cls))

        if 'pos' in value:
            value['pose'] = value['pos']
            del value['pos']

        known_values = {k: v for k, v in value.items() if k in known_fields}
        custom_fields = {k: v for k, v in value.items() if k not in known_fields}

        warnings.warn("CustomDynamicObstacle.parse is deprecated and will be removed in a future release. Call the constructor directly, e.g., CustomDynamicObstacle(**value).", FutureWarning, stacklevel=2)

        obj = cls(**known_values)
        obj.extra.update(custom_fields)
        value = obj.asdict(True)

        return converter.structure(value, cls)
