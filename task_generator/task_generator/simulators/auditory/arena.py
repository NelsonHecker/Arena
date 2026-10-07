"""Backend for auditory:=arena, the arena_auditory sidecar (propagation, hearing, emission, playback)."""

from __future__ import annotations

import typing
from collections.abc import Callable

from arena_rclpy_mixins.qos import best_effort
from arena_viz.kinds import DisplayKind
from arena_viz.style import StyleSpec
from task_generator_msgs.msg import AdapterDisplay

from task_generator.simulators.auditory import BaseAuditorySimulator
from task_generator.simulators.human.utils import stimulus_edge

if typing.TYPE_CHECKING:
    from arena_auditory_msgs.msg import ContinuousHeardSoundState

    from task_generator.simulators.human import BaseHumanSimulator

CONTINUOUS_QOS_DEPTH = 64


class PedestrianHearing:
    """Per (agent, sound kind) audibility over all sources, notifying the human simulator on every edge."""

    def __init__(self, human: BaseHumanSimulator, agent_of: Callable[[str], int | None]) -> None:
        self._human = human
        self._agent_of = agent_of
        self._heard: dict[tuple[int, str], bool] = {}
        self._sources: dict[tuple[int, str], dict[str, bool]] = {}

    def clear(self) -> None:
        self._heard.clear()
        self._sources.clear()

    async def on_heard_sound(self, msg: ContinuousHeardSoundState) -> None:
        agent_id = self._agent_of(msg.reception.listener_id)
        if agent_id is None:
            return
        key = (agent_id, msg.source.kind)
        sources = self._sources.setdefault(key, {})
        sources[msg.source.id] = bool(msg.source.active and msg.reception.audible)
        audible = any(sources.values())
        if stimulus_edge(self._heard.get(key), audible):
            await self._human.notify_stimulus(agent_id, msg.source.kind, 1.0 if audible else 0.0)
        self._heard[key] = audible


class ArenaAuditorySimulator(BaseAuditorySimulator):
    """The propagation node builds its acoustic scene from the map topic, so the map server must be up before episodes start."""

    @property
    def requires_map_server(self) -> bool:
        return True

    def displays(self) -> tuple[AdapterDisplay, ...]:
        from arena_auditory.api import ENVIRONMENT_SOURCE_MARKERS, MICROPHONE_MARKERS, PEDESTRIAN_PROPAGATION_MARKERS, ROBOT_PROPAGATION_MARKERS

        auditory_ns = self.node.get_fully_qualified_name()
        return tuple(
            AdapterDisplay(
                name=name,
                topic=f"{auditory_ns}/{topic}",
                topic_type="visualization_msgs/MarkerArray",
                kind=DisplayKind.MARKER_ARRAY,
                style_json=StyleSpec(latched=True).to_json() if topic == MICROPHONE_MARKERS else StyleSpec(enabled=True).to_json(),
                topic_must_exist=False,
                group="Sound Propagation",
            )
            for name, topic in (
                ("Microphones", MICROPHONE_MARKERS),
                ("Environment Audio Sources", ENVIRONMENT_SOURCE_MARKERS),
                ("Pedestrian Heard Sound", PEDESTRIAN_PROPAGATION_MARKERS),
                ("Robot Heard Sound", ROBOT_PROPAGATION_MARKERS),
            )
        )

    def pedestrian_hearing(self, human: BaseHumanSimulator) -> PedestrianHearing:
        from arena_auditory_msgs.msg import ContinuousHeardSoundState

        from arena_auditory.api import CONTINUOUS_HEARD_SOUNDS, ListenerId, ListenerKind

        def agent_of(listener_id: str) -> int | None:
            try:
                listener = ListenerId.parse(listener_id)
            except ValueError:
                return None
            return int(listener.owner) if listener.kind is ListenerKind.AGENT else None

        hearing = PedestrianHearing(human, agent_of)
        human.node.create_subscription(
            ContinuousHeardSoundState,
            human.node.service_namespace(CONTINUOUS_HEARD_SOUNDS),
            hearing.on_heard_sound,
            best_effort(CONTINUOUS_QOS_DEPTH),
        )
        return hearing

    def robot_displays(self, robot: str, *, hearing: bool) -> tuple[AdapterDisplay, ...]:
        from arena_auditory.api import BELIEF_GRID, BELIEF_WEDGES, SPEED_FILTER_MASK, ArrayStream, array_stream, motor_markers

        auditory_ns = self.node.get_fully_qualified_name()
        displays = [
            AdapterDisplay(
                name=name,
                topic=f"{auditory_ns}/{topic}",
                topic_type="visualization_msgs/MarkerArray",
                kind=DisplayKind.MARKER_ARRAY,
                style_json=StyleSpec(enabled=True).to_json(),
                topic_must_exist=False,
            )
            for name, topic in (
                ("Motor Sound", motor_markers(robot)),
                ("Mic Levels", array_stream(robot, ArrayStream.LEVELS)),
            )
        ]
        if hearing:
            displays.extend(
                AdapterDisplay(
                    name=name,
                    topic=f"{auditory_ns}/{robot}/{topic}",
                    topic_type=topic_type,
                    kind=kind,
                    style_json=style,
                    topic_must_exist=False,
                    group="Hearing",
                )
                for name, topic, topic_type, kind, style in (
                    ("Belief", BELIEF_GRID, "nav_msgs/OccupancyGrid", DisplayKind.MAP, StyleSpec(alpha=0.6, extra={"rviz": {"Color Scheme": "costmap", "Durability Policy": "Volatile"}}).to_json()),
                    ("Speed Mask", SPEED_FILTER_MASK, "nav_msgs/OccupancyGrid", DisplayKind.MAP, StyleSpec(alpha=0.4, enabled=False, extra={"rviz": {"Color Scheme": "costmap"}}).to_json()),
                    ("Wedges", BELIEF_WEDGES, "visualization_msgs/MarkerArray", DisplayKind.MARKER_ARRAY, StyleSpec(enabled=True).to_json()),
                )
            )
        return tuple(displays)
