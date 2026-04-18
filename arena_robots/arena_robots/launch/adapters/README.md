# Navigation adapters

A navigation adapter plugs a specific navstack (nav2, a no-op goal publisher,
RL planner, …) into task_generator's task-dispatch pipeline. Each adapter has
two halves:

| Half | Lives in | Role |
| --- | --- | --- |
| **Launch file** | `arena_robots/arena_robots/launch/adapters/<kind>.launch.py` | spawns the navstack's ROS nodes for one robot |
| **Python class** | `task_generator/task_generator/tasks/robots/adapters/<kind>.py` | implements the `Adapter` ABC — dispatches goals, polls completion, etc. |

Existing kinds: [`nav2.launch.py`](nav2.launch.py) / `Nav2Adapter`,
[`none.launch.py`](none.launch.py) / `NoneAdapter` (publishes goal_pose, runs
no navstack).

## Selection

A robot picks its adapter via `model_params.yaml`:

```yaml
navigator: nav2      # default
```

Precedence at runtime: `robot_setup` YAML > CLI `--navigator` > model_params.

## The Adapter ABC

Defined in
[`task_generator/task_generator/tasks/robots/adapters/__init__.py`](../../../../task_generator/task_generator/tasks/robots/adapters/__init__.py).
A subclass declares three class-level identity fields and implements the
lifecycle hooks it cares about:

```python
@register_adapter
class MyAdapter(Adapter):
    kind: str = "my_stack"                          # registry key
    requires = frozenset({"mobile"})                # actuator caps this needs
    accepts  = frozenset({TaskKind.GOTO_POSE})      # phase kinds this handles
    republishes_goal = False                        # True → RobotManager's goal-pub loop runs

    def launch_description(self, ctx: AdapterCtx):  # required
        ...

    async def dispatch_phase(self, phase, robot) -> None: ...
    def     is_phase_done(self, phase, robot) -> bool | None: ...
    async def wait_until_ready(self, robot, node_paths) -> None: ...
    async def on_move(self, pose, robot) -> None: ...
    def     on_episode_start(self) -> None: ...
    def     on_episode_end(self) -> None: ...
```

`AdapterCtx` is the immutable config snapshot passed into
`launch_description`:

| Field | Source |
| --- | --- |
| `namespace`, `robot_name`, `frame` | robot instance |
| `base_frame`, `odom_frame`, `sensors` | robot's `caps/mobile.yaml` (forwarded by `ModelParams` accessors) |
| `use_sim_time`, `task_generator_node` | task_generator runtime |
| `tf_buffer`, `node_handle` | shared rclpy resources |

Only `launch_description` is required. The other hooks default to no-op or
"defer to default"; a pure goal-publisher adapter (see `NoneAdapter`) can
leave most of them alone. `republishes_goal` controls whether
`RobotManager`'s goal_pose republish loop runs — set it `False` when your
adapter owns goal transport (action client, etc.) to avoid racing.

## Registration and lookup

`@register_adapter` records the class under its `kind` string in a module-level
dict. `get_adapter(kind)` is the only public lookup; importing the adapter
module (eagerly done by task_generator at startup) is what triggers
registration.

## Adding a new adapter

1. Create `arena_robots/arena_robots/launch/adapters/<kind>.launch.py` — a
   standard `generate_launch_description()` that brings up your navstack
   parametrised by the launch args your Python class passes (see
   `nav2.launch.py` for the full pattern with YAML merging and per-sensor
   costmap derivations).
2. Create `task_generator/task_generator/tasks/robots/adapters/<kind>.py`
   with a class inheriting `Adapter`, decorated with `@register_adapter`.
   Implement `launch_description` (return `IncludeLaunchDescription` pointing
   at your launch file) and whichever of `dispatch_phase` /
   `is_phase_done` / `wait_until_ready` your navstack needs.
3. Set `navigator: <kind>` in a robot's `model_params.yaml` (or pass via
   launch/CLI) and verify the new kind shows up in `get_adapter`'s error
   message by forcing a lookup.
