"""Shim implementations of MechanismITF for simulators without native door/elevator support."""

from __future__ import annotations

import asyncio
import enum
import math
import typing
from collections.abc import Sequence

import attrs
import rclpy.impl.rcutils_logger
from task_generator.shared import Door, Elevator, Orientation, Pose, Position

if typing.TYPE_CHECKING:
    from ._interface import MechanismITF

MECHANISM_TICK_RATE = 30.0  # Hz, sim time
INSIDE_DOOR_BLOCKER_RADIUS = 0.05
DOOR_INSET = 0.05
WALL_THICKNESS = 0.05

_DOOR_AXES: dict[str, tuple[tuple[float, float], tuple[float, float]]] = {
    '+x': ((1.0, 0.0), (0.0, 1.0)),
    '-x': ((-1.0, 0.0), (0.0, 1.0)),
    '+y': ((0.0, 1.0), (1.0, 0.0)),
    '-y': ((0.0, -1.0), (1.0, 0.0)),
}


def _door_basis(elevator: Elevator) -> tuple[float, float, tuple[float, float], tuple[float, float], float]:
    outward, tangent = _DOOR_AXES[elevator.door_side]
    hx, hy = elevator.size[0] / 2.0, elevator.size[1] / 2.0
    out_extent = hx if outward[0] != 0 else hy
    tan_extent = hy if outward[0] != 0 else hx
    face_cx = elevator.position.x + outward[0] * out_extent
    face_cy = elevator.position.y + outward[1] * out_extent
    return face_cx, face_cy, outward, tangent, tan_extent


def _door_slot(elevator: Elevator) -> tuple[Position, Position]:
    face_cx, face_cy, outward, tangent, tan_extent = _door_basis(elevator)
    slot_half = tan_extent - DOOR_INSET
    cx = face_cx - outward[0] * DOOR_INSET
    cy = face_cy - outward[1] * DOOR_INSET
    z = elevator.position.z
    return (
        Position(cx - tangent[0] * slot_half, cy - tangent[1] * slot_half, z),
        Position(cx + tangent[0] * slot_half, cy + tangent[1] * slot_half, z),
    )


def _elevator_wall_geometries(elevator: Elevator) -> list[tuple[str, tuple[float, float, float], Pose]]:
    face_cx, face_cy, outward, tangent, tan_extent = _door_basis(elevator)
    ex, ey, ez = elevator.size
    pos = elevator.position
    wall_z = pos.z + ez / 2.0

    def pose(cx: float, cy: float) -> Pose:
        return Pose(position=Position(x=cx, y=cy, z=wall_z), orientation=Orientation.from_yaw(0.0))

    if outward[0] != 0:
        back_size = (WALL_THICKNESS, ey, ez)
        side_size = (ex, WALL_THICKNESS, ez)
    else:
        back_size = (ex, WALL_THICKNESS, ez)
        side_size = (WALL_THICKNESS, ey, ez)
    back_cx = 2.0 * pos.x - face_cx
    back_cy = 2.0 * pos.y - face_cy
    side_dx = tangent[0] * tan_extent
    side_dy = tangent[1] * tan_extent
    return [
        ('back', back_size, pose(back_cx, back_cy)),
        ('side_pos', side_size, pose(pos.x + side_dx, pos.y + side_dy)),
        ('side_neg', side_size, pose(pos.x - side_dx, pos.y - side_dy)),
    ]


class _DoorState(enum.StrEnum):
    CLOSED = 'closed'
    OPENING = 'opening'
    OPEN = 'open'
    CLOSING = 'closing'


class _ElevatorState(enum.StrEnum):
    PRESENT = 'present'  # cabin here, door open by default
    DEPARTING = 'departing'  # cabin here, door closing (sibling called)
    ABSENT = 'absent'  # cabin at sibling, door closed
    ARRIVING = 'arriving'  # cabin in transit toward here, door closed


@attrs.define
class _DoorRuntime:
    door: Door
    closed_pose: Pose
    open_pose: Pose
    effective_kind: typing.Literal['sliding', 'teleport']
    state: _DoorState = _DoorState.CLOSED
    progress: float = 0.0  # 0 = closed, 1 = open
    last_trigger_sim_time: float = -math.inf
    last_applied_progress: float = -1.0  # forces first move_box call


@attrs.define
class _ElevatorRuntime:
    elevator: Elevator
    door_name: str
    destination_name: str
    state: _ElevatorState = _ElevatorState.ABSENT
    arriving_eta: float = -math.inf
    just_arrived: frozenset[str] = attrs.field(factory=frozenset)
    pending_occupants: tuple[tuple[str, tuple[float, float]], ...] = ()


