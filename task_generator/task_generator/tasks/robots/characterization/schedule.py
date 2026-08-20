"""Pure-Python maneuver schedule definitions for open-loop characterization."""

from __future__ import annotations

import dataclasses
import logging
import pathlib
try:
    from enum import StrEnum
except ImportError:
    from enum import Enum
    class StrEnum(str, Enum):
        pass

try:
    import yaml
except ImportError:
    yaml = None

_log = logging.getLogger(__name__)

VX_MIN = 0.0  # m/s
VX_MAX = 2.0  # m/s, default maximum rated linear speed
VX_STEP = 0.25  # m/s
VY_MAX = 0.0  # m/s (non-holonomic default)
VY_STEP = 0.25  # m/s
LINEAR_DWELL_S = 5.0  # s, steady-state capture per velocity step
LINEAR_SETTLE_S = 1.0  # s, settle at rest between linear directions
LATERAL_DWELL_S = 5.0  # s, steady-state capture per lateral step
RAMP_HORIZON_S = 1.0  # s, acceleration/deceleration horizon per step
RAMP_HORIZONS_S = (1.0,)  # legacy alias
RAMP_SETTLE_S = 1.0  # s, settle at the ramp apex before decelerating
BRAKE_DWELL_S = 3.0  # s, capture settling after step deceleration
ARC_DWELL_S = 5.0  # s, steady-state capture per arc maneuver
WZ_MIN = -2.5  # rad/s
WZ_MAX = 2.5  # rad/s, default maximum rated angular rate
WZ_STEP = 0.5  # rad/s
ANGULAR_DWELL_S = 5.0  # s, per pivot rate
IDLE_DURATION_S = 10.0  # s, mandatory standstill blocks (baseline standby draw)

DEFAULT_ARC_SPEEDS = (0.5, 1.0, 1.5)  # m/s
DEFAULT_ARC_RADII_M = (0.5, 1.0, 2.5)  # m

CONTROL_RATE_HZ = 20.0  # cmd_vel publish rate during a maneuver
ODOM_STALL_TIMEOUT_S = 3.0  # odom silent for this long: zero cmd_vel + abort
MAX_SCHEDULE_DURATION_S = 3600.0  # global safety ceiling for one run


class PhaseKind(StrEnum):
    IDLE = "idle"
    LINEAR = "linear"
    LATERAL = "lateral"
    ANGULAR = "angular"
    ARC = "arc"
    RAMP_UP = "ramp_up"
    RAMP_DOWN = "ramp_down"
    BRAKE = "brake"
    TRANSIENT = "transient"


@dataclasses.dataclass(frozen=True)
class Phase:
    """One maneuver block: a target twist held for a duration (optionally a ramp)."""

    kind: PhaseKind
    name: str  # unique label, e.g. "linear_vx_1.00", "arc_vx_1.00_r_1.00_left"
    vx_target: float = 0.0  # m/s
    vy_target: float = 0.0  # m/s (lateral / holonomic)
    wz_target: float = 0.0  # rad/s
    duration_s: float = 0.0  # s to hold the target (ramp: the ramp horizon)
    ramp_s: float = 0.0  # >0 for ramps: linearly interpolate vx from 0 to target over this horizon
    radius_m: float = 0.0  # m (turn radius for arc maneuvers)

    @property
    def key(self) -> tuple[str, float, float]:
        """Grouping key for offline aggregation: (kind, vx_target, wz_target)."""
        return self.kind.value, round(self.vx_target, 3), round(self.wz_target, 3)


def _steps(start: float, stop: float, step: float) -> list[float]:
    """Floating-point safe step range (inclusive of stop)."""
    if step <= 0:
        return [round(start, 6)]
    n = round((stop - start) / step) + 1
    return [round(start + i * step, 6) for i in range(max(1, n))]


