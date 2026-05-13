import typing

from task_generator.constants import Constants
from task_generator.tasks.registry import _REGISTRY_NAMESPACE, MODULE_MODES

if typing.TYPE_CHECKING:
    from task_generator.tasks.modules import TM_Module

_NS = _REGISTRY_NAMESPACE("staged")


@MODULE_MODES.register(Constants.TaskMode.TM_Module.STAGED, namespace=_NS)
def _load_staged() -> type["TM_Module"]:
    from .impl import Mod_Staged

    return Mod_Staged
