"""
rigged_glb_builder.py: Converts MakeHuman Collada (.dae) assets with clips into
clean, native, industry-standard Rigged glTF 2.0 (.glb) binaries.

Produces 1 Mesh + 1 Armature + Actions ("Walk", "Idle") with:
- Native GPU skinning in Blender C++
- Preserved split normals (smooth skin shading, no faceted seams)
- Correct Alpha MASK / BLEND for hair, eyebrows, eyelashes
- Centered, in-place locomotion cycles
"""
from __future__ import annotations

import io
import json
import logging
import os
import struct
from pathlib import Path
from typing import Any

import collada
import numpy as np
from PIL import Image, ImageFile
import trimesh.transformations as tf

from arena_blender_viz.model_converter import (
    _COLLADA_NS,
    _clip_sample_index,
    _compose_chain,
    _dae_root,
    _dae_source_arrays,
    _read_clip_channels,
    _read_scene_joint_transforms,
    _read_skin_controller,
    _root_joint_horizontal_pin,
    _split_floats,
)

ImageFile.LOAD_TRUNCATED_IMAGES = True
logger = logging.getLogger(__name__)

# Coordinate change from Collada (Z-up) to glTF 2.0 (Y-up):
# X_gltf = X_col
# Y_gltf = Z_col
# Z_gltf = -Y_col
_C_ZUP_TO_YUP = np.array([
    [1.0,  0.0,  0.0, 0.0],
    [0.0,  0.0,  1.0, 0.0],
    [0.0, -1.0,  0.0, 0.0],
    [0.0,  0.0,  0.0, 1.0],
], dtype=np.float64)

_C_INV = np.linalg.inv(_C_ZUP_TO_YUP)


class GlbBufferBuilder:
    def __init__(self):
        self.buffer = bytearray()
        self.buffer_views: list[dict[str, Any]] = []
        self.accessors: list[dict[str, Any]] = []

    def add_raw_chunk(self, data: bytes, alignment: int = 4) -> int:
        while len(self.buffer) % alignment != 0:
            self.buffer.append(0)
        offset = len(self.buffer)
        self.buffer.extend(data)
        return offset

    def add_buffer_view(self, data: bytes, target: int | None = None, alignment: int = 4) -> int:
        offset = self.add_raw_chunk(data, alignment)
        bv_idx = len(self.buffer_views)
        bv = {
            "buffer": 0,
            "byteOffset": offset,
            "byteLength": len(data),
        }
        if target is not None:
            bv["target"] = target
        self.buffer_views.append(bv)
        return bv_idx

    def add_accessor(
        self,
        buffer_view_idx: int,
        component_type: int,
        count: int,
        type_str: str,
        min_val: list[float] | None = None,
        max_val: list[float] | None = None,
        byte_offset: int = 0,
    ) -> int:
        acc_idx = len(self.accessors)
        acc: dict[str, Any] = {
            "bufferView": buffer_view_idx,
            "byteOffset": byte_offset,
            "componentType": component_type,
            "count": count,
            "type": type_str,
        }
        if min_val is not None:
            acc["min"] = min_val
        if max_val is not None:
            acc["max"] = max_val
        self.accessors.append(acc)
        return acc_idx


