import typing

from arena_rclpy_mixins.shared import Namespace

from task_generator.constants import Constants
from task_generator.tasks.registry import _TaskRegistry

if typing.TYPE_CHECKING:
    from arena_rclpy_mixins.ROSParamServer import ROSParamServer

    from task_generator.tasks.robots import TM_Robots


def declare_schema(node: "ROSParamServer", ns: Namespace) -> None:
    del node, ns


@_TaskRegistry.register_robots(Constants.TaskMode.TM_Robots.EXPLORE, schema=declare_schema)
def _loader() -> "type[TM_Robots]":
    from .impl import TM_Explore

    return TM_Explore
