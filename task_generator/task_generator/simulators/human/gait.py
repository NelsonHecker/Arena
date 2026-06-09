from __future__ import annotations

import math
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from builtin_interfaces.msg import Time
    from sensor_msgs.msg import JointState
else:
    try:
        from sensor_msgs.msg import JointState
    except ImportError:
        JointState = None  # type: ignore[assignment,misc]

# Animation state constants matching Pedestrian.msg
_IDLE = 0
_WALKING = 1
_RUNNING = 2
# PANIC=3, SURPRISED=4, CURIOUS=5, THREATENING=6 -> treated as idle

# Joint limits: (lo, hi) in radians, ordered to match JOINT_NAMES.
_LIMITS: tuple[tuple[float, float], ...] = (
    (-0.2, 1.0),  # waist
    (-1.0, 1.0),  # r_head
    (-1.4, 1.4),  # y_head
    (-1.5, 1.5),  # p_head
    (-1.1, 1.9),  # l_y_shoulder
    (-0.4, 3.3),  # l_p_shoulder
    (-1.7, 1.5),  # l_r_shoulder
    (0.0, 2.5),  # l_elbow
    (-1.1, 1.9),  # r_y_shoulder
    (-0.4, 3.3),  # r_p_shoulder
    (-1.7, 1.5),  # r_r_shoulder
    (0.0, 2.5),  # r_elbow
    (-0.1, 0.6),  # l_y_hip
    (-0.4, 3.3),  # l_p_hip
    (-0.4, 0.7),  # l_r_hip
    (-2.5, 0.0),  # l_knee
    (-0.1, 0.6),  # r_y_hip
    (-0.4, 3.3),  # r_p_hip
    (-0.4, 0.7),  # r_r_hip
    (-2.5, 0.0),  # r_knee
)

_IDX: dict[str, int] = {}


