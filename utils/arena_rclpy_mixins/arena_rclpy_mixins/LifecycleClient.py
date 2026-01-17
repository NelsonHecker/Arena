import asyncio
import os

import lifecycle_msgs.msg
import lifecycle_msgs.srv
import rclpy.node

from arena_rclpy_mixins.Async import AsyncNode
from arena_rclpy_mixins.Time import TimeNode


class LifecycleClient(TimeNode, rclpy.node.Node):
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)

    def get_lifecycle_state(self, node_name: str, *, timeout: float | None = None, **kwargs) -> lifecycle_msgs.msg.State:
        """
        Get state of lifecycle node
        """
        cli = self.create_client(
            lifecycle_msgs.srv.GetState,
            name := os.path.join(node_name, 'get_state'),
            **kwargs,
        )
        if not cli.wait_for_service(timeout_sec=timeout):  # type: ignore
            raise RuntimeError(f'timed out waiting for {name} after {timeout} secs')
        return cli.call(lifecycle_msgs.srv.GetState.Request()).current_state

    def get_available_lifecycle_states(self, node_name: str, *, timeout: float | None = None, **kwargs) -> list[lifecycle_msgs.msg.State]:
        """
        Get available lifecycle states
        """
        cli = self.create_client(
            lifecycle_msgs.srv.GetAvailableStates,
            name := os.path.join(node_name, 'get_available_states'),
            **kwargs,
        )

        if not cli.wait_for_service(timeout_sec=timeout):  # type: ignore
            raise RuntimeError(f'timed out waiting for {name} after {timeout} secs')
        return cli.call(lifecycle_msgs.srv.GetAvailableStates.Request()).available_states

    def get_available_lifecycle_transitions(self, node_name: str, *, timeout: float | None = None, **kwargs) -> list[lifecycle_msgs.msg.Transition]:
        """
        Get available lifecycle transitions
        """
        cli = self.create_client(
            lifecycle_msgs.srv.GetAvailableTransitions,
            name := os.path.join(node_name, 'get_available_transitions'),
            **kwargs,
        )

        if not cli.wait_for_service(timeout_sec=timeout):  # type: ignore
            raise RuntimeError(f'timed out waiting for {name} after {timeout} secs')
        return cli.call(lifecycle_msgs.srv.GetAvailableTransitions.Request()).available_transitions

    def change_lifecycle_state(self, node_name: str, transition: lifecycle_msgs.msg.Transition | int, *, timeout: float | None = None, **kwargs) -> bool:
        """
        Set state of lifecycle node
        """
        if isinstance(transition, int):
            transition = lifecycle_msgs.msg.Transition(id=transition)
        cli = self.create_client(
            lifecycle_msgs.srv.ChangeState,
            name := os.path.join(node_name, 'change_state'),
            **kwargs,
        )

        if not cli.wait_for_service(timeout_sec=timeout):  # type: ignore
            raise RuntimeError(f'timed out waiting for {name} after {timeout} secs')
        return cli.call(lifecycle_msgs.srv.ChangeState.Request(transition=transition)).success

    async def wait_for_lifecycle_state(self, node_name: str, desired_state: lifecycle_msgs.msg.State | int, *, check_interval: float = 0.5, timeout: float | None = None, **kwargs) -> bool:
        """
        Asynchronously wait for lifecycle node to reach desired state
        """
        if isinstance(desired_state, int):
            desired_state = lifecycle_msgs.msg.State(id=desired_state)
        start_time = self.wall_time
        while True:
            current_state = self.get_lifecycle_state(node_name, timeout=timeout, **kwargs)
            if current_state.id == desired_state.id:
                return True
            if timeout is not None:
                if (self.wall_time - start_time).to_seconds() >= timeout:
                    return False
            await asyncio.sleep(check_interval)


class AsyncLifecycleClient(AsyncNode):
    async def get_lifecycle_state_async(self, node_name: str, *, timeout: float | None = None, **kwargs) -> lifecycle_msgs.msg.State:
        """
        Asynchronously get state of lifecycle node
        """
        cli = self.create_client_wrapper(
            lifecycle_msgs.srv.GetState,
            os.path.join(node_name, 'get_state'),
            **kwargs,
        )

        await cli.ensure(timeout_sec=timeout)
        res = await cli.call_timeout(lifecycle_msgs.srv.GetState.Request(), timeout_sec=timeout)
        assert res is not None
        return res.current_state

    async def get_available_lifecycle_states_async(self, node_name: str, *, timeout: float | None = None, **kwargs) -> list[lifecycle_msgs.msg.State]:
        """
        Asynchronously get available lifecycle states
        """
        cli = self.create_client_wrapper(
            lifecycle_msgs.srv.GetAvailableStates,
            os.path.join(node_name, 'get_available_states'),
            **kwargs,
        )
        await cli.ensure(timeout_sec=timeout)
        res = await cli.call_timeout(lifecycle_msgs.srv.GetAvailableStates.Request(), timeout_sec=timeout)
        assert res is not None
        return res.available_states

    async def get_available_lifecycle_transitions_async(self, node_name: str, *, timeout: float | None = None, **kwargs) -> list[lifecycle_msgs.msg.Transition]:
        """
        Asynchronously get available lifecycle transitions
        """
        cli = self.create_client_wrapper(
            lifecycle_msgs.srv.GetAvailableTransitions,
            os.path.join(node_name, 'get_available_transitions'),
            **kwargs,
        )
        await cli.ensure(timeout_sec=timeout)
        res = await cli.call_timeout(lifecycle_msgs.srv.GetAvailableTransitions.Request(), timeout_sec=timeout)
        assert res is not None
        return res.available_transitions

    async def change_lifecycle_state_async(self, node_name: str, transition: lifecycle_msgs.msg.Transition | int, *, timeout: float | None = None, **kwargs) -> bool:
        """
        Asynchronously set state of lifecycle node
        """
        if isinstance(transition, int):
            transition = lifecycle_msgs.msg.Transition(id=transition)
        cli = self.create_client_wrapper(
            lifecycle_msgs.srv.ChangeState,
            os.path.join(node_name, 'change_state'),
            **kwargs,
        )
        await cli.ensure(timeout_sec=timeout)
        res = await cli.call_timeout(lifecycle_msgs.srv.ChangeState.Request(transition=transition), timeout_sec=timeout)
        assert res is not None
        return res.success

    async def wait_for_lifecycle_state_async(self, node_name: str, desired_state: lifecycle_msgs.msg.State | int, *, check_interval: float = 0.5, timeout: float | None = None, **kwargs) -> bool:
        """
        Asynchronously wait for lifecycle node to reach desired state
        """

        if isinstance(desired_state, int):
            desired_state = lifecycle_msgs.msg.State(id=desired_state)
        start_time = self.wall_time
        while True:

            current_state = await self.get_lifecycle_state_async(node_name, timeout=timeout, **kwargs)
            if current_state.id == desired_state.id:
                return True
            if timeout is not None:
                if (self.wall_time - start_time).to_seconds() >= timeout:
                    return False
            await asyncio.sleep(check_interval)
