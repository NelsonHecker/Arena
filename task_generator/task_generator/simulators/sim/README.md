# task_generator sim interface

`BaseSim` and the four sub-interfaces it combines. Implementations are
registered in `SimulatorRegistry` and instantiated by key at runtime. See also
[human simulator](../human/README.md) for the pedestrian-logic counterpart
(`BaseHumanSimulator`).

## Sub-interfaces

Defined in [`_interface.py`](_interface.py):

### `ObstacleITF`

[`_interface.py:20`](_interface.py#L20)

| Abstract method | Signature |
| --- | --- |
| `obstacle_spawn` | `(Sequence[Obstacle]) -> Sequence[bool]` |
| `obstacle_move` | `(Sequence[Obstacle]) -> Sequence[bool]` |
| `obstacle_delete` | `(Sequence[Obstacle]) -> Sequence[bool]` |

### `PedestrianITF`

[`_interface.py:38`](_interface.py#L38)

| Abstract method | Signature |
| --- | --- |
| `pedestrian_spawn` | `(Sequence[DynamicObstacle]) -> Sequence[bool]` |
| `pedestrian_move` | `(Sequence[DynamicObstacle]) -> Sequence[bool]` |
| `pedestrian_delete` | `(Sequence[DynamicObstacle]) -> Sequence[bool]` |
| `pedestrian_update` | `(Pedestrians) -> Sequence[bool]` |

### `RobotITF`

[`_interface.py:61`](_interface.py#L61)

| Abstract method | Signature |
| --- | --- |
| `robot_spawn` | `(Sequence[Robot]) -> Sequence[bool]` |
| `robot_move` | `(Sequence[Robot]) -> Sequence[bool]` |
| `robot_delete` | `(Sequence[Robot]) -> Sequence[bool]` |

### `WorldITF`

[`_interface.py:79`](_interface.py#L79)

| Abstract method | Signature |
| --- | --- |
| `spawn_walls` | `(Sequence[Wall]) -> bool` |
| `spawn_floors` | `(Sequence[Floor]) -> bool` |
| `spawn_doors` | `(Sequence[Door]) -> bool` |
| `spawn_elevators` | `(Sequence[Elevator]) -> bool` |
| `remove_world` | `() -> bool` (default raises `NotImplementedError`) |

## `BaseSim`

[`__init__.py:17`](__init__.py#L17)

```python
class BaseSim(NodeInterface, ObstacleITF, PedestrianITF, RobotITF, WorldITF, abc.ABC):
```

Additional abstract methods:

| Method | Purpose |
| --- | --- |
| `before_reset_task()` | called before every episode reset; implementations pause the sim |
| `after_reset_task()` | called after every episode reset; implementations unpause the sim |
| `step(n=1)` | advance simulation by `n` ticks; default no-op returns `True` |

## Sim-paused invariant

The sim is paused for the entire body of `Task._reset_task`. Only
node-discovery and lifecycle signals are observable while the sim is paused;
tf, costmap, and sim-clock topics are not advancing.

## Registered implementations

[`__init__.py:57`](__init__.py#L57) — `SimulatorRegistry` maps
`Constants.SimSimulator` keys to async factory functions:

| Key | Class | File | Notes |
| --- | --- | --- | --- |
| `dummy` | `DummySimulator` | [`dummy_simulator.py`](dummy_simulator.py) | no-op; publishes a synthetic `/clock` for testing |
| `gazebo` | `GazeboSimulator` | [`gazebo_simulator/gazebo_simulator.py`](gazebo_simulator/gazebo_simulator.py) | Gazebo (Ignition) via gz-transport |
| `isaac` | `IsaacSimulator` | [`isaac_simulator.py`](isaac_simulator.py) | Isaac Sim integration |

Flatland and Unity have stubs (commented out) in `__init__.py`; they are not
active. The active simulator is selected by `node.conf.Arena.SIM` and
instantiated via `SimulatorRegistry.get(key, **kwargs)`.

## Adding a new simulator

1. Subclass `BaseSim`; implement all abstract methods from the four
   sub-interfaces plus `before_reset_task` and `after_reset_task`.
2. Register a lazy async factory:

```python
@SimulatorRegistry.register(Constants.SimSimulator.MY_SIM)
async def lazy_mysim(**kwargs):
    from .my_sim import MySimulator
    return await MySimulator.create(**kwargs)
```

3. Add `MY_SIM = "my_sim"` to `Constants.SimSimulator`.
