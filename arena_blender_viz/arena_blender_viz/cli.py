"""
cli.py: Main CLI entry point for arena-blender-viz.
Provides commands:
  arena-blender-viz build   - Generates .blend scene from world.yaml + benchmark episode
  arena-blender-viz render  - Renders image from a specific camera in a .blend scene
  arena-blender-viz animate - Renders an animation frame sequence and muxes it to MP4
  arena-blender-viz hud     - Generates publication HUD cards, color scales, or composites onto renders
"""
from __future__ import annotations

import argparse
import os
import subprocess
import sys
from pathlib import Path
from typing import Any

from .bundle_builder import BundleBuilder

import platform as _platform
if _platform.system() == "Windows":
    BLENDER_EXE = Path("C:/Program Files/Blender Foundation/Blender 5.2/blender.exe")
else:
    BLENDER_EXE = Path("/usr/bin/blender")
SCRIPT_DIR = Path(__file__).parent


def _bool_flag(v: Any) -> bool:
    if isinstance(v, bool):
        return v
    if v is None:
        return True
    return str(v).strip().lower() not in ("false", "0", "no", "f", "off")


def find_blender() -> Path:
    import shutil

    # 0. Explicit override via environment variable
    env_exe = os.environ.get("BLENDER_EXE")
    if env_exe:
        p = Path(env_exe)
        if p.is_file():
            return p

    # 1. Platform-specific well-known path
    if BLENDER_EXE.is_file():
        return BLENDER_EXE

    # 2. Anywhere on PATH (covers /usr/bin/blender, snap, conda, etc.)
    p = shutil.which("blender")
    if p:
        return Path(p)

    # 3. WSL2: Windows Blender mounted under /mnt/c  (the exe runs via WSL interop)
    #    Glob all installed versions and pick the newest one.
    _wsl_base = Path("/mnt/c/Program Files/Blender Foundation")
    if _wsl_base.is_dir():
        _wsl_hits = sorted(
            _wsl_base.glob("Blender */blender.exe"),
            key=lambda p: p.parent.name,
            reverse=True,  # newest version first
        )
        if _wsl_hits:
            return _wsl_hits[0]

    # 4. Common Linux / Docker install locations
    _linux_candidates = [
        Path("/usr/bin/blender"),
        Path("/usr/local/bin/blender"),
        Path("/snap/bin/blender"),
        Path("/opt/blender/blender"),
    ]
    for cand in _linux_candidates:
        if cand.is_file():
            return cand

    _searched = (
        ["$BLENDER_EXE (not set)", str(BLENDER_EXE), "PATH",
         str(_wsl_base / "Blender *" / "blender.exe")]
        + [str(c) for c in _linux_candidates]
    )
    raise FileNotFoundError(
        "Blender executable not found.  Searched:\n"
        + "\n".join(f"  {s}" for s in _searched)
        + "\n\nOptions:\n"
        "  • WSL:    Blender installs to C:\\Program Files\\Blender Foundation and is "
        "auto-detected via /mnt/c/Program Files/Blender Foundation/Blender X.Y/blender.exe\n"
        "  • Linux:  sudo apt install blender  (or place on PATH)\n"
        "  • Any:    set env var BLENDER_EXE=/full/path/to/blender"
    )


def resolve_data_dir() -> Path:
    if "ARENA_DATA_DIR" in os.environ:
        p = Path(os.environ["ARENA_DATA_DIR"])
        if p.is_dir():
            return p
    if "ARENA_WS_DIR" in os.environ:
        p = Path(os.environ["ARENA_WS_DIR"]) / "data"
        if p.is_dir():
            return p
    for cand in [
        Path("/opt/arena_ws/data"),
        Path("u:/data"),
        Path("/data"),
    ]:
        if cand.is_dir():
            return cand
    return Path("/opt/arena_ws/data")


