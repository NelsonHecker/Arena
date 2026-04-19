from __future__ import annotations

from arena_robots.task_kinds import TaskKind, action_type, endpoint
from arena_robots.clients import Client, register_client


@register_client
class GotoPoseClient(Client):
    task_kind = TaskKind.GOTO_POSE

    def __init__(self, robot, namespace, *, node, tf_buffer) -> None:
        super().__init__(robot, namespace, node=node, tf_buffer=tf_buffer)
        self._action = node.create_action_client_wrapper(
            action_type(self.task_kind),
            self.action_endpoint(),
        )
        self._goal_handle = None
        self._result = None
        self._status = None
        self._feedback = None
        self._done = None
        self._result_future = None

    def action_endpoint(self) -> str:
        return endpoint(self.namespace, self.task_kind)

    async def wait_ready(self) -> None:
        await self._action.ensure()

    async def send_goal(self, goal) -> object:
        self._done = False
        self._result = None
        self._status = None
        self._feedback = None
        self._result_future = None
        self._goal_handle = await self._action.send_goal(goal, feedback_callback=self._on_feedback)
        self._result_future = self._goal_handle.get_result_async()
        self._result_future.add_done_callback(self._on_result)
        return self._goal_handle

    async def await_result(self) -> object:
        if self._goal_handle is None:
            raise RuntimeError("No goal in flight; call send_goal first.")
        result_response = await self._action.await_result(self._goal_handle)
        self._result = result_response.result
        self._status = result_response.result.status if result_response.result is not None else None
        self._done = True
        return self._result

    def is_done(self) -> bool | None:
        return self._done

    def cancel(self) -> None:
        if self._goal_handle is not None:
            self._goal_handle.cancel_goal_async()

    @property
    def status(self) -> int | None:
        return self._status

    @property
    def feedback(self):
        return self._feedback

    def _on_feedback(self, msg) -> None:
        self._feedback = msg.feedback

    def _on_result(self, future) -> None:
        if future is not self._result_future:
            return
        try:
            result_response = future.result()
        except Exception:
            self._done = True
            return
        self._result = result_response.result
        self._status = result_response.result.status if result_response.result is not None else None
        self._done = True
