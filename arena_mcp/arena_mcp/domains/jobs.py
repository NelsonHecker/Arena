from __future__ import annotations

from typing import Any

from arena_mcp.core import JOBS, Domain, ToolError

domain = Domain(
    "jobs",
    """Long operations started by any domain: episodes, robot actions, benchmarks, processing, training, launches, generation.
    Process jobs outlive the server and stay listed after a restart, in-process jobs end with it.""",
)


@domain.tool(read_only=True)
def jobs_list(kind: str | None = None, state: str | None = None, limit: int = 30) -> list[dict[str, Any]]:
    """Jobs, newest first, optionally filtered by kind (the prefix of the id) or state (running, succeeded, failed, cancelled, lost)."""
    return [job.as_dict() for job in JOBS.list(kind=kind, state=state, limit=limit)]


@domain.tool(read_only=True)
def jobs_status(job_id: str) -> dict[str, Any]:
    """One job: state, progress, result or error, log path."""
    return JOBS.get(job_id).as_dict()


@domain.tool(read_only=True)
def jobs_log(job_id: str, lines: int = 100) -> str:
    """The last lines of a job's log."""
    return JOBS.tail(job_id, lines)


MAX_WAIT_S = 150.0


@domain.tool(read_only=True)
async def jobs_wait(job_id: str, timeout_s: float = 30.0) -> dict[str, Any]:
    """Wait up to timeout_s (at most 150, below the 180s MCP transport deadline) for a job to finish, then return its status."""
    if not 0 < timeout_s <= MAX_WAIT_S:
        raise ToolError(f"timeout_s must be in (0, {int(MAX_WAIT_S)}]", hint="call jobs_wait again for longer jobs")
    return (await JOBS.wait(job_id, timeout_s)).as_dict()


@domain.tool(destructive=True)
async def jobs_cancel(job_id: str) -> dict[str, Any]:
    """Stop a job: process jobs get SIGINT, then SIGTERM and SIGKILL only if they survive the grace window, launch jobs run the system_stop ladder to its end."""
    return (await JOBS.cancel(job_id)).as_dict()
