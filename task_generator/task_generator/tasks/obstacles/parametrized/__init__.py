import typing

from arena_rclpy_mixins.shared import Namespace

from task_generator.constants import Constants
from task_generator.tasks.declarations import declare_catalog
from task_generator.tasks.registry import _TaskRegistry

if typing.TYPE_CHECKING:
    from arena_rclpy_mixins.ROSParamServer import ROSParamServer

    from task_generator.tasks.obstacles import TM_Obstacles


def declare_schema(node: "ROSParamServer", ns: Namespace) -> None:
    declare_catalog(node, ns("file"), "", catalog="parametrizeds", label="Parametrized file", description="Parametrized config file name.")


@_TaskRegistry.register_obstacles(Constants.TaskMode.TM_Obstacles.PARAMETRIZED, schema=declare_schema)
def _loader() -> "type[TM_Obstacles]":
    from .impl import TM_Parametrized

    return TM_Parametrized
