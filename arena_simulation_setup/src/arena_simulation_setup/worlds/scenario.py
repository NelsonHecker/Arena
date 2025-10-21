import functools
import itertools
import os
import typing
from collections.abc import Iterable

import attrs
import yaml

from arena_simulation_setup import ProviderBase
from arena_simulation_setup.shared import DynamicObstacle, Obstacle, Pose
from arena_simulation_setup.utils.cattrs import converter


@attrs.define
class RobotGoal:
    start: Pose = attrs.field(converter=Pose.converter)
    goal: Pose = attrs.field(converter=Pose.converter)

    @classmethod
    def parse(cls, obj: dict) -> "RobotGoal":
        return cls(
            start=Pose.parse(obj.get("start", [])),
            goal=Pose.parse(obj.get("goal", [])),
        )


@attrs.define
class Scenario:
    static: list[Obstacle]
    dynamic: list[DynamicObstacle]
    robots: list[RobotGoal]


class ScenarioProvider(ProviderBase):

    _names: typing.ClassVar[Iterable[str]] = [
        "scenario.yaml",
        "scenario.json",
    ]

    @functools.cached_property
    def scenario_path(self) -> str:
        """
        Get the path to the scenario file.
        """
        prefix = functools.partial(os.path.join, self.path)
        scenario = next(
            (
                p
                for p
                in map(
                    prefix,
                    self._names
                )
                if os.path.isfile(p)
            ),
            prefix(next(iter(self._names)))
        )
        return scenario

    def load(self) -> "Scenario":
        with open(self.scenario_path, 'r') as f:
            scenario = yaml.safe_load(f)

        return Scenario(
            static=[
                converter.structure({**obs, **dict(path=self.path)}, Obstacle)
                for obs
                in itertools.chain(
                    scenario.get("obstacles", {}).get("static", []),
                    scenario.get("obstacles", {}).get("interactive", [])
                )
            ],
            dynamic=[
                converter.structure({**obs, **dict(path=self.path)}, DynamicObstacle)
                for obs
                in scenario.get("obstacles", {}).get("dynamic", [])
            ],
            robots=[
                converter.structure({**robot}, RobotGoal)
                for robot
                in scenario.get("robots", [])
            ]
        )
