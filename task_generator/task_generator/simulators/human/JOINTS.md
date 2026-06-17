# Human skeleton joint contract (ROS4HRI `human_description` rig)

Frozen interface shared by the gait generator (`GaitGenerator`) and the HRI producer node.
Source of truth: `ros4hri/human_description` `urdf/human-tpl.xacro` (Apache-2.0, pinned).

## URDF generation (per body)

The producer generates one URDF per body via xacro:

```
xacro <share>/human_description/urdf/human-tpl.xacro id:=<ID> height:=<H>
```

- Only `id` (string) and `height` (float, default `1.65`) are real xacro args; the other
  proportion knobs in `create_human_urdf.py` do not map to xacro args and are inert.
- The generated URDF is set as ROS param `human_description_<ID>` and consumed by a
  `robot_state_publisher` for that body. Root link is `body_<ID>` (REP-155 hip-origin frame).

## Naming convention

Every joint/link carries a `_<ID>` suffix where **`<ID> = str(pedestrian.id)`**.
`sensor_msgs/JointState.name[i]` MUST be the full suffixed name (e.g. `l_r_hip_7`) so it
matches the body's generated URDF. The gait generator takes the agent id and suffixes.

## Articulated joints (20 revolute; all others fixed)

Publish a position for ALL 20 each tick (unanimated -> 0.0) so robot_state_publisher does
not warn. Fixed joints (`torso`, `head`, `l/r_wrist`, `l/r_ankle`) are NOT in JointState.

| # | base name | axis | limits [lo, hi] (rad) | role |
|---|---|---|---|---|
| 1 | `waist` | (0,1,0) | [-0.2, 1.0] | torso forward lean |
| 2 | `r_head` | (1,0,0) | [-1.0, 1.0] | head roll |
| 3 | `y_head` | (0,0,1) | [-1.4, 1.4] | head yaw |
| 4 | `p_head` | (0,-1,0) | [-1.5, 1.5] | head pitch |
| 5 | `l_y_shoulder` | (0,0,-1) | [-1.1, 1.9] | L shoulder yaw |
| 6 | `l_p_shoulder` | (1,0,0) | [-0.4, 3.3] | **L arm sagittal swing** |
| 7 | `l_r_shoulder` | (0,0,1) | [-1.7, 1.5] | L shoulder roll |
| 8 | `l_elbow` | (0,-1,0) | [0.0, 2.5] | **L elbow** |
| 9 | `r_y_shoulder` | (0,0,1) | [-1.1, 1.9] | R shoulder yaw |
| 10 | `r_p_shoulder` | (-1,0,0) | [-0.4, 3.3] | **R arm sagittal swing** |
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

Bold = the gait-driving DOFs. Clamp every emitted value to its `[lo, hi]`.

## Gait synthesis (recommended starting points; T1 tunes)

Phase `phi` per agent integrates from speed: `phi += 2*pi*cadence*dt`, where
`cadence ~= clamp(0.4 + 0.55*speed, 0.4, 2.2)` Hz. Legs antiphase; arms contralateral
(arm swings with the opposite leg). Suggested amplitudes:

- **walk** (`WALKING`, speed-scaled gain `g = clamp(speed/1.2, 0.2, 1.0)`):
  - `l_r_hip = 0.45*g*sin(phi)`, `r_r_hip = 0.45*g*sin(phi+pi)`
  - knees bend on the back-swing: `l_knee = -0.9*g*max(0, -sin(phi))`, `r_knee` with `phi+pi`
  - `l_p_shoulder = 0.35*g*sin(phi+pi)`, `r_p_shoulder = 0.35*g*sin(phi)` (contralateral)
  - `l_elbow = 0.3 + 0.2*g`, `r_elbow = 0.3 + 0.2*g`
- **run** (`RUNNING`): same shape, `cadence` higher, amplitudes ~1.6x, elbow bias ~1.2 rad.
- **idle** (`IDLE` and the behavior states `PANIC/SURPRISED/CURIOUS/THREATENING` for now):
  near-zero limbs; tiny breathing sway `waist = 0.03*sin(2*pi*0.25*t_phase)`. (Behavior
  states get richer posture later; baseline treats them as idle for the rig.)

State selection comes from `Pedestrian.animation_state`; speed is `hypot(twist.linear.x, y)`.

## Determinism

Per-agent phase keyed by id, cleared on despawn. Seed initial `phi` from `id`
(e.g. `(id % 360) * pi/180`) so agents are not in lockstep. Read `dt`, never wall-clock.
