import os

from .context import ARENA_FORMAT, BEHAVIOR_FORMAT, SYSTEM_INSTRUCTION

# Preview model names get retired (gemini-3-pro-preview died 2026-07); keep the
# default on a stable name and allow overriding without a rebuild.
REMOTE_LM = os.environ.get("ARENA_PROMPT_LLM", "gemini-3.5-flash")


__all__ = [
    "ARENA_FORMAT",
    "BEHAVIOR_FORMAT",
    "SYSTEM_INSTRUCTION",
    "REMOTE_LM",
]
