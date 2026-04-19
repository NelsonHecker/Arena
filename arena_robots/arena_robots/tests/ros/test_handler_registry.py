"""Tests for arena_robots.task_server_handlers — HandlerRegistry and _executor_sleep."""

from __future__ import annotations

import asyncio
from types import SimpleNamespace
from unittest.mock import MagicMock, call

import pytest


class TestHandlerRegistry:
    def _make_registry(self):
        from arena_robots.task_server_handlers import HandlerRegistry

        return HandlerRegistry()

    def test_register_and_get(self):
        reg = self._make_registry()
        loader = lambda: "value_A"  # noqa: E731
        reg.register("key_a")(loader)
        assert reg.get("key_a") == "value_A"

    def test_duplicate_key_raises(self):
        reg = self._make_registry()

        @reg.register("dup_key")
        def _l1():
            return 1

        with pytest.raises(ValueError, match="already registered"):

            @reg.register("dup_key")
            def _l2():
                return 2

    def test_get_missing_raises_key_error(self):
        reg = self._make_registry()
        with pytest.raises(KeyError):
            reg.get("nonexistent")

    def test_loader_called_lazily(self):
        reg = self._make_registry()
        call_count = 0

        @reg.register("lazy_key")
        def _loader():
            nonlocal call_count
            call_count += 1
            return "loaded"

        assert call_count == 0
        reg.get("lazy_key")
        assert call_count == 1

    def test_loader_cached_on_second_get(self):
        reg = self._make_registry()
        call_count = 0

        @reg.register("cache_key")
        def _loader():
            nonlocal call_count
            call_count += 1
            return "value"

        reg.get("cache_key")
        reg.get("cache_key")
        assert call_count == 1

    def test_keys_returns_registered(self):
        reg = self._make_registry()
        reg.register("k1")(lambda: 1)
        reg.register("k2")(lambda: 2)
        assert "k1" in reg.keys()
        assert "k2" in reg.keys()

    def test_register_decorator_returns_loader(self):
        reg = self._make_registry()

        def _loader():
            return 42

        result = reg.register("ret_key")(_loader)
        assert result is _loader


class TestGlobalHandlers:
    def test_handlers_has_goto_pose_nav2(self):
        from arena_robots.task_server_handlers import HANDLERS
        from arena_robots.task_kinds import TaskKind

        assert (TaskKind.GOTO_POSE, "nav2") in HANDLERS.keys()

    def test_handlers_has_goto_pose_none(self):
        from arena_robots.task_server_handlers import HANDLERS
        from arena_robots.task_kinds import TaskKind

        assert (TaskKind.GOTO_POSE, "none") in HANDLERS.keys()

    def test_handlers_has_goto_pose_external(self):
        from arena_robots.task_server_handlers import HANDLERS
        from arena_robots.task_kinds import TaskKind

        assert (TaskKind.GOTO_POSE, "external") in HANDLERS.keys()


class TestExecutorSleep:
    def test_wall_true_creates_wall_clock_timer(self):
        from rclpy.clock import Clock

        from arena_robots.task_server_handlers import _executor_sleep

        created_timers = []
        destroyed_timers = []

        def mock_create_timer(seconds, cb, clock=None):
            t = MagicMock()
            t._clock = clock
            t._seconds = seconds
            t._cb = cb
            created_timers.append(t)
            cb()
            return t

        node = SimpleNamespace(
            create_timer=mock_create_timer,
            destroy_timer=lambda t: destroyed_timers.append(t),
        )

        asyncio.run(_executor_sleep(node, 0.01, wall=True))
        assert len(created_timers) == 1
        assert isinstance(created_timers[0]._clock, Clock)
        assert len(destroyed_timers) == 1

    def test_wall_false_uses_default_clock(self):
        from arena_robots.task_server_handlers import _executor_sleep

        created_clocks = []

        def mock_create_timer(seconds, cb, clock=None):
            t = MagicMock()
            created_clocks.append(clock)
            cb()
            return t

        node = SimpleNamespace(
            create_timer=mock_create_timer,
            destroy_timer=lambda t: None,
        )

        asyncio.run(_executor_sleep(node, 0.01, wall=False))
        assert created_clocks[0] is None

    def test_timer_always_destroyed(self):
        from arena_robots.task_server_handlers import _executor_sleep

        destroyed = []

        def mock_create_timer(seconds, cb, clock=None):
            t = MagicMock()
            cb()
            return t

        node = SimpleNamespace(
            create_timer=mock_create_timer,
            destroy_timer=lambda t: destroyed.append(t),
        )

        asyncio.run(_executor_sleep(node, 0.01))
        assert len(destroyed) == 1
