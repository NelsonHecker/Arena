import functools
import itertools
import os
import traceback
import typing
from collections.abc import Iterable

import attrs
import yaml

from arena_simulation_setup.shared import DynamicObstacle, Obstacle, Pose
from arena_simulation_setup.tree import PathView
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
    static: list[Obstacle] = attrs.field(factory=list)
    dynamic: list[DynamicObstacle] = attrs.field(factory=list)
    robots: list[RobotGoal] = attrs.field(factory=list)


class ScenarioView(PathView):
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
        scenario = next((p for p in map(prefix, self._names) if os.path.isfile(p)), prefix(next(iter(self._names))))
        return scenario

    def load_legacy(self) -> Scenario:
        with open(self.scenario_path) as f:
            scenario = yaml.safe_load(f)

        if not isinstance(scenario, dict):
            raise ValueError(f"Scenario file {self.scenario_path} must contain a dictionary at the top level.")

        return Scenario(
            static=[converter.structure({**obs, **dict(included_from=self.path)}, Obstacle) for obs in itertools.chain(scenario.get("obstacles", {}).get("static", []), scenario.get("obstacles", {}).get("interactive", []))],
            dynamic=[converter.structure({**obs, **dict(included_from=self.path)}, DynamicObstacle) for obs in scenario.get("obstacles", {}).get("dynamic", [])],
            robots=[converter.structure({**robot}, RobotGoal) for robot in scenario.get("robots", [])],
        )

    def load(self) -> Scenario:
        load_exc: Exception
        try:
            with open(self.scenario_path) as f:
                scenario = converter.structure(yaml.safe_load(f), Scenario)
                for obj in itertools.chain(scenario.static, scenario.dynamic):
                    obj.included_from = self.path
            return scenario
        except Exception as e:
            load_exc = e

        legacy_exc: Exception
        try:
            scenario = self.load_legacy()
            import warnings

            warnings.warn("Loading Scenario in legacy format.", DeprecationWarning, stacklevel=2)
            return scenario
        except Exception as e:
            legacy_exc = e

        raise RuntimeError(
            f"Failed to load scenario from {self.scenario_path}:\n - New format error: {load_exc}\n{''.join(traceback.format_exception(type(load_exc), load_exc, load_exc.__traceback__))}\n - Legacy format error: {legacy_exc}\n{''.join(traceback.format_exception(type(legacy_exc), legacy_exc, legacy_exc.__traceback__))}"
        )
