"""
world_parser.py: Standalone parser for Arena simulation world.yaml files.
Independent of ROS 2 and cattrs to ensure zero-dependency execution.
"""
from __future__ import annotations

import math
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

import yaml


@dataclass
class Vec3:
    x: float
    y: float
    z: float = 0.0

    @classmethod
    def from_any(cls, data: Any) -> Vec3:
        if isinstance(data, (list, tuple)):
            if len(data) == 2:
                return cls(float(data[0]), float(data[1]), 0.0)
            return cls(float(data[0]), float(data[1]), float(data[2]))
        if isinstance(data, dict):
            return cls(
                float(data.get("x", 0.0)),
                float(data.get("y", 0.0)),
                float(data.get("z", 0.0)),
            )
        raise ValueError(f"Cannot parse Vec3 from {data!r}")

    def to_dict(self) -> dict[str, float]:
        return {"x": self.x, "y": self.y, "z": self.z}


@dataclass
class Quaternion:
    w: float = 1.0
    x: float = 0.0
    y: float = 0.0
    z: float = 0.0

    @classmethod
    def from_any(cls, data: Any) -> Quaternion:
        if isinstance(data, (int, float)):
            # Treat as yaw in radians
            yaw = float(data)
            return cls(
                w=math.cos(yaw / 2.0),
                x=0.0,
                y=0.0,
                z=math.sin(yaw / 2.0),
            )
        if isinstance(data, (list, tuple)):
            if len(data) == 4:
                return cls(float(data[0]), float(data[1]), float(data[2]), float(data[3]))
            if len(data) == 3:
                # Roll, pitch, yaw
                r, p, y = float(data[0]), float(data[1]), float(data[2])
                cy = math.cos(y * 0.5)
                sy = math.sin(y * 0.5)
                cp = math.cos(p * 0.5)
                sp = math.sin(p * 0.5)
                cr = math.cos(r * 0.5)
                sr = math.sin(r * 0.5)
                return cls(
                    w=cr * cp * cy + sr * sp * sy,
                    x=sr * cp * cy - cr * sp * sy,
                    y=cr * sp * cy + sr * cp * sy,
                    z=cr * cp * sy - sr * sp * cy,
                )
        if isinstance(data, dict):
            return cls(
                w=float(data.get("w", 1.0)),
                x=float(data.get("x", 0.0)),
                y=float(data.get("y", 0.0)),
                z=float(data.get("z", 0.0)),
            )
        return cls()

    def to_dict(self) -> dict[str, float]:
        return {"w": self.w, "x": self.x, "y": self.y, "z": self.z}

    def to_yaw(self) -> float:
        siny_cosp = 2.0 * (self.w * self.z + self.x * self.y)
        cosy_cosp = 1.0 - 2.0 * (self.y * self.y + self.z * self.z)
        return math.atan2(siny_cosp, cosy_cosp)


@dataclass
class WallDef:
    start: Vec3
    end: Vec3
    material_name: str = "Plaster_Wall"
    height: float = 2.0
    width: float = 0.05

    def to_dict(self) -> dict[str, Any]:
        return {
            "start": self.start.to_dict(),
            "end": self.end.to_dict(),
            "material": self.material_name,
            "height": self.height,
            "width": self.width,
        }


@dataclass
class DoorDef:
    name: str
    start: Vec3
    end: Vec3
    kind: str = "sliding"
    width: float = 0.1
    height: float = 2.0
    material_name: str = "Aluminum_Anodized"
    activation_distance: tuple[float, float] = (1.2, 1.2)
    transition_time: float = 1.0
    hold_time: float = 2.0

    def to_dict(self) -> dict[str, Any]:
        return {
            "name": self.name,
            "start": self.start.to_dict(),
            "end": self.end.to_dict(),
            "kind": self.kind,
            "width": self.width,
            "height": self.height,
            "material": self.material_name,
            "activation_distance": list(self.activation_distance),
            "transition_time": self.transition_time,
            "hold_time": self.hold_time,
        }


@dataclass
class EntityDef:
    name: str
    model_id: str
    position: Vec3
    orientation: Quaternion
    scale: Vec3 = field(default_factory=lambda: Vec3(1.0, 1.0, 1.0))

    def to_dict(self) -> dict[str, Any]:
        return {
            "name": self.name,
            "model_id": self.model_id,
            "position": self.position.to_dict(),
            "orientation": self.orientation.to_dict(),
            "scale": self.scale.to_dict(),
        }


@dataclass
class ZoneDef:
    name: str
    description: str
    floor_material: str
    corners: list[Vec3]
    walls: list[WallDef]
    doors: list[DoorDef]
    static_entities: list[EntityDef]
    dynamic_entities: list[EntityDef]
    ceiling_height: float = 2.5
    semantics: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        return {
            "name": self.name,
            "description": self.description,
            "floor_material": self.floor_material,
            "corners": [c.to_dict() for c in self.corners],
            "walls": [w.to_dict() for w in self.walls],
            "doors": [d.to_dict() for d in self.doors],
            "static_entities": [e.to_dict() for e in self.static_entities],
            "dynamic_entities": [e.to_dict() for e in self.dynamic_entities],
            "ceiling_height": self.ceiling_height,
            "semantics": self.semantics,
        }


