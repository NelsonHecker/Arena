"""Canonical viz-agnostic display kinds. Every adapter display declares one."""

from __future__ import annotations

import enum


class DisplayKind(enum.StrEnum):
    MAP = "map"
    TF = "tf"
    PEDESTRIANS = "pedestrians"
    MARKER_ARRAY = "marker_array"  # generic MarkerArray passthrough; no pedestrian-namespace assumptions
    ROBOT_MODEL = "robot_model"
    ODOM = "odom"
    LASER_SCAN = "laser_scan"
    POINTS_3D = "points3d"
    IMAGE = "image"
    IMU = "imu"
    FOOT_CONTACT = "foot_contact"
    PATH = "path"
    POSE = "pose"
    POLYGON = "polygon"
    TRAJECTORY = "trajectory"
    PLANNING_SCENE = "planning_scene"
