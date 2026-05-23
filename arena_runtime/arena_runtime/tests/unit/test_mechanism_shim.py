"""Pure-logic tests for the mechanism shim state machines.

Skipped if task_generator / arena_simulation_setup aren't importable (no
sourced overlay), since the shim's data types live there.
"""
from __future__ import annotations

import math

import pytest

pytest.importorskip("task_generator.shared")
pytest.importorskip("arena_runtime.sim._mechanism_shim")

from arena_runtime.sim._mechanism_shim import (  # noqa: E402
    DOOR_INSET,
    INSIDE_DOOR_BLOCKER_RADIUS,
    WALL_THICKNESS,
    _advance_state,
    _compute_teleport_destinations,
    _door_geometry,
    _door_open_pose,
    _door_slot,
    _DoorRuntime,
    _DoorState,
    _elevator_wall_geometries,
    _ElevatorRuntime,
    _ElevatorState,
    _inside_cabin,
    _is_triggered,
    _near_door_segment,
    _step_elevator,
)
from arena_simulation_setup.utils.geometry import Orientation, Pose, Position  # noqa: E402
from task_generator.shared import Door, Elevator  # noqa: E402

# ---------------------------------------------------------------------------
# helpers
# ---------------------------------------------------------------------------


def _door(
    name: str = "d",
    start: tuple[float, float, float] = (0.0, 0.0, 0.0),
    end: tuple[float, float, float] = (1.0, 0.0, 0.0),
    activation: tuple[float, float] = (1.5, 1.5),
    transition_time: float = 1.0,
    hold_time: float = 2.0,
    kind: str = "sliding",
) -> Door:
    return Door(
        name=name,
        start=Position(*start),
        end=Position(*end),
        kind=kind,
        activation_distance=activation,
        transition_time=transition_time,
        hold_time=hold_time,
    )


def _elevator(
    name: str = "e",
    position: tuple[float, float, float] = (0.0, 0.0, 0.0),
    size: tuple[float, float, float] = (2.0, 2.0, 2.5),
    destination: str = "",
    travel_time: float = 3.0,
    hold_time: float = 2.0,
    transition_time: float = 1.0,
    activation_distance: float = 1.5,
    door_side: str = "+x",
) -> Elevator:
    return Elevator(
        name=name,
        position=Position(*position),
        size=list(size),
        door_side=door_side,
        destination=destination,
        activation_distance=activation_distance,
        transition_time=transition_time,
        hold_time=hold_time,
        travel_time=travel_time,
    )


def _door_runtime(door: Door, kind: str = "sliding") -> _DoorRuntime:
    closed = Pose(position=Position(0.0, 0.0, 1.0), orientation=Orientation.from_yaw(0.0))
    open_p = Pose(position=Position(0.0, 1.0, 1.0), orientation=Orientation.from_yaw(0.0))
    return _DoorRuntime(door=door, closed_pose=closed, open_pose=open_p, effective_kind=kind)


def _elev_runtime(elev: Elevator, door_name: str = "d", destination: str | None = None) -> _ElevatorRuntime:
    return _ElevatorRuntime(elevator=elev, door_name=door_name, destination_name=destination or elev.destination)


# ---------------------------------------------------------------------------
# _inside_cabin
# ---------------------------------------------------------------------------


def test_inside_cabin_center():
    e = _elevator(position=(10.0, 5.0, 0.0), size=(2.0, 2.0, 2.5))
    assert _inside_cabin(e, (10.0, 5.0))


def test_inside_cabin_boundary():
    e = _elevator(position=(10.0, 5.0, 0.0), size=(2.0, 2.0, 2.5))
    assert _inside_cabin(e, (11.0, 6.0))
    assert _inside_cabin(e, (9.0, 4.0))


def test_inside_cabin_just_outside():
    e = _elevator(position=(10.0, 5.0, 0.0), size=(2.0, 2.0, 2.5))
    assert not _inside_cabin(e, (11.01, 5.0))
    assert not _inside_cabin(e, (10.0, 6.01))


def test_inside_cabin_far():
    e = _elevator(position=(10.0, 5.0, 0.0))
    assert not _inside_cabin(e, (100.0, 0.0))


# ---------------------------------------------------------------------------
# _is_triggered
# ---------------------------------------------------------------------------


def test_is_triggered_empty_positions():
    d = _door(start=(0, 0, 0), end=(1, 0, 0))
    assert not _is_triggered(d, [])


def test_is_triggered_at_start_within_radius():
    d = _door(start=(0, 0, 0), end=(10, 0, 0), activation=(1.5, 1.5))
    assert _is_triggered(d, [(0.0, 1.0)])  # 1.0 < 1.5


def test_is_triggered_at_end_within_radius():
    d = _door(start=(0, 0, 0), end=(10, 0, 0), activation=(1.5, 1.5))
    assert _is_triggered(d, [(10.0, 1.0)])


def test_is_triggered_outside_radius():
    d = _door(start=(0, 0, 0), end=(10, 0, 0), activation=(1.5, 1.5))
    assert not _is_triggered(d, [(0.0, 2.0)])  # 2.0 > 1.5


def test_is_triggered_start_disabled_by_zero():
    d = _door(start=(0, 0, 0), end=(10, 0, 0), activation=(0.0, 1.5))
    assert not _is_triggered(d, [(0.0, 0.5)])  # start disabled
    assert _is_triggered(d, [(10.0, 0.5)])    # end still active


def test_is_triggered_end_disabled_by_zero():
    d = _door(start=(0, 0, 0), end=(10, 0, 0), activation=(1.5, 0.0))
    assert _is_triggered(d, [(0.0, 0.5)])
    assert not _is_triggered(d, [(10.0, 0.5)])


