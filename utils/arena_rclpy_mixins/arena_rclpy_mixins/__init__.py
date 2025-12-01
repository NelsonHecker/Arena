import rclpy.node

from .LifecycleClient import LifecycleClient, AsyncLifecycleClient
from .ROSParamServer import ROSParamServer
from .ServiceNamespace import ServiceNamespace


class ArenaMixinNode(ROSParamServer, LifecycleClient, AsyncLifecycleClient, ServiceNamespace, rclpy.node.Node):
    """
    Megaclass with all mixins contained in arena_rclpy_mixins into the Node class.
    """
