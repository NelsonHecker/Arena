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
| `random` | `TM_Random` | [`random.py`](random.py) | samples N static, interactive, and dynamic obstacles from model pools; counts and model lists are ROS params |
| `parametrized` | `TM_Parametrized` | [`parametrized.py`](parametrized.py) | loads a `ParametrizedConfig` by name from `arena_simulation_setup`; min/max counts per entry |
| `scenario` | `TM_Scenario` | [`scenario.py`](scenario.py) | reads `static` and `dynamic` lists from a world scenario YAML |
| `environment` | `TM_Environment` | [`environment.py`](environment.py) | places obstacle groups from an environment config into detected or declared rooms |
| `prompt` | `TM_Prompt` | [`prompt/prompt.py`](prompt/prompt.py) | LLM-driven obstacle generation; PROMPT registered per `BaseHumanSimulator` subclass |

### `TM_Random` params

Declared under the mode namespace (e.g. `task.random.*`):

| Param | Default | Description |
| --- | --- | --- |
| `static.n` | `[5, 15]` | `[min, max]` static obstacle count |
| `interactive.n` | `[0, 0]` | `[min, max]` interactive obstacle count |
| `dynamic.n` | `[1, 5]` | `[min, max]` dynamic obstacle count |
| `static.models` | *(all ObjectIdentifiers)* | model name list |
| `interactive.models` | *(all ObjectIdentifiers)* | model name list |
| `dynamic.models` | *(all PedestrianIdentifiers)* | model name list |

### `TM_Parametrized` params

| Param | Default | Description |
| --- | --- | --- |
| `parametrized.file` | `''` | `ParametrizedIdentifier` name to resolve |

### `TM_Scenario` params

| Param | Default | Description |
| --- | --- | --- |
| `scenario.file` | first available scenario | scenario name within the active world |

`TM_Scenario` resolves the scenario via
`WorldIdentifier(world_name).resolve_sync().scenario(name).resolve_sync().load()`
and returns `scenario.static` / `scenario.dynamic` unchanged on each reset.

### `TM_Environment` params

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

1. Create `tasks/obstacles/<name>.py` with a class extending `TM_Obstacles`;
   override `reset` to return `(list[Obstacle], list[DynamicObstacle])`.
2. Add `<NAME> = "<name>"` to `Constants.TaskMode.TM_Obstacles` in
   [`constants/__init__.py`](../../constants/__init__.py).
3. Register a lazy loader in [`tasks/registry.py`](../registry.py):

```python
@_TaskRegistry.register_obstacles(Constants.TaskMode.TM_Obstacles.MY_MODE)
def _my_mode():
    from .obstacles.my_mode import TM_MyMode
    return TM_MyMode
```

Declare any ROS params your mode needs in `__init__` using `self.namespace()`
to scope them under the mode's parameter prefix.
