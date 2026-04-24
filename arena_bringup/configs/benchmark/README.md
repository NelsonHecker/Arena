# Benchmark configs

`Mod_Benchmark` ([task_generator/task_generator/tasks/modules/benchmark.py:185](../../../task_generator/task_generator/tasks/modules/benchmark.py#L185))
reads all benchmark configuration from
`arena_bringup/configs/benchmark/` at module-init time.

## Directory layout

```
configs/benchmark/
├── config.yaml       — top-level pointer: which suite and contest to run
├── suites/           — stage sequences (maps, episodes, task modes)
│   ├── basic.yaml
│   ├── meta_suite.yaml
│   ├── all_maps_random.yaml
│   ├── arena_corridor.yaml
│   ├── arena_hospital_small.yaml
│   └── map_empty.yaml
└── contests/         — planner lineups
    ├── basic.yaml
    ├── allplanners.yaml
    ├── inter.yaml
    └── planners.yaml
```

## config.yaml

Selects the active suite and contest for a benchmark run.

```yaml
contest:
  config: basic.yaml        # filename under contests/
general:
  simulator: gazebo         # simulator to use
suite:
  config: meta_suite.yaml   # filename under suites/
  scale_episodes: 1         # multiplier applied to each stage's episode count
```

`Mod_Benchmark._load_config()` reads this file at init and constructs a
`_Config` named tuple with `suite`, `contest`, and `general` sub-structs.

## Suite files

A suite is an ordered list of stages. `Mod_Benchmark` steps through the
stages sequentially, cycling through all contestants at each stage.

```yaml
stages:
  - name: scenario            # human-readable label (used in log output)
    map: arena_hospital_small # world/map name
    robot: jackal             # robot model
    tm_robots: scenario       # TM_Robots kind (string, upper-cased to enum key)
    tm_obstacles: random      # TM_Obstacles kind
    episodes: 1               # number of episodes at this stage
    config:                   # passed to task modes / scenario loader
      SCENARIO:
        file: 4.json
      RANDOM:
        dynamic:  {min: 3, max: 5, models: [arenian]}
        static:   {min: 5, max: 10, models: [shelf]}
        interactive: {min: 0, max: 0, models: [shelf]}
```

### Stage fields

| Field | Type | Meaning |
|---|---|---|
| `name` | string | Stage label |
| `map` | string | World name (sets `Arena.WORLD` param on the task-generator node) |
| `robot` | string | Robot model |
| `tm_robots` | string | `Constants.TaskMode.TM_Robots` enum key (case-insensitive) |
| `tm_obstacles` | string | `Constants.TaskMode.TM_Obstacles` enum key (case-insensitive) |
| `episodes` | int | Episode count (scaled by `suite.scale_episodes` from `config.yaml`) |
| `config` | dict | Arbitrary config forwarded to the task modes; `SCENARIO.file` sets `task.scenario.file` ROS param |
| `seed` | int | Auto-derived from a SHA-1 hash of the stage fields (excluding `config`); can be set explicitly |
| `timeout` | string | Per-episode timeout; defaults to `Constants.Robot.TIMEOUT` if absent |

## Contest files

A contest defines the set of planner configurations (contestants) to evaluate.
`Mod_Benchmark` iterates over all contestants at each suite stage.

```yaml
contestants:
  - name: teb                              # label for logs and output
    local_planner: teb
    inter_planner: navigate_w_replanning_time
    agent_name: ""                         # optional DRL agent name
```

### Contestant fields

| Field | Type | Default | Meaning |
|---|---|---|---|
| `name` | string | — | Label |
| `local_planner` | string | — | Local planner ID |
| `inter_planner` | string | `navigate_w_replanning_time` | Behavior-tree inter-planner |
| `agent_name` | string | `""` | DRL agent name (empty = not used) |

## How Mod_Benchmark ingests these files

`Mod_Benchmark` ([benchmark.py:185](../../../task_generator/task_generator/tasks/modules/benchmark.py#L185))
is a `TM_Module` subclass. At initialisation it:

1. Calls `_load_config()` — reads `config.yaml`.
2. Calls `_load_suite(config.suite.config, config_class)` — parses the
   selected suite file into a `Suite` named tuple; each stage becomes a
   `Suite.Stage` with enums resolved.
3. Calls `_load_contest(config.contest.config)` — parses the selected contest
   file into a `Contest` named tuple.
4. On each episode reset, calls `_set_node_parameters(stage)` to push the
   current stage's `tm_robots`, `tm_obstacles`, `map`, and `task.scenario.file`
   params to the task-generator node via `SetParameters` service.
5. Advances through the `(suite_index, contest_index)` grid, writing a
   `resume.lock` file so an interrupted run can be resumed.

Logs are written to `configs/benchmark/logs/`.
