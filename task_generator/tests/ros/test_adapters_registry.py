from __future__ import annotations

import pytest

from arena_rclpy_mixins.registry import ClassRegistry


@pytest.fixture(autouse=True)
def _ros_gate():
    try:
        import rclpy  # noqa: F401
    except ImportError:
        pytest.skip("ROS2 not available")


def test_register_and_get_round_trip():
    reg: ClassRegistry[str, type] = ClassRegistry()

    class _Foo:
        pass

    @reg.register("_test_foo")
    def _load():
        return _Foo

    assert reg.get("_test_foo") is _Foo


def test_register_raises_on_duplicate():
    reg: ClassRegistry[str, type] = ClassRegistry()

    @reg.register("_test_dup")
    def _load_a():
        return object

    with pytest.raises(ValueError):
        @reg.register("_test_dup")
        def _load_b():
            return object


def test_get_raises_key_error_unknown_kind():
    reg: ClassRegistry[str, type] = ClassRegistry()

    @reg.register("_test_known")
    def _load():
        return object

    with pytest.raises(KeyError) as exc_info:
        reg.get("_no_such_kind")
    assert "known" in str(exc_info.value)


def test_lazy_loading():
    reg: ClassRegistry[str, type] = ClassRegistry()

    @reg.register("_test_poison")
    def _poison():
        raise RuntimeError("should not be called")

    class _Bar:
        pass

    @reg.register("_test_bar")
    def _load():
        return _Bar

    assert reg.get("_test_bar") is _Bar