def convert_human_to_rigged_glb(
    asset_dir: Path,
    out_glb_path: Path,
    walk_clip_path: Path | None = None,
    idle_clip_path: Path | None = None,
) -> bool:
    leaf = asset_dir.name
    dae_candidates = [
        asset_dir / "meshes" / f"{leaf}.dae",
        asset_dir / "meshes" / "arenian.dae",
        asset_dir / f"{leaf}.dae",
    ]
    for p in (asset_dir / "meshes").glob("*.dae"):
        if p not in dae_candidates:
            dae_candidates.append(p)

    mesh_dae = next((p for p in dae_candidates if p.is_file()), None)
    if mesh_dae is None:
        logger.error(f"No Collada mesh found in {asset_dir}")
        return False

    if walk_clip_path is None:
        walk_clip_path = asset_dir / "clips" / "walk.dae"
    if idle_clip_path is None:
        idle_clip_path = asset_dir / "clips" / "idle.dae"

    col = collada.Collada(str(mesh_dae))
    if not col.geometries:
        logger.error(f"No geometries found in {mesh_dae}")
        return False

    geom = col.geometries[0]
    skin = _read_skin_controller(mesh_dae)
    if skin is None:
        logger.error(f"No skin controller found in {mesh_dae}")
        return False

    tree = _read_scene_joint_transforms(mesh_dae)
    joint_names: list[str] = skin["joint_names"]
    n_joints = len(joint_names)
    joint_to_idx = {name: i for i, name in enumerate(joint_names)}

    # Read skeleton hierarchy from Collada visual_scene
    root_el = _dae_root(mesh_dae)
    joint_parents: dict[str, str | None] = {}
    joint_children: dict[str, list[str]] = {name: [] for name in joint_names}

    def find_skeleton_joints(node_el, p_sid: str | None):
        sid = node_el.get("sid") or node_el.get("id")
        cur_p = p_sid
        if sid in joint_to_idx:
            joint_parents[sid] = p_sid
            if p_sid and p_sid in joint_children:
                joint_children[p_sid].append(sid)
            cur_p = sid
        for ch in node_el.findall(_COLLADA_NS + "node"):
            find_skeleton_joints(ch, cur_p)

    for vs in root_el.iter(_COLLADA_NS + "visual_scene"):
        for n in vs.findall(_COLLADA_NS + "node"):
            find_skeleton_joints(n, None)

    # Compute rest local transforms conjugated to glTF frame
    local_rest_mats_gltf: list[np.ndarray] = []
    rest_translations: list[list[float]] = []
    rest_rotations: list[list[float]] = []  # [x, y, z, w]

    for jname in joint_names:
        _, lm_list = tree[jname]
        m_col = np.eye(4)
        for lm in lm_list:
            m_col = m_col @ lm
        m_gltf = _C_ZUP_TO_YUP @ m_col @ _C_INV
        local_rest_mats_gltf.append(m_gltf)
        t = m_gltf[:3, 3].tolist()
        q = tf.quaternion_from_matrix(m_gltf)  # [w, x, y, z]
        rest_translations.append([float(x) for x in t])
        rest_rotations.append([float(q[1]), float(q[2]), float(q[3]), float(q[0])])

    # Convert inverse bind matrices to glTF coordinate frame
    inv_bind_gltf_bytes = bytearray()
    for j_idx in range(n_joints):
        ibm_col = skin["inv_bind"][j_idx]
        ibm_gltf = _C_ZUP_TO_YUP @ ibm_col @ _C_INV
        inv_bind_gltf_bytes.extend(ibm_gltf.astype(np.float32).tobytes())

    # Build buffer builder
    builder = GlbBufferBuilder()

    # Inverse bind matrices accessor
    bv_ibm = builder.add_buffer_view(bytes(inv_bind_gltf_bytes))
    acc_ibm = builder.add_accessor(bv_ibm, 5126, n_joints, "MAT4")

    # Textures and Materials
    tex_dir = mesh_dae.parent / "textures"
    images_dict: dict[str, Path] = {}
    if tex_dir.is_dir():
        for img_p in tex_dir.glob("*.*"):
            if img_p.suffix.lower() in [".png", ".jpg", ".jpeg", ".tga"]:
                images_dict[img_p.stem.lower()] = img_p

    materials_list: list[dict[str, Any]] = []
    textures_list: list[dict[str, Any]] = []
    images_list: list[dict[str, Any]] = []
    samplers_list: list[dict[str, Any]] = [
        {"magFilter": 9729, "minFilter": 9987, "wrapS": 10497, "wrapT": 10497}
    ]
    mat_id_to_gltf_idx: dict[str, int] = {}
    cached_image_idx: dict[str, int] = {}

    def get_or_create_material(mat_id: str) -> int:
        if mat_id in mat_id_to_gltf_idx:
            return mat_id_to_gltf_idx[mat_id]

        clean_name = mat_id.lower().replace("material", "").replace(".", "").replace("_", "")
        best_img_path = None

        for k, p in images_dict.items():
            ck = k.replace("_", "").replace(".", "")
            if ck in clean_name or clean_name in ck:
                best_img_path = p
                break

        if not best_img_path:
            for k, p in images_dict.items():
                if "diffuse" in k:
                    best_img_path = p
                    break

        mat_dict: dict[str, Any] = {
            "name": mat_id,
            "pbrMetallicRoughness": {
                "roughnessFactor": 0.6,
                "metallicFactor": 0.0,
            },
        }

        is_transparent = any(w in clean_name for w in ["hair", "eyebrow", "eyelash", "long01", "short04", "teeth"])

        if best_img_path and best_img_path.is_file():
            img_key = str(best_img_path.resolve())
            if img_key not in cached_image_idx:
                try:
                    with Image.open(best_img_path) as im:
                        if im.mode in ("RGBA", "LA") or (im.mode == "P" and "transparency" in im.info):
                            is_transparent = True
                        out_buf = io.BytesIO()
                        im.save(out_buf, format="PNG")
                        png_bytes = out_buf.getvalue()
                except Exception:
                    png_bytes = best_img_path.read_bytes()

                bv_img = builder.add_buffer_view(png_bytes)
                img_idx = len(images_list)
                images_list.append({"bufferView": bv_img, "mimeType": "image/png"})
                tex_idx = len(textures_list)
                textures_list.append({"sampler": 0, "source": img_idx})
                cached_image_idx[img_key] = tex_idx

            tex_index = cached_image_idx[img_key]
            mat_dict["pbrMetallicRoughness"]["baseColorTexture"] = {"index": tex_index}

        if is_transparent:
            mat_dict["alphaMode"] = "MASK"
            mat_dict["alphaCutoff"] = 0.5
            mat_dict["doubleSided"] = True

        idx = len(materials_list)
        materials_list.append(mat_dict)
        mat_id_to_gltf_idx[mat_id] = idx
        return idx

    # Build Primitives
    primitives_list: list[dict[str, Any]] = []
    shared_influences = skin["influences"]

    for prim in geom.primitives:
        ts = prim.triangleset()
        flat_v = ts.vertex_index.reshape(-1)
        n_verts = len(flat_v)
        if n_verts == 0:
            continue

        raw_pos = ts.vertex[flat_v]
        pos_gltf = np.empty_like(raw_pos, dtype=np.float32)
        pos_gltf[:, 0] = raw_pos[:, 0]
        pos_gltf[:, 1] = raw_pos[:, 2]
        pos_gltf[:, 2] = -raw_pos[:, 1]
        # Normals (split normals preserved from Collada)
        if ts.normal is not None and ts.normal_index is not None and len(ts.normal) > 0:
            raw_nor = ts.normal[ts.normal_index.reshape(-1)]
            nor_gltf = np.empty_like(raw_nor, dtype=np.float32)
            nor_gltf[:, 0] = raw_nor[:, 0]
            nor_gltf[:, 1] = raw_nor[:, 2]
            nor_gltf[:, 2] = -raw_nor[:, 1]
        else:
            nor_gltf = np.zeros_like(pos_gltf, dtype=np.float32)

        if len(ts.texcoordset) > 0 and len(ts.texcoord_indexset) > 0:
            raw_uv = ts.texcoordset[0][ts.texcoord_indexset[0].reshape(-1)]
            uv_gltf = raw_uv.astype(np.float32).copy()
            uv_gltf[:, 1] = 1.0 - uv_gltf[:, 1]
        else:
            uv_gltf = np.zeros((n_verts, 2), dtype=np.float32)

        joints_arr = np.zeros((n_verts, 4), dtype=np.uint16)
        weights_arr = np.zeros((n_verts, 4), dtype=np.float32)

        for i, shared_idx in enumerate(flat_v):
            infs = shared_influences[int(shared_idx)]
            total_w = sum(w for _, w in infs) or 1.0
            for k in range(min(4, len(infs))):
                joints_arr[i, k] = int(infs[k][0])
                weights_arr[i, k] = float(infs[k][1]) / total_w

        indices_arr = np.arange(n_verts, dtype=np.uint32)

        bv_pos = builder.add_buffer_view(pos_gltf.tobytes(), target=34962)
        bv_nor = builder.add_buffer_view(nor_gltf.tobytes(), target=34962)
        bv_uv = builder.add_buffer_view(uv_gltf.tobytes(), target=34962)
        bv_j = builder.add_buffer_view(joints_arr.tobytes(), target=34962)
        bv_w = builder.add_buffer_view(weights_arr.tobytes(), target=34962)
        bv_idx = builder.add_buffer_view(indices_arr.tobytes(), target=34963)

        min_pos = [float(x) for x in pos_gltf.min(axis=0)]
        max_pos = [float(x) for x in pos_gltf.max(axis=0)]

        acc_pos = builder.add_accessor(bv_pos, 5126, n_verts, "VEC3", min_val=min_pos, max_val=max_pos)
        acc_nor = builder.add_accessor(bv_nor, 5126, n_verts, "VEC3")
        acc_uv = builder.add_accessor(bv_uv, 5126, n_verts, "VEC2")
        acc_j = builder.add_accessor(bv_j, 5123, n_verts, "VEC4")
        acc_w = builder.add_accessor(bv_w, 5126, n_verts, "VEC4")
        acc_idx = builder.add_accessor(bv_idx, 5125, n_verts, "SCALAR", min_val=[0], max_val=[n_verts - 1])

        mat_idx = get_or_create_material(prim.material or "default")

        primitives_list.append({
            "attributes": {
                "POSITION": acc_pos,
                "NORMAL": acc_nor,
                "TEXCOORD_0": acc_uv,
                "JOINTS_0": acc_j,
                "WEIGHTS_0": acc_w,
            },
            "indices": acc_idx,
            "material": mat_idx,
        })

    # Nodes
    armature_node_idx = 0
    bone_start_node_idx = 1
    mesh_node_idx = 1 + n_joints

    nodes_list: list[dict[str, Any]] = []

    root_bones = [name for name in joint_names if joint_parents.get(name) is None]
    root_bone_node_indices = [bone_start_node_idx + joint_to_idx[r] for r in root_bones]

    nodes_list.append({
        "name": "Armature",
        "children": root_bone_node_indices,
    })

    for j_idx, jname in enumerate(joint_names):
        ch_names = joint_children.get(jname, [])
        ch_indices = [bone_start_node_idx + joint_to_idx[cn] for cn in ch_names if cn in joint_to_idx]

        b_node: dict[str, Any] = {
            "name": jname,
            "translation": rest_translations[j_idx],
            "rotation": rest_rotations[j_idx],
        }
        if ch_indices:
            b_node["children"] = ch_indices
        nodes_list.append(b_node)

    nodes_list.append({
        "name": f"Mesh_{leaf}",
        "mesh": 0,
        "skin": 0,
    })

    # Animations (Walk, Idle)
    animations_list: list[dict[str, Any]] = []

    def build_animation(clip_path: Path, anim_name: str) -> dict[str, Any] | None:
        if not clip_path.is_file():
            return None
        channels = _read_clip_channels(clip_path)
        if not channels:
            return None

        pin_joint = _root_joint_horizontal_pin(channels, joint_names)

        anim_channels: list[dict[str, Any]] = []
        anim_samplers: list[dict[str, Any]] = []

        for j_idx, jname in enumerate(joint_names):
            if jname not in channels:
                continue
            times, mats = channels[jname]
            n_keys = len(times)
            if n_keys == 0:
                continue

            node_idx = bone_start_node_idx + j_idx

            times_arr = times.astype(np.float32)
            trans_arr = np.zeros((n_keys, 3), dtype=np.float32)
            rot_arr = np.zeros((n_keys, 4), dtype=np.float32)

            rest_t = rest_translations[j_idx]

            for k in range(n_keys):
                mk = mats[k]
                mk_gltf = _C_ZUP_TO_YUP @ mk @ _C_INV
                t_k = mk_gltf[:3, 3]

                if jname == pin_joint:
                    t_k[0] = rest_t[0]
                    t_k[2] = rest_t[2]

                trans_arr[k] = t_k
                q_k = tf.quaternion_from_matrix(mk_gltf)
                rot_arr[k] = [float(q_k[1]), float(q_k[2]), float(q_k[3]), float(q_k[0])]

            bv_time = builder.add_buffer_view(times_arr.tobytes())
            acc_time = builder.add_accessor(
                bv_time, 5126, n_keys, "SCALAR", min_val=[float(times_arr[0])], max_val=[float(times_arr[-1])]
            )

            bv_t = builder.add_buffer_view(trans_arr.tobytes())
            acc_t = builder.add_accessor(bv_t, 5126, n_keys, "VEC3")

            smp_t_idx = len(anim_samplers)
            anim_samplers.append({
                "input": acc_time,
                "interpolation": "LINEAR",
                "output": acc_t,
            })
            anim_channels.append({
                "sampler": smp_t_idx,
                "target": {"node": node_idx, "path": "translation"},
            })

            bv_r = builder.add_buffer_view(rot_arr.tobytes())
            acc_r = builder.add_accessor(bv_r, 5126, n_keys, "VEC4")

            smp_r_idx = len(anim_samplers)
            anim_samplers.append({
                "input": acc_time,
                "interpolation": "LINEAR",
                "output": acc_r,
            })
            anim_channels.append({
                "sampler": smp_r_idx,
                "target": {"node": node_idx, "path": "rotation"},
            })

        return {
            "name": anim_name,
            "channels": anim_channels,
            "samplers": anim_samplers,
        }

    walk_anim = build_animation(walk_clip_path, "Walk")
    if walk_anim:
        animations_list.append(walk_anim)

    idle_anim = build_animation(idle_clip_path, "Idle")
    if idle_anim:
        animations_list.append(idle_anim)

    gltf_json: dict[str, Any] = {
        "asset": {
            "version": "2.0",
            "generator": "Arena Rigged glTF 2.0 Exporter",
        },
        "scene": 0,
        "scenes": [
            {
                "name": "Scene",
                "nodes": [armature_node_idx, mesh_node_idx],
            }
        ],
        "nodes": nodes_list,
        "skins": [
            {
                "name": f"Armature_{leaf}",
                "inverseBindMatrices": acc_ibm,
                "joints": [bone_start_node_idx + i for i in range(n_joints)],
                "skeleton": armature_node_idx,
            }
        ],
        "meshes": [
            {
                "name": f"Mesh_{leaf}",
                "primitives": primitives_list,
            }
        ],
        "materials": materials_list,
        "textures": textures_list,
        "images": images_list,
        "samplers": samplers_list,
        "accessors": builder.accessors,
        "bufferViews": builder.buffer_views,
        "buffers": [{"byteLength": len(builder.buffer)}],
    }

    if animations_list:
        gltf_json["animations"] = animations_list

    json_bytes = json.dumps(gltf_json, separators=(",", ":")).encode("utf-8")
    while len(json_bytes) % 4 != 0:
        json_bytes += b" "
    while len(builder.buffer) % 4 != 0:
        builder.buffer.append(0)

    total_len = 12 + 8 + len(json_bytes) + 8 + len(builder.buffer)
    header = struct.pack("<III", 0x46546C67, 2, total_len)
    chunk0 = struct.pack("<II", len(json_bytes), 0x4E4F534A) + json_bytes
    chunk1 = struct.pack("<II", len(builder.buffer), 0x004E4942) + bytes(builder.buffer)

    out_glb_path.parent.mkdir(parents=True, exist_ok=True)
    out_glb_path.write_bytes(header + chunk0 + chunk1)
    logger.info(f"Built rigged glTF: {out_glb_path.name} ({out_glb_path.stat().st_size / 1024:.1f} KB)")
    return True
