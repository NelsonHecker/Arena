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
    ModelProvider_USD,
)


@attrs.define(eq=False, hash=False)
class ObjectIdentifier(DomainAssetIdentifier[ModelWrapper]):
    """Represents an identifier referencing a 3D model asset.
    """
    _asset_type = 'Object'

    def load(self, path: Path, /, **kwargs) -> ModelWrapper:
        del kwargs  # unused
        return ModelWrapper(
            self.name,
            {
                **ModelProvider_USD.asdict(path, path.name),
                **ModelProvider_SDF.asdict(path, path.name),
            }
        )


ObjectIdentifier.use(*DynamicPaths.as_resolvers(ObjectIdentifier))
ObjectIdentifier.use(*NetResolver.all(ObjectIdentifier))