# ---------------------------------------------------------------------------
# _advance_state (door state machine)
# ---------------------------------------------------------------------------


def test_advance_closed_to_opening_on_fresh_trigger():
    d = _door(transition_time=1.0, hold_time=2.0)
    r = _door_runtime(d, kind="sliding")
    r.last_trigger_sim_time = 10.0  # fresh
    _advance_state(r, dt=0.1, now=10.0)
    assert r.state == _DoorState.OPENING
    assert pytest.approx(r.progress) == 0.1


def test_advance_opening_reaches_open():
    d = _door(transition_time=1.0, hold_time=2.0)
    r = _door_runtime(d, kind="sliding")
    r.state = _DoorState.OPENING
    r.progress = 0.95
    r.last_trigger_sim_time = 10.0
    _advance_state(r, dt=0.1, now=10.0)
    assert r.state == _DoorState.OPEN
    assert r.progress == 1.0


def test_advance_open_to_closing_when_stale():
    d = _door(transition_time=1.0, hold_time=2.0)
    r = _door_runtime(d, kind="sliding")
    r.state = _DoorState.OPEN
    r.progress = 1.0
    r.last_trigger_sim_time = 5.0  # 5.0s old, hold_time=2 -> stale
    _advance_state(r, dt=0.1, now=10.0)
    assert r.state == _DoorState.CLOSING
    assert pytest.approx(r.progress) == 0.9


def test_advance_closing_reverses_on_fresh_trigger():
    d = _door(transition_time=1.0, hold_time=2.0)
    r = _door_runtime(d, kind="sliding")
    r.state = _DoorState.CLOSING
    r.progress = 0.4
    r.last_trigger_sim_time = 10.0  # fresh now
    _advance_state(r, dt=0.1, now=10.0)
    assert r.state == _DoorState.OPENING
    assert pytest.approx(r.progress) == 0.5


def test_advance_teleport_snaps_open_on_fresh():
    d = _door(kind="teleport")
    r = _door_runtime(d, kind="teleport")
    r.last_trigger_sim_time = 10.0
    _advance_state(r, dt=0.1, now=10.0)
    assert r.state == _DoorState.OPEN
    assert r.progress == 1.0


def test_advance_teleport_snaps_closed_on_stale():
    d = _door(kind="teleport", hold_time=2.0)
    r = _door_runtime(d, kind="teleport")
    r.state = _DoorState.OPEN
    r.progress = 1.0
    r.last_trigger_sim_time = 0.0
    _advance_state(r, dt=0.1, now=10.0)
    assert r.state == _DoorState.CLOSED
    assert r.progress == 0.0


# ---------------------------------------------------------------------------
# _step_elevator (PRESENT / DEPARTING / ABSENT / ARRIVING)
# ---------------------------------------------------------------------------


def test_present_idle_empty_refreshes_door():
    a = _elev_runtime(_elevator(name="a", destination="b"), destination="b")
    a.state = _ElevatorState.PRESENT
    dr = _door_runtime(_door(name="a/door"), kind="sliding")
    dr.last_trigger_sim_time = -100.0
    _step_elevator(a, dr, None, occupants=[], near_door=False, outside_trigger=False, now=5.0)
    assert a.state == _ElevatorState.PRESENT
    assert dr.last_trigger_sim_time == 5.0


def test_present_new_occupant_no_blocker_stops_refresh():
    a = _elev_runtime(_elevator(name="a", destination="b"), destination="b")
    a.state = _ElevatorState.PRESENT
    dr = _door_runtime(_door(name="a/door"), kind="sliding")
    dr.last_trigger_sim_time = 5.0
    _step_elevator(a, dr, None, occupants=[("r", (0.0, 0.0))], near_door=False, outside_trigger=False, now=5.0)
    assert dr.last_trigger_sim_time == 5.0
    assert a.state == _ElevatorState.PRESENT


def test_present_new_occupant_with_blocker_holds_open():
    a = _elev_runtime(_elevator(name="a", destination="b"), destination="b")
    a.state = _ElevatorState.PRESENT
    dr = _door_runtime(_door(name="a/door"), kind="sliding")
    _step_elevator(a, dr, None, occupants=[("r", (0.0, 0.0))], near_door=True, outside_trigger=True, now=5.0)
    assert dr.last_trigger_sim_time == 5.0
    assert a.state == _ElevatorState.PRESENT


def test_present_new_occupant_closed_door_enters_departing():
    a = _elev_runtime(_elevator(name="a", destination="b"), destination="b")
    a.state = _ElevatorState.PRESENT
    dr = _door_runtime(_door(name="a/door"), kind="sliding")
    dr.state = _DoorState.CLOSED
    _step_elevator(a, dr, None, occupants=[("r", (0.0, 0.0))], near_door=False, outside_trigger=False, now=5.0)
    assert a.state == _ElevatorState.DEPARTING


def test_present_just_arrived_occupant_holds_open():
    """Occupant teleported in (in just_arrived) does not retrigger depart, even after long idle."""
    a = _elev_runtime(_elevator(name="a", destination="b"), destination="b")
    a.state = _ElevatorState.PRESENT
    a.just_arrived = frozenset({"r"})
    dr = _door_runtime(_door(name="a/door"), kind="sliding")
    dr.state = _DoorState.CLOSED
    _step_elevator(a, dr, None, occupants=[("r", (0.0, 0.0))], near_door=False, outside_trigger=False, now=999.0)
    assert a.state == _ElevatorState.PRESENT
    assert dr.last_trigger_sim_time == 999.0


