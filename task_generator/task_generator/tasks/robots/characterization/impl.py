"""TM_Characterization: open-loop maneuver sweep task mode.

Drives every robot in the episode directly through its full operating envelope
(linear sweep to the rated max, transient ramps, angular pivot rates) by
publishing exact ``cmd_vel`` profiles — no navigation goals, no planners.
Each maneuver is tagged with a phase marker on
``<robot_ns>/characterization_phase`` so the offline Layer 3 calculator can map
energy/acoustic samples to exact working points.

Safety: an odometry stall watchdog zeroes ``cmd_vel`` and aborts the sweep if a
robot's odom goes silent beyond ``ODOM_STALL_TIMEOUT_S``.
"""

from __future__ import annotations

import asyncio
import contextlib
import typing

from geometry_msgs.msg import Twist
from nav_msgs.msg import Odometry
from rclpy.qos import QoSProfile, ReliabilityPolicy
from std_msgs.msg import String

from task_generator.shared import Pose
from task_generator.tasks.robots import TM_Robots

from .schedule import (
    CONTROL_RATE_HZ,
    MAX_SCHEDULE_DURATION_S,
    ODOM_STALL_TIMEOUT_S,
    Phase,
    build_schedule,
    resolve_envelope,
    schedule_duration,
)

if typing.TYPE_CHECKING:
    pass


