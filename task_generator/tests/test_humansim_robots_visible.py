from __future__ import annotations

import pytest

pytest.importorskip("arena_humansim_msgs.msg")

from rcl_interfaces.msg import Parameter, ParameterType, ParameterValue

from task_generator.simulators.human.arena_humansim.arena_humansim import ROBOTS_VISIBLE, split_robots_visible


def _bool(name: str, value: bool) -> Parameter:
    return Parameter(name=name, value=ParameterValue(type=ParameterType.PARAMETER_BOOL, bool_value=value))


def _double(name: str, value: float) -> Parameter:
    return Parameter(name=name, value=ParameterValue(type=ParameterType.PARAMETER_DOUBLE, double_value=value))


def test_robots_visible_is_taken_out_of_the_engine_params() -> None:
    visible, rest, rejected = split_robots_visible([_double("global_planner.resolution", 0.1), _bool(ROBOTS_VISIBLE, False)])
    assert visible is False
    assert [p.name for p in rest] == ["global_planner.resolution"]
    assert rejected == []


def test_without_robots_visible_every_param_goes_to_the_engine() -> None:
    visible, rest, rejected = split_robots_visible([_double("global_planner.resolution", 0.1)])
    assert visible is None
    assert [p.name for p in rest] == ["global_planner.resolution"]
    assert rejected == []


def test_a_non_bool_robots_visible_is_rejected() -> None:
    visible, rest, rejected = split_robots_visible([_double(ROBOTS_VISIBLE, 0.0)])
    assert visible is None
    assert rest == []
    assert rejected == [ROBOTS_VISIBLE]