def test_present_exit_drops_from_just_arrived():
    """Occupant leaving the cabin is removed from just_arrived; reentry counts as new."""
    a = _elev_runtime(_elevator(name="a", destination="b"), destination="b")
    a.state = _ElevatorState.PRESENT
    a.just_arrived = frozenset({"r"})
    dr = _door_runtime(_door(name="a/door"), kind="sliding")
    _step_elevator(a, dr, None, occupants=[], near_door=False, outside_trigger=False, now=5.0)
    assert a.just_arrived == frozenset()


def test_absent_outside_trigger_calls_present_sibling():
    a = _elev_runtime(_elevator(name="a", destination="b"), destination="b")
    b = _elev_runtime(_elevator(name="b", destination="a"), destination="a")
    a.state = _ElevatorState.ABSENT
    b.state = _ElevatorState.PRESENT
    door_a = _door_runtime(_door(name="a/door"), kind="sliding")
    door_b = _door_runtime(_door(name="b/door"), kind="sliding")
    _step_elevator(a, door_a, b, occupants=[], near_door=True, outside_trigger=True, now=5.0)
    assert b.state == _ElevatorState.DEPARTING


def test_absent_no_outside_trigger_no_action():
    a = _elev_runtime(_elevator(name="a", destination="b"), destination="b")
    b = _elev_runtime(_elevator(name="b", destination="a"), destination="a")
    a.state = _ElevatorState.ABSENT
    b.state = _ElevatorState.PRESENT
    door_a = _door_runtime(_door(name="a/door"), kind="sliding")
    door_b = _door_runtime(_door(name="b/door"), kind="sliding")
    _step_elevator(a, door_a, b, occupants=[], near_door=False, outside_trigger=False, now=5.0)
    assert b.state == _ElevatorState.PRESENT


def test_absent_call_ignored_when_sibling_already_departing():
    a = _elev_runtime(_elevator(name="a", destination="b"), destination="b")
    b = _elev_runtime(_elevator(name="b", destination="a"), destination="a")
    a.state = _ElevatorState.ABSENT
    b.state = _ElevatorState.DEPARTING
    door_a = _door_runtime(_door(name="a/door"), kind="sliding")
    door_b = _door_runtime(_door(name="b/door"), kind="sliding")
    _step_elevator(a, door_a, b, occupants=[], near_door=True, outside_trigger=True, now=5.0)
    assert b.state == _ElevatorState.DEPARTING


def test_absent_call_ignored_while_sibling_arriving():
    a = _elev_runtime(_elevator(name="a", destination="b"), destination="b")
    b = _elev_runtime(_elevator(name="b", destination="a"), destination="a")
    a.state = _ElevatorState.ABSENT
    b.state = _ElevatorState.ARRIVING
    b.arriving_eta = 100.0
    door_a = _door_runtime(_door(name="a/door"), kind="sliding")
    door_b = _door_runtime(_door(name="b/door"), kind="sliding")
    _step_elevator(a, door_a, b, occupants=[], near_door=True, outside_trigger=True, now=5.0)
    assert b.state == _ElevatorState.ARRIVING


def test_departing_outside_trigger_reverts_to_present():
    """Doorway blocker (outside_trigger on the departing side) cancels close, reopens door."""
    a = _elev_runtime(_elevator(name="a", destination="b"), destination="b")
    a.state = _ElevatorState.DEPARTING
    dr = _door_runtime(_door(name="a/door"), kind="sliding")
    dr.last_trigger_sim_time = -100.0
    _step_elevator(a, dr, None, occupants=[], near_door=True, outside_trigger=True, now=5.0)
    assert a.state == _ElevatorState.PRESENT
    assert dr.last_trigger_sim_time == 5.0


def test_departing_occupants_do_not_block():
    """Cabin occupants are passengers; only doorway (outside_trigger) blocks close."""
    a = _elev_runtime(_elevator(name="a", destination="b"), destination="b")
    a.state = _ElevatorState.DEPARTING
    dr = _door_runtime(_door(name="a/door"), kind="sliding")
    dr.state = _DoorState.CLOSING
    _step_elevator(a, dr, None, occupants=[("r", (0.0, 0.0))], near_door=False, outside_trigger=False, now=5.0)
    assert a.state == _ElevatorState.DEPARTING


def test_departing_handoff_when_door_closed():
    elev_a = _elevator(name="a", destination="b", travel_time=3.0)
    elev_b = _elevator(name="b", destination="a")
    a = _elev_runtime(elev_a, door_name="a/door", destination="b")
    b = _elev_runtime(elev_b, door_name="b/door", destination="a")
    a.state = _ElevatorState.DEPARTING
    b.state = _ElevatorState.ABSENT
    door_a = _door_runtime(_door(name="a/door"), kind="sliding")
    door_a.state = _DoorState.CLOSED
    door_b = _door_runtime(_door(name="b/door"), kind="sliding")
    result = _step_elevator(
        a, door_a, dest_runtime=b,
        occupants=[("r1", (0.5, 0.5))], near_door=False, outside_trigger=False, now=2.0,
    )
    assert a.state == _ElevatorState.ABSENT
    assert b.state == _ElevatorState.ARRIVING
    assert b.arriving_eta == pytest.approx(5.0)
    assert result.teleport_job is None  # deferred until arrival
    assert b.pending_occupants == (("r1", (0.5, 0.5)),)


def test_departing_missing_destination_reverts_to_present():
    elev = _elevator(name="a", destination="ghost")
    a = _elev_runtime(elev, destination="ghost")
    a.state = _ElevatorState.DEPARTING
    dr = _door_runtime(_door(name="a/door"), kind="sliding")
    dr.state = _DoorState.CLOSED
    result = _step_elevator(a, dr, None, occupants=[], near_door=False, outside_trigger=False, now=5.0)
    assert result.missing_destination
    assert a.state == _ElevatorState.PRESENT
    assert dr.last_trigger_sim_time == 5.0


