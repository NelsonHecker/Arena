from __future__ import annotations

import copy
import itertools
import typing
from collections.abc import Sequence
from pathlib import Path

import attrs
import yaml
from arena_simulation_setup.tree import Identifier, ResolverBase

from arena_robots import ARENA_ROBOTS_DIR


@attrs.define()
class Config:
    """Configuration for setting up a robot instance."""

    robot: str  # name of robot
    name: str | None = None  # name or name prefix
    planner: str | None = None  # nav2 planner
    controller: str | None = None  # nav2 controller
    behavior: str | None = None  # nav2 behavior tree
    navigator: str | None = None  # navstack adapter kind (overrides model_params.navigator)

    extra: dict[str, typing.Any] = attrs.field(factory=dict)  # extra arbitrary data

    @classmethod
    def parse(cls, data: str | dict[str, typing.Any]) -> Sequence[Config]:
        """Parse a configuration from the given data."""
        if isinstance(data, str):
            return (cls(robot=data, name=data),)
        count = data.get('count', 1)
        fields = {k: v for k, v in data.items() if k != 'count'}
        return tuple(cls(**copy.deepcopy(fields)) for _ in range(count))


class RobotSetupResolver(ResolverBase):
    base_path = ARENA_ROBOTS_DIR / 'config' / 'setup'

    async def resolve(self, identifier: object) -> Path | None:
        target_path = self.base_path / f'{identifier.name}.yaml'
        if target_path.exists():
            return target_path
        return None


class RobotSetupIdentifier(Identifier[list[Config]]):
    def load(self, path: Path, /, **kwargs: object) -> list[Config]:
        del kwargs  # unused
        with open(path) as f:
            configuration = yaml.safe_load(f)

        if not isinstance(configuration, list):
            raise ValueError(f"{path}: robot_setup.yaml must be a list")

        return list(itertools.chain.from_iterable(map(Config.parse, configuration)))
