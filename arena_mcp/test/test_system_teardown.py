from __future__ import annotations

import asyncio
import os
import subprocess
import sys

import pytest

from arena_mcp.core import proc
from arena_mcp.core.errors import ToolError
from arena_mcp.domains.system import system_teardown


def test_system_teardown_rejects_invalid_grace_window() -> None:
    with pytest.raises(ToolError, match="grace_s"):
        asyncio.run(system_teardown(grace_s=0.0))
    with pytest.raises(ToolError, match="grace_s"):
        asyncio.run(system_teardown(grace_s=120.0))


def test_system_teardown_kills_arena_target_without_killing_self_or_mcp_peer() -> None:
    arena_dummy = subprocess.Popen(
        [sys.executable, "-c", "import time; time.sleep(60)", "arena_env_node"],
        start_new_session=True,
    )
    mcp_dummy = subprocess.Popen(
        [sys.executable, "-c", "import time; time.sleep(60)", "arena_mcp"],
        start_new_session=True,
    )
    try:
        result = asyncio.run(system_teardown(grace_s=2.0))
        assert arena_dummy.pid in result["terminated_pids"]
        assert result["stopped"] is True
        assert proc.alive(os.getpid())
        assert proc.alive(mcp_dummy.pid)
    finally:
        for child in (arena_dummy, mcp_dummy):
            if child.poll() is None:
                child.kill()
                child.wait(timeout=5.0)
