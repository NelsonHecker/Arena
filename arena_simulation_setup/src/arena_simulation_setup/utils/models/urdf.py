import asyncio
import json
import os
import subprocess
import sys
import xml.etree.ElementTree as ET
from pathlib import Path

import aiofiles
import attrs

from . import Model, ModelProvider, ModelType

_PACKAGE_URI = "package://"

_OPTIM_MAP: dict[str, frozenset[str]] = {
    'no_camera': frozenset({'camera', 'depth', 'rgbd_camera'}),
    'no_lidar': frozenset({'ray', 'gpu_lidar'}),
}


def _set_child(parent: ET.Element, tag: str, text: str) -> None:
    for child in parent:
        if child.tag.rpartition('}')[-1] == tag:
            child.text = text
            return
    ET.SubElement(parent, tag).text = text


def _apply_sensor_patches(root: ET.Element, patches: list[tuple[str, str, str]]) -> None:
    """Apply `(sensor name, child element path, value)` patches to URDF <gazebo> sensors."""
    by_name: dict[str, list[tuple[str, str]]] = {}
    for name, path, value in patches:
        by_name.setdefault(str(name), []).append((str(path), str(value)))

    seen: set[str] = set()
    for gazebo in root.iter():
        if gazebo.tag.rpartition('}')[-1] != 'gazebo':
            continue
        for sensor in gazebo.iter():
            if sensor.tag.rpartition('}')[-1] != 'sensor':
                continue
            name = sensor.attrib.get('name')
            if name is None or name not in by_name:
                continue
            if name in seen:
                print(f"[urdf.sensors] duplicate sensor name {name!r}, patches applied only to the first", file=sys.stderr)
                continue
            seen.add(name)
            for path, value in by_name[name]:
                *parent_tags, leaf = path.split('/')
                parent: ET.Element | None = sensor
                for tag in parent_tags:
                    parent = next((c for c in parent if c.tag.rpartition('}')[-1] == tag), None)
                    if parent is None:
                        print(f"[urdf.sensors] {name!r}: no <{tag}> element for {path!r}", file=sys.stderr)
                        break
                if parent is not None:
                    _set_child(parent, leaf, value)

    for missing in by_name.keys() - seen:
        print(f"[urdf.sensors] patches for sensor {missing!r} but the URDF has none", file=sys.stderr)


def _strip_sensors(root: ET.Element, tokens: set[str]) -> None:
    disabled_types: set[str] = set()
    unknown: set[str] = set()
    for tok in tokens:
        m = _OPTIM_MAP.get(tok)
        if m is None:
            unknown.add(tok)
        else:
            disabled_types |= m
    if unknown:
        print(f"[urdf.optim] ignoring unknown token(s): {sorted(unknown)}", file=sys.stderr)
    if not disabled_types:
        return
    for parent in root.iter():
        for child in list(parent):
            if child.tag.rpartition('}')[-1] == 'sensor' and child.attrib.get('type') in disabled_types:
                parent.remove(child)


def _ensure_effort_state(root: ET.Element) -> None:
    for control in root.iter():
        if control.tag.rpartition('}')[-1] != 'ros2_control':
            continue
        for joint in control:
            if joint.tag.rpartition('}')[-1] != 'joint':
                continue
            has_effort = any(child.tag.rpartition('}')[-1] == 'state_interface' and child.attrib.get('name') == 'effort' for child in joint)
            if not has_effort:
                ET.SubElement(joint, 'state_interface', {'name': 'effort'})


class ModelProvider_URDF(ModelProvider.provides(ModelType.URDF)):
    @classmethod
    async def load(cls, model_dir: Path, model: str, loader_args: dict | None) -> Model:

        loader_args = dict(loader_args) if loader_args else {}
        optim_raw = loader_args.pop('optim', '') or ''
        optim_tokens: set[str] = {t.strip() for t in optim_raw.split(',') if t.strip()}
        sensor_patches = loader_args.pop('sensor_patches', None) or []

        base_path = model_dir / "urdf"
        xacro_path = base_path / f"{model}.urdf.xacro"
        model_path = base_path / f"{model}.urdf"

        if not xacro_path.is_file():
            raise FileNotFoundError(f"Xacro file for model {model} not found at {xacro_path}")

        def to_string(v: object) -> str:
            if attrs.has(type(v)):
                v = attrs.asdict(v)
            if isinstance(v, dict):
                return json.dumps(v)
            return str(v)

        cmd = [
            "ros2",
            "run",
            "xacro",
            "xacro",
            str(xacro_path),
            *(f"{k}:={to_string(v)}" for k, v in loader_args.items() if v is not None),
        ]

        try:
            process = await asyncio.subprocess.create_subprocess_exec(*cmd, stdout=asyncio.subprocess.PIPE, stderr=asyncio.subprocess.PIPE)
            stdout, stderr = await process.communicate()
            if process.returncode != 0:
                raise subprocess.CalledProcessError(process.returncode or -1, cmd, output=stdout + stderr)
            model_desc = stdout.decode("utf-8")

            async with aiofiles.open(model_path, 'w') as f:
                await f.write(model_desc)

            base_dir = os.path.dirname(model_path)
            tree = ET.parse(model_path)
            root = tree.getroot()

            for elem in root.iter():
                if 'filename' not in elem.attrib:
                    continue
                if elem.tag.rpartition('}')[-1] == 'plugin':
                    continue
                original_path = elem.attrib['filename']

                if original_path.startswith(_PACKAGE_URI):
                    pkg, _, sub = original_path[len(_PACKAGE_URI) :].partition('/')
                    abs_path: str | None = None
                    try:
                        from ament_index_python.packages import PackageNotFoundError, get_package_share_directory
                    except ModuleNotFoundError:
                        pass
                    else:
                        try:
                            abs_path = os.path.join(get_package_share_directory(pkg), sub)
                        except PackageNotFoundError:
                            pass
                    if abs_path is None:
                        abs_path = os.path.abspath(os.path.join(base_dir, sub))
                    elem.attrib['filename'] = f"file://{abs_path}"
                    print(f"Resolved {original_path} -> file://{abs_path}")
                    continue

                if original_path.startswith("file://"):
                    continue

                if not os.path.isabs(original_path):
                    abs_path = os.path.abspath(os.path.join(base_dir, original_path))
                    elem.attrib['filename'] = f"file://{abs_path}"
                    print(f"Updated relative path to absolute: {original_path} -> file://{abs_path}")
                    continue

                elem.attrib['filename'] = f"file://{original_path}"

            if sensor_patches:
                _apply_sensor_patches(root, sensor_patches)

            if optim_tokens:
                _strip_sensors(root, optim_tokens)

            _ensure_effort_state(root)

            ser = ET.tostring(root, encoding="utf-8", method="xml", xml_declaration=True)
            async with aiofiles.tempfile.NamedTemporaryFile(delete=False, suffix=".urdf", mode="wb") as tmp:
                await tmp.write(ser)
                print(f"Converted URDF saved to temporary file: {tmp.name}")

            return Model(type=ModelType.URDF, name=model, description=ser.decode("utf-8"), path=Path(tmp.name))

        except subprocess.CalledProcessError as e:
            print(f"error processing model {model} URDF file {xacro_path}. refusing to load.\n{e}\n{e.output.decode('utf-8')}", file=sys.stderr)
            print(f"Command executed: {' '.join(cmd)}", file=sys.stderr)
            raise
