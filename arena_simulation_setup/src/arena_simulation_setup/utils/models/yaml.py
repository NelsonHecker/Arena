import os

from . import Model, ModelType, ModelProvider

# raise RuntimeError('YAML models are not supported anymore')


class ModelProvider_YAML(ModelProvider.provides(ModelType.YAML)):

    @classmethod
    def load(cls, model_dir, model, loader_args):

        model_path = model_dir / f"{model}.yaml"

        try:
            with open(model_path) as f:
                model_desc = f.read()
        except FileNotFoundError:
            return None

        model_obj = Model(
            type=ModelType.YAML,
            name=model,
            description=model_desc,
            path=model_path
        )
        return model_obj
