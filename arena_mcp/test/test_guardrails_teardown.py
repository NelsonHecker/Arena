from __future__ import annotations

import asyncio
import os
from pathlib import Path

import pytest

from arena_mcp.core.errors import ToolError
from arena_mcp.domains.jobs import MAX_WAIT_S, jobs_wait
from arena_mcp.domains.system import system_health, system_logs, system_teardown


def test_jobs_wait_rejects_timeout_above_transport_cap() -> None:
    assert MAX_WAIT_S == 150.0
    with pytest.raises(ToolError, match="150"):
        asyncio.run(jobs_wait("nonexistent-job", timeout_s=180.0))
    with pytest.raises(ToolError, match="150"):
        asyncio.run(jobs_wait("nonexistent-job", timeout_s=300.0))


def test_system_health_and_logs_read_benchmark_roslog_dir(tmp_path: Path) -> None:
    prev = os.environ.get("ARENA_DATA_DIR")
    os.environ["ARENA_DATA_DIR"] = str(tmp_path)
    try:
        roslog = tmp_path / "benchmarks" / "demo_run" / "roslog"
        roslog.mkdir(parents=True)
        log_file = roslog / "arena_env_0_123_456.log"
        log_file.write_text("line1\nGazebo control timeout\n", encoding="utf-8")

        health = system_health(run_id="demo_run")
        assert health["roslog_dir"] == str(roslog)
        assert "arena_env_0_123_456.log" in health["recent_roslogs"]
        assert isinstance(health["process_count"], int)

        log_res = system_logs(node="arena_env_0", run_id="demo_run", lines=10)
        assert log_res["run_id"] == "demo_run"
        assert "Gazebo control timeout" in log_res["log"]
    finally:
        if prev is None:
            os.environ.pop("ARENA_DATA_DIR", None)
        else:
            os.environ["ARENA_DATA_DIR"] = prev


def test_system_teardown_rejects_invalid_grace_window() -> None:
    with pytest.raises(ToolError, match="grace_s"):
        asyncio.run(system_teardown(grace_s=0.0))
    with pytest.raises(ToolError, match="grace_s"):
        asyncio.run(system_teardown(grace_s=120.0))
