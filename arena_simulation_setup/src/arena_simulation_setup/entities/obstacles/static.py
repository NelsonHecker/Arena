import os

from arena_simulation_setup import ProviderBase, ass_sources
from arena_simulation_setup.utils.models.model_loader import (
    ModelLoader,
    ModelProvider_SDF,
    ModelProvider_USD,
)


class ObstacleModelProvider(ProviderBase):
    ...


static_models_sources = ass_sources('entities', 'obstacles', 'static')

ObstacleModel = ObstacleModelProvider.bind(static_models_sources)

loader = ModelLoader(static_models_sources, (ModelProvider_SDF, ModelProvider_USD))
