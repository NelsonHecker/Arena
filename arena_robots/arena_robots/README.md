# arena_robots

ROS2 package containing per-robot configuration trees and Python wrappers used by the Arena task generator and simulators to discover and load robots.

## Package layout

```
arena_robots/
├── arena_robots/                # Python package (resolvers + views)
│   ├── __init__.py              # exposes ARENA_ROBOTS_DIR
│   ├── Robot.py                 # ModelParams, RobotView, RobotIdentifier
│   └── SetupFile.py             # Config, RobotSetupResolver, RobotSetupIdentifier
├── robots/<name>/               # one directory per robot
│   ├── model_params.yaml        # required: nav2 params, frames, footprint, sources
│   ├── control.yaml             # required: controller config (top-level mapping)
│   ├── mappings.yaml            # required: topic / frame remappings
│   ├── urdf/                    # required: <name>.urdf or <name>.urdf.xacro
│   └── ...                      # optional: launch/, meshes/, simulators/, ...
├── config/setup/<name>.yaml     # robot setup lists (see below)
└── package.xml
```

All 14 current robots (`boxer`, `dingo`, `husky`, `jackal`, `rbkairos`, `rbrobout`, `rbsummit`, `rbtheron`, `rbvogui`, `ridgeback`, `rskomnidirectional`, `turtlebot`, `WLP311D`, `WLP311E`) follow this layout.

## Resolution flow

Two `Identifier` types from `arena_simulation_setup.tree` provide the entry points:

- **`RobotIdentifier`** ([Robot.py:82-89](arena_robots/Robot.py#L82-L89)) — looks up a single robot by name. A `SimplePathResolver` is registered against `get_package_share_path('arena_robots') / 'robots'`, so `RobotIdentifier('turtlebot')` resolves to `robots/turtlebot/` and `.load()` returns a `RobotView`.
- **`RobotSetupIdentifier`** ([SetupFile.py:49-59](arena_robots/SetupFile.py#L49-L59)) — looks up a robot setup list by name. `RobotSetupResolver.base_path` is `ARENA_ROBOTS_DIR / 'config' / 'setup'`, so `RobotSetupIdentifier('demo')` reads `config/setup/demo.yaml` and yields a `list[Config]`.

## `RobotView`

Lazy view over a robot directory. Properties:

| Property        | Returns                | Source file              |
|-----------------|------------------------|--------------------------|
| `model_params`  | `ModelParams` (cached) | `model_params.yaml`      |
| `control`       | `dict`                 | `control.yaml`           |
| `mappings`      | `str` (path only)      | `mappings.yaml`          |
| `model`         | `ModelWrapper`         | `urdf/` and/or USD files |

`model` registers loaders for both `ModelType.URDF` and `ModelType.USD`. Consumers ask `ModelWrapper.get(only=ModelType.URDF)` or `only=ModelType.USD` to pick a format; loaders are lazy, so registering a USD loader on a URDF-only robot is free until something asks for USD.

Missing `model_params.yaml` or `control.yaml` raises `FileNotFoundError` with the robot name in the message.

## `ModelParams`

`ModelParams` is a `dict[str, Any]` subclass — intentionally a pass-through bag for arbitrary nav2 keys. Consumers downstream forward keys to nav2 costmaps, collision monitor, controllers, etc.

Three well-known keys are surfaced as properties (with defaults):

| Property      | YAML key            | Default       |
|---------------|---------------------|---------------|
| `base_frame`  | `robot_base_frame`  | `'base_link'` |
| `odom_frame`  | `robot_odom_frame`  | `'odom'`      |
| `z_offset`    | `z_offset`          | `0.0`         |

Any other key is read directly from the dict (e.g. `params['robot_radius']`).

## `robot_setup.yaml` schema

A robot setup file is a YAML list. Each entry is either a string (shorthand) or a dict parsed by [`Config.parse`](arena_robots/SetupFile.py#L28-L36). Entries expand into one or more `Config` instances.

**Shorthand** — single robot of that type, name = robot name:

```yaml
- jackal
- turtlebot
```

**Dict form** — full control:

```yaml
- robot: jackal        # required: directory name under robots/
  name: jackal_lead    # optional: instance name / prefix (default: omitted)
  count: 3             # optional: spawn N copies (default: 1)
  planner: SmacPlanner # optional: nav2 planner override
  controller: MPPI     # optional: nav2 controller override
  behavior: default    # optional: nav2 behavior tree override
  extra:               # optional: arbitrary pass-through dict
    foo: bar
```

When `count > 1` the entry expands to `count` identical `Config` objects. The `count` key is consumed during parsing and never appears on the resulting `Config`.

Existing examples:

- [config/setup/demo.yaml](config/setup/demo.yaml) — three jackals via `count`.
- [config/setup/all_robots.yaml](config/setup/all_robots.yaml) — one of each robot using shorthand.

## Dependencies

`arena_robots` depends on `arena_simulation_setup` at runtime only — declared via `<exec_depend>` in [package.xml](package.xml), which is the correct ROS2 tag for a Python-only runtime dep.