def test_arriving_keeps_door_closed_before_eta():
    a = _elev_runtime(_elevator(name="a", destination="b"), destination="b")
    a.state = _ElevatorState.ARRIVING
    a.arriving_eta = 10.0
    dr = _door_runtime(_door(name="a/door"), kind="sliding")
    dr.last_trigger_sim_time = -100.0
    _step_elevator(a, dr, None, occupants=[], near_door=False, outside_trigger=False, now=5.0)
    assert a.state == _ElevatorState.ARRIVING
    assert dr.last_trigger_sim_time == -100.0


def test_arriving_transitions_to_present_at_eta():
    a = _elev_runtime(_elevator(name="a", destination="b"), destination="b")
    a.state = _ElevatorState.ARRIVING
    a.arriving_eta = 10.0
    dr = _door_runtime(_door(name="a/door"), kind="sliding")
    _step_elevator(a, dr, None, occupants=[], near_door=False, outside_trigger=False, now=10.0)
    assert a.state == _ElevatorState.PRESENT
    assert a.arriving_eta == -math.inf
    assert dr.last_trigger_sim_time == 10.0


def test_arriving_at_eta_with_pending_fires_teleport():
    a = _elev_runtime(_elevator(name="a", destination="b"), destination="b")
    a.state = _ElevatorState.ARRIVING
    a.arriving_eta = 10.0
    a.pending_occupants = (("r", (5.0, 0.5)),)
    dr = _door_runtime(_door(name="a/door"), kind="sliding")
    result = _step_elevator(a, dr, None, occupants=[], near_door=False, outside_trigger=False, now=10.0)
    assert a.state == _ElevatorState.PRESENT
    assert result.teleport_job == ("b", "a", [("r", (5.0, 0.5))])
    assert a.just_arrived == frozenset({"r"})
    assert a.pending_occupants == ()


# ---------------------------------------------------------------------------
# _door_open_pose
# ---------------------------------------------------------------------------


def test_door_open_pose_sliding():
    d = _door(start=(0, 0, 0), end=(2, 0, 0))  # length 2 along +x
    _size, closed = _door_geometry(d)
    open_p = _door_open_pose(d, closed, "sliding")
    assert pytest.approx(open_p.position.x) == closed.position.x + 2.0
    assert pytest.approx(open_p.position.y) == closed.position.y
    assert pytest.approx(open_p.position.z) == closed.position.z


def test_door_open_pose_teleport_drops_z():
    d = _door(start=(0, 0, 0), end=(2, 0, 0), kind="teleport")
    _size, closed = _door_geometry(d)
    open_p = _door_open_pose(d, closed, "teleport")
    assert open_p.position.x == closed.position.x
    assert open_p.position.y == closed.position.y
    assert open_p.position.z == closed.position.z - 100.0


# ---------------------------------------------------------------------------
# end-to-end cycle through state machine (drives the bug-suspect path)
# ---------------------------------------------------------------------------


def test_full_cycle_call_from_absent_sibling():
    """Sibling at ABSENT calls; PRESENT side closes, hands off, sibling arrives + opens."""
    elev_a = _elevator(name="a", position=(0.0, 0.0, 0.0), destination="b",
                       travel_time=3.0, hold_time=2.0, transition_time=1.0)
    elev_b = _elevator(name="b", position=(10.0, 0.0, 0.0), destination="a",
                       travel_time=3.0, hold_time=2.0, transition_time=1.0)
    a = _elev_runtime(elev_a, door_name="a/door", destination="b")
    b = _elev_runtime(elev_b, door_name="b/door", destination="a")
    a.state = _ElevatorState.PRESENT
    b.state = _ElevatorState.ABSENT
    door_a = _door_runtime(_door(name="a/door"), kind="sliding")
    door_a.state = _DoorState.OPEN
    door_a.progress = 1.0
    door_b = _door_runtime(_door(name="b/door"), kind="sliding")

    # 1. someone at B's floor outside-triggers; A's PRESENT becomes DEPARTING
    _step_elevator(b, door_b, a, occupants=[], near_door=True, outside_trigger=True, now=1.0)
    assert a.state == _ElevatorState.DEPARTING

    # 2. A's door animates closed (mid-close, not yet finished)
    door_a.state = _DoorState.CLOSING
    door_a.progress = 0.5
    _step_elevator(a, door_a, b, occupants=[], near_door=False, outside_trigger=False, now=1.5)
    assert a.state == _ElevatorState.DEPARTING

    # 3. A's door fully closed -> handoff; ARRIVING eta on B, teleport deferred.
    door_a.state = _DoorState.CLOSED
    door_a.progress = 0.0
    result = _step_elevator(
        a, door_a, b,
        occupants=[("r", (0.0, 0.0))], near_door=False, outside_trigger=False, now=2.0,
    )
    assert a.state == _ElevatorState.ABSENT
    assert b.state == _ElevatorState.ARRIVING
    assert b.arriving_eta == pytest.approx(5.0)
    assert result.teleport_job is None
    assert b.pending_occupants == (("r", (0.0, 0.0)),)

    # 4. B is ARRIVING, before eta -> door stays closed, no teleport yet
    door_b.last_trigger_sim_time = -100.0
    result = _step_elevator(b, door_b, a, occupants=[], near_door=False, outside_trigger=False, now=4.0)
    assert b.state == _ElevatorState.ARRIVING
    assert door_b.last_trigger_sim_time == -100.0
    assert result.teleport_job is None

    # 5. eta reached -> B becomes PRESENT, teleport fires now.
    result = _step_elevator(b, door_b, a, occupants=[], near_door=False, outside_trigger=False, now=5.0)
    assert b.state == _ElevatorState.PRESENT
    assert b.arriving_eta == -math.inf
    assert door_b.last_trigger_sim_time == 5.0
    assert result.teleport_job == ("a", "b", [("r", (0.0, 0.0))])
    assert b.just_arrived == frozenset({"r"})
    assert b.pending_occupants == ()


