"""Runtime semantic kinds reading door/elevator FSM facts as latched snapshots and per-change events."""

from __future__ import annotations

import abc
import math
import typing
from collections.abc import Callable, Sequence
from typing import ClassVar

import attrs

from ._mechanism_shim import _DoorState

if typing.TYPE_CHECKING:
    from arena_simulation_setup.shared.semantics import SemanticCfg

    from ._interface import MechanismITF
    from ._mechanism_shim import _DoorRuntime, _ElevatorRuntime


@attrs.define
class SemanticEntitySnapshot:
    entity: str
    kind: str
    discrete: dict[str, str]
    continuous: dict[str, float]
    predicates: dict[str, bool]


@attrs.define
class SemanticChange:
    entity: str
    kind: str
    field_kind: str  # "state" | "predicate"
    field: str
    previous: str
    current: str


_SEMANTIC_KINDS: dict[str, type[SemanticKind]] = {}


def semantic_kind(name: str) -> Callable[[type[SemanticKind]], type[SemanticKind]]:
    """Register a SemanticKind subclass under name and set cls.KIND."""

    def register(cls: type[SemanticKind]) -> type[SemanticKind]:
        cls.KIND = name
        _SEMANTIC_KINDS[name] = cls
        return cls

    return register


def _stringify(value: str | float | bool | None) -> str:
    """Stringify a semantic value for the event stream. Missing prior value renders empty."""
    if value is None:
        return ''
    if isinstance(value, bool):
        return 'true' if value else 'false'
    return str(value)


class SemanticKind(abc.ABC):
    KIND: ClassVar[str]
    SUPPORTED_SIMS: ClassVar[frozenset[str]]

    DISCRETE: ClassVar[tuple[str, ...]] = ()
    CONTINUOUS: ClassVar[tuple[str, ...]] = ()
    PREDICATES: ClassVar[tuple[str, ...]] = ()

    def __init__(self, entity: str, discrete: tuple[str, ...], continuous: tuple[str, ...], predicates: tuple[str, ...]) -> None:
        self._entity = entity
        self._discrete = discrete
        self._continuous = continuous
        self._predicates = predicates
        self._now = -math.inf

    @classmethod
    def _classify(cls, cfgs: Sequence[SemanticCfg]) -> tuple[tuple[str, ...], tuple[str, ...], tuple[str, ...]]:
        """Split requested cfg names into this kind's discrete/continuous/predicate vocabulary."""
        discrete: list[str] = []
        continuous: list[str] = []
        predicates: list[str] = []
        for cfg in cfgs:
            if cfg.name in cls.DISCRETE:
                discrete.append(cfg.name)
            elif cfg.name in cls.CONTINUOUS:
                continuous.append(cfg.name)
            elif cfg.name in cls.PREDICATES:
                predicates.append(cfg.name)
            else:
                raise ValueError(f"{cls.KIND!r} semantics: unknown field {cfg.name!r}")
        return tuple(discrete), tuple(continuous), tuple(predicates)

    @classmethod
    @abc.abstractmethod
    def attach(cls, mech: MechanismITF, entity: str, cfgs: Sequence[SemanticCfg]) -> SemanticKind:
        """Bind to a spawned entity, ValueError on cfg names outside the kind vocabulary."""

    def step(self, now: float) -> None:
        self._now = now

    @abc.abstractmethod
    def reset(self) -> None: ...

    @abc.abstractmethod
    def snapshot(self) -> SemanticEntitySnapshot: ...


@semantic_kind('door')
class DoorSemantics(SemanticKind):
    SUPPORTED_SIMS = frozenset({'gazebo', 'isaac'})

    DISCRETE = ('state',)
    CONTINUOUS = ('progress',)
    PREDICATES = ('open', 'in_transit', 'triggered')

    def __init__(
        self,
        entity: str,
        runtime: _DoorRuntime,
        discrete: tuple[str, ...],
        continuous: tuple[str, ...],
        predicates: tuple[str, ...],
    ) -> None:
        super().__init__(entity, discrete, continuous, predicates)
        self._runtime = runtime

    @classmethod
    def attach(cls, mech: MechanismITF, entity: str, cfgs: Sequence[SemanticCfg]) -> SemanticKind:
        discrete, continuous, predicates = cls._classify(cfgs)
        return cls(entity, mech._door_runtime[entity], discrete, continuous, predicates)

    def reset(self) -> None:
        rt = self._runtime
        rt.state = _DoorState.CLOSED
        rt.progress = 0.0
        rt.last_trigger_sim_time = -math.inf
        rt.last_applied_progress = -1.0

    def snapshot(self) -> SemanticEntitySnapshot:
        rt = self._runtime
        discrete: dict[str, str] = {}
        continuous: dict[str, float] = {}
        predicates: dict[str, bool] = {}
        if 'state' in self._discrete:
            discrete['state'] = rt.state.value
        if 'progress' in self._continuous:
            continuous['progress'] = rt.progress
        if 'open' in self._predicates:
            predicates['open'] = rt.state == _DoorState.OPEN
        if 'in_transit' in self._predicates:
            predicates['in_transit'] = rt.state in (_DoorState.OPENING, _DoorState.CLOSING)
        if 'triggered' in self._predicates:
            predicates['triggered'] = (self._now - rt.last_trigger_sim_time) <= rt.door.hold_time
        return SemanticEntitySnapshot(self._entity, self.KIND, discrete, continuous, predicates)


