import typing

from task_generator.tasks import TaskMode

if typing.TYPE_CHECKING:
    from task_generator.tasks.task import Task


class TM_Module(TaskMode):
    _TASK: "Task"

    def __init__(self, *args, task: "Task", **kwargs):
        super().__init__(*args, props=task, **kwargs)
        self._TASK = task

    def before_reset(self): ...

    def after_reset(self): ...