def test_departing_aborts_mid_close_when_blocker_appears():
    """Mid-close, a doorway blocker shows up; cancel back to PRESENT, refresh trigger."""
    elev_a = _elevator(name="a", destination="b")
    elev_b = _elevator(name="b", destination="a")
    a = _elev_runtime(elev_a, door_name="a/door", destination="b")
    b = _elev_runtime(elev_b, door_name="b/door", destination="a")
    a.state = _ElevatorState.DEPARTING
    b.state = _ElevatorState.ABSENT
    door_a = _door_runtime(_door(name="a/door"), kind="sliding")
    door_a.state = _DoorState.CLOSING
    door_a.progress = 0.4
    door_b = _door_runtime(_door(name="b/door"), kind="sliding")
    _step_elevator(a, door_a, b, occupants=[], near_door=True, outside_trigger=True, now=10.0)
    assert a.state == _ElevatorState.PRESENT
    assert door_a.last_trigger_sim_time == 10.0


def test_departing_aborts_mid_close_when_inside_passenger_blocks_doorway():
    """near_door from an inside occupant (not outside_trigger) also reverts a CLOSING door."""
    a = _elev_runtime(_elevator(name="a", destination="b"), destination="b")
    a.state = _ElevatorState.DEPARTING
    dr = _door_runtime(_door(name="a/door"), kind="sliding")
    dr.state = _DoorState.CLOSING
    dr.progress = 0.3
    _step_elevator(a, dr, None, occupants=[("r", (0.0, 0.0))], near_door=True, outside_trigger=False, now=7.0)
    assert a.state == _ElevatorState.PRESENT
    assert dr.last_trigger_sim_time == 7.0


def test_departing_does_not_abort_once_door_fully_closed():
    """Lock the door at CLOSED: near_door no longer reverts, handoff commits."""
    elev_a = _elevator(name="a", destination="b", travel_time=3.0)
    elev_b = _elevator(name="b", destination="a")
    a = _elev_runtime(elev_a, door_name="a/door", destination="b")
    b = _elev_runtime(elev_b, door_name="b/door", destination="a")
    a.state = _ElevatorState.DEPARTING
    b.state = _ElevatorState.ABSENT
    dr_a = _door_runtime(_door(name="a/door"), kind="sliding")
    dr_a.state = _DoorState.CLOSED
    dr_a.progress = 0.0
    _step_elevator(a, dr_a, b, occupants=[("r", (0.0, 0.0))], near_door=True, outside_trigger=False, now=4.0)
    assert a.state == _ElevatorState.ABSENT
    assert b.state == _ElevatorState.ARRIVING


def test_present_inside_occupant_near_door_keeps_open():
    """Cabin occupant lingering by the doorway holds the door open."""
    a = _elev_runtime(_elevator(name="a", destination="b"), destination="b")
    a.state = _ElevatorState.PRESENT
    dr = _door_runtime(_door(name="a/door"), kind="sliding")
    dr.state = _DoorState.CLOSING
    dr.progress = 0.6
    dr.last_trigger_sim_time = -100.0
    _step_elevator(a, dr, None, occupants=[("r", (0.0, 0.0))], near_door=True, outside_trigger=False, now=8.0)
    assert a.state == _ElevatorState.PRESENT
    assert dr.last_trigger_sim_time == 8.0


# ---------------------------------------------------------------------------
# _compute_teleport_destinations (source-relative -> dest-relative mapping)
# ---------------------------------------------------------------------------


def _runtime_dict_with_pair(a_pos: tuple[float, float, float], b_pos: tuple[float, float, float]) -> dict[str, _ElevatorRuntime]:
    return {
        "a": _elev_runtime(_elevator(name="a", position=a_pos, destination="b"), door_name="a/door"),
        "b": _elev_runtime(_elevator(name="b", position=b_pos, destination="a"), door_name="b/door"),
    }


def test_compute_teleport_preserves_relative_offset():
    rt = _runtime_dict_with_pair((0.0, 0.0, 0.0), (10.0, 5.0, 0.0))
    # Agent at (0.3, -0.4) in source cabin (relative offset +0.3, -0.4 from cabin center)
    out = _compute_teleport_destinations(rt, "a", "b", [("r1", (0.3, -0.4))])
    assert "r1" in out
    assert out["r1"] == pytest.approx((10.3, 4.6))


def test_compute_teleport_multiple_agents():
    rt = _runtime_dict_with_pair((0.0, 0.0, 0.0), (10.0, 0.0, 0.0))
    out = _compute_teleport_destinations(rt, "a", "b", [
        ("r1", (0.5, 0.0)),
        ("p1", (-0.5, 0.3)),
    ])
    assert out["r1"] == pytest.approx((10.5, 0.0))
    assert out["p1"] == pytest.approx((9.5, 0.3))


def test_compute_teleport_unknown_pair_returns_empty():
    rt = _runtime_dict_with_pair((0.0, 0.0, 0.0), (10.0, 0.0, 0.0))
    assert _compute_teleport_destinations(rt, "ghost", "b", [("r1", (0.0, 0.0))]) == {}
    assert _compute_teleport_destinations(rt, "a", "ghost", [("r1", (0.0, 0.0))]) == {}


