from __future__ import annotations

from pathlib import Path
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
    adapters: dict[str, str] = attrs.field(factory=dict)
    parts: dict[str, list] = attrs.field(factory=dict)
    record_data_dir: str | None = None
    # resolved morphology (assembler output), None for robots without an assembly.
    # Excluded from compatible()/__eq__: it is derived from parts+model, not identity.
    resolved_assembly: object | None = attrs.field(default=None, eq=False)

    def compatible(self, value: Robot) -> bool:
        return (
            self.model.name == value.model.name
            and self.adapters == value.adapters
            and self.parts == value.parts
        )

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
        return FrameNamespace("")

    @classmethod
    def from_setup(cls, setup: RobotSetupConfig, *, node: TaskGenerator) -> Robot:
        dict_value: dict = {
            'model': setup.robot,
            'adapters': setup.adapters,
            'parts': setup.parts,
        }
        dict_value.update(setup.extra)
        dict_value["name"] = setup.name or ""
        return cls.parse(dict_value, node=node)

    @classmethod
    def parse(cls, value: dict, *, node: TaskGenerator) -> Robot:
        name = str(value['name'])
        model = str(value['model'])
        pose = Pose.parse(value.get("pos", (0, 0, 0)))

        adapters: dict[str, str] = {}
        adapters_block = value.get("adapters")
        if isinstance(adapters_block, dict):
            adapters.update({str(k): str(v) for k, v in adapters_block.items()})

        from task_generator.tasks.robots.adapters import ADAPTERS  # noqa: PLC0415

        for cap, kind in adapters.items():
            if cap not in ADAPTERS:
                raise RuntimeError(f"robot {name!r}: no adapter registry for cap {cap!r} (registered caps: {sorted(ADAPTERS)})")
            if kind not in ADAPTERS[cap]:
                raise RuntimeError(f"robot {name!r}: unknown adapter {kind!r} for cap {cap!r} (registered: {sorted(ADAPTERS[cap].keys())})")

        parts_block = value.get("parts")
        parts: dict[str, list] = dict(parts_block) if isinstance(parts_block, dict) else {}

        resolved_assembly = None
        if parts:
            from arena_runtime.constants import SimSimulator  # noqa: PLC0415

            if node.conf.Arena.SIM.value is SimSimulator.ISAAC:
                raise RuntimeError(f"robot {name!r}: morphology parametrization not available on isaac")

            from arena_robots import assembly as arena_assembly  # noqa: PLC0415

            view = RobotIdentifier.parse(model).resolve_sync()
            if view.assembly is None:
                raise RuntimeError(f"robot {name!r}: morphology parametrization requires an assembly.yaml, and {model!r} has none")

            request = {
                typ: [arena_assembly.RequestPart(variant=p.variant, mount=p.mount) for p in instances]
                for typ, instances in parts.items()
            }
            try:
                resolved_assembly = arena_assembly.resolve(view.assembly, request)
            except arena_assembly.AssemblyError as e:
                raise RuntimeError(f"robot {name!r}: {e}") from e

            for w in arena_assembly.warn_if_blind(resolved_assembly, {'lidar'}):
                node.get_logger().warn(f"robot {name!r}: {w}")

        record_data = value.get("record_data_dir", node.conf.Robot.RECORD_DATA_DIR.value)

        return cls(
            name=name,
            pose=pose,
            model=RobotIdentifier.parse(model),
            adapters=adapters,
            parts=parts,
            record_data_dir=record_data,
            resolved_assembly=resolved_assembly,
            extra=value,
        )


@attrs.define
class Region:
    name: str
    type: str  # "source" | "sink"
    polygon: list[Position] = attrs.field(factory=list)  # CCW vertices, 2D
    config: dict = attrs.Factory(dict)  # type-specific passthrough
    included_from: Path | None = None
