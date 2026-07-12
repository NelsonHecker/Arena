from __future__ import annotations

from pathlib import Path

from arena_robots.caps import ArmSpec

from task_generator.tasks.robots.adapters.arm import park_positions


def _arm(raw: dict) -> ArmSpec:
    return ArmSpec(path=Path("caps/arm.yaml"), raw=raw, name="top")


class TestParkPositions:
    def test_stow_pose_ordered_by_chain(self):
        arm = _arm(
            {
                "chain": ["a", "b", "c"],
                "controller": "top_controller",
                "named_poses": {"stow": {"joints": {"b": -1.57, "a": 0.5}}},
            }
        )
        assert park_positions(arm) == [0.5, -1.57, 0.0]

    def test_zeros_without_stow(self):
        arm = _arm({"chain": ["a", "b"], "controller": "top_controller"})
        assert park_positions(arm) == [0.0, 0.0]
