# Arena Blender Visualization Pipeline (`arena_blender_viz`)

The `arena_blender_viz` package provides an automated, publication-quality 3D visualization and rendering pipeline for the **Arena Evaluation 3.0** robotics simulation platform. It bridges Arena benchmark telemetry (trajectories, obstacle encounters, power consumption, dynamic door states, and acoustic propagation fields) into production-grade Blender scenes rendered with Cycles (OptiX GPU acceleration).

---

## 1. System Requirements & Setup

- **Operating System**: Windows 11 / Linux (WSL2 supported)
- **Blender**: Blender 5.0+ (Tested on Blender 5.2 LTS, `C:\Program Files\Blender Foundation\Blender 5.2\blender.exe`)
- **Python**: Python 3.10+
- **GPU**: NVIDIA RTX GPU with OptiX support recommended for accelerated path-tracing.

### Installation

Install the package in editable mode from the repository root:

```bash
cd /path/to/arena_blender_viz
pip install -e .
```

Once installed, the CLI executable `arena-blender-viz` is available in your environment, or you can invoke it directly via Python:

```bash
python -m arena_blender_viz.cli <command> [options]
```

---

## 2. CLI Commands Reference

The CLI provides four primary subcommands:
1. `arena-blender-viz build` — Assembles a complete 3D `.blend` scene from `world.yaml` and benchmark episode telemetry.
2. `arena-blender-viz render` — Headless rendering from calibrated camera presets with OptiX GPU acceleration.
3. `arena-blender-viz animate` — Renders an animation frame sequence and muxes it to MP4.
4. `arena-blender-viz hud` — Generates publication telemetry HUD cards, colorbars, and overlays them onto renders.

```
usage: arena-blender-viz [-h] {build,render,animate,hud} ...
```

---

### Command: `build`

Builds a self-contained `.blend` scene file and intermediate `_bundle.json` by combining architectural geometry (`world.yaml`), 3D furniture models, animated actors, robot trajectories, door timelines, and acoustic field textures.

```bash
arena-blender-viz build --world <world> [options]
```

#### Arguments & Options

| Option | Type | Default | Description |
|---|---|---|---|
| `--world` | `str` | **Required** | World name (e.g. `hospital_1`, `library_acoustic_partition`) or direct path to `world.yaml`. |
| `--benchmark` | `str` | `None` | Benchmark run folder name or path under `u:/data/benchmarks/`. |
| `--episode` | `str` | `None` | Episode identifier (e.g. `040`, `episode_040`). Defaults to first episode found. |
| `--acoustic-overlay` | `path` | Auto | Path to acoustic heatmap image (`.png`) or dynamic video (`.mp4`). If omitted and `--acoustic` is enabled, auto-resolves from benchmark `plots/`. |
| `--acoustic` | `flag` | `False` | Enables physical sound field mapping on floor geometry. |
| `--acoustic-mode` | `choice` | `plain` | Visual style: `plain` (accurate non-reflective matte picture), `subtle` (soft ambient bounce), `glow` (high-visibility emission), `additive` (white architectural floor with the field overlaid only where non-black). |
| `--output`, `-o` | `path` | `<world>.blend` | Destination `.blend` scene file. |
| `--no-animate-doors` | `flag` | `False` | Disables dynamic sliding door animation keyframes (keeps doors open). |
| `--no-animate-peds` | `flag` | `False` | Disables dynamic pedestrian animation keyframing. |
| `--static` | `flag` | `False` | **Static-frame build.** Poses the robot, doors and pedestrians at a single instant and emits **no animation data at all**, so the `.blend` is directly editable in the GUI for composing a still image. Defaults to the worst-case acoustic frame; use `--frame`/`--time` to freeze elsewhere (falls back to the trajectory midpoint, then frame 1). Pedestrians are frozen mid-stride. Defaults the output name to `<world>_static.blend` so it does not overwrite the animated build. |
| `--show-door-radius` | `flag` | `False` | Renders the $r = 1.2\,\text{m}$ automated door sensor activation radius cylinders. |
| `--show-encounters` | `flag` | `False` | Renders personal space encounter discs ($r = 0.8\,\text{m}$) at human proxemic zones. |
| `--show-energy-glow` | `flag` | `False` | Renders **side-by-side emission trails** flanking the trajectory: instantaneous power draw (viridis, left of travel) and acoustic emission level (inferno, right of travel). |
| `--glow-energy-vmin` | `float` | `0` | Power trail color-scale floor in W (pinned, constant across frames). |
| `--glow-energy-vmax` | `float` | `300` | Power trail color-scale ceiling in W. |
| `--glow-acoustic-vmin` | `float` | `40` | Acoustic trail color-scale floor in dBA. |
| `--glow-acoustic-vmax` | `float` | `65` | Acoustic trail color-scale ceiling in dBA (matches the paper Fig 1 colorbar). |
| `--trajectory-thickness` | `float` | `0.04` | Trajectory tube radius in metres ($0.04\,\text{m} = 8\,\text{cm}$ diameter). |
| `--frame` | `int` | `None` | Sets initial timeline frame to a specific telemetry sample index. |
| `--time` | `float` | `None` | Sets initial timeline frame to a specific relative timestamp in seconds. |
| `--scenario` | `str` | `None` | Scenario name or path to `scenario.yaml` (e.g. `fig4_office_desk_service`) to resolve seated vs walking pedestrian models. |

