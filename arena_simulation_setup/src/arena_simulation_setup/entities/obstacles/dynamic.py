import os

from arena_simulation_setup import ProviderBase, ass_sources
from arena_simulation_setup.utils.models.model_loader import (
    ModelLoader,
    ModelProvider_SDF,
)


class DynamicObstacleModelProvider(ProviderBase):
    ...


dynamic_models_sources = ass_sources('entities', 'obstacles', 'dynamic')

DynamicObstacleModel = DynamicObstacleModelProvider.bind(dynamic_models_sources)

loader = ModelLoader(dynamic_models_sources, (ModelProvider_SDF,))