# ---------------------------------------------------------------------------
# tick-driven full state machine (PRESENT/DEPARTING/ABSENT/ARRIVING)
# ---------------------------------------------------------------------------


DT = 1.0 / 30.0


def _prime_pair(
    iteration_order: tuple[str, str] = ("a", "b"),
    *,
    spawn_now: float = 0.0,
    hold_time: float = 2.0,
    transition_time: float = 1.0,
    travel_time: float = 3.0,
) -> tuple[dict[str, _ElevatorRuntime], dict[str, _DoorRuntime]]:
    """Build a two-cabin pair shaped like shim_spawn_elevators output. A starts PRESENT."""
    elev_a = _elevator(name="a", destination="b",
                       hold_time=hold_time, transition_time=transition_time, travel_time=travel_time)
    elev_b = _elevator(name="b", position=(10.0, 0.0, 0.0), destination="a",
                       hold_time=hold_time, transition_time=transition_time, travel_time=travel_time)
    a = _elev_runtime(elev_a, door_name="a/door", destination="b")
    b = _elev_runtime(elev_b, door_name="b/door", destination="a")
    door_a = _door_runtime(_door(name="a/door", hold_time=hold_time, transition_time=transition_time))
    door_b = _door_runtime(_door(name="b/door", hold_time=hold_time, transition_time=transition_time))
    a.state = _ElevatorState.PRESENT
    door_a.state = _DoorState.OPEN
    door_a.progress = 1.0
    door_a.last_applied_progress = 1.0
    door_a.last_trigger_sim_time = spawn_now
    b.state = _ElevatorState.ABSENT
    runtimes = {name: (a if name == "a" else b) for name in iteration_order}
    doors = {"a/door": door_a, "b/door": door_b}
    return runtimes, doors


def _run_ticks(
    runtimes: dict[str, _ElevatorRuntime],
    doors: dict[str, _DoorRuntime],
    *,
    start: float,
    n: int,
    outside_trigger: dict[str, bool] | None = None,
    occupants: dict[str, list[tuple[str, tuple[float, float]]]] | None = None,
) -> tuple[float, list[tuple[str, str, list[tuple[str, tuple[float, float]]]]]]:
    outside_trigger = outside_trigger or {}
    occupants = occupants or {}
    now = start
    jobs: list[tuple[str, str, list[tuple[str, tuple[float, float]]]]] = []
    for _ in range(n):
        now += DT
        for name, elev in runtimes.items():
            door = doors[elev.door_name]
            dest = runtimes.get(elev.destination_name)
            occ = occupants.get(name, [])
            outside = outside_trigger.get(name, False)
            near = outside or _near_door_segment(door.door, [xy for _, xy in occ], INSIDE_DOOR_BLOCKER_RADIUS)
            r = _step_elevator(
                elev, door, dest,
                occupants=occ,
                near_door=near,
                outside_trigger=outside,
                now=now,
            )
            if r.teleport_job is not None:
                jobs.append(r.teleport_job)
        for door in doors.values():
            _advance_state(door, DT, now)
    return now, jobs


def test_tick_idle_keeps_present_open_absent_closed():
    runtimes, doors = _prime_pair()
    _, jobs = _run_ticks(runtimes, doors, start=0.0, n=300)
    assert jobs == []
    assert runtimes["a"].state == _ElevatorState.PRESENT
    assert runtimes["b"].state == _ElevatorState.ABSENT
    assert doors["a/door"].state == _DoorState.OPEN
    assert doors["b/door"].state == _DoorState.CLOSED


@pytest.mark.parametrize("order", [("a", "b"), ("b", "a")])
def test_tick_call_from_sibling_handoff_then_arrival(order: tuple[str, str]) -> None:
    """Hold(2)+close(1)=3s to handoff (no teleport yet), then travel(3s) to arrival+teleport."""
    runtimes, doors = _prime_pair(iteration_order=order)
    now, jobs_pre = _run_ticks(runtimes, doors, start=0.0, n=100, outside_trigger={"b": True})
    assert runtimes["a"].state == _ElevatorState.ABSENT
    assert runtimes["b"].state == _ElevatorState.ARRIVING
    assert jobs_pre == []  # teleport deferred during transit
    assert doors["a/door"].state == _DoorState.CLOSED
    _, jobs_post = _run_ticks(runtimes, doors, start=now, n=120)
    assert len(jobs_post) == 1
    assert jobs_post[0][:2] == ("a", "b")
    assert runtimes["b"].state == _ElevatorState.PRESENT


def test_tick_full_round_trip():
    """A->B->A: each direction takes hold+close+travel+open = 7s. 250 ticks per leg."""
    runtimes, doors = _prime_pair()
    a, b = runtimes["a"], runtimes["b"]
    door_a, door_b = doors["a/door"], doors["b/door"]
    now, jobs1 = _run_ticks(runtimes, doors, start=0.0, n=250, outside_trigger={"b": True})
    assert len(jobs1) == 1
    assert a.state == _ElevatorState.ABSENT
    assert b.state == _ElevatorState.PRESENT
    assert door_b.state == _DoorState.OPEN
    now, jobs2 = _run_ticks(runtimes, doors, start=now, n=250, outside_trigger={"a": True})
    assert len(jobs2) == 1
    assert b.state == _ElevatorState.ABSENT
    assert a.state == _ElevatorState.PRESENT
    assert door_a.state == _DoorState.OPEN