@attrs.define
class _ElevatorStepResult:
    teleport_job: tuple[str, str, list[tuple[str, tuple[float, float]]]] | None = None
    missing_destination: bool = False


def _effective_kind(
    logger: rclpy.impl.rcutils_logger.RcutilsLogger,
    door: Door,
) -> typing.Literal['sliding', 'teleport']:
    """Return the animation kind, falling back to teleport for hinged with a warn-once log."""
    if door.kind == 'hinged':
        logger.warning(
            f"mechanism shim: door {door.name!r} kind='hinged' not implemented. Falling back to 'teleport'.",
        )
        return 'teleport'
    if door.kind == 'teleport':
        return 'teleport'
    return 'sliding'


def _door_geometry(door: Door) -> tuple[tuple[float, float, float], Pose]:
    """Return (size, closed_pose) for a door spanning start..end."""
    sx, sy, sz = door.start.x, door.start.y, door.start.z
    ex, ey, ez = door.end.x, door.end.y, door.end.z
    length = math.hypot(ex - sx, ey - sy)
    yaw = math.atan2(ey - sy, ex - sx)
    cx = (sx + ex) / 2.0
    cy = (sy + ey) / 2.0
    cz = (sz + ez) / 2.0 + door.height / 2.0
    return (length, door.width, door.height), Pose(
        position=Position(x=cx, y=cy, z=cz),
        orientation=Orientation.from_yaw(yaw),
    )


def _door_open_pose(door: Door, closed_pose: Pose, effective_kind: str) -> Pose:
    """Return the fully-open pose for a door (Z-drop for teleport, axis-slide for sliding)."""
    if effective_kind == 'teleport':
        return Pose(
            position=Position(
                x=closed_pose.position.x,
                y=closed_pose.position.y,
                z=closed_pose.position.z - 100.0,
            ),
            orientation=closed_pose.orientation,
        )
    # sliding: full-length slide along start->end axis, matching arena_isaac (axis * door.S.x)
    sx, sy = door.start.x, door.start.y
    ex, ey = door.end.x, door.end.y
    length = math.hypot(ex - sx, ey - sy)
    if length == 0:
        return closed_pose
    ux = (ex - sx) / length
    uy = (ey - sy) / length
    return Pose(
        position=Position(
            x=closed_pose.position.x + ux * length,
            y=closed_pose.position.y + uy * length,
            z=closed_pose.position.z,
        ),
        orientation=closed_pose.orientation,
    )


def _elevator_synthesized_door(elevator: Elevator) -> Door:
    """Wrap the inset door slot in a Door so the regular door animation pipeline handles it."""
    start, end = _door_slot(elevator)
    return Door(
        name=f'{elevator.name}/door',
        start=start,
        end=end,
        kind='sliding',
        width=0.05,
        height=elevator.size[2],
        activation_distance=(elevator.activation_distance, elevator.activation_distance),
        transition_time=elevator.transition_time,
        hold_time=elevator.hold_time,
    )


def _inside_cabin(elevator: Elevator, pos_xy: tuple[float, float]) -> bool:
    """True if pos_xy falls within the cabin footprint (inclusive of boundary)."""
    ex, ey, _ = elevator.size
    return abs(pos_xy[0] - elevator.position.x) <= ex / 2.0 and abs(pos_xy[1] - elevator.position.y) <= ey / 2.0


def _is_triggered(door: Door, positions: list[tuple[float, float]]) -> bool:
    """True if any position is within activation_distance of either door endpoint."""
    d0, d1 = door.activation_distance
    sx, sy = door.start.x, door.start.y
    ex, ey = door.end.x, door.end.y
    for x, y in positions:
        if d0 > 0 and (x - sx) ** 2 + (y - sy) ** 2 <= d0 * d0:
            return True
        if d1 > 0 and (x - ex) ** 2 + (y - ey) ** 2 <= d1 * d1:
            return True
    return False


def _near_door_segment(door: Door, positions: list[tuple[float, float]], radius: float) -> bool:
    """True if any position is within `radius` of the door line segment (start->end)."""
    sx, sy = door.start.x, door.start.y
    ex, ey = door.end.x, door.end.y
    dx, dy = ex - sx, ey - sy
    seg_len_sq = dx * dx + dy * dy
    r2 = radius * radius
    for x, y in positions:
        if seg_len_sq <= 0.0:
            if (x - sx) ** 2 + (y - sy) ** 2 <= r2:
                return True
            continue
        t = ((x - sx) * dx + (y - sy) * dy) / seg_len_sq
        if t < 0.0:
            t = 0.0
        elif t > 1.0:
            t = 1.0
        px = sx + t * dx
        py = sy + t * dy
        if (x - px) ** 2 + (y - py) ** 2 <= r2:
            return True
    return False


