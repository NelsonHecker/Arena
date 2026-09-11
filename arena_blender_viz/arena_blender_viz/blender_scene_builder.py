"""
blender_scene_builder.py: Executed inside Blender 5.2 (bpy).
Builds complete 3D scene from scene_bundle.json:
- Procedural floors and walls
- Animated sliding doors (keyframed from simulation timestamps)
- Furniture models (.glb) placed by position and quaternion
- 3D trajectory ribbons with planner color coding
- Dynamic pedestrians and robot animation
- Acoustic field emission shader on floor
- Overlays (door radius, proxemic encounter markers)
- Camera presets (TopDown, 3/4 Hero, Corridor)
- Cycles lighting and render settings
"""
import json
import math
import os
import sys
import time
from pathlib import Path

import bpy
import numpy as np
from mathutils import Matrix, Quaternion, Vector

# -----------------------------------------------------------------------------
# Stage timing
# -----------------------------------------------------------------------------
# Emits a per-stage wall-clock breakdown so build regressions are attributable.
# Always flush: when Blender's stdout is redirected it is block-buffered, which
# makes a slow stage look like it is "stuck" on whatever line happened to flush
# last.  Every print in this file must therefore pass flush=True.
_T0 = time.perf_counter()
_TLAST = _T0


def stage(label: str) -> None:
    """Print elapsed time since the previous stage() call and since startup."""
    global _TLAST
    now = time.perf_counter()
    print(
        f"[TIMING] {label:<34} +{now - _TLAST:7.2f}s  (total {now - _T0:7.2f}s)",
        flush=True,
    )
    _TLAST = now


def scene_scale(tag: str) -> None:
    """Report scene size, so timings can be read against the workload that produced them."""
    n_verts = sum(len(m.vertices) for m in bpy.data.meshes)
    print(
        f"[TIMING] {tag:<34} objects={len(bpy.data.objects)} "
        f"meshes={len(bpy.data.meshes)} verts={n_verts} actions={len(bpy.data.actions)}",
        flush=True,
    )


# -----------------------------------------------------------------------------
# Bulk keyframe writing (Blender 5.x slotted actions)
# -----------------------------------------------------------------------------
# `Action.fcurves` was removed in Blender 5.x.  Curves now live in a channelbag
# reached via action -> layer -> strip -> channelbag(slot).  Writing keyframe
# points in bulk through `foreach_set` avoids one depsgraph tag per key and
# measured 100x+ faster than `keyframe_insert` inside a per-frame loop.

def new_channelbag(action_name: str, id_block, id_type: str, slot_name: str = "Slot"):
    """Attach a fresh slotted action to `id_block`; return its fcurve channelbag.

    `id_type` is "OBJECT" for objects and "KEY" for shape-key datablocks.
    Assigning `action_slot` is mandatory -- without it the action is stored but
    never evaluated, producing a silently static scene.
    """
    act = bpy.data.actions.new(action_name)
    id_block.animation_data_create()
    id_block.animation_data.action = act
    slot = act.slots.new(id_type=id_type, name=slot_name)
    id_block.animation_data.action_slot = slot
    layer = act.layers.new("Layer")
    strip = layer.strips.new(type="KEYFRAME")
    return strip.channelbag(slot, ensure=True)


_INTERP_ENUM = {"CONSTANT": 0, "LINEAR": 1, "BEZIER": 2}
_HANDLE_ENUM = {"FREE": 0, "ALIGNED": 1, "VECTOR": 2, "AUTO": 3, "AUTO_CLAMPED": 4}


def write_fcurves(channelbag, frames, curves, interpolation="LINEAR"):
    """Bulk-write sampled animation curves.

    frames  -- (N,) array of frame numbers, shared by every curve
    curves  -- iterable of (data_path, array_index, values) with values shape (N,)

    LINEAR suits curves carrying one sample per frame: sub-frame values are never
    rendered, and it avoids per-key handle computation across millions of keys.
    BEZIER reproduces exactly what keyframe_insert produces (BEZIER interpolation
    with AUTO_CLAMPED handles) and is used where keys are sparse and the
    in-between shape is visible.
    """
    n = len(frames)
    buf = np.empty(n * 2, dtype=np.float64)
    buf[0::2] = frames
    interp = np.full(n, _INTERP_ENUM[interpolation], dtype=np.int32)
    # Without explicit handle types, bezier handles stay FREE and the curve does
    # not match the keyframe_insert default.
    handles = (
        np.full(n, _HANDLE_ENUM["AUTO_CLAMPED"], dtype=np.int32)
        if interpolation == "BEZIER"
        else None
    )
    for data_path, index, values in curves:
        fc = channelbag.fcurves.new(data_path, index=index)
        fc.keyframe_points.add(n)
        buf[1::2] = values
        fc.keyframe_points.foreach_set("co", buf)
        fc.keyframe_points.foreach_set("interpolation", interp)
        if handles is not None:
            fc.keyframe_points.foreach_set("handle_left_type", handles)
            fc.keyframe_points.foreach_set("handle_right_type", handles)
        fc.update()


# True when this script executes inside a *Windows* Blender (native or via
# WSL interop). Under a native Linux Blender (e.g. the Docker container's
# /opt/blender), POSIX paths are used as-is and every Windows/WSL path
# workaround below is skipped.
IS_WIN32 = sys.platform.startswith("win")

# Read command line arguments passed after "--"
argv = sys.argv
if "--" in argv:
    args = argv[argv.index("--") + 1:]
    bundle_path = args[0]
    out_blend_path = args[1] if len(args) > 1 else "output.blend"
else:
    bundle_path = "scene_bundle.json"
    out_blend_path = "output.blend"

print(f"[Arena Blender Viz] Loading bundle: {bundle_path}", flush=True)
with open(bundle_path, "r", encoding="utf-8") as f:
    bundle = json.load(f)

world_data = bundle["world"]
model_glbs = bundle.get("model_glbs", {})
telemetry = bundle.get("telemetry", {})
options = bundle.get("options", {})
acoustic_overlay = bundle.get("acoustic_overlay", {})

# -----------------------------------------------------------------------------
# 1. Reset Scene
# -----------------------------------------------------------------------------
bpy.ops.wm.read_factory_settings(use_empty=True)
scene = bpy.context.scene
scene.unit_settings.system = "METRIC"
scene.unit_settings.scale_length = 1.0

# Configure Timeline Frame Range early so all animation and video nodes use exact bounds
fps = options.get("fps", 30)
scene.render.fps = fps

robot_traj = telemetry.get("robot_trajectory", [])
door_timelines = telemetry.get("door_timelines", {})
peds_frames = telemetry.get("pedestrians", [])

max_sim_t = 1.0
if robot_traj:
    max_sim_t = max(max_sim_t, max(pt["t"] for pt in robot_traj))
if peds_frames:
    max_sim_t = max(max_sim_t, max(fr["t"] for fr in peds_frames))
for tl in door_timelines.values():
    if tl:
        max_sim_t = max(max_sim_t, max(entry["t"] for entry in tl))

scene.frame_start = 1
scene.frame_end = max(10, int(round(max_sim_t * fps)))
print(f"[Arena Blender Viz] Timeline configured: frames 1 to {scene.frame_end} ({max_sim_t:.1f}s at {fps} fps)", flush=True)

# -----------------------------------------------------------------------------
# Static build: pose every actor at one instant and emit no animation data
# -----------------------------------------------------------------------------
# The instant is the worst-case acoustic frame, which --frame/--time already
# select via worst_case_frame in the bundle. Poses are computed against the full
# telemetry-derived timeline below, so frame_start/frame_end are only narrowed at
# the very end of the build (see section 12).
static_mode = bool(options.get("static", False))
static_target_frame = None
if static_mode:
    _wf = telemetry.get("worst_case_frame") or {}
    if _wf.get("frame"):
        static_target_frame, _why = int(_wf["frame"]), "worst-case acoustic frame"
    elif robot_traj:
        static_target_frame, _why = scene.frame_end // 2, "trajectory midpoint (no worst_case_frame)"
    else:
        static_target_frame, _why = 1, "frame 1 (no telemetry)"
    static_target_frame = max(1, min(static_target_frame, scene.frame_end))
    print(
        f"[Arena Blender Viz] Static build: posing actors at frame {static_target_frame} ({_why})",
        flush=True,
    )

# Collections
def _to_windows_path(p: str) -> str:
    """Map a POSIX path to the Windows UNC form for existence checks.

    The Windows Blender's os.path.isfile does not see WSL POSIX paths, while
    bpy.ops.import_scene.gltf accepts them natively. Use this helper for
    isfile checks only; keep POSIX paths for imports.

    No-op under a native Linux Blender (paths are already POSIX).
    """
    s = str(p)
    if IS_WIN32 and s.startswith("/") and not s.startswith(("//wsl", "//WSL")):
        return "\\\\wsl.localhost\\Ubuntu" + s.replace("/", "\\")
    return s


def _path_exists(p: str) -> bool:
    return os.path.isfile(p) or os.path.isfile(_to_windows_path(p))


def get_or_create_collection(name, parent=None):
    if name in bpy.data.collections:
        return bpy.data.collections[name]
    col = bpy.data.collections.new(name)
    if parent:
        parent.children.link(col)
    else:
        scene.collection.children.link(col)
    return col

col_world = get_or_create_collection("World_Geometry")
col_floors = get_or_create_collection("Floors", col_world)
col_walls = get_or_create_collection("Walls", col_world)
col_doors = get_or_create_collection("Doors", col_world)
col_furniture = get_or_create_collection("Furniture", col_world)
col_trajectories = get_or_create_collection("Trajectories")
col_actors = get_or_create_collection("Actors")
col_overlays = get_or_create_collection("Overlays")
col_cameras = get_or_create_collection("Cameras")
col_lighting = get_or_create_collection("Lighting")
col_prefabs = get_or_create_collection("Templates_Hidden")
col_prefabs.hide_render = True
col_prefabs.hide_viewport = True

stage("1 scene reset")

# -----------------------------------------------------------------------------
# 2. Materials
# -----------------------------------------------------------------------------
def create_pbr_material(name, color=(0.8, 0.8, 0.8, 1.0), roughness=0.5, metallic=0.0):
    if name in bpy.data.materials:
        return bpy.data.materials[name]
    mat = bpy.data.materials.new(name)
    mat.use_nodes = True
    bsdf = mat.node_tree.nodes.get("Principled BSDF")
    if bsdf:
        bsdf.inputs["Base Color"].default_value = color
        bsdf.inputs["Roughness"].default_value = roughness
        if "Metallic" in bsdf.inputs:
            bsdf.inputs["Metallic"].default_value = metallic
        if len(color) > 3 and color[3] < 1.0:
            if "Alpha" in bsdf.inputs:
                bsdf.inputs["Alpha"].default_value = color[3]
    return mat
def create_frosted_glass_material(
    name="Mat_Door_Frosted",
    color=(0.80, 0.90, 0.96, 1.0),
    roughness=0.28,
    transmission=0.70,
    alpha=0.75,
):
    """Create realistic architectural milky / frosted translucent glass material."""
    if name in bpy.data.materials:
        return bpy.data.materials[name]
    mat = bpy.data.materials.new(name)
    mat.use_nodes = True
    bsdf = mat.node_tree.nodes.get("Principled BSDF")
    if bsdf:
        bsdf.inputs["Base Color"].default_value = color
        bsdf.inputs["Roughness"].default_value = roughness
        if "Transmission Weight" in bsdf.inputs:
            bsdf.inputs["Transmission Weight"].default_value = transmission
        elif "Transmission" in bsdf.inputs:
            bsdf.inputs["Transmission"].default_value = transmission
        if "Alpha" in bsdf.inputs:
            bsdf.inputs["Alpha"].default_value = alpha
        if "IOR" in bsdf.inputs:
            bsdf.inputs["IOR"].default_value = 1.45
    return mat

def create_ao_wall_material(name="Mat_Wall"):
    mat = bpy.data.materials.new(name)
    mat.use_nodes = True
    nodes = mat.node_tree.nodes
    links = mat.node_tree.links
    nodes.clear()

    out_node = nodes.new("ShaderNodeOutputMaterial")
    bsdf = nodes.new("ShaderNodeBsdfPrincipled")
    bsdf.inputs["Base Color"].default_value = (0.95, 0.95, 0.94, 1.0)
    bsdf.inputs["Roughness"].default_value = 0.70

    # Ambient Occlusion node for dark contact crevice lines at corners and floor base.
    # Kept deliberately gentle: the MULTIPLY mix scales albedo by
    # (1-f) + f*ramp(AO), so the old f=0.85 with a 0.28 dark stop crushed
    # occluded walls to 37% albedo on top of already-low incident light.
    ao_node = nodes.new("ShaderNodeAmbientOcclusion")
    ao_node.inputs["Distance"].default_value = 0.8

    ramp = nodes.new("ShaderNodeValToRGB")
    ramp.color_ramp.elements[0].position = 0.0
    ramp.color_ramp.elements[0].color = (0.62, 0.63, 0.66, 1.0)
    ramp.color_ramp.elements[1].position = 0.85
    ramp.color_ramp.elements[1].color = (0.95, 0.95, 0.94, 1.0)

    mix_color = nodes.new("ShaderNodeMix")
    mix_color.data_type = 'RGBA'
    mix_color.blend_type = 'MULTIPLY'
    mix_color.inputs["Factor"].default_value = 0.35
    mix_color.inputs[6].default_value = (0.95, 0.95, 0.94, 1.0)

    links.new(ao_node.outputs["AO"], ramp.inputs["Fac"])
    links.new(ramp.outputs["Color"], mix_color.inputs[7])
    links.new(mix_color.outputs[2], bsdf.inputs["Base Color"])
    links.new(bsdf.outputs["BSDF"], out_node.inputs["Surface"])
    return mat

