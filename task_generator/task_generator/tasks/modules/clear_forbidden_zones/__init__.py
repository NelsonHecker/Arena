import typing

from arena_rclpy_mixins.shared import Namespace

from task_generator.constants import Constants
from task_generator.tasks.registry import _TaskRegistry

if typing.TYPE_CHECKING:
    from arena_rclpy_mixins.ROSParamServer import ROSParamServer

    from task_generator.tasks.modules import TM_Module


def declare_schema(node: "ROSParamServer", ns: Namespace) -> None:
    pass


@_TaskRegistry.register_module(Constants.TaskMode.TM_Module.CLEAR_FORBIDDEN_ZONES, schema=declare_schema)
def _loader() -> "type[TM_Module]":
    from .impl import Mod_ClearForbiddenZones

    return Mod_ClearForbiddenZones
