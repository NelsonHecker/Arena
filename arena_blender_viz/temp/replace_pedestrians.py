"""
u:/src/Arena/arena_blender_viz/temp/replace_pedestrians.py

Industry-standard utility to replace pedestrian 3D models directly inside existing
Blender (.blend) files using Clean Native Rigged glTF 2.0 assets.

Preserves the root empty's trajectory animation (location, trajectory, rotation_euler)
and replaces child mesh parts with a native Armature + Skinned Mesh + GPU Skinning.
Assigns bone Action ('Walk' for moving pedestrians, 'Idle' for stationary observers).
Completely purges legacy 4-phase shape keys and fixes flaky/discolored skin/hair.

Usage from CLI (Python wrapper):
    python replace_pedestrians.py --blend path/to/scene.blend --mapping "0:Hospital/nurse_female_caucasian_young,1:Office/office_female_caucasian_young" [--output path/to/out.blend]

Usage with scenario YAML:
    python replace_pedestrians.py --blend path/to/scene.blend --scenario path/to/scenario.yaml [--output path/to/out.blend]

Usage inside headless Blender:
    blender -b scene.blend --python replace_pedestrians.py -- --output out.blend --mapping "0:Hospital/nurse_female_caucasian_young"
"""
from __future__ import annotations

import argparse
import json
import logging
import os
import subprocess
import sys
from pathlib import Path

logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")
logger = logging.getLogger("replace_pedestrians")

BLENDER_CANDIDATES = [
    Path(r"C:\Program Files\Blender Foundation\Blender 5.2\blender.exe"),
    Path(r"C:\Program Files\Blender Foundation\Blender 5.1\blender.exe"),
    Path(r"C:\Program Files\Blender Foundation\Blender 5.0\blender.exe"),
    Path(r"C:\Program Files\Blender Foundation\Blender 4.2\blender.exe"),
    Path(r"C:\Program Files\Blender Foundation\Blender 4.0\blender.exe"),
    Path("/usr/bin/blender"),
]


def find_blender() -> Path:
    env_p = os.environ.get("BLENDER_PATH") or os.environ.get("BLENDER_EXE")
    if env_p and Path(env_p).is_file():
        return Path(env_p)
    for c in BLENDER_CANDIDATES:
        if c.is_file():
            return c
    import shutil
    w = shutil.which("blender")
    if w:
        return Path(w)
    raise FileNotFoundError("Blender executable not found on system.")


def parse_scenario_models(scenario_yaml_path: Path) -> dict[str, str]:
    """Extract pedestrian index -> model from scenario YAML."""
    import yaml
    with open(scenario_yaml_path, "r", encoding="utf-8") as f:
        sdata = yaml.safe_load(f) or {}

    mapping = {}
    for idx, d_ent in enumerate(sdata.get("dynamic", [])):
        m = d_ent.get("model")
        if m:
            mapping[str(idx)] = m

    for s_idx, s_ent in enumerate(sdata.get("static", [])):
        m = s_ent.get("model")
        if m:
            mapping[f"static_{s_idx}"] = m
    return mapping


