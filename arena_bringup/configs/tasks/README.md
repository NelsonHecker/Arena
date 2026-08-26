# Task mode configs

## Status

Nothing currently loads a YAML file from this directory. `task.config` is
declared as a launch argument in
[`task_generator.launch.py`](../../../task_generator/launch/task_generator.launch.py)
(default empty string) but its value is never read: it is not forwarded to
the task-generator node as a ROS param, and no code converts a YAML file
into `TaskModeSpec` objects. `Task.set_tm_robots_composite`
(in [`tasks/task.py`](../../../task_generator/task_generator/tasks/task.py)),
the only consumer of `TaskModeSpec`, is never called from the launch or CLI
path either. `SCHEMA.yaml` and `default.yaml` in this directory are examples
of the target shape, not runnable configs.

The `TaskModeSpec` schema is documented below for callers that construct
these objects directly in Python and pass them to
`set_tm_robots_composite` (e.g. a custom node). If you are writing a
launch-time task config, use [Selecting task modes](#selecting-task-modes-functional-today)
instead - that path works today.

## Selecting task modes (functional today)

- `task.robots:=<kind>` - single `TM_Robots` kind for every robot in the env. Default `explore`.
- `task.obstacles:=<kind>` - single `TM_Obstacles` kind. Default `random`.
- `task.<mode>.<leaf>:=<value>` - per-mode param override, forwarded verbatim
  as a ROS param at launch time (e.g. `task.scenario.file:=4.json`,
  `task.random.static.n:=[5,10]`). Leaf names match the mode's declared
  schema. The same leaf params can be re-staged at runtime via
  `config/queue_episode` - see
  [tasks/obstacles/README.md](../../../task_generator/task_generator/tasks/obstacles/README.md).

Both lists below are read from the registry
([`tasks/registry.py`](../../../task_generator/task_generator/tasks/registry.py)),
re-enumerate instead of trusting this table to stay current:

```python
import task_generator.tasks.robots, task_generator.tasks.obstacles  # noqa: F401
from task_generator.tasks.registry import ROBOTS_MODES, OBSTACLES_MODES
sorted(k.value for k in ROBOTS_MODES.keys())
sorted(k.value for k in OBSTACLES_MODES.keys())
```

### `task.robots` kinds

| Kind | Meaning |
|---|---|
| `random` | one random reachable goal per robot per episode |
| `explore` | extends `random`, assigns a fresh random goal whenever a robot finishes or times out |
| `guided` | external controller drives the goal sequence |
| `stationary` | robot stays parked at start pose (or an explicit `pos_x`/`pos_y`/`pos_theta`, NaN default = use start pose), no goal dispatch |
| `scenario` | reads `start`/`goal` pairs from the world's scenario YAML (`file` param, default the world's `default` scenario) |
| `demo` | cycles robots through vertices of a regular polygon around a center point, dispatching goto/gesture phases |
| `characterization` | open-loop `cmd_vel` maneuver sweep through the robot's rated envelope, no nav goals |

### `task.obstacles` kinds

| Kind | Meaning |
|---|---|
| `random` | samples static/dynamic/interactive obstacles from model pools. `static.n`/`dynamic.n`/`interactive.n` are `[min, max]` counts (defaults `[5,15]`/`[1,5]`/`[0,0]`), `static.models`/`dynamic.models`/`interactive.models` are catalog name lists (default = all) |
| `parametrized` | loads a named `ParametrizedConfig` from `arena_simulation_setup` (`file` param, default empty). min/max counts per entry live in that file |
| `scenario` | reads `static`/`dynamic` obstacle lists from the world's scenario YAML (`file` param, default the world's `default` scenario) |
| `environment` | places obstacle groups from an environment config into detected/declared rooms (`file` param, default `default`) |
| `prompt` | LLM-driven obstacle generation, only registered once a `BaseHumanSimulator` is constructed (`human:=hunav` or `human:=arena`) |

## `TaskModeSpec` schema

Defined in [`fleet_manager.py`](../../../task_generator/task_generator/tasks/robots/fleet_manager.py),
shaped like [`SCHEMA.yaml`](SCHEMA.yaml):

```yaml
task_modes:
  - kind: STRING          # TM_Robots kind - matches Constants.TaskMode.TM_Robots enum value
    produces: GOTO_POSE   # task kind produced; matched against robot.accepts
    assignments:          # list of robot names to pin; [] means pool (greedy allocation)
      - ROBOT_NAME
    config: {}            # arbitrary dict, unused by FleetManager itself
```

Each entry is a `TaskModeSpec`. `set_tm_robots_composite` processes the list
in order (specs earlier in the list get priority during pool allocation).

### Fields

| Field | Type | Required | Meaning |
|---|---|---|---|
| `kind` | string | yes | TM_Robots subclass key (see [`task.robots` kinds](#taskrobots-kinds) above) or the sentinel `null` |
| `produces` | `TaskKind` member, or a list/`frozenset` of members | no | Task kind(s) this mode emits (default `GOTO_POSE`). Must be a subset of the target robot's `accepts` set. Valid members: `GOTO_POSE` (cap `mobile`), `REACH_POSE` (cap `arm`), `PLAY_GESTURE` (cap `arm`). Pass an actual `TaskKind` member when constructing `TaskModeSpec` in Python. The attrs converter treats any other string as an iterable of characters, not a single kind |
| `assignments` | list[string] | no | Pin specific robots by name. Empty list = pool (first-fit) |
| `config` | dict | no | Stored on the spec but not read by `FleetManager` or `set_tm_robots_composite` |

## Allocation rules

See [task_generator/task_generator/tasks/robots/README.md](../../../task_generator/task_generator/tasks/robots/README.md#fleet-manager)
for the full description. Summary:

1. **Pinned first** - robots named in `assignments` are bound to that spec.
   Their `accepts` must include the spec's `produces`. Duplicate pins are an
   error.
2. **Pool next** - unpinned robots join the first unpinned spec whose
   `produces` is a subset of their `accepts`. Greedy / first-fit.
3. **Null sink** - a spec with `kind: null` absorbs all still-unallocated
   robots.

## Shipped files

| File | Description |
|---|---|
| [`SCHEMA.yaml`](SCHEMA.yaml) | `TaskModeSpec` shape - not a runnable config |
| [`default.yaml`](default.yaml) | Example single-`explore`-mode, pool-allocation shape - not a runnable config |
