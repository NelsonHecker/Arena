# Adding a robot

A robot is a directory under `arena_robots/arena_robots/robots/<name>/`. The
directory name is the robot's canonical identifier — task_generator, launch
files, and the `arena feature robots` CLI all look robots up by this name.

## Required files

### `model_params.yaml`

Capabilities and physical params. Parsed by
[`arena_robots.Robot.ModelParams`](../Robot.py). Keys used by Arena
(everything else is passed through and ignored):

| Key | Type | Default | Purpose |
| --- | --- | --- | --- |
| `robot_base_frame` | str | `base_link` | tf frame that moves with the chassis |
| `robot_odom_frame` | str | `odom` | odometry frame |
| `z_offset` | float | `0.0` | spawn height correction |
| `actuator_caps` | list[str] | `["mobile"]` | capabilities the robot honors (adapter `requires` must be a subset) |
| `navigator` | str | `"nav2"` | default adapter `kind`; overridable by launch args |
| `sensors` | list[SensorSpec] | `[]` | sensors the robot exposes (name/type/topic/frame) |
| `capabilities` | list[dict] | `[]` | optional multi-adapter declaration |

`sensors` entries must have `name`, `type`, `topic`, `frame`. Canonical `type`
values are in [`Sensor.py`](../Sensor.py): `laserscan`, `pointcloud`, `image`,
`depth`. Unknown type strings are passed through to nav2 unchanged.

### `control.yaml`

ROS 2 `controller_manager` configuration. Define `joint_state_broadcaster`
plus whichever controller drives the robot (e.g.
`diff_drive_controller/DiffDriveController`). See
[`husky/control.yaml`](husky/control.yaml) for a diff-drive example.

### `mappings.yaml`

Simulator⇄ROS2 topic bridge declarations, as a JSON array. Each entry:

```yaml
{
  "gz_topic":  "/model/{robot_name}/cmd_vel",    # simulator-side topic
  "ros_topic": "cmd_vel",                         # ROS2-side topic
  "gz_type":   "gz.msgs.Twist",
  "ros_type":  "geometry_msgs/msg/Twist",
  "direction": "]",                               # "[" sim→ros, "]" ros→sim
}
```

`{robot_name}` and `{world}` are substituted at runtime. See
[`husky/mappings.yaml`](husky/mappings.yaml).

## Optional files

| Path | Purpose |
| --- | --- |
| `urdf/<name>.urdf.xacro` | robot description; mesh refs use `package://arena_robots/robots/<name>/meshes/…` or a fixed upstream package (`package://jackal_description/…`) |
| `meshes/` | STL/DAE/OBJ files, normally a git submodule under `github.com/arena-robots/<name>` (opt-in via `arena feature robots add <name>`) |
| `launch/` | robot-specific launch files (e.g. nav2 overrides) |
| `README.md` | free-form robot docs (upstream references, env vars, etc.) |

## Meshes

Every robot that needs per-robot geometry has a `meshes/` git submodule pinned
via `.gitmodules`, pointing at `github.com/arena-robots/<name>.git` with
`update = none`. Running `arena feature robots add <name>` clones it; config
edits you make under the robot dir stay in the main Arena repo. Robots that
use upstream geometry (jackal, turtlebot) have no `meshes/` submodule —
their URDFs reference `package://jackal_description/…` etc., supplied by
`deps/jackal` or `deps/turtlebot4`.

## Checklist

1. `mkdir arena_robots/arena_robots/robots/<name>/`
2. Write `model_params.yaml`, `control.yaml`, `mappings.yaml`.
3. (Optional) add `urdf/<name>.urdf.xacro` and/or a `meshes/` submodule.
4. If the robot ships an upstream ROS package, add it as a submodule with
   `robot = <name>` (and `update = none`) in `.gitmodules`.
5. `arena feature robots add <name>` to fetch any submodules.
6. `arena feature robots check` to verify every `package://arena_robots/…`
   URI resolves on disk.
7. `arena launch … robot:=<name>` to bring it up.
