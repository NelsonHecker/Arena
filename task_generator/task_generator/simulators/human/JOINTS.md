# Human skeleton joint contract

Frozen interface shared by the gait generator (`GaitGenerator`), the HRI producer node,
and every pedestrian renderer (RViz, Gazebo, Isaac). `Pedestrian.joint_state` is the
animation single source of truth (SSOT): it carries the 20 base joint names from
`GaitGenerator.JOINT_NAMES`, and every renderer resolves its own convention from that
one field.

## 1. Wire contract (normative)

### Naming convention

Every joint/link carries a `_<ID>` suffix where **`<ID> = str(pedestrian.id)`**.
`sensor_msgs/JointState.name[i]` MUST be the full suffixed name (e.g. `l_r_hip_7`) so it
matches the body's generated URDF. The gait generator takes the agent id and suffixes it.

### Publish all 20

Publish a position for all 20 base joints each tick (unanimated -> 0.0) so
`robot_state_publisher` does not warn. Fixed joints (`torso`, `head`, `l/r_wrist`,
`l/r_ankle`) are not part of the contract and never appear in `JointState`. The
per-joint `[lo, hi]` limits in the Section 2 table are advisory: generators may
clamp their output to them, the stream and presentation layers never enforce them.

### Value semantics

For every joint except the two shoulder triples, wire values are identical to the
ros4hri `human_description` URDF interpretation of that joint's axis (Section 2 states
each joint's raw meaning).

The shoulder triples (`l/r_y_shoulder`, `l/r_p_shoulder`, `l/r_r_shoulder`) are the one
exception: their wire values are anatomical, not raw URDF axis values.

- `p_shoulder`: sagittal flexion of the whole arm. Positive = forward, same sign
  convention on both sides. Antiphase is baked into the emitted values (`GaitGenerator`
  emits `l = A*sin(phi+pi)`, `r = A*sin(phi)`), the sign convention itself is not
  mirrored.
- `y_shoulder` / `r_shoulder`: arm yaw / axial twist. Reserved, currently always `0.0`
  on the wire.

Consumers must not interpret the shoulder-triple values through the raw URDF axes in
Section 2's table, that mapping is the RViz adapter's job, not the contract's.

### Gait synthesis

Phase `phi` per agent integrates from speed: `phi += 2*pi*cadence*dt`, where
`cadence ~= clamp(0.4 + 0.55*speed, 0.4, 2.2)` Hz (frozen: the Gazebo plugin's phase
lock mirrors this formula). Legs antiphase; arms contralateral (arm swings with the
opposite leg).

- **walk** (`WALKING`, speed-scaled gain `g = clamp(speed/1.2, 0.2, 1.0)`): per-joint
  profiles baked from the polished CMU 12_01 clip (`arena_humans` posture pipeline),
  mean + 3 sine harmonics per signal, all scaled by `g` (`_WALK_PROFILE` in `gait.py`).
  Limb pairs share one canonical profile with the right side evaluated at `phi + pi`,
  so L/R antiphase is exact by construction. Antiphase means `l(phi) = r(phi + pi)`,
  NOT `l = -r`: the profiles carry nonzero means (hips average forward-flexed, elbows
  ~18 deg bent).
- **run** (`RUNNING`): the same profiles at 1.6x amplitude, `cadence` higher.
- **idle** (`IDLE` and the behavior states `PANIC/SURPRISED/CURIOUS/THREATENING` for now):
  near-zero limbs; tiny breathing sway `waist = 0.03*sin(phi)` and a slow gaze wander
  `y_head = 0.06*sin(0.3*phi)`, `p_head = 0.02*sin(0.5*phi + 1.0)`. (Behavior
  states get richer posture later; baseline treats them as idle for the rig.)

State selection comes from `Pedestrian.animation_state`; speed is `hypot(twist.linear.x, y)`.

### Determinism

Per-agent phase keyed by id, cleared on despawn. Seed initial `phi` from `id`
(e.g. `(id % 360) * pi/180`) so agents are not in lockstep. Read `dt`, never wall-clock.

## 2. ros4hri URDF rendering (RViz adapter)

### URDF generation (per body)

The producer generates one URDF per body via xacro:

```
xacro <share>/human_description/urdf/human-tpl.xacro id:=<ID> height:=<H>
```

- Only `id` (string) and `height` (float, default `1.65`) are real xacro args; the other
  proportion knobs in `create_human_urdf.py` do not map to xacro args and are inert.
- The generated URDF is set as ROS param `human_description_<ID>` and consumed by a
  `robot_state_publisher` for that body. Root link is `body_<ID>` (REP-155 hip-origin frame).

### Mirror convention

Every joint origin in `human-tpl.xacro` is `rpy="0 0 0"`, so all link frames are
body-aligned at rest (REP-155: X forward, Y left, Z up).

