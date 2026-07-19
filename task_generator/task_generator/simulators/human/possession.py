"""ROS-free stream validation and the possession table shared by all human backends."""

from __future__ import annotations

import copy
import typing

from task_generator.simulators.human.gait import LIMITS, GaitGenerator

_JOINT_LIMITS: dict[str, tuple[float, float]] = dict(zip(GaitGenerator.JOINT_NAMES, LIMITS, strict=True))

POSSESSION_TIMEOUT_S = 1.0


class _JointStateLike(typing.Protocol):
    name: typing.Sequence[str]
    position: typing.Sequence[float]


class _PedestrianLike(typing.Protocol):
    name: str
    joint_state: _JointStateLike
    model_uri: str


class _PossessableLike(_PedestrianLike, typing.Protocol):
    id: int
    gait_phase: float


def bare_joint_names_valid(names: typing.Iterable[str]) -> bool:
    """True if every name is a bare GaitGenerator.JOINT_NAMES entry (no hri_producer suffix)."""
    return all(name in _JOINT_LIMITS for name in names)


def clamp_joint_state[PedestrianT: _PedestrianLike](ped: PedestrianT) -> None:
    """Clamp ped.joint_state.position to gait.LIMITS in place, matched by joint_state.name."""
    ped.joint_state.position = [_clamp(position, *_JOINT_LIMITS[name]) for name, position in zip(ped.joint_state.name, ped.joint_state.position, strict=True)]


def validate_stream[PedestrianT: _PedestrianLike](
    pedestrians: typing.Sequence[PedestrianT],
    *,
    gate_open: bool,
    known_names: typing.Container[str],
) -> tuple[list[PedestrianT], frozenset[str], frozenset[str]]:
    """Return (clamped copies with model_uri cleared, unknown names, bad joint names), all empty while the gate is closed."""
    if not gate_open:
        return [], frozenset(), frozenset()

    validated: list[PedestrianT] = []
    unknown: set[str] = set()
    bad_joints: set[str] = set()
    for ped in pedestrians:
        if ped.name not in known_names:
            unknown.add(ped.name)
            continue
        names = ped.joint_state.name
        if len(names) != len(ped.joint_state.position) or not bare_joint_names_valid(names):
            bad_joints.add(ped.name)
            continue
        clamped = copy.deepcopy(ped)
        clamped.model_uri = ""
        clamp_joint_state(clamped)
        validated.append(clamped)
    return validated, frozenset(unknown), frozenset(bad_joints)


def snapshot_roster[PedestrianT: _PedestrianLike](cache: typing.Mapping[str, PedestrianT]) -> list[PedestrianT]:
    """Deep copies, safe to mutate/publish without touching the cache."""
    return [copy.deepcopy(ped) for ped in cache.values()]


def _clamp(value: float, lo: float, hi: float) -> float:
    return max(lo, min(hi, value))


class PossessionTable[PedestrianT: _PossessableLike]:
    """Publisher-claimed ped states, substituted into outbound batches until released or expired."""

    def __init__(self, phase: typing.Callable[[int], float] | None = None) -> None:
        self._phase = phase
        self._entries: dict[str, PedestrianT] = {}
        self._last_seen: dict[str, float] = {}

    def merge(
        self,
        batch: typing.Sequence[PedestrianT],
        *,
        known_names: typing.Container[str],
        gate_open: bool,
        now: float,
    ) -> tuple[list[PedestrianT], frozenset[str], frozenset[str], list[tuple[str, PedestrianT]]]:
        """Validate a complete claim-set batch, claim/renew accepted names, release manifest omissions."""
        accepted, unknown, bad_joints = validate_stream(batch, gate_open=gate_open, known_names=known_names)
        released: list[tuple[str, PedestrianT]] = []
        if not gate_open:
            return accepted, unknown, bad_joints, released
        manifest = {ped.name for ped in batch}
        for name in [name for name in self._entries if name not in manifest]:
            released.append((name, self._release(name)))
        for ped in accepted:
            self._entries[ped.name] = copy.deepcopy(ped)
            self._last_seen[ped.name] = now
        return accepted, unknown, bad_joints, released

    def expire(self, now: float) -> list[tuple[str, PedestrianT]]:
        """Drop and return entries silent for longer than POSSESSION_TIMEOUT_S."""
        stale = [name for name in self._entries if not self._live(name, now)]
        return [(name, self._release(name)) for name in stale]

    def substitute(self, pedestrians: typing.Sequence[PedestrianT], now: float) -> list[PedestrianT]:
        """Copy-on-write overlay: possessed names swap to stored copies, everything else passes through untouched."""
        out: list[PedestrianT] = []
        for ped in pedestrians:
            if ped.name not in self._entries or not self._live(ped.name, now):
                out.append(ped)
                continue
            sub = copy.deepcopy(self._entries[ped.name])
            sub.id = ped.id
            if self._phase is not None:
                sub.gait_phase = self._phase(ped.id)
            out.append(sub)
        return out

    def possessed(self, now: float) -> set[str]:
        """Names currently possessed, expiry-checked."""
        return {name for name in self._entries if self._live(name, now)}

    def states(self, now: float) -> dict[str, PedestrianT]:
        """Deep-copied name to state mapping of live entries."""
        return {name: copy.deepcopy(ped) for name, ped in self._entries.items() if self._live(name, now)}

    def clear(self) -> None:
        """Drop everything, no release reporting."""
        self._entries.clear()
        self._last_seen.clear()

    def _live(self, name: str, now: float) -> bool:
        return now - self._last_seen[name] <= POSSESSION_TIMEOUT_S

    def _release(self, name: str) -> PedestrianT:
        del self._last_seen[name]
        return self._entries.pop(name)
