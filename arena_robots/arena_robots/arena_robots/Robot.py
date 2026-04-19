import functools
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
from arena_robots.Sensor import SensorSpec
from arena_robots.caps import RobotCaps


class ModelParams(dict[str, typing.Any]):
    """Robot-wide identity (from ``model_params.yaml``) with typed accessors
    that delegate to the sibling ``caps/`` tree for mobile primitives.

    Constructed via :meth:`from_yaml` which records the file path; the
    ``caps`` cached property resolves ``<path>.parent / 'caps'`` so every
    ``ModelParams`` that came from disk can see its robot's cap tree without
    external wiring."""

    _path: Path | None = None

    @classmethod
    def from_yaml(cls, path: str | Path) -> 'ModelParams':
        path = Path(path)
        with open(path) as f:
            data = yaml.safe_load(f)
        if not isinstance(data, dict):
            raise ValueError(f"Top-level structure in {path} must be a mapping")
        inst = cls(data)
        inst._path = path
        return inst

    @functools.cached_property
    def caps(self) -> RobotCaps:
        """Lazy view over ``<robot_dir>/caps/``. Empty if this ``ModelParams``
        wasn't loaded from disk or the caps dir doesn't exist."""
        caps_dir = (
            self._path.parent / 'caps' if self._path is not None else Path('/dev/null')
        )
        return RobotCaps(caps_dir=caps_dir)

    def _mobile(self):
        if 'mobile' not in self.caps.available:
            return None
        return self.caps.mobile

    @property
    def base_frame(self) -> str:
        return str(self.get('base_frame', self.get('robot_base_frame', 'base_link')))

    @property
    def odom_frame(self) -> str:
        m = self._mobile()
        if m is not None:
            return m.odom_frame
        return self.get('robot_odom_frame', 'odom')

    @property
    def z_offset(self) -> float:
        return float(self.get('z_offset', 0.0))

    @property
    def navigator(self) -> str:
        """Default navstack adapter kind baked into the robot model; precedence: robot_setup YAML > CLI > model_params."""
        return str(self.get('navigator', 'nav2'))

    @property
    def sensors(self) -> list["SensorSpec"]:
        raw = self.get('sensors', [])
        if not isinstance(raw, list):
            raise ValueError(
                f"model_params 'sensors' must be a list; got {type(raw).__name__}"
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


class RobotView(PathView):

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self._cached_params: ModelParams | None = None
        self._cached_control: dict | None = None

    @property
    def caps(self) -> RobotCaps:
        """Lazy view over robots/<name>/caps/, equivalent to
        ``self.model_params.caps`` — exposed directly on ``RobotView`` for
        readability."""
        return self.model_params.caps

    @property
    def model_params(self) -> ModelParams:
        if self._cached_params is None:
            path = self.path / 'model_params.yaml'
            if not path.is_file():
                raise FileNotFoundError(
                    f"model_params.yaml not found for robot '{self.name}' at {path}"
                )
            self._cached_params = ModelParams.from_yaml(path)
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
