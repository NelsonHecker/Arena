"""Child process for test_spin_teardown: exercises spin.py teardown paths under a real rclpy context."""

from __future__ import annotations

import asyncio
import os
import sys
import time

import rclpy
import rclpy.node
from arena_rclpy_mixins.node import ArenaMixinNode
from arena_rclpy_mixins.spin import create_executor, spin_context, spin_node, start_loop_watchdog
from std_msgs.msg import String
from std_srvs.srv import SetBool

_STALL_S = 12.0
_DEADLINE_BLOCK_S = 5.0
_DEADLINE_S = 1.5


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


class Stall(ArenaMixinNode):
    """Block the loop past the watchdog threshold, then report back."""

    async def setup(self) -> None:
        print("READY", flush=True)
        self._stall = asyncio.create_task(self._block())

    async def _block(self) -> None:
        time.sleep(_STALL_S)
        print("RESUMED", flush=True)


class Deadline(ArenaMixinNode):
    """Block the loop past a short watchdog deadline; on_deadline exits the process."""

    async def setup(self) -> None:
        loop = asyncio.get_running_loop()
        start_loop_watchdog(loop, self, deadline_s=_DEADLINE_S, on_deadline=lambda: os._exit(7))
        self._stall = asyncio.create_task(self._block())

    async def _block(self) -> None:
        time.sleep(_DEADLINE_BLOCK_S)


class Failing(ArenaMixinNode):
    """An async timer callback raises once the executor spins."""

    async def setup(self) -> None:
        self._timer = self.create_timer(0.05, self._fail)

    async def _fail(self) -> None:
        raise RuntimeError("callback failed")


class Plain(rclpy.node.Node):
    """Plain node with a timer, publishers and a service, spun on the events executor."""

    def __init__(self) -> None:
        super().__init__("teardown_plain")
        self._pubs = [self.create_publisher(String, f"teardown_plain_{i}", 10) for i in range(40)]
        self.create_service(SetBool, "teardown_plain_flag", lambda req, res: res)
        self._ready = False
        self.create_timer(0.05, self._tick)

    def _tick(self) -> None:
        for pub in self._pubs:
            pub.publish(String(data="tick"))
        if not self._ready:
            self._ready = True
            print("READY", flush=True)


def main() -> None:
    mode = sys.argv[1]
    if mode == "async_storm":
        Storm.run_main("teardown_storm")
    elif mode == "async_stall":
        Stall.run_main("teardown_stall")
    elif mode == "watchdog_deadline":
        Deadline.run_main("teardown_deadline")
    elif mode == "callback_failure":
        Failing.run_main("teardown_callback_failure")
    elif mode == "sync_events":
        rclpy.init()
        spin_node(Plain(), executor=create_executor())
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
