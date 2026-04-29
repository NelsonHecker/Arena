#! /usr/bin/env python3
import asyncio
import errno
import gc
import traceback

import rclpy
import rclpy.executors

from .node import TaskGenerator


def spin_blocking(executor: rclpy.executors.Executor) -> None:
    try:
        executor.spin()
    except rclpy.executors.ExternalShutdownException:
        pass


def _suppress_shutdown_noise(loop: asyncio.AbstractEventLoop, context: dict) -> None:
    """Drop launch-internal asyncio noise: in-process LaunchServices fight over signal handlers and double-fire process_exited."""
    exc = context.get("exception")
    if isinstance(exc, asyncio.InvalidStateError):
        return
    if not rclpy.ok():
        if isinstance(exc, AssertionError):
            return
        if isinstance(exc, OSError) and exc.errno == errno.EBADF:
            return
    loop.default_exception_handler(context)


async def app_logic(node: TaskGenerator) -> None:
    node.get_logger().info('Beginning client, shut down with CTRL-C')
    await node.setup()
    stop_event = asyncio.Event()
    await stop_event.wait()


async def main_async(args: list[str] | None = None) -> None:
    del args
    rclpy.init()
    loop = asyncio.get_running_loop()
    loop.set_exception_handler(_suppress_shutdown_noise)

    executor = rclpy.executors.MultiThreadedExecutor()

    node = TaskGenerator()
    node.event_loop = loop

    executor.add_node(node)

    spin_future = loop.run_in_executor(None, spin_blocking, executor)
    app_task = asyncio.create_task(app_logic(node))

    try:
        import aiomonitor

        with aiomonitor.start_monitor(loop=loop, locals=locals()):
            done, _ = await asyncio.wait([spin_future, app_task], return_when=asyncio.FIRST_COMPLETED)

        if spin_future in done:
            spin_future.result()

        if app_task in done:
            app_task.result()

    except asyncio.CancelledError:
        node.get_logger().info('Shutting down.')
    except Exception:
        node.get_logger().error(traceback.format_exc())
        raise
    finally:
        if not app_task.done():
            app_task.cancel()

        await node._launch_manager.kill_all()

        executor.shutdown()

        try:
            await spin_future
        except Exception:
            pass

        executor.remove_node(node)
        node.destroy_node()
        # Run lingering subprocess-transport finalizers while the loop is still alive
        # so their loop.call_soon() inside __del__ doesn't hit a closed loop.
        gc.collect()
        rclpy.try_shutdown()


def main(args: list[str] | None = None) -> None:
    try:
        asyncio.run(main_async(args=args))
    except KeyboardInterrupt:
        pass


if __name__ == '__main__':
    import time

    time.sleep(5)
    main()
