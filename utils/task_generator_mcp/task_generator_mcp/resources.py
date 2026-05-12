from __future__ import annotations

import json

from mcp.server import Server
from mcp.types import Resource, TextContent

from .ros_bridge import RosBridge
from .tools import _param_value_to_python


def _record_to_dict(record: object) -> dict:
    return {
        "episode_id": record.episode_id,
        "world": record.world,
        "seed": record.seed,
        "tm_robots": record.tm_robots,
        "tm_obstacles": record.tm_obstacles,
        "tm_modules": list(record.tm_modules),
        "outcome_state": record.outcome_state,
        "outcome_info": record.outcome_info,
        "goal_uuid": record.goal_uuid,
        "integrity": record.integrity,
        "obstacles_params": [{"name": p.name, "type": p.value.type, "value": _param_value_to_python(p.value)} for p in record.obstacles_params],
        "robots_params": [{"name": p.name, "type": p.value.type, "value": _param_value_to_python(p.value)} for p in record.robots_params],
    }


def register_resources(server: Server, bridge: RosBridge) -> None:
    """Register MCP resources on *server* backed by *bridge* state caches."""

    @server.list_resources()
    async def list_resources() -> list[Resource]:
        return [
            Resource(
                uri="task_generator://state/world",
                name="Current world id",
                description="The world id currently active in the task_generator node. Updated whenever the world changes at a reset boundary.",
                mimeType="text/plain",
            ),
            Resource(
                uri="task_generator://state/episode",
                name="Episode state",
                description="Episode state as JSON: current episode record and queued (next) episode record.",
                mimeType="application/json",
            ),
        ]

    @server.read_resource()
    async def read_resource(uri: str) -> list[TextContent]:
        if uri == "task_generator://state/world":
            return [TextContent(type="text", text=bridge.state_world)]

        if uri == "task_generator://state/episode":
            cur = bridge.current_episode
            que = bridge.queued_episode
            payload = {
                "current": _record_to_dict(cur) if cur is not None else None,
                "queued": _record_to_dict(que) if que is not None else None,
            }
            return [TextContent(type="text", text=json.dumps(payload, default=str))]

        return [TextContent(type="text", text=json.dumps({"error": f"unknown resource: {uri}"}))]