mat_wall = create_ao_wall_material("Mat_Wall")
# Milky frosted translucent glass doors with anodized aluminum hardware
mat_door = create_frosted_glass_material("Mat_Door", color=(0.80, 0.90, 0.96, 1.0), roughness=0.28, transmission=0.70, alpha=0.75)
mat_door_frame = create_pbr_material("Mat_Door_Frame", color=(0.35, 0.38, 0.42, 1.0), roughness=0.3, metallic=0.85)
mat_door_open = create_pbr_material("Mat_Door_Open", color=(0.1, 0.7, 0.3, 0.5), roughness=0.3)

def create_procedural_wood_material(
    name,
    base_color=(0.34, 0.22, 0.13, 1.0),
    roughness=0.35,
    grain_scale=10.0,
    darken_factor=0.75,
):
    """Create authentic procedural wood material with directional grain and roughness."""
    if name in bpy.data.materials:
        return bpy.data.materials[name]
    mat = bpy.data.materials.new(name)
    mat.use_nodes = True
    nodes = mat.node_tree.nodes
    links = mat.node_tree.links
    bsdf = nodes.get("Principled BSDF")

    tex_coord = nodes.new("ShaderNodeTexCoord")
    mapping = nodes.new("ShaderNodeMapping")
    mapping.inputs["Scale"].default_value = (1.0, grain_scale, 1.0)
    links.new(tex_coord.outputs["Object"], mapping.inputs["Vector"])

    noise = nodes.new("ShaderNodeTexNoise")
    noise.inputs["Scale"].default_value = 6.0
    noise.inputs["Detail"].default_value = 3.0
    links.new(mapping.outputs["Vector"], noise.inputs["Vector"])

    ramp = nodes.new("ShaderNodeValToRGB")
    dark_tone = (
        base_color[0] * darken_factor,
        base_color[1] * darken_factor,
        base_color[2] * darken_factor,
        1.0,
    )
    ramp.color_ramp.elements[0].color = dark_tone
    ramp.color_ramp.elements[1].color = base_color
    links.new(noise.outputs["Fac"], ramp.inputs["Fac"])

    links.new(ramp.outputs["Color"], bsdf.inputs["Base Color"])
    bsdf.inputs["Roughness"].default_value = roughness
    if "Specular IOR Level" in bsdf.inputs:
        bsdf.inputs["Specular IOR Level"].default_value = 0.55
    return mat

mat_library_bookcase = create_procedural_wood_material("Mat_Library_Bookcase", base_color=(0.36, 0.22, 0.13, 1.0), roughness=0.35, grain_scale=12.0)
mat_library_doors = create_procedural_wood_material("Mat_Library_Doors", base_color=(0.26, 0.15, 0.08, 1.0), roughness=0.30, grain_scale=12.0)
mat_desk_oak = create_procedural_wood_material("Mat_Desk_Oak", base_color=(0.78, 0.68, 0.54, 1.0), roughness=0.32, grain_scale=8.0)
mat_plant_leaf = create_pbr_material("Mat_Plant_Leaf", color=(0.12, 0.38, 0.10, 1.0), roughness=0.4)
mat_reception_wood = create_procedural_wood_material("Mat_Reception_Wood", base_color=(0.25, 0.25, 0.27, 1.0), roughness=0.25, grain_scale=6.0)

# Prop palette for models whose source asset carries no texture (see
# _assign_prop_material below). Kept deliberately small and low-saturation so
# re-materialled props sit quietly inside the architectural lighting.
mat_prop_electronics = create_pbr_material("Mat_Prop_Electronics", color=(0.055, 0.058, 0.068, 1.0), roughness=0.32)
mat_prop_cardboard = create_pbr_material("Mat_Prop_Cardboard", color=(0.55, 0.40, 0.26, 1.0), roughness=0.85)
mat_prop_metal = create_pbr_material("Mat_Prop_Metal", color=(0.55, 0.57, 0.60, 1.0), roughness=0.35, metallic=0.9)
mat_prop_wood = create_procedural_wood_material("Mat_Prop_Wood", base_color=(0.55, 0.40, 0.26, 1.0), roughness=0.40, grain_scale=8.0)
mat_prop_fabric = create_pbr_material("Mat_Prop_Fabric", color=(0.30, 0.32, 0.36, 1.0), roughness=0.85)
# Sanitary ware is legitimately white; the point is to shade it so the form reads
# instead of blowing out to a featureless silhouette.
mat_prop_sanitary = create_pbr_material("Mat_Prop_Sanitary", color=(0.87, 0.88, 0.88, 1.0), roughness=0.18)
mat_prop_neutral = create_pbr_material("Mat_Prop_Neutral", color=(0.62, 0.61, 0.59, 1.0), roughness=0.55)

stage("2 materials")

# -----------------------------------------------------------------------------
# 3. Floors & Acoustic Propagation Overlay
# -----------------------------------------------------------------------------
min_x, min_y, max_x, max_y = world_data.get("bounds", [0, 0, 50, 35])
span_x = max(max_x - min_x, 1.0)
span_y = max(max_y - min_y, 1.0)

acoustic_png = acoustic_overlay.get("png_path")
if acoustic_png:
    acoustic_png = str(acoustic_png)
    if IS_WIN32:
        # /opt/arena_ws is a symlink to /home/nelson/arena_ws; Blender's WSL
        # path mapping resolves /home but not /opt (nor the symlink through
        # UNC), so normalize before any existence check or image load.
        acoustic_png = acoustic_png.replace("/opt/arena_ws", "/home/nelson/arena_ws")

mat_acoustic = None

# Extent the acoustic texture is mapped onto. bundle_builder takes this from
# the texture's own manifest when one exists, falling back to world bounds.
_tb = acoustic_overlay.get("bounds")
if _tb and len(_tb) >= 4:
    tex_min_x, tex_min_y, tex_max_x, tex_max_y = (float(v) for v in _tb[:4])
else:
    tex_min_x, tex_min_y, tex_max_x, tex_max_y = min_x, min_y, max_x, max_y
tex_span_x = max(tex_max_x - tex_min_x, 1e-6)
tex_span_y = max(tex_max_y - tex_min_y, 1e-6)
print(
    f"[Arena Blender Viz] Acoustic field mapped over x {tex_min_x:.2f}..{tex_max_x:.2f}  "
    f"y {tex_min_y:.2f}..{tex_max_y:.2f}  (source: "
    f"{acoustic_overlay.get('bounds_source', 'world')})",
    flush=True,
)
# Additive floor ramp, in dBA. Defaults sit around the field's typical level
# (measured median 47.3 dBA on hospital_1_ep000) so a white plan shows through
# and only genuinely loud regions light up. Overridable per build with
# --additive-start-dba / --additive-full-dba.
# The ramp must sit where the field actually lives, or the floor shows nothing.
# The original mask saturated at texture luminance ~0.12; these defaults
# reproduce that reach (full colour by 32 dBA) but over a wider span, so the
# boundary fades instead of stepping. Raising START past ~30 dBA puts the whole
# ramp above most of the field and the floor goes bare -- which is exactly what
# happened when these were 30/45.
_ADDITIVE_START_DBA = 20.0
_ADDITIVE_FULL_DBA = 32.0

# Shadowless bounce fill (see the lighting section). Raised to 1.8 when it was
# introduced to stop -Y walls reading black; that also washed the scene out and
# fought the acoustic floor, so it now defaults low and is tunable. Set
# --fill-light-strength 0 to disable it entirely.
_FILL_LIGHT_DEFAULT_W = 0.6

# Albedo of the "white" floor in additive mode. The scene is lit hard enough
# that a white floor glares and swallows the field colour, so the quiet floor is
# deliberately dim. Raise towards 0.85 for the old bright architectural look.
_FLOOR_BRIGHTNESS = 0.25

# Fallback colour-scale limits, used only when the texture manifest does not
# supply its own (it normally does -- see bundle_builder).
_FIELD_VMIN_DBA = 20.0
_FIELD_VMAX_DBA = 60.0

# Colormap anchor tables (sampled from matplotlib). Declared before the
# acoustic shader because the additive floor ramp converts a dBA threshold
# into a texture luminance at material-build time.
INFERNO_ANCHORS = (
    (0.0015, 0.0005, 0.0139),
    (0.0140, 0.0112, 0.0719),
    (0.0423, 0.0281, 0.1411),
    (0.0820, 0.0433, 0.2153),
    (0.1358, 0.0469, 0.2998),
    (0.1904, 0.0393, 0.3614),
    (0.2450, 0.0371, 0.4000),
    (0.2972, 0.0475, 0.4205),
    (0.3540, 0.0669, 0.4309),
    (0.4039, 0.0856, 0.4332),
    (0.4537, 0.1038, 0.4305),
    (0.5035, 0.1216, 0.4234),
    (0.5596, 0.1413, 0.4101),
    (0.6093, 0.1595, 0.3936),
    (0.6585, 0.1790, 0.3727),
    (0.7065, 0.2007, 0.3478),
    (0.7584, 0.2291, 0.3153),
    (0.8019, 0.2587, 0.2831),
    (0.8420, 0.2929, 0.2486),
    (0.8780, 0.3321, 0.2123),
    (0.9130, 0.3816, 0.1698),
    (0.9387, 0.4301, 0.1304),
    (0.9591, 0.4820, 0.0895),
    (0.9742, 0.5368, 0.0484),
    (0.9846, 0.6011, 0.0236),
    (0.9879, 0.6603, 0.0517),
    (0.9856, 0.7208, 0.1122),
    (0.9775, 0.7823, 0.1859),
    (0.9625, 0.8515, 0.2855),
    (0.9487, 0.9105, 0.3953),
    (0.9517, 0.9606, 0.5242),
    (0.9884, 0.9984, 0.6449),
)


# Viridis anchors (sampled from matplotlib) for the electrical power trail;
# distinct from inferno so the two side-by-side trails never read as one scale.

def _lut_rgb(val: float, v_min: float, v_max: float, anchors: tuple) -> tuple[float, float, float, float]:
    """Map a value through an embedded matplotlib colormap anchor table (pinned limits)."""
    norm = max(0.0, min(1.0, (val - v_min) / (v_max - v_min)))
    pos = norm * (len(anchors) - 1)
    i = int(pos)
    f = pos - i
    if i >= len(anchors) - 1:
        r, g, b = anchors[-1]
    else:
        (r0, g0, b0), (r1, g1, b1) = anchors[i], anchors[i + 1]
        r = r0 + f * (r1 - r0)
        g = g0 + f * (g1 - g0)
        b = b0 + f * (b1 - b0)
    return (r, g, b, 1.0)


def _dba_to_luminance(dba: float, v_min: float, v_max: float) -> float:
    """Rec.709 luminance of the inferno colour at `dba` on a [v_min, v_max] scale.

    Lets the additive floor ramp be specified in dBA -- the unit the field is
    actually measured in -- while the shader can only threshold the texture's
    luminance, which the colormap makes a non-linear function of level.
    """
    r, g, b, _ = _lut_rgb(dba, v_min, v_max, INFERNO_ANCHORS)
    return 0.2126 * r + 0.7152 * g + 0.0722 * b


