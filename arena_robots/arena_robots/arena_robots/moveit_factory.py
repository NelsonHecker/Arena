"""Build a MoveIt config dict for a robot, shared between move_group launch
and the RViz parameter-injection path."""

from __future__ import annotations

from pathlib import Path

from ament_index_python.packages import get_package_share_directory
from moveit_configs_utils import MoveItConfigsBuilder

import arena_robots.Robot


def build_moveit_params(robot_name: str) -> dict[str, object] | None:
    """Return a flat parameter dict (URDF, SRDF, kinematics, joint limits)
    for ``robot_name`` if it advertises ``arm``; ``None`` otherwise."""
    robot = arena_robots.Robot.RobotIdentifier(robot_name).resolve_sync()
    if "arm" not in robot.caps.available:
        return None

    arms = robot.caps.arm
    if arms is None:
        raise ValueError(f"{robot_name}: arm cap required but absent")
    if len(arms) != 1:
        raise NotImplementedError(f"{robot_name}: multi-arm not yet supported")
    (arm,) = arms.values()

    mv = arm.raw.get("moveit") or {}
    pkg = mv.get("package")
    if not pkg:
        return None

    args_dict = mv.get("args") or {}
    mappings = {k: (str(v).lower() if isinstance(v, bool) else str(v)) for k, v in args_dict.items()}
    mappings.setdefault("name", mappings.get("ur_type", "ur5e"))

    urdf_abs = Path(get_package_share_directory("arena_robots")) / "robots" / robot_name / "urdf" / f"{robot_name}.urdf.xacro"

    srdf_ref = mv.get("srdf") or {}
    srdf_pkg = srdf_ref.get("package", pkg)
    srdf_rel = srdf_ref.get("path", "srdf/ur.srdf.xacro")
    srdf_abs = Path(get_package_share_directory(srdf_pkg)) / srdf_rel

    jl_ref = mv.get("joint_limits") or {}
    jl_pkg = jl_ref.get("package", pkg)
    jl_rel = jl_ref.get("path", "config/joint_limits.yaml")
    jl_abs = Path(get_package_share_directory(jl_pkg)) / jl_rel

    moveit_config = MoveItConfigsBuilder(robot_name="ur", package_name=pkg).robot_description(file_path=str(urdf_abs), mappings=mappings).robot_description_semantic(srdf_abs, mappings=mappings).joint_limits(jl_abs).to_moveit_configs()
    return moveit_config.to_dict()
