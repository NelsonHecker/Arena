import aiofiles

from . import Model, ModelProvider, ModelType


class ModelProvider_SDF(ModelProvider.provides(ModelType.SDF)):

    @classmethod
    async def load(cls, model_dir, model, loader_args) -> Model:
        model_paths = (
            model_dir / f"{model}.sdf" / f"{model}.sdf",
            model_dir / f"{model}.sdf",
        )
        model_path = next((p for p in model_paths if p.is_file()), None)
        if model_path is None:
            raise FileNotFoundError(f"Could not find SDF model file for '{model}' in '{model_dir}' (searched: {model_paths})")
        async with aiofiles.open(model_path) as f:
            return Model(
                type=ModelType.SDF,
                name=model,
                description=await f.read(),
                path=model_path
            )