def resolve_world_path(world_arg: str) -> Path:
    p = Path(world_arg)
    if p.is_file():
        return p
    search_roots: list[Path] = []
    if "ARENA_DIR" in os.environ:
        search_roots.append(Path(os.environ["ARENA_DIR"]) / "arena_simulation_setup" / "worlds")
    if "ARENA_WS_DIR" in os.environ:
        search_roots.append(Path(os.environ["ARENA_WS_DIR"]) / "src" / "Arena" / "arena_simulation_setup" / "worlds")
    search_roots.extend([
        Path("/opt/arena_ws/src/Arena/arena_simulation_setup/worlds"),
        Path("u:/src/Arena/arena_simulation_setup/worlds"),
        Path(__file__).resolve().parent.parent.parent / "arena_simulation_setup" / "worlds",
    ])
    for base_worlds in search_roots:
        candidates = [
            base_worlds / world_arg / "0" / "world.yaml",
            base_worlds / world_arg / "world.yaml",
            base_worlds / world_arg,
        ]
        for c in candidates:
            if c.is_file():
                return c
    raise FileNotFoundError(f"Could not find world.yaml for '{world_arg}' across {search_roots}")


def resolve_episode_dir(benchmark_arg: str, episode_arg: str | None = None) -> Path | None:
    bench_p = Path(benchmark_arg)
    if not bench_p.is_dir():
        search_roots: list[Path] = []
        if "ARENA_DATA_DIR" in os.environ:
            search_roots.append(Path(os.environ["ARENA_DATA_DIR"]) / "benchmarks")
        if "ARENA_WS_DIR" in os.environ:
            search_roots.append(Path(os.environ["ARENA_WS_DIR"]) / "data" / "benchmarks")
        search_roots.extend([
            Path("/opt/arena_ws/data/benchmarks"),
            Path("u:/data/benchmarks"),
            Path("/data/benchmarks"),
        ])
        for root in search_roots:
            cand = root / benchmark_arg
            if cand.is_dir():
                bench_p = cand
                break

    if not bench_p.is_dir():
        return None

    if episode_arg:
        try:
            ep_clean = str(episode_arg).lower().replace("episode_", "").replace("ep_", "").strip()
            ep_num = int(ep_clean)
            cand_ep = bench_p / "episodes" / f"episode_{ep_num:03d}"
            if cand_ep.is_dir():
                return cand_ep
        except ValueError:
            pass
        ep_dir = bench_p / "episodes" / str(episode_arg)
        if ep_dir.is_dir():
            return ep_dir

    # Default to first episode
    episodes_dir = bench_p / "episodes"
    if episodes_dir.is_dir():
        first = next(episodes_dir.glob("episode_*"), None)
        if first and first.is_dir():
            return first

    return None


