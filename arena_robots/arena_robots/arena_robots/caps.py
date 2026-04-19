"""Capability-file loader for robots/<name>/caps/.

Each YAML under caps/ declares one capability the robot advertises. File
presence is the advertisement: `caps/arm.yaml` means the robot has `arm`.

Shape convention:
    caps/mobile.yaml  — flat primitives + adapter sub-blocks (nav2, rl, ...)
    caps/arm.yaml     — dict of named instances (single-arm is one entry named "arm")
    caps/lift.yaml    — dict of named instances
    caps/gripper.yaml — dict of named instances, with per-entry `arm:` back-ref

Adapter-specific sub-blocks (moveit, drl_grasp, nav2, rl) are raw dicts inside
each entry / at top level — read only by their matching runtime-selected adapter.
"""

from __future__ import annotations

import subprocess
import typing
import xml.etree.ElementTree as ET
from pathlib import Path

import attrs
import yaml


@attrs.define(slots=False)
class CapConfig:
    """Raw cap file content + the path it came from, for error messages and
    adapter-sub-block access. Typed subclasses front the fields adapters need
    directly."""

    path: Path
    raw: dict[str, typing.Any]

    def sub(self, adapter: str) -> dict[str, typing.Any]:
        """Return the adapter-specific sub-block or an empty dict."""
        v = self.raw.get(adapter, {})
        if not isinstance(v, dict):
            raise ValueError(f"{self.path}: '{adapter}' sub-block must be a mapping; got {type(v).__name__}")
        return v


@attrs.define(slots=False)
class MobileSpec(CapConfig):
    """Primitives from caps/mobile.yaml (flat, single-instance)."""

    @property
    def odom_frame(self) -> str:
        return str(self.raw.get('odom_frame', 'odom'))

    @property
    def sensor_frame(self) -> str | None:
        v = self.raw.get('sensor_frame')
        return None if v is None else str(v)

    @property
    def radius(self) -> float | None:
        v = self.raw.get('radius')
        return None if v is None else float(v)

    @property
    def is_holonomic(self) -> bool:
        return bool(self.raw.get('is_holonomic', False))


@attrs.define(slots=False)
class InstanceSpec(CapConfig):
    """Per-instance spec for multi-instance caps (arm, lift, gripper).

    An instance's `path` points at the cap file; `name` is the dict key within
    that file. Adapter-specific sub-blocks are nested inside each instance.
    """

    name: str


@attrs.define(slots=False)
class ArmSpec(InstanceSpec):
    """Serial-chain arm primitives. Resolves via SRDF if `srdf:` is declared
    and the matching field isn't explicit; explicit always wins."""

    _srdf_cache: dict[str, typing.Any] | None = attrs.field(default=None, init=False)

    def _srdf(self) -> dict[str, typing.Any]:
        if self._srdf_cache is None:
            srdf_ref = self.raw.get('srdf')
            self._srdf_cache = _parse_srdf_group(srdf_ref, self.name) if srdf_ref else {}
        return self._srdf_cache

    @property
    def base_link(self) -> str:
        v = self.raw.get('base_link') or self._srdf().get('base_link')
        if v is None:
            raise ValueError(f"{self.path}: arm '{self.name}' has no base_link (not explicit, not derivable from srdf)")
        return str(v)

    @property
    def tip_link(self) -> str:
        v = self.raw.get('tip_link') or self._srdf().get('tip_link')
        if v is None:
            raise ValueError(f"{self.path}: arm '{self.name}' has no tip_link (not explicit, not derivable from srdf)")
        return str(v)

    @property
    def chain(self) -> list[str]:
        v = self.raw.get('chain')
        if v is None:
            v = self._srdf().get('chain')
        if not isinstance(v, list):
            raise ValueError(f"{self.path}: arm '{self.name}' has no chain (not explicit, not derivable from srdf)")
        return [str(j) for j in v]

    @property
    def controller(self) -> str:
        v = self.raw.get('controller')
        if v is None:
            raise ValueError(f"{self.path}: arm '{self.name}' missing 'controller' (controllers are not in SRDF; always author explicitly)")
        return str(v)


@attrs.define(slots=False)
class LiftSpec(InstanceSpec):
    """Prismatic lift primitives."""

    @property
    def joint(self) -> str:
        v = self.raw.get('joint')
        if v is None:
            raise ValueError(f"{self.path}: lift '{self.name}' missing 'joint'")
        return str(v)

    @property
    def controller(self) -> str:
        v = self.raw.get('controller')
        if v is None:
            raise ValueError(f"{self.path}: lift '{self.name}' missing 'controller'")
        return str(v)