#### Example: Build Library Acoustic Scene

```bash
arena-blender-viz build \
  --world library_acoustic_partition \
  --benchmark 20260902-234905-fig6_tier2_policy_synthesis-fig6_tier2_acoustic_tuning \
  --episode 040 \
  --acoustic \
  --acoustic-mode plain \
  --output library_acoustic_plain.blend
```

#### Example: Static frame for a still image

Everything is posed at one instant and no animation data is written, so the
`.blend` opens ready to edit (lighting, materials, camera) and render:

```bash
arena-blender-viz build \
  --world office_1 \
  --benchmark 20260909-183932-hero_grand_tour-graceful_hero \
  --episode 005 \
  --acoustic \
  --static \
  --time 29.7          # optional; freezes at the worst-case acoustic frame otherwise
```

The actors are posed from the same interpolated trajectories the animated build
keys from, so **the frozen frame is identical to the animated build evaluated at
that frame**. Unlike `--no-animate-peds`, pedestrians are kept and frozen
mid-stride; combine the two for a clean architectural shot with no people.

---

### Command: `render`

Performs headless Cycles path-tracing from calibrated camera presets, with automatic OptiX GPU detection, denoising, and optional publication HUD compositing.

```bash
arena-blender-viz render --blend <path.blend> --output <path.png> [options]
```

#### Arguments & Options

