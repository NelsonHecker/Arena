"""Semantic to ros4hri URDF joint translation for pedestrian animation.

Pedestrian.joint_state carries anatomical shoulder values, positive p_shoulder is
sagittal flexion forward on both sides. The ros4hri human_description URDF instead
reads p_shoulder as lateral abduction, so rendered raw both arms sway in unison.
This adapter re-expresses the shoulder triples for the RViz robot_state_publisher,
the only consumer that speaks raw URDF.

URDF shoulder chains compose child-in-parent:
    left:  R = Rz(-y) . Rx(p) . Rz(r)
    right: R = Rz(y) . Rx(-p) . Rz(-r)
Target for semantic flexion f (both sides), positive f forward:
    R_target = R(axis=(0,-1,0), angle=f) = Ry(-f)
Solution, identical commanded values on both sides:
    y = pi/2, p = f, r = pi/2
So {l,r}_{y,r}_shoulder emit the constant pi/2, {l,r}_p_shoulder pass the semantic
value through, all other joints pass through unchanged. pi/2 is emitted exact even
though the URDF declares r_shoulder limit 1.5, robot_state_publisher does not enforce
limits. Reserved semantic y/r_shoulder inputs are ignored, they are always 0 today.
"""

from __future__ import annotations

import math
from collections.abc import Sequence

_HALF_PI = math.pi / 2

_SHOULDER_CONST = frozenset(
    {"l_y_shoulder", "r_y_shoulder", "l_r_shoulder", "r_r_shoulder"}
)


def semantic_to_rig(names: Sequence[str], positions: Sequence[float]) -> list[float]:
    """Translate semantic joint positions into raw ros4hri URDF positions."""
    return [
        _HALF_PI if name in _SHOULDER_CONST else value
        for name, value in zip(names, positions, strict=True)
    ]
