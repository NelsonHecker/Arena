import typing

from task_generator.tasks import TaskMode

if typing.TYPE_CHECKING:
    from task_generator.tasks.task import Task


class TM_Module(TaskMode):
    _task: "Task"

    def __init__(self, *args: object, task: "Task", **kwargs: object) -> None:
        super().__init__(*args, **kwargs)
        self._task = task

    def before_reset(self): ...

    def after_reset(self): ...
