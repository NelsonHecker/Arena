import typing

from arena_rclpy_mixins.ROSParamServer import ROSParamServer
from arena_rclpy_mixins.shared import Namespace

from task_generator.constants import Constants
from task_generator.tasks.declarations import declare_string
from task_generator.tasks.registry import _REGISTRY_NAMESPACE, ROBOTS_MODES

if typing.TYPE_CHECKING:
    from task_generator.tasks.robots import TM_Robots

_NS = _REGISTRY_NAMESPACE("scenario")


def _declare_schema(node: ROSParamServer, ns: Namespace) -> None:
    declare_string(node, ns("file"), "default.json", description="Scenario file name resolved via WorldIdentifier.")


@ROBOTS_MODES.register(Constants.TaskMode.TM_Robots.SCENARIO, namespace=_NS, schema=_declare_schema)
def _load_scenario() -> type["TM_Robots"]:
    from .impl import TM_Scenario

    return TM_Scenario
