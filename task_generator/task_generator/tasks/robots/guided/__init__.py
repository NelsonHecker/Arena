import typing

from task_generator.constants import Constants
from task_generator.tasks.registry import _REGISTRY_NAMESPACE, ROBOTS_MODES

if typing.TYPE_CHECKING:
    from task_generator.tasks.robots import TM_Robots

_NS = _REGISTRY_NAMESPACE("guided")


@ROBOTS_MODES.register(Constants.TaskMode.TM_Robots.GUIDED, namespace=_NS)
def _load_guided() -> type["TM_Robots"]:
    from .impl import TM_Guided

    return TM_Guided