def resolve_envelope(
    robot_name: str | None = None,
    *,
    caps_dir: pathlib.Path | None = None,
    fallback: tuple[float, float] | None = None,
) -> dict[str, float | bool]:
    """Resolve the operating envelope (vx_max, vy_max, wz_max, is_holonomic) for a robot."""
    vx_max = VX_MAX
    vy_max = VY_MAX
    wz_max = WZ_MAX
    is_holonomic = False

    if fallback is not None:
        vx_max, wz_max = fallback

    mobile: pathlib.Path | None = None
    try:
        if caps_dir is not None:
            mobile = pathlib.Path(caps_dir) / f"{robot_name}/caps/mobile.yaml" if robot_name else None
            if mobile is None or not mobile.is_file():
                return {
                    "vx_max": vx_max,
                    "vy_max": vy_max,
                    "wz_max": wz_max,
                    "is_holonomic": is_holonomic,
                }
        else:
            from ament_index_python.packages import get_package_share_directory

            mobile = pathlib.Path(get_package_share_directory("arena_robots")) / "robots" / (robot_name or "") / "caps" / "mobile.yaml"

        if yaml is not None:
            cfg = yaml.safe_load(mobile.read_text()) or {}
            is_holonomic = bool(cfg.get("is_holonomic", False))

            continuous = cfg.get("actions", {}).get("continuous", {})
            if isinstance(continuous, dict):
                linear = continuous.get("linear")
                if isinstance(linear, dict) and linear.get("max") is not None:
                    vx_max = float(linear["max"])
                lateral = continuous.get("lateral")
                if isinstance(lateral, dict) and lateral.get("max") is not None:
                    vy_max = float(lateral["max"])
                    is_holonomic = True
                elif is_holonomic:
                    vy_max = vx_max
                angular = continuous.get("angular")
                if isinstance(angular, dict) and angular.get("max") is not None:
                    wz_max = float(angular["max"])
        else:
            text = mobile.read_text()
            is_holonomic = "is_holonomic: true" in text.lower()
            if is_holonomic and vy_max == 0.0:
                vy_max = vx_max
    except (OSError, KeyError, TypeError, ValueError, AttributeError) as e:
        _log.warning(f"characterization: robot {robot_name!r} envelope falls back to vx_max={vx_max} wz_max={wz_max}, could not read {mobile}: {e!r}")
    return {
        "vx_max": vx_max,
        "vy_max": vy_max,
        "wz_max": wz_max,
        "is_holonomic": is_holonomic,
    }