def _advance_state(runtime: _DoorRuntime, dt: float, now: float) -> None:
    """Advance door state machine one tick: linear T-delta for sliding, instant snap for teleport."""
    door = runtime.door
    fresh = (now - runtime.last_trigger_sim_time) <= door.hold_time
    if runtime.effective_kind == 'teleport':
        runtime.progress = 1.0 if fresh else 0.0
        runtime.state = _DoorState.OPEN if fresh else _DoorState.CLOSED
        return
    # sliding: per-tick linear T delta over transition_time, mirrors arena_isaac XFormAnimation.step
    target = 1.0 if fresh else 0.0
    step = dt / max(door.transition_time, 1e-9)
    if target > runtime.progress:
        runtime.state = _DoorState.OPENING
        runtime.progress = min(1.0, runtime.progress + step)
        if runtime.progress >= 1.0:
            runtime.state = _DoorState.OPEN
    elif target < runtime.progress:
        runtime.state = _DoorState.CLOSING
        runtime.progress = max(0.0, runtime.progress - step)
        if runtime.progress <= 0.0:
            runtime.state = _DoorState.CLOSED
    else:
        runtime.state = _DoorState.OPEN if target == 1.0 else _DoorState.CLOSED


def _interp_pose(runtime: _DoorRuntime) -> Pose:
    """Linear interpolation between closed and open pose at runtime.progress."""
    a = runtime.closed_pose.position
    b = runtime.open_pose.position
    t = runtime.progress
    return Pose(
        position=Position(
            x=a.x + (b.x - a.x) * t,
            y=a.y + (b.y - a.y) * t,
            z=a.z + (b.z - a.z) * t,
        ),
        orientation=runtime.closed_pose.orientation,
    )


def _step_elevator(
    runtime: _ElevatorRuntime,
    door_runtime: _DoorRuntime,
    dest_runtime: _ElevatorRuntime | None,
    occupants: Sequence[tuple[str, tuple[float, float]]],
    near_door: bool,
    outside_trigger: bool,
    now: float,
) -> _ElevatorStepResult:
    result = _ElevatorStepResult()
    state = runtime.state
    closing_abort = near_door and door_runtime.state != _DoorState.CLOSED
    if state == _ElevatorState.PRESENT:
        current = frozenset(name for name, _ in occupants)
        runtime.just_arrived &= current
        new_occupants = current - runtime.just_arrived
        if outside_trigger or not new_occupants or closing_abort:
            door_runtime.last_trigger_sim_time = now
        if door_runtime.state == _DoorState.CLOSED and new_occupants:
            runtime.state = _ElevatorState.DEPARTING
    elif state == _ElevatorState.DEPARTING:
        if outside_trigger or closing_abort:
            runtime.state = _ElevatorState.PRESENT
            door_runtime.last_trigger_sim_time = now
        elif door_runtime.state == _DoorState.CLOSED:
            if dest_runtime is None:
                result.missing_destination = True
                runtime.state = _ElevatorState.PRESENT
                door_runtime.last_trigger_sim_time = now
            else:
                runtime.state = _ElevatorState.ABSENT
                runtime.just_arrived = frozenset()
                dest_runtime.state = _ElevatorState.ARRIVING
                dest_runtime.arriving_eta = now + runtime.elevator.travel_time
                dest_runtime.pending_occupants = tuple(occupants)
    elif state == _ElevatorState.ABSENT:
        if outside_trigger and dest_runtime is not None and dest_runtime.state == _ElevatorState.PRESENT:
            dest_runtime.state = _ElevatorState.DEPARTING
    elif state == _ElevatorState.ARRIVING:
        if now >= runtime.arriving_eta:
            runtime.state = _ElevatorState.PRESENT
            runtime.arriving_eta = -math.inf
            door_runtime.last_trigger_sim_time = now
            if runtime.pending_occupants:
                src_name = runtime.destination_name
                result.teleport_job = (src_name, runtime.elevator.name, list(runtime.pending_occupants))
                runtime.just_arrived = frozenset(name for name, _ in runtime.pending_occupants)
                runtime.pending_occupants = ()
    return result