@dataclass
class WorldDef:
    zones: list[ZoneDef]
    bounds: tuple[float, float, float, float]  # min_x, min_y, max_x, max_y

    def to_dict(self) -> dict[str, Any]:
        return {
            "zones": [z.to_dict() for z in self.zones],
            "bounds": list(self.bounds),
        }


def _parse_material_name(mat_raw: Any, default: str = "Concrete_Smooth") -> str:
    if isinstance(mat_raw, str):
        return mat_raw
    if isinstance(mat_raw, list) and len(mat_raw) > 0:
        return str(mat_raw[0])
    if isinstance(mat_raw, dict):
        return str(mat_raw.get("name", default))
    return default


def parse_world_yaml(yaml_path: Path) -> WorldDef:
    """Parse an Arena world.yaml into typed WorldDef dataclass."""
    with open(yaml_path, "r", encoding="utf-8") as f:
        data = yaml.safe_load(f)

    if not isinstance(data, dict):
        raise ValueError(f"Invalid world YAML root at {yaml_path}")

    raw_zones = data.get("zones", [])
    zones: list[ZoneDef] = []

    all_x: list[float] = []
    all_y: list[float] = []

    for z_raw in raw_zones:
        z_name = str(z_raw.get("name", "unnamed_zone"))
        z_desc = str(z_raw.get("description", ""))
        z_floor_mat = _parse_material_name(z_raw.get("material"), "Concrete_Smooth")

        # Corners
        corners: list[Vec3] = []
        for c in z_raw.get("corners", []):
            v = Vec3.from_any(c)
            corners.append(v)
            all_x.append(v.x)
            all_y.append(v.y)

        # Walls
        walls: list[WallDef] = []
        for w in z_raw.get("walls", []):
            start = Vec3.from_any(w.get("start", {}))
            end = Vec3.from_any(w.get("end", {}))
            mat_name = _parse_material_name(w.get("material"), "Plaster_Wall")
            walls.append(WallDef(start=start, end=end, material_name=mat_name))
            all_x.extend([start.x, end.x])
            all_y.extend([start.y, end.y])

        # Doors
        doors: list[DoorDef] = []
        for d in z_raw.get("doors", []):
            d_name = str(d.get("name", f"{z_name}_door_{len(doors)}"))
            start = Vec3.from_any(d.get("start", {}))
            end = Vec3.from_any(d.get("end", {}))
            kind = str(d.get("kind", "sliding"))
            width = float(d.get("width", 0.1))
            height = float(d.get("height", 2.0))
            mat_name = _parse_material_name(d.get("material"), "Aluminum_Anodized")
            act_dist_raw = d.get("activation_distance", [1.2, 1.2])
            if isinstance(act_dist_raw, (int, float)):
                act_dist = (float(act_dist_raw), float(act_dist_raw))
            else:
                act_dist = (float(act_dist_raw[0]), float(act_dist_raw[1]))
            doors.append(
                DoorDef(
                    name=d_name,
                    start=start,
                    end=end,
                    kind=kind,
                    width=width,
                    height=height,
                    material_name=mat_name,
                    activation_distance=act_dist,
                    transition_time=float(d.get("transition_time", 1.0)),
                    hold_time=float(d.get("hold_time", 2.0)),
                )
            )

        # Entities
        entities_block = z_raw.get("entities", {})
        static_entities: list[EntityDef] = []
        for s in entities_block.get("static", []):
            e_name = str(s.get("name", "entity"))
            model_id = str(s.get("model", ""))
            pose_dict = s.get("pose", {})
            pos = Vec3.from_any(pose_dict.get("position", {}))
            orient = Quaternion.from_any(pose_dict.get("orientation", {}))
            scale = Vec3.from_any(s.get("scale", [1.0, 1.0, 1.0]))
            static_entities.append(
                EntityDef(
                    name=e_name,
                    model_id=model_id,
                    position=pos,
                    orientation=orient,
                    scale=scale,
                )
            )

        dynamic_entities: list[EntityDef] = []
        for dy in entities_block.get("dynamic", []):
            e_name = str(dy.get("name", "actor"))
            model_id = str(dy.get("model", ""))
            pose_dict = dy.get("pose", {})
            pos = Vec3.from_any(pose_dict.get("position", {}))
            orient = Quaternion.from_any(pose_dict.get("orientation", {}))
            dynamic_entities.append(
                EntityDef(
                    name=e_name,
                    model_id=model_id,
                    position=pos,
                    orientation=orient,
                )
            )

        # Semantics
        semantics: dict[str, Any] = {}
        for sem in z_raw.get("semantics", []):
            if isinstance(sem, dict) and "state" in sem:
                semantics[sem["state"]] = sem.get("value", True)

        ceiling_h = float(z_raw.get("ceiling_height", 2.5) or 2.5)

        zones.append(
            ZoneDef(
                name=z_name,
                description=z_desc,
                floor_material=z_floor_mat,
                corners=corners,
                walls=walls,
                doors=doors,
                static_entities=static_entities,
                dynamic_entities=dynamic_entities,
                ceiling_height=ceiling_h,
                semantics=semantics,
            )
        )

    min_x = min(all_x) if all_x else 0.0
    min_y = min(all_y) if all_y else 0.0
    max_x = max(all_x) if all_x else 50.0
    max_y = max(all_y) if all_y else 50.0

    return WorldDef(zones=zones, bounds=(min_x, min_y, max_x, max_y))
