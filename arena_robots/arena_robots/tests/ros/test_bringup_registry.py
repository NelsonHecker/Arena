"""Tests for arena_robots.bringup registry (register_bringup, get_bringup, check_caps)."""

from __future__ import annotations

from pathlib import Path
from types import SimpleNamespace
from unittest.mock import MagicMock

import pytest
import yaml


def _make_mock_robot(caps_available: frozenset[str], name: str = "test_robot") -> object:
    mock_caps = MagicMock()
    mock_caps.available = caps_available
    mock_robot = MagicMock()
    mock_robot.name = name
    mock_robot.caps = mock_caps
    return mock_robot


class TestRegisterBringup:
    def test_duplicate_kind_raises(self):
        from arena_robots.bringup import _BRINGUPS, register_bringup, Bringup

        class _TempBringup(Bringup):
            kind = "__test_dup_kind__"
            requires = frozenset()

            def _launch_actions(self, **kwargs):
                return []

        old = _BRINGUPS.pop("__test_dup_kind__", None)
        try:
            register_bringup(_TempBringup)
            with pytest.raises((ValueError, AssertionError, KeyError)):
                register_bringup(_TempBringup)
        finally:
            _BRINGUPS.pop("__test_dup_kind__", None)
            if old is not None:
                _BRINGUPS["__test_dup_kind__"] = old

    def test_register_new_kind(self):
        from arena_robots.bringup import _BRINGUPS, get_bringup, register_bringup, Bringup

        class _NewBringup(Bringup):
            kind = "__test_new_kind__"
            requires = frozenset()

            def _launch_actions(self, **kwargs):
                return []

        old = _BRINGUPS.pop("__test_new_kind__", None)
        try:
            register_bringup(_NewBringup)
            assert get_bringup("__test_new_kind__") is _NewBringup
        finally:
            _BRINGUPS.pop("__test_new_kind__", None)
            if old is not None:
                _BRINGUPS["__test_new_kind__"] = old

    def test_register_returns_cls(self):
        from arena_robots.bringup import _BRINGUPS, register_bringup, Bringup

        class _RetBringup(Bringup):
            kind = "__test_ret_kind__"
            requires = frozenset()

            def _launch_actions(self, **kwargs):
                return []

        old = _BRINGUPS.pop("__test_ret_kind__", None)
        try:
            result = register_bringup(_RetBringup)
            assert result is _RetBringup
        finally:
            _BRINGUPS.pop("__test_ret_kind__", None)
            if old is not None:
                _BRINGUPS["__test_ret_kind__"] = old


class TestGetBringup:
    def test_not_found_raises_key_error(self):
        from arena_robots.bringup import get_bringup

        with pytest.raises(KeyError, match="__nonexistent_kind__"):
            get_bringup("__nonexistent_kind__")

    def test_nav2_is_registered(self):
        from arena_robots.bringup import get_bringup
        from arena_robots.bringup.nav2 import Nav2Bringup

        assert get_bringup("nav2") is Nav2Bringup

    def test_none_is_registered(self):
        from arena_robots.bringup import get_bringup
        from arena_robots.bringup.none import NoneBringup

        assert get_bringup("none") is NoneBringup

    def test_external_is_registered(self):
        from arena_robots.bringup import get_bringup
        from arena_robots.bringup.external import ExternalBringup

        assert get_bringup("external") is ExternalBringup


class TestCheckCaps:
    def test_matching_caps_no_raise(self):
        from arena_robots.bringup import check_caps

        robot = _make_mock_robot(frozenset({"mobile"}))
        mock_bringup = MagicMock()
        mock_bringup.requires = frozenset({"mobile"})
        mock_bringup.kind = "nav2"
        mock_bringup.robot = robot
        check_caps(mock_bringup)

    def test_missing_cap_raises_adapter_cap_mismatch(self):
        from arena_robots.bringup import AdapterCapMismatch, check_caps

        robot = _make_mock_robot(frozenset())
        mock_bringup = MagicMock()
        mock_bringup.requires = frozenset({"mobile"})
        mock_bringup.kind = "nav2"
        mock_bringup.robot = robot
        with pytest.raises(AdapterCapMismatch, match="mobile"):
            check_caps(mock_bringup)

    def test_superset_caps_no_raise(self):
        from arena_robots.bringup import check_caps

        robot = _make_mock_robot(frozenset({"mobile", "arm", "lift"}))
        mock_bringup = MagicMock()
        mock_bringup.requires = frozenset({"mobile"})
        mock_bringup.kind = "nav2"
        mock_bringup.robot = robot
        check_caps(mock_bringup)

    def test_partial_caps_raises(self):
        from arena_robots.bringup import AdapterCapMismatch, check_caps

        robot = _make_mock_robot(frozenset({"mobile"}))
        mock_bringup = MagicMock()
        mock_bringup.requires = frozenset({"mobile", "arm"})
        mock_bringup.kind = "custom"
        mock_bringup.robot = robot
        with pytest.raises(AdapterCapMismatch):
            check_caps(mock_bringup)


class TestAcceptsTaskKinds:
    def test_nav2_bringup_accepts_goto_pose(self):
        from arena_robots.bringup.nav2 import Nav2Bringup
        from arena_robots.task_kinds import TaskKind

        robot = _make_mock_robot(frozenset({"mobile"}))
        b = Nav2Bringup(robot=robot, namespace="/robot1")
        accepted = b.accepts_task_kinds
        assert TaskKind.GOTO_POSE in accepted

    def test_none_bringup_accepts_goto_pose(self):
        from arena_robots.bringup.none import NoneBringup
        from arena_robots.task_kinds import TaskKind

        robot = _make_mock_robot(frozenset({"mobile"}))
        b = NoneBringup(robot=robot, namespace="/robot1")
        accepted = b.accepts_task_kinds
        assert TaskKind.GOTO_POSE in accepted