The arm macro reflects axes per side: `l_p_shoulder` axis `(1,0,0)`, `r_p_shoulder`
axis `(-1,0,0)`; `l_y_shoulder` `(0,0,-1)`, `r_y_shoulder` `(0,0,1)`; `l_r_shoulder`
`(0,0,1)`, `r_r_shoulder` `(0,0,-1)`. So the raw URDF meaning of `p_shoulder` is
**lateral abduction** (rotation about body-forward X), positive = outward on both
sides, not a sagittal swing.

Leg sagittal joints are not reflected: `l_r_hip`/`r_r_hip` are both `(0,-1,0)`,
positive = forward; knees and elbows are both `(0,-1,0)` on both sides. `l_p_hip`/
`r_p_hip` are mirrored (`(1,0,0)`/`(-1,0,0)`), positive = abduct outward on both sides,
which coincides with the semantic meaning (both reserved, idle at `0.0`), so only the
shoulder triples need the Section 1 exception.

### Articulated joints (20 revolute; all others fixed)

| # | base name | axis | limits [lo, hi] (rad) | role |
|---|---|---|---|---|
| 1 | `waist` | (0,1,0) | [-0.2, 1.0] | torso forward lean |
| 2 | `r_head` | (1,0,0) | [-1.0, 1.0] | head roll |
| 3 | `y_head` | (0,0,1) | [-1.4, 1.4] | head yaw |
| 4 | `p_head` | (0,-1,0) | [-1.5, 1.5] | head pitch |
| 5 | `l_y_shoulder` | (0,0,-1) | [-1.1, 1.9] | L shoulder yaw |
| 6 | `l_p_shoulder` | (1,0,0) | [-0.4, 3.3] | **L arm abduction (raw axis)** † |
| 7 | `l_r_shoulder` | (0,0,1) | [-1.7, 1.5] | L shoulder roll |
| 8 | `l_elbow` | (0,-1,0) | [0.0, 2.5] | **L elbow** |
| 9 | `r_y_shoulder` | (0,0,1) | [-1.1, 1.9] | R shoulder yaw |
| 10 | `r_p_shoulder` | (-1,0,0) | [-0.4, 3.3] | **R arm abduction (raw axis)** † |
| 11 | `r_r_shoulder` | (0,0,-1) | [-1.7, 1.5] | R shoulder roll |
| 12 | `r_elbow` | (0,-1,0) | [0.0, 2.5] | **R elbow** |
| 13 | `l_y_hip` | (0,0,-1) | [-0.1, 0.6] | L hip yaw |
| 14 | `l_p_hip` | (1,0,0) | [-0.4, 3.3] | L hip abduction |
| 15 | `l_r_hip` | (0,-1,0) | [-0.4, 0.7] | **L leg sagittal swing** |
| 16 | `l_knee` | (0,-1,0) | [-2.5, 0.0] | **L knee** |
| 17 | `r_y_hip` | (0,0,-1) | [-0.1, 0.6] | R hip yaw |
| 18 | `r_p_hip` | (-1,0,0) | [-0.4, 3.3] | R hip abduction |
| 19 | `r_r_hip` | (0,-1,0) | [-0.4, 0.7] | **R leg sagittal swing** |
| 20 | `r_knee` | (0,-1,0) | [-2.5, 0.0] | **R knee** |

Bold = the gait-driving DOFs. † Raw URDF axis meaning; the wire-contract value carried
in this DOF is anatomical flexion (Section 1), not this raw abduction, the `rig.py`
adapter below performs the conversion.

### `rig.py` adapter obligation

`rviz_utils`' `hri_producer` translates Section 1's semantic wire values into this raw
URDF frame before `robot_state_publisher` sees them, via `rviz_utils/hri/rig.py`. For
both sides it emits `y_shoulder = pi/2`, `r_shoulder = pi/2`, `p_shoulder` = flexion
passthrough, everything else passthrough.

This is a ZXZ Euler conjugation: `Rz(-pi/2) * Rx(f) * Rz(pi/2) = R((0,-1,0), f)`, the
constant pi/2 pre/post twists turn the abduction DOF (`Rx`) into a rotation about
`(0,-1,0)`, the same sagittal axis already used by the hip/knee/elbow joints. Because
the arm chain's axes are already reflected between sides (see Mirror convention above),
the identical `y_shoulder = r_shoulder = pi/2` pre-twist on both sides yields the same
sagittal swing on each side from the same commanded flexion value.

`robot_state_publisher` does not enforce URDF joint limits, so the exact `pi/2` on
`r_shoulder` (declared limit `1.5`) is intended, not a bug.

## 3. Other renderers

- **Isaac**: `peds` `bone_map.py` already speaks the semantic convention (same-sign
  flexion, antiphase baked into the values) and spreads `waist` over the
  LowerBack/Spine/Spine1 chain and the head DOFs over neck plus head.
  `ExternalPoseProvider` replaces mapped bones with the wire pose instead of
  composing it over the walking clip.
- **Gazebo**: clip fidelity only. gz-sim 8 actors expose no per-bone skeleton control
  (see `arena_gz_plugins` `PedSkeletonPlugin.cc` header), the plugin follows
  `animation_state`/pose and ignores `joint_state` by design.
