from __future__ import annotations

import json
import os
import subprocess
import sys

import pytest

_DRIVER = r"""
import json
import os
import sys

import launch
import launch.actions
import yaml
from ament_index_python.packages import get_package_share_directory
from launch.launch_description_sources import PythonLaunchDescriptionSource
from launch_ros.actions import Node

ctx = launch.LaunchContext()
ctx.launch_configurations.update(json.loads(sys.argv[1]))
path = os.path.join(get_package_share_directory("task_generator"), "launch", "task_generator.launch.py")
env_actions = []
for entity in PythonLaunchDescriptionSource(path).get_launch_description(ctx).entities:
    if isinstance(entity, launch.actions.DeclareLaunchArgument):
        entity.execute(ctx)
    elif isinstance(entity, launch.actions.OpaqueFunction):
        env_actions = entity.execute(ctx) or []

found = {"includes": {}, "params": {}}
expanded = ("auditory.launch.py", "arena.launch.py", "arena_auditory.launch.py")

def perform(value):
    return launch.utilities.perform_substitutions(ctx, launch.utilities.normalize_to_list_of_substitutions(value))

def walk(entity):
    if isinstance(entity, Node):
        if entity.node_package == "arena_auditory":
            entity._perform_substitutions(ctx)
            params = {}
            for argument, is_file in entity._Node__expanded_parameter_arguments:
                if is_file:
                    with open(argument) as f:
                        for section in yaml.safe_load(f).values():
                            params.update(section["ros__parameters"])
            found["params"][entity.node_name.rsplit("/", 1)[-1]] = params
    elif isinstance(entity, launch.actions.IncludeLaunchDescription):
        entity.launch_description_source.get_launch_description(ctx)
        name = os.path.basename(entity.launch_description_source.location)
        found["includes"][name] = sorted(perform(k) for k, _ in entity.launch_arguments)
        if name in expanded:
            for child in entity.execute(ctx):
                walk(child)
    elif isinstance(entity, launch.LaunchDescription):
        for child in entity.entities:
            walk(child)
    elif isinstance(entity, launch.Action) and not isinstance(entity, (launch.actions.ExecuteProcess, launch.actions.RegisterEventHandler)):
        for child in entity.execute(ctx) or []:
            walk(child)

for action in env_actions:
    walk(action)
print(json.dumps(found))
"""

_BASE_ARGS = {"env.managed": "true", "sim": "dummy", "env.id": "7", "env.ns": "env7/task_generator_node"}


def _env(*, with_auditory: bool) -> dict[str, str]:
    if with_auditory:
        return dict(os.environ)
    prefixes = [p for p in os.environ["AMENT_PREFIX_PATH"].split(os.pathsep) if os.path.basename(p) != "arena_auditory"]
    paths = [p for p in os.environ.get("PYTHONPATH", "").split(os.pathsep) if "arena_auditory" not in p]
    return {**os.environ, "AMENT_PREFIX_PATH": os.pathsep.join(prefixes), "PYTHONPATH": os.pathsep.join(paths)}


def _launch(args: dict[str, str], *, with_auditory: bool) -> subprocess.CompletedProcess[str]:
    return subprocess.run([sys.executable, "-c", _DRIVER, json.dumps({**_BASE_ARGS, **args})], env=_env(with_auditory=with_auditory), capture_output=True, text=True, timeout=120, check=False)


def _found(proc: subprocess.CompletedProcess[str]) -> dict:
    assert proc.returncode == 0, proc.stderr
    return json.loads(proc.stdout.strip().splitlines()[-1])


@pytest.fixture(scope="module", autouse=True)
def _require_ament() -> None:
    if "AMENT_PREFIX_PATH" not in os.environ:
        pytest.skip("AMENT_PREFIX_PATH unset: source install/setup.bash")


def test_task_generator_imports_without_arena_auditory(tmp_path) -> None:
    code = "import importlib.util, task_generator.simulators.human, task_generator.tasks.modules.sounds.impl; assert importlib.util.find_spec('arena_auditory') is None"
    proc = subprocess.run([sys.executable, "-c", code], env=_env(with_auditory=False), cwd=tmp_path, capture_output=True, text=True, timeout=120, check=False)
    assert proc.returncode == 0, proc.stderr


def test_auditory_none_launches_without_arena_auditory() -> None:
    found = _found(_launch({"auditory": "none"}, with_auditory=False))
    assert "auditory.launch.py" not in found["includes"]
    assert "hearing.launch.py" not in found["includes"]


@pytest.mark.parametrize(
    "args",
    [
        {"auditory": "arena"},
        {"auditory": "none", "auditory.static_sounds": "[{name: radio}]"},
        {"auditory": "none", "task.modules": "sounds"},
    ],
)
def test_sounds_module_without_arena_auditory_names_the_feature(args: dict[str, str]) -> None:
    proc = _launch(args, with_auditory=False)
    assert proc.returncode != 0
    assert "arena feature auditory install" in proc.stderr


def test_auditory_arena_leaves_empty_paths_to_the_auditory_defaults() -> None:
    found = _found(_launch({"auditory": "arena"}, with_auditory=True))
    assert "auditory.launch.py" in found["includes"]
    assert "array.spec" in found["includes"]["arena_auditory.launch.py"]
    assert found["params"]
    for name, params in found["params"].items():
        assert "array.spec" not in params, name


def test_auditory_arena_forwards_explicit_paths() -> None:
    found = _found(_launch({"auditory": "arena", "auditory.array.spec": "/tmp/array.yaml"}, with_auditory=True))
    assert found["params"]
    for name, params in found["params"].items():
        assert params["array.spec"] == "/tmp/array.yaml", name


def test_hearing_included_only_when_enabled() -> None:
    assert "hearing.launch.py" not in _found(_launch({"auditory": "arena"}, with_auditory=True))["includes"]
    assert "hearing.launch.py" in _found(_launch({"auditory": "arena", "robot.hearing": "bus"}, with_auditory=True))["includes"]
