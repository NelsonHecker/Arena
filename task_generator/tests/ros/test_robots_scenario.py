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
    def __init__(self):
        self.warns = []
    def get_child(self, name):
        return self
    def debug(self, *a, **kw): ...
    def info(self, *a, **kw): ...
    def warn(self, msg, *a, **kw):
        self.warns.append(msg)
    def warning(self, *a, **kw): ...
    def error(self, *a, **kw): ...


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


def _make_robot_goal(start_x=0.0, start_y=0.0, goal_x=5.0, goal_y=5.0):
    from arena_simulation_setup.tree.World.Scenario import RobotGoal
    from arena_simulation_setup.utils.geometry import Pose, Position, Orientation
    return RobotGoal(
        start=Pose(Position(start_x, start_y), Orientation.from_yaw(0.0)),
        goal=Pose(Position(goal_x, goal_y), Orientation.from_yaw(0.0)),
    )


def _make_scenario_tm(node, robots_dict, scenario_robots, world_name="test_world"):
    from task_generator.tasks.robots.scenario.impl import TM_Scenario
    from arena_rclpy_mixins.shared import Namespace

    logger = _FakeLogger()
    node.get_logger = lambda: logger

    ctx = SimpleNamespace(
        robots_manager=SimpleNamespace(managers=robots_dict),
        robots=robots_dict,
        environment_manager=SimpleNamespace(realize=lambda x: x),
        world_manager=SimpleNamespace(
            world_name=world_name,
            forbid=lambda poses: None,
        ),
    )

    fake_param = SimpleNamespace(value=scenario_robots)

    with patch("task_generator.tasks.robots.scenario.impl.WorldIdentifier") as mock_wi:
        tm = TM_Scenario.__new__(TM_Scenario)
        tm._NodeInterface__node = node
        tm._ctx = ctx
        tm._namespace = Namespace("test")
        tm._last_reset = 0
        tm._config = fake_param
        return tm, logger, ctx


def _make_robot_manager_stub(name="robot1", safe_distance=0.5):
    return SimpleNamespace(
        name=name,
        safe_distance=safe_distance,
        move=AsyncMock(return_value=None),
        submit_task=AsyncMock(return_value=None),
    )


def test_reset_zip_alignment_preserved():
    node = SimpleNamespace(
        conf=_FakeConf(),
        sim_time=SimpleNamespace(sec=0),
        get_logger=lambda: _FakeLogger(),
    )
    rg1 = _make_robot_goal(start_x=1.0, goal_x=10.0)
    rg2 = _make_robot_goal(start_x=2.0, goal_x=20.0)

    rm1 = _make_robot_manager_stub("r1")
    rm2 = _make_robot_manager_stub("r2")
    robots_dict = {"r1": rm1, "r2": rm2}

    tm, logger, ctx = _make_scenario_tm(node, robots_dict, [rg1, rg2])
    asyncio.run(tm.reset())

    rm1.move.assert_called_once()
    rm2.move.assert_called_once()
    rm1.submit_task.assert_called_once()
    rm2.submit_task.assert_called_once()


def test_reset_more_setup_than_scenario_warns_and_truncates():
    node = SimpleNamespace(
        conf=_FakeConf(),
        sim_time=SimpleNamespace(sec=0),
        get_logger=lambda: _FakeLogger(),
    )
    rg1 = _make_robot_goal()
    rm1 = _make_robot_manager_stub("r1")
    rm2 = _make_robot_manager_stub("r2")
    robots_dict = {"r1": rm1, "r2": rm2}

    tm, logger, ctx = _make_scenario_tm(node, robots_dict, [rg1])
    asyncio.run(tm.reset())

    assert any("more robots" in w.lower() for w in logger.warns)
    rm1.move.assert_called_once()
    rm2.move.assert_not_called()


def test_reset_more_scenario_than_setup_warns_and_truncates():
    node = SimpleNamespace(
        conf=_FakeConf(),
        sim_time=SimpleNamespace(sec=0),
        get_logger=lambda: _FakeLogger(),
    )
    rg1 = _make_robot_goal()
    rg2 = _make_robot_goal(start_x=5.0)
    rm1 = _make_robot_manager_stub("r1")
    robots_dict = {"r1": rm1}

    tm, logger, ctx = _make_scenario_tm(node, robots_dict, [rg1, rg2])
    asyncio.run(tm.reset())

    assert any("more robots" in w.lower() for w in logger.warns)
    rm1.move.assert_called_once()


def test_reset_equal_counts_no_warn():
    node = SimpleNamespace(
        conf=_FakeConf(),
        sim_time=SimpleNamespace(sec=0),
        get_logger=lambda: _FakeLogger(),
    )
    rg1 = _make_robot_goal()
    rm1 = _make_robot_manager_stub("r1")
    robots_dict = {"r1": rm1}

    tm, logger, ctx = _make_scenario_tm(node, robots_dict, [rg1])
    asyncio.run(tm.reset())

    assert len(logger.warns) == 0


def test_reset_calls_forbid_for_each_robot():
    node = SimpleNamespace(
        conf=_FakeConf(),
        sim_time=SimpleNamespace(sec=0),
        get_logger=lambda: _FakeLogger(),
    )
    rg1 = _make_robot_goal()
    rm1 = _make_robot_manager_stub("r1")
    robots_dict = {"r1": rm1}

    forbid_calls = []
    ctx_extras = {}

    tm, logger, ctx = _make_scenario_tm(node, robots_dict, [rg1])
    ctx.world_manager.forbid = lambda poses: forbid_calls.append(poses)

    asyncio.run(tm.reset())
    assert len(forbid_calls) == 1


def test_parse_scenario_calls_world_identifier():
    from arena_simulation_setup.tree.World.Scenario import RobotGoal, Scenario
    from arena_simulation_setup.utils.geometry import Pose

    node = SimpleNamespace(
        conf=_FakeConf(),
        sim_time=SimpleNamespace(sec=0),
        get_logger=lambda: _FakeLogger(),
    )

    robots_dict = {}
    fake_robots = [_make_robot_goal()]
    fake_scenario = Scenario(static=[], dynamic=[], robots=fake_robots)
    fake_load = SimpleNamespace(robots=fake_robots)

    with patch("task_generator.tasks.robots.scenario.impl.WorldIdentifier") as mock_wi:
        mock_wi.return_value.resolve_sync.return_value.scenario.return_value.resolve_sync.return_value.load.return_value = fake_load

        from task_generator.tasks.robots.scenario.impl import TM_Scenario
        from arena_rclpy_mixins.shared import Namespace

        ctx = SimpleNamespace(
            robots_manager=SimpleNamespace(managers=robots_dict),
            environment_manager=SimpleNamespace(realize=lambda x: x),
            world_manager=SimpleNamespace(world_name="test_world", forbid=lambda x: None),
        )

        tm = TM_Scenario.__new__(TM_Scenario)
        tm._NodeInterface__node = node
        tm._ctx = ctx
        tm._namespace = Namespace("test")

        result = tm._parse_scenario("default")
        assert result == fake_robots
