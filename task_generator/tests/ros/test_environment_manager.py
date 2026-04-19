from __future__ import annotations

import asyncio
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock, patch

import pytest


@pytest.fixture(autouse=True)
def _ros_gate():
    try:
        import rclpy  # noqa: F401
    except ImportError:
        pytest.skip("ROS2 not available")


class _FakeLogger:
    def get_child(self, name):
        return self
    def debug(self, *a, **kw): ...
    def info(self, *a, **kw): ...
    def warn(self, *a, **kw): ...
    def error(self, *a, **kw): ...


def _make_env_manager(realizer=None, human_sim=None, sim=None):
    from task_generator.manager.environment_manager import EnvironmentManager
    from task_generator.manager.realizer import Realizer

    if realizer is None:
        realizer = Realizer(Realizer._Configuration(x=0.0, y=0.0, prefix=""))

    if human_sim is None:
        human_sim = SimpleNamespace(
            spawn_world=AsyncMock(return_value=None),
            spawn_obstacles=AsyncMock(return_value=None),
            spawn_dynamic_obstacles=AsyncMock(return_value=None),
            unuse_obstacles=AsyncMock(return_value=None),
            remove_obstacles=AsyncMock(return_value=None),
            spawn_robot=AsyncMock(return_value=[]),
            move_robot=AsyncMock(return_value=[]),
            remove_robot=AsyncMock(return_value=[]),
        )

    if sim is None:
        sim = SimpleNamespace(
            spawn_floors=AsyncMock(return_value=None),
            spawn_elevators=AsyncMock(return_value=None),
            step=AsyncMock(return_value=True),
            before_reset_task=AsyncMock(return_value=True),
            after_reset_task=AsyncMock(return_value=True),
        )

    node = SimpleNamespace(
        get_logger=lambda: _FakeLogger(),
    )

    em = EnvironmentManager.__new__(EnvironmentManager)
    em._NodeInterface__node = node
    em._realizer = realizer
    em._human_simulator = human_sim
    em._simulator = sim
    return em


def test_realize_delegates_to_realizer():
    from arena_simulation_setup.utils.geometry import Position
    from task_generator.manager.realizer import Realizer
    realizer = Realizer(Realizer._Configuration(x=5.0, y=3.0, prefix=""))
    em = _make_env_manager(realizer=realizer)
    p = Position(1.0, 2.0)
    result = em.realize(p)
    import math
    assert math.isclose(result.x, 6.0)
    assert math.isclose(result.y, 5.0)


def test_spawn_world_obstacles_with_floors():
    from arena_simulation_setup.utils.geometry import Position
    sim = SimpleNamespace(
        spawn_floors=AsyncMock(return_value=None),
        spawn_elevators=AsyncMock(return_value=None),
    )
    human_sim = SimpleNamespace(
        spawn_world=AsyncMock(return_value=None),
        spawn_obstacles=AsyncMock(return_value=None),
    )
    em = _make_env_manager(human_sim=human_sim, sim=sim)

    from arena_simulation_setup.shared import Floor
    floor = Floor(pos=Position(0, 0), name="f1", extra={})
    world = SimpleNamespace(
        all_walls=iter([]),
        all_doors=iter([]),
        all_floors=iter([floor]),
        all_elevators=iter([]),
        all_static_entities=iter([]),
        all_dynamic_entities=iter([]),
    )
    asyncio.run(em.spawn_world_obstacles(world))
    sim.spawn_floors.assert_called_once()


def test_spawn_world_obstacles_no_floors_no_spawn_floors():
    sim = SimpleNamespace(
        spawn_floors=AsyncMock(return_value=None),
        spawn_elevators=AsyncMock(return_value=None),
    )
    human_sim = SimpleNamespace(
        spawn_world=AsyncMock(return_value=None),
        spawn_obstacles=AsyncMock(return_value=None),
    )
    em = _make_env_manager(human_sim=human_sim, sim=sim)

    world = SimpleNamespace(
        all_walls=iter([]),
        all_doors=iter([]),
        all_floors=iter([]),
        all_elevators=iter([]),
        all_static_entities=iter([]),
        all_dynamic_entities=iter([]),
    )
    asyncio.run(em.spawn_world_obstacles(world))
    sim.spawn_floors.assert_not_called()


def test_spawn_world_obstacles_with_walls():
    from arena_simulation_setup.shared import Wall
    from arena_simulation_setup.utils.geometry import Position

    sim = SimpleNamespace(
        spawn_floors=AsyncMock(return_value=None),
        spawn_elevators=AsyncMock(return_value=None),
    )
    human_sim = SimpleNamespace(
        spawn_world=AsyncMock(return_value=None),
        spawn_obstacles=AsyncMock(return_value=None),
    )
    em = _make_env_manager(human_sim=human_sim, sim=sim)

    w = Wall(start=Position(0, 0), end=Position(1, 0))
    world = SimpleNamespace(
        all_walls=iter([w]),
        all_doors=iter([]),
        all_floors=iter([]),
        all_elevators=iter([]),
        all_static_entities=iter([]),
        all_dynamic_entities=iter([]),
    )
    asyncio.run(em.spawn_world_obstacles(world))
    human_sim.spawn_world.assert_called_once()


