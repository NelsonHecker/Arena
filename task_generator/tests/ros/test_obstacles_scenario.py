from __future__ import annotations

import asyncio
from types import SimpleNamespace
from unittest.mock import MagicMock, patch

import pytest


@pytest.fixture(autouse=True)
def _ros_gate():
    try:
        import rclpy  # noqa: F401
    except ImportError:
        pytest.skip("ROS2 not available")


class _FakeConf:
    class Robot:
        class TIMEOUT:
            value = 60
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


class _FakeLogger:
    def get_child(self, name):
        return self
    def debug(self, *a, **kw): ...
    def info(self, *a, **kw): ...
    def warn(self, *a, **kw): ...
    def error(self, *a, **kw): ...


def _make_static():
    from arena_simulation_setup.shared import Obstacle
    from arena_simulation_setup.utils.geometry import Pose, Position
    return Obstacle(name="s1", pose=Pose(Position(0, 0)), model="box", extra={})


def _make_dynamic():
    from arena_simulation_setup.shared import DynamicObstacle
    from arena_simulation_setup.utils.geometry import Pose, Position
    return DynamicObstacle(name="d1", pose=Pose(Position(0, 0)), model="human", waypoints=[], extra={})


def _make_scenario(static_list=None, dynamic_list=None):
    from arena_simulation_setup.tree.World.Scenario import Scenario
    return Scenario(
        static=static_list or [],
        dynamic=dynamic_list or [],
        robots=[],
    )


def _build_tm_scenario(fake_scenario, world_name="test_world"):
    from task_generator.tasks.obstacles.scenario.impl import TM_Scenario
    from arena_rclpy_mixins.shared import Namespace

    node = SimpleNamespace(
        conf=_FakeConf(),
        sim_time=SimpleNamespace(sec=0),
        get_logger=lambda: _FakeLogger(),
    )

    ctx = SimpleNamespace(
        robots_manager=SimpleNamespace(managers={}),
        environment_manager=SimpleNamespace(realize=lambda x: x),
        world_manager=SimpleNamespace(loaded_world=world_name),
    )

    tm = TM_Scenario.__new__(TM_Scenario)
    tm._NodeInterface__node = node
    tm._ctx = ctx
    tm._namespace = Namespace("test")
    tm._config = SimpleNamespace(value=fake_scenario)
    return tm


def test_reset_returns_static_and_dynamic():
    static = [_make_static()]
    dynamic = [_make_dynamic()]
    scenario = _make_scenario(static, dynamic)
    tm = _build_tm_scenario(scenario)

    result = asyncio.run(tm.reset())
    assert result[0] is static
    assert result[1] is dynamic


def test_reset_returns_empty_lists():
    scenario = _make_scenario([], [])
    tm = _build_tm_scenario(scenario)

    result = asyncio.run(tm.reset())
    assert result == ([], [])


def test_parse_scenario_calls_world_identifier():
    from arena_simulation_setup.tree.World.Scenario import Scenario

    fake_scenario = _make_scenario([_make_static()], [_make_dynamic()])

    with patch("task_generator.tasks.obstacles.scenario.impl.WorldIdentifier") as mock_wi:
        mock_wi.return_value.resolve_sync.return_value.scenario.return_value.resolve_sync.return_value.load.return_value = fake_scenario

        from task_generator.tasks.obstacles.scenario.impl import TM_Scenario
        from arena_rclpy_mixins.shared import Namespace

        node = SimpleNamespace(
            conf=_FakeConf(),
            sim_time=SimpleNamespace(sec=0),
            get_logger=lambda: _FakeLogger(),
        )
        ctx = SimpleNamespace(
            robots_manager=SimpleNamespace(managers={}),
            environment_manager=SimpleNamespace(realize=lambda x: x),
            world_manager=SimpleNamespace(loaded_world="test_world"),
        )
        tm = TM_Scenario.__new__(TM_Scenario)
        tm._NodeInterface__node = node
        tm._ctx = ctx
        tm._namespace = Namespace("test")

        result = tm._parse_scenario("default.json")
        assert result is fake_scenario


def test_init_default_scenario_exists():
    with patch("task_generator.tasks.obstacles.scenario.impl.WorldIdentifier") as mock_wi:
        mock_wi.return_value.resolve_sync.return_value.scenario.listall.return_value = [
            SimpleNamespace(shortname="default"),
            SimpleNamespace(shortname="scenario2"),
        ]

        with patch("task_generator.tasks.obstacles.scenario.impl.identifier_to_available") as mock_ita:
            mock_ita.return_value = ["default", "scenario2"]

            from task_generator.tasks.obstacles.scenario.impl import TM_Scenario
            from arena_rclpy_mixins.shared import Namespace

            fake_scenario = _make_scenario()

            class _FakeROSParam:
                def __class_getitem__(cls, item):
                    class _P:
                        def __call__(self, ns, default, parse):
                            return SimpleNamespace(value=parse(default))
                    return _P()

            node = SimpleNamespace(
                conf=_FakeConf(),
                sim_time=SimpleNamespace(sec=0),
                get_logger=lambda: _FakeLogger(),
                ROSParam=_FakeROSParam,
            )
            ctx = SimpleNamespace(
                robots_manager=SimpleNamespace(managers={}),
                environment_manager=SimpleNamespace(realize=lambda x: x),
                world_manager=SimpleNamespace(loaded_world="test_world"),
            )

            mock_wi.return_value.resolve_sync.return_value.scenario.return_value.resolve_sync.return_value.load.return_value = fake_scenario

            tm = TM_Scenario.__new__(TM_Scenario)
            tm._NodeInterface__node = node
            tm._ctx = ctx
            tm._namespace = Namespace("test")
            TM_Scenario.__init__(tm, node=node, ctx=ctx, namespace=Namespace("test"))


def test_init_no_scenarios_raises():
    with patch("task_generator.tasks.obstacles.scenario.impl.WorldIdentifier") as mock_wi:
        with patch("task_generator.tasks.obstacles.scenario.impl.identifier_to_available") as mock_ita:
            mock_ita.return_value = []

            from task_generator.tasks.obstacles.scenario.impl import TM_Scenario
            from arena_rclpy_mixins.shared import Namespace

            node = SimpleNamespace(
                conf=_FakeConf(),
                sim_time=SimpleNamespace(sec=0),
                get_logger=lambda: _FakeLogger(),
            )
            ctx = SimpleNamespace(
                robots_manager=SimpleNamespace(managers={}),
                environment_manager=SimpleNamespace(realize=lambda x: x),
                world_manager=SimpleNamespace(loaded_world="empty_world"),
            )

            with pytest.raises(ValueError, match="No scenarios found"):
                TM_Scenario.__init__(
                    TM_Scenario.__new__(TM_Scenario),
                    node=node,
                    ctx=ctx,
                    namespace=Namespace("test"),
                )
