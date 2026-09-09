"""
model_converter.py: Resolves Arena model assets and caches them as GLB meshes.
Converts Collada (.dae) models with textures into fast-loading glTF/GLB binaries.

Skinned human models ("arenian" & co.) keep their character pose in animation
*clips* (e.g. ``arenian_seated/clips/sitting.dae``) while the skinned mesh DAEs
are bound in a plain standing pose. Converters that only export bind-pose
geometry therefore render seated characters standing. For model folders whose
name contains "seated", the conversion bakes the *last frame* of the idle
sitting clip onto the skinned mesh (gazebo-actor semantics: a clip channel
replaces the joint's node transform), producing a genuinely seated static GLB.
"""
from __future__ import annotations

import logging
import shutil
import xml.etree.ElementTree as ET
from pathlib import Path
from typing import Any

import numpy as np
import trimesh
import yaml

import os

logger = logging.getLogger(__name__)

# Namespace of every COLLADA document this converter handles.
_COLLADA_NS = "{http://www.collada.org/2005/11/COLLADASchema}"
# Bump when the seated pose-bake math changes: seated GLBs carry a matching
# sidecar (<glb>.posever) so stale bind-pose caches regenerate automatically.
_POSE_BAKE_VERSION = 1


def _dae_root(dae_path: Path) -> ET.Element:
    return ET.parse(dae_path).getroot()


def _dae_source_arrays(root: ET.Element) -> dict[str, ET.Element]:
    """Map every <source id> to its first value array element (float/Name/IDREF)."""
    out: dict[str, ET.Element] = {}
    for src in root.iter(_COLLADA_NS + "source"):
        sid = src.get("id")
        if not sid:
            continue
        for tag in ("float_array", "Name_array", "IDREF_array"):
            arr = src.find(_COLLADA_NS + tag)
            if arr is not None:
                out[sid] = arr
                break
    return out


def _split_floats(arr: ET.Element) -> np.ndarray:
    return np.array(arr.text.split(), dtype=float) if arr.text and arr.text.strip() else np.empty(0)


def _read_clip_channels(dae_path: Path) -> dict[str, tuple[np.ndarray, np.ndarray]]:
    """Joint sid -> (times, per-sample 4x4 local matrices) for every clip channel.

    MakeHuman actor clips store one <animation> per joint; channels target
    ``<joint-sid>/transform`` and each OUTPUT float_array row is the joint's
    local transform matrix for one sample (gazebo-actor convention).
    """
    root = _dae_root(dae_path)
    sources = _dae_source_arrays(root)
    samplers: dict[str, dict[str, str]] = {}
    for smp in root.iter(_COLLADA_NS + "sampler"):
        sid = smp.get("id")
        if not sid:
            continue
        inputs = {inp.get("semantic"): inp.get("source", "").lstrip("#") for inp in smp.iter(_COLLADA_NS + "input")}
        samplers[sid] = inputs

    channels: dict[str, tuple[np.ndarray, np.ndarray]] = {}
    for chan in root.iter(_COLLADA_NS + "channel"):
        target = chan.get("target", "")
        src_id = chan.get("source", "").lstrip("#")
        if "/" not in target:
            continue
        joint_sid = target.split("/", 1)[0]
        ins = samplers.get(src_id)
        if not ins:
            continue
        times_arr = sources.get(ins.get("INPUT", ""))
        out_arr = sources.get(ins.get("OUTPUT", ""))
        if times_arr is None or out_arr is None:
            continue
        times = _split_floats(times_arr)
        mats = _split_floats(out_arr)
        if not len(times) or not len(mats):
            continue
        mats = mats.reshape(-1, 4, 4)
        if len(times) != len(mats):
            # Clip trimmed differently than samples; keep a 1:1 usable subset.
            n = min(len(times), len(mats))
            times, mats = times[:n], mats[:n]
        channels[joint_sid] = (times, mats)
    return channels