def test_spawn_world_obstacles_no_walls_no_spawn_world():
    sim = SimpleNamespace(
        spawn_floors=AsyncMock(return_value=None),
        spawn_elevators=AsyncMock(return_value=None),
    )
    human_sim = SimpleNamespace(
        spawn_world=AsyncMock(return_value=None),
        spawn_obstacles=AsyncMock(return_value=None),
    )
    em = _make_env_manager(human_sim=human_sim, sim=sim)

    world = SimpleNamespace(
        all_walls=iter([]),
        all_doors=iter([]),
        all_floors=iter([]),
        all_elevators=iter([]),
        all_static_entities=iter([]),
        all_dynamic_entities=iter([]),
    )
    asyncio.run(em.spawn_world_obstacles(world))
    human_sim.spawn_world.assert_not_called()


def test_spawn_world_obstacles_always_calls_spawn_obstacles():
    sim = SimpleNamespace(
        spawn_floors=AsyncMock(return_value=None),
        spawn_elevators=AsyncMock(return_value=None),
    )
    human_sim = SimpleNamespace(
        spawn_world=AsyncMock(return_value=None),
        spawn_obstacles=AsyncMock(return_value=None),
    )
    em = _make_env_manager(human_sim=human_sim, sim=sim)

    world = SimpleNamespace(
        all_walls=iter([]),
        all_doors=iter([]),
        all_floors=iter([]),
        all_elevators=iter([]),
        all_static_entities=iter([]),
        all_dynamic_entities=iter([]),
    )
    asyncio.run(em.spawn_world_obstacles(world))
    human_sim.spawn_obstacles.assert_called_once()


def test_spawn_world_obstacles_with_elevators():
    from arena_simulation_setup.shared import Elevator
    from arena_simulation_setup.utils.geometry import Position

    sim = SimpleNamespace(
        spawn_floors=AsyncMock(return_value=None),
        spawn_elevators=AsyncMock(return_value=None),
    )
    human_sim = SimpleNamespace(
        spawn_world=AsyncMock(return_value=None),
        spawn_obstacles=AsyncMock(return_value=None),
    )
    em = _make_env_manager(human_sim=human_sim, sim=sim)

    e = Elevator(position=Position(0, 0), name="e1", extra={})
    world = SimpleNamespace(
        all_walls=iter([]),
        all_doors=iter([]),
        all_floors=iter([]),
        all_elevators=iter([e]),
        all_static_entities=iter([]),
        all_dynamic_entities=iter([]),
    )
    asyncio.run(em.spawn_world_obstacles(world))
    sim.spawn_elevators.assert_called_once()


def test_respawn_calls_unuse_callback_remove():
    human_sim = SimpleNamespace(
        spawn_world=AsyncMock(return_value=None),
        spawn_obstacles=AsyncMock(return_value=None),
        spawn_dynamic_obstacles=AsyncMock(return_value=None),
        unuse_obstacles=AsyncMock(return_value=None),
        remove_obstacles=AsyncMock(return_value=None),
    )
    sim = SimpleNamespace(
        spawn_floors=AsyncMock(return_value=None),
        spawn_elevators=AsyncMock(return_value=None),
    )
    em = _make_env_manager(human_sim=human_sim, sim=sim)

    callback_called = []

    async def _callback():
        callback_called.append(True)

    asyncio.run(em.respawn(_callback))

    human_sim.unuse_obstacles.assert_called_once()
    human_sim.remove_obstacles.assert_called_once()
    assert callback_called == [True]


def test_reset_calls_remove_obstacles_with_purge():
    from task_generator.simulators.human.utils import ObstacleLayer
    human_sim = SimpleNamespace(
        remove_obstacles=AsyncMock(return_value=None),
    )
    sim = SimpleNamespace()
    em = _make_env_manager(human_sim=human_sim, sim=sim)

    asyncio.run(em.reset(purge=ObstacleLayer.INUSE))
    human_sim.remove_obstacles.assert_called_once_with(purge=ObstacleLayer.INUSE)


def test_step_delegates_to_simulator():
    sim = SimpleNamespace(step=AsyncMock(return_value=True))
    em = _make_env_manager(sim=sim)
    result = asyncio.run(em.step(1))
    assert result is True
    sim.step.assert_called_once_with(1)


def test_step_zero():
    sim = SimpleNamespace(step=AsyncMock(return_value=False))
    em = _make_env_manager(sim=sim)
    asyncio.run(em.step(0))
    sim.step.assert_called_once_with(0)


def test_before_reset_task_delegates():
    sim = SimpleNamespace(before_reset_task=AsyncMock(return_value=True))
    em = _make_env_manager(sim=sim)
    result = asyncio.run(em.before_reset_task())
    assert result is True


def test_after_reset_task_delegates():
    sim = SimpleNamespace(after_reset_task=AsyncMock(return_value=True))
    em = _make_env_manager(sim=sim)
    result = asyncio.run(em.after_reset_task())
    assert result is True


def test_spawn_dynamic_obstacles_delegates():
    from arena_simulation_setup.shared import DynamicObstacle
    from arena_simulation_setup.utils.geometry import Position, Pose

    human_sim = SimpleNamespace(spawn_dynamic_obstacles=AsyncMock(return_value=None))
    em = _make_env_manager(human_sim=human_sim)

    obs = DynamicObstacle(
        name="h1",
        pose=Pose(Position(0, 0)),
        model="human",
        waypoints=[],
        extra={},
    )
    asyncio.run(em.spawn_dynamic_obstacles([obs]))
    human_sim.spawn_dynamic_obstacles.assert_called_once()
