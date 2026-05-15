import typing

from arena_rclpy_mixins.ROSParamServer import ROSParamServer
from arena_rclpy_mixins.shared import Namespace

from task_generator.constants import Constants
from task_generator.tasks.declarations import declare_double, declare_enum, declare_string
from task_generator.tasks.registry import _REGISTRY_NAMESPACE, OBSTACLES_MODES

if typing.TYPE_CHECKING:
    from task_generator.tasks.obstacles import TM_Obstacles

_NS = _REGISTRY_NAMESPACE("prompt")


def _declare_schema(node: ROSParamServer, ns: Namespace) -> None:
    declare_string(node, ns("user_prompt"), "An empty space with no pedestrian.", label="Prompt", description="Natural-language prompt describing the desired crowd.")
    declare_double(node, ns("top_p"), 0.3, label="Top-p", description="Nucleus sampling top-p for LLM generation.")
    declare_enum(node, ns("generation_mode"), "arena", choices=["arena", "behavior_tree", "crowded_behavior_tree"], label="Generation mode", description="Generation mode.")


@OBSTACLES_MODES.register(Constants.TaskMode.TM_Obstacles.PROMPT, namespace=_NS, schema=_declare_schema)
def _load_prompt() -> type["TM_Obstacles"]:
    from .prompt import TM_Prompt

    return TM_Prompt