def _read_skin_controller(dae_path: Path) -> dict[str, Any] | None:
    """Parse the first <controller><skin> of a skinned mesh DAE.

    Returns joint names, inverse-bind world matrices, bind shape matrix and
    per-vertex influence lists, or None when the file carries no skin.
    """
    root = _dae_root(dae_path)
    for ctrl in root.iter(_COLLADA_NS + "controller"):
        skin = ctrl.find(_COLLADA_NS + "skin")
        if skin is None:
            continue
        sources = _dae_source_arrays(root)
        joints: dict[str, str] = {}
        for inp in skin.find(_COLLADA_NS + "joints").findall(_COLLADA_NS + "input"):
            joints[inp.get("semantic", "")] = inp.get("source", "").lstrip("#")

        name_arr = sources.get(joints.get("JOINT", ""))
        ibm_arr = sources.get(joints.get("INV_BIND_MATRIX", ""))
        if name_arr is None or ibm_arr is None:
            return None
        joint_names = name_arr.text.split()
        inv_bind = _split_floats(ibm_arr).reshape(-1, 4, 4)

        bsm = np.eye(4)
        bsm_el = skin.find(_COLLADA_NS + "bind_shape_matrix")
        if bsm_el is not None and bsm_el.text:
            bsm = np.array(bsm_el.text.split(), dtype=float).reshape(4, 4)

        vw = skin.find(_COLLADA_NS + "vertex_weights")
        if vw is None:
            return None
        vw_inputs: dict[str, tuple[int, str]] = {}
        for inp in vw.findall(_COLLADA_NS + "input"):
            vw_inputs[inp.get("semantic", "")] = (int(inp.get("offset", "0")), inp.get("source", "").lstrip("#"))
        joint_off, joint_src = vw_inputs.get("JOINT", (0, ""))
        weight_off, weight_src = vw_inputs.get("WEIGHT", (1, ""))
        joint_list = sources.get(joint_src)
        weight_list = sources.get(weight_src)
        if joint_list is None or weight_list is None:
            return None
        weight_values = _split_floats(weight_list)
        vcounts = np.array(vw.find(_COLLADA_NS + "vcount").text.split(), dtype=int)
        v_pairs = np.array(vw.find(_COLLADA_NS + "v").text.split(), dtype=int)

        # Expand <vcount>/<v> into per-vertex (joint index, weight index) lists.
        influences: list[list[tuple[int, float]]] = []
        cursor = 0
        for n_inf in vcounts:
            infs: list[tuple[int, float]] = []
            for _ in range(int(n_inf)):
                j_idx = int(v_pairs[cursor + joint_off])
                w_idx = int(v_pairs[cursor + weight_off])
                infs.append((j_idx, float(weight_values[w_idx])))
                cursor += 2
            influences.append(infs)

        return {
            "joint_names": joint_names,
            "inv_bind": inv_bind,
            "bind_shape": bsm,
            "influences": influences,
        }
    return None


