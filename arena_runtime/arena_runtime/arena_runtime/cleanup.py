from __future__ import annotations

import re

from arena_runtime.sim._interface import SimLifecycle

_ENV_PREFIX_RE = re.compile(r'^env_\d+[/_]')


def is_valid_env_prefix(prefix: str) -> bool:
    return bool(_ENV_PREFIX_RE.match(prefix))


class CleanupManager:
    def __init__(self, lifecycle: SimLifecycle) -> None:
        self._lifecycle = lifecycle

    async def cleanup_namespace(self, prefix: str, *, internal: bool = False) -> tuple[bool, int, str]:
        if not internal and not is_valid_env_prefix(prefix):
            return False, 0, f"invalid prefix {prefix!r}: must match env_<digits>/ or env_<digits>_"
        removed = await self._lifecycle.cleanup_namespace(prefix)
        return True, removed, ""
