import warnings
from .worlds import World
from .worlds.scenario import Scenario

warnings.warn(
    "The 'arena_simulation_setup.world' module is deprecated. "
    "Use 'arena_simulation_setup.worlds' instead.",
    FutureWarning,
    stacklevel=2
)

__all__ = [
    'World',
    'Scenario',
]
