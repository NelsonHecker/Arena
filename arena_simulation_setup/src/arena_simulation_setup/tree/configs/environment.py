import yaml

from arena_simulation_setup import ASS_DIR
from arena_simulation_setup.tree import StaticProvider

# TODO


class EnvironmentDescription(dict):
    ...


class EnvironmentProvider(StaticProvider):
    def load(self, *args, **kwargs) -> EnvironmentDescription:
        with open(self.path, 'r') as f:
            value = yaml.safe_load(f)
        assert isinstance(value, dict)
        return EnvironmentDescription(value)


Environment = EnvironmentProvider.bind(ASS_DIR / 'configs' / 'environment')
