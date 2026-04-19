from pathlib import Path

import attrs

from arena_simulation_setup.tree import (
    DomainAssetIdentifier,
    DynamicPaths,
    NetResolver,
)
from arena_simulation_setup.utils.models import ModelWrapper
from arena_simulation_setup.utils.models.model_loader import (
    ModelProvider_SDF,
)


@attrs.define(eq=False, hash=False)
class PedestrianIdentifier(DomainAssetIdentifier[ModelWrapper]):
    """Represents an identifier referencing a 3D model asset."""

    _asset_type = 'Pedestrian'

    def load(self, path: Path, /, **kwargs: object) -> ModelWrapper:
        del kwargs  # unused
        return ModelWrapper(
            self.name,
            {
                **ModelProvider_SDF.asdict(path, path.name),
            },
        )


PedestrianIdentifier.use(*DynamicPaths.as_resolvers(PedestrianIdentifier))
PedestrianIdentifier.use(*NetResolver.all(PedestrianIdentifier))
