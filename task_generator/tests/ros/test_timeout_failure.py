from __future__ import annotations

import asyncio
from types import SimpleNamespace
from unittest.mock import MagicMock

import pytest


@pytest.fixture(autouse=True)
def _ros_gate():
    try:
        import rclpy  # noqa: F401
    except ImportError:
        pytest.skip("ROS2 not available")


class _FakeRobot:
    def __init__(self, done: bool) -> None:
        self._done = done

    @property
    async def is_done(self) -> bool:
        return self._done


def _make_tm_robots(*, timeout=60, elapsed_sec=0, robots_done=False):
    from arena_rclpy_mixins.shared import Namespace
    from task_generator.tasks.robots import TM_Robots

    class _FakeConf:
        class Robot:
            class TIMEOUT:
                value = timeout

    node = SimpleNamespace(
        conf=_FakeConf(),
        sim_time=SimpleNamespace(sec=elapsed_sec),
        fail_episode=MagicMock(),
        get_logger=lambda: MagicMock(),
    )

    robot = _FakeRobot(robots_done)

    ctx = SimpleNamespace(
        robots={"jackal": robot},
        robots_manager=SimpleNamespace(managers={"jackal": robot}),
        environment_manager=SimpleNamespace(),
        world_manager=SimpleNamespace(),
        abort_episode=MagicMock(),
    )

    tm = TM_Robots(
        node=node,
        ctx=ctx,
        namespace=Namespace("env_0"),
    )
    tm._last_reset = 0
    return tm, node, ctx


def test_timeout_triggers_fail_episode_when_robots_not_done():
    tm, node, ctx = _make_tm_robots(timeout=10, elapsed_sec=15, robots_done=False)
    is_done = asyncio.run(tm.done)
    assert is_done is True
    node.fail_episode.assert_called_once_with("timeout")


def test_no_fail_episode_when_robots_done_before_timeout():
    tm, node, ctx = _make_tm_robots(timeout=60, elapsed_sec=10, robots_done=True)
    is_done = asyncio.run(tm.done)
    assert is_done is True
    node.fail_episode.assert_not_called()


def test_in_progress_when_robots_not_done_and_within_timeout():
    tm, node, ctx = _make_tm_robots(timeout=60, elapsed_sec=10, robots_done=False)
    is_done = asyncio.run(tm.done)
    assert is_done is False
    node.fail_episode.assert_not_called()


def test_stationary_mode_succeeds_on_timeout_without_failure():
    from arena_rclpy_mixins.shared import Namespace
    from task_generator.tasks.robots.stationary.impl import TM_Stationary

    class _FakeConf:
        class Robot:
            class TIMEOUT:
                value = 30

    class _FakeParamServer:
        def __getitem__(self, _type):
            return lambda _name, default: SimpleNamespace(value=default)

    node = SimpleNamespace(
        conf=_FakeConf(),
        sim_time=SimpleNamespace(sec=35),
        fail_episode=MagicMock(),
        get_logger=lambda: MagicMock(),
        ROSParam=_FakeParamServer(),
    )

    ctx = SimpleNamespace(
        robots={},
        robots_manager=SimpleNamespace(managers={}),
        environment_manager=SimpleNamespace(),
        world_manager=SimpleNamespace(),
        abort_episode=MagicMock(),
    )

    tm = TM_Stationary(
        node=node,
        ctx=ctx,
        namespace=Namespace("env_0"),
    )
    tm._last_reset = 0

    is_done = asyncio.run(tm.done)
    assert is_done is True
    node.fail_episode.assert_not_called()
