import typing

from arena_rclpy_mixins.ROSParamServer import ROSParamServer
from arena_rclpy_mixins.shared import Namespace

from task_generator.constants import Constants
from task_generator.tasks.declarations import declare_catalog
from task_generator.tasks.registry import _REGISTRY_NAMESPACE, OBSTACLES_MODES

if typing.TYPE_CHECKING:
    from task_generator.tasks.obstacles import TM_Obstacles

_NS = _REGISTRY_NAMESPACE("scenario")


def declare_schema(node: ROSParamServer, ns: Namespace) -> None:
    """Shared schema for the `scenario` task mode, used by both TM_Obstacles and TM_Robots."""
    declare_catalog(node, ns("file"), "default", catalog="scenarios", label="Scenario file", description="Scenario file name.")


@OBSTACLES_MODES.register(Constants.TaskMode.TM_Obstacles.SCENARIO, namespace=_NS, schema=declare_schema)
def _load_scenario() -> type["TM_Obstacles"]:
    from .impl import TM_Scenario

    return TM_Scenario
