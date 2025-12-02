import asyncio
import functools
import inspect
import typing

import launch
import rclpy.client
import rclpy.node
import rclpy.qos

T = typing.TypeVar('T')


class AsyncLaunchManager:
    def __init__(self):
        self.active_tasks = set()

    async def launch_description(self, description: launch.LaunchDescription):
        """ Launch a launch description asynchronously

        Args:
            description (launch.LaunchDescription): _launch description to launch
        """
        ls = launch.LaunchService()
        ls.include_launch_description(description)
        task = asyncio.create_task(ls.run_async())
        self.active_tasks.add(task)
        task.add_done_callback(self.active_tasks.discard)
        return task

    async def kill_all(self):
        """ Kill all active launch description tasks asynchronously
        """
        if not self.active_tasks:
            return
        for task in self.active_tasks:
            if not task.done():
                task.cancel()
        await asyncio.gather(*self.active_tasks, return_exceptions=True)


class AsyncUtil(rclpy.node.Node):
    """Async utils for rclpy nodes.
    """

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self._loop: asyncio.AbstractEventLoop = asyncio.get_running_loop()
        self._launch_manager = AsyncLaunchManager()

    @property
    def event_loop(self) -> asyncio.AbstractEventLoop:
        """active event loop of node
        """
        return self._loop

    @event_loop.setter
    def event_loop(self, loop: asyncio.AbstractEventLoop) -> None:
        self._loop = loop

    async def wait_for_service_async(
        self,
        client: rclpy.client.Client,
        timeout: float | None = None,
        interval: float = 0.1,
    ) -> bool:
        """
        Asynchronously wait for service to be available
        """
        start_time = self.get_clock().now()
        while True:
            if client.wait_for_service(timeout_sec=interval):
                return True
            if timeout is not None:
                elapsed = (self.get_clock().now() - start_time).nanoseconds / 1e9
                if elapsed >= timeout:
                    return False
            await asyncio.sleep(interval)

    async def do_launch(self, launch_description: launch.LaunchDescription) -> None:
        """
        Asynchronously launch a launch description
        """
        async def _launcher():
            await self._launch_manager.launch_description(launch_description)
        asyncio.run_coroutine_threadsafe(_launcher(), self._loop)

    def wait_for(self, future: typing.Awaitable[T]) -> T:
        """
        Wait for an awaitable to complete in a blocking manner
        """
        async def coro() -> T:
            return await future
        return asyncio.run_coroutine_threadsafe(coro(), self.event_loop).result()

    def sync_wrap(self, fn: typing.Callable[..., typing.Awaitable[T]]) -> typing.Callable[..., T]:
        """
        Wrap an asynchronous function to be called synchronously
        """
        @functools.wraps(fn)
        def sync_fn(*args, **kwargs) -> T:
            return self.wait_for(fn(*args, **kwargs))
        return sync_fn

    def syncify(self, fn: typing.Callable[..., T] | typing.Callable[..., typing.Awaitable[T]]) -> typing.Callable[..., T]:
        """
        Wrap any function to be called synchronously
        """
        if inspect.iscoroutinefunction(fn):
            return self.sync_wrap(fn)

        @functools.wraps(fn)
        def sync_fn(*args, **kwargs) -> T:
            result = fn(*args, **kwargs)
            if inspect.isawaitable(result):
                return self.wait_for(result)
            return result
        return sync_fn

    async def await_ros(self, ros_future: asyncio.Future[T]) -> T:
        """
        Wraps a ROS Future into an Asyncio Future so it can be awaited.
        """
        aio_future = self._loop.create_future()

        def on_ros_done(fut):
            if aio_future.cancelled():
                return

            try:
                result = fut.result()
                self._loop.call_soon_threadsafe(aio_future.set_result, result)
            except Exception as e:
                self._loop.call_soon_threadsafe(aio_future.set_exception, e)

        ros_future.add_done_callback(on_ros_done)

        return await aio_future

    # rclpy.node.Node overrides
    def create_subscription(self, msg_type, topic: str, callback: typing.Callable[[rclpy.node.MsgType], None] | typing.Callable[[rclpy.node.MsgType], typing.Awaitable[None]], qos_profile: rclpy.client.QoSProfile | int, *, callback_group: rclpy.client.CallbackGroup | None = None, event_callbacks: rclpy.node.SubscriptionEventCallbacks | None = None, qos_overriding_options: rclpy.node.QoSOverridingOptions | None = None, raw: bool = False) -> rclpy.node.Subscription:
        callback = self.syncify(callback)
        return super().create_subscription(msg_type, topic, callback, qos_profile, callback_group=callback_group, event_callbacks=event_callbacks, qos_overriding_options=qos_overriding_options, raw=raw)

    def create_service(self, srv_type, srv_name: str, callback: typing.Callable[[rclpy.node.SrvTypeRequest, rclpy.node.SrvTypeResponse], rclpy.node.SrvTypeResponse] | typing.Callable[[rclpy.node.SrvTypeRequest, rclpy.node.SrvTypeResponse], typing.Awaitable[rclpy.node.SrvTypeResponse]], *, qos_profile: rclpy.client.QoSProfile = rclpy.qos.qos_profile_services_default, callback_group: rclpy.client.CallbackGroup | None = None) -> rclpy.node.Service:
        callback = self.syncify(callback)
        return super().create_service(srv_type, srv_name, callback, qos_profile=qos_profile, callback_group=callback_group)