def _read_scene_joint_transforms(dae_path: Path) -> dict[str, tuple[list[str], list[Any]]]:
    """sid -> (ancestor sids root-first, local transform list) for every joint node.

    The local transform list mirrors each node's element order (translate /
    rotate / scale / matrix). Ancestors include the skeleton root chain so the
    composed world matrix spans the whole visual scene.
    """
    root = _dae_root(dae_path)
    parents: dict[str, str | None] = {}
    local: dict[str, list[Any]] = {}

    def el_to_mat(tag: str, text: str) -> np.ndarray:
        vals = np.array([float(x) for x in text.split()])
        if tag == "matrix":
            return vals.reshape(4, 4)
        if tag == "translate":
            m = np.eye(4)
            m[0:3, 3] = vals
            return m
        if tag == "scale":
            return np.diag([vals[0], vals[1], vals[2], 1.0])
        if tag == "rotate":
            axis = vals[0:3]
            axis = axis / (np.linalg.norm(axis) or 1.0)
            ang = np.radians(vals[3])
            k = np.array([[0, -axis[2], axis[1]], [axis[2], 0, -axis[0]], [-axis[1], axis[0], 0]])
            r = np.eye(3) + np.sin(ang) * k + (1 - np.cos(ang)) * (k @ k)
            m = np.eye(4)
            m[0:3, 0:3] = r
            return m
        return np.eye(4)

    def walk(node: ET.Element, parent_sid: str | None) -> None:
        sid = node.get("sid") or node.get("id")
        if sid:
            parents[sid] = parent_sid
            transforms: list[Any] = []
            for el in node:
                tag = el.tag.replace(_COLLADA_NS, "")
                if tag == "node":
                    continue
                if el.text and el.text.strip():
                    transforms.append(el_to_mat(tag, el.text))
                else:
                    transforms.append(np.eye(4))
            local[sid] = transforms
        for child in node.findall(_COLLADA_NS + "node"):
            walk(child, sid if sid else parent_sid)

    for vs in root.iter(_COLLADA_NS + "visual_scene"):
        for node in vs.findall(_COLLADA_NS + "node"):
            walk(node, None)

    def ancestor_chain(sid: str) -> list[str]:
        chain: list[str] = []
        cur: str | None = sid
        while cur is not None:
            chain.append(cur)
            cur = parents.get(cur)
        return chain[::-1]

    out: dict[str, tuple[list[str], list[Any]]] = {}
    for sid in local:
        out[sid] = (ancestor_chain(sid), local[sid])
    return out


def _compose_chain(chain: list[str], local: dict[str, list[Any]],
                   replacement: dict[str, np.ndarray]) -> np.ndarray:
    """World matrix for the chain root-first; optional per-sid whole-matrix swap."""
    m = np.eye(4)
    for sid in chain:
        if sid in replacement:
            m = m @ replacement[sid]
        else:
            for lm in local[sid]:
                m = m @ lm
    return m


def _bake_pose_vertices(dae_path: Path, clip_dae_path: Path) -> np.ndarray | None:
    """Skin the mesh positions at the clip's last frame (seated pose).

    Gazebo-actor semantics: every clip channel replaces the matching joint's
    local node transform; joints without a channel keep their bind transform.
    Returns deformed shared positions (n, 3), or None when anything is off.
    """
    try:
        skin = _read_skin_controller(dae_path)
        if skin is None:
            return None
        joint_names: list[str] = skin["joint_names"]
        inv_bind: np.ndarray = skin["inv_bind"]
        influences: list[list[tuple[int, float]]] = skin["influences"]

        tree = _read_scene_joint_transforms(dae_path)
        local_by_sid = {sid: mats for sid, (_, mats) in tree.items()}
        channels = _read_clip_channels(clip_dae_path)

        # Joint sids must resolve both ways (skin rig == clip rig).
        missing = [n for n in joint_names if n not in tree]
        if missing:
            logger.warning(f"Seated pose bake: skin joints missing in scene tree: {missing}")
            return None
        unanimated = [n for n in joint_names if n not in channels]
        if unanimated:
            logger.warning(
                f"Seated pose bake: {len(unanimated)} joints without clip channels "
                f"(kept at bind pose): {unanimated[:6]}"
            )

        # Sample each channel at its final key (settled seated idle pose).
        replacements: dict[str, np.ndarray] = {}
        for jname in joint_names:
            chan = channels.get(jname)
            if chan is not None:
                replacements[jname] = chan[1][-1]

        world: dict[str, np.ndarray] = {}
        for jname in joint_names:
            chain, _ = tree[jname]
            world[jname] = _compose_chain(chain, local_by_sid, replacements)

        # Per-vertex skinning: v' = Σ_j w_j · (world_j @ inv_bind_j) · v
        n_verts = len(influences)
        if not n_verts:
            return None
        # Shared positions come from the mesh DAE geometry source; read them
        # via the geometry float arrays with the largest "position" source.
        positions: np.ndarray | None = None
        root = _dae_root(dae_path)
        for src in root.iter(_COLLADA_NS + "source"):
            sid = src.get("id") or ""
            if "position" not in sid.lower():
                continue
            arr = src.find(_COLLADA_NS + "float_array")
            if arr is None:
                continue
            vals = _split_floats(arr)
            if len(vals) % 3 == 0:
                cand = vals.reshape(-1, 3)
                if len(cand) == n_verts:
                    positions = cand
                    break
        if positions is None:
            logger.warning("Seated pose bake: shared position source size != vertex weight count")
            return None

        acc = np.zeros_like(positions)
        for i, infs in enumerate(influences):
            for j_idx, w in infs:
                if w <= 0.0:
                    continue
                m = world[joint_names[j_idx]] @ inv_bind[j_idx]
                acc[i] += w * (positions[i] @ m[0:3, 0:3].T + m[0:3, 3])
        bsm = skin["bind_shape"]
        if not np.allclose(bsm, np.eye(4)):
            acc = acc @ bsm[0:3, 0:3].T + bsm[0:3, 3]
        return acc
    except Exception as exc:
        logger.warning(f"Seated pose bake failed ({exc}) — falling back to bind pose")
        return None


