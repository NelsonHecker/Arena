"""Auditory simulator axis: `auditory:=<backend>` selects the sidecar launched next to the human simulator."""

from __future__ import annotations

import abc
import typing

from arena_rclpy_mixins.registry import AsyncFactoryRegistry as Registry
from arena_rclpy_mixins.shared import Namespace
from arena_runtime._node import NodeInterface
from task_generator_msgs.msg import AdapterDisplay

from task_generator.constants import Constants

if typing.TYPE_CHECKING:
    from task_generator.simulators.auditory.arena import PedestrianHearing
    from task_generator.simulators.human import BaseHumanSimulator


class BaseAuditorySimulator(NodeInterface, abc.ABC):
    """Node-side counterpart of the auditory sidecar. Declares what the task generator must provide for it."""

    def __init__(self, *args: object, namespace: Namespace, **kwargs: object) -> None:
        super().__init__(*args, **kwargs)
        self._namespace = namespace

    @property
    @abc.abstractmethod
    def requires_map_server(self) -> bool:
        """Whether the sidecar reads the map server (acoustic scene from the occupancy grid)."""

    def displays(self) -> tuple[AdapterDisplay, ...]:
        """Env-level rviz displays of the sidecar."""
        return ()

    def pedestrian_hearing(self, human: BaseHumanSimulator) -> PedestrianHearing | None:
        """Pedestrian hearing feeding the human simulator's stimuli, None when pedestrians hear nothing."""
        del human
        return None

    def robot_displays(self, robot: str, *, hearing: bool) -> tuple[AdapterDisplay, ...]:
        """Per-robot rviz displays, published as the robot's `_auditory` adapter entry, the hearing ones only when robot hearing runs."""
        del robot, hearing
        return ()


AuditorySimulatorRegistry = Registry[Constants.AuditorySimulator, BaseAuditorySimulator]()


@AuditorySimulatorRegistry.register(Constants.AuditorySimulator.NONE)
async def none(**kwargs: object) -> BaseAuditorySimulator:
    from .noop import NoopAuditorySimulator

    return NoopAuditorySimulator(**kwargs)


@AuditorySimulatorRegistry.register(Constants.AuditorySimulator.ARENA)
async def arena(**kwargs: object) -> BaseAuditorySimulator:
    from .arena import ArenaAuditorySimulator

    return ArenaAuditorySimulator(**kwargs)
