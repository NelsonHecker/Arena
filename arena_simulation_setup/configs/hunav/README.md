# HuNav configs

This directory contains two distinct things used by the HuNav human simulator:

1. `default.yaml` — default agent template loaded at module init.
2. `behavior_trees/` — shared BTCPP v4 XML behavior tree library.

## `default.yaml` — default agent template

`HunavDynamicObstacle._default` is populated by
`_load_config()` in
[task_generator/simulators/human/hunav/__init__.py:264](../../../task_generator/task_generator/simulators/human/hunav/__init__.py#L264),
which reads `<arena_simulation_setup share>/configs/hunav/default.yaml` at
module import time.

The file sets the default field values for every `HunavDynamicObstacle` that
does not override them explicitly:

```yaml
id: 1
group_id: -1
skin: 0
max_vel: 0.8
radius: 0.3
goal_radius: 2.0
cyclic_goals: true
init_pose:
  x: 0.0
  y: 0.0
  z: 1.250        # spawn height in Gazebo
  h: 0.0
behavior:
  type: 1         # hunav_msgs::msg::BEH_REGULAR
  configuration: 0
  goal_force_factor: 5.0
  obstacle_force_factor: 20.0
  social_force_factor: 20.0
  other_force_factor: 20.0
```

`HunavDynamicObstacle.Behavior._default` is then set from `_default.behavior`
([task_generator/simulators/human/hunav/__init__.py:327](../../../task_generator/task_generator/simulators/human/hunav/__init__.py#L327)).

## `behavior_trees/` — BT library

Shared BTCPP v4 XML files defining reusable pedestrian behaviors. These files
are referenced by name from scenario `behavior_tree:` fields and from
per-agent `hunav_<N>_behavior_tree.xml` files in scenario directories.

| File | Behavior |
|---|---|
| `BTRegularNav.xml` | Standard goal-directed navigation |
| `BTCuriousNav.xml` | Curious pedestrian; deviates toward the robot |
| `BTScaredNav.xml` | Scared pedestrian; avoids the robot |
| `BTSurprisedNav.xml` | Surprised pedestrian; brief stop then reroutes |
| `BTThreateningNav.xml` | Threatening pedestrian; approaches the robot |
| `default.xml` | Alias used as the fallback in `HunavDynamicObstacle._default.behavior_tree` |

Per-scenario BT files (`hunav_<N>_behavior_tree.xml` in a scenario directory)
are instance-specific overrides that can reference or extend these shared trees.
The `behavior_tree` field in `scenario.yaml` accepts a path relative to the
scenario directory (e.g. `./hunav_1_behavior_tree.xml`) or a name from this
library (e.g. `BTRegularNav.xml`).
