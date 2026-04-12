from arena_rclpy_mixins.shared import Namespace

from task_generator import NodeInterface
from task_generator.tasks.context import TaskContext


class Namespaced:
    _namespace: Namespace = Namespace('').ParamNamespace()

    def namespace(self, *path: str) -> Namespace:
        return self._namespace(*path)


class TaskMode(NodeInterface, Namespaced):
    _ctx: TaskContext

    def __init__(self, *args, ctx: TaskContext, namespace: Namespace, **kwargs):
        super().__init__(*args, **kwargs)
        self._ctx = ctx
        self._namespace = namespace
