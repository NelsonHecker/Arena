# Arena bringup usage

Most Arena sessions start with `arena.launch.py`. It brings up the simulator,
one or more task-generator nodes, and (optionally) a human simulator.
Navigation stacks and robot spawning are handled by
`task_generator.launch.py`, which `arena.launch.py` includes automatically.

For the decoupled flow (runtime stays up, envs come and go),
`arena_runtime.launch.py` brings up just the simulator and the `arena_node`
runtime; clients then attach task-generator envs dynamically via
`task_generator.launch.py`. See [Runtime / client mode](#runtime--client-mode-dynamic-envs)
below.

The full argument surface is in [launch/README.md](launch/README.md).

---

## Minimum-viable invocations

### 1. Smoke check — dummy sim, empty map

No physics engine. Useful for verifying that the ROS graph comes up without
hardware or GPU.

```bash
ros2 launch arena_bringup arena.launch.py \
    sim:=dummy \
    world:=map_empty \
    robot:=jackal \
    tm_robots:=explore \
    tm_obstacles:=random
```

| Arg | Implication |
|---|---|
| `sim:=dummy` | No physics engine; a `map→dummy` static TF is published instead |
| `world:=map_empty` | Loads the empty map from `arena_simulation_setup` |
| `robot:=jackal` | Single jackal; `navigator` defaults to `none` (dummy sim has no nav2) |
| `tm_robots:=explore` | Robot gets fresh random goals continuously |
| `tm_obstacles:=random` | Random static/dynamic obstacles placed each episode |

The `human` arg defaults to `dummy` when `sim=dummy`, so no human simulator
is started.

---

### 2. Gazebo + jackal + random obstacles

```bash
ros2 launch arena_bringup arena.launch.py \
    sim:=gazebo \
    world:=map_empty \
    robot:=jackal \
    local_planner:=teb \
    tm_robots:=explore \
    tm_obstacles:=random
```

| Arg | Implication |
|---|---|
| `sim:=gazebo` | Starts gz-sim 8 (dart physics, ogre renderer). `human` defaults to `hunav` |
| `world:=map_empty` | Resolved to `arena_simulation_setup/worlds/map_empty/worlds/map_empty.world`; falls back to `configs/gazebo/empty.sdf` if absent |
| `local_planner:=teb` | TEB local planner in nav2; `navigator` defaults to `nav2` for gazebo |
| `headless` | Omitted → `0` (GUI visible). Pass `headless:=1` for rviz-only, `headless:=2` for no GUI |

To suppress the HuNavSim agent manager when no human obstacles are needed,
add `human:=dummy` to the command above.

---

### 3. Gazebo + jackal + HuNavSim

```bash
ros2 launch arena_bringup arena.launch.py \
    sim:=gazebo \
    world:=map_empty \
    robot:=jackal \
    human:=hunav \
    tm_robots:=explore \
    tm_obstacles:=random
```

`human:=hunav` starts `hunav_agent_manager` in the task-generator namespace.
Human pedestrian models are managed by the HuNavSim plugin; the
`tm_obstacles` mode controls non-human obstacles separately.

---

### 4. Isaac + multi-robot via task_config

Isaac must be installed and `arena feature isaac` must be set up before launch.

```bash
ros2 launch arena_bringup arena.launch.py \
    sim:=isaac \
    world:=map_empty \
    task_config:=$(ros2 pkg prefix arena_bringup)/share/arena_bringup/configs/tasks/default.yaml \
    tm_obstacles:=random \
    headless:=2
```

| Arg | Implication |
|---|---|
| `sim:=isaac` | Runs `arena feature isaac launch` via bash. `navigator` defaults to `nav2` |
| `task_config:=<path>` | Structured `TaskModeSpec` YAML; overrides `tm_robots`. Use to split a fleet across multiple task modes |
| `headless:=2` | No GUI (server-only mode) |

Multi-robot fleet with two modes:

```bash
cat > /tmp/fleet.yaml << 'EOF'
task_modes:
  - kind: scenario
    produces: GOTO_POSE
    assignments: [jackal_0]
    config: {}
  - kind: explore
    produces: GOTO_POSE
    assignments: []
    config: {}
EOF

ros2 launch arena_bringup arena.launch.py \
    sim:=isaac \
    world:=map_empty \
    robot:=jackal \
    task_config:=/tmp/fleet.yaml \
    tm_obstacles:=random \
    headless:=2
```

`jackal_0` follows a scenario; every other jackal explores. See
[configs/tasks/README.md](configs/tasks/README.md) for the full schema.

---

### 5. Multiple parallel environments

```bash
ros2 launch arena_bringup arena.launch.py \
    sim:=gazebo \
    world:=map_empty \
    robot:=jackal \
    env_n:=3 \
    headless:=1
```

| Arg | Implication |
|---|---|
| `env_n:=3` | Three task-generator instances under `arena/env_0/task_generator_node`, `arena/env_1/...`, `arena/env_2/...`. `arena_node` self-orchestrates the fleet via `/arena/spawn_env`. |
| `headless:=1` | Only rviz is shown (no per-env Gazebo GUIs). `headless:=-1` shows all envs, `0` shows env 0 only, `2` hides everything. |

Slot positions are placed by the shelf packer in `arena_node` based on each env's `WorldExtent`; spacing is governed by the `slot_buffer` ROS parameter on `arena_node` (default 5 m).

---

### 6. Runtime / client mode (dynamic envs)

The runtime (`arena_node`) and the simulator can be launched without any
task-generator envs, then envs can be added or removed at runtime.

```bash
# Runtime: sim + arena_node only, no envs.
ros2 launch arena_bringup arena_runtime.launch.py \
    sim:=gazebo \
    world:=map_empty \
    headless:=1
```

`arena.launch.py env_n:=0` reaches the same state via the all-in-one
launcher; `arena_runtime.launch.py` is the leaner direct entry.

Once the runtime is up, attach an env with `task_generator.launch.py`:

```bash
ros2 launch task_generator task_generator.launch.py \
    robot:=jackal \
    tm_robots:=explore \
    tm_obstacles:=random
```

The env registers with `arena_node` (`/arena/register_env`), is placed on the
shelf-packed grid, and runs its task loop until despawned. See
[arena_runtime/arena_runtime/README.md](../arena_runtime/arena_runtime/README.md)
for the simulator interface and registry primitives.

To tear an env down by id, call the cleanup service (or use
`arena cleanup <env_id>`, see [CLI verbs](#cli-verbs)).

---

### 7. RL training mode

```bash
ros2 launch arena_bringup arena.launch.py \
    sim:=gazebo \
    world:=map_empty \
    robot:=jackal \
    train_config:=/path/to/train_config.yaml
```

When `train_config` is non-empty:
- `auto_reset` is forced `false` — managed mode; the RL training loop drives
  resets via `lifecycle/reset_episode`.
- `train_agent.py` is started automatically with `--config <train_config>`.

---

## Common options

```bash
log_level:=debug     # verbose output from all nodes
use_sim_time:=false  # real-time clock (unusual — only for real robots)
complexity:=2        # AMCL (position unknown); 3 = SLAM
record_data_dir:=/tmp/arena_run  # enable data recording
```

## CLI verbs

`source arena` (from `~/arena_ws`) loads a bash function that wraps the
common entry points. Verbs relevant to bringup:

| Verb | Wraps | Purpose |
|---|---|---|
| `arena launch [args]` | `arena.launch.py` | All-in-one launch (sim + runtime + envs). |
| `arena runtime [args]` | `arena_runtime.launch.py` | Runtime-only launch (sim + `arena_node`, no envs). |
| `arena env [args]` | `task_generator.launch.py` | Attach one task-generator env to a running runtime. |
| `arena cleanup <env_id>` | `/arena/cleanup_namespace` service | Force-clean an env's namespace by id (calls the service for both the `env_<id>_` and `env_<id>/` prefixes, covering gazebo and isaac layouts). |
| `arena train [args]` | `arena_training` feature launcher | RL training entry, see section 7 below. |

`arena launch` and `arena runtime` both kill any prior `task_generator_node`,
`arena_node`, and `world_generator` processes before relaunching.

## Benchmark mode

Benchmark runs use `tm_modules:=benchmark` and are configured through
[configs/benchmark/](configs/benchmark/README.md):

```bash
ros2 launch arena_bringup arena.launch.py \
    sim:=gazebo \
    tm_modules:=benchmark \
    headless:=2
```

`Mod_Benchmark` reads `config.yaml`, selects the active suite and contest,
and drives the task-generator through stages automatically.
