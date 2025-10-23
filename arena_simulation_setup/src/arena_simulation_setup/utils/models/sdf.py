from . import ModelProvider, Model, ModelType


class ModelProvider_SDF(ModelProvider.provides(ModelType.SDF)):

    @classmethod
    def load(cls, model_dir, model, loader_args):
        model_path = model_dir / model / f"{model}.sdf"
        try:
            with open(model_path) as f:
                return Model(
                    type=ModelType.SDF,
                    name=model,
                    description=f.read(),
                    path=model_path
                )
        except FileNotFoundError:
            pass
        return None
