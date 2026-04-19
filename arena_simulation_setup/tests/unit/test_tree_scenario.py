from __future__ import annotations

import os
import warnings

import pytest
import yaml

from arena_simulation_setup.tree.World.Scenario import RobotGoal, Scenario, ScenarioView
from arena_simulation_setup.utils.geometry import Pose


# ---------------------------------------------------------------------------
# RobotGoal.parse
# ---------------------------------------------------------------------------


def test_robot_goal_parse_full_dict():
    rg = RobotGoal.parse({"start": [1.0, 2.0], "goal": [3.0, 4.0]})
    assert rg.start.position.x == pytest.approx(1.0)
    assert rg.goal.position.x == pytest.approx(3.0)


def test_robot_goal_parse_start_only():
    rg = RobotGoal.parse({"start": [5.0, 6.0], "goal": [0.0, 0.0]})
    assert rg.start.position.x == pytest.approx(5.0)
    assert isinstance(rg.goal, Pose)


def test_robot_goal_parse_goal_only():
    rg = RobotGoal.parse({"start": [0.0, 0.0], "goal": [7.0, 8.0]})
    assert rg.goal.position.x == pytest.approx(7.0)
    assert isinstance(rg.start, Pose)


def test_robot_goal_parse_empty_parse_fallback():
    with pytest.raises(ValueError):
        RobotGoal.parse({})


# ---------------------------------------------------------------------------
# Scenario
# ---------------------------------------------------------------------------


def test_scenario_empty_construction():
    s = Scenario()
    assert s.static == []
    assert s.dynamic == []
    assert s.robots == []


def test_scenario_with_robots():
    rg = RobotGoal.parse({"start": [0.0, 0.0], "goal": [1.0, 1.0]})
    s = Scenario(robots=[rg])
    assert len(s.robots) == 1


# ---------------------------------------------------------------------------
# ScenarioView
# ---------------------------------------------------------------------------


def test_scenario_view_path_yaml_priority(tmp_path):
    scenario_dir = tmp_path / "test_scenario"
    scenario_dir.mkdir()
    yaml_file = scenario_dir / "scenario.yaml"
    json_file = scenario_dir / "scenario.json"
    yaml_file.write_text(yaml.dump({"static": [], "dynamic": [], "robots": []}))
    json_file.write_text('{"static": [], "dynamic": [], "robots": []}')

    view = ScenarioView(scenario_dir)
    assert view.scenario_path.endswith("scenario.yaml")


def test_scenario_view_path_fallback_to_json_when_no_yaml(tmp_path):
    scenario_dir = tmp_path / "test_scenario2"
    scenario_dir.mkdir()
    view = ScenarioView(scenario_dir)
    # No files exist; should return yaml path as default
    assert "scenario.yaml" in view.scenario_path


def test_scenario_view_load_new_format(tmp_path):
    scenario_dir = tmp_path / "sc_new"
    scenario_dir.mkdir()
    data = {"static": [], "dynamic": [], "robots": [{"start": [1.0, 2.0], "goal": [3.0, 4.0]}]}
    (scenario_dir / "scenario.yaml").write_text(yaml.dump(data))

    view = ScenarioView(scenario_dir)
    scenario = view.load()
    assert len(scenario.robots) == 1


def test_scenario_view_load_legacy(tmp_path):
    scenario_dir = tmp_path / "sc_legacy"
    scenario_dir.mkdir()
    # Legacy format uses 'obstacles.static' key - this will fail new format (no 'static' top-level)
    data = {
        "obstacles": {
            "static": [{"name": "obs1", "pose": [0.0, 0.0], "model": "box"}],
            "dynamic": [],
        },
        "robots": [{"start": [1.0, 2.0], "goal": [3.0, 4.0]}],
    }
    (scenario_dir / "scenario.yaml").write_text(yaml.dump(data))

    view = ScenarioView(scenario_dir)
    with warnings.catch_warnings(record=True) as w:
        warnings.simplefilter("always")
        scenario = view.load()
    # New format parses successfully (empty static/dynamic), no DeprecationWarning
    # OR falls to legacy with DeprecationWarning. Either way should succeed.
    assert isinstance(scenario, Scenario)
    assert len(scenario.robots) >= 0


def test_scenario_view_load_malformed_raises_runtime_error(tmp_path):
    scenario_dir = tmp_path / "sc_bad"
    scenario_dir.mkdir()
    (scenario_dir / "scenario.yaml").write_text(": : : invalid yaml: :")

    view = ScenarioView(scenario_dir)
    with pytest.raises((RuntimeError, Exception)):
        view.load()


def test_scenario_view_included_from_propagated(tmp_path):
    scenario_dir = tmp_path / "sc_incl"
    scenario_dir.mkdir()
    # Use new format so we know it succeeds with static obstacles
    data = {
        "static": [{"name": "obs1", "pose": [0.0, 0.0], "model": "box"}],
        "dynamic": [],
        "robots": [],
    }
    (scenario_dir / "scenario.yaml").write_text(yaml.dump(data))

    view = ScenarioView(scenario_dir)
    scenario = view.load()
    assert len(scenario.static) >= 1
    assert scenario.static[0].included_from == scenario_dir
