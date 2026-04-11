from __future__ import annotations

from typing import TYPE_CHECKING, Optional

import attrs
from arena_rclpy_mixins.shared import FrameNamespace, Namespace
from arena_robots.Robot import RobotIdentifier
from arena_robots.SetupFile import Config as RobotSetupConfig
from arena_simulation_setup.shared import (  # noqa
    CustomDynamicObstacle,
    Door,
    DynamicObstacle,
    Entity,
    Floor,
    Obstacle,
    Wall,
    Elevator,
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
    inter_planner: str
    local_planner: str
    global_planner: str
    agent: str
    record_data_dir: Optional[str] = None

    def compatible(self, value: Robot) -> bool:
        return self.model.name == value.model.name and self.local_planner == value.local_planner and self.global_planner == value.global_planner and self.agent == value.agent

    def __eq__(self, value: object) -> bool:
        if not isinstance(value, Robot):
            return False

        return self.compatible(value) and self.name == value.name and self.record_data_dir == value.record_data_dir

    @property
    def frame(self) -> FrameNamespace:
        if hasattr(self, 'sim_path'):
            return FrameNamespace(getattr(self, 'sim_path'))
        if self.name:
            return FrameNamespace(self.name)
        return FrameNamespace('')

    @classmethod
    def from_setup(cls, setup: RobotSetupConfig, *, node: "TaskGenerator") -> Robot:
        dict_value = {}
        dict_value['model'] = setup.robot
        if setup.behavior is not None:
            dict_value['inter_planner'] = setup.behavior
        if setup.controller is not None:
            dict_value['local_planner'] = setup.controller
        if setup.planner is not None:
            dict_value['global_planner'] = setup.planner
        dict_value.update(setup.extra)
        dict_value['name'] = setup.name or ''
        return cls.parse(dict_value, node=node)

    @classmethod
    def parse(cls, value: dict, *, node: "TaskGenerator") -> "Robot":
        name = str(value['name'])
        model = str(value['model'])
        pose = Pose(value.get("pos", (0, 0, 0)))
        inter_planner = str(value.get("inter_planner", node.conf.Robot.BEHAVIOR.value))
        local_planner = str(value.get("local_planner", node.conf.Robot.CONTROLLER.value))
        global_planner = str(value.get("global_planner", node.conf.Robot.PLANNER.value))
        agent = str(value.get("agent", node.conf.Robot.AGENT.value))
        record_data = value.get("record_data_dir", node.conf.Robot.RECORD_DATA_DIR.value)

        return cls(
            name=name,
            pose=pose,
            inter_planner=inter_planner,
            local_planner=local_planner,
            global_planner=global_planner,
            model=RobotIdentifier.parse(model),
            agent=agent,
            record_data_dir=record_data,
            extra=value,
        )
