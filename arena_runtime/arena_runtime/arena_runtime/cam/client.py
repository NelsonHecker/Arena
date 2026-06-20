"""ROS 2 client for the Arena viewport camera (`/arena/viewport/*`).

`CamNode` wraps the viewport services and the `cmd_view` stream so the `Camera`
facade can drive the GUI user-camera from an external process. It runs via
`run_main`: `setup` ensures the services, plays the timeline, then shuts down.

It drives a segment two ways. LIVE: stream keyframes on `cmd_view`, paced by
wall-clock. RECORD: walk the segment at a fixed fps and `capture` each frame
synchronously, so the output is deterministic and independent of render speed.
"""

from __future__ import annotations

import asyncio
import typing

import rclpy
from arena_rclpy_mixins import ArenaMixinNode
from arena_runtime_msgs.msg import ViewportView
from arena_runtime_msgs.srv import (
    ViewportCapture,
    ViewportSetProjection,
    ViewportSetReferenceFrame,
    ViewportSetView,
)
from geometry_msgs.msg import Point, Pose, PoseStamped, Quaternion
from rclpy.duration import Duration
from rclpy.qos import HistoryPolicy, QoSProfile, ReliabilityPolicy

from . import curves
from .curves import Quat, Vec3
from .record import Recorder

if typing.TYPE_CHECKING:
    from collections.abc import Callable

    from arena_rclpy_mixins.Async import ClientWrapper

    from .camera import Camera

    # A frame sampler: eased progress in [0, 1] -> (position, quat, fov).
    Frame = Callable[[float], tuple[Vec3, Quat, float]]

# Best-effort, deep queue: the plugin buffers keyframes, so none should be dropped.
_STREAM_QOS = QoSProfile(depth=64, history=HistoryPolicy.KEEP_LAST, reliability=ReliabilityPolicy.BEST_EFFORT)

_REFERENCE_MODES = {
    "full": ViewportSetReferenceFrame.Request.FULL,
    "yaw": ViewportSetReferenceFrame.Request.YAW_ONLY,
    "position": ViewportSetReferenceFrame.Request.POSITION_ONLY,
}

# cmd_view publish rate for streamed segments (Hz, wall-clock LIVE mode).
_FRAME_RATE = 60.0

# Keyframes are stamped this far ahead, so the plugin's buffer rides out publish
# stalls up to this long. The cost is this much added view latency.
_LEAD = 0.3


def _ros_pose(position: Vec3, quat: Quat) -> Pose:
    return Pose(
        position=Point(x=float(position[0]), y=float(position[1]), z=float(position[2])),
        orientation=Quaternion(w=float(quat[0]), x=float(quat[1]), y=float(quat[2]), z=float(quat[3])),
    )


