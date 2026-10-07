"""Rewrite zone corner coordinates in a level world.yaml, leaving every other byte untouched."""

import os
import tempfile
from collections.abc import Mapping, Sequence
from pathlib import Path

import yaml

_PRECISION = 4


def _mapping_value(node: yaml.MappingNode, key: str) -> yaml.Node | None:
    return next((v for k, v in node.value if isinstance(k, yaml.ScalarNode) and k.value == key), None)


def _coordinate_nodes(corner: yaml.Node) -> tuple[yaml.Node | None, yaml.Node | None]:
    if isinstance(corner, yaml.SequenceNode) and len(corner.value) >= 2:
        return corner.value[0], corner.value[1]
    if isinstance(corner, yaml.MappingNode):
        return _mapping_value(corner, "x"), _mapping_value(corner, "y")
    raise ValueError("corner must be a sequence of 2-3 numbers or an x/y mapping")


def write_zone_corners(world_yaml: Path, corners: Mapping[str, Sequence[tuple[float, float]]]) -> int:
    """Set the x and y of the named zones' corners, rewriting only the number tokens that differ. Returns the count changed."""
    text = world_yaml.read_bytes().decode("utf-8")
    root = yaml.compose(text)
    if not isinstance(root, yaml.MappingNode):
        raise ValueError(f"{world_yaml} is not a mapping")
    zones = _mapping_value(root, "zones")
    if not isinstance(zones, yaml.SequenceNode):
        raise ValueError(f"{world_yaml} has no zones list")

    by_name: dict[str, yaml.MappingNode] = {}
    for zone in zones.value:
        if not isinstance(zone, yaml.MappingNode):
            continue
        name = _mapping_value(zone, "name")
        if isinstance(name, yaml.ScalarNode):
            if name.value in by_name:
                raise ValueError(f"{world_yaml} has duplicate zone {name.value!r}")
            by_name[name.value] = zone

    splices: list[tuple[int, int, str]] = []
    for name, points in corners.items():
        zone = by_name.get(name)
        if zone is None:
            raise ValueError(f"{world_yaml} has no zone {name!r}")
        nodes = _mapping_value(zone, "corners")
        if not isinstance(nodes, yaml.SequenceNode) or len(nodes.value) != len(points):
            raise ValueError(f"zone {name!r} in {world_yaml} does not have {len(points)} corners")
        for corner, point in zip(nodes.value, points, strict=True):
            for target, coordinate in zip(_coordinate_nodes(corner), point, strict=True):
                if not isinstance(target, yaml.ScalarNode):
                    raise ValueError(f"zone {name!r} in {world_yaml} has a corner coordinate that is not a number")
                if abs(float(target.value) - coordinate) > 10 ** -(_PRECISION + 1):
                    splices.append((target.start_mark.index, target.end_mark.index, repr(round(coordinate, _PRECISION))))

    for start, end, token in sorted(splices, reverse=True):
        text = text[:start] + token + text[end:]
    if splices:
        fd, tmp = tempfile.mkstemp(dir=world_yaml.parent, prefix=".world.", suffix=".tmp")
        try:
            with os.fdopen(fd, "wb") as f:
                f.write(text.encode("utf-8"))
            os.chmod(tmp, world_yaml.stat().st_mode)
            os.replace(tmp, world_yaml)
        except BaseException:
            os.unlink(tmp)
            raise
    return len(splices)
