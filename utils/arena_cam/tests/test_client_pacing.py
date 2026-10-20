"""A recorded segment is paced to wall clock."""

from __future__ import annotations

import asyncio
import time
from collections.abc import Iterator
from pathlib import Path

import pytest
import rclpy
from arena_cam.camera import Camera
from arena_cam.client import CamNode, Steered
from arena_cam.curves import Quat, Vec3
from arena_cam.surfaces import TargetSelection


@pytest.fixture
def ros_context() -> Iterator[None]:
    started = not rclpy.ok()
    if started:
        rclpy.init()
    try:
        yield
    finally:
        if started:
            rclpy.try_shutdown()


def test_record_segment_is_paced_to_wall_clock(ros_context: None, tmp_path: Path) -> None:
    targets = TargetSelection(include_sim=False, viz_all=False, viz_env=None)
    sampled: list[float] = []

    def frame_at(t: float) -> tuple[Vec3, Quat, float]:
        sampled.append(t)
        return (0.0, 0.0, 0.0), (1.0, 0.0, 0.0, 0.0), 0.0

    async def run() -> float:
        node = CamNode(timeline=Camera(targets), targets=targets, record=(str(tmp_path / "take.mp4"), 10.0))
        try:
            start = time.monotonic()
            await node.drive(0.5, False, frame_at)
            return time.monotonic() - start
        finally:
            node.destroy_node()

    elapsed = asyncio.run(run())

    assert len(sampled) == 5
    assert elapsed >= 0.30, f"segment was not paced (took {elapsed:.3f}s)"


def test_steer_segment_is_paced_to_wall_clock(ros_context: None, tmp_path: Path) -> None:
    targets = TargetSelection(include_sim=False, viz_all=False, viz_env=None)
    served: list[float] = []

    def next_frame(dt: float) -> Steered | None:
        served.append(dt)
        if len(served) > 5:
            return None
        return Steered(position=(0.0, 0.0, 0.0), quat=(1.0, 0.0, 0.0, 0.0), fov=0.0, referenced=False)

    async def run() -> float:
        node = CamNode(timeline=Camera(targets), targets=targets, record=(str(tmp_path / "take.mp4"), 10.0))
        try:
            start = time.monotonic()
            await node.steer(next_frame)
            return time.monotonic() - start
        finally:
            node.destroy_node()

    elapsed = asyncio.run(run())

    assert len(served) == 6
    assert elapsed >= 0.30, f"segment was not paced (took {elapsed:.3f}s)"