def _compute_teleport_destinations(
    elevator_runtime: dict[str, _ElevatorRuntime],
    source_name: str,
    dest_name: str,
    named_occupants: Sequence[tuple[str, tuple[float, float]]],
) -> dict[str, tuple[float, float]]:
    """Translate occupant positions from the source cabin frame into the destination cabin frame."""
    source_rt = elevator_runtime.get(source_name)
    dest_rt = elevator_runtime.get(dest_name)
    if source_rt is None or dest_rt is None:
        return {}
    src_pos = source_rt.elevator.position
    dst_pos = dest_rt.elevator.position
    out: dict[str, tuple[float, float]] = {}
    for agent_name, (x, y) in named_occupants:
        out[agent_name] = (dst_pos.x + (x - src_pos.x), dst_pos.y + (y - src_pos.y))
    return out


def _ensure_loop(mech: MechanismITF) -> None:
    """Start the mechanism tick loop if not already running."""
    if mech._mechanism_loop_task is None or mech._mechanism_loop_task.done():
        mech._mechanism_loop_task = asyncio.create_task(_loop(mech))


async def _loop(mech: MechanismITF) -> None:
    """Sim-time rate loop driving door animation and elevator state machine."""
    logger = mech.node.get_logger()
    with mech.node.sim_time_rate(MECHANISM_TICK_RATE) as (done, rate):
        while not done.is_set():
            try:
                dt = await rate.get()
            except asyncio.CancelledError:
                raise
            try:
                await _tick(mech, dt)
            except asyncio.CancelledError:
                raise
            except Exception as e:
                logger.warning(f"mechanism shim tick failed: {e!r}")


async def _tick(mech: MechanismITF, dt: float) -> None:
    """Single tick: update triggers, advance state machines, dispatch move_box and teleports."""
    robot_positions = list(mech.robot_positions_xy())
    ped_positions: list[tuple[str, tuple[float, float]]] = list(mech._human_simulator.pedestrian_positions_xy()) if mech._human_simulator is not None else []
    named_positions = robot_positions + ped_positions
    ped_names: set[str] = {name for name, _ in ped_positions}
    now = mech.node.sim_time.to_seconds()

    elev_occupant_idx: dict[str, set[int]] = {}
    all_occupant_idx: set[int] = set()
    for elev_name, runtime in mech._elevator_runtime.items():
        occ = {i for i, (_n, xy) in enumerate(named_positions) if _inside_cabin(runtime.elevator, xy)}
        elev_occupant_idx[elev_name] = occ
        all_occupant_idx.update(occ)
    outside_xys = [xy for i, (_n, xy) in enumerate(named_positions) if i not in all_occupant_idx]
    all_xys = [xy for _n, xy in named_positions]

    elevator_door_names = set(mech._elevator_doors.values())
    teleport_jobs: list[tuple[str, str, list[tuple[str, tuple[float, float]]]]] = []
    logger = mech.node.get_logger()
    for elev_name, runtime in mech._elevator_runtime.items():
        door_runtime = mech._door_runtime.get(runtime.door_name)
        if door_runtime is None:
            continue
        occupants = [named_positions[i] for i in elev_occupant_idx[elev_name]]
        outside_trigger = _is_triggered(door_runtime.door, outside_xys)
        near_door = outside_trigger or _near_door_segment(
            door_runtime.door,
            [xy for _, xy in occupants],
            INSIDE_DOOR_BLOCKER_RADIUS,
        )
        dest_runtime = mech._elevator_runtime.get(runtime.destination_name)
        result = _step_elevator(runtime, door_runtime, dest_runtime, occupants, near_door, outside_trigger, now)
        if result.missing_destination:
            logger.warning(f"Elevator {elev_name!r}: destination {runtime.destination_name!r} unknown; staying PRESENT.")
        if result.teleport_job is not None:
            teleport_jobs.append(result.teleport_job)

    # Regular doors take proximity from the full agent list. Elevator doors are gated above.
    for name, runtime in mech._door_runtime.items():
        if name in elevator_door_names:
            continue
        if _is_triggered(runtime.door, all_xys):
            runtime.last_trigger_sim_time = now

    pending: list[typing.Awaitable] = []
    for name, runtime in mech._door_runtime.items():
        _advance_state(runtime, dt, now)
        if runtime.progress != runtime.last_applied_progress:
            runtime.last_applied_progress = runtime.progress
            pending.append(mech.move_box(name, _interp_pose(runtime)))
    if pending:
        await asyncio.gather(*pending, return_exceptions=True)

    # Run teleport jobs after door updates are dispatched.
    for source_name, dest_name, named_occupants in teleport_jobs:
        destinations = _compute_teleport_destinations(mech._elevator_runtime, source_name, dest_name, named_occupants)
        if not destinations:
            continue
        robot_destinations = {k: v for k, v in destinations.items() if k not in ped_names}
        ped_destinations = {k: v for k, v in destinations.items() if k in ped_names}
        for sim_path, (x, y) in robot_destinations.items():
            try:
                await mech.set_robot_pose(sim_path, Pose(position=Position(x, y, 0.0), orientation=Orientation(1, 0, 0, 0)))
            except Exception as e:
                logger.warning(f"Elevator robot teleport {source_name!r} -> {dest_name!r} failed for {sim_path!r}: {e!r}")
        if ped_destinations:
            if mech._human_simulator is not None:
                try:
                    await mech._human_simulator.pedestrian_teleport(ped_destinations)
                except Exception as e:
                    logger.warning(f"Elevator ped teleport {source_name!r} -> {dest_name!r} failed: {e!r}")
            else:
                logger.info(f"Elevator teleport (no-op, no human sim): {len(ped_destinations)} peds {source_name!r} -> {dest_name!r}")


