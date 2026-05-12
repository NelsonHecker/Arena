# task_generator obstacle task modes

`TM_Obstacles` and its shipped subclasses. Each mode's `reset()` returns
`(list[Obstacle], list[DynamicObstacle])` consumed by `EnvironmentManager`.

## `TM_Obstacles` ABC

[`__init__.py:8`](__init__.py#L8)

```python
class TM_Obstacles(TaskMode):
    async def reset(self, **kwargs) -> Obstacles:
        return [], []
```

`Obstacles = tuple[list[Obstacle], list[DynamicObstacle]]`. The base
implementation returns empty lists; every subclass overrides `reset`.

## Shipped modes

| Kind | Class | File | Behavior |
| --- | --- | --- | --- |
| `random` | `TM_Random` | [`random.py`](random.py) | samples N static and dynamic obstacles from model pools; counts and model lists are ROS params |
| `parametrized` | `TM_Parametrized` | [`parametrized.py`](parametrized.py) | loads a `ParametrizedConfig` by name from `arena_simulation_setup`; min/max counts per entry |
| `scenario` | `TM_Scenario` | [`scenario.py`](scenario.py) | reads `static` and `dynamic` lists from a world scenario YAML |
| `environment` | `TM_Environment` | [`environment.py`](environment.py) | places obstacle groups from an environment config into detected or declared rooms |
| `prompt` | `TM_Prompt` | [`prompt/prompt.py`](prompt/prompt.py) | LLM-driven obstacle generation; PROMPT registered per `BaseHumanSimulator` subclass |

## Package structure

Each `TM_Obstacles` subclass is a package:

- `__init__.py` (eager): registers the mode via `_TaskRegistry.register_obstacles` and calls `declare_schema(node, ns)` to forward-declare all parameters at node startup.
- `impl.py` (lazy): contains the class body, imported only on first activation.

Parameters live under `task.<mode>.<leaf>` (e.g. `task.random.static.n`).

## Setting per-mode params: staged contract

All `task.*` writes go through `config/queue_episode`. The request carries the mode change and a leaf-keyed `obstacles_params` / `robots_params` payload (`rcl_interfaces/Parameter[]`, names **relative to the mode**, no `task.<mode>.` prefix). The server stages them and applies at the next `lifecycle/reset_episode` boundary. Failures warn, never abort. Last-write-wins on duplicate leaf keys within an axis between resets.

A leaf is what's left after stripping `task.<mode>.`. For `task.random.static.n` the leaf is `static.n`; for `task.scenario.file` the leaf is `file`. The active mode is taken from the request's `tm_obstacles` / `tm_robots`; sending `task.scenario.file` as a param name (full path) results in the server constructing `task.<mode>.task.scenario.file` and dropping it as undeclared.

Because all parameters are forward-declared at startup, raw `SetParameters` also works at any time for the full `task.<mode>.<leaf>` path; no activation ordering constraint.

### `TM_Random` params

Declared under the mode namespace (e.g. `task.random.*`):

| Param | Default | Description |
| --- | --- | --- |
| `static.n` | `[5, 15]` | `[min, max]` static obstacle count |
| `dynamic.n` | `[1, 5]` | `[min, max]` dynamic obstacle count |
| `static.models` | *(all ObjectIdentifiers)* | model name list |
| `dynamic.models` | *(all PedestrianIdentifiers)* | model name list |

### `TM_Parametrized` params

Declared under `task.parametrized.*`:

| Param | Default | Description |
| --- | --- | --- |
| `parametrized.file` | `''` | `ParametrizedIdentifier` name to resolve |

### `TM_Scenario` params

Declared under `task.scenario.*`:

| Param | Default | Description |
| --- | --- | --- |
| `scenario.file` | first available scenario | scenario name within the active world |

`TM_Scenario` resolves the scenario via
`WorldIdentifier(world_name).resolve_sync().scenario(name).resolve_sync().load()`
and returns `scenario.static` / `scenario.dynamic` unchanged on each reset.

### `TM_Environment` params

Declared under `task.environment.*`:

| Param | Default | Description |
| --- | --- | --- |
| `environment.file` | `'default.json'` | `EnvironmentIdentifier` name to resolve |

Groups from the environment config are placed into rooms. Rooms are either
taken from `world_manager.world.zones` (explicit zone declarations) or
detected from wall geometry via `_create_rooms_from_walls`.

## Zone references

`TM_Scenario` delegates zone-ref resolution to the `Scenario` loader in
`arena_simulation_setup`. `pose_ref` and `waypoint_refs` declared in a
scenario file are resolved against named zones at load time using a seeded
RNG (the seed comes from `node.conf.General.RNG`), so replaying with the same
seed produces identical placements.

## `obstacles/prompt/`

`TM_Prompt` ([`prompt/prompt.py`](prompt/prompt.py)) generates obstacle lists
via an LLM. PROMPT registration is per-`BaseHumanSimulator` subclass — see
[PROMPT registration](../../simulators/human/README.md#prompt-registration).

## Adding a new TM_Obstacles mode

1. Create `tasks/obstacles/<name>/` as a package.
2. In `__init__.py`: call `_TaskRegistry.register_obstacles` (registering the lazy loader from `impl.py`) and define `declare_schema(node, ns)` using helpers from [`task_generator.tasks.declarations`](../declarations.py) (e.g. `declare_int_pair`, `declare_catalog`).
3. In `impl.py`: define the class extending `TM_Obstacles`; override `reset` to return `(list[Obstacle], list[DynamicObstacle])`.
4. Add `<NAME> = "<name>"` to `Constants.TaskMode.TM_Obstacles` in [`constants/__init__.py`](../../constants/__init__.py).
5. Ensure `_TaskRegistry.walk_schemas` will pick up your schema (it iterates all registered families at node init automatically).
