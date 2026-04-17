import typing
from pathlib import Path

import attrs
import yaml
from ament_index_python.packages import get_package_share_path
from arena_simulation_setup.tree import Identifier, PathView, SimplePathResolver
from arena_simulation_setup.utils.models import ModelWrapper
from arena_simulation_setup.utils.models.model_loader import (
    ModelProvider_URDF,
    ModelProvider_USD,
)
from arena_robots.Sensor import SensorSpec, SensorType


class ModelParams(dict[str, typing.Any]):
    @classmethod
    def from_yaml(cls, path: str) -> 'ModelParams':
        with open(path) as f:
            data = yaml.safe_load(f)
            if not isinstance(data, dict):
                raise ValueError(f"Top-level structure in {path} must be a mapping")
            return cls(data)

    @property
    def base_frame(self) -> str:
        return self.get('robot_base_frame', 'base_link')

    @property
    def odom_frame(self) -> str:
        return self.get('robot_odom_frame', 'odom')

    @property
    def z_offset(self) -> float:
        return self.get('z_offset', 0.0)

    @property
    def actuator_caps(self) -> frozenset[str]:
        """Actuator-capability set this robot honors; defaults to {"mobile"}."""
        raw = self.get('actuator_caps', ['mobile'])
        if not isinstance(raw, (list, tuple, set, frozenset)):
            raise ValueError(
                f"model_params 'actuator_caps' must be a list/sequence of "
                f"strings; got {type(raw).__name__}"
            )
        return frozenset(str(c) for c in raw)

    @property
    def navigator(self) -> str:
        """Default navstack adapter kind baked into the robot model; precedence: robot_setup YAML > CLI > model_params."""
        return str(self.get('navigator', 'nav2'))

    @property
    def sensors(self) -> list["SensorSpec"]:
        """Declared sensors parsed into SensorSpec entries; extra keys are ignored."""
        raw = self.get('sensors', [])
        if not isinstance(raw, list):
            raise ValueError(
                f"model_params 'sensors' must be a list; got "
                f"{type(raw).__name__}"
            )
        out: list[SensorSpec] = []
        for i, entry in enumerate(raw):
            if not isinstance(entry, dict):
                raise ValueError(
                    f"model_params 'sensors[{i}]' must be a mapping; "
                    f"got {type(entry).__name__}"
                )
            missing = {'name', 'type', 'topic', 'frame'} - set(entry)
            if missing:
                raise ValueError(
                    f"model_params 'sensors[{i}]' missing required "
                    f"keys: {sorted(missing)}"
                )
            out.append(SensorSpec(
                name=str(entry['name']),
                type=str(entry['type']),
                topic=str(entry['topic']),
                frame=str(entry['frame']),
            ))
        return out

    @property
    def capabilities(self) -> list[dict[str, typing.Any]]:
        """Structured multi-adapter declaration as a list of dicts."""
        raw = self.get('capabilities', [])
        if not isinstance(raw, list):
            raise ValueError(
                f"model_params 'capabilities' must be a list; got "
                f"{type(raw).__name__}"
            )
        return [dict(entry) for entry in raw]


def compile_sensors_to_nav2(
    sensors: list["SensorSpec"],
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
        type_str = (
            spec.type.value
            if isinstance(spec.type, SensorType)
            else str(spec.type)
        )
        data_type = _TYPE_TO_NAV2.get(type_str, type_str)
        out[spec.name] = {
            "topic": spec.topic,
            "data_type": data_type,
            "max_obstacle_height": max_obstacle_height,
            "clearing": clearing,
            "marking": marking,
        }
    return out


class RobotView(PathView):

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self._cached_params: ModelParams | None = None
        self._cached_control: dict | None = None

    @property
    def model_params(self) -> ModelParams:
        if self._cached_params is None:
            path = self.path / 'model_params.yaml'
            if not path.is_file():
                raise FileNotFoundError(
                    f"model_params.yaml not found for robot '{self.name}' at {path}"
                )
            self._cached_params = ModelParams.from_yaml(str(path))
        return self._cached_params

    @property
    def mappings(self) -> str:
        return str(self.path / 'mappings.yaml')

    @property
    def control(self) -> dict:
        if self._cached_control is None:
            control_path = self.path / 'control.yaml'
            if not control_path.is_file():
                raise FileNotFoundError(
                    f"control.yaml not found for robot '{self.name}' at {control_path}"
                )
            with open(control_path) as f:
                mapping = yaml.safe_load(f)
                if not isinstance(mapping, dict):
                    raise ValueError(f"Control file {control_path} must contain a dictionary at the top level.")
                self._cached_control = mapping
        return self._cached_control

    @property
    def model(self) -> ModelWrapper:
        return ModelWrapper(
            self.name,
            {
                **ModelProvider_URDF.asdict(self.path, self.name),
                **ModelProvider_USD.asdict(self.path, self.name),
            }
        )


@attrs.define(eq=False, hash=False)
class RobotIdentifier(Identifier[RobotView]):
    def load(self, path: Path, /, **kwargs) -> RobotView:
        del kwargs  # unused
        return RobotView(path)


RobotIdentifier.use(SimplePathResolver(RobotIdentifier, get_package_share_path('arena_robots') / 'robots'))
