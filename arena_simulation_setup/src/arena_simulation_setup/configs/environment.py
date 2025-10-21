import yaml

from arena_simulation_setup import ProviderBase, ass_sources


class EnvironmentProvider(ProviderBase):
    def load(self):
        with open(self.path, 'r') as f:
            return yaml.safe_load(f)


Environment = EnvironmentProvider.bind(ass_sources('configs', 'environment'))
