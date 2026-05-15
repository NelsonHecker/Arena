# Simulator dispatch

Entry point: [`sim.launch.py`](sim.launch.py).

Called from `arena_runtime.launch.py` with `simulator`, `use_sim_time`, `world`, and
`headless`. Its sole job is to select and delegate to one simulator backend.

## SelectAction dispatch

`SelectAction` is a key→action registry resolved at launch time. The selector
expression is `LaunchConfiguration('simulator')`. Each registered key maps to
a `GroupAction` or `IncludeLaunchDescription`.

```
simulator key  →  action
──────────────────────────────────────────────────────────────────
dummy          →  static_transform_publisher (map → dummy TF only)
gazebo         →  gazebo/gazebo.launch.py
isaac          →  isaac/isaac.launch.py
```

The `simulator` `LaunchArgument` is declared *after* the `SelectAction` is
built so that `choices` can be derived from `launch_simulator.keys` — the
keys registered above. Passing an unregistered value causes a launch-time
validation error.

## Per-sim subdir layout

```
launch/simulator/sim/
├── sim.launch.py          — dispatcher (this file's parent)
├── gazebo/
│   └── gazebo.launch.py   — gz-sim 8 bringup + clock bridge
└── isaac/
    └── isaac.launch.py    — delegates to `arena feature isaac launch`
```

### gazebo/gazebo.launch.py

- Stages models via `arena_simulation_setup model_staging` at Python-load time.
- Sets `GZ_SIM_RESOURCE_PATH` and `GAZEBO_MODEL_PATH` from the staging
  directory plus `arena_robots` and any declared deps.
- Resolves the world SDF: looks for
  `arena_simulation_setup/worlds/<world>/worlds/<world>.world`; falls back to
  `arena_bringup/configs/gazebo/empty.sdf` if the file is absent.
- Launches `ros_gz_sim gz_sim.launch.py` (gz-sim 8, dart physics, ogre
  renderer). When `headless=True`, passes `-s` (server-only).
- Starts a `ros_gz_bridge parameter_bridge` for `/clock`.

Forwarded args: `use_sim_time`, `world`, `headless`.

### isaac/isaac.launch.py

- Runs `arena feature isaac launch` via `ExecuteProcess` (bash).
- Triggers `Shutdown` on process exit.
- Forwarded arg: `use_sim_time` (passed via launch arguments; `headless` is
  currently commented out).

## Adding a new simulator

1. Create `launch/simulator/sim/<name>/<name>.launch.py`.
2. In `sim.launch.py`, call `launch_simulator.add("<name>", IncludeLaunchDescription(...))`.
3. The new key appears in `launch_simulator.keys` automatically, so the
   `simulator` argument's `choices` list updates without extra changes.
4. Add the corresponding `Constants.SimSimulator.<NAME>` entry in
   `task_generator/task_generator/constants/__init__.py` if the task-generator
   needs to branch on it.
