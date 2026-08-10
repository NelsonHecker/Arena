from arena_evaluation_mcp.tools import register_tools
from arena_evaluation_mcp.eval_bridge import EvalBridge
from mcp.server import Server

server = Server("test")
bridge = EvalBridge()
register_tools(server, bridge)

print(f"Bridge OK - data_root: {bridge.data_root}")
print(f"Benchmarks: {len(bridge.list_benchmarks())}")
print(f"Maps: {bridge.discover_available_maps()}")
print(f"Manifests: {bridge.discover_available_manifests()}")
print(f"Metrics: {len(bridge.discover_available_metrics())} metrics")
print(f"Planners: {bridge.discover_available_planners()}")
print(f"Inter planners: {bridge.discover_available_inter_planners()}")
print("All modules load successfully")
