# Navigation adapters (Python half)

Companion to [`arena_robots/launch/adapters/README.md`](../../../../../arena_robots/arena_robots/launch/adapters/README.md).
Every navigation adapter has two halves:

| Half | Lives in | Role |
| --- | --- | --- |
| **Launch file** | `arena_robots/arena_robots/launch/adapters/<kind>.launch.py` | spawns the navstack's ROS nodes for one robot |
| **Python class** | `task_generator/task_generator/tasks/robots/adapters/<kind>.py` | implements the `Adapter` ABC — dispatches goals, polls completion, etc. |

This dir owns the Python half. Existing kinds:

- [`nav2.py`](nav2.py) → `Nav2Adapter` — `NavigateToPose` action client, handles
  lifecycle waits, rejection retries, resubmit on ABORTED, local-costmap clear
  on teleport.
- [`none.py`](none.py) → `NoneAdapter` — publishes `goal_pose` and does no
  further dispatch. Pairs with `none.launch.py` (no navstack).
- [`external.py`](external.py) → `ExternalAdapter` — like `none` but the goal
  topic, `cmd_vel` topic, launch file, and required caps are all configurable
  from the robot's `capabilities` entry. For third-party planners that Arena
  does not own.

## The `Adapter` ABC

Defined in [`__init__.py`](__init__.py). A subclass declares three class-level
identity fields and implements the lifecycle hooks it cares about:

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

Only `launch_description` is required. The other hooks default to no-op or
"defer to default" — a pure goal-publisher adapter can leave most of them
alone.

### `AdapterCtx`

Immutable config snapshot handed to `launch_description`:

| Field | Source |
| --- | --- |
| `namespace`, `robot_name`, `frame` | robot instance |
| `base_frame`, `odom_frame`, `sensors` | robot's `model_params.yaml` |
| `use_sim_time`, `task_generator_node` | task_generator runtime |
| `tf_buffer`, `node_handle` | shared rclpy resources |

### `republishes_goal`

`RobotManager` runs a loop that republishes `_goal_pos` to `goal_pose` to
cover AMCL jitter and the gap before nav2 is subscribed. Set
`republishes_goal = False` when your adapter owns goal transport (e.g.
`NavigateToPose` action client) — otherwise the loop races your dispatch.

## Registration and lookup

`@register_adapter` records the class under its `kind` string in a
module-level dict. `get_adapter(kind)` is the only public lookup.

Registration is side-effect: importing `task_generator.tasks.robots.adapters.<kind>`
triggers `@register_adapter`. [`RobotManager`](../../../manager/robot_manager/robot_manager.py)
eagerly imports `nav2`, `none`, and `external` at construction time so
`get_adapter` can resolve any shipped kind.

## How `RobotManager` binds an adapter

In [`RobotManager.__init__`](../../../manager/robot_manager/robot_manager.py):

1. **Select the kind.** Precedence: `robot.navigator` (set from robot_setup
   YAML / CLI) > `model_params.navigator` (model default).
2. **Resolve the class.** `get_adapter(kind)`.
3. **Derive kwargs.** If `model_params.capabilities` has exactly one entry
   with `kind: <chosen>`, its remaining keys flow as kwargs to the adapter
   constructor. Multiple entries for the same kind → error. Entries for
   other kinds are logged but unused (multi-capability composition is TODO).
4. **For nav2 specifically**, fill defaults for `global_planner`,
   `local_planner`, `inter_planner`, `train_mode` from the `Robot` runtime
   config when the capabilities entry does not override them.
5. **Instantiate.** `adapter_cls(**adapter_kwargs)` — `TypeError` here becomes
   an assertion with the offending kwargs in the message.
6. **Cap check.** `adapter.requires - model_params.actuator_caps` must be
   empty; otherwise abort with a diagnostic listing both sides.
7. **Build dispatch table.** `self._adapters = {k: adapter for k in adapter.accepts}`
   so multiple `TaskKind`s can share one adapter instance.

## Dispatch flow

`submit_task(request)` on `RobotManager`:

1. Validate: every phase's `kind` is in `self._adapters`.
2. Store request, set `_phase_index = 0`.
3. Call `adapter.dispatch_phase(phase0, self)`.
4. Start/stop `_publish_goal_loop` based on `adapter.republishes_goal`.

Completion is polled by `is_done`, which runs a three-tier check:

1. **Tier 1** — `request.done_predicate(robot, phase)` if the request set one.
2. **Tier 2** — `adapter.is_phase_done(phase, robot)`.
3. **Tier 3** — `phase.is_satisfied(robot)` (pose-within-tolerance default).

First non-`None` verdict wins. On `True` the phase index advances and the
next phase is dispatched; on the last phase, `is_done` returns `True`.

`move(pose)` teleports and then calls `adapter.on_move(pose, robot)` — nav2
uses this hook to clear its local costmap so stale obstacle data around the
old pose does not block planning from the new one.

## Adding a new adapter

1. Create `arena_robots/arena_robots/launch/adapters/<kind>.launch.py` — a
   standard `generate_launch_description()` parametrised by the launch args
   your Python class passes. See `nav2.launch.py` for the full pattern with
   YAML merging and per-sensor costmap derivations.
2. Create `task_generator/task_generator/tasks/robots/adapters/<kind>.py`:

   ```python
   @register_adapter
   class MyAdapter(Adapter):
       kind = "my_stack"
       requires = frozenset({"mobile"})
       accepts  = frozenset({TaskKind.GOTO_POSE})

       def launch_description(self, ctx: AdapterCtx):
           return launch.actions.IncludeLaunchDescription(
               launch.launch_description_sources.PythonLaunchDescriptionSource(
                   launch.substitutions.PathJoinSubstitution([
                       FindPackageShare("arena_robots"),
                       "launch", "adapters", "my_stack.launch.py",
                   ])
               ),
               launch_arguments=[...],
           )

       async def dispatch_phase(self, phase, robot) -> None: ...
       def     is_phase_done(self, phase, robot) -> bool | None: ...
   ```

3. Eager-import the module from [`RobotManager.__init__`](../../../manager/robot_manager/robot_manager.py)
   so the registration side-effect fires before `get_adapter(kind)` runs.
4. Set `navigator: <kind>` in a robot's `model_params.yaml`, or pass via
   robot_setup / CLI. Verify resolution by forcing a `get_adapter(kind)`
   lookup.