| Option | Type | Default | Description |
|---|---|---|---|
| `--blend` | `path` | **Required** | Path to a `.blend` file, **or just its name** (`office_1_ep005_static`) to resolve against `--benchmark`/`--episode` and the data directories — see [Resolving `--blend` by name](#resolving---blend-by-name). |
| `--output`, `-o` | `path` | Auto | Destination PNG. Defaults to `<blend_dir>/<blend>_<camera>.png`. With several (or all) cameras this names a **directory**, and each file is suffixed with its camera name. |
| `--camera` | `str` | `Cam_TopDown_Full` | A camera preset, a comma-separated list of names, or `all` to render every camera found in the scene (see [Camera Presets](#4-camera-presets-reference)). |
| `--frame` | `int` | Scene Default | Timeline frame index to render. Defaults to worst-case acoustic hotspot frame. |
| `--resolution`, `-r` | `int int` | Scene Default | Direct render pixel dimensions (e.g. `--resolution 3840 2160`). |
| `--dpi` | `int` | `None` | Target publication DPI scale relative to standard 300 DPI baseline (e.g. `--dpi 600` doubles resolution). |
| `--samples`, `-s` | `int` | Scene Default | Cycles render path-tracing samples (e.g. `--samples 256` or `512` for crisp, noise-free large maps). |
| `--percentage` | `int` | `100` | Render scale percentage (e.g. `100`, `150`, `200`). |
| `--hud` | `flag` | `False` | Automatically extracts metrics, generates HUD card & colorbar, and composites onto image. |
| `--benchmark` | `str` | `None` | Benchmark run path (required if `--hud` is specified). |
| `--episode` | `str` | `None` | Episode ID (required if `--hud` is specified). |
| `--hud-pos` | `choice` | `auto` | HUD card corner position: `auto`, `top_left`, `top_right`, `bottom_left`, `bottom_right`. |
| `--hud-scale` | `float` | `0.25` | Fraction of rendered image width occupied by HUD card ($0.25 = 25\%$). |

#### Example: Render Hero Perspective with HUD

```bash
arena-blender-viz render \
  --blend library_acoustic_plain.blend \
  --camera Cam_3Quarter_Hero \
  --frame 1798 \
  --hud \
  --benchmark 20260902-234905-fig6_tier2_policy_synthesis-fig6_tier2_acoustic_tuning \
  --episode 040 \
  --hud-pos bottom_left \
  --output render_library_hero.png
```

#### Example: Render every camera in the scene

```bash
# Every camera object in the .blend — the built-in presets plus any you added
# by hand in the GUI — rendered in a single Blender launch.
arena-blender-viz render \
  --blend library_acoustic_plain.blend \
  --camera all \
  --frame 1798 \
  --output renders/          # each image lands in renders/<blend>_<camera>.png

# A specific subset, also one launch:
arena-blender-viz render --blend library_acoustic_plain.blend \
  --camera Cam_TopDown_Full,Cam_3Quarter_Hero -o renders/
```

---

### Command: `animate`

Renders the animated scene as a PNG frame sequence with Cycles and muxes it to H.264 MP4 (`video_renderer.py`). Blender's internal video output is not used; frame sequences are resumable and reusable for stills.

```bash
arena-blender-viz animate --blend <path.blend> --output <path.mp4> [options]
```

#### Arguments & Options

| Option | Type | Default | Description |
|---|---|---|---|
| `--blend` | `path` | **Required** | Path to a `.blend` file, or just its name to resolve against `--benchmark`/`--episode` (see [Resolving `--blend` by name](#resolving---blend-by-name)). |
| `--output`, `-o` | `path` | **Required** | Destination MP4 path. Frames land in `<output>_frames/` next to it. With several (or all) cameras one MP4 is written per camera, suffixed with its name. |
| `--camera` | `str` | `Cam_TopDown_Full` | A camera preset, a comma-separated list of names, or `all` to render every camera found in the scene. |
| `--start` / `--end` | `int` | `1` / `scene.frame_end` | Frame range. Frame $f$ maps to time $(f-1)/\text{fps}$, matching the acoustic MOVIE texture timeline (`frame_start=1`, `frame_offset=0`) exactly. |
| `--stride` | `int` | `1` | Render every Nth frame. $>1$ gives a time-lapse preview. |
| `--fps` | `float` | `30.0` | Output playback frame rate. |
| `--resolution`, `-r` | `int int` | Scene Default | Render pixel dimensions (e.g. `--resolution 1920 810`). |
| `--samples`, `-s` | `int` | Scene Default | Cycles samples override. |
| `--percentage` | `int` | `100` | Render scale percentage. |
| `--crf` | `int` | `18` | H.264 CRF quality for the imageio-ffmpeg mux. |
| `--frames-dir` | `path` | Auto | Explicit directory for PNG frames. |
| `--only-missing-frames` | `flag` | `False` | Skip frames whose PNG already exists (resume interrupted renders). |

The Cycles seed is pinned for temporal stability; muxing uses `imageio-ffmpeg` (bundled ffmpeg, no system dependency) with a cv2 `mp4v` fallback. Preview iterations typically run `--stride 10 --samples 32`, finals run `--stride 1 --samples 256`.

#### Example: Preview + final

```bash
arena-blender-viz animate --blend hospital_1_acoustic.blend --camera Cam_TopDown_Full \
  --stride 10 --samples 32 --resolution 960 540 -o hero_preview.mp4

arena-blender-viz animate --blend hospital_1_acoustic.blend --camera Cam_TopDown_Full \
  --stride 1 --samples 256 --resolution 1920 810 -o hero.mp4

# Every camera at once, one MP4 each (`hero_Cam_TopDown_Full.mp4`, ...).
# One Blender launch, one .blend open, N frame sequences.
arena-blender-viz animate --blend hospital_1_acoustic.blend --camera all \
  --stride 10 --samples 32 --resolution 960 540 -o hero.mp4
```

---

### Command: `hud`

Generates standalone publication telemetry HUD cards, continuous false-color colorbars, or composites an existing render with telemetry cards without re-rendering in Blender.

```bash
arena-blender-viz hud --benchmark <bench> --episode <ep> [options]
```

#### Arguments & Options

| Option | Type | Default | Description |
|---|---|---|---|
| `--benchmark` | `str` | **Required** | Benchmark run directory or name under `u:/data/benchmarks/`. |
| `--episode` | `str` | **Required** | Episode identifier (e.g. `040`). |
| `--image` | `path` | `None` | Optional base image to overlay HUD card and colorbar onto. |
| `--pos` | `choice` | `auto` | Overlay position on base image. |
| `--scale` | `float` | `0.25` | Overlay card scale relative to base image width. |
| `--output`, `-o` | `path` | Auto | Output path for card or composited image. |

#### Example: Standalone HUD Generation & Compositing

```bash
arena-blender-viz hud \
  --benchmark 20260902-234905-fig6_tier2_policy_synthesis-fig6_tier2_acoustic_tuning \
  --episode 040 \
  --image my_custom_render.png \
  --pos top_right \
  --output my_custom_render_with_hud.png
```

---

## 3. Dynamic Acoustic Video (MP4) Pipeline

For physical wave propagation (e.g. acoustic emission, regional speed envelopes), static single-frame PNG snapshots fail to capture temporal phenomena like sound leakage through opening doors. The pipeline supports full **30-fps dynamic MP4 video textures**.

### Generating the Raw MP4 Video

The canonical generator is the `arena_evaluation` texture pipeline (see `arena_evaluation` presentation README), invoked per episode as:

```bash
python -m arena_evaluation.cli acoustic texture \
  --benchmark-dir <run> --episode 040 --vmin 20 --vmax 60
```

which writes `plots/<episode>_acoustic_raw.mp4` (auto-resolved by `build --acoustic`) plus a pinned `<episode>_acoustic_texture.yaml` manifest. It is built on the C++ acoustic impedance solver (`compute_attenuations`) and `AcousticFieldRenderer`:

```python
from arena_evaluation.presentation.plot_types.acoustic_field import AcousticFieldRenderer
from arena_evaluation.processing.acoustics.door_map import build_pixel_tl, door_segments
from arena_evaluation.processing.acoustics.door_state import DoorStateTimeline
from arena_evaluation.processing.acoustics.impedance_grid import compute_attenuations
```

Key principles of the video generator:
1. **Physical Spatial Resolution**: Downsampled by 2 to $0.1\,\text{m/px}$ ($480 \times 340$ grid matching $[0, 48] \times [0, 34]\,\text{m}$ world bounds).
2. **Spatial-Temporal Caching**: Solver calls are cached when $\Delta d \le 0.04\,\text{m}$ and door aperture is unchanged, speeding up calculation from 18 minutes to $\approx 2$ minutes.
3. **Decibel Colormapping**: Exact calibration using Matplotlib `inferno` colormap ($v_{\min} = 20.0\,\text{dBA}$, $v_{\max} = 60.0\,\text{dBA}$).
4. **OpenCV VideoWriter**: Writes BGR frames to `.mp4` using `mp4v` codec at 30.0 fps ($N = 4,281$ frames for 142.7s duration).

### Timeline Synchronization in Blender

When an `.mp4` file is passed via `--acoustic-overlay` or discovered in `plots/`:
- Blender configures the texture node with `source = 'MOVIE'`, `use_auto_refresh = True`, `frame_start = 1`, and `frame_duration = 4281`.
- Scrubbing the timeline anywhere from Frame 1 to Frame 4281 updates the floor sound field in exact synchronization with robot pose, door position, and pedestrian stride phases.

---

## 4. Camera Presets Reference

Every generated Blender scene includes calibrated cameras positioned according to architectural bounds:

| Camera Name | Type | Focal / Ortho | Description |
|---|---|---|---|
| `Cam_3Quarter_Hero` | Perspective | $50\,\text{mm}$ | Elevated 3/4 isometric perspective overlooking the primary action area and partition doorways. |
| `Cam_TopDown` | Orthographic | Auto-fit ($48 \times 34\,\text{m}$) | Architectural plan view covering the active simulation zones. |
| `Cam_TopDown_Full` | Orthographic | Auto-fit ($56 \times 40\,\text{m}$) | Top-down overview capturing the entire world canvas and exterior bounds. |
| `Cam_TopDown_Ward` | Orthographic | Auto-fit ($24 \times 18\,\text{m}$) | Targeted top-down framing focused on patient rooms and quiet study halls. |
| `Cam_Corridor_EyeLevel` | Perspective | $35\,\text{mm}$ | First-person / human eye-level ($Z = 1.65\,\text{m}$) perspective looking down hallways. |

### Selecting cameras

`--camera` accepts three forms, on both `render` and `animate`:

| Value | Effect |
|---|---|
| `Cam_TopDown_Full` | That one camera (default). |
| `Cam_TopDown_Full,Cam_3Quarter_Hero` | Exactly those cameras. |
| `all` (or `*`) | **Every camera in the `.blend`.** |

`all` is resolved inside Blender, so it picks up cameras added by hand in the GUI — not just the presets above. This is why the names in an `all` run are only known once the file is open, and why the output paths are derived there.

Every selection is rendered in **a single Blender launch**: opening the `.blend` and building the render state costs far more than the extra frames, so N cameras cost roughly one startup plus N renders rather than N startups.

Output layout:

- **One camera** — `--output` is the exact file, unchanged from previous versions. Omitted, it defaults to `<blend_dir>/<blend>_<camera>.png`.
- **Several / all** — `--output` names a **directory** (or a filename, whose stem becomes a prefix). Files are written as `<blend>_<camera>.png`, so `--camera all -o renders/` gives `renders/library_acoustic_plain_Cam_TopDown_Full.png` and so on. For `animate`, one MP4 is written per camera and each frame sequence gets its own `frames/<camera>/` directory.

### Resolving `--blend` by name

`--blend` takes a full path, but a **bare name is usually enough** — `build` writes scenes to `<benchmark>/blender/`, so the benchmark already implies the directory:

```bash
arena blender render \
  --camera all \
  --benchmark 20260909-183932-hero_grand_tour-graceful_hero \
  --episode episode_005 \
  --blend office_1_ep005_static \
  --dpi 400
```

Resolution order (first hit wins, and the chosen path is echoed back):

1. An existing file — used as-is. A directory works too, if it holds exactly one `.blend`.
2. `<benchmark>/blender/<name>[.blend]` — where `build` writes.
3. `<benchmark>/<name>`, then the episode directory.
4. `<data>/blender/<world>/<name>` and `<data>/benchmarks/*/blender/<name>`.

The `.blend` suffix is optional, and an episode tag is filled in when absent: `--blend office_1 --episode 005` finds `office_1_ep005.blend` (falling back to `office_1_ep005_static.blend`). On a miss the error lists what was searched *and* the scenes sitting in the most likely directory, so a typo is usually self-correcting.

## 5. Shading & Scientific False-Color Fidelity

To ensure false-color heatmaps remain scientifically accurate and match publication colorbars:
1. **Zero Glare & Zero Shadows (`ShaderNodeLightPath`)**:
   - `Is Camera Ray == 1`: Evaluates as pure `ShaderNodeEmission` (Strength = 1.0). Overhead area lights and furniture casting shadows do **not** darken or distort the floor dB values.
   - `Is Camera Ray == 0`: Indirect bounce light is cast onto wall bases and furniture, integrating the sound field naturally into the 3D environment.
2. **Color Management Transform**:
   - Set to `scene.view_settings.view_transform = 'Standard'` (disables filmic or AgX tone-mapping curves that compress high/low saturated colors).
3. **Trajectory Ribbon**:
   - Distinct laser crimson emission (`#FF0000`) elevated at $Z = 0.08\,\text{m}$ with an $8\,\text{cm}$ diameter poly-curve bevel.

---

## 6. Architecture & Data Directory Structure

The visualization pipeline places all artifacts, scenes, and renders under the shared persistent `data/` directory instead of cluttering package source directories:

```
data/
├── benchmarks/
│   └── <benchmark_run_id>/
│       ├── episodes/
│       ├── blender/                       # Auto-placed .blend files & _bundle.json for this run
│       │   ├── <world>_ep001.blend
│       │   └── <world>_ep001_bundle.json
│       ├── hud/                           # Standalone HUD cards and colorbars
│       └── plots/                         # Acoustic heatmaps & videos
├── blender/                               # Standalone world scenes (without benchmark runs)
│   ├── <world_name>/
│   │   ├── <world_name>.blend
│   │   └── <world_name}_bundle.json
│   └── renders/                           # Publication renders and composited images
└── blender_cache/
    └── glb/                               # Converted 3D GLB assets (Jackal, Arenian, furniture)
                                           #   regenerated on demand — see "Derived assets" below

arena_blender_viz/
├── arena_blender_viz/
│   ├── cli.py                     # CLI entry point (build, render, animate, hud)
│   ├── bundle_builder.py          # Extracts telemetry, resolves models, exports JSON bundle
│   ├── world_parser.py            # Parses world.yaml (zones, walls, doors, entities)
│   ├── model_converter.py         # Converts DAE/OBJ/BLEND to GLB, cleans materials & transforms
│   ├── blender_scene_builder.py   # Headless Blender Python script assembling 3D scenes
│   ├── video_renderer.py          # Animation frame-sequence rendering + MP4 muxing
│   └── hud_generator.py           # Generates telemetry cards, colorbars, and composites
├── pyproject.toml                 # Package definition and dependencies
└── README.md                      # This documentation
```

### Derived assets

Three families of GLB are consumed by the scene builder but correspond to no `model_id`, so
`model_converter.py` derives them during `build`. They are cached with a version sidecar
(`.walkver` / `.robotver`) and regenerate automatically when their source or the bake version
changes — nothing has to be run by hand, and deleting the cache is safe.

| Asset | Source | Produced by |
|---|---|---|
| `Common_arenian_idle.glb` | `_assets/default/Common/Human/arenian/clips/idle.dae` | `ModelConverter.get_human_phase_glbs()` |
| `Common_arenian_walk_0..3.glb` | `…/arenian/clips/walk.dae`, sampled at 4 evenly spaced phases | `ModelConverter.get_human_phase_glbs()` |
| `jackal_robot.glb` | `data/blender/robots_cache/jackal/robot.blend` | `ModelConverter.get_robot_glb()` |

Notes:
- Walk phases are baked **in place**: the clip's root-joint horizontal travel is pinned, because the
  builder drives pedestrian position from telemetry and re-applies stride length itself
  (`STRIDE_LEN = 1.151 m`). Leaving root motion in causes pedestrians to surge.
- All five human GLBs share identical mesh topology, which is what lets the builder bake them into
  `Walk_0..3` shape keys on the idle mesh.
- `.blend` cannot be read by trimesh/pycollada, so `get_robot_glb()` is the one conversion that
  shells out to Blender. A pre-existing `jackal_robot.glb` newer than the `.blend` and lacking a
  sidecar is treated as hand-authored and left alone.

---

## 7. Added Functionality & Fixes

### Seated arenian pose bake (2026-09-09)

`arenian_seated` (and any `*_seated` human) binds its skinned mesh in a plain **standing** pose — the seated posture lives only in the `clips/sitting.dae` animation (the model's SDF maps it as the "idle" clip). Exporting bind-pose geometry therefore produced a standing character wherever a seated observer was placed. `model_converter.py` now detects seated model folders and **bakes the clip's final frame onto the skin** (gazebo-actor semantics: each clip channel replaces the matching joint's node transform), so `Common_arenian_seated.glb` is a genuinely seated, textured static mesh (~1.22 m tall). Seated bakes are gated on the model name containing `"seated"`; any other skinned model (standing arenian, workers, …) keeps the unchanged bind-pose conversion. Baked GLBs carry a `<glb>.posever` sidecar, so caches produced before pose baking regenerate automatically; the legacy nested cache copy (`Common_Human/arenian_seated.glb`) is refreshed in the same pass.

### Side-by-side emission trails (`--show-energy-glow`)

Enabling `--show-energy-glow` builds two wide emission strips flanking the trajectory ribbon, colored by the robot's **instantaneous** telemetry at each point:

- **Power trail** (left of travel): `power_w` through a 32-anchor `viridis` LUT.
- **Acoustic trail** (right of travel): `acoustic_dba` through a 32-anchor `inferno` LUT (matches the floor texture and HUD colorbar exactly).

Colormap limits are **pinned per axis** and constant across every frame of an animation (GEMINI §12): `--glow-energy-vmin/vmax` (default 0/300 W, matching the paper Fig 1 power axis) and `--glow-acoustic-vmin/vmax` (default 40/65 dBA, matching the paper Fig 1 colorbar). Values outside the bounds clamp to the colormap ends. Scene objects: `trajectory_energy_glow`, `trajectory_acoustic_glow`.

### Additive acoustic floor mode (`--acoustic-mode additive`)

The normal white architectural floor remains visible everywhere; the acoustic field is overlaid **only where the texture is non-black**. Camera rays mix between a white Principled BSDF and the color-true field emission using the texture luminance as the mask (RGBToBW → MixShader), so colored pixels stay physically accurate while black pixels show the plain floor.

### Multi-camera rendering (`--camera all`)

`render` and `animate` accept `--camera all` (or `*`) to render **every camera object in the `.blend`** — resolved inside Blender, so hand-added GUI cameras are included, not just the presets. A comma-separated list selects a subset. All cameras render in **one Blender launch**: opening the `.blend` dominates, so N cameras cost one startup plus N renders.

This replaced two blocks of duplicated `--python-expr` code (the still path and the frame path each carried their own copy of the Cycles device setup) with two template constants in `video_renderer.py` sharing `_GPU_CONFIG` and `_CAMERA_RESOLVE`.

Two robustness fixes came with it:

- **A failed render now fails.** Blender exits `0` even when `--python-expr` raises, so a missing camera or a render that never started used to print `[OK] Render saved` regardless. Background invocations now pass `--python-exit-code 1`, and the scripts raise on "no renderable camera".
- **`--output` may be omitted** on `render` (it was `required=True` while a default path already existed in the code, unreachable). Defaults to `<blend_dir>/<blend>_<camera>.png`.

Output paths are reported back from Blender as a **file name only** (`[RENDERED] <camera>\t<file>`), never a full path, so the `\\wsl.localhost\...` UNC forms `_windows_form` produces never have to be translated back into POSIX paths. `--hud` now composites onto every rendered image rather than just the first.

### Lighting: suns, bounce fill, and AO

Four sources, plus a per-zone downlight in each zone:

| Light | Type | Energy | Direction |
|---|---|---|---|
| `ArchitecturalKeyLight` | SUN | 4.5 | from +X +Y, 32° from zenith |
| `SkylightSun` | SUN | 2.5 | from −X +Y, 52° from zenith |
| `BounceFillLight` | SUN, **shadowless** | 1.8 | from −Y, 45° elevation |
| `ZenithFillLight` | AREA, `span × 1.1` at Z=11 | 220 | straight down |
| `Light_<zone>` | AREA at Z=2.35 | 80 + 15·√(area) | straight down |
| World background | — | 0.25 | uniform `(0.90, 0.93, 0.96)` |

**Both suns sit on the +Y side**, so any wall whose normal faces −Y received no direct light from either and rendered as near-black. Ambient alone cannot fix this: the same geometry that shadows the wall also occludes the sky, so raising world strength lifts the midtones but leaves the dark tail where it is.

Measured on `office_1_ep005` through `Cam_3Quarter_Hero`, over wall pixels isolated by an emission ID pass (wall→magenta, everything else→black), toggling only the fill light and the AO values on a single scene:

| wall pixels | p1 | p5 | p25 | median | p75 | < 16/255 | < 32/255 | < 64/255 |
|---|---|---|---|---|---|---|---|---|
| before (no fill, AO 0.85) | 7 | 33 | 78 | 136 | 181 | 2.0% | 4.6% | **16.8%** |
| after (fill + AO 0.35) | 43 | 79 | 147 | 167 | 193 | 0.0% | 0.2% | **2.8%** |

The darkest wall pixels are ~6× brighter and the proportion below 64/255 drops six-fold, while the distribution stays tight enough to keep directional shading. The fill is deliberately `use_shadow = False` — a shadow-casting fill would be blocked by the very walls it exists to light.

`Mat_Wall` also carried an over-strong ambient-occlusion term — its base colour is `Mix(A, ramp(AO), MULTIPLY, f)`, which scales albedo by `(1−f) + f·ramp(AO)`, so the old `f=0.85` with a `0.28` dark stop crushed occluded walls to **37% albedo** before any lighting was applied. Now `f=0.35` with a `0.62` dark stop. (`Mat_Floor` still carries the old `f=0.8` / `0.35` values — untouched, as acoustic builds replace it entirely.)

### Pedestrian walk-cycle fix

The walk-phase GLBs (`Common_arenian_idle/walk_0..3.glb`) live in `data/blender_cache/glb`, but the scene builder previously searched a bundle-relative `.cache/glb` that never exists, silently disabling the 4-phase stride shape keys. The cache directory is now resolved **content-based** (probes model-path parent directories for the arenian idle/walk assets, independent of dict ordering) and the walk shape keys keyframe per frame via continuous stride phase $\phi = s / L_{\text{stride}} \pmod 1$.

### WSL path handling (Windows Blender + WSL workspace)

Blender on Windows applies its WSL path mapping inconsistently, so the scene builder and CLI now normalize explicitly:

- `/opt/arena_ws` is normalized to `/home/nelson/arena_ws` before existence checks and image loads (Blender maps `/home` but not `/opt`, and the symlink is unresolvable via UNC).
- `bpy.data.images.load` receives the explicit `\\wsl.localhost\Ubuntu\...` UNC form (it does not map POSIX paths), while gltf imports keep POSIX (they do map it).
- `os.path.normpath` is applied only to Windows-style paths (it would corrupt POSIX paths into root-relative `\home\...`).
- CLI `build`/`render`/`animate` convert POSIX arguments to UNC via `video_renderer._windows_form` when running under WSL (identity on native Windows).
