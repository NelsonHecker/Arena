import typing

from task_generator.constants import Constants
from task_generator.tasks.obstacles.scenario import declare_schema
from task_generator.tasks.registry import _REGISTRY_NAMESPACE, ROBOTS_MODES

if typing.TYPE_CHECKING:
    from task_generator.tasks.robots import TM_Robots

_NS = _REGISTRY_NAMESPACE("scenario")


@ROBOTS_MODES.register(Constants.TaskMode.TM_Robots.SCENARIO, namespace=_NS, schema=declare_schema)
def _load_scenario() -> type["TM_Robots"]:
    from .impl import TM_Scenario

    return TM_Scenario