@semantic_kind('elevator')
class ElevatorSemantics(SemanticKind):
    SUPPORTED_SIMS = frozenset({'gazebo', 'isaac'})

    CONTINUOUS = ('arriving_eta', 'occupants')
    PREDICATES = ('departing', 'in_transit', 'dispatched', 'just_arrived')

    def __init__(
        self,
        entity: str,
        runtime: _ElevatorRuntime,
        discrete: tuple[str, ...],
        continuous: tuple[str, ...],
        predicates: tuple[str, ...],
    ) -> None:
        super().__init__(entity, discrete, continuous, predicates)
        self._runtime = runtime

    @classmethod
    def attach(cls, mech: MechanismITF, entity: str, cfgs: Sequence[SemanticCfg]) -> SemanticKind:
        discrete, continuous, predicates = cls._classify(cfgs)
        return cls(entity, mech._elevator_runtime[entity], discrete, continuous, predicates)

    def reset(self) -> None:
        rt = self._runtime
        rt.arriving_eta = -math.inf
        rt.pending_occupants = ()
        rt.just_arrived = {}
        rt.departing = False
        rt.dispatched = set()

    def snapshot(self) -> SemanticEntitySnapshot:
        rt = self._runtime
        continuous: dict[str, float] = {}
        predicates: dict[str, bool] = {}
        if 'arriving_eta' in self._continuous:
            continuous['arriving_eta'] = max(0.0, rt.arriving_eta - self._now) if rt.arriving_eta > -math.inf else -1.0
        if 'occupants' in self._continuous:
            continuous['occupants'] = float(len(rt.dispatched) + len(rt.pending_occupants) + len(rt.just_arrived))
        if 'departing' in self._predicates:
            predicates['departing'] = rt.departing
        if 'in_transit' in self._predicates:
            predicates['in_transit'] = rt.arriving_eta > -math.inf
        if 'dispatched' in self._predicates:
            predicates['dispatched'] = bool(rt.dispatched)
        if 'just_arrived' in self._predicates:
            predicates['just_arrived'] = bool(rt.just_arrived)
        return SemanticEntitySnapshot(self._entity, self.KIND, {}, continuous, predicates)


def _diff(prev: SemanticEntitySnapshot | None, snap: SemanticEntitySnapshot) -> list[SemanticChange]:
    """Emit one SemanticChange per field whose value differs from the previous snapshot."""
    prev_discrete = prev.discrete if prev is not None else {}
    prev_continuous = prev.continuous if prev is not None else {}
    prev_predicates = prev.predicates if prev is not None else {}
    changes: list[SemanticChange] = []
    for name, value in snap.discrete.items():
        old = prev_discrete.get(name)
        if old != value:
            changes.append(SemanticChange(snap.entity, snap.kind, 'state', name, _stringify(old), _stringify(value)))
    for name, fvalue in snap.continuous.items():
        fold = prev_continuous.get(name)
        if fold != fvalue:
            changes.append(SemanticChange(snap.entity, snap.kind, 'state', name, _stringify(fold), _stringify(fvalue)))
    for name, bvalue in snap.predicates.items():
        bold = prev_predicates.get(name)
        if bold != bvalue:
            changes.append(SemanticChange(snap.entity, snap.kind, 'predicate', name, _stringify(bold), _stringify(bvalue)))
    return changes


class SemanticsManager:
    def __init__(self, mech: MechanismITF) -> None:
        self._mech = mech
        self._sim: str | None = None
        self._instances: dict[str, SemanticKind] = {}
        self._last: dict[str, SemanticEntitySnapshot] = {}
        self._callback: Callable[[Sequence[SemanticChange]], None] | None = None

    def set_sim(self, name: str) -> None:
        self._sim = name

    def attach(self, kind: str, entity: str, cfgs: Sequence[SemanticCfg]) -> None:
        """Instantiate the kind for entity, skipping unsupported sims and empty cfg lists."""
        if not cfgs:
            return
        kind_cls = _SEMANTIC_KINDS.get(kind)
        if kind_cls is None:
            self._mech.node.get_logger().info(f"semantics: unknown kind {kind!r} for {entity!r}, skipping")
            return
        if self._sim not in kind_cls.SUPPORTED_SIMS:
            self._mech.node.get_logger().info(f"semantics: kind {kind!r} unsupported on sim {self._sim!r}, skipping {entity!r}")
            return
        self._instances[entity] = kind_cls.attach(self._mech, entity, cfgs)

    def detach(self, entity: str) -> None:
        self._instances.pop(entity, None)
        self._last.pop(entity, None)

    def step(self, now: float) -> None:
        """Step every instance, diff against the last snapshot, emit changes as one batch."""
        changes: list[SemanticChange] = []
        for entity, instance in self._instances.items():
            instance.step(now)
            snap = instance.snapshot()
            changes.extend(_diff(self._last.get(entity), snap))
            self._last[entity] = snap
        if changes and self._callback is not None:
            self._callback(changes)

    def reset(self) -> None:
        for instance in self._instances.values():
            instance.reset()
        self._last.clear()

    def snapshot(self) -> list[SemanticEntitySnapshot]:
        return [instance.snapshot() for instance in self._instances.values()]

    def set_change_callback(self, cb: Callable[[Sequence[SemanticChange]], None]) -> None:
        self._callback = cb
