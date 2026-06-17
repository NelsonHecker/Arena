import geometry_msgs.msg as geometry_msgs
from arena_rclpy_mixins.Time import Time

from task_generator.shared import Pose
from task_generator.tasks.modules import TM_Module


class Mod_OverrideRobot(TM_Module):
    TOPIC_SET_POSITION = "initialpose"
    TOPIC_SET_GOAL = "goal_pose"
    TOPIC_NEW_SCENARIO = "clicked_point"
    PARAM_WAYPOINTS = "guided_waypoints"

    _timeouts: dict[int, Time]

    def __init__(self, *args: object, **kwargs: object) -> None:
        TM_Module.__init__(self, *args, **kwargs)

        self._timeouts = {}

        self.node.create_subscription(geometry_msgs.PoseWithCovarianceStamped, self.node.service_namespace(self.TOPIC_SET_POSITION), self._cb_set_position, 1)

        self.node.create_subscription(geometry_msgs.PoseStamped, self.node.service_namespace(self.TOPIC_SET_GOAL), self._cb_set_goal, 1)

        self.node.create_subscription(geometry_msgs.PointStamped, self.node.service_namespace(self.TOPIC_NEW_SCENARIO), self._cb_new_scenario, 1)

    def _reset_timeout(self, index: int):
        self._timeouts[index] = self.node.sim_time

    def _to_abstract(self, frame_id: str, pose: Pose) -> Pose:
        return self.node._realizer.ezilear(pose) if frame_id == 'map' else pose

    async def _cb_set_position(self, pos: geometry_msgs.PoseWithCovarianceStamped):
        await self._task.set_robot_position(self._to_abstract(pos.header.frame_id, Pose.from_msg(pos.pose.pose)))

    async def _cb_set_goal(self, pos: geometry_msgs.PoseStamped):
        await self._task.set_robot_goal(self._to_abstract(pos.header.frame_id, Pose.from_msg(pos.pose)))

    def _cb_new_scenario(self, *args: object, **kwargs: object) -> None:
        self._task.force_reset()  # type: ignore
