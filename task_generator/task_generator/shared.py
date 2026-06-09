from __future__ import annotations

from typing import TYPE_CHECKING

import attrs
from arena_rclpy_mixins.shared import FrameNamespace
from arena_robots.Robot import RobotIdentifier
from arena_robots.SetupFile import Config as RobotSetupConfig
from arena_simulation_setup.shared import (  # noqa
    Ceiling,
    CustomDynamicObstacle,
    Door,
    DynamicObstacle,
    Elevator,
    Entity,
    Floor,
    Obstacle,
    Wall,
)
from arena_simulation_setup.shared.entities import Entity as _Entity  # noqa
from arena_simulation_setup.utils.geometry import (  # noqa
    Orientation,
    Pose,
    Position,
    PositionRadius,
)
from arena_simulation_setup.utils.models import Model, ModelType, ModelWrapper  # noqa

if TYPE_CHECKING:
    from . import TaskGenerator


@attrs.define
class Robot(Entity):
    model: RobotIdentifier  # type: ignore
    adapter_overrides: dict[str, str] = attrs.field(factory=dict)
    record_data_dir: str | None = None

    def compatible(self, value: Robot) -> bool:
        return self.model.name == value.model.name and self.adapter_overrides == value.adapter_overrides

    def __eq__(self, value: object) -> bool:
        if not isinstance(value, Robot):
            return False

        return self.compatible(value) and self.name == value.name and self.record_data_dir == value.record_data_dir

    @property
    def frame(self) -> FrameNamespace:
        if hasattr(self, 'sim_path'):
            return FrameNamespace(self.sim_path)
        if self.name:
            return FrameNamespace(self.name)
        return FrameNamespace('')

    @classmethod
    def from_setup(cls, setup: RobotSetupConfig, *, node: TaskGenerator) -> Robot:
        dict_value: dict = {'model': setup.robot}
        if setup.mobile is not None:
            dict_value['mobile'] = setup.mobile  # consumed by parse
        if setup.arm is not None:
            dict_value['arm'] = setup.arm  # consumed by parse
        dict_value.update(setup.extra)
        dict_value['name'] = setup.name or ''
        return cls.parse(dict_value, node=node)

    @classmethod
    def parse(cls, value: dict, *, node: TaskGenerator) -> Robot:
        name = str(value['name'])
        model = str(value['model'])
        pose = Pose.parse(value.get("pos", (0, 0, 0)))

        overrides: dict[str, str] = {}
        adapters_block = value.get("adapters")
        if isinstance(adapters_block, dict):
            overrides.update({str(k): str(v) for k, v in adapters_block.items()})
        # Flat per-cap sugar: top-level `mobile:` / `arm:` keys override the adapters block.
        for cap in ("mobile", "arm"):
            flat = value.get(cap)
            if isinstance(flat, str) and flat:
                overrides[cap] = flat

        record_data = value.get("record_data_dir", node.conf.Robot.RECORD_DATA_DIR.value)

        return cls(
            name=name,
            pose=pose,
            model=RobotIdentifier.parse(model),
            adapter_overrides=overrides,
            record_data_dir=record_data,
            extra=value,
        )
