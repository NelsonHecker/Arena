from arena_simulation_setup.tree import AssetType, DynamicProvider, NetResolver, Resolvers
from arena_simulation_setup.utils.models.model_loader import (
    ModelLoader,
    ModelProvider_SDF,
    ModelProvider_USD,
)


class ObjectProvider(DynamicProvider):
    ...


ObjectResolver = NetResolver(AssetType.OBJECT)
Resolvers.register(ObjectResolver)

Object = ObjectProvider.bind(ObjectResolver)
loader = ModelLoader(Object, (ModelProvider_SDF, ModelProvider_USD))
