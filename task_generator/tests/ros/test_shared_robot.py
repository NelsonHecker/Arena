from __future__ import annotations

from types import SimpleNamespace

import pytest


@pytest.fixture(autouse=True)
def _ros_gate():
    try:
        import rclpy  # noqa: F401
    except ImportError:
        pytest.skip("ROS2 not available")


@pytest.fixture()
def stub_node():
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

    return SimpleNamespace(
        conf=_FakeConf(),
        sim_time=SimpleNamespace(sec=0),
        get_logger=lambda: _FakeLogger(),
    )


def _make_robot(name, model_name, lp="dwa", gp="navfn", agent="rosnav", navigator="nav2"):
    from task_generator.shared import Robot, Pose
    from arena_robots.Robot import RobotIdentifier
    return Robot(
        name=name,
        pose=Pose(),
        model=RobotIdentifier.parse(model_name),
        inter_planner="rosnav",
        local_planner=lp,
        global_planner=gp,
        agent=agent,
        navigator=navigator,
        extra={},
    )


def test_compatible_same_config():
    r1 = _make_robot("r1", "turtlebot3_burger")
    r2 = _make_robot("r2", "turtlebot3_burger")
    assert r1.compatible(r2) is True


def test_compatible_different_model():
    r1 = _make_robot("r1", "turtlebot3_burger")
    r2 = _make_robot("r2", "jackal")
    assert r1.compatible(r2) is False


def test_compatible_different_local_planner():
    r1 = _make_robot("r1", "turtlebot3_burger", lp="dwa")
    r2 = _make_robot("r2", "turtlebot3_burger", lp="teb")
    assert r1.compatible(r2) is False


def test_compatible_different_global_planner():
    r1 = _make_robot("r1", "turtlebot3_burger", gp="navfn")
    r2 = _make_robot("r2", "turtlebot3_burger", gp="smac")
    assert r1.compatible(r2) is False


def test_compatible_different_agent():
    r1 = _make_robot("r1", "turtlebot3_burger", agent="rosnav")
    r2 = _make_robot("r2", "turtlebot3_burger", agent="rl_agent")
    assert r1.compatible(r2) is False


def test_compatible_different_navigator():
    r1 = _make_robot("r1", "turtlebot3_burger", navigator="nav2")
    r2 = _make_robot("r2", "turtlebot3_burger", navigator="none")
    assert r1.compatible(r2) is False


def test_parse_uses_conf_defaults_when_keys_missing(stub_node):
    from task_generator.shared import Robot
    value = {"name": "bot1", "model": "turtlebot3_burger"}
    robot = Robot.parse(value, node=stub_node)
    assert robot.local_planner == "dwa"
    assert robot.global_planner == "navfn"
    assert robot.agent == "rosnav"
    assert robot.navigator == "nav2"
    assert robot.record_data_dir is None


def test_parse_explicit_values_override_conf(stub_node):
    from task_generator.shared import Robot
    value = {
        "name": "bot2",
        "model": "turtlebot3_burger",
        "local_planner": "teb",
        "global_planner": "smac",
        "agent": "custom_agent",
        "navigator": "none",
    }
    robot = Robot.parse(value, node=stub_node)
    assert robot.local_planner == "teb"
    assert robot.global_planner == "smac"
    assert robot.agent == "custom_agent"
    assert robot.navigator == "none"


def test_parse_extra_dict_preserved(stub_node):
    from task_generator.shared import Robot
    value = {"name": "bot3", "model": "turtlebot3_burger", "custom_key": "custom_val"}
    robot = Robot.parse(value, node=stub_node)
    assert "custom_key" in robot.extra
    assert robot.extra["custom_key"] == "custom_val"


def test_parse_name_set_correctly(stub_node):
    from task_generator.shared import Robot
    value = {"name": "my_robot", "model": "turtlebot3_burger"}
    robot = Robot.parse(value, node=stub_node)
    assert robot.name == "my_robot"


def test_parse_default_pos_is_zero(stub_node):
    from task_generator.shared import Robot
    value = {"name": "bot4", "model": "turtlebot3_burger"}
    robot = Robot.parse(value, node=stub_node)
    assert robot.pose.position.x == 0.0
    assert robot.pose.position.y == 0.0


def test_frame_sim_path_branch():
    from task_generator.shared import Robot, Pose
    from arena_robots.Robot import RobotIdentifier
    robot = Robot(
        name="r",
        pose=Pose(),
        model=RobotIdentifier.parse("turtlebot3_burger"),
        inter_planner="x",
        local_planner="x",
        global_planner="x",
        agent="x",
        extra={},
    )
    robot.sim_path = "simulation/r"
    frame = robot.frame
    assert "simulation/r" in str(frame)


def test_frame_name_fallback():
    from task_generator.shared import Robot, Pose
    from arena_robots.Robot import RobotIdentifier
    robot = Robot(
        name="robot_a",
        pose=Pose(),
        model=RobotIdentifier.parse("turtlebot3_burger"),
        inter_planner="x",
        local_planner="x",
        global_planner="x",
        agent="x",
        extra={},
    )
    frame = robot.frame
    assert "robot_a" in str(frame)


def test_from_setup_delegates_to_parse(stub_node):
    from task_generator.shared import Robot
    from arena_robots.SetupFile import Config
    setup = Config(robot="turtlebot3_burger", name="setup_bot")
    robot = Robot.from_setup(setup, node=stub_node)
    assert robot.name == "setup_bot"
    assert robot.model.name == "turtlebot3_burger"


def test_eq_equal_when_all_fields_match():
    r1 = _make_robot("bot", "turtlebot3_burger")
    r2 = _make_robot("bot", "turtlebot3_burger")
    assert r1 == r2


def test_eq_not_equal_when_name_differs():
    r1 = _make_robot("bot_a", "turtlebot3_burger")
    r2 = _make_robot("bot_b", "turtlebot3_burger")
    assert r1 != r2


def test_eq_not_equal_when_model_differs():
    r1 = _make_robot("bot", "turtlebot3_burger")
    r2 = _make_robot("bot", "jackal")
    assert r1 != r2


def test_eq_not_equal_when_record_data_dir_differs():
    from task_generator.shared import Robot, Pose
    from arena_robots.Robot import RobotIdentifier
    r1 = Robot(
        name="bot",
        pose=Pose(),
        model=RobotIdentifier.parse("turtlebot3_burger"),
        inter_planner="rosnav",
        local_planner="dwa",
        global_planner="navfn",
        agent="rosnav",
        navigator="nav2",
        extra={},
        record_data_dir="/tmp/a",
    )
    r2 = Robot(
        name="bot",
        pose=Pose(),
        model=RobotIdentifier.parse("turtlebot3_burger"),
        inter_planner="rosnav",
        local_planner="dwa",
        global_planner="navfn",
        agent="rosnav",
        navigator="nav2",
        extra={},
        record_data_dir="/tmp/b",
    )
    assert r1 != r2


def test_eq_not_equal_to_non_robot():
    r = _make_robot("bot", "turtlebot3_burger")
    assert (r == "some string") is False


def test_frame_empty_name_fallback_to_empty_string():
    from task_generator.shared import Robot, Pose
    from arena_robots.Robot import RobotIdentifier
    robot = Robot(
        name="",
        pose=Pose(),
        model=RobotIdentifier.parse("turtlebot3_burger"),
        inter_planner="x",
        local_planner="x",
        global_planner="x",
        agent="x",
        extra={},
    )
    assert str(robot.frame) == ""
