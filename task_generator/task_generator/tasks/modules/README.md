# task_generator modules

`TM_Module` and its shipped subclasses. Modules run cross-cutting logic before
and after every episode reset without owning the robot or obstacle axes.

## `TM_Module` ABC

[`__init__.py:8`](__init__.py#L8)

```python
class TM_Module(TaskMode):
    _task: "Task"

    def before_reset(self): ...
    def after_reset(self): ...
```

Both hooks default to no-ops. Subclasses override only the ones they need.
`_task` is the live `Task` instance, giving modules access to
`world_manager`, `robots_manager`, and `force_reset()`.

Modules are instantiated in `Task.__init__` from the `tm_modules` ROS param
(a comma-separated list of `Constants.TaskMode.TM_Module` values). Each is
registered in `_TaskRegistry.registry_module` by
[`tasks/registry.py`](../registry.py).

## Shipped modules

| Enum value | Class | File | `before_reset` | `after_reset` |
| --- | --- | --- | --- | --- |
| `benchmark` | `Mod_Benchmark` | [`benchmark.py`](benchmark.py) | advances suite/contest stage; sets `tm_robots`, `tm_obstacles`, world params for the next stage | counts episode; triggers stage advance when episode limit reached |
| `clear_forbidden_zones` | `Mod_ClearForbiddenZones` | [`clear_forbidden_zones.py`](clear_forbidden_zones.py) | calls `world_manager.forbid_clear()` | — |
| `rviz_ui` | `Mod_OverrideRobot` | [`rviz_ui.py`](rviz_ui.py) | — | — |
| `staged` | `Mod_Staged` | [`staged.py`](staged.py) | loads new stage config when stage index changes; publishes `goal_radius` and obstacle counts | — |

### `Mod_Benchmark`

[`benchmark.py:185`](benchmark.py#L185)

Drives a multi-stage benchmark: loads `arena_bringup/configs/benchmark/config.yaml`,
parses a `Suite` (stages with `tm_robots`, `tm_obstacles`, map, seed, timeout)
and a `Contest` (contestants with planner configs). `before_reset` calls
`_reincarnate` when `needs_reincarnation` is set, which updates ROS params
for the next stage via `node.conf.TaskMode.*` setters and triggers a task
reset. `after_reset` increments the episode index and marks reincarnation
when the episode limit is hit.

### `Mod_ClearForbiddenZones`

[`clear_forbidden_zones.py:4`](clear_forbidden_zones.py#L4)

Clears all dynamically forbidden map cells before each reset so obstacles
from the previous episode do not pollute free-cell sampling.

### `Mod_OverrideRobot`

[`rviz_ui.py:8`](rviz_ui.py#L8)

Subscribes to `/initialpose` (`PoseWithCovarianceStamped`), `/goal_pose`
(`PoseStamped`), and `/clicked_point` (`PointStamped`). Forwards set-position
and set-goal calls to `Task.set_robot_position` / `set_robot_goal`; a clicked
point calls `task.force_reset()`. Provides interactive RViz-based control
without modifying the active task mode.

### `Mod_Staged`

[`staged.py:44`](staged.py#L44)

Reads a curriculum YAML (list of stages, each with `static`, `interactive`,
`dynamic`, `goal_radius`, and optional `dynamic_map` fields). Stage index is
advanced via `next_stage` / `previous_stage` ROS topics. `before_reset`
publishes the stage's `goal_radius` and obstacle counts as ROS params when
the stage index changes.

## Adding a module

1. Create `tasks/modules/<name>.py` with a class extending `TM_Module`; override
   `before_reset` and/or `after_reset`.
2. Add `<NAME> = "<name>"` to `Constants.TaskMode.TM_Module` in
   [`constants/__init__.py`](../../constants/__init__.py).
3. Register a lazy loader in [`tasks/registry.py`](../registry.py):

```python
@_TaskRegistry.register_module(Constants.TaskMode.TM_Module.MY_MODULE)
def _my_module():
    from .modules.my_module import Mod_MyModule
    return Mod_MyModule
```
