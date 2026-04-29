# Arena bringup usage

All Arena sessions start with `arena.launch.py`. It brings up the simulator,
one or more task-generator nodes, and (optionally) a human simulator.
Navigation stacks and robot spawning are handled by
`task_generator.launch.py`, which `arena.launch.py` includes automatically.

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
    env_d:=60 \
    headless:=1
```

| Arg | Implication |
|---|---|
| `env_n:=3` | Three task-generator instances under `task_generator_node/env0`, `.../env1`, `.../env2` |
| `env_d:=60` | 60 m spacing between environments on the snail grid |
| `headless:=1` | Only rviz is shown (no per-env Gazebo GUIs) |

---

### 6. RL training mode

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
