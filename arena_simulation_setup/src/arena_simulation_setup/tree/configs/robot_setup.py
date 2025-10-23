import typing
from collections.abc import Sequence

import yaml

from arena_simulation_setup import AB_DIR
from arena_simulation_setup.tree import StaticProvider


class RobotSetupConfig(dict[str, typing.Any]):
    ...
    # TODO


class RobotSetupProvider(StaticProvider):

    def load(self) -> Sequence[RobotSetupConfig]:
        with open(self.path, 'r') as f:
            configuration = yaml.safe_load(f)

        result: list[RobotSetupConfig] = []
        assert isinstance(configuration, list), "robot_setup.yaml must be a list"

        for entry_ in configuration:
            entry: dict = dict(entry_)
            amount = int(entry.pop('amount', 1))
            for _ in range(amount):
                result.append(RobotSetupConfig(entry))

        return result


RobotSetup = RobotSetupProvider.bind(AB_DIR / 'configs' / 'robot_setup')