if acoustic_png and _path_exists(acoustic_png):



    print(f"[Arena Blender Viz] Setting up acoustic propagation floor: {acoustic_png}", flush=True)
    mat_acoustic = bpy.data.materials.new("Mat_Acoustic_Field")
    mat_acoustic.use_nodes = True
    nodes = mat_acoustic.node_tree.nodes
    links = mat_acoustic.node_tree.links
    nodes.clear()

    out_node = nodes.new("ShaderNodeOutputMaterial")

    # Image texture
    tex_node = nodes.new("ShaderNodeTexImage")
    clean_png = str(acoustic_png)
    if IS_WIN32:
        # /opt/arena_ws is a symlink to /home/nelson/arena_ws; Blender's WSL
        # path mapping resolves /home but not /opt, so normalize before loading.
        clean_png = clean_png.replace("/opt/arena_ws", "/home/nelson/arena_ws")
        if clean_png.startswith("//wsl.localhost/"):
            clean_png = "\\\\" + clean_png[2:].replace("/", "\\")
        # normpath only for already-Windows-style paths; POSIX /home forms must
        # stay POSIX so Blender's WSL path mapping resolves them (normpath would
        # turn them into root-relative '\home\...' paths the loader cannot read).
        if "\\" in clean_png or (len(clean_png) > 1 and clean_png[1] == ":"):
            clean_png = os.path.normpath(clean_png)
        if not os.path.isfile(clean_png):
            alt = clean_png.replace(r"\\wsl.localhost\Ubuntu\home\nelson\arena_ws", "U:").replace(r"\\wsl.localhost\ubuntu\home\nelson\arena_ws", "U:")
            if os.path.isfile(alt):
                clean_png = alt
    # bpy.data.images.load does not apply Blender's WSL path mapping, so pass
    # the explicit UNC form (POSIX /home is kept for isfile checks and gltf
    # imports, which do map it).
    tex_node.image = bpy.data.images.load(_to_windows_path(clean_png))
    ext = os.path.splitext(clean_png)[1].lower()
    if ext in [".mp4", ".mov", ".avi", ".mkv", ".webm"]:
        tex_node.image.source = 'MOVIE'
        max_f = max(scene.frame_end, 3000)
        tex_node.image_user.frame_duration = max_f
        tex_node.image_user.frame_start = 1
        tex_node.image_user.frame_offset = 0
        tex_node.image_user.use_auto_refresh = True
        tex_node.image_user.use_cyclic = False
        print(f"[Arena Blender Viz] Dynamic acoustic MP4 movie texture linked: {clean_png} (duration={max_f}, auto_refresh=True)", flush=True)
    else:
        try:
            tex_node.image.pack()
        except Exception:
            pass
    tex_node.extension = 'EXTEND'

    # Texture Coordinate (Object coordinates)
    texcoord = nodes.new("ShaderNodeTexCoord")

    # Exact Normalized Mapping: (x - tex_min_x) / tex_span_x, similarly for y.
    # Uses the TEXTURE's extent, not the map's: the solver grid runs half a cell
    # past the map on every side, so mapping with world bounds stretches the
    # field and shifts it (episode_000: ~2% and 0.25 m). Camera framing and the
    # zenith light still use the world extent -- only the field mapping is
    # tied to the texture.
    sub_node = nodes.new("ShaderNodeVectorMath")
    sub_node.operation = 'SUBTRACT'
    sub_node.inputs[1].default_value = (tex_min_x, tex_min_y, 0.0)

    mul_node = nodes.new("ShaderNodeVectorMath")
    mul_node.operation = 'MULTIPLY'
    mul_node.inputs[1].default_value = (1.0 / tex_span_x, 1.0 / tex_span_y, 1.0)

    links.new(texcoord.outputs["Object"], sub_node.inputs[0])
    links.new(sub_node.outputs["Vector"], mul_node.inputs[0])
    links.new(mul_node.outputs["Vector"], tex_node.inputs["Vector"])

    # -------------------------------------------------------------------------
    # Acoustic Heatmap Shading:
    # 1. Camera View: Pure Emission (Strength = 1.0) with exact heatmap color.
    #    - ZERO specular reflections or light glare from overhead lamps.
    #    - ZERO shadows from furniture, walls, or robot.
    #    - 100% color-true pixel accuracy matching the HUD dB scale.
    # 2. Global Illumination (Indirect Rays): Emissive radiance casting sound field
    #    glow onto adjacent walls and bookshelves.
    # -------------------------------------------------------------------------
    em_cam = nodes.new("ShaderNodeEmission")
    em_cam.inputs["Strength"].default_value = 1.0
    links.new(tex_node.outputs["Color"], em_cam.inputs["Color"])

    em_indirect = nodes.new("ShaderNodeEmission")
    acoustic_mode = str(options.get("acoustic_mode", "plain")).lower()
    print(f"[Arena Blender Viz] Acoustic floor mode: '{acoustic_mode}'", flush=True)

    if acoustic_mode == "subtle":
        em_indirect.inputs["Strength"].default_value = 1.4
    elif acoustic_mode == "glow":
        em_indirect.inputs["Strength"].default_value = 2.2
    elif acoustic_mode == "additive":
        # Additive keeps the white architectural floor, so the raw inferno
        # field colour is lifted to fill that white with hue. The same
        # near-black inferno values also drive the indirect GI that washes the
        # wall bases, so the wall glow is dialled down here.
        em_indirect.inputs["Strength"].default_value = 0.8
    else:  # plain / matte
        em_indirect.inputs["Strength"].default_value = 1.0

    links.new(tex_node.outputs["Color"], em_indirect.inputs["Color"])

    light_path = nodes.new("ShaderNodeLightPath")
    mix_light = nodes.new("ShaderNodeMixShader")

    if acoustic_mode == "additive":
        # Additive: the white architectural floor stays, TINTED by the acoustic
        # field. The heatmap drives the floor's albedo and fades to white where
        # the field is quiet, so the floor is visibly coloured without the field
        # having to out-shine the floor.
        #
        # Why albedo and not an added emission: adding colour to a lit white
        # floor cannot produce saturated colour. The floor renders near 0.9, and
        # inferno orange (0.85, 0.40, 0.15) added at any strength clamps to
        # white -- measured on episode_000, the field pixels came out
        # (255,255,167), a faint yellow, with only the dark quiet fringe
        # surviving as colour. Multiplying the floor's own colour has no such
        # ceiling: loud areas are genuinely orange, and the lighting still
        # shades them like an architectural floor.
        #
        # The ramp is in dBA and converted through the colormap below, so the
        # thresholds mean the same thing whatever the episode's vmin/vmax are.
        vmin = float(acoustic_overlay.get("vmin") or _FIELD_VMIN_DBA)
        vmax = float(acoustic_overlay.get("vmax") or _FIELD_VMAX_DBA)
        start_dba = float(options.get("additive_start_dba") or _ADDITIVE_START_DBA)
        full_dba = float(options.get("additive_full_dba") or _ADDITIVE_FULL_DBA)
        if full_dba <= start_dba:
            full_dba = start_dba + 10.0
        FLOOR_BLACK = _dba_to_luminance(start_dba, vmin, vmax)
        FLOOR_FULL = _dba_to_luminance(full_dba, vmin, vmax)
        if FLOOR_FULL <= FLOOR_BLACK:
            FLOOR_FULL = FLOOR_BLACK + 0.05
        floor_level = float(options.get("floor_brightness")
                            if options.get("floor_brightness") is not None
                            else _FLOOR_BRIGHTNESS)
        print(
            f"[Arena Blender Viz] Additive floor: white floor below {start_dba:.0f} dBA "
            f"(albedo {floor_level:.2f}), field EMISSION above, full at {full_dba:.0f} dBA "
            f"(vmin/vmax {vmin:.0f}/{vmax:.0f})",
            flush=True,
        )

        # Fully matte, no specular, and deliberately dim. The scene carries two
        # suns, a 220 W zenith panel and a downlight per zone, so a white floor
        # (0.85 albedo) renders blown out and glares -- measured at mean RGB
        # (231,232,233), 73% of floor pixels near-white, with the field's colour
        # invisible against it. Dropping the albedo leaves the acoustic emission
        # as the brightest thing on the floor, which is the point of the mode.
        # --floor-brightness tunes it; 0.85 restores the old architectural white.
        floor_bsdf = nodes.new("ShaderNodeBsdfPrincipled")
        floor_bsdf.inputs["Base Color"].default_value = (floor_level,) * 3 + (1.0,)
        floor_bsdf.inputs["Roughness"].default_value = 1.0
        for _sock in ("Specular IOR Level", "Specular"):
            if _sock in floor_bsdf.inputs:
                floor_bsdf.inputs[_sock].default_value = 0.0
                break

        # ramp = clamp((lum - FLOOR_BLACK) / (FLOOR_FULL - FLOOR_BLACK), 0, 1)
        bw_node = nodes.new("ShaderNodeRGBToBW")
        links.new(tex_node.outputs["Color"], bw_node.inputs["Color"])

        sub_lum = nodes.new("ShaderNodeMath")
        sub_lum.operation = 'SUBTRACT'
        sub_lum.inputs[1].default_value = FLOOR_BLACK
        links.new(bw_node.outputs["Val"], sub_lum.inputs[0])

        norm_lum = nodes.new("ShaderNodeMath")
        norm_lum.operation = 'MULTIPLY'
        norm_lum.inputs[1].default_value = 1.0 / (FLOOR_FULL - FLOOR_BLACK)
        links.new(sub_lum.outputs["Value"], norm_lum.inputs[0])

        mask_node = nodes.new("ShaderNodeClamp")
        mask_node.clamp_type = 'MINMAX'
        mask_node.inputs["Min"].default_value = 0.0
        mask_node.inputs["Max"].default_value = 1.0
        links.new(norm_lum.outputs["Value"], mask_node.inputs["Value"])

        # Camera rays: quiet floor stays the white architectural BSDF, loud
        # floor shows the field as EMISSION -- the pixel *is* the heatmap colour
        # and no lighting touches it, which is the only way the colour stays
        # saturated on a floor this brightly lit.
        #
        # An albedo tint (base colour = mix(white, heatmap, ramp)) was tried here
        # and is strictly worse: the colour is multiplied by the scene lighting,
        # and a pale-yellow albedo lit at ~3x renders white. Emission, as here,
        # is what `plain` mode does and it is why plain reads and this did not.
        mix_floor = nodes.new("ShaderNodeMixShader")
        links.new(mask_node.outputs["Result"], mix_floor.inputs["Fac"])
        links.new(floor_bsdf.outputs["BSDF"], mix_floor.inputs[1])   # quiet -> white floor
        links.new(em_cam.outputs["Emission"], mix_floor.inputs[2])   # loud -> heatmap colour

        links.new(light_path.outputs["Is Camera Ray"], mix_light.inputs["Fac"])
        links.new(em_indirect.outputs["Emission"], mix_light.inputs[1])  # non-camera rays
        links.new(mix_floor.outputs["Shader"], mix_light.inputs[2])      # camera rays

    else:
        links.new(light_path.outputs["Is Camera Ray"], mix_light.inputs["Fac"])
        links.new(em_indirect.outputs["Emission"], mix_light.inputs[1])  # Non-camera rays
        links.new(em_cam.outputs["Emission"], mix_light.inputs[2])       # Camera rays

    links.new(mix_light.outputs["Shader"], out_node.inputs["Surface"])


stage("3a acoustic shader (material only)")

# Default Architectural Slate Floor with Ambient Occlusion contact darkening
def create_architectural_floor_material(name="Mat_Floor"):
    mat = bpy.data.materials.new(name)
    mat.use_nodes = True
    nodes = mat.node_tree.nodes
    links = mat.node_tree.links
    nodes.clear()

    out_node = nodes.new("ShaderNodeOutputMaterial")
    bsdf = nodes.new("ShaderNodeBsdfPrincipled")
    bsdf.inputs["Base Color"].default_value = (0.68, 0.70, 0.72, 1.0)  # Cool architectural slate grey
    bsdf.inputs["Roughness"].default_value = 0.25

    ao_node = nodes.new("ShaderNodeAmbientOcclusion")
    ao_node.inputs["Distance"].default_value = 0.8

    ramp = nodes.new("ShaderNodeValToRGB")
    ramp.color_ramp.elements[0].position = 0.0
    ramp.color_ramp.elements[0].color = (0.35, 0.36, 0.38, 1.0)
    ramp.color_ramp.elements[1].position = 0.85
    ramp.color_ramp.elements[1].color = (0.68, 0.70, 0.72, 1.0)

    mix_color = nodes.new("ShaderNodeMix")
    mix_color.data_type = 'RGBA'
    mix_color.blend_type = 'MULTIPLY'
    mix_color.inputs["Factor"].default_value = 0.8
    mix_color.inputs[6].default_value = (0.68, 0.70, 0.72, 1.0)

    links.new(ao_node.outputs["AO"], ramp.inputs["Fac"])
    links.new(ramp.outputs["Color"], mix_color.inputs[7])
    links.new(mix_color.outputs[2], bsdf.inputs["Base Color"])
    links.new(bsdf.outputs["BSDF"], out_node.inputs["Surface"])
    return mat

mat_default_floor = create_architectural_floor_material("Mat_Floor_Architectural")

for zone in world_data.get("zones", []):
    z_name = zone["name"]
    corners = zone.get("corners", [])
    if len(corners) < 3:
        continue

    verts = [(c["x"], c["y"], 0.0) for c in corners]
    faces = [list(range(len(verts)))]

    mesh = bpy.data.meshes.new(f"mesh_floor_{z_name}")
    mesh.from_pydata(verts, [], faces)
    mesh.update()

    obj = bpy.data.objects.new(f"floor_{z_name}", mesh)
    col_floors.objects.link(obj)

    # Assign material: acoustic emission if available, else high-contrast architectural slate
    if mat_acoustic:
        obj.data.materials.append(mat_acoustic)
    else:
        obj.data.materials.append(mat_default_floor)

