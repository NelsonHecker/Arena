"""Nav2 launch helpers."""

import tempfile
import typing
from pathlib import Path

import launch
import yaml
from arena_bringup.substitutions import YAMLFileSubstitution

from arena_robots.caps import MobileSpec
from arena_robots.Robot import ModelParams
from arena_robots.Sensor import SensorSpec, SensorType


def compile_sensors_to_nav2(
    sensors: list[SensorSpec],
    *,
    max_obstacle_height: float = 2.0,
    clearing: bool = True,
    marking: bool = True,
) -> dict[str, dict[str, typing.Any]]:
    """Compile Arena SensorSpec entries into nav2's observation_sources_dict shape."""
    # Unknown type strings fall through unchanged so third-party sensor
    # kinds nav2 understands keep working.
    _TYPE_TO_NAV2: dict[str, str] = {
        SensorType.LASERSCAN.value: "LaserScan",
        SensorType.POINTCLOUD.value: "PointCloud2",
        SensorType.IMAGE.value: "Image",
        SensorType.DEPTH.value: "DepthImage",
    }

    out: dict[str, dict[str, typing.Any]] = {}
    for spec in sensors:
        type_str = spec.type.value if isinstance(spec.type, SensorType) else str(spec.type)
        data_type = _TYPE_TO_NAV2.get(type_str, type_str)
        out[spec.name] = {
            "topic": spec.topic,
            "data_type": data_type,
            "max_obstacle_height": max_obstacle_height,
            "clearing": clearing,
            "marking": marking,
        }
    return out


def _load_mobile(path_str: str) -> MobileSpec:
    with open(path_str) as f:
        data = yaml.safe_load(f) or {}
    if not isinstance(data, dict):
        raise ValueError(f"{path_str}: mobile.yaml must be a mapping at top level")
    return MobileSpec(path=Path(path_str), raw=data)


class SensorsDerivedYAML(YAMLFileSubstitution):
    """Emit a temp YAML file with `observation_sources{,_string,_dict}` derived
    from the `sensors:` block of model_params.yaml. Keeps the three nav2 costmap
    forms in sync from one source."""

    def __init__(self, model_params_path: launch.SomeSubstitutionsType):
        super().__init__(path=[], default={}, substitute=False)
        self._path = launch.utilities.normalize_to_list_of_substitutions(model_params_path)

    def perform(self, context: launch.LaunchContext) -> str:
        path_str = launch.utilities.perform_substitutions(context, self._path)
        sensors = ModelParams.from_yaml(path_str).sensors
        names = [s.name for s in sensors]
        derived = {
            'observation_sources_string': ' '.join(names),
            'observation_sources': list(names),
            'observation_sources_dict': compile_sensors_to_nav2(sensors),
        }
        tmp = tempfile.NamedTemporaryFile(mode='w', delete=False, suffix='.yaml')
        yaml.dump(derived, tmp)
        tmp.close()
        return tmp.name


class Nav2SubBlockYAML(YAMLFileSubstitution):
    """Extract the `nav2:` sub-block from caps/mobile.yaml and emit it at top level
    as a temp YAML file. Lets YAMLMergeSubstitution treat adapter-specific config
    (footprint, polygons*, planner_plugins*) as flat merge-time keys while they
    stay nested in the authored file."""

    def __init__(self, mobile_path: launch.SomeSubstitutionsType):
        super().__init__(path=[], default={}, substitute=False)
        self._path = launch.utilities.normalize_to_list_of_substitutions(mobile_path)

    def perform(self, context: launch.LaunchContext) -> str:
        path_str = launch.utilities.perform_substitutions(context, self._path)
        raw = _load_mobile(path_str).sub('nav2')
        tmp = tempfile.NamedTemporaryFile(mode='w', delete=False, suffix='.yaml')
        yaml.dump(raw, tmp)
        tmp.close()
        return tmp.name
