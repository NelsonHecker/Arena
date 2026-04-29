from __future__ import annotations

import asyncio
import logging

import rclpy
from mcp.server import Server
from mcp.server.stdio import stdio_server

from .resources import register_resources
from .ros_bridge import RosBridge
from .tools import register_tools

logger = logging.getLogger(__name__)

_DISCOVERY_TIMEOUT = 10.0


async def _wait_for_bridge(bridge: RosBridge) -> None:
    """Wait briefly for initial state/episode to arrive from latched topic."""
    deadline = asyncio.get_event_loop().time() + _DISCOVERY_TIMEOUT
    while bridge.current_episode is None:
        if asyncio.get_event_loop().time() >= deadline:
            logger.warning("state/episode not received within %.1fs; continuing anyway", _DISCOVERY_TIMEOUT)
            break
        await asyncio.sleep(0.1)


async def _run(bridge: RosBridge) -> None:
    await _wait_for_bridge(bridge)

    # Fetch param descriptors once for the full allowlist; tools.py caches them.
    # (Descriptors are passed through to register_tools for schema building.)
    from rcl_interfaces.srv import DescribeParameters

    from .params import EPISODE_PARAMS, STATIC_CONFIG_PARAMS

    all_params = list(EPISODE_PARAMS) + list(STATIC_CONFIG_PARAMS)
    req = DescribeParameters.Request()
    req.names = all_params
    resp = await bridge.client_describe_parameters.call_timeout(req, timeout_sec=_DISCOVERY_TIMEOUT)
    param_descriptors: dict[str, object] = {}
    if resp is not None:
        for name, desc in zip(all_params, resp.descriptors, strict=True):
            param_descriptors[name] = desc

    server = Server("task_generator_mcp")
    register_tools(server, bridge, param_descriptors)
    register_resources(server, bridge)

    async with stdio_server() as (read_stream, write_stream):
        await server.run(read_stream, write_stream, server.create_initialization_options())


def main() -> None:
    rclpy.init()
    bridge = RosBridge()
    try:
        asyncio.run(_run(bridge))
    finally:
        bridge.destroy_node()
        rclpy.shutdown()