stage("3 floors")

# -----------------------------------------------------------------------------
# 4. Extruded Walls
# -----------------------------------------------------------------------------
def create_wall_box(start, end, height=2.0, width=0.05, name="wall"):
    dx = end["x"] - start["x"]
    dy = end["y"] - start["y"]
    length = math.hypot(dx, dy)
    if length < 1e-4:
        return None

    ux = dx / length
    uy = dy / length
    # Perpendicular vector
    px = -uy * (width / 2.0)
    py = ux * (width / 2.0)

    # 4 bottom vertices, 4 top vertices
    v0 = (start["x"] + px, start["y"] + py, 0.0)
    v1 = (start["x"] - px, start["y"] - py, 0.0)
    v2 = (end["x"] - px, end["y"] - py, 0.0)
    v3 = (end["x"] + px, end["y"] + py, 0.0)

    v4 = (start["x"] + px, start["y"] + py, height)
    v5 = (start["x"] - px, start["y"] - py, height)
    v6 = (end["x"] - px, end["y"] - py, height)
    v7 = (end["x"] + px, end["y"] + py, height)

    verts = [v0, v1, v2, v3, v4, v5, v6, v7]
    faces = [
        [0, 1, 2, 3],  # bottom
        [4, 7, 6, 5],  # top
        [0, 3, 7, 4],  # front
        [1, 5, 6, 2],  # back
        [0, 4, 5, 1],  # left
        [3, 2, 6, 7],  # right
    ]

    mesh = bpy.data.meshes.new(f"mesh_{name}")
    mesh.from_pydata(verts, [], faces)
    mesh.update()

    obj = bpy.data.objects.new(name, mesh)
    obj.data.materials.append(mat_wall)
    return obj

def subtract_doors_from_wall(w_start, w_end, doors):
    """Subtract door apertures from wall segment to ensure zero overlap."""
    dx = w_end["x"] - w_start["x"]
    dy = w_end["y"] - w_start["y"]
    L = math.hypot(dx, dy)
    if L < 1e-4:
        return []
    ux = dx / L
    uy = dy / L

    intervals_to_cut = []
    for d in doors:
        ds = d["start"]
        de = d["end"]
        # Check collinearity via cross product
        cross1 = (ds["x"] - w_start["x"]) * uy - (ds["y"] - w_start["y"]) * ux
        cross2 = (de["x"] - w_start["x"]) * uy - (de["y"] - w_start["y"]) * ux
        if abs(cross1) < 0.12 and abs(cross2) < 0.12:
            t1 = (ds["x"] - w_start["x"]) * ux + (ds["y"] - w_start["y"]) * uy
            t2 = (de["x"] - w_start["x"]) * ux + (de["y"] - w_start["y"]) * uy
            cut_start = max(0.0, min(t1, t2))
            cut_end = min(L, max(t1, t2))
            if cut_end - cut_start > 0.05:
                intervals_to_cut.append((cut_start, cut_end))

    if not intervals_to_cut:
        return [(w_start, w_end)]

    intervals_to_cut.sort()
    merged_cuts = []
    for s, e in intervals_to_cut:
        if not merged_cuts or merged_cuts[-1][1] < s:
            merged_cuts.append([s, e])
        else:
            merged_cuts[-1][1] = max(merged_cuts[-1][1], e)

    res = []
    cur_t = 0.0
    for s, e in merged_cuts:
        if s - cur_t > 0.05:
            res.append((
                {"x": w_start["x"] + cur_t * ux, "y": w_start["y"] + cur_t * uy, "z": w_start.get("z", 0.0)},
                {"x": w_start["x"] + s * ux, "y": w_start["y"] + s * uy, "z": w_end.get("z", 0.0)},
            ))
        cur_t = max(cur_t, e)
    if L - cur_t > 0.05:
        res.append((
            {"x": w_start["x"] + cur_t * ux, "y": w_start["y"] + cur_t * uy, "z": w_start.get("z", 0.0)},
            {"x": w_start["x"] + L * ux, "y": w_start["y"] + L * uy, "z": w_end.get("z", 0.0)},
        ))
    return res

# Collect all doors in the world for aperture subtraction
all_doors = [d for zone in world_data.get("zones", []) for d in zone.get("doors", [])]

DEFAULT_WALL_HEIGHT = 2.0

wall_idx = 0
for zone in world_data.get("zones", []):
    for w in zone.get("walls", []):
        sub_segs = subtract_doors_from_wall(w["start"], w["end"], all_doors)
        w_height = w.get("height", DEFAULT_WALL_HEIGHT)
        for s_start, s_end in sub_segs:
            w_obj = create_wall_box(
                s_start,
                s_end,
                height=w_height,
                width=w.get("width", 0.05),
                name=f"wall_{wall_idx}",
            )
            if w_obj:
                col_walls.objects.link(w_obj)
                wall_idx += 1

stage("4 walls")

# -----------------------------------------------------------------------------
# 5. Sliding Doors & Dynamic Keyframing
# -----------------------------------------------------------------------------
door_timelines = telemetry.get("door_timelines", {})
fps = options.get("fps", 30)
default_door_open = options.get("doors_open", True)  # Open by default so doorway is visible

door_idx = 0
for zone in world_data.get("zones", []):
    for d in zone.get("doors", []):
        d_name = d.get("name", f"door_{door_idx}")
        start, end = d["start"], d["end"]
        # Guarantee exact same height as walls (flush top rim)
        height = d.get("height", DEFAULT_WALL_HEIGHT)
        door_thick = 0.035  # Realistic 3.5cm architectural sliding door panel

        dx = end["x"] - start["x"]
        dy = end["y"] - start["y"]
        aperture_len = math.hypot(dx, dy)
        if aperture_len < 1e-4:
            continue

        dir_x = dx / aperture_len
        dir_y = dy / aperture_len
        # Perpendicular normal vector for lateral wall-track mounting offset
        norm_x = -dir_y * 0.045
        norm_y = dir_x * 0.045

        # Door panel start and end offset laterally so it hangs on exterior track
        p_start = {"x": start["x"] + norm_x, "y": start["y"] + norm_y, "z": 0.0}
        p_end = {"x": end["x"] + norm_x, "y": end["y"] + norm_y, "z": 0.0}

        d_obj = create_wall_box(p_start, p_end, height=height, width=door_thick, name=f"door_{d_name}")
        if not d_obj:
            continue
        d_obj.data.materials.clear()
        d_obj.data.materials.append(mat_door)
        col_doors.objects.link(d_obj)

        # Overhead Guide Rail mounted FLUSH within wall top rim (height - 0.05 to height)
        # Guarantees the rail NEVER extends above the top rim of the wall
        r_start = {"x": start["x"] - dir_x * 0.2 + norm_x, "y": start["y"] - dir_y * 0.2 + norm_y, "z": height - 0.05}
        r_end = {"x": end["x"] + dir_x * (aperture_len + 0.2) + norm_x, "y": end["y"] + dir_y * (aperture_len + 0.2) + norm_y, "z": height - 0.05}
        rail_obj = create_wall_box(r_start, r_end, height=0.05, width=0.05, name=f"door_rail_{d_name}")
        if rail_obj:
            rail_obj.data.materials.clear()
            rail_obj.data.materials.append(mat_door_frame)
            col_doors.objects.link(rail_obj)

        # Dynamic sliding keyframing or open resting position
        timeline = door_timelines.get(d_name)
        if timeline is None:
            # Fuzzy match door name (with/without zone prefix, door_ prefix)
            for k, tl in door_timelines.items():
                if k == d_name or k.endswith(f"/{d_name}") or d_name.endswith(f"/{k}") or k in d_name or d_name in k:
                    timeline = tl
                    break
        if timeline is None:
            timeline = []

        slide_vec = Vector((dir_x * (aperture_len * 0.9), dir_y * (aperture_len * 0.9), 0.0))

        if timeline and options.get("animate_doors", True):
            closed_loc = Vector(d_obj.location)
            # Find closest progress in timeline to active timeframe
            target_t = 0.0
            worst_frame = telemetry.get("worst_case_frame")
            if worst_frame and worst_frame.get("t") is not None:
                target_t = float(worst_frame["t"])
            if static_mode:
                # Freeze on the timeline state at the chosen instant. The entry
                # touched here becomes the door's permanent resting position.
                target_t = static_target_frame / fps
            closest_entry = min(timeline, key=lambda e: abs(e["t"] - target_t))
            init_prog = float(closest_entry.get("progress", 0.0))

            # Set initial resting position to active timeframe state
            d_obj.location = closed_loc + slide_vec * init_prog

            if static_mode:
                pass  # static build: pose set above, no action created
            else:
                # Bulk-write the whole timeline. These timelines are sampled at
                # roughly the frame rate (one door carries 2,269 entries here), so a
                # keyframe_insert call per entry dominated this stage. keyframe_insert
                # *replaces* a key at an already-keyed frame, so collapse duplicate
                # frames keeping the last value.
                by_frame = {}
                for entry in timeline:
                    frame = max(1, int(entry["t"] * fps))
                    by_frame[frame] = closed_loc + slide_vec * float(entry.get("progress", 0.0))
                ordered = sorted(by_frame)
                door_frames = np.array(ordered, dtype=np.float64)
                door_locs = np.array([tuple(by_frame[f]) for f in ordered], dtype=np.float64)
                # BEZIER + AUTO_CLAMPED matches keyframe_insert exactly; these keys are
                # sparse enough that the in-between shape is visible.
                write_fcurves(
                    new_channelbag(f"{d_obj.name}_action", d_obj, "OBJECT"),
                    door_frames,
                    [(f"location", i, door_locs[:, i]) for i in range(3)],
                    interpolation="BEZIER",
                )
        elif default_door_open:
            # Main corridor doors retract 85% open so the threshold is open and visible.
            # Narrow stall / restroom doors (<1.0m) stay closed in static view to keep cubicles neat.
            slide_factor = 0.0 if (aperture_len < 1.0 or "stall" in d_name) else 0.85
            d_obj.location = Vector(d_obj.location) + slide_vec * slide_factor

        # Optional Door Trigger Radius Overlay
        if options.get("show_door_radius", False):
            act_dist = d.get("activation_distance", [1.2, 1.2])[0]
            cx = (start["x"] + end["x"]) / 2.0
            cy = (start["y"] + end["y"]) / 2.0
            bpy.ops.mesh.primitive_cylinder_add(
                radius=act_dist, depth=0.01, location=(cx, cy, 0.01)
            )
            cyl = bpy.context.active_object
            cyl.name = f"trigger_radius_{d_name}"
            mat_trig = create_pbr_material(f"Mat_Trigger_{d_name}", color=(0.1, 0.6, 0.9, 0.25), roughness=0.5)
            cyl.data.materials.append(mat_trig)
            col_overlays.objects.link(cyl)
            scene.collection.objects.unlink(cyl)

        door_idx += 1

stage("5 doors")

# -----------------------------------------------------------------------------
# 6. Furniture Models Import (.glb)
# -----------------------------------------------------------------------------
print(f"[Arena Blender Viz] Importing {len(model_glbs)} unique furniture models...", flush=True)

loaded_prefabs = {}
placed_bookcases = {}

# Verify each model path once. The entity loop below references the same handful
# of models hundreds of times, and os.path.isfile is a syscall every call.
model_glb_ok = {
    m_id: bool(p) and os.path.isfile(p) for m_id, p in model_glbs.items()
}


# -----------------------------------------------------------------------------
# Untextured-asset repair
# -----------------------------------------------------------------------------
# Most Office/Hospital source .dae assets ship an empty <library_images/> with a
# lambert diffuse of 1 1 1 -- SM_Printer, SM_BoxPortableB, SM_MonitorPC,
# SM_TableCoffee, SM_FileCabinet_01 among them. The .png sitting beside those
# assets is a preview thumbnail (the folders also hold *_thumb/_topdown), not a
# texture, so the GLB imports as plain white and the prop reads as "missing a
# texture" against the light architectural floor.
#
# Pure BLACK source materials are deliberately left alone: they are rarer, and
# dark equipment is a plausible authoring intent rather than a defect.

