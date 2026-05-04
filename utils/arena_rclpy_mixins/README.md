# arena_rclpy_mixins

Shared ROS 2 / asyncio glue for the Arena-Rosnav workspace. Provides the
`ArenaMixinNode` megaclass, typed ROS parameter helpers, lifecycle client
utilities, namespace tools, and spin/teardown helpers. The CLAUDE.md rule:
**scan this package before writing new ROS glue** (namespaces, async, lifecycle,
params, time). If a facility already exists here, use it instead of
hand-rolling.

## Public API

Sourced from `__init__.py` plus the submodules it re-exports.

| Name | Kind | What it does | When to use it |
| --- | --- | --- | --- |
| `ArenaMixinNode` | class | All mixins composed with `rclpy.node.Node`; override `setup()` / `teardown()` | Base class for every Arena node |
| `ROSParamServer` | mixin | Typed `.ROSParam[T]` and `.rosparam[T]` descriptors, callback-on-set | Nodes that declare or read ROS params |
| `LifecycleClient` | mixin | Sync `get_lifecycle_state`, `change_lifecycle_state`, `wait_for_lifecycle_state` | Driving a peer lifecycle node from sync code |
| `AsyncLifecycleClient` | mixin | Async `*_async` variants of the above via `ClientWrapper` | Driving a peer lifecycle node from `async` context |
| `ServiceNamespace` | mixin | `service_namespace(*parts)` — node-FQN-prefixed `Namespace` | Correct service/topic prefixing (rclpy ignores node namespace for services) |
| `TimeNode` | mixin | `.sim_time`, `.wall_time`, `.time`, `.wall_clock`, `.wall_timer()`, `.sim_time_rate()` | Any node that needs clock utilities |
| `Time` | class | Arithmetic, comparable, converts between `rclpy.time.Time`, `builtin_interfaces.msg.Time`, `rosgraph_msgs.msg.Clock`, and `float` | Time math without rclpy churn |
| `AsyncNode` | class | `await_ros()`, `wait_for()`, `sync_wrap()`, `syncify()`, `create_client_wrapper()`, `create_action_client_wrapper()`, `do_launch()` | Nodes mixing async and sync code |
| `ClientWrapper` | class | Async `call_timeout()` / sync `call_timeout_sync()` around a service client | Service calls with timeout logging |
| `ActionClientWrapper` | class | `send_goal()`, `send_goal_timeout()`, `await_result()`, `send_and_await()`, `cancel()`, `ensure()` | Action client with timeout wrappers |
| `AsyncUtil` | class | `AsyncUtil.timeout(coro, sec)` — `asyncio.wait_for` that returns `None` on timeout | One-off timeout wrapper |
| `AsyncLaunchManager` | class | Async `launch_description()`, `kill_all()` — manages active `LaunchService` tasks | Nodes that programmatically launch sub-processes |
| `Namespace` | class | `str` subclass with `/`-join `__call__`, `.simulation_ns`, `.robot_ns`, `.remove_double_slash()` | Building topic / service paths |
| `FrameNamespace` | class | `Namespace` subclass with `.sanitize()` (replaces non-alphanumeric with `_`) | TF frame name construction |
| `ParamNamespace` | class | `Namespace` with `.`-join `__call__`, converts to/from slash namespaces | ROS param key construction |
| `ClassRegistry` | class | Lazy `key -> class` registry with `.register(key)` decorator, cached on first `.get(key)` | Kind-based class lookup (e.g. simulator kind to class) |
| `FactoryRegistry` | class | Like `ClassRegistry` but factory is called fresh on every `.get(key, *args)` | Per-call factory dispatch |
| `AsyncFactoryRegistry` | class | Async version of `FactoryRegistry`; `.get()` returns an `Awaitable` | Async factory dispatch |

## Mixins and `ArenaMixinNode`

`ArenaMixinNode` inherits `ROSParamServer`, `LifecycleClient`,
`AsyncLifecycleClient`, `ServiceNamespace`, `TimeNode`, and
`rclpy.node.Node` in MRO order. Use it as the sole base for Arena nodes:

```python
class MyNode(ArenaMixinNode, rclpy.lifecycle.LifecycleNode):
    async def setup(self) -> None: ...   # called once by run_main
    async def teardown(self) -> None: ...  # called on SIGINT/SIGTERM
```

`run_main` (classmethod) is the standard entry point: `def main(): MyNode.run_main()`.

## Async bridge

`AsyncNode.await_ros(ros_future)` bridges a rclpy `Future` into the asyncio
event loop without blocking. Use it (and `ClientWrapper` / `ActionClientWrapper`
built on top of it) instead of `asyncio.wrap_future` or hand-rolled
`run_coroutine_threadsafe` chains — the rclpy bridge is subtle and the wrappers
handle thread-safety and timeout logging correctly.

`create_subscription` and `create_service` on `AsyncNode` transparently accept
`async def` callbacks via `syncify()`, so callers never need to bridge those
manually.

`wait_for(future)` submits a coroutine to the node's event loop and blocks the
calling thread until done. It warns if called from the event loop thread itself
(would deadlock).

## Time and params

`TimeNode` subscribes to `/clock` and exposes `.sim_time` (latest simulated
time), `.wall_time` (datetime-based wall clock), and `.time` (delegates to the
node clock, respecting `use_sim_time`). `wall_timer(period, cb)` creates a
timer driven by the steady wall clock regardless of `use_sim_time`. The `Time`
value type supports arithmetic, comparison, and round-trips to all ROS time
representations.

`ROSParamServer` exposes two per-node helpers bound to `self`:

- `self.ROSParam[T](name, default)` — declares a param, registers a callback,
  and keeps a typed `.value` property in sync with the param server.
- `self.rosparam[T].get(name, default)` / `.set(name, value)` /
  `.declare_safe(name, value)` — lightweight one-shot param access without a
  persistent descriptor.

## Spin and lifecycle

`spin.py` owns process-level startup and teardown.

`run_main(node_cls, *args, **kwargs)` calls `asyncio.run(async_main(...))`.
`async_main` initialises rclpy, creates a `MultiThreadedExecutor`, spins it in
a thread-pool worker, installs `SIGINT`/`SIGTERM` handlers, calls `node.setup()`,
and on shutdown awaits `node.teardown()` (5 s timeout), cancels pending tasks,
drains launches, and calls `rclpy.try_shutdown()`.

`spin_node(node)` is the simpler sync equivalent for non-async nodes.
`spin_context()` is a context manager that suppresses `KeyboardInterrupt` /
`ExternalShutdownException` and shuts down the executor and rclpy on exit.

Optional `aiomonitor` integration: override `aiomonitor_config()` on the node
to return kwargs for `aiomonitor.start_monitor`, then pass `aiomonitor=True`
to `run_main`.
