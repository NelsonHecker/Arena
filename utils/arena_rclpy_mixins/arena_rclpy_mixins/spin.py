"""Process-spin helpers: clean rclpy teardown across SIGINT/SIGTERM."""

from __future__ import annotations

import contextlib
from collections.abc import Iterator

import rclpy
import rclpy.executors
import rclpy.node
from rclpy.executors import ExternalShutdownException


@contextlib.contextmanager
def spin_context(
    *,
    executor: rclpy.executors.Executor | None = None,
) -> Iterator[None]:
    """Wrap a custom mainloop with robust teardown.

    First SIGINT/external shutdown exits the body; subsequent KeyboardInterrupts
    during shutdown are swallowed so finalizers don't get torn apart mid-call.

    Caller-supplied executor is shut down on exit (we own what we're handed).
    A None executor means the body relies on rclpy.spin's implicit global, which
    rclpy.shutdown cleans up.

    Body drives its own spin::

        with spin_context(executor=exec):
            while rclpy.ok():
                exec.spin_once(timeout_sec=0.1)
                do_other_work()
    """
    try:
        yield
    except (KeyboardInterrupt, ExternalShutdownException):
        pass
    finally:
        with contextlib.suppress(KeyboardInterrupt):
            if executor is not None:
                executor.shutdown()
            if rclpy.ok():
                rclpy.shutdown()


def spin_node(node: rclpy.node.Node, **kwargs: object) -> None:
    """Spin a single node until shutdown. Forwards kwargs to spin_context."""
    executor = kwargs.get("executor")
    with spin_context(**kwargs):
        try:
            rclpy.spin(node, executor=executor)
        finally:
            with contextlib.suppress(KeyboardInterrupt):
                node.destroy_node()