_PROP_MATERIAL_RULES = (
    # (substring of model_id, material); first match wins
    ("monitor", mat_prop_electronics),
    ("tvdisplay", mat_prop_electronics),
    ("laptop", mat_prop_electronics),
    ("keyboard", mat_prop_electronics),
    ("mousepad", mat_prop_electronics),
    ("smartphone", mat_prop_electronics),
    ("phone", mat_prop_electronics),
    ("printer", mat_prop_electronics),
    ("box", mat_prop_cardboard),
    ("filecabinet", mat_prop_metal),
    ("cupboard", mat_prop_metal),
    ("rack", mat_prop_metal),
    ("markerboard", mat_prop_metal),
    ("mirror", mat_prop_metal),
    ("extinguisher", mat_prop_metal),
    ("table", mat_prop_wood),
    ("armchair", mat_prop_fabric),
    ("chair", mat_prop_fabric),
    ("toilet", mat_prop_sanitary),
    ("washbasin", mat_prop_sanitary),
    ("trashcan", mat_prop_sanitary),
    ("handdryer", mat_prop_sanitary),
)


def _is_untextured_white_material(mat) -> bool:
    """True for an imported material that is plain white with no image texture."""
    if mat is None or not mat.use_nodes:
        return False
    for node in mat.node_tree.nodes:
        if node.type == "TEX_IMAGE" and node.image:
            return False
    for node in mat.node_tree.nodes:
        if node.type == "BSDF_PRINCIPLED":
            base = node.inputs["Base Color"]
            if base.is_linked:
                return False
            r, g, b = base.default_value[:3]
            return r > 0.97 and g > 0.97 and b > 0.97
    return False


def assign_prop_material(obj, m_id_lower: str) -> str | None:
    """Re-material an untextured prop; return the material name, or None if untouched.

    Textured props are left completely alone. Untextured ones get the curated
    material for their category, falling back to a neutral so that no prop can
    render as a featureless white silhouette.
    """
    current = obj.material_slots[0].material if obj.material_slots else None
    if current is not None and not _is_untextured_white_material(current):
        return None

    # Match on the glTF mesh node name as well as the model id: the node name
    # comes straight from the source asset, whereas the model id can be a
    # fuzzy-matched alias that says nothing about what the prop actually is
    # (model id X resolving to SM_BoxPortableB, say).
    haystack = f"{m_id_lower} {obj.name.lower()}"
    chosen = mat_prop_neutral
    for token, mat in _PROP_MATERIAL_RULES:
        if token in haystack:
            chosen = mat
            break

    if obj.material_slots:
        obj.material_slots[0].material = chosen
    else:
        obj.data.materials.append(chosen)
    return chosen.name

for zone in world_data.get("zones", []):
    z_name = zone["name"]
    zone_furniture_col = get_or_create_collection(f"Furn_{z_name}", col_furniture)

    for ent in zone.get("static_entities", []):
        m_id = ent.get("model_id", "")
        glb_path = model_glbs.get(m_id)
        if not model_glb_ok.get(m_id):
            continue

        # Import or duplicate from prefab
        if glb_path not in loaded_prefabs:
            bpy.ops.import_scene.gltf(filepath=glb_path)
            imported_objs = list(bpy.context.selected_objects)
            # Parent imported objects to an underground root empty in hidden prefabs collection
            root_empty = bpy.data.objects.new(f"Prefab_{m_id}", None)
            root_empty.location = (0.0, 0.0, -1000.0)
            root_empty.hide_render = True
            root_empty.hide_viewport = True
            col_prefabs.objects.link(root_empty)
            for o in imported_objs:
                o.parent = root_empty
                o.hide_render = True
                o.hide_viewport = True
                for c in list(o.users_collection):
                    c.objects.unlink(o)
                col_prefabs.objects.link(o)

                # Enhance untextured models with authentic architectural PBR materials
                m_id_lower = m_id.lower()
                if "bookcase" in m_id_lower:
                    if "section1" in o.name.lower():
                        if o.material_slots:
                            o.material_slots[0].material = mat_library_doors
                        else:
                            o.data.materials.append(mat_library_doors)
                    else:
                        if o.material_slots:
                            o.material_slots[0].material = mat_library_bookcase
                        else:
                            o.data.materials.append(mat_library_bookcase)
                elif "secretarydesk" in m_id_lower or ("desk" in m_id_lower and "office" in m_id_lower):
                    if o.material_slots:
                        o.material_slots[0].material = mat_desk_oak
                    else:
                        o.data.materials.append(mat_desk_oak)
                elif "plant" in m_id_lower:
                    if o.material_slots:
                        o.material_slots[0].material = mat_plant_leaf
                    else:
                        o.data.materials.append(mat_plant_leaf)
                elif "receptionstand" in m_id_lower:
                    if o.material_slots:
                        o.material_slots[0].material = mat_reception_wood
                    else:
                        o.data.materials.append(mat_reception_wood)
                else:
                    # Everything else keeps its imported material -- unless that
                    # material is untextured white, which most Office props are.
                    assign_prop_material(o, m_id_lower)

            loaded_prefabs[glb_path] = root_empty

        # Overlap filter for bookcases (resolves severe 84 cm mesh penetration & Z-fighting)
        is_bookcase = "bookcase" in ent.get("name", "").lower() or "sm_bookcasea" in m_id.lower()
        pos = ent.get("position", {"x": 0, "y": 0, "z": 0})
        orient = ent.get("orientation", {"w": 1, "x": 0, "y": 0, "z": 0})
        scale = ent.get("scale", {"x": 1, "y": 1, "z": 1})

        if is_bookcase:
            overlap_found = False
            for bx, by in placed_bookcases.get(z_name, []):
                # Filter out true duplicate overlaps (same stack at identical/near X with delta_y < 1.6m)
                # while allowing back-to-back paired L and R stacks (dx = 0.5m)
                if abs(pos["x"] - bx) < 0.2 and abs(pos["y"] - by) < 1.6:
                    overlap_found = True
                    break
            if overlap_found:
                continue
            placed_bookcases.setdefault(z_name, []).append((pos["x"], pos["y"]))

            # Double-sided library stack orientation:
            # When back-to-back bookcases are paired (_L and _R), rotate the left bookcase
            # 180 degrees around Z so its open shelves face the left aisle instead of clipping into _R's back.
            ent_name = ent.get("name", "").lower()
            if "_l_" in ent_name or ent_name.endswith("_l"):
                if abs(orient.get("z", 0.0)) < 0.01 and abs(orient.get("w", 1.0) - 1.0) < 0.01:
                    orient = {"w": 0.0, "x": 0.0, "y": 0.0, "z": 1.0}

        # Instantiate instance
        prefab_root = loaded_prefabs[glb_path]
        instance = bpy.data.objects.new(ent.get("name", "furniture"), None)
        instance.instance_type = "COLLECTION"

        instance.location = (pos["x"], pos["y"], pos["z"])
        instance.rotation_mode = "QUATERNION"
        instance.rotation_quaternion = (orient["w"], orient["x"], orient["y"], orient["z"])
        instance.scale = (scale["x"], scale["y"], scale["z"])

        zone_furniture_col.objects.link(instance)

        # Linked duplicates: same mesh datablock, independent transform.
        # Copying the mesh here (dupe.data = child.data.copy()) gave every placed
        # entity its own datablock, so all of them were serialised on save -- a
        # 151-entity world produced a 631 MB .blend. Furniture is static, so
        # sharing the mesh renders identically at a fraction of the size.
        for child in prefab_root.children:
            dupe = child.copy()
            dupe.data = child.data
            dupe.parent = instance
            dupe.hide_render = False
            dupe.hide_viewport = False
            zone_furniture_col.objects.link(dupe)

stage("6 furniture (import+instantiate)")

# -----------------------------------------------------------------------------
# 7. Robot Trajectory Ribbon & Animation
# -----------------------------------------------------------------------------
robot_traj = telemetry.get("robot_trajectory", [])
peds_frames = telemetry.get("pedestrians", [])


# Pinned colormap limits for the side-by-side emission trails (--show-energy-glow).
# Energy defaults match the paper Fig 1 power axis (0-300 W); acoustic defaults
# match the paper Fig 1 colorbar (40-65 dBA). Limits are constant across frames
# (GEMINI.md section 12) and overridable at build time via --glow-energy-vmin/
# --glow-energy-vmax and --glow-acoustic-vmin/--glow-acoustic-vmax.
_GLOW_ENERGY_VMIN_W = 0.0
_GLOW_ENERGY_VMAX_W = 300.0
_GLOW_ACOUSTIC_VMIN_DBA = 40.0
_GLOW_ACOUSTIC_VMAX_DBA = 65.0

# Emission strength for the ribbon when --show-energy-glow is on. The plain
# ribbon sits at 1.5; this lifts it so it reads as a light source rather than a
# painted stripe.
_GLOW_STRENGTH = 3.0
VIRIDIS_ANCHORS = (
    (0.2670, 0.0049, 0.3294),
    (0.2770, 0.0503, 0.3757),
    (0.2823, 0.0950, 0.4173),
    (0.2829, 0.1359, 0.4534),
    (0.2780, 0.1804, 0.4867),
    (0.2693, 0.2188, 0.5096),
    (0.2573, 0.2561, 0.5266),
    (0.2431, 0.2921, 0.5385),
    (0.2259, 0.3308, 0.5473),
    (0.2105, 0.3637, 0.5522),
    (0.1959, 0.3954, 0.5553),
    (0.1823, 0.4262, 0.5571),
    (0.1681, 0.4600, 0.5581),
    (0.1563, 0.4896, 0.5579),
    (0.1448, 0.5191, 0.5566),
    (0.1337, 0.5485, 0.5535),
    (0.1235, 0.5817, 0.5474),
    (0.1194, 0.6111, 0.5390),
    (0.1248, 0.6405, 0.5271),
    (0.1433, 0.6695, 0.5112),
    (0.1807, 0.7014, 0.4882),
    (0.2264, 0.7289, 0.4628),
    (0.2815, 0.7552, 0.4326),
    (0.3441, 0.7800, 0.3974),
    (0.4219, 0.8058, 0.3519),
    (0.4966, 0.8264, 0.3064),
    (0.5756, 0.8446, 0.2564),
    (0.6576, 0.8602, 0.2031),
    (0.7519, 0.8750, 0.1432),
    (0.8353, 0.8860, 0.1026),
    (0.9162, 0.8961, 0.1007),
    (0.9932, 0.9062, 0.1439),
)


