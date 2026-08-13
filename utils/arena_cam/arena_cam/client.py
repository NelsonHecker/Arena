"""ROS 2 client for the Arena viewport cameras.

`CamNode` fans a single `Camera` timeline out across one or more viewport surfaces:
the sim GUI camera at `/arena/viewport/*` and any number of per-env rviz cameras at
`/arena/env_<id>/task_generator_node/viewport/*`. The `Camera` facade authors the
shot in world coordinates. Each endpoint subtracts its env's world origin (the
registry `reference`) so the same absolute shot lands at the matching place in every
env. That localization stops once a reference frame is set: the camera pose is then
composed as reference * local, so poses are relative to the reference and only the
reference pose itself is localized. The sim endpoint has a zero offset.

It runs via `run_main`: `setup` discovers the selected endpoints, plays the timeline,
then shuts down. A segment drives two ways. LIVE: stream keyframes on `cmd_view`,
paced by wall-clock. RECORD: walk the segment at a fixed fps and `capture` each frame
synchronously, so the output is deterministic. Record requires a single endpoint.
"""

from __future__ import annotations

import asyncio
import typing

import rclpy
from arena_rclpy_mixins import ArenaMixinNode
from arena_runtime_msgs.msg import EnvRegistry
from geometry_msgs.msg import Point, PoseStamped
from rclpy.duration import Duration
from viewport_control_msgs.msg import ViewportView
from viewport_control_msgs.srv import (
    ViewportCapture,
    ViewportSetProjection,
    ViewportSetReferenceFrame,
    ViewportSetView,
)

from . import curves, surfaces
from .curves import Quat, Vec3
from .record import Recorder
from .surfaces import TargetSelection

if typing.TYPE_CHECKING:
    from collections.abc import Callable

    from arena_rclpy_mixins.Async import ClientWrapper

    from .camera import Camera

    # A frame sampler: eased progress in [0, 1] -> (position, quat, fov).
    Frame = Callable[[float], tuple[Vec3, Quat, float]]

# cmd_view publish rate for streamed segments (Hz, wall-clock LIVE mode).
_FRAME_RATE = 60.0

# Keyframes are stamped this far ahead, so the plugin's buffer rides out publish
# stalls up to this long. The cost is this much added view latency, which the
# interactive driver trades away for responsiveness (see drive.DRIVE_LEAD).
LEAD = 0.3


class _Endpoint:
    """One viewport surface: its namespace, its world->local offset, and ROS handles."""

    def __init__(self, node: CamNode, ns: str, offset: tuple[float, float]) -> None:
        self.ns = ns
        self._ox, self._oy = offset
        self.set_view = node.create_client_wrapper(ViewportSetView, f"{ns}/viewport/set_view", timeout=10.0)
        self.set_reference = node.create_client_wrapper(ViewportSetReferenceFrame, f"{ns}/viewport/set_reference_frame", timeout=10.0)
        self.set_projection = node.create_client_wrapper(ViewportSetProjection, f"{ns}/viewport/set_projection", timeout=10.0)
        # Generous timeout: a capture round-trips a full rendered frame.
        self.capture = node.create_client_wrapper(ViewportCapture, f"{ns}/viewport/capture", timeout=30.0)
        self.cmd_view = node.create_publisher(ViewportView, f"{ns}/viewport/cmd_view", surfaces.STREAM_QOS)
        self._pose: tuple[Vec3, Quat] | None = None
        node.create_subscription(PoseStamped, f"{ns}/viewport/camera_pose", self._on_pose, 10)

    def _on_pose(self, msg: PoseStamped) -> None:
        p, q = msg.pose.position, msg.pose.orientation
        self._pose = ((p.x, p.y, p.z), (q.w, q.x, q.y, q.z))

    def localize(self, position: Vec3) -> Vec3:
        """World coords -> this env's local frame (pure planar offset, no rotation)."""
        return surfaces.localize((self._ox, self._oy), position)

    def world_pose(self) -> tuple[Vec3, Quat] | None:
        """Latest camera pose lifted back into world coords, or None if not yet seen."""
        if self._pose is None:
            return None
        (x, y, z), q = self._pose
        return ((x + self._ox, y + self._oy, z), q)


