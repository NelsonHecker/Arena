"""
model_converter.py: Resolves Arena model assets and caches them as GLB meshes.
Converts Collada (.dae) models with textures into fast-loading glTF/GLB binaries.
"""
from __future__ import annotations

import logging
from pathlib import Path
from typing import Any

import numpy as np
import trimesh
import yaml

import os

logger = logging.getLogger(__name__)


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

        # Check if cache is valid (source older than cached glb)
        if (
            glb_cache_path.exists()
            and glb_cache_path.stat().st_mtime >= source_mesh.stat().st_mtime
        ):
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
                return self._convert_skinned_collada(source_mesh, glb_cache_path, model_id)

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

    def _convert_skinned_collada(self, dae_path: Path, out_glb_path: Path, model_id: str) -> Path | None:
        """Convert a skinned Collada mesh (like arenian) with textures into glTF/GLB."""
        try:
            import collada
            from PIL import Image

            col = collada.Collada(str(dae_path))
            if not col.geometries:
                return None
            geom = col.geometries[0]
            tex_dir = dae_path.parent / "textures"

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