def ensure_rigged_glb(model_id: str, cache_dir: Path) -> Path | None:
    """Ensure a rigged GLB exists for model_id. Returns Path to GLB or None."""
    cache_dir.mkdir(parents=True, exist_ok=True)
    leaf = model_id.split("/")[-1]
    domain = model_id.split("/")[0] if "/" in model_id else "Common"

    # Known candidate names
    cands = [
        cache_dir / f"{domain}_{leaf}_rigged.glb",
        cache_dir / f"{leaf}_rigged.glb",
    ]
    for c in cands:
        if c.is_file() and c.stat().st_size > 10000:
            return c

    # Fuzzy match
    for f in cache_dir.glob(f"*{leaf}*rigged*.glb"):
        if f.is_file() and f.stat().st_size > 10000:
            return f

    # Fallbacks for corrupt assets
    if "worker_male_african_young" in leaf or "worker_male_caucasian_middleage" in leaf:
        fallback = cache_dir / "Common_worker_male_caucasian_young_rigged.glb"
        if fallback.is_file():
            logger.info(f"Using fallback rigged GLB for {model_id} -> {fallback.name}")
            return fallback

    # Try building on-the-fly via arena_blender_viz.model_converter
    try:
        from arena_blender_viz.model_converter import convert_human_to_rigged_glb
    except ImportError:
        sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
        from arena_blender_viz.model_converter import convert_human_to_rigged_glb

    assets_root = Path("u:/src/Arena/_assets/default")
    asset_dir_cands = [
        assets_root / domain / "Human" / leaf,
        assets_root / "Common" / "Human" / leaf,
        assets_root / "Hospital" / "Human" / leaf,
        assets_root / "Office" / "Human" / leaf,
    ]
    asset_dir = next((p for p in asset_dir_cands if p.is_dir()), None)
    if asset_dir:
        target_glb = cache_dir / f"{domain}_{leaf}_rigged.glb"
        logger.info(f"Building on-the-fly rigged GLB for {model_id} -> {target_glb.name}...")
        try:
            if convert_human_to_rigged_glb(asset_dir, target_glb):
                return target_glb
        except Exception as e:
            logger.warning(f"Failed on-the-fly build of {model_id}: {e}")

    # General fallback to Arenian
    arenian_cand = cache_dir / "Common_arenian_rigged.glb"
    if arenian_cand.is_file():
        logger.warning(f"Model {model_id} not found — falling back to {arenian_cand.name}")
        return arenian_cand

    return None


