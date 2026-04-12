from __future__ import annotations

import typing

import rclpy.impl.rcutils_logger

from task_generator.safe_callback import SafeCallbackNode  # noqa: F401

if typing.TYPE_CHECKING:
    from task_generator.node import TaskGenerator


class NodeInterface:
    def __init__(self, *args, node: TaskGenerator, **kwargs) -> None:
        super().__init__(*args, **kwargs)
        self.__node = node

    @property
    def node(self) -> TaskGenerator:
        return self.__node

    @property
    def _logger(self) -> rclpy.impl.rcutils_logger.RcutilsLogger:
        return self.node.get_logger().get_child(type(self).__name__)
