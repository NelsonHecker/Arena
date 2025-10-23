import yaml

from arena_simulation_setup import ASS_DIR
from arena_simulation_setup.tree import StaticProvider


class EnvironmentProvider(StaticProvider):
    def load(self):
        with open(self.path, 'r') as f:
            return yaml.safe_load(f)


Environment = EnvironmentProvider.bind(ASS_DIR / 'configs' / 'environment')
