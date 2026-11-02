from __future__ import annotations

import asyncio

import pytest

pytest.importorskip("arena_humansim_msgs.msg")

from arena_humansim_msgs.srv import ResetSimulation
from arena_runtime._node import NodeInterface
from rcl_interfaces.msg import Parameter, ParameterType, ParameterValue, SetParametersResult
from rcl_interfaces.srv import SetParametersAtomically

from task_generator.simulators.human.arena_humansim.arena_humansim import ROBOTS_VISIBLE, ArenaHumanSimulator, split_robots_visible


def _bool(name: str, value: bool) -> Parameter:
    return Parameter(name=name, value=ParameterValue(type=ParameterType.PARAMETER_BOOL, bool_value=value))


def _double(name: str, value: float) -> Parameter:
    return Parameter(name=name, value=ParameterValue(type=ParameterType.PARAMETER_DOUBLE, double_value=value))


class _EngineClient:
    def __init__(self, response: SetParametersAtomically.Response | None) -> None:
        self._response = response
        self.requests: list[SetParametersAtomically.Request] = []

    async def call_timeout(self, request: SetParametersAtomically.Request) -> SetParametersAtomically.Response | None:
        self.requests.append(request)
        return self._response


class _ResetClient:
    def __init__(self) -> None:
        self.requests: list[ResetSimulation.Request] = []

    async def call_timeout(self, request: ResetSimulation.Request) -> None:
        self.requests.append(request)


class _Logger:
    def __init__(self) -> None:
        self.errors: list[str] = []

    def get_child(self, name: str) -> _Logger:
        return self

    def error(self, message: str) -> None:
        self.errors.append(message)


class _Node:
    def __init__(self, root_logger: _Logger) -> None:
        self._root_logger = root_logger

    def get_logger(self) -> _Logger:
        return self._root_logger


def _simulator(robots_visible: bool, engine: _EngineClient) -> tuple[ArenaHumanSimulator, _ResetClient, _Logger]:
    logger = _Logger()
    reset = _ResetClient()
    sim = object.__new__(ArenaHumanSimulator)
    # _logger is a read-only property of NodeInterface, so the node comes in through its initializer
    NodeInterface.__init__(sim, node=_Node(logger))
    sim._robots_visible = robots_visible
    sim._set_params_client = engine
    sim._reset_client = reset
    return sim, reset, logger


def test_robots_visible_is_taken_out_of_the_engine_params() -> None:
    visible, rest, rejected = split_robots_visible([_double("global_planner.resolution", 0.1), _bool(ROBOTS_VISIBLE, False)])
    assert visible is False
    assert [p.name for p in rest] == ["global_planner.resolution"]
    assert rejected == []


def test_robots_visible_true_is_taken_out_of_the_engine_params() -> None:
    visible, rest, rejected = split_robots_visible([_double("global_planner.resolution", 0.1), _bool(ROBOTS_VISIBLE, True)])
    assert visible is True
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


def test_robots_visible_alone_is_applied_accepted_and_followed_by_a_reset() -> None:
    engine = _EngineClient(None)
    sim, reset, logger = _simulator(robots_visible=True, engine=engine)
    accepted = asyncio.run(sim._configure_impl([_bool(ROBOTS_VISIBLE, False)]))
    assert accepted == {ROBOTS_VISIBLE}
    assert sim._robots_visible is False
    assert engine.requests == []
    assert [request.soft for request in reset.requests] == [True]
    assert logger.errors == []


def test_an_accepted_engine_batch_applies_robots_visible_with_its_params() -> None:
    engine = _EngineClient(SetParametersAtomically.Response(result=SetParametersResult(successful=True)))
    sim, reset, logger = _simulator(robots_visible=True, engine=engine)
    accepted = asyncio.run(sim._configure_impl([_double("global_planner.resolution", 0.1), _bool(ROBOTS_VISIBLE, False)]))
    assert accepted == {"global_planner.resolution", ROBOTS_VISIBLE}
    assert sim._robots_visible is False
    assert [p.name for p in engine.requests[0].parameters] == ["global_planner.resolution"]
    assert [request.soft for request in reset.requests] == [True]
    assert logger.errors == []


def test_a_rejected_engine_batch_applies_no_robots_visible_and_logs_the_engine_reason() -> None:
    engine = _EngineClient(SetParametersAtomically.Response(result=SetParametersResult(successful=False, reason="no such parameter")))
    sim, reset, logger = _simulator(robots_visible=True, engine=engine)
    accepted = asyncio.run(sim._configure_impl([_double("global_planner.resolution", 0.1), _bool(ROBOTS_VISIBLE, False)]))
    assert accepted == set()
    assert sim._robots_visible is True
    assert logger.errors == ["engine rejected human params ['global_planner.resolution']: no such parameter"]
    assert [request.soft for request in reset.requests] == [True]


def test_a_timed_out_engine_batch_applies_no_robots_visible_and_logs_the_timeout() -> None:
    engine = _EngineClient(None)
    sim, reset, logger = _simulator(robots_visible=True, engine=engine)
    accepted = asyncio.run(sim._configure_impl([_double("global_planner.resolution", 0.1), _bool(ROBOTS_VISIBLE, False)]))
    assert accepted == set()
    assert sim._robots_visible is True
    assert logger.errors == ["engine rejected human params ['global_planner.resolution']: timeout"]
    assert [request.soft for request in reset.requests] == [True]
