from arena_hunav_sim_bridge import BT_REF_DOC_PATH, CHROMA_DB_PATH

from .context import (
    ARENA_FORMAT,
    BEHAVIOR_TREE_FORMAT,
    SPLIT_PROMPT_INSTRUCTION,
    SYSTEM_INSTRUCTION,
)
from .vector_db import (
    create_chroma_db,
    get_chroma_collection,
    get_relevant_bt_nodes,
    process_json_doc,
)

LOCAL_LM = "Qwen/Qwen3-0.6B"
REMOTE_LM = "gemini-3-pro-preview"


__all__ = [
    "ARENA_FORMAT",
    "BEHAVIOR_TREE_FORMAT",
    "SYSTEM_INSTRUCTION",
    "SPLIT_PROMPT_INSTRUCTION",
    "BT_REF_DOC_PATH",
    "CHROMA_DB_PATH",
    "create_chroma_db",
    "get_chroma_collection",
    "get_relevant_bt_nodes",
    "process_json_doc",
]
