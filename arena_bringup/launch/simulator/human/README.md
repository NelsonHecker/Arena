# Human simulator dispatch

Entry point: [`human.launch.py`](human.launch.py).

Called from `arena.launch.py` (once per environment) with `simulator` (the
human-sim key) and `namespace`. Its job is to select and delegate to one
human-simulation backend.

## SelectAction dispatch

The selector expression is `LaunchConfiguration('simulator')`. Registered
keys:

```
simulator key  →  action
──────────────────────────────────────────────────────────────────
dummy          →  empty GroupAction (no nodes)
isaac          →  empty GroupAction (no nodes)
hunav          →  hunav/hunav.launch.py
```

The `simulator` `LaunchArgument` is declared after the `SelectAction` is
built; its `choices` are derived from `launch_human_simulator.keys`.

The `human` arg from `arena.launch.py` (not the `sim` arg) is passed
here as `simulator`. The mapping is:
- `sim=dummy` → `human=dummy`
- `sim=gazebo` → `human=hunav`
- `sim=isaac` → `human=hunav`

This is computed by `PythonExpression` in `arena.launch.py` and can be
overridden explicitly with `human:=<key>`.

## Per-human-sim subdir layout

```
launch/simulator/human/
├── human.launch.py        — dispatcher
└── hunav/
    └── hunav.launch.py    — hunav_agent_manager node
```

### hunav/hunav.launch.py

Starts `hunav_agent_manager/arena_hunav_agent_manager` in the given namespace.

| Arg | Default | Meaning |
|---|---|---|
| `use_sim_time` | `true` | Passed to the node as a bool parameter |
| `namespace` | (required) | ROS namespace for the agent manager node |
| `world_file` | `` (empty) | Passed through; callers may provide a world SDF path |

## Adding a new human simulator

1. Create `launch/simulator/human/<name>/<name>.launch.py`.
2. In `human.launch.py`, call
   `launch_human_simulator.add("<name>", IncludeLaunchDescription(...))`.
3. Update the `human` default expression in `arena.launch.py` to map the
   appropriate `sim` values to the new key.
