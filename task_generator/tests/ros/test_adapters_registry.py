from __future__ import annotations

import pytest


@pytest.fixture(autouse=True)
def _ros_gate():
    try:
        import rclpy  # noqa: F401
    except ImportError:
        pytest.skip("ROS2 not available")


def test_register_and_get_round_trip():
    from task_generator.tasks.robots.adapters import Adapter, _ADAPTERS, register_adapter, get_adapter

    class _TestFoo(Adapter):
        kind = "_test_foo"

        async def dispatch_phase(self, phase, robot):
            return None

    try:
        register_adapter(_TestFoo)
        assert get_adapter("_test_foo") is _TestFoo
    finally:
        _ADAPTERS.pop("_test_foo", None)


def test_register_idempotent_same_class():
    from task_generator.tasks.robots.adapters import Adapter, _ADAPTERS, register_adapter

    class _TestIdem(Adapter):
        kind = "_test_idem"

        async def dispatch_phase(self, phase, robot):
            return None

    try:
        register_adapter(_TestIdem)
        register_adapter(_TestIdem)
    finally:
        _ADAPTERS.pop("_test_idem", None)


def test_register_raises_value_error_different_class():
    from task_generator.tasks.robots.adapters import Adapter, _ADAPTERS, register_adapter

    class _TestBarA(Adapter):
        kind = "_test_bar"

        async def dispatch_phase(self, phase, robot):
            return None

    class _TestBarB(Adapter):
        kind = "_test_bar"

        async def dispatch_phase(self, phase, robot):
            return None

    try:
        register_adapter(_TestBarA)
        with pytest.raises(ValueError) as exc_info:
            register_adapter(_TestBarB)
        assert "_TestBarA" in str(exc_info.value)
    finally:
        _ADAPTERS.pop("_test_bar", None)


def test_register_raises_type_error_non_string_kind():
    from task_generator.tasks.robots.adapters import Adapter, register_adapter

    class _TestIntKind(Adapter):
        kind = 123  # type: ignore[assignment]

        async def dispatch_phase(self, phase, robot):
            return None

    with pytest.raises(TypeError):
        register_adapter(_TestIntKind)


def test_register_raises_type_error_empty_string_kind():
    from task_generator.tasks.robots.adapters import Adapter, register_adapter

    class _TestEmptyKind(Adapter):
        kind = ""

        async def dispatch_phase(self, phase, robot):
            return None

    with pytest.raises(TypeError):
        register_adapter(_TestEmptyKind)


def test_register_raises_type_error_missing_kind():
    from task_generator.tasks.robots.adapters import Adapter, register_adapter

    class _TestNoKind(Adapter):
        async def dispatch_phase(self, phase, robot):
            return None

    with pytest.raises(TypeError):
        register_adapter(_TestNoKind)


def test_get_adapter_raises_key_error_unknown_kind():
    from task_generator.tasks.robots.adapters import Adapter, _ADAPTERS, register_adapter, get_adapter

    class _TestKnown(Adapter):
        kind = "_test_known"

        async def dispatch_phase(self, phase, robot):
            return None

    try:
        register_adapter(_TestKnown)
        with pytest.raises(KeyError) as exc_info:
            get_adapter("_test_no_such_kind_xyz")
        msg = str(exc_info.value)
        assert "known" in msg
        assert "_test_known" in msg
    finally:
        _ADAPTERS.pop("_test_known", None)


def test_register_returns_class():
    from task_generator.tasks.robots.adapters import Adapter, _ADAPTERS, register_adapter

    class _TestRet(Adapter):
        kind = "_test_ret"

        async def dispatch_phase(self, phase, robot):
            return None

    try:
        result = register_adapter(_TestRet)
        assert result is _TestRet
    finally:
        _ADAPTERS.pop("_test_ret", None)
