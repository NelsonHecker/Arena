import attrs

from arena_simulation_setup.tree import (
    AssetType,
    DynamicProvider,
    Identifier,
    NetResolver,
    Resolvers,
)
from arena_simulation_setup.utils.models import ModelWrapper
from arena_simulation_setup.utils.models.model_loader import (
    ModelProvider_SDF,
    ModelProvider_USD,
)


class ObjectProvider(DynamicProvider[ModelWrapper]):

    def load(self, *args, **kwargs) -> ModelWrapper:
        resolved = self.resolve(self.identifier)
        if resolved is None:
            raise FileNotFoundError(f'Object model {self.identifier} not found')
        return ModelWrapper(
            self.name,
            {
                **ModelProvider_USD.asdict(resolved, resolved.name),
                **ModelProvider_SDF.asdict(resolved, resolved.name),
            }
        )


ObjectResolver = NetResolver(AssetType.OBJECT)
Resolvers.register(ObjectResolver)

ObjectLoader = ObjectProvider.bind(ObjectResolver)


@attrs.define(eq=False, hash=False)
class ObjectIdentifier(Identifier[ModelWrapper]):
    """Represents an identifier referencing a 3D model asset.
    """


ObjectIdentifier.provide(ObjectLoader)
