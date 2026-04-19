"""ROS node that exposes per-TaskKind action servers for the configured bringup."""

import threading

import rclpy
import tf2_ros
from rclpy.action import ActionServer
from rclpy.action.server import ServerGoalHandle
from rclpy.node import Node

from arena_robots.bringup import check_caps, get_bringup
from arena_robots.Robot import RobotIdentifier
from arena_robots.task_kinds import TaskKind, action_type, endpoint
from arena_robots.task_server_handlers import HANDLERS


class TaskServerNode(Node):
    def __init__(self) -> None:
        super().__init__("task_server")

        robot_name = self.declare_parameter("robot_name", "").value
        bringup_kind = self.declare_parameter("bringup_kind", "").value

        if not robot_name:
            raise RuntimeError("Parameter 'robot_name' is required")
        if not bringup_kind:
            raise RuntimeError("Parameter 'bringup_kind' is required")

        namespace = self.get_namespace()

        robot = RobotIdentifier(robot_name).resolve_sync()

        self._tf_buffer = tf2_ros.Buffer()
        tf2_ros.TransformListener(self._tf_buffer, self)

        self._bringup = get_bringup(bringup_kind)(robot, namespace)
        check_caps(self._bringup)

        # Single-goal-per-TaskKind: a new accepted goal preempts the previous.
        # The preempted handler sees ``goal_handle.is_active == False`` and
        # bails without retrying, so the newest goal is the only one nav2 sees.
        self._current_handles: dict[TaskKind, ServerGoalHandle] = {}
        self._handle_lock = threading.Lock()

        self._servers: list[ActionServer] = []
        for tk in self._bringup.accepts_task_kinds:
            handler_cls = HANDLERS.get((tk, self._bringup.kind))
            handler = handler_cls(self._bringup, tf_buffer=self._tf_buffer, node=self)
            server = ActionServer(
                self,
                action_type(tk),
                endpoint(namespace, tk),
                execute_callback=handler.execute,
                handle_accepted_callback=self._make_handle_accepted(tk),
            )
            self._servers.append(server)

    def _make_handle_accepted(self, tk: TaskKind) -> object:
        def _handle_accepted(goal_handle: ServerGoalHandle) -> None:
            with self._handle_lock:
                prev = self._current_handles.get(tk)
                self._current_handles[tk] = goal_handle
            if prev is not None and prev.is_active:
                prev.abort()
            goal_handle.execute()

        return _handle_accepted


def main(args: list[str] | None = None) -> None:
    rclpy.init(args=args)
    node = TaskServerNode()
    try:
        rclpy.spin(node)
    finally:
        node.destroy_node()
        rclpy.shutdown()


if __name__ == "__main__":
    main()
