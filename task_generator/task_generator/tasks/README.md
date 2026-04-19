# task_generator tasks

Core abstractions for the episode loop: the `Task` orchestrator, `TaskMode`
base, `TaskContext` dependency bundle, and the `_TaskRegistry` that wires
everything together.

## Key types

### `Task`

[`task.py:33`](task.py#L33)

The top-level orchestrator. Combines one `TM_Robots`, one `TM_Obstacles`, and
zero-or-more `TM_Module` instances into a single episode loop. Entry points:

| Method | Purpose |
| --- | --- |
| `Task.create(...)` | async factory; calls `robots_manager.set_up()` before returning |
| `reset(**kwargs)` | run one full episode reset (see sequence below) |
| `set_tm_robots(enum)` | swap the active `TM_Robots` mode |
| `set_tm_robots_composite(specs)` | bind a multi-TM composite via `FleetManager` |
| `set_tm_obstacles(enum)` | swap the active `TM_Obstacles` mode |
| `is_done` | async property; `True` when `tm_robots.done` or `force_reset()` called |
| `force_reset()` | set the force-reset flag so the next `is_done` poll returns `True` |
| `submit_task(request, robot_name)` | bypass `TM_Robots` and submit directly to one robot |

Published ROS topics: `reset_start` and `reset_end` (`std_msgs/Empty`).
ROS parameter `resetting` (`bool`) is declared via `declare_parameters`.

### `TaskMode`

[`mode.py:14`](mode.py#L14)

Abstract base for all three axes. Provides `_ctx: TaskContext`,
`_namespace: Namespace`, and a `namespace(*path)` helper for constructing
parameter names scoped to the mode. Extends `NodeInterface` so every mode has
access to `self.node`.

### `TaskContext`

[`context.py:10`](context.py#L10)

`attrs.define` dataclass bundling the three managers:

```python
@attrs.define
class TaskContext:
    environment_manager: EnvironmentManager
    robots_manager: RobotsManager
    world_manager: WorldManager

    @property
    def robots(self) -> dict[str, RobotManager]: ...
```

`TM_Composite` replaces `robots_manager` with a scoped view so each sub-TM
only sees its allocated fleet slice.

### `_TaskRegistry`

[`registry.py:29`](registry.py#L29)

Class-level dictionaries mapping each enum value to a `(loader, Namespace)`
pair. Three decorator factories:

| Decorator | Dict | Key type |
| --- | --- | --- |
| `register_robots(name)` | `registry_robots` | `Constants.TaskMode.TM_Robots` |
| `register_obstacles(name)` | `registry_obstacles` | `Constants.TaskMode.TM_Obstacles` |
| `register_module(name)` | `registry_module` | `Constants.TaskMode.TM_Module` |

Loaders are zero-argument callables that import and return the concrete class
(lazy import pattern). All registrations fire at import time from the
`declare_*()` calls at the bottom of [`registry.py`](registry.py).

## The three axes

| Axis | ABC | Enum | README |
| --- | --- | --- | --- |
| Robot goal dispatch | `TM_Robots` | `Constants.TaskMode.TM_Robots` | [robots/](robots/README.md) |
| Obstacle population | `TM_Obstacles` | `Constants.TaskMode.TM_Obstacles` | [obstacles/](obstacles/README.md) |
| Cross-cutting modules | `TM_Module` | `Constants.TaskMode.TM_Module` | [modules/](modules/README.md) |

## Reset semantics

`Task._reset_task` runs in this order:

1. `robots_manager.set_up()` — reconcile fleet (spawn/remove robots).
2. `environment_manager.before_reset_task()` — pauses the simulator. The sim
   is paused for the entire body below; only node-discovery and lifecycle
   signals are observable here.
3. `module.before_reset()` for every active module.
4. `tm_robots.reset()` — compute new start/goal positions.
5. `tm_obstacles.reset()` — produce `(obstacles, dynamic_obstacles)` lists.
6. `environment_manager.respawn(callback)` — marks all current `INUSE`
   obstacles as `UNUSED`, runs the callback (which spawns the new lists), then
   removes everything still `UNUSED`.
7. `module.after_reset()` for every active module.
8. `environment_manager.after_reset_task()` — unpauses the simulator.

**WORLD layer invariant:** entities spawned with `ObstacleLayer.WORLD` (walls,
doors, floors, world static entities) are never touched during `respawn`. They
survive all episode resets for the lifetime of the world.
