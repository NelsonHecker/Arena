import typing

from arena_rclpy_mixins.ROSParamServer import ROSParamServer
from arena_rclpy_mixins.shared import Namespace

from task_generator.constants import Constants
from task_generator.tasks.declarations import declare_catalog
from task_generator.tasks.registry import _REGISTRY_NAMESPACE, OBSTACLES_MODES

if typing.TYPE_CHECKING:
    from task_generator.tasks.obstacles import TM_Obstacles

_NS = _REGISTRY_NAMESPACE("parametrized")


def _declare_schema(node: ROSParamServer, ns: Namespace) -> None:
    declare_catalog(node, ns("file"), "", catalog="parametrizeds", label="Parametrized file", description="Parametrized config file name.")


@OBSTACLES_MODES.register(Constants.TaskMode.TM_Obstacles.PARAMETRIZED, namespace=_NS, schema=_declare_schema)
def _load_parametrized() -> type["TM_Obstacles"]:
    from .impl import TM_Parametrized

    return TM_Parametrized