if robot_traj:
    # Which quantity colours the ribbon. `--glow-metric power` swaps the
    # acoustic ramp for the electrical-power one; acoustic stays the default so
    # existing figures are byte-identical unless the flag is passed.
    glow_metric = str(options.get("glow_metric", "acoustic")).lower()
    metric_key = "power_w" if glow_metric == "power" else "acoustic_dba"
    print(f"[Arena Blender Viz] Building false-color emissive trajectory ribbon "
          f"({len(robot_traj)} points, metric={glow_metric})...", flush=True)
    thick = options.get("trajectory_thickness", 0.08)
    half_w = max(0.04, thick / 2.0)
    z_lift = 0.08

    # Pinned colour limits: explicit options win, else the data range, else the
    # documented defaults (0-300 W / 40-65 dBA).
    _m_lo = options.get("glow_energy_vmin" if metric_key == "power_w" else "glow_acoustic_vmin")
    _m_hi = options.get("glow_energy_vmax" if metric_key == "power_w" else "glow_acoustic_vmax")
    _defaults = (0.0, 300.0) if metric_key == "power_w" else (40.0, 65.0)
    if _m_lo is None or _m_hi is None or float(_m_hi) <= float(_m_lo):
        _vals = [float(pt.get(metric_key) or 0.0) for pt in robot_traj]
        _lo, _hi = (min(_vals), max(_vals)) if _vals else _defaults
        if _hi - _lo < 1e-3:
            _lo, _hi = _defaults
    else:
        _lo, _hi = float(_m_lo), float(_m_hi)
    min_db, max_db = _lo, _hi

    # Color ramp: Smooth Turbo / Plasma palette: Blue (quiet) -> Cyan -> Green -> Yellow -> Orange -> Deep Red (loud)
    def acoustic_to_rgb(val: float, v_min: float, v_max: float) -> tuple[float, float, float, float]:
        norm = max(0.0, min(1.0, (val - v_min) / (v_max - v_min)))
        # 5-segment smooth gradient
        # 0.0: Quiet Blue (0.1, 0.3, 0.9)
        # 0.25: Cyan (0.0, 0.8, 0.8)
        # 0.50: Green (0.2, 0.9, 0.2)
        # 0.75: Amber/Yellow (1.0, 0.75, 0.0)
        # 1.0: Hot Red / Magenta (1.0, 0.1, 0.2)
        if norm <= 0.25:
            f = norm / 0.25
            r = 0.1 + f * (-0.1)
            g = 0.3 + f * 0.5
            b = 0.9 + f * (-0.1)
        elif norm <= 0.50:
            f = (norm - 0.25) / 0.25
            r = 0.0 + f * 0.2
            g = 0.8 + f * 0.1
            b = 0.8 + f * (-0.6)
        elif norm <= 0.75:
            f = (norm - 0.50) / 0.25
            r = 0.2 + f * 0.8
            g = 0.9 + f * (-0.15)
            b = 0.2 + f * (-0.2)
        else:
            f = (norm - 0.75) / 0.25
            r = 1.0 + f * 0.0
            g = 0.75 + f * (-0.65)
            b = 0.0 + f * 0.2
        return (r, g, b, 1.0)

    # Build connected ribbon quad strip
    verts = []
    faces = []
    pt_colors = []

    # --- Stationary-point dedupe -------------------------------------------
    # A telemetry frame where the robot barely moved produces a degenerate
    # segment. At 30 Hz even 3 mm/s falls under the old 1e-4 m test, and the
    # strip then fell back to a hardcoded (0,1) normal -- a direction unrelated
    # to travel -- so the ribbon twisted 90 degrees at every such point (38 of
    # them in hospital_1_ep000). Drop those points entirely: they carry no
    # geometry, and dropping them also removes the coplanar quad overlap that
    # made the ribbon z-fight.
    MIN_STEP = max(1e-3, half_w * 0.05)
    keep = [0]
    for i in range(1, len(robot_traj)):
        dx = robot_traj[i]["x"] - robot_traj[keep[-1]]["x"]
        dy = robot_traj[i]["y"] - robot_traj[keep[-1]]["y"]
        if math.hypot(dx, dy) >= MIN_STEP:
            keep.append(i)
    if keep[-1] != len(robot_traj) - 1:
        keep.append(len(robot_traj) - 1)
    pts = [robot_traj[i] for i in keep]
    dropped = len(robot_traj) - len(pts)

    # --- Mitered offset normals --------------------------------------------
    # An offset polyline must miter: the offset direction at a joint is the
    # normalised sum of the two adjacent segment normals, not either one alone.
    # Using a single segment's normal makes the two edges cross at corners
    # (44 folded edges before this change).
    n = len(pts)
    seg_n = []
    for i in range(n):
        if i < n - 1:
            dx = pts[i + 1]["x"] - pts[i]["x"]
            dy = pts[i + 1]["y"] - pts[i]["y"]
        else:
            dx = pts[i]["x"] - pts[i - 1]["x"]
            dy = pts[i]["y"] - pts[i - 1]["y"]
        L = math.hypot(dx, dy)
        seg_n.append((-dy / L, dx / L) if L > 1e-9 else (0.0, 0.0))

    normals = []
    for i in range(n):
        a = seg_n[max(i - 1, 0)]
        b = seg_n[min(i + 1, n - 1)]
        sx, sy = a[0] + b[0], a[1] + b[1]
        L = math.hypot(sx, sy)
        if L < 1e-9:
            # Exact 180-degree reversal: the two segments cancel. Fall back to
            # the incoming normal rather than an arbitrary axis.
            normals.append(a if (a[0] or a[1]) else (0.0, 1.0))
        else:
            mx, my = sx / L, sy / L
            # Miter length compensation: without it the strip pinches on the
            # inside of a corner. Clamped so a hairpin cannot explode the width.
            cos_half = math.hypot(a[0] + b[0], a[1] + b[1]) / 2.0
            scale = 1.0 / max(cos_half, 0.25)
            normals.append((mx * scale, my * scale))

    for i in range(n):
        pt = pts[i]
        curr_x, curr_y = pt["x"], pt["y"]
        nx, ny = normals[i]

        verts.append((curr_x + nx * half_w, curr_y + ny * half_w, z_lift))
        verts.append((curr_x - nx * half_w, curr_y - ny * half_w, z_lift))

        val = float(pt.get(metric_key) or min_db)
        if metric_key == "power_w":
            col = _lut_rgb(val, min_db, max_db, VIRIDIS_ANCHORS)
        else:
            col = acoustic_to_rgb(val, min_db, max_db)
        pt_colors.append(col)
        pt_colors.append(col)

        if i > 0:
            # Quad face connecting (2*i-2, 2*i-1, 2*i+1, 2*i)
            idx = 2 * i
            faces.append((idx - 2, idx - 1, idx + 1, idx))

    if dropped:
        print(f"[Arena Blender Viz] Ribbon: dropped {dropped} stationary point(s), "
              f"{n} remain (min step {MIN_STEP:.4f} m)", flush=True)

    mesh_data = bpy.data.meshes.new("robot_trajectory_mesh")
    mesh_data.from_pydata(verts, [], faces)
    mesh_data.update()

    # Apply Vertex Color layer (bulk write instead of per-vertex assignment)
    color_attr = mesh_data.color_attributes.new(name="Col", type="FLOAT_COLOR", domain="POINT")
    color_attr.data.foreach_set(
        "color", np.asarray(pt_colors, dtype=np.float32).ravel()
    )

    curve_obj = bpy.data.objects.new("robot_trajectory", mesh_data)
    col_trajectories.objects.link(curve_obj)

    # Trajectory Emission Material with Vertex Colors
    mat_traj = bpy.data.materials.new("Mat_Trajectory_Acoustic")
    mat_traj.use_nodes = True
    nodes = mat_traj.node_tree.nodes
    links = mat_traj.node_tree.links
    nodes.clear()

    vcol = nodes.new("ShaderNodeVertexColor")
    vcol.layer_name = "Col"

    em = nodes.new("ShaderNodeEmission")
    em.inputs["Strength"].default_value = 1.5

    out = nodes.new("ShaderNodeOutputMaterial")

    links.new(vcol.outputs["Color"], em.inputs["Color"])
    links.new(em.outputs["Emission"], out.inputs["Surface"])
    curve_obj.data.materials.append(mat_traj)

# --show-energy-glow: the trajectory ribbon IS the glow.
#
# This used to build two flanking lanes (viridis power on the left, inferno
# acoustic on the right). They read as two unrelated bands rather than a glow,
# and they inherited the ribbon's offset-normal bug multiplicatively, so they
# were removed. The glow is now the ribbon itself: one emissive strip coloured
# by --glow-metric (default acoustic), brightened so it reads as a light source.
if robot_traj and options.get("show_energy_glow", False):
    traj_mat = bpy.data.materials.get("Mat_Trajectory_Acoustic")
    if traj_mat and traj_mat.use_nodes:
        for _n in traj_mat.node_tree.nodes:
            if _n.type == "EMISSION":
                _n.inputs["Strength"].default_value = float(
                    options.get("glow_strength") or _GLOW_STRENGTH
                )
    print(
        f"[Arena Blender Viz] Energy glow: trajectory ribbon coloured by "
        f"'{glow_metric}' ({min_db:.0f}-{max_db:.0f}), emission strength "
        f"{float(options.get('glow_strength') or _GLOW_STRENGTH):.1f}",
        flush=True,
    )

# Robot actor: loaded and keyframed independently of the energy-glow trails, so
# the Jackal is present in every build. This block used to sit inside the
# `show_energy_glow` guard above, which defaults to False and therefore silently
# dropped the robot from the saved .blend.
if robot_traj:
    # Load authentic Jackal UGV robot model or high-contrast procedural robot
    worst_frame = telemetry.get("worst_case_frame")
    jackal_glb = model_glbs.get("robot/jackal")
    if not jackal_glb or not _path_exists(jackal_glb):
        base_dir = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
        for cand in (
            Path("/opt/arena_ws/data/blender_cache/glb/jackal_robot.glb"),
            Path(bundle_path).parent / ".cache" / "glb" / "jackal_robot.glb",
            Path(base_dir) / ".cache" / "glb" / "jackal_robot.glb",
        ):
            if _path_exists(str(cand)):
                jackal_glb = str(cand)
                break

    robot_obj = None
    if jackal_glb and _path_exists(jackal_glb):
        print(f"[Arena Blender Viz] Loading authentic Clearpath Jackal UGV model: {jackal_glb}", flush=True)
        try:
            bpy.ops.import_scene.gltf(filepath=jackal_glb)
            imported_objs = list(bpy.context.selected_objects)
            robot_root = bpy.data.objects.new("Robot_Jackal", None)
            col_actors.objects.link(robot_root)
            for io in imported_objs:
                io.parent = robot_root
                # The glTF importer links into the scene root; re-home the
                # imported meshes into Actors and clear every other collection
                # so only the "Actors" collection governs their visibility.
                for c in list(io.users_collection):
                    c.objects.unlink(io)
                col_actors.objects.link(io)
                io.hide_render = False
                io.hide_viewport = False
            robot_obj = robot_root
        except Exception as e:
            print(f"[!] Failed to import jackal glb: {e}")

    if robot_obj is None:
        bpy.ops.mesh.primitive_cube_add(size=0.45, location=(0, 0, 0.18))
        robot_obj = bpy.context.active_object
        robot_obj.name = "Robot_Jackal"
        for c in list(robot_obj.users_collection):
            c.objects.unlink(robot_obj)
        col_actors.objects.link(robot_obj)
        mat_robot = create_pbr_material("Mat_Robot_Jackal", color=(1.0, 0.72, 0.0, 1.0), roughness=0.3)
        robot_obj.data.materials.append(mat_robot)
        print("[Arena Blender Viz] Jackal GLB unavailable; using procedural cube stand-in.", flush=True)

    # Initial resting pose: position directly at worst-case acoustic source hotspot if present
    if worst_frame and worst_frame.get("robot_x") is not None:
        rx = worst_frame["robot_x"]
        ry = worst_frame["robot_y"]
        ryaw = worst_frame.get("robot_yaw", 0.0)
        print(f"[Arena Blender Viz] Setting robot to worst acoustic frame pose: ({rx:.2f}, {ry:.2f}, yaw={ryaw:.2f})", flush=True)
        robot_obj.location = (rx, ry, 0.0)
        robot_obj.rotation_euler = (0.0, 0.0, ryaw)
    else:
        robot_obj.location = (robot_traj[0]["x"], robot_traj[0]["y"], 0.0)
        robot_obj.rotation_euler = (0.0, 0.0, robot_traj[0].get("yaw", 0.0))

    # Keyframe robot position and yaw along recorded simulation trajectory with unwrapped heading
    r_ts = np.array([pt["t"] for pt in robot_traj])
    r_xs = np.array([pt["x"] for pt in robot_traj])
    r_ys = np.array([pt["y"] for pt in robot_traj])
    r_yaws = np.unwrap(np.array([pt.get("yaw", 0.0) for pt in robot_traj]))

    frames_arr = np.arange(1, scene.frame_end + 1, dtype=np.float64)
    target_times = (frames_arr - 1.0) / fps
    r_interp_xs = np.interp(target_times, r_ts, r_xs)
    r_interp_ys = np.interp(target_times, r_ts, r_ys)
    r_interp_yaws = np.interp(target_times, r_ts, r_yaws)

    if static_mode:
        # Pose at the frozen instant; indexing the same interpolated arrays the
        # animated build keys from guarantees the still matches that frame.
        idx = int(min(max(static_target_frame, 1), len(frames_arr))) - 1
        robot_obj.location = (float(r_interp_xs[idx]), float(r_interp_ys[idx]), 0.0)
        robot_obj.rotation_euler = (0.0, 0.0, float(r_interp_yaws[idx]))
    else:
        # Bulk keyframe write (see write_fcurves): robot_obj is an Empty, so its
        # rotation mode is the default XYZ and rotation_euler is the right channel.
        write_fcurves(
            new_channelbag(f"{robot_obj.name}_action", robot_obj, "OBJECT"),
            frames_arr,
            [
                ("location", 0, r_interp_xs),
                ("location", 1, r_interp_ys),
                ("location", 2, np.zeros_like(r_interp_xs)),
                ("rotation_euler", 0, np.zeros_like(r_interp_yaws)),
                ("rotation_euler", 1, np.zeros_like(r_interp_yaws)),
                ("rotation_euler", 2, r_interp_yaws),
            ],
        )

    # Activate the worst-case acoustic timeline frame by default
    if worst_frame and worst_frame.get("frame"):
        wf_idx = worst_frame["frame"]
        scene.frame_set(wf_idx)
        print(f"[Arena Blender Viz] Activated timeline frame {wf_idx} (worst acoustic emission frame)", flush=True)


stage("7 robot ribbon + animation")

