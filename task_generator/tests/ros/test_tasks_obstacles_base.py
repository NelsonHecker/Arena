from __future__ import annotations

import asyncio
from types import SimpleNamespace

import pytest


@pytest.fixture(autouse=True)
def _ros_gate():
    try:
        import rclpy  # noqa: F401
    except ImportError:
        pytest.skip("ROS2 not available")


class _FakeConf:
    class Robot:
        class BEHAVIOR:
            value = "rosnav"
        class CONTROLLER:
            value = "dwa"
        class PLANNER:
            value = "navfn"
        class AGENT:
            value = "rosnav"
        class NAVIGATOR:
            value = "nav2"
        class RECORD_DATA_DIR:
            value = None
        class TIMEOUT:
            value = 60


class _FakeLogger:
    def get_child(self, name):
        return self
    def debug(self, *a, **kw): ...
    def info(self, *a, **kw): ...
    def warn(self, *a, **kw): ...
    def error(self, *a, **kw): ...


def _make_tm_obstacles():
    from task_generator.tasks.obstacles import TM_Obstacles
    from arena_rclpy_mixins.shared import Namespace

    node = SimpleNamespace(
        conf=_FakeConf(),
        sim_time=SimpleNamespace(sec=0),
        get_logger=lambda: _FakeLogger(),
    )

    class _ConcreteObstacles(TM_Obstacles):
        pass

    ctx = SimpleNamespace(
        robots_manager=SimpleNamespace(managers={}),
        environment_manager=SimpleNamespace(),
        world_manager=SimpleNamespace(world_name="test_world"),
    )

    return _ConcreteObstacles(
        node=node,
        ctx=ctx,
        namespace=Namespace("test"),
    )


def test_tm_obstacles_reset_returns_empty_tuple():
    tm = _make_tm_obstacles()
    result = asyncio.run(tm.reset())
    static, dynamic = result
    assert static == []
    assert dynamic == []


def test_tm_obstacles_reset_ignores_kwargs():
    tm = _make_tm_obstacles()
    result = asyncio.run(tm.reset(world_name="some_world", count=5))
    static, dynamic = result
    assert static == []
    assert dynamic == []


def test_tm_obstacles_reset_returns_tuple():
    tm = _make_tm_obstacles()
    result = asyncio.run(tm.reset())
    assert isinstance(result, tuple)
    assert len(result) == 2