def build_schedule(
    *,
    modes: list[str] | None = None,
    idle_s: float = IDLE_DURATION_S,
    linear_dwell_s: float = LINEAR_DWELL_S,
    linear_settle_s: float = LINEAR_SETTLE_S,
    lateral_dwell_s: float = LATERAL_DWELL_S,
    angular_dwell_s: float = ANGULAR_DWELL_S,
    arc_dwell_s: float = ARC_DWELL_S,
    arc_speeds: list[float] | None = None,
    arc_radii_m: list[float] | None = None,
    ramp_horizon_s: float = RAMP_HORIZON_S,
    ramp_settle_s: float = RAMP_SETTLE_S,
    brake_dwell_s: float = BRAKE_DWELL_S,
    vx_min: float = VX_MIN,
    vx_max: float = VX_MAX,
    vx_step: float = VX_STEP,
    vy_max: float = VY_MAX,
    vy_step: float = VY_STEP,
    wz_min: float = WZ_MIN,
    wz_max: float = WZ_MAX,
    wz_step: float = WZ_STEP,
    is_holonomic: bool = False,
) -> list[Phase]:
    """Build the comprehensive open-loop maneuver schedule."""
    phases: list[Phase] = []
    active_modes = set(modes) if modes is not None else {"idle", "linear", "lateral", "arc", "ramps", "brake", "angular"}

    # 1. Baseline Standby / Idle Block
    if "idle" in active_modes:
        phases.append(Phase(PhaseKind.IDLE, "idle_start", duration_s=idle_s))

    # 2. Longitudinal Linear Cruising Sweep
    if "linear" in active_modes:
        for vx in _steps(vx_step, vx_max, vx_step):
            phases.append(Phase(PhaseKind.LINEAR, f"linear_vx_{vx:.2f}", vx_target=vx, duration_s=linear_dwell_s))
            if linear_settle_s > 0:
                phases.append(Phase(PhaseKind.IDLE, f"linear_settle_{vx:.2f}", duration_s=linear_settle_s))
            phases.append(Phase(PhaseKind.LINEAR, f"linear_vx_-{vx:.2f}", vx_target=-vx, duration_s=linear_dwell_s))
            if linear_settle_s > 0:
                phases.append(Phase(PhaseKind.IDLE, f"linear_settle_-{vx:.2f}", duration_s=linear_settle_s))

    # 3. Lateral Holonomic Cruising Sweep (Omnidirectional / Mecanum)
    if "lateral" in active_modes and is_holonomic and vy_max > 0.0:
        if "idle" in active_modes:
            phases.append(Phase(PhaseKind.IDLE, "idle_lateral_pre", duration_s=max(2.0, idle_s / 2.0)))
        for vy in _steps(vy_step, vy_max, vy_step):
            phases.append(Phase(PhaseKind.LATERAL, f"lateral_vy_{vy:.2f}", vy_target=vy, duration_s=lateral_dwell_s))
            if linear_settle_s > 0:
                phases.append(Phase(PhaseKind.IDLE, f"lateral_settle_{vy:.2f}", duration_s=linear_settle_s))
            phases.append(Phase(PhaseKind.LATERAL, f"lateral_vy_-{vy:.2f}", vy_target=-vy, duration_s=lateral_dwell_s))
            if linear_settle_s > 0:
                phases.append(Phase(PhaseKind.IDLE, f"lateral_settle_-{vy:.2f}", duration_s=linear_settle_s))

    # 4. Curvilinear Arc Steering Sweeps
    if "arc" in active_modes:
        if "idle" in active_modes:
            phases.append(Phase(PhaseKind.IDLE, "idle_arc_pre", duration_s=max(2.0, idle_s / 2.0)))
        speeds = arc_speeds or list(DEFAULT_ARC_SPEEDS)
        radii = arc_radii_m or list(DEFAULT_ARC_RADII_M)
        for vx in speeds:
            if vx > vx_max:
                continue
            for r in radii:
                if r <= 0.0:
                    continue
                wz = vx / r
                if wz > wz_max:
                    continue
                # Left Turn (+wz)
                phases.append(
                    Phase(
                        PhaseKind.ARC,
                        f"arc_vx_{vx:.2f}_r_{r:.2f}_left",
                        vx_target=vx,
                        wz_target=wz,
                        duration_s=arc_dwell_s,
                        radius_m=r,
                    )
                )
                if linear_settle_s > 0:
                    phases.append(Phase(PhaseKind.IDLE, f"arc_settle_{vx:.2f}_r_{r:.2f}_left", duration_s=linear_settle_s))
                # Right Turn (-wz)
                phases.append(
                    Phase(
                        PhaseKind.ARC,
                        f"arc_vx_{vx:.2f}_r_{r:.2f}_right",
                        vx_target=vx,
                        wz_target=-wz,
                        duration_s=arc_dwell_s,
                        radius_m=r,
                    )
                )
                if linear_settle_s > 0:
                    phases.append(Phase(PhaseKind.IDLE, f"arc_settle_{vx:.2f}_r_{r:.2f}_right", duration_s=linear_settle_s))

    # 5. Dynamic Acceleration & Deceleration Ramps
    if "ramps" in active_modes:
        if "idle" in active_modes:
            phases.append(Phase(PhaseKind.IDLE, "idle_ramps_pre", duration_s=max(2.0, idle_s / 2.0)))
        for vx in _steps(vx_step, vx_max, vx_step):
            phases.append(Phase(PhaseKind.RAMP_UP, f"ramp_up_vx_{vx:.2f}", vx_target=vx, duration_s=ramp_horizon_s, ramp_s=ramp_horizon_s))
            if ramp_settle_s > 0:
                phases.append(Phase(PhaseKind.LINEAR, f"ramp_apex_vx_{vx:.2f}", vx_target=vx, duration_s=ramp_settle_s))
            phases.append(Phase(PhaseKind.RAMP_DOWN, f"ramp_down_vx_{vx:.2f}", vx_target=vx, duration_s=ramp_horizon_s, ramp_s=ramp_horizon_s))
            phases.append(Phase(PhaseKind.RAMP_UP, f"ramp_up_vx_-{vx:.2f}", vx_target=-vx, duration_s=ramp_horizon_s, ramp_s=ramp_horizon_s))
            if ramp_settle_s > 0:
                phases.append(Phase(PhaseKind.LINEAR, f"ramp_apex_vx_-{vx:.2f}", vx_target=-vx, duration_s=ramp_settle_s))
            phases.append(Phase(PhaseKind.RAMP_DOWN, f"ramp_down_vx_-{vx:.2f}", vx_target=-vx, duration_s=ramp_horizon_s, ramp_s=ramp_horizon_s))

    # 6. Emergency Braking & Step Deceleration
    if "brake" in active_modes:
        if "idle" in active_modes:
            phases.append(Phase(PhaseKind.IDLE, "idle_brake_pre", duration_s=max(2.0, idle_s / 2.0)))
        # Forward rated brake
        phases.append(Phase(PhaseKind.LINEAR, f"brake_approach_vx_{vx_max:.2f}", vx_target=vx_max, duration_s=3.0))
        phases.append(Phase(PhaseKind.BRAKE, f"brake_step_vx_{vx_max:.2f}", vx_target=0.0, duration_s=brake_dwell_s))
        # Reverse rated brake
        phases.append(Phase(PhaseKind.LINEAR, f"brake_approach_vx_-{vx_max:.2f}", vx_target=-vx_max, duration_s=3.0))
        phases.append(Phase(PhaseKind.BRAKE, f"brake_step_vx_-{vx_max:.2f}", vx_target=0.0, duration_s=brake_dwell_s))

    # 7. In-Place Angular Pivot Sweep
    if "angular" in active_modes:
        if "idle" in active_modes:
            phases.append(Phase(PhaseKind.IDLE, "idle_angular_pre", duration_s=max(2.0, idle_s / 2.0)))
        for wz in _steps(wz_min, wz_max, wz_step):
            phases.append(Phase(PhaseKind.ANGULAR, f"angular_wz_{wz:+.2f}", wz_target=wz, duration_s=angular_dwell_s))

    # 8. Final Standstill Block
    if "idle" in active_modes:
        phases.append(Phase(PhaseKind.IDLE, "idle_end", duration_s=idle_s))

    return phases


def schedule_duration(phases: list[Phase]) -> float:
    """Total wall/sim time of a schedule (sum of phase durations)."""
    return sum(p.duration_s for p in phases)


def classify_cmd_point(vx_cmd: float, wz_cmd: float, vy_cmd: float = 0.0) -> tuple[PhaseKind, float, float]:
    """Offline fallback: classify a (cmd_vel) sample into a phase key."""
    vx = round(float(vx_cmd or 0.0), 3)
    vy = round(float(vy_cmd or 0.0), 3)
    wz = round(float(wz_cmd or 0.0), 3)
    if vx == 0.0 and vy == 0.0 and wz == 0.0:
        return PhaseKind.IDLE, 0.0, 0.0
    if vy != 0.0 and vx == 0.0 and wz == 0.0:
        return PhaseKind.LATERAL, 0.0, 0.0
    if vx != 0.0 and wz != 0.0:
        return PhaseKind.ARC, vx, wz
    if wz != 0.0:
        return PhaseKind.ANGULAR, 0.0, wz
    return PhaseKind.LINEAR, vx, 0.0