# -----------------------------------------------------------------------------
# 8. Dynamic Pedestrians & Encounter Discs (Skinned Animation & Walking Strides)
# -----------------------------------------------------------------------------
peds_frames = telemetry.get("pedestrians", [])
if peds_frames and options.get("animate_peds", True):
    print(f"[Arena Blender Viz] Animating dynamic pedestrians across {len(peds_frames)} frames...", flush=True)
    # Gather pedestrian IDs
    ped_ids = sorted(list({p["id"] for fr in peds_frames for p in fr.get("peds", [])}), key=str)

    # Resolve human 3D mesh assets (natural idle stance + walk cycle phases)
    # The model converter caches GLBs under the workspace data dir
    # (data/blender_cache/glb); the walk-phase GLBs live there flat, so derive
    # the cache dir from any resolved model path before falling back.
    cache_glb_dir = Path(bundle_path).parent / ".cache" / "glb"
    # Content-based resolution (order-independent): pick the first directory
    # that actually holds the arenian idle/walk assets. Model paths are either
    # <cache>/<Category>_<Model>.glb (flat) or <cache>/<Category>/<Model>.glb
    # (nested), so both parent and parent.parent are probed.
    if not (_path_exists(str(cache_glb_dir / "Common_arenian_idle.glb")) or _path_exists(str(cache_glb_dir / "Common_arenian_walk_0.glb"))):
        for cand in [
            *(Path(p).parent for p in model_glbs.values() if isinstance(p, str) and p),
            *(Path(p).parent.parent for p in model_glbs.values() if isinstance(p, str) and p),
            Path(__file__).resolve().parent.parent / ".cache" / "glb",
            Path("/opt/arena_ws/data/blender_cache/glb"),
            Path("/opt/arena_ws/src/Arena/arena_blender_viz/.cache/glb"),
            Path("u:/src/Arena/arena_blender_viz/.cache/glb"),
        ]:
            if _path_exists(str(cand / "Common_arenian_idle.glb")) or _path_exists(str(cand / "Common_arenian_walk_0.glb")):
                cache_glb_dir = cand
                break

    idle_glb = str(cache_glb_dir / "Common_arenian_idle.glb")
    if not _path_exists(idle_glb):
        idle_glb = (
            model_glbs.get("Common/Human/arenian")
            or model_glbs.get("arenian")
            or model_glbs.get("Common_arenian")
            or str(cache_glb_dir / "Common_arenian.glb")
        )

    seated_glb = str(cache_glb_dir / "Common_arenian_seated.glb")
    if not _path_exists(seated_glb):
        for cand_s in [
            cache_glb_dir / "Common_Human" / "arenian_seated.glb",
            cache_glb_dir / "arenian_seated.glb",
        ]:
            if _path_exists(str(cand_s)):
                seated_glb = str(cand_s)
                break
        if not _path_exists(seated_glb):
            seated_glb = (
                model_glbs.get("Common/Human/arenian_seated")
                or model_glbs.get("arenian_seated")
                or model_glbs.get("Common_arenian_seated")
                or ""
            )

    walk_glbs = [str(cache_glb_dir / f"Common_arenian_walk_{i}.glb") for i in range(4)]
    has_walk_glbs = all(_path_exists(w) for w in walk_glbs)

    human_prefab = None
    if idle_glb and os.path.isfile(idle_glb):
        if idle_glb not in loaded_prefabs:
            bpy.ops.import_scene.gltf(filepath=idle_glb)
            imported_objs = [o for o in bpy.context.selected_objects if o.type == "MESH"]
            root_empty = bpy.data.objects.new("Prefab_Human_Arenian", None)
            root_empty.location = (0.0, 0.0, -1000.0)
            root_empty.hide_render = True
            root_empty.hide_viewport = True
            col_prefabs.objects.link(root_empty)
            for o in imported_objs:
                o.parent = root_empty
                o.hide_render = True
                o.hide_viewport = True
                for c in list(o.users_collection):
                    c.objects.unlink(o)
                col_prefabs.objects.link(o)

            # Build multi-phase walking shape keys on human prefab
            if has_walk_glbs:
                print(f"[Arena Blender Viz] Building 4-phase walking shape keys on human prefab...", flush=True)
                for w_idx, w_path in enumerate(walk_glbs):
                    bpy.ops.import_scene.gltf(filepath=w_path)
                    w_objs = [o for o in bpy.context.selected_objects if o.type == "MESH"]
                    for io, wo in zip(imported_objs, w_objs):
                        if not io.data.shape_keys:
                            io.shape_key_add(name="Idle")
                        sk = io.shape_key_add(name=f"Walk_{w_idx}")
                        # Read the phase coordinates straight into a numpy buffer.
                        # A Python nested comprehension here extracts ~1.7M floats
                        # across the four phases and showed up as ~1s of build time.
                        n_co = len(wo.data.vertices) * 3
                        coords = np.empty(n_co, dtype=np.float32)
                        wo.data.vertices.foreach_get("co", coords)
                        sk.data.foreach_set("co", coords)
                    for wo in w_objs:
                        bpy.data.objects.remove(wo, do_unlink=True)
                print(f"[Arena Blender Viz] Successfully loaded {len(walk_glbs)} walk phases onto human prefab.", flush=True)

            loaded_prefabs[idle_glb] = root_empty
        human_prefab = loaded_prefabs[idle_glb]
        print(f"[Arena Blender Viz] Loaded 3D pedestrian standing prefab from: {idle_glb}", flush=True)

    # Also build seated prefab if available
    seated_prefab = None
    if seated_glb and os.path.isfile(seated_glb):
        if seated_glb not in loaded_prefabs:
            bpy.ops.import_scene.gltf(filepath=seated_glb)
            imported_s_objs = [o for o in bpy.context.selected_objects if o.type == "MESH"]
            root_s_empty = bpy.data.objects.new("Prefab_Human_Arenian_Seated", None)
            root_s_empty.location = (0.0, 0.0, -1000.0)
            root_s_empty.hide_render = True
            root_s_empty.hide_viewport = True
            col_prefabs.objects.link(root_s_empty)
            for o in imported_s_objs:
                o.parent = root_s_empty
                o.hide_render = True
                o.hide_viewport = True
                for c in list(o.users_collection):
                    c.objects.unlink(o)
                col_prefabs.objects.link(o)
            loaded_prefabs[seated_glb] = root_s_empty
        seated_prefab = loaded_prefabs[seated_glb]
        print(f"[Arena Blender Viz] Loaded 3D pedestrian seated prefab from: {seated_glb}", flush=True)

    stage("8a ped prefab import (+walk shape keys)")

    ped_model_map = telemetry.get("pedestrian_models", {})
    ped_objs = {}
    for pid in ped_ids:
        # Determine if this pedestrian is seated
        req_model = ped_model_map.get(str(pid), "")
        is_seated = "seated" in req_model or "sitting" in req_model
        active_prefab = seated_prefab if (is_seated and seated_prefab) else human_prefab

        if active_prefab:
            # Instantiate 3D realistic human mesh (seated or standing)
            p_root = bpy.data.objects.new(f"Pedestrian_{pid}", None)
            col_actors.objects.link(p_root)
            # NOTE: unlike furniture, pedestrians must own their mesh data.
            # The walk cycle is driven by shape-key *values*, and shape keys live
            # on the mesh datablock -- sharing them (dupe.data = child.data) would
            # make every pedestrian march in lockstep. Counts are small (tens), so
            # the private copies are cheap.
            for child in active_prefab.children:
                dupe = child.copy()
                dupe.data = child.data.copy()
                dupe.parent = p_root
                dupe.hide_render = False
                dupe.hide_viewport = False
                col_actors.objects.link(dupe)
            p_obj = p_root
            p_obj["is_seated"] = bool(active_prefab == seated_prefab)
        else:
            # Fallback cylinder proxy
            bpy.ops.mesh.primitive_cylinder_add(radius=0.25, depth=1.7, location=(0, 0, 0.85))
            p_obj = bpy.context.active_object
            p_obj.name = f"Pedestrian_{pid}"
            col_actors.objects.link(p_obj)
            scene.collection.objects.unlink(p_obj)
            mat_ped = create_pbr_material(f"Mat_Ped_{pid}", color=(0.85, 0.45, 0.2, 1.0), roughness=0.6)
            p_obj.data.materials.append(mat_ped)
            p_obj["is_seated"] = False

        ped_objs[pid] = p_obj

    stage("8b ped instancing")

    # Keyframe pedestrian movements and stride animations
    # Group trajectories by pedestrian ID for clean, continuous interpolation
    from collections import defaultdict
    ped_raw_trajs = defaultdict(list)
    for fr in peds_frames:
        t_curr = fr["t"]
        for p in fr.get("peds", []):
            ped_raw_trajs[p["id"]].append((t_curr, p["x"], p["y"], p.get("yaw", 0.0)))

    frames_arr = np.arange(1, scene.frame_end + 1, dtype=np.float64)
    target_times = (frames_arr - 1.0) / fps

    for pid in ped_ids:
        if pid not in ped_objs:
            continue
        p_obj = ped_objs[pid]
        raw_pts = ped_raw_trajs.get(pid, [])
        if not raw_pts:
            continue

        raw_ts = np.array([pt[0] for pt in raw_pts])
        raw_xs = np.array([pt[1] for pt in raw_pts])
        raw_ys = np.array([pt[2] for pt in raw_pts])
        raw_yaws = np.unwrap(np.array([pt[3] for pt in raw_pts]))

        # Calculate cumulative distance along path
        if len(raw_pts) > 1:
            step_dists = np.sqrt(np.diff(raw_xs) ** 2 + np.diff(raw_ys) ** 2)
            cum_dists = np.concatenate([[0.0], np.cumsum(step_dists)])
        else:
            cum_dists = np.array([0.0])
        total_dist = cum_dists[-1]

        z_pos = 0.0 if human_prefab else 0.85

        if total_dist < 0.3:
            # Stationary observer / patron: stay motionless at starting anchor in natural Idle stance
            p_obj.location = (float(raw_xs[0]), float(raw_ys[0]), z_pos)
            p_obj.rotation_euler = (0.0, 0.0, float(raw_yaws[0]))
            if static_mode:
                # Pose is set; walk shape keys already default to 0.0 (idle).
                pass
            else:
                p_obj.keyframe_insert(data_path="location", frame=1)
                p_obj.keyframe_insert(data_path="rotation_euler", frame=1)
                p_obj.keyframe_insert(data_path="location", frame=scene.frame_end)
                p_obj.keyframe_insert(data_path="rotation_euler", frame=scene.frame_end)

                if human_prefab and p_obj.children:
                    for child in p_obj.children:
                        if child.data and child.data.shape_keys:
                            kb = child.data.shape_keys.key_blocks
                            for k in range(4):
                                k_name = f"Walk_{k}"
                                if k_name in kb:
                                    kb[k_name].value = 0.0
                                    kb[k_name].keyframe_insert(data_path="value", frame=1)
                                    kb[k_name].keyframe_insert(data_path="value", frame=scene.frame_end)
        else:
            # Active walking pedestrian: interpolate continuous, smooth trajectory and stride cycle
            interp_xs = np.interp(target_times, raw_ts, raw_xs)
            interp_ys = np.interp(target_times, raw_ts, raw_ys)
            interp_yaws = np.interp(target_times, raw_ts, raw_yaws)
            interp_s = np.interp(target_times, raw_ts, cum_dists)

            n_frames = len(frames_arr)

            if static_mode:
                # Freeze mid-stride: same arrays the animated build keys from, so
                # the pose matches that frame exactly (including the stride blend).
                _idx = int(min(max(static_target_frame, 1), n_frames)) - 1
                p_obj.location = (float(interp_xs[_idx]), float(interp_ys[_idx]), z_pos)
                p_obj.rotation_euler = (0.0, 0.0, float(interp_yaws[_idx]))

                _s = float(interp_s[_idx])
                _pv = ((_s / 1.151) % 1.0) * 4.0
                _i0 = int(_pv) % 4
                _i1 = (_i0 + 1) % 4
                _w1 = _pv - int(_pv)
                _w0 = 1.0 - _w1
                for child in p_obj.children:
                    if child.data and child.data.shape_keys:
                        kb = child.data.shape_keys.key_blocks
                        for k in range(4):
                            k_name = f"Walk_{k}"
                            if k_name in kb:
                                kb[k_name].value = (
                                    _w0 if k == _i0 else (_w1 if k == _i1 else 0.0)
                                )
                continue

            # Bulk keyframe the root transform in one pass.
            write_fcurves(
                new_channelbag(f"{p_obj.name}_action", p_obj, "OBJECT"),
                frames_arr,
                [
                    ("location", 0, interp_xs),
                    ("location", 1, interp_ys),
                    ("location", 2, np.full(n_frames, z_pos)),
                    ("rotation_euler", 0, np.zeros(n_frames)),
                    ("rotation_euler", 1, np.zeros(n_frames)),
                    ("rotation_euler", 2, interp_yaws),
                ],
            )

            if not (human_prefab and p_obj.children):
                continue

            # Stride-phase blend weights, vectorised. 1.151m per full 4-phase
            # cycle; each frame blends the two adjacent walk phases. interp_s is
            # non-negative, so truncation and floor agree.
            STRIDE_LEN = 1.151
            p_val = ((interp_s / STRIDE_LEN) % 1.0) * 4.0
            idx0 = p_val.astype(np.int64) % 4
            idx1 = (idx0 + 1) % 4
            w1 = p_val - np.floor(p_val)
            w0 = 1.0 - w1
            walk_vals = np.zeros((n_frames, 4), dtype=np.float64)
            for k in range(4):
                walk_vals[:, k] = np.where(k == idx0, w0, np.where(k == idx1, w1, 0.0))

            # Each skinned child owns its shape keys, so each needs its own action
            # on the shape-key datablock (id_type "KEY").
            for child in p_obj.children:
                shape_keys = child.data.shape_keys if child.data else None
                if not shape_keys:
                    continue
                kb = shape_keys.key_blocks
                curves = [
                    (f'key_blocks["Walk_{k}"].value', 0, walk_vals[:, k])
                    for k in range(4)
                    if f"Walk_{k}" in kb
                ]
                if curves:
                    write_fcurves(
                        new_channelbag(f"{child.name}_shapekeys", shape_keys, "KEY", "ShapeKey"),
                        frames_arr,
                        curves,
                    )


    stage("8c ped keyframing")

