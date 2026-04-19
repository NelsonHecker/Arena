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


def _make_node(sim_time_sec=0, timeout=60):
    class _Conf:
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
                value = timeout

    return SimpleNamespace(
        conf=_Conf(),
        sim_time=SimpleNamespace(sec=sim_time_sec),
        get_logger=lambda: _FakeLogger(),
    )


def _make_tm_robots(node, robots_dict=None):
    from task_generator.tasks.robots import TM_Robots
    from arena_rclpy_mixins.shared import Namespace

    if robots_dict is None:
        robots_dict = {}

    ctx = SimpleNamespace(
        robots_manager=SimpleNamespace(managers=robots_dict),
        robots=robots_dict,
        environment_manager=SimpleNamespace(realize=lambda x: x),
        world_manager=SimpleNamespace(world_name="test_world"),
    )

    class _ConcreteRobots(TM_Robots):
        pass

    tm = _ConcreteRobots(
        node=node,
        ctx=ctx,
        namespace=Namespace("test"),
    )
    tm._last_reset = 0
    return tm


def test_reset_sets_last_reset_from_sim_time():
    node = _make_node(sim_time_sec=42)
    tm = _make_tm_robots(node)
    asyncio.run(tm.reset())
    assert tm._last_reset == 42


def test_done_empty_robots_returns_false():
    node = _make_node(sim_time_sec=0)
    tm = _make_tm_robots(node, robots_dict={})
    result = asyncio.run(tm.done)
    assert result is False


def test_done_timeout_exceeded_returns_true():
    node = _make_node(sim_time_sec=120, timeout=60)
    tm = _make_tm_robots(node, robots_dict={})
    tm._last_reset = 0
    result = asyncio.run(tm.done)
    assert result is True


def test_done_not_exceeded_empty_robots_returns_false():
    node = _make_node(sim_time_sec=30, timeout=60)
    tm = _make_tm_robots(node, robots_dict={})
    tm._last_reset = 0
    result = asyncio.run(tm.done)
    assert result is False


def test_done_all_done_returns_true():
    node = _make_node(sim_time_sec=10, timeout=60)

    async def _done_coroutine():
        return True

    robot_manager = SimpleNamespace(is_done=_done_coroutine())

    robots_dict = {"robot1": robot_manager}
    tm = _make_tm_robots(node, robots_dict=robots_dict)
    tm._last_reset = 0

    result = asyncio.run(tm.done)
    assert result is True


def test_done_not_all_done_returns_false():
    node = _make_node(sim_time_sec=10, timeout=60)

    async def _not_done():
        return False

    robot_manager = SimpleNamespace(is_done=_not_done())
    robots_dict = {"robot1": robot_manager}
    tm = _make_tm_robots(node, robots_dict=robots_dict)
    tm._last_reset = 0

    result = asyncio.run(tm.done)
    assert result is False
