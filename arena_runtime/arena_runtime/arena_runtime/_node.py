from __future__ import annotations

import rclpy.impl.rcutils_logger
import rclpy.node


class NodeInterface[NodeT: rclpy.node.Node]:
    def __init__(self, *args: object, node: NodeT, **kwargs: object) -> None:
        super().__init__(*args, **kwargs)
        self.__node = node

    @property
    def node(self) -> NodeT:
        return self.__node

    @property
    def _logger(self) -> rclpy.impl.rcutils_logger.RcutilsLogger:
        return self.node.get_logger().get_child(type(self).__name__)
