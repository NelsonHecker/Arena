from __future__ import annotations

import typing

from arena_simulation_setup.utils.models import ModelWrapper
from arena_simulation_setup.utils.models.model_loader import ModelLoader


def model_parse(parser: ModelLoader, *, overrides: typing.Iterable[ModelLoader] = ()) -> typing.Callable[[typing.Any], ModelWrapper]:
    def validator(v: str | ModelWrapper) -> ModelWrapper:
        if isinstance(v, ModelWrapper):
            if any(v.loader_matches(overridee) for overridee in overrides):
                return parser.bind(v.name)
            return v
        return parser.bind(v)
    return validator