class CamNode(ArenaMixinNode):
    """Standalone node that plays a `Camera` timeline against the selected viewports."""

    def __init__(
        self,
        *,
        timeline: Camera,
        targets: TargetSelection,
        node_name: str = "arena_cam",
        record: tuple[str, float] | None = None,
        lead: float = LEAD,
    ) -> None:
        super().__init__(node_name)
        self._timeline = timeline
        self._selection = targets
        self.lead = lead
        self._recorder = Recorder(*record) if record is not None else None
        self._env_refs: dict[int, tuple[float, float]] = {}
        self._endpoints: list[_Endpoint] = []
        # True once a reference frame is set: from then on poses are relative to it and
        # must not be localized. Until then the reference is identity and the env offset
        # is what maps an absolute shot into each env.
        self._referenced = False

    async def setup(self) -> None:
        self.create_subscription(EnvRegistry, surfaces.ENVS_TOPIC, self._on_envs, surfaces.ENVS_QOS)

        found = await self._await_endpoints()
        if not found:
            self.get_logger().error("no viewport targets found, is the sim GUI / rviz up? (headless sim has none)")
            rclpy.try_shutdown()
            return
        if self._recorder is not None and len(found) != 1:
            self.get_logger().error(f"record needs exactly one target, found {len(found)}, narrow with --sim or --viz <env_id>")
            rclpy.try_shutdown()
            return

        self._endpoints = [_Endpoint(self, ns, offset) for ns, offset in found]
        reachable: list[_Endpoint] = []
        for endpoint in self._endpoints:
            if await endpoint.set_view.ensure(timeout_sec=10.0):
                reachable.append(endpoint)
            else:
                self.get_logger().warning(f"{endpoint.ns}/viewport did not answer, skipping")
        self._endpoints = reachable

        if not self._endpoints:
            self.get_logger().error("no reachable viewport targets")
        elif self._recorder is not None and not await self._endpoints[0].capture.ensure(timeout_sec=10.0):
            self.get_logger().error("no viewport/capture service, rebuild the plugin for record mode")
        else:
            names = ", ".join(endpoint.ns for endpoint in self._endpoints)
            self.get_logger().info(f"viewport connected ({names}), {'recording' if self._recorder else 'playing'} shot")
            await asyncio.sleep(0.3)  # let a camera_pose arrive to seed the cursor
            await self._timeline.run(self)
            if rclpy.ok():
                if self._recorder is not None:
                    self.get_logger().info(f"recorded {self._recorder.n} frames to {self._recorder.dir}")
                else:
                    self.get_logger().info("shot complete")
        rclpy.try_shutdown()

    def _on_envs(self, msg: EnvRegistry) -> None:
        self._env_refs = surfaces.env_refs(msg)

    async def _await_endpoints(self) -> list[tuple[str, tuple[float, float]]]:
        """Wait for the selected viewport surfaces to appear, then resolve their offsets."""
        waited = 0.0
        while rclpy.ok():
            if self._find_targets():
                await asyncio.sleep(1.0)  # settle to catch stragglers and let the env table land
                return self._find_targets()
            await asyncio.sleep(0.5)
            waited += 0.5
            if waited >= 10.0 and (waited % 10.0) < 0.5:
                self.get_logger().warning(f"arena cam: waiting for viewport targets ({waited:.0f}s elapsed)")
        return []

    def _find_targets(self) -> list[tuple[str, tuple[float, float]]]:
        names = [name for name, _types in self.get_service_names_and_types()]
        return surfaces.find_targets(names, self._selection, self._env_refs)

    def ok(self) -> bool:
        """False once the rclpy context is shutting down, so streaming stops cleanly."""
        return rclpy.ok()

    def camera_pose(self) -> tuple[Vec3, Quat] | None:
        """A representative camera world pose to seed the cursor, or None if not yet seen."""
        for endpoint in self._endpoints:
            pose = endpoint.world_pose()
            if pose is not None:
                return pose
        return None

    def _local(self, endpoint: _Endpoint, position: Vec3) -> Vec3:
        """World coords -> endpoint-local, unless a reference is set (poses are relative to it)."""
        return position if self._referenced else endpoint.localize(position)

    # low-level verbs ------------------------------------------------------

    async def look(self, eye: Vec3, target: Vec3, fov: float = 0.0) -> bool:
        if self._recorder is not None:
            return await self._record_frame(self._endpoints[0], eye, curves.look_at_quat(eye, target), False, fov)
        ok = True
        for endpoint in self._endpoints:
            req = ViewportSetView.Request()
            eye_local, target_local = self._local(endpoint, eye), self._local(endpoint, target)
            req.eye = Point(x=float(eye_local[0]), y=float(eye_local[1]), z=float(eye_local[2]))
            req.target = Point(x=float(target_local[0]), y=float(target_local[1]), z=float(target_local[2]))
            req.fov = float(fov)
            ok = await self._call(endpoint.set_view, req) and ok
        return ok

    async def set_reference(self, entity: str = "", pose: tuple[Vec3, Quat] | None = None, mode: str = "full") -> bool:
        ok = True
        for endpoint in self._endpoints:
            req = ViewportSetReferenceFrame.Request()
            req.entity = entity
            req.has_pose = pose is not None
            if pose is not None:
                # The reference pose is authored in world coords, so it localizes once here.
                req.pose = surfaces.ros_pose(endpoint.localize(pose[0]), pose[1])
            req.mode = surfaces.REFERENCE_MODES[mode]
            ok = await self._call(endpoint.set_reference, req) and ok
        self._referenced = True
        return ok

    async def set_projection(self, projection: str) -> bool:
        ok = True
        for endpoint in self._endpoints:
            req = ViewportSetProjection.Request()
            req.projection = projection
            ok = await self._call(endpoint.set_projection, req) and ok
        return ok

    def stream(self, position: Vec3, quat: Quat, world_orientation: bool = False, fov: float = 0.0) -> None:
        if not rclpy.ok():
            return
        stamp = (self.get_clock().now() + Duration(seconds=self.lead)).to_msg()
        for endpoint in self._endpoints:
            msg = ViewportView()
            msg.target_time = stamp
            msg.pose = surfaces.ros_pose(self._local(endpoint, position), quat)
            msg.world_orientation = bool(world_orientation)
            msg.fov = float(fov)
            endpoint.cmd_view.publish(msg)

    async def drive(self, duration: float, world_orientation: bool, frame_at: Frame) -> None:
        """Play one segment by sampling `frame_at(t)` over t in [0, 1].

        Record mode walks a fixed `duration * fps` frames and captures each one
        synchronously, so timing is exact. Live mode streams on `cmd_view` paced by
        wall-clock, so a starved step jumps to the right point rather than running
        the whole move in slow motion.
        """
        if self._recorder is not None:
            endpoint = self._endpoints[0]
            frames = max(1, round(duration * self._recorder.fps))
            for i in range(frames):
                if not rclpy.ok():
                    return
                pos, quat, fov = frame_at((i + 1) / frames)
                if not await self._record_frame(endpoint, pos, quat, world_orientation, fov):
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

    async def capture(self, endpoint: _Endpoint, position: Vec3, quat: Quat, world_orientation: bool, fov: float) -> object | None:
        req = ViewportCapture.Request()
        req.pose = surfaces.ros_pose(self._local(endpoint, position), quat)
        req.world_orientation = bool(world_orientation)
        req.fov = float(fov)
        try:
            return await endpoint.capture.call_timeout(req)
        except Exception as e:
            self.get_logger().warning(f"capture call failed: {e}")
            return None

    async def _record_frame(self, endpoint: _Endpoint, position: Vec3, quat: Quat, world_orientation: bool, fov: float) -> bool:
        res = await self.capture(endpoint, position, quat, world_orientation, fov)
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
