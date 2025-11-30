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
from arena_hunav_sim_bridge import BT_REF_DOC_PATH, CHROMA_DB_PATH

LOCAL_LM = "Qwen/Qwen3-0.6B"
REMOTE_LM = "gemini-3-pro-preview"


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
