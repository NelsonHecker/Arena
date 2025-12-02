import aiofiles

from . import Model, ModelProvider, ModelType


class ModelProvider_SDF(ModelProvider.provides(ModelType.SDF)):

    @classmethod
    async def load(cls, model_dir, model, loader_args) -> Model:
        model_path = model_dir / model / f"{model}.sdf"
        async with aiofiles.open(model_path) as f:
            return Model(
                type=ModelType.SDF,
                name=model,
                description=await f.read(),
                path=model_path
            )
