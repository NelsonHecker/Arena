import aiofiles

from . import Model, ModelProvider, ModelType

# raise RuntimeError('YAML models are not supported anymore')


class ModelProvider_YAML(ModelProvider.provides(ModelType.YAML)):

    @classmethod
    async def load(cls, model_dir, model, loader_args) -> Model:

        model_path = model_dir / f"{model}.yaml"

        async with aiofiles.open(model_path, 'r') as f:
            model_desc = await f.read()

        model_obj = Model(
            type=ModelType.YAML,
            name=model,
            description=model_desc,
            path=model_path
        )
        return model_obj
