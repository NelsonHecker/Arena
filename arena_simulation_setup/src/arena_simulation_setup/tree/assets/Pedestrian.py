from arena_simulation_setup.tree import AssetType, DynamicProvider, NetResolver, Resolvers
from arena_simulation_setup.utils.models.model_loader import (
    ModelLoader,
    ModelProvider_SDF,
)


class PedestrianProvider(DynamicProvider):
    ...


PedestrianResolver = NetResolver(AssetType.PEDESTRIAN)
Resolvers.register(PedestrianResolver)

Pedestrian = PedestrianProvider.bind(PedestrianResolver)
loader = ModelLoader(Pedestrian, (ModelProvider_SDF,))
