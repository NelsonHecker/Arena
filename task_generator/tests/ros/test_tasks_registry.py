from __future__ import annotations

import pytest


@pytest.fixture(autouse=True)
def _ros_gate():
    try:
        import rclpy  # noqa: F401
    except ImportError:
        pytest.skip("ROS2 not available")


def test_registry_has_obstacles_entries():
    from task_generator.tasks.registry import _TaskRegistry
    from task_generator.constants import Constants
    assert Constants.TaskMode.TM_Obstacles.PARAMETRIZED in _TaskRegistry.registry_obstacles
    assert Constants.TaskMode.TM_Obstacles.RANDOM in _TaskRegistry.registry_obstacles
    assert Constants.TaskMode.TM_Obstacles.SCENARIO in _TaskRegistry.registry_obstacles
    assert Constants.TaskMode.TM_Obstacles.ENVIRONMENT in _TaskRegistry.registry_obstacles


def test_registry_has_robots_entries():
    from task_generator.tasks.registry import _TaskRegistry
    from task_generator.constants import Constants
    assert Constants.TaskMode.TM_Robots.GUIDED in _TaskRegistry.registry_robots
    assert Constants.TaskMode.TM_Robots.EXPLORE in _TaskRegistry.registry_robots
    assert Constants.TaskMode.TM_Robots.RANDOM in _TaskRegistry.registry_robots
    assert Constants.TaskMode.TM_Robots.SCENARIO in _TaskRegistry.registry_robots


def test_registry_has_module_entries():
    from task_generator.tasks.registry import _TaskRegistry
    from task_generator.constants import Constants
    assert Constants.TaskMode.TM_Module.BENCHMARK in _TaskRegistry.registry_module
    assert Constants.TaskMode.TM_Module.CLEAR_FORBIDDEN_ZONES in _TaskRegistry.registry_module
    assert Constants.TaskMode.TM_Module.RVIZ_UI in _TaskRegistry.registry_module
    assert Constants.TaskMode.TM_Module.STAGED in _TaskRegistry.registry_module


def test_register_obstacles_duplicate_raises():
    from task_generator.tasks.registry import _TaskRegistry
    from task_generator.constants import Constants
    with pytest.raises(AssertionError, match="already exists"):
        @_TaskRegistry.register_obstacles(Constants.TaskMode.TM_Obstacles.RANDOM)
        def _loader():
            pass


def test_register_robots_duplicate_raises():
    from task_generator.tasks.registry import _TaskRegistry
    from task_generator.constants import Constants
    with pytest.raises(AssertionError, match="already exists"):
        @_TaskRegistry.register_robots(Constants.TaskMode.TM_Robots.GUIDED)
        def _loader():
            pass


def test_register_module_duplicate_raises():
    from task_generator.tasks.registry import _TaskRegistry
    from task_generator.constants import Constants
    with pytest.raises(AssertionError, match="already exists"):
        @_TaskRegistry.register_module(Constants.TaskMode.TM_Module.STAGED)
        def _loader():
            pass


def test_obstacles_loader_is_callable():
    from task_generator.tasks.registry import _TaskRegistry
    from task_generator.constants import Constants
    loader, namespace = _TaskRegistry.registry_obstacles[Constants.TaskMode.TM_Obstacles.RANDOM]
    assert callable(loader)


def test_robots_loader_is_callable():
    from task_generator.tasks.registry import _TaskRegistry
    from task_generator.constants import Constants
    loader, namespace = _TaskRegistry.registry_robots[Constants.TaskMode.TM_Robots.RANDOM]
    assert callable(loader)


def test_module_loader_is_callable():
    from task_generator.tasks.registry import _TaskRegistry
    from task_generator.constants import Constants
    loader, namespace = _TaskRegistry.registry_module[Constants.TaskMode.TM_Module.STAGED]
    assert callable(loader)


def test_obstacles_namespace_contains_value():
    from task_generator.tasks.registry import _TaskRegistry
    from task_generator.constants import Constants
    _, namespace = _TaskRegistry.registry_obstacles[Constants.TaskMode.TM_Obstacles.RANDOM]
    assert "random" in str(namespace)


def test_robots_namespace_contains_value():
    from task_generator.tasks.registry import _TaskRegistry
    from task_generator.constants import Constants
    _, namespace = _TaskRegistry.registry_robots[Constants.TaskMode.TM_Robots.SCENARIO]
    assert "scenario" in str(namespace)


def test_obstacles_loader_returns_class():
    from task_generator.tasks.registry import _TaskRegistry
    from task_generator.constants import Constants
    loader, _ = _TaskRegistry.registry_obstacles[Constants.TaskMode.TM_Obstacles.RANDOM]
    cls = loader()
    assert isinstance(cls, type)


def test_robots_loader_returns_class():
    from task_generator.tasks.registry import _TaskRegistry
    from task_generator.constants import Constants
    loader, _ = _TaskRegistry.registry_robots[Constants.TaskMode.TM_Robots.RANDOM]
    cls = loader()
    assert isinstance(cls, type)