def cmd_build(args: argparse.Namespace) -> None:
    world_yaml = resolve_world_path(args.world)
    episode_dir = resolve_episode_dir(args.benchmark, args.episode) if args.benchmark else None
    acoustic_png = Path(args.acoustic_overlay) if args.acoustic_overlay else None

    world_name = world_yaml.parent.parent.name if world_yaml.parent.name == "0" else world_yaml.parent.name

    if args.output:
        out_blend = Path(args.output)
    else:
        data_dir = resolve_data_dir()
        if episode_dir:
            # Place in <benchmark_dir>/blender/<world_name>_ep<num>.blend
            bench_root = episode_dir.parent.parent
            blender_out_dir = bench_root / "blender"
            try:
                ep_clean = str(episode_dir.name).lower().replace("episode_", "").replace("ep_", "").strip()
                ep_tag = f"_ep{int(ep_clean):03d}"
            except ValueError:
                ep_tag = f"_{episode_dir.name}"
            out_blend = blender_out_dir / f"{world_name}{ep_tag}.blend"
        else:
            # Place in data/blender/<world_name>/<world_name>.blend
            blender_out_dir = data_dir / "blender" / world_name
            out_blend = blender_out_dir / f"{world_name}.blend"

    out_blend.parent.mkdir(parents=True, exist_ok=True)
    bundle_json = out_blend.parent / f"{out_blend.stem}_bundle.json"

    options = {
        "animate_doors": not args.no_animate_doors,
        "animate_peds": not args.no_animate_peds,
        "show_door_radius": args.show_door_radius,
        "show_encounters": getattr(args, "show_encounters", False),
        "show_energy_glow": args.show_energy_glow,
        "glow_energy_vmin": getattr(args, "glow_energy_vmin", None),
        "glow_energy_vmax": getattr(args, "glow_energy_vmax", None),
        "glow_acoustic_vmin": getattr(args, "glow_acoustic_vmin", None),
        "glow_acoustic_vmax": getattr(args, "glow_acoustic_vmax", None),
        "trajectory_thickness": args.trajectory_thickness,
        "acoustic": args.acoustic or (args.acoustic_overlay is not None),
        "acoustic_mode": getattr(args, "acoustic_mode", "plain"),
        "frame": getattr(args, "frame", None),
        "time": getattr(args, "time", None),
        "scenario": getattr(args, "scenario", None),
    }

    print(f"[*] Building scene bundle from {world_yaml}...")
    builder = BundleBuilder(
        world_yaml_path=world_yaml,
        benchmark_episode_dir=episode_dir,
        acoustic_overlay_png=acoustic_png,
        options=options,
    )
    builder.build_bundle(bundle_json)
    print(f"[+] Bundle written to: {bundle_json}")

    # Invoke Blender to construct scene
    blender_path = find_blender()
    scene_builder_script = SCRIPT_DIR / "blender_scene_builder.py"
    from .video_renderer import _windows_form

    print(f"[*] Executing Blender scene assembly with {blender_path}...")
    cmd = [
        str(blender_path),
        "--background",
        "--python",
        _windows_form(scene_builder_script),
        "--",
        _windows_form(bundle_json),
        _windows_form(out_blend),
    ]

    res = subprocess.run(cmd)
    if res.returncode == 0:
        print(f"[OK] Successfully created Blender scene: {out_blend}")
        print(f"    Open in Blender GUI: & '{blender_path}' '{out_blend}'")
    else:
        print(f"[!] Blender exited with code {res.returncode}")
        sys.exit(res.returncode)