def test_tick_blocker_at_departing_doorway_reverts_to_present():
    """Outside trigger on the DEPARTING side cancels the close. Door reopens fully."""
    runtimes, doors = _prime_pair()
    door_a = doors["a/door"]
    now, _ = _run_ticks(runtimes, doors, start=0.0, n=int(2.5 / DT), outside_trigger={"b": True})
    assert runtimes["a"].state == _ElevatorState.DEPARTING
    assert 0.0 < door_a.progress < 1.0
    _, _ = _run_ticks(runtimes, doors, start=now, n=int(1.5 / DT), outside_trigger={"a": True})
    assert runtimes["a"].state == _ElevatorState.PRESENT
    assert door_a.state == _DoorState.OPEN
    assert door_a.progress == 1.0


def test_tick_robot_self_boards_and_rides():
    """Armed PRESENT cabin with occupant and no sibling call: hold + close + travel + open ~= 7s."""
    runtimes, doors = _prime_pair()
    _, jobs = _run_ticks(
        runtimes, doors, start=0.0, n=250,
        occupants={"a": [("r1", (-0.5, 0.0))]},
    )
    assert jobs == [("a", "b", [("r1", (-0.5, 0.0))])]
    assert runtimes["a"].state == _ElevatorState.ABSENT
    assert runtimes["b"].state == _ElevatorState.PRESENT


def test_tick_robot_exits_cabin_stays_idle():
    """Robot exits at destination, empty cabin stays PRESENT (no auto-shuttle)."""
    runtimes, doors = _prime_pair()
    a, b = runtimes["a"], runtimes["b"]
    now, jobs1 = _run_ticks(
        runtimes, doors, start=0.0, n=230,
        outside_trigger={"b": True},
        occupants={"a": [("r1", (-0.5, 0.0))]},
    )
    assert len(jobs1) == 1
    assert b.state == _ElevatorState.PRESENT
    _, jobs2 = _run_ticks(runtimes, doors, start=now, n=300)
    assert jobs2 == []
    assert b.state == _ElevatorState.PRESENT
    assert doors["b/door"].state == _DoorState.OPEN


def test_tick_robot_stays_at_destination_no_shuttle_back():
    """Robot rides to B and stays inside; cabin does not shuttle back even after long idle."""
    runtimes, doors = _prime_pair()
    a, b = runtimes["a"], runtimes["b"]
    now, jobs1 = _run_ticks(
        runtimes, doors, start=0.0, n=230,
        outside_trigger={"b": True},
        occupants={"a": [("r1", (-0.5, 0.0))]},
    )
    assert len(jobs1) == 1
    assert b.state == _ElevatorState.PRESENT
    # Robot now sitting in B's cabin (centered at (10, 0)). 20s of inaction.
    _, jobs2 = _run_ticks(
        runtimes, doors, start=now, n=int(20.0 / DT),
        occupants={"b": [("r1", (10.0, 0.0))]},
    )
    assert jobs2 == []
    assert b.state == _ElevatorState.PRESENT
    assert "r1" in b.just_arrived  # still in just_arrived since never left


def test_tick_robot_exits_then_reenters_redeparts():
    """Exit clears just_arrived; re-entry counts as a new occupant and triggers depart."""
    runtimes, doors = _prime_pair()
    a, b = runtimes["a"], runtimes["b"]
    now, jobs1 = _run_ticks(
        runtimes, doors, start=0.0, n=230,
        outside_trigger={"b": True},
        occupants={"a": [("r1", (-0.5, 0.0))]},
    )
    assert len(jobs1) == 1
    # Robot exits at B. just_arrived gets pruned to empty.
    now, _ = _run_ticks(runtimes, doors, start=now, n=60)
    assert b.just_arrived == frozenset()
    # Re-enter and ride back.
    _, jobs3 = _run_ticks(
        runtimes, doors, start=now, n=250,
        occupants={"b": [("r1", (10.0, 0.0))]},
    )
    assert jobs3 == [("b", "a", [("r1", (10.0, 0.0))])]
    assert a.state == _ElevatorState.PRESENT
    assert b.state == _ElevatorState.ABSENT


def test_tick_missing_destination_reverts_to_present():
    runtimes, doors = _prime_pair()
    a = runtimes["a"]
    a.state = _ElevatorState.DEPARTING
    del runtimes["b"]
    doors["a/door"].state = _DoorState.CLOSED
    doors["a/door"].progress = 0.0
    _, jobs = _run_ticks(runtimes, doors, start=0.0, n=5)
    assert jobs == []
    assert a.state == _ElevatorState.PRESENT


def test_tick_iteration_order_invariant():
    end_states = []
    for order in [("a", "b"), ("b", "a")]:
        runtimes, doors = _prime_pair(iteration_order=order)
        _, _ = _run_ticks(runtimes, doors, start=0.0, n=100, outside_trigger={"b": True})
        end_states.append((
            runtimes["a"].state, runtimes["b"].state,
            doors["a/door"].state, round(doors["a/door"].progress, 3),
        ))
    assert end_states[0] == end_states[1]


# ---------------------------------------------------------------------------
# end-to-end passenger journeys (full state machine + teleport)
# ---------------------------------------------------------------------------