def _resolve_default_assets_dir() -> Path:
    if "ARENA_ASSETS_DIR" in os.environ:
        cand = Path(os.environ["ARENA_ASSETS_DIR"]) / "default"
        if cand.is_dir():
            return cand
    if "ARENA_DIR" in os.environ:
        cand = Path(os.environ["ARENA_DIR"]) / "_assets" / "default"
        if cand.is_dir():
            return cand
    for p in [
        Path("/opt/arena_ws/src/Arena/_assets/default"),
        Path("u:/src/Arena/_assets/default"),
        Path(__file__).resolve().parent.parent.parent / "_assets" / "default",
    ]:
        if p.is_dir():
            return p
    return Path("/opt/arena_ws/src/Arena/_assets/default")


def _resolve_default_cache_dir() -> Path:
    data_cand = None
    if "ARENA_DATA_DIR" in os.environ:
        data_cand = Path(os.environ["ARENA_DATA_DIR"]) / "blender_cache" / "glb"
    elif "ARENA_WS_DIR" in os.environ:
        data_cand = Path(os.environ["ARENA_WS_DIR"]) / "data" / "blender_cache" / "glb"
    else:
        for root in [Path("/opt/arena_ws/data"), Path("u:/data"), Path("/data")]:
            if root.is_dir():
                data_cand = root / "blender_cache" / "glb"
                break

    legacy_cand = Path(__file__).resolve().parent.parent / ".cache" / "glb"
    if data_cand:
        data_cand.mkdir(parents=True, exist_ok=True)
        return data_cand
    return legacy_cand


DEFAULT_ASSETS_DIR = _resolve_default_assets_dir()
DEFAULT_CACHE_DIR = _resolve_default_cache_dir()