def cmd_render(args: argparse.Namespace) -> None:
    blend_path = Path(args.blend).resolve()
    if not blend_path.is_file():
        print(f"[!] Blend file not found: {blend_path}")
        sys.exit(1)

    if args.output:
        raw_out = str(args.output).replace("\\", "/")
        if len(raw_out) >= 2 and raw_out[1] == ":":
            out_png_posix = raw_out
        elif raw_out.startswith("/"):
            out_png_posix = raw_out
        else:
            # Relative path: put relative to blend file's parent or data/renders
            out_png_posix = str((blend_path.parent / args.output).resolve()).replace("\\", "/")
    else:
        # Default render output in blend_path's parent directory
        out_png_posix = str((blend_path.parent / f"{blend_path.stem}_{args.camera}.png").resolve()).replace("\\", "/")

    Path(out_png_posix).parent.mkdir(parents=True, exist_ok=True)
    blender_path = find_blender()
    from .video_renderer import _windows_form
    blend_arg_win = _windows_form(blend_path)
    out_png_win = _windows_form(Path(out_png_posix))

    # Map telemetry frame to animation frame if bundle exists
    target_frame = args.frame
    if target_frame is not None:
        bundle_cand = blend_path.parent / f"{blend_path.stem}_bundle.json"
        if bundle_cand.is_file():
            try:
                import json
                bdata = json.loads(bundle_cand.read_text())
                traj = bdata.get("telemetry", {}).get("robot_trajectory", [])
                fps = bdata.get("options", {}).get("fps", 30)
                if traj and target_frame < len(traj):
                    mapped = max(1, int(traj[target_frame]["t"] * fps))
                    print(f"[*] Mapping telemetry frame {target_frame} (t={traj[target_frame]['t']}s) to animation frame {mapped}")
                    target_frame = mapped
            except Exception:
                pass

    # GPU / CPU configuration and robust denoiser fallback
    python_expr = f"""
import bpy
scene = bpy.context.scene
scene.render.engine = 'CYCLES'
scene.cycles.device = 'GPU'

try:
    cprefs = bpy.context.preferences.addons['cycles'].preferences
    has_gpu = False
    for dev_type in ['OPTIX', 'CUDA', 'HIP']:
        try:
            cprefs.compute_device_type = dev_type
            cprefs.get_devices()
            devs = [d for d in cprefs.devices if d.type == dev_type]
            if devs:
                for d in devs:
                    d.use = True
                print(f'[GPU] Enabled {{dev_type}} successfully')
                has_gpu = True
                break
        except Exception:
            pass
    if not has_gpu:
        print('[CPU] Falling back to CPU render')
        scene.cycles.device = 'CPU'
except Exception as e:
    print(f'[!] Compute device configuration note: {{e}}')
    scene.cycles.device = 'CPU'

# Ensure denoising does not crash if Blender build lacks OpenImageDenoiser
try:
    csettings = scene.cycles
    denoiser_val = getattr(csettings, 'denoiser', None)
    if not denoiser_val or denoiser_val not in ('OPENIMAGEDENOISE', 'OPTIX'):
        csettings.use_denoising = False
except Exception:
    pass

# Dynamic resolution, DPI, and sampling overrides
{f"scene.render.resolution_x = {args.resolution[0]}" if getattr(args, "resolution", None) else ""}
{f"scene.render.resolution_y = {args.resolution[1]}" if getattr(args, "resolution", None) else ""}
{f"scene.render.resolution_percentage = {args.percentage}" if getattr(args, "percentage", None) else ""}
{f"scene.cycles.samples = {args.samples}" if getattr(args, "samples", None) else ""}
{f'''
# DPI scaling relative to standard 300 DPI publication baseline
dpi_scale = {args.dpi} / 300.0
scene.render.resolution_x = int(scene.render.resolution_x * dpi_scale)
scene.render.resolution_y = int(scene.render.resolution_y * dpi_scale)
''' if getattr(args, "dpi", None) else ""}

print(f"[Render Config] Resolution: {{scene.render.resolution_x}}x{{scene.render.resolution_y}} ({{scene.render.resolution_percentage}}%), Samples: {{scene.cycles.samples}}")

cam = bpy.data.objects.get('{args.camera}')
if cam:
    scene.camera = cam

{f"scene.frame_set({target_frame})" if target_frame is not None else "# Keep scene active frame (worst-case frame)"}

scene.render.filepath = r'{out_png_win}'
try:
    bpy.ops.render.render(write_still=True)
except Exception as e:
    print(f'[!] Render failed with {{e}}. Retrying with denoising disabled...')
    scene.cycles.use_denoising = False
    bpy.ops.render.render(write_still=True)

print('[OK] Render completed')
"""

    print(f"[*] Rendering camera '{args.camera}' to {out_png_posix}...")
    cmd = [
        str(blender_path),
        "--background",
        blend_arg_win,
        "--python-expr",
        python_expr,
    ]
    res = subprocess.run(cmd)
    if res.returncode == 0:
        print(f"[OK] Render saved: {out_png_posix}")
    else:
        sys.exit(res.returncode)

    # Optional HUD overlay generation
    if getattr(args, "hud", False):
        if not args.benchmark or not args.episode:
            print("[!] Note: --hud requires --benchmark and --episode to extract metrics. Skipping HUD.")
            return

        from .hud_generator import HUDGenerator
        out_p = Path(out_png_posix)
        metrics = HUDGenerator.extract_metrics(args.benchmark, args.episode)

        card_path = out_p.with_name(f"{out_p.stem}_hud_card.png")
        cb_path = out_p.with_name(f"{out_p.stem}_colorbar.png")
        comp_path = out_p.with_name(f"{out_p.stem}_with_hud.png")

        HUDGenerator.generate_colorbar(cb_path, vmin=metrics.get("vmin", 20.0), vmax=metrics.get("vmax", 100.0))
        HUDGenerator.generate_hud_card(metrics, card_path)
        HUDGenerator.composite_onto_image(
            base_image_path=out_p,
            out_image_path=comp_path,
            hud_card_path=card_path,
            colorbar_path=cb_path,
            position=getattr(args, "hud_pos", "auto"),
            hud_scale_width_pct=getattr(args, "hud_scale", 0.25),
        )
        print(f"[OK] Standalone HUD Card: {card_path}")
        print(f"[OK] Standalone Colorbar: {cb_path}")
        print(f"[OK] Publication Composite with HUD: {comp_path}")


