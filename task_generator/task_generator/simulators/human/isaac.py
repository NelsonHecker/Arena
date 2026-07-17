import typing

from arena_runtime.sim import BaseSim
from arena_runtime.sim.isaac_simulator import IsaacSimulator

from task_generator.simulators.human.dummy import DummyHumanSimulator


class IsaacHumanSimulator(DummyHumanSimulator):
    def __init__(self, *args: object, simulator: BaseSim, **kwargs: object) -> None:
        if not isinstance(simulator, IsaacSimulator):
            raise ValueError("IsaacEntityManager only works with IsaacSimulator")
        super().__init__(*args, simulator=simulator, **kwargs)
        self._simulator = typing.cast(IsaacSimulator, self._simulator)

        self._walls: list[str] = []
