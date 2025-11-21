import os

from ament_index_python import get_package_share_directory

from .bt_models import Root
from .context import ARENA_CONTEXT, BEHAVIOR_TREE_CONTEXT
from .vector_db import (
    create_chroma_db,
    get_chroma_collection,
    get_relevant_bt_nodes,
    process_json_doc,
)

LOCAL_LM = "Qwen/Qwen3-0.6B"
REMOTE_LM = "gemini-2.5-flash"
CHROMA_DB_PATH = os.path.join(
    get_package_share_directory("task_generator"),
    "prompt_utils",
    "chroma"
)
BT_REF_DOC_PATH = os.path.join(
    get_package_share_directory("task_generator"),
    "prompt_utils",
    "HuNavSim_BT_Reference_Structured.json"
)


__all__ = [
    "ARENA_CONTEXT",
    "BEHAVIOR_TREE_CONTEXT",
    "BT_REF_DOC_PATH",
    "create_chroma_db",
    "get_chroma_collection",
    "get_relevant_bt_nodes",
    "process_json_doc",
    "Root"
]