def _run_inside_blender(args_list: list[str]):
    import bpy
    import math
    import numpy as np

    parser = argparse.ArgumentParser(description="In-Blender Pedestrian Replacer (Rigged glTF)")
    parser.add_argument("--output", "-o", type=str, default="", help="Output blend file path")
    parser.add_argument("--mapping", type=str, default="", help="Key-value mapping: '0:modelA,1:modelB'")
    parser.add_argument("--scenario", type=str, default="", help="Path to scenario.yaml")
    parser.add_argument("--cache-dir", type=str, default="", help="GLB cache directory")

    args = parser.parse_args(args_list)

    target_models: dict[str, str] = {}
    if args.mapping:
        for pair in args.mapping.split(","):
            if ":" in pair:
                k, v = pair.split(":", 1)
                target_models[k.strip()] = v.strip()

    if args.scenario and Path(args.scenario).is_file():
        sc_map = parse_scenario_models(Path(args.scenario))
        for k, v in sc_map.items():
            if k not in target_models:
                target_models[k] = v

    print(f"[Blender Ped Replacer] Active mapping: {target_models}", flush=True)

    cache_dir = Path(args.cache_dir) if args.cache_dir else Path("u:/data/blender_cache/glb")

    ped_roots: dict[str, bpy.types.Object] = {}
    for obj in bpy.data.objects:
        if obj.name.startswith("Pedestrian_"):
            pid = obj.name.replace("Pedestrian_", "")
            ped_roots[pid] = obj

    print(f"[Blender Ped Replacer] Found {len(ped_roots)} pedestrians: {sorted(ped_roots.keys())}", flush=True)

    col_actors = bpy.data.collections.get("Actors")
    if not col_actors:
        col_actors = bpy.context.scene.collection

    # Purge legacy Prefab_Human_Arenian if present
    old_prefab = bpy.data.objects.get("Prefab_Human_Arenian")
    if old_prefab:
        for ch in list(old_prefab.children):
            bpy.data.objects.remove(ch, do_unlink=True)
        bpy.data.objects.remove(old_prefab, do_unlink=True)
        print("[Blender Ped Replacer] Removed legacy Prefab_Human_Arenian", flush=True)

    # Pre-detect default domain from scene path
    blend_name = bpy.data.filepath.lower() if bpy.data.filepath else ""
    default_model = "Common/Human/arenian"
    if "hospital" in blend_name:
        default_model = "Hospital/nurse_female_caucasian_young"
    elif "office" in blend_name or "library" in blend_name:
        default_model = "Office/office_female_caucasian_young"

    replaced_count = 0
    for pid, p_root in ped_roots.items():
        target_model = target_models.get(pid)
        if not target_model:
            num_key = pid.replace("static_", "")
            target_model = target_models.get(num_key, default_model)

        rigged_glb = ensure_rigged_glb(target_model, cache_dir)
        if not rigged_glb or not rigged_glb.is_file():
            print(f"[!] Warning: No rigged GLB available for {target_model}", flush=True)
            continue

        leaf = target_model.split("/")[-1]
        print(f"[Blender Ped Replacer] Replacing {p_root.name} with rigged '{leaf}' ({rigged_glb.name})...", flush=True)

        # 1. Detect if pedestrian is moving or stationary across timeline
        # Evaluate world translation at start, middle, and end frames
        f_start = bpy.context.scene.frame_start
        f_end = bpy.context.scene.frame_end
        f_mid = (f_start + f_end) // 2

        bpy.context.scene.frame_set(f_start)
        p0 = p_root.matrix_world.translation.copy()
        bpy.context.scene.frame_set(f_mid)
        pm = p_root.matrix_world.translation.copy()
        bpy.context.scene.frame_set(f_end)
        p1 = p_root.matrix_world.translation.copy()
        bpy.context.scene.frame_set(f_start)

        displacement = max((pm - p0).length, (p1 - p0).length)
        is_moving = displacement > 0.15
        print(f"  Pedestrian {pid} displacement = {displacement:.3f}m -> {'WALKING' if is_moving else 'IDLE'}", flush=True)

        # 2. Remove old child armatures, child meshes, and old shape key actions
        for child in list(p_root.children):
            if child.data and hasattr(child.data, "shape_keys") and child.data.shape_keys:
                sk = child.data.shape_keys
                if sk.animation_data and sk.animation_data.action:
                    old_act = sk.animation_data.action
                    bpy.data.actions.remove(old_act)
            for grand_child in list(child.children):
                bpy.data.objects.remove(grand_child, do_unlink=True)
            bpy.data.objects.remove(child, do_unlink=True)

        # Also remove any orphaned meshes/armatures previously associated with this pid
        for o in list(bpy.data.objects):
            if o.name.startswith(f"Mesh_{pid}_") or o.name.startswith(f"Armature_{pid}_"):
                bpy.data.objects.remove(o, do_unlink=True)

        # 3. Import Rigged glTF 2.0
        # Remember objects before import to accurately isolate newly imported objects
        existing_objs = set(bpy.data.objects)
        existing_actions = set(bpy.data.actions)

        bpy.ops.import_scene.gltf(filepath=str(rigged_glb))

        new_objs = [o for o in bpy.data.objects if o not in existing_objs]
        new_actions = [a for a in bpy.data.actions if a not in existing_actions]

        arm_obj = next((o for o in new_objs if o.type == "ARMATURE"), None)
        mesh_objs = [o for o in new_objs if o.type == "MESH" and o.name != "Icosphere"]

        # Clean up helper icosphere if glTF importer created one
        for o in new_objs:
            if o.name == "Icosphere" and o.type == "MESH":
                bpy.data.objects.remove(o, do_unlink=True)

        if not arm_obj:
            print(f"[!] Error: No Armature imported from {rigged_glb.name}", flush=True)
            continue

        # Rename to avoid collisions
        arm_obj.name = f"Armature_{pid}_{leaf}"
        for mo in mesh_objs:
            mo.name = f"Mesh_{pid}_{leaf}_{mo.name.split('_')[-1]}"
            # Ensure mesh modifier points to this armature
            for mod in mo.modifiers:
                if mod.type == "ARMATURE":
                    mod.object = arm_obj

        # 4. Parent Armature to Pedestrian root empty
        arm_obj.parent = p_root
        arm_obj.location = (0.0, 0.0, 0.0)
        arm_obj.rotation_euler = (0.0, 0.0, 0.0)
        arm_obj.scale = (1.0, 1.0, 1.0)

        # Link to collection
        for o in [arm_obj] + mesh_objs:
            for c in list(o.users_collection):
                c.objects.unlink(o)
            col_actors.objects.link(o)

        # 5. Build full-timeline NLA tracks so animations loop across the entire scene timeline
        if not arm_obj.animation_data:
            arm_obj.animation_data_create()

        # Find Walk and Idle actions
        walk_act = None
        idle_act = None
        for act in new_actions + list(bpy.data.actions):
            if not walk_act and (act.name == "Walk" or act.name.startswith("Walk.")):
                walk_act = act
            if not idle_act and (act.name == "Idle" or act.name.startswith("Idle.")):
                idle_act = act

        total_frames = max(100, bpy.context.scene.frame_end - bpy.context.scene.frame_start + 20)

        # Clear active action so NLA tracks evaluate properly across frames
        arm_obj.animation_data.action = None

        # Base track: Idle (always loops underneath across entire timeline)
        if idle_act:
            t_idle = arm_obj.animation_data.nla_tracks.new()
            t_idle.name = "Track_Idle"
            s_idle = t_idle.strips.new("Idle", bpy.context.scene.frame_start, idle_act)
            c_len_i = max(0.1, idle_act.frame_range[1] - idle_act.frame_range[0])
            s_idle.repeat = math.ceil(total_frames / c_len_i) + 2

        if is_moving and walk_act:
            t_walk = arm_obj.animation_data.nla_tracks.new()
            t_walk.name = "Track_Walk"
            s_walk = t_walk.strips.new("Walk", bpy.context.scene.frame_start, walk_act)
            c_len_w = max(0.1, walk_act.frame_range[1] - walk_act.frame_range[0])
            s_walk.repeat = math.ceil(total_frames / c_len_w) + 2
            s_walk.blend_type = "REPLACE"

            # Check if pedestrian has stationary segments along its timeline
            fps = bpy.context.scene.render.fps or 24
            step_fr = max(1, int(fps // 4))  # sample 4 times per second
            sampled_frames = list(range(bpy.context.scene.frame_start, bpy.context.scene.frame_end + 1, step_fr))
            if sampled_frames[-1] != bpy.context.scene.frame_end:
                sampled_frames.append(bpy.context.scene.frame_end)

            speeds = []
            for sf in sampled_frames:
                bpy.context.scene.frame_set(sf)
                p_now = p_root.matrix_world.translation.copy()
                bpy.context.scene.frame_set(max(1, sf - 1))
                p_prev = p_root.matrix_world.translation.copy()
                spd = (p_now - p_prev).length * fps
                speeds.append(spd)

            # Check if there are pauses (< 0.05 m/s) interspersed with walking
            has_pauses = any(s < 0.05 for s in speeds) and any(s >= 0.05 for s in speeds)
            if has_pauses:
                print(f"  Modulating Walk/Idle influence across timeline (pauses detected)...", flush=True)
                for sf, spd in zip(sampled_frames, speeds):
                    inf = 1.0 if spd >= 0.05 else 0.0
                    s_walk.influence = inf
                    s_walk.keyframe_insert("influence", frame=sf)
            else:
                s_walk.influence = 1.0

            print(f"  Configured Walk NLA track (repeat={s_walk.repeat:.1f}, timeline={total_frames}f) on {arm_obj.name}", flush=True)
        elif idle_act:
            print(f"  Configured Idle NLA track (repeat={s_idle.repeat:.1f}, timeline={total_frames}f) on {arm_obj.name}", flush=True)

        # 6. Ensure materials have correct blend mode (HASHED for hair/alpha cards)
        for mo in mesh_objs:
            for mat in mo.data.materials:
                if mat:
                    mat.blend_method = "HASHED"
                    if hasattr(mat, "shadow_method"):
                        mat.shadow_method = "HASHED"

        replaced_count += 1

    print(f"\n[Blender Ped Replacer] Successfully replaced {replaced_count}/{len(ped_roots)} pedestrians with rigged glTF.", flush=True)

    out_file = args.output if args.output else bpy.data.filepath
    if out_file:
        bpy.ops.wm.save_as_mainfile(filepath=str(Path(out_file).resolve()))
        print(f"[Blender Ped Replacer] Saved modified scene to: {out_file}", flush=True)


def main():
    if "--" in sys.argv:
        idx = sys.argv.index("--")
        _run_inside_blender(sys.argv[idx + 1:])
        return

    parser = argparse.ArgumentParser(description="Replace pedestrians in existing .blend files with Rigged glTF models")
    parser.add_argument("--blend", "-b", type=str, required=True, help="Input .blend file path")
    parser.add_argument("--output", "-o", type=str, default="", help="Output .blend file path (defaults to overwrite input)")
    parser.add_argument("--mapping", "-m", type=str, default="", help="Key-value mapping: '0:Hospital/nurse_female_caucasian_young'")
    parser.add_argument("--scenario", "-s", type=str, default="", help="Path to scenario.yaml")
    parser.add_argument("--cache-dir", type=str, default="u:/data/blender_cache/glb", help="GLB cache directory")

    args = parser.parse_args()

    blend_path = Path(args.blend).resolve()
    if not blend_path.is_file():
        logger.error(f"Blend file does not exist: {blend_path}")
        sys.exit(1)

    out_path = Path(args.output).resolve() if args.output else blend_path
    cache_dir = Path(args.cache_dir).resolve()

    # Pre-check and generate required rigged GLBs
    target_models = []
    if args.mapping:
        for pair in args.mapping.split(","):
            if ":" in pair:
                target_models.append(pair.split(":", 1)[1].strip())
    if args.scenario and Path(args.scenario).is_file():
        sc_map = parse_scenario_models(Path(args.scenario))
        target_models.extend(sc_map.values())

    if not target_models:
        # Default based on blend name
        bname = blend_path.name.lower()
        if "hospital" in bname:
            target_models.append("Hospital/nurse_female_caucasian_young")
        elif "office" in bname or "library" in bname:
            target_models.append("Office/office_female_caucasian_young")
        else:
            target_models.append("Common/Human/arenian")

    logger.info(f"Checking rigged GLBs for: {set(target_models)}")
    for tm in set(target_models):
        glb = ensure_rigged_glb(tm, cache_dir)
        if glb:
            logger.info(f"  Ready: {tm} -> {glb.name}")
        else:
            logger.warning(f"  Could not prepare rigged GLB for {tm}")

    blender_exe = find_blender()
    logger.info(f"Launching Blender: {blender_exe}")

    script_path = Path(__file__).resolve()
    cmd = [
        str(blender_exe),
        "--background",
        str(blend_path),
        "--python",
        str(script_path),
        "--",
        "--output",
        str(out_path),
        "--cache-dir",
        str(cache_dir),
    ]
    if args.mapping:
        cmd.extend(["--mapping", args.mapping])
    if args.scenario:
        cmd.extend(["--scenario", args.scenario])

    logger.info(f"Executing: {' '.join(cmd)}")
    res = subprocess.run(cmd)
    if res.returncode != 0:
        logger.error(f"Blender execution failed with code {res.returncode}")
        sys.exit(res.returncode)

    logger.info(f"Replacement completed successfully. Saved to: {out_path}")


if __name__ == "__main__":
    main()
