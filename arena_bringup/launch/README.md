# arena_bringup launch

Entry point: [`arena.launch.py`](arena.launch.py).

## Arguments

All arguments are declared with `LaunchArgument` (a thin wrapper around
`DeclareLaunchArgument` that also auto-appends to the description list and
exposes `.substitution` / `.dict` / `.param`).

| Name | Type / choices | Default | Meaning |
|---|---|---|---|
| `log_level` | level / `{glob:lvl,…,default}` / yaml path | `warn` | Per-node log level via `NodeLogLevelExtension`. See [Log level](#log-level) below. |
| `robot` | string | `jackal` | Robot model; must match a directory under `arena_robots/robots/` |
| `inter_planner` | string | `navigate_w_replanning_time` | Behavior-Tree inter-planner (nav2) |
| `local_planner` | string | `dwb` | Local planner (`teb`, `dwa`, `mpc`, `rlca`, `arena`, `rosnav`, `cohan`, …) |
| `global_planner` | string | `navfn` | Global planner |
| `sim` | string | `dummy` | Physics simulator: `dummy`, `gazebo`, or `isaac` |
| `navigator` | string | `none` for `dummy`, `nav2` otherwise | Nav-stack adapter kind; per-robot `navigator:` in `robot_setup.yaml` wins |
| `headless` | `-1`\|`0`\|`1`\|`2` | `0` | `-1` show all, `0` show all, `1` rviz only, `2` nothing |
| `human` | string | `dummy` for `dummy` sim, `hunav` for `gazebo`/`isaac` | Human-simulator backend |
| `complexity` | string | `1` | `1` map+position known; `2` map known AMCL; `3` SLAM |
| `agent_name` | string | value of `robot` | DRL agent name |
| `record_data_dir` | string | `` (empty) | Directory for data recording; empty disables |
| `tm_robots` | string | `explore` | Robot task mode (legacy single-kind shorthand) |
| `task_config` | string | `` (empty) | Path to a [TaskModeSpec YAML](../configs/tasks/README.md); empty → synthesize from `tm_robots` (wins if both set) |
| `tm_obstacles` | string | `random` | Obstacle task mode |
| `tm_modules` | string | `rviz_ui` | Comma-separated task modules to load |
| `world` | string | `map_empty` | World name; resolved under `arena_simulation_setup/worlds/` |
| `use_sim_time` | bool string | `true` | Use sim clock instead of wall clock |
| `env_n` | int string | `1` | Number of parallel task-generator environments |
| `env_d` | float string | `50` | Spacing (metres) between environments on the snail grid |
| `debug` | bool string | `False` | Enable debug features |
| `train_config` | string | `` (empty) | Path to RL training config YAML; non-empty forces `auto_reset=false` and starts `train_agent.py` |
| `auto_reset` | bool expression | `true` (or `false` when `train_config` set) | `true` = standalone: node auto-advances episodes; `false` = managed: external controller drives resets via `lifecycle/reset_episode` |

## Simulator dispatch

- [simulator/sim/README.md](simulator/sim/README.md) — physics simulator backends (`dummy`, `gazebo`, `isaac`).
- [simulator/human/README.md](simulator/human/README.md) — human-simulation backends (`dummy`, `hunav`).

## Top-level composition

`generate_launch_description()` assembles the following in order:

1. **`SetGlobalLogLevelAction`** — stores `log_level` in the launch context so
   `NodeLogLevelExtension` can inject `--log-level` into every subsequent `Node`
   action.
2. **`OpaqueFunction` → `create_task_generators`** — resolves `env_n` and
   `env_d` at launch time, then spawns one `IsolatedGroupAction` per
   environment. Each group contains:
   - `human.launch.py` — starts the human simulator (if any) for that
     environment.
   - `task_generator.launch.py` — starts the task-generator node with all
     forwarded args plus `namespace`, `reference`, and `prefix`.
3. **`IsolatedGroupAction` → `sim.launch.py`** — the physics simulator
   (shared across all environments).
4. **`world_generator`** node (`arena_simulation_setup`) — generates world
   assets.
5. **`train_agent.py`** (conditional) — started only when `train_config` is
   non-empty.

Environments are positioned on a *snail grid* (`snail_grid(d)`) that spirals
outward from the origin with spacing `d`, so multiple parallel environments do
not overlap.

The simulator is paused during setup and the entire `Task._reset_episode` body —
see [Sim-paused invariant](../../task_generator/task_generator/simulators/sim/README.md#sim-paused-invariant).

## utils/

| File | Purpose |
|---|---|
| [`utils/fake_localization.launch.py`](utils/fake_localization.launch.py) | Publishes a static `map → odom` TF (zero transform). Args: `global_frame_id` (default `map`), `odom_frame_id` (default `odom`). Used for `complexity=1` (position known). |
| [`utils/map_server.launch.py`](utils/map_server.launch.py) | Starts `nav2_map_server` with `nav2_lifecycle_manager` (autostart, `bond_timeout=0`). No launch args — callers remap parameters directly. |