def cmd_animate(args: argparse.Namespace) -> None:
    from .video_renderer import render_frames, mux_frames_mp4

    blend_path = Path(args.blend).resolve()
    if not blend_path.is_file():
        print(f"[!] Blend file not found: {blend_path}")
        sys.exit(1)

    out_mp4 = Path(args.output)
    out_mp4.parent.mkdir(parents=True, exist_ok=True)
    frames_dir = Path(args.frames_dir) if args.frames_dir else out_mp4.parent / f"{out_mp4.stem}_frames"

    print(f"[*] Rendering animation frames from {blend_path} (camera '{args.camera}')...")
    render_frames(
        blend_path=blend_path,
        camera=args.camera,
        frames_dir=frames_dir,
        start=args.start,
        end=args.end,
        stride=args.stride,
        resolution=args.resolution,
        percentage=args.percentage,
        samples=args.samples,
        only_missing=args.only_missing_frames,
    )

    print(f"[*] Muxing frames to {out_mp4} at {args.fps} fps...")
    mux_frames_mp4(frames_dir, out_mp4, fps=args.fps, crf=args.crf)
    print(f"[OK] Animation saved: {out_mp4}")


def cmd_hud(args: argparse.Namespace) -> None:
    from .hud_generator import HUDGenerator
    bench_p = Path(args.benchmark)
    if not bench_p.is_dir():
        search_roots: list[Path] = []
        if "ARENA_DATA_DIR" in os.environ:
            search_roots.append(Path(os.environ["ARENA_DATA_DIR"]) / "benchmarks")
        if "ARENA_WS_DIR" in os.environ:
            search_roots.append(Path(os.environ["ARENA_WS_DIR"]) / "data" / "benchmarks")
        search_roots.extend([
            Path("/opt/arena_ws/data/benchmarks"),
            Path("u:/data/benchmarks"),
            Path("/data/benchmarks"),
        ])
        for root in search_roots:
            cand = root / args.benchmark
            if cand.is_dir():
                bench_p = cand
                break

    metrics = HUDGenerator.extract_metrics(bench_p, args.episode)
    if args.output:
        out_dir = Path(args.output).parent
        stem = Path(args.output).stem
    else:
        out_dir = (bench_p / "hud") if bench_p.is_dir() else (resolve_data_dir() / "hud")
        try:
            ep_clean = str(args.episode).lower().replace("episode_", "").replace("ep_", "").strip()
            stem = f"episode_{int(ep_clean):03d}_hud"
        except ValueError:
            stem = f"episode_{args.episode}_hud"
    out_dir.mkdir(parents=True, exist_ok=True)

    cb_path = out_dir / f"{stem}_colorbar.png"
    card_path = out_dir / f"{stem}_card.png"

    HUDGenerator.generate_colorbar(cb_path, vmin=metrics.get("vmin", 20.0), vmax=metrics.get("vmax", 100.0))
    print(f"[+] Colorbar generated: {cb_path}")

    HUDGenerator.generate_hud_card(metrics, card_path)
    print(f"[+] HUD Card generated: {card_path}")

    if args.image:
        img_p = Path(args.image)
        comp_out = Path(args.output) if args.output else img_p.with_name(f"{img_p.stem}_with_hud.png")
        HUDGenerator.composite_onto_image(
            base_image_path=img_p,
            out_image_path=comp_out,
            hud_card_path=card_path,
            colorbar_path=cb_path,
            position=getattr(args, "pos", "auto"),
            hud_scale_width_pct=getattr(args, "scale", 0.25),
        )
        print(f"[+] Composited image saved: {comp_out}")


