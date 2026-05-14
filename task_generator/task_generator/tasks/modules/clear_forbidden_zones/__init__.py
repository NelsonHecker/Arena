import typing

from task_generator.constants import Constants
from task_generator.tasks.registry import _REGISTRY_NAMESPACE, MODULE_MODES

if typing.TYPE_CHECKING:
    from task_generator.tasks.modules import TM_Module

_NS = _REGISTRY_NAMESPACE("clear_forbidden_zones")


@MODULE_MODES.register(Constants.TaskMode.TM_Module.CLEAR_FORBIDDEN_ZONES, namespace=_NS)
def _load_clear_forbidden_zones() -> type["TM_Module"]:
    from .impl import Mod_ClearForbiddenZones

    return Mod_ClearForbiddenZones