@attrs.define(slots=False)
class GripperSpec(InstanceSpec):
    """Gripper primitives with an optional back-reference to its arm."""

    @property
    def arm(self) -> str | None:
        v = self.raw.get('arm')
        return None if v is None else str(v)

    @property
    def joint(self) -> str:
        v = self.raw.get('joint')
        if v is None:
            raise ValueError(f"{self.path}: gripper '{self.name}' missing 'joint'")
        return str(v)

    @property
    def controller(self) -> str:
        v = self.raw.get('controller')
        if v is None:
            raise ValueError(f"{self.path}: gripper '{self.name}' missing 'controller'")
        return str(v)


_INSTANCE_CLASSES: dict[str, type[InstanceSpec]] = {
    'arm': ArmSpec,
    'lift': LiftSpec,
    'gripper': GripperSpec,
}


@attrs.define(slots=False)
class RobotCaps:
    """Lazy, typed view over a robot's caps/ directory.

    File presence → cap advertisement. Typed accessors front the cap files;
    the generic `raw(<cap>)` exposes adapter-sub-blocks authored on a cap
    Arena doesn't model as a first-class spec yet.
    """

    caps_dir: Path

    _cached: dict[str, typing.Any] = attrs.field(factory=dict, init=False)

    @property
    def available(self) -> frozenset[str]:
        """Cap names present as `caps/<name>.yaml`. Empty if no caps/ dir."""
        if not self.caps_dir.is_dir():
            return frozenset()
        return frozenset(p.stem for p in self.caps_dir.glob('*.yaml'))

    def _load_cap_file(self, cap: str) -> dict[str, typing.Any]:
        if cap in self._cached:
            return self._cached[cap]
        path = self.caps_dir / f'{cap}.yaml'
        if not path.is_file():
            raise FileNotFoundError(f"cap '{cap}' not declared: {path} does not exist")
        with open(path) as f:
            data = yaml.safe_load(f) or {}
        if not isinstance(data, dict):
            raise ValueError(f"{path}: top-level structure must be a mapping; got {type(data).__name__}")
        self._cached[cap] = data
        return data

    @property
    def mobile(self) -> MobileSpec:
        data = self._load_cap_file('mobile')
        return MobileSpec(path=self.caps_dir / 'mobile.yaml', raw=data)

    @property
    def arm(self) -> dict[str, ArmSpec]:
        return self._instances('arm', ArmSpec)

    @property
    def lift(self) -> dict[str, LiftSpec]:
        return self._instances('lift', LiftSpec)

    @property
    def gripper(self) -> dict[str, GripperSpec]:
        return self._instances('gripper', GripperSpec)

    def _instances(
        self,
        cap: str,
        cls: type[InstanceSpec],
    ) -> dict[str, typing.Any]:
        data = self._load_cap_file(cap)
        path = self.caps_dir / f'{cap}.yaml'
        out: dict[str, typing.Any] = {}
        for name, entry in data.items():
            if not isinstance(entry, dict):
                raise ValueError(f"{path}: '{name}' must be a mapping (dict-keyed instance); got {type(entry).__name__}. See robots/README.md on the uniform dict-keyed shape for multi-instance caps.")
            out[str(name)] = cls(path=path, raw=entry, name=str(name))
        return out


def _parse_srdf_group(srdf_ref: str, group_name: str) -> dict[str, typing.Any]:
    """Resolve a `$(find …)/…srdf[.xacro]` ref and extract a <group>'s primitives.

    Returns a dict with `base_link`, `tip_link`, and — if the group enumerates
    joints via <joints> or the URDF walk succeeds — `chain`.
    """
    src_path = _resolve_find_ref(srdf_ref)
    if src_path.suffix == '.xacro':
        xml_text = subprocess.check_output(
            ['xacro', '--inorder', str(src_path)],
            text=True,
        )
        root = ET.fromstring(xml_text)
    else:
        root = ET.parse(str(src_path)).getroot()

    group = root.find(f"./group[@name='{group_name}']")
    if group is None:
        raise ValueError(f"{srdf_ref}: no <group name='{group_name}'> found")

    out: dict[str, typing.Any] = {}
    chain = group.find('./chain')
    if chain is not None:
        out['base_link'] = chain.attrib.get('base_link')
        out['tip_link'] = chain.attrib.get('tip_link')

    joints_nodes = group.findall('./joint')
    if joints_nodes:
        out['chain'] = [j.attrib['name'] for j in joints_nodes]

    return out


def _resolve_find_ref(ref: str) -> Path:
    """Resolve `$(find <pkg>)/<rest>` to an absolute Path. Non-$(find) inputs
    are treated as filesystem paths as-is."""
    ref = ref.strip()
    if ref.startswith('$(find '):
        end = ref.index(')')
        pkg = ref[len('$(find ') : end]
        rest = ref[end + 1 :].lstrip('/')
        from ament_index_python.packages import get_package_share_path

        return get_package_share_path(pkg) / rest
    return Path(ref)
