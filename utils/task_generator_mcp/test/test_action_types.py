"""Test: RunEpisode action goal/result/feedback types instantiate and carry expected fields."""
from task_generator_msgs.action import RunEpisode


def test_goal_has_world_field():
    goal = RunEpisode.Goal()
    goal.world = "empty_map"
    assert goal.world == "empty_map"


def test_goal_default_world_is_empty():
    goal = RunEpisode.Goal()
    assert goal.world == ""


def test_result_state_constants():
    assert RunEpisode.Result.SUCCESS == 1
    assert RunEpisode.Result.FAILED == 2
    assert RunEpisode.Result.SKIPPED == 3


def test_result_fields():
    result = RunEpisode.Result()
    result.state = RunEpisode.Result.SUCCESS
    result.reason = "finished"
    result.episode_id = 42
    assert result.state == 1
    assert result.reason == "finished"
    assert result.episode_id == 42


def test_feedback_state_constant():
    assert RunEpisode.Feedback.STARTED == 1


def test_feedback_field():
    fb = RunEpisode.Feedback()
    fb.state = RunEpisode.Feedback.STARTED
    assert fb.state == 1


def test_state_name_mapping():
    from task_generator_mcp.tools import _RUN_EPISODE_STATE_NAMES

    assert _RUN_EPISODE_STATE_NAMES[RunEpisode.Result.SUCCESS] == "SUCCESS"
    assert _RUN_EPISODE_STATE_NAMES[RunEpisode.Result.FAILED] == "FAILED"
    assert _RUN_EPISODE_STATE_NAMES[RunEpisode.Result.SKIPPED] == "SKIPPED"
