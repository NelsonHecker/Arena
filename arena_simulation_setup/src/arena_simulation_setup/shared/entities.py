from __future__ import annotations

import re
import typing
import warnings

import attrs

from arena_simulation_setup.tree.assets.Pedestrian import (
    loader as PedestrianLoader,
)
from arena_simulation_setup.tree.assets.Object import loader as ObjectLoader
from arena_simulation_setup.utils.cattrs import (
    Parseable,
    converter,
)
from arena_simulation_setup.utils.models import ModelWrapper

from arena_simulation_setup.utils.geometry import Pose, Position

from .utils import model_parse

EntityT = typing.TypeVar("EntityT", bound="Entity")


@attrs.define
class Entity(Parseable):
    pose: Pose = attrs.field(converter=Pose.converter)
    name: str = attrs.field(converter=lambda s: Entity.sanitize_name(str(s)))
    model: ModelWrapper

    extra: dict = attrs.field(factory=dict, kw_only=True)
    path: str = attrs.field(repr=False, default='', kw_only=True)

    def asdict(self, expand_extra: bool = True) -> dict:
        if expand_extra:
            return {
                **attrs.asdict(self, filter=lambda a, v: a.name != 'extra'),
                **self.extra,
            }
        return attrs.asdict(self)

    @classmethod
    def sanitize_name(cls, name: str) -> str:
        return re.sub('[^A-Za-z0-9_]', '_', name)

    @classmethod
    def parse(cls: typing.Type[EntityT], value: dict) -> EntityT:
        if 'pos' in value:
            value['pose'] = value['pos']
            del value['pos']
        value['extra'] = {**value}
        return converter.structure_attrs_fromdict(value, cls)


converter.register_structure_hook(
    Entity, lambda data, _: Entity.parse(data)
)


@attrs.define
class Obstacle(Entity):
    model: ModelWrapper = attrs.field(converter=model_parse(ObjectLoader))
    # type_: str = attrs.field(converter=str)


@attrs.define
class DynamicObstacle(Obstacle):
    model: ModelWrapper = attrs.field(converter=model_parse(PedestrianLoader, overrides=(ObjectLoader,)))
    waypoints: list[Position]
    velocity: float = attrs.field(converter=float, default=1.0)  # m/s


@attrs.define
class CustomDynamicObstacle(DynamicObstacle):
    """
    DynamicObstacles but with properties can be define in runtime
    """

    def __getattr__(self, name):
        """
        Allow access to dynamic attributes "attr_name" via self.attr_name
        """
        if name in self.extra:
            return self.extra[name]
        raise AttributeError(f"{name} not found")

    @classmethod
    def parse(cls, value) -> CustomDynamicObstacle:
        known_fields = set(f.name for f in attrs.fields(cls))

        if 'pos' in value:
            value['pose'] = value['pos']
            del value['pos']

        known_values = {k: v for k, v in value.items() if k in known_fields}
        custom_fields = {k: v for k, v in value.items() if k not in known_fields}

        warnings.warn(
            "CustomDynamicObstacle.parse is deprecated and will be removed in a future release. "
            "Call the constructor directly, e.g., CustomDynamicObstacle(**value).",
            FutureWarning,
            stacklevel=2
        )

        obj = cls(**known_values)
        obj.extra.update(custom_fields)
        value = obj.asdict(True)

        return converter.structure(value, cls)