class CamNode(ArenaMixinNode):
    """Standalone node that plays a `Camera` timeline against `/arena/viewport/*`."""

    def __init__(
        self,
        *,
        timeline: Camera,
        arena_ns: str = "/arena",
        node_name: str = "arena_cam",
        record: tuple[str, float] | None = None,
    ) -> None:
        super().__init__(node_name)
        self._timeline = timeline
        ns = arena_ns.rstrip("/")
        self._set_view = self.create_client_wrapper(ViewportSetView, f"{ns}/viewport/set_view", timeout=10.0)
        self._set_reference = self.create_client_wrapper(
            ViewportSetReferenceFrame, f"{ns}/viewport/set_reference_frame", timeout=10.0
        )
        self._set_projection = self.create_client_wrapper(
            ViewportSetProjection, f"{ns}/viewport/set_projection", timeout=10.0
        )
        # Generous timeout: a capture round-trips a full rendered frame.
        self._capture = self.create_client_wrapper(ViewportCapture, f"{ns}/viewport/capture", timeout=30.0)
        self._cmd_view = self.create_publisher(ViewportView, f"{ns}/viewport/cmd_view", _STREAM_QOS)
        self._camera_pose: tuple[Vec3, Quat] | None = None
        self.create_subscription(PoseStamped, f"{ns}/viewport/camera_pose", self._on_camera_pose, 10)
        self._recorder = Recorder(*record) if record is not None else None

    async def setup(self) -> None:
        if not await self._set_view.ensure(timeout_sec=10.0):
            self.get_logger().error("no /arena/viewport/* services, is the gazebo GUI up? (headless has none)")
        elif self._recorder is not None and not await self._capture.ensure(timeout_sec=10.0):
            self.get_logger().error("no /arena/viewport/capture service, rebuild the plugin for record mode")
        else:
            self.get_logger().info(f"viewport connected, {'recording' if self._recorder else 'playing'} shot")
            await asyncio.sleep(0.3)  # let a camera_pose arrive to seed the cursor
            await self._timeline.run(self)
            if rclpy.ok():
                if self._recorder is not None:
                    self.get_logger().info(f"recorded {self._recorder.n} frames to {self._recorder.dir}")
                else:
                    self.get_logger().info("shot complete")
        rclpy.try_shutdown()

    def ok(self) -> bool:
        """False once the rclpy context is shutting down, so streaming stops cleanly."""
        return rclpy.ok()

    def _on_camera_pose(self, msg: PoseStamped) -> None:
        p, q = msg.pose.position, msg.pose.orientation
        self._camera_pose = ((p.x, p.y, p.z), (q.w, q.x, q.y, q.z))

    def camera_pose(self) -> tuple[Vec3, Quat] | None:
        """Latest viewport camera world pose (position, quat), or None if not yet seen."""
        return self._camera_pose

    # low-level verbs ------------------------------------------------------

    async def look(self, eye: Vec3, target: Vec3, fov: float = 0.0) -> bool:
        if self._recorder is not None:
            return await self._record_frame(eye, curves.look_at_quat(eye, target), False, fov)
        req = ViewportSetView.Request()
        req.eye = Point(x=float(eye[0]), y=float(eye[1]), z=float(eye[2]))
        req.target = Point(x=float(target[0]), y=float(target[1]), z=float(target[2]))
        req.fov = float(fov)
        return await self._call(self._set_view, req)

    async def set_reference(self, entity: str = "", pose: tuple[Vec3, Quat] | None = None, mode: str = "full") -> bool:
        req = ViewportSetReferenceFrame.Request()
        req.entity = entity
        req.has_pose = pose is not None
        if pose is not None:
            req.pose = _ros_pose(pose[0], pose[1])
        req.mode = _REFERENCE_MODES[mode]
        return await self._call(self._set_reference, req)

    async def set_projection(self, projection: str) -> bool:
        req = ViewportSetProjection.Request()
        req.projection = projection
        return await self._call(self._set_projection, req)

    def stream(self, position: Vec3, quat: Quat, world_orientation: bool = False, fov: float = 0.0) -> None:
        if not rclpy.ok():
            return
        msg = ViewportView()
        msg.target_time = (self.get_clock().now() + Duration(seconds=_LEAD)).to_msg()
        msg.pose = _ros_pose(position, quat)
        msg.world_orientation = bool(world_orientation)
        msg.fov = float(fov)
        self._cmd_view.publish(msg)

    async def drive(self, duration: float, world_orientation: bool, frame_at: Frame) -> None:
        """Play one segment by sampling `frame_at(t)` over t in [0, 1].

        Record mode walks a fixed `duration * fps` frames and captures each one
        synchronously, so timing is exact. Live mode streams on `cmd_view` paced by
        wall-clock, so a starved step jumps to the right point rather than running
        the whole move in slow motion.
        """
        if self._recorder is not None:
            frames = max(1, round(duration * self._recorder.fps))
            for i in range(frames):
                if not rclpy.ok():
                    return
                pos, quat, fov = frame_at((i + 1) / frames)
                if not await self._record_frame(pos, quat, world_orientation, fov):
                    return
            return
        if duration <= 0.0:
            pos, quat, fov = frame_at(1.0)
            self.stream(pos, quat, world_orientation, fov)
            return
        loop = asyncio.get_running_loop()
        start = loop.time()
        period = 1.0 / _FRAME_RATE
        while rclpy.ok():
            t = min(1.0, (loop.time() - start) / duration)
            pos, quat, fov = frame_at(t)
            self.stream(pos, quat, world_orientation, fov)
            if t >= 1.0:
                break
            await asyncio.sleep(period)

    async def capture(self, position: Vec3, quat: Quat, world_orientation: bool, fov: float) -> object | None:
        req = ViewportCapture.Request()
        req.pose = _ros_pose(position, quat)
        req.world_orientation = bool(world_orientation)
        req.fov = float(fov)
        try:
            return await self._capture.call_timeout(req)
        except Exception as e:
            self.get_logger().warning(f"capture call failed: {e}")
            return None

    async def _record_frame(self, position: Vec3, quat: Quat, world_orientation: bool, fov: float) -> bool:
        res = await self.capture(position, quat, world_orientation, fov)
        if res is None or not res.success:
            detail = "service timed out" if res is None else res.message
            self.get_logger().warning(f"capture failed ({detail}), stopping record")
            return False
        self._recorder.write(res.image)
        return True

    async def _call(self, client: ClientWrapper, req: object) -> bool:
        try:
            res = await client.call_timeout(req)
        except Exception as e:
            self.get_logger().warning(f"viewport call failed: {e}")
            return False
        if res is None:
            self.get_logger().warning("viewport service timed out")
            return False
        if not res.success:
            self.get_logger().warning(f"viewport call rejected: {res.message}")
        return res.success