class TM_Characterization(TM_Robots):
    """Open-loop sweep: exact cmd_vel profiles through the robot's envelope."""

    _schedule: list[Phase] = []
    _finished: bool = False
    _aborted: bool = False
    _driver: asyncio.Task | None = None
    _twist_pubs: dict[str, typing.Any] = {}
    _phase_pubs: dict[str, typing.Any] = {}
    _odom_subs: list[typing.Any] = []
    _last_odom: dict[str, float] = {}
    _last_marker: dict[str, str] = {}

    async def reset(self, **kwargs: object) -> None:
        await super().reset(**kwargs)
        # Cancel any driver left over from the previous episode.
        if self._driver is not None:
            self._driver.cancel()
            with contextlib.suppress(asyncio.CancelledError):
                await self._driver
        self._finished = False
        self._aborted = False
        self._driver = None
        self._last_odom = {}
        self._last_marker = {}
        self._twist_pubs = {}
        self._phase_pubs = {}
        self._odom_subs = []

        # Place every robot near the map centre (a free cell) so the sweep's
        # out-and-back legs (max excursion ≈ 5·vx_max m) stay inside the arena.

        self._start_poses = {}
        robot_positions = list(kwargs.get("ROBOT_POSITIONS", []) or [])
        for idx, manager in enumerate(self._ctx.robots.values()):
            if idx < len(robot_positions):
                self._start_poses[manager.name] = robot_positions[idx][0]
            else:
                self._start_poses[manager.name] = await self._centre_placement()
            self._logger.info(f"TM_Characterization: {manager.name} placed at {self._start_poses[manager.name].position}")

        # The robot stack's cmd_vel consumers (twist stamper / velocity
        # smoother) subscribe RELIABLE and reject a BEST_EFFORT publisher —
        # "No messages will be sent to it" (verified in env logs). Publish
        # RELIABLE; the recorder's BEST_EFFORT subscription is compatible.
        cmd_qos = QoSProfile(depth=10, reliability=ReliabilityPolicy.RELIABLE)
        odom_qos = QoSProfile(depth=10, reliability=ReliabilityPolicy.BEST_EFFORT)

        self._schedule = []
        for manager in self._ctx.robots.values():
            model = getattr(getattr(manager, "robot", None), "model", None)
            model_name = getattr(model, "name", None) or manager.name
            envelope = resolve_envelope(model_name)
            schedule = build_schedule(vx_max=envelope["vx_max"], wz_max=envelope["wz_max"])
            if not self._schedule:
                self._schedule = schedule
            self._logger.info(
                f"TM_Characterization: {manager.name} (model={model_name}) "
                f"{len(schedule)} phases ≈ {schedule_duration(schedule):.0f}s "
                f"(vx up to {envelope['vx_max']:.2f} m/s, wz up to {envelope['wz_max']:.2f} rad/s)"
            )

            # manager.namespace is the full robot namespace (the fleet itself
            # publishes ns=str(mgr.namespace)); manager.frame is only the
            # robot's short name and would point at the wrong topics.
            ns = str(manager.namespace)
            self._twist_pubs[manager.name] = self.node.create_publisher(Twist, f"{ns}/cmd_vel", cmd_qos)
            self._phase_pubs[manager.name] = self.node.create_publisher(String, f"{ns}/characterization_phase", cmd_qos)
            self._odom_subs.append(
                self.node.create_subscription(
                    Odometry, f"{ns}/odom", self._make_odom_cb(manager.name), odom_qos
                )
            )
            self._last_odom[manager.name] = self._sim_now()

        if self._schedule:
            self._driver = asyncio.create_task(self._drive())

    async def _centre_placement(self) -> Pose:
        """A free cell closest to the map centre (fallback: random placement)."""
        from task_generator.manager.world_manager.world_manager import _occupancy_to_available
        from task_generator.shared import Orientation, Position
        from task_generator.tasks.robots._placement import random_placement

        try:
            import numpy as np

            wm = self._ctx.world_manager
            grid = wm.map.occupancy.grid
            rows, cols = grid.shape
            available = _occupancy_to_available(grid, 0.0)
            if len(available) > 0:
                # Closest available cell to the centre.
                dist = np.abs(available[:, 0] - rows // 2) + np.abs(available[:, 1] - cols // 2)
                row, col = available[int(np.argmin(dist))]
                pos = wm.map.tf_grid2pos((int(row), int(col)))
                return Pose(Position(pos.x, pos.y, 0.0), orientation=Orientation.from_yaw(0.0))
        except Exception as e:
            self._logger.warning(f"TM_Characterization centre placement failed ({e!r}), using random")
        return await random_placement(self._ctx)

    def _make_odom_cb(self, robot_name: str) -> typing.Callable[[Odometry], None]:
        def _cb(msg: Odometry) -> None:
            self._last_odom[robot_name] = self._sim_now()
        return _cb

    def _sim_now(self) -> float:
        return self.node.get_clock().now().nanoseconds * 1e-9

    def _publish_zero(self) -> None:
        for pub in self._twist_pubs.values():
            pub.publish(Twist())

    async def _drive(self) -> None:
        """Advance the schedule on sim time and publish exact cmd_vel profiles."""
        rate = asyncio.get_running_loop().time()
        phase_idx = 0
        phase_start = self._sim_now()
        run_start = phase_start
        published = set()

        try:
            while not self._finished:
                now = self._sim_now()

                # Stall watchdog: any robot with silent odometry aborts the sweep.
                for name, last in self._last_odom.items():
                    if now - last > ODOM_STALL_TIMEOUT_S:
                        self._aborted = True
                        self._logger.error(
                            f"TM_Characterization WATCHDOG: odometry of '{name}' silent "
                            f"for >{ODOM_STALL_TIMEOUT_S}s — zeroing cmd_vel and aborting"
                        )
                        break
                if self._aborted:
                    self._publish_zero()
                    self._finished = True
                    return

                if now - run_start > MAX_SCHEDULE_DURATION_S:
                    self._logger.error(
                        f"TM_Characterization: schedule exceeded {MAX_SCHEDULE_DURATION_S:.0f}s ceiling"
                    )
                    self._publish_zero()
                    self._finished = True
                    return

                if phase_idx >= len(self._schedule):
                    self._publish_zero()
                    self._finished = True
                    self._logger.info("TM_Characterization: schedule complete")
                    return

                phase = self._schedule[phase_idx]
                elapsed = now - phase_start
                if elapsed >= phase.duration_s:
                    phase_idx += 1
                    phase_start = now
                    continue

                if phase.name not in published:
                    published.add(phase.name)
                    marker = String()
                    marker.data = phase.name
                    for pub in self._phase_pubs.values():
                        pub.publish(marker)
                    self._logger.info(
                        f"TM_Characterization phase → {phase.name} "
                        f"(vx={phase.vx_target} wz={phase.wz_target} dt={phase.duration_s}s)"
                    )

                twist = self._target_twist(phase, elapsed)
                for pub in self._twist_pubs.values():
                    pub.publish(twist)

                await asyncio.sleep(1.0 / CONTROL_RATE_HZ)
        except asyncio.CancelledError:
            self._publish_zero()
            raise
        except Exception:
            self._logger.exception("TM_Characterization driver crashed")
            self._publish_zero()
            self._finished = True

    def _target_twist(self, phase: Phase, elapsed_s: float) -> Twist:
        twist = Twist()
        if phase.kind.value == "angular":
            twist.angular.z = phase.wz_target
        elif phase.ramp_s > 0.0:
            frac = min(max(elapsed_s / phase.ramp_s, 0.0), 1.0)
            if phase.kind.value == "ramp_down":
                twist.linear.x = phase.vx_target * (1.0 - frac)
            else:
                twist.linear.x = phase.vx_target * frac
        else:
            twist.linear.x = phase.vx_target
        return twist

    async def set_goal(self, pose: Pose):
        """Open-loop mode ignores navigation goals."""
        del pose

    async def set_position(self, pose: Pose):
        """Open-loop mode ignores pose overrides."""
        del pose

    @property
    async def done(self) -> bool:
        return bool(self._finished)

    async def teardown(self) -> None:
        """Cancel the driver and zero cmd_vel on episode teardown."""
        self._finished = True
        if self._driver is not None:
            self._driver.cancel()
            with contextlib.suppress(asyncio.CancelledError):
                await self._driver
        self._publish_zero()
        for sub in self._odom_subs:
            with contextlib.suppress(Exception):
                self.node.destroy_subscription(sub)
        self._odom_subs = []