def test_tick_passenger_boards_at_present_and_returns():
    """Robot inside A's cabin; B-side caller triggers departure; robot teleports to B.
    Robot exits; A-side caller summons empty cabin back. Robot re-enters at A; B-side
    caller triggers another departure. Verifies state, door animation, and teleport payload
    across a full round trip."""
    runtimes, doors = _prime_pair()
    a, b = runtimes["a"], runtimes["b"]
    door_a, door_b = doors["a/door"], doors["b/door"]

    # Leg 1: robot inside A, B calls. ~7s = hold(2)+close(1)+travel(3)+open(1).
    now, jobs1 = _run_ticks(
        runtimes, doors, start=0.0, n=230,
        outside_trigger={"b": True},
        occupants={"a": [("r1", (-0.5, 0.0))]},
    )
    assert jobs1 == [("a", "b", [("r1", (-0.5, 0.0))])]
    assert a.state == _ElevatorState.ABSENT
    assert b.state == _ElevatorState.PRESENT
    assert door_a.state == _DoorState.CLOSED
    assert door_b.state == _DoorState.OPEN

    # Leg 2: robot exited, A calls. Empty cabin rides back.
    now, jobs2 = _run_ticks(
        runtimes, doors, start=now, n=230,
        outside_trigger={"a": True},
    )
    assert jobs2 == [("b", "a", [])]
    assert b.state == _ElevatorState.ABSENT
    assert a.state == _ElevatorState.PRESENT
    assert door_b.state == _DoorState.CLOSED
    assert door_a.state == _DoorState.OPEN

    # Leg 3: robot re-enters A, B calls again. Confirms repeatable cycle.
    now, jobs3 = _run_ticks(
        runtimes, doors, start=now, n=230,
        outside_trigger={"b": True},
        occupants={"a": [("r1", (0.2, -0.1))]},
    )
    assert jobs3 == [("a", "b", [("r1", (0.2, -0.1))])]
    assert a.state == _ElevatorState.ABSENT
    assert b.state == _ElevatorState.PRESENT
    assert door_b.state == _DoorState.OPEN


def test_tick_robot_calls_from_absent_then_rides_back():
    """Robot at B's outside (cabin at A) calls; empty cabin teleports to B.
    Robot enters B's cabin; A-side caller triggers return ride."""
    runtimes, doors = _prime_pair()
    a, b = runtimes["a"], runtimes["b"]
    door_a, door_b = doors["a/door"], doors["b/door"]

    # Leg 1: empty cabin moves from A to B.
    now, jobs1 = _run_ticks(runtimes, doors, start=0.0, n=230, outside_trigger={"b": True})
    assert jobs1 == [("a", "b", [])]
    assert a.state == _ElevatorState.ABSENT
    assert b.state == _ElevatorState.PRESENT
    assert door_b.state == _DoorState.OPEN

    # Leg 2: robot now inside B's cabin (B's center is (10, 0)); A calls.
    now, jobs2 = _run_ticks(
        runtimes, doors, start=now, n=230,
        outside_trigger={"a": True},
        occupants={"b": [("r1", (10.0, 0.0))]},
    )
    assert jobs2 == [("b", "a", [("r1", (10.0, 0.0))])]
    assert b.state == _ElevatorState.ABSENT
    assert a.state == _ElevatorState.PRESENT
    assert door_a.state == _DoorState.OPEN


# ---------------------------------------------------------------------------
# elevator door panel + wall geometry helpers
# ---------------------------------------------------------------------------


def _make_elevator(
    name: str = "elev",
    position: tuple[float, float, float] = (0.0, 0.0, 0.0),
    size: tuple[float, float, float] = (2.0, 2.0, 2.5),
    door_side: str = "+x",
) -> Elevator:
    return Elevator(name=name, position=Position(*position), size=list(size), door_side=door_side)


def test_door_slot_plus_x_inset():
    e = _make_elevator(position=(10.0, 5.0, 0.0), door_side='+x')
    start, end = _door_slot(e)
    assert start.x == pytest.approx(11.0 - DOOR_INSET)
    assert end.x == pytest.approx(11.0 - DOOR_INSET)
    assert start.y == pytest.approx(5.0 - 1.0 + DOOR_INSET)
    assert end.y == pytest.approx(5.0 + 1.0 - DOOR_INSET)
    assert start.z == pytest.approx(0.0)


def test_door_slot_minus_y_inset():
    e = _make_elevator(door_side='-y')
    start, end = _door_slot(e)
    assert start.y == pytest.approx(-1.0 + DOOR_INSET)
    assert end.y == pytest.approx(-1.0 + DOOR_INSET)
    assert start.x == pytest.approx(-1.0 + DOOR_INSET)
    assert end.x == pytest.approx(1.0 - DOOR_INSET)


def test_wall_geometries_plus_x_door():
    e = _make_elevator(door_side='+x')
    walls = {suffix: (size, pose) for suffix, size, pose in _elevator_wall_geometries(e)}
    assert set(walls) == {'back', 'side_pos', 'side_neg'}
    back_size, back_pose = walls['back']
    assert back_size == pytest.approx((WALL_THICKNESS, 2.0, 2.5))
    assert back_pose.position.x == pytest.approx(-1.0)
    assert back_pose.position.y == pytest.approx(0.0)
    side_size, side_pose_pos = walls['side_pos']
    assert side_size == pytest.approx((2.0, WALL_THICKNESS, 2.5))
    assert side_pose_pos.position.y == pytest.approx(1.0)
    assert walls['side_neg'][1].position.y == pytest.approx(-1.0)


def test_wall_geometries_minus_y_door():
    e = _make_elevator(door_side='-y')
    walls = {suffix: (size, pose) for suffix, size, pose in _elevator_wall_geometries(e)}
    back_size, back_pose = walls['back']
    assert back_size == pytest.approx((2.0, WALL_THICKNESS, 2.5))
    assert back_pose.position.y == pytest.approx(1.0)
    assert walls['side_pos'][0] == pytest.approx((WALL_THICKNESS, 2.0, 2.5))
    assert walls['side_pos'][1].position.x == pytest.approx(1.0)
    assert walls['side_neg'][1].position.x == pytest.approx(-1.0)


def test_wall_z_at_top_of_cabin():
    for _suffix, _size, pose in _elevator_wall_geometries(_make_elevator()):
        assert pose.position.z == pytest.approx(1.25)
