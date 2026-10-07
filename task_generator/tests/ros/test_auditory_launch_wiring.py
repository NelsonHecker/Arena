from __future__ import annotations

import os

import pytest
import yaml


@pytest.fixture(scope="module", autouse=True)
def _require_auditory() -> None:
    if "AMENT_PREFIX_PATH" not in os.environ:
        pytest.skip("AMENT_PREFIX_PATH unset: source install/setup.bash")
    pytest.importorskip("arena_auditory")


def _launch_path(*parts: str) -> str:
    from ament_index_python.packages import get_package_share_directory

    return os.path.join(get_package_share_directory("task_generator"), "launch", *parts)


def _declared_default(path: str, name: str) -> str:
    import launch
    from launch.launch_description_sources import PythonLaunchDescriptionSource

    ctx = launch.LaunchContext()
    for entity in PythonLaunchDescriptionSource(path).get_launch_description(ctx).entities:
        if isinstance(entity, launch.actions.DeclareLaunchArgument) and entity.name == name:
            return launch.utilities.perform_substitutions(ctx, entity.default_value)
    raise AssertionError(f"{name} is not declared in {path}")


def _arena_nodes() -> dict:
    import launch
    from launch.launch_description_sources import PythonLaunchDescriptionSource
    from launch_ros.actions import Node

    ctx = launch.LaunchContext()
    ctx.launch_configurations.update({"namespace": "env7/task_generator_node", "environment_namespace": "env7"})
    nodes: dict = {}

    def walk(entity) -> None:
        if isinstance(entity, Node):
            entity._perform_substitutions(ctx)
            nodes[entity.node_name.rsplit("/", 1)[-1]] = entity
        elif isinstance(entity, launch.LaunchDescription):
            for child in entity.entities:
                walk(child)
        elif isinstance(entity, launch.Action):
            for child in entity.execute(ctx) or []:
                walk(child)

    walk(PythonLaunchDescriptionSource(_launch_path("auditory", "arena", "arena.launch.py")).get_launch_description(ctx))
    return nodes


def _parameters(node) -> dict:
    params: dict = {}
    for argument, is_file in node._Node__expanded_parameter_arguments:
        if is_file:
            with open(argument) as f:
                for section in yaml.load(f, Loader=yaml.FullLoader).values():
                    params.update(section["ros__parameters"])
    return params


def _topic(node, name: str) -> str:
    from rclpy.expand_topic_name import expand_topic_name

    return expand_topic_name(name, node.node_name.rsplit("/", 1)[-1], node.expanded_node_namespace)


def test_auditory_playback_nodes_run_on_sim_time() -> None:
    nodes = _arena_nodes()
    for name in ("array_renderer", "listener_renderer", "robot_emitter"):
        assert _parameters(nodes[name])["use_sim_time"] is True, name


def test_discrete_sound_events_share_the_sound_events_topic() -> None:
    from arena_auditory.constants import HEARD_SOUND_EVENTS, SOUND_EVENTS

    nodes = _arena_nodes()
    assert _topic(nodes["human_emitter"], SOUND_EVENTS) == _topic(nodes["sound_propagation_node"], SOUND_EVENTS) == "/env7/task_generator_node/sound_events"
    heard = _topic(nodes["sound_propagation_node"], HEARD_SOUND_EVENTS)
    for name in ("array_renderer", "listener_renderer", "robot_hearing_node"):
        assert _topic(nodes[name], HEARD_SOUND_EVENTS) == heard, name


def test_pedestrian_hearing_defaults_off() -> None:
    from arena_auditory.params import all_params

    assert "pedestrian_listeners.enabled" not in _parameters(_arena_nodes()["sound_propagation_node"])
    assert all_params()["pedestrian_listeners.enabled"].default is False
    assert _declared_default(_launch_path("task_generator.launch.py"), "auditory.pedestrian_listeners.enabled") == ""
