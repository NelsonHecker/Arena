from pathlib import Path
import yaml

from arena_simulation_setup import ASS_DIR
from arena_simulation_setup.tree import Identifier, ResolverBase


class EnvironmentDescription(dict):
    # TODO
    ...


class EnvironmentResolver(ResolverBase):
    base_path = ASS_DIR / 'configs' / 'environment'

    async def resolve(self, identifier):
        target_path = self.base_path / f'{identifier.name}.yaml'
        if target_path.exists():
            return target_path
        return None


class EnvironmentIdentifier(Identifier[EnvironmentDescription]):
    def load(self, path: Path, /, **kwargs) -> EnvironmentDescription:
        del kwargs
        with open(path, 'r') as f:
            value = yaml.safe_load(f)
        assert isinstance(value, dict)
        return EnvironmentDescription(value)


EnvironmentIdentifier.use(EnvironmentResolver(EnvironmentIdentifier))
