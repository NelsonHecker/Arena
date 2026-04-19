import rclpy.node

from .LifecycleClient import AsyncLifecycleClient, LifecycleClient
from .ROSParamServer import ROSParamServer
from .ServiceNamespace import ServiceNamespace
from .Time import TimeNode


class ArenaMixinNode(ROSParamServer, LifecycleClient, AsyncLifecycleClient, ServiceNamespace, TimeNode, rclpy.node.Node):
    """
    Megaclass with all mixins contained in arena_rclpy_mixins into the Node class.
    """
