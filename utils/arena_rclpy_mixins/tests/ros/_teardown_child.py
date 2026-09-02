"""Child process for test_spin_teardown: exercises spin.py teardown paths under a real rclpy context."""

from __future__ import annotations

import asyncio
import sys

import rclpy
from std_msgs.msg import String

from arena_rclpy_mixins.node import ArenaMixinNode
from arena_rclpy_mixins.spin import spin_context


class Storm(ArenaMixinNode):
    """Fire-and-forget publish tasks at 100 Hz, the shape of humansim's interpolation loop."""

    async def setup(self) -> None:
        self._pub = self.create_publisher(String, "teardown_probe", 10)
        self._storm = asyncio.create_task(self._run())
        print("READY", flush=True)

    async def _run(self) -> None:
        loop = asyncio.get_running_loop()
        while True:
            loop.create_task(self._publish_once())
            await asyncio.sleep(0.01)

    async def _publish_once(self) -> None:
        self._pub.publish(String(data="tick"))


def main() -> None:
    mode = sys.argv[1]
    if mode == "async_storm":
        Storm.run_main("teardown_storm")
    elif mode == "sync_late":
        rclpy.init()
        with spin_context():
            rclpy.shutdown()
            raise RuntimeError("late callback")
    elif mode == "sync_real":
        rclpy.init()
        with spin_context():
            raise RuntimeError("real failure")
    else:
        raise SystemExit(f"unknown mode {mode}")


if __name__ == "__main__":
    main()