async def shim_spawn_doors(mech: MechanismITF, doors: Sequence[Door]) -> bool:
    """Spawn box geometry for each door and register door runtimes."""
    ok = True
    logger = mech.node.get_logger()
    for door in doors:
        kind = _effective_kind(logger, door)
        size, closed_pose = _door_geometry(door)
        open_pose = _door_open_pose(door, closed_pose, kind)
        if await mech.spawn_box(door.name, size, closed_pose):
            mech._door_primitives[door.name] = [door.name]
            mech._door_runtime[door.name] = _DoorRuntime(
                door=door,
                closed_pose=closed_pose,
                open_pose=open_pose,
                effective_kind=kind,
            )
        else:
            ok = False
    if mech._door_runtime:
        _ensure_loop(mech)
    return ok


async def shim_remove_doors(mech: MechanismITF, names: Sequence[str]) -> bool:
    """Delete box geometry and drop door runtimes for the given names."""
    ok = True
    for name in names:
        for prim_name in mech._door_primitives.pop(name, []):
            if not await mech.delete_box(prim_name):
                ok = False
        mech._door_runtime.pop(name, None)
    return ok


async def shim_spawn_elevators(mech: MechanismITF, elevators: Sequence[Elevator]) -> bool:
    """Spawn wall geometry and synthesized doors for each elevator, then prime PRESENT state."""
    ok = True
    synthesized_doors: list[Door] = []
    pending_runtimes: list[_ElevatorRuntime] = []
    for elevator in elevators:
        spawned: list[str] = []
        for suffix, size, pose in _elevator_wall_geometries(elevator):
            name = f'{elevator.name}/{suffix}'
            if await mech.spawn_box(name, size, pose):
                spawned.append(name)
            else:
                ok = False
        mech._elevator_primitives[elevator.name] = spawned
        door = _elevator_synthesized_door(elevator)
        synthesized_doors.append(door)
        mech._elevator_doors[elevator.name] = door.name
        pending_runtimes.append(
            _ElevatorRuntime(
                elevator=elevator,
                door_name=door.name,
                destination_name=elevator.destination,
            )
        )
    if synthesized_doors and not await shim_spawn_doors(mech, synthesized_doors):
        ok = False
    for runtime in pending_runtimes:
        mech._elevator_runtime[runtime.elevator.name] = runtime
    now = mech.node.sim_time.to_seconds()
    for runtime in pending_runtimes:
        dest = mech._elevator_runtime.get(runtime.destination_name)
        if dest is None or dest.state == _ElevatorState.ABSENT:
            runtime.state = _ElevatorState.PRESENT
            door_runtime = mech._door_runtime.get(runtime.door_name)
            if door_runtime is not None:
                door_runtime.state = _DoorState.OPEN
                door_runtime.progress = 1.0
                door_runtime.last_trigger_sim_time = now
    return ok


async def shim_remove_elevators(mech: MechanismITF, names: Sequence[str]) -> bool:
    """Delete elevator wall geometry and synthesized doors for the given names."""
    ok = True
    door_names: list[str] = []
    for name in names:
        for prim_name in mech._elevator_primitives.pop(name, []):
            if not await mech.delete_box(prim_name):
                ok = False
        door_name = mech._elevator_doors.pop(name, None)
        if door_name is not None:
            door_names.append(door_name)
        mech._elevator_runtime.pop(name, None)
    if door_names and not await shim_remove_doors(mech, door_names):
        ok = False
    return ok