# Encounters Discs (r = 1.2m) - optional overlay
encounters = telemetry.get("encounters", [])
if encounters and options.get("show_encounters", False):
    mat_enc = create_pbr_material("Mat_Encounter", color=(0.95, 0.2, 0.15, 0.35), roughness=0.5)
    for i, enc in enumerate(encounters):
        pos = enc["ped_pos"]
        bpy.ops.mesh.primitive_cylinder_add(radius=1.2, depth=0.01, location=(pos["x"], pos["y"], 0.02))
        enc_obj = bpy.context.active_object
        enc_obj.name = f"encounter_zone_{i}"
        enc_obj.data.materials.append(mat_enc)
        col_overlays.objects.link(enc_obj)
        scene.collection.objects.unlink(enc_obj)

stage("8 pedestrians")

# -----------------------------------------------------------------------------
# 9. Camera Presets (Auto-scaled to World Bounds with Aspect Ratio Padding)
# -----------------------------------------------------------------------------
cx = (min_x + max_x) / 2.0
cy = (min_y + max_y) / 2.0
span_x = max(max_x - min_x, 1.0)
span_y = max(max_y - min_y, 1.0)
max_dim = max(span_x, span_y)

res_x = scene.render.resolution_x
res_y = scene.render.resolution_y
aspect = res_x / res_y  # e.g. 2148 / 1400 ≈ 1.534

# Aspect ratio aware orthographic scale:
# In Blender, ortho_scale controls the horizontal dimension in landscape.
# Visible width = ortho_scale, Visible height = ortho_scale / aspect.
# To ensure visible_width >= span_x * margin AND visible_height >= span_y * margin:
#   ortho_scale = max(span_x * margin, span_y * margin * aspect)
margin = 1.35
auto_ortho_scale = max(span_x * margin, span_y * margin * aspect)
print(f"[Arena Blender Viz] Camera auto-scale: span_x={span_x:.1f}m, span_y={span_y:.1f}m, ortho_scale={auto_ortho_scale:.2f}", flush=True)

def add_camera(name, location, rotation, cam_type="PERSP", lens=35, ortho_scale=30.0, is_active=False):
    cam_data = bpy.data.cameras.new(name)
    cam_data.type = cam_type
    if cam_type == "ORTHO":
        cam_data.ortho_scale = ortho_scale
    else:
        cam_data.lens = lens

    cam_obj = bpy.data.objects.new(name, cam_data)
    cam_obj.location = location
    cam_obj.rotation_euler = rotation
    col_cameras.objects.link(cam_obj)
    if is_active:
        scene.camera = cam_obj
    return cam_obj

# 1. Full top-down orthographic (both Cam_TopDown and Cam_TopDown_Full for CLI compatibility)
add_camera(
    "Cam_TopDown",
    location=(cx, cy, max_dim * 2.0),
    rotation=(0, 0, 0),
    cam_type="ORTHO",
    ortho_scale=auto_ortho_scale,
    is_active=True,
)
add_camera(
    "Cam_TopDown_Full",
    location=(cx, cy, max_dim * 2.0),
    rotation=(0, 0, 0),
    cam_type="ORTHO",
    ortho_scale=auto_ortho_scale,
)

# 2. Focused ward top-down
add_camera(
    "Cam_TopDown_Ward",
    location=(6.0, 20.0, 25.0),
    rotation=(0, 0, 0),
    cam_type="ORTHO",
    ortho_scale=22.0,
)

# 3. 3/4 Hero perspective auto-framed to world bounds
hero_dist = max_dim * 1.15
add_camera(
    "Cam_3Quarter_Hero",
    location=(cx - hero_dist * 0.55, cy - hero_dist * 0.72, hero_dist * 0.70),
    rotation=(math.radians(54), 0, math.radians(-38)),
    cam_type="PERSP",
    lens=32,
)

# 4. Corridor Eye-Level
add_camera(
    "Cam_Corridor_EyeLevel",
    location=(10.0, 2.0, 1.4),
    rotation=(math.radians(85), 0, math.radians(180)),
    cam_type="PERSP",
    lens=40,
)

stage("9 cameras")

# -----------------------------------------------------------------------------
# 10. Lighting (High-Contrast Architectural Lighting — Soft Depth Shadows & Clear Corners)
# -----------------------------------------------------------------------------
# 1. Subtle Ambient World Fill (reduced to 0.16 for rich, readable shadow depth)
world = scene.world
if not world:
    world = bpy.data.worlds.new("World")
    scene.world = world
world.use_nodes = True
bg = world.node_tree.nodes.get("Background")
if bg:
    bg.inputs["Color"].default_value = (0.90, 0.93, 0.96, 1.0)
    bg.inputs["Strength"].default_value = 0.25

# 2. Angled Architectural Key Light (casts soft, crisp 0.5m drop shadows from walls)
key_data = bpy.data.lights.new("ArchitecturalKeyLight", type="SUN")
key_data.energy = 4.5
key_data.angle = math.radians(12)  # Soft shadow boundary
key_data.color = (1.0, 0.98, 0.95)
key_obj = bpy.data.objects.new("ArchitecturalKeyLight", key_data)
# 32 degrees from zenith, 24 degrees azimuth
key_obj.rotation_euler = (math.radians(-32), math.radians(24), 0)
col_lighting.objects.link(key_obj)

# 2b. Skylight Sun (soft slightly-angled skylight brightening the whole scene,
#     complementary azimuth to the key light so shadows stay readable)
sky_data = bpy.data.lights.new("SkylightSun", type="SUN")
sky_data.energy = 2.5
sky_data.angle = math.radians(30)  # Very soft shadow boundary
sky_data.color = (0.88, 0.94, 1.0)
sky_obj = bpy.data.objects.new("SkylightSun", sky_data)
# 52 degrees from zenith, -68 degrees azimuth
sky_obj.rotation_euler = (math.radians(-52), math.radians(-68), 0)
col_lighting.objects.link(sky_obj)

# 2c. Shadowless Bounce Fill (from the opposite azimuth to both suns)
#     Both suns sit on the +Y side (key from +X+Y, sky from -X+Y), so every
#     wall whose normal faces -Y receives no direct light from either and reads
#     as pure black. Ambient world light cannot rescue those surfaces: the same
#     geometry that shadows them also occludes the sky, so raising world
#     strength lifts the midtones but leaves the black tail untouched
#     (measured: 7.6% of wall pixels < 16/255 at world 0.25, still 7.3% at
#     0.85). A shadowless fill is what reaches occluded surfaces -- it drops
#     that to 3.0% while keeping directional contrast. Shadowless is the point:
#     a shadow-casting fill would be blocked by the very walls it must light.
_FILL_LIGHT_W = float(options.get("fill_light_strength")
                      if options.get("fill_light_strength") is not None
                      else _FILL_LIGHT_DEFAULT_W)
fill_data = bpy.data.lights.new("BounceFillLight", type="SUN")
fill_data.energy = _FILL_LIGHT_W
fill_data.angle = math.radians(45)  # Very soft, diffuse bounce character
fill_data.color = (0.93, 0.95, 1.0)
fill_data.use_shadow = False  # Deliberate: fills geometry the suns cannot reach
fill_obj = bpy.data.objects.new("BounceFillLight", fill_data)
# 45 degrees elevation, from -Y: travel direction (0, +0.707, -0.707)
fill_obj.rotation_euler = (math.radians(-45), 0, math.radians(180))
col_lighting.objects.link(fill_obj)

# 3. Soft Zenith Area Fill Light (fills room interiors from above)
zen_data = bpy.data.lights.new("ZenithFillLight", type="AREA")
zen_data.shape = "RECTANGLE"
zen_data.size = span_x * 1.1
zen_data.size_y = span_y * 1.1
zen_data.energy = 220.0
zen_data.color = (0.96, 0.98, 1.0)
zen_obj = bpy.data.objects.new("ZenithFillLight", zen_data)
zen_obj.location = (cx, cy, 11.0)
zen_obj.rotation_euler = (0, 0, 0)
col_lighting.objects.link(zen_obj)

# 3. Zone-based Interior Ceiling Downlights (realistic architectural lighting)
for z in world_data.get("zones", []):
    z_name = z.get("name", "zone")
    corners = z.get("corners", [])
    if not corners:
        continue
    z_cx = sum(c["x"] for c in corners) / len(corners)
    z_cy = sum(c["y"] for c in corners) / len(corners)
    z_min_x = min(c["x"] for c in corners)
    z_max_x = max(c["x"] for c in corners)
    z_min_y = min(c["y"] for c in corners)
    z_max_y = max(c["y"] for c in corners)
    w = max(1.0, z_max_x - z_min_x)
    h = max(1.0, z_max_y - z_min_y)

    l_data = bpy.data.lights.new(f"Light_{z_name}", type="AREA")
    l_data.shape = "RECTANGLE"
    l_data.size = min(w * 0.7, 6.0)
    l_data.size_y = min(h * 0.7, 6.0)
    l_data.energy = 80.0 + 15.0 * (w * h) ** 0.5
    l_data.color = (1.0, 0.98, 0.95) if ("patient" in z_name or "resting" in z_name) else (0.96, 0.98, 1.0)
    l_obj = bpy.data.objects.new(f"Light_{z_name}", l_data)
    l_obj.location = (z_cx, z_cy, 2.35)
    l_obj.rotation_euler = (0, 0, 0)
    col_lighting.objects.link(l_obj)

stage("10 lighting")

# -----------------------------------------------------------------------------
# 11. Render Settings (Cycles GPU, 300 DPI ICRA Format)
# -----------------------------------------------------------------------------
scene.render.engine = "CYCLES"
try:
    scene.cycles.device = "GPU"
    prefs = bpy.context.preferences.addons["cycles"].preferences
    prefs.compute_device_type = "OPTIX"
    prefs.get_devices()
    for d in prefs.devices:
        d.use = True
except Exception:
    scene.cycles.device = "CPU"

scene.cycles.samples = 128
scene.cycles.use_denoising = True
try:
    scene.cycles.use_fast_gi = True
except Exception:
    pass
scene.render.film_transparent = True

# Resolution for ICRA (double column: ~7.16 inches at 300 DPI = 2148 x 1400)
scene.render.resolution_x = 2148
scene.render.resolution_y = 1400
scene.render.resolution_percentage = 100

# Color Management: Use 'Standard' view transform for scientific false-color heatmap fidelity
if acoustic_overlay and acoustic_overlay.get("png_path"):
    scene.view_settings.view_transform = "Standard"

stage("11 render settings (incl. Cycles device init)")

# -----------------------------------------------------------------------------
# 12. Save Scene
# -----------------------------------------------------------------------------
# Ensure timeline is evaluated at active / worst-case frame upon saving
worst_frame = telemetry.get("worst_case_frame")
if worst_frame and worst_frame.get("frame"):
    scene.frame_set(int(worst_frame["frame"]))

# Static builds collapse the timeline onto the frozen frame. Doing this last keeps
# the pose arrays (built from the full timeline above) intact, and it pins the
# acoustic MOVIE texture -- which is frame-driven -- to the matching frame.
if static_mode:
    scene.frame_start = static_target_frame
    scene.frame_end = static_target_frame
    scene.frame_set(static_target_frame)
    n_actions = len(bpy.data.actions)
    print(
        f"[Arena Blender Viz] Static build: timeline pinned to frame {static_target_frame} "
        f"(actions in file: {n_actions})",
        flush=True,
    )

out_blend = Path(out_blend_path).resolve()
out_blend.parent.mkdir(parents=True, exist_ok=True)

# Build output is a generated artifact: skip Blender's .blend1 backup (a full
# duplicate write of a multi-hundred-MB file) and compress, since the geometry
# is highly repetitive.
try:
    bpy.context.preferences.filepaths.save_version = 0
except Exception:
    pass
bpy.ops.wm.save_as_mainfile(filepath=str(out_blend), compress=True)
print(f"[Arena Blender Viz] Successfully saved Blender scene to: {out_blend}", flush=True)
stage("12 save")

scene_scale("FINAL")
if os.path.isfile(out_blend):
    print(
        f"[Arena Blender Viz] .blend size: {os.path.getsize(out_blend) / 1e6:.1f} MB",
        flush=True,
    )
print(f"[Arena Blender Viz] Total build time: {time.perf_counter() - _T0:.1f}s", flush=True)
