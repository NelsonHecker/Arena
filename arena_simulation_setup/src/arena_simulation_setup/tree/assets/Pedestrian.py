from functools import cached_property
from pathlib import Path

import attrs

from arena_simulation_setup.tree import (
    DomainAssetIdentifier,
    DynamicPaths,
    NetResolver,
    PathView,
)
from arena_simulation_setup.utils.models import ModelWrapper
from arena_simulation_setup.utils.models.model_loader import (
    ModelProvider_SDF,
)


class PedestrianView(PathView):
    """View around a resolved Pedestrian asset directory.

    Mirrors `ObjectView` so the resolved-asset accessor is uniform across
    asset kinds, callers can always do `(await ident.resolve()).model`.
    """

    @cached_property
    def model(self) -> ModelWrapper:
        return ModelWrapper(
            self.path.name,
            {
                **ModelProvider_SDF.asdict(self.path, self.path.name),
            },
        )


@attrs.define(eq=False, hash=False)
class PedestrianIdentifier(DomainAssetIdentifier[PedestrianView]):
    """Represents an identifier referencing a 3D model asset."""

    _asset_type = 'Pedestrian'

    def load(self, path: Path, /, **kwargs: object) -> PedestrianView:
        del kwargs  # unused
        return PedestrianView(path)


PedestrianIdentifier.use(*DynamicPaths.as_resolvers(PedestrianIdentifier))
PedestrianIdentifier.use(*NetResolver.all(PedestrianIdentifier))