class ModelConverter:
    def __init__(
        self,
        assets_dir: Path | None = None,
        cache_dir: Path | None = None,
    ):
        self.assets_dir = Path(assets_dir) if assets_dir else _resolve_default_assets_dir()
        self.cache_dir = Path(cache_dir) if cache_dir else _resolve_default_cache_dir()
        self.cache_dir.mkdir(parents=True, exist_ok=True)
        self._conversion_cache: dict[str, Path] = {}

    def resolve_asset_dir(self, model_id: str) -> tuple[str, str, Path | None]:
        """Split model_id into domain, name, and search for the model asset folder."""
        if "/" in model_id:
            domain, model_name = model_id.split("/", 1)
        else:
            domain, model_name = "Common", model_id

        # Search candidates in assets_dir
        candidates = [
            self.assets_dir / domain / "Object" / model_name,
            self.assets_dir / domain / "Human" / model_name,
            self.assets_dir / domain / model_name,
            self.assets_dir / "Common" / "Human" / model_name,
            self.assets_dir / "Common" / "Object" / model_name,
            self.assets_dir / "Hospital" / "Object" / model_name,
            self.assets_dir / "Office" / "Object" / model_name,
        ]

        for cand in candidates:
            if cand.is_dir():
                return domain, model_name, cand

        # Fuzzy fallback: check if a related variant exists (e.g. SM_SupplyCart_01e for SM_SupplyCart_03a)
        prefix = model_name.rsplit("_", 1)[0] if "_" in model_name else model_name
        for cand_root in [self.assets_dir / domain / "Object", self.assets_dir / "Common" / "Object"]:
            if cand_root.is_dir():
                matches = list(cand_root.glob(f"{prefix}*"))
                if matches and matches[0].is_dir():
                    logger.info(f"Fuzzy fallback: mapped {model_id} -> {matches[0].name}")
                    return domain, matches[0].name, matches[0]

        return domain, model_name, None

    def get_glb(self, model_id: str) -> Path | None:
        """
        Get or convert model_id into a cached .glb file.
        Returns Path to .glb, or None if asset cannot be resolved.
        """
        if model_id in self._conversion_cache:
            return self._conversion_cache[model_id]

        domain, model_name, asset_dir = self.resolve_asset_dir(model_id)
        if asset_dir is None:
            logger.warning(f"Could not find asset directory for model {model_id}")
            return None

        # Safe filename for cache
        safe_name = f"{domain}_{model_name}.glb"
        glb_cache_path = self.cache_dir / safe_name

        # Find source mesh (.dae / .obj)
        sdf_dir = asset_dir / f"{model_name}.sdf"
        meshes_dir = asset_dir / "meshes"
        dae_candidates = [
            meshes_dir / f"{model_name}.dae",
            meshes_dir / "arenian.dae",
            sdf_dir / f"{model_name}.dae",
            asset_dir / f"{model_name}.dae",
        ]
        # Also check for any .dae file inside sdf_dir or meshes_dir
        for sub_dir in [sdf_dir, meshes_dir]:
            if sub_dir.is_dir():
                for p in sub_dir.glob("*.dae"):
                    if p not in dae_candidates:
                        dae_candidates.append(p)

        source_mesh = next((p for p in dae_candidates if p.is_file()), None)

        if source_mesh is None:
            # Check for direct .obj or .glb
            for ext in [".obj", ".glb", ".gltf", ".fbx"]:
                p = sdf_dir / f"{model_name}{ext}"
                if p.is_file():
                    source_mesh = p
                    break

        if source_mesh is None:
            logger.warning(f"No 3D mesh found for {model_id} in {asset_dir}")
            return self._create_placeholder_glb(model_id, asset_dir, glb_cache_path)

        # Seated human variants (e.g. arenian_seated) bind their mesh in a plain
        # standing pose; the seated posture lives in clips/sitting.dae. Bake the
        # clip's final frame into the exported geometry so the cached GLB is a
        # genuinely seated character.
        pose_clip: Path | None = None
        if "seated" in model_name.lower():
            clip_cand = asset_dir / "clips" / "sitting.dae"
            if clip_cand.is_file():
                pose_clip = clip_cand
            else:
                logger.warning(
                    f"Model {model_id} looks seated but has no clips/sitting.dae — "
                    "exporting bind pose (character will render standing)"
                )

        # Check if cache is valid (source older than cached glb). Seated bakes
        # additionally require the clip and a matching pose-bake version sidecar:
        # bind-pose caches produced before pose baking must regenerate.
        cache_valid = glb_cache_path.exists()
        if cache_valid:
            cache_valid = glb_cache_path.stat().st_mtime >= source_mesh.stat().st_mtime
        if cache_valid and pose_clip is not None:
            sidecar = Path(str(glb_cache_path) + ".posever")
            cache_valid = (
                sidecar.is_file()
                and sidecar.read_text().strip() == str(_POSE_BAKE_VERSION)
                and glb_cache_path.stat().st_mtime >= pose_clip.stat().st_mtime
            )
        if cache_valid:
            self._conversion_cache[model_id] = glb_cache_path
            return glb_cache_path

        # If source is already .glb, copy or symlink
        if source_mesh.suffix.lower() == ".glb":
            self._conversion_cache[model_id] = source_mesh
            return source_mesh

        # Convert using trimesh / collada
        try:
            loaded = trimesh.load(source_mesh)
            # Detect skinned Collada meshes (like arenian) where geometry is instantiated via controller
            if isinstance(loaded, trimesh.Scene) and len(loaded.geometry) == 0:
                return self._convert_skinned_collada(
                    source_mesh, glb_cache_path, model_id, pose_clip=pose_clip
                )

            # Transform Collada Z-up (-90 deg around X) to match glTF 2.0 Y-up specification.
            # When Blender's glTF importer loads this, the model stands perfectly upright
            # with its base on the floor at Z=0 and height along +Z.
            rot = trimesh.transformations.rotation_matrix(np.radians(-90), [1, 0, 0])
            loaded.apply_transform(rot)
            loaded.export(glb_cache_path)
            self._conversion_cache[model_id] = glb_cache_path
            logger.info(f"Converted {model_id} -> {glb_cache_path.name}")
            return glb_cache_path
        except Exception as e:
            logger.error(f"Failed to convert mesh {source_mesh} for {model_id}: {e}")
            return self._create_placeholder_glb(model_id, asset_dir, glb_cache_path)

    def _convert_skinned_collada(
        self,
        dae_path: Path,
        out_glb_path: Path,
        model_id: str,
        pose_clip: Path | None = None,
    ) -> Path | None:
        """Convert a skinned Collada mesh (like arenian) with textures into glTF/GLB.

        When pose_clip is given (seated variants), the mesh is skinned at the
        clip's final frame instead of its bind pose, so the exported GLB shows
        the character in the clip's end pose (sitting).
        """
        try:
            import collada
            from PIL import Image

            col = collada.Collada(str(dae_path))
            if not col.geometries:
                return None
            geom = col.geometries[0]
            tex_dir = dae_path.parent / "textures"

            # Bake pose clip's final frame onto the shared mesh positions.
            deformed: np.ndarray | None = None
            if pose_clip is not None:
                deformed = _bake_pose_vertices(dae_path, pose_clip)
                if deformed is None:
                    logger.warning(
                        f"Seated pose bake unavailable for {model_id} — exporting bind pose"
                    )
                else:
                    logger.info(
                        f"Baked seated pose (last frame of {pose_clip.name}) "
                        f"into {model_id} -> {out_glb_path.name}"
                    )

            scene = trimesh.Scene()
            images = {}
            for img in col.images:
                img_path = tex_dir / Path(img.path).name
                if img_path.is_file():
                    try:
                        images[img.id] = Image.open(img_path)
                    except Exception:
                        pass

            mat_to_image = {}
            for m in col.materials:
                diff = getattr(m.effect, "diffuse", None)
                if isinstance(diff, collada.material.Map):
                    sampler_id = diff.sampler.id if hasattr(diff, "sampler") and diff.sampler else None
                    for img_id, img_obj in images.items():
                        if img_id.lower().replace("_", "") in m.effect.id.lower().replace("_", "") or (sampler_id and sampler_id.startswith(img_id)):
                            mat_to_image[m.id] = img_obj
                            break
                    if m.id not in mat_to_image:
                        for img_id, img_obj in images.items():
                            clean_m = m.id.lower().replace("material", "").replace("_", "")
                            clean_img = img_id.lower().replace("png", "").replace("_", "")
                            if clean_m in clean_img or clean_img in clean_m:
                                mat_to_image[m.id] = img_obj
                                break

            for i, prim in enumerate(geom.primitives):
                ts = prim.triangleset()
                if deformed is not None:
                    v_data = deformed[ts.vertex_index].reshape(-1, 3)
                else:
                    v_data = ts.vertex[ts.vertex_index].reshape(-1, 3)
                faces = np.arange(len(v_data)).reshape(-1, 3)

                uv_data = None
                if len(ts.texcoordset) > 0 and len(ts.texcoord_indexset) > 0:
                    tc_idx = ts.texcoord_indexset[0]
                    uv_data = ts.texcoordset[0][tc_idx].reshape(-1, 2)
                    uv_data[:, 1] = 1.0 - uv_data[:, 1]

                mat_id = prim.material
                img = mat_to_image.get(mat_id)

                visual = None
                if img and uv_data is not None:
                    material = trimesh.visual.material.PBRMaterial(
                        baseColorTexture=img,
                        roughnessFactor=0.6,
                        metallicFactor=0.0
                    )
                    visual = trimesh.visual.TextureVisuals(uv=uv_data, image=img, material=material)
                elif uv_data is not None:
                    visual = trimesh.visual.TextureVisuals(uv=uv_data)

                m = trimesh.Trimesh(vertices=v_data, faces=faces, visual=visual, process=False)
                scene.add_geometry(m, node_name=f"{model_id}_part_{i}")

            rot = trimesh.transformations.rotation_matrix(np.radians(-90), [1, 0, 0])
            scene.apply_transform(rot)
            min_z = scene.bounds[0][2]
            trans = trimesh.transformations.translation_matrix([0, 0, -min_z])
            scene.apply_transform(trans)

            out_glb_path.parent.mkdir(parents=True, exist_ok=True)
            scene.export(str(out_glb_path))
            if pose_clip is not None:
                Path(str(out_glb_path) + ".posever").write_text(str(_POSE_BAKE_VERSION))
                # Legacy nested cache layout (<Category>_<Sub>/<Model>.glb, e.g.
                # Common_Human/arenian_seated.glb) is still consulted as a
                # fallback by older scene builders — refresh it so no stale
                # standing copy can be picked up.
                if "/" in model_id:
                    nested_dir = out_glb_path.parent / "_".join(model_id.split("/")[:-1])
                    nested_dir.mkdir(parents=True, exist_ok=True)
                    nested_path = nested_dir / f"{model_id.rsplit('/', 1)[-1]}.glb"
                    shutil.copyfile(out_glb_path, nested_path)
            self._conversion_cache[model_id] = out_glb_path
            logger.info(f"Converted skinned {model_id} -> {out_glb_path.name}")
            return out_glb_path
        except Exception as exc:
            logger.error(f"Failed to convert skinned Collada {dae_path} for {model_id}: {exc}")
            return None

    def _create_placeholder_glb(
        self, model_id: str, asset_dir: Path | None, out_path: Path
    ) -> Path | None:
        """Create a placeholder box from annotation.yaml bounding box if mesh is absent."""
        size = [1.0, 1.0, 1.0]
        center = [0.0, 0.0, 0.5]

        if asset_dir is not None:
            ann_file = asset_dir / "annotation.yaml"
            if ann_file.is_file():
                try:
                    with open(ann_file, "r", encoding="utf-8") as f:
                        ann = yaml.safe_load(f)
                    bbox = ann.get("bounding_box")
                    if bbox and len(bbox) == 3:
                        (min_x, max_x), (min_y, max_y), (min_z, max_z) = bbox
                        size = [max_x - min_x, max_y - min_y, max_z - min_z]
                        center = [
                            (min_x + max_x) / 2.0,
                            (min_y + max_y) / 2.0,
                            (min_z + max_z) / 2.0,
                        ]
                except Exception:
                    pass

        try:
            box = trimesh.creation.box(extents=size)
            box.apply_translation(center)
            rot = trimesh.transformations.rotation_matrix(np.radians(90), [1, 0, 0])
            box.apply_transform(rot)
            box.export(out_path)
            self._conversion_cache[model_id] = out_path
            return out_path
        except Exception as e:
            logger.error(f"Failed to create placeholder box for {model_id}: {e}")
            return None

    def batch_convert_models(self, model_ids: list[str]) -> dict[str, str]:
        """Convert a list of unique model_ids in batch. Returns {model_id: glb_path_str}."""
        res: dict[str, str] = {}
        for mid in set(model_ids):
            if not mid:
                continue
            glb = self.get_glb(mid)
            if glb is not None:
                res[mid] = str(glb.resolve()).replace("\\", "/")
        return res
