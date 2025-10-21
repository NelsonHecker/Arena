import os
import typing

import yaml

from arena_simulation_setup import ProviderBase, ass_sources
from arena_simulation_setup.utils.models.model_loader import (
    ModelLoader,
    ModelProvider_URDF,
)


class ModelParams(dict[str, typing.Any]):
    @classmethod
    def from_yaml(cls, path: str) -> 'ModelParams':
        with open(path) as f:
            return cls(yaml.safe_load(f))

    @property
    def base_frame(self) -> str:
        return self.get('robot_base_frame', 'base_link')

    @property
    def odom_frame(self) -> str:
        return self.get('robot_odom_frame', 'odom')

    @property
    def z_offset(self) -> float:
        return self.get('z_offset', 0.0)


class RobotProvider(ProviderBase):

    def __init__(self, name: str) -> None:
        super().__init__(name)
        self._cached_params = None

    @property
    def model_params(self) -> ModelParams:
        if self._cached_params is None:
            self._cached_params = ModelParams.from_yaml(os.path.join(self.path, 'model_params.yaml'))
        return self._cached_params

    @property
    def mappings(self) -> str:
        return os.path.join(
            self.path,
            'mappings.yaml'
        )

    @property
    def control(self) -> dict:
        with open(os.path.join(self.path, 'control.yaml')) as f:
            return yaml.safe_load(f)


robots_sources = ass_sources('entities', 'robots')

Robot = RobotProvider.bind(robots_sources)

loader = ModelLoader(robots_sources, (ModelProvider_URDF,))