def main(argv: list[str] | None = None) -> None:
    parser = argparse.ArgumentParser(description="Arena 3.0 Blender Visualization Pipeline")
    subparsers = parser.add_subparsers(dest="command", required=True)

    # Subcommand: build
    p_build = subparsers.add_parser("build", help="Build a 3D Blender scene file from world and telemetry")
    p_build.add_argument("--world", required=True, help="World name (e.g. hospital_1) or path to world.yaml")
    p_build.add_argument("--benchmark", help="Benchmark run name or path to benchmark directory")
    p_build.add_argument("--episode", help="Episode ID (e.g. 008, 047)")
    p_build.add_argument("--acoustic-overlay", help="Path to acoustic field PNG heatmap")
    p_build.add_argument("--output", "-o", help="Output .blend file path")
    p_build.add_argument("--no-animate-doors", nargs="?", const=True, default=False, type=_bool_flag, help="Disable dynamic door sliding animation")
    p_build.add_argument("--no-animate-peds", nargs="?", const=True, default=False, type=_bool_flag, help="Disable dynamic pedestrian animation")
    p_build.add_argument("--show-door-radius", nargs="?", const=True, default=False, type=_bool_flag, help="Visualize door trigger activation radius (r=1.2m)")
    p_build.add_argument("--show-encounters", nargs="?", const=True, default=False, type=_bool_flag, help="Visualize personal space encounter disc overlays")
    p_build.add_argument("--show-energy-glow", nargs="?", const=True, default=False, type=_bool_flag,
                         help="Enable side-by-side emission trails along the trajectory: instantaneous power draw (viridis, left of travel) and acoustic emission level (inferno, right of travel)")
    p_build.add_argument("--glow-energy-vmin", type=float, default=None, help="Power trail color-scale floor in W (default: 0)")
    p_build.add_argument("--glow-energy-vmax", type=float, default=None, help="Power trail color-scale ceiling in W (default: 300)")
    p_build.add_argument("--glow-acoustic-vmin", type=float, default=None, help="Acoustic trail color-scale floor in dBA (default: 40)")
    p_build.add_argument("--glow-acoustic-vmax", type=float, default=None, help="Acoustic trail color-scale ceiling in dBA (default: 65)")
    p_build.add_argument("--acoustic", nargs="?", const=True, default=False, type=_bool_flag, help="Enable acoustics propagation floor material")
    p_build.add_argument(
        "--acoustic-mode",
        choices=["plain", "subtle", "glow", "additive"],
        default="plain",
        help="Acoustic floor rendering mode: plain (accurate non-reflective matte picture), subtle (gentle warm glow), glow (high-visibility emission), additive (white architectural floor with the field overlaid only where non-black)",
    )
    p_build.add_argument("--trajectory-thickness", type=float, default=0.04, help="Trajectory tube radius in metres")
    p_build.add_argument("--frame", type=int, default=None, help="Episode telemetry frame index (e.g. 621) or Blender animation frame")
    p_build.add_argument("--time", type=float, default=None, help="Episode relative time in seconds (e.g. 84.65)")
    p_build.add_argument("--scenario", help="Optional scenario name or path to scenario.yaml (e.g. fig4_office_desk_service)")

    # Subcommand: render
    p_render = subparsers.add_parser("render", help="Render an image from a camera preset in a .blend file")
    p_render.add_argument("--blend", required=True, help="Path to .blend file")
    p_render.add_argument("--camera", default="Cam_TopDown_Full", help="Camera name (Cam_TopDown_Full, Cam_TopDown, Cam_TopDown_Ward, Cam_3Quarter_Hero, Cam_Corridor_EyeLevel)")
    p_render.add_argument("--frame", type=int, default=None, help="Timeline frame to render (default: worst-case frame from scene)")
    p_render.add_argument("--output", "-o", required=True, help="Output PNG image path")
    p_render.add_argument("--hud", nargs="?", const=True, default=False, type=_bool_flag, help="Generate and composite publication HUD card & colorbar onto the render")
    p_render.add_argument("--benchmark", help="Benchmark run name or path (required for --hud)")
    p_render.add_argument("--episode", help="Episode ID (required for --hud)")
    p_render.add_argument("--hud-pos", default="auto", choices=["auto", "top_left", "top_right", "bottom_left", "bottom_right"], help="Position of HUD overlay on rendered image (default: auto)")
    p_render.add_argument("--hud-scale", type=float, default=0.25, help="Width fraction of image for HUD card (default: 0.25)")
    p_render.add_argument("--resolution", "-r", nargs=2, type=int, metavar=("WIDTH", "HEIGHT"), help="Render image resolution in pixels (e.g. --resolution 3840 2160)")
    p_render.add_argument("--dpi", type=int, default=None, help="Target DPI scaling factor (scales base 2148x1400 relative to standard 300 DPI, e.g. --dpi 600 doubles resolution)")
    p_render.add_argument("--samples", "-s", type=int, default=None, help="Cycles render samples (e.g. 256, 512, 1024). Overrides scene default")
    p_render.add_argument("--percentage", type=int, default=None, help="Render scale percentage (e.g. 100, 150, 200)")

    # Subcommand: animate
    p_animate = subparsers.add_parser("animate", help="Render an animation frame sequence and mux it to MP4")
    p_animate.add_argument("--blend", required=True, help="Path to .blend file")
    p_animate.add_argument("--camera", default="Cam_TopDown_Full", help="Camera name (default: Cam_TopDown_Full)")
    p_animate.add_argument("--output", "-o", required=True, help="Output MP4 path")
    p_animate.add_argument("--start", type=int, default=None, help="First frame (default: 1)")
    p_animate.add_argument("--end", type=int, default=None, help="Last frame (default: scene.frame_end)")
    p_animate.add_argument("--stride", type=int, default=1, help="Render every Nth frame (default: 1; >1 gives a time-lapse preview)")
    p_animate.add_argument("--fps", type=float, default=30.0, help="Output playback fps (default: 30)")
    p_animate.add_argument("--resolution", "-r", nargs=2, type=int, metavar=("WIDTH", "HEIGHT"),
                           help="Render image resolution in pixels (e.g. --resolution 1920 810)")
    p_animate.add_argument("--samples", "-s", type=int, default=None, help="Cycles render samples (e.g. 128, 256). Overrides scene default")
    p_animate.add_argument("--percentage", type=int, default=None, help="Render scale percentage (e.g. 100, 150, 200)")
    p_animate.add_argument("--crf", type=int, default=18, help="H.264 CRF quality for imageio-ffmpeg mux (default: 18)")
    p_animate.add_argument("--frames-dir", help="Directory for PNG frame files (default: <output>_frames next to the MP4)")
    p_animate.add_argument("--only-missing-frames", action="store_true",
                           help="Skip frames whose PNG already exists (resume interrupted render)")

    # Subcommand: hud
    p_hud = subparsers.add_parser("hud", help="Generate standalone HUD telemetry card, color scale, or composite onto image")
    p_hud.add_argument("--benchmark", required=True, help="Benchmark run name or path")
    p_hud.add_argument("--episode", required=True, help="Episode ID")
    p_hud.add_argument("--image", help="Optional rendered image to composite HUD onto")
    p_hud.add_argument("--pos", default="auto", choices=["auto", "top_left", "top_right", "bottom_left", "bottom_right"], help="Position on image (default: auto)")
    p_hud.add_argument("--scale", type=float, default=0.25, help="Width fraction of image for HUD card (default: 0.25)")
    p_hud.add_argument("--output", "-o", help="Output path for composited image or card")

    args = parser.parse_args(argv)
    if args.command == "build":
        cmd_build(args)
    elif args.command == "render":
        cmd_render(args)
    elif args.command == "animate":
        cmd_animate(args)
    elif args.command == "hud":
        cmd_hud(args)


if __name__ == "__main__":
    main()