class GaitGenerator:
    """Deterministic per-agent gait synthesis for the ROS4HRI human_description rig."""

    JOINT_NAMES: tuple[str, ...] = (
        "waist",
        "r_head",
        "y_head",
        "p_head",
        "l_y_shoulder",
        "l_p_shoulder",
        "l_r_shoulder",
        "l_elbow",
        "r_y_shoulder",
        "r_p_shoulder",
        "r_r_shoulder",
        "r_elbow",
        "l_y_hip",
        "l_p_hip",
        "l_r_hip",
        "l_knee",
        "r_y_hip",
        "r_p_hip",
        "r_r_hip",
        "r_knee",
    )

    def __init__(self) -> None:
        self._phase: dict[int, float] = {}

    def _get_phase(self, agent_id: int) -> float:
        if agent_id not in self._phase:
            self._phase[agent_id] = (agent_id % 360) * math.pi / 180.0
        return self._phase[agent_id]

    def _set_phase(self, agent_id: int, phi: float) -> None:
        self._phase[agent_id] = phi

    def forget(self, agent_id: int) -> None:
        """Drop accumulated phase state for a despawned agent."""
        self._phase.pop(agent_id, None)

    def compute(
        self,
        agent_id: int,
        animation_state: int,
        speed: float,
        dt: float,
    ) -> dict[str, float]:
        """Return base-joint-name -> angle for all 20 joints, clamped to limits.

        Phase advances by dt each call and is keyed per agent_id.
        animation_state: int matching Pedestrian.msg constants (IDLE=0, WALKING=1, RUNNING=2).
        """
        angles: dict[str, float] = {name: 0.0 for name in self.JOINT_NAMES}

        if animation_state == _WALKING:
            angles = self._gait_walk(agent_id, speed, dt)
        elif animation_state == _RUNNING:
            angles = self._gait_run(agent_id, speed, dt)
        else:
            angles = self._gait_idle(agent_id, dt)

        return {name: _clamp(angles.get(name, 0.0), _LIMITS[i][0], _LIMITS[i][1]) for i, name in enumerate(self.JOINT_NAMES)}

    def _gait_walk(self, agent_id: int, speed: float, dt: float) -> dict[str, float]:
        cadence = _clamp(0.4 + 0.55 * speed, 0.4, 2.2)
        phi = self._get_phase(agent_id)
        phi += 2.0 * math.pi * cadence * dt
        self._set_phase(agent_id, phi)

        g = _clamp(speed / 1.2, 0.2, 1.0)

        l_r_hip = 0.45 * g * math.sin(phi)
        r_r_hip = 0.45 * g * math.sin(phi + math.pi)
        l_knee = -0.9 * g * max(0.0, -math.sin(phi))
        r_knee = -0.9 * g * max(0.0, -math.sin(phi + math.pi))
        l_p_shoulder = 0.35 * g * math.sin(phi + math.pi)
        r_p_shoulder = 0.35 * g * math.sin(phi)
        elbow_bias = 0.3 + 0.2 * g

        return {
            "waist": 0.0,
            "r_head": 0.0,
            "y_head": 0.0,
            "p_head": 0.0,
            "l_y_shoulder": 0.0,
            "l_p_shoulder": l_p_shoulder,
            "l_r_shoulder": 0.0,
            "l_elbow": elbow_bias,
            "r_y_shoulder": 0.0,
            "r_p_shoulder": r_p_shoulder,
            "r_r_shoulder": 0.0,
            "r_elbow": elbow_bias,
            "l_y_hip": 0.0,
            "l_p_hip": 0.0,
            "l_r_hip": l_r_hip,
            "l_knee": l_knee,
            "r_y_hip": 0.0,
            "r_p_hip": 0.0,
            "r_r_hip": r_r_hip,
            "r_knee": r_knee,
        }

    def _gait_run(self, agent_id: int, speed: float, dt: float) -> dict[str, float]:
        cadence = _clamp(0.4 + 0.55 * speed, 0.4, 2.2)
        phi = self._get_phase(agent_id)
        phi += 2.0 * math.pi * cadence * dt
        self._set_phase(agent_id, phi)

        g = _clamp(speed / 1.2, 0.2, 1.0)
        amp = 1.6 * g

        l_r_hip = 0.45 * amp * math.sin(phi)
        r_r_hip = 0.45 * amp * math.sin(phi + math.pi)
        l_knee = -0.9 * amp * max(0.0, -math.sin(phi))
        r_knee = -0.9 * amp * max(0.0, -math.sin(phi + math.pi))
        l_p_shoulder = 0.35 * amp * math.sin(phi + math.pi)
        r_p_shoulder = 0.35 * amp * math.sin(phi)
        elbow_bias = 1.2

        return {
            "waist": 0.0,
            "r_head": 0.0,
            "y_head": 0.0,
            "p_head": 0.0,
            "l_y_shoulder": 0.0,
            "l_p_shoulder": l_p_shoulder,
            "l_r_shoulder": 0.0,
            "l_elbow": elbow_bias,
            "r_y_shoulder": 0.0,
            "r_p_shoulder": r_p_shoulder,
            "r_r_shoulder": 0.0,
            "r_elbow": elbow_bias,
            "l_y_hip": 0.0,
            "l_p_hip": 0.0,
            "l_r_hip": l_r_hip,
            "l_knee": l_knee,
            "r_y_hip": 0.0,
            "r_p_hip": 0.0,
            "r_r_hip": r_r_hip,
            "r_knee": r_knee,
        }

    def _gait_idle(self, agent_id: int, dt: float) -> dict[str, float]:
        phi = self._get_phase(agent_id)
        phi += 2.0 * math.pi * 0.25 * dt
        self._set_phase(agent_id, phi)

        waist = 0.03 * math.sin(phi)

        return {
            "waist": waist,
            "r_head": 0.0,
            "y_head": 0.0,
            "p_head": 0.0,
            "l_y_shoulder": 0.0,
            "l_p_shoulder": 0.0,
            "l_r_shoulder": 0.0,
            "l_elbow": 0.0,
            "r_y_shoulder": 0.0,
            "r_p_shoulder": 0.0,
            "r_r_shoulder": 0.0,
            "r_elbow": 0.0,
            "l_y_hip": 0.0,
            "l_p_hip": 0.0,
            "l_r_hip": 0.0,
            "l_knee": 0.0,
            "r_y_hip": 0.0,
            "r_p_hip": 0.0,
            "r_r_hip": 0.0,
            "r_knee": 0.0,
        }

    def joint_state(
        self,
        angles: dict[str, float],
        stamp: Time | None = None,
    ) -> JointState:
        """Build a sensor_msgs/JointState from a compute() result with bare semantic names."""
        msg = JointState()
        if stamp is not None:
            msg.header.stamp = stamp
        msg.name = list(self.JOINT_NAMES)
        msg.position = [angles[name] for name in self.JOINT_NAMES]
        return msg


def _clamp(value: float, lo: float, hi: float) -> float:
    return max(lo, min(hi, value))
