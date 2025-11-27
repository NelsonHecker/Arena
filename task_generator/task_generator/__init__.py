import typing

import launch
import rclpy
import rclpy.node
import rclpy.client
import rclpy.callback_groups
import rclpy.impl.rcutils_logger
from arena_rclpy_mixins import ArenaMixinNode
from arena_rclpy_mixins.ROSParamServer import ROSParamServer


class SafeCallbackNode(rclpy.node.Node):
    """
    Automatically make clients part of a new MutuallyExclusiveCallbackGroup to avoid deadlocks.
    """

    @property
    def default_callback_group(self) -> rclpy.callback_groups.CallbackGroup:
        return rclpy.callback_groups.MutuallyExclusiveCallbackGroup()


class NodeInterface:
    class Taskgen_T(ArenaMixinNode, SafeCallbackNode):
        do_launch: typing.Callable[[launch.LaunchDescription], None]

        # TODO
        _environment_manager: typing.Any
        _world_manager: typing.Any
        conf: typing.Any

    node: Taskgen_T

    def __init__(self) -> None:
        ...

    @property
    def _logger(self) -> rclpy.impl.rcutils_logger.RcutilsLogger:
        return self.node.get_logger().get_child(type(self).__name__)

    @classmethod
    def init_task_gen_node(
        cls,
        do_launch: typing.Callable[[launch.LaunchDescription], None],
    ) -> ROSParamServer:

        from .node import TaskGenerator
        NodeInterface.node = TaskGenerator(do_launch=do_launch)

        # TODO deprecate
        from .shared import configure_node
        configure_node(NodeInterface.node)

        return NodeInterface.node
